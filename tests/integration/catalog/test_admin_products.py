"""`/api/v1/admin/products` (VS-013): validation, versioning, soft delete, audit,
the admin boundary and CSRF. DB-level refusals live in test_product_schema.py."""

import base64
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.infrastructure.models import (
    CategoryModel,
    ColourModel,
    MaterialModel,
    ProductModel,
)
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import register, retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)

PRODUCTS = "/api/v1/admin/products"

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _refs(db: AsyncSession, *, active: bool = True) -> dict[str, str]:
    """A fresh category, material and colour, so each test owns its data."""
    rows: list[CategoryModel | MaterialModel | ColourModel] = [
        CategoryModel(
            name=f"zzz-vs013-{uuid.uuid4().hex}",
            slug=f"c-{uuid.uuid4().hex[:12]}",
            is_active=active,
        ),
        MaterialModel(name=f"zzz-vs013-m-{uuid.uuid4().hex}", is_active=active),
        ColourModel(name=f"zzz-vs013-c-{uuid.uuid4().hex}", is_active=active),
    ]
    db.add_all(rows)
    await db.commit()
    register(*(row.id for row in rows))
    return {key: str(row.id) for key, row in zip(_REF_KEYS, rows, strict=True)}


_REF_KEYS = ("category_id", "material_id", "colour_id")


def _slug() -> str:
    return f"p-{uuid.uuid4().hex[:12]}"


def _stl(refs: dict[str, str], **over: Any) -> dict[str, Any]:
    body = {
        "type": "stl",
        "category_id": refs["category_id"],
        "name": "Dragon",
        "slug": _slug(),
        "price": {"amount_cents": 1500, "currency": "USD"},
    }
    return body | over


def _physical(refs: dict[str, str], **over: Any) -> dict[str, Any]:
    body = _stl(refs) | {
        "type": "physical",
        "purchase_mode": "online_only",
        "accepted_payment_methods": "cash",
        "material_id": refs["material_id"],
        "colour_id": refs["colour_id"],
        "dimensions": {"length_mm": 100, "width_mm": 50, "height_mm": 20},
        "production_lead_time_days": 3,
        "batch_size": 4,
        "max_quantity_per_line": 10,
        "weight_grams": 250,
    }
    return body | over


