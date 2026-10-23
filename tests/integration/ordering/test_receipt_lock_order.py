"""Lock order of the VS-029b routes, read from the SQL they send (ADR-024 d9): the caller's
`orders` row, then its lines by id, and no other row lock; the writes come after both."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from app.ordering.infrastructure.orders import SqlOrderStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user, csrf, login
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.ordering.receipt_support import ACTIONS, REPORT, action_path, body_for
from tests.integration.ordering.test_lock_order import _TABLE, captured, locks, tables

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


@pytest.mark.parametrize("action", ACTIONS)
async def test_both_actions_lock_the_callers_order_then_its_lines_then_write(
    action: str, db_session: AsyncSession
) -> None:
    await create_user(db_session, role=UserRole.ADMIN)
    user = await create_user(db_session)
    order = await seed_physical_order(
        db_session, user_id=user.id, email=user.email, line_states=["delivered", "pending"]
    )
    with client_for(main_app) as client:
        login(client, user.email)
        with captured(main_app.state.db_engine.sync_engine) as statements:
            response = client.post(
                action_path(order.order_id, action), json=body_for(action), headers=csrf(client)
            )
    assert response.status_code in (200, 201), response.text
    held = locks(statements)
    print(f"\n{action} LOCKS", *(h[:120] for h in held), sep="\n  ")
    assert tables(held) == ["orders", "order_items"]
    assert "orders.user_id = " in held[0]
    assert "ORDER BY order_items.id FOR UPDATE" in held[1]
    lines_lock = max(i for i, s in enumerate(statements) if "FOR UPDATE" in s)
    writes = [
        (i, _TABLE.findall(s)[0])
        for i, s in enumerate(statements)
        if s.startswith(("INSERT", "UPDATE"))
    ]
    print(f"{action} WRITES", [table for _, table in writes])
    assert all(i > lines_lock for i, _ in writes)
    written = [table for _, table in writes if table != "notifications"]
    if action == REPORT:
        assert written == ["contact_messages", "order_items", "audit_logs"]
    else:
        assert written == ["order_items", "audit_logs"]


@pytest.mark.parametrize("stamp", ["stamp_receipt_confirmed", "stamp_problem_reported"])
async def test_a_stamp_never_writes_a_line_of_another_order_or_one_not_received(
    stamp: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Money review finding 1: the UPDATE repeats the rule, whatever ids it is given."""
    mine = await seed_physical_order(db_session, line_states=["delivered"])
    other = await seed_physical_order(db_session, line_states=["delivered", "shipped"])
    stray = [*other.line_ids, *mine.line_ids]
    async with async_sessionmaker(db_engine)() as session, session.begin():
        stamped = await getattr(SqlOrderStore(session), stamp)(
            mine.order_id, stray, at=datetime.now(UTC)
        )
        own_only = await getattr(SqlOrderStore(session), stamp)(
            other.order_id, [other.line_ids[1]], at=datetime.now(UTC)
        )
    assert (stamped, own_only) == ([mine.line_ids[0]], [])
