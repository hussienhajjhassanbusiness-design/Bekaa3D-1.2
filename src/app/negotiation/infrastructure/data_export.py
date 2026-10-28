"""VS-044's offer read: every offer of the user with its complete round history."""

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.negotiation.domain.offers import Offer, OfferRound
from app.negotiation.infrastructure.offers import _O, _OFFER_COLUMNS, _R, _ROUND_COLUMNS, _offer

_COLS = _ROUND_COLUMNS


@dataclass(frozen=True)
class ExportOfferRow:
    offer: Offer
    rounds: list[OfferRound]


async def offers_for_export(session: AsyncSession, user_id: UUID) -> list[ExportOfferRow]:
    """Oldest first; the rounds in sequence order."""
    stmt = select(*_OFFER_COLUMNS).where(_O.user_id == user_id).order_by(_O.created_at, _O.id)
    offers = [_offer(row) for row in (await session.execute(stmt)).all()]
    if not offers:
        return []
    rounds: dict[UUID, list[OfferRound]] = defaultdict(list)
    found = await session.execute(
        select(*_ROUND_COLUMNS)
        .where(_R.offer_id.in_([offer.id for offer in offers]))
        .order_by(_R.offer_id, _R.sequence)
    )
    for row in found.all():
        rounds[row.offer_id].append(OfferRound(**{c.key: getattr(row, c.key) for c in _COLS}))
    return [ExportOfferRow(offer, rounds[offer.id]) for offer in offers]
