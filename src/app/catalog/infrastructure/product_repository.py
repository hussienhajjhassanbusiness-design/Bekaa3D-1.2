from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Literal, NoReturn
from uuid import UUID

from sqlalchemy import Select, func, literal, literal_column, or_, select, tuple_, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.enums import ProductType
from app.catalog.domain.exceptions import SlugConflictError
from app.catalog.domain.product import (
    ENTITY_TYPE,
    Dimensions,
    Product,
    ProductAttributes,
    ProductDraft,
)
from app.catalog.infrastructure.models import ProductModel
from app.catalog.infrastructure.repositories import _violates

LIVE_SLUG_INDEX = frozenset({"ix_products_live_slug"})

ProductSort = Literal["-created_at", "price", "-price"]
SORT_COLUMNS = {
    "-created_at": ProductModel.created_at,
    "price": ProductModel.price_cents,
    "-price": ProductModel.price_cents,
}


@dataclass(frozen=True)
class ProductFilter:
    product_type: ProductType | None = None
    category_id: UUID | None = None
    is_visible: bool | None = None
    is_featured: bool | None = None
    is_available: bool | None = None
    deleted: bool = False
    q: str | None = None


def _columns(attrs: ProductAttributes) -> dict[str, Any]:
    out = {f.name: getattr(attrs, f.name) for f in fields(attrs)}
    if attrs.dimensions is not None:
        out["dimensions"] = attrs.dimensions.as_dict()
    return out


def _to_domain(model: ProductModel) -> Product:
    names = {f.name for f in fields(ProductAttributes)} - {"dimensions"}
    dims = model.dimensions
    attrs = ProductAttributes(
        **{name: getattr(model, name) for name in names},
        dimensions=Dimensions(**dims) if dims is not None else None,
    )
    return Product(
        id=model.id,
        type=model.type,
        attributes=attrs,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        average_rating=model.average_rating,
        review_count=model.review_count,
        wishlist_count=model.wishlist_count,
    )


def _translate(exc: IntegrityError, slug: str) -> NoReturn:
    if _violates(exc, LIVE_SLUG_INDEX):
        raise SlugConflictError(slug, ENTITY_TYPE) from exc
    raise exc


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, draft: ProductDraft) -> Product:
        model = ProductModel(type=draft.type, **_columns(draft.attributes))
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            _translate(exc, draft.attributes.slug)
        await self._session.refresh(model)
        return _to_domain(model)

    async def get_by_id(self, product_id: UUID) -> Product | None:
        model = await self._session.get(ProductModel, product_id, populate_existing=True)
        return _to_domain(model) if model else None

    async def save_if_version(self, product: Product, expected_version: int) -> Product | None:
        """`UPDATE ... WHERE version = :expected`: the row lock it takes re-checks the
        predicate after a concurrent writer commits, so exactly one stale writer loses."""
        stmt = (
            update(ProductModel)
            .where(ProductModel.id == product.id, ProductModel.version == expected_version)
            .values(
                **_columns(product.attributes),
                deleted_at=product.deleted_at,
                updated_at=product.updated_at,
                version=ProductModel.version + 1,
            )
            .returning(ProductModel)
            .execution_options(populate_existing=True, synchronize_session=False)
        )
        try:
            model = (await self._session.scalars(stmt)).one_or_none()
        except IntegrityError as exc:
            _translate(exc, product.attributes.slug)
        return _to_domain(model) if model else None

    async def get_for_update(self, product_id: UUID) -> Product | None:
        stmt = (
            select(ProductModel)
            .where(ProductModel.id == product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(stmt)
        return _to_domain(model) if model else None

    async def current_version(self, product_id: UUID) -> int | None:
        stmt = select(ProductModel.version).where(ProductModel.id == product_id)
        return await self._session.scalar(stmt)

    async def list_page(
        self,
        *,
        limit: int,
        sort: ProductSort,
        filters: ProductFilter,
        after: tuple[int | datetime, UUID] | None = None,
    ) -> list[Product]:
        stmt = self._filtered(filters)
        column = SORT_COLUMNS[sort]
        descending = sort.startswith("-")
        if after is not None:
            key, after_id = after
            pair = tuple_(column, ProductModel.id)
            bound = tuple_(literal(key), literal(after_id, postgresql.UUID(as_uuid=True)))
            stmt = stmt.where(pair < bound if descending else pair > bound)
        order = (column.desc(), ProductModel.id.desc()) if descending else (column, ProductModel.id)
        stmt = stmt.order_by(*order).limit(limit)
        return [_to_domain(m) for m in (await self._session.scalars(stmt)).all()]

    @staticmethod
    def _filtered(filters: ProductFilter) -> Select[ProductModel]:
        stmt = select(ProductModel)
        if filters.deleted:
            stmt = stmt.where(ProductModel.deleted_at.is_not(None))
        else:
            stmt = stmt.where(ProductModel.deleted_at.is_(None))
        exact = {
            ProductModel.type: filters.product_type,
            ProductModel.category_id: filters.category_id,
            ProductModel.is_visible: filters.is_visible,
            ProductModel.is_featured: filters.is_featured,
            ProductModel.is_available: filters.is_available,
        }
        for column, value in exact.items():
            if value is not None:
                stmt = stmt.where(column == value)
        if filters.q:
            query = func.websearch_to_tsquery(literal_column("'english'::regconfig"), filters.q)
            stmt = stmt.where(
                or_(
                    ProductModel.search_vector.op("@@")(query),
                    ProductModel.name.ilike(f"%{_escape_like(filters.q)}%", escape="\\"),
                )
            )
        return stmt
