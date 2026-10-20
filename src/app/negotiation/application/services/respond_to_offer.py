"""Counter, accept, reject, withdraw (FR-13, VS-040; ADR-035). Each locks the offer, checks it
under the lock, and writes round, audit, notification and email in the caller's transaction."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.catalog.application.ports import CartProduct
from app.negotiation.application.ports import (
    AuditWriter,
    CartProductReader,
    OfferMailer,
    OfferNotifier,
    OfferSettings,
    OfferStore,
    StlOwnership,
)
from app.negotiation.application.services.submit_offer import OfferRequestContext
from app.negotiation.domain.enums import OfferActor
from app.negotiation.domain.exceptions import OfferNotFoundError, OfferProductOwnedError
from app.negotiation.domain.offers import (
    ENTITY_TYPE,
    NewRound,
    Offer,
    OfferMove,
    accept,
    check_amount_seen,
    check_move,
    check_negotiable,
    counter,
    reject,
    withdraw,
)

COUNTERED_TEMPLATE = "offer_countered"
ACCEPTED_TEMPLATE = "offer_accepted"
REJECTED_TEMPLATE = "offer_rejected"


@dataclass(frozen=True)
class OfferDeps:
    offers: OfferStore
    products: CartProductReader
    ownership: StlOwnership
    settings: OfferSettings
    notifier: OfferNotifier
    mailer: OfferMailer
    audit: AuditWriter
    # Read only once the row lock is held: a wait on the lock must not outlast the deadline.
    clock: Callable[[], datetime]


@dataclass(frozen=True)
class Responder:
    """Who answers: a customer only ever reaches their own offer (404 otherwise)."""

    actor: OfferActor
    user_id: UUID
    context: OfferRequestContext = field(default_factory=OfferRequestContext)

    @property
    def scope(self) -> UUID | None:
        return self.user_id if self.actor is OfferActor.CUSTOMER else None


async def counter_offer(
    deps: OfferDeps,
    who: Responder,
    *,
    offer_id: UUID,
    amount_cents: int,
    message: str | None,
) -> Offer:
    offer, now = await _locked(deps, who, offer_id, OfferMove.COUNTER)
    product = await _negotiable(deps, offer)
    countered, round_ = counter(
        offer,
        actor=who.actor,
        amount_cents=amount_cents,
        message=message,
        list_price_cents=product.price_cents,
        percentage=await deps.settings.get_int("minimum_offer_percentage"),
        response_window_seconds=await deps.settings.get_duration_seconds("offer_response_window"),
        next_sequence=await deps.offers.next_sequence(offer.id),
        now=now,
    )
    details = {
        "amount_cents": amount_cents,
        "currency": offer.currency,
        "responds_by": _iso(countered.responds_by),
    }
    await _write(deps, who, offer, countered, round_, "offer.countered", details, now)
    # SRS 16.1 emails the customer only; the administrator learns in-app.
    template = COUNTERED_TEMPLATE if who.actor is OfferActor.ADMIN else None
    await _tell(deps, who, countered, product.name, "offer.countered", details, template)
    return countered


async def accept_offer(
    deps: OfferDeps, who: Responder, *, offer_id: UUID, expected_amount_cents: int
) -> Offer:
    offer, now = await _locked(deps, who, offer_id, OfferMove.ACCEPT)
    check_amount_seen(offer, expected_amount_cents)
    product = await _negotiable(deps, offer)
    # FR-13: acquisition racing acceptance is re-checked here; VS-041 closes the offer.
    if await deps.ownership.owns(offer.user_id, offer.product_id):
        raise OfferProductOwnedError()
    accepted, round_ = accept(
        offer,
        actor=who.actor,
        expected_amount_cents=expected_amount_cents,
        list_price_cents=product.price_cents,
        checkout_window_seconds=await deps.settings.get_duration_seconds("offer_checkout_window"),
        next_sequence=await deps.offers.next_sequence(offer.id),
        now=now,
    )
    details = {
        "agreed_amount_cents": accepted.agreed_amount_cents,
        "currency": offer.currency,
        "checkout_expires_at": _iso(accepted.checkout_expires_at),
    }
    await _write(deps, who, offer, accepted, round_, "offer.accepted", details, now)
    await _tell(deps, who, accepted, product.name, "offer.accepted", details, ACCEPTED_TEMPLATE)
    if who.actor is OfferActor.CUSTOMER:
        # ADR-035 d7: the customer's own list shows the checkout deadline too.
        body = {
            "event": "offer.accepted",
            "offer_id": str(accepted.id),
            "product_id": str(accepted.product_id),
            "product_name": product.name,
        } | details
        await deps.notifier.notify_customer(accepted.user_id, body)
    return accepted


async def reject_offer(
    deps: OfferDeps, who: Responder, *, offer_id: UUID, reason: str | None
) -> Offer:
    offer, now = await _locked(deps, who, offer_id, OfferMove.REJECT)
    rejected, round_ = reject(
        offer,
        reason=reason,
        cooldown_seconds=await deps.settings.get_duration_seconds("offer_rejection_cooldown"),
        next_sequence=await deps.offers.next_sequence(offer.id),
        now=now,
    )
    details = {"cooldown_until": _iso(rejected.cooldown_until)}
    await _write(deps, who, offer, rejected, round_, "offer.rejected", details, now)
    name = await _product_name(deps, offer)
    await _tell(deps, who, rejected, name, "offer.rejected", details, REJECTED_TEMPLATE)
    return rejected


async def withdraw_offer(
    deps: OfferDeps, who: Responder, *, offer_id: UUID, reason: str | None
) -> Offer:
    offer, now = await _locked(deps, who, offer_id, OfferMove.WITHDRAW)
    withdrawn, round_ = withdraw(
        offer, reason=reason, next_sequence=await deps.offers.next_sequence(offer.id), now=now
    )
    await _write(deps, who, offer, withdrawn, round_, "offer.withdrawn", {}, now)
    name = await _product_name(deps, offer)
    await _tell(deps, who, withdrawn, name, "offer.withdrawn", {}, None)
    return withdrawn


async def _locked(
    deps: OfferDeps, who: Responder, offer_id: UUID, move: OfferMove
) -> tuple[Offer, datetime]:
    """The offer under its row lock, and the time read after taking it."""
    offer = await deps.offers.lock(offer_id, user_id=who.scope)
    if offer is None:
        raise OfferNotFoundError()
    now = deps.clock()
    check_move(offer, who.actor, move, now)
    return offer, now


async def _negotiable(deps: OfferDeps, offer: Offer) -> CartProduct:
    found = await deps.products.get_many([offer.product_id])
    return check_negotiable(found.get(offer.product_id), offer.product_id)


async def _product_name(deps: OfferDeps, offer: Offer) -> str | None:
    product = (await deps.products.get_many([offer.product_id])).get(offer.product_id)
    return product.name if product is not None else None


async def _write(
    deps: OfferDeps,
    who: Responder,
    before: Offer,
    after: Offer,
    round_: NewRound,
    action: str,
    details: dict[str, Any],
    now: datetime,
) -> None:
    await deps.offers.save_state(after)
    await deps.offers.add_round(after.id, round_, at=now)
    await deps.audit.record(
        actor_user_id=who.user_id,
        action=action,
        entity_type=ENTITY_TYPE,
        entity_id=after.id,
        before_data={
            "status": before.status.value,
            "turn": before.turn and before.turn.value,
            "current_amount_cents": before.current_amount_cents,
        },
        after_data={"status": after.status.value, "turn": after.turn and after.turn.value}
        | details,
        request_id=who.context.request_id,
        ip_hash=who.context.ip_hash,
    )


async def _tell(
    deps: OfferDeps,
    who: Responder,
    offer: Offer,
    product_name: str | None,
    event: str,
    details: dict[str, Any],
    template: str | None,
) -> None:
    """In-app to the other party; email, when SRS 16.1 lists one, always to the customer."""
    body = {
        "offer_id": str(offer.id),
        "product_id": str(offer.product_id),
        "product_name": product_name,
    } | details
    if who.actor is OfferActor.ADMIN:
        await deps.notifier.notify_customer(offer.user_id, {"event": event} | body)
    else:
        await deps.notifier.notify_administrators({"event": event} | body)
    if template is not None:
        await deps.mailer.send(offer.user_id, template, body)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None
