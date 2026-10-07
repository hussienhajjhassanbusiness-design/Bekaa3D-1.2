"""VS-014 races. Every image command row-locks the product, so cover, order and the
image cap are decided one transaction at a time; without the lock these fail."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.application.commands.product_image_admin import (
    SetProductCover,
    UploadProductImage,
)
from app.catalog.domain.exceptions import UploadRejectedError
from app.catalog.domain.product_image import MAX_IMAGES_PER_PRODUCT
from app.catalog.infrastructure.models import CategoryModel, ProductImageModel, ProductModel
from app.catalog.infrastructure.product_image_repository import ProductImageRepository
from app.catalog.infrastructure.product_repository import ProductRepository
from app.identity.infrastructure.models import UserModel
from app.integrations.images.pillow import PillowImageSanitizer
from app.integrations.scanning.fake import FakeScanner
from app.integrations.storage.local import LocalStorage
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import register, retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.image_samples import sample

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]
ITERATIONS = 3
Factory = async_sessionmaker[AsyncSession]


async def _seed(factory: Factory, images: int) -> tuple[uuid.UUID, uuid.UUID, list[uuid.UUID]]:
    """A product with `images` rows (the first is the cover); no files needed."""
    async with factory() as db, db.begin():
        user = UserModel(email=f"race-{uuid.uuid4().hex}@example.com", password_hash="x")
        category = CategoryModel(
            name=f"zzz-vs014-{uuid.uuid4().hex}", slug=f"c-{uuid.uuid4().hex[:12]}"
        )
        db.add_all([user, category])
        await db.flush()
        register(category.id)
        product = ProductModel(
            type="stl",
            category_id=category.id,
            name="p",
            slug=f"p-{uuid.uuid4().hex[:12]}",
            price_cents=1,
        )
        db.add(product)
        await db.flush()
        repo = ProductImageRepository(db)
        ids = [
            (
                await repo.add(
                    product_id=product.id,
                    storage_key=f"products/{uuid.uuid4()}.jpg",
                    alt_text=None,
                    sort_order=n,
                    is_cover=n == 0,
                )
            ).id
            for n in range(images)
        ]
        return user.id, product.id, ids


async def _race(
    factory: Factory, work: list[Callable[[AsyncSession], Awaitable[object]]]
) -> list[BaseException | None]:
    barrier = asyncio.Barrier(len(work))

    async def one(job: Callable[[AsyncSession], Awaitable[object]]) -> BaseException | None:
        try:
            async with factory() as db, db.begin():
                await db.execute(select(ProductModel.id).limit(0))
                await meet_or_fail(barrier)
                await job(db)
        except Exception as exc:
            return exc
        return None

    return list(await asyncio.gather(*(one(job) for job in work)))


async def _live(factory: Factory, product: uuid.UUID) -> list[ProductImageModel]:
    async with factory() as db:
        stmt = select(ProductImageModel).where(
            ProductImageModel.product_id == product, ProductImageModel.deleted_at.is_(None)
        )
        return list(await db.scalars(stmt))


def _upload(
    storage: LocalStorage, product: uuid.UUID, actor: uuid.UUID
) -> Callable[[AsyncSession], Awaitable[object]]:
    async def job(db: AsyncSession) -> object:
        return await UploadProductImage(
            ProductRepository(db),
            ProductImageRepository(db),
            SqlAuditWriter(db),
            storage=storage,
            scanner=FakeScanner(),
            sanitizer=PillowImageSanitizer(),
        ).execute(
            product_id=product,
            data=sample("JPEG"),
            alt_text=None,
            actor_user_id=actor,
            request_id=None,
            ip_hash=None,
        )

    return job


def _cover(
    product: uuid.UUID, image: uuid.UUID, actor: uuid.UUID
) -> Callable[[AsyncSession], Awaitable[object]]:
    async def job(db: AsyncSession) -> object:
        return await SetProductCover(
            ProductRepository(db), ProductImageRepository(db), SqlAuditWriter(db)
        ).execute(
            product_id=product, image_id=image, actor_user_id=actor, request_id=None, ip_hash=None
        )

    return job


async def test_concurrent_cover_changes_leave_exactly_one_cover(db_engine: AsyncEngine) -> None:
    """Done-when: a product never has two covers - and neither request fails."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    for _ in range(ITERATIONS):
        actor, product, (_, b, c) = await _seed(factory, 3)
        errors = await _race(factory, [_cover(product, b, actor), _cover(product, c, actor)])
        assert errors == [None, None], errors
        covers = [row.id for row in await _live(factory, product) if row.is_cover]
        assert len(covers) == 1 and covers[0] in {b, c}


async def test_concurrent_first_uploads_make_one_cover(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    for _ in range(ITERATIONS):
        actor, product, _ = await _seed(factory, 0)
        storage = LocalStorage(tmp_path)
        errors = await _race(factory, [_upload(storage, product, actor) for _ in range(2)])
        assert errors == [None, None], errors
        rows = await _live(factory, product)
        assert sorted(r.sort_order for r in rows) == [0, 1]
        assert sum(r.is_cover for r in rows) == 1


async def test_concurrent_uploads_never_exceed_the_cap(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    for _ in range(ITERATIONS):
        actor, product, _ = await _seed(factory, MAX_IMAGES_PER_PRODUCT - 1)
        storage = LocalStorage(tmp_path)
        errors = await _race(factory, [_upload(storage, product, actor) for _ in range(2)])
        assert errors.count(None) == 1, errors
        assert any(isinstance(e, UploadRejectedError) for e in errors), errors
        async with factory() as db:
            count = await db.scalar(
                select(func.count()).where(
                    ProductImageModel.product_id == product, ProductImageModel.deleted_at.is_(None)
                )
            )
        assert count == MAX_IMAGES_PER_PRODUCT
