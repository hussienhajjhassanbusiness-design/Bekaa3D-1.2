"""Two administrators claiming the same category slug at the same moment.

The invariant is that the *database* settles it. `CreateCategory` never reads
the slug to see whether it is free - a `SELECT` followed by an `INSERT` has a
window in which another transaction can commit the same slug, so the read would
report "available" for a slug that is about to be taken. The partial unique
index is the only authority.

Following the lesson from the VS-004 reset race we repaired: this test asserts
the invariant, never the schedule. Either attempt may win, identity travels with
each result, and neither input is called a winner before the race is run.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.application.commands.category_admin import ArchiveCategory, CreateCategory
from app.catalog.domain.exceptions import SlugConflictError
from app.catalog.infrastructure.models import CategoryModel
from app.catalog.infrastructure.repositories import CategoryRepository
from app.identity.infrastructure.models import UserModel
from app.platform.public import SqlAuditWriter as AuditWriter
from tests.concurrency.barrier import meet_or_fail


async def _admin(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as db, db.begin():
        user = UserModel(email=f"test-{uuid.uuid4().hex}@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        return user.id


async def _attempt(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    name: str,
    slug: str,
    actor: uuid.UUID,
    barrier: asyncio.Barrier,
) -> tuple[str, BaseException | None]:
    """One request's worth of work, transaction boundary included.

    Returns the name it submitted alongside its outcome, so the caller can tell
    *which* attempt won rather than assuming. `asyncio.gather` preserves
    argument order; the order two transactions reach a unique index does not
    follow from it.
    """
    try:
        async with session_factory() as db, db.begin():
            # Force the transaction open before the barrier, so both racers are
            # genuinely inside one when released rather than still connecting.
            await db.execute(select(CategoryModel.id).limit(0))
            await meet_or_fail(barrier)
            await CreateCategory(CategoryRepository(db), AuditWriter(db)).execute(
                name=name,
                slug=slug,
                is_active=True,
                actor_user_id=actor,
                request_id=None,
                ip_hash=None,
            )
    except Exception as exc:
        return name, exc
    return name, None


@pytest.mark.integration
@pytest.mark.concurrency
async def test_two_administrators_claiming_one_slug_produce_exactly_one_category(
    db_engine: AsyncEngine,
) -> None:
    """Exactly one succeeds, exactly one is refused, one live row owns the slug.

    Which one wins is not asserted - that is decided by whichever transaction
    reaches the index first, and both outcomes are correct.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    slug = f"race-{uuid.uuid4().hex[:12]}"
    first_name, second_name = f"{slug}-first", f"{slug}-second"

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _attempt(session_factory, name=first_name, slug=slug, actor=actor, barrier=barrier),
        _attempt(session_factory, name=second_name, slug=slug, actor=actor, barrier=barrier),
    )

    succeeded = [name for name, error in outcomes if error is None]
    rejected = [(name, error) for name, error in outcomes if error is not None]

    assert len(succeeded) == 1, outcomes
    assert len(rejected) == 1, outcomes
    # Refused for the right reason. Any other exception would mean the second
    # request crashed rather than being correctly refused - a different bug
    # wearing the same shape.
    assert isinstance(rejected[0][1], SlugConflictError), outcomes
    assert {succeeded[0], rejected[0][0]} == {first_name, second_name}

    async with session_factory() as db:
        rows = list(
            await db.scalars(
                select(CategoryModel).where(
                    CategoryModel.slug == slug, CategoryModel.deleted_at.is_(None)
                )
            )
        )

    assert len(rows) == 1, f"exactly one live row must own the slug, found {len(rows)}"
    # The surviving row belongs to whichever attempt actually succeeded -
    # derived from the outcomes, never assumed from argument order.
    assert rows[0].name == succeeded[0]


