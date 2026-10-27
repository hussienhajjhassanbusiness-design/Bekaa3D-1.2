"""VS-043 report services over fake ports (plan 6.1): the port order, failures propagating from
every port of every report (never zeros), STL labels and customer statistics."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.reporting.application import reports
from app.reporting.application.ports import Sources
from app.reporting.domain.metrics import (
    CustomerCounts,
    GroupBy,
    OrderLabel,
    PaidPayment,
    PendingOffers,
    ProductLabel,
    RatedProduct,
    ReportLine,
    Stream,
)

DAY = date(2026, 10, 1)
AT = datetime(2026, 10, 1, 9, tzinfo=UTC)


class BoomError(RuntimeError):
    pass


class Fakes:
    """All six ports at once, recording calls; `fail` names the method that raises."""

    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail = fail
        self.user = uuid4()
        self.order = uuid4()
        self.stl_product = uuid4()
        self.payment = PaidPayment(uuid4(), self.order, AT)
        self.physical = ReportLine(
            uuid4(), self.order, self.user, uuid4(), "Lamp", Stream.PHYSICAL, "delivered", 1, 1000
        )
        self.stl = ReportLine(
            uuid4(),
            self.order,
            self.user,
            self.stl_product,
            "Old name",
            Stream.STL,
            "awaiting_delivery",
            1,
            500,
        )
        self.cancelled = ReportLine(
            uuid4(), self.order, self.user, uuid4(), "Vase", Stream.PHYSICAL, "cancelled", 1, 700
        )

    def _hit(self, name: str) -> None:
        self.calls.append(name)
        if name == self.fail:
            raise BoomError(name)

    async def between(self, lower: datetime, upper: datetime) -> list[PaidPayment]:
        self._hit("between")
        return [self.payment]

    async def page(self, *, before: tuple[datetime, UUID] | None, limit: int) -> list[PaidPayment]:
        self._hit("page")
        return [self.payment]

    async def excess_cents(self, payment_ids: Sequence[UUID]) -> int:
        self._hit("excess_cents")
        return 0

    async def refunded_cents_by_line(self, line_ids: Sequence[UUID]) -> dict[UUID, int]:
        self._hit("refunded_cents_by_line")
        return {self.physical.id: 250}

    async def covered_lines(self, line_ids: Sequence[UUID]) -> frozenset[UUID]:
        self._hit("covered_lines")
        return frozenset({self.physical.id})

    async def lines(self, order_ids: Sequence[UUID]) -> list[ReportLine]:
        self._hit("lines")
        return [self.physical, self.stl, self.cancelled]

    async def labels(self, ids: Sequence[UUID]) -> Any:
        self._hit("labels")
        if self.order in ids:
            return {self.order: OrderLabel("B3D-1", "online", self.user)}
        return {self.stl_product: ProductLabel("New name", "new-name")}

    async def stl_awaiting_delivery(self) -> dict[UUID, int]:
        self._hit("stl_awaiting_delivery")
        return {self.stl_product: 3, uuid4(): 2}

    async def live_counts(self) -> PendingOffers:
        self._hit("live_counts")
        return PendingOffers(1, 2, 3)

    async def top_rated(self, *, limit: int, min_reviews: int) -> list[RatedProduct]:
        self._hit("top_rated")
        return [RatedProduct(uuid4(), "Best", "best", "stl", Decimal("4.50"), 4, True)]

    async def counts(self, created_from: datetime, created_to: datetime) -> CustomerCounts:
        self._hit("counts")
        return CustomerCounts(10, 2)

    def sources(self) -> Sources:
        return Sources(self, self, self, self, self, self)


REPORTS: dict[str, Any] = {
    "revenue": lambda s: reports.revenue_report(s, start=DAY, end=DAY, group_by=GroupBy.DAY),
    "overview": lambda s: reports.overview(s, start=DAY, end=DAY),
    "customers": lambda s: reports.customer_stats(s, start=DAY, end=DAY),
    "stl_sales": lambda s: reports.stl_sales_report(s, start=DAY, end=DAY, limit=5),
    "recent": lambda s: reports.recent_purchases(s, before=None, limit=5),
    "top_rated": lambda s: reports.top_rated(s, limit=5, min_reviews=1),
}


async def _ports_used(name: str) -> list[str]:
    fakes = Fakes()
    await REPORTS[name](fakes.sources())
    return fakes.calls


async def test_revenue_reads_the_ports_in_order_and_nothing_else() -> None:
    assert await _ports_used("revenue") == [
        "between",
        "lines",
        "refunded_cents_by_line",
        "covered_lines",
        "excess_cents",
    ]


async def test_revenue_drops_a_bare_cancelled_line_and_subtracts_refunds() -> None:
    fakes = Fakes()
    found = await reports.revenue_report(fakes.sources(), start=DAY, end=DAY, group_by=GroupBy.DAY)
    assert found.totals.gross.physical_cents == 1000  # the bare cancelled 700 is not a paid line
    assert (found.totals.net.physical_cents, found.totals.net.stl_cents) == (750, 500)


@pytest.mark.parametrize("report", sorted(REPORTS))
async def test_every_port_failure_propagates_from_every_report(report: str) -> None:
    """FR-18: a failed read is an error, never a body of zeros."""
    for port in await _ports_used(report):
        fakes = Fakes(fail=port)
        with pytest.raises(BoomError):
            await REPORTS[report](fakes.sources())


async def test_stl_sales_use_todays_label_and_the_awaiting_counts() -> None:
    fakes = Fakes()
    found = await reports.stl_sales_report(fakes.sources(), start=DAY, end=DAY, limit=5)
    [row] = found.items
    assert (row.name, row.slug, row.awaiting_delivery) == ("New name", "new-name", 3)
    assert found.stl_lines_awaiting_delivery == 5


async def test_stl_sales_fall_back_to_the_snapshot_name() -> None:
    fakes = Fakes()

    async def no_labels(ids: Sequence[UUID]) -> dict[UUID, ProductLabel]:
        return {}

    unlabelled = type("Unlabelled", (), {"labels": staticmethod(no_labels)})()
    sources = replace(fakes.sources(), products=unlabelled)
    found = await reports.stl_sales_report(sources, start=DAY, end=DAY, limit=5)
    assert (found.items[0].name, found.items[0].slug) == ("Old name", None)


async def test_customer_stats_count_buyers_and_net_per_buyer() -> None:
    found = await reports.customer_stats(Fakes().sources(), start=DAY, end=DAY)
    assert (found.counts.registered, found.counts.new_in_range) == (10, 2)
    assert (found.buyers.buyers, found.buyers.repeat_buyers) == (1, 0)
    assert found.buyers.net_per_buyer_cents == 1250


async def test_overview_carries_offers_and_the_awaiting_total() -> None:
    found = await reports.overview(Fakes().sources(), start=DAY, end=DAY)
    assert found.pending_offers.total == 6
    assert (found.paid_orders, found.buyers, found.new_customers) == (1, 1, 2)
    assert found.stl_lines_awaiting_delivery == 5


async def test_recent_purchases_ask_one_more_than_the_page() -> None:
    fakes = Fakes()
    items, more = await reports.recent_purchases(fakes.sources(), before=None, limit=1)
    assert not more
    assert items[0].revenue.net_cents == 1250
    assert items[0].label.order_number == "B3D-1"


async def test_a_bad_range_raises_before_any_port_is_read() -> None:
    fakes = Fakes()
    with pytest.raises(ValueError):
        await reports.revenue_report(
            fakes.sources(), start=date(2026, 10, 2), end=DAY, group_by=GroupBy.DAY
        )
    assert fakes.calls == []
