"""The customer data export's records (VS-044, ADR-046): customer-safe by construction, each
field listed here or not exported. The API serialises these same types."""

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

FORMAT_VERSION: Final = 1
# The six data sets after the profile, in body order (SRS 14.5 as amended by ADR-046).
SECTIONS: Final = ("addresses", "orders", "reviews", "offers", "contact_messages")


@dataclass(frozen=True)
class Money:
    amount_cents: int
    currency: str

    def __post_init__(self) -> None:
        # A NUMERIC SUM arrives as Decimal and would be serialised as a string.
        if type(self.amount_cents) is not int:
            raise TypeError(f"amount_cents must be int, not {type(self.amount_cents).__name__}")


@dataclass(frozen=True)
class ExportProfile:
    id: UUID
    email: str
    role: str
    email_verified: bool
    email_verified_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class ExportAddress:
    id: UUID
    label: str
    recipient_name: str
    phone: str
    governorate: str
    city: str
    area: str | None
    street: str | None
    landmark_notes: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    deleted: bool
    deleted_at: datetime | None


@dataclass(frozen=True)
class ExportOrderLine:
    id: UUID
    product_id: UUID
    product_type: str
    name: str
    offer_id: UUID | None
    unit_price: Money
    quantity: int
    line_total: Money
    fulfillment_status: str
    fulfilled_at: datetime | None  # STL: when the administrator emailed the file
    cancelled_at: datetime | None
    receipt_confirmed_at: datetime | None
    problem_reported_at: datetime | None


@dataclass(frozen=True)
class ExportStatusChange:
    order_item_id: UUID | None
    from_status: str | None
    to_status: str
    at: datetime


@dataclass(frozen=True)
class ExportDeliveryAddress:
    recipient_name: str | None
    governorate: str | None
    city: str | None
    area: str | None
    street: str | None
    landmark_notes: str | None


@dataclass(frozen=True)
class ExportPayment:
    provider: str
    status: str
    amount: Money


@dataclass(frozen=True)
class ExportRefund:
    kind: str
    status: str
    amount: Money
    created_at: datetime


@dataclass(frozen=True)
class ExportOrder:
    id: UUID
    order_number: str
    source: str
    status: str
    payment_method: str
    fulfillment_method: str | None
    payment_due: bool
    amount_due: Money | None
    subtotal: Money
    tax: Money
    total: Money
    delivery_address: ExportDeliveryAddress | None
    contact_phone: str | None
    delivery_email: str | None  # where the paid STL files are emailed
    customer_note: str | None
    estimated_dispatch_at: datetime | None
    placed_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    lines: list[ExportOrderLine]
    payment: ExportPayment | None
    refunds: list[ExportRefund]
    status_history: list[ExportStatusChange]


@dataclass(frozen=True)
class ExportReview:
    id: UUID
    product_id: UUID
    product_name: str | None
    rating: int
    body: str | None
    is_verified_purchase: bool
    is_hidden: bool
    created_at: datetime
    updated_at: datetime
    deleted: bool
    deleted_at: datetime | None


@dataclass(frozen=True)
class ExportOfferRound:
    sequence: int
    actor: str
    action: str
    amount: Money | None
    message: str | None
    created_at: datetime


@dataclass(frozen=True)
class ExportOffer:
    id: UUID
    product_id: UUID
    product_name: str | None
    status: str
    turn: str | None
    initial_amount: Money
    current_amount: Money
    agreed_amount: Money | None
    responds_by: datetime | None
    accepted_at: datetime | None
    checkout_expires_at: datetime | None
    cooldown_until: datetime | None
    created_at: datetime
    updated_at: datetime
    rounds: list[ExportOfferRound]


@dataclass(frozen=True)
class ExportContactMessage:
    subject: str | None
    message: str
    created_at: datetime


def money(cents: int | None, currency: str | None) -> Money | None:
    return Money(cents, currency) if cents is not None and currency is not None else None
