"""Refund rows read for the order projection (VS-030 plan 3.0, 3.4). Plain reads, made
after the caller holds the orders lock: every refund writer takes that lock first."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.application.ports import NO_REFUNDS, RefundFacts
from app.payments.domain.outcome import REACHED_PAID
from app.payments.domain.refunds import PaymentFact, RefundFact, facts_for
from app.payments.infrastructure.models import PaymentModel, RefundModel

_P, _R = PaymentModel, RefundModel


async def order_refund_facts(session: AsyncSession, order_id: UUID) -> RefundFacts:
    """`NO_REFUNDS` until a payment reached paid. Chargebacks join here in PR C."""
    paid = (
        await session.execute(
            select(_P.id, _P.provider, _P.status, _P.amount_cents).where(
                _P.order_id == order_id, _P.status.in_(REACHED_PAID)
            )
        )
    ).first()
    if paid is None:
        return NO_REFUNDS
    rows = await session.execute(
        select(_R.id, _R.payment_id, _R.kind, _R.status, _R.reissued_at, _R.amount_cents)
        .where(_R.order_id == order_id)
        .order_by(_R.id)
    )
    refunds = [
        RefundFact(r.id, r.payment_id, r.kind, r.status, r.reissued_at is not None, r.amount_cents)
        for r in rows
    ]
    return facts_for(PaymentFact(paid.id, paid.provider, paid.status, paid.amount_cents), refunds)
