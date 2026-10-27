"""Negotiation's reporting read (VS-043): live offers now, by status. Unlocked, read-only."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.negotiation.domain.enums import OfferStatus
from app.negotiation.infrastructure.models import OfferModel

LIVE_STATUSES = (OfferStatus.AWAITING_ADMIN, OfferStatus.AWAITING_CUSTOMER, OfferStatus.ACCEPTED)


async def live_offer_counts(session: AsyncSession) -> dict[str, int]:
    """Every live status (`LIVE_SQL`) present, absent ones as 0 (`ix_offers_status_responds_by`)."""
    query = (
        select(OfferModel.status, func.count())
        .where(OfferModel.status.in_(LIVE_STATUSES))
        .group_by(OfferModel.status)
    )
    found = {str(status): int(n) for status, n in (await session.execute(query)).tuples()}
    return {str(status): found.get(str(status), 0) for status in LIVE_STATUSES}
