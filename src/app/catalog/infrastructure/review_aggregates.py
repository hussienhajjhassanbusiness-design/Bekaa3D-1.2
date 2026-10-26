"""The product side of reviews (VS-036 plan 3.4): the aggregate lock, its writer, and the
public list's slug lookup. Aggregates bump neither `version` nor `updated_at` (ADR-020 d5)."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.reviewable import ReviewableProduct
from app.catalog.domain.slug import is_canonical_slug
from app.catalog.infrastructure.models import CategoryModel, ProductModel
from app.catalog.infrastructure.visibility import listed_predicate

_P = ProductModel


def _select() -> Any:
    return select(
        _P.id,
        _P.slug,
        _P.deleted_at.is_(None).label("live"),
        listed_predicate().label("visible"),
        _P.purchase_mode,
    ).join(CategoryModel, CategoryModel.id == _P.category_id)


def _to_domain(row: Any) -> ReviewableProduct:
    return ReviewableProduct(
        id=row.id,
        slug=row.slug,
        live=row.live,
        visible=row.visible,
        purchase_mode=row.purchase_mode,
    )


async def lock_product_for_reviews(
    session: AsyncSession, product_id: UUID
) -> ReviewableProduct | None:
    """`FOR NO KEY UPDATE OF products`: serialises aggregate writers, never blocks the
    reviews FK's key-share check; the category row is not locked."""
    stmt = _select().where(_P.id == product_id).with_for_update(of=_P, key_share=True)
    row = (await session.execute(stmt)).one_or_none()
    return None if row is None else _to_domain(row)


async def set_review_aggregates(
    session: AsyncSession, product_id: UUID, average: Decimal, count: int
) -> None:
    """Absolute values, under `lock_product_for_reviews` in the same transaction."""
    await session.execute(
        update(_P)
        .where(_P.id == product_id)
        .values(average_rating=average, review_count=count)
        .execution_options(synchronize_session=False)
    )


async def visible_product(session: AsyncSession, slug: str) -> ReviewableProduct | None:
    """`read_product`'s 404 rule: canonical slug, live and visible (SRS 6.5). No lock."""
    if not is_canonical_slug(slug):
        return None
    stmt = _select().where(_P.slug == slug, listed_predicate())
    row = (await session.execute(stmt)).one_or_none()
    return None if row is None else _to_domain(row)


async def reviewable_products(
    session: AsyncSession, product_ids: Sequence[UUID]
) -> dict[UUID, ReviewableProduct]:
    """One batched read for the D14 mask; no visibility filter. No lock."""
    if not product_ids:
        return {}
    stmt = _select().where(_P.id.in_(list(set(product_ids))))
    return {row.id: _to_domain(row) for row in (await session.execute(stmt)).all()}
