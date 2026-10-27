"""VS-043 admin business analytics (api-endpoints 27, 27.1; ADR-045). GET only, behind the admin
boundary, with a 30/min per-administrator limit on top of the router's 300. Reads are not
audited: no response carries personal data (plan Q7)."""

import base64
import binascii
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApiError
from app.core.rate_limit import enforce_rate_limit
from app.identity.public import AccessTokenClaims, AdminBoundaryRoute, require_admin
from app.reporting.api.schemas import (
    AnalyticsOverview,
    CustomerAnalytics,
    PendingOfferCounts,
    RecentPurchase,
    RecentPurchasePage,
    RevenueAnalytics,
    RevenueBucket,
    RevenueFigures,
    StlSalesAnalytics,
    StlSalesItem,
    StreamCentsRead,
    TopRatedProduct,
    TopRatedProductList,
)
from app.reporting.api.session import report_session
from app.reporting.application import reports
from app.reporting.domain.metrics import (
    CURRENCY,
    TIMEZONE,
    GroupBy,
    RangeError,
    default_range,
)
from app.reporting.infrastructure.adapters import sql_sources

ANALYTICS_RATE_LIMIT: Final = 30
ANALYTICS_RATE_WINDOW_SECONDS: Final = 60
_DEFAULT_LIMIT, _MAX_LIMIT = 20, 100


