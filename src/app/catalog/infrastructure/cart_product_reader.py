from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.storefront import CartProduct
from app.catalog.infrastructure.models import CategoryModel, ProductImageModel, ProductModel
from app.catalog.infrastructure.product_image_repository import _to_domain as _image
from app.catalog.infrastructure.visibility import listed_predicate

_P = ProductModel


class SqlCartProductReader:
    """`CartProductReader` (VS-022 plan §3.1): one query per batch. `listed` is selected,
    not filtered on, so a line whose product went non-public still gets its name."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many(self, product_ids: Sequence[UUID]) -> dict[UUID, CartProduct]:
        ids = list(dict.fromkeys(product_ids))
        if not ids:
            return {}
        # At most one live cover per product (`ix_product_images_live_cover`).
        cover_join = and_(
            ProductImageModel.product_id == _P.id,
            ProductImageModel.is_cover,
            ProductImageModel.deleted_at.is_(None),
        )
        stmt = (
            select(
                _P.id,
                _P.type,
                _P.name,
                _P.slug,
                _P.price_cents,
                _P.currency,
                _P.purchase_mode,
                _P.is_available,
                _P.max_quantity_per_line,
                listed_predicate().label("listed"),
                ProductImageModel,
            )
            .join(CategoryModel, CategoryModel.id == _P.category_id)
            .outerjoin(ProductImageModel, cover_join)
            .where(_P.id.in_(ids))
        )
        rows = (await self._session.execute(stmt)).all()
        return {
            row.id: CartProduct(
                id=row.id,
                type=row.type,
                name=row.name,
                slug=row.slug,
                price_cents=row.price_cents,
                currency=row.currency,
                purchase_mode=row.purchase_mode,
                is_available=row.is_available,
                max_quantity_per_line=row.max_quantity_per_line,
                listed=bool(row.listed),
                cover=_image(row.ProductImageModel) if row.ProductImageModel else None,
            )
            for row in rows
        }
