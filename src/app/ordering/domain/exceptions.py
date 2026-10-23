from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import PurchaseRefusal


class OrderingDomainError(Exception):
    """Base for ordering-context domain errors; routers map them to stable codes."""


class ProductNotPurchasableError(OrderingDomainError):
    """The product cannot go in a cart now (422 PRODUCT_NOT_PURCHASABLE)."""

    def __init__(self, product_id: UUID, reason: PurchaseRefusal) -> None:
        super().__init__(f"Product {product_id} is not purchasable: {reason}.")
        self.product_id = product_id
        self.reason = reason


class QuantityExceedsLimitError(OrderingDomainError):
    """The line would exceed the product's current cap (422 QUANTITY_EXCEEDS_LIMIT)."""

    def __init__(
        self, product_id: UUID, *, max_quantity: int, requested: int, current_quantity: int
    ) -> None:
        super().__init__(f"Product {product_id}: at most {max_quantity} per line.")
        self.product_id = product_id
        self.max_quantity = max_quantity
        self.requested = requested
        self.current_quantity = current_quantity


class CartLineLimitReachedError(OrderingDomainError):
    """A new line would exceed the cart's line cap (422 CART_LINE_LIMIT_REACHED)."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"A cart holds at most {limit} lines.")
        self.limit = limit


class CartLineNotFoundError(OrderingDomainError):
    """The caller's cart has no line for this product (404); no cart counts as none."""

    def __init__(self, product_id: UUID) -> None:
        super().__init__(f"No cart line for product {product_id}.")
        self.product_id = product_id


@dataclass(frozen=True)
class LineRefusal:
    """One cart line checkout refuses: a `PurchaseRefusal` value or `over_cap`."""

    product_id: UUID
    reason: str
    max_quantity: int | None = None


class CheckoutLinesRefusedError(OrderingDomainError):
    """Lines that cannot be bought; every one is named (422, VS-022 contract)."""

    def __init__(self, refusals: list[LineRefusal]) -> None:
        super().__init__(f"{len(refusals)} cart line(s) cannot be bought.")
        self.refusals = refusals
        self.only_caps = all(r.reason == "over_cap" for r in refusals)


class CartEmptyError(OrderingDomainError):
    """No cart, no lines, or every line dropped as already owned (409 CART_EMPTY)."""

    def __init__(self, dropped: tuple[UUID, ...] = ()) -> None:
        super().__init__("The cart has nothing to check out.")
        self.dropped = dropped


@dataclass(frozen=True)
class PriceChange:
    product_id: UUID
    old_amount_cents: int
    new_amount_cents: int
    currency: str


class CartPriceChangedError(OrderingDomainError):
    """A live price differs from the snapshot and was not accepted (409)."""

    def __init__(self, changes: list[PriceChange]) -> None:
        super().__init__(f"{len(changes)} price(s) changed since they were added.")
        self.changes = changes


class InvalidFulfillmentError(OrderingDomainError):
    """The fulfillment fields do not fit the kept lines (422 INVALID_FULFILLMENT)."""


class PaymentMethodNotAllowedError(OrderingDomainError):
    """422 PAYMENT_METHOD_NOT_ALLOWED with a machine-readable `reason`."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Payment method not allowed: {reason}.")
        self.reason = reason


class OnlinePaymentUnavailableError(OrderingDomainError):
    """No online provider is configured (503 ONLINE_PAYMENT_UNAVAILABLE)."""


class OrdersPausedError(OrderingDomainError):
    """`accepting_orders` is off (503 ORDERS_PAUSED)."""


class ConsentRequiredError(OrderingDomainError):
    """A required acceptance is missing (422 VALIDATION_ERROR at `field`)."""

    def __init__(self, message: str, field: str = "accept_digital_final_sale") -> None:
        super().__init__(message)
        self.field = field


class CashLimitReachedError(OrderingDomainError):
    """422 CASH_PAYMENT_LIMIT_REACHED; `reason` is `order_total`, a check on no phone."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Cash payment limit reached: {reason}.")
        self.reason = reason


class CashNotAvailableError(OrderingDomainError):
    """422 CASH_NOT_AVAILABLE: a block or an open cash order, never saying which, nor
    whether the account or the phone matched (ADR-038)."""


class ProductAlreadyOwnedError(OrderingDomainError):
    """The STL is owned, or held by another live order of this user (409)."""

    def __init__(self, product_ids: tuple[UUID, ...]) -> None:
        super().__init__(f"Already owned: {', '.join(map(str, product_ids))}.")
        self.product_ids = product_ids


class OrderNumberExhaustedError(OrderingDomainError):
    """Every generated order number collided; a defect, surfaced as a 500."""


class OrderNotReleasableError(OrderingDomainError):
    """A hold release on an order that is not an unpaid, uncancelled online order."""


class RetryOrderNotFoundError(OrderingDomainError):
    """Unknown, or not the caller's: the same 404 either way (VS-024 2.1)."""


class RetryRefusedError(OrderingDomainError):
    """409 INVALID_STATE_TRANSITION; `reason` is a T1 `RetryRefusal` value."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Payment retry refused: {reason}.")
        self.reason = reason


class LiveAttemptExistsError(OrderingDomainError):
    """`uq_payments_one_live` refused the new attempt (raised inside its SAVEPOINT)."""


class PaymentAlreadyActiveError(OrderingDomainError):
    """409 PAYMENT_ALREADY_ACTIVE: the live attempt the customer can resume."""

    def __init__(self, payment_id: UUID | None, status: str | None, redirect_url: str | None):
        super().__init__("A payment for this order is already in progress.")
        self.payment_id, self.status, self.redirect_url = payment_id, status, redirect_url


class OfferCheckoutNotFoundError(OrderingDomainError):
    """404: no such offer among the caller's own (VS-041)."""


class OfferCheckoutExpiredError(OrderingDomainError):
    """410 OFFER_CHECKOUT_EXPIRED: the accepted offer's window has closed (BR-086)."""


class OfferNotCheckoutableError(OrderingDomainError):
    """409 INVALID_STATE_TRANSITION with `offer_status`: the offer is not accepted."""

    def __init__(self, offer_status: str) -> None:
        super().__init__(f"An offer that is {offer_status} cannot be checked out.")
        self.offer_status = offer_status


class OfferChangedError(OrderingDomainError):
    """The locked offer differs from the one priced: a 500, never a charge (ADR-037 d3)."""


class LineNotFoundError(OrderingDomainError):
    """404: the item is not a line of the order (or the order does not exist)."""


class InvalidLineTransitionError(OrderingDomainError):
    """409 INVALID_STATE_TRANSITION with `reason` (VS-023b) and the state read (VS-029)."""

    def __init__(
        self,
        reason: str,
        *,
        fulfilled_at: datetime | None = None,
        current_status: str | None = None,
    ) -> None:
        super().__init__(f"The line cannot make this transition: {reason}.")
        self.reason = reason
        self.fulfilled_at = fulfilled_at
        self.current_status = current_status


class HandoverRefusedError(OrderingDomainError):
    """409 INVALID_STATE_TRANSITION: the order cannot take a cash handover now (VS-029)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"The cash handover is refused: {reason}.")
        self.reason = reason


class CashAmountMismatchError(OrderingDomainError):
    """422 CASH_AMOUNT_MISMATCH: not exactly the live total above zero (BR-055, BR-143)."""

    def __init__(self, due_cents: int, currency: str) -> None:
        super().__init__("The cash entered differs from the amount due.")
        self.due_cents = due_cents
        self.currency = currency
