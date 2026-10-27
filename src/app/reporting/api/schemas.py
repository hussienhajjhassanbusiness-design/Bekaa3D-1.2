"""VS-043 response bodies (api-endpoints 30, "Admin analytics"). Integer cents, one currency per
body; no email, name, phone or address anywhere (ADR-045 d7)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.reporting.domain.metrics import GroupBy, StreamCents


class StreamCentsRead(BaseModel):
    physical_cents: int
    stl_cents: int
    total_cents: int

    @classmethod
    def of(cls, cents: StreamCents) -> "StreamCentsRead":
        return cls(
            physical_cents=cents.physical_cents,
            stl_cents=cents.stl_cents,
            total_cents=cents.total_cents,
        )


class _Ranged(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: date = Field(alias="from")
    to: date
    timezone: str
    currency: str


class RevenueFigures(BaseModel):
    gross: StreamCentsRead
    refunded: StreamCentsRead
    net: StreamCentsRead
    paid_lines: int
    paid_orders: int


class RevenueBucket(BaseModel):
    start: date
    net: StreamCentsRead


class RevenueAnalytics(_Ranged):
    group_by: GroupBy
    totals: RevenueFigures
    buckets: list[RevenueBucket]
    unattributed_chargeback_excess_cents: int


class PendingOfferCounts(BaseModel):
    awaiting_admin: int
    awaiting_customer: int
    accepted: int
    total: int


class AnalyticsOverview(_Ranged):
    net: StreamCentsRead
    paid_orders: int
    buyers: int
    new_customers: int
    pending_offers: PendingOfferCounts
    stl_lines_awaiting_delivery: int


class CustomerAnalytics(_Ranged):
    registered_customers: int
    new_customers: int
    buyers: int
    repeat_buyers: int
    net_per_buyer_cents: int | None


class StlSalesItem(BaseModel):
    product_id: UUID
    name: str
    slug: str | None
    units: int
    lines: int
    net_cents: int
    awaiting_delivery: int


class StlSalesAnalytics(_Ranged):
    items: list[StlSalesItem]
    stl_lines_awaiting_delivery: int


class TopRatedProduct(BaseModel):
    product_id: UUID
    name: str
    slug: str
    type: Literal["physical", "stl"]
    average_rating: Decimal
    review_count: int
    is_visible: bool


class TopRatedProductList(BaseModel):
    items: list[TopRatedProduct]


class RecentPurchase(BaseModel):
    order_id: UUID
    order_number: str
    user_id: UUID
    paid_at: datetime
    payment_method: Literal["online", "cash"]
    gross: StreamCentsRead
    refunded_cents: int
    net_cents: int
    paid_lines: int


class RecentPurchasePage(BaseModel):
    items: list[RecentPurchase]
    next_cursor: str | None
