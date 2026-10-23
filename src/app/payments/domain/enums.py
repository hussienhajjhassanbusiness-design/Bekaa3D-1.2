"""Payments' stored enums, values exactly as database-design.md 3.8 and 3.13 (VS-023)."""

from enum import StrEnum


class PaymentStatus(StrEnum):
    """`paid`, `partially_refunded` and `refunded` count as "reached paid" (SRS 20.1)."""

    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    FAILED = "failed"
    EXPIRED = "expired"


class PaymentProvider(StrEnum):
    """`cash` has no adapter; VS-032 adds the real online value(s)."""

    MOCK = "mock"
    CASH = "cash"


class RefundKind(StrEnum):
    """VS-030: a chargeback is its own record (`chargebacks`), never a refund kind (ADR-042)."""

    ADMIN = "admin"
    CANCELLATION = "cancellation"
    LATE_CAPTURE = "late_capture"


class RefundStatus(StrEnum):
    """`failed` stays owed until reissued; `voided` closes an obligation unpaid (ADR-042)."""

    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    VOIDED = "voided"
