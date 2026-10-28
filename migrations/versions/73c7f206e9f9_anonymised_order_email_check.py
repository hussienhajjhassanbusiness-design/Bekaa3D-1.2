"""An anonymised order also holds its account's anonymised email (VS-045 audit A-04, ADR-047 d2).
Revision ID: 73c7f206e9f9, revises 0b349a492461."""

from collections.abc import Sequence

from alembic import op

revision: str = "73c7f206e9f9"
down_revision: str | None = "0b349a492461"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_orders_anonymised_shape"
_SCRUBBED = (
    "recipient_name IS NULL AND contact_phone_snapshot IS NULL AND city IS NULL "
    "AND area IS NULL AND street IS NULL AND landmark_notes IS NULL AND customer_note IS NULL"
)
_EMAIL = "customer_email_snapshot = 'deleted+' || user_id::text || '@invalid'"


def _shape(condition: str) -> None:
    op.drop_constraint(_NAME, "orders", type_="check")
    op.create_check_constraint(_NAME, "orders", f"anonymized_at IS NULL OR ({condition})")


def upgrade() -> None:
    _shape(f"{_SCRUBBED} AND {_EMAIL}")


def downgrade() -> None:
    _shape(_SCRUBBED)
