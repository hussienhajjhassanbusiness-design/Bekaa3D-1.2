"""`GET /api/v1/settings/public` is rate limited, and says so the standard way.

api-endpoints.md:230 lists `429` as the only error this endpoint can return, so
the limiter is part of its contract rather than an optional hardening.

The policy itself is asserted from `PUBLIC_RATE_LIMIT` rather than from a number
copied into this file. That matters: this is the codebase's first public-read
limit - every other limiter guards an auth route - so its value is an
operational decision that may well be revised. A test that hardcoded 600 would
have to be edited alongside the policy, and would silently stop proving anything
if the two drifted.
"""

import pytest
import redis.asyncio as redis_asyncio
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.platform.api.settings import PUBLIC_RATE_LIMIT

PUBLIC_PATH = "/api/v1/settings/public"

# Mirrors `rate_limiter`'s key construction: one counter per prefix per client
# IP. Every request in the test suite arrives from the same TestClient host, so
# the counter is shared - which is exactly why it has to be cleared explicitly.
_LIMITER_KEYS = "ratelimit:settings:public:*"


async def _clear_limiter() -> None:
    """Reset this endpoint's counters.

    Redis is a session-scoped container and `configured_app` flushes it only
    once, at setup - so without this the test would inherit whatever count
    earlier tests left behind and pass or fail depending on execution order.
    Only this endpoint's prefix is cleared, so other tests' throttle state is
    left alone.
    """
    redis = redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    async for key in redis.scan_iter(_LIMITER_KEYS):
        await redis.delete(key)
    await redis.aclose()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_public_endpoint_is_rate_limited_and_uses_the_standard_contract() -> None:
    """Exhaust the window, then check the refusal is an ordinary RATE_LIMITED
    problem document rather than something this endpoint invented.

    The requests are real rather than a pre-seeded counter, so this proves the
    limiter is actually wired to the route - a seeded counter would prove only
    that `rate_limiter` works, which VS-002 already established.
    """
    from app.main import app

    await _clear_limiter()
    try:
        with TestClient(app) as client:
            allowed = [client.get(PUBLIC_PATH) for _ in range(PUBLIC_RATE_LIMIT)]
            refused = client.get(PUBLIC_PATH)

        # Everything inside the window is served normally.
        assert {response.status_code for response in allowed} == {200}

        # The standard RateLimit-* headers are present on success, not only on
        # refusal, so a client can back off before being refused.
        assert allowed[0].headers["RateLimit-Limit"] == str(PUBLIC_RATE_LIMIT)
        assert allowed[0].headers["RateLimit-Remaining"] == str(PUBLIC_RATE_LIMIT - 1)

        # And the refusal follows the project's error contract: RFC 9457
        # problem+json carrying the stable machine-readable code the client
        # renders from (SRS 22.2).
        assert refused.status_code == 429
        assert refused.headers["content-type"] == "application/problem+json"
        assert refused.headers["RateLimit-Limit"] == str(PUBLIC_RATE_LIMIT)
        assert refused.headers["RateLimit-Remaining"] == "0"

        body = refused.json()
        assert body["code"] == "RATE_LIMITED"
        assert body["status"] == 429
        assert body["instance"] == PUBLIC_PATH
        # Correlation is on every problem response, including this one.
        assert body["request_id"]
    finally:
        # Leave the counter as it was found, so an unlucky ordering cannot make
        # an unrelated test see a 429 from this endpoint.
        await _clear_limiter()
