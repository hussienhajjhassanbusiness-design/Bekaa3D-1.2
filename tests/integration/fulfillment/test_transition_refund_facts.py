"""A physical transition recomputes the order from real refund rows (VS-030 plan 3.4, B2):
a pending partial refund, or a failed one still owed, keeps the order partially_refunded."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from tests.integration.deep_support import client_for, create_user, mfa_admin
from tests.integration.fulfillment.order_support import move, seed_physical_order, states

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


@pytest.mark.parametrize("refund_status", ["pending", "failed"])
async def test_a_physical_transition_keeps_a_refunded_order_partially_refunded(
    refund_status: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="partially_refunded",
        order_status="partially_refunded",
    )
    admin = (await create_user(db_session, role=UserRole.ADMIN)).id
    refund, at = uuid.uuid4(), datetime.now(UTC)
    await db_session.execute(
        text(
            "INSERT INTO refunds (id, order_id, payment_id, payment_provider, kind, status,"
            " amount_cents, reason, requested_by, initiated_at, failed_at)"
            " SELECT :r, p.order_id, p.id, p.provider, 'admin', CAST(:s AS refund_status), 1,"
            " 'Goodwill.', :by, :at, :failed FROM payments p WHERE p.order_id = :o"
        ),
        {
            "r": refund,
            "s": refund_status,
            "o": order.order_id,
            "by": admin,
            "at": at,
            "failed": at if refund_status == "failed" else None,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO refund_items (refund_id, order_id, order_item_id, amount_cents)"
            " VALUES (:r, :o, :i, 1)"
        ),
        {"r": refund, "o": order.order_id, "i": order.line_ids[0]},
    )
    await db_session.commit()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = move(client, order, "in_production")
    assert response.status_code == 200, response.text
    assert await states(db_engine, order.order_id) == ("partially_refunded", ["in_production"])


async def test_without_refund_rows_the_old_status_is_not_kept(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The stop-gap is gone: a seeded status with no refund behind it is recomputed."""
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        order_status="partially_refunded",
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = move(client, order, "in_production")
    assert response.status_code == 200, response.text
    assert await states(db_engine, order.order_id) == ("in_progress", ["in_production"])
