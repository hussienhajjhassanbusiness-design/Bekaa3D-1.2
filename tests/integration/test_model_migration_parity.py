"""The ORM models match migration 03a4730dd046 for VS-023's six tables: Alembic's
autogenerate diff against the migrated schema must be empty (VS-023 plan 8, PR A)."""

from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core import models as _models  # noqa: F401 - registers every model
from app.core.database import Base

pytestmark = pytest.mark.integration

VS023_TABLES = {
    "orders",
    "order_items",
    "order_status_history",
    "payments",
    "webhook_events",
    "idempotency_records",
}


def _table_of(obj: Any, type_: str) -> str | None:
    if type_ == "table":
        return str(obj.name)
    table = getattr(obj, "table", None)
    return None if table is None else str(table.name)


def _include(obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    return _table_of(obj, type_) in VS023_TABLES


def _diff(conn: Connection) -> list[Any]:
    context = MigrationContext.configure(
        conn, opts={"compare_type": True, "include_object": _include}
    )
    return list(compare_metadata(context, Base.metadata))


async def test_models_match_the_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        diff = await conn.run_sync(_diff)
    assert diff == []


def test_every_vs023_table_has_a_model() -> None:
    assert set(Base.metadata.tables) >= VS023_TABLES
