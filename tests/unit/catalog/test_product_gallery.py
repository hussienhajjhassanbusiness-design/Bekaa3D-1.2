"""Cover, order, cap and deletion rules for a product's live images (VS-014)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.catalog.domain.exceptions import (
    CoverDeletionBlockedError,
    ImageOrderMismatchError,
    ProductImageNotFoundError,
    UploadRejectedError,
)
from app.catalog.domain.product_image import (
    MAX_IMAGES_PER_PRODUCT,
    ProductGallery,
    ProductImage,
)

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)
PRODUCT = uuid.uuid4()


def _image(order: int, *, cover: bool = False) -> ProductImage:
    return ProductImage(
        id=uuid.uuid4(),
        product_id=PRODUCT,
        storage_key=f"products/{uuid.uuid4()}.jpg",
        alt_text=None,
        sort_order=order,
        is_cover=cover,
        created_at=NOW,
        updated_at=NOW,
    )


def _gallery(count: int) -> ProductGallery:
    return ProductGallery([_image(n, cover=n == 0) for n in range(count)])


def test_the_first_image_is_the_cover_and_later_ones_append() -> None:
    assert (ProductGallery([]).next_slot().is_cover, ProductGallery([]).next_slot().sort_order) == (
        True,
        0,
    )
    slot = _gallery(3).next_slot()
    assert (slot.is_cover, slot.sort_order) == (False, 3)


def test_the_cap_refuses_one_past_the_limit_but_not_at_it() -> None:
    _gallery(MAX_IMAGES_PER_PRODUCT - 1).next_slot()
    with pytest.raises(UploadRejectedError):
        _gallery(MAX_IMAGES_PER_PRODUCT).next_slot()


def test_setting_a_cover_moves_it_and_returns_the_loser_first() -> None:
    gallery = _gallery(3)
    old, new = gallery.images[0], gallery.images[2]
    changed = gallery.set_cover(new.id, LATER)
    assert changed == [old, new]
    assert [i.is_cover for i in gallery.images] == [False, False, True]
    assert gallery.set_cover(new.id, LATER) == []


def test_reorder_assigns_positions_in_the_given_order() -> None:
    gallery = _gallery(3)
    a, b, c = gallery.images
    gallery.reorder([c.id, a.id, b.id], LATER)
    assert [i.id for i in gallery.images] == [c.id, a.id, b.id]
    assert [i.sort_order for i in gallery.images] == [0, 1, 2]


@pytest.mark.parametrize("case", ["missing", "extra", "duplicate", "empty"])
def test_reorder_must_name_exactly_the_live_set(case: str) -> None:
    gallery = _gallery(3)
    ids = [i.id for i in gallery.images]
    bad = {
        "missing": ids[:2],
        "extra": [*ids, uuid.uuid4()],
        "duplicate": [ids[0], ids[0], ids[1], ids[2]],
        "empty": [],
    }[case]
    with pytest.raises(ImageOrderMismatchError):
        gallery.reorder(bad, LATER)
    assert [i.sort_order for i in gallery.images] == [0, 1, 2]


def test_the_cover_cannot_be_deleted_while_others_remain() -> None:
    gallery = _gallery(2)
    with pytest.raises(CoverDeletionBlockedError):
        gallery.delete(gallery.images[0].id, LATER)


def test_the_last_image_may_be_deleted_even_as_cover() -> None:
    gallery = _gallery(1)
    gone = gallery.delete(gallery.images[0].id, LATER)
    assert gone.deleted_at == LATER and gone.is_cover is False
    assert gallery.images == []


def test_deleting_a_non_cover_keeps_the_cover() -> None:
    gallery = _gallery(2)
    gallery.delete(gallery.images[1].id, LATER)
    assert [i.is_cover for i in gallery.images] == [True]


def test_an_unknown_image_is_not_found_everywhere() -> None:
    gallery = _gallery(2)
    stranger = uuid.uuid4()
    for action in (
        gallery.get,
        lambda i: gallery.set_cover(i, LATER),
        lambda i: gallery.delete(i, LATER),
    ):
        with pytest.raises(ProductImageNotFoundError):
            action(stranger)
