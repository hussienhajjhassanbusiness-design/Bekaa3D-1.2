"""`expire_offers`' VS-040 passes against real PostgreSQL: the checkout window (BR-086,
F-095) and the customer's "expiring soon" email (SRS 16.1; ADR-035)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs.expire_offers import expire_offers
from app.negotiation import public as negotiation_public
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.negotiation.offer_support import (
    offer_state,
    seed_offer,
    side_effects,
    stl,
)

pytestmark = pytest.mark.integration
SECOND = timedelta(seconds=1)
NOW_MINUS = datetime(2001, 1, 1, tzinfo=UTC)


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


async def _accepted(db: AsyncSession, closes_at: datetime) -> uuid.UUID:
    user = (await create_user(db)).id
    return await seed_offer(
        db,
        user_id=user,
        product_id=await stl(db),
        status="accepted",
        responds_by=None,
        checkout_expires_at=closes_at,
    )


async def _reminded(db: AsyncSession, remind_at: datetime, deadline: datetime) -> uuid.UUID:
    user = (await create_user(db)).id
    return await seed_offer(
        db,
        user_id=user,
        product_id=await stl(db),
        status="awaiting_customer",
        responds_by=deadline,
        remind_at=remind_at,
    )


@pytest.mark.parametrize(
    ("offset", "closed"), [(-SECOND, False), (timedelta(0), True), (SECOND, True)]
)
async def test_the_checkout_window_closes_at_its_deadline(
    db_session: AsyncSession, db_engine: AsyncEngine, offset: timedelta, closed: bool
) -> None:
    closes_at = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=10)
    offer = await _accepted(db_session, closes_at)
    await expire_offers(_ctx(db_engine), now=closes_at + offset)
    state = await offer_state(db_engine, offer)
    assert state["status"] == ("checkout_expired" if closed else "accepted")
    effects = await side_effects(db_engine, offer)
    if closed:
        assert state["rounds"][-1] == "2:system:checkout_expired:-"
        assert (state["agreed_amount_cents"], state["checkout_expires_at"]) == (800, closes_at)
        assert effects == {
            "audits": ["offer.checkout_expired"],
            "notifications": ["offer.checkout_expired"],
            "emails": [],
        }
    else:
        assert len(state["rounds"]) == 1 and effects["audits"] == []


async def test_checkout_expiry_rerun_is_a_noop(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    offer = await _accepted(db_session, datetime.now(UTC) - timedelta(minutes=1))
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    first = await offer_state(db_engine, offer)
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    assert await offer_state(db_engine, offer) == first
    assert len((await side_effects(db_engine, offer))["audits"]) == 1


async def test_a_closed_checkout_frees_the_product_for_a_new_offer(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    user = (await create_user(db_session)).id
    product = await stl(db_session)
    await seed_offer(
        db_session,
        user_id=user,
        product_id=product,
        status="accepted",
        checkout_expires_at=datetime.now(UTC) - SECOND,
    )
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    await seed_offer(db_session, user_id=user, product_id=product)


@pytest.mark.parametrize(
    ("offset", "sent"), [(-SECOND, False), (timedelta(0), True), (SECOND, True)]
)
async def test_the_reminder_is_sent_from_remind_at(
    db_session: AsyncSession, db_engine: AsyncEngine, offset: timedelta, sent: bool
) -> None:
    remind_at = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=10)
    offer = await _reminded(db_session, remind_at, remind_at + timedelta(minutes=15))
    await expire_offers(_ctx(db_engine), now=remind_at + offset)
    effects = await side_effects(db_engine, offer)
    state = await offer_state(db_engine, offer)
    assert effects["emails"] == (["offer_expiring_soon"] if sent else [])
    assert effects["notifications"] == (["offer.expiring_soon"] if sent else [])
    assert state["remind_at"] == (None if sent else remind_at)
    assert state["status"] == "awaiting_customer" and len(state["rounds"]) == 1


async def test_the_reminder_is_sent_once(db_session: AsyncSession, db_engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    offer = await _reminded(db_session, now - SECOND, now + timedelta(hours=1))
    for _ in range(3):
        await expire_offers(_ctx(db_engine), now=now)
    assert (await side_effects(db_engine, offer))["emails"] == ["offer_expiring_soon"]


async def test_an_offer_already_past_its_deadline_expires_without_a_reminder(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    now = datetime.now(UTC)
    offer = await _reminded(db_session, now - timedelta(hours=1), now - SECOND)
    await expire_offers(_ctx(db_engine), now=now)
    state = await offer_state(db_engine, offer)
    assert (state["status"], state["remind_at"]) == ("expired", None)
    assert (await side_effects(db_engine, offer))["emails"] == []


async def test_one_failing_offer_never_stalls_the_other_passes(
    db_session: AsyncSession, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row that fails every run is logged and skipped; checkout expiry still happens."""
    user = (await create_user(db_session)).id
    stuck = await seed_offer(
        db_session, user_id=user, product_id=await stl(db_session), responds_by=NOW_MINUS
    )
    accepted = await _accepted(db_session, datetime.now(UTC) - SECOND)

    async def broken(*_: Any, offer_id: uuid.UUID, **__: Any) -> bool:
        raise RuntimeError(f"offer {offer_id} is unreadable")

    monkeypatch.setattr(negotiation_public, "expire_offer", broken)
    result = await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    assert result["expired"] == 0 and result["checkout_expired"] >= 1
    assert (await offer_state(db_engine, stuck))["status"] == "awaiting_admin"
    assert (await offer_state(db_engine, accepted))["status"] == "checkout_expired"
