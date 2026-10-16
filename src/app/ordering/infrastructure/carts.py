from typing import Any, Literal, overload
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ProductType
from app.ordering.domain.entities import Cart, CartLine
from app.ordering.infrastructure.models import CartItemModel, CartModel

_C, _I = CartModel, CartItemModel
_CART_COLUMNS = (_C.id, _C.user_id, _C.created_at, _C.updated_at)
_LINE_COLUMNS = (
    _I.id,
    _I.cart_id,
    _I.product_id,
    _I.product_type,
    _I.quantity,
    _I.price_snapshot_cents,
    _I.currency,
    _I.created_at,
    _I.updated_at,
)


def _cart(row: Any) -> Cart:
    return Cart(
        id=row.id, user_id=row.user_id, created_at=row.created_at, updated_at=row.updated_at
    )


def _line(row: Any) -> CartLine:
    return CartLine(
        id=row.id,
        cart_id=row.cart_id,
        product_id=row.product_id,
        product_type=row.product_type,
        quantity=row.quantity,
        price_snapshot_cents=row.price_snapshot_cents,
        currency=row.currency,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlCartStore:
    """`CartStore` (VS-022 plan §3.5). Single statements; it never commits - the request's
    unit of work does. Requires READ COMMITTED, the app's level (plan §3.5)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @overload
    async def lock(self, user_id: UUID, *, create: Literal[True]) -> Cart: ...

    @overload
    async def lock(self, user_id: UUID, *, create: Literal[False]) -> Cart | None: ...

    async def lock(self, user_id: UUID, *, create: bool) -> Cart | None:
        """INSERT ... ON CONFLICT DO NOTHING waits on a concurrent first add's row, then
        the SELECT ... FOR UPDATE reads it once committed: both first adds succeed."""
        if create:
            await self._session.execute(
                postgresql.insert(_C)
                .values(user_id=user_id)
                .on_conflict_do_nothing(index_elements=[_C.user_id])
            )
        stmt = select(*_CART_COLUMNS).where(_C.user_id == user_id).with_for_update()
        row = (await self._session.execute(stmt)).first()
        if row is None and create:
            raise RuntimeError("cart vanished between insert and lock")
        return _cart(row) if row is not None else None

    async def get(self, user_id: UUID) -> Cart | None:
        row = (
            await self._session.execute(select(*_CART_COLUMNS).where(_C.user_id == user_id))
        ).first()
        return _cart(row) if row is not None else None

    async def lines(self, cart_id: UUID) -> list[CartLine]:
        stmt = select(*_LINE_COLUMNS).where(_I.cart_id == cart_id).order_by(_I.created_at, _I.id)
        return [_line(row) for row in (await self._session.execute(stmt)).all()]

    async def line(self, cart_id: UUID, product_id: UUID) -> CartLine | None:
        stmt = select(*_LINE_COLUMNS).where(_I.cart_id == cart_id, _I.product_id == product_id)
        row = (await self._session.execute(stmt)).first()
        return _line(row) if row is not None else None

    async def count_lines(self, cart_id: UUID) -> int:
        stmt = select(func.count()).select_from(_I).where(_I.cart_id == cart_id)
        return await self._session.scalar(stmt) or 0

    async def insert_line(
        self,
        *,
        cart_id: UUID,
        product_id: UUID,
        product_type: ProductType,
        quantity: int,
        price_snapshot_cents: int,
        currency: str,
    ) -> CartLine:
        """A plain INSERT: under the cart lock no conflict is expected, so a unique
        violation here is a bug that must surface, not be absorbed."""
        stmt = (
            postgresql.insert(_I)
            .values(
                cart_id=cart_id,
                product_id=product_id,
                product_type=product_type,
                quantity=quantity,
                price_snapshot_cents=price_snapshot_cents,
                currency=currency,
            )
            .returning(*_LINE_COLUMNS)
        )
        return _line((await self._session.execute(stmt)).one())

    async def set_quantity(self, line_id: UUID, quantity: int) -> CartLine:
        stmt = (
            update(_I)
            .where(_I.id == line_id)
            .values(quantity=quantity, updated_at=func.now())
            .returning(*_LINE_COLUMNS)
            .execution_options(synchronize_session=False)
        )
        return _line((await self._session.execute(stmt)).one())

    async def delete_line(self, cart_id: UUID, product_id: UUID) -> bool:
        stmt = (
            delete(_I)
            .where(_I.cart_id == cart_id, _I.product_id == product_id)
            .returning(_I.id)
            .execution_options(synchronize_session=False)
        )
        return (await self._session.execute(stmt)).first() is not None

    async def clear(self, cart_id: UUID) -> int:
        stmt = delete(_I).where(_I.cart_id == cart_id).returning(_I.id)
        return len((await self._session.execute(stmt)).all())

    async def touch(self, cart_id: UUID) -> None:
        await self._session.execute(
            update(_C)
            .where(_C.id == cart_id)
            .values(updated_at=func.now())
            .execution_options(synchronize_session=False)
        )
