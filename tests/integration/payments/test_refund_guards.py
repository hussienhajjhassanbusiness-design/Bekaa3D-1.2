"""VS-030 guards: refund facts are read only under the order's row lock (plan 3.4, 8.1),
and the refund routes sit behind the admin boundary with CSRF on writes (6.5 S1)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from app.ordering.public import lock_order_for_change
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
from tests.integration.payments.refund_support import ADMIN, REFUNDS, create, key, ok, paid_online

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