@pytest.mark.integration
@pytest.mark.concurrency
async def test_archiving_releases_the_slug_for_another_category(
    db_engine: AsyncEngine,
) -> None:
    """The partial index is what makes this work: the archived row leaves the
    index, so the slug is immediately free with no cleanup step."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    slug = f"reuse-{uuid.uuid4().hex[:12]}"

    async with session_factory() as db, db.begin():
        first = await CreateCategory(CategoryRepository(db), AuditWriter(db)).execute(
            name="first",
            slug=slug,
            is_active=True,
            actor_user_id=actor,
            request_id=None,
            ip_hash=None,
        )

    # While it is still live, the slug is taken.
    async with session_factory() as db, db.begin():
        with pytest.raises(SlugConflictError):
            await CreateCategory(CategoryRepository(db), AuditWriter(db)).execute(
                name="blocked",
                slug=slug,
                is_active=True,
                actor_user_id=actor,
                request_id=None,
                ip_hash=None,
            )

    async with session_factory() as db, db.begin():
        await ArchiveCategory(CategoryRepository(db), AuditWriter(db)).execute(
            category_id=first.id, actor_user_id=actor, request_id=None, ip_hash=None
        )

    async with session_factory() as db, db.begin():
        second = await CreateCategory(CategoryRepository(db), AuditWriter(db)).execute(
            name="second",
            slug=slug,
            is_active=True,
            actor_user_id=actor,
            request_id=None,
            ip_hash=None,
        )

    assert second.id != first.id

    async with session_factory() as db:
        rows = list(await db.scalars(select(CategoryModel).where(CategoryModel.slug == slug)))

    # Both rows survive - the archived one keeps its slug value, it simply no
    # longer participates in the index.
    assert len(rows) == 2
    live = [row for row in rows if row.deleted_at is None]
    archived = [row for row in rows if row.deleted_at is not None]
    assert len(live) == 1 and live[0].id == second.id
    assert len(archived) == 1 and archived[0].id == first.id
    assert archived[0].is_active is False


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_slug_may_be_reused_only_once_at_a_time(db_engine: AsyncEngine) -> None:
    """Two categories racing to claim a slug that was just released still
    resolve to one winner - archiving frees the slug, it does not disable the
    constraint."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    slug = f"freed-{uuid.uuid4().hex[:12]}"

    async with session_factory() as db, db.begin():
        original = await CreateCategory(CategoryRepository(db), AuditWriter(db)).execute(
            name="original",
            slug=slug,
            is_active=True,
            actor_user_id=actor,
            request_id=None,
            ip_hash=None,
        )
    async with session_factory() as db, db.begin():
        await ArchiveCategory(CategoryRepository(db), AuditWriter(db)).execute(
            category_id=original.id, actor_user_id=actor, request_id=None, ip_hash=None
        )

    barrier = asyncio.Barrier(2)
    outcomes = await asyncio.gather(
        _attempt(session_factory, name="claim-a", slug=slug, actor=actor, barrier=barrier),
        _attempt(session_factory, name="claim-b", slug=slug, actor=actor, barrier=barrier),
    )

    succeeded = [name for name, error in outcomes if error is None]
    rejected = [error for _, error in outcomes if error is not None]
    assert len(succeeded) == 1, outcomes
    assert len(rejected) == 1 and isinstance(rejected[0], SlugConflictError), outcomes

    async with session_factory() as db:
        live = list(
            await db.scalars(
                select(CategoryModel).where(
                    CategoryModel.slug == slug, CategoryModel.deleted_at.is_(None)
                )
            )
        )
    assert len(live) == 1
    assert live[0].name == succeeded[0]


@pytest.mark.integration
@pytest.mark.concurrency
async def test_a_failed_create_leaves_no_audit_row(db_engine: AsyncEngine) -> None:
    """Mutation and audit share one transaction, so a rejected create must not
    leave an audit row claiming a category was created."""
    from app.platform.infrastructure.models import AuditLogModel

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    actor = await _admin(session_factory)
    slug = f"noaudit-{uuid.uuid4().hex[:12]}"
    since = datetime.now(UTC) - timedelta(seconds=5)

    async with session_factory() as db, db.begin():
        await CreateCategory(CategoryRepository(db), AuditWriter(db)).execute(
            name="taken",
            slug=slug,
            is_active=True,
            actor_user_id=actor,
            request_id=None,
            ip_hash=None,
        )

    async with session_factory() as db, db.begin():
        with pytest.raises(SlugConflictError):
            await CreateCategory(CategoryRepository(db), AuditWriter(db)).execute(
                name="refused",
                slug=slug,
                is_active=True,
                actor_user_id=actor,
                request_id=None,
                ip_hash=None,
            )

    async with session_factory() as db:
        rows = list(
            await db.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.actor_user_id == actor,
                    AuditLogModel.action == "category.created",
                    AuditLogModel.created_at >= since,
                )
            )
        )

    # Exactly one audit row: the successful create. The refused one wrote none.
    assert len(rows) == 1, [row.after_data for row in rows]
    assert rows[0].after_data is not None
    assert rows[0].after_data["name"] == "taken"
