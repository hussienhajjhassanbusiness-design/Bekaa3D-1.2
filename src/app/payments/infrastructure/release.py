"""The hold release (VS-024 plan 2.5, 3.1 T2): `release_stale`, the job body, and
`release_order_by_admin`, the manual release. Only an explicit `failed` or `expired` for
the latest attempt releases automatically; both re-check under orders, lines, payments."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.public import (
    LockedOrder,
    OrderStatus,
    hold_deadline,
    lock_order_for_change,
    manual_release_available_at,
    manual_release_refusal,
    release_candidates,
    release_unpaid_order,
)
from app.payments.domain.alerts import AlertKind
from app.payments.domain.enums import PaymentStatus
from app.payments.domain.exceptions import (
    ManualReleaseRefusedError,
    OrderNotFoundError,
    ProviderUnavailableError,
)
from app.payments.domain.limits import (
    JOB_RUN_DEADLINE_SECONDS,
    MANUAL_RELEASE_GRACE,
    RELEASE_PAGE_SIZE,
    STUCK_AFTER,
)
from app.payments.domain.outcome import LIVE, ProviderResult
from app.payments.domain.payments import Payment
from app.payments.domain.release import (
    Capability,
    ReleaseKind,
    Unavailable,
    release_action,
)
from app.payments.infrastructure.alerts import ALERT_ACTION, alert
from app.payments.infrastructure.ordering_side import SqlPaymentNotices
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.reconcile import Breaker, provider_unreachable
from app.payments.infrastructure.verification import (
    Factory,
    Providers,
    apply_provider_result,
    ask_provider,
    capability,
)
from app.payments.infrastructure.webhook_events import SqlWebhookEventStore
from app.platform.public import SqlAuditWriter, settings_reader

logger = structlog.get_logger()
Keyset = tuple[datetime, UUID]
HOLD_SETTING = "checkout_hold_period"
RELEASE_ACTION = "order.checkout_released"
COUNTERS = (
    "seen",
    "released",
    "applied",
    "not_due",
    "skipped",
    "deferred",
    "breaker_open",
    "rechecked",
    "truncated",
)


def _latest(attempts: Sequence[Payment]) -> Payment | None:
    """By `(initiated_at, id)`, the order T2 and the hold deadline use (D4)."""
    dated = [p for p in attempts if p.initiated_at is not None]
    return max(dated, key=lambda p: (p.initiated_at, p.id), default=None)


async def checkout_hold(factory: Factory) -> timedelta:
    async with factory() as session, session.begin():
        seconds = await settings_reader(session).get_duration_seconds(HOLD_SETTING)
    return timedelta(seconds=seconds)


async def release_stale(
    factory: Factory,
    providers: Providers,
    *,
    now: datetime,
    start_after: Keyset | None = None,
    clock: Callable[[], float] = time.monotonic,
    deadline_seconds: float = JOB_RUN_DEADLINE_SECONDS,
) -> dict[str, int]:
    """The `release_stale_checkouts` body: unpaid online orders past their hold, oldest
    first, keyset-paged; `start_after` resumes from a cursor."""
    hold = await checkout_hold(factory)
    counts = dict.fromkeys(COUNTERS, 0)
    breaker, started, after = Breaker(), clock(), start_after
    while True:
        async with factory() as session:
            page = await release_candidates(
                session, placed_before=now - hold, after=after, limit=RELEASE_PAGE_SIZE
            )
        for placed_at, order_id in page:
            if clock() - started > deadline_seconds:
                counts["truncated"] = 1
                break
            counts["seen"] += 1
            await _one(factory, providers, order_id, placed_at, hold, now, breaker, counts)
        else:
            if len(page) == RELEASE_PAGE_SIZE:
                after = page[-1]
                continue
        break
    await logger.ainfo("release_stale_checkouts_run", **counts)
    return counts


async def _one(
    factory: Factory,
    providers: Providers,
    order_id: UUID,
    placed_at: datetime,
    hold: timedelta,
    now: datetime,
    breaker: Breaker,
    counts: dict[str, int],
) -> None:
    async with factory() as session, session.begin():  # Tx A, no lock
        attempts = await SqlPaymentStore(session).for_order(order_id)
        events = await SqlWebhookEventStore(session).count_unprocessed_for_payments(
            [p.id for p in attempts]
        )
    latest = _latest(attempts)
    if latest is None or latest.initiated_at is None:
        counts["skipped"] += 1
        return
    deadline = hold_deadline(placed_at, latest.initiated_at, hold)
    if now < deadline:
        counts["not_due"] += 1
        return
    provider = latest.provider.value
    able = capability(providers, provider)
    answer: ProviderResult | Unavailable | None = None
    reference: str | None = None
    if events == 0 and able is Capability.STATUS_QUERY:
        if breaker.is_open(provider):
            counts["breaker_open"] += 1
            answer = Unavailable.UNAVAILABLE
        else:
            try:
                status = await ask_provider(providers, latest)  # no transaction open
                answer, reference = status.result, status.provider_payment_id
                breaker.answered(provider)
            except ProviderUnavailableError:
                answer = Unavailable.UNAVAILABLE
                if breaker.failed(provider):
                    await provider_unreachable(factory, provider)
    verdict = release_action(
        unprocessed_events=events,
        capability=able,
        answer=answer,
        stuck=latest.initiated_at <= now - STUCK_AFTER,
        grace_passed=now >= deadline + MANUAL_RELEASE_GRACE,
    )
    if verdict.kind is ReleaseKind.SKIP:
        counts["deferred" if isinstance(answer, Unavailable) else "skipped"] += 1
        if verdict.alert is not None:
            await alert(
                factory,
                verdict.alert,
                payment_id=latest.id,
                order_id=order_id,
                details={"provider": provider, "attempt_status": latest.status.value},
            )
        return
    assert isinstance(answer, ProviderResult)
    async with factory() as session, session.begin():  # Tx B
        if verdict.kind is ReleaseKind.APPLY_ONLY:
            await apply_provider_result(
                session,
                latest.id,
                answer,
                source="release",
                actor_user_id=None,
                provider_payment_id=reference,
            )
            counts["applied"] += 1
            return
        released = await _release(session, order_id, latest, answer, reference, hold, now)
    counts["released" if released else "rechecked"] += 1


async def _locked(
    session: AsyncSession, order_id: UUID
) -> tuple[LockedOrder | None, list[Payment], int]:
    """Orders, lines by id, then the order's payments by id; the event count is unlocked."""
    locked = await lock_order_for_change(session, order_id)
    if locked is None:
        return None, [], 0
    payments = await SqlPaymentStore(session).lock_for_order(order_id)
    events = await SqlWebhookEventStore(session).count_unprocessed_for_payments(
        [p.id for p in payments]
    )
    return locked, payments, events


