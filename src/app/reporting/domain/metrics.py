"""The VS-043 metric definitions (api-endpoints 27.1, ADR-045). Pure: every row comes from a
context's reporting read, all taken in one snapshot by the caller."""

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

TIMEZONE: Final = "Asia/Beirut"
BEIRUT: Final = ZoneInfo(TIMEZONE)
CURRENCY: Final = "USD"
MAX_SPAN_DAYS: Final = 366
DEFAULT_SPAN_DAYS: Final = 30
EARLIEST: Final = date(2020, 1, 1)
LATEST: Final = date(2100, 12, 31)
# 27.1 item 7: a sold STL line is still owned; `refunded` and `cancelled` are not.
STL_SOLD: Final = frozenset({"awaiting_delivery", "delivered"})


class Stream(StrEnum):
    PHYSICAL = "physical"
    STL = "stl"


class GroupBy(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class RangeError(ValueError):
    """The router answers 400 INVALID_DATE_RANGE naming `field`."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class PaidPayment:
    id: UUID
    order_id: UUID
    verified_at: datetime


@dataclass(frozen=True)
class ReportLine:
    id: UUID
    order_id: UUID
    user_id: UUID
    product_id: UUID
    name_snapshot: str
    stream: Stream
    status: str
    quantity: int
    line_total_cents: int

    @property
    def cancelled(self) -> bool:
        return self.status == "cancelled"


@dataclass(frozen=True)
class LineRevenue:
    line: ReportLine
    paid_on: date
    refunded_cents: int

    @property
    def net_cents(self) -> int:
        return self.line.line_total_cents - self.refunded_cents


def is_paid_line(line: ReportLine, *, covered: bool) -> bool:
    """BR-149 on a paid order: a cancelled line is unpaid only when nothing counts against it
    (L2's bare cancel), so a chargeback-cancelled line stays paid and nets to 0 (ADR-045 d2)."""
    return not line.cancelled or covered


def report_window(start: date, end: date) -> tuple[datetime, datetime]:
    """Inclusive Beirut calendar days to a half-open UTC window [lower, upper)."""
    for field, day in (("from", start), ("to", end)):
        if not EARLIEST <= day <= LATEST:
            raise RangeError(field, f"must be between {EARLIEST} and {LATEST}")
    if end < start:
        raise RangeError("to", "must not be before from")
    if (end - start).days + 1 > MAX_SPAN_DAYS:
        raise RangeError("to", f"the range may span at most {MAX_SPAN_DAYS} days")
    lower = datetime.combine(start, time.min, BEIRUT)
    upper = datetime.combine(end + timedelta(days=1), time.min, BEIRUT)
    return lower.astimezone(UTC), upper.astimezone(UTC)


def default_range(start: date | None, end: date | None, *, now: datetime) -> tuple[date, date]:
    """`to` defaults to today in Beirut, `from` to 29 days before `to`."""
    last = end or local_day(now)
    if start is not None:
        return start, last
    try:
        return last - timedelta(days=DEFAULT_SPAN_DAYS - 1), last
    except OverflowError as exc:
        raise RangeError("to", f"must be between {EARLIEST} and {LATEST}") from exc


def local_day(moment: datetime) -> date:
    return moment.astimezone(BEIRUT).date()


def bucket_start(day: date, group_by: GroupBy) -> date:
    if group_by is GroupBy.WEEK:
        return day - timedelta(days=day.weekday())
    if group_by is GroupBy.MONTH:
        return day.replace(day=1)
    return day


def _next_bucket(first: date, group_by: GroupBy) -> date:
    if group_by is GroupBy.WEEK:
        return first + timedelta(days=7)
    if group_by is GroupBy.MONTH:
        return (first + timedelta(days=32)).replace(day=1)
    return first + timedelta(days=1)


def bucket_starts(start: date, end: date, group_by: GroupBy) -> list[date]:
    out, first = [], bucket_start(start, group_by)
    while first <= end:
        out.append(first)
        first = _next_bucket(first, group_by)
    return out


@dataclass(frozen=True)
class StreamCents:
    physical_cents: int
    stl_cents: int

    @property
    def total_cents(self) -> int:
        return self.physical_cents + self.stl_cents


def stream_sum(facts: Iterable[LineRevenue], cents: Callable[[LineRevenue], int]) -> StreamCents:
    by_stream = {Stream.PHYSICAL: 0, Stream.STL: 0}
    for fact in facts:
        by_stream[fact.line.stream] += cents(fact)
    return StreamCents(by_stream[Stream.PHYSICAL], by_stream[Stream.STL])


def _gross(fact: LineRevenue) -> int:
    return fact.line.line_total_cents


def _refunded(fact: LineRevenue) -> int:
    return fact.refunded_cents


def _net(fact: LineRevenue) -> int:
    return fact.net_cents


@dataclass(frozen=True)
class RevenueFigures:
    gross: StreamCents
    refunded: StreamCents
    net: StreamCents
    paid_lines: int
    paid_orders: int


def figures(facts: Sequence[LineRevenue]) -> RevenueFigures:
    return RevenueFigures(
        gross=stream_sum(facts, _gross),
        refunded=stream_sum(facts, _refunded),
        net=stream_sum(facts, _net),
        paid_lines=len(facts),
        paid_orders=len({fact.line.order_id for fact in facts}),
    )


@dataclass(frozen=True)
class RevenueBucket:
    start: date
    net: StreamCents


@dataclass(frozen=True)
class RevenueReport:
    start: date
    end: date
    group_by: GroupBy
    totals: RevenueFigures
    buckets: tuple[RevenueBucket, ...]
    excess_cents: int


def summarise(
    facts: Sequence[LineRevenue], *, start: date, end: date, group_by: GroupBy, excess_cents: int
) -> RevenueReport:
    """Every bucket from `start` to `end`, an empty one as 0; the first is clipped to `start`."""
    by_bucket: defaultdict[date, list[LineRevenue]] = defaultdict(list)
    for fact in facts:
        by_bucket[bucket_start(fact.paid_on, group_by)].append(fact)
    buckets = tuple(
        RevenueBucket(max(first, start), stream_sum(by_bucket.get(first, ()), _net))
        for first in bucket_starts(start, end, group_by)
    )
    return RevenueReport(start, end, group_by, figures(facts), buckets, excess_cents)


@dataclass(frozen=True)
class BuyerStats:
    buyers: int
    repeat_buyers: int
    net_per_buyer_cents: int | None


def buyer_stats(facts: Sequence[LineRevenue]) -> BuyerStats:
    orders: defaultdict[UUID, set[UUID]] = defaultdict(set)
    for fact in facts:
        orders[fact.line.user_id].add(fact.line.order_id)
    buyers = len(orders)
    repeat = sum(1 for placed in orders.values() if len(placed) >= 2)
    net = sum(fact.net_cents for fact in facts)
    return BuyerStats(buyers, repeat, net // buyers if buyers else None)


@dataclass(frozen=True)
class StlSale:
    product_id: UUID
    name_snapshot: str
    units: int
    lines: int
    net_cents: int


def stl_sales(facts: Sequence[LineRevenue], *, limit: int) -> list[StlSale]:
    """Paid STL lines still owned, by product: units, then net, then product id."""
    grouped: defaultdict[UUID, list[LineRevenue]] = defaultdict(list)
    for fact in facts:
        if fact.line.stream is Stream.STL and fact.line.status in STL_SOLD:
            grouped[fact.line.product_id].append(fact)
    sales = [
        StlSale(
            product_id,
            sold[0].line.name_snapshot,
            sum(fact.line.quantity for fact in sold),
            len(sold),
            sum(fact.net_cents for fact in sold),
        )
        for product_id, sold in grouped.items()
    ]
    sales.sort(key=lambda sale: (-sale.units, -sale.net_cents, str(sale.product_id)))
    return sales[:limit]


@dataclass(frozen=True)
class OrderRevenue:
    gross: StreamCents
    refunded_cents: int
    net_cents: int
    paid_lines: int


def order_revenue(facts: Sequence[LineRevenue]) -> dict[UUID, OrderRevenue]:
    grouped: defaultdict[UUID, list[LineRevenue]] = defaultdict(list)
    for fact in facts:
        grouped[fact.line.order_id].append(fact)
    return {
        order_id: OrderRevenue(
            stream_sum(lines, _gross),
            sum(fact.refunded_cents for fact in lines),
            sum(fact.net_cents for fact in lines),
            len(lines),
        )
        for order_id, lines in grouped.items()
    }


@dataclass(frozen=True)
class PendingOffers:
    awaiting_admin: int
    awaiting_customer: int
    accepted: int

    @property
    def total(self) -> int:
        return self.awaiting_admin + self.awaiting_customer + self.accepted


@dataclass(frozen=True)
class CustomerCounts:
    registered: int
    new_in_range: int


@dataclass(frozen=True)
class ProductLabel:
    name: str
    slug: str | None


@dataclass(frozen=True)
class RatedProduct:
    product_id: UUID
    name: str
    slug: str
    type: str
    average_rating: Decimal
    review_count: int
    is_visible: bool


@dataclass(frozen=True)
class OrderLabel:
    order_number: str
    payment_method: str
    user_id: UUID
