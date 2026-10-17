"""Checkout's first transaction (VS-023 plan 3.3; SRS 7.3). It runs in the caller's
session after the idempotency claim, never commits and never calls the provider."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import CartProductReader, ProductType
from app.ordering.application.ports import (
    CartStore,
    OrderStore,
    PaymentAttemptRef,
    PaymentAttempts,
    SettingsSource,
)
from app.ordering.application.services.cart import clear_cart, lock_cart_for_checkout
from app.ordering.domain.checkout_rules import (
    DIGITAL_TERMS_VERSION,
    CheckoutCommand,
    collect_refusals,
    price_changes,
    price_lines,
    require_consent,
    require_digital_only,
    require_online,
    split_owned,
    totals,
)
from app.ordering.domain.enums import OrderItemStatus, OrderSource, PaymentMethod
from app.ordering.domain.exceptions import (
    CartEmptyError,
    CartPriceChangedError,
    OnlinePaymentUnavailableError,
    OrdersPausedError,
    PaymentMethodNotAllowedError,
)
from app.ordering.domain.order_number import new_order_number
from app.ordering.domain.order_status import OrderStatusInputs, derive_order_status
from app.ordering.domain.orders import NewOrder, Order, OrderLine, StatusChange
from app.platform.application.ports import AuditWriter


@dataclass(frozen=True)
class CheckoutCustomer:
    id: UUID
    email: str


@dataclass(frozen=True)
class PlacedOrder:
    order: Order
    lines: tuple[OrderLine, ...]
    payment: PaymentAttemptRef
    dropped: tuple[UUID, ...]


def _provider(command: CheckoutCommand, configured: frozenset[str]) -> str:
    if command.payment_provider is not None:
        if command.payment_provider not in configured:
            raise PaymentMethodNotAllowedError("provider_not_configured")
        return command.payment_provider
    if len(configured) != 1:
        raise PaymentMethodNotAllowedError("provider_required")
    return next(iter(configured))


async def place_order(
    *,
    carts: CartStore,
    products: CartProductReader,
    orders: OrderStore,
    attempts: PaymentAttempts,
    settings: SettingsSource,
    audit: AuditWriter,
    customer: CheckoutCustomer,
    command: CheckoutCommand,
    now: datetime,
    number: Callable[[], str] = new_order_number,
) -> PlacedOrder:
    """Locks: the cart row only. Every order, line and payment row is a new INSERT, so
    no existing `orders` row is locked while the cart lock is held (ADR-029 d4)."""
    if not await settings.get_bool("accepting_orders"):
        raise OrdersPausedError("Checkout is paused.")
    configured = attempts.configured_providers()
    if not configured:
        raise OnlinePaymentUnavailableError("No online payment provider is configured.")
    locked = await lock_cart_for_checkout(carts, user_id=customer.id)
    if locked is None or not locked.lines:
        raise CartEmptyError()
    found = await products.get_many([line.product_id for line in locked.lines])
    collect_refusals(locked.lines, found)
    require_digital_only(locked.lines, command)
    require_online(command)
    stl_ids = [line.product_id for line in locked.lines if line.product_type is ProductType.STL]
    kept, dropped = split_owned(
        locked.lines, await orders.owned_stl_product_ids(customer.id, stl_ids)
    )
    if not kept:
        raise CartEmptyError(dropped)
    if changes := price_changes(kept, found, command.accepted_price_changes):
        raise CartPriceChangedError(changes)
    has_stl = any(line.product_type is ProductType.STL for line in kept)
    require_consent(command, has_stl=has_stl)
    new_lines = price_lines(kept, found)
    money = totals(new_lines)
    if money.total_cents == 0:
        raise PaymentMethodNotAllowedError("zero_total")
    provider = _provider(command, configured)

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
            source=OrderSource.CART,
            status=status,
            payment_method=PaymentMethod.ONLINE,
            subtotal_cents=money.subtotal_cents,
            tax_cents=money.tax_cents,
            total_cents=money.total_cents,
            currency=money.currency,
            customer_note=command.customer_note,
            terms_accepted_at=now,
            digital_terms_accepted_at=now if has_stl else None,
            digital_terms_version=DIGITAL_TERMS_VERSION if has_stl else None,
            placed_at=now,
        ),
        number,
    )
    lines = await orders.insert_lines(order, new_lines, status=OrderItemStatus.PENDING)
    payment = await attempts.open_attempt(
        order_id=order.id,
        amount_cents=money.total_cents,
        currency=money.currency,
        provider=provider,
        at=now,
    )
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
            "total_cents": money.total_cents,
            "payment_id": str(payment.id),
            "dropped_product_ids": [str(p) for p in dropped],
        },
    )
    await clear_cart(carts, locked)
    return PlacedOrder(order=order, lines=tuple(lines), payment=payment, dropped=dropped)
