"""`expire_offers` (BR-084, F-093): one overdue offer per call, in the caller's transaction."""

from datetime import datetime
from uuid import UUID

from app.negotiation.application.ports import AuditWriter, OfferNotifier, OfferStore
from app.negotiation.domain.offers import ENTITY_TYPE, expire, is_overdue


async def expire_offer(
    offers: OfferStore,
    notifier: OfferNotifier,
    audit: AuditWriter,
    *,
    offer_id: UUID,
    now: datetime,
) -> bool:
    """Lock, re-check, expire. False if another run holds it or it was answered meanwhile."""
    offer = await offers.lock_unless_locked(offer_id)
    if offer is None or not is_overdue(offer, now):
        return False
    expired, round_ = expire(offer, next_sequence=await offers.next_sequence(offer.id), now=now)
    await offers.save_state(expired)
    await offers.add_round(offer.id, round_, at=now)
    await audit.record(
        actor_user_id=None,
        action="offer.expired",
        entity_type=ENTITY_TYPE,
        entity_id=offer.id,
        before_data={"status": offer.status.value, "turn": offer.turn and offer.turn.value},
        after_data={"status": expired.status.value, "responds_by": _iso(offer.responds_by)},
    )
    await notifier.notify_customer(
        offer.user_id,
        {"event": "offer.expired", "offer_id": str(offer.id), "product_id": str(offer.product_id)},
    )
    return True


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None