async def _release(
    session: AsyncSession,
    order_id: UUID,
    asked: Payment,
    answer: ProviderResult,
    reference: str | None,
    hold: timedelta,
    now: datetime,
) -> bool:
    """False, writing nothing, when the re-check under the locks fails: paid, cancelled,
    a newer attempt, a new event, or the deadline moved (plan 3.1, T2 notes)."""
    locked, payments, events = await _locked(session, order_id)
    latest = _latest(payments)
    if (
        locked is None
        or latest is None
        or latest.id != asked.id
        or locked.order.status is not OrderStatus.PENDING_PAYMENT
        or locked.order.cancelled_at is not None
        or events > 0
        or now < hold_deadline(locked.order.placed_at, latest.initiated_at, hold)
    ):
        return False
    await apply_provider_result(
        session,
        asked.id,
        answer,
        source="release",
        actor_user_id=None,
        provider_payment_id=reference,
    )
    after = await SqlPaymentStore(session).lock_for_order(order_id)  # rows already held
    if any(p.status not in (PaymentStatus.FAILED, PaymentStatus.EXPIRED) for p in after):
        return False
    at = datetime.now(UTC)
    lines = await release_unpaid_order(session, locked, at=at, reason="hold_expired")
    await SqlAuditWriter(session).record(
        actor_user_id=None,
        action=RELEASE_ACTION,
        entity_type="order",
        entity_id=order_id,
        after_data={
            "source": "job",
            "reason": f"provider_{answer.state}",
            "payment_id": str(asked.id),
            "hold_deadline": hold_deadline(
                locked.order.placed_at, latest.initiated_at, hold
            ).isoformat(),
            "lines_cancelled": [str(line_id) for line_id in lines],
        },
    )
    await SqlPaymentNotices(session).checkout_released(locked)
    return True


