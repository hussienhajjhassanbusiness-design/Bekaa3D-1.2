"""STL ownership as the customer sees it (VS-023 plan 2.3; ADR-025 d2)."""

from uuid import UUID

from app.catalog.application.ports import CartProductReader, ProductType
from app.ordering.application.ports import OrderStore


async def owns_listed_stl(
    products: CartProductReader, orders: OrderStore, *, user_id: UUID, product_id: UUID
) -> bool:
    """True only for a listed STL the caller has paid for and not had refunded; unknown,
    hidden or physical products and the caller's own unpaid line all answer false."""
    product = (await products.get_many([product_id])).get(product_id)
    if product is None or not product.listed or product.type is not ProductType.STL:
        return False
    return bool(await orders.owned_stl_product_ids(user_id, [product_id]))
