from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Row, Select, literal, select, tuple_
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.catalog.domain.storefront import (
    CategoryRef,
    CursorKey,
    FacetRef,
    StorefrontFilter,
    StorefrontProduct,
    StorefrontSort,
)
from app.catalog.infrastructure.models import (
    CategoryModel,
    ColourModel,
    MaterialModel,
    ProductModel,
)
from app.catalog.infrastructure.product_repository import _to_domain

_Page = Select[ProductModel, CategoryModel, MaterialModel, ColourModel]
SORT_COLUMNS: dict[StorefrontSort, Any] = {
    "price": ProductModel.price_cents,
    "-price": ProductModel.price_cents,
    "-average_rating": ProductModel.average_rating,
    "-created_at": ProductModel.created_at,
}

# SRS 6.5. Bare `is_visible`, not `IS TRUE`, so the planner matches the partial indexes.
_VISIBLE: tuple[ColumnElement[bool], ...] = (
    ProductModel.deleted_at.is_(None),
    ProductModel.is_visible.expression,
    CategoryModel.deleted_at.is_(None),
    CategoryModel.is_active.expression,
)


def _base() -> _Page:
    return (
        select(ProductModel, CategoryModel, MaterialModel, ColourModel)
        .join(CategoryModel, CategoryModel.id == ProductModel.category_id)
        .outerjoin(MaterialModel, MaterialModel.id == ProductModel.material_id)
        .outerjoin(ColourModel, ColourModel.id == ProductModel.colour_id)
        .where(*_VISIBLE)
        .options(defer(ProductModel.search_vector))
    )


def _filtered(stmt: _Page, filters: StorefrontFilter) -> _Page:
    exact = {
        ProductModel.type: filters.product_type,
        ProductModel.category_id: filters.category_id,
        ProductModel.material_id: filters.material_id,
        ProductModel.colour_id: filters.colour_id,
        ProductModel.is_featured: filters.featured,
    }
    for column, value in exact.items():
        if value is not None:
            stmt = stmt.where(column == value)
    if filters.price_min_cents is not None:
        stmt = stmt.where(ProductModel.price_cents >= filters.price_min_cents)
    if filters.price_max_cents is not None:
        stmt = stmt.where(ProductModel.price_cents <= filters.price_max_cents)
    if filters.min_rating is not None:
        stmt = stmt.where(ProductModel.average_rating >= filters.min_rating)
    return stmt


def _to_storefront(
    row: Row[ProductModel, CategoryModel, MaterialModel, ColourModel],
) -> StorefrontProduct:
    product, category, material, colour = row
    return StorefrontProduct(
        product=_to_domain(product),
        category=CategoryRef(category.id, category.name, category.slug),
        material=FacetRef(material.id, material.name) if material else None,
        colour=FacetRef(colour.id, colour.name) if colour else None,
    )


def page_statement(
    *,
    limit: int,
    sort: StorefrontSort,
    filters: StorefrontFilter,
    after: tuple[CursorKey, UUID] | None = None,
) -> _Page:
    """Keyset page tie-broken by `id`, so inserts never duplicate or skip a row."""
    stmt = _filtered(_base(), filters)
    column = SORT_COLUMNS[sort]
    descending = sort.startswith("-")
    if after is not None:
        key, after_id = after
        pair = tuple_(column, ProductModel.id)
        bound = tuple_(literal(key), literal(after_id, postgresql.UUID(as_uuid=True)))
        # The redundant single-column bound is one the browse indexes can seek on.
        if descending:
            stmt = stmt.where(column <= key, pair < bound)
        else:
            stmt = stmt.where(column >= key, pair > bound)
    order = (column.desc(), ProductModel.id.desc()) if descending else (column, ProductModel.id)
    return stmt.order_by(*order).limit(limit)


class StorefrontProductQuery:
    """Read-only: the storefront never writes, so it takes no locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_page(
        self,
        *,
        limit: int,
        sort: StorefrontSort,
        filters: StorefrontFilter,
        after: tuple[CursorKey, UUID] | None = None,
    ) -> list[StorefrontProduct]:
        stmt = page_statement(limit=limit, sort=sort, filters=filters, after=after)
        return [_to_storefront(row) for row in (await self._session.execute(stmt)).all()]

    async def get_by_slug(self, slug: str) -> StorefrontProduct | None:
        stmt = _base().where(ProductModel.slug == slug)
        row = (await self._session.execute(stmt)).one_or_none()
        return _to_storefront(row) if row else None
