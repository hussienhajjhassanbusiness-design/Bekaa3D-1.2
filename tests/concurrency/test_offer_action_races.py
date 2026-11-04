"""VS-040 races (FR-13 concurrency; ADR-034 consequences, ADR-035): every answer locks the
offer row, so two answers, or an answer and the expiry job, never both transition it."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.infrastructure.cart_product_reader import SqlCartProductReader
from app.identity.domain.enums import UserRole
from app.jobs.expire_offers import expire_offers
from app.negotiation.api.wiring import offer_deps
from app.negotiation.application.services.expire_offers import (
    expire_checkout_offer,
    expire_offer,
    remind_offer,
)
from app.negotiation.application.services.respond_to_offer import (
    OfferDeps,
    Responder,
    accept_offer,
    counter_offer,
    reject_offer,
    withdraw_offer,
)
from app.negotiation.domain.enums import OfferActor
from app.negotiation.domain.exceptions import (
    NegotiationDomainError,
    OfferExpiredError,
    OfferInvalidTransitionError,
    OfferNotYourTurnError,
)
from app.negotiation.domain.offers import Offer
from app.negotiation.infrastructure.offers import SqlOfferStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.deep_support import create_user
from tests.integration.negotiation.offer_support import seed_offer, stl

pytestmark = [pytest.mark.concurrency, pytest.mark.integration]
Action = Callable[[OfferDeps], Awaitable[object]]


class _SyncedStore(SqlOfferStore):
    """Releases every racer together at the row lock the race is about."""

    def __init__(self, session: AsyncSession, barrier: asyncio.Barrier) -> None:
        super().__init__(session)
        self._barrier = barrier

    async def lock(self, offer_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> Offer | None:
        await meet_or_fail(self._barrier)
        return await super().lock(offer_id, user_id=user_id)

    async def lock_unless_locked(self, offer_id: uuid.UUID) -> Offer | None:
        await meet_or_fail(self._barrier)
        return await super().lock_unless_locked(offer_id)

    async def get(self, offer_id: uuid.UUID, *, user_id: uuid.UUID | None = None) -> Offer | None:
        await meet_or_fail(self._barrier)
        return await super().get(offer_id, user_id=user_id)


async def _seed(engine: AsyncEngine, **over: Any) -> tuple[uuid.UUID, Responder, uuid.UUID]:
    """The customer, an administrator to answer as, and an offer on the admin's turn."""
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        user = (await create_user(db)).id
        admin = Responder(OfferActor.ADMIN, (await create_user(db, role=UserRole.ADMIN)).id)
        return user, admin, await seed_offer(db, user_id=user, product_id=await stl(db), **over)


async def _race(engine: AsyncEngine, *actions: Action) -> list[object]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    barrier = asyncio.Barrier(len(actions))

    async def run(action: Action) -> object:
        try:
            async with factory() as session, session.begin():
                deps = offer_deps(session, SqlCartProductReader(session))
                return await action(replace(deps, offers=_SyncedStore(session, barrier)))
        except NegotiationDomainError as exc:
            return exc

    return list(await asyncio.gather(*(run(action) for action in actions)))


async def _rounds_and_audits(engine: AsyncEngine, offer: uuid.UUID) -> tuple[int, int]:
    async with engine.connect() as conn:
        rounds = await conn.scalar(
            text("SELECT count(*) FROM offer_rounds WHERE offer_id = :o"), {"o": offer}
        )
        audits = await conn.scalar(
            text("SELECT count(*) FROM audit_logs WHERE entity_id = :o"), {"o": offer}
        )
    return int(rounds or 0), int(audits or 0)


async def test_accept_racing_reject_one_wins(db_engine: AsyncEngine) -> None:
    _, admin, offer = await _seed(db_engine)
    results = await _race(
        db_engine,
        lambda d: accept_offer(d, admin, offer_id=offer, expected_amount_cents=800),
        lambda d: reject_offer(d, admin, offer_id=offer, reason=None),
    )
    assert sum(isinstance(r, Offer) for r in results) == 1
    assert sum(isinstance(r, OfferInvalidTransitionError) for r in results) == 1
    assert await _rounds_and_audits(db_engine, offer) == (2, 1)