@dataclass(frozen=True)
class ManualRelease:
    order_id: UUID
    cancelled_at: datetime
    attempts_expired: tuple[UUID, ...]
    events_dismissed: tuple[UUID, ...]


async def release_order_by_admin(
    session: AsyncSession,
    order_id: UUID,
    *,
    admin_id: UUID,
    reason: str,
    events_reviewed: bool,
    hold: timedelta,
    now: datetime,
    request_id: str | None = None,
    ip_hash: str | None = None,
) -> ManualRelease:
    """Plan 2.5 in the caller's unit of work; never calls the provider. Raises
    OrderNotFoundError or ManualReleaseRefusedError, writing nothing."""
    locked, payments, events = await _locked(session, order_id)
    if locked is None:
        raise OrderNotFoundError(f"order {order_id} does not exist")
    latest = _latest(payments)
    deadline = hold_deadline(locked.order.placed_at, latest.initiated_at if latest else None, hold)
    early = (
        latest is not None
        and latest.provider_payment_id is None
        and await answered_unknown(session, latest)
    )
    available_at = manual_release_available_at(deadline, MANUAL_RELEASE_GRACE, early=early)
    refusal = manual_release_refusal(
        locked.order,
        locked.lines,
        now=now,
        available_at=available_at,
        unprocessed_events=events,
        events_reviewed=events_reviewed,
    )
    if refusal is not None:
        raise ManualReleaseRefusedError(
            refusal.value, available_at=available_at, unprocessed_events=events
        )
    store, audit = SqlPaymentStore(session), SqlAuditWriter(session)
    expired = tuple(p.id for p in payments if p.status in LIVE)
    for payment_id in expired:
        await store.mark_status(payment_id, PaymentStatus.EXPIRED, at=now)
        await audit.record(
            actor_user_id=admin_id,
            action="payment.expired",
            entity_type="payment",
            entity_id=payment_id,
            after_data={"order_id": str(order_id), "source": "admin_release"},
            request_id=request_id,
            ip_hash=ip_hash,
        )
    dismissed: tuple[UUID, ...] = ()
    if events_reviewed and events:
        dismissed = tuple(
            await SqlWebhookEventStore(session).dismiss_for_payments(
                [p.id for p in payments], at=now
            )
        )
    lines = await release_unpaid_order(
        session, locked, at=now, reason="released_by_admin", actor_user_id=admin_id
    )
    after_data: dict[str, Any] = {
        "source": "admin",
        "reason": reason,
        "hold_deadline": deadline.isoformat(),
        "attempts_expired": [str(i) for i in expired],
        "events_dismissed": [str(i) for i in dismissed],
        "lines_cancelled": [str(i) for i in lines],
    }
    await audit.record(
        actor_user_id=admin_id,
        action=RELEASE_ACTION,
        entity_type="order",
        entity_id=order_id,
        after_data=after_data,
        request_id=request_id,
        ip_hash=ip_hash,
    )
    await SqlPaymentNotices(session).checkout_released(locked)
    return ManualRelease(order_id, now, expired, dismissed)


async def answered_unknown(session: AsyncSession, payment: Payment) -> bool:
    """Q7's early release: the `reference_unknown` alert row records an `unknown` answer."""
    return await SqlAuditWriter(session).recorded(
        action=ALERT_ACTION,
        entity_type="payment",
        entity_id=payment.id,
        matching={"kind": str(AlertKind.REFERENCE_UNKNOWN)},
        since=None,
    )
