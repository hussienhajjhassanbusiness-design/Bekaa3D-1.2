"""The accepted offer as offer checkout and payment retry see it (VS-041, BR-086). Both
answer 404, 410 or 409 by the same rule; only `lock_for_checkout` decides."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.negotiation.application.ports import OfferStore
from app.negotiation.domain.exceptions import OfferNotFoundError
from app.negotiation.domain.offers import Offer, check_checkout


async def read_for_checkout(
    offers: OfferStore, *, offer_id: UUID, user_id: UUID, now: datetime
) -> Offer:
    """No lock: the refusals before any insert. The caller re-checks under the lock."""
    offer = await offers.get(offer_id, user_id=user_id)
    if offer is None:
        raise OfferNotFoundError()
    check_checkout(offer, now)
    return offer


async def lock_for_checkout(
    offers: OfferStore, *, offer_id: UUID, user_id: UUID, clock: Callable[[], datetime]
) -> Offer:
    """`FOR UPDATE`, then the clock: a wait on the lock must not outlast the window."""
    offer = await offers.lock(offer_id, user_id=user_id)
    if offer is None:
        raise OfferNotFoundError()
    check_checkout(offer, clock())
    return offer
