"""Cart services against fakes (VS-022 plan §3.4, §3.6, §6 unit): the lock comes first,
snapshots are set once, and reads never lock or create."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal, overload
from uuid import UUID, uuid4

import pytest

from app.catalog.application.ports import CartProduct, ProductType, PurchaseRefusal
from app.catalog.domain.enums import AcceptedPaymentMethods, PurchaseMode
from app.ordering.application.services.cart import (
    add_item,
    clear_cart,
    lock_cart_for_checkout,
    read_cart,
    remove_item,
    set_item_quantity,
)
from app.ordering.domain.entities import MAX_CART_LINES, Cart, CartLine
from app.ordering.domain.exceptions import (
    CartLineLimitReachedError,
    CartLineNotFoundError,
    ProductNotPurchasableError,
    QuantityExceedsLimitError,
)

NOW = datetime(2026, 10, 16, tzinfo=UTC)
USER = uuid4()


class FakeCarts:
    """In-memory `CartStore` that records every call, in order."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.carts: dict[UUID, Cart] = {}
        self.rows: dict[UUID, list[CartLine]] = {}

    @overload
    async def lock(self, user_id: UUID, *, create: Literal[True]) -> Cart: ...

    @overload
    async def lock(self, user_id: UUID, *, create: Literal[False]) -> Cart | None: ...

    async def lock(self, user_id: UUID, *, create: bool) -> Cart | None:
        self.calls.append(f"lock(create={create})")
        if user_id not in self.carts and create:
            cart = Cart(uuid4(), user_id, NOW, NOW)
            self.carts[user_id], self.rows[cart.id] = cart, []
        return self.carts.get(user_id)

    async def get(self, user_id: UUID) -> Cart | None:
        self.calls.append("get")
        return self.carts.get(user_id)

    async def lines(self, cart_id: UUID) -> list[CartLine]:
        self.calls.append("lines")
        return list(self.rows[cart_id])

    async def line(self, cart_id: UUID, product_id: UUID) -> CartLine | None:
        self.calls.append("line")
        return next((r for r in self.rows[cart_id] if r.product_id == product_id), None)

    async def count_lines(self, cart_id: UUID) -> int:
        self.calls.append("count_lines")
        return len(self.rows[cart_id])

    async def insert_line(
        self,
        *,
        cart_id: UUID,
        product_id: UUID,
        product_type: ProductType,
        quantity: int,
        price_snapshot_cents: int,
        currency: str,
    ) -> CartLine:
        self.calls.append("insert_line")
        row = CartLine(
            uuid4(),
            cart_id,
            product_id,
            product_type,
            quantity,
            price_snapshot_cents,
            currency,
            NOW,
            NOW,
        )
        self.rows[cart_id].append(row)
        return row

    async def set_quantity(self, line_id: UUID, quantity: int) -> CartLine:
        self.calls.append("set_quantity")
        for rows in self.rows.values():
            for i, row in enumerate(rows):
                if row.id == line_id:
                    rows[i] = replace(row, quantity=quantity)
                    return rows[i]
        raise AssertionError("unknown line")

    async def delete_line(self, cart_id: UUID, product_id: UUID) -> bool:
        self.calls.append("delete_line")
        before = len(self.rows[cart_id])
        self.rows[cart_id] = [r for r in self.rows[cart_id] if r.product_id != product_id]
        return len(self.rows[cart_id]) < before

    async def clear(self, cart_id: UUID) -> int:
        self.calls.append("clear")
        count = len(self.rows[cart_id])
        self.rows[cart_id] = []
        return count

    async def touch(self, cart_id: UUID) -> None:
        self.calls.append("touch")

    def only_line(self) -> CartLine:
        [row] = self.rows[self.carts[USER].id]
        return row


class FakeProducts:
    def __init__(self, *products: CartProduct) -> None:
        self.by_id = {p.id: p for p in products}
        self.batches: list[list[UUID]] = []

    async def get_many(self, product_ids: Sequence[UUID]) -> dict[UUID, CartProduct]:
        self.batches.append(list(product_ids))
        return {i: self.by_id[i] for i in product_ids if i in self.by_id}


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


