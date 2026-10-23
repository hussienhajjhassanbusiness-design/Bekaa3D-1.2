"""The administrator's view of orders (VS-029; SRS 8.7, 15.2). Unlike `CustomerOrder` it
keeps the internal note, the customer, the real line states and who changed them."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import (
    CancelReason,
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)


@dataclass(frozen=True)
class AdminOrderFilters:
    status: OrderStatus | None = None
    fulfillment_method: FulfillmentMethod | None = None
    payment_method: PaymentMethod | None = None
    payment_due: bool | None = None
    customer_id: UUID | None = None
    order_number: str | None = None
    placed_after: datetime | None = None
    placed_before: datetime | None = None


@dataclass(frozen=True)
class AdminOrder:
    id: UUID
    order_number: str
    user_id: UUID
    customer_email_snapshot: str
    source: OrderSource
    status: OrderStatus
    fulfillment_method: FulfillmentMethod | None
    payment_method: PaymentMethod
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency: str
    recipient_name: str | None
    contact_phone_snapshot: str | None
    governorate: str | None
    city: str | None
    area: str | None
    street: str | None
    landmark_notes: str | None
    customer_note: str | None
    admin_note: str | None
    estimated_dispatch_at: datetime | None
    placed_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    live_total_cents: int


@dataclass(frozen=True)
class AdminOrderLine:
    id: UUID
    product_id: UUID
    product_type: ProductType
    product_name_snapshot: str
    image_snapshot: str | None
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    currency: str
    fulfillment_status: OrderItemStatus
    fulfilled_at: datetime | None
    delivered_by: UUID | None
    cancelled_at: datetime | None
    cancel_reason: CancelReason | None
    offer_id: UUID | None
    lead_time_days_snapshot: int | None
    batch_size_snapshot: int | None
    receipt_confirmed_at: datetime | None
    problem_reported_at: datetime | None


@dataclass(frozen=True)
class AdminHistoryEntry:
    order_item_id: UUID | None
    from_status: str | None
    to_status: str
    actor_user_id: UUID | None
    reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class CashBlock:
    """A cash payment block as an administrator sees it: never the phone or its hash."""

    id: UUID
    user_id: UUID
    order_id: UUID
    order_number: str
    reason: CancelReason
    created_at: datetime
    cleared_at: datetime | None
    cleared_by: UUID | None


def cash_due(status: OrderStatus, payment_method: PaymentMethod) -> bool:
    """The "cash due" view (SRS 8.7); `ix_orders_cash_due` has the same predicate."""
    return payment_method is PaymentMethod.CASH and status is OrderStatus.IN_PROGRESS