def _create(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(PRODUCTS, json=body, headers=csrf(client))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _patch(client: TestClient, product: dict[str, Any], **changes: Any) -> Any:
    body = {"version": product["version"]} | changes
    return client.patch(f"{PRODUCTS}/{product['id']}", json=body, headers=csrf(client))


def _delete(client: TestClient, product_id: str, version: Any) -> Any:
    return client.delete(f"{PRODUCTS}/{product_id}?version={version}", headers=csrf(client))


async def _audit(db: AsyncSession, entity_id: str) -> list[AuditLogModel]:
    db.expire_all()
    stmt = (
        select(AuditLogModel)
        .where(AuditLogModel.entity_id == uuid.UUID(entity_id))
        .order_by(AuditLogModel.created_at)
    )
    return list(await db.scalars(stmt))


async def _product_rows(db: AsyncSession, slug: str) -> list[ProductModel]:
    db.expire_all()
    return list(await db.scalars(select(ProductModel).where(ProductModel.slug == slug)))


def _locs(response: Any) -> set[tuple[str, ...]]:
    return {tuple(str(p) for p in error["loc"]) for error in response.json()["errors"]}


# --- create and read -------------------------------------------------------


async def test_both_types_round_trip_with_version_and_zero_aggregates(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        stl = _create(client, _stl(refs))
        physical = _create(client, _physical(refs))
        read = client.get(f"{PRODUCTS}/{physical['id']}").json()

    assert read == physical
    assert stl["type"] == "stl" and stl["purchase_mode"] is None and stl["dimensions"] is None
    assert physical["dimensions"] == {"length_mm": 100, "width_mm": 50, "height_mm": 20}
    assert physical["price"] == {"amount_cents": 1500, "currency": "USD"}
    for product in (stl, physical):
        assert product["version"] == 1
        assert (product["average_rating"], product["review_count"]) == (0, 0)
        assert product["wishlist_count"] == 0
        assert (product["is_visible"], product["is_featured"]) == (False, False)
        assert product["is_available"] is True and product["deleted_at"] is None


async def test_an_stl_product_can_be_made_unavailable(db_session: AsyncSession) -> None:
    """Owner decision for VS-013: availability is common to both types (SRS 6.1)."""
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        created = _create(client, _stl(refs, is_available=False))
        patched = _patch(client, created, is_available=True)

    assert created["is_available"] is False
    assert patched.status_code == 200 and patched.json()["is_available"] is True


@pytest.mark.parametrize(
    "field",
    [
        "purchase_mode",
        "accepted_payment_methods",
        "material_id",
        "colour_id",
        "dimensions",
        "production_lead_time_days",
        "batch_size",
        "max_quantity_per_line",
        "weight_grams",
    ],
)
async def test_an_stl_create_refuses_each_physical_field(
    db_session: AsyncSession, field: str
) -> None:
    refs = await _refs(db_session)
    body = _stl(refs) | {field: _physical(refs)[field]}
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(PRODUCTS, json=body, headers=csrf(client))

    assert_problem(response, 422, "VALIDATION_ERROR")
    assert ("body", field) in _locs(response)
    assert await _product_rows(db_session, body["slug"]) == []


@pytest.mark.parametrize(
    "field", ["purchase_mode", "production_lead_time_days", "batch_size", "max_quantity_per_line"]
)
async def test_a_physical_create_requires_each_production_field(
    db_session: AsyncSession, field: str
) -> None:
    refs = await _refs(db_session)
    body = _physical(refs)
    del body[field]
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(PRODUCTS, json=body, headers=csrf(client))

    assert_problem(response, 422, "VALIDATION_ERROR")
    assert ("body", field) in _locs(response)


async def test_material_and_colour_are_optional_on_a_physical_product(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    body = _physical(refs)
    del body["material_id"], body["colour_id"]
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        created = _create(client, body)
    assert created["material_id"] is None and created["colour_id"] is None


@pytest.mark.parametrize(
    "price",
    [
        {"amount_cents": 100, "currency": "EUR"},
        {"amount_cents": -1, "currency": "USD"},
        {"amount_cents": 1.5, "currency": "USD"},
        {"amount_cents": "100", "currency": "USD"},
        {"amount_cents": 2**63, "currency": "USD"},
    ],
)
async def test_price_must_be_usd_integer_cents(
    db_session: AsyncSession, price: dict[str, Any]
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(PRODUCTS, json=_stl(refs, price=price), headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    "over",
    [
        {"name": "   "},
        {"name": "Bad\x00name"},
        {"slug": "Not a slug"},
        {"og_image_url": "javascript:alert(1)"},
        {"dimensions": {"length_mm": 0, "width_mm": 1, "height_mm": 1}},
        {"dimensions": {"length_mm": 1, "width_mm": 1}},
        {"batch_size": 2**31},
    ],
)
async def test_malformed_fields_are_422_not_500(
    db_session: AsyncSession, over: dict[str, Any]
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(PRODUCTS, json=_physical(refs, **over), headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_a_slug_is_normalised_and_the_bad_one_names_its_field(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    slug = _slug()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        created = _create(client, _stl(refs, slug=f"  {slug.upper()} "))
        bad = client.post(PRODUCTS, json=_stl(refs, slug="a--b"), headers=csrf(client))
    assert created["slug"] == slug
    assert_problem(bad, 422, "VALIDATION_ERROR")
    assert ("body", "slug") in _locs(bad)


# --- PATCH: type integrity, immutable type, aggregates ---------------------


@pytest.mark.parametrize(
    ("kind", "changes", "field"),
    [
        ("stl", {"production_lead_time_days": 3}, "production_lead_time_days"),
        ("stl", {"purchase_mode": "both"}, "purchase_mode"),
        ("physical", {"batch_size": None}, "batch_size"),
        ("physical", {"purchase_mode": None}, "purchase_mode"),
        ("stl", {"accepted_payment_methods": "online"}, "accepted_payment_methods"),
        ("physical", {"accepted_payment_methods": None}, "accepted_payment_methods"),
    ],
)
async def test_patch_cannot_break_type_integrity(
    db_session: AsyncSession, kind: str, changes: dict[str, Any], field: str
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs) if kind == "stl" else _physical(refs))
        response = _patch(client, product, **changes)
        after = client.get(f"{PRODUCTS}/{product['id']}").json()

    assert_problem(response, 422, "VALIDATION_ERROR")
    assert ("body", field) in _locs(response)
    assert after == product
    assert [row.action for row in await _audit(db_session, product["id"])] == ["product.created"]


@pytest.mark.parametrize(
    "field", ["type", "average_rating", "review_count", "wishlist_count", "id", "deleted_at"]
)
async def test_type_and_server_fields_are_not_client_writable(
    db_session: AsyncSession, field: str
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))
        response = _patch(client, product, **{field: "physical" if field == "type" else 4})
        create = client.post(PRODUCTS, json=_stl(refs) | {field: 4}, headers=csrf(client))
        after = client.get(f"{PRODUCTS}/{product['id']}").json()

    assert_problem(response, 422, "VALIDATION_ERROR")
    if field != "type":
        assert_problem(create, 422, "VALIDATION_ERROR")
    assert after == product


@pytest.mark.parametrize(
    "body",
    [{}, {"name": "x"}, {"version": 1}, {"version": 0, "name": "x"}, {"version": 1, "name": None}],
)
async def test_a_malformed_patch_body_is_422(
    db_session: AsyncSession, body: dict[str, Any]
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))
        response = client.patch(f"{PRODUCTS}/{product['id']}", json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")


async def test_a_patch_updates_in_place_and_clears_optional_fields(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _physical(refs, description="Old", seo_title="T"))
        response = _patch(
            client,
            product,
            name="Lamp",
            description=None,
            purchase_mode="whatsapp_only",
            is_visible=True,
            is_featured=True,
            price={"amount_cents": 999},
            dimensions=None,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 2
    assert (body["name"], body["description"], body["seo_title"]) == ("Lamp", None, "T")
    assert body["purchase_mode"] == "whatsapp_only" and body["dimensions"] is None
    assert body["price"] == {"amount_cents": 999, "currency": "USD"}
    assert body["updated_at"] > product["updated_at"]


async def test_a_physical_product_created_without_accepted_methods_accepts_both(
    db_session: AsyncSession,
) -> None:
    """BR-019 default; the column has no DB default, so the application must fill it."""
    refs = await _refs(db_session)
    body = _physical(refs)
    del body["accepted_payment_methods"]
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        created = _create(client, body)
    assert created["accepted_payment_methods"] == "online_or_cash"
    [row] = await _product_rows(db_session, body["slug"])
    assert row.accepted_payment_methods == "online_or_cash"


async def test_accepted_methods_round_trip_and_a_change_is_audited(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _physical(refs))
        response = _patch(client, product, accepted_payment_methods="online")
        stl = _create(client, _stl(refs))

    assert product["accepted_payment_methods"] == "cash" and stl["accepted_payment_methods"] is None
    assert response.status_code == 200 and response.json()["accepted_payment_methods"] == "online"
    updated = (await _audit(db_session, product["id"]))[-1]
    assert updated.action == "product.updated"
    assert updated.before_data is not None and updated.after_data is not None
    assert updated.before_data["accepted_payment_methods"] == "cash"
    assert updated.after_data["accepted_payment_methods"] == "online"


@pytest.mark.parametrize("value", ["both", "cash_only", "", 1])
async def test_an_unknown_accepted_methods_value_is_422(
    db_session: AsyncSession, value: Any
) -> None:
    refs = await _refs(db_session)
    body = _physical(refs, accepted_payment_methods=value)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.post(PRODUCTS, json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert ("body", "accepted_payment_methods") in _locs(response)


async def test_a_no_op_patch_keeps_the_version_and_is_still_audited(
    db_session: AsyncSession,
) -> None:
    """ADR-020 / VS-007: same values -> 200, nothing written, equal before/after."""
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))
        response = _patch(client, product, name=product["name"], is_visible=False)

    assert response.status_code == 200
    assert response.json() == product
    rows = await _audit(db_session, product["id"])
    assert [row.action for row in rows] == ["product.created", "product.updated"]
    assert rows[1].before_data == rows[1].after_data


# --- slugs -----------------------------------------------------------------


async def test_a_duplicate_live_slug_is_409_on_create_and_on_patch(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        first = _create(client, _stl(refs))
        second = _create(client, _stl(refs))
        on_create = client.post(PRODUCTS, json=_stl(refs, slug=first["slug"]), headers=csrf(client))
        on_patch = _patch(client, second, slug=first["slug"].upper())

    assert_problem(on_create, 409, "SLUG_CONFLICT")
    assert_problem(on_patch, 409, "SLUG_CONFLICT")
    assert "product" in on_patch.json()["detail"]
    assert [row.action for row in await _audit(db_session, second["id"])] == ["product.created"]


async def test_deleting_a_product_releases_its_slug(db_session: AsyncSession) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        first = _create(client, _stl(refs))
        assert _delete(client, first["id"], 1).status_code == 204
        second = _create(client, _stl(refs, slug=first["slug"]))

    rows = await _product_rows(db_session, first["slug"])
    assert {str(row.id) for row in rows} == {first["id"], second["id"]}


# --- soft delete -----------------------------------------------------------


async def test_delete_is_soft_keeps_visibility_and_bumps_the_version(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs, is_visible=True))
        response = _delete(client, product["id"], 1)
        read = client.get(f"{PRODUCTS}/{product['id']}")

    assert response.status_code == 204
    assert read.status_code == 200
    body = read.json()
    assert body["deleted_at"] is not None
    assert body["is_visible"] is True and body["version"] == 2
    assert len(await _product_rows(db_session, product["slug"])) == 1


@pytest.mark.parametrize("operation", ["patch", "delete"])
async def test_a_deleted_product_cannot_be_mutated(
    db_session: AsyncSession, operation: str
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))
        assert _delete(client, product["id"], 1).status_code == 204
        if operation == "patch":
            response = _patch(client, product | {"version": 2}, name="Back")
        else:
            response = _delete(client, product["id"], 2)

    assert_problem(response, 409, "INVALID_STATE_TRANSITION")
    actions = [row.action for row in await _audit(db_session, product["id"])]
    assert actions == ["product.created", "product.deleted"]


@pytest.mark.parametrize("version", [None, "abc", "0", "-1"])
async def test_delete_requires_a_valid_version(db_session: AsyncSession, version: Any) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))
        path = f"{PRODUCTS}/{product['id']}"
        response = client.delete(
            path if version is None else f"{path}?version={version}", headers=csrf(client)
        )
        after = client.get(path).json()

    assert_problem(response, 422, "VALIDATION_ERROR")
    assert after["deleted_at"] is None


# --- optimistic concurrency (ADR-020) --------------------------------------


@pytest.mark.parametrize("operation", ["patch", "delete"])
async def test_a_stale_version_is_409_with_the_current_version_and_writes_nothing(
    db_session: AsyncSession, operation: str
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))
        newer = _patch(client, product, name="Newer").json()
        if operation == "patch":
            response = _patch(client, product, name="Stale")
        else:
            response = _delete(client, product["id"], product["version"])
        after = client.get(f"{PRODUCTS}/{product['id']}").json()

    assert_problem(response, 409, "VERSION_CONFLICT")
    assert response.json()["current_version"] == 2
    assert after == newer
    actions = [row.action for row in await _audit(db_session, product["id"])]
    assert actions == ["product.created", "product.updated"]


async def test_every_write_increments_the_version_by_one(db_session: AsyncSession) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))
        for expected in (2, 3, 4):
            product = _patch(client, product, name=f"n{expected}").json()
            assert product["version"] == expected
        assert _delete(client, product["id"], 4).status_code == 204
        assert client.get(f"{PRODUCTS}/{product['id']}").json()["version"] == 5


