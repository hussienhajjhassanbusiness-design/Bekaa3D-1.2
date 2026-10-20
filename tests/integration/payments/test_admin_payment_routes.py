"""The VS-024 admin routes over HTTP (plan 2.2, 2.3, 2.5, 6.2): reconcile answers 202
before any provider call and holds no transaction during it; manual confirm and manual
release with their refusals, audit rows, CSRF, MFA, authorization and per-admin limits."""

import asyncio
import json
import os
import uuid
from collections.abc import Callable, MutableMapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import redis.asyncio as redis_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from app.payments.api import admin_payments
from app.payments.application.ports import PaymentRef, ProviderStatus
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.reconcile import reconcile_stuck
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
    running_app,
)
from tests.integration.payments.recovery_support import (
    HOLD,
    ORDER_STATE,
    PAYMENT_STATE,
    UNTOUCHED,
    YEARS_AHEAD,
    Down,
    SeededOrder,
    drop_alert_emails,  # noqa: F401
    factory,
    keyset_start,
    one,
    seed_attempt,
    seed_event,
    seed_order,
)
from tests.integration.payments.test_verification_recovery import (
    OPEN_TRANSACTIONS,
    NoStatus,
    _forget,
)
from tests.integration.payments.verification_support import Seeded, mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]

REASON = "dashboard shows 10.00 USD captured; customer confirmed by phone"
GRACE = timedelta(hours=24)
AUDITS = """
    SELECT action, actor_user_id, request_id, ip_hash, after_data FROM audit_logs
    WHERE entity_id = :e ORDER BY created_at
"""


class QuietNoStatus(NoStatus):
    """The app's lifespan closes every provider in `app.state` on shutdown."""

    async def aclose(self) -> None:
        return None


class QuietDown(Down):
    async def aclose(self) -> None:
        return None


def _reconcile(payment_id: uuid.UUID) -> str:
    return f"/api/v1/admin/payments/{payment_id}/reconcile"


def _confirm(payment_id: uuid.UUID) -> str:
    return f"/api/v1/admin/payments/{payment_id}/confirm"


def _release(order_id: uuid.UUID) -> str:
    return f"/api/v1/admin/orders/{order_id}/release"


def _epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 5, 1, tzinfo=UTC)


async def _audits(engine: AsyncEngine, entity: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        return list((await conn.execute(text(AUDITS), {"e": entity})).all())


async def _attempt(
    db: AsyncSession, mock: MockPaymentProvider, at: datetime, **attempt: Any
) -> tuple[SeededOrder, uuid.UUID]:
    order = await seed_order(db, placed_at=at)
    return order, await seed_attempt(db, order, initiated_at=at, mock=mock, **attempt)


async def _cash_payment(db: AsyncSession, admin_id: uuid.UUID, at: datetime) -> uuid.UUID:
    order = await seed_order(
        db,
        placed_at=at,
        physical=True,
        stl=False,
        payment_method="cash",
        status="in_progress",
        cash_terms_accepted_at=at,
        digital_terms_accepted_at=None,
        digital_terms_version=None,
    )
    payment_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO payments (id, order_id, provider, order_payment_method, status,"
            " amount_cents, initiated_at, verified_at, recorded_by) VALUES"
            " (:id, :o, 'cash', 'cash', 'paid', 2000, :t, :t, :a)"
        ),
        {"id": payment_id, "o": order.order_id, "t": at, "a": admin_id},
    )
    await db.commit()
    return payment_id


async def _preset(prefix: str, admin_id: uuid.UUID, used: int) -> None:
    store = redis_asyncio.from_url(os.environ["REDIS_URL"])  # type: ignore[no-untyped-call]
    await store.set(f"ratelimit:{prefix}:{admin_id}", used, ex=3600)
    await store.aclose()


def _post(client: TestClient, path: str, body: Any = None, **headers: str) -> httpx.Response:
    response: httpx.Response = client.post(path, json=body, headers=csrf(client) | headers)
    return response


