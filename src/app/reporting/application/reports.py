"""The six VS-043 reports. No `except` anywhere: a failed read propagates, so a report is an
error, never a body of zeros (FR-18, ADR-045 d1)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.reporting.application.ports import Sources
from app.reporting.domain.metrics import (
    BuyerStats,
    CustomerCounts,
    GroupBy,
    LineRevenue,
    OrderLabel,
    OrderRevenue,
    PaidPayment,
    PendingOffers,
    RatedProduct,
    RevenueReport,
    StlSale,
    StreamCents,
    buyer_stats,
    is_paid_line,
    local_day,
    order_revenue,
    report_window,
    stl_sales,
    stream_sum,
    summarise,
)


async def paid_line_revenue(
    sources: Sources, paid: Sequence[PaidPayment]
) -> tuple[list[LineRevenue], int]:
    """Every paid line of these payments' orders, with its refunds, and the unattributed excess.
    One paid payment per order (`uq_payments_one_live`), so `paid_on` keys by order."""
    paid_on = {payment.order_id: local_day(payment.verified_at) for payment in paid}
    lines = await sources.orders.lines(list(paid_on))
    line_ids = [line.id for line in lines]
    refunded = await sources.refunds.refunded_cents_by_line(line_ids)
    covered = await sources.refunds.covered_lines(line_ids)
    facts = [
        LineRevenue(line, paid_on[line.order_id], refunded.get(line.id, 0))
        for line in lines
        if is_paid_line(line, covered=line.id in covered)
    ]
    excess = await sources.payments.excess_cents([payment.id for payment in paid])
    return facts, excess


async def _facts_in(sources: Sources, start: date, end: date) -> tuple[list[LineRevenue], int]:
    lower, upper = report_window(start, end)
    return await paid_line_revenue(sources, await sources.payments.between(lower, upper))


async def revenue_report(
    sources: Sources, *, start: date, end: date, group_by: GroupBy
) -> RevenueReport:
    facts, excess = await _facts_in(sources, start, end)
    return summarise(facts, start=start, end=end, group_by=group_by, excess_cents=excess)


@dataclass(frozen=True)
class Overview:
    net: StreamCents
    paid_orders: int
    buyers: int
    new_customers: int
    pending_offers: PendingOffers
    stl_lines_awaiting_delivery: int


async def overview(sources: Sources, *, start: date, end: date) -> Overview:
    lower, upper = report_window(start, end)
    facts, _ = await paid_line_revenue(sources, await sources.payments.between(lower, upper))
    counts = await sources.customers.counts(lower, upper)
    offers = await sources.offers.live_counts()
    awaiting = await sources.orders.stl_awaiting_delivery()
    return Overview(
        net=stream_sum(facts, lambda fact: fact.net_cents),
        paid_orders=len({fact.line.order_id for fact in facts}),
        buyers=buyer_stats(facts).buyers,
        new_customers=counts.new_in_range,
        pending_offers=offers,
        stl_lines_awaiting_delivery=sum(awaiting.values()),
    )


@dataclass(frozen=True)
class CustomerStats:
    counts: CustomerCounts
    buyers: BuyerStats


async def customer_stats(sources: Sources, *, start: date, end: date) -> CustomerStats:
    lower, upper = report_window(start, end)
    facts, _ = await paid_line_revenue(sources, await sources.payments.between(lower, upper))
    return CustomerStats(await sources.customers.counts(lower, upper), buyer_stats(facts))


@dataclass(frozen=True)
class StlSaleRow:
    sale: StlSale
    name: str
    slug: str | None
    awaiting_delivery: int


@dataclass(frozen=True)
class StlSalesReport:
    items: list[StlSaleRow]
    stl_lines_awaiting_delivery: int


async def stl_sales_report(
    sources: Sources, *, start: date, end: date, limit: int
) -> StlSalesReport:
    facts, _ = await _facts_in(sources, start, end)
    sales = stl_sales(facts, limit=limit)
    labels = await sources.products.labels([sale.product_id for sale in sales])
    awaiting = await sources.orders.stl_awaiting_delivery()
    rows = []
    for sale in sales:
        label = labels.get(sale.product_id)
        rows.append(
            StlSaleRow(
                sale,
                label.name if label else sale.name_snapshot,
                label.slug if label else None,
                awaiting.get(sale.product_id, 0),
            )
        )
    return StlSalesReport(rows, sum(awaiting.values()))


@dataclass(frozen=True)
class RecentPurchase:
    payment: PaidPayment
    label: OrderLabel
    revenue: OrderRevenue


async def recent_purchases(
    sources: Sources, *, before: tuple[datetime, UUID] | None, limit: int
) -> tuple[list[RecentPurchase], bool]:
    """Newest verification first; the flag says another page exists."""
    page = await sources.payments.page(before=before, limit=limit + 1)
    more, page = len(page) > limit, page[:limit]
    facts, _ = await paid_line_revenue(sources, page)
    by_order = order_revenue(facts)
    labels = await sources.orders.labels([payment.order_id for payment in page])
    empty = OrderRevenue(StreamCents(0, 0), 0, 0, 0)
    items = [
        RecentPurchase(payment, labels[payment.order_id], by_order.get(payment.order_id, empty))
        for payment in page
    ]
    return items, more


async def top_rated(sources: Sources, *, limit: int, min_reviews: int) -> list[RatedProduct]:
    return await sources.products.top_rated(limit=limit, min_reviews=min_reviews)
