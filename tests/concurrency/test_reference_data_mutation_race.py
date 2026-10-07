"""Concurrent administrator mutations on one reference-data row.

Every mutation is a read-modify-write, so each takes `SELECT ... FOR UPDATE`
before reading anything it then acts on. These tests cover three properties, and
- importantly - they do not all come from the same mechanism:

- **the audit trail describes the transitions that actually happened**, not a
  "before" state that was already stale when the write landed. This is the
  load-bearing test for the row lock: removing the lock turns it RED.
- **a PATCH racing an archive leaves the row archived**;
- **two PATCHes touching disjoint fields both survive**.

The last two stay GREEN with the lock removed, and that is not a defect in them.
Break-verification established that they are provided by SQLAlchemy's
per-attribute dirty tracking - each UPDATE emits only the columns that
transaction changed, so a PATCH that never touched `deleted_at` cannot clear it.
They remain valuable regression tests for behaviour we rely on; they are simply
not row-lock guards. Different tests protect different mechanisms.

Following the VS-004 lesson: the invariant is asserted, never the schedule.
Which request wins the lock is the operating system's business, identity travels
with each result, and both orderings are accepted as correct.
"""

import asyncio
import uuid
from typing import Any

import pytest
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.application.commands.category_admin import (
    ArchiveCategory,
    CreateCategory,
    UpdateCategory,
)
from app.catalog.application.commands.value_admin import (
    ArchiveReferenceValue,
    CreateReferenceValue,
    UpdateReferenceValue,
)
from app.catalog.domain.entities import Colour, Material
from app.catalog.domain.exceptions import ArchivedValueNotMutableError
from app.catalog.infrastructure.models import CategoryModel, ColourModel, MaterialModel
from app.catalog.infrastructure.repositories import (
    CategoryRepository,
    ColourRepository,
    MaterialRepository,
)
from app.identity.infrastructure.models import UserModel
from app.platform.infrastructure.models import AuditLogModel
from app.platform.public import SqlAuditWriter as AuditWriter
from tests.concurrency.barrier import meet_or_fail