# --- references ------------------------------------------------------------


@pytest.mark.parametrize("field", _REF_KEYS)
@pytest.mark.parametrize("state", ["archived", "unknown"])
async def test_an_archived_or_unknown_reference_is_refused(
    db_session: AsyncSession, field: str, state: str
) -> None:
    refs = await _refs(db_session)
    target = str(uuid.uuid4())
    if state == "archived":
        dead = await _refs(db_session)
        models: dict[str, type[CategoryModel] | type[MaterialModel] | type[ColourModel]] = {
            "category_id": CategoryModel,
            "material_id": MaterialModel,
            "colour_id": ColourModel,
        }
        model = models[field]
        await db_session.execute(
            update(model)
            .where(model.id == uuid.UUID(dead[field]))
            .values(is_active=False, deleted_at=func.now())
        )
        await db_session.commit()
        target = dead[field]
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        created = client.post(
            PRODUCTS, json=_physical(refs, **{field: target}), headers=csrf(client)
        )
        product = _create(client, _physical(refs))
        patched = _patch(client, product, **{field: target})

    for response in (created, patched):
        assert_problem(response, 422, "VALIDATION_ERROR")
        assert ("body", field) in _locs(response)
    assert [row.action for row in await _audit(db_session, product["id"])] == ["product.created"]


