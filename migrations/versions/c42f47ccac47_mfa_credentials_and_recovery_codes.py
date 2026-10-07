"""mfa credentials and recovery codes

Revision ID: c42f47ccac47
Revises: 33a9f7a809ea
Create Date: 2026-08-26 01:06:02.313057

VS-005. Creates exactly the two tables frozen in database-design.md 5.6 and
5.7, with no added columns, constraints or indexes.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c42f47ccac47"
down_revision: str | None = "33a9f7a809ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mfa_credentials",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "method",
            sa.Enum("totp", name="mfa_method"),
            server_default="totp",
            nullable=False,
        ),
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        # RFC 6238 5.2 replay protection: the time-step of the last accepted
        # TOTP. NULL until the credential accepts its first code. Edited into
        # this revision rather than added as a follow-up because VS-005 is
        # still unmerged, so no database anywhere has run it yet.
        sa.Column("last_totp_step", sa.BigInteger(), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
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
        # CASCADE is correct only for a legitimate physical purge; ordinary
        # account closure is anonymisation (database-design.md 5.6 "FK Delete").
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # "at most one MFA credential per user" (database-design.md 5.6). Held
        # in the database rather than the application because two concurrent
        # enrollments would otherwise both succeed and leave an account with
        # two secrets, either of which would open the admin boundary.
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("mfa_credential_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["mfa_credential_id"], ["mfa_credentials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    # Exactly the partial index database-design.md 5.7 specifies. Every hot
    # query filters on unused rows, and spent codes are dead weight in it.
    op.create_index(
        "ix_mfa_recovery_codes_unused",
        "mfa_recovery_codes",
        ["mfa_credential_id"],
        unique=False,
        postgresql_where=sa.text("used_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mfa_recovery_codes_unused",
        table_name="mfa_recovery_codes",
        postgresql_where=sa.text("used_at IS NULL"),
    )
    op.drop_table("mfa_recovery_codes")
    op.drop_table("mfa_credentials")
    # Autogenerate does not emit this, and without it the downgrade is not
    # actually reversible: `create_table` creates the `mfa_method` type
    # implicitly, `drop_table` leaves it behind, and the next `upgrade` dies on
    # `type "mfa_method" already exists`. CONTRIBUTING.md requires the
    # downgrade/upgrade round-trip to pass before a migration PR is opened, so
    # the type is dropped explicitly here.
    #
    # `checkfirst=True` keeps the downgrade idempotent if the type was already
    # removed by hand during recovery from a botched migration.
    sa.Enum(name="mfa_method").drop(op.get_bind(), checkfirst=True)
