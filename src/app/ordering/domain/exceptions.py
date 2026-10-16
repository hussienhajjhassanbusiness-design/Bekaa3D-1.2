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
