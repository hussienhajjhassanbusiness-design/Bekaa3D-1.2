"""Seed `homepage_hero_image` (docs/homepage-hero-image.md): JSON null, the default visual.

Revision ID: c8e2f4a6b1d3, revises b7c41e2a9d10."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8e2f4a6b1d3"
down_revision: str | None = "b7c41e2a9d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared locally, not imported from models: a migration is frozen history.
_settings = sa.table(
    "settings",
    sa.column("key", sa.Text),
    sa.column(
        "type",
        postgresql.ENUM(
            "boolean",
            "integer",
            "string",
            "money",
            "duration",
            "json",
            name="setting_type",
            create_type=False,
        ),
    ),
    # none_as_null=False: an unconfigured setting stores JSON null, not SQL NULL.
    sa.column("value", postgresql.JSONB(none_as_null=False)),
    sa.column("description", sa.Text),
)
_KEY = "homepage_hero_image"


def upgrade() -> None:
    op.execute(
        postgresql.insert(_settings)
        .values(
            key=_KEY,
            type="string",
            value=None,
            description=(
                "The homepage hero's large image, uploaded through PUT /api/v1/admin/home/"
                "hero-image. Null shows the default brand visual."
            ),
        )
        .on_conflict_do_nothing(index_elements=["key"])
    )


def downgrade() -> None:
    op.execute(sa.delete(_settings).where(_settings.c.key == _KEY))
