"""VS-043 metric definitions (api-endpoints 27.1): the paid-line rule, Beirut day windows with
both DST days, ranges, buckets and the aggregations (plan 6.1)."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.reporting.domain.metrics import (
    GroupBy,
    LineRevenue,
    RangeError,
    ReportLine,
    Stream,
    StreamCents,
    bucket_start,
    buyer_stats,
    default_range,
    is_paid_line,
    local_day,
    order_revenue,
    report_window,
    stl_sales,
    summarise,
)


def _line(
    *,
    stream: Stream = Stream.PHYSICAL,
    status: str = "delivered",
    total: int = 1000,
    order_id: UUID | None = None,
    user_id: UUID | None = None,
    product_id: UUID | None = None,
    quantity: int = 1,
) -> ReportLine:
    return ReportLine(
        uuid4(),
        order_id or uuid4(),
        user_id or uuid4(),
        product_id or uuid4(),
        "Snapshot",
        stream,
        status,
        quantity,
        total,
    )


def _fact(line: ReportLine, paid_on: date = date(2026, 10, 1), refunded: int = 0) -> LineRevenue:
    return LineRevenue(line, paid_on, refunded)


# --- the paid line (BR-149, ADR-045 d2) ------------------------------------------------------


def test_a_live_line_is_paid_whether_or_not_covered() -> None:
    assert is_paid_line(_line(), covered=False)
    assert is_paid_line(_line(), covered=True)


def test_a_cancelled_line_with_nothing_against_it_is_not_paid() -> None:
    assert not is_paid_line(_line(status="cancelled"), covered=False)


def test_a_cancelled_line_something_counts_against_stays_paid() -> None:
    """A chargeback-cancelled line (ADR-042 d17) carries its items: paid, netted to 0."""
    assert is_paid_line(_line(status="cancelled"), covered=True)


# --- windows, ranges, days -------------------------------------------------------------------


def test_one_october_day_is_21_00z_to_21_00z() -> None:
    lower, upper = report_window(date(2026, 10, 1), date(2026, 10, 1))
    assert (lower, upper) == (
        datetime(2026, 9, 30, 21, tzinfo=UTC),
        datetime(2026, 10, 1, 21, tzinfo=UTC),
    )


def test_the_spring_dst_day_lasts_23_hours() -> None:
    lower, upper = report_window(date(2026, 3, 29), date(2026, 3, 29))
    assert upper - lower == timedelta(hours=23)
    assert lower == datetime(2026, 3, 28, 22, tzinfo=UTC)


def test_the_autumn_dst_day_lasts_25_hours() -> None:
    """Lebanon falls back at Sunday 00:00 +03 to Saturday 23:00 +02: Saturday is the long day."""
    lower, upper = report_window(date(2026, 10, 24), date(2026, 10, 24))
    assert upper - lower == timedelta(hours=25)
    assert upper == datetime(2026, 10, 24, 22, tzinfo=UTC)
    sunday_lower, sunday_upper = report_window(date(2026, 10, 25), date(2026, 10, 25))
    assert sunday_upper - sunday_lower == timedelta(hours=24)
    assert sunday_lower == upper


def test_adjacent_windows_meet_across_both_dst_days() -> None:
    for day in (date(2026, 3, 28), date(2026, 3, 29), date(2026, 10, 24), date(2026, 10, 25)):
        after = day + timedelta(days=1)
        assert report_window(day, day)[1] == report_window(after, after)[0]


def test_local_day_puts_a_late_utc_evening_on_the_next_beirut_day() -> None:
    assert local_day(datetime(2026, 10, 1, 22, 30, tzinfo=UTC)) == date(2026, 10, 2)
    assert local_day(datetime(2026, 10, 1, 20, 59, tzinfo=UTC)) == date(2026, 10, 1)


def test_366_days_pass_and_367_fail_on_to() -> None:
    report_window(date(2025, 1, 1), date(2025, 1, 1) + timedelta(days=365))
    with pytest.raises(RangeError) as caught:
        report_window(date(2025, 1, 1), date(2025, 1, 1) + timedelta(days=366))
    assert caught.value.field == "to"


def test_to_before_from_fails_on_to() -> None:
    with pytest.raises(RangeError) as caught:
        report_window(date(2026, 10, 2), date(2026, 10, 1))
    assert caught.value.field == "to"


@pytest.mark.parametrize(
    ("start", "end", "field"),
    [
        (date(2019, 12, 31), date(2020, 1, 1), "from"),
        (date(2100, 12, 31), date(2101, 1, 1), "to"),
        (date.min, date(2020, 1, 1), "from"),
        (date(2100, 1, 1), date.max, "to"),
    ],
)
def test_a_year_outside_2020_2100_fails_on_its_field(start: date, end: date, field: str) -> None:
    with pytest.raises(RangeError) as caught:
        report_window(start, end)
    assert caught.value.field == field


def test_the_default_range_is_the_last_30_beirut_days() -> None:
    now = datetime(2026, 10, 26, 22, 30, tzinfo=UTC)  # already the 27th in Beirut
    assert default_range(None, None, now=now) == (date(2026, 9, 28), date(2026, 10, 27))
    assert default_range(None, date(2026, 1, 30), now=now) == (date(2026, 1, 1), date(2026, 1, 30))
    assert default_range(date(2026, 10, 1), None, now=now) == (
        date(2026, 10, 1),
        date(2026, 10, 27),
    )


def test_a_default_from_before_date_min_is_a_range_error() -> None:
    with pytest.raises(RangeError):
        default_range(None, date(1, 1, 2), now=datetime.now(UTC))


def test_bucket_start_for_day_week_and_month() -> None:
    sunday = date(2026, 10, 25)
    assert bucket_start(sunday, GroupBy.DAY) == sunday
    assert bucket_start(sunday, GroupBy.WEEK) == date(2026, 10, 19)
    assert bucket_start(date(2026, 10, 19), GroupBy.WEEK) == date(2026, 10, 19)
    assert bucket_start(sunday, GroupBy.MONTH) == date(2026, 10, 1)


# --- aggregations ----------------------------------------------------------------------------


def test_a_mixed_order_splits_by_stream() -> None:
    order = uuid4()
    facts = [
        _fact(_line(order_id=order, total=10_000)),
        _fact(_line(stream=Stream.STL, order_id=order, total=4_000)),
    ]
    report = summarise(
        facts,
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        group_by=GroupBy.DAY,
        excess_cents=0,
    )
    assert report.totals.gross == StreamCents(10_000, 4_000)
    assert report.totals.net.total_cents == 14_000
    assert (report.totals.paid_lines, report.totals.paid_orders) == (2, 1)


def test_buckets_are_zero_filled_and_the_first_is_clipped() -> None:
    facts = [_fact(_line(total=500), date(2026, 10, 7), 100)]
    report = summarise(
        facts,
        start=date(2026, 10, 1),
        end=date(2026, 10, 20),
        group_by=GroupBy.WEEK,
        excess_cents=0,
    )
    assert [bucket.start for bucket in report.buckets] == [
        date(2026, 10, 1),
        date(2026, 10, 5),
        date(2026, 10, 12),
        date(2026, 10, 19),
    ]
    assert [bucket.net.total_cents for bucket in report.buckets] == [0, 400, 0, 0]


def test_monthly_buckets_cross_a_year() -> None:
    report = summarise(
        [], start=date(2025, 12, 15), end=date(2026, 2, 1), group_by=GroupBy.MONTH, excess_cents=0
    )
    assert [bucket.start for bucket in report.buckets] == [
        date(2025, 12, 15),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]


def test_the_excess_is_carried_not_subtracted() -> None:
    facts = [_fact(_line(total=1000), refunded=1000)]
    report = summarise(
        facts,
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        group_by=GroupBy.DAY,
        excess_cents=300,
    )
    assert report.totals.net.total_cents == 0
    assert report.excess_cents == 300


def test_buyers_and_repeat_buyers_count_distinct_orders() -> None:
    alice, bob = uuid4(), uuid4()
    first, second = uuid4(), uuid4()
    facts = [
        _fact(_line(user_id=alice, order_id=first, total=1000)),
        _fact(_line(user_id=alice, order_id=first, total=1000)),
        _fact(_line(user_id=alice, order_id=second, total=1000)),
        _fact(_line(user_id=bob, total=1001)),
    ]
    stats = buyer_stats(facts)
    assert (stats.buyers, stats.repeat_buyers) == (2, 1)
    assert stats.net_per_buyer_cents == 4001 // 2


def test_no_buyers_gives_a_null_net_per_buyer() -> None:
    assert buyer_stats([]).net_per_buyer_cents is None


def test_stl_sales_keep_owned_lines_and_rank_by_units_then_net() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    facts = [
        _fact(_line(stream=Stream.STL, product_id=a, status="delivered", total=500)),
        _fact(
            _line(stream=Stream.STL, product_id=a, status="awaiting_delivery", total=500),
            refunded=200,
        ),
        _fact(_line(stream=Stream.STL, product_id=b, status="delivered", total=900, quantity=2)),
        _fact(_line(stream=Stream.STL, product_id=c, status="refunded", total=500), refunded=500),
        _fact(_line(stream=Stream.STL, product_id=c, status="cancelled", total=500), refunded=500),
        _fact(_line(stream=Stream.PHYSICAL, product_id=c, total=5000)),
    ]
    sales = stl_sales(facts, limit=10)
    assert [(s.product_id, s.units, s.lines, s.net_cents) for s in sales] == [
        (b, 2, 1, 900),
        (a, 2, 2, 800),
    ]
    assert len(stl_sales(facts, limit=1)) == 1


def test_order_revenue_sums_each_order() -> None:
    order = uuid4()
    facts = [
        _fact(_line(order_id=order, total=1000), refunded=250),
        _fact(_line(stream=Stream.STL, order_id=order, total=500)),
    ]
    found = order_revenue(facts)[order]
    assert (found.gross, found.refunded_cents, found.net_cents, found.paid_lines) == (
        StreamCents(1000, 500),
        250,
        1250,
        2,
    )
