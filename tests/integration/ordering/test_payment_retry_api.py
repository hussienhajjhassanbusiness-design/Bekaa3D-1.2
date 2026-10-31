"""`POST /api/v1/me/orders/{order_id}/payments` over HTTP (VS-024 plan 2.1, 6.2): the
owner only, the idempotency scope, the one-live index mapped to a clean 409, the hold,
no transaction open during the provider call, and the redirect URL never logged."""

import asyncio
import io
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core import logging as app_logging
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.main import app as main_app
from app.payments.domain.exceptions import ProviderUnavailableError
from app.payments.infrastructure.payments import SqlPaymentAttempts
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.verification import verify_payment
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    PASSWORD,
    async_client,
    client_for,
    create_user,
    csrf,
    login,
    running_app,
)
from tests.integration.payments.recovery_support import (
    HOLD,
    ORDER_STATE,
    SeededOrder,
    factory,
    one,
    seed_attempt,
    seed_order,
)
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

OPEN_TRANSACTIONS = """
    SELECT count(*) FROM pg_stat_activity
    WHERE datname = current_database() AND pid <> pg_backend_pid()
      AND state LIKE 'idle in transaction%'
"""
ATTEMPTS = "SELECT status FROM payments WHERE order_id = :o ORDER BY initiated_at, id"


def _path(order_id: uuid.UUID) -> str:
    return f"/api/v1/me/orders/{order_id}/payments"


def _key() -> str:
    return f"retry-{uuid.uuid4().hex}"


def _retry(
    client: TestClient, order_id: uuid.UUID, key: str | None = None, **body: Any
) -> httpx.Response:
    headers = csrf(client) | {"Idempotency-Key": key or _key()}
    response: httpx.Response = client.post(_path(order_id), json=body, headers=headers)
    return response


async def _unpaid(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    age: timedelta = timedelta(minutes=5),
    attempt: str | None = "failed",
    **over: Any,
) -> SeededOrder:
    """The caller's unpaid order placed `age` ago, with one attempt in `attempt`."""
    placed = datetime.now(UTC) - age
    order = await seed_order(db, placed_at=placed, user_id=user_id, **over)
    if attempt is not None:
        await seed_attempt(db, order, initiated_at=placed, status=attempt)
    return order


async def _statuses(engine: AsyncEngine, order_id: uuid.UUID) -> list[str]:
    async with engine.connect() as conn:
        return list((await conn.execute(text(ATTEMPTS), {"o": order_id})).scalars())


async def _signed_in(client: TestClient, db: AsyncSession, **kw: Any) -> uuid.UUID:
    user = await create_user(db, **kw)
    login(client, user.email)
    return user.id


# --- The happy path ---------------------------------------------------------------------


async def test_a_failed_attempt_is_retried_on_the_same_order_and_then_paid(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """BR-040's kill switch (`accepting_orders`, off by default here) never blocks a retry."""
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id)
        response = _retry(client, order.order_id)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["order"]["id"], body["order"]["order_number"]) == (
        str(order.order_id),
        order.order_number,
    )
    assert (body["order"]["status"], body["order"]["total_cents"]) == ("pending_payment", 1000)
    assert (body["payment"]["status"], body["payment"]["amount_cents"]) == ("pending", 1000)
    assert body["payment"]["redirect_url"].endswith(order.order_number)
    assert await _statuses(db_engine, order.order_id) == ["failed", "pending"]
    hold_expires = datetime.fromisoformat(body["order"]["hold_expires_at"])
    assert abs(hold_expires - (datetime.now(UTC) + HOLD)) < timedelta(minutes=1)
    payment_id = uuid.UUID(body["payment"]["id"])
    await mock.simulate(payment_id, "paid")
    await verify_payment(factory(db_engine), {"mock": mock}, payment_id)
    paid = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (paid.status, paid.lines) == ("in_progress", ["awaiting_delivery"])


async def test_the_amount_is_the_orders_total_whatever_the_product_now_costs(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id, total_cents=1234)
        await db_session.execute(
            text("UPDATE products SET price_cents = 99 WHERE id = :p"), {"p": order.stl_id}
        )
        await db_session.commit()
        response = _retry(client, order.order_id)
    assert response.status_code == 201, response.text
    assert response.json()["payment"]["amount_cents"] == 1234


