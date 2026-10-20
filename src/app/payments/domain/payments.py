"""A payment attempt as Payments reads it (database-design 9.1)."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.payments.domain.enums import PaymentProvider, PaymentStatus


@dataclass(frozen=True)
class Payment:
    id: UUID
    order_id: UUID
    provider: PaymentProvider
    status: PaymentStatus
    amount_cents: int
    currency: str
    provider_payment_id: str | None
    late_captured_at: datetime | None
    initiated_at: datetime | None = None
    captured_amount_cents: int | None = None
    captured_currency: str | None = None
    # Never in a repr, log or audit row (VS-024 2.1).
    redirect_url: str | None = field(default=None, repr=False)
