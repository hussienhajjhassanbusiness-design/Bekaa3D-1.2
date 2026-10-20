"""Negotiation's stored enums, values exactly as database-design.md 3.9, 3.10, 3.13."""

from enum import StrEnum


class OfferStatus(StrEnum):
    AWAITING_ADMIN = "awaiting_admin"
    AWAITING_CUSTOMER = "awaiting_customer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"
    PAID = "paid"
    CHECKOUT_EXPIRED = "checkout_expired"
    AUTO_CLOSED = "auto_closed"


class OfferTurn(StrEnum):
    ADMIN = "admin"
    CUSTOMER = "customer"


class OfferActor(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    SYSTEM = "system"


class OfferAction(StrEnum):
    SUBMITTED = "submitted"
    COUNTERED = "countered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    PAID = "paid"
    CHECKOUT_EXPIRED = "checkout_expired"
    AUTO_CLOSED = "auto_closed"


# Glossary "Live Offer"; the partial unique index `uq_offers_live` names the same three.
LIVE_STATUSES = frozenset(
    {OfferStatus.AWAITING_ADMIN, OfferStatus.AWAITING_CUSTOMER, OfferStatus.ACCEPTED}
)
# A turn and a running `responds_by` exist only while someone must answer (SRS 11.2).
AWAITING_STATUSES = frozenset({OfferStatus.AWAITING_ADMIN, OfferStatus.AWAITING_CUSTOMER})
