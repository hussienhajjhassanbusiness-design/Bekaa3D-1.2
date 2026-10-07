"""Retire the categories, materials and colours a test seeds once it ends: the
suites share one database and the public lists cap at 100 rows, so values left
live crowd other tests' rows out (VS-010 audit A-06). Soft, like the application."""

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_SEEDED: list[uuid.UUID] = []


def register(*value_ids: uuid.UUID) -> None:
    _SEEDED.extend(value_ids)


@pytest_asyncio.fixture(autouse=True)
async def retire_seeded_catalog_values(db_engine: AsyncEngine) -> AsyncGenerator[None]:
    yield
    if not _SEEDED:
        return
    ids = list(_SEEDED)
    _SEEDED.clear()
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE products SET deleted_at = now(), is_visible = false "
                "WHERE deleted_at IS NULL AND (category_id = ANY(:ids) "
                "OR material_id = ANY(:ids) OR colour_id = ANY(:ids))"
            ),
            {"ids": ids},
        )
        for table in ("categories", "materials", "colours"):
            await conn.execute(
                text(
                    f"UPDATE {table} SET deleted_at = coalesce(deleted_at, now()), "
                    "is_active = false WHERE id = ANY(:ids)"
                ),
                {"ids": ids},
            )
