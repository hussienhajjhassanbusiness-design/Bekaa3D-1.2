"""FR-01 concurrent access: products inserted between two page fetches never make an
existing product repeat or vanish. New rows show only if they sort after the cursor."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.infrastructure.models import ProductModel
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.catalog.storefront_support import Refs, seed_product, seed_refs
from tests.integration.deep_support import asgi_client

BASE = datetime(2026, 3, 1, tzinfo=UTC)


def _values(i: int) -> dict[str, Any]:
    return {
        "price_cents": 100 * i,
        "average_rating": Decimal(i) / 2,
        "created_at": BASE - timedelta(minutes=i),
    }


SORTS: dict[str, Callable[[ProductModel], Any]] = {
    "price": lambda p: (p.price_cents, p.id),
    "-price": lambda p: (p.price_cents, p.id),
    "-average_rating": lambda p: (p.average_rating, p.id),
    "-created_at": lambda p: (p.created_at, p.id),
}


async def _read(client: httpx.AsyncClient, params: dict[str, Any]) -> Any:
    response = await client.get("/api/v1/products", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _reader(
    client: httpx.AsyncClient, refs: Refs, sort: str, barriers: list[asyncio.Barrier]
) -> tuple[list[str], list[str]]:
    params: dict[str, Any] = {"category_id": str(refs.category.id), "sort": sort, "limit": 3}
    first = await _read(client, params)
    await meet_or_fail(barriers[0])
    await meet_or_fail(barriers[1])
    rest: list[str] = []
    cursor = first["next_cursor"]
    while cursor:
        page = await _read(client, params | {"cursor": cursor})
        rest += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
    return [item["id"] for item in first["items"]], rest


async def _inserter(
    db: AsyncSession, refs: Refs, barriers: list[asyncio.Barrier], out: list[ProductModel]
) -> None:
    await meet_or_fail(barriers[0])
    # Before, at and after the page-one boundary (index 3 of 1..6), in every sort.
    for i in (0, 3, 3, 7):
        out.append(await seed_product(db, refs, **_values(i)))
    await meet_or_fail(barriers[1])


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("sort", SORTS)
async def test_paging_sees_each_existing_product_once_despite_inserts(
    db_session: AsyncSession, make_app: Callable[[], FastAPI], sort: str
) -> None:
    refs = await seed_refs(db_session)
    originals = [await seed_product(db_session, refs, **_values(i)) for i in range(1, 7)]
    inserted: list[ProductModel] = []
    barriers = [asyncio.Barrier(2), asyncio.Barrier(2)]
    async with asgi_client(make_app) as client:
        (first, rest), _ = await asyncio.gather(
            _reader(client, refs, sort, barriers),
            _inserter(db_session, refs, barriers, inserted),
        )

    key, descending = SORTS[sort], sort.startswith("-")
    ordered = sorted(originals, key=key, reverse=descending)
    assert first == [str(p.id) for p in ordered[:3]]
    boundary = key(ordered[2])
    after = [
        p for p in originals + inserted if (key(p) < boundary if descending else key(p) > boundary)
    ]
    expected = sorted(after, key=key, reverse=descending)
    assert rest == [str(p.id) for p in expected]
    seen = first + rest
    assert len(seen) == len(set(seen))
    assert {str(p.id) for p in originals} <= set(seen)
