"""`GET /api/v1/products` and `/products/{slug}` (VS-015): visibility, facets, sorts,
cursors, payload allowlist and errors. Each test owns its category, so the shared DB
cannot make a negative assertion pass vacuously (VS-010 audit A-06)."""

import base64
import itertools
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.api.product_cursor import encode_cursor
from app.catalog.domain.enums import AcceptedPaymentMethods, ProductType, PurchaseMode
from app.catalog.infrastructure.models import (
    CategoryModel,
    MaterialModel,
    ProductImageModel,
    ProductModel,
)
from app.core.config import get_settings
from app.main import app as main_app
from tests.catalog_seed import register, retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import Refs, seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for

PRODUCTS = "/api/v1/products"

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _get(client: TestClient, path: str = PRODUCTS, **params: Any) -> Any:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _ids(payload: Any) -> list[str]:
    return [item["id"] for item in payload["items"]]


def _walk(client: TestClient, limit: int, **params: Any) -> list[str]:
    """Every page in order; a repeated cursor would loop, so cap the walk."""
    seen: list[str] = []
    cursor = None
    for _ in range(100):
        page = _get(client, limit=limit, **params, **({"cursor": cursor} if cursor else {}))
        seen += _ids(page)
        cursor = page["next_cursor"]
        if cursor is None:
            return seen
    pytest.fail("pagination never ended")


# ---------------------------------------------------------------- visibility


async def _hide(db: AsyncSession, refs: Refs, product: ProductModel, how: str) -> None:
    now = datetime.now(UTC)
    if how == "hidden":
        stmt: Any = update(ProductModel).values(is_visible=False)
    elif how == "deleted":
        stmt = update(ProductModel).values(deleted_at=now)
    else:
        values = {"is_active": False} | ({"deleted_at": now} if how == "archived" else {})
        await db.execute(
            update(CategoryModel).where(CategoryModel.id == refs.category.id).values(**values)
        )
        await db.commit()
        return
    await db.execute(stmt.where(ProductModel.id == product.id))
    await db.commit()


INVISIBLE = ["hidden", "deleted", "category_disabled", "archived"]


@pytest.mark.parametrize("how", INVISIBLE)
async def test_invisible_products_are_excluded_from_the_list(
    db_session: AsyncSession, how: str
) -> None:
    gone_refs, kept_refs = await seed_refs(db_session), await seed_refs(db_session)
    gone = await seed_product(db_session, gone_refs)
    kept = await seed_product(db_session, kept_refs)
    await _hide(db_session, gone_refs, gone, how)
    with client_for(main_app) as client:
        assert _ids(_get(client, category_id=str(gone_refs.category.id))) == []
        newest = _ids(_get(client, limit=100))
    assert str(kept.id) in newest, "the control product must show, or this proves nothing"
    assert str(gone.id) not in newest


@pytest.mark.parametrize("how", INVISIBLE)
async def test_invisible_products_have_no_detail_page(db_session: AsyncSession, how: str) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        assert client.get(f"{PRODUCTS}/{product.slug}").status_code == 200
        await _hide(db_session, refs, product, how)
        assert_problem(client.get(f"{PRODUCTS}/{product.slug}"), 404, "NOT_FOUND")


