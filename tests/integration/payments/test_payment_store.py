"""SqlPaymentStore and the Ordering-port adapter against Postgres (VS-023 plan 3.6)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.payments.domain.enums import PaymentProvider, PaymentStatus
from app.payments.infrastructure.payments import SqlPaymentAttempts, SqlPaymentStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user
from tests.integration.payments.support import NOW, seed_online_order

pytestmark = pytest.mark.integration


async def _order(db: AsyncSession) -> uuid.UUID:
    user = await create_user(db)
    stl = await seed_product(db, await seed_refs(db), type=ProductType.STL)
    return await seed_online_order(db, user_id=user.id, stl_id=stl.id)


async def test_open_attempt_inserts_one_pending_online_payment(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id = await _order(db_session)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        attempts = SqlPaymentAttempts(session, {"mock": object()})  # type: ignore[dict-item]
        assert attempts.configured_providers() == frozenset({"mock"})
        ref = await attempts.open_attempt(
            order_id=order_id, amount_cents=1000, currency="USD", provider="mock", at=NOW
        )
    assert (ref.provider, ref.status, ref.amount_cents, ref.currency) == (
        "mock",
        "pending",
        1000,
        "USD",
    )
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT order_payment_method, provider_payment_id FROM payments WHERE id = :i"
                ),
                {"i": ref.id},
            )
        ).one()
    assert (row.order_payment_method, row.provider_payment_id) == ("online", None)


async def test_the_reference_is_stored_once_and_failure_moves_only_a_pending_attempt(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id = await _order(db_session)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        store = SqlPaymentStore(session)
        payment = await store.insert_pending(
            order_id=order_id,
            provider=PaymentProvider.MOCK,
            amount_cents=1000,
            currency="USD",
            at=NOW,
        )
        await store.set_provider_reference(payment.id, "mock_a", redirect_url="http://x/r", at=NOW)
        await store.set_provider_reference(payment.id, "mock_b", redirect_url=None, at=NOW)
        await store.mark_failed(payment.id, at=NOW)
        await store.mark_failed(payment.id, at=NOW)
        stored = await store.get(payment.id)
        found = await store.find_by_reference(PaymentProvider.MOCK, "mock_a")
    assert stored is not None and found == stored
    assert (stored.provider_payment_id, stored.status) == ("mock_a", PaymentStatus.FAILED)
    async with db_engine.connect() as conn:
        meta = await conn.scalar(
            text("SELECT provider_metadata FROM payments WHERE id = :i"), {"i": payment.id}
        )
    assert meta == {"redirect_url": "http://x/r"}


async def test_mark_failed_never_undoes_a_paid_attempt(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order_id = await _order(db_session)
    async with async_sessionmaker(db_engine)() as session, session.begin():
        store = SqlPaymentStore(session)
        payment = await store.insert_pending(
            order_id=order_id,
            provider=PaymentProvider.MOCK,
            amount_cents=1000,
            currency="USD",
            at=NOW,
        )
        await session.execute(
            text("UPDATE payments SET status = 'paid', verified_at = now() WHERE id = :i"),
            {"i": payment.id},
        )
        await store.mark_failed(payment.id, at=NOW)
        locked = await store.lock(payment.id)
    assert locked is not None and locked.status is PaymentStatus.PAID
