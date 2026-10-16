"""`purchase_refusal` (VS-022): the cart's product rule, pinned to ADR-022's flag."""

from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.catalog.domain.enums import ProductType, PurchaseMode
from app.catalog.domain.storefront import (
    CartProduct,
    PurchaseRefusal,
    capabilities,
    purchase_refusal,
)

PHYSICAL, STL = ProductType.PHYSICAL, ProductType.STL
NOT_LISTED = PurchaseRefusal.NOT_LISTED
UNAVAILABLE = PurchaseRefusal.UNAVAILABLE
WHATSAPP_ONLY = PurchaseRefusal.WHATSAPP_ONLY


def _product(
    product_type: ProductType,
    mode: PurchaseMode | None,
    *,
    available: bool = True,
    listed: bool = True,
) -> CartProduct:
    return CartProduct(
        id=uuid4(),
        type=product_type,
        name="Vase",
        slug="vase",
        price_cents=1000,
        currency="USD",
        purchase_mode=mode,
        is_available=available,
        max_quantity_per_line=5 if product_type is PHYSICAL else None,
        listed=listed,
    )


@pytest.mark.parametrize(
    ("product_type", "mode", "available", "listed", "expected"),
    [
        (PHYSICAL, PurchaseMode.ONLINE_ONLY, True, True, None),
        (PHYSICAL, PurchaseMode.BOTH, True, True, None),
        (PHYSICAL, PurchaseMode.WHATSAPP_ONLY, True, True, WHATSAPP_ONLY),
        (PHYSICAL, PurchaseMode.ONLINE_ONLY, False, True, UNAVAILABLE),
        (PHYSICAL, PurchaseMode.BOTH, False, True, UNAVAILABLE),
        # Unavailable is reported before WhatsApp-only.
        (PHYSICAL, PurchaseMode.WHATSAPP_ONLY, False, True, UNAVAILABLE),
        (STL, None, True, True, None),
        (STL, None, False, True, UNAVAILABLE),
        # Not listed wins over every other reason: it never says more than a 404.
        (PHYSICAL, PurchaseMode.ONLINE_ONLY, True, False, NOT_LISTED),
        (PHYSICAL, PurchaseMode.WHATSAPP_ONLY, True, False, NOT_LISTED),
        (PHYSICAL, PurchaseMode.ONLINE_ONLY, False, False, NOT_LISTED),
        (STL, None, True, False, NOT_LISTED),
        (STL, None, False, False, NOT_LISTED),
    ],
)
def test_refusal_follows_listing_availability_and_mode(
    product_type: ProductType,
    mode: PurchaseMode | None,
    available: bool,
    listed: bool,
    expected: PurchaseRefusal | None,
) -> None:
    product = _product(product_type, mode, available=available, listed=listed)
    assert purchase_refusal(product) is expected


_MODES = st.sampled_from([*PurchaseMode, None])


@settings(database=None)
@given(
    product_type=st.sampled_from(list(ProductType)),
    mode=_MODES,
    available=st.booleans(),
    listed=st.booleans(),
)
def test_the_cart_is_never_looser_or_stricter_than_the_storefront_flag(
    product_type: ProductType, mode: PurchaseMode | None, available: bool, listed: bool
) -> None:
    product = _product(product_type, mode, available=available, listed=listed)
    flag = capabilities(product_type, mode, available).can_add_to_cart
    assert (purchase_refusal(product) is None) == (listed and flag)
