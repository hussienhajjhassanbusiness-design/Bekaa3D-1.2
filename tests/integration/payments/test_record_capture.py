"""I22 (VS-030 plan 3.6, Q5): record-capture turns a dashboard capture whose amount or
currency differs from the attempt into a late capture with its refund obligation, only for
a provider without a status API; everything else is refused and writes nothing."""

import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from tests.integration.deep_support import assert_problem, client_for, csrf, mfa_admin
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.refund_support import (
    count,
    key,
    late_refunds,
    paid_cash,
    paid_online,
    payment_of,
)
from tests.integration.payments.test_verification_recovery import NoStatus

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

REASON = "dashboard shows 12.00 USD captured after the attempt expired"


class QuietNoStatus(NoStatus):
    """The app's lifespan closes every provider in `app.state` on shutdown."""

    async def aclose(self) -> None:
        return None


def _post(
    client: TestClient, payment_id: uuid.UUID, idem: str | None = None, **over: Any
) -> httpx.Response:
    body = {
        "captured_amount_cents": 1200,
        "captured_currency": "USD",
        "dashboard_reference": f"dash_{payment_id.hex}",
        "reason": REASON,
    } | over
    response: httpx.Response = client.post(
        f"/api/v1/admin/payments/{payment_id}/record-capture",
        json=body,
        headers=csrf(client) | {"Idempotency-Key": idem or key()},
    )
    return response


async def _expired(engine: AsyncEngine, db: AsyncSession, status: str = "expired") -> uuid.UUID:
    order = await seed_physical_order(db, payment_method="online", payment_status=status)
    return await payment_of(engine, order.order_id)


async def test_i22_a_mismatch_becomes_a_late_capture_with_its_obligation(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    payment = await _expired(db_engine, db_session)
    idem = key()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        first = _post(client, payment, idem)
        assert first.status_code == 201, first.text
        replay = _post(client, payment, idem)
        again = _post(client, payment)
    body = first.json()
    assert body["outcome"] == "late_capture" and body["payment"]["status"] == "expired"
    assert replay.json() == body and replay.headers["Idempotent-Replayed"] == "true"
    assert_problem(again, 409, "INVALID_STATE_TRANSITION")
    assert again.json()["reason"] == "already_late_captured"
    (row,) = await late_refunds(db_engine, payment)
    assert str(row.id) == body["refund_id"]
    assert (row.amount_cents, row.currency, row.status) == (1200, "USD", "pending")
    audit = (
        "SELECT count(*) FROM audit_logs WHERE action = 'payment.capture_recorded'"
        " AND entity_id = :p AND after_data->>'dashboard_reference' = :d"
    )
    assert await count(db_engine, audit, p=payment, d=f"dash_{payment.hex}") == 1


async def test_a_live_attempt_with_a_mismatch_is_failed_and_owed(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    payment = await _expired(db_engine, db_session, status="pending")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        response = _post(client, payment, captured_amount_cents=90000, captured_currency="LBP")
    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "late_capture_and_fail"
    assert response.json()["payment"]["status"] == "failed"
    (row,) = await late_refunds(db_engine, payment)
    assert (row.amount_cents, row.currency) == (90000, "LBP")  # never converted (Q6)


async def test_i22_refusals_write_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    expired = await _expired(db_engine, db_session)
    paid = await payment_of(db_engine, (await paid_online(db_session, stl=None)).order_id)
    cash = await payment_of(db_engine, (await paid_cash(db_session)).order_id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        status_api = _post(client, expired)  # the mock has a status API
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        matching = _post(client, expired, captured_amount_cents=1000)
        on_paid = _post(client, paid)
        on_cash = _post(client, cash)
        unknown = _post(client, uuid.uuid4())
        lowercase = _post(client, expired, captured_currency="usd")
    assert_problem(status_api, 409, "MANUAL_CONFIRMATION_NOT_ALLOWED")
    for response, reason in (
        (matching, "use_confirm"),
        (on_paid, "already_paid"),
        (on_cash, "cash_payment"),
    ):
        assert_problem(response, 409, "INVALID_STATE_TRANSITION")
        assert response.json()["reason"] == reason
    assert_problem(unknown, 404)
    assert_problem(lowercase, 422, "VALIDATION_ERROR")
    for payment in (expired, paid, cash):
        assert await late_refunds(db_engine, payment) == []
    stored = (
        "SELECT count(*) FROM idempotency_records WHERE scope = 'admin_record_capture'"
        " AND resource_id = ANY(:ids)"
    )
    assert await count(db_engine, stored, ids=[expired, paid, cash]) == 0


def test_the_route_declares_session_csrf_and_the_boundary() -> None:
    with TestClient(main_app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    operation = paths["/api/v1/admin/payments/{payment_id}/record-capture"]["post"]
    assert operation["security"] == [{"sessionCookie": [], "csrfToken": []}]
    assert {"401", "403", "404", "409"} <= set(operation["responses"])
