"""VS-026 / FR-03: concurrent address-book writes for one user leave exactly one default and
never pass the cap. Without the per-user lock the second switch's clear misses the first's
new default and hits the unique index; two first creates both become default."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.application.commands.address_book import (
    CreateAddress,
    SetDefaultAddress,
    UpdateAddress,
)
from app.identity.domain.address import MAX_LIVE_ADDRESSES, AddressDetails
from app.identity.domain.exceptions import AddressLimitReachedError
from app.identity.infrastructure.addresses import SqlAddressRepository
from app.identity.infrastructure.models import AddressModel
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import create_user

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]

# The locked loser waits inside PostgreSQL and cannot arrive; the winner moves on.
_AFTER_LOCK_TIMEOUT_SECONDS = 1.0
DETAILS = AddressDetails.of(
    label="Race",
    recipient_name="Racer",
    phone="03 123 456",
    governorate="beirut",
    city="Beirut",
    area=None,
    street=None,
    landmark_notes="Corner shop",
)


class _SyncedRepository(SqlAddressRepository):
    def __init__(
        self, session: AsyncSession, before_lock: asyncio.Barrier, after_lock: asyncio.Barrier
    ) -> None:
        super().__init__(session)
        self._before_lock = before_lock
        self._after_lock = after_lock

    async def lock_address_book(self, user_id: uuid.UUID) -> bool:
        await meet_or_fail(self._before_lock)
        live = await super().lock_address_book(user_id)
        with suppress(TimeoutError, asyncio.BrokenBarrierError):
            await asyncio.wait_for(self._after_lock.wait(), _AFTER_LOCK_TIMEOUT_SECONDS)
        return live


async def _seed(engine: AsyncEngine, count: int, *, default_first: bool) -> tuple[Any, list[Any]]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user_id = (await create_user(db)).id
        rows = [
            AddressModel(
                user_id=user_id,
                label=f"A{n}",
                recipient_name="Seed",
                phone="+9613123456",
                governorate="beirut",
                city="Beirut",
                landmark_notes="seeded",
                is_default=default_first and n == 0,
            )
            for n in range(count)
        ]
        db.add_all(rows)
        await db.commit()
    return user_id, [row.id for row in rows]


async def _race(
    engine: AsyncEngine, actions: list[Callable[[SqlAddressRepository], Awaitable[Any]]]
) -> list[Any]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    before_lock, after_lock = asyncio.Barrier(len(actions)), asyncio.Barrier(len(actions))

    async def run(action: Callable[[SqlAddressRepository], Awaitable[Any]]) -> Any:
        async with factory() as db, db.begin():
            try:
                return await action(_SyncedRepository(db, before_lock, after_lock))
            except AddressLimitReachedError:
                return "refused"

    return await asyncio.gather(*(run(action) for action in actions))


async def _state(engine: AsyncEngine, user_id: Any) -> tuple[int, list[Any]]:
    async with async_sessionmaker(engine)() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(AddressModel)
            .where(AddressModel.user_id == user_id, AddressModel.deleted_at.is_(None))
        )
        defaults = await db.scalars(
            select(AddressModel.id).where(
                AddressModel.user_id == user_id,
                AddressModel.is_default,
                AddressModel.deleted_at.is_(None),
            )
        )
        return int(count or 0), list(defaults.all())


def _switch(path: str, user_id: Any, address_id: Any) -> Callable[[Any], Awaitable[Any]]:
    if path == "put_default":
        return lambda repo: SetDefaultAddress(repo).execute(user_id=user_id, address_id=address_id)
    return lambda repo: UpdateAddress(repo).execute(
        user_id=user_id, address_id=address_id, changes={}, make_default=True
    )


@pytest.mark.parametrize("run", range(3))
@pytest.mark.parametrize("path", ["put_default", "patch_is_default"])
async def test_parallel_switches_leave_one_default(
    db_engine: AsyncEngine, path: str, run: int
) -> None:
    user_id, (_, b, c) = await _seed(db_engine, 3, default_first=True)
    await _race(db_engine, [_switch(path, user_id, b), _switch(path, user_id, c)])
    count, defaults = await _state(db_engine, user_id)
    assert count == 3
    assert len(defaults) == 1
    assert defaults[0] in (b, c)


@pytest.mark.parametrize("run", range(3))
async def test_parallel_creates_with_is_default_leave_one_default(
    db_engine: AsyncEngine, run: int
) -> None:
    user_id, _ = await _seed(db_engine, 1, default_first=True)
    create = lambda repo: CreateAddress(repo).execute(  # noqa: E731
        user_id=user_id, details=DETAILS, make_default=True
    )
    created = await _race(db_engine, [create, create])
    count, defaults = await _state(db_engine, user_id)
    assert count == 3
    assert len(defaults) == 1
    assert defaults[0] in {address.id for address in created}


@pytest.mark.parametrize("run", range(3))
async def test_parallel_first_creates_produce_exactly_one_default(
    db_engine: AsyncEngine, run: int
) -> None:
    user_id, _ = await _seed(db_engine, 0, default_first=False)
    create = lambda repo: CreateAddress(repo).execute(  # noqa: E731
        user_id=user_id, details=DETAILS, make_default=False
    )
    created = await _race(db_engine, [create, create])
    count, defaults = await _state(db_engine, user_id)
    assert count == 2
    assert sorted(address.is_default for address in created) == [False, True]
    assert len(defaults) == 1


@pytest.mark.parametrize("run", range(3))
async def test_parallel_creates_at_the_cap_admit_one(db_engine: AsyncEngine, run: int) -> None:
    user_id, _ = await _seed(db_engine, MAX_LIVE_ADDRESSES - 1, default_first=True)
    create = lambda repo: CreateAddress(repo).execute(  # noqa: E731
        user_id=user_id, details=DETAILS, make_default=False
    )
    outcomes = await _race(db_engine, [create, create])
    count, defaults = await _state(db_engine, user_id)
    assert sorted(o == "refused" for o in outcomes) == [False, True]
    assert count == MAX_LIVE_ADDRESSES
    assert len(defaults) == 1