def _canonical(response: httpx.Response) -> tuple[int, str]:
    body = response.json()
    body.pop("request_id", None)
    body.pop("instance", None)
    return response.status_code, json.dumps(body, sort_keys=True)


# --- Authorization, MFA and CSRF on all three routes ---------------------------------------


async def test_customers_admins_without_mfa_and_csrf_less_writes_are_refused(
    db_session: AsyncSession,
) -> None:
    paths = [_reconcile(uuid.uuid4()), _confirm(uuid.uuid4()), _release(uuid.uuid4())]
    imaginary = "/api/v1/admin/payments/definitely-not-a-route"
    with client_for(main_app) as client:
        login(client, (await create_user(db_session)).email)
        expected = _canonical(_post(client, imaginary, {}))
        customer = [_canonical(_post(client, p, {})) for p in paths]
    with client_for(main_app) as client:
        login(client, (await create_user(db_session, role=UserRole.ADMIN)).email)
        no_mfa = [_post(client, p, {}) for p in paths]
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        no_csrf = [client.post(p, json={}) for p in paths]
    assert customer == [expected] * 3 and expected[0] == 404
    assert {(r.status_code, r.json()["code"]) for r in no_mfa} == {(401, "MFA_REQUIRED")}
    assert {(r.status_code, r.json()["code"]) for r in no_csrf} == {(403, "CSRF_INVALID")}


# --- Reconcile -------------------------------------------------------------------------------


async def test_reconcile_answers_202_before_the_provider_is_asked_with_no_transaction_open(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
) -> None:
    """A raw ASGI harness: `send` and the spy write to one list, so the order of the
    response body and the provider call is observed, not inferred (TestClient waits)."""
    _, payment_id = await _attempt(db_session, mock, _epoch(1800), state="paid")
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        cookies = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
        token = client.cookies["csrf_token"]
    await db_session.commit()  # the test's own session read the admin; close its transaction
    events: list[str] = []
    entered, go_on = asyncio.Event(), asyncio.Event()

    class Spy:
        name = "mock"
        supports_status_query = True

        async def query_status(self, ref: PaymentRef) -> ProviderStatus:
            events.append("query_status")
            entered.set()
            await go_on.wait()
            return await mock.query_status(ref)

        async def aclose(self) -> None:
            return None

    async def send(message: MutableMapping[str, Any]) -> None:
        events.append(message["type"])

    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            await asyncio.Event().wait()
        received = True
        return {"type": "http.request", "body": b"", "more_body": False}

    path = _reconcile(payment_id)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"cookie", cookies.encode()),
            (b"x-csrf-token", token.encode()),
        ],
        "client": ("203.0.113.9", 50000),
        "server": ("testserver", 80),
    }
    async with running_app(make_app) as app:
        app.state.payment_providers = {"mock": Spy()}
        call = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(entered.wait(), 10)
        async with db_engine.connect() as conn:
            open_during_call = await conn.scalar(text(OPEN_TRANSACTIONS))
        go_on.set()
        await asyncio.wait_for(call, 10)
    print("\nRECONCILE ASGI ORDER:", events)
    assert events.index("http.response.start") < events.index("http.response.body")
    assert events.index("http.response.body") < events.index("query_status")
    assert open_during_call == 0
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "paid"
    actions = [a.action for a in await _audits(db_engine, payment_id)]
    assert actions[0] == "payment.reconcile_requested" and "payment.verified" in actions


@pytest.mark.parametrize(("state", "year"), [("paid", 1801), ("failed", 1802)])
async def test_a_lost_background_task_is_picked_up_by_the_job(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    year: int,
) -> None:
    at = _epoch(year)
    _, payment_id = await _attempt(db_session, mock, at, state=state)

    async def dies(*args: Any) -> None:
        raise RuntimeError("worker restarted")

    monkeypatch.setattr(admin_payments, "reconcile_in_background", dies)
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = _post(client, _reconcile(payment_id))
    assert response.status_code == 202, response.text
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "pending"
    assert [a.action for a in await _audits(db_engine, payment_id)] == [
        "payment.reconcile_requested"
    ]
    counts = await reconcile_stuck(
        factory(db_engine),
        {"mock": mock},
        now=at + timedelta(minutes=10),
        start_after=keyset_start(at),
    )
    assert counts["applied"] == 1, counts
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == state