async def _admin(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as db, db.begin():
        user = UserModel(email=f"test-{uuid.uuid4().hex}@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        return user.id


async def _hold(barrier: asyncio.Barrier) -> None:
    """Release both racers at the same point.

    `asyncio.gather` alone usually runs one coroutine to completion before the
    other starts - the VS-005 lesson - so without this the two transactions
    would never overlap and the test would pass against unlocked code. Both
    racers reach the barrier *before* taking any lock, so a missed barrier means
    the race did not happen, and the test fails rather than passing on a
    sequential run (audit A-12).
    """
    await meet_or_fail(barrier)


async def _seed_category(
    session_factory: async_sessionmaker[AsyncSession], actor: uuid.UUID
) -> tuple[uuid.UUID, str, str]:
    name, slug = f"orig-{uuid.uuid4().hex[:8]}", f"slug-{uuid.uuid4().hex[:10]}"
    async with session_factory() as db, db.begin():
        category = await CreateCategory(CategoryRepository(db), AuditWriter(db)).execute(
            name=name,
            slug=slug,
            is_active=True,
            actor_user_id=actor,
            request_id=None,
            ip_hash=None,
        )
    return category.id, name, slug


async def _patch_category(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    category_id: uuid.UUID,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
    name: str | None = None,
    slug: str | None = None,
) -> tuple[str, BaseException | None]:
    label = f"patch-{name or slug}"
    try:
        async with session_factory() as db, db.begin():
            await db.execute(select(CategoryModel.id).limit(0))
            await _hold(barrier)
            await UpdateCategory(CategoryRepository(db), AuditWriter(db)).execute(
                category_id=category_id,
                name=name,
                slug=slug,
                is_active=None,
                actor_user_id=actor,
                request_id=None,
                ip_hash=None,
            )
    except Exception as exc:
        return label, exc
    return label, None


async def _archive_category(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    category_id: uuid.UUID,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
) -> tuple[str, BaseException | None]:
    try:
        async with session_factory() as db, db.begin():
            await db.execute(select(CategoryModel.id).limit(0))
            await _hold(barrier)
            await ArchiveCategory(CategoryRepository(db), AuditWriter(db)).execute(
                category_id=category_id,
                actor_user_id=actor,
                request_id=None,
                ip_hash=None,
            )
    except Exception as exc:
        return "archive", exc
    return "archive", None


# --------------------------------------------------------------------------
# A. Category PATCH vs archive
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_patch_racing_an_archive_leaves_the_row_archived(
    db_engine: AsyncEngine,
) -> None:
    """Whoever wins, the row ends archived.

    Two schedules are legitimate and both are accepted:

      PATCH first  -> PATCH succeeds, archive then succeeds, row archived
      archive first-> archive succeeds, PATCH sees archived state and is refused

    Not a row-lock guard: this stays green with the lock removed, because the
    PATCH's UPDATE never includes `deleted_at` and so cannot clear it. It is a
    regression test for that end-state property, which we depend on either way.
    The lock's own guarantee is asserted by the audit test below.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    category_id, _, _ = await _seed_category(session_factory, actor)
    new_name = f"renamed-{uuid.uuid4().hex[:8]}"

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _patch_category(
            session_factory, category_id=category_id, actor=actor, barrier=barrier, name=new_name
        ),
        _archive_category(session_factory, category_id=category_id, actor=actor, barrier=barrier),
    )
    results = dict(outcomes)

    # The archive always succeeds: it either goes first, or goes second against a
    # row the PATCH left un-archived.
    assert results["archive"] is None, results

    patch_label = next(label for label in results if label.startswith("patch"))
    patch_error = results[patch_label]
    assert patch_error is None or isinstance(patch_error, ArchivedValueNotMutableError), results

    # Read in a fresh session, so this is the committed row rather than anything
    # either racer left in an identity map.
    async with session_factory() as db:
        row = await db.get(CategoryModel, category_id)
    assert row is not None

    assert row.deleted_at is not None, "the row must end archived whatever the schedule"
    assert row.is_active is False


@pytest.mark.integration
@pytest.mark.concurrency
async def test_the_archive_audit_row_records_the_state_it_actually_replaced(
    db_engine: AsyncEngine,
) -> None:
    """The load-bearing test for `SELECT ... FOR UPDATE`.

    The audit trail must describe the serialised history, not a stale read. If
    the PATCH committed first, the archive's `before` has to show the *new*
    name - the state the archive genuinely replaced. An unlocked archive
    snapshots the pre-PATCH name and writes a history that never happened, which
    is the same defect VS-007's settings race guarded against.

    This is the test that turns RED when `get_by_id_for_update` is downgraded to
    an unlocked `get_by_id`; the other two in this module do not, and are not
    meant to.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    category_id, original_name, _ = await _seed_category(session_factory, actor)
    new_name = f"renamed-{uuid.uuid4().hex[:8]}"

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _patch_category(
            session_factory, category_id=category_id, actor=actor, barrier=barrier, name=new_name
        ),
        _archive_category(session_factory, category_id=category_id, actor=actor, barrier=barrier),
    )
    results = dict(outcomes)
    patch_label = next(label for label in results if label.startswith("patch"))
    patch_succeeded = results[patch_label] is None

    async with session_factory() as db:
        rows = list(
            await db.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.entity_id == category_id,
                    AuditLogModel.action == "category.archived",
                )
            )
        )

    assert len(rows) == 1, "exactly one archive should have happened"
    before: dict[str, Any] | None = rows[0].before_data
    assert before is not None

    # Whichever way the race went, the archive's "before" must match the state
    # that actually preceded it.
    expected = new_name if patch_succeeded else original_name
    assert before["name"] == expected, (
        f"archive recorded a before-name of {before['name']!r}; the PATCH "
        f"{'did' if patch_succeeded else 'did not'} commit first, so it should be {expected!r}"
    )
    assert before["deleted_at"] is None
    assert rows[0].after_data is not None
    assert rows[0].after_data["deleted_at"] is not None