async def test_disabled_reference_values_can_be_assigned(db_session: AsyncSession) -> None:
    """Owner decision: an admin may prepare products under a value not yet live."""
    refs = await _refs(db_session, active=False)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        created = _create(client, _physical(refs))
    assert created["category_id"] == refs["category_id"]


# --- audit -----------------------------------------------------------------


async def test_every_successful_write_is_audited_with_actor_and_snapshots(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        admin_id = admin.id
        product = _create(client, _physical(refs))
        updated = _patch(client, product, name="Renamed").json()
        assert _delete(client, product["id"], 2).status_code == 204

    rows = await _audit(db_session, product["id"])
    assert [row.action for row in rows] == ["product.created", "product.updated", "product.deleted"]
    assert {row.entity_type for row in rows} == {"Product"}
    assert {row.actor_user_id for row in rows} == {admin_id}
    created, renamed, deleted = rows
    assert created.before_data is None and created.after_data is not None
    assert created.after_data["type"] == "physical" and created.after_data["version"] == 1
    assert renamed.before_data == created.after_data
    assert renamed.after_data is not None and renamed.after_data["name"] == updated["name"]
    assert deleted.before_data == renamed.after_data
    assert deleted.after_data is not None and deleted.after_data["deleted_at"] is not None
    assert "review_count" not in created.after_data


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_a_failed_audit_write_rolls_back_the_product_change(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """FR-04 failure behaviour: the change and its audit row commit together or not at all."""
    refs = await _refs(db_session)
    body = _stl(refs)
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))

        async def refuse(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(SqlAuditWriter, "record", refuse)
        if operation == "create":
            response = client.post(PRODUCTS, json=body, headers=csrf(client))
        elif operation == "update":
            response = _patch(client, product, name="Lost")
        else:
            response = _delete(client, product["id"], 1)
        monkeypatch.undo()
        after = client.get(f"{PRODUCTS}/{product['id']}").json()

    assert_problem(response, 500, "INTERNAL_ERROR")
    assert await _product_rows(db_session, body["slug"]) == []
    assert after == product


# --- authorization and CSRF ------------------------------------------------


def _operations(product_id: str) -> list[tuple[str, str, Any]]:
    item = f"{PRODUCTS}/{product_id}"
    return [
        ("GET", PRODUCTS, None),
        ("POST", PRODUCTS, {}),
        ("GET", item, None),
        ("PATCH", item, {"version": 1, "name": "x"}),
        ("DELETE", f"{item}?version=1", None),
    ]


async def test_anonymous_callers_get_401_and_customers_404_on_every_operation(
    db_session: AsyncSession,
) -> None:
    refs = await _refs(db_session)
    customer = await create_user(db_session)
    with client_for(main_app) as admin_client:
        await mfa_admin(admin_client, db_session)
        product = _create(admin_client, _stl(refs))
    for method, path, body in _operations(product["id"]):
        with client_for(main_app) as anonymous:
            assert_problem(anonymous.request(method, path, json=body), 401, "AUTH_REQUIRED")
        with client_for(main_app) as client:
            login(client, customer.email)
            response = client.request(method, path, json=body, headers=csrf(client))
            assert_problem(response, 404, "NOT_FOUND")


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
async def test_an_unknown_product_is_404(db_session: AsyncSession, method: str) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        path = f"{PRODUCTS}/{uuid.uuid4()}"
        if method == "DELETE":
            path += "?version=1"
        body = {"version": 1, "name": "x"} if method == "PATCH" else None
        response = client.request(method, path, json=body, headers=csrf(client))
    assert_problem(response, 404, "NOT_FOUND")


async def test_unsafe_methods_require_the_csrf_header(db_session: AsyncSession) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _stl(refs))
        item = f"{PRODUCTS}/{product['id']}"
        responses = [
            client.post(PRODUCTS, json=_stl(refs)),
            client.patch(item, json={"version": 1, "name": "x"}),
            client.delete(f"{item}?version=1"),
        ]
        after = client.get(item).json()

    for response in responses:
        assert_problem(response, 403, "CSRF_INVALID")
    assert after == product


