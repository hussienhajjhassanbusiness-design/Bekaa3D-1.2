"""A public IP-keyed limiter counts each request exactly once.

`rate_limiter` delegates to `enforce_rate_limit` (VS-011); a leftover second
INCR in the wrapper would silently halve every public limit. The Redis counter is
read directly, so the test does not depend on the response headers it also
produces.
"""

import pytest
import redis.asyncio as redis_asyncio
from fastapi.testclient import TestClient

from app.core.config import get_settings

CATEGORIES = "/api/v1/categories"
_KEYS = "ratelimit:catalogue:*"


async def _counters() -> dict[str, int]:
    redis = redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    try:
        return {key.decode(): int(await redis.get(key)) async for key in redis.scan_iter(_KEYS)}
    finally:
        await redis.aclose()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_one_request_to_a_public_limiter_increments_its_counter_by_exactly_one() -> None:
    from app.main import app

    assert await _counters() == {}, "configured_app flushes Redis, so no counter yet"
    with TestClient(app) as client:
        first = client.get(CATEGORIES)
        after_one = await _counters()
        second = client.get(CATEGORIES)
        after_two = await _counters()

    assert first.status_code == second.status_code == 200
    assert list(after_one.values()) == [1], after_one
    assert list(after_two.values()) == [2], after_two
    assert after_one.keys() == after_two.keys()
