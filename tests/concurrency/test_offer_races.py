"""VS-039 races (SRS 11.4, 24 "concurrent offer submission"; ADR-034): concurrent submissions
leave one live offer, overlapping expiry runs write one round, and a submission racing an
uncommitted rejection still sees its cooldown."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.infrastructure.cart_product_reader import SqlCartProductReader
from app.negotiation.application.services.expire_offers import expire_offer
from app.negotiation.application.services.submit_offer import OfferRequestContext, submit_offer
from app.negotiation.domain.exceptions import OfferAlreadyActiveError, OfferCooldownActiveError
from app.negotiation.domain.offers import Offer
from app.negotiation.infrastructure.adapters import EngagementOfferNotifier, OrderingStlOwnership
from app.negotiation.infrastructure.offers import SqlOfferStore
from app.platform.public import SqlAuditWriter, settings_reader
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import create_user
from tests.integration.negotiation.offer_support import seed_offer, shop_open, stl  # noqa: F401

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]


class _SyncedStore(SqlOfferStore):
    """Holds every racer at the one statement the race is about."""

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def lock_acquisition(self, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
        # Since ADR-037 submissions queue on this lock, so they meet here; each insert
        # then still relies on `uq_offers_live`, as no application check precedes it.
        await meet_or_fail(self._barrier)
        await super().lock_acquisition(user_id, product_id)

    async def lock_unless_locked(self, offer_id: uuid.UUID) -> Offer | None:
        await meet_or_fail(self._barrier)
        return await super().lock_unless_locked(offer_id)


async def _submit(
    session: AsyncSession, store: SqlOfferStore, user: uuid.UUID, product: uuid.UUID
) -> Offer:
    return await submit_offer(
        offers=store,
        products=SqlCartProductReader(session),
        ownership=OrderingStlOwnership(session),
        settings=settings_reader(session),
        notifier=EngagementOfferNotifier(session),
        audit=SqlAuditWriter(session),
        user_id=user,
        product_id=product,
        amount_cents=800,
        message=None,
        now=datetime.now(UTC),
        context=OfferRequestContext(),
    )


async def _counts(engine: AsyncEngine, user: uuid.UUID) -> tuple[int, int, int]:
    sql = """
        SELECT (SELECT count(*) FROM offers WHERE user_id = :u),
          (SELECT count(*) FROM offer_rounds r JOIN offers o ON o.id = r.offer_id
            WHERE o.user_id = :u),
          (SELECT count(*) FROM audit_logs WHERE actor_user_id = :u
            AND action = 'offer.submitted')
    """
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), {"u": user})).one()
    return int(row[0]), int(row[1]), int(row[2])


@pytest.mark.usefixtures("shop_open")
@pytest.mark.parametrize("racers", [2, 5])
async def test_concurrent_submissions_leave_one_live_offer(
    db_engine: AsyncEngine, racers: int
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db:
        user = (await create_user(db)).id
        product = await stl(db)
    barrier = asyncio.Barrier(racers)

    async def racer() -> Offer | Exception:
        try:
            async with factory() as session, session.begin():
                return await _submit(session, _SyncedStore(session, barrier), user, product)
        except OfferAlreadyActiveError as exc:
            return exc

    results = await asyncio.gather(*(racer() for _ in range(racers)))
    assert sum(isinstance(r, Offer) for r in results) == 1
    assert sum(isinstance(r, OfferAlreadyActiveError) for r in results) == racers - 1
    assert await _counts(db_engine, user) == (1, 1, 1)


async def test_overlapping_expiry_runs_expire_once(db_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db:
        user = (await create_user(db)).id
        offer = await seed_offer(
            db,
            user_id=user,
            product_id=await stl(db),
            responds_by=datetime.now(UTC) - timedelta(minutes=1),
        )
    barrier = asyncio.Barrier(2)

    async def run() -> bool:
        async with factory() as session, session.begin():
            return await expire_offer(
                _SyncedStore(session, barrier),
                EngagementOfferNotifier(session),
                SqlAuditWriter(session),
                offer_id=offer,
                now=datetime.now(UTC),
            )

    assert sorted(await asyncio.gather(run(), run())) == [False, True]
    async with db_engine.connect() as conn:
        rounds = await conn.scalar(
            text("SELECT count(*) FROM offer_rounds WHERE offer_id = :o"), {"o": offer}
        )
        audits = await conn.scalar(
            text("SELECT count(*) FROM audit_logs WHERE entity_id = :o"), {"o": offer}
        )
    assert (rounds, audits) == (2, 1)


async def _wait_until_blocked(engine: AsyncEngine) -> None:
    """Until some backend waits on a lock: the submission's insert behind the rejection."""
    for _ in range(100):
        async with engine.connect() as conn:
            waiting = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND query LIKE 'INSERT INTO offers%'"
                )
            )
        if waiting:
            return
        await asyncio.sleep(0.05)
    pytest.fail("the submission never blocked behind the uncommitted rejection")


@pytest.mark.usefixtures("shop_open")
@pytest.mark.parametrize(
    ("cooldown", "refused"), [(timedelta(days=7), True), (timedelta(0), False)]
)
async def test_submission_racing_a_rejection_sees_its_cooldown(
    db_engine: AsyncEngine, cooldown: timedelta, refused: bool
) -> None:
    """The cooldown is read after the insert, which can only succeed once the rejection has
    committed; read before it, this submission slipped through during the cooldown."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db:
        user = (await create_user(db)).id
        product = await stl(db)
        live = await seed_offer(db, user_id=user, product_id=product)
    now = datetime.now(UTC)
    async with db_engine.connect() as rejecting:
        transaction = await rejecting.begin()
        await rejecting.execute(
            text(
                "UPDATE offers SET status = 'rejected', turn = NULL, rejected_at = :n,"
                " cooldown_until = :c WHERE id = :o"
            ),
            {"n": now, "c": now + cooldown, "o": live},
        )

        async def submission() -> Offer | Exception:
            try:
                async with factory() as session, session.begin():
                    return await _submit(session, SqlOfferStore(session), user, product)
            except OfferCooldownActiveError as exc:
                return exc

        pending = asyncio.create_task(submission())
        await _wait_until_blocked(db_engine)
        await transaction.commit()
        result = await pending
    assert isinstance(result, OfferCooldownActiveError) is refused
    assert (await _counts(db_engine, user))[0] == (1 if refused else 2)