async def analytics_rate_limit(
    request: Request, response: Response, claims: AccessTokenClaims = Depends(require_admin)
) -> None:
    """After the boundary, as `admin_rate_limit`: a non-administrator never spends it."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="admin_analytics",
        subject=str(claims.user_id),
        limit=ANALYTICS_RATE_LIMIT,
        window_seconds=ANALYTICS_RATE_WINDOW_SECONDS,
    )


admin_router = APIRouter(
    prefix="/analytics",
    tags=["admin"],
    route_class=AdminBoundaryRoute,
    dependencies=[Depends(analytics_rate_limit)],
)

_BASE: dict[int | str, dict[str, Any]] = {
    401: {"description": "No session, or MFA not completed."},
    404: {"description": "Caller is not an administrator."},
    422: {"description": "A parameter that cannot be parsed, or out of its bounds."},
    429: {"description": "The admin or the analytics rate limit."},
    503: {"description": "A query failed or timed out; never a body of zeros."},
}
_RANGED = _BASE | {
    400: {
        "description": "`INVALID_DATE_RANGE`: `to` before `from`, over 366 days, or a year "
        "outside 2020-2100."
    }
}

FromDate = Query(
    default=None, alias="from", description="Inclusive Beirut date; default 29 days before `to`."
)
ToDate = Query(default=None, description="Inclusive Beirut date; default today in Beirut.")
Limit = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)


def _range_error(error: RangeError) -> ApiError:
    return ApiError(
        status_code=400,
        code="INVALID_DATE_RANGE",
        title="Invalid date range",
        detail=str(error),
        errors=[{"loc": ["query", error.field], "msg": str(error), "type": "value_error"}],
    )


async def _ranged[T](
    from_: date | None, to: date | None, report: Callable[[date, date], Awaitable[T]]
) -> tuple[date, date, T]:
    try:
        start, end = default_range(from_, to, now=datetime.now(UTC))
        return start, end, await report(start, end)
    except RangeError as error:
        raise _range_error(error) from error


def _labels(start: date, end: date) -> dict[str, Any]:
    return {"from_": start, "to": end, "timezone": TIMEZONE, "currency": CURRENCY}


@admin_router.get(
    "/revenue",
    response_model=RevenueAnalytics,
    summary="Revenue by stream, attributed per line (27.1)",
    responses=_RANGED,
)
async def revenue(
    from_: date | None = FromDate,
    to: date | None = ToDate,
    group_by: GroupBy = Query(default=GroupBy.DAY),
    session: AsyncSession = Depends(report_session, scope="function"),
) -> RevenueAnalytics:
    sources = sql_sources(session)
    start, end, found = await _ranged(
        from_,
        to,
        lambda s, e: reports.revenue_report(sources, start=s, end=e, group_by=group_by),
    )
    totals = found.totals
    return RevenueAnalytics(
        **_labels(start, end),
        group_by=group_by,
        totals=RevenueFigures(
            gross=StreamCentsRead.of(totals.gross),
            refunded=StreamCentsRead.of(totals.refunded),
            net=StreamCentsRead.of(totals.net),
            paid_lines=totals.paid_lines,
            paid_orders=totals.paid_orders,
        ),
        buckets=[
            RevenueBucket(start=bucket.start, net=StreamCentsRead.of(bucket.net))
            for bucket in found.buckets
        ],
        unattributed_chargeback_excess_cents=found.excess_cents,
    )


@admin_router.get(
    "/overview",
    response_model=AnalyticsOverview,
    summary="Net revenue, orders and customers in the range; pending offers now",
    responses=_RANGED,
)
async def overview(
    from_: date | None = FromDate,
    to: date | None = ToDate,
    session: AsyncSession = Depends(report_session, scope="function"),
) -> AnalyticsOverview:
    sources = sql_sources(session)
    start, end, found = await _ranged(
        from_, to, lambda s, e: reports.overview(sources, start=s, end=e)
    )
    offers = found.pending_offers
    return AnalyticsOverview(
        **_labels(start, end),
        net=StreamCentsRead.of(found.net),
        paid_orders=found.paid_orders,
        buyers=found.buyers,
        new_customers=found.new_customers,
        pending_offers=PendingOfferCounts(
            awaiting_admin=offers.awaiting_admin,
            awaiting_customer=offers.awaiting_customer,
            accepted=offers.accepted,
            total=offers.total,
        ),
        stl_lines_awaiting_delivery=found.stl_lines_awaiting_delivery,
    )


@admin_router.get(
    "/customers",
    response_model=CustomerAnalytics,
    summary="Customer statistics (27.1 item 8)",
    responses=_RANGED,
)
async def customers(
    from_: date | None = FromDate,
    to: date | None = ToDate,
    session: AsyncSession = Depends(report_session, scope="function"),
) -> CustomerAnalytics:
    sources = sql_sources(session)
    start, end, found = await _ranged(
        from_, to, lambda s, e: reports.customer_stats(sources, start=s, end=e)
    )
    return CustomerAnalytics(
        **_labels(start, end),
        registered_customers=found.counts.registered,
        new_customers=found.counts.new_in_range,
        buyers=found.buyers.buyers,
        repeat_buyers=found.buyers.repeat_buyers,
        net_per_buyer_cents=found.buyers.net_per_buyer_cents,
    )


@admin_router.get(
    "/stl-sales",
    response_model=StlSalesAnalytics,
    summary="Best-selling STLs from paid, unrefunded lines (27.1 item 7)",
    responses=_RANGED,
)
async def stl_sales(
    from_: date | None = FromDate,
    to: date | None = ToDate,
    limit: int = Limit,
    session: AsyncSession = Depends(report_session, scope="function"),
) -> StlSalesAnalytics:
    sources = sql_sources(session)
    start, end, found = await _ranged(
        from_, to, lambda s, e: reports.stl_sales_report(sources, start=s, end=e, limit=limit)
    )
    return StlSalesAnalytics(
        **_labels(start, end),
        items=[
            StlSalesItem(
                product_id=row.sale.product_id,
                name=row.name,
                slug=row.slug,
                units=row.sale.units,
                lines=row.sale.lines,
                net_cents=row.sale.net_cents,
                awaiting_delivery=row.awaiting_delivery,
            )
            for row in found.items
        ],
        stl_lines_awaiting_delivery=found.stl_lines_awaiting_delivery,
    )


@admin_router.get(
    "/top-rated-products",
    response_model=TopRatedProductList,
    summary="Top rated products by the maintained aggregates",
    responses=_BASE,
)
async def top_rated_products(
    limit: int = Limit,
    min_reviews: int = Query(default=3, ge=1, le=1000),
    session: AsyncSession = Depends(report_session, scope="function"),
) -> TopRatedProductList:
    found = await reports.top_rated(sql_sources(session), limit=limit, min_reviews=min_reviews)
    return TopRatedProductList(
        items=[
            TopRatedProduct(
                product_id=row.product_id,
                name=row.name,
                slug=row.slug,
                type=row.type,
                average_rating=row.average_rating,
                review_count=row.review_count,
                is_visible=row.is_visible,
            )
            for row in found
        ]
    )


_SEPARATOR = "|"


def _encode_cursor(verified_at: datetime, payment_id: UUID) -> str:
    raw = f"{verified_at.isoformat()}{_SEPARATOR}{payment_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(raw: str | None) -> tuple[datetime, UUID] | None:
    if raw is None:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
        at_raw, id_raw = decoded.split(_SEPARATOR)
        at, payment_id = datetime.fromisoformat(at_raw), UUID(id_raw)
        if at.tzinfo is None:
            raise ValueError("naive")
        at.astimezone(UTC)
    except (ValueError, OverflowError, binascii.Error) as exc:
        raise RequestValidationError(
            [{"loc": ("query", "cursor"), "msg": "not a valid cursor", "type": "value_error"}]
        ) from exc
    return at, payment_id


@admin_router.get(
    "/recent-purchases",
    response_model=RecentPurchasePage,
    summary="Paid payments, newest verification first (27.1 item 6)",
    responses=_BASE,
)
async def recent_purchases(
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Limit,
    session: AsyncSession = Depends(report_session, scope="function"),
) -> RecentPurchasePage:
    before = _decode_cursor(cursor)
    items, more = await reports.recent_purchases(sql_sources(session), before=before, limit=limit)
    last = items[-1].payment if more and items else None
    return RecentPurchasePage(
        items=[
            RecentPurchase(
                order_id=item.payment.order_id,
                order_number=item.label.order_number,
                user_id=item.label.user_id,
                paid_at=item.payment.verified_at,
                payment_method=item.label.payment_method,
                gross=StreamCentsRead.of(item.revenue.gross),
                refunded_cents=item.revenue.refunded_cents,
                net_cents=item.revenue.net_cents,
                paid_lines=item.revenue.paid_lines,
            )
            for item in items
        ],
        next_cursor=_encode_cursor(last.verified_at, last.id) if last else None,
    )
