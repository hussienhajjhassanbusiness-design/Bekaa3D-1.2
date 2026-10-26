"""VS-036 plan 6.2 (API, aggregates) and 6.4 (security) over HTTP on real Postgres."""

import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.catalog.infrastructure.models import ProductModel
from app.identity.infrastructure.models import UserModel
from app.main import app as main_app
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user, csrf, login
from tests.integration.engagement.review_support import (
    MINE,
    REVIEWS,
    delete_review,
    execute,
    fresh_totals,
    patch_review,
    post_review,
    product_facts,
    public_path,
    review_row,
    stored_totals,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _signed_in(client: TestClient, db: AsyncSession, *, verified: bool = True) -> UserModel:
    user = await create_user(db, verified=verified)
    login(client, user.email)
    return user


async def _product(db: AsyncSession, **over: Any) -> ProductModel:
    return await seed_product(db, await seed_refs(db), **over)


async def _assert_exact(engine: AsyncEngine, product_id: uuid.UUID) -> None:
    assert await stored_totals(engine, product_id) == await fresh_totals(engine, product_id)


# --- create, the badge for a non-buyer, aggregates ------------------------------------------


async def test_a_non_buyer_reviews_without_a_badge_and_the_aggregates_move(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        response = post_review(client, product.id, 5, "  Lovely finish.  ")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["is_verified_purchase"] is False
    assert (body["rating"], body["body"], body["edited"], body["is_hidden"]) == (
        5,
        "Lovely finish.",
        False,
        False,
    )
    assert body["product_id"] == str(product.id) and body["product_slug"] == product.slug
    assert await stored_totals(db_engine, product.id) == (Decimal("5.00"), 1)


async def test_rating_only_reviews_are_allowed(db_session: AsyncSession) -> None:
    product = await _product(db_session)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        response = post_review(client, product.id, 3)
    assert response.status_code == 201 and response.json()["body"] is None


async def test_a_duplicate_is_409_also_while_hidden_and_allowed_after_delete(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        first = post_review(client, product.id, 4).json()
        assert_problem(post_review(client, product.id, 2), 409, "REVIEW_ALREADY_EXISTS")
        await execute(
            db_engine,
            "UPDATE reviews SET is_hidden = true, hidden_at = now() WHERE id = :r",
            r=uuid.UUID(first["id"]),
        )
        assert_problem(post_review(client, product.id, 2), 409, "REVIEW_ALREADY_EXISTS")
        assert delete_review(client, first["id"]).status_code == 204
        again = post_review(client, product.id, 1)
    assert again.status_code == 201, again.text
    await _assert_exact(db_engine, product.id)


async def test_unverified_anonymous_and_missing_csrf_are_refused(db_session: AsyncSession) -> None:
    product = await _product(db_session)
    payload = {"product_id": str(product.id), "rating": 5}
    with client_for(main_app) as client:
        assert client.post(REVIEWS, json=payload).status_code == 401
        await _signed_in(client, db_session, verified=False)
        assert_problem(
            client.post(REVIEWS, json=payload, headers=csrf(client)),
            403,
            "EMAIL_VERIFICATION_REQUIRED",
        )
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        assert client.post(REVIEWS, json=payload).status_code == 403


@pytest.mark.parametrize("state", ["invisible", "deleted", "unknown"])
async def test_a_non_public_product_is_404_on_create_and_on_the_list(
    state: str, db_session: AsyncSession
) -> None:
    over: dict[str, Any] = {"is_visible": False} if state == "invisible" else {}
    product = await _product(db_session, **over)
    if state == "deleted":
        product.deleted_at = product.created_at
        await db_session.commit()
    product_id = uuid.uuid4() if state == "unknown" else product.id
    slug = "no-such-product" if state == "unknown" else product.slug
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        assert_problem(post_review(client, product_id), 404)
        assert_problem(client.get(public_path(slug)), 404)


@pytest.mark.parametrize(
    ("payload", "code", "reason"),
    [
        ({"rating": 0}, None, None),
        ({"rating": 6}, None, None),
        ({"rating": "5"}, None, None),
        ({"rating": 5, "body": "a" * 2001}, None, None),
        ({"rating": 5, "body": "bad\x00text"}, None, None),
        ({"rating": 5, "body": "see https://spam.example"}, "REVIEW_CONTENT_REJECTED", "link"),
        ({"rating": 5, "body": "what a shit lamp"}, "REVIEW_CONTENT_REJECTED", "profanity"),
    ],
)
async def test_bad_content_is_422(
    payload: dict[str, Any], code: str | None, reason: str | None, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        response = client.post(
            REVIEWS, json={"product_id": str(product.id)} | payload, headers=csrf(client)
        )
    assert_problem(response, 422, code)
    if reason is not None:
        assert response.json()["reason"] == reason


# --- edit and delete ------------------------------------------------------------------------


async def test_edit_and_delete_keep_aggregates_exact_and_never_bump_the_product(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    before = await product_facts(db_engine, product.id)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        mine = post_review(client, product.id, 5).json()
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        other = post_review(client, product.id, 2).json()
        await _assert_exact(db_engine, product.id)
        assert await stored_totals(db_engine, product.id) == (Decimal("3.50"), 2)
        edited = patch_review(client, other["id"], rating=4)
        assert edited.status_code == 200 and edited.json()["edited"] is True
        assert await stored_totals(db_engine, product.id) == (Decimal("4.50"), 2)
        body_only = patch_review(client, other["id"], body="Changed my mind.")
        assert body_only.json()["rating"] == 4
        assert await stored_totals(db_engine, product.id) == (Decimal("4.50"), 2)
        cleared = patch_review(client, other["id"], body=None)
        assert cleared.json()["body"] is None
        assert delete_review(client, other["id"]).status_code == 204
        assert_problem(delete_review(client, other["id"]), 404)
        assert_problem(patch_review(client, other["id"], rating=3), 404)
    assert await stored_totals(db_engine, product.id) == (Decimal("5.00"), 1)
    await _assert_exact(db_engine, product.id)
    after = await product_facts(db_engine, product.id)
    assert (after.version, after.updated_at) == (before.version, before.updated_at)
    assert (await review_row(db_engine, mine["id"])).deleted_at is None


async def test_someone_elses_review_is_the_same_404_as_a_missing_one(
    db_session: AsyncSession,
) -> None:
    product = await _product(db_session)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        theirs = post_review(client, product.id, 5).json()
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        foreign = patch_review(client, theirs["id"], rating=1)
        missing = patch_review(client, str(uuid.uuid4()), rating=1)
        foreign_delete = delete_review(client, theirs["id"])
    assert foreign.status_code == missing.status_code == foreign_delete.status_code == 404

    def stable(body: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in body.items() if k not in {"instance", "request_id"}}

    assert stable(foreign.json()) == stable(missing.json()) == stable(foreign_delete.json())


async def test_an_edit_needs_a_field_and_the_client_cannot_set_moderation_or_badge(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        review = post_review(client, product.id, 5).json()
        assert_problem(patch_review(client, review["id"]), 422)
        assert_problem(patch_review(client, review["id"], rating=None), 422)
        for field, value in (("is_verified_purchase", True), ("is_hidden", True)):
            assert_problem(patch_review(client, review["id"], **{field: value}), 422)
            assert_problem(
                client.post(
                    REVIEWS,
                    json={"product_id": str(product.id), "rating": 5, field: value},
                    headers=csrf(client),
                ),
                422,
            )
    row = await review_row(db_engine, review["id"])
    assert (row.is_verified_purchase, row.is_hidden) == (False, False)


async def test_a_hidden_review_stays_hidden_after_an_edit(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        review = post_review(client, product.id, 5).json()
        await execute(
            db_engine,
            "UPDATE reviews SET is_hidden = true, hidden_at = now() WHERE id = :r",
            r=uuid.UUID(review["id"]),
        )
        edited = patch_review(client, review["id"], rating=1)
    assert edited.status_code == 200 and edited.json()["is_hidden"] is True
    assert (await review_row(db_engine, review["id"])).is_hidden is True


# --- the lists ------------------------------------------------------------------------------


async def test_the_public_list_hides_hidden_and_deleted_and_filters_and_pages(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    ids: list[str] = []
    for rating in (5, 4, 4, 2, 1):
        with client_for(main_app) as client:
            await _signed_in(client, db_session)
            ids.append(post_review(client, product.id, rating).json()["id"])
    await execute(
        db_engine,
        "UPDATE reviews SET is_hidden = true, hidden_at = now() WHERE id = :r",
        r=uuid.UUID(ids[3]),
    )
    await execute(
        db_engine, "UPDATE reviews SET deleted_at = now() WHERE id = :r", r=uuid.UUID(ids[4])
    )
    await execute(
        db_engine,
        "UPDATE reviews SET is_verified_purchase = true WHERE id = :r",
        r=uuid.UUID(ids[0]),
    )
    with client_for(main_app) as client:
        everything = client.get(public_path(product.slug)).json()
        fours = client.get(public_path(product.slug), params={"rating": 4}).json()
        verified = client.get(public_path(product.slug), params={"verified_purchase": True})
        page_one = client.get(public_path(product.slug), params={"limit": 2}).json()
        page_two = client.get(
            public_path(product.slug), params={"limit": 2, "cursor": page_one["next_cursor"]}
        ).json()
    assert [item["id"] for item in everything["items"]] == list(reversed(ids[:3]))
    assert {item["rating"] for item in fours["items"]} == {4} and len(fours["items"]) == 2
    assert [item["id"] for item in verified.json()["items"]] == [ids[0]]
    assert [i["id"] for i in page_one["items"] + page_two["items"]] == list(reversed(ids[:3]))
    assert page_two["next_cursor"] is None
    for item in everything["items"]:
        assert set(item) == {"id", "rating", "body", "is_verified_purchase", "created_at", "edited"}


async def test_the_cursor_is_stable_under_inserts(db_session: AsyncSession) -> None:
    product = await _product(db_session)
    ids = []
    for _ in range(3):
        with client_for(main_app) as client:
            await _signed_in(client, db_session)
            ids.append(post_review(client, product.id).json()["id"])
    with client_for(main_app) as client:
        first = client.get(public_path(product.slug), params={"limit": 2}).json()
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        post_review(client, product.id)
        second = client.get(
            public_path(product.slug), params={"limit": 2, "cursor": first["next_cursor"]}
        ).json()
    assert [item["id"] for item in second["items"]] == [ids[0]]


async def test_my_reviews_show_hidden_with_state_and_never_deleted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    hidden_on = await _product(db_session)
    deleted_on = await _product(db_session, type=ProductType.STL)
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        hidden = post_review(client, hidden_on.id, 3).json()
        deleted = post_review(client, deleted_on.id, 4).json()
        await execute(
            db_engine,
            "UPDATE reviews SET is_hidden = true, hidden_at = now() WHERE id = :r",
            r=uuid.UUID(hidden["id"]),
        )
        delete_review(client, deleted["id"])
        mine = client.get(MINE).json()
    assert [(i["id"], i["is_hidden"]) for i in mine["items"]] == [(hidden["id"], True)]
    assert mine["items"][0]["product_slug"] == hidden_on.slug


async def test_my_reviews_need_only_a_session(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        assert client.get(MINE).status_code == 401
        await _signed_in(client, db_session, verified=False)
        assert client.get(MINE).status_code == 200


async def test_the_eleventh_write_in_an_hour_is_429_and_anonymous_posts_spend_nothing(
    db_session: AsyncSession,
) -> None:
    products = [await _product(db_session) for _ in range(6)]
    with client_for(main_app) as client:
        for _ in range(3):
            assert client.post(REVIEWS, json={"rating": 5}).status_code == 401
        await _signed_in(client, db_session)
        codes = []
        for product in products[:5]:
            review = post_review(client, product.id)
            codes.append(review.status_code)
            codes.append(delete_review(client, review.json()["id"]).status_code)
        assert codes == [201, 204] * 5
        refused = post_review(client, products[5].id)
    assert_problem(refused, 429, "RATE_LIMITED")
    assert "Retry-After" in refused.headers


async def test_the_public_list_is_limited_at_600_per_ip_per_hour(db_session: AsyncSession) -> None:
    product = await _product(db_session)
    with client_for(main_app) as client:
        response = client.get(public_path(product.slug))
    assert response.status_code == 200
    assert response.headers["RateLimit-Limit"] == "600"