async def test_withdraw_racing_admin_accept_one_wins(db_engine: AsyncEngine) -> None:
    user, admin, offer = await _seed(db_engine)
    customer = Responder(OfferActor.CUSTOMER, user)
    results = await _race(
        db_engine,
        lambda d: withdraw_offer(d, customer, offer_id=offer, reason=None),
        lambda d: accept_offer(d, admin, offer_id=offer, expected_amount_cents=800),
    )
    assert sum(isinstance(r, Offer) for r in results) == 1
    assert sum(isinstance(r, OfferInvalidTransitionError) for r in results) == 1
    assert await _rounds_and_audits(db_engine, offer) == (2, 1)


async def test_a_double_clicked_counter_counts_once(db_engine: AsyncEngine) -> None:
    """The second sees the turn already passed: 409, never a second round."""
    _, admin, offer = await _seed(db_engine)

    def counter(deps: OfferDeps) -> Awaitable[Offer]:
        return counter_offer(deps, admin, offer_id=offer, amount_cents=900, message=None)

    results = await _race(db_engine, counter, counter)
    assert sum(isinstance(r, Offer) for r in results) == 1
    assert sum(isinstance(r, OfferNotYourTurnError) for r in results) == 1
    assert await _rounds_and_audits(db_engine, offer) == (2, 1)


async def test_a_last_second_answer_racing_the_expiry_job(db_engine: AsyncEngine) -> None:
    """ADR-034 d6: whichever locks first wins; the offer is never both countered and expired."""
    deadline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    _, admin, offer = await _seed(db_engine, responds_by=deadline)

    async def answer(deps: OfferDeps) -> object:
        late = replace(deps, clock=lambda: deadline - timedelta(seconds=1))
        return await counter_offer(late, admin, offer_id=offer, amount_cents=900, message=None)

    async def job(deps: OfferDeps) -> object:
        return await expire_offer(
            deps.offers, deps.notifier, deps.audit, offer_id=offer, now=deadline
        )

    answered, expired = await _race(db_engine, answer, job)
    assert (isinstance(answered, Offer), expired) in {(True, False), (False, True)}
    if expired is True:
        assert isinstance(answered, OfferExpiredError)
    assert await _rounds_and_audits(db_engine, offer) == (2, 1)
    async with db_engine.connect() as conn:
        status = await conn.scalar(
            text("SELECT status::text FROM offers WHERE id = :o"), {"o": offer}
        )
    assert status == ("awaiting_customer" if isinstance(answered, Offer) else "expired")


@pytest.mark.parametrize("second", ["accept", "counter"])
async def test_two_tabs_withdraw_racing_an_answer(db_engine: AsyncEngine, second: str) -> None:
    """The customer's two tabs serialise: withdrawing after an accept is refused, while
    withdrawing after a counter is still legal (BR-092), so then both land, in order."""
    user, _, offer = await _seed(db_engine, status="awaiting_customer")
    customer = Responder(OfferActor.CUSTOMER, user)

    def answer(deps: OfferDeps) -> Awaitable[Offer]:
        if second == "accept":
            return accept_offer(deps, customer, offer_id=offer, expected_amount_cents=800)
        return counter_offer(deps, customer, offer_id=offer, amount_cents=900, message=None)

    results = await _race(
        db_engine,
        lambda d: withdraw_offer(d, customer, offer_id=offer, reason=None),
        answer,
    )
    withdrawn, answered = results
    counted = await _rounds_and_audits(db_engine, offer)
    if isinstance(answered, Offer) and isinstance(withdrawn, Offer):
        assert second == "counter" and counted == (3, 2)
    else:
        assert sum(isinstance(r, NegotiationDomainError) for r in results) == 1
        assert counted == (2, 1)
    async with db_engine.connect() as conn:
        status = await conn.scalar(
            text("SELECT status::text FROM offers WHERE id = :o"), {"o": offer}
        )
    assert status in {"withdrawn", "accepted"}
    assert (status == "accepted") is isinstance(withdrawn, NegotiationDomainError)


