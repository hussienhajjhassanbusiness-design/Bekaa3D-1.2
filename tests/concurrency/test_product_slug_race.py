"""FR-04 / INV-13: two admins creating products with one slug at the same moment.
The live-slug index settles it: one product, one SlugConflictError, either order."""

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.application.commands.product_admin import CreateProduct
from app.catalog.domain.enums import ProductType
from app.catalog.domain.exceptions import SlugConflictError
from app.catalog.domain.product import ProductAttributes
from app.catalog.infrastructure.models import CategoryModel, ProductModel
from app.catalog.infrastructure.product_repository import ProductRepository
from app.catalog.infrastructure.repositories import SqlReferenceLocks
from app.identity.infrastructure.models import UserModel
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import register, retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail


async def _attempt(
    factory: async_sessionmaker[AsyncSession],
    attrs: ProductAttributes,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
) -> tuple[str, BaseException | None]:
    try:
        async with factory() as db, db.begin():
            await db.execute(select(ProductModel.id).limit(0))
            await meet_or_fail(barrier)
            await CreateProduct(
                ProductRepository(db), SqlReferenceLocks(db), SqlAuditWriter(db)
            ).execute(
                product_type=ProductType.STL,
                attributes=attrs,
                actor_user_id=actor,
                request_id=None,
                ip_hash=None,
            )
    except Exception as exc:
        return attrs.name, exc
    return attrs.name, None


@pytest.mark.integration
@pytest.mark.concurrency
async def test_two_admins_claiming_one_slug_produce_exactly_one_product(
    db_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db, db.begin():
        user = UserModel(email=f"race-{uuid.uuid4().hex}@example.com", password_hash="x")
        category = CategoryModel(
            name=f"zzz-vs013-{uuid.uuid4().hex}", slug=f"c-{uuid.uuid4().hex[:12]}"
        )
        db.add_all([user, category])
        await db.flush()
        register(category.id)
        actor, category_id = user.id, category.id
    slug = f"race-{uuid.uuid4().hex[:12]}"

    def attrs(name: str) -> ProductAttributes:
        return ProductAttributes(category_id=category_id, name=name, slug=slug, price_cents=1)

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _attempt(factory, attrs("first"), actor, barrier),
        _attempt(factory, attrs("second"), actor, barrier),
    )

    succeeded = [name for name, error in outcomes if error is None]
    rejected = [error for _, error in outcomes if error is not None]
    assert len(succeeded) == 1, outcomes
    assert len(rejected) == 1 and isinstance(rejected[0], SlugConflictError), outcomes
    async with factory() as db:
        live = list(
            await db.scalars(
                select(ProductModel.name).where(
                    ProductModel.slug == slug, ProductModel.deleted_at.is_(None)
                )
            )
        )
    assert live == succeeded