async def test_a_product_turned_cash_only_after_placement_never_blocks_the_retry(
    db_session: AsyncSession,
) -> None:
    """VS-049 (ADR-048 d6): the order's payment method is fixed; products are not re-read."""
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id, physical=True)
        lamp = await db_session.scalar(
            text(
                "SELECT product_id FROM order_items WHERE order_id = :o"
                " AND product_type = 'physical'"
            ),
            {"o": order.order_id},
        )
        assert lamp is not None
        await db_session.execute(
            text("UPDATE products SET accepted_payment_methods = 'cash' WHERE id = :p"),
            {"p": lamp},
        )
        await db_session.commit()
        response = _retry(client, order.order_id)
    assert response.status_code == 201, response.text
    assert response.json()["payment"]["status"] == "pending"


# --- A live attempt: 409 PAYMENT_ALREADY_ACTIVE ----------------------------------------------


@pytest.mark.parametrize("live", ["pending", "processing"])
async def test_a_live_attempt_is_resumed_not_duplicated(
    db_engine: AsyncEngine, db_session: AsyncSession, live: str
) -> None:
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id, attempt=None)
        first = _retry(client, order.order_id)
        assert first.status_code == 201, first.text
        await db_session.execute(
            text("UPDATE payments SET status = CAST(:s AS payment_status) WHERE id = :p"),
            {"s": live, "p": first.json()["payment"]["id"]},
        )
        await db_session.commit()
        again = _retry(client, order.order_id)
    assert again.status_code == 409, again.text
    problem = again.json()
    assert (problem["code"], problem["payment_id"], problem["payment_status"]) == (
        "PAYMENT_ALREADY_ACTIVE",
        first.json()["payment"]["id"],
        live,
    )
    expected_url = first.json()["payment"]["redirect_url"] if live == "pending" else None
    assert problem["redirect_url"] == expected_url
    assert await _statuses(db_engine, order.order_id) == [live]


async def test_the_one_live_index_race_is_a_clean_409_and_leaves_no_claim(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live attempt appears between the unlocked read and the INSERT (in the same
    transaction, as a concurrent writer's would after its commit)."""
    real = SqlPaymentAttempts.open_retry_attempt

    async def with_a_rival(self: SqlPaymentAttempts, **kw: Any) -> Any:
        await self._session.execute(
            text(
                "INSERT INTO payments (order_id, provider, order_payment_method, status,"
                " amount_cents, initiated_at) VALUES (:o, 'mock', 'online', 'pending', 1000, now())"
            ),
            {"o": kw["order_id"]},
        )
        return await real(self, **kw)

    key = _key()
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id)
        with monkeypatch.context() as patch:
            patch.setattr(SqlPaymentAttempts, "open_retry_attempt", with_a_rival)
            raced = _retry(client, order.order_id, key)
        assert raced.status_code == 409, raced.text
        assert raced.json()["code"] == "PAYMENT_ALREADY_ACTIVE"
        async with db_engine.connect() as conn:
            claims = await conn.scalar(
                text("SELECT count(*) FROM idempotency_records WHERE user_id = :u"),
                {"u": user_id},
            )
        assert claims == 0
        assert await _statuses(db_engine, order.order_id) == ["failed"]
        assert _retry(client, order.order_id, key).status_code == 201  # the same key, later


# --- T1 refusals -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shape", "reason"),
    [
        ("paid", "order_not_payable"),
        ("released", "order_cancelled"),
        ("hold-expired", "checkout_hold_expired"),
        ("cash", "cash_order"),
    ],
)
async def test_an_order_that_cannot_take_a_payment_is_refused(
    db_engine: AsyncEngine, db_session: AsyncSession, shape: str, reason: str
) -> None:
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        if shape == "paid":
            order = await _unpaid(db_session, user_id, status="in_progress")
            await db_session.execute(
                text(
                    "UPDATE order_items SET fulfillment_status = 'awaiting_delivery'"
                    " WHERE order_id = :o"
                ),
                {"o": order.order_id},
            )
            await db_session.commit()
        elif shape == "released":
            order = await _unpaid(
                db_session, user_id, status="cancelled", cancelled_at=datetime.now(UTC)
            )
        elif shape == "hold-expired":
            order = await _unpaid(db_session, user_id, age=HOLD + timedelta(seconds=1))
        else:
            order = await _unpaid(
                db_session,
                user_id,
                attempt=None,
                physical=True,
                stl=False,
                payment_method="cash",
                status="in_progress",
                cash_terms_accepted_at=datetime.now(UTC),
                digital_terms_accepted_at=None,
                digital_terms_version=None,
            )
        before = await _statuses(db_engine, order.order_id)
        response = _retry(client, order.order_id)
    assert response.status_code == 409, response.text
    assert (response.json()["code"], response.json()["reason"]) == (
        "INVALID_STATE_TRANSITION",
        reason,
    )
    assert await _statuses(db_engine, order.order_id) == before


