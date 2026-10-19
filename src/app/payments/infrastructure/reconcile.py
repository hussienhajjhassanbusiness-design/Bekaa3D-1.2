"""The `reconcile_payments` body (VS-024 plan 3.2): pages of stale live attempts, each
asked with no transaction open, then applied in Tx B. Unlocked selection; sequential
queries; a per-provider breaker and a run deadline. Alerts go in their own transactions."""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from app.payments.domain.alerts import AlertKind
from app.payments.domain.exceptions import ProviderUnavailableError
from app.payments.domain.limits import (
    JOB_RUN_DEADLINE_SECONDS,
    PROVIDER_BREAKER_FAILURES,
    RECONCILE_MIN_AGE,
    RECONCILE_PAGE_SIZE,
    STUCK_AFTER,
)
from app.payments.domain.outcome import LIVE, Outcome
from app.payments.domain.release import Capability
from app.payments.infrastructure.alerts import alert
from app.payments.infrastructure.payments import SqlPaymentStore
from app.payments.infrastructure.verification import (
    Factory,
    Providers,
    capability,
    verify_payment_answer,
)

logger = structlog.get_logger()
Keyset = tuple[datetime, UUID]
COUNTERS = (
    "seen",
    "applied",
    "unchanged",
    "deferred",
    "unknown",
    "stuck",
    "skipped_manual",
    "skipped_unconfigured",
    "breaker_open",
    "truncated",
)


class Breaker:
    """Consecutive failures per provider within one run; open at PROVIDER_BREAKER_FAILURES."""

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}

    def is_open(self, provider: str) -> bool:
        return self._failures.get(provider, 0) >= PROVIDER_BREAKER_FAILURES

    def failed(self, provider: str) -> bool:
        """True exactly when this failure opens the breaker."""
        self._failures[provider] = self._failures.get(provider, 0) + 1
        return self._failures[provider] == PROVIDER_BREAKER_FAILURES

    def answered(self, provider: str) -> None:
        self._failures[provider] = 0


async def provider_unreachable(factory: Factory, provider: str) -> None:
    await alert(factory, AlertKind.PROVIDER_UNREACHABLE, details={"provider": provider})


async def reconcile_stuck(
    factory: Factory,
    providers: Providers,
    *,
    now: datetime,
    start_after: Keyset | None = None,
    clock: Callable[[], float] = time.monotonic,
    deadline_seconds: float = JOB_RUN_DEADLINE_SECONDS,
) -> dict[str, int]:
    """Live online attempts initiated at or before `now - RECONCILE_MIN_AGE`; `start_after`
    is the keyset to resume from (the run's own cursor otherwise starts at the oldest)."""
    counts = dict.fromkeys(COUNTERS, 0)
    breaker, started, after = Breaker(), clock(), start_after
    while True:
        async with factory() as session:
            page = await SqlPaymentStore(session).stale_live_ids(
                before=now - RECONCILE_MIN_AGE, after=after, limit=RECONCILE_PAGE_SIZE
            )
        for key in page:
            if clock() - started > deadline_seconds:
                counts["truncated"] = 1
                break
            counts["seen"] += 1
            await _one(factory, providers, key[1], now, breaker, counts)
        else:
            if len(page) == RECONCILE_PAGE_SIZE:
                after = page[-1]
                continue
        break
    await logger.ainfo("reconcile_payments_run", **counts)
    return counts


async def _one(
    factory: Factory,
    providers: Providers,
    payment_id: UUID,
    now: datetime,
    breaker: Breaker,
    counts: dict[str, int],
) -> None:
    async with factory() as session, session.begin():
        payment = await SqlPaymentStore(session).get(payment_id)
    if payment is None or payment.status not in LIVE:
        counts["unchanged"] += 1
        return
    provider = payment.provider.value
    ids: dict[str, Any] = {"payment_id": payment.id, "order_id": payment.order_id}
    able = capability(providers, provider)
    if able is Capability.NOT_CONFIGURED:
        counts["skipped_unconfigured"] += 1
        await alert(
            factory, AlertKind.PROVIDER_NOT_CONFIGURED, **ids, details={"provider": provider}
        )
        return
    if able is Capability.NO_STATUS_QUERY:
        counts["skipped_manual"] += 1
        await alert(
            factory, AlertKind.MANUAL_CONFIRMATION_DUE, **ids, details={"provider": provider}
        )
        return
    if breaker.is_open(provider):
        counts["breaker_open"] += 1
        return
    try:
        result, outcome = await verify_payment_answer(
            factory, providers, payment.id, source="reconcile", actor_user_id=None
        )
    except ProviderUnavailableError:
        counts["deferred"] += 1
        if breaker.failed(provider):
            await provider_unreachable(factory, provider)
        return
    breaker.answered(provider)
    if result is not None and result.state == "unknown":
        counts["unknown"] += 1
        await alert(factory, AlertKind.REFERENCE_UNKNOWN, **ids, details={})
        return
    counts["applied" if outcome is not Outcome.NOOP else "unchanged"] += 1
    still_live = result is not None and result.state in ("pending", "processing")
    if (
        still_live
        and payment.initiated_at is not None
        and payment.initiated_at <= now - STUCK_AFTER
    ):
        counts["stuck"] += 1
        await alert(
            factory, AlertKind.STUCK, **ids, details={"attempt_status": payment.status.value}
        )
