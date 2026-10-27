"""VS-037 plan 6.2 and 6.4: admin hide / restore over HTTP on real Postgres. Aggregates,
the 404 rule for deleted reviews, 409 on a repeat, audit rows, list filters and keyset."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import PurchaseMode
from app.catalog.infrastructure.models import ProductModel
from app.main import app as main_app
from app.platform.infrastructure.audit_writer import SqlAuditWriter
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.engagement.review_support import (
    MINE,
    delete_review,
    email_of,
    execute,
    fresh_totals,
    patch_review,
    public_path,
    review_as,
    review_row,
    stored_totals,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

ADMIN = "/api/v1/admin/reviews"


def _hide(client: TestClient, review_id: Any, **body: Any) -> httpx.Response:
    response: httpx.Response = client.post(
        f"{ADMIN}/{review_id}/hide", json=body, headers=csrf(client)
    )
    return response


def _restore(client: TestClient, review_id: Any, **body: Any) -> httpx.Response:
    response: httpx.Response = client.post(
        f"{ADMIN}/{review_id}/restore", json=body, headers=csrf(client)
    )
    return response


async def _product(db: AsyncSession, **over: Any) -> ProductModel:
    return await seed_product(db, await seed_refs(db), **over)


async def _reviews(db: AsyncSession, product_id: uuid.UUID, *ratings: int) -> list[str]:
    """Each rating by a fresh verified author over HTTP, so the aggregates are maintained."""
    ids = []
    for rating in ratings:
        author = await create_user(db)
        ids.append((await review_as(db, author.id, product_id, rating))["id"])
    return ids


async def _author_of(engine: AsyncEngine, review_id: str) -> uuid.UUID:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT user_id FROM reviews WHERE id = :r"), {"r": uuid.UUID(review_id)}
        )
    assert isinstance(found, uuid.UUID)
    return found


async def _audits(db: AsyncSession, review_id: str) -> list[AuditLogModel]:
    stmt = (
        select(AuditLogModel)
        .where(AuditLogModel.entity_type == "review")
        .where(AuditLogModel.entity_id == uuid.UUID(review_id))
        .order_by(AuditLogModel.created_at)
    )
    return list((await db.scalars(stmt)).all())


async def _insert(
    engine: AsyncEngine,
    user_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    rating: int = 3,
    created_at: datetime | None = None,
    hidden: bool = False,
    verified: bool = False,
) -> uuid.UUID:
    """A review row straight in SQL, for list tests that do not read the aggregates."""
    review_id = uuid.uuid4()
    at = created_at or datetime.now(UTC)
    await execute(
        engine,
        "INSERT INTO reviews (id, user_id, product_id, rating, is_verified_purchase,"
        " is_hidden, hidden_at, created_at, updated_at)"
        " VALUES (:i, :u, :p, :r, :v, :h, :ha, :c, :c)",
        i=review_id,
        u=user_id,
        p=product_id,
        r=rating,
        v=verified,
        h=hidden,
        ha=at if hidden else None,
        c=at,
    )
    return review_id


async def _assert_exact(engine: AsyncEngine, product_id: uuid.UUID) -> None:
    assert await stored_totals(engine, product_id) == await fresh_totals(engine, product_id)


# --- hide and restore move the public list and the aggregates ----------------------------


async def test_hide_leaves_the_public_list_and_aggregates_and_restore_brings_it_back(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    five, four, one = await _reviews(db_session, product.id, 5, 4, 1)
    assert await stored_totals(db_engine, product.id) == (Decimal("3.33"), 3)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        hidden = _hide(admin, one, reason="  abusive  ")
        assert hidden.status_code == 200, hidden.text
        body = hidden.json()
        assert body["is_hidden"] is True and body["hidden_at"] is not None
        assert await stored_totals(db_engine, product.id) == (Decimal("4.50"), 2)
        listed = admin.get(public_path(product.slug)).json()["items"]
        assert {item["id"] for item in listed} == {five, four}
        restored = _restore(admin, one)
        assert restored.status_code == 200, restored.text
        assert restored.json()["is_hidden"] is False and restored.json()["hidden_at"] is None
        listed = admin.get(public_path(product.slug)).json()["items"]
    assert {item["id"] for item in listed} == {five, four, one}
    assert await stored_totals(db_engine, product.id) == (Decimal("3.33"), 3)
    await _assert_exact(db_engine, product.id)


async def test_a_failure_after_the_recompute_rolls_back_the_toggle_and_the_aggregate(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same transaction: the audit write fails, so neither the flag nor the rating moved."""
    product = await _product(db_session)
    [review] = await _reviews(db_session, product.id, 2)
    before = await stored_totals(db_engine, product.id)

    async def boom(self: SqlAuditWriter, **row: Any) -> None:
        raise RuntimeError("audit store down")

    with client_for(main_app, raise_server_exceptions=False) as admin:
        await mfa_admin(admin, db_session)
        monkeypatch.setattr(SqlAuditWriter, "record", boom)
        response = _hide(admin, review)
    assert response.status_code == 500
    assert (await review_row(db_engine, review)).is_hidden is False
    assert await stored_totals(db_engine, product.id) == before == (Decimal("2.00"), 1)


