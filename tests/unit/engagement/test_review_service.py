"""VS-036 plan 6.1: the use cases call their ports in lock order, and refuse before any."""

import subprocess
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.catalog.application.ports import ReviewableProduct
from app.engagement.application.services.reviews import (
    create_review,
    delete_review,
    edit_review,
)
from app.engagement.domain.exceptions import (
    ReviewAlreadyExistsError,
    ReviewContentRejectedError,
    ReviewNotFoundError,
    ReviewProductUnavailableError,
)
from app.engagement.domain.reviews import NewReview, Review

NOW = datetime(2026, 10, 26, tzinfo=UTC)
SRC = Path(__file__).resolve().parents[3] / "src"


class Fake:
    def __init__(self, product: ReviewableProduct | None, existing: Review | None = None) -> None:
        self.calls: list[str] = []
        self.product = product
        self.existing = existing
        self.evidence_ids: set[UUID] = set()
        self.rating: tuple[Decimal, int] | None = None

    # ReviewStore
    async def lock_user(self, user_id: UUID) -> None:
        self.calls.append("lock_user")

    async def live_for(self, user_id: UUID, product_id: UUID) -> Review | None:
        self.calls.append("live_for")
        return self.existing

    async def own_product_id(self, review_id: UUID, user_id: UUID) -> UUID | None:
        self.calls.append("own_product_id")
        return self.existing.product_id if self.existing else None

    async def get_own_for_update(self, review_id: UUID, user_id: UUID) -> Review | None:
        self.calls.append("get_own_for_update")
        return self.existing

    async def insert(self, new: NewReview) -> Review:
        self.calls.append("insert")
        return Review(
            uuid4(),
            new.user_id,
            new.product_id,
            new.rating,
            new.body,
            new.is_verified_purchase,
            False,
            None,
            None,
            NOW,
            NOW,
        )

    async def update(
        self, review_id: UUID, *, rating: int, body: str | None, verified: bool
    ) -> Review:
        self.calls.append("update")
        assert self.existing is not None
        return replace(self.existing, rating=rating, body=body, is_verified_purchase=verified)

    async def soft_delete(self, review_id: UUID) -> None:
        self.calls.append("soft_delete")

    async def visible_totals(self, product_id: UUID) -> tuple[int, int]:
        self.calls.append("visible_totals")
        return 9, 2

    # ReviewableProducts
    async def lock(self, product_id: UUID) -> ReviewableProduct | None:
        self.calls.append("products.lock")
        return self.product

    async def set_rating(self, product_id: UUID, average: Decimal, count: int) -> None:
        self.calls.append("set_rating")
        self.rating = (average, count)

    # PurchaseEvidence
    async def evidence(self, user_id: UUID, product_ids: Sequence[UUID]) -> set[UUID]:
        self.calls.append("evidence")
        return self.evidence_ids & set(product_ids)


def _product(*, live: bool = True, visible: bool = True) -> ReviewableProduct:
    return ReviewableProduct(uuid4(), "a-slug", live, visible, None)


def _review(product_id: UUID, user_id: UUID) -> Review:
    return Review(uuid4(), user_id, product_id, 3, "ok", False, True, NOW, None, NOW, NOW)


async def test_create_calls_its_ports_in_lock_order() -> None:
    fake = Fake(_product())
    fake.evidence_ids = {fake.product.id} if fake.product else set()
    assert fake.product is not None
    review = await create_review(
        fake, fake, fake.evidence, user_id=uuid4(), product_id=fake.product.id, rating=5, body=None
    )
    assert fake.calls == [
        "lock_user",
        "products.lock",
        "live_for",
        "evidence",
        "insert",
        "visible_totals",
        "set_rating",
    ]
    assert review.is_verified_purchase
    assert fake.rating == (Decimal("4.50"), 2)


