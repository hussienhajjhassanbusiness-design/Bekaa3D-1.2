"""Shared helpers for the deep edge-case suites (`test_deep_*.py`).

Not a test module. Three things the existing helpers do not give the deep
suites, and which they need constantly:

- **A fresh client IP per client.** Every public route is rate limited per IP,
  and the deep suites fire far more requests per test than the per-feature
  suites do. Starlette's `TestClient(client=...)` and httpx's `ASGITransport`
  both let the peer address be chosen, so each client gets its own buckets.
- **Direct user creation.** Registering through the API costs a rate-limit slot
  and an Argon2 hash per user; many deep tests only need an account to exist.
- **Genuinely concurrent requests.** `asgi_client` runs one app instance and
  lets a test `asyncio.gather` N requests against it on one event loop, so N
  transactions really are in flight at once against the real PostgreSQL.
"""

import asyncio
import random
import statistics
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.application.security.password_hasher import hash_password
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import UserModel

PASSWORD = "correct-horse-battery"
SETUP_PATH = "/api/v1/auth/mfa/setup"
CONFIRM_PATH = "/api/v1/auth/mfa/setup/confirm"

PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "code", "request_id", "errors"}


def unique_email(prefix: str = "deep") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def fresh_ip() -> str:
    """A random private address, so no two clients share a rate-limit bucket."""
    return f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def client_for(app: FastAPI, ip: str | None = None, **kwargs: Any) -> TestClient:
    return TestClient(app, client=(ip or fresh_ip(), 50000), **kwargs)


async def create_user(
    db: AsyncSession,
    *,
    email: str | None = None,
    password: str = PASSWORD,
    verified: bool = True,
    role: UserRole = UserRole.CUSTOMER,
    active: bool = True,
) -> UserModel:
    """Insert an account directly, bypassing registration."""
    row = UserModel(
        email=email or unique_email(),
        password_hash=hash_password(password),
        role=role,
        is_active=active,
        email_verified_at=datetime.now(UTC) if verified else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def login(client: TestClient, email: str, password: str = PASSWORD) -> httpx.Response:
    response: httpx.Response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response


def csrf(client: TestClient | httpx.AsyncClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token is not None, "no csrf_token cookie in the jar"
    return {"X-CSRF-Token": token}


async def mfa_admin(client: TestClient, db: AsyncSession) -> tuple[UserModel, str, list[str]]:
    """An administrator whose *current* session in `client` is MFA-complete.

    `/setup/confirm` re-mints the access token with the MFA claim, so no
    second login (and no second TOTP step) is needed. Returns the account, the
    TOTP secret and the recovery codes."""
    user = await create_user(db, role=UserRole.ADMIN)
    login(client, user.email)
    setup = client.post(SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(client))
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    confirm = client.post(
        CONFIRM_PATH, json={"code": pyotp.TOTP(secret).now()}, headers=csrf(client)
    )
    assert confirm.status_code == 200, confirm.text
    return user, secret, list(confirm.json()["recovery_codes"])


def assert_problem(response: httpx.Response, status: int, code: str | None = None) -> None:
    """RFC 9457 shape plus the project's `code`/`request_id`/`errors` fields."""
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert set(body) >= PROBLEM_KEYS, body
    assert body["status"] == status
    assert body["request_id"] == response.headers["x-request-id"]
    if code is not None:
        assert body["code"] == code, body


@asynccontextmanager
async def asgi_client(
    make_app: Callable[[], FastAPI], ip: str | None = None
) -> AsyncGenerator[httpx.AsyncClient]:
    """One running app, driven in-process on the test's own event loop.

    `raise_app_exceptions=False` so a 500 is observed as a response - which is
    what a real client sees - rather than re-raised into the test."""
    app = make_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(
            app=app, client=(ip or fresh_ip(), 50000), raise_app_exceptions=False
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


async def gather_n(n: int, factory: Callable[[int], Awaitable[Any]]) -> list[Any]:
    return list(await asyncio.gather(*(factory(i) for i in range(n))))


@asynccontextmanager
async def running_app(make_app: Callable[[], FastAPI]) -> AsyncGenerator[FastAPI]:
    """One app with its lifespan running, for tests that need several clients
    (each with its own IP and cookie jar) against the same process."""
    app = make_app()
    async with app.router.lifespan_context(app):
        yield app


def async_client(app: FastAPI, ip: str | None = None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(
        app=app, client=(ip or fresh_ip(), 50000), raise_app_exceptions=False
    )
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


# --------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------


def _clock_is_traced() -> bool:
    """A coverage or debug tracer slows each branch in proportion to the Python
    it executes, so wall-clock comparisons between branches are meaningless."""
    import sys

    if sys.gettrace() is not None:
        return True
    try:
        import coverage
    except ImportError:
        return False
    return coverage.Coverage.current() is not None


untraced_clock = pytest.mark.skipif(
    _clock_is_traced(), reason="wall-clock timing is meaningless under a coverage/debug tracer"
)

TIMING_SAMPLES = 12


def distinguishable(a: list[float], b: list[float]) -> bool:
    """Whether two timing samples separate cleanly: their interquartile ranges
    do not overlap. At that point a single response is classified correctly
    well over half the time, which is what an enumeration oracle means."""
    qa, qb = statistics.quantiles(a, n=4), statistics.quantiles(b, n=4)
    return qa[0] > qb[2] or qb[0] > qa[2]


def describe(a: list[float], b: list[float]) -> str:
    def q(xs: list[float]) -> str:
        return "/".join(f"{v * 1000:.0f}" for v in statistics.quantiles(xs, n=4))

    return f"A p25/p50/p75 {q(a)}ms vs B {q(b)}ms"
