"""Offer checkout's first transaction (VS-041; SRS 5.4, BR-085, BR-086; ADR-037). Like cart
checkout it runs after the idempotency claim, never commits and never calls the provider.
The order is inserted before the offer is locked, the lock order a payment's auto-close uses."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import (
    CartProduct,
    CartProductReader,
    PurchaseRefusal,
    purchase_refusal,
)
from app.ordering.application.ports import (
    AcceptedOffer,
    OfferCheckouts,
    OrderStore,
    PaymentAttempts,
    SettingsSource,
)
from app.ordering.application.services.checkout import CheckoutCustomer, PlacedOrder
from app.ordering.application.services.retry import already_active
from app.ordering.domain.checkout_rules import DIGITAL_TERMS_VERSION, choose_provider
from app.ordering.domain.enums import OrderItemStatus, OrderSource, PaymentMethod
from app.ordering.domain.exceptions import (
    CheckoutLinesRefusedError,
    LineRefusal,
    OnlinePaymentUnavailableError,
    OrdersPausedError,
)
from app.ordering.domain.order_number import new_order_number
from app.ordering.domain.order_status import OrderStatusInputs, derive_order_status
from app.ordering.domain.orders import NewOrder, NewOrderLine, StatusChange
from app.platform.application.ports import AuditWriter


@dataclass(frozen=True)
class OfferCheckoutCommand:
    offer_id: UUID
    payment_provider: str | None


async def place_offer_order(
    *,
    offers: OfferCheckouts,
    products: CartProductReader,
    orders: OrderStore,
    attempts: PaymentAttempts,
    settings: SettingsSource,
    audit: AuditWriter,
    customer: CheckoutCustomer,
    command: OfferCheckoutCommand,
    now: datetime,
    clock: Callable[[], datetime],
    number: Callable[[], str] | None = None,
) -> PlacedOrder:
    """Refusals in ADR-037's order; the price is the agreed amount, never the list price."""
    offer = await offers.read(command.offer_id, customer.id, now=now)
    if not await settings.get_bool("accepting_orders"):
        raise OrdersPausedError("Checkout is paused.")
    configured = attempts.configured_providers()
    if not configured:
        raise OnlinePaymentUnavailableError("No online payment provider is configured.")
    product = _purchasable(
        offer, (await products.get_many([offer.product_id])).get(offer.product_id)
    )
    unpaid = await orders.unpaid_offer_order(offer.id)
    live = await attempts.live_attempt(unpaid) if unpaid is not None else None
    if live is not None:
        raise already_active(live)
    # An unpaid order with no live attempt is refused by the ownership index below.
    status = derive_order_status(
        OrderStatusInputs(
            PaymentMethod.ONLINE, cancelled_at_set=False, payment_reached_paid=False, lines=()
        )
    )
    order = await orders.insert_order(
        NewOrder(
            order_number="",
            user_id=customer.id,
            customer_email_snapshot=customer.email,
            source=OrderSource.OFFER,
            status=status,
            payment_method=PaymentMethod.ONLINE,
            subtotal_cents=offer.agreed_amount_cents,
            tax_cents=0,
            total_cents=offer.agreed_amount_cents,
            currency=offer.currency,
            customer_note=None,
            terms_accepted_at=now,
            digital_terms_accepted_at=now,
            digital_terms_version=DIGITAL_TERMS_VERSION,
            placed_at=now,
        ),
        number or new_order_number,
    )
    lines = await orders.insert_lines(
        order, [_line(offer, product)], status=OrderItemStatus.PENDING
    )
    provider = choose_provider(command.payment_provider, configured)
    payment = await attempts.open_attempt(
        order_id=order.id,
        amount_cents=offer.agreed_amount_cents,
        currency=offer.currency,
        provider=provider,
        at=now,
    )
    # The decision: a closing window or a racing job refuses here and rolls it all back.
    await offers.lock(offer.id, customer.id, clock=clock)
    await orders.add_history(
        [StatusChange(order.id, None, status.value, actor_user_id=customer.id)]
    )
    await audit.record(
        actor_user_id=customer.id,
        action="order.placed",
        entity_type="order",
        entity_id=order.id,
        after_data={
            "order_number": order.order_number,
            "total_cents": offer.agreed_amount_cents,
            "payment_id": str(payment.id),
            "source": OrderSource.OFFER.value,
            "offer_id": str(offer.id),
        },
    )
    return PlacedOrder(order=order, lines=tuple(lines), payment=payment, dropped=())


def _purchasable(offer: AcceptedOffer, product: CartProduct | None) -> CartProduct:
    """Hidden or unavailable refuses, as accept does; the list price is never read."""
    reason = PurchaseRefusal.NOT_LISTED if product is None else purchase_refusal(product)
    if reason is not None or product is None:
        reason = reason or PurchaseRefusal.NOT_LISTED
        raise CheckoutLinesRefusedError([LineRefusal(offer.product_id, reason.value)])
    return product


def _line(offer: AcceptedOffer, product: CartProduct) -> NewOrderLine:
    return NewOrderLine(
        product_id=product.id,
        product_type=product.type,
        product_name_snapshot=product.name,
        image_snapshot=product.cover.storage_key if product.cover else None,
        unit_price_cents=offer.agreed_amount_cents,
        quantity=1,
        line_total_cents=offer.agreed_amount_cents,
        currency=offer.currency,
        offer_id=offer.id,
    )
