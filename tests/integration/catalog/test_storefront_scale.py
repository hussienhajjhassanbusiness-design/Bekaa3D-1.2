"""NFR-01 / NFR-07 on 10,000 products: browse plans use the SRS 21.3 partial indexes,
and browse stays under 500 ms at p95. The seed is this module's own and is removed."""

import json
import statistics
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.catalog.domain.enums import ProductType
from app.catalog.domain.storefront import StorefrontFilter, StorefrontSort
from app.catalog.infrastructure.models import (
    CategoryModel,
    ColourModel,
    MaterialModel,
    ProductModel,
)
from app.catalog.infrastructure.storefront_query import page_statement
from tests.integration.deep_support import asgi_client

pytestmark = pytest.mark.integration

PRODUCT_COUNT = 10_000
P95_BUDGET_SECONDS = 0.5

_SEED = """
INSERT INTO products (
    type, category_id, name, slug, price_cents, is_visible, is_featured, average_rating,
    review_count, created_at, purchase_mode, material_id, colour_id,
    production_lead_time_days, batch_size, max_quantity_per_line)
SELECT
    CASE WHEN g % 2 = 0 THEN 'physical' ELSE 'stl' END::product_type,
    (CAST(:cats AS uuid[]))[1 + (g / 2) % 5],
    'Scale product ' || g,
    :prefix || g,
    100 + (g * 7919) % 50000,
    g % 7 <> 0,
    g % 17 = 0,
    ((g * 31) % 501) / 100.0,
    g % 50,
    now() - make_interval(mins => g),
    CASE WHEN g % 2 = 0 THEN 'online_only'::purchase_mode END,
    CASE WHEN g % 2 = 0 THEN (CAST(:mats AS uuid[]))[1 + (g / 10) % 3] END,
    CASE WHEN g % 2 = 0 THEN (CAST(:cols AS uuid[]))[1 + (g / 30) % 3] END,
    CASE WHEN g % 2 = 0 THEN 3 END,
    CASE WHEN g % 2 = 0 THEN 1 END,
    CASE WHEN g % 2 = 0 THEN 10 END
FROM generate_series(1, :count) AS g
"""


@dataclass(frozen=True)
class Seed:
    categories: list[uuid.UUID]
    materials: list[uuid.UUID]
    colours: list[uuid.UUID]


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def seed(db_engine: AsyncEngine) -> AsyncGenerator[Seed]:
    token = uuid.uuid4().hex[:10]
    s = Seed(*([uuid.uuid4() for _ in range(n)] for n in (5, 3, 3)))
    async with db_engine.begin() as conn:
        for i, cid in enumerate(s.categories):
            await conn.execute(
                insert(CategoryModel).values(
                    id=cid, name=f"zzz-scale-{token}-{i}", slug=f"scale-{token}-{i}"
                )
            )
        values: list[tuple[type[Any], list[uuid.UUID]]] = [
            (MaterialModel, s.materials),
            (ColourModel, s.colours),
        ]
        for model, ids in values:
            for i, value_id in enumerate(ids):
                await conn.execute(insert(model).values(id=value_id, name=f"zzz-scale-{token}-{i}"))
        await conn.execute(
            text(_SEED),
            {
                "cats": s.categories,
                "mats": s.materials,
                "cols": s.colours,
                "prefix": f"scale-{token}-",
                "count": PRODUCT_COUNT,
            },
        )
    async with db_engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text("ANALYZE products, categories, materials, colours"))
    yield s
    async with db_engine.begin() as conn:
        await conn.execute(delete(ProductModel).where(ProductModel.category_id.in_(s.categories)))
        refs: list[tuple[type[Any], list[uuid.UUID]]] = [
            (CategoryModel, s.categories),
            (MaterialModel, s.materials),
            (ColourModel, s.colours),
        ]
        for model, ids in refs:
            await conn.execute(delete(model).where(model.id.in_(ids)))


def _index_names(node: dict[str, Any]) -> set[str]:
    names = {node["Index Name"]} if "Index Name" in node else set()
    for child in node.get("Plans", []):
        names |= _index_names(child)
    return names


async def _plan(
    engine: AsyncEngine, sort: StorefrontSort, filters: StorefrontFilter
) -> dict[str, Any]:
    stmt = page_statement(limit=21, sort=sort, filters=filters)
    async with engine.connect() as conn:
        compiled = stmt.compile(dialect=conn.dialect)
        params = tuple(compiled.params[name] for name in compiled.positiontup or ())
        result = await conn.exec_driver_sql(f"EXPLAIN (FORMAT JSON) {compiled}", params)
        raw = result.scalar_one()
    plan = json.loads(raw) if isinstance(raw, str) else raw
    return dict(plan[0]["Plan"])


SHAPES: dict[str, tuple[StorefrontSort, Callable[[Seed], StorefrontFilter], str]] = {
    "newest": ("-created_at", lambda s: StorefrontFilter(), "ix_products_browse_newest"),
    "top_rated": ("-average_rating", lambda s: StorefrontFilter(), "ix_products_browse_rating"),
    "type_category_price": (
        "price",
        lambda s: StorefrontFilter(product_type=ProductType.PHYSICAL, category_id=s.categories[1]),
        "ix_products_browse_category",
    ),
    "type_material_colour_price": (
        "-price",
        lambda s: StorefrontFilter(
            product_type=ProductType.PHYSICAL, material_id=s.materials[0], colour_id=s.colours[2]
        ),
        "ix_products_browse_facets",
    ),
}


@pytest.mark.parametrize("shape", SHAPES)
async def test_browse_plans_use_the_partial_indexes(
    db_engine: AsyncEngine, seed: Seed, shape: str
) -> None:
    sort, filters, index = SHAPES[shape]
    plan = await _plan(db_engine, sort, filters(seed))
    assert index in _index_names(plan), json.dumps(plan, indent=1)


@pytest.mark.usefixtures("configured_app")
async def test_browse_p95_is_under_500_ms_on_10k_products(
    seed: Seed, make_app: Callable[[], FastAPI]
) -> None:
    queries: list[dict[str, Any]] = [
        {},
        {"sort": "-average_rating"},
        {"sort": "price", "type": "physical", "category_id": str(seed.categories[0])},
        {"sort": "-price", "material_id": str(seed.materials[1])},
        {"type": "stl", "min_rating": "4", "price_max_cents": "20000"},
        {"featured": "true", "limit": "100"},
    ]
    timings: list[float] = []
    async with asgi_client(make_app) as client:
        await client.get("/api/v1/products")
        for _ in range(8):
            for params in queries:
                start = time.perf_counter()
                first = await client.get("/api/v1/products", params=params)
                timings.append(time.perf_counter() - start)
                assert first.status_code == 200, first.text
                cursor = first.json()["next_cursor"]
                start = time.perf_counter()
                second = await client.get("/api/v1/products", params=params | {"cursor": cursor})
                timings.append(time.perf_counter() - start)
                assert second.status_code == 200, second.text
    p95 = statistics.quantiles(timings, n=20)[-1]
    assert p95 < P95_BUDGET_SECONDS, f"p95 {p95 * 1000:.0f} ms over {len(timings)} requests"
