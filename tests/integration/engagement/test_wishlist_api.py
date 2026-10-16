"""VS-038 / FR-14: `/api/v1/me/wishlist*` and `/api/v1/admin/analytics/wishlist` -
idempotent add/remove, the verified-write boundary, non-public products, and
`wishlist_count` staying exactly the number of live rows."""

import uuid
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.enums import ProductType
from app.catalog.infrastructure.models import ProductModel
from app.engagement.infrastructure.models import WishlistItemModel
from app.identity.infrastructure.models import UserModel
from app.main import app as main_app
from tests.integration.catalog.storefront_support import Refs, seed_product, seed_refs
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)

PATH = "/api/v1/me/wishlist"
ADMIN_PATH = "/api/v1/admin/analytics/wishlist"
pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _signed_in(client: TestClient, db: AsyncSession, *, verified: bool = True) -> UserModel:
    user = await create_user(db, verified=verified)
    login(client, user.email)
    return user


async def _product(db: AsyncSession, refs: Refs, **over: Any) -> ProductModel:
    over.setdefault("type", ProductType.STL)
    return await seed_product(db, refs, **over)


async def _wishlist_count(db: AsyncSession, product_id: UUID) -> int:
    """`populate_existing`, not `db.expire_all()`: expiring the whole session
    would also expire `product` itself, and a later plain `product.id` read
    (needed to build the next request's URL) would then try to lazy-reload
    outside any async context and raise `MissingGreenlet`."""
    stmt = (
        select(ProductModel)
        .where(ProductModel.id == product_id)
        .execution_options(populate_existing=True)
    )
    return (await db.scalars(stmt)).one().wishlist_count


async def _active_rows(db: AsyncSession, product_id: UUID) -> list[WishlistItemModel]:
    stmt = (
        select(WishlistItemModel)
        .where(WishlistItemModel.product_id == product_id, WishlistItemModel.deleted_at.is_(None))
        .execution_options(populate_existing=True)
    )
    return list((await db.scalars(stmt)).all())


# --------------------------------------------------------------------------
# Add / remove, idempotency, the counter
# --------------------------------------------------------------------------


async def test_add_list_remove_list_round_trip(db_session: AsyncSession) -> None:
    """The slice's smoke test: add a product, see it listed, remove it, see
    the list empty again - the shallow "does it work at all" level."""
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)

        added = client.put(f"{PATH}/{product.id}", headers=csrf(client))
        listed = client.get(PATH)
        removed = client.delete(f"{PATH}/{product.id}", headers=csrf(client))
        emptied = client.get(PATH)

    assert added.status_code == 204
    assert [item["product_id"] for item in listed.json()["items"]] == [str(product.id)]
    assert removed.status_code == 204
    assert emptied.json()["items"] == []


