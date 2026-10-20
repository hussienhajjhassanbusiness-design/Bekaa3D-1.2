from datetime import datetime
from uuid import UUID

from app.negotiation.domain.enums import OfferStatus


class NegotiationDomainError(Exception):
    """Base for Negotiation's domain errors; routers map them to stable codes."""


class OfferNotAllowedError(NegotiationDomainError):
    """422 PRODUCT_NOT_PURCHASABLE with `reason` (not_listed, unavailable, not_negotiable)."""

    def __init__(self, product_id: UUID, reason: str) -> None:
        super().__init__(f"Product {product_id} cannot be offered on: {reason}.")
        self.product_id = product_id
        self.reason = reason


class OfferBelowMinimumError(NegotiationDomainError):
    """422 OFFER_BELOW_MINIMUM (BR-090)."""

    def __init__(self, minimum_cents: int) -> None:
        super().__init__(f"An offer must be at least {minimum_cents} cents.")
        self.minimum_cents = minimum_cents


class OfferAboveListPriceError(NegotiationDomainError):
    """422 VALIDATION_ERROR: above list price the customer should simply buy (ADR-034)."""

    def __init__(self, list_price_cents: int) -> None:
        super().__init__(f"An offer may not exceed the list price of {list_price_cents} cents.")
        self.list_price_cents = list_price_cents


class OfferCooldownActiveError(NegotiationDomainError):
    """422 OFFER_COOLDOWN_ACTIVE (BR-089)."""

    def __init__(self, until: datetime) -> None:
        super().__init__(f"A new offer is allowed from {until.isoformat()}.")
        self.until = until


class OfferAlreadyActiveError(NegotiationDomainError):
    """409 OFFER_ALREADY_ACTIVE (BR-081); raised when `uq_offers_live` refuses the row."""


class OfferProductOwnedError(NegotiationDomainError):
    """409 PRODUCT_ALREADY_OWNED: a paid, unrefunded STL line exists (ADR-019 d5)."""


class OffersPausedError(NegotiationDomainError):
    """503 ORDERS_PAUSED: `accepting_orders` is off (ADR-034)."""


class OfferNotFoundError(NegotiationDomainError):
    """404: unknown, or not the caller's."""


class OfferNotExpirableError(NegotiationDomainError):
    def __init__(self, status: OfferStatus) -> None:
        super().__init__(f"An offer in {status} cannot expire from inactivity.")
        self.status = status


class OfferInvalidTransitionError(NegotiationDomainError):
    """409 INVALID_STATE_TRANSITION: the offer is closed or accepted (SRS 20.6)."""

    def __init__(self, status: OfferStatus) -> None:
        super().__init__(f"An offer in {status} cannot be answered.")
        self.status = status


class OfferNotYourTurnError(NegotiationDomainError):
    """409 OFFER_NOT_YOUR_TURN: only the party whose turn it is may answer (FR-13)."""


class OfferAmountChangedError(NegotiationDomainError):
    """409 OFFER_AMOUNT_CHANGED: accept named an amount no longer on the table (ADR-035 d9)."""

    def __init__(self, current_amount_cents: int) -> None:
        super().__init__(f"The amount on the table is now {current_amount_cents} cents.")
        self.current_amount_cents = current_amount_cents


class OfferExpiredError(NegotiationDomainError):
    """410 OFFER_EXPIRED: the turn's deadline has been reached (BR-084, ADR-034 d6)."""
