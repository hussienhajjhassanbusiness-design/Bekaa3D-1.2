"""Cart quantity and line rules (VS-022 plan §3.2). Pure: Catalog's product state comes
in as a `CartProduct`, and the purchase rule is Catalog's own `purchase_refusal`."""

from dataclasses import dataclass

from app.catalog.application.ports import (
    CartProduct,
    ProductImage,
    ProductType,
    PurchaseRefusal,
    purchase_refusal,
)
from app.ordering.domain.entities import MAX_CART_LINES, CartLine
from app.ordering.domain.enums import PaymentMethod
from app.ordering.domain.exceptions import (
    CartLineLimitReachedError,
    ProductNotPurchasableError,
    QuantityExceedsLimitError,
)
from app.ordering.domain.payment_methods import ALL_METHODS, accepted_methods


def cap_for(product: CartProduct) -> int:
    """STL is always 1. A physical product with no cap fails closed: the DB type CHECK
    makes it unreachable, but the domain must not invent a cap."""
    if product.type is ProductType.STL:
        return 1
    if product.max_quantity_per_line is None:
        raise ProductNotPurchasableError(product.id, PurchaseRefusal.NOT_LISTED)
    return product.max_quantity_per_line


def _refuse_unless_purchasable(product: CartProduct) -> None:
    if (reason := purchase_refusal(product)) is not None:
        raise ProductNotPurchasableError(product.id, reason)


def quantity_after_add(product: CartProduct, requested: int, existing: CartLine | None) -> int:
    """The line's quantity after this add. An STL re-add is an idempotent 1; a physical
    add merges, and anything over the cap is refused, never clamped (Q4, Q5)."""
    _refuse_unless_purchasable(product)
    current = existing.quantity if existing else 0
    if product.type is ProductType.STL:
        if requested != 1:
            raise QuantityExceedsLimitError(
                product.id, max_quantity=1, requested=requested, current_quantity=current
            )
        return 1
    cap = cap_for(product)
    merged = current + requested
    if merged > cap:
        raise QuantityExceedsLimitError(
            product.id, max_quantity=cap, requested=requested, current_quantity=current
        )
    return merged


def check_set_quantity(product: CartProduct, quantity: int, current: int) -> None:
    """An absolute quantity for an existing line (`PATCH`)."""
    _refuse_unless_purchasable(product)
    cap = cap_for(product)
    if quantity > cap:
        raise QuantityExceedsLimitError(
            product.id, max_quantity=cap, requested=quantity, current_quantity=current
        )


def check_line_capacity(line_count: int) -> None:
    """Called only before inserting a new line, so merging at the cap still works."""
    if line_count >= MAX_CART_LINES:
        raise CartLineLimitReachedError(MAX_CART_LINES)


@dataclass(frozen=True)
class CartLineView:
    """The read model behind `CartLineRead`. A product that is not listed keeps its
    name (the owner's own data) but not its slug, price, cap or cover. `name` is None
    only if the product row is gone, which the RESTRICT foreign key prevents."""

    line: CartLine
    name: str | None
    slug: str | None
    cover: ProductImage | None
    current_price_cents: int | None
    price_changed: bool
    max_quantity: int | None
    over_cap: bool
    refusal: PurchaseRefusal | None
    payment_methods: frozenset[PaymentMethod] = ALL_METHODS  # what the product accepts

    @property
    def purchasable(self) -> bool:
        return self.refusal is None


def view_line(line: CartLine, product: CartProduct | None) -> CartLineView:
    if product is None:
        return CartLineView(
            line, None, None, None, None, False, None, False, PurchaseRefusal.NOT_LISTED
        )
    refusal = purchase_refusal(product)
    try:
        cap: int | None = cap_for(product)
    except ProductNotPurchasableError:
        cap, refusal = None, refusal or PurchaseRefusal.NOT_LISTED
    listed = product.listed
    return CartLineView(
        line=line,
        name=product.name,
        slug=product.slug if listed else None,
        cover=product.cover if listed else None,
        current_price_cents=product.price_cents if listed else None,
        price_changed=listed and product.price_cents != line.price_snapshot_cents,
        max_quantity=cap if listed and product.type is ProductType.PHYSICAL else None,
        over_cap=cap is not None and line.quantity > cap,
        refusal=refusal,
        payment_methods=accepted_methods(product.type, product.accepted_payment_methods),
    )
