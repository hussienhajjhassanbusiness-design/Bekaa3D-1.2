"""Two administrators creating the same material/colour name, differing only in
case, at the same moment.

As with category slugs, the database settles it: the case-insensitive live-name
index is the only authority, and nothing reads first to see whether a name is
free. The invariant is asserted, never the schedule - either attempt may win.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.application.commands.value_admin import CreateReferenceValue
from app.catalog.domain.entities import Colour, Material
from app.catalog.domain.exceptions import NameConflictError
from app.catalog.infrastructure.models import ColourModel, MaterialModel
from app.catalog.infrastructure.repositories import ColourRepository, MaterialRepository
from app.identity.infrastructure.models import UserModel
from app.platform.public import SqlAuditWriter as AuditWriter
from tests.concurrency.barrier import meet_or_fail


async def _admin(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as db, db.begin():
        user = UserModel(email=f"test-{uuid.uuid4().hex}@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        return user.id


def _create(
    kind: str, db: AsyncSession
) -> CreateReferenceValue[Material] | CreateReferenceValue[Colour]:
    if kind == "material":
        return CreateReferenceValue[Material](
            MaterialRepository(db), AuditWriter(db), entity_type="Material"
        )
    return CreateReferenceValue[Colour](ColourRepository(db), AuditWriter(db), entity_type="Colour")


async def _attempt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    kind: str,
    name: str,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
) -> tuple[str, BaseException | None]:
    try:
        async with session_factory() as db, db.begin():
            await db.execute(select(literal(1)))
            await meet_or_fail(barrier)
            await _create(kind, db).execute(
                name=name, is_active=True, actor_user_id=actor, request_id=None, ip_hash=None
            )
    except Exception as exc:
        return name, exc
    return name, None


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.parametrize("kind", ["material", "colour"])
async def test_two_administrators_creating_one_name_produce_exactly_one_value(
    db_engine: AsyncEngine, kind: str
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    base = f"Pla-{uuid.uuid4().hex[:8]}"
    first_name, second_name = base.lower(), base.upper()

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _attempt(session_factory, kind=kind, name=first_name, actor=actor, barrier=barrier),
        _attempt(session_factory, kind=kind, name=second_name, actor=actor, barrier=barrier),
    )

    succeeded = [name for name, error in outcomes if error is None]
    rejected = [(name, error) for name, error in outcomes if error is not None]
    assert len(succeeded) == 1, outcomes
    assert len(rejected) == 1, outcomes
    # Refused for the right reason - not a crash wearing the same shape.
    assert isinstance(rejected[0][1], NameConflictError), outcomes

    model: type[MaterialModel] | type[ColourModel] = (
        MaterialModel if kind == "material" else ColourModel
    )
    async with session_factory() as db:
        live = list(
            await db.scalars(
                select(model.name).where(
                    func.lower(model.name) == base.lower(), model.deleted_at.is_(None)
                )
            )
        )
    assert live == [succeeded[0]], f"exactly one live row must own the name, found {live}"
