"""VS-004 deep edge cases: password reset request and confirm."""

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
import time_machine
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.infrastructure.models import PasswordResetTokenModel, SessionModel, UserModel
from app.identity.infrastructure.repositories import PasswordResetTokenRepository
from app.main import app as main_app
from app.platform.infrastructure.models import EmailOutboxModel
from tests.integration.deep_support import (
    PASSWORD,
    TIMING_SAMPLES,
    assert_problem,
    async_client,
    client_for,
    create_user,
    csrf,
    describe,
    distinguishable,
    login,
    running_app,
    unique_email,
    untraced_clock,
)

REQUEST = "/api/v1/auth/password-reset/request"
CONFIRM = "/api/v1/auth/password-reset/confirm"
NEW_PASSWORD = "a-brand-new-password"


async def _issue(db: AsyncSession, user_id: Any, *, ttl: timedelta = timedelta(hours=1)) -> str:
    """Insert a reset token directly, bypassing the request cooldown."""
    raw = generate_raw_token()
    await PasswordResetTokenRepository(db).add(
        user_id=user_id, token_hash=hash_token(raw), expires_at=datetime.now(UTC) + ttl
    )
    await db.commit()
    return raw


async def _reset_tokens(db: AsyncSession, user_id: Any) -> list[PasswordResetTokenModel]:
    db.expire_all()
    result = await db.scalars(
        select(PasswordResetTokenModel).where(PasswordResetTokenModel.user_id == user_id)
    )
    return list(result.all())


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty"),
        pytest.param({"email": None}, id="null"),
        pytest.param({"email": ""}, id="blank"),
        pytest.param({"email": "not-an-email"}, id="invalid"),
        pytest.param({"email": ["a@example.com"]}, id="array"),
        pytest.param({"email": "a@example.com", "redirect": "https://evil.example"}, id="extra"),
    ],
)
def test_reset_request_input_shapes(body: dict[str, Any]) -> None:
    with client_for(main_app) as client:
        response = client.post(REQUEST, json=body)
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reset_request_is_byte_identical_for_every_account_state(
    db_session: AsyncSession,
) -> None:
    known = await create_user(db_session)
    unverified = await create_user(db_session, verified=False)
    deactivated = await create_user(db_session, active=False)
    in_cooldown = await create_user(db_session)
    varying = {"x-request-id", "date", "ratelimit-remaining", "ratelimit-reset"}
    with client_for(main_app) as client:
        client.post(REQUEST, json={"email": in_cooldown.email})
    responses = []
    for email in (
        unique_email(),
        known.email,
        unverified.email,
        deactivated.email,
        in_cooldown.email,
    ):
        # A client per request: five requests from one IP is exactly the limit.
        with client_for(main_app) as client:
            responses.append(client.post(REQUEST, json={"email": email}))
    shapes = {
        (r.status_code, r.content, tuple(sorted(h for h in r.headers if h not in varying)))
        for r in responses
    }
    assert len(shapes) == 1, shapes


