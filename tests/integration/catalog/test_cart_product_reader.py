"""`SqlCartProductReader` (VS-022 plan §3.1): one query per batch, and the same
visibility rule as the storefront, through the one shared `listed_predicate()`."""

import ast
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.infrastructure.cart_product_reader import SqlCartProductReader
from app.catalog.infrastructure.models import CategoryModel, ProductImageModel, ProductModel
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import Refs, seed_product, seed_refs
from tests.integration.deep_support import client_for

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

SRC = Path(__file__).resolve().parents[3] / "src" / "app" / "catalog" / "infrastructure"


async def _change(db: AsyncSession, refs: Refs, product: ProductModel, how: str) -> None:
    now = datetime.now(UTC)
    changes: dict[str, dict[str, Any]] = {
        "visible": {},
        "hidden": {"is_visible": False},
        "deleted": {"deleted_at": now},
        "unavailable": {"is_available": False},
        "whatsapp_only": {"purchase_mode": PurchaseMode.WHATSAPP_ONLY},
    }
    product_values = changes.get(how, {})
    if how in ("category_inactive", "category_archived"):
        values = {"is_active": False} | ({"deleted_at": now} if how == "category_archived" else {})
        await db.execute(
            update(CategoryModel).where(CategoryModel.id == refs.category.id).values(**values)
        )
    elif product_values:
        await db.execute(
            update(ProductModel).where(ProductModel.id == product.id).values(**product_values)
        )
    await db.commit()


CASES = [
    ("visible", True),
    ("hidden", False),
    ("deleted", False),
    ("category_inactive", False),
    ("category_archived", False),
    ("unavailable", True),
    ("whatsapp_only", True),
]


@pytest.mark.parametrize(("how", "listed"), CASES)
async def test_the_cart_reader_and_the_storefront_agree_on_listed(
    db_session: AsyncSession, db_engine: AsyncEngine, how: str, listed: bool
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    await _change(db_session, refs, product, how)

    async with AsyncSession(db_engine) as session:
        found = (await SqlCartProductReader(session).get_many([product.id]))[product.id]
    with client_for(main_app) as client:
        status = client.get(f"/api/v1/products/{product.slug}").status_code

    assert found.listed is listed
    assert status == (200 if listed else 404)


async def test_one_query_for_a_batch_with_covers_and_unknown_ids(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    refs = await seed_refs(db_session)
    physical = await seed_product(db_session, refs, price_cents=2500)
    stl = await seed_product(db_session, refs, type=ProductType.STL)
    cover = ProductImageModel(
        product_id=physical.id,
        storage_key=f"products/{uuid.uuid4()}.webp",
        sort_order=0,
        is_cover=True,
    )
    db_session.add(cover)
    await db_session.commit()
    unknown = uuid.uuid4()

    statements: list[str] = []

    def _count(*args: Any) -> None:
        statements.append(args[2])

    event.listen(db_engine.sync_engine, "before_cursor_execute", _count)
    try:
        async with AsyncSession(db_engine) as session:
            found = await SqlCartProductReader(session).get_many(
                [physical.id, stl.id, unknown, physical.id]
            )
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", _count)

    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == 1
    assert set(found) == {physical.id, stl.id}
    assert found[physical.id].price_cents == 2500
    assert found[physical.id].max_quantity_per_line == 5
    found_cover = found[physical.id].cover
    assert found_cover is not None
    assert found_cover.id == cover.id
    assert found[stl.id].type is ProductType.STL
    assert found[stl.id].max_quantity_per_line is None
    assert found[stl.id].cover is None


async def test_an_empty_batch_runs_no_query(db_engine: AsyncEngine) -> None:
    async with AsyncSession(db_engine) as session:
        assert await SqlCartProductReader(session).get_many([]) == {}


def _calls_listed_predicate(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "listed_predicate"
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize("module", ["storefront_query.py", "cart_product_reader.py"])
def test_visibility_is_never_restated(module: str) -> None:
    """Both readers call the one predicate and define no visibility terms of their own."""
    path = SRC / module
    source = path.read_text(encoding="utf-8")
    assert _calls_listed_predicate(path)
    assert "is_visible.expression" not in source
    assert "is_active.expression" not in source
