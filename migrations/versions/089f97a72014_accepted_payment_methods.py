"""Accepted payment methods per physical product, snapshotted on physical lines (VS-049, ADR-048).

Revision ID: 089f97a72014, revises 73c7f206e9f9."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "089f97a72014"
down_revision: str | None = "73c7f206e9f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM = postgresql.ENUM("online", "cash", "online_or_cash", name="accepted_payment_methods")
_SNAPSHOT = "accepted_payment_methods_snapshot"

# Frozen copies, not imports from the model: a migration must not change when the code does.
_TYPE_INTEGRITY_BEFORE = (
    "(type = 'physical' AND purchase_mode IS NOT NULL AND production_lead_time_days IS NOT NULL"
    " AND batch_size IS NOT NULL AND max_quantity_per_line IS NOT NULL)"
    " OR (type = 'stl' AND purchase_mode IS NULL AND material_id IS NULL AND colour_id IS NULL"
    " AND dimensions IS NULL AND production_lead_time_days IS NULL AND batch_size IS NULL"
    " AND max_quantity_per_line IS NULL AND weight_grams IS NULL)"
)
_TYPE_INTEGRITY = (
    "(type = 'physical' AND purchase_mode IS NOT NULL AND accepted_payment_methods IS NOT NULL"
    " AND production_lead_time_days IS NOT NULL"
    " AND batch_size IS NOT NULL AND max_quantity_per_line IS NOT NULL)"
    " OR (type = 'stl' AND purchase_mode IS NULL AND accepted_payment_methods IS NULL"
    " AND material_id IS NULL AND colour_id IS NULL"
    " AND dimensions IS NULL AND production_lead_time_days IS NULL AND batch_size IS NULL"
    " AND max_quantity_per_line IS NULL AND weight_grams IS NULL)"
)
_BY_TYPE = f"(product_type = 'physical') = ({_SNAPSHOT} IS NOT NULL)"
_METHOD_ACCEPTED = (
    f"{_SNAPSHOT} IS NULL OR {_SNAPSHOT} = 'online_or_cash' "
    f"OR ({_SNAPSHOT} = 'cash' AND payment_method = 'cash') "
    f"OR ({_SNAPSHOT} = 'online' AND payment_method = 'online')"
)


def _type_integrity(condition: str) -> None:
    op.drop_constraint("ck_products_type_integrity", "products", type_="check")
    op.create_check_constraint("ck_products_type_integrity", "products", condition)


def upgrade() -> None:
    _ENUM.create(op.get_bind())
    op.add_column("products", sa.Column("accepted_payment_methods", _ENUM, nullable=True))
    # Today every physical product accepts both, so the backfill changes no behaviour.
    op.execute(
        "UPDATE products SET accepted_payment_methods = 'online_or_cash' WHERE type = 'physical'"
    )
    _type_integrity(_TYPE_INTEGRITY)

    op.add_column("order_items", sa.Column(_SNAPSHOT, _ENUM, nullable=True))
    op.execute(
        f"UPDATE order_items SET {_SNAPSHOT} = 'online_or_cash' WHERE product_type = 'physical'"
    )
    op.create_check_constraint("ck_order_items_accepted_methods_by_type", "order_items", _BY_TYPE)
    op.create_check_constraint("ck_order_items_method_accepted", "order_items", _METHOD_ACCEPTED)


def downgrade() -> None:
    op.drop_constraint("ck_order_items_method_accepted", "order_items", type_="check")
    op.drop_constraint("ck_order_items_accepted_methods_by_type", "order_items", type_="check")
    op.drop_column("order_items", _SNAPSHOT)
    _type_integrity(_TYPE_INTEGRITY_BEFORE)
    op.drop_column("products", "accepted_payment_methods")
    _ENUM.drop(op.get_bind())
