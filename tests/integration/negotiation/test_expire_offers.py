"""The `expire_offers` job against real PostgreSQL (VS-039; BR-084, BR-087, F-093)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.identity.domain.enums import UserRole
from app.jobs.expire_offers import expire_offers
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.negotiation.offer_support import seed_offer, set_setting, stl

pytestmark = pytest.mark.integration
SECOND = timedelta(seconds=1)


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


async def _overdue(
    db: AsyncSession, status: str, deadline: datetime
) -> tuple[uuid.UUID, uuid.UUID]:
    user = (await create_user(db)).id
    offer = await seed_offer(
        db, user_id=user, product_id=await stl(db), status=status, responds_by=deadline
    )
    return user, offer


async def _state(engine: AsyncEngine, offer: uuid.UUID) -> dict[str, Any]:
    sql = """
        SELECT o.status::text AS status, o.turn::text AS turn, o.responds_by,
          (SELECT array_agg(r.sequence || ':' || r.actor || ':' || r.action ORDER BY r.sequence)
             FROM offer_rounds r WHERE r.offer_id = o.id) AS rounds,
          (SELECT count(*) FROM audit_logs a WHERE a.entity_id = o.id
             AND a.action = 'offer.expired' AND a.actor_user_id IS NULL) AS audits,
          (SELECT count(*) FROM notifications n WHERE n.user_id = o.user_id AND n.type = 'offer'
             AND n.payload->>'event' = 'offer.expired'
             AND n.payload->>'offer_id' = o.id::text) AS notifications
        FROM offers o WHERE o.id = :o
    """
    async with engine.connect() as conn:
        return dict((await conn.execute(text(sql), {"o": offer})).one()._mapping)


@pytest.mark.parametrize("status", ["awaiting_admin", "awaiting_customer"])
async def test_an_overdue_offer_expires_with_a_system_round(
    db_session: AsyncSession, db_engine: AsyncEngine, status: str
) -> None:
    deadline = datetime.now(UTC).replace(microsecond=0) - SECOND
    await create_user(db_session, role=UserRole.ADMIN)
    owner, offer = await _overdue(db_session, status, deadline)
    result = await expire_offers(_ctx(db_engine), now=deadline + SECOND)
    assert result["expired"] >= 1
    state = await _state(db_engine, offer)
    assert state == {
        "status": "expired",
        "turn": None,
        "responds_by": deadline,
        "rounds": ["1:customer:submitted", "2:system:expired"],
        "audits": 1,
        "notifications": 1,
    }
    async with db_engine.connect() as conn:
        others = await conn.scalar(
            text(
                "SELECT count(*) FROM notifications WHERE payload->>'offer_id' = :o"
                " AND user_id <> :u"
            ),
            {"o": str(offer), "u": owner},
        )
    assert others == 0


@pytest.mark.parametrize(
    ("offset", "expired"),
    [(-SECOND, False), (timedelta(0), True), (SECOND, True)],
    ids=["deadline-1s", "at-deadline", "deadline+1s"],
)
async def test_expiry_boundary(
    db_session: AsyncSession, db_engine: AsyncEngine, offset: timedelta, expired: bool
) -> None:
    deadline = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=10)
    _, offer = await _overdue(db_session, "awaiting_admin", deadline)
    await expire_offers(_ctx(db_engine), now=deadline + offset)
    state = await _state(db_engine, offer)
    assert state["status"] == ("expired" if expired else "awaiting_admin")
    assert len(state["rounds"]) == (2 if expired else 1)


async def test_a_rerun_is_a_noop(db_session: AsyncSession, db_engine: AsyncEngine) -> None:
    deadline = datetime.now(UTC) - timedelta(minutes=1)
    _, offer = await _overdue(db_session, "awaiting_customer", deadline)
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    first = await _state(db_engine, offer)
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    assert await _state(db_engine, offer) == first
    assert (len(first["rounds"]), first["audits"], first["notifications"]) == (2, 1, 1)


@pytest.mark.parametrize(
    "status",
    ["accepted", "rejected", "expired", "withdrawn", "paid", "checkout_expired", "auto_closed"],
)
async def test_only_awaiting_offers_expire(
    db_session: AsyncSession, db_engine: AsyncEngine, status: str
) -> None:
    """BR-087: an accepted offer's inactivity timer is void, whatever `responds_by` says."""
    _, offer = await _overdue(db_session, status, datetime.now(UTC) - timedelta(days=3))
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    state = await _state(db_engine, offer)
    assert state["status"] == status and len(state["rounds"]) == 1 and state["audits"] == 0


async def test_kill_switch_does_not_stop_expiry(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """ADR-034: `accepting_orders` blocks new offers only."""
    _, offer = await _overdue(db_session, "awaiting_admin", datetime.now(UTC) - SECOND)
    before = await set_setting(db_engine, "accepting_orders", "false")
    try:
        await expire_offers(_ctx(db_engine), now=datetime.now(UTC))
    finally:
        await set_setting(db_engine, "accepting_orders", before)
    assert (await _state(db_engine, offer))["status"] == "expired"


async def test_a_capped_run_leaves_the_rest_for_the_next_tick(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """Soonest deadline first; the second run takes what the first could not."""
    far_past = datetime(2000, 1, 1, tzinfo=UTC)
    offers = [
        (await _overdue(db_session, "awaiting_admin", far_past - timedelta(minutes=i)))[1]
        for i in range(3)
    ]
    first = await expire_offers(_ctx(db_engine), now=datetime.now(UTC), limit=2)
    assert (first["candidates"], first["expired"]) == (2, 2)
    assert [(await _state(db_engine, o))["status"] for o in offers] == [
        "awaiting_admin",
        "expired",
        "expired",
    ]
    await expire_offers(_ctx(db_engine), now=datetime.now(UTC), limit=2)
    assert (await _state(db_engine, offers[0]))["status"] == "expired"
