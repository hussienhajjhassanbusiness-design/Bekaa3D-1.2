"""Customer order history payloads (VS-025; api-endpoints.md `OrderDetail`). Fixed
schemas: no `admin_note`, provider reference, phone hash, actor or reason (plan Q7)."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from app.catalog.application.ports import ProductType
from app.catalog.public import PriceRead, media_url
from app.ordering.application.services.order_history import OrderDetailView, OrderSummaryView
from app.ordering.domain.enums import (
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)
from app.ordering.domain.fulfillment import DELIVERY_FEE_NOTE
from app.ordering.domain.orders import CustomerOrder, CustomerOrderLine, HistoryEntry


def _price(cents: int, currency: str) -> PriceRead:
    return PriceRead(amount_cents=cents, currency=currency)


class OrderSummaryRead(BaseModel):
    id: UUID
    order_number: str
    status: OrderStatus
    payment_method: PaymentMethod
    fulfillment_method: FulfillmentMethod | None
    payment_due: bool = Field(description="An unpaid cash order: pay the courier or at pickup.")
    amount_due: PriceRead | None = Field(description="While payment_due: the live total.")
    total: PriceRead
    placed_at: datetime

    @classmethod
    def of(cls, view: OrderSummaryView) -> Self:
        o = view.order
        return cls(
            id=o.id,
            order_number=o.order_number,
            status=o.status,
            payment_method=o.payment_method,
            fulfillment_method=o.fulfillment_method,
            payment_due=view.payment_due,
            amount_due=_price(o.live_total_cents, o.currency) if view.payment_due else None,
            total=_price(o.total_cents, o.currency),
            placed_at=o.placed_at,
        )


class OrderPage(BaseModel):
    items: list[OrderSummaryRead]
    next_cursor: str | None


class OrderLineRead(BaseModel):
    id: UUID
    product_id: UUID
    product_type: ProductType
    name: str = Field(description="The name at purchase; later catalogue edits never change it.")
    image_url: str | None
    unit_price: PriceRead
    quantity: int
    line_total: PriceRead
    fulfillment_status: OrderItemStatus = Field(
        description="Never `in_production`: a line being printed reads `pending`."
    )
    fulfilled_at: datetime | None = Field(description="STL: when the file was emailed.")
    cancelled_at: datetime | None

    @classmethod
    def of(cls, line: CustomerOrderLine, media_base_url: str) -> Self:
        image = line.image_snapshot
        return cls(
            id=line.id,
            product_id=line.product_id,
            product_type=line.product_type,
            name=line.product_name_snapshot,
            image_url=media_url(media_base_url, image) if image else None,
            unit_price=_price(line.unit_price_cents, line.currency),
            quantity=line.quantity,
            line_total=_price(line.line_total_cents, line.currency),
            fulfillment_status=line.fulfillment_status,
            fulfilled_at=line.fulfilled_at,
            cancelled_at=line.cancelled_at,
        )


class DeliveryAddressRead(BaseModel):
    recipient_name: str | None
    governorate: str | None
    city: str | None
    area: str | None
    street: str | None
    landmark_notes: str | None

    @classmethod
    def of(cls, o: CustomerOrder) -> Self | None:
        if o.fulfillment_method is not FulfillmentMethod.DELIVERY:
            return None
        return cls(
            recipient_name=o.recipient_name,
            governorate=o.governorate,
            city=o.city,
            area=o.area,
            street=o.street,
            landmark_notes=o.landmark_notes,
        )


class OrderPaymentRead(BaseModel):
    status: str
    provider: str
    amount: PriceRead


class StatusHistoryRead(BaseModel):
    order_item_id: UUID | None = Field(description="Null for the order's own status.")
    from_status: str | None
    to_status: str
    at: datetime

    @classmethod
    def of(cls, entry: HistoryEntry) -> Self:
        return cls(
            order_item_id=entry.order_item_id,
            from_status=entry.from_status,
            to_status=entry.to_status,
            at=entry.created_at,
        )


class OrderDetailRead(BaseModel):
    id: UUID
    order_number: str
    source: OrderSource
    status: OrderStatus
    fulfillment_method: FulfillmentMethod | None
    payment_method: PaymentMethod
    payment_due: bool
    amount_due: PriceRead | None = Field(description="While payment_due: the live total.")
    can_cancel: bool
    can_retry_payment: bool = Field(
        description="A new payment attempt may be started now; the POST re-checks."
    )
    hold_expires_at: datetime | None = Field(
        description="An unpaid online order: when it may be released if still unpaid."
    )
    subtotal: PriceRead
    tax: PriceRead
    total: PriceRead
    delivery_address: DeliveryAddressRead | None
    contact_phone: str | None
    delivery_fee_note: str | None
    estimated_dispatch_at: datetime | None = Field(description="The estimated ready date.")
    placed_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    customer_note: str | None
    lines: list[OrderLineRead]
    payment: OrderPaymentRead | None = Field(description="Null while a cash order is unpaid.")
    status_history: list[StatusHistoryRead] = Field(description="Oldest first.")

    @classmethod
    def of(cls, view: OrderDetailView, media_base_url: str) -> Self:
        o, paid = view.order, view.payment
        delivery = o.fulfillment_method is FulfillmentMethod.DELIVERY
        return cls(
            id=o.id,
            order_number=o.order_number,
            source=o.source,
            status=o.status,
            fulfillment_method=o.fulfillment_method,
            payment_method=o.payment_method,
            payment_due=view.payment_due,
            amount_due=_price(o.live_total_cents, o.currency) if view.payment_due else None,
            can_cancel=view.can_cancel,
            can_retry_payment=view.can_retry_payment,
            hold_expires_at=view.hold_expires_at,
            subtotal=_price(o.subtotal_cents, o.currency),
            tax=_price(o.tax_cents, o.currency),
            total=_price(o.total_cents, o.currency),
            delivery_address=DeliveryAddressRead.of(o),
            contact_phone=o.contact_phone_snapshot,
            delivery_fee_note=DELIVERY_FEE_NOTE if delivery else None,
            estimated_dispatch_at=o.estimated_dispatch_at,
            placed_at=o.placed_at,
            completed_at=o.completed_at,
            cancelled_at=o.cancelled_at,
            customer_note=o.customer_note,
            lines=[OrderLineRead.of(line, media_base_url) for line in view.lines],
            payment=OrderPaymentRead(
                status=paid.status,
                provider=paid.provider,
                amount=_price(paid.amount_cents, paid.currency),
            )
            if paid is not None
            else None,
            status_history=[StatusHistoryRead.of(entry) for entry in view.history],
        )
