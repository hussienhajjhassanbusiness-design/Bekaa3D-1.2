"""VS-036 audit A-08: a write without the CSRF header is refused before its rate limit
counts it, so a cross-site request cannot spend a customer's or an administrator's budget."""

import os
import uuid

import pytest
import redis.asyncio as redis_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as main_app
from tests.integration.deep_support import (
    PASSWORD,
    assert_problem,
    client_for,
    create_user,
    csrf,
    fresh_ip,
    login,
    mfa_admin,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

ANY = uuid.UUID(int=1)
ROUTES = [
    ("POST", "/api/v1/reviews", "reviews"),
    ("PATCH", f"/api/v1/reviews/{ANY}", "reviews"),
    ("DELETE", f"/api/v1/reviews/{ANY}", "reviews"),
    ("POST", "/api/v1/cart/items", "cart"),
    ("PATCH", f"/api/v1/cart/items/{ANY}", "cart"),
    ("DELETE", f"/api/v1/cart/items/{ANY}", "cart"),
    ("PUT", f"/api/v1/me/wishlist/{ANY}", "wishlist"),
    ("DELETE", f"/api/v1/me/wishlist/{ANY}", "wishlist"),
    ("POST", "/api/v1/offers", "offers"),
    ("POST", f"/api/v1/me/offers/{ANY}/counter", "offer_actions"),
    ("POST", f"/api/v1/me/offers/{ANY}/accept", "offer_actions"),
    ("POST", f"/api/v1/me/offers/{ANY}/withdraw", "offer_actions"),
]


async def _counter(prefix: str, subject: object) -> bytes | None:
    store = redis_asyncio.from_url(os.environ["REDIS_URL"])  # type: ignore[no-untyped-call]
    try:
        value: bytes | None = await store.get(f"ratelimit:{prefix}:{subject}")
        return value
    finally:
        await store.aclose()


@pytest.mark.parametrize(
    ("method", "path", "prefix"), ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES]
)
async def test_a_write_without_csrf_is_refused_before_the_limit_counts_it(
    method: str, path: str, prefix: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        refused = client.request(method, path, json={})
        assert_problem(refused, 403, "CSRF_INVALID")
        assert await _counter(prefix, user.id) is None
        counted = client.request(method, path, json={}, headers=csrf(client))
    assert counted.status_code != 403
    assert await _counter(prefix, user.id) == b"1"


async def test_regenerating_recovery_codes_without_csrf_spends_no_attempt(
    db_session: AsyncSession,
) -> None:
    """The limit is per IP (5 an hour) and guards a password check, so it is worth more."""
    path, prefix = "/api/v1/auth/mfa/recovery-codes/regenerate", "auth:mfa:recovery"
    body, ip = {"current_password": PASSWORD}, fresh_ip()
    with client_for(main_app, ip=ip) as client:
        await mfa_admin(client, db_session)
        before = await _counter(prefix, ip)
        refused = client.post(path, json=body)
        assert_problem(refused, 403, "CSRF_INVALID")
        assert await _counter(prefix, ip) == before
        regenerated = client.post(path, json=body, headers=csrf(client))
    assert regenerated.status_code == 200, regenerated.text
    assert await _counter(prefix, ip) == str(int(before or 0) + 1).encode()
