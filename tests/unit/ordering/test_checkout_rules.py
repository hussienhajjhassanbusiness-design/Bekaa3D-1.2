"""Checkout's pure rules and order numbers (VS-023 plan 3.1, 6.1)."""

import re
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.catalog.application.ports import CartProduct
from app.catalog.domain.enums import PurchaseMode
from app.catalog.domain.product_image import ProductImage
from app.ordering.domain.checkout_rules import (
    AcceptedPrice,
    CheckoutCommand,
    collect_refusals,
    price_changes,
    price_lines,
    require_consent,
    split_owned,
    totals,
)
from app.ordering.domain.enums import PaymentMethod
from app.ordering.domain.exceptions import (
    CheckoutLinesRefusedError,
    ConsentRequiredError,
)
from app.ordering.domain.order_number import CROCKFORD, new_order_number
from tests.unit.ordering.test_cart_rules import NOW, line, physical, stl

BASE = CheckoutCommand(
    payment_method=PaymentMethod.ONLINE,
    payment_provider=None,
    customer_note=None,
    accept_digital_final_sale=True,
    accepted_price_changes=(),
)


def command(**over: Any) -> CheckoutCommand:
    return replace(BASE, **over)


def by_id(*products: CartProduct) -> dict[UUID, CartProduct]:
    return {p.id: p for p in products}


def test_every_unbuyable_line_is_named() -> None:
    gone, paused, whatsapp = (
        stl(listed=False),
        stl(is_available=False),
        physical(purchase_mode=PurchaseMode.WHATSAPP_ONLY),
    )
    capped, ok = physical(max_quantity_per_line=2), stl()
    lines = [line(gone, 1), line(paused, 1), line(whatsapp, 1), line(capped, 3), line(ok, 1)]
    with pytest.raises(CheckoutLinesRefusedError) as caught:
        collect_refusals(lines, by_id(gone, paused, whatsapp, capped, ok))
    got = {(r.product_id, r.reason, r.max_quantity) for r in caught.value.refusals}
    assert got == {
        (gone.id, "not_listed", None),
        (paused.id, "unavailable", None),
        (whatsapp.id, "whatsapp_only", None),
        (capped.id, "over_cap", 2),
    }
    assert not caught.value.only_caps


def test_a_product_missing_from_catalog_is_not_listed() -> None:
    missing = stl()
    with pytest.raises(CheckoutLinesRefusedError) as caught:
        collect_refusals([line(missing, 1)], {})
    assert [r.reason for r in caught.value.refusals] == ["not_listed"]


def test_only_cap_failures_are_flagged_as_such() -> None:
    capped = physical(max_quantity_per_line=1)
    with pytest.raises(CheckoutLinesRefusedError) as caught:
        collect_refusals([line(capped, 2)], by_id(capped))
    assert caught.value.only_caps


def test_buyable_lines_pass() -> None:
    a, b = stl(), physical()
    collect_refusals([line(a, 1), line(b, 5)], by_id(a, b))


def test_owned_stls_are_dropped_and_named() -> None:
    a, b = stl(), stl()
    kept, dropped = split_owned([line(a, 1), line(b, 1)], {b.id})
    assert [k.product_id for k in kept] == [a.id]
    assert dropped == (b.id,)
    kept, dropped = split_owned([line(a, 1)], {a.id})
    assert kept == () and dropped == (a.id,)


def test_price_change_detection() -> None:
    up, same = stl(price_cents=1200), stl(price_cents=1000)
    lines = [line(up, 1, snapshot=1000), line(same, 1, snapshot=1000)]
    changes = price_changes(lines, by_id(up, same), [])
    assert [(c.product_id, c.old_amount_cents, c.new_amount_cents) for c in changes] == [
        (up.id, 1000, 1200)
    ]


def test_a_price_drop_is_a_change_too() -> None:
    down = stl(price_cents=800)
    assert len(price_changes([line(down, 1, snapshot=1000)], by_id(down), [])) == 1


def test_an_exact_acceptance_clears_the_change() -> None:
    up = stl(price_cents=1200)
    accepted = [AcceptedPrice(up.id, 1200, "USD")]
    assert price_changes([line(up, 1, snapshot=1000)], by_id(up), accepted) == []


@pytest.mark.parametrize(("amount", "currency"), [(1100, "USD"), (1200, "EUR")])
def test_a_stale_or_foreign_acceptance_fails_again(amount: int, currency: str) -> None:
    up = stl(price_cents=1200)
    accepted = [AcceptedPrice(up.id, amount, currency)]
    assert len(price_changes([line(up, 1, snapshot=1000)], by_id(up), accepted)) == 1


def test_lines_are_priced_live_never_from_the_snapshot() -> None:
    cover = ProductImage(
        id=uuid4(),
        product_id=uuid4(),
        storage_key="products/a.webp",
        alt_text=None,
        sort_order=0,
        is_cover=True,
        created_at=NOW,
        updated_at=NOW,
    )
    product = stl(price_cents=1500, cover=cover)
    priced = price_lines([line(product, 1, snapshot=999)], by_id(product))
    assert len(priced) == 1
    (only,) = priced
    assert (only.unit_price_cents, only.line_total_cents) == (1500, 1500)
    assert only.image_snapshot == "products/a.webp"
    assert only.product_name_snapshot == product.name


def test_totals_have_no_tax_and_no_shipping() -> None:
    a, b = stl(price_cents=700), stl(price_cents=300)
    result = totals(price_lines([line(a, 1), line(b, 1)], by_id(a, b)))
    assert (result.subtotal_cents, result.tax_cents, result.total_cents) == (1000, 0, 1000)


def test_stl_lines_need_the_final_sale_consent() -> None:
    with pytest.raises(ConsentRequiredError):
        require_consent(command(accept_digital_final_sale=False), has_stl=True)
    require_consent(command(accept_digital_final_sale=False), has_stl=False)
    require_consent(command(), has_stl=True)


def test_order_numbers_are_readable_and_random() -> None:
    number = new_order_number()
    assert re.fullmatch(f"B3D-[{CROCKFORD}]{{8}}", number)
    assert new_order_number(lambda n: b"\x00" * n) == "B3D-00000000"
    assert new_order_number(lambda n: b"\xff" * n) == "B3D-ZZZZZZZZ"
    assert len({new_order_number() for _ in range(200)}) == 200
