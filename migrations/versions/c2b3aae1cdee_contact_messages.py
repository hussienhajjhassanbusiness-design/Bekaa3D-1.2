"""contact_messages (VS-033): database-design.md 12.6; user_id and order_id come with VS-029b.

Revision ID: c2b3aae1cdee, revises cc87333ebe79."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c2b3aae1cdee"
down_revision: str | None = "cc87333ebe79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("new", "read", "replied", "archived", name="contact_message_status"),
            server_default="new",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "char_length(name) <= 100 AND name ~ '[^[:space:]]'",
            name="ck_contact_messages_name_length",
        ),
        sa.CheckConstraint(
            "char_length(email) BETWEEN 3 AND 254 AND position('@' in email) > 1",
            name="ck_contact_messages_email_shape",
        ),
        sa.CheckConstraint(
            "phone IS NULL OR (char_length(phone) <= 32 AND phone ~ '[^[:space:]]')",
            name="ck_contact_messages_phone_length",
        ),
        sa.CheckConstraint(
            "subject IS NULL OR (char_length(subject) <= 200 AND subject ~ '[^[:space:]]')",
            name="ck_contact_messages_subject_length",
        ),
        sa.CheckConstraint(
            "char_length(message) <= 5000 AND message ~ '[^[:space:]]'",
            name="ck_contact_messages_message_length",
        ),
    )
    op.create_index("ix_contact_messages_queue", "contact_messages", ["status", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_contact_messages_queue", table_name="contact_messages")
    op.drop_table("contact_messages")
    # drop_table leaves the implicitly created enum type behind (see ac29d4c2170c).
    sa.Enum(name="contact_message_status").drop(op.get_bind(), checkfirst=True)
