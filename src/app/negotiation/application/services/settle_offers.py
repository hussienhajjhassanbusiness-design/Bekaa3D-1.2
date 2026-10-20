"""An STL was paid (SRS 5.4 step 6, BR-088, VS-041): the offer it was bought through becomes
`paid`, any other live offer on it `auto_closed`. Runs in the payment's own transaction,
after its orders, lines and payment locks (ADR-037)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from app.negotiation.application.ports import AuditWriter, OfferStore
from app.negotiation.domain.enums import OfferStatus
from app.negotiation.domain.offers import ENTITY_TYPE, auto_close, mark_paid

logger = structlog.get_logger()


@dataclass(frozen=True)
class StlPurchase:
    order_id: UUID
    user_id: UUID
    product_id: UUID
    offer_id: UUID | None


async def settle_stl_purchases(
    offers: OfferStore, audit: AuditWriter, purchases: Sequence[StlPurchase], *, now: datetime
) -> None:
    """Advisory locks first, then each product's live offer, all in product order."""
    ordered = sorted(purchases, key=lambda p: p.product_id.bytes)
    for purchase in ordered:
        await offers.lock_acquisition(purchase.user_id, purchase.product_id)
    for purchase in ordered:
        await _settle(offers, audit, purchase, now)


async def _settle(
    offers: OfferStore, audit: AuditWriter, purchase: StlPurchase, now: datetime
) -> None:
    paid_through_offer = False
    for offer in await offers.lock_live(purchase.user_id, purchase.product_id):
        sequence = await offers.next_sequence(offer.id)
        if offer.id == purchase.offer_id and offer.status is OfferStatus.ACCEPTED:
            closed, round_ = mark_paid(offer, next_sequence=sequence, now=now)
            action, paid_through_offer = "offer.paid", True
        else:
            closed, round_ = auto_close(offer, next_sequence=sequence, now=now)
            action = "offer.auto_closed"
        await offers.save_state(closed)
        await offers.add_round(offer.id, round_, at=now)
        await audit.record(
            actor_user_id=None,
            action=action,
            entity_type=ENTITY_TYPE,
            entity_id=offer.id,
            before_data={"status": offer.status.value},
            after_data={
                "status": closed.status.value,
                "order_id": str(purchase.order_id),
                "agreed_amount_cents": offer.agreed_amount_cents,
            },
        )
    if purchase.offer_id is not None and not paid_through_offer:
        # Unreachable while retry and the expiry job hold the offer lock (ADR-037); the
        # line is paid at its agreed price regardless, so this is reported, not refused.
        await logger.aerror(
            "offer_paid_out_of_state",
            offer_id=str(purchase.offer_id),
            order_id=str(purchase.order_id),
        )
