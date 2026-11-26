"""Promotions persistence. Promotions are few (a handful of campaigns a year), so the
pricing read loads every currently active one with its product set in two queries and the
domain picks the one that applies per product (`apply_best`)."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.promotions import Promotion, PromotionFields
from app.catalog.infrastructure.models import (
    ProductModel,
    PromotionModel,
    PromotionProductModel,
)

ADMIN_LIST_LIMIT = 200

_P = PromotionModel


def _fields(row: PromotionModel, product_ids: Iterable[UUID]) -> PromotionFields:
    return PromotionFields(
        name=row.name,
        discount_type=row.discount_type,
        discount_value=row.discount_value,
        scope=row.scope,
        product_ids=frozenset(product_ids),
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        active=row.is_active,
        badge_text=row.badge_text,
    )


class SqlPromotions:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _products_of(self, promotion_ids: Sequence[UUID]) -> dict[UUID, set[UUID]]:
        found: dict[UUID, set[UUID]] = defaultdict(set)
        if not promotion_ids:
            return found
        stmt = select(PromotionProductModel.promotion_id, PromotionProductModel.product_id).where(
            PromotionProductModel.promotion_id.in_(promotion_ids)
        )
        for promotion_id, product_id in (await self._session.execute(stmt)).all():
            found[promotion_id].add(product_id)
        return found

    async def _hydrate(self, rows: Sequence[PromotionModel]) -> list[Promotion]:
        products = await self._products_of([r.id for r in rows])
        return [
            Promotion(
                id=r.id,
                fields=_fields(r, products.get(r.id, ())),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    async def list_recent(self, limit: int = ADMIN_LIST_LIMIT) -> list[Promotion]:
        stmt = select(_P).order_by(_P.created_at.desc(), _P.id.desc()).limit(limit)
        return await self._hydrate(list(await self._session.scalars(stmt)))

    async def get(self, promotion_id: UUID, *, for_update: bool = False) -> Promotion | None:
        stmt = select(_P).where(_P.id == promotion_id)
        if for_update:
            stmt = stmt.with_for_update()
        row = (await self._session.scalars(stmt)).one_or_none()
        return None if row is None else (await self._hydrate([row]))[0]

    async def active_at(self, now: datetime) -> list[Promotion]:
        """Every promotion applying at `now` (served by `ix_promotions_active_window`)."""
        stmt = (
            select(_P)
            .where(_P.is_active, _P.starts_at <= now, _P.ends_at > now)
            .order_by(_P.ends_at, _P.id)
        )
        return await self._hydrate(list(await self._session.scalars(stmt)))

    async def live_product_ids(self, product_ids: Iterable[UUID]) -> set[UUID]:
        """The ids, among these, of products that exist and are not deleted."""
        ids = list(product_ids)
        if not ids:
            return set()
        stmt = select(ProductModel.id).where(
            ProductModel.id.in_(ids), ProductModel.deleted_at.is_(None)
        )
        return set(await self._session.scalars(stmt))

    async def _replace_products(self, promotion_id: UUID, product_ids: frozenset[UUID]) -> None:
        await self._session.execute(
            delete(PromotionProductModel).where(PromotionProductModel.promotion_id == promotion_id)
        )
        self._session.add_all(
            PromotionProductModel(promotion_id=promotion_id, product_id=product_id)
            for product_id in sorted(product_ids)
        )

    async def create(self, fields: PromotionFields, now: datetime) -> Promotion:
        row = PromotionModel(
            name=fields.name,
            badge_text=fields.badge_text,
            discount_type=fields.discount_type,
            discount_value=fields.discount_value,
            scope=fields.scope,
            starts_at=fields.starts_at,
            ends_at=fields.ends_at,
            is_active=fields.active,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        await self._replace_products(row.id, fields.product_ids)
        await self._session.flush()
        return Promotion(id=row.id, fields=fields, created_at=now, updated_at=now)

    async def update(self, current: Promotion, fields: PromotionFields, now: datetime) -> Promotion:
        row = await self._session.get_one(PromotionModel, current.id)
        row.name = fields.name
        row.badge_text = fields.badge_text
        row.discount_type = fields.discount_type
        row.discount_value = fields.discount_value
        row.scope = fields.scope
        row.starts_at = fields.starts_at
        row.ends_at = fields.ends_at
        row.is_active = fields.active
        row.updated_at = now
        if fields.product_ids != current.fields.product_ids:
            await self._replace_products(current.id, fields.product_ids)
        await self._session.flush()
        return Promotion(
            id=current.id, fields=fields, created_at=current.created_at, updated_at=now
        )
