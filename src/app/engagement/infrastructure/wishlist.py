from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, func, literal, select, text, tuple_, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.public import adjust_wishlist_count
from app.engagement.domain.entities import WishlistItem
from app.engagement.infrastructure.models import WishlistItemModel

_M = WishlistItemModel
_COLUMNS = (_M.id, _M.user_id, _M.product_id, _M.deleted_at, _M.created_at, _M.updated_at)


def _row_to_domain(row: Any) -> WishlistItem:
    return WishlistItem(
        id=row.id,
        user_id=row.user_id,
        product_id=row.product_id,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlWishlistCounter:
    """Adapts `app.catalog.public.adjust_wishlist_count` to `WishlistCounter`,
    bound to the same session as the `WishlistStore` adapter it is paired
    with. Deliberately does not commit - the caller's request-scoped unit of
    work does (see `app.engagement.public.create_notification`'s callers)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def adjust(self, product_id: UUID, delta: int) -> None:
        await adjust_wishlist_count(self._session, product_id, delta)


class SqlWishlistRepository:
    """Persistence for the WishlistItem aggregate. Insert-only `add`: a
    previously removed row is never reactivated, so re-adding always inserts
    a fresh row with its own `created_at` (VS-038 plan §3)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, user_id: UUID, product_id: UUID) -> bool:
        """One statement. `True` iff a row was inserted; `False` if an active
        row for this (user, product) already exists - the conflict target
        must mirror the partial unique index's predicate exactly, or Postgres
        has no matching arbiter index to resolve the conflict against."""
        stmt = (
            postgresql.insert(_M)
            .values(user_id=user_id, product_id=product_id)
            .on_conflict_do_nothing(
                index_elements=[_M.user_id, _M.product_id],
                index_where=text("deleted_at IS NULL"),
            )
            .returning(_M.id)
        )
        row = (await self._session.execute(stmt)).first()
        return row is not None

    async def remove(self, *, user_id: UUID, product_id: UUID) -> bool:
        """`True` iff an active row was soft-deleted; `False` if there was none."""
        stmt = (
            update(_M)
            .where(_M.user_id == user_id, _M.product_id == product_id, _M.deleted_at.is_(None))
            .values(deleted_at=func.now(), updated_at=func.now())
            .returning(_M.id)
            .execution_options(synchronize_session=False)
        )
        row = (await self._session.execute(stmt)).first()
        return row is not None

    async def remove_all(self, user_id: UUID) -> list[UUID]:
        stmt = (
            update(_M)
            .where(_M.user_id == user_id, _M.deleted_at.is_(None))
            .values(deleted_at=func.now(), updated_at=func.now())
            .returning(_M.product_id)
            .execution_options(synchronize_session=False)
        )
        return list((await self._session.scalars(stmt)).all())

    async def list_page(
        self, *, user_id: UUID, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[WishlistItem]:
        stmt = select(*_COLUMNS).where(_M.user_id == user_id, _M.deleted_at.is_(None))
        if after is not None:
            after_created_at, after_id = after
            stmt = stmt.where(
                tuple_(_M.created_at, _M.id)
                < tuple_(
                    literal(after_created_at, DateTime(timezone=True)),
                    literal(after_id, postgresql.UUID(as_uuid=True)),
                )
            )
        stmt = stmt.order_by(_M.created_at.desc(), _M.id.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).all()
        return [_row_to_domain(row) for row in rows]

    async def count_active(self) -> int:
        stmt = select(func.count()).select_from(_M).where(_M.deleted_at.is_(None))
        return await self._session.scalar(stmt) or 0
