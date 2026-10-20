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
from app.negotiation.api.wiring import offer_deps
from app.negotiation.application.services.expire_offers import expire_offer
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
    now = datetime.now(UTC)
    results = await _race(
        db_engine,
        lambda d: accept_offer(d, admin, offer_id=offer, now=now),
        lambda d: reject_offer(d, admin, offer_id=offer, reason=None, now=now),
    )
    assert sum(isinstance(r, Offer) for r in results) == 1
    assert sum(isinstance(r, OfferInvalidTransitionError) for r in results) == 1
    assert await _rounds_and_audits(db_engine, offer) == (2, 1)


async def test_withdraw_racing_admin_accept_one_wins(db_engine: AsyncEngine) -> None:
    user, admin, offer = await _seed(db_engine)
    customer = Responder(OfferActor.CUSTOMER, user)
    now = datetime.now(UTC)
    results = await _race(
        db_engine,
        lambda d: withdraw_offer(d, customer, offer_id=offer, reason=None, now=now),
        lambda d: accept_offer(d, admin, offer_id=offer, now=now),
    )
    assert sum(isinstance(r, Offer) for r in results) == 1
    assert sum(isinstance(r, OfferInvalidTransitionError) for r in results) == 1
    assert await _rounds_and_audits(db_engine, offer) == (2, 1)


async def test_a_double_clicked_counter_counts_once(db_engine: AsyncEngine) -> None:
    """The second sees the turn already passed: 409, never a second round."""
    _, admin, offer = await _seed(db_engine)
    now = datetime.now(UTC)

    def counter(deps: OfferDeps) -> Awaitable[Offer]:
        return counter_offer(deps, admin, offer_id=offer, amount_cents=900, message=None, now=now)

    results = await _race(db_engine, counter, counter)
    assert sum(isinstance(r, Offer) for r in results) == 1
    assert sum(isinstance(r, OfferNotYourTurnError) for r in results) == 1
    assert await _rounds_and_audits(db_engine, offer) == (2, 1)


async def test_a_last_second_answer_racing_the_expiry_job(db_engine: AsyncEngine) -> None:
    """ADR-034 d6: whichever locks first wins; the offer is never both countered and expired."""
    deadline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    _, admin, offer = await _seed(db_engine, responds_by=deadline)

    async def answer(deps: OfferDeps) -> object:
        return await counter_offer(
            deps,
            admin,
            offer_id=offer,
            amount_cents=900,
            message=None,
            now=deadline - timedelta(seconds=1),
        )

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
