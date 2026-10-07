"""FR-04 / ADR-020: two admins writing one product from the same `version`.
Both pass the version check before either writes, so only the conditional UPDATE
can stop the second: exactly one wins, the other writes nothing, audit included."""

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.application.commands.product_admin import (
    CreateProduct,
    DeleteProduct,
    UpdateProduct,
)
from app.catalog.domain.enums import ProductType
from app.catalog.domain.exceptions import VersionConflictError
from app.catalog.domain.product import Product, ProductAttributes
from app.catalog.infrastructure.models import CategoryModel, ProductModel
from app.catalog.infrastructure.product_repository import ProductRepository
from app.catalog.infrastructure.repositories import SqlReferenceLocks
from app.identity.infrastructure.models import UserModel
from app.platform.infrastructure.models import AuditLogModel
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import register, retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail


class _MeetBeforeSave(ProductRepository):
    """Holds each racer after its version check and before its write."""

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def save_if_version(self, product: Product, expected_version: int) -> Product | None:
        await meet_or_fail(self._barrier)
        return await super().save_if_version(product, expected_version)


async def _seed(factory: async_sessionmaker[AsyncSession]) -> tuple[uuid.UUID, Product]:
    async with factory() as db, db.begin():
        user = UserModel(email=f"race-{uuid.uuid4().hex}@example.com", password_hash="x")
        category = CategoryModel(
            name=f"zzz-vs013-{uuid.uuid4().hex}", slug=f"c-{uuid.uuid4().hex[:12]}"
        )
        db.add_all([user, category])
        await db.flush()
        register(category.id)
        product = await CreateProduct(
            ProductRepository(db), SqlReferenceLocks(db), SqlAuditWriter(db)
        ).execute(
            product_type=ProductType.STL,
            attributes=ProductAttributes(
                category_id=category.id,
                name="Base",
                slug=f"p-{uuid.uuid4().hex[:12]}",
                price_cents=1,
            ),
            actor_user_id=user.id,
            request_id=None,
            ip_hash=None,
        )
        return user.id, product


async def _racer(
    factory: async_sessionmaker[AsyncSession],
    product: Product,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
    change: dict[str, Any] | None,
) -> tuple[str, BaseException | None]:
    label = "delete" if change is None else str(change["name"])
    try:
        async with factory() as db, db.begin():
            args = (_MeetBeforeSave(db, barrier), SqlReferenceLocks(db), SqlAuditWriter(db))
            common: dict[str, Any] = {
                "product_id": product.id,
                "expected_version": product.version,
                "actor_user_id": actor,
                "request_id": None,
                "ip_hash": None,
            }
            if change is None:
                await DeleteProduct(*args).execute(**common)
            else:
                await UpdateProduct(*args).execute(changes=change, **common)
    except Exception as exc:
        return label, exc
    return label, None


async def _audit_actions(
    factory: async_sessionmaker[AsyncSession], product_id: uuid.UUID
) -> list[str]:
    async with factory() as db:
        rows = await db.scalars(
            select(AuditLogModel.action).where(AuditLogModel.entity_id == product_id)
        )
        return sorted(rows)


@pytest.mark.integration
@pytest.mark.concurrency
async def test_two_patches_from_one_version_yield_one_winner_and_no_silent_overwrite(
    db_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor, product = await _seed(factory)
    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _racer(factory, product, actor, barrier, {"name": "Alice"}),
        _racer(factory, product, actor, barrier, {"name": "Bob"}),
    )

    winners = [label for label, error in outcomes if error is None]
    losers = [error for _, error in outcomes if error is not None]
    assert len(winners) == 1, outcomes
    assert len(losers) == 1, outcomes
    loser = losers[0]
    assert isinstance(loser, VersionConflictError), outcomes
    assert loser.current_version == 2

    async with factory() as db:
        row = await db.get(ProductModel, product.id)
    assert row is not None
    assert (row.name, row.version) == (winners[0], 2)
    assert await _audit_actions(factory, product.id) == ["product.created", "product.updated"]


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_patch_and_a_delete_from_one_version_yield_one_winner(
    db_engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor, product = await _seed(factory)
    barrier = asyncio.Barrier(2)
    outcomes = dict(
        await asyncio.gather(
            _racer(factory, product, actor, barrier, {"name": "Edited"}),
            _racer(factory, product, actor, barrier, None),
        )
    )

    assert sum(error is None for error in outcomes.values()) == 1, outcomes
    assert sum(isinstance(e, VersionConflictError) for e in outcomes.values()) == 1, outcomes
    async with factory() as db:
        row = await db.get(ProductModel, product.id)
    assert row is not None and row.version == 2
    if outcomes["delete"] is None:
        assert row.deleted_at is not None and row.name == "Base"
    else:
        assert row.deleted_at is None and row.name == "Edited"
    assert len(await _audit_actions(factory, product.id)) == 2
