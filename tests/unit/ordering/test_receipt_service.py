"""`confirm_receipt` and `report_problem` against fakes (VS-029b; FR-21, ADR-041)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from app.catalog.application.ports import ProductType
from app.ordering.application.services.receipt import confirm_receipt, report_problem
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.enums import OrderSource, OrderStatus, PaymentMethod
from app.ordering.domain.exceptions import NoDeliveredLineError, ReceiptOrderNotFoundError
from app.ordering.domain.orders import Order, OrderLine

AT = datetime(2026, 10, 23, 12, tzinfo=UTC)
USER = uuid.uuid4()


def _order() -> Order:
    return Order(
        id=uuid.uuid4(),
        order_number="B3D-ABC123",
        user_id=USER,
        customer_email_snapshot="old@example.com",
        source=OrderSource.CART,
        status=OrderStatus.COMPLETED,
        fulfillment_method=None,
        payment_method=PaymentMethod.CASH,
        subtotal_cents=1000,
        tax_cents=0,
        total_cents=1000,
        currency="USD",
        placed_at=AT,
        cancelled_at=None,
        recipient_name="Rana",
    )


def _line(order: Order, status: S) -> OrderLine:
    return OrderLine(
        id=uuid.uuid4(),
        order_id=order.id,
        user_id=USER,
        product_id=uuid.uuid4(),
        product_type=ProductType.PHYSICAL,
        product_name_snapshot="Lamp",
        unit_price_cents=1000,
        quantity=1,
        line_total_cents=1000,
        currency="USD",
        fulfillment_status=status,
    )


@dataclass
class FakeOrders:
    order: Order
    lines: list[OrderLine]
    confirmed: set[uuid.UUID] = field(default_factory=set)
    reported: set[uuid.UUID] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    async def lock_owned_order(self, order_id: uuid.UUID, user_id: uuid.UUID) -> Order | None:
        self.calls.append("lock_order")
        owned = order_id == self.order.id and user_id == self.order.user_id
        return self.order if owned else None

    async def lock_lines(self, order_id: uuid.UUID) -> list[OrderLine]:
        self.calls.append("lock_lines")
        return self.lines

    async def stamp_receipt_confirmed(
        self, line_ids: Sequence[uuid.UUID], *, at: datetime
    ) -> list[uuid.UUID]:
        self.calls.append("stamp")
        new = sorted(set(line_ids) - self.confirmed)
        self.confirmed |= set(new)
        return new

    async def stamp_problem_reported(
        self, line_ids: Sequence[uuid.UUID], *, at: datetime
    ) -> list[uuid.UUID]:
        self.calls.append("stamp")
        new = sorted(set(line_ids) - self.reported)
        self.reported |= set(new)
        return new


@dataclass
class FakeInbox:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def submit(self, **report: Any) -> uuid.UUID:
        self.calls.append(report)
        return uuid.uuid4()


@dataclass
class FakeAudit:
    rows: list[dict[str, Any]] = field(default_factory=list)

    async def record(self, **row: Any) -> None:
        self.rows.append(row)


def _orders(*states: S) -> FakeOrders:
    order = _order()
    return FakeOrders(order, [_line(order, s) for s in states])


async def _confirm(orders: FakeOrders, audit: FakeAudit, **over: Any) -> list[uuid.UUID]:
    args: dict[str, Any] = {"user_id": USER, "order_id": orders.order.id} | over
    return await confirm_receipt(orders, audit, at=AT, request_id="r", ip_hash="h", **args)


async def _report(orders: FakeOrders, inbox: FakeInbox, audit: FakeAudit, **over: Any) -> uuid.UUID:
    args: dict[str, Any] = {"user_id": USER, "order_id": orders.order.id} | over
    return await report_problem(
        orders,
        inbox,
        audit,
        email="rana@example.com",
        message="Cracked.",
        at=AT,
        request_id="r",
        ip_hash="h",
        **args,
    )


async def test_confirm_stamps_received_lines_once_and_audits_only_a_change() -> None:
    orders, audit = _orders(S.DELIVERED, S.SHIPPED), FakeAudit()
    assert await _confirm(orders, audit) == [orders.lines[0].id]
    assert await _confirm(orders, audit) == []
    [row] = audit.rows
    assert row["action"] == "order.receipt_confirmed" and row["actor_user_id"] == USER
    assert row["after_data"] == {
        "order_number": "B3D-ABC123",
        "line_ids": [str(orders.lines[0].id)],
    }
    assert orders.calls[:3] == ["lock_order", "lock_lines", "stamp"]


@pytest.mark.parametrize("action", ["confirm", "report"])
async def test_another_customers_order_is_not_found_and_nothing_is_written(action: str) -> None:
    orders, inbox, audit = _orders(S.DELIVERED), FakeInbox(), FakeAudit()
    with pytest.raises(ReceiptOrderNotFoundError):
        if action == "confirm":
            await _confirm(orders, audit, user_id=uuid.uuid4())
        else:
            await _report(orders, inbox, audit, user_id=uuid.uuid4())
    assert (orders.calls, inbox.calls, audit.rows) == (["lock_order"], [], [])


@pytest.mark.parametrize("action", ["confirm", "report"])
async def test_nothing_received_is_refused_before_any_write(action: str) -> None:
    orders, inbox, audit = _orders(S.SHIPPED, S.CANCELLED), FakeInbox(), FakeAudit()
    with pytest.raises(NoDeliveredLineError):
        if action == "confirm":
            await _confirm(orders, audit)
        else:
            await _report(orders, inbox, audit)
    assert (orders.calls, inbox.calls, audit.rows) == (["lock_order", "lock_lines"], [], [])


async def test_a_report_queues_the_message_then_stamps_and_audits_without_the_body() -> None:
    orders, inbox, audit = _orders(S.PICKED_UP), FakeInbox(), FakeAudit()
    message_id = await _report(orders, inbox, audit)
    [sent] = inbox.calls
    assert sent == {
        "user_id": USER,
        "order_id": orders.order.id,
        "order_number": "B3D-ABC123",
        "recipient_name": "Rana",
        "email": "rana@example.com",
        "message": "Cracked.",
    }
    [row] = audit.rows
    assert row["action"] == "order.problem_reported"
    assert row["after_data"]["contact_message_id"] == str(message_id)
    assert "Cracked" not in str(row) and "rana@example.com" not in str(row)


async def test_a_second_report_is_queued_and_audited_but_stamps_nothing() -> None:
    orders, inbox, audit = _orders(S.DELIVERED), FakeInbox(), FakeAudit()
    await _report(orders, inbox, audit)
    await _report(orders, inbox, audit)
    assert len(inbox.calls) == 2
    assert [r["after_data"]["line_ids"] for r in audit.rows] == [[str(orders.lines[0].id)], []]
