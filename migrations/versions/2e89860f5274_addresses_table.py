"""addresses (VS-026): database-design.md 5.2, one live default per user, Lebanese only.

Revision ID: 2e89860f5274, revises c2b3aae1cdee."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2e89860f5274"
down_revision: str | None = "c2b3aae1cdee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GOVERNORATES = (
    "'akkar', 'baalbek_hermel', 'beirut', 'beqaa', 'keserwan_jbeil', "
    "'mount_lebanon', 'nabatieh', 'north', 'south'"
)


def _required(column: str, limit: int) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"char_length({column}) <= {limit} AND {column} ~ '[^[:space:]]'",
        name=f"ck_addresses_{column}_length",
    )


def _optional(column: str, limit: int) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} IS NULL OR (char_length({column}) <= {limit} AND {column} ~ '[^[:space:]]')",
        name=f"ck_addresses_{column}_length",
    )


def upgrade() -> None:
    op.create_table(
        "addresses",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("recipient_name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("governorate", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("area", sa.Text(), nullable=True),
        sa.Column("street", sa.Text(), nullable=True),
        sa.Column("landmark_notes", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        # CASCADE: the unverified purge must never be blocked; verified users are only anonymised.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "NOT (is_default AND deleted_at IS NOT NULL)", name="ck_addresses_deleted_not_default"
        ),
        sa.CheckConstraint(f"governorate IN ({_GOVERNORATES})", name="ck_addresses_governorate"),
        sa.CheckConstraint("phone ~ '^\\+961[0-9]{7,8}$'", name="ck_addresses_phone_e164"),
        _required("label", 50),
        _required("recipient_name", 100),
        _required("city", 100),
        _required("landmark_notes", 500),
        _optional("area", 100),
        _optional("street", 200),
    )
    op.create_index(
        "uq_addresses_one_default_per_user",
        "addresses",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_addresses_user_live",
        "addresses",
        ["user_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_addresses_user_live", table_name="addresses")
    op.drop_index("uq_addresses_one_default_per_user", table_name="addresses")
    op.drop_table("addresses")
