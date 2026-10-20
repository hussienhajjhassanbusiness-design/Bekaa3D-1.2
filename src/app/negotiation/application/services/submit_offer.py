"""`POST /offers` (FR-13, VS-039). Runs in the caller's session and never commits."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.negotiation.application.ports import (
    AuditWriter,
    CartProductReader,
    OfferNotifier,
    OfferSettings,
    OfferStore,
    StlOwnership,
)
from app.negotiation.domain.exceptions import OfferProductOwnedError, OffersPausedError
from app.negotiation.domain.offers import (
    ENTITY_TYPE,
    Offer,
    check_cooldown,
    check_offerable,
    open_offer,
)


@dataclass(frozen=True)
class OfferRequestContext:
    request_id: str | None = None
    ip_hash: str | None = None


async def submit_offer(
    *,
    offers: OfferStore,
    products: CartProductReader,
    ownership: StlOwnership,
    settings: OfferSettings,
    notifier: OfferNotifier,
    audit: AuditWriter,
    user_id: UUID,
    product_id: UUID,
    amount_cents: int,
    message: str | None,
    now: datetime,
    context: OfferRequestContext,
) -> Offer:
    if not await settings.get_bool("accepting_orders"):
        raise OffersPausedError()
    product = check_offerable((await products.get_many([product_id])).get(product_id), product_id)
    if await ownership.owns(user_id, product_id):
        raise OfferProductOwnedError()
    new = open_offer(
        product,
        user_id=user_id,
        amount_cents=amount_cents,
        message=message,
        percentage=await settings.get_int("minimum_offer_percentage"),
        response_window_seconds=await settings.get_duration_seconds("offer_response_window"),
        now=now,
    )
    offer = await offers.add(new, at=now)
    # After the insert, not before: it can only succeed once a racing rejection has
    # committed, so this read sees that rejection's cooldown (ADR-034).
    check_cooldown(await offers.cooldowns(user_id, product_id), now)
    await audit.record(
        actor_user_id=user_id,
        action="offer.submitted",
        entity_type=ENTITY_TYPE,
        entity_id=offer.id,
        after_data={
            "product_id": str(product_id),
            "status": offer.status.value,
            "amount_cents": amount_cents,
            "currency": offer.currency,
            "responds_by": new.responds_by.isoformat(),
        },
        request_id=context.request_id,
        ip_hash=context.ip_hash,
    )
    await notifier.notify_administrators(
        {
            "event": "offer.submitted",
            "offer_id": str(offer.id),
            "product_id": str(product_id),
            "product_name": product.name,
            "amount_cents": amount_cents,
            "currency": offer.currency,
        }
    )
    return offer
