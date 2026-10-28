"""orders.anonymized_at and addresses.anonymized_at (VS-045, ADR-047): an anonymised row may
lack its phone and address, and must lack every personal field. Revision ID: 0b349a492461,
revises eeed201dcfd2."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0b349a492461"
down_revision: str | None = "eeed201dcfd2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PHONE = "fulfillment_method IS NULL OR contact_phone_snapshot IS NOT NULL"
_ADDRESS = (
    "fulfillment_method IS DISTINCT FROM 'delivery' OR (recipient_name IS NOT NULL "
    "AND governorate IS NOT NULL AND city IS NOT NULL AND landmark_notes IS NOT NULL)"
)
_ORDER_SHAPE = (
    "anonymized_at IS NULL OR (recipient_name IS NULL AND contact_phone_snapshot IS NULL "
    "AND city IS NULL AND area IS NULL AND street IS NULL AND landmark_notes IS NULL "
    "AND customer_note IS NULL)"
)
# The existing length and E.164 CHECKs pass on NULL, so only NOT NULL moves into a CHECK.
_BOOK_REQUIRED = ("recipient_name", "phone", "city", "landmark_notes")
_BOOK_PRESENT = (
    "anonymized_at IS NOT NULL OR ("
    + " AND ".join(f"{c} IS NOT NULL" for c in _BOOK_REQUIRED)
    + ")"
)
_BOOK_SHAPE = (
    "anonymized_at IS NULL OR (deleted_at IS NOT NULL AND recipient_name IS NULL "
    "AND phone IS NULL AND city IS NULL AND area IS NULL AND street IS NULL "
    "AND landmark_notes IS NULL)"
)


def _replace(name: str, condition: str) -> None:
    op.drop_constraint(name, "orders", type_="check")
    op.create_check_constraint(name, "orders", condition)


def upgrade() -> None:
    op.add_column("orders", sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True))
    _replace("ck_orders_physical_has_phone", f"anonymized_at IS NOT NULL OR {_PHONE}")
    _replace("ck_orders_delivery_address", f"anonymized_at IS NOT NULL OR {_ADDRESS}")
    op.create_check_constraint("ck_orders_anonymised_shape", "orders", _ORDER_SHAPE)

    op.add_column(
        "addresses", sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True)
    )
    for column in _BOOK_REQUIRED:
        op.alter_column("addresses", column, existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(
        "ck_addresses_required_unless_anonymised", "addresses", _BOOK_PRESENT
    )
    op.create_check_constraint("ck_addresses_anonymised_shape", "addresses", _BOOK_SHAPE)


def downgrade() -> None:
    # Fails once an anonymised row exists: its phone and address are gone for good.
    op.drop_constraint("ck_addresses_anonymised_shape", "addresses", type_="check")
    op.drop_constraint("ck_addresses_required_unless_anonymised", "addresses", type_="check")
    for column in _BOOK_REQUIRED:
        op.alter_column("addresses", column, existing_type=sa.Text(), nullable=False)
    op.drop_column("addresses", "anonymized_at")

    op.drop_constraint("ck_orders_anonymised_shape", "orders", type_="check")
    _replace("ck_orders_delivery_address", _ADDRESS)
    _replace("ck_orders_physical_has_phone", _PHONE)
    op.drop_column("orders", "anonymized_at")