@pytest.mark.parametrize(
    ("rating", "body", "error"),
    [
        (5, "visit x.com", ReviewContentRejectedError),
        (5, "shit", ReviewContentRejectedError),
        (0, None, ValueError),
        (6, None, ValueError),
        (5, "a" * 2001, ValueError),
    ],
)
async def test_a_refusal_calls_no_port(rating: int, body: str, error: type[Exception]) -> None:
    fake = Fake(_product())
    with pytest.raises(error):
        await create_review(
            fake, fake, fake.evidence, user_id=uuid4(), product_id=uuid4(), rating=rating, body=body
        )
    assert fake.calls == []


@pytest.mark.parametrize("product", [None, _product(live=False), _product(visible=False)])
async def test_create_refuses_a_missing_deleted_or_invisible_product(
    product: ReviewableProduct | None,
) -> None:
    fake = Fake(product)
    with pytest.raises(ReviewProductUnavailableError):
        await create_review(
            fake, fake, fake.evidence, user_id=uuid4(), product_id=uuid4(), rating=4, body=None
        )
    assert "insert" not in fake.calls


async def test_a_second_live_review_is_refused_before_the_evidence_read() -> None:
    product = _product()
    fake = Fake(product, existing=_review(product.id, uuid4()))
    with pytest.raises(ReviewAlreadyExistsError):
        await create_review(
            fake, fake, fake.evidence, user_id=uuid4(), product_id=product.id, rating=4, body=None
        )
    assert fake.calls == ["lock_user", "products.lock", "live_for"]


async def test_edit_locks_user_product_then_row_and_keeps_hidden() -> None:
    product, user_id = _product(), uuid4()
    fake = Fake(product, existing=_review(product.id, user_id))
    review = await edit_review(
        fake,
        fake,
        fake.evidence,
        user_id=user_id,
        review_id=uuid4(),
        rating=None,
        body="better now",
        body_given=True,
    )
    assert fake.calls == [
        "lock_user",
        "own_product_id",
        "products.lock",
        "get_own_for_update",
        "evidence",
        "update",
        "visible_totals",
        "set_rating",
    ]
    assert (review.rating, review.body, review.is_hidden) == (3, "better now", True)


async def test_edit_with_body_null_clears_the_text() -> None:
    product, user_id = _product(), uuid4()
    fake = Fake(product, existing=_review(product.id, user_id))
    review = await edit_review(
        fake,
        fake,
        fake.evidence,
        user_id=user_id,
        review_id=uuid4(),
        rating=2,
        body=None,
        body_given=True,
    )
    assert (review.rating, review.body) == (2, None)


async def test_edit_or_delete_of_an_unknown_review_is_not_found() -> None:
    fake = Fake(_product())
    with pytest.raises(ReviewNotFoundError):
        await edit_review(
            fake,
            fake,
            fake.evidence,
            user_id=uuid4(),
            review_id=uuid4(),
            rating=4,
            body=None,
            body_given=False,
        )
    with pytest.raises(ReviewNotFoundError):
        await delete_review(fake, fake, user_id=uuid4(), review_id=uuid4())
    assert "products.lock" not in fake.calls


async def test_delete_locks_then_soft_deletes_then_recomputes() -> None:
    product, user_id = _product(), uuid4()
    fake = Fake(product, existing=_review(product.id, user_id))
    await delete_review(fake, fake, user_id=user_id, review_id=uuid4())
    assert fake.calls == [
        "lock_user",
        "own_product_id",
        "products.lock",
        "get_own_for_update",
        "soft_delete",
        "visible_totals",
        "set_rating",
    ]


def test_engagement_public_never_imports_ordering() -> None:
    """Ordering's line writers import Engagement; the reverse would be a cycle (plan 3.0)."""
    import ast

    tree = ast.parse((SRC / "app" / "engagement" / "public.py").read_text(encoding="utf-8"))
    names = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(name.startswith("app.ordering") for name in names)


def test_both_publics_import_in_a_fresh_interpreter() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import app.engagement.public, app.ordering.public"],
        capture_output=True,
        text=True,
        cwd=SRC,
    )
    assert result.returncode == 0, result.stderr