@pytest.mark.timing
@untraced_clock
@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reset_request_timing_does_not_reveal_whether_the_account_exists(
    db_session: AsyncSession,
) -> None:
    known: list[float] = []
    unknown: list[float] = []
    for i in range(TIMING_SAMPLES):
        user = await create_user(db_session)
        with client_for(main_app) as client:
            client.get("/api/v1/settings/public")
            order = [(known, user.email), (unknown, unique_email())]
            for bucket, email in order if i % 2 else reversed(order):
                started = time.perf_counter()
                client.post(REQUEST, json={"email": email})
                bucket.append(time.perf_counter() - started)
    print("TIMING", describe(known, unknown))
    assert not distinguishable(known, unknown), describe(known, unknown)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("elapsed", "issued"),
    [
        pytest.param(timedelta(seconds=119), 1, id="cooldown-minus-1s"),
        pytest.param(timedelta(seconds=120), 2, id="exactly-cooldown"),
    ],
)
async def test_reset_request_cooldown_boundary(
    elapsed: timedelta, issued: int, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    uid, email = user.id, user.email
    with client_for(main_app) as client:
        client.post(REQUEST, json={"email": email})
        [first] = await _reset_tokens(db_session, uid)
        with time_machine.travel(first.created_at + elapsed, tick=False):
            client.post(REQUEST, json={"email": email})
    assert len(await _reset_tokens(db_session, uid)) == issued


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_concurrent_reset_requests_queue_one_email(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    uid = user.id
    async with running_app(make_app) as app:
        clients = [async_client(app) for _ in range(10)]
        try:
            await asyncio.gather(*(c.post(REQUEST, json={"email": user.email}) for c in clients))
        finally:
            for c in clients:
                await c.aclose()
    assert len(await _reset_tokens(db_session, uid)) == 1


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_emailed_reset_link_is_followable(db_session: AsyncSession) -> None:
    """BUG-09: the link used to point at the POST-only confirm route with
    `?token=`, so following it answered 405. It now opens the frontend's reset
    page with the token in the fragment; the page POSTs it with the new
    password."""
    user = await create_user(db_session)
    user_id, email, old_hash = user.id, user.email, user.password_hash
    with client_for(main_app) as client:
        client.post(REQUEST, json={"email": email})
        db_session.expire_all()
        outbox = await db_session.scalar(
            select(EmailOutboxModel).where(
                EmailOutboxModel.recipient_email == email,
                EmailOutboxModel.template == "password_reset_email",
            )
        )
        assert outbox is not None
        link = urlsplit(str(outbox.payload["reset_url"]))
        frontend = urlsplit(get_settings().frontend_base_url)
        assert (link.scheme, link.netloc) == (frontend.scheme, frontend.netloc)
        assert link.path == f"{frontend.path.rstrip('/')}/reset-password"
        # Never in the query string: a fragment is not sent to any server.
        assert link.query == ""
        fragment = parse_qs(link.fragment, strict_parsing=True)
        assert list(fragment) == ["token"]
        [token] = fragment["token"]
        assert token == outbox.payload["token"]
        # The API stays POST-only, and the token from the link works there.
        assert client.get(CONFIRM, params={"token": token}).status_code == 405
        response = client.post(CONFIRM, json={"token": token, "new_password": NEW_PASSWORD})
        assert response.status_code == 204, response.text
    db_session.expire_all()
    row = await db_session.get(UserModel, user_id)
    assert row is not None and row.password_hash != old_hash


# --------------------------------------------------------------------------
# Confirm: inputs and boundaries
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("password", "status"),
    [
        pytest.param("a" * 7, 422, id="len-7"),
        pytest.param("a" * 8, 204, id="len-8"),
        pytest.param("a" * 256, 204, id="len-256"),
        pytest.param("a" * 257, 422, id="len-257"),
        pytest.param(None, 422, id="null"),
        pytest.param(12345678, 422, id="number"),
    ],
)
async def test_confirm_password_boundaries(
    password: Any, status: int, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    raw = await _issue(db_session, user.id)
    with client_for(main_app) as client:
        response = client.post(CONFIRM, json={"token": raw, "new_password": password})
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "extra", [{"user_id": "x"}, {"email": "a@example.com"}, {"password": "x"}], ids=str
)
async def test_confirm_refuses_extra_fields_and_leaves_the_token_unspent(
    extra: dict[str, Any], db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    uid = user.id
    raw = await _issue(db_session, uid)
    with client_for(main_app) as client:
        response = client.post(CONFIRM, json={"token": raw, "new_password": NEW_PASSWORD, **extra})
    assert_problem(response, 422, "VALIDATION_ERROR")
    [token] = await _reset_tokens(db_session, uid)
    assert token.used_at is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("offset", "status"),
    [
        pytest.param(timedelta(seconds=-1), 204, id="expiry-minus-1s"),
        pytest.param(timedelta(0), 410, id="exactly-expiry"),
        pytest.param(timedelta(seconds=1), 410, id="expiry-plus-1s"),
    ],
)
async def test_reset_token_expiry_boundary(
    offset: timedelta, status: int, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    uid = user.id
    raw = await _issue(db_session, uid)
    [token] = await _reset_tokens(db_session, uid)
    with (
        client_for(main_app) as client,
        time_machine.travel(token.expires_at + offset, tick=False),
    ):
        response = client.post(CONFIRM, json={"token": raw, "new_password": NEW_PASSWORD})
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_expired_confirm_changes_nothing(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    uid, old_hash, email = user.id, user.password_hash, user.email
    raw = await _issue(db_session, uid, ttl=timedelta(seconds=-1))
    with client_for(main_app) as client:
        assert (
            client.post(CONFIRM, json={"token": raw, "new_password": NEW_PASSWORD}).status_code
            == 410
        )
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            ).status_code
            == 200
        )
    db_session.expire_all()
    row = await db_session.get(UserModel, uid)
    assert row is not None and row.password_hash == old_hash and row.auth_epoch == 0


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_successful_reset_ends_everything_and_only_the_new_password_works(
    db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    user = await create_user(db_session)
    uid, email = user.id, user.email
    # Two devices open at once, so two independent apps (see make_app in conftest).
    with client_for(make_app()) as old_device, client_for(make_app()) as other_device:
        login(old_device, email)
        login(other_device, email)
        stale_access = old_device.cookies.get("access_token")
        stale_refresh = old_device.cookies.get("refresh_token")
        stale_csrf = csrf(old_device)
        spare = await _issue(db_session, uid)
        raw = await _issue(db_session, uid)
        confirm = old_device.post(CONFIRM, json={"token": raw, "new_password": NEW_PASSWORD})
        assert confirm.status_code == 204
        replay = old_device.post(CONFIRM, json={"token": raw, "new_password": "yet-another-pass"})
        spare_used = old_device.post(
            CONFIRM, json={"token": spare, "new_password": "yet-another-pass"}
        )
        old_device.cookies.clear()
        old_device.cookies.set("access_token", stale_access or "")
        stale_me = old_device.get("/api/v1/me")
        other_me = other_device.get("/api/v1/me")
        old_device.cookies.clear()
        old_device.cookies.set("refresh_token", stale_refresh or "", path="/api/v1/auth")
        stale_rotate = old_device.post("/api/v1/auth/refresh", headers=stale_csrf)
    with client_for(main_app) as fresh:
        old_pw = fresh.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        new_pw = fresh.post("/api/v1/auth/login", json={"email": email, "password": NEW_PASSWORD})
    assert_problem(replay, 400, "INVALID_TOKEN")
    assert_problem(spare_used, 400, "INVALID_TOKEN")
    assert stale_me.status_code == other_me.status_code == 401
    assert stale_rotate.status_code == 401
    assert old_pw.status_code == 401 and new_pw.status_code == 200
    db_session.expire_all()
    live = await db_session.scalar(
        select(func.count())
        .select_from(SessionModel)
        .where(SessionModel.user_id == uid, SessionModel.revoked_at.is_(None))
    )
    assert live == 1, "only the session created after the reset may be live"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_reset_does_not_verify_an_unverified_address_or_revive_a_disabled_one(
    db_session: AsyncSession,
) -> None:
    unverified = await create_user(db_session, verified=False)
    disabled = await create_user(db_session, active=False)
    unverified_id, disabled_id = unverified.id, disabled.id
    raw_unverified = await _issue(db_session, unverified_id)
    raw_disabled = await _issue(db_session, disabled_id)
    with client_for(main_app) as client:
        ok = client.post(CONFIRM, json={"token": raw_unverified, "new_password": NEW_PASSWORD})
        refused = client.post(CONFIRM, json={"token": raw_disabled, "new_password": NEW_PASSWORD})
    assert ok.status_code == 204
    assert_problem(refused, 400, "INVALID_TOKEN")
    db_session.expire_all()
    assert (await db_session.get(UserModel, unverified_id)).email_verified_at is None  # type: ignore[union-attr]
    assert (await db_session.get(UserModel, disabled_id)).is_active is False  # type: ignore[union-attr]


# --------------------------------------------------------------------------
# Confirm: concurrency
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_one_token_confirmed_twenty_times_at_once_wins_once(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    uid = user.id
    raw = await _issue(db_session, uid)
    async with running_app(make_app) as app:
        clients = [async_client(app) for _ in range(20)]
        try:
            responses = await asyncio.gather(
                *(
                    c.post(CONFIRM, json={"token": raw, "new_password": f"new-password-{n}"})
                    for n, c in enumerate(clients)
                )
            )
        finally:
            for c in clients:
                await c.aclose()
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [204] + [400] * 19, statuses
    db_session.expire_all()
    row = await db_session.get(UserModel, uid)
    assert row is not None and row.auth_epoch == 1


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_two_tokens_for_one_account_confirmed_together_never_500(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    outcomes = []
    async with running_app(make_app) as app:
        for _ in range(3):
            user = await create_user(db_session)
            raws = [await _issue(db_session, user.id), await _issue(db_session, user.id)]
            clients = [async_client(app) for _ in raws]
            try:
                responses = await asyncio.gather(
                    *(
                        c.post(CONFIRM, json={"token": raw, "new_password": NEW_PASSWORD})
                        for c, raw in zip(clients, raws, strict=True)
                    )
                )
            finally:
                for c in clients:
                    await c.aclose()
            outcomes.append(sorted(r.status_code for r in responses))
    assert outcomes == [[204, 400]] * 3, outcomes
