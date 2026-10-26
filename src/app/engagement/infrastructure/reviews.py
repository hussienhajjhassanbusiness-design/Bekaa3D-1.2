"""Persistence for reviews (VS-036 plan 3.2b, 3.3). Edit and delete stamp
`clock_timestamp()`, which can never precede `created_at` (its CHECK)."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Integer,
    func,
    literal,
    select,
    text,
    tuple_,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.application.ports import ReviewableProduct
from app.catalog.public import lock_product_for_reviews, set_review_aggregates
from app.engagement.domain.exceptions import ReviewAlreadyExistsError
from app.engagement.domain.reviews import REVIEW_LOCK_NS, NewReview, Review
from app.engagement.infrastructure.models import ReviewModel

_R = ReviewModel
_COLUMNS = (
    _R.id,
    _R.user_id,
    _R.product_id,
    _R.rating,
    _R.body,
    _R.is_verified_purchase,
    _R.is_hidden,
    _R.hidden_at,
    _R.deleted_at,
    _R.created_at,
    _R.updated_at,
)
_LIVE = _R.deleted_at.is_(None)
# Bare NOT, not IS FALSE, so the planner matches ix_reviews_product_visible.
_VISIBLE = ~_R.is_hidden


def _to_domain(row: Any) -> Review:
    return Review(
        id=row.id,
        user_id=row.user_id,
        product_id=row.product_id,
        rating=row.rating,
        body=row.body,
        is_verified_purchase=row.is_verified_purchase,
        is_hidden=row.is_hidden,
        hidden_at=row.hidden_at,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _before(after: tuple[datetime, UUID]) -> Any:
    created_at, review_id = after
    return tuple_(_R.created_at, _R.id) < tuple_(
        literal(created_at, DateTime(timezone=True)),
        literal(review_id, postgresql.UUID(as_uuid=True)),
    )


async def lock_review_user(session: AsyncSession, user_id: UUID) -> None:
    """`R_user`: re-entrant within the transaction, released at COMMIT or ROLLBACK."""
    await session.execute(
        select(func.pg_advisory_xact_lock(REVIEW_LOCK_NS, func.hashtext(str(user_id))))
    )


class SqlReviewStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_user(self, user_id: UUID) -> None:
        await lock_review_user(self._session, user_id)

    async def live_for(self, user_id: UUID, product_id: UUID) -> Review | None:
        stmt = select(*_COLUMNS).where(_R.user_id == user_id, _R.product_id == product_id, _LIVE)
        row = (await self._session.execute(stmt)).one_or_none()
        return None if row is None else _to_domain(row)

    async def own_product_id(self, review_id: UUID, user_id: UUID) -> UUID | None:
        stmt = select(_R.product_id).where(_R.id == review_id, _R.user_id == user_id, _LIVE)
        return await self._session.scalar(stmt)

    async def get_own_for_update(self, review_id: UUID, user_id: UUID) -> Review | None:
        stmt = (
            select(*_COLUMNS)
            .where(_R.id == review_id, _R.user_id == user_id, _LIVE)
            .with_for_update()
        )
        row = (await self._session.execute(stmt)).one_or_none()
        return None if row is None else _to_domain(row)

    async def insert(self, new: NewReview) -> Review:
        """The live unique index is the arbiter; a conflict inserts nothing (D8 backstop)."""
        stmt = (
            postgresql.insert(_R)
            .values(
                user_id=new.user_id,
                product_id=new.product_id,
                rating=new.rating,
                body=new.body,
                is_verified_purchase=new.is_verified_purchase,
            )
            .on_conflict_do_nothing(
                index_elements=[_R.user_id, _R.product_id], index_where=text("deleted_at IS NULL")
            )
            .returning(*_COLUMNS)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            raise ReviewAlreadyExistsError(new.product_id)
        return _to_domain(row)

    async def update(
        self, review_id: UUID, *, rating: int, body: str | None, verified: bool
    ) -> Review:
        stmt = (
            update(_R)
            .where(_R.id == review_id)
            .values(
                rating=rating,
                body=body,
                is_verified_purchase=verified,
                updated_at=func.clock_timestamp(),
            )
            .returning(*_COLUMNS)
            .execution_options(synchronize_session=False)
        )
        return _to_domain((await self._session.execute(stmt)).one())

    async def soft_delete(self, review_id: UUID) -> None:
        await self._session.execute(
            update(_R)
            .where(_R.id == review_id)
            .values(deleted_at=func.clock_timestamp(), updated_at=func.clock_timestamp())
            .execution_options(synchronize_session=False)
        )

    async def visible_totals(self, product_id: UUID) -> tuple[int, int]:
        stmt = select(func.coalesce(func.sum(_R.rating), 0).cast(Integer), func.count()).where(
            _R.product_id == product_id, _LIVE, _VISIBLE
        )
        ratings_sum, count = (await self._session.execute(stmt)).one()
        return int(ratings_sum), int(count)

    async def lock_live_for_products(
        self, user_id: UUID, product_ids: Sequence[UUID]
    ) -> list[tuple[UUID, UUID]]:
        """(id, product_id) of the live reviews, FOR UPDATE in id order (plan 3.2b step 2)."""
        stmt = (
            select(_R.id, _R.product_id)
            .where(_R.user_id == user_id, _R.product_id.in_(list(product_ids)), _LIVE)
            .order_by(_R.id)
            .with_for_update()
        )
        return [(row.id, row.product_id) for row in (await self._session.execute(stmt)).all()]

    async def set_verified(self, review_ids: Sequence[UUID], true_product_ids: set[UUID]) -> None:
        """Only rows whose value changes; `updated_at` stays the author's edit time."""
        verified = _R.product_id.in_(list(true_product_ids)) if true_product_ids else literal(False)
        await self._session.execute(
            update(_R)
            .where(_R.id.in_(list(review_ids)), _R.is_verified_purchase.is_distinct_from(verified))
            .values(is_verified_purchase=verified)
            .execution_options(synchronize_session=False)
        )

    async def public_page(
        self,
        product_id: UUID,
        *,
        rating: int | None,
        verified: bool | None,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[Review]:
        """Visible rows only. `verified` filters the stored flag; the caller applies D14."""
        stmt = select(*_COLUMNS).where(_R.product_id == product_id, _LIVE, _VISIBLE)
        if rating is not None:
            stmt = stmt.where(_R.rating == rating)
        if verified is not None:
            stmt = stmt.where(_R.is_verified_purchase.is_(verified))
        if after is not None:
            stmt = stmt.where(_before(after))
        stmt = stmt.order_by(_R.created_at.desc(), _R.id.desc()).limit(limit)
        return [_to_domain(row) for row in (await self._session.execute(stmt)).all()]

    async def own_page(
        self, user_id: UUID, *, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[Review]:
        """Live rows, hidden ones included, newest first."""
        stmt = select(*_COLUMNS).where(_R.user_id == user_id, _LIVE)
        if after is not None:
            stmt = stmt.where(_before(after))
        stmt = stmt.order_by(_R.created_at.desc(), _R.id.desc()).limit(limit)
        return [_to_domain(row) for row in (await self._session.execute(stmt)).all()]

    async def all_for_user(self, user_id: UUID) -> list[Review]:
        stmt = select(*_COLUMNS).where(_R.user_id == user_id).order_by(_R.created_at, _R.id)
        return [_to_domain(row) for row in (await self._session.execute(stmt)).all()]

    async def lock_for_moderation(self, review_id: UUID) -> Review | None:
        stmt = select(*_COLUMNS).where(_R.id == review_id).with_for_update()
        row = (await self._session.execute(stmt)).one_or_none()
        return None if row is None else _to_domain(row)

    async def set_hidden(self, review_id: UUID, *, hidden: bool, at: datetime) -> None:
        await self._session.execute(
            update(_R)
            .where(_R.id == review_id)
            .values(is_hidden=hidden, hidden_at=at if hidden else None)
            .execution_options(synchronize_session=False)
        )


class CatalogReviewableProducts:
    """`ReviewableProducts` over `app.catalog.public`, bound to the review's session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock(self, product_id: UUID) -> ReviewableProduct | None:
        return await lock_product_for_reviews(self._session, product_id)

    async def set_rating(self, product_id: UUID, average: Decimal, count: int) -> None:
        await set_review_aggregates(self._session, product_id, average, count)
