"""`expire_offers` (BR-084, BR-086, F-093, F-095): one offer per call, in the caller's
transaction; each locks with SKIP LOCKED and re-checks, so reruns and races are no-ops."""

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from app.negotiation.application.ports import (
    AuditWriter,
    CartProductReader,
    OfferMailer,
    OfferNotifier,
    OfferStore,
)
from app.negotiation.domain.offers import (
    ENTITY_TYPE,
    expire,
    expire_checkout,
    is_checkout_over,
    is_overdue,
    is_reminder_due,
)

EXPIRING_SOON_TEMPLATE = "offer_expiring_soon"


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


async def expire_checkout_offer(
    offers: OfferStore,
    notifier: OfferNotifier,
    audit: AuditWriter,
    *,
    offer_id: UUID,
    now: datetime,
) -> bool:
    """`accepted -> checkout_expired`; SRS 16.1 lists no email for it, so in-app only."""
    offer = await offers.lock_unless_locked(offer_id)
    if offer is None or not is_checkout_over(offer, now):
        return False
    closed, round_ = expire_checkout(
        offer, next_sequence=await offers.next_sequence(offer.id), now=now
    )
    await offers.save_state(closed)
    await offers.add_round(offer.id, round_, at=now)
    await audit.record(
        actor_user_id=None,
        action="offer.checkout_expired",
        entity_type=ENTITY_TYPE,
        entity_id=offer.id,
        before_data={"status": offer.status.value},
        after_data={
            "status": closed.status.value,
            "checkout_expires_at": _iso(offer.checkout_expires_at),
        },
    )
    await notifier.notify_customer(
        offer.user_id,
        {
            "event": "offer.checkout_expired",
            "offer_id": str(offer.id),
            "product_id": str(offer.product_id),
        },
    )
    return True


async def remind_offer(
    offers: OfferStore,
    products: CartProductReader,
    notifier: OfferNotifier,
    mailer: OfferMailer,
    *,
    offer_id: UUID,
    now: datetime,
) -> bool:
    """The "expiring soon" email, once per customer turn: clearing `remind_at` is the receipt."""
    offer = await offers.lock_unless_locked(offer_id)
    if offer is None or offer.remind_at is None or offer.remind_at > now:
        return False
    await offers.save_state(replace(offer, remind_at=None))
    if not is_reminder_due(offer, now):
        return False
    product = (await products.get_many([offer.product_id])).get(offer.product_id)
    body = {
        "offer_id": str(offer.id),
        "product_id": str(offer.product_id),
        "product_name": product.name if product is not None else None,
        "amount_cents": offer.current_amount_cents,
        "currency": offer.currency,
        "responds_by": _iso(offer.responds_by),
    }
    await mailer.send(offer.user_id, EXPIRING_SOON_TEMPLATE, body)
    await notifier.notify_customer(offer.user_id, {"event": "offer.expiring_soon"} | body)
    return True


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None