async def test_anonymous_visitors_can_browse_without_cookies(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        assert not client.cookies
        assert _ids(_get(client, category_id=str(refs.category.id))) == [str(product.id)]
        assert _get(client, f"{PRODUCTS}/{product.slug}")["id"] == str(product.id)


async def test_an_unavailable_product_is_listed_and_served_but_marked(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, is_available=False)
    with client_for(main_app) as client:
        [item] = _get(client, category_id=str(refs.category.id))["items"]
        detail = _get(client, f"{PRODUCTS}/{product.slug}")
    assert item["is_available"] is False
    assert detail["is_available"] is False
    assert detail["capabilities"]["can_add_to_cart"] is False


async def test_hiding_a_product_removes_it_from_the_next_page(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        await seed_product(db_session, refs, created_at=base - timedelta(minutes=i))
        for i in range(3)
    ]
    with client_for(main_app) as client:
        first = _get(client, category_id=str(refs.category.id), limit=1)
        assert _ids(first) == [str(rows[0].id)]
        await _hide(db_session, refs, rows[1], "hidden")
        rest = _get(client, category_id=str(refs.category.id), cursor=first["next_cursor"])
    assert _ids(rest) == [str(rows[2].id)]


# ------------------------------------------------------------------- facets


async def test_facets_combine_with_and(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    m, c = refs.materials, refs.colours
    rows: dict[str, dict[str, Any]] = {}
    grid = itertools.product(m, c, (100, 300), (Decimal("2.00"), Decimal("4.50")), (True, False))
    for material, colour, price, rating, featured in grid:
        row = await seed_product(
            db_session,
            refs,
            material_id=material.id,
            colour_id=colour.id,
            price_cents=price,
            average_rating=rating,
            is_featured=featured,
        )
        rows[str(row.id)] = {
            "type": "physical",
            "material_id": str(material.id),
            "colour_id": str(colour.id),
            "price": price,
            "rating": rating,
            "featured": featured,
        }
    for i in range(2):
        row = await seed_product(
            db_session, refs, type=ProductType.STL, price_cents=200, average_rating=Decimal(i * 5)
        )
        rows[str(row.id)] = {
            "type": "stl",
            "material_id": None,
            "colour_id": None,
            "price": 200,
            "rating": Decimal(i * 5),
            "featured": False,
        }

    checks: dict[str, Callable[[dict[str, Any]], bool]] = {
        "type=stl": lambda r: r["type"] == "stl",
        f"material_id={m[1].id}": lambda r: r["material_id"] == str(m[1].id),
        f"colour_id={c[0].id}": lambda r: r["colour_id"] == str(c[0].id),
        "price_min_cents=200": lambda r: r["price"] >= 200,
        "price_max_cents=200": lambda r: r["price"] <= 200,
        "min_rating=4.5": lambda r: r["rating"] >= Decimal("4.5"),
        "featured=true": lambda r: r["featured"] is True,
        "featured=false": lambda r: r["featured"] is False,
    }
    with client_for(main_app) as client:
        for size in (1, 2, 3):
            for combo in itertools.combinations(checks, size):
                params = dict(part.split("=", 1) for part in combo)
                if "featured" in params and sum("featured" in p for p in combo) > 1:
                    continue
                got = _walk(client, 100, category_id=str(refs.category.id), **params)
                expected = {i for i, r in rows.items() if all(checks[k](r) for k in combo)}
                assert len(got) == len(set(got))
                assert set(got) == expected, combo


# -------------------------------------------------------------------- sorts

SORT_KEYS: dict[str, Callable[[ProductModel], Any]] = {
    "price": lambda p: (p.price_cents, p.id),
    "-price": lambda p: (p.price_cents, p.id),
    "-average_rating": lambda p: (p.average_rating, p.id),
    "-created_at": lambda p: (p.created_at, p.id),
}


@pytest.mark.parametrize("sort", SORT_KEYS)
async def test_every_sort_pages_in_order_with_ties_broken_by_id(
    db_session: AsyncSession, sort: str
) -> None:
    refs = await seed_refs(db_session)
    moment = datetime(2026, 5, 1, tzinfo=UTC)
    rows = [
        await seed_product(
            db_session,
            refs,
            price_cents=500 * (i % 2),
            average_rating=Decimal("3.50") if i % 3 else Decimal("1.25"),
            created_at=moment - timedelta(seconds=i % 2),
        )
        for i in range(7)
    ]
    expected = sorted(rows, key=SORT_KEYS[sort], reverse=sort.startswith("-"))
    with client_for(main_app) as client:
        got = _walk(client, 2, category_id=str(refs.category.id), sort=sort)
    assert got == [str(r.id) for r in expected]


@pytest.mark.parametrize("sort", ["price", "-price"])
async def test_paging_past_a_price_above_the_int32_range_works(
    db_session: AsyncSession, sort: str
) -> None:
    refs = await seed_refs(db_session)
    prices = [2**31 - 1, 2**31, 3_000_000_000, 2**62]
    rows = [await seed_product(db_session, refs, price_cents=p) for p in prices]
    expected = sorted(rows, key=lambda r: r.price_cents, reverse=sort == "-price")
    with client_for(main_app) as client:
        got = _walk(client, 1, category_id=str(refs.category.id), sort=sort)
    assert got == [str(r.id) for r in expected]


async def test_the_default_sort_is_newest_first(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    base = datetime(2026, 2, 1, tzinfo=UTC)
    old = await seed_product(db_session, refs, created_at=base)
    new = await seed_product(db_session, refs, created_at=base + timedelta(days=1))
    with client_for(main_app) as client:
        assert _ids(_get(client, category_id=str(refs.category.id))) == [str(new.id), str(old.id)]


# ------------------------------------------------------------------- errors


def _forged(sort: str, key: object) -> str:
    raw = json.dumps({"s": sort, "k": key, "i": str(uuid.uuid4())}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"sort": "name"}, "sort"),
        ({"sort": "-wishlist_count"}, "sort"),
        ({"limit": 0}, "limit"),
        ({"limit": 101}, "limit"),
        ({"type": "digital"}, "type"),
        ({"price_min_cents": -1}, "price_min_cents"),
        ({"price_min_cents": 501, "price_max_cents": 500}, "price_min_cents"),
        ({"min_rating": "5.01"}, "min_rating"),
        ({"min_rating": "NaN"}, "min_rating"),
        ({"min_rating": "3.994"}, "min_rating"),
        ({"category_id": "not-a-uuid"}, "category_id"),
        ({"cursor": "garbage"}, "cursor"),
        ({"cursor": _forged("price", 2**63), "sort": "price"}, "cursor"),
        ({"cursor": _forged("-average_rating", "10"), "sort": "-average_rating"}, "cursor"),
        ({"cursor": encode_cursor("price", 100, uuid.uuid4()), "sort": "-price"}, "cursor"),
        (
            {
                "cursor": encode_cursor("-average_rating", 100, uuid.uuid4()),
                "sort": "-average_rating",
            },
            "cursor",
        ),
    ],
)
def test_bad_query_parameters_are_a_validation_error(params: dict[str, Any], field: str) -> None:
    with client_for(main_app) as client:
        response = client.get(PRODUCTS, params=params)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert ["query", field] in [e["loc"] for e in response.json()["errors"]]


