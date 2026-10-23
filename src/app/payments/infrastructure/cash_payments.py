"""The one writer of a `cash` payment (VS-029; SRS 9.8.3, BR-054): called only by the
cash handover, under the order's locks. Also the admin order detail's payment rows."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.domain.exceptions import CashAlreadyRecordedError
from app.payments.domain.payments import OrderPaymentRow
from app.payments.infrastructure.models import PaymentModel

_P = PaymentModel
# A second cash row breaks both; which one Postgres reports depends on index order.
ALREADY_RECORDED = frozenset({"uq_payments_one_cash", "uq_payments_one_live"})


def _constraint(error: IntegrityError) -> str | None:
    name = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    return name if isinstance(name, str) else None


async def insert_cash_payment(
    session: AsyncSession,
    *,
    order_id: UUID,
    amount_cents: int,
    currency: str,
    recorded_by: UUID,
    at: datetime,
) -> UUID:
    """Created directly as `paid` (SRS 20.1); `uq_payments_one_cash` is the final guard."""
    try:
        async with session.begin_nested():
            payment_id: UUID = (
                await session.execute(
                    insert(_P)
                    .values(
                        order_id=order_id,
                        provider=PaymentProvider.CASH,
                        order_payment_method="cash",
                        status=PaymentStatus.PAID,
                        amount_cents=amount_cents,
                        currency=currency,
                        initiated_at=at,
                        verified_at=at,
                        recorded_by=recorded_by,
                    )
                    .returning(_P.id)
                )
            ).scalar_one()
    except IntegrityError as exc:
        if _constraint(exc) in ALREADY_RECORDED:
            raise CashAlreadyRecordedError(f"order {order_id} already has its cash") from exc
        raise
    return payment_id


async def order_payment_rows(session: AsyncSession, order_id: UUID) -> list[OrderPaymentRow]:
    """Every payment of one order, newest first; no reference, metadata or captured data."""
    rows = await session.execute(
        select(
            _P.id,
            _P.provider,
            _P.status,
            _P.amount_cents,
            _P.currency,
            _P.initiated_at,
            _P.verified_at,
            _P.late_captured_at,
            _P.recorded_by,
        )
        .where(_P.order_id == order_id)
        .order_by(_P.initiated_at.desc(), _P.id.desc())
    )
    return [
        OrderPaymentRow(
            id=row.id,
            provider=row.provider.value,
            status=row.status.value,
            amount_cents=row.amount_cents,
            currency=row.currency,
            initiated_at=row.initiated_at,
            verified_at=row.verified_at,
            late_captured_at=row.late_captured_at,
            recorded_by=row.recorded_by,
        )
        for row in rows
    ]
