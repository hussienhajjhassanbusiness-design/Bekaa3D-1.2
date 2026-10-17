"""custom_requests, custom_request_attachments, the retention setting and a `custom_request`
notification type (VS-034, ADR-030). Revision ID: 26d5d039d72c, revises bde6135b2538."""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "26d5d039d72c"
down_revision: str | None = "bde6135b2538"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STORAGE_KEY_FORMAT = (
    "storage_key ~ '^custom-requests/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
    "[0-9a-f]{12}\\.(jpg|png|webp)$'"
)
_NOTIFICATION_TYPES = ("account", "order", "payment", "refund", "offer", "download")

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
_RETENTION_KEY = "custom_request_attachment_retention"


def _text_check(column: str, maximum: int, *, nullable: bool = False) -> sa.CheckConstraint:
    rule = f"char_length({column}) <= {maximum} AND {column} ~ '[^[:space:]]'"
    if nullable:
        rule = f"{column} IS NULL OR ({rule})"
    return sa.CheckConstraint(rule, name=f"ck_custom_requests_{column}_length")


def _moment(name: str, *, nullable: bool = True) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "custom_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("project_title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("preferred_material", sa.Text(), nullable=True),
        sa.Column("preferred_colour", sa.Text(), nullable=True),
        sa.Column("dimensions", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "contacted",
                "quoted",
                "in_progress",
                "completed",
                "closed",
                "lost",
                name="custom_request_status",
            ),
            server_default="new",
            nullable=False,
        ),
        # The pipeline columns VS-035 writes; it has no migration of its own.
        sa.Column("quoted_amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(3), nullable=True),
        sa.Column("outcome", sa.Enum("won", "lost", name="custom_request_outcome"), nullable=True),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        _moment("contacted_at"),
        _moment("quoted_at"),
        _moment("completed_at"),
        _moment("closed_at"),
        _moment("created_at", nullable=False),
        _moment("updated_at", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _text_check("name", 100),
        sa.CheckConstraint(
            "char_length(email) BETWEEN 3 AND 254 AND position('@' in email) > 1",
            name="ck_custom_requests_email_shape",
        ),
        _text_check("phone", 32),
        _text_check("project_title", 200),
        _text_check("description", 5000),
        _text_check("preferred_material", 100, nullable=True),
        _text_check("preferred_colour", 100, nullable=True),
        _text_check("dimensions", 200, nullable=True),
        _text_check("admin_notes", 5000, nullable=True),
        # database-design.md 12.4: a quote is lead reporting in USD cents, never a charge.
        sa.CheckConstraint(
            "quoted_amount_cents IS NULL OR (quoted_amount_cents >= 0 AND currency = 'USD')",
            name="ck_custom_requests_quote_money",
        ),
        sa.CheckConstraint(
            "(quoted_amount_cents IS NULL) = (currency IS NULL)",
            name="ck_custom_requests_currency_with_quote",
        ),
    )
    op.create_index("ix_custom_requests_queue", "custom_requests", ["status", "created_at", "id"])

    op.create_table(
        "custom_request_attachments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("custom_request_id", sa.UUID(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        # Scanning is synchronous, so a row only ever exists for a clean file (ADR-030).
        sa.Column("scan_status", sa.Enum("clean", name="upload_scan_status"), nullable=False),
        _moment("expires_at", nullable=False),
        _moment("created_at", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["custom_request_id"], ["custom_requests.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key", name="uq_custom_request_attachments_storage_key"),
        sa.CheckConstraint(
            _STORAGE_KEY_FORMAT, name="ck_custom_request_attachments_storage_key_format"
        ),
        sa.CheckConstraint(
            "char_length(original_filename) BETWEEN 1 AND 255",
            name="ck_custom_request_attachments_filename_length",
        ),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_custom_request_attachments_mime_type",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_custom_request_attachments_size_positive"),
        sa.CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'", name="ck_custom_request_attachments_checksum_sha256"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_custom_request_attachments_expires_after_created"
        ),
    )
    op.create_index(
        "ix_custom_request_attachments_expires_at", "custom_request_attachments", ["expires_at"]
    )
    op.create_index(
        "ix_custom_request_attachments_request",
        "custom_request_attachments",
        ["custom_request_id"],
    )

    op.execute(
        postgresql.insert(_settings)
        .values(
            key=_RETENTION_KEY,
            type="duration",
            value=7_776_000,  # 90 days
            description="Seconds a Bring Your Idea reference image is kept before it is purged.",
        )
        .on_conflict_do_nothing(index_elements=["key"])
    )
    # Not usable in this same transaction, and nothing here uses it.
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'custom_request'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value, so the type is rebuilt without it.
    op.execute("DELETE FROM notifications WHERE type = 'custom_request'")
    op.execute("ALTER TYPE notification_type RENAME TO notification_type_old")
    sa.Enum(*_NOTIFICATION_TYPES, name="notification_type").create(op.get_bind())
    op.execute(
        "ALTER TABLE notifications ALTER COLUMN type TYPE notification_type "
        "USING type::text::notification_type"
    )
    op.execute("DROP TYPE notification_type_old")

    op.execute(_settings.delete().where(_settings.c.key == _RETENTION_KEY))
    op.drop_index("ix_custom_request_attachments_request", "custom_request_attachments")
    op.drop_index("ix_custom_request_attachments_expires_at", "custom_request_attachments")
    op.drop_table("custom_request_attachments")
    op.drop_index("ix_custom_requests_queue", table_name="custom_requests")
    op.drop_table("custom_requests")
    # drop_table leaves the implicitly created enum types behind (see ac29d4c2170c).
    for name in ("upload_scan_status", "custom_request_outcome", "custom_request_status"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
