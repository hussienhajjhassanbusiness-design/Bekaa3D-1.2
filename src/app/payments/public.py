"""Payments' published surface (frozen at VS-023 Checkpoint 2). Another context imports
from here or from `app.payments.application.ports` only; callers type against the ports."""

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ordering.public import LockedOrder
from app.payments.application.ports import (
    CreatedPayment,
    CreatePayment,
    PaymentProviderPort,
)
from app.payments.application.services import refunds as _refunds
from app.payments.application.services.payments import (
    fail_attempt,
    record_provider_reference,
    start_online_payment,
)
from app.payments.domain import limits
from app.payments.domain.alerts import AlertKind, repeat_window
from app.payments.domain.exceptions import (
    CashAlreadyRecordedError,
    ManualReleaseRefusedError,
    OrderNotFoundError,
    OrderTotalMismatchError,
    PaymentConfigurationError,
    ProviderUnavailableError,
    RefundExceedsAvailableError,
)
from app.payments.domain.limits import CHECKOUT_RATE_LIMIT, CHECKOUT_RATE_WINDOW_SECONDS
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.domain.payments import OrderPaymentRow
from app.payments.infrastructure.alerts import SqlPaymentAlerts
from app.payments.infrastructure.cash_payments import insert_cash_payment, order_payment_rows
from app.payments.infrastructure.chargebacks import ChargebackRow, order_chargebacks
from app.payments.infrastructure.manual import confirm_payment_manually
from app.payments.infrastructure.order_payments import SqlOrderPaymentReader, SqlPaymentInFlight
from app.payments.infrastructure.payments import SqlPaymentAttempts, SqlPaymentStore
from app.payments.infrastructure.providers.factory import configured_payment_providers
from app.payments.infrastructure.reconcile import reconcile_stuck
from app.payments.infrastructure.refund_side import refund_deps
from app.payments.infrastructure.refund_views import (
    CustomerRefund,
    RefundBalances,
    admin_refunds,
    customer_refunds,
)
from app.payments.infrastructure.refunds import RefundRow, order_refund_facts
from app.payments.infrastructure.release import release_order_by_admin, release_stale
from app.payments.infrastructure.reports import (
    PaidPaymentRow,
    chargeback_excess_cents,
    paid_payment_page,
    paid_payments_between,
    refund_covered_lines,
    refunded_cents_by_line,
    unsettled_refund_exists,
)
from app.payments.infrastructure.verification import (
    apply_provider_result,
    verify_event,
    verify_payment,
    verify_unprocessed,
)

logger = structlog.get_logger()

__all__ = [
    "CHECKOUT_RATE_LIMIT",
    "CHECKOUT_RATE_WINDOW_SECONDS",
    "CancellationRefund",
    "CashAlreadyRecordedError",
    "ChargebackRow",
    "CreatePayment",
    "CreatedPayment",
    "CustomerRefund",
    "ManualReleaseRefusedError",
    "OrderNotFoundError",
    "OrderPaymentRow",
    "OrderTotalMismatchError",
    "Outcome",
    "PaidPaymentRow",
    "PaymentConfigurationError",
    "PaymentProviderPort",
    "ProviderResult",
    "ProviderUnavailableError",
    "RefundBalances",
    "RefundExceedsAvailableError",
    "RefundRow",
    "admin_refunds",
    "alert_refund_integrity",
    "announce_manual_payment",
    "apply_provider_result",
    "chargeback_excess_cents",
    "configured_payment_providers",
    "confirm_payment_manually",
    "create_cancellation_refund",
    "customer_refunds",
    "fail_attempt",
    "insert_cash_payment",
    "limits",
    "order_chargebacks",
    "order_payment_reader",
    "order_payment_rows",
    "order_refund_facts",
    "paid_payment_page",
    "paid_payments_between",
    "payment_attempts",
    "payment_in_flight",
    "payment_store",
    "reconcile_stuck",
    "record_provider_reference",
    "refund_balances",
    "refund_covered_lines",
    "refunded_cents_by_line",
    "release_order_by_admin",
    "release_stale",
    "start_online_payment",
    "unsettled_refund_exists",
    "verify_event",
    "verify_payment",
    "verify_unprocessed",
]


