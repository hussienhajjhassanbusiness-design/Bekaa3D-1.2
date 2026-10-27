"""Payments' reporting reads (VS-043; VS-030 plan 3.7). Unlocked display reads that never
decide money (ADR-042 d14); each joins only Payments' own tables."""

from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.public import order_ids_for_user
from app.payments.domain.enums import PaymentStatus, RefundKind, RefundStatus
from app.payments.infrastructure.models import (
    ChargebackItemModel,
    ChargebackModel,
    PaymentModel,
    RefundItemModel,
    RefundModel,
)

_CHUNK = 5_000
_REACHED_PAID = (PaymentStatus.PAID, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)
_NOT_LATE = RefundModel.kind != RefundKind.LATE_CAPTURE
# Plan 3.7: what revenue subtracts. Pending and settled only; never failed, voided or late.
_REVENUE_COUNTED = _NOT_LATE & RefundModel.status.in_((RefundStatus.PENDING, RefundStatus.SETTLED))
# `is_counted` (domain/refunds.py) in SQL: also a failed refund not yet reissued.
_COVERAGE_COUNTED = _NOT_LATE & (
    RefundModel.status.in_((RefundStatus.PENDING, RefundStatus.SETTLED))
    | ((RefundModel.status == RefundStatus.FAILED) & RefundModel.reissued_at.is_(None))
)
# `ix_refunds_obligations`' predicate, any kind (BR-126, VS-045 note).
_OBLIGATION = (RefundModel.status == RefundStatus.PENDING) | (
    (RefundModel.status == RefundStatus.FAILED) & RefundModel.reissued_at.is_(None)
)


def _chunks(ids: Sequence[UUID]) -> Iterator[list[UUID]]:
    for start in range(0, len(ids), _CHUNK):
        yield list(ids[start : start + _CHUNK])


@dataclass(frozen=True)
class PaidPaymentRow:
    id: UUID
    order_id: UUID
    verified_at: datetime


_PAID = select(PaymentModel.id, PaymentModel.order_id, PaymentModel.verified_at).where(
    PaymentModel.status.in_(_REACHED_PAID)
)


def _rows(found: Sequence[tuple[UUID, UUID, datetime | None]]) -> list[PaidPaymentRow]:
    # `ck_payments_paid_verified`: a payment that reached paid always has `verified_at`.
    return [PaidPaymentRow(pid, oid, at) for pid, oid, at in found if at is not None]


async def paid_payments_between(
    session: AsyncSession, lower: datetime, upper: datetime
) -> list[PaidPaymentRow]:
    """Payments that reached paid with `verified_at` in [lower, upper)."""
    query = _PAID.where(PaymentModel.verified_at >= lower, PaymentModel.verified_at < upper)
    return _rows((await session.execute(query)).tuples().all())


async def paid_payment_page(
    session: AsyncSession, *, before: tuple[datetime, UUID] | None, limit: int
) -> list[PaidPaymentRow]:
    """Newest `verified_at` first, keyset on (verified_at, id) descending."""
    query = _PAID
    if before is not None:
        query = query.where(tuple_(PaymentModel.verified_at, PaymentModel.id) < tuple_(*before))
    query = query.order_by(PaymentModel.verified_at.desc(), PaymentModel.id.desc()).limit(limit)
    return _rows((await session.execute(query)).tuples().all())


async def chargeback_excess_cents(session: AsyncSession, payment_ids: Sequence[UUID]) -> int:
    """What chargebacks on these payments charged beyond every line (never on a line)."""
    total = 0
    for chunk in _chunks(payment_ids):
        query = select(func.coalesce(func.sum(ChargebackModel.excess_cents), 0)).where(
            ChargebackModel.payment_id.in_(chunk)
        )
        total += int((await session.execute(query)).scalar_one())
    return total


async def refunded_cents_by_line(
    session: AsyncSession, line_ids: Sequence[UUID]
) -> dict[UUID, int]:
    """Pending and settled refund items plus chargeback items, per line; never failed,
    voided or late_capture (VS-030 plan 3.7)."""
    out: defaultdict[UUID, int] = defaultdict(int)
    for chunk in _chunks(line_ids):
        refunded = (
            select(RefundItemModel.order_item_id, func.sum(RefundItemModel.amount_cents))
            .join(RefundModel, RefundModel.id == RefundItemModel.refund_id)
            .where(RefundItemModel.order_item_id.in_(chunk), _REVENUE_COUNTED)
            .group_by(RefundItemModel.order_item_id)
        )
        charged = (
            select(ChargebackItemModel.order_item_id, func.sum(ChargebackItemModel.amount_cents))
            .where(ChargebackItemModel.order_item_id.in_(chunk))
            .group_by(ChargebackItemModel.order_item_id)
        )
        for query in (refunded, charged):
            for line_id, cents in (await session.execute(query)).tuples():
                out[line_id] += int(cents)
    return dict(out)


async def refund_covered_lines(session: AsyncSession, line_ids: Sequence[UUID]) -> frozenset[UUID]:
    """Lines something counts against: an item in a pending, settled or owed refund (not
    late_capture), or a chargeback item. L1/L2's coverage (`line_balances`)."""
    covered: set[UUID] = set()
    for chunk in _chunks(line_ids):
        refunded = (
            select(RefundItemModel.order_item_id)
            .join(RefundModel, RefundModel.id == RefundItemModel.refund_id)
            .where(RefundItemModel.order_item_id.in_(chunk), _COVERAGE_COUNTED)
        )
        charged = select(ChargebackItemModel.order_item_id).where(
            ChargebackItemModel.order_item_id.in_(chunk)
        )
        for query in (refunded, charged):
            covered.update((await session.execute(query)).scalars())
    return frozenset(covered)


async def unsettled_refund_exists(session: AsyncSession, user_id: UUID) -> bool:
    """A pending refund, an owed one, or a pending late_capture on any of the user's orders
    (BR-126). Unlocked: VS-045 calls it again under its own user and order locks."""
    order_ids = await order_ids_for_user(session, user_id)
    for chunk in _chunks(order_ids):
        query = select(exists().where(RefundModel.order_id.in_(chunk), _OBLIGATION))
        if (await session.execute(query)).scalar():
            return True
    return False
