"""Checkout payloads (VS-023 plan 2.1; api-endpoints.md 29.5). The body carries no amount,
total or price: `extra="forbid"` refuses one, and checkout charges live prices (BR-031)."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.api.text import MultilineStr, PlainStr
from app.catalog.application.ports import ProductType
from app.catalog.public import PriceRead
from app.ordering.application.services.checkout import PlacedOrder
from app.ordering.domain.checkout_rules import AcceptedPrice, CheckoutCommand
from app.ordering.domain.enums import (
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)

MAX_ACCEPTED_PRICES = 50
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9._:-]{8,255}$"


class AcceptedPriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    amount_cents: Annotated[StrictInt, Field(ge=0)]
    currency: Annotated[PlainStr, Field(min_length=3, max_length=3)]


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_method: PaymentMethod
    payment_provider: Annotated[PlainStr, Field(min_length=1, max_length=32)] | None = None
    fulfillment_method: FulfillmentMethod | None = None
    address_id: UUID | None = None
    contact_phone: Annotated[PlainStr, Field(max_length=32)] | None = None
    customer_note: Annotated[MultilineStr, Field(max_length=1000)] | None = None
    accept_terms: Literal[True]
    accept_digital_final_sale: Literal[True] | None = None
    accept_cash_terms: Literal[True] | None = Field(
        default=None, description="Accepted and ignored for online orders (VS-028 uses it)."
    )
    accepted_price_changes: Annotated[
        list[AcceptedPriceIn], Field(max_length=MAX_ACCEPTED_PRICES)
    ] = Field(default_factory=list)

    def command(self) -> CheckoutCommand:
        return CheckoutCommand(
            payment_method=self.payment_method,
            payment_provider=self.payment_provider,
            fulfillment_requested=any(
                v is not None
                for v in (self.fulfillment_method, self.address_id, self.contact_phone)
            ),
            customer_note=self.customer_note,
            accept_digital_final_sale=bool(self.accept_digital_final_sale),
            accepted_price_changes=tuple(
                AcceptedPrice(a.product_id, a.amount_cents, a.currency)
                for a in self.accepted_price_changes
            ),
        )


class CheckoutLineRead(BaseModel):
    id: UUID
    product_id: UUID
    product_type: ProductType
    name: str
    unit_price: PriceRead
    quantity: int
    line_total: PriceRead
    fulfillment_status: OrderItemStatus


class CheckoutOrderRead(BaseModel):
    id: UUID
    order_number: str
    source: OrderSource
    status: OrderStatus
    payment_method: PaymentMethod
    fulfillment_method: FulfillmentMethod | None
    subtotal: PriceRead
    tax: PriceRead
    total: PriceRead
    placed_at: datetime
    lines: list[CheckoutLineRead]


class CheckoutPaymentRead(BaseModel):
    id: UUID
    status: str
    provider: str
    redirect_url: str | None = Field(description="The provider's payment page; null if none.")


class DroppedLineRead(BaseModel):
    product_id: UUID
    reason: Literal["already_owned"]


class CheckoutRead(BaseModel):
    order: CheckoutOrderRead
    payment: CheckoutPaymentRead
    dropped_lines: list[DroppedLineRead] = Field(
        description="STL lines bought since they were added: not charged (SRS 7.3 step 5)."
    )

    @classmethod
    def of(cls, placed: PlacedOrder, redirect_url: str | None) -> Self:
        order, currency = placed.order, placed.order.currency

        def price(cents: int) -> PriceRead:
            return PriceRead(amount_cents=cents, currency=currency)

        return cls(
            order=CheckoutOrderRead(
                id=order.id,
                order_number=order.order_number,
                source=order.source,
                status=order.status,
                payment_method=order.payment_method,
                fulfillment_method=order.fulfillment_method,
                subtotal=price(order.subtotal_cents),
                tax=price(order.tax_cents),
                total=price(order.total_cents),
                placed_at=order.placed_at,
                lines=[
                    CheckoutLineRead(
                        id=line.id,
                        product_id=line.product_id,
                        product_type=line.product_type,
                        name=line.product_name_snapshot,
                        unit_price=price(line.unit_price_cents),
                        quantity=line.quantity,
                        line_total=price(line.line_total_cents),
                        fulfillment_status=line.fulfillment_status,
                    )
                    for line in placed.lines
                ],
            ),
            payment=CheckoutPaymentRead(
                id=placed.payment.id,
                status=placed.payment.status,
                provider=placed.payment.provider,
                redirect_url=redirect_url,
            ),
            dropped_lines=[
                DroppedLineRead(product_id=p, reason="already_owned") for p in placed.dropped
            ],
        )
