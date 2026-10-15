"""`add_to_wishlist`/`remove_from_wishlist` against fakes (VS-038 plan §6):
the "changed -> True" branching, repeat calls reporting no change, and the
404-on-unavailable path - including the is_deleted case."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.catalog.domain.enums import ProductType
from app.catalog.domain.product import Product, ProductAttributes, ProductDraft
from app.engagement.application.services.wishlist import add_to_wishlist, remove_from_wishlist
from app.engagement.domain.entities import WishlistItem
from app.engagement.domain.exceptions import WishlistProductUnavailableError


def _product(*, is_visible: bool = True, deleted: bool = False) -> Product:
    return Product(
        id=uuid4(),
        type=ProductType.STL,
        attributes=ProductAttributes(
            category_id=uuid4(),
            name="Widget",
            slug="widget",
            price_cents=1000,
            is_visible=is_visible,
        ),
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        deleted_at=datetime.now(UTC) if deleted else None,
    )


@dataclass
class _FakeProductStore:
    """Implements all of `ProductStore`; only `get_by_id` is exercised here."""

    product: Product | None

    async def add(self, draft: ProductDraft) -> Product:
        raise NotImplementedError

    async def get_by_id(self, product_id: UUID) -> Product | None:
        return self.product

    async def save_if_version(self, product: Product, expected_version: int) -> Product | None:
        raise NotImplementedError

    async def current_version(self, product_id: UUID) -> int | None:
        raise NotImplementedError

    async def get_for_update(self, product_id: UUID) -> Product | None:
        raise NotImplementedError

    async def get_many(self, product_ids: list[UUID]) -> list[Product]:
        raise NotImplementedError

    async def top_by_wishlist_count(self, limit: int) -> list[Product]:
        raise NotImplementedError


@dataclass
class _FakeWishlistStore:
    """Implements all of `WishlistStore`; only `add`/`remove` are exercised here."""

    add_result: bool = True
    remove_result: bool = True
    add_calls: list[tuple[UUID, UUID]] = field(default_factory=list)
    remove_calls: list[tuple[UUID, UUID]] = field(default_factory=list)

    async def add(self, *, user_id: UUID, product_id: UUID) -> bool:
        self.add_calls.append((user_id, product_id))
        return self.add_result

    async def remove(self, *, user_id: UUID, product_id: UUID) -> bool:
        self.remove_calls.append((user_id, product_id))
        return self.remove_result

    async def list_page(
        self, *, user_id: UUID, after: tuple[datetime, UUID] | None, limit: int
    ) -> list[WishlistItem]:
        raise NotImplementedError

    async def count_active(self) -> int:
        raise NotImplementedError


async def test_add_reports_changed_on_a_fresh_insert() -> None:
    store = _FakeWishlistStore(add_result=True)
    product = _product()

    changed = await add_to_wishlist(
        store, _FakeProductStore(product), user_id=uuid4(), product_id=product.id
    )

    assert changed is True
    assert len(store.add_calls) == 1


async def test_repeat_add_reports_no_change() -> None:
    store = _FakeWishlistStore(add_result=False)
    product = _product()

    changed = await add_to_wishlist(
        store, _FakeProductStore(product), user_id=uuid4(), product_id=product.id
    )

    assert changed is False


async def test_repeat_remove_reports_no_change() -> None:
    store = _FakeWishlistStore(remove_result=False)

    changed = await remove_from_wishlist(store, user_id=uuid4(), product_id=uuid4())

    assert changed is False


async def test_remove_reports_changed_on_a_real_soft_delete() -> None:
    store = _FakeWishlistStore(remove_result=True)

    changed = await remove_from_wishlist(store, user_id=uuid4(), product_id=uuid4())

    assert changed is True


async def test_add_of_a_hidden_product_is_rejected() -> None:
    store = _FakeWishlistStore()
    product = _product(is_visible=False)

    with pytest.raises(WishlistProductUnavailableError):
        await add_to_wishlist(
            store, _FakeProductStore(product), user_id=uuid4(), product_id=product.id
        )
    assert store.add_calls == []


async def test_add_of_a_deleted_product_is_rejected() -> None:
    store = _FakeWishlistStore()
    product = _product(deleted=True)

    with pytest.raises(WishlistProductUnavailableError):
        await add_to_wishlist(
            store, _FakeProductStore(product), user_id=uuid4(), product_id=product.id
        )
    assert store.add_calls == []


async def test_add_of_an_unknown_product_is_rejected() -> None:
    store = _FakeWishlistStore()
    product_id = uuid4()

    with pytest.raises(WishlistProductUnavailableError):
        await add_to_wishlist(
            store, _FakeProductStore(None), user_id=uuid4(), product_id=product_id
        )
    assert store.add_calls == []