async def test_overlapping_checkout_expiry_runs_close_once(db_engine: AsyncEngine) -> None:
    closes_at = datetime.now(UTC) - timedelta(minutes=1)
    _, _, offer = await _seed(
        db_engine, status="accepted", responds_by=None, checkout_expires_at=closes_at
    )

    class NoPayment:  # the offer has no order, so nothing is in flight
        async def in_flight(self, offer_id: uuid.UUID) -> bool:
            return False

    async def run(deps: OfferDeps) -> object:
        return await expire_checkout_offer(
            deps.offers,
            deps.notifier,
            deps.audit,
            NoPayment(),
            offer_id=offer,
            now=datetime.now(UTC),
        )

    assert sorted(map(bool, await _race(db_engine, run, run))) == [False, True]
    assert await _rounds_and_audits(db_engine, offer) == (2, 1)


async def _reminder_emails(engine: AsyncEngine, offer: uuid.UUID) -> int:
    async with engine.connect() as conn:
        sent = await conn.scalar(
            text(
                "SELECT count(*) FROM email_outbox WHERE payload->>'offer_id' = :s "
                "AND template = 'offer_expiring_soon'"
            ),
            {"s": str(offer)},
        )
    return int(sent or 0)


def _remind(offer: uuid.UUID, now: datetime) -> Action:
    def run(deps: OfferDeps) -> Awaitable[object]:
        return remind_offer(
            deps.offers, deps.products, deps.notifier, deps.mailer, offer_id=offer, now=now
        )

    return run


async def test_two_reminder_runs_at_once_send_one_email(db_engine: AsyncEngine) -> None:
    """ADR-035 d3: clearing `remind_at` under the row lock is the receipt."""
    now = datetime.now(UTC)
    _, _, offer = await _seed(
        db_engine, status="awaiting_customer", remind_at=now - timedelta(minutes=1)
    )
    results = await _race(db_engine, _remind(offer, now), _remind(offer, now))
    assert sorted(map(bool, results)) == [False, True]
    assert await _reminder_emails(db_engine, offer) == 1


async def test_a_reminder_racing_an_accept_never_undoes_it(db_engine: AsyncEngine) -> None:
    """The reminder writes the row back, so it must never do so from a stale read."""
    now = datetime.now(UTC)
    user, _, offer = await _seed(
        db_engine, status="awaiting_customer", remind_at=now - timedelta(minutes=1)
    )
    customer = Responder(OfferActor.CUSTOMER, user)
    _, answered = await _race(
        db_engine,
        _remind(offer, now),
        lambda d: accept_offer(d, customer, offer_id=offer, expected_amount_cents=800),
    )
    assert isinstance(answered, Offer)
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT status::text, remind_at FROM offers WHERE id = :o"), {"o": offer}
            )
        ).one()
    assert tuple(row) == ("accepted", None)


@pytest.mark.parametrize(
    "seed",
    [
        {"responds_by": -60},
        {"status": "accepted", "checkout_expires_at": -60},
        {"status": "awaiting_customer", "remind_at": -60},
    ],
    ids=["overdue", "checkout_window", "reminder"],
)
async def test_the_job_skips_a_locked_offer_instead_of_waiting(
    db_engine: AsyncEngine, seed: dict[str, Any]
) -> None:
    """ADR-035 d5: one row held by an answer must not stall the job; the next run takes it."""
    now = datetime.now(UTC)
    over = {k: now + timedelta(seconds=v) if isinstance(v, int) else v for k, v in seed.items()}
    _, _, offer = await _seed(db_engine, **over)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    ctx = {"session_factory": factory}

    async def written() -> tuple[int, int, int]:
        rounds, audits = await _rounds_and_audits(db_engine, offer)
        return rounds, audits, await _reminder_emails(db_engine, offer)

    async with factory() as holder, holder.begin():
        await holder.execute(text("SELECT 1 FROM offers WHERE id = :o FOR UPDATE"), {"o": offer})
        await asyncio.wait_for(expire_offers(ctx, now=now), timeout=20)
        assert await written() == (1, 0, 0)
    await expire_offers(ctx, now=now)
    assert await written() != (1, 0, 0)
