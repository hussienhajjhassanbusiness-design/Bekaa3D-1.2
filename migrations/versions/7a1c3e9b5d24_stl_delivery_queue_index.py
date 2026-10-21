"""STL delivery queue index and daily_download_cap removed (VS-023b, ADR-019). Revision ID:
7a1c3e9b5d24, revises fcd589e89e59."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7a1c3e9b5d24"
down_revision: str | None = "fcd589e89e59"
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
    sa.column("value", postgresql.JSONB(none_as_null=False)),
    sa.column("description", sa.Text),
)

# Restored on downgrade exactly as de1d8a23512f seeded it.
_DAILY_DOWNLOAD_CAP = {
    "key": "daily_download_cap",
    "type": "integer",
    "value": 20,
    "description": "Download attempts allowed per authenticated customer per UTC day.",
}


def upgrade() -> None:
    op.create_index(
        "ix_order_items_stl_awaiting",
        "order_items",
        ["created_at", "id"],
        postgresql_where=sa.text(
            "product_type = 'stl' AND fulfillment_status = 'awaiting_delivery'"
        ),
    )
    op.execute(_settings.delete().where(_settings.c.key == _DAILY_DOWNLOAD_CAP["key"]))


def downgrade() -> None:
    op.execute(
        postgresql.insert(_settings)
        .values([_DAILY_DOWNLOAD_CAP])
        .on_conflict_do_nothing(index_elements=["key"])
    )
    op.drop_index("ix_order_items_stl_awaiting", table_name="order_items")
