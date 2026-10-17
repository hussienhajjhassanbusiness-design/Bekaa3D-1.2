"""`apply_result` decides only from rows read under its locks (VS-023 Checkpoint 4,
deviation 3): the unlocked pre-read supplies the order id and nothing else."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import OrderItemStatus, OrderSource, OrderStatus, PaymentMethod
from app.ordering.domain.orders import Order, OrderLine
from app.ordering.public import LockedOrder
from app.payments.application.services.apply import apply_result
from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.domain.payments import Payment

NOW = datetime(2026, 10, 17, tzinfo=UTC)
ORDER_ID, PAYMENT_ID = uuid.uuid4(), uuid.uuid4()
STALE = Payment(
    PAYMENT_ID, ORDER_ID, PaymentProvider.MOCK, PaymentStatus.PENDING, 1000, "USD", None, None
)
ORDER = Order(
    ORDER_ID,
    "B3D-UNIT0000",
    uuid.uuid4(),
    "x@example.com",
    OrderSource.CART,
    OrderStatus.PENDING_PAYMENT,
    None,
    PaymentMethod.ONLINE,
    1000,
    0,
    1000,
    "USD",
    NOW,
    None,
)
LINE = OrderLine(
    uuid.uuid4(),
    ORDER_ID,
    ORDER.user_id,
    uuid.uuid4(),
    ProductType.STL,
    "STL",
    1000,
    1,
    1000,
    "USD",
    OrderItemStatus.PENDING,
)


class Payments:
    def __init__(self, locked: Payment) -> None:
        self.locked, self.calls = locked, []  # type: ignore[var-annotated]

    async def get(self, payment_id: uuid.UUID) -> Payment:
        self.calls.append("get")
        return STALE

    async def lock(self, payment_id: uuid.UUID) -> Payment:
        self.calls.append("lock")
        return self.locked

    def __getattr__(self, name: str) -> Any:
        async def write(*args: Any, **kwargs: Any) -> None:
            self.calls.append(name)

        return write


class Orders:
    def __init__(self, order: Order) -> None:
        self.order, self.calls = order, []  # type: ignore[var-annotated]

    async def lock(self, order_id: uuid.UUID) -> LockedOrder:
        self.calls.append(("lock", order_id))
        return LockedOrder(self.order, (LINE,))

    async def mark_paid(self, locked: LockedOrder, *, at: datetime) -> tuple[uuid.UUID, ...]:
        self.calls.append("mark_paid")
        return (LINE.id,)

    async def recompute_unpaid(self, locked: LockedOrder) -> None:
        self.calls.append("recompute")


class Sink:
    async def record(self, **kwargs: Any) -> None: ...

    async def payment_confirmed(self, locked: LockedOrder) -> None: ...


async def _apply(payments: Payments, orders: Orders, result: ProviderResult) -> Outcome:
    return await apply_result(
        payments=payments,
        orders=orders,
        audit=Sink(),
        notices=Sink(),
        payment_id=PAYMENT_ID,
        result=result,
        source="reconcile",
        actor_user_id=None,
        provider_payment_id=None,
        at=NOW,
    )


@pytest.mark.parametrize(
    ("locked", "order", "expected"),
    [
        (replace(STALE, status=PaymentStatus.PAID), ORDER, Outcome.NOOP),
        (replace(STALE, status=PaymentStatus.EXPIRED), ORDER, Outcome.LATE_CAPTURE),
        (STALE, replace(ORDER, cancelled_at=NOW), Outcome.LATE_CAPTURE_AND_FAIL),
        (replace(STALE, late_captured_at=NOW, status=PaymentStatus.FAILED), ORDER, Outcome.NOOP),
    ],
    ids=["paid-meanwhile", "expired-meanwhile", "cancelled-meanwhile", "late-already"],
)
async def test_the_decision_uses_the_locked_rows_not_the_pre_read(
    locked: Payment, order: Order, expected: Outcome
) -> None:
    payments, orders = Payments(locked), Orders(order)
    assert await _apply(payments, orders, ProviderResult("paid", 1000, "USD")) is expected
    assert "mark_paid" not in orders.calls


async def test_the_pre_read_only_finds_the_order_and_precedes_every_lock() -> None:
    payments, orders = Payments(STALE), Orders(ORDER)
    assert await _apply(payments, orders, ProviderResult("paid", 1000, "USD")) is Outcome.APPLY_PAID
    assert payments.calls[:2] == ["get", "lock"]
    assert orders.calls[0] == ("lock", STALE.order_id)
