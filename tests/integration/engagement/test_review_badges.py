"""VS-036 plan 6.2 (badge, D14, B-LOSS): the Verified Purchase badge follows current line
facts through the real writers W1-W8. One HTTP client at a time."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.engagement.public import reviews_for_export
from app.main import app as main_app
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import client_for, create_user, csrf, login, mfa_admin
from tests.integration.engagement.review_support import (
    MINE,
    badge,
    email_of,
    execute,
    product_facts,
    product_of_line,
    public_path,
    review_as,
    review_row,
    slug_of,
)
from tests.integration.fulfillment.order_support import (
    hand_over,
    move,
    seed_physical_order,
    transition_path,
)
from tests.integration.payments.refund_support import (
    act,
    attempt,
    chargeback,
    create,
    late_capture,
    line_state,
    ok,
    paid_online,
    payment_of,
)
from tests.integration.payments.support import seed_online_order

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _as_admin(db: AsyncSession) -> TestClient:
    """An entered client with an MFA-complete admin; the caller closes it."""
    client = client_for(main_app).__enter__()
    await mfa_admin(client, db)
    return client


def _close(client: TestClient) -> None:
    client.__exit__(None, None, None)


async def _review_line(
    engine: AsyncEngine, db: AsyncSession, user_id: uuid.UUID, line_id: uuid.UUID, rating: int = 5
) -> str:
    product_id = await product_of_line(engine, line_id)
    return str((await review_as(db, user_id, product_id, rating))["id"])


async def _public_badges(engine: AsyncEngine, product_id: uuid.UUID, **params: Any) -> list[Any]:
    with client_for(main_app) as client:
        body = client.get(public_path(await slug_of(engine, product_id)), params=params).json()
    return [(item["id"], item["is_verified_purchase"]) for item in body["items"]]


# --- STL: payment grants, delivery keeps, a full refund revokes ----------------------------


async def test_stl_paid_after_the_review_then_delivered_then_fully_refunded(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await seed_product(db_session, await seed_refs(db_session), type=ProductType.STL)
    user = await create_user(db_session)
    order_id = await seed_online_order(db_session, user_id=user.id, stl_id=product.id)
    payment = await attempt(db_session, order_id, status="pending")
    review = str((await review_as(db_session, user.id, product.id))["id"])
    assert await badge(db_engine, review) is False
    await late_capture(db_engine, payment, 1000)
    assert await badge(db_engine, review) is True
    line = await _line_ids(db_engine, order_id)
    admin = await _as_admin(db_session)
    try:
        sent = admin.post(
            transition_path(order_id, line[0]),
            json={"target_status": "delivered"},
            headers=csrf(admin),
        )
        assert sent.status_code == 200, sent.text
        assert await badge(db_engine, review) is True
        ok(create(admin, order_id, [(line[0], 1000)]), 201)
    finally:
        _close(admin)
    assert await badge(db_engine, review) is False


async def _line_ids(engine: AsyncEngine, order_id: uuid.UUID) -> list[uuid.UUID]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT id FROM order_items WHERE order_id = :o ORDER BY id"), {"o": order_id}
        )
        return [row.id for row in rows]


# --- physical online: only a received line earns -------------------------------------------


async def test_online_physical_earns_only_when_delivered(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", line_states=["in_production"]
    )
    review = await _review_line(db_engine, db_session, order.user_id, order.line_ids[0])
    assert await badge(db_engine, review) is False
    admin = await _as_admin(db_session)
    try:
        for target, expected in (("ready_to_ship", False), ("shipped", False), ("delivered", True)):
            assert move(admin, order, target).status_code == 200
            assert await badge(db_engine, review) is expected, target
    finally:
        _close(admin)


async def test_online_pickup_earns_when_picked_up(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        fulfillment="pickup",
        line_states=["ready_for_pickup"],
    )
    review = await _review_line(db_engine, db_session, order.user_id, order.line_ids[0])
    assert await badge(db_engine, review) is False
    admin = await _as_admin(db_session)
    try:
        assert move(admin, order, "picked_up").status_code == 200
    finally:
        _close(admin)
    assert await badge(db_engine, review) is True


async def test_a_returned_line_earns_nothing_until_it_is_delivered_again(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """`returned` is reachable only from `shipped`, so the item never reached the buyer."""
    order = await seed_physical_order(
        db_session, payment_method="online", payment_status="paid", line_states=["shipped"]
    )
    review = await _review_line(db_engine, db_session, order.user_id, order.line_ids[0])
    admin = await _as_admin(db_session)
    try:
        for target, expected in (("returned", False), ("shipped", False), ("delivered", True)):
            response = move(admin, order, target)
            assert response.status_code == 200, response.text
            assert await badge(db_engine, review) is expected, target
    finally:
        _close(admin)


# --- cash: unpaid earns nothing, the handover grants it ------------------------------------


async def test_an_unpaid_cash_line_earns_nothing_and_the_handover_grants_it(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(db_session, line_states=["shipped"])
    review = await _review_line(db_engine, db_session, order.user_id, order.line_ids[0])
    assert await badge(db_engine, review) is False
    admin = await _as_admin(db_session)
    try:
        assert hand_over(admin, order, 1000).status_code == 200
    finally:
        _close(admin)
    assert await badge(db_engine, review) is True


async def test_a_refused_cash_line_never_earns_while_the_rest_is_handed_over(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await seed_physical_order(
        db_session, fulfillment="pickup", line_states=["ready_for_pickup", "ready_for_pickup"]
    )
    refused = await _review_line(db_engine, db_session, order.user_id, order.line_ids[0])
    kept = await _review_line(db_engine, db_session, order.user_id, order.line_ids[1])
    admin = await _as_admin(db_session)
    try:
        cancel = move(admin, order, "cancelled", line=0, cancel_reason="refused")
        assert cancel.status_code == 200, cancel.text
        assert hand_over(admin, order, 1000).status_code == 200
    finally:
        _close(admin)
    assert await badge(db_engine, refused) is False
    assert await badge(db_engine, kept) is True


# --- refunds: partial keeps, full revokes, fail / void / settle change nothing --------------


async def test_partial_keeps_full_revokes_and_fail_void_settle_change_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    review = await _review_line(db_engine, db_session, order.user_id, line)
    assert await badge(db_engine, review) is True
    stamp = (await review_row(db_engine, review)).updated_at
    admin = await _as_admin(db_session)
    try:
        voided = ok(create(admin, order.order_id, [(line, 300)]), 201)["id"]
        assert await badge(db_engine, review) is True
        ok(act(admin, voided, "void", {"reason": "Mistake."}))
        assert await badge(db_engine, review) is True
        settled = ok(create(admin, order.order_id, [(line, 200)]), 201)["id"]
        ok(act(admin, settled, "settle", {}))
        assert await badge(db_engine, review) is True
        full = ok(create(admin, order.order_id, [(line, 800)]), 201)["id"]
        assert await line_state(db_engine, line) == "refunded"
        assert await badge(db_engine, review) is False
        ok(act(admin, full, "fail", {"reason": "Bounced."}))
        assert await badge(db_engine, review) is False
    finally:
        _close(admin)
    assert (await review_row(db_engine, review)).updated_at == stamp


async def test_another_received_order_of_the_product_keeps_the_badge(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    first = await paid_online(db_session, stl=None)
    second = await seed_physical_order(
        db_session,
        payment_method="online",
        payment_status="paid",
        line_states=["delivered"],
        user_id=first.user_id,
    )
    product_id = await product_of_line(db_engine, first.physical[0])
    await execute(
        db_engine,
        "UPDATE order_items SET product_id = :p WHERE id = :i",
        p=product_id,
        i=second.line_ids[0],
    )
    review = await _review_line(db_engine, db_session, first.user_id, first.physical[0])
    admin = await _as_admin(db_session)
    try:
        ok(create(admin, first.order_id, [(first.physical[0], 1000)]), 201)
    finally:
        _close(admin)
    assert await badge(db_engine, review) is True


async def test_a_review_after_the_purchase_is_verified_at_creation(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    review = await _review_line(db_engine, db_session, order.user_id, order.physical[0])
    assert await badge(db_engine, review) is True


# --- chargebacks ---------------------------------------------------------------------------


async def test_a_chargeback_emptying_a_delivered_line_revokes_and_an_unfinished_one_does_not(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    received = await paid_online(db_session, stl=None)
    unfinished = await paid_online(db_session, physical=("in_production",), stl=None)
    got = await _review_line(db_engine, db_session, received.user_id, received.physical[0])
    never = await _review_line(db_engine, db_session, unfinished.user_id, unfinished.physical[0])
    assert (await badge(db_engine, got), await badge(db_engine, never)) == (True, False)
    admin = await _as_admin(db_session)
    try:
        for order in (received, unfinished):
            payment = await payment_of(db_engine, order.order_id)
            line = order.physical[0]
            ok(chargeback(admin, order.order_id, payment, 1000, [(line, 1000)]), 201)
    finally:
        _close(admin)
    assert await line_state(db_engine, unfinished.physical[0]) == "cancelled"
    assert (await badge(db_engine, got), await badge(db_engine, never)) == (False, False)


# --- WhatsApp-only (BR-103, D14) -----------------------------------------------------------


async def test_a_whatsapp_only_product_reviewer_without_a_line_has_no_badge(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await seed_product(
        db_session, await seed_refs(db_session), purchase_mode=PurchaseMode.WHATSAPP_ONLY
    )
    user = await create_user(db_session)
    review = str((await review_as(db_session, user.id, product.id))["id"])
    assert await badge(db_engine, review) is False


async def test_d14_whatsapp_only_masks_every_read_and_keeps_the_stored_fact(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    product_id = await product_of_line(db_engine, order.physical[0])
    review = await _review_line(db_engine, db_session, order.user_id, order.physical[0])
    xmin = await review_row_xmin(db_engine, review)
    await execute(
        db_engine, "UPDATE products SET purchase_mode = 'whatsapp_only' WHERE id = :p", p=product_id
    )
    assert await badge(db_engine, review) is True
    assert await _public_badges(db_engine, product_id) == [(review, False)]
    assert await _public_badges(db_engine, product_id, verified_purchase=True) == []
    assert await _public_badges(db_engine, product_id, verified_purchase=False) == [(review, False)]
    with client_for(main_app) as client:
        login(client, await email_of(db_session, order.user_id))
        mine = client.get(MINE).json()["items"]
    assert [(item["id"], item["is_verified_purchase"]) for item in mine] == [(review, False)]
    async with async_sessionmaker(db_engine)() as session:
        exported = await reviews_for_export(session, order.user_id)
    assert [(str(r.id), r.is_verified_purchase) for r in exported] == [(review, False)]
    await execute(
        db_engine, "UPDATE products SET purchase_mode = 'both' WHERE id = :p", p=product_id
    )
    assert await _public_badges(db_engine, product_id) == [(review, True)]
    assert await review_row_xmin(db_engine, review) == xmin


async def review_row_xmin(engine: AsyncEngine, review_id: str) -> str:
    async with engine.connect() as conn:
        return str(
            await conn.scalar(
                text("SELECT xmin::text FROM reviews WHERE id = :r"), {"r": uuid.UUID(review_id)}
            )
        )


# --- the hook skips deleted rows and updates hidden ones -----------------------------------


async def test_the_hook_skips_a_deleted_review_and_updates_a_hidden_one(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    hidden_order = await paid_online(db_session, stl=None)
    deleted_order = await paid_online(db_session, stl=None)
    hidden = await _review_line(
        db_engine, db_session, hidden_order.user_id, hidden_order.physical[0]
    )
    deleted = await _review_line(
        db_engine, db_session, deleted_order.user_id, deleted_order.physical[0]
    )
    await execute(
        db_engine,
        "UPDATE reviews SET is_hidden = true, hidden_at = now() WHERE id = :r",
        r=uuid.UUID(hidden),
    )
    await execute(
        db_engine, "UPDATE reviews SET deleted_at = now() WHERE id = :r", r=uuid.UUID(deleted)
    )
    admin = await _as_admin(db_session)
    try:
        for order in (hidden_order, deleted_order):
            ok(create(admin, order.order_id, [(order.physical[0], 1000)]), 201)
    finally:
        _close(admin)
    assert await badge(db_engine, hidden) is False
    assert await badge(db_engine, deleted) is True


# --- B-LOSS: losing the badge changes only the flag ----------------------------------------


@pytest.mark.parametrize("how", ["refund", "chargeback"])
async def test_b_loss_only_the_flag_changes(
    how: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    line = order.physical[0]
    product_id = await product_of_line(db_engine, line)
    buyer = await _review_line(db_engine, db_session, order.user_id, line, 5)
    for rating in (4, 2):
        await review_as(db_session, (await create_user(db_session)).id, product_id, rating)
    assert await badge(db_engine, buyer) is True
    before = await product_facts(db_engine, product_id)
    assert (before.average_rating, before.review_count) == (Decimal("3.67"), 3)
    stamp = (await review_row(db_engine, buyer)).updated_at
    admin = await _as_admin(db_session)
    try:
        if how == "refund":
            ok(create(admin, order.order_id, [(line, 1000)]), 201)
        else:
            payment = await payment_of(db_engine, order.order_id)
            ok(chargeback(admin, order.order_id, payment, 1000, [(line, 1000)]), 201)
    finally:
        _close(admin)
    assert await badge(db_engine, buyer) is False
    listed = await _public_badges(db_engine, product_id)
    assert (buyer, False) in listed and len(listed) == 3
    assert await _public_badges(db_engine, product_id, verified_purchase=True) == []
    after = await product_facts(db_engine, product_id)
    assert tuple(after) == tuple(before), "no products UPDATE: aggregates, version, xmin"
    assert (await review_row(db_engine, buyer)).updated_at == stamp
