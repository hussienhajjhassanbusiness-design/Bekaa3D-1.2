"""Helpers for the VS-041 suites: an offer's order and attempt written straight to the
database, and paying an attempt through the real apply path (orders, lines, payment)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.public import apply_provider_result
from tests.integration.payments.support import seed_online_order


async def seed_order_with_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    product_id: uuid.UUID,
    amount: int = 800,
    offer_id: uuid.UUID | None = None,
    attempt: str = "pending",
    placed_at: datetime | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """An unpaid STL order (from the offer when `offer_id`) and one attempt in `attempt`."""
    at = placed_at or datetime.now(UTC)
    source = "offer" if offer_id else "cart"
    order_id = await seed_online_order(
        db, user_id=user_id, stl_id=product_id, total_cents=amount, source=source, placed_at=at
    )
    if offer_id is not None:
        await db.execute(
            text("UPDATE order_items SET offer_id = :f WHERE order_id = :o"),
            {"f": offer_id, "o": order_id},
        )
    payment_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO payments (id, order_id, provider, order_payment_method, status,"
            " amount_cents, initiated_at, failed_at, expired_at)"
            " VALUES (:id, :o, 'mock', 'online', :s, :a, :t, :f, :e)"
        ),
        {
            "id": payment_id,
            "o": order_id,
            "s": attempt,
            "a": amount,
            "t": at,
            "f": at if attempt == "failed" else None,
            "e": at if attempt == "expired" else None,
        },
    )
    await db.commit()
    return order_id, payment_id


async def pay(engine: AsyncEngine, payment_id: uuid.UUID, amount: int = 800) -> Outcome:
    """The provider answers `paid` for exactly `amount`, applied as reconciliation would."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        return await apply_provider_result(
            session,
            payment_id,
            ProviderResult("paid", amount, "USD"),
            source="reconcile",
            actor_user_id=None,
        )


async def line_status(engine: AsyncEngine, order_id: uuid.UUID) -> str:
    async with engine.connect() as conn:
        return str(
            await conn.scalar(
                text("SELECT fulfillment_status FROM order_items WHERE order_id = :o"),
                {"o": order_id},
            )
        )
