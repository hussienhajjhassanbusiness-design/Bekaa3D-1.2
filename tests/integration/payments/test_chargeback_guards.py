"""S1 for chargebacks (VS-030 plan 6.5): the routes sit behind the admin boundary, the write
needs CSRF and an Idempotency-Key, and a hostile body is never a 500."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.main import app as main_app
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
    key,
    paid_online,
    payment_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

WRITE = "/api/v1/admin/orders/{order_id}/chargebacks"
READS = [WRITE, "/api/v1/admin/chargebacks/{chargeback_id}"]


@pytest.mark.parametrize(("method", "path"), [("post", WRITE)] + [("get", p) for p in READS])
def test_the_chargeback_routes_declare_session_csrf_and_the_boundary(
    method: str, path: str
) -> None:
    with TestClient(main_app) as client:
        operation = client.get("/openapi.json").json()["paths"][path][method]
    scheme: dict[str, list[str]] = {"sessionCookie": []}
    assert operation["security"] == [scheme if method == "get" else scheme | {"csrfToken": []}]
    assert {"401", "404"} <= set(operation["responses"])
    walked = {p for _, p in ADMIN_OPERATIONS}
    assert any(p.endswith("/chargebacks") and "/orders/" in p for p in walked)
    assert any(p.startswith(f"{ADMIN}/chargebacks/") for p in walked)


async def test_customers_get_404_admins_without_mfa_401_and_the_write_needs_csrf_and_a_key(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    payment = await payment_of(db_engine, order.order_id)
    write = WRITE.replace("{order_id}", str(order.order_id))
    reads = [write, f"{ADMIN}/chargebacks/{uuid.uuid4()}"]
    body = {"payment_id": str(payment), "charged_cents": 1}
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert_problem(
            client.post(write, json=body, headers={"Idempotency-Key": key()}), 403, "CSRF_INVALID"
        )
        valid = body | {
            "provider_dispute_reference": "dp-no-key",
            "charged_cents": 1000,
            "items": [{"order_item_id": str(order.physical[0]), "amount_cents": 1000}],
            "reason": "Bank dispute.",
            "received_at": "2026-10-20T10:00:00Z",
        }
        missing = client.post(write, json=valid, headers=csrf(client))
        assert_problem(missing, 422, "VALIDATION_ERROR")  # only the Idempotency-Key is missing
        assert "idempotency" in missing.text.lower()
    customer = await create_user(db_session)
    admin = await create_user(db_session, role=UserRole.ADMIN)
    for email, expected in ((customer.email, 404), (admin.email, 401)):
        with client_for(main_app) as other:
            login(other, email)
            response = other.post(
                write, json=body, headers=csrf(other) | {"Idempotency-Key": key()}
            )
            assert response.status_code == expected, response.text
            for path in reads:
                assert other.get(path).status_code == expected, path


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"payment_id": "nope", "charged_cents": "x"},
        {"payment_id": str(uuid.uuid4()), "charged_cents": 0, "items": "x"},
        {"provider_dispute_reference": "x" * 201, "reason": "x" * 1001},
        {"received_at": "2026-10-20T10:00:00"},  # naive: refused
    ],
)
async def test_a_hostile_chargeback_body_is_never_a_500(
    body: object, db_session: AsyncSession
) -> None:
    order = await paid_online(db_session, stl=None)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(
            WRITE.replace("{order_id}", str(order.order_id)),
            json=body,
            headers=csrf(client) | {"Idempotency-Key": key()},
        )
    assert response.status_code == 422, response.text
