"""VS-003 deep edge cases: login, the throttle, JWTs, cookies, CSRF and refresh."""

import asyncio
import base64
import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
import time_machine
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.identity.application.services import login_throttle
from app.identity.infrastructure.models import SessionModel
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.main import app as main_app
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
    fresh_ip,
    login,
    running_app,
    unique_email,
    untraced_clock,
)

LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/me"


def _set_cookie(response: Any, name: str) -> str:
    for raw in response.headers.get_list("set-cookie"):
        if raw.startswith(f"{name}="):
            return str(raw)
    raise AssertionError(f"no Set-Cookie for {name}")


def _b64(obj: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def _claims(user_id: uuid.UUID, session_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "typ": "access",
        "sub": str(user_id),
        "sid": str(session_id),
        "role": "customer",
        "ver": True,
        "mfa": False,
        "auth_epoch": 0,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    for key, value in overrides.items():
        if value is ...:
            claims.pop(key, None)
        else:
            claims[key] = value
    return claims


# --------------------------------------------------------------------------
# Login inputs
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("body", "status"),
    [
        pytest.param({}, 422, id="empty"),
        pytest.param({"email": "a@example.com"}, 422, id="no-password"),
        pytest.param({"password": PASSWORD}, 422, id="no-email"),
        pytest.param({"email": None, "password": PASSWORD}, 422, id="null-email"),
        pytest.param({"email": "a@example.com", "password": None}, 422, id="null-password"),
        pytest.param({"email": "a@example.com", "password": 12345678}, 422, id="number-password"),
        pytest.param({"email": "a@example.com", "password": "x" * 257}, 422, id="257-password"),
        pytest.param({"email": "a@example.com", "password": ""}, 401, id="empty-password"),
        pytest.param({"email": "not-an-email", "password": PASSWORD}, 422, id="bad-email"),
        pytest.param(
            {"email": "a@example.com", "password": PASSWORD, "remember_me": True},
            422,
            id="extra-field",
        ),
        pytest.param(
            {"email": "a@example.com", "password": PASSWORD, "role": "admin"}, 422, id="role"
        ),
    ],
)
def test_login_input_shapes(body: dict[str, Any], status: int) -> None:
    with client_for(main_app) as client:
        response = client.post(LOGIN, json=body)
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_login_is_case_insensitive_on_the_email(db_session: AsyncSession) -> None:
    user = await create_user(db_session, email=f"MiXeD-{uuid.uuid4().hex[:8]}@Example.com")
    with client_for(main_app) as client:
        response = client.post(LOGIN, json={"email": user.email.upper(), "password": PASSWORD})
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_password_is_case_and_whitespace_sensitive(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        for variant in (PASSWORD.upper(), f" {PASSWORD}", f"{PASSWORD} ", PASSWORD[:-1]):
            response = client.post(LOGIN, json={"email": user.email, "password": variant})
            assert_problem(response, 401, "INVALID_CREDENTIALS")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_password_matches_in_any_unicode_normalisation_form(
    db_session: AsyncSession,
) -> None:
    import unicodedata

    nfc = unicodedata.normalize("NFC", "café-crème-brûlée")
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    user = await create_user(db_session, password=nfc)
    with client_for(main_app) as client:
        response = client.post(LOGIN, json={"email": user.email, "password": nfd})
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_deactivated_account_with_a_wrong_password_looks_unknown(
    db_session: AsyncSession,
) -> None:
    """ACCOUNT_DISABLED is only ever revealed to someone holding the password."""
    disabled = await create_user(db_session, active=False)
    with client_for(main_app) as client:
        wrong = client.post(LOGIN, json={"email": disabled.email, "password": "wrong-password"})
        unknown = client.post(LOGIN, json={"email": unique_email(), "password": "wrong-password"})
        right = client.post(LOGIN, json={"email": disabled.email, "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "INVALID_CREDENTIALS"
    assert wrong.json()["detail"] == unknown.json()["detail"]
    assert_problem(right, 403, "ACCOUNT_DISABLED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_login_stores_a_salted_ip_hash_and_a_truncated_user_agent(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    uid = user.id
    ip = fresh_ip()
    with client_for(main_app, ip=ip) as client:
        client.post(
            LOGIN,
            json={"email": user.email, "password": PASSWORD},
            headers={"User-Agent": "U" * 10_000},
        )
    db_session.expire_all()
    row = await db_session.scalar(select(SessionModel).where(SessionModel.user_id == uid))
    assert row is not None
    assert row.user_agent == "U" * 512
    assert row.ip_hash is not None and ip not in row.ip_hash and len(row.ip_hash) == 64


@pytest.mark.timing
@untraced_clock
@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_login_timing_does_not_reveal_whether_the_email_exists(
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
                client.post(LOGIN, json={"email": email, "password": "wrong-password-1"})
                bucket.append(time.perf_counter() - started)
    print("TIMING", describe(known, unknown))
    assert not distinguishable(known, unknown), describe(known, unknown)


# --------------------------------------------------------------------------
# Login throttle: exact boundaries (asyncio.sleep is recorded, not slept)
# --------------------------------------------------------------------------


@pytest.fixture
def recorded_delays(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    delays: list[float] = []

    async def record(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(f"{login_throttle.__name__}.asyncio.sleep", record)
    return delays


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_throttle_delays_and_lockout_hit_the_exact_attempts(
    db_session: AsyncSession, recorded_delays: list[float]
) -> None:
    user = await create_user(db_session)
    statuses: list[int] = []
    per_attempt: list[float] = []
    with client_for(main_app) as client:
        for _ in range(11):
            before = len(recorded_delays)
            response = client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
            statuses.append(response.status_code)
            per_attempt.append(sum(recorded_delays[before:]))
        locked_even_with_the_right_password = client.post(
            LOGIN, json={"email": user.email, "password": PASSWORD}
        )
    assert statuses == [401] * 9 + [429, 429]
    assert per_attempt[:9] == [0, 0, 0, 1, 2, 4, 8, 8, 8]
    assert_problem(locked_even_with_the_right_password, 429, "RATE_LIMITED")
    assert locked_even_with_the_right_password.headers["retry-after"] == "900"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unknown_email_locks_out_identically(recorded_delays: list[float]) -> None:
    email = unique_email()
    with client_for(main_app) as client:
        statuses = [
            client.post(LOGIN, json={"email": email, "password": "wrong-password"}).status_code
            for _ in range(10)
        ]
    assert statuses == [401] * 9 + [429]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_lock_is_per_email_and_ip_and_case_insensitive(
    db_session: AsyncSession, recorded_delays: list[float]
) -> None:
    victim = await create_user(db_session)
    bystander = await create_user(db_session)
    attacker_ip = fresh_ip()
    with client_for(main_app, ip=attacker_ip) as attacker:
        for _ in range(9):
            attacker.post(LOGIN, json={"email": victim.email, "password": "wrong-password"})
        upper = attacker.post(LOGIN, json={"email": victim.email.upper(), "password": PASSWORD})
        other_account = attacker.post(LOGIN, json={"email": bystander.email, "password": PASSWORD})
    with client_for(main_app) as victim_client:
        own_login = victim_client.post(LOGIN, json={"email": victim.email, "password": PASSWORD})
    assert upper.status_code == 429
    assert other_account.status_code == 200
    assert own_login.status_code == 200, "an attacker on another IP must not lock the victim out"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_correct_password_clears_the_counter(
    db_session: AsyncSession, recorded_delays: list[float]
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        for _ in range(6):
            client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
        assert (
            client.post(LOGIN, json={"email": user.email, "password": PASSWORD}).status_code == 200
        )
        recorded_delays.clear()
        client.cookies.clear()
        for _ in range(3):
            client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
    assert recorded_delays == [], "the counter restarted, so attempts 1-3 must be free again"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_parallel_guesses_cannot_outrun_the_lockout(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    async with running_app(make_app) as app, async_client(app) as client:
        responses = await asyncio.gather(
            *(
                client.post(LOGIN, json={"email": user.email, "password": f"guess-{n:04d}"})
                for n in range(20)
            )
        )
    evaluated = sum(r.status_code == 401 for r in responses)
    assert evaluated <= 9, f"{evaluated} guesses were checked against the password"


@pytest.mark.timing
@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_password_hashing_does_not_block_the_event_loop(
    make_app: Callable[[], FastAPI],
) -> None:
    """A ticker that should wake every 5ms records its largest gap while four
    logins run. Offloaded hashing leaves the loop free; inline hashing shows up
    as a gap as long as one Argon2 verification."""
    gaps: list[float] = []
    running = True

    async def ticker() -> None:
        last = time.perf_counter()
        while running:
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    async with running_app(make_app) as app:
        clients = [async_client(app) for _ in range(4)]
        # Warm the pool with an identical burst first. Opening a new database
        # connection (TLS + SCRAM handshake) runs on the loop too and would be
        # measured here instead of hashing, which is what this test is about.
        await asyncio.gather(
            *(
                c.post(LOGIN, json={"email": unique_email(), "password": "wrong-password"})
                for c in clients
            )
        )
        task = asyncio.create_task(ticker())
        try:
            await asyncio.gather(
                *(
                    c.post(LOGIN, json={"email": unique_email(), "password": "wrong-password"})
                    for c in clients
                )
            )
        finally:
            running = False
            await task
            for c in clients:
                await c.aclose()
    assert max(gaps) < 0.04, f"the event loop froze for {max(gaps) * 1000:.0f}ms"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_argon2_never_runs_on_the_event_loop(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BUG-06, machine-independent. Every Argon2 hash and verification made by
    a request must run in a worker thread - a thread with no running event
    loop - never inline on the loop, whatever the machine's speed."""
    from app.identity.application.security import password_hasher

    user = await create_user(db_session)
    real = password_hasher._hasher
    on_loop: list[bool] = []

    def running_on_a_loop() -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True

    class Spy:
        def hash(self, *args: Any, **kwargs: Any) -> str:
            on_loop.append(running_on_a_loop())
            return real.hash(*args, **kwargs)

        def verify(self, *args: Any, **kwargs: Any) -> bool:
            on_loop.append(running_on_a_loop())
            return real.verify(*args, **kwargs)

    monkeypatch.setattr(password_hasher, "_hasher", Spy())
    with client_for(main_app) as client:
        client.post(
            "/api/v1/auth/register",
            json={
                "captcha_token": FAKE_CAPTCHA_PASS,
                "email": unique_email(),
                "password": PASSWORD,
            },
        )
        client.post(
            "/api/v1/auth/resend-verification",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": unique_email()},
        )
        client.post(
            "/api/v1/auth/password-reset/request",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": user.email},
        )
        client.post(LOGIN, json={"email": unique_email(), "password": "wrong-password"})
        client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
        login(client, user.email)
    assert len(on_loop) >= 6, on_loop
    assert not any(on_loop), "an Argon2 operation ran on the event loop thread"


# --------------------------------------------------------------------------
# Cookies
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("environment", ["development", "production", "staging"])
async def test_cookie_flags_per_environment(
    environment: str, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    if environment != "development":
        # The fake captcha refuses to boot outside test and development (ADR-026).
        monkeypatch.setenv("CAPTCHA_PROVIDER", "turnstile")
        monkeypatch.setenv("TURNSTILE_SECRET", "unused-in-this-test")
        # The mock payment provider refuses to boot outside test and development (VS-023).
        monkeypatch.setenv("PAYMENT_PROVIDER", "none")
    get_settings.cache_clear()
    user = await create_user(db_session)
    try:
        with client_for(main_app) as client:
            response = login(client, user.email)
    finally:
        get_settings.cache_clear()
    access = _set_cookie(response, "access_token").lower()
    refresh = _set_cookie(response, "refresh_token").lower()
    token = _set_cookie(response, "csrf_token").lower()
    for cookie in (access, refresh, token):
        assert "samesite=lax" in cookie
        assert ("secure" in cookie) is (environment != "development")
    assert "httponly" in access and "httponly" in refresh and "httponly" not in token
    assert "path=/;" in access + ";" and "path=/;" in token + ";"
    assert "path=/api/v1/auth" in refresh
    assert "max-age=900" in access and "max-age=2592000" in refresh


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_refresh_cookie_never_travels_outside_the_auth_routes(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        me = client.get(ME)
        refreshed = client.post(REFRESH, headers=csrf(client))
    assert "refresh_token=" not in me.request.headers.get("cookie", "")
    assert refreshed.status_code == 204


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_logout_expires_all_three_cookies_on_their_own_paths(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        response = client.post(LOGOUT, headers=csrf(client))
    assert response.status_code == 204
    for name in ("access_token", "refresh_token", "csrf_token"):
        cookie = _set_cookie(response, name).lower()
        assert "max-age=0" in cookie or "expires=thu, 01 jan 1970" in cookie
    assert "path=/api/v1/auth" in _set_cookie(response, "refresh_token").lower()


# --------------------------------------------------------------------------
# Access token tampering
# --------------------------------------------------------------------------


def _forge(claims: dict[str, Any], *, key: str | None = None, alg: str = "HS256") -> str:
    return jwt.encode(claims, key or get_settings().jwt_signing_key, algorithm=alg)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda t, c: _forge({**c, "exp": datetime.now(UTC) - timedelta(seconds=1)}),
            id="expired",
        ),
        pytest.param(lambda t, c: _forge(c, key="not-the-server-key-" * 3), id="wrong-key"),
        pytest.param(lambda t, c: _forge(c, alg="HS512"), id="hs512"),
        pytest.param(
            lambda t, c: (
                _b64({"alg": "none", "typ": "JWT"})
                + "."
                + _b64({k: str(v) for k, v in c.items()})
                + "."
            ),
            id="alg-none",
        ),
        pytest.param(lambda t, c: t[:-6], id="truncated"),
        pytest.param(lambda t, c: t + "x", id="extended-signature"),
        pytest.param(
            lambda t, c: (
                t.split(".")[0]
                + "."
                + _b64({**{k: str(v) for k, v in c.items()}, "role": "admin"})
                + "."
                + t.split(".")[2]
            ),
            id="payload-swapped",
        ),
        pytest.param(lambda t, c: "garbage", id="garbage"),
        pytest.param(lambda t, c: "", id="empty"),
        pytest.param(lambda t, c: _forge({**c, "typ": "refresh"}), id="typ-refresh"),
        pytest.param(lambda t, c: _forge({k: v for k, v in c.items() if k != "typ"}), id="no-typ"),
        pytest.param(lambda t, c: _forge({k: v for k, v in c.items() if k != "sub"}), id="no-sub"),
        pytest.param(lambda t, c: _forge({k: v for k, v in c.items() if k != "sid"}), id="no-sid"),
        pytest.param(
            lambda t, c: _forge({k: v for k, v in c.items() if k != "role"}), id="no-role"
        ),
        pytest.param(lambda t, c: _forge({**c, "role": "superadmin"}), id="unknown-role"),
        pytest.param(lambda t, c: _forge({**c, "sub": "not-a-uuid"}), id="bad-sub"),
        pytest.param(lambda t, c: _forge({**c, "sub": str(uuid.uuid4())}), id="unknown-user"),
        pytest.param(lambda t, c: _forge({**c, "auth_epoch": 1}), id="future-epoch"),
        pytest.param(lambda t, c: _forge({**c, "auth_epoch": -1}), id="negative-epoch"),
        pytest.param(lambda t, c: _forge({**c, "auth_epoch": "0"}), id="string-epoch"),
        pytest.param(lambda t, c: _forge({**c, "auth_epoch": True}), id="bool-epoch"),
        pytest.param(lambda t, c: _forge({**c, "auth_epoch": 2**70}), id="huge-epoch"),
    ],
)
async def test_a_tampered_access_token_is_401(mutate: Any, db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        real = client.cookies.get("access_token")
        assert real is not None
        claims = jwt.decode(real, options={"verify_signature": False})
        claims["iat"] = datetime.fromtimestamp(claims["iat"], UTC)
        claims["exp"] = datetime.fromtimestamp(claims["exp"], UTC)
        forged = mutate(real, claims)
        client.cookies.clear()
        client.cookies.set("access_token", forged)
        response = client.get(ME)
    assert_problem(response, 401, "AUTH_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_signed_token_without_exp_is_refused(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        real = client.cookies.get("access_token")
        assert real is not None
        claims = jwt.decode(real, options={"verify_signature": False})
        claims.pop("exp")
        client.cookies.clear()
        client.cookies.set("access_token", _forge(claims))
        response = client.get(ME)
    assert_problem(response, 401, "AUTH_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("offset", "status"),
    [
        pytest.param(timedelta(minutes=15) - timedelta(seconds=1), 200, id="exp-minus-1s"),
        pytest.param(timedelta(minutes=15), 401, id="exactly-exp"),
        pytest.param(timedelta(minutes=15, seconds=1), 401, id="exp-plus-1s"),
    ],
)
async def test_access_token_expiry_boundary(
    offset: timedelta, status: int, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    t0 = datetime.now(UTC).replace(microsecond=0)
    with client_for(main_app) as client:
        with time_machine.travel(t0, tick=False):
            login(client, user.email)
        with time_machine.travel(t0 + offset, tick=False):
            response = client.get(ME)
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_token_minted_in_the_future_is_not_trusted_early(db_session: AsyncSession) -> None:
    """A server-signed token whose iat lies an hour ahead of the clock."""
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        real = client.cookies.get("access_token")
        assert real is not None
        claims = jwt.decode(real, options={"verify_signature": False})
        future = datetime.now(UTC) + timedelta(hours=1)
        claims.update(iat=future, exp=future + timedelta(minutes=15))
        client.cookies.clear()
        client.cookies.set("access_token", _forge(claims))
        response = client.get(ME)
    assert response.status_code == 401


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "variant",
    ["missing", "empty", "wrong", "upper", "padded", "cookie-and-header-both-attacker-chosen"],
)
async def test_every_csrf_variant_but_the_real_one_is_403(
    variant: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        real = csrf(client)["X-CSRF-Token"]
        headers: dict[str, str] = {
            "missing": {},
            "empty": {"X-CSRF-Token": ""},
            "wrong": {"X-CSRF-Token": "0" * 64},
            "upper": {"X-CSRF-Token": real.upper()},
            "padded": {"X-CSRF-Token": f" {real} "},
            "cookie-and-header-both-attacker-chosen": {"X-CSRF-Token": "attacker"},
        }[variant]
        if variant == "cookie-and-header-both-attacker-chosen":
            client.cookies.set("csrf_token", "attacker")
        response = client.post(LOGOUT, headers=headers)
        still_alive = client.get(ME)
    assert_problem(response, 403, "CSRF_INVALID")
    assert still_alive.status_code == 200


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("path", [LOGOUT, REFRESH])
async def test_a_non_ascii_csrf_header_is_a_403_not_a_500(
    path: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, user.email)
        response = client.post(path, headers={"X-CSRF-Token": bytes([0xE9, 0x74, 0xE9])})
    assert_problem(response, 403, "CSRF_INVALID")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_csrf_token_survives_refresh_because_it_is_bound_to_the_session(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        before = csrf(client)["X-CSRF-Token"]
        assert client.post(REFRESH, headers={"X-CSRF-Token": before}).status_code == 204
        after = csrf(client)["X-CSRF-Token"]
        assert client.post(LOGOUT, headers={"X-CSRF-Token": before}).status_code == 204
    assert before == after


# --------------------------------------------------------------------------
# Refresh
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("swap", ["access-as-refresh", "refresh-as-access"])
async def test_the_two_token_types_are_not_interchangeable(
    swap: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        access = client.cookies.get("access_token")
        refresh = client.cookies.get("refresh_token")
        token = csrf(client)
        client.cookies.clear()
        if swap == "access-as-refresh":
            client.cookies.set("refresh_token", access or "", path="/api/v1/auth")
            response = client.post(REFRESH, headers=token)
        else:
            client.cookies.set("access_token", refresh or "")
            response = client.get(ME)
    assert_problem(response, 401, "AUTH_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("offset", "status"),
    [
        pytest.param(timedelta(days=30) - timedelta(seconds=1), 204, id="expiry-minus-1s"),
        pytest.param(timedelta(days=30), 401, id="exactly-expiry"),
    ],
)
async def test_refresh_expiry_boundary(
    offset: timedelta, status: int, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    t0 = datetime.now(UTC).replace(microsecond=0)
    with client_for(main_app) as client:
        with time_machine.travel(t0, tick=False):
            login(client, user.email)
        with time_machine.travel(t0 + offset, tick=False):
            response = client.post(REFRESH, headers=csrf(client))
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_refresh_after_logout_is_refused(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        token = csrf(client)
        refresh = client.cookies.get("refresh_token")
        assert client.post(LOGOUT, headers=token).status_code == 204
        client.cookies.set("refresh_token", refresh or "", path="/api/v1/auth")
        response = client.post(REFRESH, headers=token)
    assert_problem(response, 401, "AUTH_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_twenty_parallel_refreshes_of_one_token(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    """At most one rotation succeeds (FR-02); every other request is a replay
    of a now-stale token, so reuse detection revokes the session. No 500s and
    no deadlocks either way."""
    user = await create_user(db_session)
    uid = user.id
    async with running_app(make_app) as app:
        async with async_client(app) as seed:
            await seed.post(LOGIN, json={"email": user.email, "password": PASSWORD})
            refresh = seed.cookies.get("refresh_token")
            token = csrf(seed)
        clients = [async_client(app) for _ in range(20)]
        headers = {**token, "Cookie": f"refresh_token={refresh}"}
        try:
            responses = await asyncio.gather(*(c.post(REFRESH, headers=headers) for c in clients))
        finally:
            for c in clients:
                await c.aclose()
    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(204) == 1, statuses
    assert statuses.count(401) == 19
    db_session.expire_all()
    session = await db_session.scalar(select(SessionModel).where(SessionModel.user_id == uid))
    assert session is not None and session.revoked_at is not None
    assert session.reuse_detected_at is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_logout_after_the_access_token_expired_still_ends_the_session(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    t0 = datetime.now(UTC)
    with client_for(main_app) as client:
        with time_machine.travel(t0, tick=False):
            login(client, user.email)
        # Captured before logout: a successful logout clears the cookies, so
        # replaying them afterwards proves the session is dead on the server,
        # not merely forgotten by this client.
        token = csrf(client)
        refresh = client.cookies.get("refresh_token")
        with time_machine.travel(t0 + timedelta(minutes=20), tick=False):
            logout = client.post(LOGOUT, headers=token)
            assert logout.status_code == 204, logout.text
            assert client.cookies.get("refresh_token") is None
            client.cookies.set("refresh_token", refresh or "", path="/api/v1/auth")
            refresh_after_logout = client.post(REFRESH, headers=token)
    assert_problem(refresh_after_logout, 401, "AUTH_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_access_token_lives_out_its_fifteen_minutes_after_logout(
    db_session: AsyncSession,
) -> None:
    """BUG-27, an accepted trade-off (ADR-006, ADR-018; README "Logout, and the
    15-minute access-token tail"). Authentication checks the signature and the
    account-wide auth_epoch, not the session row, so a copy of the access token
    taken before logout keeps working until it expires - and not one second
    longer. If this ever starts failing because the copy is refused sooner,
    that is a deliberate design change: update the README and ADRs with it."""
    user = await create_user(db_session)
    t0 = datetime.now(UTC)
    with client_for(main_app) as client:
        with time_machine.travel(t0, tick=False):
            login(client, user.email)
            stolen = client.cookies.get("access_token")
            assert client.post(LOGOUT, headers=csrf(client)).status_code == 204
            assert client.cookies.get("access_token") is None
        client.cookies.set("access_token", stolen or "")
        with time_machine.travel(t0 + timedelta(minutes=15) - timedelta(seconds=1), tick=False):
            last_second = client.get(ME)
        with time_machine.travel(t0 + timedelta(minutes=15), tick=False):
            expired = client.get(ME)
    assert last_second.status_code == 200, last_second.text
    assert_problem(expired, 401, "AUTH_REQUIRED")
