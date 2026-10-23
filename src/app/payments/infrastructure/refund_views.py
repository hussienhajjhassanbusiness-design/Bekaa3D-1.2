"""Refund reads for the order details (VS-030 plan 1, ADR-033 d7): the admin's refunds and
balances, and the customer's summary (Q9). Display only: no lock, never decides money."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.ordering.public import OrderItemStatus
from app.payments.domain.enums import RefundKind, RefundStatus
from app.payments.domain.outcome import REACHED_PAID
from app.payments.domain.refunds import (
    ItemFact,
    Ledger,
    LineFact,
    PaymentFact,
    RefundFact,
    line_balances,
    payment_balance,
)
from app.payments.infrastructure.models import PaymentModel
from app.payments.infrastructure.refunds import RefundRow, order_refunds

CustomerRefundStatus = Literal["processing", "refunded"]


@dataclass(frozen=True)
class RefundBalances:
    lines: dict[UUID, int]
    payment_cents: int


@dataclass(frozen=True)
class CustomerRefund:
    kind: RefundKind
    status: CustomerRefundStatus
    amount_cents: int
    currency: str
    created_at: datetime


def _fact(row: RefundRow) -> RefundFact:
    items = tuple(ItemFact(i.order_item_id, i.amount_cents) for i in row.items)
    reissued = row.reissued_at is not None
    return RefundFact(
        row.id, row.payment_id, row.kind, row.status, reissued, row.amount_cents, items
    )


class _Line(Protocol):
    @property
    def id(self) -> UUID: ...
    @property
    def product_type(self) -> ProductType: ...
    @property
    def fulfillment_status(self) -> OrderItemStatus: ...
    @property
    def line_total_cents(self) -> int: ...


async def admin_refunds(
    session: AsyncSession, order_id: UUID, total_cents: int, lines: Sequence[_Line]
) -> tuple[list[RefundRow], RefundBalances | None]:
    """The order's refunds, oldest first, and the balances (None until paid)."""
    rows = await order_refunds(session, order_id)
    paid = (
        await session.execute(
            select(
                PaymentModel.id,
                PaymentModel.provider,
                PaymentModel.status,
                PaymentModel.amount_cents,
                PaymentModel.currency,
            ).where(PaymentModel.order_id == order_id, PaymentModel.status.in_(REACHED_PAID))
        )
    ).first()
    if paid is None:
        return rows, None
    ledger = Ledger(
        total_cents,
        tuple(
            LineFact(line.id, line.product_type, line.fulfillment_status, line.line_total_cents)
            for line in lines
        ),
        PaymentFact(paid.id, paid.provider, paid.status, paid.amount_cents, paid.currency),
        tuple(_fact(row) for row in rows),
    )
    return rows, RefundBalances(line_balances(ledger), payment_balance(ledger))


async def customer_refunds(session: AsyncSession, order_id: UUID) -> list[CustomerRefund]:
    """Q9: admin, cancellation and late_capture refunds as processing or refunded; voided
    ones and chargebacks are never shown."""
    shown: list[CustomerRefund] = []
    for row in await order_refunds(session, order_id):
        if row.status is RefundStatus.VOIDED:
            continue
        if row.status is RefundStatus.FAILED and row.reissued_at is not None:
            continue  # its reissue is shown instead
        status: CustomerRefundStatus = (
            "refunded" if row.status is RefundStatus.SETTLED else "processing"
        )
        shown.append(
            CustomerRefund(row.kind, status, row.amount_cents, row.currency, row.created_at)
        )
    return shown
