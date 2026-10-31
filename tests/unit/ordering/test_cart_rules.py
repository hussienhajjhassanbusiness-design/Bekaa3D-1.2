"""Cart quantity, line-cap and read-model rules (VS-022 plan §3.2, §6 unit)."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from app.catalog.application.ports import CartProduct, ProductType, PurchaseRefusal
from app.catalog.domain.enums import AcceptedPaymentMethods, PurchaseMode
from app.catalog.domain.product_image import ProductImage
from app.ordering.domain.cart_rules import (
    cap_for,
    check_line_capacity,
    check_set_quantity,
    quantity_after_add,
    view_line,
)
from app.ordering.domain.entities import MAX_CART_LINES, CartLine
from app.ordering.domain.enums import PaymentMethod
from app.ordering.domain.exceptions import (
    CartLineLimitReachedError,
    ProductNotPurchasableError,
    QuantityExceedsLimitError,
)

NOW = datetime(2026, 10, 16, tzinfo=UTC)


def physical(**over: Any) -> CartProduct:
    values: dict[str, Any] = {
        "id": uuid4(),
        "type": ProductType.PHYSICAL,
        "name": "Lamp",
        "slug": "lamp",
        "price_cents": 1000,
        "currency": "USD",
        "purchase_mode": PurchaseMode.ONLINE_ONLY,
        "accepted_payment_methods": AcceptedPaymentMethods.ONLINE_OR_CASH,
        "is_available": True,
        "max_quantity_per_line": 5,
        "listed": True,
    }
    return CartProduct(**(values | over))


def stl(**over: Any) -> CartProduct:
    base = {
        "type": ProductType.STL,
        "purchase_mode": None,
        "accepted_payment_methods": None,
        "max_quantity_per_line": None,
    }
    return physical(**(base | over))


def line(product: CartProduct, quantity: int, snapshot: int = 1000) -> CartLine:
    return CartLine(
        id=uuid4(),
        cart_id=uuid4(),
        product_id=product.id,
        product_type=product.type,
        quantity=quantity,
        price_snapshot_cents=snapshot,
        currency="USD",
        created_at=NOW,
        updated_at=NOW,
    )


REFUSED = [
    (physical(listed=False), PurchaseRefusal.NOT_LISTED),
    (physical(is_available=False), PurchaseRefusal.UNAVAILABLE),
    (physical(purchase_mode=PurchaseMode.WHATSAPP_ONLY), PurchaseRefusal.WHATSAPP_ONLY),
    (stl(listed=False), PurchaseRefusal.NOT_LISTED),
    (stl(is_available=False), PurchaseRefusal.UNAVAILABLE),
]

# ------------------------------------------------------------------ cap_for


def test_cap_is_one_for_stl_and_the_product_cap_for_physical() -> None:
    assert cap_for(stl()) == 1
    assert cap_for(physical(max_quantity_per_line=7)) == 7


def test_a_physical_product_without_a_cap_fails_closed() -> None:
    with pytest.raises(ProductNotPurchasableError) as caught:
        cap_for(physical(max_quantity_per_line=None))
    assert caught.value.reason is PurchaseRefusal.NOT_LISTED


# --------------------------------------------------------- quantity_after_add


def test_stl_quantity_is_exactly_one() -> None:
    assert quantity_after_add(stl(), 1, None) == 1
    with pytest.raises(QuantityExceedsLimitError) as caught:
        quantity_after_add(stl(), 2, None)
    assert (caught.value.max_quantity, caught.value.requested) == (1, 2)


def test_re_adding_an_stl_already_in_the_cart_is_an_idempotent_one() -> None:
    product = stl()
    assert quantity_after_add(product, 1, line(product, 1)) == 1


@pytest.mark.parametrize(("requested", "allowed"), [(1, True), (5, True), (6, False)])
def test_a_first_physical_add_is_bounded_by_the_cap(requested: int, allowed: bool) -> None:
    product = physical(max_quantity_per_line=5)
    if allowed:
        assert quantity_after_add(product, requested, None) == requested
    else:
        with pytest.raises(QuantityExceedsLimitError):
            quantity_after_add(product, requested, None)


def test_a_physical_add_merges_up_to_the_cap() -> None:
    product = physical(max_quantity_per_line=5)
    assert quantity_after_add(product, 3, line(product, 2)) == 5


def test_a_merge_over_the_cap_is_refused_never_clamped() -> None:
    product = physical(max_quantity_per_line=4)
    with pytest.raises(QuantityExceedsLimitError) as caught:
        quantity_after_add(product, 3, line(product, 2))
    error = caught.value
    assert (error.max_quantity, error.requested, error.current_quantity) == (4, 3, 2)


@pytest.mark.parametrize(("product", "reason"), REFUSED)
def test_a_refused_product_is_refused_before_any_quantity_check(
    product: CartProduct, reason: PurchaseRefusal
) -> None:
    with pytest.raises(ProductNotPurchasableError) as caught:
        quantity_after_add(product, 99, None)
    assert caught.value.reason is reason


# ---------------------------------------------------------- check_set_quantity


def test_set_quantity_is_bounded_by_the_current_cap() -> None:
    product = physical(max_quantity_per_line=5)
    check_set_quantity(product, 5, current=2)
    with pytest.raises(QuantityExceedsLimitError):
        check_set_quantity(product, 6, current=2)


def test_set_quantity_on_an_stl_line_accepts_only_one() -> None:
    check_set_quantity(stl(), 1, current=1)
    with pytest.raises(QuantityExceedsLimitError):
        check_set_quantity(stl(), 2, current=1)


@pytest.mark.parametrize(("product", "reason"), REFUSED)
def test_set_quantity_on_a_refused_product_is_refused(
    product: CartProduct, reason: PurchaseRefusal
) -> None:
    with pytest.raises(ProductNotPurchasableError) as caught:
        check_set_quantity(product, 1, current=1)
    assert caught.value.reason is reason


# --------------------------------------------------------- check_line_capacity


def test_the_fiftieth_line_is_allowed_and_the_fifty_first_is_not() -> None:
    check_line_capacity(MAX_CART_LINES - 1)
    with pytest.raises(CartLineLimitReachedError) as caught:
        check_line_capacity(MAX_CART_LINES)
    assert caught.value.limit == 50


# ------------------------------------------------------------------ view_line


@pytest.mark.parametrize(("current", "changed"), [(1200, True), (800, True), (1000, False)])
def test_price_changed_in_either_direction(current: int, changed: bool) -> None:
    product = physical(price_cents=current)
    view = view_line(line(product, 1, snapshot=1000), product)
    assert view.price_changed is changed
    assert view.current_price_cents == current


def test_a_purchasable_line_shows_everything() -> None:
    cover = ProductImage(uuid4(), uuid4(), "products/x.webp", None, 0, True, NOW, NOW)
    product = physical(cover=cover)
    view = view_line(line(product, 2), product)
    assert view.purchasable
    assert (view.name, view.slug, view.cover, view.max_quantity) == ("Lamp", "lamp", cover, 5)
    assert view.over_cap is False


@pytest.mark.parametrize(
    ("accepted", "methods"),
    [
        (AcceptedPaymentMethods.ONLINE, {PaymentMethod.ONLINE}),
        (AcceptedPaymentMethods.CASH, {PaymentMethod.CASH}),
        (AcceptedPaymentMethods.ONLINE_OR_CASH, {PaymentMethod.ONLINE, PaymentMethod.CASH}),
    ],
)
def test_a_line_carries_what_its_product_accepts(
    accepted: AcceptedPaymentMethods, methods: set[PaymentMethod]
) -> None:
    product = physical(accepted_payment_methods=accepted)
    assert view_line(line(product, 1), product).payment_methods == methods


def test_an_stl_line_accepts_online_only() -> None:
    product = stl()
    assert view_line(line(product, 1), product).payment_methods == {PaymentMethod.ONLINE}


def test_a_line_whose_product_is_not_listed_keeps_only_its_name() -> None:
    cover = ProductImage(uuid4(), uuid4(), "products/x.webp", None, 0, True, NOW, NOW)
    product = physical(listed=False, price_cents=1500, cover=cover)
    view = view_line(line(product, 2), product)
    assert view.refusal is PurchaseRefusal.NOT_LISTED
    assert view.name == "Lamp"
    assert (view.slug, view.cover, view.current_price_cents, view.max_quantity) == (
        None,
        None,
        None,
        None,
    )
    assert view.price_changed is False


@pytest.mark.parametrize("product", [p for p, _ in REFUSED if p.listed])
def test_listed_but_unbuyable_lines_keep_their_price_and_are_flagged(
    product: CartProduct,
) -> None:
    view = view_line(line(product, 1), product)
    assert not view.purchasable
    assert view.slug is not None
    assert view.current_price_cents == product.price_cents


def test_over_cap_when_the_cap_is_lowered_below_the_quantity() -> None:
    product = physical(max_quantity_per_line=3)
    assert view_line(line(product, 4), product).over_cap is True
    assert view_line(line(product, 3), product).over_cap is False


def test_over_cap_is_independent_of_listing_and_hides_the_cap() -> None:
    product = physical(max_quantity_per_line=3, listed=False)
    view = view_line(line(product, 4), product)
    assert view.over_cap is True
    assert view.max_quantity is None


def test_an_stl_line_is_never_over_cap_and_shows_no_cap() -> None:
    product = stl()
    view = view_line(line(product, 1), product)
    assert view.over_cap is False
    assert view.max_quantity is None


def test_a_missing_product_reads_as_not_listed() -> None:
    product = physical()
    view = view_line(line(product, 1), None)
    assert view.refusal is PurchaseRefusal.NOT_LISTED
    assert (view.name, view.current_price_cents, view.over_cap) == (None, None, False)


def test_a_physical_product_without_a_cap_reads_as_not_purchasable() -> None:
    product = replace(physical(), max_quantity_per_line=None)
    view = view_line(line(product, 1), product)
    assert view.refusal is PurchaseRefusal.NOT_LISTED
    assert view.over_cap is False
