"""U11: the cash handover recomputes with `NO_REFUNDS` (VS-030 plan 3.4). Its cash payment
is inserted in the same transaction, so no refund can exist on the order yet."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.ordering import public
from app.ordering.domain.enums import FulfillmentMethod, OrderSource, OrderStatus, PaymentMethod
from app.ordering.domain.enums import OrderItemStatus as S
from app.ordering.domain.order_status import NO_REFUNDS, OrderStatusInputs
from app.ordering.domain.orders import Order, OrderLine

AT = datetime(2026, 10, 23, tzinfo=UTC)


class _Store:
    def __init__(self, _session: object) -> None: ...

    async def move_line(self, *_: object, **__: object) -> bool:
        return True

    async def add_history(self, _rows: object) -> None: ...


def _locked() -> public.LockedOrder:
    order = Order(
        id=uuid4(),
        order_number="BK-1",
        user_id=uuid4(),
        customer_email_snapshot="a@example.com",
        source=OrderSource.CART,
        status=OrderStatus.IN_PROGRESS,
        fulfillment_method=FulfillmentMethod.PICKUP,
        payment_method=PaymentMethod.CASH,
        subtotal_cents=200,
        tax_cents=0,
        total_cents=200,
        currency="USD",
        placed_at=AT,
        cancelled_at=None,
    )

    def line(status: S) -> OrderLine:
        return OrderLine(
            uuid4(), order.id, order.user_id, uuid4(), ProductType.PHYSICAL, "x", 100, 1, 100,
            "USD", status,
        )  # fmt: skip

    return public.LockedOrder(order, (line(S.READY_FOR_PICKUP), line(S.CANCELLED)))


async def test_the_handover_recomputes_with_no_refunds(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[OrderStatusInputs] = []
    hooked: list[list[UUID]] = []

    async def recompute(
        _session: object, _locked: object, inputs: OrderStatusInputs, **_: object
    ) -> OrderStatus:
        seen.append(inputs)
        return OrderStatus.COMPLETED

    async def refresh(_session: object, _locked: object, line_ids: Sequence[UUID]) -> None:
        hooked.append(list(line_ids))

    locked = _locked()
    monkeypatch.setattr(public, "SqlOrderStore", _Store)
    monkeypatch.setattr(public, "recompute_order_status", recompute)
    # VS-036: the badge hook is the writer's new database collaborator; stubbed like the store.
    monkeypatch.setattr(public, "_refresh_review_badges", refresh)
    await public.hand_over_cash_lines(
        cast(AsyncSession, object()),
        locked,
        admin_id=uuid4(),
        at=AT,
        note=None,
    )
    assert len(seen) == 1
    assert seen[0].refunds is NO_REFUNDS and seen[0].payment_reached_paid
    live, cancelled = locked.lines
    assert hooked == [[live.id]] and cancelled.id not in hooked[0]
