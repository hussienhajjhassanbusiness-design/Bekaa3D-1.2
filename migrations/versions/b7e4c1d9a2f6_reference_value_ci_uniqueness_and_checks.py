"""case-insensitive live uniqueness and archived-not-active checks for reference data

Revision ID: b7e4c1d9a2f6
Revises: 5e1c0a7d2b94
Create Date: 2026-10-01 12:00:00.000000

Additive only - no column changes, nothing dropped:

- `ix_materials_live_name_ci`, `ix_colours_live_name_ci`: UNIQUE(lower(name))
  WHERE deleted_at IS NULL. Materials and colours are facet values; "PLA"
  beside "pla" would split one storefront filter into two (SRS 592). Partial,
  so archiving a value releases its name, exactly as archiving a category
  releases its slug.
- `ix_categories_live_slug_ci`: UNIQUE(lower(slug)) WHERE deleted_at IS NULL,
  beside the existing exact `ix_categories_live_slug`. The application already
  lowercases slugs; this makes the database refuse a case variant written any
  other way.
- `ck_<table>_archived_not_active`: CHECK (deleted_at IS NULL OR NOT is_active)
  on all three tables - an archived row can never still be flagged active.

Existing rows:

- Archived rows still flagged active are normalised to `is_active = false`
  before the CHECK is added. That is the state `archive()` has always written,
  and an archived row is hidden from every public read either way, so no
  visible behaviour changes.
- Live case-insensitive duplicates cannot be resolved automatically - which
  of two live "PLA"/"pla" rows survives is an administrator's decision - so
  the upgrade stops before changing anything and names every duplicate
  group. Rename or archive the extras through the admin API, then rerun.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4c1d9a2f6"
down_revision: str | None = "5e1c0a7d2b94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("categories", "materials", "colours")

# (table, column, index)
_CI_UNIQUE = (
    ("categories", "slug", "ix_categories_live_slug_ci"),
    ("materials", "name", "ix_materials_live_name_ci"),
    ("colours", "name", "ix_colours_live_name_ci"),
)


class LiveDuplicatesError(RuntimeError):
    """Live rows that differ only by case; resolve them before upgrading."""


def _live_duplicates() -> list[str]:
    bind = op.get_bind()
    found: list[str] = []
    for table, column, _ in _CI_UNIQUE:
        rows = bind.execute(
            sa.text(
                f"SELECT lower({column}) AS value, count(*) AS n, "
                f"string_agg(id::text, ', ' ORDER BY id) AS ids "
                f"FROM {table} WHERE deleted_at IS NULL "
                f"GROUP BY lower({column}) HAVING count(*) > 1 ORDER BY 1"
            )
        ).all()
        found.extend(f"{table}.{column} {row.value!r} x{row.n} (ids: {row.ids})" for row in rows)
    return found


def upgrade() -> None:
    duplicates = _live_duplicates()
    if duplicates:
        raise LiveDuplicatesError(
            "Cannot add case-insensitive uniqueness: these live values differ only "
            "by case. Rename or archive the extras, then rerun the upgrade. "
            + "; ".join(duplicates)
        )

    for table in _TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} SET is_active = false WHERE deleted_at IS NOT NULL AND is_active"
            )
        )
        op.create_check_constraint(
            f"ck_{table}_archived_not_active",
            table,
            "deleted_at IS NULL OR NOT is_active",
        )

    for table, column, index in _CI_UNIQUE:
        op.create_index(
            index,
            table,
            [sa.text(f"lower({column})")],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    for table, _, index in reversed(_CI_UNIQUE):
        op.drop_index(index, table_name=table, postgresql_where=sa.text("deleted_at IS NULL"))
    for table in reversed(_TABLES):
        op.drop_constraint(f"ck_{table}_archived_not_active", table, type_="check")
    # The upgrade's `is_active = false` normalisation of archived rows is not
    # reversed: it is the state archiving has always meant to write, and no
    # read distinguishes it.
