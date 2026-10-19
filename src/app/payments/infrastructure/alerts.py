"""Operator alerts (VS-024 plan 3.5): an audit row, then an in-app notification and an
outbox email per active, verified administrator, then an error log. Each delivery runs
in its own SAVEPOINT, so a failed alert never rolls back the money write around it."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engagement.public import NotificationType, create_notification
from app.identity.public import active_administrator_contacts
from app.ordering.public import LockedOrder
from app.payments.domain.alerts import AlertKind, alert_payload, repeat_window
from app.payments.domain.payments import Payment
from app.platform.public import SqlAuditWriter, SqlOutboxWriter

logger = structlog.get_logger()

ALERT_ACTION = "payment.alert_raised"
ALERT_TEMPLATE = "admin_payment_alert"


class SqlPaymentAlerts:
    """On the caller's session; never commits. Only ids and the kind reach the log."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def raise_alert(
        self,
        kind: AlertKind,
        *,
        payment_id: UUID | None,
        order_id: UUID | None,
        details: dict[str, Any],
        dedupe_window: timedelta | None,
    ) -> bool:
        payload = alert_payload(kind, payment_id=payment_id, order_id=order_id, details=details)
        try:
            async with self._session.begin_nested():
                # Last lock of the transaction (after any orders, lines, payments): two
                # raisers of one alert serialise here, so the check below sees the other.
                key = func.hashtextextended(_key(kind, payload), 0)
                await self._session.execute(select(func.pg_advisory_xact_lock(key)))
                if await self._raised(kind, payment_id, payload, dedupe_window):
                    return False
                await SqlAuditWriter(self._session).record(
                    actor_user_id=None,
                    action=ALERT_ACTION,
                    entity_type="payment",
                    entity_id=payment_id,
                    after_data={k: v for k, v in payload.items() if k != "event"},
                )
                contacts = await active_administrator_contacts(self._session)
        except Exception as exc:
            # The type only: a database error's text carries its bound parameters.
            await logger.aerror(
                "payment_alert_failed",
                kind=str(kind),
                payment_id=_id(payment_id),
                error=type(exc).__name__,
            )
            return False
        failed = 0
        for admin_id, email in contacts:
            failed += await self._deliver(admin_id, email, payload)
        await logger.aerror(
            "payment_alert",
            kind=str(kind),
            payment_id=_id(payment_id),
            order_id=_id(order_id),
            administrators=len(contacts),
            failed_deliveries=failed,
        )
        return True

    async def _raised(
        self,
        kind: AlertKind,
        payment_id: UUID | None,
        payload: dict[str, Any],
        window: timedelta | None,
    ) -> bool:
        """Per payment, or per provider when there is no payment (`ix_audit_logs_*`)."""
        matching = {"kind": str(kind)}
        if payment_id is None and payload.get("provider"):
            matching["provider"] = str(payload["provider"])
        return await SqlAuditWriter(self._session).recorded(
            action=ALERT_ACTION,
            entity_type="payment",
            entity_id=payment_id,
            matching=matching,
            since=None if window is None else datetime.now(UTC) - window,
        )

    async def _deliver(self, admin_id: UUID, email: str, payload: dict[str, Any]) -> int:
        """How many of the two deliveries failed; each failure rolls back alone."""
        failed = 0
        try:
            async with self._session.begin_nested():
                await create_notification(
                    self._session,
                    user_id=admin_id,
                    notification_type=NotificationType.PAYMENT,
                    payload=payload,
                )
        except Exception:
            failed += 1
            await logger.awarning(
                "payment_alert_delivery_failed", channel="notification", admin_id=str(admin_id)
            )
        try:
            async with self._session.begin_nested():
                await SqlOutboxWriter(self._session).add(
                    user_id=admin_id,
                    recipient_email=email,
                    template=ALERT_TEMPLATE,
                    payload=payload,
                )
        except Exception:
            failed += 1
            await logger.awarning(
                "payment_alert_delivery_failed", channel="email", admin_id=str(admin_id)
            )
        return failed


class SqlLateCaptureAlerts:
    """VS-024's `LateCaptureSink`: one `late_capture` alert per payment, ever (3.5).
    VS-030 adds the refund obligation beside it."""

    def __init__(self, alerts: SqlPaymentAlerts) -> None:
        self._alerts = alerts

    async def late_capture_recorded(
        self,
        locked: LockedOrder,
        payment: Payment,
        *,
        captured_amount_cents: int | None,
        captured_currency: str | None,
        reason: str,
        at: datetime,
    ) -> None:
        await self._alerts.raise_alert(
            AlertKind.LATE_CAPTURE,
            payment_id=payment.id,
            order_id=locked.order.id,
            details={
                "order_number": locked.order.order_number,
                "reason": reason,
                "attempt_status": payment.status.value,
                "captured_amount_cents": captured_amount_cents,
                "captured_currency": captured_currency,
                "expected_amount_cents": payment.amount_cents,
            },
            dedupe_window=None,
        )


def _id(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _key(kind: AlertKind, payload: dict[str, Any]) -> str:
    """The de-duplication entity: the payment, or the provider for a provider alert."""
    entity = payload.get("payment_id") or payload.get("provider") or ""
    return f"payment_alert:{kind}:{entity}"


async def alert(
    factory: async_sessionmaker[AsyncSession],
    kind: AlertKind,
    *,
    payment_id: UUID | None = None,
    order_id: UUID | None = None,
    details: dict[str, Any],
) -> bool:
    """A job's alert in its own short transaction, repeated per `repeat_window(kind)`."""
    async with factory() as session, session.begin():
        return await SqlPaymentAlerts(session).raise_alert(
            kind,
            payment_id=payment_id,
            order_id=order_id,
            details=details,
            dedupe_window=repeat_window(kind),
        )
