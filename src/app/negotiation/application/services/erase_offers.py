"""Account deletion withdraws every live offer (VS-045, ADR-047). Runs in the deletion's
transaction: the offers are locked before the user row, and again here to read them as now."""

from datetime import datetime
from uuid import UUID

from app.negotiation.application.ports import OfferStore
from app.negotiation.domain.offers import withdraw_for_erasure


async def lock_live_offers(offers: OfferStore, user_id: UUID) -> None:
    await offers.lock_live_for_user(user_id)


async def withdraw_live_offers(offers: OfferStore, user_id: UUID, *, now: datetime) -> int:
    """No notification and no per-offer audit row: the deletion's one audit row counts them."""
    live = await offers.lock_live_for_user(user_id)
    for offer in live:
        withdrawn, round_ = withdraw_for_erasure(
            offer, next_sequence=await offers.next_sequence(offer.id), now=now
        )
        await offers.save_state(withdrawn)
        await offers.add_round(offer.id, round_, at=now)
    return len(live)
