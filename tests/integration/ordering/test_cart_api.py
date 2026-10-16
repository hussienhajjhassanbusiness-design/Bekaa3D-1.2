"""VS-022 / FR-05: `/api/v1/cart*` - merging, caps, the verified-write boundary,
products that change after being added, and the line and rate limits (plan §6)."""

import os
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import pytest
import redis.asyncio as redis_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.infrastructure.models import CategoryModel, ProductImageModel, ProductModel
from app.identity.infrastructure.models import UserModel
from app.main import app as main_app
from app.ordering.domain.entities import MAX_CART_LINES
from app.ordering.infrastructure.models import CartItemModel, CartModel
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import Refs, seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user, csrf, login

CART = "/api/v1/cart"
ITEMS = f"{CART}/items"
pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _signed_in(client: TestClient, db: AsyncSession, *, verified: bool = True) -> UserModel:
    user = await create_user(db, verified=verified)
    login(client, user.email)
    return user


def _add(client: TestClient, product_id: UUID, quantity: int | None = None) -> httpx.Response:
    body: dict[str, Any] = {"product_id": str(product_id)}
    if quantity is not None:
        body["quantity"] = quantity
    response: httpx.Response = client.post(ITEMS, json=body, headers=csrf(client))
    return response


def _patch(client: TestClient, product_id: UUID, quantity: int) -> httpx.Response:
    response: httpx.Response = client.patch(
        f"{ITEMS}/{product_id}", json={"quantity": quantity}, headers=csrf(client)
    )
    return response


def _delete(client: TestClient, product_id: UUID) -> httpx.Response:
    response: httpx.Response = client.delete(f"{ITEMS}/{product_id}", headers=csrf(client))
    return response


def _line(cart: dict[str, Any], product_id: UUID) -> dict[str, Any]:
    found: list[dict[str, Any]] = [i for i in cart["items"] if i["product_id"] == str(product_id)]
    assert len(found) == 1, cart
    return found[0]


async def _set(db: AsyncSession, product: ProductModel, **values: Any) -> None:
    await db.execute(update(ProductModel).where(ProductModel.id == product.id).values(**values))
    await db.commit()


async def _cart_rows(db: AsyncSession, user_id: UUID) -> int:
    return await db.scalar(select(func.count()).where(CartModel.user_id == user_id)) or 0