@pytest.mark.parametrize("hide_first", [True, False])
async def test_a_repeat_is_409_invalid_state_transition_and_writes_nothing(
    hide_first: bool, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    [review] = await _reviews(db_session, product.id, 4)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        if hide_first:
            assert _hide(admin, review).status_code == 200
            totals = await stored_totals(db_engine, product.id)
            repeat = _hide(admin, review)
        else:
            totals = await stored_totals(db_engine, product.id)
            repeat = _restore(admin, review)
    assert_problem(repeat, 409, "INVALID_STATE_TRANSITION")
    assert repeat.json()["is_hidden"] is hide_first
    assert await stored_totals(db_engine, product.id) == totals
    assert len(await _audits(db_session, review)) == (1 if hide_first else 0)


# --- soft-deleted reviews are missing (D3) -----------------------------------------------


async def test_a_deleted_review_is_404_for_hide_restore_and_detail_like_an_unknown_id(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    [review] = await _reviews(db_session, product.id, 5)
    author = await _author_of(db_engine, review)
    with client_for(main_app) as client:
        login(client, await email_of(db_session, author))
        assert delete_review(client, review).status_code == 204
    totals = await stored_totals(db_engine, product.id)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        unknown = _hide(admin, uuid.uuid4())
        responses = [
            _hide(admin, review),
            _restore(admin, review),
            admin.get(f"{ADMIN}/{review}"),
        ]
        listed = admin.get(ADMIN, params={"product_id": str(product.id)}).json()["items"]
    assert_problem(unknown, 404, "NOT_FOUND")
    strip = ("request_id", "instance")
    for response in responses:
        assert_problem(response, 404, "NOT_FOUND")
        assert {k: v for k, v in response.json().items() if k not in strip} == {
            k: v for k, v in unknown.json().items() if k not in strip
        }
    assert listed == []
    assert await _audits(db_session, review) == []
    assert await stored_totals(db_engine, product.id) == totals


async def test_a_hidden_review_deleted_by_its_author_stays_hidden_and_cannot_be_restored(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    keep, gone = await _reviews(db_session, product.id, 5, 1)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        assert _hide(admin, gone).status_code == 200
    with client_for(main_app) as client:
        login(client, await email_of(db_session, await _author_of(db_engine, gone)))
        assert delete_review(client, gone).status_code == 204
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        restore = _restore(admin, gone)
    assert_problem(restore, 404, "NOT_FOUND")
    row = await review_row(db_engine, gone)
    assert row.is_hidden is True and row.deleted_at is not None
    assert await stored_totals(db_engine, product.id) == (Decimal("5.00"), 1)
    assert keep


# --- the author's view ----------------------------------------------------------------------


async def test_me_reviews_shows_moderation_state_and_an_edit_keeps_it_hidden(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    other, review = await _reviews(db_session, product.id, 5, 1)
    email = await email_of(db_session, await _author_of(db_engine, review))
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        assert _hide(admin, review).status_code == 200
    with client_for(main_app) as client:
        login(client, email)
        assert client.get(MINE).json()["items"][0]["is_hidden"] is True
        edited = patch_review(client, review, rating=4)
    assert edited.status_code == 200 and edited.json()["is_hidden"] is True
    assert await stored_totals(db_engine, product.id) == (Decimal("5.00"), 1)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        assert _restore(admin, review).status_code == 200
    with client_for(main_app) as client:
        login(client, email)
        assert client.get(MINE).json()["items"][0]["is_hidden"] is False
    assert await stored_totals(db_engine, product.id) == (Decimal("4.50"), 2)
    assert other


# --- audit rows (D8) --------------------------------------------------------------------------


async def test_hide_and_restore_write_one_audit_row_each_with_no_text_or_email(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    author = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, author.email)
        posted = client.post(
            "/api/v1/reviews",
            json={"product_id": str(product.id), "rating": 1, "body": "Secret words here"},
            headers=csrf(client),
        )
    assert posted.status_code == 201, posted.text
    review = posted.json()["id"]
    with client_for(main_app) as admin:
        admin_user = (await mfa_admin(admin, db_session))[0]
        assert _hide(admin, review, reason="Off-topic").status_code == 200
        assert _restore(admin, review).status_code == 200
    hidden, restored = await _audits(db_session, review)
    assert (hidden.action, restored.action) == ("review.hidden", "review.restored")
    for row in (hidden, restored):
        assert row.actor_user_id == admin_user.id and row.request_id
        dumped = json.dumps([row.before_data, row.after_data])
        assert "Secret words" not in dumped and author.email not in dumped
        assert str(author.id) not in dumped
    assert hidden.before_data == {
        "is_hidden": False,
        "hidden_at": None,
        "product_id": str(product.id),
    }
    assert hidden.after_data is not None and hidden.after_data["is_hidden"] is True
    assert hidden.after_data["reason"] == "Off-topic" and hidden.after_data["hidden_at"]
    assert restored.before_data == {k: v for k, v in hidden.after_data.items() if k != "reason"}
    assert restored.after_data == {
        "is_hidden": False,
        "hidden_at": None,
        "product_id": str(product.id),
        "reason": None,
    }


# --- the request body ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [{"reason": "x" * 501}, {"reason": "bad\x07bell"}, {"note": "unknown field"}],
)
async def test_a_bad_reason_or_unknown_field_is_422_and_nothing_changes(
    body: dict[str, Any], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    [review] = await _reviews(db_session, product.id, 3)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        response = _hide(admin, review, **body)
    assert_problem(response, 422)
    assert (await review_row(db_engine, review)).is_hidden is False


async def test_no_body_is_accepted_and_the_reason_is_null(db_session: AsyncSession) -> None:
    product = await _product(db_session)
    [review] = await _reviews(db_session, product.id, 3)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        response = admin.post(f"{ADMIN}/{review}/hide", headers=csrf(admin))
    assert response.status_code == 200, response.text
    [row] = await _audits(db_session, review)
    assert row.after_data is not None and row.after_data["reason"] is None


async def test_hide_without_the_csrf_header_is_403_and_changes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    [review] = await _reviews(db_session, product.id, 3)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        response = admin.post(f"{ADMIN}/{review}/hide", json={})
    assert response.status_code == 403
    assert (await review_row(db_engine, review)).is_hidden is False
    assert await _audits(db_session, review) == []


# --- a product deleted later ----------------------------------------------------------------


async def test_a_review_of_a_deleted_product_is_still_moderated_and_recomputed(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    keep, review = await _reviews(db_session, product.id, 5, 2)
    await execute(db_engine, "UPDATE products SET deleted_at = now() WHERE id = :p", p=product.id)
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        response = _hide(admin, review)
    assert response.status_code == 200, response.text
    assert response.json()["product_slug"] is None
    assert await stored_totals(db_engine, product.id) == (Decimal("5.00"), 1)
    await _assert_exact(db_engine, product.id)
    assert keep


# --- list and detail ----------------------------------------------------------------------


async def test_the_list_filters_and_shows_stored_and_masked_badges_with_no_email(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    online = await _product(db_session)
    whatsapp = await _product(db_session, purchase_mode=PurchaseMode.WHATSAPP_ONLY)
    alice, bob = await create_user(db_session), await create_user(db_session)
    a_hidden = await _insert(db_engine, alice.id, online.id, rating=1, hidden=True)
    b_online = await _insert(db_engine, bob.id, online.id, rating=5, verified=True)
    a_whats = await _insert(db_engine, alice.id, whatsapp.id, rating=4, verified=True)

    def ids(response: httpx.Response) -> set[uuid.UUID]:
        assert response.status_code == 200, response.text
        return {uuid.UUID(item["id"]) for item in response.json()["items"]}

    scoped = {"user_id": str(alice.id)}
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        by_alice = admin.get(ADMIN, params=scoped)
        assert ids(by_alice) == {a_hidden, a_whats}
        assert ids(admin.get(ADMIN, params=scoped | {"hidden": "true"})) == {a_hidden}
        assert ids(admin.get(ADMIN, params=scoped | {"hidden": "false"})) == {a_whats}
        assert ids(admin.get(ADMIN, params={"product_id": str(online.id)})) == {
            a_hidden,
            b_online,
        }
        on_product = {"product_id": str(online.id)}
        assert ids(admin.get(ADMIN, params=on_product | {"rating": 5})) == {b_online}
        verified = admin.get(ADMIN, params=scoped | {"verified_purchase": "true"})
        assert ids(verified) == {a_whats}
        unverified = admin.get(ADMIN, params=scoped | {"verified_purchase": "false"})
        assert ids(unverified) == {a_hidden}
        detail = admin.get(f"{ADMIN}/{a_whats}")
        bad_rating = admin.get(ADMIN, params={"rating": 6})
    [item] = verified.json()["items"]
    assert (item["is_verified_purchase"], item["badge_shown"]) == (True, False)
    assert detail.status_code == 200
    assert detail.json() == item
    assert "email" not in json.dumps(by_alice.json()) and alice.email not in by_alice.text
    assert_problem(bad_rating, 422)


async def test_keyset_pages_cover_every_live_review_once_in_order(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = await _product(db_session)
    base = datetime(2026, 10, 1, tzinfo=UTC)
    expected = []
    for n in range(45):
        author = await create_user(db_session)
        at = base + timedelta(minutes=n // 3)  # ties on created_at, broken by id
        expected.append((at, await _insert(db_engine, author.id, product.id, created_at=at)))
    expected.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
    seen: list[uuid.UUID] = []
    params: dict[str, Any] = {"product_id": str(product.id), "limit": 20}
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        while True:
            page = admin.get(ADMIN, params=params).json()
            seen.extend(uuid.UUID(item["id"]) for item in page["items"])
            if page["next_cursor"] is None:
                break
            params["cursor"] = page["next_cursor"]
        tampered = admin.get(ADMIN, params={"cursor": "not-a-cursor"})
    assert seen == [review_id for _, review_id in expected]
    assert_problem(tampered, 422)
