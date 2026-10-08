"""NFR-01/02/07 on 10,000 products: browse and search plans use the SRS 21.3 indexes;
browse p95 < 500 ms, search p95 < 800 ms. The seed is this module's own and is removed."""

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
from app.catalog.domain.storefront import SearchMode, StorefrontFilter, StorefrontSort
from app.catalog.infrastructure.models import (
    CategoryModel,
    ColourModel,
    MaterialModel,
    ProductModel,
)
from app.catalog.infrastructure.storefront_query import (
    page_statement,
    suggestions_statement,
    trigram_threshold_statement,
)
from tests.integration.deep_support import asgi_client

pytestmark = pytest.mark.integration

PRODUCT_COUNT = 10_000
P95_BUDGET_SECONDS = 0.5
SEARCH_P95_BUDGET_SECONDS = 0.8

_SEED = """
INSERT INTO products (
    type, category_id, name, description, slug, price_cents, is_visible, is_featured,
    average_rating,
    review_count, created_at, purchase_mode, material_id, colour_id,
    production_lead_time_days, batch_size, max_quantity_per_line)
SELECT
    CASE WHEN g % 2 = 0 THEN 'physical' ELSE 'stl' END::product_type,
    (CAST(:cats AS uuid[]))[1 + (g / 2) % 5],
    -- Eight common words, plus `gryphon` on one product in a thousand, for search shapes.
    'Scale ' || (ARRAY['dragon', 'vase', 'lamp', 'planter', 'gear', 'chess', 'bracket',
        'figurine'])[1 + g % 8] || CASE WHEN g % 1000 = 0 THEN ' gryphon' ELSE '' END || ' ' || g,
    'Printed in ' || (ARRAY['PLA', 'PETG', 'resin'])[1 + g % 3] || ' with a matte finish',
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
        # VACUUM, as autovacuum would: it flushes the GIN pending list the bulk insert filled.
        await conn.execute(text("VACUUM ANALYZE products, categories, materials, colours"))
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


async def _plan(engine: AsyncEngine, stmt: Any) -> dict[str, Any]:
    async with engine.connect() as conn:
        await conn.execute(trigram_threshold_statement())
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
    plan = await _plan(db_engine, page_statement(limit=21, sort=sort, filters=filters(seed)))
    assert index in _index_names(plan), json.dumps(plan, indent=1)


SEARCH_SHAPES: dict[str, tuple[Any, str]] = {
    "full_text": (
        page_statement(limit=21, sort="-relevance", filters=StorefrontFilter(q="gryphon")),
        "ix_products_search_vector",
    ),
    "fuzzy": (
        page_statement(
            limit=21,
            sort="-relevance",
            filters=StorefrontFilter(q="gryphn"),
            mode=SearchMode.FUZZY,
        ),
        "ix_products_name_trgm",
    ),
    "suggestions": (suggestions_statement("gryph", 10), "ix_products_name_trgm"),
}


@pytest.mark.parametrize("shape", SEARCH_SHAPES)
async def test_search_plans_use_the_gin_indexes(
    db_engine: AsyncEngine, seed: Seed, shape: str
) -> None:
    stmt, index = SEARCH_SHAPES[shape]
    plan = await _plan(db_engine, stmt)
    assert index in _index_names(plan), json.dumps(plan, indent=1)


@pytest.mark.usefixtures("configured_app")
async def test_search_p95_is_under_800_ms_on_10k_products(
    seed: Seed, make_app: Callable[[], FastAPI]
) -> None:
    searches: list[tuple[str, dict[str, Any]]] = [
        ("/api/v1/products", {"q": "dragon"}),
        ("/api/v1/products", {"q": "dragon", "sort": "price", "type": "physical"}),
        ("/api/v1/products", {"q": "dragn", "limit": "100"}),
        ("/api/v1/products", {"q": "gryphon"}),
        ("/api/v1/products", {"q": "gryphn", "material_id": str(seed.materials[0])}),
        ("/api/v1/products", {"q": "resin figurine", "sort": "-average_rating"}),
        ("/api/v1/products", {"q": "zzqqxx"}),
        ("/api/v1/search/suggestions", {"q": "drag"}),
        ("/api/v1/search/suggestions", {"q": "plnter"}),
    ]
    timings: list[float] = []
    async with asgi_client(make_app) as client:
        await client.get("/api/v1/products", params={"q": "warm"})
        for _ in range(6):
            for path, params in searches:
                start = time.perf_counter()
                first = await client.get(path, params=params)
                timings.append(time.perf_counter() - start)
                assert first.status_code == 200, first.text
                if cursor := first.json().get("next_cursor"):
                    start = time.perf_counter()
                    second = await client.get(path, params=params | {"cursor": cursor})
                    timings.append(time.perf_counter() - start)
                    assert second.status_code == 200, second.text
    p95 = statistics.quantiles(timings, n=20)[-1]
    assert p95 < SEARCH_P95_BUDGET_SECONDS, f"p95 {p95 * 1000:.0f} ms over {len(timings)}"


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