# ------------------------------------------------------------------ add_item


async def test_add_takes_the_cart_lock_before_any_read() -> None:
    carts, product = FakeCarts(), physical()
    await add_item(carts, FakeProducts(product), user_id=USER, product_id=product.id, quantity=1)
    assert carts.calls == ["lock(create=True)", "line", "count_lines", "insert_line", "touch"]


async def test_the_first_add_snapshots_the_current_price_and_type() -> None:
    carts, product = FakeCarts(), physical(price_cents=2500)
    await add_item(carts, FakeProducts(product), user_id=USER, product_id=product.id, quantity=2)
    row = carts.only_line()
    assert (row.price_snapshot_cents, row.product_type, row.quantity) == (
        2500,
        ProductType.PHYSICAL,
        2,
    )


async def test_a_merge_keeps_the_snapshot_and_does_not_count_lines() -> None:
    carts, product = FakeCarts(), physical(price_cents=1000)
    await add_item(carts, FakeProducts(product), user_id=USER, product_id=product.id, quantity=1)
    raised = replace(product, price_cents=1500)
    carts.calls.clear()
    await add_item(carts, FakeProducts(raised), user_id=USER, product_id=product.id, quantity=2)
    row = carts.only_line()
    assert (row.quantity, row.price_snapshot_cents) == (3, 1000)
    assert "count_lines" not in carts.calls
    assert carts.calls[0] == "lock(create=True)"


async def test_an_stl_re_add_writes_nothing() -> None:
    carts, product = FakeCarts(), stl()
    products = FakeProducts(product)
    await add_item(carts, products, user_id=USER, product_id=product.id, quantity=1)
    carts.calls.clear()
    await add_item(carts, products, user_id=USER, product_id=product.id, quantity=1)
    assert carts.calls == ["lock(create=True)", "line"]
    assert carts.only_line().quantity == 1


async def test_an_unknown_product_is_refused_as_not_listed() -> None:
    carts = FakeCarts()
    with pytest.raises(ProductNotPurchasableError) as caught:
        await add_item(carts, FakeProducts(), user_id=USER, product_id=uuid4(), quantity=1)
    assert caught.value.reason is PurchaseRefusal.NOT_LISTED
    assert "insert_line" not in carts.calls


async def test_an_over_cap_merge_changes_nothing() -> None:
    carts, product = FakeCarts(), physical(max_quantity_per_line=5)
    products = FakeProducts(product)
    await add_item(carts, products, user_id=USER, product_id=product.id, quantity=3)
    with pytest.raises(QuantityExceedsLimitError):
        await add_item(carts, products, user_id=USER, product_id=product.id, quantity=3)
    assert carts.only_line().quantity == 3


async def test_a_new_line_past_the_cap_is_refused_but_a_merge_is_not() -> None:
    carts = FakeCarts()
    products = [physical() for _ in range(MAX_CART_LINES + 1)]
    reader = FakeProducts(*products)
    for p in products[:MAX_CART_LINES]:
        await add_item(carts, reader, user_id=USER, product_id=p.id, quantity=1)
    with pytest.raises(CartLineLimitReachedError):
        await add_item(carts, reader, user_id=USER, product_id=products[-1].id, quantity=1)
    await add_item(carts, reader, user_id=USER, product_id=products[0].id, quantity=1)


# --------------------------------------------------------- set_item_quantity


async def test_set_quantity_locks_first_and_keeps_the_snapshot() -> None:
    carts, product = FakeCarts(), physical(price_cents=1000)
    await add_item(carts, FakeProducts(product), user_id=USER, product_id=product.id, quantity=1)
    carts.calls.clear()
    raised = FakeProducts(replace(product, price_cents=1800))
    await set_item_quantity(carts, raised, user_id=USER, product_id=product.id, quantity=4)
    assert carts.calls == ["lock(create=False)", "line", "set_quantity", "touch"]
    assert (carts.only_line().quantity, carts.only_line().price_snapshot_cents) == (4, 1000)


