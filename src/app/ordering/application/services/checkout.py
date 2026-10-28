"""Checkout's first transaction (VS-023 plan 3.3, VS-028 plan 3.4; SRS 7.3). It runs in the
caller's session after the idempotency claim, never commits and never calls the provider."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.catalog.application.ports import CartProductReader, ProductType
from app.core.phone import normalise_lebanese_phone
from app.ordering.application.ports import (
    CartStore,
    CashChecks,
    CheckoutAddresses,
    CustomerAccounts,
    OrderNotices,
    OrderStore,
    PaymentAttemptRef,
    PaymentAttempts,
    SettingsSource,
)
from app.ordering.application.services.cart import clear_cart, lock_cart_for_checkout
from app.ordering.domain.cash import cash_limits, cash_precheck
from app.ordering.domain.checkout_rules import (
    DIGITAL_TERMS_VERSION,
    CheckoutCommand,
    choose_provider,
    collect_refusals,
    price_changes,
    price_lines,
    require_cash_terms,
    require_consent,
    split_owned,
    totals,
)
from app.ordering.domain.enums import (
    FulfillmentMethod,
    OrderItemStatus,
    OrderSource,
    PaymentMethod,
)
from app.ordering.domain.exceptions import (
    CartEmptyError,
    CartPriceChangedError,
    CustomerAccountClosedError,
    InvalidFulfillmentError,
    OnlinePaymentUnavailableError,
    OrdersPausedError,
    PaymentMethodNotAllowedError,
)
from app.ordering.domain.fulfillment import (
    dispatch_days,
    estimated_dispatch_at,
    resolve_fulfillment,
)
from app.ordering.domain.order_number import new_order_number
from app.ordering.domain.order_status import LineState, OrderStatusInputs, derive_order_status
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
    payment: PaymentAttemptRef | None
    dropped: tuple[UUID, ...]


@dataclass(frozen=True)
class OnlinePlacedOrder(PlacedOrder):
    """A placed order that has a payment attempt to start."""

    payment: PaymentAttemptRef


async def place_order(
    *,
    carts: CartStore,
    products: CartProductReader,
    orders: OrderStore,
    attempts: PaymentAttempts,
    addresses: CheckoutAddresses,
    accounts: CustomerAccounts,
    cash: CashChecks,
    notices: OrderNotices,
    settings: SettingsSource,
    audit: AuditWriter,
    customer: CheckoutCustomer,
    command: CheckoutCommand,
    hash_phone: Callable[[str], str],
    now: datetime,
    number: Callable[[], str] | None = None,
) -> PlacedOrder:
    """Locks, in order: the cart row, the address row FOR SHARE (delivery), the cash phone
    advisory lock (cash). Then reads and INSERTs only: no existing `orders` row is locked."""
    online = command.payment_method is PaymentMethod.ONLINE
    if not await settings.get_bool("accepting_orders"):
        raise OrdersPausedError("Checkout is paused.")
    configured = attempts.configured_providers()
    if online and not configured:
        raise OnlinePaymentUnavailableError("No online payment provider is configured.")
    locked = await lock_cart_for_checkout(carts, user_id=customer.id)
    if not await accounts.is_live(customer.id):  # deletion holds the cart lock (ADR-047)
        raise CustomerAccountClosedError()
    if locked is None or not locked.lines:
        raise CartEmptyError()
    found = await products.get_many([line.product_id for line in locked.lines])
    collect_refusals(locked.lines, found)
    stl_ids = [line.product_id for line in locked.lines if line.product_type is ProductType.STL]
    kept, dropped = split_owned(
        locked.lines, await orders.owned_stl_product_ids(customer.id, stl_ids)
    )
    if not kept:
        raise CartEmptyError(dropped)
    fulfillment = resolve_fulfillment(
        [line.product_type for line in kept],
        payment_method=command.payment_method,
        method=command.fulfillment_method,
        address_id=command.address_id,
        contact_phone=command.contact_phone,
    )
    if fulfillment.method is FulfillmentMethod.PICKUP and not await settings.get_text(
        "pickup_address"
    ):
        raise InvalidFulfillmentError("Pickup is not available: no pickup address is set.")
    address = None
    phone = fulfillment.contact_phone
    if fulfillment.address_id is not None:
        address = await addresses.lock_for_share(fulfillment.address_id, customer.id)
        if address is None:
            raise InvalidFulfillmentError("The address is not available.")
        phone = normalise_lebanese_phone(address.phone)
    phone_hash = hash_phone(phone) if phone is not None else None
    if changes := price_changes(kept, found, command.accepted_price_changes):
        raise CartPriceChangedError(changes)
    has_stl = any(line.product_type is ProductType.STL for line in kept)
    require_consent(command, has_stl=has_stl)
    require_cash_terms(command)
    new_lines = price_lines(kept, found)
    money = totals(new_lines)
    provider = None
    if online:
        if money.total_cents == 0:
            raise PaymentMethodNotAllowedError("zero_total")
        provider = choose_provider(command.payment_provider, configured)
    else:
        if command.payment_provider is not None:
            raise PaymentMethodNotAllowedError("provider_not_applicable")
        cash_precheck(
            new_lines,
            money.total_cents,
            enabled=await settings.get_bool("cash_payment_enabled"),
            max_total=await settings.get_money_cents("cash_max_order_total"),
        )
        if phone_hash is None:  # unreachable: cash is physical, so a phone was resolved
            raise InvalidFulfillmentError("A cash order needs a contact phone.")
        await cash.lock_phone(phone_hash)
        cash_limits(
            blocked=await cash.active_block(customer.id, phone_hash),
            open_orders=await cash.open_order_count(customer.id, phone_hash, at=now),
            max_open=await settings.get_int("cash_max_open_orders"),
        )

    status = derive_order_status(
        OrderStatusInputs(
            command.payment_method,
            cancelled_at_set=False,
            payment_reached_paid=False,
            lines=tuple(LineState(OrderItemStatus.PENDING) for _ in new_lines),
        )
    )
    order = await orders.insert_order(
        NewOrder(
            order_number="",
            user_id=customer.id,
            customer_email_snapshot=customer.email,
            source=OrderSource.CART,
            status=status,
            payment_method=command.payment_method,
            subtotal_cents=money.subtotal_cents,
            tax_cents=money.tax_cents,
            total_cents=money.total_cents,
            currency=money.currency,
            customer_note=command.customer_note,
            terms_accepted_at=now,
            digital_terms_accepted_at=now if has_stl else None,
            digital_terms_version=DIGITAL_TERMS_VERSION if has_stl else None,
            placed_at=now,
            fulfillment_method=fulfillment.method,
            recipient_name=address.recipient_name if address else None,
            contact_phone_snapshot=phone,
            contact_phone_hash=phone_hash,
            governorate=address.governorate if address else None,
            city=address.city if address else None,
            area=address.area if address else None,
            street=address.street if address else None,
            landmark_notes=address.landmark_notes if address else None,
            estimated_dispatch_at=estimated_dispatch_at(now, dispatch_days(new_lines)),
            cash_terms_accepted_at=None if online else now,
        ),
        number or new_order_number,
    )
    lines = await orders.insert_lines(order, new_lines, status=OrderItemStatus.PENDING)
    payment = None
    if provider is not None:
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
            "payment_method": command.payment_method.value,
            "fulfillment_method": fulfillment.method.value if fulfillment.method else None,
            "payment_id": str(payment.id) if payment else None,
            "dropped_product_ids": [str(p) for p in dropped],
        },
    )
    if not online:
        await notices.cash_order_placed(order, lines)
    await clear_cart(carts, locked)
    return PlacedOrder(order=order, lines=tuple(lines), payment=payment, dropped=dropped)
