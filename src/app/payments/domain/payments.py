"""A payment attempt as Payments reads it (database-design 9.1)."""

from dataclasses import dataclass
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
