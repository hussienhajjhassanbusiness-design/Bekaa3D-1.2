"""Admin order payloads (VS-029; api-endpoints.md `AdminOrderDetail`, ADR-025). Admin only:
the internal note, real line states and actors appear here and in no customer schema."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.api.text import MultilineStr
from app.catalog.application.ports import ProductType
from app.catalog.public import PriceRead, media_url
from app.fulfillment.application.admin_order_detail import AdminOrderView, LineWithActions
from app.fulfillment.domain import limits
from app.ordering.public import (
    DELIVERY_FEE_NOTE,
    AdminHistoryEntry,
    AdminOrder,
    CancelReason,
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
    cash_due,
)
from app.payments.public import OrderPaymentRow


def _price(cents: int, currency: str) -> PriceRead:
    return PriceRead(amount_cents=cents, currency=currency)


class AdminOrderSummaryRead(BaseModel):
    id: UUID
    order_number: str
    customer_id: UUID
    customer_email: str
    status: OrderStatus
    fulfillment_method: FulfillmentMethod | None
    payment_method: PaymentMethod
    payment_due: bool = Field(description="An unpaid cash order: the 'cash due' view.")
    amount_due: PriceRead | None = Field(description="While payment_due: the live total.")
    total: PriceRead
    estimated_dispatch_at: datetime | None
    placed_at: datetime

    @classmethod
    def of(cls, o: AdminOrder) -> Self:
        due = cash_due(o.status, o.payment_method)
        return cls(
            id=o.id,
            order_number=o.order_number,
            customer_id=o.user_id,
            customer_email=o.customer_email_snapshot,
            status=o.status,
            fulfillment_method=o.fulfillment_method,
            payment_method=o.payment_method,
            payment_due=due,
            amount_due=_price(o.live_total_cents, o.currency) if due else None,
            total=_price(o.total_cents, o.currency),
            estimated_dispatch_at=o.estimated_dispatch_at,
            placed_at=o.placed_at,
        )


class AdminOrderPage(BaseModel):
    items: list[AdminOrderSummaryRead]
    next_cursor: str | None


class AvailableActionRead(BaseModel):
    target_status: OrderItemStatus
    cancel_reasons: list[CancelReason] = Field(
        description="Empty: the transition takes no reason. Always empty until VS-031."
    )


class AdminOrderLineRead(BaseModel):
    id: UUID
    product_id: UUID
    product_type: ProductType
    name: str
    image_url: str | None
    unit_price: PriceRead
    quantity: int
    line_total: PriceRead
    fulfillment_status: OrderItemStatus = Field(description="The real state, never masked.")
    fulfilled_at: datetime | None
    delivered_by: UUID | None
    cancelled_at: datetime | None
    cancel_reason: CancelReason | None
    offer_id: UUID | None
    lead_time_days: int | None
    batch_size: int | None
    receipt_confirmed_at: datetime | None
    problem_reported_at: datetime | None
    available_actions: list[AvailableActionRead] = Field(
        description="What the transition endpoint accepts now; it re-checks (ADR-025)."
    )

    @classmethod
    def of(cls, item: LineWithActions, media_base_url: str) -> Self:
        line = item.line
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
            delivered_by=line.delivered_by,
            cancelled_at=line.cancelled_at,
            cancel_reason=line.cancel_reason,
            offer_id=line.offer_id,
            lead_time_days=line.lead_time_days_snapshot,
            batch_size=line.batch_size_snapshot,
            receipt_confirmed_at=line.receipt_confirmed_at,
            problem_reported_at=line.problem_reported_at,
            available_actions=[
                AvailableActionRead(target_status=target, cancel_reasons=[])
                for target in item.available
            ],
        )


class AdminDeliveryAddressRead(BaseModel):
    recipient_name: str | None
    governorate: str | None
    city: str | None
    area: str | None
    street: str | None
    landmark_notes: str | None


class AdminOrderPaymentRead(BaseModel):
    id: UUID
    provider: str
    status: str
    amount: PriceRead
    initiated_at: datetime
    verified_at: datetime | None
    late_captured_at: datetime | None
    recorded_by: UUID | None = Field(description="Cash: the administrator who recorded it.")

    @classmethod
    def of(cls, p: OrderPaymentRow) -> Self:
        return cls(
            id=p.id,
            provider=p.provider,
            status=p.status,
            amount=_price(p.amount_cents, p.currency),
            initiated_at=p.initiated_at,
            verified_at=p.verified_at,
            late_captured_at=p.late_captured_at,
            recorded_by=p.recorded_by,
        )


class AdminHistoryRead(BaseModel):
    order_item_id: UUID | None = Field(description="Null for the order's own status.")
    from_status: str | None
    to_status: str
    actor_user_id: UUID | None = Field(description="Null: the system.")
    reason: str | None
    at: datetime

    @classmethod
    def of(cls, h: AdminHistoryEntry) -> Self:
        return cls(
            order_item_id=h.order_item_id,
            from_status=h.from_status,
            to_status=h.to_status,
            actor_user_id=h.actor_user_id,
            reason=h.reason,
            at=h.created_at,
        )


class AdminOrderRefundRead(BaseModel):
    """One refund of the order (VS-030); the full record is `GET /admin/refunds/{id}`."""

    id: UUID
    kind: str
    status: str
    owed: bool
    amount: PriceRead
    created_at: datetime


class AdminOrderChargebackRead(BaseModel):
    """One chargeback of the order (VS-030); the full record is `GET /admin/chargebacks/{id}`."""

    id: UUID
    payment_id: UUID
    charged: PriceRead
    applied_cents: int
    excess_cents: int
    received_at: datetime


class AdminLineBalanceRead(BaseModel):
    order_item_id: UUID
    balance_cents: int


class AdminRefundBalanceRead(BaseModel):
    """What can still be refunded, per line and on the paid payment (VS-030 L2, L3)."""

    lines: list[AdminLineBalanceRead]
    payment_cents: int


class AdminOrderDetail(BaseModel):
    id: UUID
    order_number: str
    source: OrderSource
    customer_id: UUID
    customer_email: str
    status: OrderStatus
    fulfillment_method: FulfillmentMethod | None
    payment_method: PaymentMethod
    payment_reached_paid: bool
    payment_due: bool
    amount_due: PriceRead | None = Field(description="While payment_due: the live total.")
    subtotal: PriceRead
    tax: PriceRead
    total: PriceRead
    delivery_address: AdminDeliveryAddressRead | None
    contact_phone: str | None
    delivery_fee_note: str | None
    customer_note: str | None
    admin_note: str | None = Field(description="Internal; never shown to the customer.")
    estimated_dispatch_at: datetime | None
    placed_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    lines: list[AdminOrderLineRead]
    payments: list[AdminOrderPaymentRead] = Field(description="Newest first.")
    status_history: list[AdminHistoryRead] = Field(description="Oldest first.")
    refunds: list[AdminOrderRefundRead] = Field(default_factory=list, description="Oldest first.")
    chargebacks: list[AdminOrderChargebackRead] = Field(
        default_factory=list, description="Oldest first; never in the obligations queue."
    )
    refund_balance: AdminRefundBalanceRead | None = Field(
        default=None, description="Null until a payment reached paid."
    )

    @classmethod
    def of(cls, view: AdminOrderView, media_base_url: str) -> Self:
        o = view.order
        delivery = o.fulfillment_method is FulfillmentMethod.DELIVERY
        return cls(
            id=o.id,
            order_number=o.order_number,
            source=o.source,
            customer_id=o.user_id,
            customer_email=o.customer_email_snapshot,
            status=o.status,
            fulfillment_method=o.fulfillment_method,
            payment_method=o.payment_method,
            payment_reached_paid=view.payment_reached_paid,
            payment_due=view.payment_due,
            amount_due=_price(o.live_total_cents, o.currency) if view.payment_due else None,
            subtotal=_price(o.subtotal_cents, o.currency),
            tax=_price(o.tax_cents, o.currency),
            total=_price(o.total_cents, o.currency),
            delivery_address=AdminDeliveryAddressRead(
                recipient_name=o.recipient_name,
                governorate=o.governorate,
                city=o.city,
                area=o.area,
                street=o.street,
                landmark_notes=o.landmark_notes,
            )
            if delivery
            else None,
            contact_phone=o.contact_phone_snapshot,
            delivery_fee_note=DELIVERY_FEE_NOTE if delivery else None,
            customer_note=o.customer_note,
            admin_note=o.admin_note,
            estimated_dispatch_at=o.estimated_dispatch_at,
            placed_at=o.placed_at,
            completed_at=o.completed_at,
            cancelled_at=o.cancelled_at,
            lines=[AdminOrderLineRead.of(line, media_base_url) for line in view.lines],
            payments=[AdminOrderPaymentRead.of(p) for p in view.payments],
            status_history=[AdminHistoryRead.of(h) for h in view.history],
        )


class AdminOrderUpdate(BaseModel):
    """`admin_note` is required; blank or null clears it (F-062)."""

    model_config = ConfigDict(extra="forbid")

    admin_note: Annotated[MultilineStr | None, Field(max_length=limits.ADMIN_NOTE_MAX)]

    def note(self) -> str | None:
        return (self.admin_note or "").strip() or None


class CashHandoverRequest(BaseModel):
    """The cash the customer paid; the server never derives the amount from it (BR-143)."""

    model_config = ConfigDict(extra="forbid")

    amount_cents: Annotated[int, Field(strict=True, ge=0)]
    currency: Literal["USD"]
    note: Annotated[MultilineStr | None, Field(max_length=limits.NOTE_MAX)] = None
