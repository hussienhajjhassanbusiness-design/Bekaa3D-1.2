"""The customer's order history and order detail (VS-025; F-026, F-027)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from app.ordering.application.ports import (
    OfferCheckouts,
    OrderFilters,
    OrderHistoryStore,
    OrderPaymentReader,
    OrderPaymentView,
    PaymentAttemptRef,
)
from app.ordering.domain.customer_view import (
    can_cancel,
    can_retry_payment,
    customer_history,
    customer_lines,
    hold_expires_at,
    payment_due,
)
from app.ordering.domain.enums import OrderSource
from app.ordering.domain.exceptions import (
    OfferCheckoutExpiredError,
    OfferCheckoutNotFoundError,
    OfferNotCheckoutableError,
)
from app.ordering.domain.orders import CustomerOrder, CustomerOrderLine, HistoryEntry

_UNPAID = OrderPaymentView(reached_paid=False, shown=None)


@dataclass(frozen=True)
class OrderSummaryView:
    order: CustomerOrder
    payment_due: bool


@dataclass(frozen=True)
class OrderDetailView:
    order: CustomerOrder
    lines: list[CustomerOrderLine]
    history: list[HistoryEntry]
    payment: PaymentAttemptRef | None
    payment_due: bool
    can_cancel: bool
    can_retry_payment: bool
    hold_expires_at: datetime | None


@dataclass(frozen=True)
class RetryContext:
    """What `can_retry_payment` and `hold_expires_at` need beyond the order (VS-024, VS-041)."""

    offers: OfferCheckouts
    hold: timedelta
    now: datetime


async def list_orders(
    orders: OrderHistoryStore,
    payments: OrderPaymentReader,
    *,
    user_id: UUID,
    filters: OrderFilters,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[OrderSummaryView]:
    """One page, then one batched payment read for it."""
    page = await orders.page(user_id, filters, after=after, limit=limit)
    views = await payments.views([order.id for order in page])
    return [_summary(order, views.get(order.id, _UNPAID)) for order in page]


def _summary(order: CustomerOrder, view: OrderPaymentView) -> OrderSummaryView:
    due = payment_due(
        status=order.status, payment_method=order.payment_method, reached_paid=view.reached_paid
    )
    return OrderSummaryView(order=order, payment_due=due)


async def get_order(
    orders: OrderHistoryStore,
    payments: OrderPaymentReader,
    *,
    user_id: UUID,
    order_id: UUID,
    retry: RetryContext,
) -> OrderDetailView | None:
    """None for an unknown order and for another customer's alike."""
    order = await orders.get(user_id, order_id)
    if order is None:
        return None
    lines: Sequence[CustomerOrderLine] = await orders.lines(user_id, order_id)
    view = (await payments.views([order_id])).get(order_id, _UNPAID)
    return OrderDetailView(
        order=order,
        lines=customer_lines(lines),
        history=customer_history(await orders.history(user_id, order_id)),
        payment=view.shown,
        payment_due=_summary(order, view).payment_due,
        can_cancel=can_cancel(
            status=order.status,
            payment_method=order.payment_method,
            reached_paid=view.reached_paid,
            lines=lines,
        ),
        can_retry_payment=can_retry_payment(
            order,
            lines,
            attempt_status=view.shown.status if view.shown else None,
            offer_open=await _offer_open(retry, order, lines, user_id),
            now=retry.now,
            hold=retry.hold,
        ),
        hold_expires_at=hold_expires_at(
            order, latest_initiated_at=view.latest_initiated_at, hold=retry.hold
        ),
    )


async def _offer_open(
    retry: RetryContext,
    order: CustomerOrder,
    lines: Sequence[CustomerOrderLine],
    user_id: UUID,
) -> bool:
    """An offer order can take a new attempt only inside the offer's window (ADR-037)."""
    if order.source is not OrderSource.OFFER:
        return True
    try:
        for offer_id in {line.offer_id for line in lines if line.offer_id is not None}:
            await retry.offers.read(offer_id, user_id, now=retry.now)
    except (OfferCheckoutNotFoundError, OfferCheckoutExpiredError, OfferNotCheckoutableError):
        return False
    return True
