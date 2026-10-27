"""Helpers for the VS-043 analytics tests. The test database is shared, so each revenue test
moves its payments onto a Beirut day no other paid payment uses (`free_day`)."""

import random
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

ANALYTICS = "/api/v1/admin/analytics"
BEIRUT = ZoneInfo("Asia/Beirut")
_PAID = "status IN ('paid', 'partially_refunded', 'refunded')"


async def free_day(engine: AsyncEngine) -> date:
    """A 2021-2024 day whose neighbours too hold no paid payment (no Beirut edge spill)."""
    rng = random.SystemRandom()
    async with engine.connect() as conn:
        for _ in range(50):
            day = date(2021, 1, 1) + timedelta(days=rng.randrange(1400))
            lower = datetime.combine(day - timedelta(days=1), time.min, UTC)
            used = await conn.scalar(
                text(
                    f"SELECT count(*) FROM payments WHERE {_PAID}"
                    " AND verified_at >= :lo AND verified_at < :hi"
                ),
                {"lo": lower, "hi": lower + timedelta(days=4)},
            )
            if not used:
                return day
    raise AssertionError("no free day found")


def beirut_noon(day: date) -> datetime:
    return datetime.combine(day, time(12), BEIRUT).astimezone(UTC)


async def paid_at(engine: AsyncEngine, order_id: uuid.UUID, moment: datetime) -> None:
    """Moves the order's paid payment to `moment` (its verification, or cash handover)."""
    async with engine.begin() as conn:
        moved = await conn.execute(
            text(
                f"UPDATE payments SET initiated_at = :m, verified_at = :m"
                f" WHERE order_id = :o AND {_PAID}"
            ),
            {"m": moment, "o": order_id},
        )
    assert moved.rowcount == 1


def report(client: TestClient, path: str, **params: Any) -> httpx.Response:
    query = {("from" if key == "from_" else key): str(value) for key, value in params.items()}
    response: httpx.Response = client.get(f"{ANALYTICS}/{path}", params=query)
    return response


def body(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    assert response.status_code == status, response.text
    found: dict[str, Any] = response.json()
    return found


def revenue(client: TestClient, start: object, end: object = None, **params: Any) -> Any:
    return body(report(client, "revenue", from_=start, to=end or start, **params))


def net(found: dict[str, Any]) -> tuple[int, int, int]:
    """(physical, stl, total) net cents of a revenue report."""
    cents = found["totals"]["net"]
    return cents["physical_cents"], cents["stl_cents"], cents["total_cents"]


def stream(found: dict[str, Any], figure: str) -> tuple[int, int]:
    cents = found["totals"][figure]
    return cents["physical_cents"], cents["stl_cents"]