async def _line_rows(db: AsyncSession, user_id: UUID) -> list[CartItemModel]:
    stmt = (
        select(CartItemModel)
        .join(CartModel, CartModel.id == CartItemModel.cart_id)
        .where(CartModel.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return list((await db.scalars(stmt)).all())


def _comparable(response: httpx.Response) -> dict[str, Any]:
    """The problem body without the per-request fields."""
    body: dict[str, Any] = response.json()
    return {k: v for k, v in body.items() if k not in ("request_id", "instance")}


# -------------------------------------------------------------- happy paths


async def test_add_read_patch_delete_round_trip(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    physical = await seed_product(db_session, refs, price_cents=1500)
    stl = await seed_product(db_session, refs, type=ProductType.STL, price_cents=900)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        assert _add(client, physical.id, 2).status_code == 200
        added = _add(client, stl.id)
        cart = client.get(CART).json()
        patched = _patch(client, physical.id, 4)
        deleted = _delete(client, stl.id)
        after = client.get(CART).json()

    assert added.status_code == 200
    assert cart["contains_physical"] and cart["contains_digital"]
    line = _line(cart, physical.id)
    assert line["quantity"] == 2
    assert (
        line["snapshot_price"]
        == line["current_price"]
        == {
            "amount_cents": 1500,
            "currency": "USD",
        }
    )
    assert (line["price_changed"], line["over_cap"], line["purchasable"]) == (False, False, True)
    assert (line["max_quantity"], line["unpurchasable_reason"]) == (5, None)
    assert _line(cart, stl.id)["max_quantity"] is None
    assert patched.status_code == 200
    assert _line(patched.json(), physical.id)["quantity"] == 4
    assert deleted.status_code == 204
    assert [i["product_id"] for i in after["items"]] == [str(physical.id)]
    assert (after["contains_physical"], after["contains_digital"]) == (True, False)
    assert "total" not in after and all("total" not in i for i in after["items"])


async def test_adding_the_same_product_twice_merges_into_one_line(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        _add(client, product.id, 2)
        merged = _add(client, product.id, 3)
    assert _line(merged.json(), product.id)["quantity"] == 5
    assert len(await _line_rows(db_session, user.id)) == 1


async def test_re_adding_an_stl_is_a_no_op(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    stl = await seed_product(db_session, refs, type=ProductType.STL)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        _add(client, stl.id)
        again = _add(client, stl.id, 1)
    assert again.status_code == 200
    assert [i["quantity"] for i in again.json()["items"]] == [1]


async def test_a_cover_image_is_shown_for_a_listed_product(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    key = f"products/{uuid.uuid4()}.webp"
    db_session.add(
        ProductImageModel(product_id=product.id, storage_key=key, sort_order=0, is_cover=True)
    )
    await db_session.commit()
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        cover = _line(_add(client, product.id).json(), product.id)["cover_image"]
    assert cover["url"].endswith(key)


# ---------------------------------------------------- the verified boundary


async def test_an_unverified_user_reads_an_empty_cart_and_cannot_write(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session, verified=False)
        read = client.get(CART)
        writes = [_add(client, product.id), _patch(client, product.id, 1)]
        writes.append(_delete(client, product.id))
    assert read.status_code == 200
    assert read.json() == {
        "id": None,
        "items": [],
        "contains_physical": False,
        "contains_digital": False,
        "updated_at": None,
    }
    for response in writes:
        assert_problem(response, 403, "EMAIL_VERIFICATION_REQUIRED")
        assert "ratelimit-remaining" not in response.headers
    assert await _cart_rows(db_session, user.id) == 0


async def test_anonymous_callers_get_401_everywhere() -> None:
    product_id = uuid.uuid4()
    with client_for(main_app) as client:
        responses = [
            client.get(CART),
            client.post(ITEMS, json={"product_id": str(product_id)}),
            client.patch(f"{ITEMS}/{product_id}", json={"quantity": 1}),
            client.delete(f"{ITEMS}/{product_id}"),
        ]
    for response in responses:
        assert_problem(response, 401)


async def test_a_write_without_the_csrf_header_is_refused(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        response = client.post(ITEMS, json={"product_id": str(product.id)})
    assert_problem(response, 403, "CSRF_INVALID")


async def test_reading_never_creates_a_cart(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        assert client.get(CART).json()["id"] is None
    assert await _cart_rows(db_session, user.id) == 0


# ------------------------------------------------------------------ refusals


async def _not_listed(db: AsyncSession, refs: Refs, how: str) -> UUID:
    if how == "unknown":
        return uuid.uuid4()
    product = await seed_product(db, refs)
    if how == "deleted":
        await _set(db, product, deleted_at=datetime.now(UTC))
    elif how == "hidden":
        await _set(db, product, is_visible=False)
    else:
        await db.execute(
            update(CategoryModel)
            .where(CategoryModel.id == refs.category.id)
            .values(is_active=False)
        )
        await db.commit()
    return product.id


async def test_unknown_deleted_hidden_and_category_off_products_answer_identically(
    db_session: AsyncSession,
) -> None:
    bodies = []
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        for how in ("unknown", "deleted", "hidden", "category_off"):
            product_id = await _not_listed(db_session, await seed_refs(db_session), how)
            response = _add(client, product_id)
            assert_problem(response, 422, "PRODUCT_NOT_PURCHASABLE")
            bodies.append(_comparable(response))
    assert bodies[0]["reason"] == "not_listed"
    assert all(body == bodies[0] for body in bodies)


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ({"purchase_mode": PurchaseMode.WHATSAPP_ONLY}, "whatsapp_only"),
        ({"is_available": False}, "unavailable"),
    ],
)
async def test_unbuyable_products_are_refused_with_their_reason(
    db_session: AsyncSession, values: dict[str, Any], reason: str
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, **values)
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        response = _add(client, product.id)
    assert_problem(response, 422, "PRODUCT_NOT_PURCHASABLE")
    assert response.json()["reason"] == reason
    assert await _line_rows(db_session, user.id) == []


async def test_a_both_mode_physical_product_is_accepted(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, purchase_mode=PurchaseMode.BOTH)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        assert _add(client, product.id).status_code == 200


async def test_stl_quantity_above_one_is_refused_on_add_and_patch(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    stl = await seed_product(db_session, refs, type=ProductType.STL)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        on_add = _add(client, stl.id, 2)
        _add(client, stl.id)
        on_patch = _patch(client, stl.id, 2)
    for response in (on_add, on_patch):
        assert_problem(response, 422, "QUANTITY_EXCEEDS_LIMIT")
        assert response.json()["max_quantity"] == 1


async def test_a_physical_add_over_the_cap_changes_nothing(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, max_quantity_per_line=5)
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        _add(client, product.id, 3)
        response = _add(client, product.id, 3)
    assert_problem(response, 422, "QUANTITY_EXCEEDS_LIMIT")
    body = response.json()
    assert (body["max_quantity"], body["requested"], body["current_quantity"]) == (5, 3, 3)
    [row] = await _line_rows(db_session, user.id)
    assert row.quantity == 3


@pytest.mark.parametrize("quantity", [0, -1, 2_147_483_648, "1", 1.0])
async def test_out_of_range_or_non_integer_quantities_are_validation_errors(
    db_session: AsyncSession, quantity: Any
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        response = _add(client, product.id, quantity)
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_an_unknown_body_field_is_refused(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        body = {"product_id": str(product.id), "price_cents": 1}
        response = client.post(ITEMS, json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")


# --------------------------------------------------------- missing lines (404)


@pytest.mark.parametrize("has_cart", [True, False])
async def test_patch_and_delete_on_a_missing_line_are_404(
    db_session: AsyncSession, has_cart: bool
) -> None:
    refs = await seed_refs(db_session)
    present = await seed_product(db_session, refs)
    absent = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        if has_cart:
            _add(client, present.id)
        responses = [_patch(client, absent.id, 1), _delete(client, absent.id)]
    for response in responses:
        assert_problem(response, 404, "NOT_FOUND")
    assert await _cart_rows(db_session, user.id) == (1 if has_cart else 0)


# --------------------------------------------- products that change after adding


async def test_a_price_change_is_flagged_and_clears_when_restored(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, price_cents=1000)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        _add(client, product.id)
        await _set(db_session, product, price_cents=1200)
        raised = _line(client.get(CART).json(), product.id)
        await _set(db_session, product, price_cents=1000)
        restored = _line(client.get(CART).json(), product.id)
    assert raised["price_changed"] is True
    assert (raised["snapshot_price"]["amount_cents"], raised["current_price"]["amount_cents"]) == (
        1000,
        1200,
    )
    assert restored["price_changed"] is False


@pytest.mark.parametrize("how", ["hidden", "deleted", "category_archived", "category_inactive"])
async def test_a_line_whose_product_stops_being_listed_stays_reduced(
    db_session: AsyncSession, how: str
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, name="Desk lamp")
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        _add(client, product.id)
        now = datetime.now(UTC)
        if how == "hidden":
            await _set(db_session, product, is_visible=False)
        elif how == "deleted":
            await _set(db_session, product, deleted_at=now)
        else:
            values = {"is_active": False} | (
                {"deleted_at": now} if how.endswith("archived") else {}
            )
            await db_session.execute(
                update(CategoryModel).where(CategoryModel.id == refs.category.id).values(**values)
            )
            await db_session.commit()
        line = _line(client.get(CART).json(), product.id)
        removed = _delete(client, product.id)
    assert (line["purchasable"], line["unpurchasable_reason"]) == (False, "not_listed")
    assert line["name"] == "Desk lamp"
    assert (line["slug"], line["current_price"], line["cover_image"], line["max_quantity"]) == (
        None,
        None,
        None,
        None,
    )
    assert line["price_changed"] is False
    assert removed.status_code == 204


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ({"purchase_mode": PurchaseMode.WHATSAPP_ONLY}, "whatsapp_only"),
        ({"is_available": False}, "unavailable"),
    ],
)
async def test_a_line_that_becomes_unbuyable_is_flagged_frozen_and_removable(
    db_session: AsyncSession, values: dict[str, Any], reason: str
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        _add(client, product.id, 2)
        await _set(db_session, product, **values)
        line = _line(client.get(CART).json(), product.id)
        patched = _patch(client, product.id, 1)
        removed = _delete(client, product.id)
    assert (line["purchasable"], line["unpurchasable_reason"]) == (False, reason)
    assert line["slug"] is not None
    assert_problem(patched, 422, "PRODUCT_NOT_PURCHASABLE")
    assert patched.json()["reason"] == reason
    assert removed.status_code == 204


async def test_a_lowered_cap_flags_over_cap_and_allows_only_going_down(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, max_quantity_per_line=5)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        _add(client, product.id, 5)
        await _set(db_session, product, max_quantity_per_line=3)
        line = _line(client.get(CART).json(), product.id)
        up = _patch(client, product.id, 4)
        down = _patch(client, product.id, 3)
    assert (line["over_cap"], line["max_quantity"], line["quantity"]) == (True, 3, 5)
    assert line["purchasable"] is True
    assert_problem(up, 422, "QUANTITY_EXCEEDS_LIMIT")
    assert _line(down.json(), product.id)["over_cap"] is False


async def test_delete_then_re_add_takes_the_new_price(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs, price_cents=1000)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        _add(client, product.id)
        await _set(db_session, product, price_cents=1700)
        merged = _line(_add(client, product.id).json(), product.id)
        _delete(client, product.id)
        fresh = _line(_add(client, product.id).json(), product.id)
    assert merged["snapshot_price"]["amount_cents"] == 1000  # kept on merge (Q3)
    assert fresh["snapshot_price"]["amount_cents"] == 1700
    assert fresh["price_changed"] is False


# ------------------------------------------------------------------- limits


async def test_the_fifty_first_distinct_product_is_refused(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    products = [
        await seed_product(db_session, refs, type=ProductType.STL)
        for _ in range(MAX_CART_LINES + 1)
    ]
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        for product in products[:MAX_CART_LINES]:
            assert _add(client, product.id).status_code == 200
        refused = _add(client, products[-1].id)
        merged = _add(client, products[0].id)
    assert_problem(refused, 422, "CART_LINE_LIMIT_REACHED")
    assert refused.json()["limit"] == 50
    assert merged.status_code == 200


async def test_the_rate_limit_is_per_user_and_reads_are_never_limited(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await seed_product(db_session, refs)
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        first = _add(client, product.id)
        # Spend the rest of the hour's 300 without 299 round trips.
        store = redis_asyncio.from_url(os.environ["REDIS_URL"])  # type: ignore[no-untyped-call]
        await store.set(f"ratelimit:cart:{user.id}", 300, ex=3600)
        await store.aclose()
        limited = _patch(client, product.id, 2)
        reads = [client.get(CART) for _ in range(3)]
    assert first.headers["ratelimit-limit"] == "300"
    assert_problem(limited, 429, "RATE_LIMITED")
    assert "retry-after" in limited.headers
    assert all(r.status_code == 200 for r in reads)


# ---------------------------------------------------------- order and isolation


async def test_lines_keep_add_order_and_never_leak_between_users(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    first, second = await seed_product(db_session, refs), await seed_product(db_session, refs)
    with client_for(main_app) as alice:
        await _signed_in(alice, db_session)
        _add(alice, first.id)
        _add(alice, second.id)
        _patch(alice, first.id, 3)
        order = [i["product_id"] for i in alice.get(CART).json()["items"]]
    with client_for(main_app) as bob:
        await _signed_in(bob, db_session)
        bob_cart = bob.get(CART).json()
        bob_patch = _patch(bob, first.id, 1)
    assert order == [str(first.id), str(second.id)]
    assert bob_cart["items"] == []
    assert_problem(bob_patch, 404, "NOT_FOUND")
