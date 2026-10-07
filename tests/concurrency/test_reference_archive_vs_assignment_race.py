"""FR-04: archiving a category/material/colour racing a product assigned to it.
Never both: either the product lands and the archive gets ReferenceValueInUseError,
or the archive lands and the product write gets ReferenceValueUnusableError."""

import asyncio
import uuid
from dataclasses import replace
from typing import Any, Literal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.application.commands.category_admin import ArchiveCategory
from app.catalog.application.commands.product_admin import CreateProduct, UpdateProduct
from app.catalog.application.commands.value_admin import ArchiveReferenceValue
from app.catalog.domain.entities import Colour, Material
from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.domain.exceptions import ReferenceValueInUseError, ReferenceValueUnusableError
from app.catalog.domain.product import Product, ProductAttributes
from app.catalog.infrastructure.models import (
    CategoryModel,
    ColourModel,
    MaterialModel,
    ProductModel,
)
from app.catalog.infrastructure.product_repository import ProductRepository
from app.catalog.infrastructure.repositories import (
    CategoryRepository,
    ColourRepository,
    MaterialRepository,
    SqlReferenceLocks,
)
from app.identity.infrastructure.models import UserModel
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import register, retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail

Field = Literal["category_id", "material_id", "colour_id"]
FIELDS: list[Field] = ["category_id", "material_id", "colour_id"]
ReferenceModel = type[CategoryModel] | type[MaterialModel] | type[ColourModel]
MODELS: dict[str, ReferenceModel] = {
    "category_id": CategoryModel,
    "material_id": MaterialModel,
    "colour_id": ColourModel,
}
ITERATIONS = 3


async def _seed(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    async with factory() as db, db.begin():
        user = UserModel(email=f"race-{uuid.uuid4().hex}@example.com", password_hash="x")
        rows: dict[str, CategoryModel | MaterialModel | ColourModel] = {
            "category_id": CategoryModel(
                name=f"zzz-vs013-{uuid.uuid4().hex}", slug=f"c-{uuid.uuid4().hex[:12]}"
            ),
            "material_id": MaterialModel(name=f"zzz-vs013-m-{uuid.uuid4().hex}"),
            "colour_id": ColourModel(name=f"zzz-vs013-c-{uuid.uuid4().hex}"),
        }
        db.add_all([user, *rows.values()])
        await db.flush()
        register(*(row.id for row in rows.values()))
        return user.id, {key: row.id for key, row in rows.items()}


def _one(field: str, value: uuid.UUID) -> dict[str, Any]:
    return {field: value}


def _attrs(refs: dict[str, uuid.UUID]) -> ProductAttributes:
    return ProductAttributes(
        category_id=refs["category_id"],
        material_id=refs["material_id"],
        colour_id=refs["colour_id"],
        name="Lamp",
        slug=f"p-{uuid.uuid4().hex[:12]}",
        price_cents=100,
        purchase_mode=PurchaseMode.ONLINE_ONLY,
        production_lead_time_days=1,
        batch_size=1,
        max_quantity_per_line=1,
    )


async def _archive(db: AsyncSession, field: Field, value_id: uuid.UUID, actor: uuid.UUID) -> None:
    audit = SqlAuditWriter(db)
    if field == "category_id":
        await ArchiveCategory(CategoryRepository(db), audit).execute(
            category_id=value_id, actor_user_id=actor, request_id=None, ip_hash=None
        )
    elif field == "material_id":
        await ArchiveReferenceValue[Material](
            MaterialRepository(db), audit, entity_type="Material"
        ).execute(value_id=value_id, actor_user_id=actor, request_id=None, ip_hash=None)
    else:
        await ArchiveReferenceValue[Colour](
            ColourRepository(db), audit, entity_type="Colour"
        ).execute(value_id=value_id, actor_user_id=actor, request_id=None, ip_hash=None)


async def _archive_racer(
    factory: async_sessionmaker[AsyncSession],
    field: Field,
    value_id: uuid.UUID,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
    *,
    lock_first: bool,
) -> BaseException | None:
    try:
        async with factory() as db, db.begin():
            model = MODELS[field]
            stmt = select(model.id).where(model.id == value_id)
            await db.execute(stmt.with_for_update() if lock_first else stmt)
            await meet_or_fail(barrier)
            await _archive(db, field, value_id, actor)
    except Exception as exc:
        return exc
    return None


async def _product_racer(
    factory: async_sessionmaker[AsyncSession],
    field: Field,
    value_id: uuid.UUID,
    refs: dict[str, uuid.UUID],
    existing: Product | None,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
    *,
    lock_first: bool,
) -> BaseException | None:
    try:
        async with factory() as db, db.begin():
            locks = SqlReferenceLocks(db)
            if lock_first:
                assert await locks.lock_live(field, value_id)
            else:
                await db.execute(select(ProductModel.id).limit(0))
            await meet_or_fail(barrier)
            args = (ProductRepository(db), locks, SqlAuditWriter(db))
            if existing is None:
                await CreateProduct(*args).execute(
                    product_type=ProductType.PHYSICAL,
                    attributes=replace(_attrs(refs), **_one(field, value_id)),
                    actor_user_id=actor,
                    request_id=None,
                    ip_hash=None,
                )
            else:
                await UpdateProduct(*args).execute(
                    product_id=existing.id,
                    expected_version=existing.version,
                    changes={field: value_id},
                    actor_user_id=actor,
                    request_id=None,
                    ip_hash=None,
                )
    except Exception as exc:
        return exc
    return None


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("operation", ["create", "patch"])
@pytest.mark.parametrize("first", ["product", "archive"])
async def test_an_archive_and_an_assignment_never_both_succeed(
    db_engine: AsyncEngine, field: Field, operation: str, first: str
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    for _ in range(ITERATIONS):
        actor, target = await _seed(factory)
        _, spare = await _seed(factory)
        existing = None
        if operation == "patch":
            async with factory() as db, db.begin():
                existing = await CreateProduct(
                    ProductRepository(db), SqlReferenceLocks(db), SqlAuditWriter(db)
                ).execute(
                    product_type=ProductType.PHYSICAL,
                    attributes=_attrs(spare),
                    actor_user_id=actor,
                    request_id=None,
                    ip_hash=None,
                )
        barrier = asyncio.Barrier(2)
        product_error, archive_error = await asyncio.gather(
            _product_racer(
                factory,
                field,
                target[field],
                target if existing is None else spare,
                existing,
                actor,
                barrier,
                lock_first=first == "product",
            ),
            _archive_racer(
                factory, field, target[field], actor, barrier, lock_first=first == "archive"
            ),
        )

        if first == "product":
            assert product_error is None, product_error
            assert isinstance(archive_error, ReferenceValueInUseError), archive_error
        else:
            assert archive_error is None, archive_error
            assert isinstance(product_error, ReferenceValueUnusableError), product_error

        model = MODELS[field]
        column = getattr(ProductModel, field)
        async with factory() as db:
            archived = await db.scalar(
                select(model.deleted_at.is_not(None)).where(model.id == target[field])
            )
            orphans = await db.scalar(
                select(ProductModel.id).where(
                    column == target[field], ProductModel.deleted_at.is_(None)
                )
            )
        assert not (archived and orphans), "a live product references an archived value"