async def test_the_hold_boundary_allows_a_second_before_and_refuses_at_it(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        inside = await _unpaid(db_session, user_id, age=HOLD - timedelta(seconds=20))
        at_deadline = await _unpaid(db_session, user_id, age=HOLD)
        assert _retry(client, inside.order_id).status_code == 201
        refused = _retry(client, at_deadline.order_id)
    assert refused.json()["reason"] == "checkout_hold_expired"


# --- Owner only, boundary ----------------------------------------------------------------------


def _canonical(response: httpx.Response) -> tuple[int, str]:
    body = response.json()
    body.pop("request_id", None)
    body.pop("instance", None)
    return response.status_code, json.dumps(body, sort_keys=True)


async def test_another_users_order_and_an_unknown_one_get_the_same_404(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    owner = await create_user(db_session)
    theirs = await _unpaid(db_session, owner.id)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        stranger = _retry(client, theirs.order_id)
        unknown = _retry(client, uuid.uuid4())
    assert _canonical(stranger) == _canonical(unknown)
    assert stranger.status_code == 404
    assert "redirect_url" not in stranger.text and theirs.order_number not in stranger.text
    assert await _statuses(db_engine, theirs.order_id) == ["failed"]


async def test_the_boundary_refuses_unverified_csrf_less_and_anonymous_callers(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        anonymous = client.post(_path(uuid.uuid4()), json={}, headers={"Idempotency-Key": _key()})
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id)
        no_csrf = client.post(_path(order.order_id), json={}, headers={"Idempotency-Key": _key()})
    with client_for(main_app) as client:
        unverified = await _signed_in(client, db_session, verified=False)
        mine = await _unpaid(db_session, unverified)
        refused = _retry(client, mine.order_id)
    assert (anonymous.status_code, anonymous.json()["code"]) == (401, "AUTH_REQUIRED")
    assert (no_csrf.status_code, no_csrf.json()["code"]) == (403, "CSRF_INVALID")
    assert (refused.status_code, refused.json()["code"]) == (403, "EMAIL_VERIFICATION_REQUIRED")


async def test_no_amount_is_accepted(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id)
        response = _retry(client, order.order_id, amount_cents=1)
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


# --- Idempotency, scoped per order and user --------------------------------------------------


async def test_one_key_is_one_retry_of_one_order_by_one_user(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    key = _key()
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        a, b = await _unpaid(db_session, user_id), await _unpaid(db_session, user_id)
        first = _retry(client, a.order_id, key)
        replayed = _retry(client, a.order_id, key)
        other_order = _retry(client, b.order_id, key)
        conflict = _retry(client, a.order_id, key, payment_provider="other")
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        theirs = _retry(client, a.order_id, key)  # not their order: 404, never a replay
    assert first.status_code == 201 and other_order.status_code == 201
    assert replayed.status_code == 201 and replayed.headers["Idempotent-Replayed"] == "true"
    assert replayed.json() == first.json()
    assert (conflict.status_code, conflict.json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")
    assert theirs.status_code == 404 and "redirect_url" not in theirs.text
    assert await _statuses(db_engine, a.order_id) == ["failed", "pending"]
    async with db_engine.connect() as conn:
        scopes: Any = (
            await conn.execute(
                text("SELECT scope FROM idempotency_records WHERE user_id = :u ORDER BY scope"),
                {"u": user_id},
            )
        ).scalars()
        assert sorted(scopes) == sorted(
            [f"payment_retry:{a.order_id}", f"payment_retry:{b.order_id}"]
        )


async def test_another_user_with_the_same_key_on_their_own_order_is_independent(
    db_session: AsyncSession,
) -> None:
    key = _key()
    with client_for(main_app) as client:
        first_user = await _signed_in(client, db_session)
        first = _retry(client, (await _unpaid(db_session, first_user)).order_id, key)
    with client_for(main_app) as client:
        second_user = await _signed_in(client, db_session)
        second = _retry(client, (await _unpaid(db_session, second_user)).order_id, key)
    assert first.status_code == second.status_code == 201
    assert "Idempotent-Replayed" not in second.headers
    assert second.json()["payment"]["id"] != first.json()["payment"]["id"]


# --- Providers ---------------------------------------------------------------------------------


async def test_an_unconfigured_provider_and_no_provider_at_all(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id)
        named = _retry(client, order.order_id, payment_provider="other")
        monkeypatch.setattr(main_app.state, "payment_providers", {})
        none = _retry(client, order.order_id)
    assert (named.status_code, named.json()["reason"]) == (422, "provider_not_configured")
    assert (none.status_code, none.json()["code"]) == (503, "ONLINE_PAYMENT_UNAVAILABLE")
    assert await _statuses(db_engine, order.order_id) == ["failed"]


async def test_a_provider_failure_is_a_replayed_502_with_the_order_still_payable(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def down(self: Any, request: Any) -> Any:
        raise ProviderUnavailableError("refused")

    key = _key()
    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id)
        with monkeypatch.context() as patch:
            patch.setattr(MockPaymentProvider, "create_payment", down)
            failed = _retry(client, order.order_id, key)
        replayed = _retry(client, order.order_id, key)
        fresh = _retry(client, order.order_id)
    assert (failed.status_code, failed.json()["code"]) == (502, "PAYMENT_PROVIDER_UNAVAILABLE")
    assert replayed.status_code == 502 and replayed.headers["Idempotent-Replayed"] == "true"
    assert fresh.status_code == 201
    assert await _statuses(db_engine, order.order_id) == ["failed", "failed", "pending"]


# --- Limits ------------------------------------------------------------------------------------


async def test_the_eleventh_retry_in_an_hour_is_429_and_redis_down_fails_closed(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        statuses = [_retry(client, uuid.uuid4()).status_code for _ in range(11)]

        async def broken(*args: Any, **kwargs: Any) -> Any:
            raise ConnectionError("redis is down")

        monkeypatch.setattr(main_app.state.redis, "eval", broken)
        down = _retry(client, uuid.uuid4())
    assert statuses == [404] * 10 + [429]
    assert down.status_code == 503, down.text  # fail closed, as every limiter (VS-011)


# --- No transaction open during the provider call ----------------------------------------------


async def test_no_transaction_is_open_while_the_provider_creates_the_payment(
    db_engine: AsyncEngine, db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    user = await create_user(db_session)
    order = await _unpaid(db_session, user.id)
    entered, release = asyncio.Event(), asyncio.Event()
    async with running_app(make_app) as app:
        provider = app.state.payment_providers["mock"]
        real_create = provider.create_payment

        async def slow_create(request: Any) -> Any:
            entered.set()
            await release.wait()
            return await real_create(request)

        provider.create_payment = slow_create
        client = async_client(app)
        try:
            await client.post(
                "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
            )
            headers = {"X-CSRF-Token": client.cookies["csrf_token"], "Idempotency-Key": _key()}
            task = asyncio.create_task(client.post(_path(order.order_id), json={}, headers=headers))
            await asyncio.wait_for(entered.wait(), timeout=10)
            async with db_engine.connect() as conn:
                open_during_call = await conn.scalar(text(OPEN_TRANSACTIONS))
                committed: Any = (
                    (await conn.execute(text(ATTEMPTS), {"o": order.order_id})).scalars().all()
                )
            release.set()
            response = await task
        finally:
            release.set()
            await client.aclose()
    assert response.status_code == 201, response.text
    assert open_during_call == 0
    assert list(committed) == ["failed", "pending"]  # Tx1 committed before the call


# --- The redirect URL never reaches a log or an audit row ---------------------------------------


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """The production JSON renderer, every level."""
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    production = get_settings().model_copy(update={"environment": "production"})
    monkeypatch.setattr(app_logging, "get_settings", lambda: production)
    configure_logging()
    logging.getLogger().setLevel(logging.DEBUG)
    return buffer


async def test_the_redirect_url_is_never_logged_or_audited(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    captured_logs: io.StringIO,
) -> None:
    async def down(self: Any, request: Any) -> Any:
        raise ProviderUnavailableError("refused")

    with client_for(main_app) as client:
        user_id = await _signed_in(client, db_session)
        order = await _unpaid(db_session, user_id)
        created = _retry(client, order.order_id)
        resumed = _retry(client, order.order_id)
        other = await _unpaid(db_session, user_id)
        with monkeypatch.context() as patch:
            patch.setattr(MockPaymentProvider, "create_payment", down)
            failed = _retry(client, other.order_id)
    assert (created.status_code, resumed.status_code, failed.status_code) == (201, 409, 502)
    url = created.json()["payment"]["redirect_url"]
    assert url and resumed.json()["redirect_url"] == url
    assert url not in captured_logs.getvalue()
    async with db_engine.connect() as conn:
        leaked = await conn.scalar(
            text("SELECT count(*) FROM audit_logs WHERE CAST(after_data AS text) LIKE :u"),
            {"u": f"%{url}%"},
        )
    assert leaked == 0
