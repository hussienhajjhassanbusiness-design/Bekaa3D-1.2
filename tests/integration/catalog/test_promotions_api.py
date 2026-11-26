"""Seasonal promotions: the admin API (boundary, CSRF, validation, audit), the public list,
and the storefront's server-computed price (`price`, `list_price`, `promotion`)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.enums import ProductType
from app.catalog.domain.promotions import DiscountType, PromotionScope
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.promotion_support import (
    ADMIN_PROMOTIONS,
    PUBLIC_PROMOTIONS,
    no_promotions,  # noqa: F401
    promotion_body,
    seed_promotion,
)
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app", "no_promotions")]

PRODUCTS = "/api/v1/products"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with client_for(main_app) as c:
        yield c


def _create(client: TestClient, **over: Any) -> Any:
    return client.post(ADMIN_PROMOTIONS, json=promotion_body(**over), headers=csrf(client))


def _locs(response: Any) -> set[str]:
    return {e["loc"][-1] for e in response.json().get("errors", [])}


async def _product(db: AsyncSession, **over: Any) -> Any:
    return await seed_product(db, await seed_refs(db), **over)


def _listed(client: TestClient, slug_or_id: str, **params: Any) -> dict[str, Any]:
    items = client.get(PRODUCTS, params={"limit": 100} | params).json()["items"]
    [item] = [i for i in items if slug_or_id in (i["slug"], i["id"])]
    return dict(item)


# ------------------------------------------------------------------ admin API


async def test_create_list_read_and_switch_off(
    client: TestClient, db_session: AsyncSession
) -> None:
    admin, _, _ = await mfa_admin(client, db_session)
    admin_id = admin.id  # read before expire_all() below
    created = _create(client)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["name"], body["badge_text"], body["status"], body["active"]) == (
        "Ramadan Sale",
        "Ramadan",
        "active",
        True,
    )
    assert (body["discount_type"], body["discount_value"], body["scope"]) == (
        "percentage",
        25,
        "all",
    )
    listed = client.get(ADMIN_PROMOTIONS).json()["items"]
    assert [p["id"] for p in listed] == [body["id"]]
    assert client.get(f"{ADMIN_PROMOTIONS}/{body['id']}").json()["name"] == "Ramadan Sale"

    off = client.patch(
        f"{ADMIN_PROMOTIONS}/{body['id']}", json={"active": False}, headers=csrf(client)
    )
    assert off.status_code == 200, off.text
    assert (off.json()["active"], off.json()["status"]) == (False, "inactive")
    assert client.get(PUBLIC_PROMOTIONS).json()["items"] == []

    db_session.expire_all()
    audit = list(
        await db_session.scalars(
            select(AuditLogModel)
            .where(AuditLogModel.entity_id == uuid.UUID(body["id"]))
            .order_by(AuditLogModel.created_at)
        )
    )
    assert [(a.action, a.actor_user_id) for a in audit] == [
        ("promotion.created", admin_id),
        ("promotion.updated", admin_id),
    ]
    assert audit[1].before_data is not None and audit[1].before_data["active"] is True
    assert audit[1].after_data is not None and audit[1].after_data["active"] is False


async def test_status_is_derived_scheduled_and_ended(
    client: TestClient, db_session: AsyncSession
) -> None:
    await mfa_admin(client, db_session)
    now = datetime.now(UTC)
    later = _create(
        client,
        starts_at=(now + timedelta(days=2)).isoformat(),
        ends_at=(now + timedelta(days=3)).isoformat(),
    ).json()
    assert later["status"] == "scheduled"
    await seed_promotion(
        db_session, starts_at=now - timedelta(days=3), ends_at=now - timedelta(days=2)
    )
    statuses = sorted(p["status"] for p in client.get(ADMIN_PROMOTIONS).json()["items"])
    assert statuses == ["ended", "scheduled"]


@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"discount_value": 101}, "discount_value"),
        ({"discount_value": 0}, "discount_value"),
        ({"discount_type": "fixed", "discount_value": 0}, "discount_value"),
        ({"ends_at": (datetime.now(UTC) - timedelta(days=2)).isoformat()}, "ends_at"),
        ({"scope": "selected"}, "product_ids"),
        ({"product_ids": [str(uuid.uuid4())]}, "product_ids"),
        ({"name": "   "}, "name"),
        ({"starts_at": "2026-12-01T10:00:00"}, "starts_at"),  # no offset
        ({"stacking": True}, "stacking"),  # unknown field
    ],
)
async def test_validation(
    client: TestClient, db_session: AsyncSession, over: dict[str, Any], field: str
) -> None:
    await mfa_admin(client, db_session)
    response = _create(client, **over)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert field in _locs(response)
    assert client.get(ADMIN_PROMOTIONS).json()["items"] == []


async def test_selected_products_must_exist_and_not_be_deleted(
    client: TestClient, db_session: AsyncSession
) -> None:
    await mfa_admin(client, db_session)
    gone = await _product(db_session, deleted_at=datetime.now(UTC))
    response = _create(client, scope="selected", product_ids=[str(gone.id)])
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert _locs(response) == {"product_ids"}


async def test_patch_validates_the_merged_promotion(
    client: TestClient, db_session: AsyncSession
) -> None:
    await mfa_admin(client, db_session)
    created = _create(client, discount_type="fixed", discount_value=500).json()
    # 500 is a fine fixed amount but not a percentage.
    response = client.patch(
        f"{ADMIN_PROMOTIONS}/{created['id']}",
        json={"discount_type": "percentage"},
        headers=csrf(client),
    )
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert client.get(f"{ADMIN_PROMOTIONS}/{created['id']}").json()["discount_type"] == "fixed"


async def test_writes_need_csrf(client: TestClient, db_session: AsyncSession) -> None:
    await mfa_admin(client, db_session)
    assert_problem(client.post(ADMIN_PROMOTIONS, json=promotion_body()), 403, "CSRF_INVALID")
    promotion = await seed_promotion(db_session)
    patched = client.patch(f"{ADMIN_PROMOTIONS}/{promotion}", json={"active": False})
    assert_problem(patched, 403, "CSRF_INVALID")


async def test_admin_boundary(client: TestClient, db_session: AsyncSession) -> None:
    promotion = await seed_promotion(db_session)
    assert client.get(ADMIN_PROMOTIONS).status_code == 401
    customer = await create_user(db_session)
    login(client, customer.email)
    assert_problem(client.get(ADMIN_PROMOTIONS), 404)
    assert_problem(client.get(f"{ADMIN_PROMOTIONS}/{promotion}"), 404)
    assert_problem(_create(client), 404)


# ------------------------------------------------------------ public reads


async def test_public_list_shows_only_active_promotions(
    client: TestClient, db_session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    active = await seed_promotion(db_session, name="Christmas Sale", badge_text="Xmas")
    await seed_promotion(db_session, name="Off", is_active=False)
    await seed_promotion(
        db_session,
        name="Future",
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=2),
    )
    await seed_promotion(
        db_session,
        name="Past",
        starts_at=now - timedelta(days=3),
        ends_at=now - timedelta(days=1),
    )
    items = client.get(PUBLIC_PROMOTIONS).json()["items"]
    assert [(i["id"], i["name"], i["badge_text"]) for i in items] == [
        (str(active), "Christmas Sale", "Xmas")
    ]
    assert "product_ids" not in items[0]


async def test_storefront_price_is_the_promotional_price(
    client: TestClient, db_session: AsyncSession
) -> None:
    product = await _product(db_session, price_cents=2500)
    promotion = await seed_promotion(db_session, discount_value=20)
    item = _listed(client, product.slug)
    assert item["price"] == {"amount_cents": 2000, "currency": "USD"}
    assert item["list_price"] == {"amount_cents": 2500, "currency": "USD"}
    assert item["promotion"]["id"] == str(promotion)
    assert (item["promotion"]["discount_type"], item["promotion"]["discount_value"]) == (
        "percentage",
        20,
    )
    detail = client.get(f"{PRODUCTS}/{product.slug}").json()
    assert (detail["price"]["amount_cents"], detail["list_price"]["amount_cents"]) == (2000, 2500)
    assert detail["promotion"]["name"] == "Eid Sale"


async def test_fixed_discount(client: TestClient, db_session: AsyncSession) -> None:
    product = await _product(db_session, price_cents=2500)
    await seed_promotion(db_session, discount_type=DiscountType.FIXED, discount_value=500)
    assert _listed(client, product.slug)["price"]["amount_cents"] == 2000


@pytest.mark.parametrize("state", ["inactive", "future", "expired"])
async def test_promotion_outside_its_window_changes_nothing(
    client: TestClient, db_session: AsyncSession, state: str
) -> None:
    now = datetime.now(UTC)
    states: dict[str, dict[str, Any]] = {
        "inactive": {"is_active": False},
        "future": {"starts_at": now + timedelta(hours=1), "ends_at": now + timedelta(days=1)},
        "expired": {"starts_at": now - timedelta(days=2), "ends_at": now - timedelta(seconds=1)},
    }
    over = states[state]
    product = await _product(db_session, price_cents=2500)
    await seed_promotion(db_session, **over)
    item = _listed(client, product.slug)
    assert (item["price"], item["promotion"]) == (item["list_price"], None)


async def test_scopes(client: TestClient, db_session: AsyncSession) -> None:
    physical = await _product(db_session, price_cents=1000)
    stl = await _product(db_session, type=ProductType.STL, price_cents=1000)
    chosen = await _product(db_session, type=ProductType.STL, price_cents=1000)
    await seed_promotion(db_session, scope=PromotionScope.PHYSICAL, discount_value=10)
    selected = await seed_promotion(
        db_session, scope=PromotionScope.SELECTED, discount_value=30, products=[chosen.id]
    )
    assert _listed(client, physical.slug)["price"]["amount_cents"] == 900
    assert _listed(client, stl.slug)["promotion"] is None
    assert _listed(client, chosen.slug)["price"]["amount_cents"] == 700
    covered = client.get(PRODUCTS, params={"promotion_id": str(selected)}).json()["items"]
    assert [i["id"] for i in covered] == [str(chosen.id)]


async def test_no_stacking(client: TestClient, db_session: AsyncSession) -> None:
    product = await _product(db_session, price_cents=2500)
    await seed_promotion(db_session, name="Ten", discount_value=10)
    best = await seed_promotion(
        db_session, name="Five off", discount_type=DiscountType.FIXED, discount_value=500
    )
    item = _listed(client, product.slug)
    # $20.00 (only the $5 one), never $25 - 10% - $5 = $17.50.
    assert item["price"]["amount_cents"] == 2000
    assert item["promotion"]["id"] == str(best)


async def test_promotion_filter_lists_nothing_for_an_inactive_promotion(
    client: TestClient, db_session: AsyncSession
) -> None:
    await _product(db_session)
    off = await seed_promotion(db_session, is_active=False)
    assert client.get(PRODUCTS, params={"promotion_id": str(off)}).json()["items"] == []
    assert client.get(PRODUCTS, params={"promotion_id": str(uuid.uuid4())}).json() == {
        "items": [],
        "next_cursor": None,
    }
