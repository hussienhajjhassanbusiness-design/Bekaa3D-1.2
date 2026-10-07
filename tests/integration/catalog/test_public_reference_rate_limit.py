"""The public reference lists are rate limited, and say so the standard way.

api-endpoints.md lists `429` as the only error these three endpoints can return,
so the limiter is part of their contract rather than optional hardening.

The policy is asserted from `PUBLIC_RATE_LIMIT` rather than from a number copied
into this file. That matters: 600/hour is a V1 operational decision that may well
be revised, and a test hardcoding it would have to be edited alongside the policy
- and would silently stop proving anything if the two drifted.
"""

import pytest
import redis.asyncio as redis_asyncio
from fastapi.testclient import TestClient

from app.catalog.api.reference_data import PUBLIC_RATE_LIMIT, PUBLIC_RATE_WINDOW_SECONDS
from app.core.config import get_settings

CATEGORIES = "/api/v1/categories"
MATERIALS = "/api/v1/materials"

# Mirrors `rate_limiter`'s key construction: one counter per prefix per client
# IP. Every request in the suite arrives from the same TestClient host, so the
# counters are shared and have to be cleared explicitly.
_LIMITER_KEYS = "ratelimit:catalogue:*"


async def _clear_limiters() -> None:
    """Reset only this slice's counters.

    Redis is a session-scoped container and `configured_app` flushes it once at
    setup, so without this the test would inherit whatever count earlier tests
    left behind and pass or fail depending on collection order.
    """
    redis = redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    async for key in redis.scan_iter(_LIMITER_KEYS):
        await redis.delete(key)
    await redis.aclose()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_public_lists_are_rate_limited_with_the_standard_contract() -> None:
    """Exhaust one endpoint's window, then check the refusal is an ordinary
    RATE_LIMITED problem document rather than something invented here.

    The requests are real rather than a pre-seeded counter, so this proves the
    limiter is actually wired to the route - a seeded counter would prove only
    that `rate_limiter` works, which VS-002 already established.
    """
    from app.main import app

    await _clear_limiters()
    try:
        with TestClient(app) as client:
            allowed = [client.get(CATEGORIES) for _ in range(PUBLIC_RATE_LIMIT)]
            refused = client.get(CATEGORIES)

        assert {response.status_code for response in allowed} == {200}

        # Standard headers on success, not only on refusal, so a client can back
        # off before being refused.
        assert allowed[0].headers["RateLimit-Limit"] == str(PUBLIC_RATE_LIMIT)
        assert allowed[0].headers["RateLimit-Remaining"] == str(PUBLIC_RATE_LIMIT - 1)

        assert refused.status_code == 429
        assert refused.headers["content-type"] == "application/problem+json"
        assert refused.headers["RateLimit-Limit"] == str(PUBLIC_RATE_LIMIT)
        assert refused.headers["RateLimit-Remaining"] == "0"
        # RFC 9110 10.2.3: a 429 says when to come back (BUG-11, audit A-08).
        retry_after = int(refused.headers["Retry-After"])
        assert 0 < retry_after <= PUBLIC_RATE_WINDOW_SECONDS

        body = refused.json()
        assert body["code"] == "RATE_LIMITED"
        assert body["status"] == 429
        assert body["instance"] == CATEGORIES
        assert body["request_id"]
    finally:
        await _clear_limiters()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_each_reference_endpoint_counts_independently() -> None:
    """Exhausting categories must not refuse materials.

    They are separate counters by design - a storefront hammering one facet list
    should not take the others down with it - and a single shared prefix would
    quietly couple them.
    """
    from app.main import app

    await _clear_limiters()
    try:
        with TestClient(app) as client:
            for _ in range(PUBLIC_RATE_LIMIT):
                client.get(CATEGORIES)
            categories_refused = client.get(CATEGORIES)
            materials_still_served = client.get(MATERIALS)

        assert categories_refused.status_code == 429
        assert materials_still_served.status_code == 200
        assert materials_still_served.headers["RateLimit-Remaining"] == str(PUBLIC_RATE_LIMIT - 1)
    finally:
        await _clear_limiters()
