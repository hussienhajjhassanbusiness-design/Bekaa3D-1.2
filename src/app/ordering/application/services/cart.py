"""Cart use cases (VS-022 plan §3.4, §3.6). Each runs in the caller's session and does
not commit. Every write takes the cart lock first, before any read; reads take none."""

from dataclasses import dataclass
from uuid import UUID

from app.catalog.application.ports import CartProductReader, PurchaseRefusal
from app.ordering.application.ports import CartStore
from app.ordering.domain.cart_rules import (
    CartLineView,
    check_line_capacity,
    check_set_quantity,
    quantity_after_add,
    view_line,
)
from app.ordering.domain.entities import Cart, CartLine
from app.ordering.domain.exceptions import CartLineNotFoundError, ProductNotPurchasableError


@dataclass(frozen=True)
class CartView:
    cart: Cart | None
    lines: tuple[CartLineView, ...]


@dataclass(frozen=True)
class LockedCart:
    """A cart the caller holds `FOR UPDATE`, with its lines in (created_at, id) order."""

    cart: Cart
    lines: tuple[CartLine, ...]


async def add_item(
    carts: CartStore,
    products: CartProductReader,
    *,
    user_id: UUID,
    product_id: UUID,
    quantity: int,
) -> None:
    cart = await carts.lock(user_id, create=True)
    product = (await products.get_many([product_id])).get(product_id)
    if product is None:
        raise ProductNotPurchasableError(product_id, PurchaseRefusal.NOT_LISTED)
    existing = await carts.line(cart.id, product_id)
    new_quantity = quantity_after_add(product, quantity, existing)
    # VS-023 inserts the STL ownership check here (409 PRODUCT_ALREADY_OWNED).
    if existing is not None:
        if new_quantity == existing.quantity:
            return
        # The snapshot is kept on a merge (plan Q3).
        await carts.set_quantity(existing.id, new_quantity)
    else:
        check_line_capacity(await carts.count_lines(cart.id))
        # The stored type and price come from `product`, the read made above under the
        # cart lock - never from the request - so the snapshot matches the row the
        # composite FK (product_id, product_type) checks.
        await carts.insert_line(
            cart_id=cart.id,
            product_id=product_id,
            product_type=product.type,
            quantity=new_quantity,
            price_snapshot_cents=product.price_cents,
            currency=product.currency,
        )
    await carts.touch(cart.id)


async def set_item_quantity(
    carts: CartStore,
    products: CartProductReader,
    *,
    user_id: UUID,
    product_id: UUID,
    quantity: int,
) -> None:
    cart = await carts.lock(user_id, create=False)
    existing = await carts.line(cart.id, product_id) if cart is not None else None
    if cart is None or existing is None:
        raise CartLineNotFoundError(product_id)
    product = (await products.get_many([product_id])).get(product_id)
    if product is None:
        raise ProductNotPurchasableError(product_id, PurchaseRefusal.NOT_LISTED)
    check_set_quantity(product, quantity, existing.quantity)
    if quantity != existing.quantity:
        await carts.set_quantity(existing.id, quantity)
        await carts.touch(cart.id)


async def remove_item(carts: CartStore, *, user_id: UUID, product_id: UUID) -> None:
    """No product read: a line for a product gone non-public can always be removed."""
    cart = await carts.lock(user_id, create=False)
    if cart is None or not await carts.delete_line(cart.id, product_id):
        raise CartLineNotFoundError(product_id)
    await carts.touch(cart.id)


async def read_cart(carts: CartStore, products: CartProductReader, *, user_id: UUID) -> CartView:
    """Unlocked; never creates a cart. Three queries: cart, lines, one Catalog batch."""
    cart = await carts.get(user_id)
    if cart is None:
        return CartView(cart=None, lines=())
    lines = await carts.lines(cart.id)
    found = await products.get_many([line.product_id for line in lines])
    return CartView(
        cart=cart, lines=tuple(view_line(line, found.get(line.product_id)) for line in lines)
    )


async def lock_cart_for_checkout(carts: CartStore, *, user_id: UUID) -> LockedCart | None:
    """Lock the cart and load its lines (plan §3.6 step 2). None means no cart; VS-023
    answers that, and an empty `lines`, with 409 CART_EMPTY. Never creates a cart."""
    cart = await carts.lock(user_id, create=False)
    if cart is None:
        return None
    return LockedCart(cart=cart, lines=tuple(await carts.lines(cart.id)))


async def clear_cart(carts: CartStore, locked: LockedCart) -> None:
    """Delete every line of a cart the caller still holds locked (SRS 7.3 step 12)."""
    await carts.clear(locked.cart.id)
    await carts.touch(locked.cart.id)
