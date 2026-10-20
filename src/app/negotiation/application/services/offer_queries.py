"""Offer reads for the customer and the administrator (FR-13, SRS 11.6). No locks."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import CartProduct
from app.negotiation.application.ports import (
    AdminOfferFilters,
    CartProductReader,
    CustomerDirectory,
    CustomerOfferFilters,
    OfferStore,
    QueuedOffer,
    QueueKey,
)
from app.negotiation.domain.enums import OfferActor
from app.negotiation.domain.offers import Offer, OfferRound, allowed_moves


@dataclass(frozen=True)
class OfferView:
    offer: Offer
    product: CartProduct | None
    rounds: tuple[OfferRound, ...] = ()
    customer_email: str | None = None
    allowed_actions: tuple[str, ...] = ()


async def customer_offers(
    offers: OfferStore,
    products: CartProductReader,
    *,
    user_id: UUID,
    filters: CustomerOfferFilters,
    after: tuple[datetime, UUID] | None,
    limit: int,
) -> list[OfferView]:
    page = await offers.customer_page(user_id, filters, after=after, limit=limit)
    found = await products.get_many([offer.product_id for offer in page])
    return [OfferView(offer, found.get(offer.product_id)) for offer in page]


async def offer_detail(
    offers: OfferStore,
    products: CartProductReader,
    *,
    offer_id: UUID,
    user_id: UUID | None = None,
    customers: CustomerDirectory | None = None,
    now: datetime | None = None,
) -> OfferView | None:
    """`user_id` scopes it to that customer (404 otherwise), else the administrator's view
    with the email; `now` fills `allowed_actions` for that viewer."""
    offer = await offers.get(offer_id, user_id=user_id)
    if offer is None:
        return None
    product = (await products.get_many([offer.product_id])).get(offer.product_id)
    email = (await customers.emails([offer.user_id])).get(offer.user_id) if customers else None
    viewer = OfferActor.CUSTOMER if user_id is not None else OfferActor.ADMIN
    moves = allowed_moves(offer, viewer, now) if now is not None else []
    rounds = tuple(await offers.rounds(offer.id))
    return OfferView(offer, product, rounds, email, tuple(move.value for move in moves))


async def admin_queue(
    offers: OfferStore,
    products: CartProductReader,
    customers: CustomerDirectory,
    *,
    filters: AdminOfferFilters,
    after: QueueKey | None,
    limit: int,
) -> list[tuple[OfferView, QueueKey]]:
    page: list[QueuedOffer] = await offers.queue_page(filters, after=after, limit=limit)
    found = await products.get_many([row.offer.product_id for row in page])
    emails = await customers.emails(list({row.offer.user_id for row in page}))
    return [
        (
            OfferView(
                row.offer,
                found.get(row.offer.product_id),
                customer_email=emails.get(row.offer.user_id),
            ),
            row.key,
        )
        for row in page
    ]