@pytest.mark.parametrize("has_cart", [True, False])
async def test_set_quantity_on_a_missing_line_is_not_found_and_creates_nothing(
    has_cart: bool,
) -> None:
    carts, product = FakeCarts(), physical()
    if has_cart:
        await carts.lock(USER, create=True)
    with pytest.raises(CartLineNotFoundError):
        await set_item_quantity(
            carts, FakeProducts(product), user_id=USER, product_id=product.id, quantity=1
        )
    assert (USER in carts.carts) is has_cart


async def test_set_quantity_on_a_line_no_longer_purchasable_is_refused() -> None:
    carts, product = FakeCarts(), physical()
    await add_item(carts, FakeProducts(product), user_id=USER, product_id=product.id, quantity=1)
    whatsapp = FakeProducts(replace(product, purchase_mode=PurchaseMode.WHATSAPP_ONLY))
    with pytest.raises(ProductNotPurchasableError) as caught:
        await set_item_quantity(carts, whatsapp, user_id=USER, product_id=product.id, quantity=1)
    assert caught.value.reason is PurchaseRefusal.WHATSAPP_ONLY


# ---------------------------------------------------------------- remove_item


async def test_remove_locks_first_and_never_reads_catalog() -> None:
    carts, product = FakeCarts(), physical()
    reader = FakeProducts(product)
    await add_item(carts, reader, user_id=USER, product_id=product.id, quantity=1)
    reader.batches.clear()
    carts.calls.clear()
    await remove_item(carts, user_id=USER, product_id=product.id)
    assert carts.calls == ["lock(create=False)", "delete_line", "touch"]
    assert reader.batches == []


@pytest.mark.parametrize("has_cart", [True, False])
async def test_remove_of_a_missing_line_is_not_found(has_cart: bool) -> None:
    carts = FakeCarts()
    if has_cart:
        await carts.lock(USER, create=True)
    with pytest.raises(CartLineNotFoundError):
        await remove_item(carts, user_id=USER, product_id=uuid4())
    assert (USER in carts.carts) is has_cart


# ------------------------------------------------------------------ read_cart


async def test_read_never_locks_or_creates() -> None:
    carts = FakeCarts()
    view = await read_cart(carts, FakeProducts(), user_id=USER)
    assert (view.cart, view.lines) == (None, ())
    assert carts.calls == ["get"]
    assert USER not in carts.carts


async def test_read_makes_one_catalog_batch_in_add_order() -> None:
    carts, first, second = FakeCarts(), physical(), stl()
    reader = FakeProducts(first, second)
    for p in (first, second):
        await add_item(carts, reader, user_id=USER, product_id=p.id, quantity=1)
    reader.batches.clear()
    carts.calls.clear()
    view = await read_cart(carts, reader, user_id=USER)
    assert carts.calls == ["get", "lines"]
    assert reader.batches == [[first.id, second.id]]
    assert [v.line.product_id for v in view.lines] == [first.id, second.id]


# ------------------------------------------------- the VS-023 checkout interface


async def test_lock_for_checkout_never_creates_a_cart() -> None:
    carts = FakeCarts()
    assert await lock_cart_for_checkout(carts, user_id=USER) is None
    assert carts.calls == ["lock(create=False)"]
    assert USER not in carts.carts


async def test_lock_for_checkout_then_clear() -> None:
    carts, product = FakeCarts(), physical()
    await add_item(carts, FakeProducts(product), user_id=USER, product_id=product.id, quantity=2)
    carts.calls.clear()
    locked = await lock_cart_for_checkout(carts, user_id=USER)
    assert locked is not None
    assert [row.product_id for row in locked.lines] == [product.id]
    await clear_cart(carts, locked)
    assert carts.calls == ["lock(create=False)", "lines", "clear", "touch"]
    assert carts.rows[locked.cart.id] == []
