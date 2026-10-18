"""payments.captured_amount_cents and captured_currency (VS-024 PR A, plan 4.2): what the
provider reported captured, so a late capture's refund need not parse audit JSON.

Revision ID: 00ce1ce252a6, revises 03a4730dd046."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "00ce1ce252a6"
down_revision: str | None = "03a4730dd046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Declared locally, not imported from the model: a migration is frozen history.
_SHAPE = (
    "(captured_amount_cents IS NULL OR captured_amount_cents >= 0) "
    "AND (captured_currency IS NULL OR captured_currency ~ '^[A-Z]{3}$') "
    "AND (captured_currency IS NULL OR captured_amount_cents IS NOT NULL)"
)
_WHEN = (
    "captured_amount_cents IS NULL OR (provider <> 'cash' AND (late_captured_at IS NOT NULL "
    "OR status IN ('paid', 'partially_refunded', 'refunded')))"
)


def upgrade() -> None:
    # Nullable without a default: metadata-only ADD COLUMN, and every existing row passes.
    op.add_column("payments", sa.Column("captured_amount_cents", sa.BigInteger(), nullable=True))
    op.add_column("payments", sa.Column("captured_currency", sa.CHAR(3), nullable=True))
    op.create_check_constraint("ck_payments_captured_shape", "payments", _SHAPE)
    op.create_check_constraint("ck_payments_captured_when", "payments", _WHEN)


def downgrade() -> None:
    # Dependents first: both CHECKs read the columns, so they go before them.
    op.drop_constraint("ck_payments_captured_when", "payments", type_="check")
    op.drop_constraint("ck_payments_captured_shape", "payments", type_="check")
    op.drop_column("payments", "captured_currency")
    op.drop_column("payments", "captured_amount_cents")
