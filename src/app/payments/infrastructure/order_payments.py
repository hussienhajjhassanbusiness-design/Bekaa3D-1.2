"""Ordering's `OrderPaymentReader` (VS-025 plan Q4): per order, whether a payment reached
paid and the one attempt the customer is shown. Never a provider reference."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ordering.application.ports import OrderPaymentView, PaymentAttemptRef
from app.payments.domain.enums import PaymentStatus
from app.payments.domain.outcome import REACHED_PAID
from app.payments.infrastructure.models import PaymentModel

_ENDED = frozenset({PaymentStatus.FAILED, PaymentStatus.EXPIRED})


class SqlOrderPaymentReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def views(self, order_ids: Sequence[UUID]) -> dict[UUID, OrderPaymentView]:
        if not order_ids:
            return {}
        p = PaymentModel
        rows = (
            await self._session.execute(
                select(p.order_id, p.id, p.provider, p.status, p.amount_cents, p.currency)
                .where(p.order_id.in_(order_ids))
                .order_by(p.order_id, p.initiated_at.desc(), p.id.desc())
            )
        ).all()
        by_order: dict[UUID, list[PaymentAttemptRef]] = {}
        for row in rows:
            by_order.setdefault(row.order_id, []).append(
                PaymentAttemptRef(
                    row.id, row.provider.value, row.status.value, row.amount_cents, row.currency
                )
            )
        return {order_id: _view(attempts) for order_id, attempts in by_order.items()}


def _view(newest_first: list[PaymentAttemptRef]) -> OrderPaymentView:
    """The one live-or-paid attempt (`uq_payments_one_live`), else the newest ended one."""
    current = [a for a in newest_first if PaymentStatus(a.status) not in _ENDED]
    return OrderPaymentView(
        reached_paid=any(PaymentStatus(a.status) in REACHED_PAID for a in newest_first),
        shown=(current or newest_first)[0],
    )
