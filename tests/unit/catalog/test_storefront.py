"""Storefront filter validation and derived commerce capabilities (VS-015)."""

from decimal import Decimal

import pytest

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.domain.exceptions import ProductValidationError
from app.catalog.domain.storefront import StorefrontFilter, capabilities

PHYSICAL, STL = ProductType.PHYSICAL, ProductType.STL


def test_an_inverted_price_range_is_refused() -> None:
    with pytest.raises(ProductValidationError) as caught:
        StorefrontFilter(price_min_cents=501, price_max_cents=500)
    assert set(caught.value.errors) == {"price_min_cents"}


def test_an_equal_price_range_is_allowed() -> None:
    StorefrontFilter(price_min_cents=500, price_max_cents=500)


@pytest.mark.parametrize("rating", ["-0.01", "5.01"])
def test_min_rating_outside_zero_to_five_is_refused(rating: str) -> None:
    with pytest.raises(ProductValidationError) as caught:
        StorefrontFilter(min_rating=Decimal(rating))
    assert set(caught.value.errors) == {"min_rating"}


@pytest.mark.parametrize("rating", ["0", "5", "3.5"])
def test_min_rating_bounds_are_inclusive(rating: str) -> None:
    StorefrontFilter(min_rating=Decimal(rating))


@pytest.mark.parametrize(
    ("product_type", "mode", "available", "cart", "offer", "whatsapp"),
    [
        (PHYSICAL, PurchaseMode.ONLINE_ONLY, True, True, False, False),
        (PHYSICAL, PurchaseMode.BOTH, True, True, False, True),
        (PHYSICAL, PurchaseMode.WHATSAPP_ONLY, True, False, False, True),
        # Unavailable stops on-platform buying only; WhatsApp is off-platform.
        (PHYSICAL, PurchaseMode.ONLINE_ONLY, False, False, False, False),
        (PHYSICAL, PurchaseMode.BOTH, False, False, False, True),
        (PHYSICAL, PurchaseMode.WHATSAPP_ONLY, False, False, False, True),
        (STL, None, True, True, True, False),
        (STL, None, False, False, False, False),
    ],
)
def test_capabilities_follow_type_mode_and_availability(
    product_type: ProductType,
    mode: PurchaseMode | None,
    available: bool,
    cart: bool,
    offer: bool,
    whatsapp: bool,
) -> None:
    derived = capabilities(product_type, mode, available)
    assert (derived.can_add_to_cart, derived.can_offer, derived.whatsapp_available) == (
        cart,
        offer,
        whatsapp,
    )