async def test_reconcile_refuses_cash_no_status_and_unknown_payments(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        cash = await _cash_payment(db_session, admin.id, _epoch(1803))
        _, manual = await _attempt(db_session, mock, _epoch(1803))
        cash_response = _post(client, _reconcile(cash))
        unknown = _post(client, _reconcile(uuid.uuid4()))
        stub = QuietNoStatus()
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": stub})
        no_status = _post(client, _reconcile(manual))
    assert (cash_response.status_code, cash_response.json()["reason"]) == (409, "cash_payment")
    assert unknown.status_code == 404
    assert (no_status.status_code, no_status.json()["code"]) == (
        503,
        "PAYMENT_VERIFICATION_UNAVAILABLE",
    )
    assert stub.calls == [] and await _audits(db_engine, manual) == []


@pytest.mark.parametrize(("answer", "year"), [("error", 1804), ("unknown", 1805)])
async def test_an_unanswered_reconcile_is_recorded_as_deferred_and_moves_nothing(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
    year: int,
) -> None:
    order, payment_id = await _attempt(db_session, mock, _epoch(year))
    if answer == "unknown":
        await _forget(Seeded(order.user_id, order.order_id, payment_id, "", ""))
    before = await one(db_engine, UNTOUCHED, o=order.order_id)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        if answer == "error":
            monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietDown()})
        assert _post(client, _reconcile(payment_id)).status_code == 202
    audits = await _audits(db_engine, payment_id)
    assert [a.action for a in audits] == [
        "payment.reconcile_requested",
        "payment.reconcile_deferred",
    ]
    assert audits[1].after_data == {
        "reason": "provider_unavailable" if answer == "error" else "unknown"
    }
    after = await one(db_engine, UNTOUCHED, o=order.order_id)
    assert (after.status, after.payments, after.lines) == (
        before.status,
        before.payments,
        before.lines,
    )


