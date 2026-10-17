"""Ordering's stored enums, values exactly as database-design.md 3.4-3.7 (VS-023)."""

from enum import StrEnum


class FulfillmentMethod(StrEnum):
    """NULL on the order means digital-only (3.4)."""

    DELIVERY = "delivery"
    PICKUP = "pickup"


class PaymentMethod(StrEnum):
    """Chosen at checkout and immutable; cash requires every line physical (ADR-024)."""

    ONLINE = "online"
    CASH = "cash"


class CancelReason(StrEnum):
    REFUSED = "refused"
    NO_SHOW = "no_show"
    OTHER = "other"


class OrderSource(StrEnum):
    CART = "cart"
    OFFER = "offer"


class OrderStatus(StrEnum):
    """A derived projection (SRS 20.2); never set as business input."""

    PENDING_PAYMENT = "pending_payment"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"


class OrderItemStatus(StrEnum):
    """One storage enum for STL and physical line states (3.7)."""

    PENDING = "pending"
    AWAITING_DELIVERY = "awaiting_delivery"
    IN_PRODUCTION = "in_production"
    READY_TO_SHIP = "ready_to_ship"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    RETURNED = "returned"
    READY_FOR_PICKUP = "ready_for_pickup"
    PICKED_UP = "picked_up"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
