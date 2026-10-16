"""Ordering's repository ports. Every method that writes `cart_items` is called only
while the caller holds `CartStore.lock` on that cart (VS-022 plan §3.3 invariant)."""

from typing import Literal, Protocol, overload
from uuid import UUID

from app.catalog.application.ports import ProductType
from app.ordering.domain.entities import Cart, CartLine


class CartStore(Protocol):
    @overload
    async def lock(self, user_id: UUID, *, create: Literal[True]) -> Cart: ...

    @overload
    async def lock(self, user_id: UUID, *, create: Literal[False]) -> Cart | None: ...

    async def lock(self, user_id: UUID, *, create: bool) -> Cart | None:
        """Row-lock the user's cart (`FOR UPDATE`), creating it first if `create`;
        None only when `create` is False and no cart exists."""
        ...

    async def get(self, user_id: UUID) -> Cart | None:
        """No lock: reads only."""
        ...

    async def lines(self, cart_id: UUID) -> list[CartLine]:
        """Ordered by (created_at, id)."""
        ...

    async def line(self, cart_id: UUID, product_id: UUID) -> CartLine | None: ...

    async def count_lines(self, cart_id: UUID) -> int: ...

    async def insert_line(
        self,
        *,
        cart_id: UUID,
        product_id: UUID,
        product_type: ProductType,
        quantity: int,
        price_snapshot_cents: int,
        currency: str,
    ) -> CartLine: ...

    async def set_quantity(self, line_id: UUID, quantity: int) -> CartLine: ...

    async def delete_line(self, cart_id: UUID, product_id: UUID) -> bool: ...

    async def clear(self, cart_id: UUID) -> int: ...

    async def touch(self, cart_id: UUID) -> None:
        """`updated_at = now()` on the cart."""
        ...
