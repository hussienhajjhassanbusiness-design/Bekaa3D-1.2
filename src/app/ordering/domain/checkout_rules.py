"""Checkout's pure rules (VS-023 plan 3.1; SRS 7.2-7.3). Catalog state arrives as
`CartProduct`; prices always come from it, never from the cart snapshot (ADR-029 d3)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.catalog.application.ports import (
    CartProduct,
    ProductType,
    PurchaseRefusal,
    purchase_refusal,
)
from app.ordering.domain.cart_rules import cap_for
from app.ordering.domain.entities import CartLine
from app.ordering.domain.enums import PaymentMethod
from app.ordering.domain.exceptions import (
    CheckoutLinesRefusedError,
    ConsentRequiredError,
    InvalidFulfillmentError,
    LineRefusal,
    PaymentMethodNotAllowedError,
    PriceChange,
    ProductNotPurchasableError,
)
from app.ordering.domain.orders import NewOrderLine

OVER_CAP = "over_cap"
# Plan addition (Q18, ADR-032): a constant until a settings value exists.
DIGITAL_TERMS_VERSION = "2026-10-17"


@dataclass(frozen=True)
class AcceptedPrice:
    product_id: UUID
    amount_cents: int
    currency: str


@dataclass(frozen=True)
class CheckoutCommand:
    """The validated request. `fulfillment_requested` is true when any of fulfillment
    method, address or contact phone was sent (all VS-028)."""

    payment_method: PaymentMethod
    payment_provider: str | None
    fulfillment_requested: bool
    customer_note: str | None
    accept_digital_final_sale: bool
    accepted_price_changes: tuple[AcceptedPrice, ...]


@dataclass(frozen=True)
class Totals:
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency: str


def collect_refusals(lines: Sequence[CartLine], products: Mapping[UUID, CartProduct]) -> None:
    """Refuse the whole cart, naming every line that cannot be bought now (no silent drop)."""
    refusals: list[LineRefusal] = []
    for line in lines:
        product = products.get(line.product_id)
        if product is None:
            refusals.append(LineRefusal(line.product_id, PurchaseRefusal.NOT_LISTED.value))
            continue
        if (reason := purchase_refusal(product)) is not None:
            refusals.append(LineRefusal(line.product_id, reason.value))
            continue
        try:
            cap = cap_for(product)
        except ProductNotPurchasableError as exc:
            refusals.append(LineRefusal(line.product_id, exc.reason.value))
            continue
        if line.quantity > cap:
            refusals.append(LineRefusal(line.product_id, OVER_CAP, max_quantity=cap))
    if refusals:
        raise CheckoutLinesRefusedError(refusals)


def require_digital_only(lines: Sequence[CartLine], command: CheckoutCommand) -> None:
    """Physical lines and fulfillment details arrive with VS-028."""
    if command.fulfillment_requested or any(
        line.product_type is ProductType.PHYSICAL for line in lines
    ):
        raise InvalidFulfillmentError("Physical fulfillment is not available yet.")


def require_online(command: CheckoutCommand) -> None:
    """Cash needs every line physical (ADR-024 d2); an STL-only order is paid online."""
    if command.payment_method is PaymentMethod.CASH:
        raise PaymentMethodNotAllowedError("cash_requires_physical")


def split_owned(
    lines: Sequence[CartLine], owned: set[UUID]
) -> tuple[tuple[CartLine, ...], tuple[UUID, ...]]:
    """SRS 7.3 step 5: an STL bought since it was added is dropped, and named."""
    kept = tuple(line for line in lines if line.product_id not in owned)
    dropped = tuple(line.product_id for line in lines if line.product_id in owned)
    return kept, dropped


def price_changes(
    lines: Sequence[CartLine],
    products: Mapping[UUID, CartProduct],
    accepted: Sequence[AcceptedPrice],
) -> list[PriceChange]:
    """Changes not accepted at exactly the live amount; a second change fails again."""
    confirmed = {(a.product_id, a.amount_cents, a.currency) for a in accepted}
    changes: list[PriceChange] = []
    for line in lines:
        product = products[line.product_id]
        if product.price_cents == line.price_snapshot_cents:
            continue
        if (line.product_id, product.price_cents, product.currency) in confirmed:
            continue
        changes.append(
            PriceChange(
                line.product_id, line.price_snapshot_cents, product.price_cents, product.currency
            )
        )
    return changes


def price_lines(
    lines: Sequence[CartLine], products: Mapping[UUID, CartProduct]
) -> tuple[NewOrderLine, ...]:
    """Order lines at the live price, with name and cover snapshots."""
    priced: list[NewOrderLine] = []
    for line in lines:
        product = products[line.product_id]
        priced.append(
            NewOrderLine(
                product_id=product.id,
                product_type=product.type,
                product_name_snapshot=product.name,
                image_snapshot=product.cover.storage_key if product.cover else None,
                unit_price_cents=product.price_cents,
                quantity=line.quantity,
                line_total_cents=product.price_cents * line.quantity,
                currency=product.currency,
            )
        )
    return tuple(priced)


def totals(lines: Sequence[NewOrderLine]) -> Totals:
    """No tax and no shipping in V1 (BR-059, ADR-024 d1)."""
    subtotal = sum(line.line_total_cents for line in lines)
    return Totals(subtotal_cents=subtotal, tax_cents=0, total_cents=subtotal, currency="USD")


def require_consent(command: CheckoutCommand, *, has_stl: bool) -> None:
    """BR-060: STL purchases are final, and the customer must say so."""
    if has_stl and not command.accept_digital_final_sale:
        raise ConsentRequiredError("accept_digital_final_sale is required for STL lines.")


def choose_provider(
    requested: str | None, configured: frozenset[str], previous: str | None = None
) -> str:
    """Checkout and retry (VS-024 plan 3.6): the named provider, else the previous attempt's
    while still configured, else the only one; raises PaymentMethodNotAllowedError."""
    if requested is not None:
        if requested not in configured:
            raise PaymentMethodNotAllowedError("provider_not_configured")
        return requested
    if previous is not None and previous in configured:
        return previous
    if len(configured) != 1:
        raise PaymentMethodNotAllowedError("provider_required")
    return next(iter(configured))