# --- list ------------------------------------------------------------------


async def test_the_list_filters_by_each_field(db_session: AsyncSession) -> None:
    refs = await _refs(db_session)
    token = uuid.uuid4().hex[:10]
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        stl = _create(client, _stl(refs, name=f"Dragon {token}", is_featured=True))
        physical = _create(
            client, _physical(refs, name="Lamp", is_visible=True, is_available=False)
        )
        gone = _create(client, _stl(refs))
        assert _delete(client, gone["id"], 1).status_code == 204

        def ids(**params: Any) -> set[str]:
            response = client.get(PRODUCTS, params={"category_id": refs["category_id"]} | params)
            assert response.status_code == 200, response.text
            return {item["id"] for item in response.json()["items"]}

        assert ids() == {stl["id"], physical["id"]}
        assert ids(type="stl") == {stl["id"]}
        assert ids(is_visible="true") == {physical["id"]}
        assert ids(is_featured="true") == {stl["id"]}
        assert ids(is_available="false") == {physical["id"]}
        assert ids(deleted="true") == {gone["id"]}
        assert ids(q=token) == {stl["id"]}
        assert ids(q="dragons") == {stl["id"]}  # english stemming; deleted rows excluded
        assert ids(q="100%_") == set()


@pytest.mark.parametrize("sort", ["-created_at", "price", "-price"])
async def test_cursor_pages_cover_every_row_once_in_order(
    db_session: AsyncSession, sort: str
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        made = [
            _create(client, _stl(refs, price={"amount_cents": cents}))
            for cents in (300, 100, 300, 200, 100)
        ]
        seen: list[dict[str, Any]] = []
        cursor = None
        while True:
            params = {"category_id": refs["category_id"], "sort": sort, "limit": 2}
            page = client.get(PRODUCTS, params=params | ({"cursor": cursor} if cursor else {}))
            assert page.status_code == 200, page.text
            seen += page.json()["items"]
            cursor = page.json()["next_cursor"]
            if cursor is None:
                break

    assert sorted(p["id"] for p in seen) == sorted(p["id"] for p in made)
    keys = [p["created_at"] if sort == "-created_at" else p["price"]["amount_cents"] for p in seen]
    assert keys == sorted(keys, reverse=sort.startswith("-"))


def _cursor(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "not-a-cursor"},
        {"cursor": _cursor({"s": "price", "k": 1, "i": str(uuid.UUID(int=0))})},
        {"sort": "name"},
        {"q": "a\x01b"},
        {"limit": 101},
        {"type": "digital"},
    ],
    ids=["garbage", "cursor-from-another-sort", "unknown-sort", "control-char", "limit", "type"],
)
async def test_bad_list_parameters_are_422(
    db_session: AsyncSession, params: dict[str, Any]
) -> None:
    """The second cursor is well-formed but for `price`, used against the default sort."""
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(PRODUCTS, params=params)
    assert_problem(response, 422, "VALIDATION_ERROR")
