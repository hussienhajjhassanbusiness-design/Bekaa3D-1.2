"""Seeds for the storefront tests: each test owns a category, material pair and
colour pair, retired afterwards by `tests.catalog_seed`."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.infrastructure.models import (
    CategoryModel,
    ColourModel,
    MaterialModel,
    ProductModel,
)
from tests.catalog_seed import register


@dataclass
class Refs:
    category: CategoryModel
    materials: list[MaterialModel]
    colours: list[ColourModel]


async def seed_refs(db: AsyncSession) -> Refs:
    token = uuid.uuid4().hex[:12]
    refs = Refs(
        category=CategoryModel(name=f"zzz-vs015-{token}", slug=f"c-{token}"),
        materials=[MaterialModel(name=f"zzz-vs015-m{i}-{token}") for i in range(2)],
        colours=[ColourModel(name=f"zzz-vs015-c{i}-{token}") for i in range(2)],
    )
    db.add_all([refs.category, *refs.materials, *refs.colours])
    await db.commit()
    register(refs.category.id, *(r.id for r in refs.materials + refs.colours))
    return refs


async def seed_product(db: AsyncSession, refs: Refs, **over: Any) -> ProductModel:
    physical = over.get("type", ProductType.PHYSICAL) is ProductType.PHYSICAL
    values: dict[str, Any] = {
        "type": ProductType.PHYSICAL,
        "category_id": refs.category.id,
        "name": "Lamp",
        "slug": f"p-{uuid.uuid4().hex[:12]}",
        "price_cents": 1000,
        "is_visible": True,
    }
    if physical:
        values |= {
            "purchase_mode": PurchaseMode.ONLINE_ONLY,
            "material_id": refs.materials[0].id,
            "colour_id": refs.colours[0].id,
            "production_lead_time_days": 3,
            "batch_size": 2,
            "max_quantity_per_line": 5,
        }
    row = ProductModel(**(values | over))
    db.add(row)
    await db.commit()
    return row