def payment_attempts(
    session: AsyncSession, providers: Mapping[str, PaymentProviderPort]
) -> SqlPaymentAttempts:
    """Ordering's `PaymentAttempts` port on the caller's session (checkout Tx1)."""
    return SqlPaymentAttempts(session, providers)


def order_payment_reader(session: AsyncSession) -> SqlOrderPaymentReader:
    """Ordering's `OrderPaymentReader` for the customer's order history (VS-025)."""
    return SqlOrderPaymentReader(session)


def payment_store(session: AsyncSession) -> SqlPaymentStore:
    """The payment repository on the caller's session (checkout Tx2)."""
    return SqlPaymentStore(session)


def payment_in_flight(session: AsyncSession) -> SqlPaymentInFlight:
    """Negotiation's `PaymentInFlight` for `expire_offers` (VS-041)."""
    return SqlPaymentInFlight(session)


CancellationRefund = _refunds.CancellationRefund


async def refund_balances(
    session: AsyncSession, locked: LockedOrder
) -> tuple[dict[UUID, int], int]:
    """Per-line and payment balances; locks the payments. The caller holds
    `lock_order_for_change` (VS-030 plan 3.7)."""
    return await _refunds.refund_balances(refund_deps(session), locked)


async def create_cancellation_refund(
    session: AsyncSession,
    locked: LockedOrder,
    *,
    cancelling: frozenset[UUID],
    reason: str,
    actor_user_id: UUID,
    by_customer: bool,
    at: datetime,
    request_id: str | None = None,
    ip_hash: str | None = None,
) -> CancellationRefund | None:
    """The cancel's refund for every cancelled line's whole remaining balance (ADR-043), under
    the caller's `lock_order_for_change`; the caller cancels the lines and recomputes last.
    A customer's own cancel is requested by them and approved by no administrator."""
    return await _refunds.create_cancellation_refund(
        refund_deps(session),
        locked,
        cancelling=cancelling,
        reason=reason,
        ctx=_refunds.AuditContext(actor_user_id, request_id, ip_hash),
        at=at,
        approved_by=None if by_customer else actor_user_id,
    )


async def alert_refund_integrity(
    session_factory: async_sessionmaker[AsyncSession],
    exc: OrderTotalMismatchError | RefundExceedsAvailableError,
    order_id: UUID,
) -> None:
    """A cancel's refund refused on integrity (VS-031): an error log and, for Q-2, the
    `refund_integrity` alert, in their own transaction after the cancel rolled back."""
    await logger.aerror("cancel_refund_refused", order_id=str(order_id), error=type(exc).__name__)
    async with session_factory() as session, session.begin():
        await SqlPaymentAlerts(session).raise_alert(
            AlertKind.REFUND_INTEGRITY,
            payment_id=getattr(exc, "payment_id", None),
            order_id=order_id,
            details={"reason": "order_total_mismatch"}
            if isinstance(exc, OrderTotalMismatchError)
            else {"reason": "refund_exceeds_available"},
            dedupe_window=repeat_window(AlertKind.REFUND_INTEGRITY),
        )


async def announce_manual_payment(
    session: AsyncSession, *, payment_id: UUID, order_id: UUID, order_number: str
) -> None:
    """ADR-049, VS-050 Q2: tell every administrator a `manual` order awaits their call. On
    the caller's session, as its last lock; at most once per payment."""
    await SqlPaymentAlerts(session).raise_alert(
        AlertKind.MANUAL_PAYMENT_DUE,
        payment_id=payment_id,
        order_id=order_id,
        details={"order_number": order_number, "provider": "manual"},
        dedupe_window=repeat_window(AlertKind.MANUAL_PAYMENT_DUE),
    )
