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
