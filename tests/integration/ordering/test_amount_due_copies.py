"""The amount due has three copies kept equal by this test (ADR-038 d17, VS-028 audit A-02):
`amount_due_cents` and the `live_total_cents` subqueries of the order history and admin reads."""

from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.domain.cash import amount_due_cents
from app.ordering.infrastructure.admin_orders import SqlAdminOrders
from app.ordering.infrastructure.order_history import SqlOrderHistory
from tests.integration.fulfillment.order_support import seed_physical_order

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class Case:
    payment_method: str
    line_states: tuple[str, ...]
    line_totals: tuple[int, ...]
    expected: int
    payment_status: str | None = None
    order_status: str | None = None
    stl_line: str | None = None


CASES = {
    "cash, every line live": Case("cash", ("pending", "in_production"), (1500, 700), 2200),
    "cash, one line cancelled": Case(
        "cash", ("pending", "cancelled", "shipped"), (1500, 700, 300), 1800
    ),
    "cash, every line cancelled": Case(
        "cash", ("cancelled", "cancelled"), (1500, 700), 0, order_status="cancelled"
    ),
    "cash, handed over with a refused line": Case(
        "cash", ("delivered", "cancelled"), (1500, 700), 1500, order_status="completed"
    ),
    "online, partly refunded": Case(
        "online",
        ("delivered", "refunded"),
        (1200, 800),
        2000,
        payment_status="partially_refunded",
        order_status="partially_refunded",
    ),
    "online, fully refunded": Case(
        "online",
        ("refunded", "refunded"),
        (1200, 800),
        2000,
        payment_status="refunded",
        order_status="refunded",
    ),
    "mixed, a physical line cancelled": Case(
        "online",
        ("pending", "cancelled"),
        (1000, 400),
        1500,
        payment_status="paid",
        stl_line="awaiting_delivery",
    ),
}


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
async def test_the_pure_amount_due_and_both_sql_copies_agree(
    db_session: AsyncSession, case: Case
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method=case.payment_method,
        fulfillment="pickup",
        line_states=case.line_states,
        line_totals=case.line_totals,
        payment_status=case.payment_status,
        order_status=case.order_status,
        stl_line=case.stl_line,
    )
    history = SqlOrderHistory(db_session)
    customer = await history.get(order.user_id, order.order_id)
    admin = await SqlAdminOrders(db_session).get(order.order_id)
    lines = await history.lines(order.user_id, order.order_id)
    assert customer is not None and admin is not None
    assert amount_due_cents(lines) == case.expected
    assert customer.live_total_cents == case.expected
    assert admin.live_total_cents == case.expected
