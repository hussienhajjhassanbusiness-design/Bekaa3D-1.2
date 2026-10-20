"""Negotiation's published surface for other contexts and the worker. Another context imports
only this or `app.negotiation.application.ports` (`tests/unit/test_deep_architecture.py`)."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog.public import cart_product_reader
from app.negotiation.application.services.expire_offers import (
    expire_checkout_offer,
    expire_offer,
    remind_offer,
)
from app.negotiation.infrastructure.adapters import EngagementOfferNotifier, PlatformOfferMailer
from app.negotiation.infrastructure.offers import SqlOfferStore
from app.platform.public import SqlAuditWriter

__all__ = ["expire_overdue_offers"]

logger = structlog.get_logger()


async def expire_overdue_offers(
    session_factory: async_sessionmaker[AsyncSession], *, now: datetime, limit: int
) -> dict[str, int]:
    """Three passes - inactivity, checkout window, reminders - each SRS 20.8's batch shape:
    candidates without a lock, then one short lock-and-recheck transaction per offer."""

    async def expire_one(session: AsyncSession, offer_id: UUID) -> bool:
        notifier, audit = EngagementOfferNotifier(session), SqlAuditWriter(session)
        return await expire_offer(
            SqlOfferStore(session), notifier, audit, offer_id=offer_id, now=now
        )

    async def close_checkout(session: AsyncSession, offer_id: UUID) -> bool:
        notifier, audit = EngagementOfferNotifier(session), SqlAuditWriter(session)
        return await expire_checkout_offer(
            SqlOfferStore(session), notifier, audit, offer_id=offer_id, now=now
        )

    async def remind(session: AsyncSession, offer_id: UUID) -> bool:
        return await remind_offer(
            SqlOfferStore(session),
            await cart_product_reader(session),
            EngagementOfferNotifier(session),
            PlatformOfferMailer(session),
            offer_id=offer_id,
            now=now,
        )

    async with session_factory() as session, session.begin():
        store = SqlOfferStore(session)
        overdue = await store.overdue_ids(now, limit)
        checkouts = await store.checkout_overdue_ids(now, limit)
        reminders = await store.reminder_due_ids(now, limit)
    return {
        "candidates": len(overdue),
        "expired": await _each(session_factory, overdue, expire_one),
        "checkout_candidates": len(checkouts),
        "checkout_expired": await _each(session_factory, checkouts, close_checkout),
        "reminded": await _each(session_factory, reminders, remind),
    }


async def _each(
    session_factory: async_sessionmaker[AsyncSession],
    ids: list[UUID],
    step: Callable[[AsyncSession, UUID], Awaitable[bool]],
) -> int:
    """One rolled-back failure is logged and skipped, so one bad row never stalls the rest."""
    done = 0
    for offer_id in ids:
        try:
            async with session_factory() as session, session.begin():
                done += await step(session, offer_id)
        except (OSError, DBAPIError) as exc:
            if isinstance(exc, OSError) or exc.connection_invalidated:
                raise
            await logger.aexception("expire_offers_step_failed", offer_id=str(offer_id))
        except Exception:
            await logger.aexception("expire_offers_step_failed", offer_id=str(offer_id))
    return done
