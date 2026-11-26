"""Helpers for the promotion suites. A promotion is global (an `all` one reprices every
product), so every promotion test empties both tables before and after itself: a leftover
row would change prices other suites assert."""

import uuid
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.promotions import DiscountType, PromotionScope
from app.catalog.infrastructure.models import PromotionModel, PromotionProductModel

ADMIN_PROMOTIONS = "/api/v1/admin/promotions"
PUBLIC_PROMOTIONS = "/api/v1/promotions"


async def _empty(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM promotion_products"))
        await conn.execute(text("DELETE FROM promotions"))


@pytest_asyncio.fixture
async def no_promotions(db_engine: AsyncEngine) -> AsyncIterator[None]:
    await _empty(db_engine)
    yield
    await _empty(db_engine)


async def seed_promotion(
    db: AsyncSession, *, products: Iterable[uuid.UUID] = (), **over: Any
) -> uuid.UUID:
    """Active now by default: 20% off everything for a day either side of now."""
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "name": "Eid Sale",
        "discount_type": DiscountType.PERCENTAGE,
        "discount_value": 20,
        "scope": PromotionScope.ALL,
        "starts_at": now - timedelta(days=1),
        "ends_at": now + timedelta(days=1),
        "is_active": True,
    } | over
    row = PromotionModel(**values)
    db.add(row)
    await db.flush()
    db.add_all(PromotionProductModel(promotion_id=row.id, product_id=p) for p in products)
    await db.commit()
    return row.id


def promotion_body(**over: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "name": "Ramadan Sale",
        "badge_text": "Ramadan",
        "discount_type": "percentage",
        "discount_value": 25,
        "scope": "all",
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(days=7)).isoformat(),
        "active": True,
    } | over
