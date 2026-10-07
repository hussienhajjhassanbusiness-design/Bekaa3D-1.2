"""The three public reference lists.

These endpoints are unauthenticated and feed the storefront's facet filters. The
property that matters most is negative: a value an administrator has disabled or
archived must never appear, and no lifecycle column may leak into the response.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.api.reference_data import PUBLIC_LIST_LIMIT
from app.catalog.infrastructure.models import CategoryModel, ColourModel, MaterialModel

CATEGORIES = "/api/v1/categories"
MATERIALS = "/api/v1/materials"
COLOURS = "/api/v1/colours"


async def seed_category(
    db_session: AsyncSession,
    *,
    name: str | None = None,
    slug: str | None = None,
    is_active: bool = True,
    archived: bool = False,
) -> CategoryModel:
    token = uuid.uuid4().hex[:12]
    row = CategoryModel(
        name=name or f"cat-{token}",
        slug=slug or f"cat-{token}",
        # Archived rows are always inactive: `archive()` writes that, and the
        # ck_<table>_archived_not_active CHECK refuses anything else.
        is_active=is_active and not archived,
        deleted_at=datetime.now(UTC) if archived else None,
    )
    db_session.add(row)
    await db_session.flush()
    await db_session.commit()
    return row


async def seed_material(
    db_session: AsyncSession,
    *,
    name: str | None = None,
    is_active: bool = True,
    archived: bool = False,
) -> MaterialModel:
    row = MaterialModel(
        name=name or f"mat-{uuid.uuid4().hex[:12]}",
        # Archived rows are always inactive: `archive()` writes that, and the
        # ck_<table>_archived_not_active CHECK refuses anything else.
        is_active=is_active and not archived,
        deleted_at=datetime.now(UTC) if archived else None,
    )
    db_session.add(row)
    await db_session.flush()
    await db_session.commit()
    return row


async def seed_colour(
    db_session: AsyncSession,
    *,
    name: str | None = None,
    is_active: bool = True,
    archived: bool = False,
) -> ColourModel:
    row = ColourModel(
        name=name or f"col-{uuid.uuid4().hex[:12]}",
        # Archived rows are always inactive: `archive()` writes that, and the
        # ck_<table>_archived_not_active CHECK refuses anything else.
        is_active=is_active and not archived,
        deleted_at=datetime.now(UTC) if archived else None,
    )
    db_session.add(row)
    await db_session.flush()
    await db_session.commit()
    return row


def _get(path: str) -> dict[str, Any]:
    from app.main import app

    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _prefix() -> str:
    # Leading digits sort before letters in both the C and en_US collations, so
    # these rows sit near the front of the capped, name-ordered window.
    return f"00-{uuid.uuid4().hex[:12]}"


def assert_window_covers(returned: set[str], sentinel_id: object, path: str) -> None:
    """Refuse to let a hidden-row assertion pass vacuously.

    The public lists are capped at `PUBLIC_LIST_LIMIT` rows ordered by name and
    the database is shared by the whole suite, so a row can be missing from the
    response merely because 100 other live rows sort before it. Each test seeds
    its rows under one prefix plus a live *sentinel* that sorts after all of
    them: if the sentinel is returned, every row under test lay inside the
    returned window, so "not in the response" really means "filtered out".
    """
    assert str(sentinel_id) in returned, (
        f"{path}: the sentinel is outside the capped window, so the hidden-row "
        "assertions below could not prove anything"
    )


# --------------------------------------------------------------------------
# Only live, active values are public
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_categories_expose_only_live_active_rows(db_session: AsyncSession) -> None:
    prefix = _prefix()
    live = await seed_category(db_session, name=f"{prefix}-a")
    disabled = await seed_category(db_session, name=f"{prefix}-b", is_active=False)
    archived = await seed_category(db_session, name=f"{prefix}-c", archived=True)
    sentinel = await seed_category(db_session, name=f"{prefix}-z")

    returned = {item["id"] for item in _get(CATEGORIES)["items"]}

    assert_window_covers(returned, sentinel.id, CATEGORIES)
    assert str(live.id) in returned
    assert str(disabled.id) not in returned, "a disabled category must not be public"
    assert str(archived.id) not in returned, "an archived category must not be public"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_materials_expose_only_live_active_rows(db_session: AsyncSession) -> None:
    prefix = _prefix()
    live = await seed_material(db_session, name=f"{prefix}-a")
    disabled = await seed_material(db_session, name=f"{prefix}-b", is_active=False)
    archived = await seed_material(db_session, name=f"{prefix}-c", archived=True)
    sentinel = await seed_material(db_session, name=f"{prefix}-z")

    returned = {item["id"] for item in _get(MATERIALS)["items"]}

    assert_window_covers(returned, sentinel.id, MATERIALS)
    assert str(live.id) in returned
    assert str(disabled.id) not in returned
    assert str(archived.id) not in returned


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_colours_expose_only_live_active_rows(db_session: AsyncSession) -> None:
    prefix = _prefix()
    live = await seed_colour(db_session, name=f"{prefix}-a")
    disabled = await seed_colour(db_session, name=f"{prefix}-b", is_active=False)
    archived = await seed_colour(db_session, name=f"{prefix}-c", archived=True)
    sentinel = await seed_colour(db_session, name=f"{prefix}-z")

    returned = {item["id"] for item in _get(COLOURS)["items"]}

    assert_window_covers(returned, sentinel.id, COLOURS)
    assert str(live.id) in returned
    assert str(disabled.id) not in returned
    assert str(archived.id) not in returned


# --------------------------------------------------------------------------
# Response shape
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_public_responses_never_carry_lifecycle_columns(db_session: AsyncSession) -> None:
    """The second of the two guards. Even if the query filter were wrong, the
    response schema has no field for operational state to land in."""
    await seed_category(db_session)
    await seed_material(db_session)
    await seed_colour(db_session)

    category = _get(CATEGORIES)["items"][0]
    material = _get(MATERIALS)["items"][0]
    colour = _get(COLOURS)["items"][0]

    assert set(category) == {"id", "name", "slug"}
    assert set(material) == {"id", "name"}
    assert set(colour) == {"id", "name"}
    for item in (category, material, colour):
        for leaked in ("is_active", "deleted_at", "created_at", "updated_at"):
            assert leaked not in item


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_lists_are_bounded_lists_not_cursor_pages(db_session: AsyncSession) -> None:
    """api-endpoints.md calls these "hard-limited reference list". They are
    deliberately not paginated, so there is no `next_cursor` to follow."""
    await seed_category(db_session)
    body = _get(CATEGORIES)
    assert set(body) == {"items"}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_empty_list_is_an_empty_array(db_session: AsyncSession) -> None:
    """api-endpoints.md 2: `"items": []`, never null and never a 404. Asserted
    on shape rather than emptiness, since the table is shared across the
    suite."""
    body = _get(COLOURS)
    assert isinstance(body["items"], list)


# --------------------------------------------------------------------------
# Ordering and the hard cap
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_categories_are_ordered_by_name(db_session: AsyncSession) -> None:
    prefix = f"zz-{uuid.uuid4().hex[:8]}"
    for suffix in ("charlie", "alpha", "bravo"):
        await seed_category(db_session, name=f"{prefix}-{suffix}")

    names = [item["name"] for item in _get(CATEGORIES)["items"] if item["name"].startswith(prefix)]

    assert names == sorted(names), f"expected alphabetical order, got {names}"
    assert names == [f"{prefix}-alpha", f"{prefix}-bravo", f"{prefix}-charlie"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_public_list_is_capped(db_session: AsyncSession) -> None:
    """The V1 hard limit is 100. Seeded past the cap so the response is bounded
    by the limit rather than by how much test data happens to exist.

    The seeded rows are removed afterwards (test-data cleanup, not an
    application delete). Left behind, 105 live materials would crowd every
    later test's rows out of the capped public list, which made the suite
    order-dependent (audit A-06).
    """
    seeded = [
        MaterialModel(name=f"cap-{uuid.uuid4().hex[:8]}-{index:03d}", is_active=True)
        for index in range(PUBLIC_LIST_LIMIT + 5)
    ]
    db_session.add_all(seeded)
    await db_session.commit()

    try:
        items = _get(MATERIALS)["items"]
    finally:
        await db_session.execute(
            delete(MaterialModel).where(MaterialModel.id.in_([row.id for row in seeded]))
        )
        await db_session.commit()

    assert len(items) == PUBLIC_LIST_LIMIT
