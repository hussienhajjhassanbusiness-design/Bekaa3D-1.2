"""`apply_result` for VS-024 (plan 3.4): the captured amount comes from the provider's
answer and is written after every lock, the late-capture sink runs after the capture is
stored, and the admin actor reaches every audit row."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.ordering.public import LockedOrder
from app.payments.application.services.apply import apply_result
from app.payments.domain.enums import PaymentStatus
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.domain.payments import Payment
from tests.unit.payments.test_apply_decides_under_lock import (
    LINE,
    ORDER,
    PAYMENT_ID,
    STALE,
)

NOW = datetime(2026, 10, 19, tzinfo=UTC)
ADMIN = uuid.uuid4()


class Log:
    """One ordered journal of every call, shared by every fake."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def kwargs(self, name: str) -> dict[str, Any]:
        return next(kw for n, kw in self.calls if n == name)


class Payments:
    def __init__(self, log: Log, locked: Payment) -> None:
        self.log, self.locked = log, locked

    async def get(self, payment_id: uuid.UUID) -> Payment:
        self.log.calls.append(("payments.get", {}))
        return STALE

    async def lock(self, payment_id: uuid.UUID) -> Payment:
        self.log.calls.append(("payments.lock", {}))
        return self.locked

    def __getattr__(self, name: str) -> Any:
        async def write(*args: Any, **kwargs: Any) -> None:
            self.log.calls.append((f"payments.{name}", kwargs))

        return write


class Orders:
    def __init__(self, log: Log, order: Any = ORDER) -> None:
        self.log, self.order = log, order

    async def lock(self, order_id: uuid.UUID) -> LockedOrder:
        self.log.calls.append(("orders.lock", {}))
        return LockedOrder(self.order, (LINE,))

    async def mark_paid(self, locked: LockedOrder, *, at: datetime) -> tuple[uuid.UUID, ...]:
        self.log.calls.append(("orders.mark_paid", {}))
        return (LINE.id,)

    async def recompute_unpaid(self, locked: LockedOrder) -> None:
        self.log.calls.append(("orders.recompute", {}))


class Audit:
    def __init__(self, log: Log) -> None:
        self.log = log

    async def record(self, **kwargs: Any) -> None:
        self.log.calls.append(("audit", kwargs))

    async def payment_confirmed(self, locked: LockedOrder) -> None:
        self.log.calls.append(("notice", {}))


class Sink:
    def __init__(self, log: Log) -> None:
        self.log = log

    async def late_capture_recorded(
        self, locked: LockedOrder, payment: Payment, **kwargs: Any
    ) -> None:
        self.log.calls.append(("sink", {"payment": payment, **kwargs}))


async def _apply(
    log: Log,
    result: ProviderResult,
    *,
    locked: Payment = STALE,
    order: Any = ORDER,
    actor: uuid.UUID | None = None,
    sink: bool = True,
) -> Outcome:
    return await apply_result(
        payments=Payments(log, locked),
        orders=Orders(log, order),
        audit=Audit(log),
        notices=Audit(log),
        payment_id=PAYMENT_ID,
        result=result,
        source="manual" if actor else "reconcile",
        actor_user_id=actor,
        provider_payment_id=None,
        at=NOW,
        late_captures=Sink(log) if sink else None,
    )


LOCKS = ["payments.get", "orders.lock", "payments.lock"]


async def test_paid_writes_the_answers_amount_after_the_three_locks() -> None:
    log = Log()
    assert await _apply(log, ProviderResult("paid", 1000, "USD")) is Outcome.APPLY_PAID
    assert log.names()[:4] == [*LOCKS, "payments.mark_paid"]
    kw = log.kwargs("payments.mark_paid")
    assert (kw["captured_amount_cents"], kw["captured_currency"]) == (1000, "USD")
    assert "sink" not in log.names()


@pytest.mark.parametrize(
    ("result", "locked", "order", "fail", "reason"),
    [
        (ProviderResult("paid", 900, "USD"), STALE, ORDER, True, "amount_mismatch"),
        (ProviderResult("paid", 1000, "EUR"), STALE, ORDER, True, "amount_mismatch"),
        (
            ProviderResult("paid", 1000, "USD"),
            replace(STALE, status=PaymentStatus.EXPIRED),
            ORDER,
            False,
            "attempt_not_live",
        ),
        (
            ProviderResult("paid", 1000, "USD"),
            STALE,
            replace(ORDER, cancelled_at=NOW),
            True,
            "order_cancelled",
        ),
    ],
    ids=["underpaid", "currency", "after-expiry", "cancelled-order"],
)
async def test_a_late_capture_stores_the_answer_then_calls_the_sink(
    result: ProviderResult, locked: Payment, order: Any, fail: bool, reason: str
) -> None:
    log = Log()
    await _apply(log, result, locked=locked, order=order)
    names = log.names()
    assert names[:4] == [*LOCKS, "payments.mark_late_capture"]
    capture = log.kwargs("payments.mark_late_capture")
    assert capture == {
        "at": NOW,
        "fail": fail,
        "captured_amount_cents": result.captured_amount_cents,
        "captured_currency": result.currency,
    }
    assert names[-1] == "sink"
    sink = log.kwargs("sink")
    assert sink == {
        "payment": locked,
        "captured_amount_cents": result.captured_amount_cents,
        "captured_currency": result.currency,
        "reason": reason,
        "at": NOW,
    }


@pytest.mark.parametrize(
    "result",
    [
        ProviderResult("failed", None, None),
        ProviderResult("expired", None, None),
        ProviderResult("processing", None, None),
        ProviderResult("pending", None, None),
        ProviderResult("unknown", None, None),
    ],
    ids=lambda r: r.state,
)
async def test_no_capture_and_no_sink_without_a_capture(result: ProviderResult) -> None:
    log = Log()
    await _apply(log, result)
    assert not any("captured" in str(kw) for _, kw in log.calls)
    assert "sink" not in log.names()


async def test_no_sink_bound_still_stores_the_capture() -> None:
    log = Log()
    await _apply(log, ProviderResult("paid", 900, "USD"), sink=False)
    assert log.kwargs("payments.mark_late_capture")["captured_amount_cents"] == 900


@pytest.mark.parametrize(
    ("result", "action"),
    [
        (ProviderResult("paid", 1000, "USD"), "payment.verified"),
        (ProviderResult("failed", None, None), "payment.failed"),
        (ProviderResult("expired", None, None), "payment.expired"),
        (ProviderResult("paid", 900, "USD"), "payment.late_capture"),
    ],
    ids=["paid", "failed", "expired", "late-capture"],
)
@pytest.mark.parametrize("actor", [ADMIN, None], ids=["admin", "job"])
async def test_every_audit_row_carries_the_actor(
    result: ProviderResult, action: str, actor: uuid.UUID | None
) -> None:
    log = Log()
    await _apply(log, result, actor=actor)
    (audit,) = [kw for name, kw in log.calls if name == "audit"]
    assert (audit["action"], audit["actor_user_id"]) == (action, actor)
    assert audit["after_data"]["source"] == ("manual" if actor else "reconcile")
