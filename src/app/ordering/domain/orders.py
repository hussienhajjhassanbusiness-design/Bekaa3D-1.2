"""Order entities (VS-023 plan 3.1). Pure: rows come in and out through Ordering's ports."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.enums import (
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)


@dataclass(frozen=True)
class NewOrderLine:
    """A line priced from the live product, never from the cart snapshot (ADR-029 d3)."""

    product_id: UUID
    product_type: ProductType
    product_name_snapshot: str
    image_snapshot: str | None
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    currency: str
    offer_id: UUID | None = None
    lead_time_days_snapshot: int | None = None
    batch_size_snapshot: int | None = None


@dataclass(frozen=True)
class NewOrder:
    order_number: str
    user_id: UUID
    customer_email_snapshot: str
    source: OrderSource
    status: OrderStatus
    payment_method: PaymentMethod
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency: str
    customer_note: str | None
    terms_accepted_at: datetime
    digital_terms_accepted_at: datetime | None
    digital_terms_version: str | None
    placed_at: datetime
    fulfillment_method: FulfillmentMethod | None = None
    recipient_name: str | None = None
    contact_phone_snapshot: str | None = None
    contact_phone_hash: str | None = None
    governorate: str | None = None
    city: str | None = None
    area: str | None = None
    street: str | None = None
    landmark_notes: str | None = None
    estimated_dispatch_at: datetime | None = None
    cash_terms_accepted_at: datetime | None = None


@dataclass(frozen=True)
class Order:
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
    placed_at: datetime
    cancelled_at: datetime | None
    estimated_dispatch_at: datetime | None = None
    recipient_name: str | None = None
    governorate: str | None = None
    city: str | None = None
    area: str | None = None
    street: str | None = None
    landmark_notes: str | None = None


@dataclass(frozen=True)
class OrderLine:
    id: UUID
    order_id: UUID
    user_id: UUID
    product_id: UUID
    product_type: ProductType
    product_name_snapshot: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int
    currency: str
    fulfillment_status: OrderItemStatus
    offer_id: UUID | None = None
    fulfilled_at: datetime | None = None
    delivered_by: UUID | None = None


@dataclass(frozen=True)
class StlDeliveryRow:
    """One admin queue row: an STL line awaiting delivery, with its order's contact."""

    item_id: UUID
    order_id: UUID
    order_number: str
    product_id: UUID
    product_name: str
    customer_id: UUID
    customer_email: str
    line_total_cents: int
    currency: str
    queued_at: datetime


@dataclass(frozen=True)
class StatusChange:
    """One `order_status_history` row; `order_item_id` None means the order projection."""

    order_id: UUID
    from_status: str | None
    to_status: str
    order_item_id: UUID | None = None
    actor_user_id: UUID | None = None
    reason: str | None = None


@dataclass(frozen=True)
class CustomerOrder:
    """An order as its customer may read it (VS-025): no `admin_note`, phone hash or email."""

    id: UUID
    order_number: str
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
    estimated_dispatch_at: datetime | None
    placed_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    live_total_cents: int = 0


@dataclass(frozen=True)
class CustomerOrderLine:
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
    cancelled_at: datetime | None
    offer_id: UUID | None = None
    receipt_confirmed_at: datetime | None = None
    problem_reported_at: datetime | None = None


@dataclass(frozen=True)
class HistoryEntry:
    """One customer-visible `order_status_history` row: no actor and no reason."""

    order_item_id: UUID | None
    from_status: str | None
    to_status: str
    created_at: datetime
