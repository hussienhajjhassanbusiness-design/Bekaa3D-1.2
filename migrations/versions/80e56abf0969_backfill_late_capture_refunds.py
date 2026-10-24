"""Backfill late-capture refunds (VS-030 PR C, plan 4.3): one pending `late_capture` refund
for every late-captured payment without a live one. Rerunnable; a malformed audit row is
skipped and reported. Revision ID: 80e56abf0969, revises c01e53ab3e0f."""

import json
import logging
import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "80e56abf0969"
down_revision: str | None = "c01e53ab3e0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# Frozen here, not imported: a migration is history (the live sink's rules, VS-030 Q6).
BATCH_SIZE = 500
MARKER = f"late capture (backfill {revision})"
NO_AMOUNT_NOTE = "provider reported no amount; check the dashboard"
MAX_CENTS = 10**12
_CURRENCY = re.compile(r"[A-Z]{3}")
_NO_AUDIT = object()

_REFUNDS = sa.table(
    "refunds",
    sa.column("order_id"),
    sa.column("payment_id"),
    sa.column("payment_provider"),
    sa.column("kind"),
    sa.column("status"),
    sa.column("amount_cents"),
    sa.column("currency"),
    sa.column("reason"),
    sa.column("initiated_at"),
)
_LIVE_LATE = sa.text("kind = 'late_capture' AND status NOT IN ('failed', 'voided')")
_PAYMENTS = sa.text(
    "SELECT id, order_id, provider, amount_cents, currency, captured_amount_cents,"
    " captured_currency, late_captured_at FROM payments"
    " WHERE late_captured_at IS NOT NULL AND id > :after ORDER BY id LIMIT :limit"
)
# Any late-capture refund at all, whatever its status: a failed or voided one is already
# the admin's to handle, so a rerun never adds a second obligation beside it.
_HANDLED = sa.text(
    "SELECT DISTINCT payment_id FROM refunds WHERE kind = 'late_capture' AND payment_id = ANY(:ids)"
)
_AUDITS = sa.text(
    "SELECT DISTINCT ON (entity_id) entity_id, after_data FROM audit_logs"
    " WHERE entity_type = 'payment' AND action = 'payment.late_capture'"
    " AND entity_id = ANY(:ids) ORDER BY entity_id, created_at, id"
)


def _cents(raw: object) -> int | None:
    """An int, or a string of digits, in (0, 10^12]; anything else (a float) is malformed."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, str) and raw.strip().isdigit():
        raw = int(raw.strip())
    if isinstance(raw, int) and 0 < raw <= MAX_CENTS:
        return raw
    return None


def resolve(payment: Any, audit: object) -> tuple[int, str, bool] | str:
    """(amount, currency, flagged), or the skip reason: the stored capture, else the oldest
    audit row, else (no audit row at all) the attempt's amount, flagged (Q6)."""
    if payment.captured_amount_cents is not None:
        if payment.captured_amount_cents <= 0:
            return "amount_zero"
        return payment.captured_amount_cents, payment.captured_currency or payment.currency, False
    if audit is _NO_AUDIT:
        return payment.amount_cents, payment.currency, True
    if not isinstance(audit, dict) or "captured_amount_cents" not in audit:
        return "audit_malformed"
    currency = audit.get("captured_currency")
    if currency is not None and not (isinstance(currency, str) and _CURRENCY.fullmatch(currency)):
        return "audit_malformed"
    if audit["captured_amount_cents"] is None:  # none reported: the attempt's, in its own (Q6)
        return payment.amount_cents, payment.currency, True
    amount = _cents(audit["captured_amount_cents"])
    if amount is None:
        return "audit_malformed"
    return amount, currency or payment.currency, False


def backfill(bind: sa.Connection, *, batch_size: int = BATCH_SIZE) -> dict[str, int]:
    """Keyset batches on `payments.id`; each batch one INSERT ... ON CONFLICT DO NOTHING
    (the index still decides against a concurrent live late capture)."""
    counts = {"scanned": 0, "created": 0, "existing": 0, "skipped": 0, "batches": 0}
    skipped: list[dict[str, str]] = []
    after = "00000000-0000-0000-0000-000000000000"
    while rows := bind.execute(_PAYMENTS, {"after": after, "limit": batch_size}).all():
        after = rows[-1].id
        counts["batches"] += 1
        counts["scanned"] += len(rows)
        ids = [p.id for p in rows]
        handled = set(bind.execute(_HANDLED, {"ids": ids}).scalars())
        audits = {row.entity_id: row.after_data for row in bind.execute(_AUDITS, {"ids": ids})}
        values = []
        for payment in rows:
            if payment.id in handled:
                counts["existing"] += 1
                continue
            outcome = resolve(payment, audits.get(payment.id, _NO_AUDIT))
            if isinstance(outcome, str):
                logger.warning(
                    "late_capture_backfill_skipped payment_id=%s reason=%s", payment.id, outcome
                )
                skipped.append({"payment_id": str(payment.id), "reason": outcome})
                continue
            amount, currency, flagged = outcome
            values.append(
                {
                    "order_id": payment.order_id,
                    "payment_id": payment.id,
                    "payment_provider": payment.provider,
                    "kind": "late_capture",
                    "status": "pending",
                    "amount_cents": amount,
                    "currency": currency,
                    "reason": f"{MARKER}; {NO_AMOUNT_NOTE}" if flagged else MARKER,
                    "initiated_at": payment.late_captured_at,
                }
            )
        created = 0
        if values:
            insert = (
                postgresql.insert(_REFUNDS)
                .values(values)
                .on_conflict_do_nothing(index_elements=["payment_id"], index_where=_LIVE_LATE)
                .returning(sa.column("payment_id"))
            )
            created = len(bind.execute(insert).all())
        counts["created"] += created
        counts["existing"] += len(values) - created
    counts["skipped"] = len(skipped)
    if skipped:
        bind.execute(
            sa.text(
                "INSERT INTO audit_logs (action, entity_type, after_data)"
                " VALUES ('refund.backfill_skipped', 'refund', CAST(:data AS jsonb))"
            ),
            {"data": json.dumps({"revision": revision, "skipped": skipped})},
        )
    logger.info(
        "late_capture_backfill: scanned=%(scanned)d created=%(created)d"
        " existing=%(existing)d skipped=%(skipped)d",
        counts,
    )
    return counts


def remove(bind: sa.Connection) -> tuple[int, int]:
    """(deleted, kept): only this revision's still-pending rows nothing reissued; settled,
    failed or voided ones are money history and stay."""
    deleted = bind.execute(
        sa.text(
            "DELETE FROM refunds r WHERE r.kind = 'late_capture' AND r.reason LIKE :marker"
            " AND r.status = 'pending' AND NOT EXISTS"
            " (SELECT 1 FROM refunds x WHERE x.reissue_of_refund_id = r.id) RETURNING r.id"
        ),
        {"marker": f"{MARKER}%"},
    ).all()
    kept = bind.scalar(
        sa.text("SELECT count(*) FROM refunds WHERE kind = 'late_capture' AND reason LIKE :m"),
        {"m": f"{MARKER}%"},
    )
    logger.info("late_capture_backfill_downgrade_kept=%d deleted=%d", kept, len(deleted))
    return len(deleted), int(kept or 0)


def upgrade() -> None:
    backfill(op.get_bind())


def downgrade() -> None:
    remove(op.get_bind())
