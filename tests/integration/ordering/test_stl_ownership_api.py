"""`GET /api/v1/me/stl-ownership` (VS-023 plan 2.3, 6.2; ADR-025 d2): true only for a
listed STL the caller paid for and was not refunded."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.enums import ProductType
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user, login
from tests.integration.payments.support import seed_online_order

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]
OWNERSHIP = "/api/v1/me/stl-ownership"


async def _stl(db: AsyncSession) -> uuid.UUID:
    return (await seed_product(db, await seed_refs(db), type=ProductType.STL)).id


@pytest.mark.parametrize(
    ("line_status", "owned"),
    [(None, False), ("pending", False), ("awaiting_delivery", True), ("delivered", True)],
    ids=["never-bought", "own-unpaid", "awaiting-delivery", "delivered"],
)
async def test_ownership_follows_the_paid_line_states(
    db_session: AsyncSession, line_status: str | None, owned: bool
) -> None:
    stl = await _stl(db_session)
    user = await create_user(db_session, verified=False)
    if line_status is not None:
        await seed_online_order(db_session, user_id=user.id, stl_id=stl, line_status=line_status)
    with client_for(main_app) as client:
        login(client, user.email)
        response = client.get(OWNERSHIP, params={"product_id": str(stl)})
    assert response.status_code == 200, response.text
    assert response.json() == {"product_id": str(stl), "owned": owned}


async def test_another_customers_purchase_is_not_yours(db_session: AsyncSession) -> None:
    stl = await _stl(db_session)
    other = await create_user(db_session)
    await seed_online_order(db_session, user_id=other.id, stl_id=stl, line_status="delivered")
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        assert client.get(OWNERSHIP, params={"product_id": str(stl)}).json()["owned"] is False


async def test_unknown_hidden_and_physical_products_answer_false(db_session: AsyncSession) -> None:
    refs = await seed_refs(db_session)
    user = await create_user(db_session)
    hidden = (await seed_product(db_session, refs, type=ProductType.STL)).id
    await seed_online_order(db_session, user_id=user.id, stl_id=hidden, line_status="delivered")
    await db_session.execute(
        text("UPDATE products SET is_visible = false WHERE id = :i"), {"i": hidden}
    )
    await db_session.commit()
    physical = (await seed_product(db_session, refs)).id
    with client_for(main_app) as client:
        login(client, user.email)
        answers = [
            client.get(OWNERSHIP, params={"product_id": str(p)}).json()["owned"]
            for p in (uuid.uuid4(), hidden, physical)
        ]
    assert answers == [False, False, False]


@pytest.mark.parametrize("params", [{}, {"product_id": "not-a-uuid"}])
async def test_a_missing_or_malformed_product_id_is_422(
    db_session: AsyncSession, params: dict[str, str]
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        assert_problem(client.get(OWNERSHIP, params=params), 422, "VALIDATION_ERROR")


def test_anonymous_is_401() -> None:
    with client_for(main_app) as client:
        assert_problem(client.get(OWNERSHIP, params={"product_id": str(uuid.uuid4())}), 401)
