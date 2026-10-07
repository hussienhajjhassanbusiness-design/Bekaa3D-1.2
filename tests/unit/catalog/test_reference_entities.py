"""The three-state lifecycle shared by categories, materials and colours.

`is_active` and `deleted_at` are different states, not two spellings of one, and
these tests pin that down where it is cheapest to check - before any of it
reaches a query predicate.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.catalog.domain.entities import Category, Colour, Material

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def _category(*, is_active: bool = True, deleted_at: datetime | None = None) -> Category:
    return Category(
        id=uuid.uuid4(),
        name="Lamps",
        slug="lamps",
        is_active=is_active,
        deleted_at=deleted_at,
        created_at=NOW,
        updated_at=NOW,
    )


def _material(*, is_active: bool = True, deleted_at: datetime | None = None) -> Material:
    return Material(
        id=uuid.uuid4(),
        name="Resin",
        is_active=is_active,
        deleted_at=deleted_at,
        created_at=NOW,
        updated_at=NOW,
    )


def _colour(*, is_active: bool = True, deleted_at: datetime | None = None) -> Colour:
    return Colour(
        id=uuid.uuid4(),
        name="Matte Black",
        is_active=is_active,
        deleted_at=deleted_at,
        created_at=NOW,
        updated_at=NOW,
    )


# --------------------------------------------------------------------------
# Three states
# --------------------------------------------------------------------------


def test_a_live_active_row_is_publicly_visible() -> None:
    assert _category().is_publicly_visible is True
    assert _category().is_archived is False


def test_a_disabled_row_is_retained_but_hidden() -> None:
    """Disabled is not archived: the row keeps its slug and can be reactivated."""
    disabled = _category(is_active=False)
    assert disabled.is_publicly_visible is False
    assert disabled.is_archived is False


def test_an_archived_row_is_hidden_whatever_is_active_says() -> None:
    """Belt and braces. `archive()` clears `is_active`, but if a row ever
    reached this state some other way it must still not be public."""
    archived = Category(
        id=uuid.uuid4(),
        name="Lamps",
        slug="lamps",
        is_active=True,
        deleted_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    assert archived.is_archived is True
    assert archived.is_publicly_visible is False


@pytest.mark.parametrize("factory", [_category, _material, _colour])
def test_archiving_sets_both_columns_together(factory: object) -> None:
    """A row must never be "archived but still flagged active": every public
    query filters on both columns, and one that satisfied only one of them
    would be a latent bug waiting for a query that checks the other."""
    value = factory()  # type: ignore[operator]
    later = NOW + timedelta(hours=1)

    value.archive(later)

    assert value.deleted_at == later
    assert value.is_active is False
    assert value.updated_at == later
    assert value.is_publicly_visible is False


# --------------------------------------------------------------------------
# Partial update
# --------------------------------------------------------------------------


def test_updating_nothing_reports_no_change_and_leaves_the_timestamp() -> None:
    """The VS-007 convention: a PATCH submitting the values already stored is a
    successful request that changes nothing, and `updated_at` describes when the
    row last actually moved."""
    category = _category()
    later = NOW + timedelta(hours=1)

    changed = category.apply_update(name="Lamps", slug="lamps", is_active=True, at=later)

    assert changed is False
    assert category.updated_at == NOW


def test_omitted_fields_are_left_alone() -> None:
    category = _category()
    later = NOW + timedelta(hours=1)

    changed = category.apply_update(name="Desk Lamps", slug=None, is_active=None, at=later)

    assert changed is True
    assert category.name == "Desk Lamps"
    assert category.slug == "lamps"
    assert category.is_active is True
    assert category.updated_at == later


def test_a_disabled_row_can_be_reactivated() -> None:
    """The documented route back from `is_active=false`, and the reason archive
    and disable have to stay distinct states."""
    category = _category(is_active=False)
    later = NOW + timedelta(hours=1)

    changed = category.apply_update(name=None, slug=None, is_active=True, at=later)

    assert changed is True
    assert category.is_publicly_visible is True


def test_setting_active_to_its_current_value_is_not_a_change() -> None:
    """`is not` rather than `!=`, so a bool compared against itself is handled
    without Python's True == 1 trap ever coming up."""
    material = _material(is_active=True)
    assert material.apply_update(name=None, is_active=True, at=NOW) is False


# --------------------------------------------------------------------------
# Audit snapshot
# --------------------------------------------------------------------------


def test_a_category_snapshot_carries_its_slug() -> None:
    snapshot = _category().audit_snapshot()
    assert snapshot == {"name": "Lamps", "is_active": True, "deleted_at": None, "slug": "lamps"}


@pytest.mark.parametrize("factory", [_material, _colour])
def test_a_simple_value_snapshot_has_no_slug(factory: object) -> None:
    snapshot = factory().audit_snapshot()  # type: ignore[operator]
    assert "slug" not in snapshot
    assert set(snapshot) == {"name", "is_active", "deleted_at"}


def test_an_archived_snapshot_serialises_the_timestamp() -> None:
    """`deleted_at` goes into JSONB, so it has to be a string rather than a
    datetime the driver would refuse."""
    category = _category()
    category.archive(NOW)
    snapshot = category.audit_snapshot()
    assert snapshot["deleted_at"] == NOW.isoformat()
    assert isinstance(snapshot["deleted_at"], str)
