"""Catalog's reporting reads (VS-043). Unlocked, read-only; no visibility filter, as the
wishlist analytics (plan 5.8): a hidden product is listed and flagged."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.infrastructure.models import ProductModel

_P = ProductModel


@dataclass(frozen=True)
class RatedProductRow:
    product_id: UUID
    name: str
    slug: str
    type: str
    average_rating: Decimal
    review_count: int
    is_visible: bool


@dataclass(frozen=True)
class ProductLabelRow:
    name: str
    slug: str | None


async def top_rated_products(
    session: AsyncSession, *, limit: int, min_reviews: int
) -> list[RatedProductRow]:
    """Live products with at least `min_reviews`, by the maintained aggregates (VS-036)."""
    query = (
        select(
            _P.id,
            _P.name,
            _P.slug,
            _P.type,
            _P.average_rating,
            _P.review_count,
            _P.is_visible,
        )
        .where(_P.deleted_at.is_(None), _P.review_count >= min_reviews)
        .order_by(_P.average_rating.desc(), _P.review_count.desc(), _P.id)
        .limit(limit)
    )
    return [
        RatedProductRow(pid, name, slug, str(kind), rating, count, visible)
        for pid, name, slug, kind, rating, count, visible in (await session.execute(query)).tuples()
    ]


async def product_labels(
    session: AsyncSession, product_ids: Sequence[UUID]
) -> dict[UUID, ProductLabelRow]:
    """Today's name; the slug only while the product is live."""
    if not product_ids:
        return {}
    query = select(_P.id, _P.name, _P.slug, _P.deleted_at).where(_P.id.in_(list(product_ids)))
    return {
        pid: ProductLabelRow(name, slug if deleted is None else None)
        for pid, name, slug, deleted in (await session.execute(query)).tuples()
    }