# --------------------------------------------------------------------------
# Disjoint partial updates
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.concurrency
async def test_concurrent_partial_updates_preserve_disjoint_fields(
    db_engine: AsyncEngine,
) -> None:
    """One request renames, the other re-slugs, at the same moment; both land.

    **This property is currently provided by SQLAlchemy dirty tracking, not by
    the row lock.** Each transaction's UPDATE carries only the columns it
    actually changed, so the rename and the re-slug touch disjoint column sets
    and cannot overwrite one another - which is why this test stays green with
    the lock removed.

    Kept deliberately: it is a real regression test for behaviour the admin API
    depends on, and it would catch a future change that started writing whole
    rows (a raw `UPDATE ... SET` of every column, say) and reintroduced a genuine
    lost update. It is simply not the test that proves the lock.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    category_id, original_name, original_slug = await _seed_category(session_factory, actor)
    new_name = f"newname-{uuid.uuid4().hex[:8]}"
    new_slug = f"newslug-{uuid.uuid4().hex[:10]}"

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _patch_category(
            session_factory, category_id=category_id, actor=actor, barrier=barrier, name=new_name
        ),
        _patch_category(
            session_factory, category_id=category_id, actor=actor, barrier=barrier, slug=new_slug
        ),
    )

    assert all(error is None for _, error in outcomes), outcomes

    async with session_factory() as db:
        row = await db.get(CategoryModel, category_id)
    assert row is not None

    assert row.name == new_name, (
        f"the rename was lost: name is {row.name!r}, expected {new_name!r} - "
        "a concurrent update overwrote a column it never changed"
    )
    assert row.slug == new_slug, (
        f"the re-slug was lost: slug is {row.slug!r}, expected {new_slug!r}"
    )
    assert original_name != new_name and original_slug != new_slug


# --------------------------------------------------------------------------
# B. Materials and colours (the shared simple-value path)
#
# Colours run through the same parameterised commands as materials but have
# their own repository - and so their own `SELECT ... FOR UPDATE` - so both are
# raced. Before audit A-01 only materials were, and only by the end-state test,
# which does not guard the lock.
# --------------------------------------------------------------------------

_VALUE_KINDS = ["material", "colour"]


def _update_value(
    kind: str, db: AsyncSession
) -> UpdateReferenceValue[Material] | UpdateReferenceValue[Colour]:
    if kind == "material":
        return UpdateReferenceValue[Material](
            MaterialRepository(db), AuditWriter(db), entity_type="Material"
        )
    return UpdateReferenceValue[Colour](ColourRepository(db), AuditWriter(db), entity_type="Colour")


def _archive_value(
    kind: str, db: AsyncSession
) -> ArchiveReferenceValue[Material] | ArchiveReferenceValue[Colour]:
    if kind == "material":
        return ArchiveReferenceValue[Material](
            MaterialRepository(db), AuditWriter(db), entity_type="Material"
        )
    return ArchiveReferenceValue[Colour](
        ColourRepository(db), AuditWriter(db), entity_type="Colour"
    )


async def _seed_value(
    session_factory: async_sessionmaker[AsyncSession], kind: str, actor: uuid.UUID
) -> tuple[uuid.UUID, str]:
    name = f"{kind}-{uuid.uuid4().hex[:12]}"
    async with session_factory() as db, db.begin():
        create: CreateReferenceValue[Material] | CreateReferenceValue[Colour]
        if kind == "material":
            create = CreateReferenceValue[Material](
                MaterialRepository(db), AuditWriter(db), entity_type="Material"
            )
        else:
            create = CreateReferenceValue[Colour](
                ColourRepository(db), AuditWriter(db), entity_type="Colour"
            )
        value = await create.execute(
            name=name, is_active=True, actor_user_id=actor, request_id=None, ip_hash=None
        )
    return value.id, name


async def _patch_value(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    kind: str,
    value_id: uuid.UUID,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
    name: str,
) -> tuple[str, BaseException | None]:
    try:
        async with session_factory() as db, db.begin():
            await db.execute(select(literal(1)))
            await _hold(barrier)
            await _update_value(kind, db).execute(
                value_id=value_id,
                name=name,
                is_active=None,
                actor_user_id=actor,
                request_id=None,
                ip_hash=None,
            )
    except Exception as exc:
        return "patch", exc
    return "patch", None


async def _archive_racer(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    kind: str,
    value_id: uuid.UUID,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
) -> tuple[str, BaseException | None]:
    try:
        async with session_factory() as db, db.begin():
            await db.execute(select(literal(1)))
            await _hold(barrier)
            await _archive_value(kind, db).execute(
                value_id=value_id, actor_user_id=actor, request_id=None, ip_hash=None
            )
    except Exception as exc:
        return "archive", exc
    return "archive", None


async def _race_patch_and_archive(
    db_engine: AsyncEngine, kind: str
) -> tuple[uuid.UUID, str, str, dict[str, BaseException | None]]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    value_id, original_name = await _seed_value(session_factory, kind, actor)
    new_name = f"renamed-{uuid.uuid4().hex[:12]}"

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _patch_value(
            session_factory,
            kind=kind,
            value_id=value_id,
            actor=actor,
            barrier=barrier,
            name=new_name,
        ),
        _archive_racer(session_factory, kind=kind, value_id=value_id, actor=actor, barrier=barrier),
    )
    return value_id, original_name, new_name, dict(outcomes)


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.parametrize("kind", _VALUE_KINDS)
async def test_a_value_patch_racing_an_archive_leaves_the_row_archived(
    db_engine: AsyncEngine, kind: str
) -> None:
    """The same end-state invariant on the material and colour paths. Like its
    category counterpart, this is a dirty-tracking regression test rather than
    a row-lock guard; the audit test below is the lock guard."""
    value_id, _, _, results = await _race_patch_and_archive(db_engine, kind)

    assert results["archive"] is None, results
    patch_error = results["patch"]
    assert patch_error is None or isinstance(patch_error, ArchivedValueNotMutableError), results

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    row: MaterialModel | ColourModel | None
    async with session_factory() as db:
        if kind == "material":
            row = await db.get(MaterialModel, value_id)
        else:
            row = await db.get(ColourModel, value_id)
    assert row is not None
    assert row.deleted_at is not None
    assert row.is_active is False


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.parametrize("kind", _VALUE_KINDS)
async def test_a_value_archive_audit_row_records_the_state_it_actually_replaced(
    db_engine: AsyncEngine, kind: str
) -> None:
    """The row-lock guard for materials and colours (audit A-01).

    Same reasoning as the category test: if the PATCH committed first, the
    archive's `before` must show the new name. With `FOR UPDATE` removed from
    `MaterialRepository`/`ColourRepository.get_by_id_for_update`, the archive
    snapshots the pre-PATCH name and this turns red.
    """
    value_id, original_name, new_name, results = await _race_patch_and_archive(db_engine, kind)
    assert results["archive"] is None, results
    patch_succeeded = results["patch"] is None
    if not patch_succeeded:
        assert isinstance(results["patch"], ArchivedValueNotMutableError), results

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as db:
        rows = list(
            await db.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.entity_id == value_id,
                    AuditLogModel.action == f"{kind}.archived",
                )
            )
        )

    assert len(rows) == 1, "exactly one archive should have happened"
    before: dict[str, Any] | None = rows[0].before_data
    assert before is not None
    expected = new_name if patch_succeeded else original_name
    assert before["name"] == expected, (
        f"{kind} archive recorded a before-name of {before['name']!r}; the PATCH "
        f"{'did' if patch_succeeded else 'did not'} commit first, so it should be {expected!r}"
    )
    assert before["deleted_at"] is None
