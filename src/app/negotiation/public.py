"""Negotiation's published surface for other contexts and the worker. Another context imports
only this or `app.negotiation.application.ports` (`tests/unit/test_deep_architecture.py`)."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.negotiation.application.services.expire_offers import expire_offer
from app.negotiation.infrastructure.adapters import EngagementOfferNotifier
from app.negotiation.infrastructure.offers import SqlOfferStore
from app.platform.public import SqlAuditWriter

__all__ = ["expire_overdue_offers"]


async def expire_overdue_offers(
    session_factory: async_sessionmaker[AsyncSession], *, now: datetime, limit: int
) -> dict[str, int]:
    """Candidates without a lock, then one short transaction per offer (lock, re-check,
    expire), so overlapping runs never expire one offer twice (SRS 20.8 batch shape)."""
    async with session_factory() as session, session.begin():
        candidates = await SqlOfferStore(session).overdue_ids(now, limit)
    expired = 0
    for offer_id in candidates:
        async with session_factory() as session, session.begin():
            expired += await expire_offer(
                SqlOfferStore(session),
                EngagementOfferNotifier(session),
                SqlAuditWriter(session),
                offer_id=offer_id,
                now=now,
            )
    return {"candidates": len(candidates), "expired": expired}
