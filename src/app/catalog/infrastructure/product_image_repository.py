from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.product_image import ProductImage
from app.catalog.infrastructure.models import ProductImageModel


def _to_domain(model: ProductImageModel) -> ProductImage:
    return ProductImage(
        id=model.id,
        product_id=model.product_id,
        storage_key=model.storage_key,
        alt_text=model.alt_text,
        sort_order=model.sort_order,
        is_cover=model.is_cover,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
    )


_ORDER = (ProductImageModel.sort_order, ProductImageModel.created_at, ProductImageModel.id)


class ProductImageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def live_for_product(self, product_id: UUID) -> list[ProductImage]:
        return (await self.live_for_products([product_id]))[product_id]

    async def live_for_products(
        self, product_ids: Iterable[UUID]
    ) -> dict[UUID, list[ProductImage]]:
        """One query for a whole page of products, so listing is not N+1."""
        ids = list(product_ids)
        found: dict[UUID, list[ProductImage]] = defaultdict(list)
        if ids:
            stmt = (
                select(ProductImageModel)
                .where(
                    ProductImageModel.product_id.in_(ids), ProductImageModel.deleted_at.is_(None)
                )
                .order_by(ProductImageModel.product_id, *_ORDER)
                .execution_options(populate_existing=True)
            )
            for model in await self._session.scalars(stmt):
                found[model.product_id].append(_to_domain(model))
        return {product_id: found[product_id] for product_id in ids}

    async def add(
        self,
        *,
        product_id: UUID,
        storage_key: str,
        alt_text: str | None,
        sort_order: int,
        is_cover: bool,
    ) -> ProductImage:
        model = ProductImageModel(
            product_id=product_id,
            storage_key=storage_key,
            alt_text=alt_text,
            sort_order=sort_order,
            is_cover=is_cover,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _to_domain(model)

    async def save(self, images: list[ProductImage]) -> None:
        for image in images:
            model = await self._session.get(ProductImageModel, image.id)
            if model is None:
                raise ValueError(f"ProductImage {image.id} not found")
            model.alt_text = image.alt_text
            model.sort_order = image.sort_order
            model.is_cover = image.is_cover
            model.deleted_at = image.deleted_at
            model.updated_at = image.updated_at
            await self._session.flush()

    async def referenced_keys(self, keys: list[str]) -> set[str]:
        """Keys any row holds, deleted rows included: their files stay (BR-033)."""
        if not keys:
            return set()
        stmt = select(ProductImageModel.storage_key).where(ProductImageModel.storage_key.in_(keys))
        return set(await self._session.scalars(stmt))