async def test_put_on_a_visible_product_adds_one_row_and_increments_the_counter(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        before = await _wishlist_count(db_session, product.id)
        response = client.put(f"{PATH}/{product.id}", headers=csrf(client))
    assert response.status_code == 204
    assert await _wishlist_count(db_session, product.id) == before + 1
    assert len(await _active_rows(db_session, product.id)) == 1


async def test_repeated_put_counts_once(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        client.put(f"{PATH}/{product.id}", headers=csrf(client))
        before = await _wishlist_count(db_session, product.id)
        second = client.put(f"{PATH}/{product.id}", headers=csrf(client))
    assert second.status_code == 204
    assert await _wishlist_count(db_session, product.id) == before
    assert len(await _active_rows(db_session, product.id)) == 1


async def test_delete_then_put_inserts_a_new_row_not_a_restore(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        client.put(f"{PATH}/{product.id}", headers=csrf(client))
        [first_row] = await _active_rows(db_session, product.id)
        client.delete(f"{PATH}/{product.id}", headers=csrf(client))
        assert await _wishlist_count(db_session, product.id) == 0

        second = client.put(f"{PATH}/{product.id}", headers=csrf(client))
    assert second.status_code == 204
    assert await _wishlist_count(db_session, product.id) == 1
    [new_row] = await _active_rows(db_session, product.id)
    assert new_row.id != first_row.id
    assert new_row.created_at > first_row.created_at


async def test_repeated_delete_is_a_no_op(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        client.put(f"{PATH}/{product.id}", headers=csrf(client))
        client.delete(f"{PATH}/{product.id}", headers=csrf(client))
        before = await _wishlist_count(db_session, product.id)
        second = client.delete(f"{PATH}/{product.id}", headers=csrf(client))
    assert second.status_code == 204
    assert await _wishlist_count(db_session, product.id) == before == 0


async def test_add_remove_three_cycles_then_add_leaves_one_active_row(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        for _ in range(3):
            client.put(f"{PATH}/{product.id}", headers=csrf(client))
            client.delete(f"{PATH}/{product.id}", headers=csrf(client))
        client.put(f"{PATH}/{product.id}", headers=csrf(client))
    assert await _wishlist_count(db_session, product.id) == 1
    assert len(await _active_rows(db_session, product.id)) == 1


# --------------------------------------------------------------------------
# Visibility, auth boundary
# --------------------------------------------------------------------------


async def test_put_on_a_nonexistent_product_is_404(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        response = client.put(f"{PATH}/{uuid.uuid4()}", headers=csrf(client))
    assert_problem(response, 404)


async def test_put_on_a_hidden_product_is_404(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs, is_visible=False)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        response = client.put(f"{PATH}/{product.id}", headers=csrf(client))
    assert_problem(response, 404)


async def test_put_by_an_unverified_user_is_403(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session, verified=False)
        response = client.put(f"{PATH}/{product.id}", headers=csrf(client))
    assert_problem(response, 403)


async def test_get_by_an_unverified_user_returns_their_own_possibly_empty_list(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        await _signed_in(client, db_session, verified=False)
        response = client.get(PATH)
    assert response.status_code == 200
    assert response.json()["items"] == []


# --------------------------------------------------------------------------
# Listing: pagination, isolation, non-public products
# --------------------------------------------------------------------------


async def test_get_never_returns_another_users_items(db_session: AsyncSession) -> None:
    """Two sequential clients, not nested - two `TestClient`s driving the same
    `main_app` instance concurrently is a different (and separately fragile)
    thing from what this test needs, which is just "visible to the next
    caller", not genuine concurrency; see the concurrency suite for that."""
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client_a:
        await _signed_in(client_a, db_session)
        client_a.put(f"{PATH}/{product.id}", headers=csrf(client_a))
    with client_for(main_app) as client_b:
        await _signed_in(client_b, db_session)
        response = client_b.get(PATH)
    assert response.json()["items"] == []


async def test_pagination_covers_a_seeded_set_with_no_duplicates_or_gaps(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    products = [await _product(db_session, refs) for _ in range(5)]
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        for product in products:
            client.put(f"{PATH}/{product.id}", headers=csrf(client))

        first_page = client.get(PATH, params={"limit": 3}).json()
        assert len(first_page["items"]) == 3
        assert first_page["next_cursor"] is not None

        second_page = client.get(
            PATH, params={"limit": 3, "cursor": first_page["next_cursor"]}
        ).json()

    seen = {item["product_id"] for item in first_page["items"] + second_page["items"]}
    assert seen == {str(p.id) for p in products}
    assert second_page["next_cursor"] is None


async def test_get_keeps_an_item_whose_product_became_hidden(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        client.put(f"{PATH}/{product.id}", headers=csrf(client))

        product.is_visible = False
        db_session.add(product)
        await db_session.commit()

        response = client.get(PATH)
    [item] = response.json()["items"]
    assert item["available"] is False
    assert item["name"] == product.name
    assert item["slug"] is None
    assert item["price_cents"] is None


# --------------------------------------------------------------------------
# Admin analytics
# --------------------------------------------------------------------------


async def test_admin_analytics_requires_admin_and_mfa(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        response = client.get(ADMIN_PATH)
    assert_problem(response, 401)


async def test_admin_analytics_rejects_a_limit_above_the_max(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(ADMIN_PATH, params={"limit": 101})
    assert response.status_code == 422


async def test_admin_analytics_counts_a_non_public_product(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    with client_for(main_app) as customer:
        await _signed_in(customer, db_session)
        customer.put(f"{PATH}/{product.id}", headers=csrf(customer))

    product.is_visible = False
    db_session.add(product)
    await db_session.commit()

    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        response = admin.get(ADMIN_PATH, params={"limit": 100})

    body = response.json()
    assert body["total_active"] >= 1
    matching = [row for row in body["most_wishlisted"] if row["product_id"] == str(product.id)]
    assert matching and matching[0]["wishlist_count"] >= 1


# --------------------------------------------------------------------------
# Database constraint, independent of the application path
# --------------------------------------------------------------------------


async def test_the_partial_unique_index_rejects_a_second_active_row_directly(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    product = await _product(db_session, refs)
    user = await create_user(db_session)
    db_session.add(WishlistItemModel(user_id=user.id, product_id=product.id))
    await db_session.commit()

    try:
        db_session.add(WishlistItemModel(user_id=user.id, product_id=product.id))
        await db_session.commit()
    except IntegrityError:
        await db_session.rollback()
    else:
        raise AssertionError("Postgres should have rejected the second active row")
