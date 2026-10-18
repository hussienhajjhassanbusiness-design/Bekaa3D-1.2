"""VS-024 store additions against Postgres (plan 3.4): the order's attempts locked by id,
the live attempt and its redirect URL, the latest provider, the stale-attempt page, and
the per-payment event count and close."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.payments.application.ports import NewWebhookEvent
from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.infrastructure.payments import SqlPaymentAttempts, SqlPaymentStore
from app.payments.infrastructure.webhook_events import SqlWebhookEventStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user
from tests.integration.ordering.test_lock_order import captured
from tests.integration.payments.support import seed_online_order

pytestmark = pytest.mark.integration

# Far before any other test's rows, so the stale page sees only this file's attempts.
EPOCH = datetime(1991, 3, 1, tzinfo=UTC)
# The stale page's own window: no other test here writes a live attempt in it.
STALE_EPOCH = datetime(1985, 3, 1, tzinfo=UTC)


async def _order(db: AsyncSession) -> uuid.UUID:
    user = await create_user(db)
    stl = await seed_product(db, await seed_refs(db), type=ProductType.STL)
    return await seed_online_order(db, user_id=user.id, stl_id=stl.id)


async def _attempt(
    db: AsyncSession, order_id: uuid.UUID, status: str, at: datetime, **extra: object
) -> uuid.UUID:
    payment_id = uuid.uuid4()
    stamps = {"failed": "failed_at", "expired": "expired_at", "paid": "verified_at"}
    row: dict[str, object] = {
        "id": payment_id,
        "order_id": order_id,
        "provider": "mock",
        "order_payment_method": "online",
        "status": status,
        "amount_cents": 1000,
        "initiated_at": at,
    } | extra
    if status in stamps:
        row[stamps[status]] = at
    columns = ", ".join(row)
    values = ", ".join(f"CAST(:{k} AS jsonb)" if k == "provider_metadata" else f":{k}" for k in row)
    await db.execute(text(f"INSERT INTO payments ({columns}) VALUES ({values})"), row)
    await db.commit()
    return payment_id


async def test_lock_for_order_locks_every_attempt_by_id(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id = await _order(db_session)
    ids = [
        await _attempt(db_session, order_id, "failed", EPOCH),
        await _attempt(db_session, order_id, "expired", EPOCH + timedelta(minutes=1)),
        await _attempt(db_session, order_id, "pending", EPOCH + timedelta(minutes=2)),
    ]
    with captured(db_engine.sync_engine) as statements:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            locked = await SqlPaymentStore(session).lock_for_order(order_id)
    assert [p.id for p in locked] == sorted(ids)
    (select_,) = statements
    assert select_.endswith("ORDER BY payments.id FOR UPDATE"), select_


async def test_the_live_attempt_carries_its_redirect_url_outside_its_repr(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id = await _order(db_session)
    await _attempt(db_session, order_id, "failed", EPOCH)
    live = await _attempt(
        db_session,
        order_id,
        "processing",
        EPOCH + timedelta(minutes=1),
        provider_payment_id=f"mock_{uuid.uuid4().hex}",
        provider_metadata='{"redirect_url": "https://pay.example/secret-session"}',
    )
    async with async_sessionmaker(db_engine)() as session:
        payment = await SqlPaymentStore(session).live_for_order(order_id)
        ref = await SqlPaymentAttempts(session, {}).live_attempt(order_id)
    assert payment is not None and ref is not None
    assert (payment.id, ref.id, ref.status) == (live, live, "processing")
    assert payment.redirect_url == ref.redirect_url == "https://pay.example/secret-session"
    assert "secret-session" not in repr(payment) and "secret-session" not in repr(ref)
    assert payment.initiated_at == EPOCH + timedelta(minutes=1)


async def test_no_live_attempt_and_the_latest_provider(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id, fresh = await _order(db_session), await _order(db_session)
    await _attempt(db_session, order_id, "failed", EPOCH)
    await _attempt(db_session, order_id, "expired", EPOCH + timedelta(minutes=1))
    async with async_sessionmaker(db_engine)() as session:
        store, attempts = SqlPaymentStore(session), SqlPaymentAttempts(session, {})
        assert await store.live_for_order(order_id) is None
        assert await attempts.live_attempt(order_id) is None
        assert await store.previous_provider(order_id) is PaymentProvider.MOCK
        assert await attempts.previous_provider(order_id) == "mock"
        assert await attempts.previous_provider(fresh) is None


async def test_stale_live_ids_pages_only_old_online_live_attempts(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    stale = []
    for minute in range(5):
        order_id = await _order(db_session)
        stale.append(
            (
                STALE_EPOCH + timedelta(minutes=minute),
                await _attempt(
                    db_session, order_id, "pending", STALE_EPOCH + timedelta(minutes=minute)
                ),
            )
        )
    for status in ("paid", "failed", "expired"):
        await _attempt(db_session, await _order(db_session), status, STALE_EPOCH)
    await _attempt(db_session, await _order(db_session), "pending", STALE_EPOCH + timedelta(days=1))
    before = STALE_EPOCH + timedelta(hours=1)
    async with async_sessionmaker(db_engine)() as session:
        store = SqlPaymentStore(session)
        first = await store.stale_live_ids(before=before, after=None, limit=3)
        rest = await store.stale_live_ids(before=before, after=first[-1], limit=3)
    assert first + rest == stale


async def test_unprocessed_events_are_counted_and_closed_per_payment(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id = await _order(db_session)
    payment_id = await _attempt(db_session, order_id, "pending", EPOCH)
    other = await _attempt(db_session, await _order(db_session), "pending", EPOCH)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        events = SqlWebhookEventStore(session)
        for target, processed in ((payment_id, None), (payment_id, None), (payment_id, EPOCH)):
            await events.insert_if_new(_new_event(target, processed))
        await events.insert_if_new(_new_event(other, None))
    at = datetime.now(UTC)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        events = SqlWebhookEventStore(session)
        assert await events.count_unprocessed_for_payment(payment_id) == 2
        assert await events.mark_processed_for_payment(payment_id, at=at) == 2
        assert await events.count_unprocessed_for_payment(payment_id) == 0
        assert await events.count_unprocessed_for_payment(other) == 1


def _new_event(payment_id: uuid.UUID, processed_at: datetime | None) -> NewWebhookEvent:
    return NewWebhookEvent(
        provider=PaymentProvider.MOCK,
        provider_event_id=f"ev_{uuid.uuid4().hex}",
        event_type="payment",
        payload={},
        signature_valid=True,
        provider_payment_id=None,
        payment_id=payment_id,
        processing_error=None,
        processed_at=processed_at,
    )


async def test_the_captured_amount_is_read_back(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id = await _order(db_session)
    payment_id = await _attempt(
        db_session, order_id, "paid", EPOCH, captured_amount_cents=1000, captured_currency="USD"
    )
    async with async_sessionmaker(db_engine)() as session:
        payment = await SqlPaymentStore(session).get(payment_id)
    assert payment is not None and payment.status is PaymentStatus.PAID
    assert (payment.captured_amount_cents, payment.captured_currency) == (1000, "USD")
