"""FR-01 concurrent access, for search: inserts that lift full-text hits past the fallback
threshold mid-walk never drop the trigram matches already promised. The cursor pins the mode."""

import asyncio
from collections.abc import Callable
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


async def _read(client: httpx.AsyncClient, params: dict[str, Any]) -> Any:
    response = await client.get("/api/v1/products", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _reader(
    client: httpx.AsyncClient, refs: Refs, barriers: list[asyncio.Barrier]
) -> tuple[list[str], list[str]]:
    params = {"category_id": str(refs.category.id), "q": "lamp", "sort": "price", "limit": 2}
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
    # Two more full-text hits make six: a fresh first page would no longer fall back.
    for price in (50, 950):
        out.append(await seed_product(db, refs, name="Lamp", price_cents=price))
    await meet_or_fail(barriers[1])


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.usefixtures("configured_app")
async def test_search_paging_keeps_its_mode_when_inserts_flip_the_threshold(
    db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    refs = await seed_refs(db_session)
    names = ["Lamp", "Lampshade", "Lamp", "Lampshade", "Lamp", "Lampshade", "Lamp"]
    originals = [
        await seed_product(db_session, refs, name=name, price_cents=100 * (i + 1))
        for i, name in enumerate(names)
    ]
    inserted: list[ProductModel] = []
    barriers = [asyncio.Barrier(2), asyncio.Barrier(2)]
    async with asgi_client(make_app) as client:
        (first, rest), _ = await asyncio.gather(
            _reader(client, refs, barriers), _inserter(db_session, refs, barriers, inserted)
        )
        fresh = await _read(
            client, {"category_id": str(refs.category.id), "q": "lamp", "limit": 100}
        )

    assert first == [str(p.id) for p in originals[:2]]
    late = inserted[1]
    assert rest == [str(p.id) for p in originals[2:]] + [str(late.id)]
    seen = first + rest
    assert len(seen) == len(set(seen))
    shades = {str(p.id) for p in originals if p.name == "Lampshade"}
    assert not shades & {item["id"] for item in fresh["items"]}, "six hits: no fallback now"
