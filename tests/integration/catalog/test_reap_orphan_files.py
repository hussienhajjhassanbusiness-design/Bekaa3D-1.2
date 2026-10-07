"""SRS 23 `reap_orphan_files`: storage writes are not transactional with Postgres, so a
failed commit leaves a file no row knows about; the reaper removes it after 24 h."""

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import time_machine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.application.commands.product_image_admin import UploadProductImage
from app.catalog.infrastructure.models import CategoryModel, ProductModel
from app.catalog.infrastructure.product_image_repository import ProductImageRepository
from app.catalog.infrastructure.product_repository import ProductRepository
from app.identity.infrastructure.models import UserModel
from app.integrations.images.pillow import PillowImageSanitizer
from app.integrations.scanning.fake import FakeScanner
from app.integrations.storage.local import LocalStorage
from app.jobs.reap_orphan_files import GRACE_PERIOD, reap
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import register, retire_seeded_catalog_values  # noqa: F401
from tests.image_samples import sample

pytestmark = pytest.mark.integration

WRITTEN_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class _CommitFailedError(Exception):
    pass


async def _seed(factory: async_sessionmaker[AsyncSession]) -> tuple[uuid.UUID, uuid.UUID]:
    async with factory() as db, db.begin():
        user = UserModel(email=f"reap-{uuid.uuid4().hex}@example.com", password_hash="x")
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
        return user.id, product.id


async def _upload(
    factory: async_sessionmaker[AsyncSession],
    storage: LocalStorage,
    product: uuid.UUID,
    actor: uuid.UUID,
) -> str:
    async with factory() as db, db.begin():
        image = await UploadProductImage(
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
        return image.storage_key


def _age(root: Path, key: str) -> None:
    stamp = WRITTEN_AT.timestamp()
    os.utime(root / key, (stamp, stamp))


@pytest.fixture
def factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def _orphan_from_a_failed_commit(
    factory: async_sessionmaker[AsyncSession], storage: LocalStorage
) -> str:
    """The file is written, then the transaction that held its row rolls back."""
    actor, product = await _seed(factory)
    written: list[str] = []
    with pytest.raises(_CommitFailedError):
        async with factory() as db, db.begin():
            image = await UploadProductImage(
                ProductRepository(db),
                ProductImageRepository(db),
                SqlAuditWriter(db),
                storage=storage,
                scanner=FakeScanner(),
                sanitizer=PillowImageSanitizer(),
            ).execute(
                product_id=product,
                data=sample("PNG"),
                alt_text=None,
                actor_user_id=actor,
                request_id=None,
                ip_hash=None,
            )
            written.append(image.storage_key)
            raise _CommitFailedError
    async with factory() as db:
        assert await ProductImageRepository(db).referenced_keys(written) == set()
    return written[0]


@pytest.mark.parametrize(
    ("offset", "reaped"),
    [(timedelta(seconds=-1), False), (timedelta(0), True), (timedelta(seconds=1), True)],
    ids=["grace-minus-1s", "exactly-at-grace", "grace-plus-1s"],
)
async def test_an_orphan_from_a_failed_commit_is_reaped_after_the_grace_period(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path, offset: timedelta, reaped: bool
) -> None:
    """Done-when: orphan files are cleaned up (FR-04 failure behaviour)."""
    storage = LocalStorage(tmp_path)
    key = await _orphan_from_a_failed_commit(factory, storage)
    _age(tmp_path, key)
    with time_machine.travel(WRITTEN_AT + GRACE_PERIOD + offset, tick=False):
        removed = await reap(storage, factory, datetime.now(UTC))
    assert (key in removed) is reaped
    assert (tmp_path / key).exists() is not reaped


async def test_files_of_live_and_deleted_images_are_kept_however_old(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """Soft-deleted rows still reference their file (BR-018, BR-033)."""
    storage = LocalStorage(tmp_path)
    actor, product = await _seed(factory)
    live = await _upload(factory, storage, product, actor)
    deleted = await _upload(factory, storage, product, actor)
    async with factory() as db, db.begin():
        images = await ProductImageRepository(db).live_for_product(product)
        doomed = next(i for i in images if i.storage_key == deleted)
        doomed.deleted_at = doomed.updated_at
        await ProductImageRepository(db).save([doomed])
    stray = f"products/{uuid.uuid4()}.webp"
    await storage.put(stray, b"leftover")
    for key in (live, deleted, stray):
        _age(tmp_path, key)

    removed = await reap(storage, factory, WRITTEN_AT + GRACE_PERIOD * 30)

    assert removed == [stray]
    assert (tmp_path / live).exists() and (tmp_path / deleted).exists()


async def test_files_outside_the_products_prefix_are_never_touched(
    factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    storage = LocalStorage(tmp_path)
    await storage.put("other/keep.txt", b"not ours")
    _age(tmp_path, "other/keep.txt")
    assert await reap(storage, factory, WRITTEN_AT + GRACE_PERIOD * 30) == []
    assert (tmp_path / "other" / "keep.txt").exists()
