"""VS-030 guards: refund facts are read only under the order's row lock (plan 3.4, 8.1),
and the refund routes sit behind the admin boundary with CSRF on writes (6.5 S1)."""

import os
import uuid
from datetime import UTC, datetime

import pytest
import redis.asyncio as redis_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from app.ordering.public import lock_order_for_change
from app.payments.domain import limits
from app.payments.domain.enums import RefundStatus
from app.payments.domain.exceptions import OrderLockRequiredError
from app.payments.infrastructure.refunds import SqlRefundStore, order_refund_facts
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.identity.test_deep_vs005_admin_mfa import ADMIN_OPERATIONS
from tests.integration.payments.refund_support import (
    ADMIN,
    REFUNDS,
    act,
    create,
    key,
    ok,
    paid_online,
    payment_of,
    refund_count,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

WRITES = [
    "/api/v1/admin/orders/{order_id}/refunds",
    "/api/v1/admin/refunds/{refund_id}/settle",
    "/api/v1/admin/refunds/{refund_id}/fail",
    "/api/v1/admin/refunds/{refund_id}/void",
    "/api/v1/admin/refunds/{refund_id}/reissue",
]
READS = ["/api/v1/admin/refunds", "/api/v1/admin/refunds/{refund_id}"]


# --- the orders-lock-before-facts guard -----------------------------------------------------


async def test_reading_refund_facts_without_the_orders_lock_is_refused(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        with pytest.raises(OrderLockRequiredError):
            await order_refund_facts(session, order.order_id)
        with pytest.raises(OrderLockRequiredError):
            await SqlRefundStore(session).for_order(order.order_id)
    async with factory() as session, session.begin():
        assert await lock_order_for_change(session, order.order_id) is not None
        assert not (await order_refund_facts(session, order.order_id)).present
        assert await SqlRefundStore(session).for_order(order.order_id) == []


async def test_another_orders_lock_does_not_count(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order, other = await paid_online(db_session, stl=None), await paid_online(db_session, stl=None)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await lock_order_for_change(session, other.order_id)
        with pytest.raises(OrderLockRequiredError):
            await order_refund_facts(session, order.order_id)


# --- ADR-042 d10: the second guards behind the orders lock (audit A-05) ----------------------


async def _one_refund(db_engine: AsyncEngine, db_session: AsyncSession) -> tuple[uuid.UUID, ...]:
    """(admin, refund, payment): one pending refund of 100 on a paid order."""
    order = await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        admin = (await mfa_admin(client, db_session))[0].id
        refund = uuid.UUID(
            ok(create(client, order.order_id, [(order.physical[0], 100)]), 201)["id"]
        )
    return admin, refund, await payment_of(db_engine, order.order_id)


async def test_a_state_update_matches_only_a_row_still_in_its_source_state(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    admin, refund, _ = await _one_refund(db_engine, db_session)
    at = datetime.now(UTC)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        store = SqlRefundStore(session)
        assert await store.settle(refund, by=admin, at=at, reference="dash-1", note=None)
        assert not await store.fail(refund, by=admin, at=at, reason="A late bounce.")
        assert not await store.settle(refund, by=admin, at=at, reference="dash-2", note=None)
        row = await store.get(refund)
    assert row is not None and row.status is RefundStatus.SETTLED


@pytest.mark.parametrize("path", ["lock", "lock_open_for_payment"])
async def test_the_refund_rows_a_decision_reads_are_locked(
    path: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    _, refund, payment = await _one_refund(db_engine, db_session)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as holder, holder.begin():
        store = SqlRefundStore(holder)
        if path == "lock":
            assert await store.lock(refund) is not None
        else:
            assert [r.id for r in await store.lock_open_for_payment(payment)] == [refund]
        async with db_engine.connect() as other:
            with pytest.raises(DBAPIError, match="could not obtain lock"):
                await other.execute(
                    text("SELECT 1 FROM refunds WHERE id = :r FOR UPDATE NOWAIT"), {"r": refund}
                )


# --- rate limits: 60 writes and 300 reads an hour per administrator (audit A-02) -------------


async def _preset(prefix: str, admin_id: uuid.UUID, used: int) -> None:
    store = redis_asyncio.from_url(os.environ["REDIS_URL"])  # type: ignore[no-untyped-call]
    await store.set(f"ratelimit:{prefix}:{admin_id}", used, ex=limits.ADMIN_ACTION_WINDOW_SECONDS)
    await store.aclose()


async def test_the_refund_write_and_read_budgets_are_separate_and_enforced(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None, physical=("delivered", "delivered"))
    a, b = order.physical
    with client_for(main_app) as client:
        admin = (await mfa_admin(client, db_session))[0].id
        await _preset("admin_refund_write", admin, limits.REFUND_WRITE_RATE_LIMIT - 1)
        last = ok(create(client, order.order_id, [(a, 100)]), 201)["id"]
        refused = [create(client, order.order_id, [(b, 100)]), act(client, last, "settle", {})]
        await _preset("admin_refund_read", admin, limits.REFUND_READ_RATE_LIMIT - 1)
        read = client.get(f"{REFUNDS}/{last}")  # the spent write budget does not block reads
        refused_reads = [client.get(f"{REFUNDS}/{last}"), client.get(REFUNDS)]
    for response in refused + refused_reads:
        assert_problem(response, 429, "RATE_LIMITED")
    assert refused[0].headers["RateLimit-Limit"] == str(limits.REFUND_WRITE_RATE_LIMIT)
    assert refused_reads[0].headers["RateLimit-Limit"] == str(limits.REFUND_READ_RATE_LIMIT)
    assert ok(read)["status"] == "pending"  # the refused settle wrote nothing
    assert await refund_count(db_engine, order.order_id) == 1


# --- S1 -------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", WRITES + READS)
def test_the_refund_routes_declare_session_csrf_and_the_boundary(path: str) -> None:
    with TestClient(main_app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    method = "get" if path in READS else "post"
    operation = paths[path][method]
    scheme: dict[str, list[str]] = {"sessionCookie": []}
    assert operation["security"] == [scheme if method == "get" else scheme | {"csrfToken": []}]
    assert {"401", "404"} <= set(operation["responses"])
    if method == "post":
        assert "403" in operation["responses"]


def test_the_boundary_matrix_walks_the_refund_routes() -> None:
    walked = {path for _, path in ADMIN_OPERATIONS if path.startswith(REFUNDS)}
    tails = {path.rsplit("/", 1)[-1] for path in walked}
    assert {"settle", "fail", "void", "reissue"} <= tails
    assert any(p.endswith("/refunds") and "/orders/" in p for _, p in ADMIN_OPERATIONS)


def _concrete(path: str, order_id: uuid.UUID, refund_id: uuid.UUID) -> str:
    return path.replace("{order_id}", str(order_id)).replace("{refund_id}", str(refund_id))


async def test_customers_get_404_admins_without_mfa_401_and_writes_need_csrf(
    db_session: AsyncSession,
) -> None:
    order = await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        refund = uuid.UUID(ok(create(client, order.order_id, [(order.physical[0], 1)]), 201)["id"])
        for path in WRITES:
            response = client.post(
                _concrete(path, order.order_id, refund),
                json={"reason": "x"},
                headers={"Idempotency-Key": key()},
            )
            assert_problem(response, 403, "CSRF_INVALID")
    customer = await create_user(db_session)
    admin = await create_user(db_session, role=UserRole.ADMIN)
    for email, expected in ((customer.email, 404), (admin.email, 401)):
        with client_for(main_app) as other:
            login(other, email)
            for path in WRITES:
                response = other.post(
                    _concrete(path, order.order_id, refund),
                    json={"reason": "x"},
                    headers=csrf(other) | {"Idempotency-Key": key()},
                )
                assert response.status_code == expected, (path, response.text)
            for path in READS:
                response = other.get(_concrete(path, order.order_id, refund))
                assert response.status_code == expected, (path, response.text)


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        "x",
        {"items": "x", "reason": 1},
        {"items": [{"order_item_id": "nope", "amount_cents": "1"}], "reason": "x"},
        {"items": [{"order_item_id": str(uuid.uuid4()), "amount_cents": 1}] * 51, "reason": "x"},
        {"items": [{"order_item_id": str(uuid.uuid4()), "amount_cents": 1}], "reason": "x" * 1001},
        {"reference": "x" * 201, "note": None, "reason": None},
    ],
)
async def test_a_hostile_body_is_never_a_500(body: object, db_session: AsyncSession) -> None:
    order = await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        refund = ok(create(client, order.order_id, [(order.physical[0], 1)]), 201)["id"]
        targets = [f"{ADMIN}/orders/{order.order_id}/refunds"] + [
            f"{REFUNDS}/{refund}/{action}" for action in ("settle", "fail", "void")
        ]
        for target in targets:
            response = client.post(
                target, json=body, headers=csrf(client) | {"Idempotency-Key": key()}
            )
            assert response.status_code < 500, (target, response.text)