@pytest.mark.parametrize(
    "slug", ["Lamp-UPPER", "no-such-product", "bad_slug", "bad%20slug", "a" * 201]
)
def test_unknown_or_non_canonical_slugs_are_404(slug: str) -> None:
    with client_for(main_app) as client:
        assert_problem(client.get(f"{PRODUCTS}/{slug}"), 404, "NOT_FOUND")


async def test_a_renamed_slug_no_longer_resolves(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    old = product.slug
    await db_session.execute(
        update(ProductModel).where(ProductModel.id == product.id).values(slug=f"{old}-new")
    )
    await db_session.commit()
    with client_for(main_app) as client:
        assert_problem(client.get(f"{PRODUCTS}/{old}"), 404, "NOT_FOUND")
        assert client.get(f"{PRODUCTS}/{old}-new").status_code == 200


@pytest.mark.parametrize("path", [PRODUCTS, f"{PRODUCTS}/some-slug"])
def test_a_postgres_outage_is_a_structured_503(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/db")
    get_settings.cache_clear()
    try:
        with client_for(main_app, raise_server_exceptions=False) as client:
            assert_problem(client.get(path), 503, "SERVICE_UNAVAILABLE")
    finally:
        get_settings.cache_clear()


# ------------------------------------------------------------------ payloads

LIST_KEYS = {
    "id", "type", "name", "slug", "cover_image", "price", "category", "material", "colour",
    "is_available", "purchase_mode", "accepted_payment_methods", "average_rating",
    "review_count", "is_featured",
}  # fmt: skip
DETAIL_KEYS = LIST_KEYS | {
    "description", "images", "seo_title", "seo_description", "og_image_url", "dimensions",
    "production_lead_time_days", "batch_size", "max_quantity_per_line", "capabilities",
}  # fmt: skip


async def _image(db: AsyncSession, product: ProductModel, order: int, cover: bool) -> str:
    row = ProductImageModel(
        product_id=product.id,
        storage_key=f"products/{uuid.uuid4()}.webp",
        alt_text=f"view {order}",
        sort_order=order,
        is_cover=cover,
    )
    db.add(row)
    await db.commit()
    return str(row.id)


async def test_payloads_expose_exactly_the_public_fields(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, weight_grams=120, wishlist_count=9)
    await _image(db_session, product, 0, cover=True)
    with client_for(main_app) as client:
        [item] = _get(client, category_id=str(refs.category.id))["items"]
        detail = _get(client, f"{PRODUCTS}/{product.slug}")
    assert set(item) == LIST_KEYS
    assert set(detail) == DETAIL_KEYS
    image_keys = {"id", "url", "alt_text", "is_cover"}
    assert set(item["cover_image"]) == set(detail["images"][0]) == image_keys


async def test_a_physical_detail_carries_gallery_specs_seo_and_capabilities(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(
        db_session,
        refs,
        purchase_mode=PurchaseMode.BOTH,
        accepted_payment_methods=AcceptedPaymentMethods.CASH,
        description="Hand finished.",
        seo_title="Lamp | Bekaa3D",
        seo_description="A lamp.",
        og_image_url="https://cdn.example.com/og.png",
        dimensions={"length_mm": 100, "width_mm": 50, "height_mm": 20},
        average_rating=Decimal("4.25"),
        review_count=8,
        is_featured=True,
    )
    second = await _image(db_session, product, 1, cover=False)
    cover = await _image(db_session, product, 0, cover=True)
    deleted = ProductImageModel(
        product_id=product.id,
        storage_key=f"products/{uuid.uuid4()}.webp",
        sort_order=2,
        deleted_at=datetime.now(UTC),
    )
    db_session.add(deleted)
    await db_session.commit()
    with client_for(main_app) as client:
        detail = _get(client, f"{PRODUCTS}/{product.slug}")
        [item] = _get(client, category_id=str(refs.category.id))["items"]
    media = get_settings().media_public_url.rstrip("/")
    assert [i["id"] for i in detail["images"]] == [cover, second]
    assert detail["images"][0]["url"].startswith(f"{media}/products/")
    assert detail["cover_image"]["id"] == item["cover_image"]["id"] == cover
    assert detail["price"] == {"amount_cents": 1000, "currency": "USD"}
    assert detail["category"] == {
        "id": str(refs.category.id),
        "name": refs.category.name,
        "slug": refs.category.slug,
    }
    assert detail["material"] == {"id": str(refs.materials[0].id), "name": refs.materials[0].name}
    assert detail["colour"] == {"id": str(refs.colours[0].id), "name": refs.colours[0].name}
    assert detail["dimensions"] == {"length_mm": 100, "width_mm": 50, "height_mm": 20}
    assert (detail["production_lead_time_days"], detail["batch_size"]) == (3, 2)
    assert detail["max_quantity_per_line"] == 5
    assert (detail["seo_title"], detail["seo_description"]) == ("Lamp | Bekaa3D", "A lamp.")
    assert detail["og_image_url"] == "https://cdn.example.com/og.png"
    assert (detail["average_rating"], detail["review_count"]) == (4.25, 8)
    assert detail["purchase_mode"] == "both"
    assert detail["accepted_payment_methods"] == item["accepted_payment_methods"] == "cash"
    assert detail["capabilities"] == {
        "can_add_to_cart": True,
        "can_offer": False,
        "whatsapp_available": True,
    }


async def test_an_stl_detail_has_no_physical_fields_and_can_be_offered(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, type=ProductType.STL)
    with client_for(main_app) as client:
        detail = _get(client, f"{PRODUCTS}/{product.slug}")
    assert detail["type"] == "stl"
    assert detail["cover_image"] is None and detail["images"] == []
    physical = (
        "purchase_mode",
        "accepted_payment_methods",
        "material",
        "colour",
        "dimensions",
        "production_lead_time_days",
    )
    assert all(detail[name] is None for name in physical)
    assert detail["capabilities"] == {
        "can_add_to_cart": True,
        "can_offer": True,
        "whatsapp_available": False,
    }


async def test_a_disabled_material_still_shows_on_its_product(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    await db_session.execute(
        update(MaterialModel)
        .where(MaterialModel.id == refs.materials[0].id)
        .values(is_active=False)
    )
    await db_session.commit()
    with client_for(main_app) as client:
        detail = _get(client, f"{PRODUCTS}/{product.slug}")
    assert detail["material"]["id"] == str(refs.materials[0].id)
