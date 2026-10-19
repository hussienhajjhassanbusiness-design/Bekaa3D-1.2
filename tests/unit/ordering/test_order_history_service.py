"""`list_orders` / `get_order` (VS-025) over in-memory fakes."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.application.ports import OrderFilters, OrderPaymentView, PaymentAttemptRef
from app.ordering.application.services.order_history import get_order, list_orders
from app.ordering.domain.enums import (
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)
from app.ordering.domain.orders import CustomerOrder, CustomerOrderLine, HistoryEntry

AT = datetime(2026, 10, 19, tzinfo=UTC)
OWNER = uuid.uuid4()


def _order(**over: Any) -> CustomerOrder:
    base = CustomerOrder(
        id=uuid.uuid4(),
        order_number="B3D-AAAA0000",
        source=OrderSource.CART,
        status=OrderStatus.IN_PROGRESS,
        fulfillment_method=FulfillmentMethod.PICKUP,
        payment_method=PaymentMethod.CASH,
        subtotal_cents=100,
        tax_cents=0,
        total_cents=100,
        currency="USD",
        recipient_name=None,
        contact_phone_snapshot="+96170123456",
        governorate=None,
        city=None,
        area=None,
        street=None,
        landmark_notes=None,
        customer_note=None,
        estimated_dispatch_at=None,
        placed_at=AT,
        completed_at=None,
        cancelled_at=None,
    )
    return replace(base, **over)


def _line(status: OrderItemStatus) -> CustomerOrderLine:
    return CustomerOrderLine(
        id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        product_type=ProductType.PHYSICAL,
        product_name_snapshot="Vase",
        image_snapshot=None,
        unit_price_cents=100,
        quantity=1,
        line_total_cents=100,
        currency="USD",
        fulfillment_status=status,
        fulfilled_at=None,
        cancelled_at=None,
    )


@dataclass
class FakeOrders:
    orders: list[CustomerOrder]
    order_lines: list[CustomerOrderLine] = field(default_factory=list)
    entries: list[HistoryEntry] = field(default_factory=list)

    async def page(
        self,
        user_id: UUID,
        filters: OrderFilters,
        *,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[CustomerOrder]:
        return self.orders[:limit] if user_id == OWNER else []

    async def get(self, user_id: UUID, order_id: UUID) -> CustomerOrder | None:
        found = [o for o in self.orders if o.id == order_id]
        return found[0] if found and user_id == OWNER else None

    async def lines(self, user_id: UUID, order_id: UUID) -> list[CustomerOrderLine]:
        return self.order_lines

    async def history(self, user_id: UUID, order_id: UUID) -> list[HistoryEntry]:
        return self.entries


@dataclass
class FakePayments:
    by_order: dict[UUID, OrderPaymentView] = field(default_factory=dict)
    calls: list[list[UUID]] = field(default_factory=list)

    async def views(self, order_ids: Sequence[UUID]) -> dict[UUID, OrderPaymentView]:
        self.calls.append(list(order_ids))
        return {i: self.by_order[i] for i in order_ids if i in self.by_order}


async def test_a_page_reads_its_payments_in_one_batch() -> None:
    orders = [_order(), _order(payment_method=PaymentMethod.ONLINE)]
    payments = FakePayments()
    page = await list_orders(
        FakeOrders(orders), payments, user_id=OWNER, filters=OrderFilters(), after=None, limit=20
    )
    assert payments.calls == [[o.id for o in orders]]
    assert [s.payment_due for s in page] == [True, False]


async def test_a_paid_cash_order_is_not_due() -> None:
    order = _order()
    payments = FakePayments({order.id: OrderPaymentView(reached_paid=True, shown=None)})
    [summary] = await list_orders(
        FakeOrders([order]), payments, user_id=OWNER, filters=OrderFilters(), after=None, limit=1
    )
    assert not summary.payment_due


async def test_another_customers_order_is_none() -> None:
    order = _order()
    got = await get_order(
        FakeOrders([order]), FakePayments(), user_id=uuid.uuid4(), order_id=order.id
    )
    assert got is None


async def test_can_cancel_reads_the_unmasked_line_state() -> None:
    """The in-production line is shown as pending, yet it still blocks cancellation."""
    order = _order()
    store = FakeOrders(
        [order], [_line(OrderItemStatus.PENDING), _line(OrderItemStatus.IN_PRODUCTION)]
    )
    detail = await get_order(store, FakePayments(), user_id=OWNER, order_id=order.id)
    assert detail is not None
    assert [line.fulfillment_status for line in detail.lines] == [OrderItemStatus.PENDING] * 2
    assert not detail.can_cancel
    assert detail.payment_due


async def test_detail_masks_history_and_shows_the_chosen_payment() -> None:
    order = _order(payment_method=PaymentMethod.ONLINE)
    shown = PaymentAttemptRef(uuid.uuid4(), "mock", "paid", 100, "USD")
    store = FakeOrders(
        [order],
        [_line(OrderItemStatus.PENDING)],
        [
            HistoryEntry(None, "pending_payment", "in_progress", AT),
            HistoryEntry(uuid.uuid4(), "pending", "in_production", AT),
        ],
    )
    payments = FakePayments({order.id: OrderPaymentView(reached_paid=True, shown=shown)})
    detail = await get_order(store, payments, user_id=OWNER, order_id=order.id)
    assert detail is not None
    assert [(h.from_status, h.to_status) for h in detail.history] == [
        ("pending_payment", "in_progress")
    ]
    assert (detail.payment, detail.can_cancel, detail.payment_due) == (shown, True, False)