async def test_reconciling_an_expired_attempt_finds_its_late_capture(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    _, payment_id = await _attempt(db_session, mock, _epoch(1806), status="expired", state="paid")
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        assert _post(client, _reconcile(payment_id)).status_code == 202
    payment = await one(db_engine, PAYMENT_STATE, p=payment_id)
    assert payment.late_captured_at is not None and payment.captured_amount_cents == 1000
    late = [a for a in await _audits(db_engine, payment_id) if a.action == "payment.late_capture"]
    assert len(late) == 1 and late[0].actor_user_id == admin.id


async def test_the_sixty_first_reconcile_in_an_hour_is_429(
    db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    _, payment_id = await _attempt(db_session, mock, _epoch(1807))
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        await _preset("admin_payment_reconcile", admin.id, 60)
        limited = _post(client, _reconcile(payment_id))
    assert (limited.status_code, limited.json()["code"]) == (429, "RATE_LIMITED")


# --- Manual confirm ----------------------------------------------------------------------------


def _confirm_body(payment_id: uuid.UUID, **over: Any) -> dict[str, Any]:
    return {
        "provider_reference": f"dash_{payment_id.hex}",
        "verified_amount_cents": 1000,
        "verified_currency": "USD",
        "reason": REASON,
    } | over


async def test_a_manual_confirm_pays_and_audits_the_typed_amount_and_reason(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order, payment_id = await _attempt(db_session, mock, _epoch(1810), reference=False)
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        response = _post(client, _confirm(payment_id), _confirm_body(payment_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["outcome"], body["payment"]["status"]) == ("apply_paid", "paid")
    assert "redirect_url" not in response.text and "buyer@example.com" not in response.text
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).lines == ["awaiting_delivery"]
    audits = {a.action: a for a in await _audits(db_engine, payment_id)}
    manual = audits["payment.manual_confirmation"]
    assert (manual.actor_user_id, audits["payment.verified"].actor_user_id) == (admin.id, admin.id)
    assert manual.request_id and manual.ip_hash
    assert (manual.after_data["typed_amount_cents"], manual.after_data["typed_currency"]) == (
        1000,
        "USD",
    )
    assert manual.after_data["reason"] == REASON


@pytest.mark.parametrize(
    ("over", "year"),
    [
        ({"verified_amount_cents": 999}, 1811),
        ({"verified_amount_cents": 1001}, 1812),
        ({"verified_amount_cents": 0}, 1813),
        ({"verified_currency": "EUR"}, 1814),
    ],
    ids=["minus-1", "plus-1", "zero", "eur"],
)
async def test_a_differing_amount_is_422_and_writes_nothing(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    over: dict[str, Any],
    year: int,
) -> None:
    """Every row is unchanged after a refusal (next test); then the right amount pays."""
    _, payment_id = await _attempt(db_session, mock, _epoch(year), reference=False)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        refused = _post(client, _confirm(payment_id), _confirm_body(payment_id, **over))
        accepted = _post(client, _confirm(payment_id), _confirm_body(payment_id))
    assert refused.status_code == 422, refused.text
    problem = refused.json()
    assert (problem["code"], problem["expected_amount_cents"], problem["currency"]) == (
        "PAYMENT_AMOUNT_MISMATCH",
        1000,
        "USD",
    )
    assert accepted.status_code == 200 and accepted.json()["outcome"] == "apply_paid"


async def test_a_refused_confirm_leaves_every_row_as_it_was(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order, payment_id = await _attempt(db_session, mock, _epoch(1815), reference=False)
    await seed_event(db_session, payment_id, received_at=_epoch(1815))
    snapshot = """
        SELECT (SELECT count(*) FROM audit_logs WHERE entity_id = :p) AS audits,
          (SELECT count(*) FROM webhook_events WHERE payment_id = :p AND processed_at IS NULL)
            AS unprocessed
    """
    before = (
        await one(db_engine, UNTOUCHED, o=order.order_id),
        await one(db_engine, PAYMENT_STATE, p=payment_id),
        await one(db_engine, snapshot, p=payment_id),
    )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        refused = _post(
            client, _confirm(payment_id), _confirm_body(payment_id, verified_amount_cents=999)
        )
    assert refused.status_code == 422
    assert (
        await one(db_engine, UNTOUCHED, o=order.order_id),
        await one(db_engine, PAYMENT_STATE, p=payment_id),
        await one(db_engine, snapshot, p=payment_id),
    ) == before


async def test_confirm_refusals_status_provider_reference_cash_reason_and_limit(
    db_session: AsyncSession, mock: MockPaymentProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, status_provider = await _attempt(db_session, mock, _epoch(1816))  # reference stored
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        cash = await _cash_payment(db_session, admin.id, _epoch(1816))
        not_allowed = _post(client, _confirm(status_provider), _confirm_body(status_provider))
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        mismatch = _post(client, _confirm(status_provider), _confirm_body(status_provider))
        cash_response = _post(
            client, _confirm(cash), _confirm_body(cash, verified_amount_cents=2000)
        )
        no_reason = _post(
            client, _confirm(status_provider), _confirm_body(status_provider, reason="")
        )
        unknown = _post(client, _confirm(uuid.uuid4()), _confirm_body(uuid.uuid4()))
        await _preset("admin_payment_confirm", admin.id, 30)
        limited = _post(client, _confirm(status_provider), _confirm_body(status_provider))
    assert (not_allowed.status_code, not_allowed.json()["code"]) == (
        409,
        "MANUAL_CONFIRMATION_NOT_ALLOWED",
    )
    assert (mismatch.status_code, mismatch.json()["code"]) == (409, "PAYMENT_REFERENCE_MISMATCH")
    assert (cash_response.status_code, cash_response.json()["reason"]) == (409, "cash_payment")
    assert (no_reason.status_code, no_reason.json()["code"]) == (422, "VALIDATION_ERROR")
    assert unknown.status_code == 404
    assert (limited.status_code, limited.json()["code"]) == (429, "RATE_LIMITED")


# --- Manual release ----------------------------------------------------------------------------


async def _due_for_release(
    db: AsyncSession, mock: MockPaymentProvider, age: timedelta
) -> tuple[SeededOrder, uuid.UUID]:
    placed = datetime.now(UTC) - age
    return await _attempt(db, mock, placed)


async def test_a_release_before_the_grace_is_409_and_after_it_cancels_the_order(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    early, _ = await _due_for_release(db_session, mock, HOLD + timedelta(hours=1))
    order, payment_id = await _due_for_release(
        db_session, mock, HOLD + GRACE + timedelta(minutes=1)
    )
    before = await one(db_engine, UNTOUCHED, o=early.order_id)
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        refused = _post(client, _release(early.order_id), {"reason": REASON})
        released = _post(client, _release(order.order_id), {"reason": REASON})
        again = _post(client, _release(order.order_id), {"reason": REASON})
    assert (refused.status_code, refused.json()["reason"]) == (409, "grace_not_elapsed")
    available = datetime.fromisoformat(refused.json()["release_available_at"])
    assert available == early.placed_at + HOLD + GRACE
    assert await one(db_engine, UNTOUCHED, o=early.order_id) == before
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "cancelled"
    assert released.json()["attempts_expired"] == [str(payment_id)]
    assert (again.status_code, again.json()["reason"]) == (409, "order_cancelled")
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (state.status, state.released_audits, state.notices, state.emails) == (
        "cancelled",
        1,
        1,
        1,
    )
    (audit,) = [
        a for a in await _audits(db_engine, order.order_id) if a.action == "order.checkout_released"
    ]
    assert (audit.actor_user_id, audit.after_data["reason"]) == (admin.id, REASON)
    assert audit.request_id and audit.ip_hash


async def test_unprocessed_events_need_events_reviewed(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    order, payment_id = await _due_for_release(
        db_session, mock, HOLD + GRACE + timedelta(minutes=1)
    )
    event = await seed_event(db_session, payment_id, received_at=datetime.now(UTC))
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        refused = _post(client, _release(order.order_id), {"reason": REASON})
        released = _post(
            client, _release(order.order_id), {"reason": REASON, "events_reviewed": True}
        )
    assert (refused.status_code, refused.json()["reason"], refused.json()["count"]) == (
        409,
        "unprocessed_events",
        1,
    )
    assert released.status_code == 200 and released.json()["events_dismissed"] == [str(event)]


async def test_release_refusals_reason_cash_paid_unknown_and_limit(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    old = HOLD + GRACE + timedelta(minutes=1)
    order, _ = await _due_for_release(db_session, mock, old)
    paid = await seed_order(db_session, placed_at=datetime.now(UTC) - old, status="in_progress")
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        await _cash_payment(db_session, admin.id, datetime.now(UTC) - old)
        cash_order = await db_session.scalar(
            text("SELECT order_id FROM payments WHERE provider = 'cash' AND recorded_by = :a"),
            {"a": admin.id},
        )
        short = _post(client, _release(order.order_id), {"reason": "too short"})
        missing = _post(client, _release(order.order_id), {})
        cash = _post(client, _release(cash_order), {"reason": REASON})
        paid_response = _post(client, _release(paid.order_id), {"reason": REASON})
        unknown = _post(client, _release(uuid.uuid4()), {"reason": REASON})
        await _preset("admin_order_release", admin.id, 30)
        limited = _post(client, _release(order.order_id), {"reason": REASON})
    assert {short.status_code, missing.status_code} == {422}
    assert (cash.status_code, cash.json()["reason"]) == (409, "cash_order")
    assert (paid_response.status_code, paid_response.json()["reason"]) == (409, "order_not_payable")
    assert unknown.status_code == 404
    assert (limited.status_code, limited.json()["code"]) == (429, "RATE_LIMITED")
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "pending_payment"
