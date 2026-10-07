"""BR-013 / FR-04: a category, material or colour a live product uses cannot be
archived (409 CATEGORY_IN_USE); reassigning or deleting the product frees it."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.test_admin_products import (
    PRODUCTS,
    _audit,
    _create,
    _delete,
    _patch,
    _physical,
    _refs,
)
from tests.integration.deep_support import assert_problem, client_for, csrf, mfa_admin

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

RESOURCES = [
    pytest.param("category_id", "/api/v1/admin/categories", "category", id="category"),
    pytest.param("material_id", "/api/v1/admin/materials", "material", id="material"),
    pytest.param("colour_id", "/api/v1/admin/colours", "colour", id="colour"),
]


@pytest.mark.parametrize(("field", "path", "prefix"), RESOURCES)
async def test_a_value_a_live_product_uses_cannot_be_archived(
    db_session: AsyncSession, field: str, path: str, prefix: str
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        _create(client, _physical(refs))
        response = client.delete(f"{path}/{refs[field]}", headers=csrf(client))
        after = client.get(f"{path}/{refs[field]}").json()

    assert_problem(response, 409, "CATEGORY_IN_USE")
    assert after["deleted_at"] is None and after["is_active"] is True
    assert [row.action for row in await _audit(db_session, refs[field])] == []


@pytest.mark.parametrize(("field", "path", "prefix"), RESOURCES)
async def test_reassigning_the_product_frees_the_value(
    db_session: AsyncSession, field: str, path: str, prefix: str
) -> None:
    refs, spare = await _refs(db_session), await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _physical(refs))
        assert _patch(client, product, **{field: spare[field]}).status_code == 200
        response = client.delete(f"{path}/{refs[field]}", headers=csrf(client))

    assert response.status_code == 204, response.text
    rows = await _audit(db_session, refs[field])
    assert [row.action for row in rows] == [f"{prefix}.archived"]


@pytest.mark.parametrize(("field", "path", "prefix"), RESOURCES)
async def test_a_value_used_only_by_deleted_products_can_be_archived(
    db_session: AsyncSession, field: str, path: str, prefix: str
) -> None:
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        product = _create(client, _physical(refs))
        assert _delete(client, product["id"], 1).status_code == 204
        response = client.delete(f"{path}/{refs[field]}", headers=csrf(client))
        kept = client.get(f"{PRODUCTS}/{product['id']}").json()

    assert response.status_code == 204, response.text
    assert kept[field] == refs[field]


@pytest.mark.parametrize(("field", "path", "prefix"), RESOURCES)
async def test_disabling_a_used_value_is_still_allowed(
    db_session: AsyncSession, field: str, path: str, prefix: str
) -> None:
    """Only archiving is guarded; disabling just hides the value publicly."""
    refs = await _refs(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        _create(client, _physical(refs))
        response = client.patch(
            f"{path}/{refs[field]}", json={"is_active": False}, headers=csrf(client)
        )
    assert response.status_code == 200, response.text
    assert uuid.UUID(response.json()["id"]) == uuid.UUID(refs[field])
