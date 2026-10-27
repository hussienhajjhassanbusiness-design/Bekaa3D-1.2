"""VS-037 plan 6.1: hide / restore call their ports in lock order, check the state under the
row lock, treat a deleted review as missing, and audit no text and no author."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.catalog.application.ports import PurchaseMode, ReviewableProduct
from app.engagement.application.commands.custom_request_pipeline import AdminContext
from app.engagement.application.services.review_moderation import moderate_review
from app.engagement.domain.exceptions import ReviewModerationConflictError, ReviewNotFoundError
from app.engagement.domain.reviews import (
    MODERATION_REASON_MAX,
    Review,
    normalise_reason,
)

NOW = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)
ADMIN = uuid4()
CONTEXT = AdminContext(actor_user_id=ADMIN, request_id="req-1", ip_hash="iphash")
BODY = "The author's private words"


def _review(*, hidden: bool = False, deleted: bool = False) -> Review:
    return Review(
        id=uuid4(),
        user_id=uuid4(),
        product_id=uuid4(),
        rating=2,
        body=BODY,
        is_verified_purchase=True,
        is_hidden=hidden,
        hidden_at=datetime(2026, 10, 1, tzinfo=UTC) if hidden else None,
        deleted_at=NOW if deleted else None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
        updated_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


class Fake:
    """`ReviewModerationStore`, `ReviewableProducts` and `AuditWriter` in one call log."""

    def __init__(self, review: Review | None, *, locked: Review | None = None) -> None:
        self.calls: list[str] = []
        self.review = review
        self.locked = review if locked is None else locked
        self.audits: list[dict[str, Any]] = []
        self.rating: tuple[Decimal, int] | None = None
        self.hidden: tuple[bool, datetime] | None = None

    async def lock_user(self, user_id: UUID) -> None:
        self.calls.append("lock_user")

    async def product_id_of(self, review_id: UUID) -> UUID | None:
        self.calls.append("product_id_of")
        return self.review.product_id if self.review else None

    async def lock_for_moderation(self, review_id: UUID) -> Review | None:
        self.calls.append("lock_for_moderation")
        return self.locked

    async def set_hidden(self, review_id: UUID, *, hidden: bool, at: datetime) -> None:
        self.calls.append("set_hidden")
        self.hidden = (hidden, at)

    async def visible_totals(self, product_id: UUID) -> tuple[int, int]:
        self.calls.append("visible_totals")
        return 9, 2

    async def lock(self, product_id: UUID) -> ReviewableProduct | None:
        self.calls.append("lock_product")
        return ReviewableProduct(product_id, "slug", True, True, PurchaseMode.BOTH)

    async def set_rating(self, product_id: UUID, average: Decimal, count: int) -> None:
        self.calls.append("set_rating")
        self.rating = (average, count)

    async def record(self, **row: Any) -> None:
        self.calls.append("audit")
        self.audits.append(row)


async def _run(fake: Fake, review_id: UUID, *, hide: bool, reason: str | None = None) -> Review:
    return await moderate_review(
        fake, fake, fake, review_id=review_id, hide=hide, reason=reason, now=NOW, context=CONTEXT
    )


FULL_ORDER = [
    "product_id_of",
    "lock_product",
    "lock_for_moderation",
    "set_hidden",
    "visible_totals",
    "set_rating",
    "audit",
]
NOTHING_WRITTEN = ["product_id_of", "lock_product", "lock_for_moderation"]


async def test_hide_locks_the_product_then_the_row_and_never_takes_r_user() -> None:
    review = _review()
    fake = Fake(review)
    out = await _run(fake, review.id, hide=True, reason="spam")
    assert fake.calls == FULL_ORDER
    assert "lock_user" not in fake.calls
    assert fake.hidden == (True, NOW)
    assert fake.rating == (Decimal("4.50"), 2)
    assert (out.is_hidden, out.hidden_at) == (True, NOW)


async def test_restore_runs_the_same_order_and_clears_hidden_at() -> None:
    review = _review(hidden=True)
    fake = Fake(review)
    out = await _run(fake, review.id, hide=False)
    assert fake.calls == FULL_ORDER
    assert fake.hidden == (False, NOW)
    assert (out.is_hidden, out.hidden_at) == (False, None)
    assert fake.audits[0]["action"] == "review.restored"
    assert fake.audits[0]["after_data"]["hidden_at"] is None


@pytest.mark.parametrize("hidden", [True, False])
async def test_a_repeat_is_a_conflict_with_nothing_written_after_the_lock(hidden: bool) -> None:
    review = _review(hidden=hidden)
    fake = Fake(review)
    with pytest.raises(ReviewModerationConflictError) as caught:
        await _run(fake, review.id, hide=hidden)
    assert caught.value.is_hidden is hidden
    assert fake.calls == NOTHING_WRITTEN
    assert fake.hidden is None and fake.rating is None and fake.audits == []


async def test_the_state_is_read_from_the_locked_row_not_the_unlocked_read() -> None:
    """The row was hidden while this transaction waited: the locked copy decides."""
    review = _review()
    fake = Fake(review, locked=replace(review, is_hidden=True, hidden_at=NOW))
    with pytest.raises(ReviewModerationConflictError):
        await _run(fake, review.id, hide=True)
    assert fake.audits == []


async def test_an_unknown_review_is_missing_before_any_lock() -> None:
    fake = Fake(None)
    with pytest.raises(ReviewNotFoundError):
        await _run(fake, uuid4(), hide=True)
    assert fake.calls == ["product_id_of"]


@pytest.mark.parametrize("hide", [True, False])
async def test_a_review_deleted_under_the_lock_is_missing_and_nothing_is_written(
    hide: bool,
) -> None:
    review = _review(hidden=not hide)
    fake = Fake(review, locked=replace(review, deleted_at=NOW))
    with pytest.raises(ReviewNotFoundError):
        await _run(fake, review.id, hide=hide)
    assert fake.calls == NOTHING_WRITTEN
    assert fake.audits == []


@pytest.mark.parametrize("reason", ["Contains an insult", None])
async def test_the_audit_row_carries_state_and_reason_but_no_text_or_author(
    reason: str | None,
) -> None:
    review = _review()
    fake = Fake(review)
    await _run(fake, review.id, hide=True, reason=reason)
    [row] = fake.audits
    assert row["action"] == "review.hidden"
    assert (row["entity_type"], row["entity_id"]) == ("review", review.id)
    assert (row["actor_user_id"], row["request_id"], row["ip_hash"]) == (ADMIN, "req-1", "iphash")
    assert row["before_data"] == {
        "is_hidden": False,
        "hidden_at": None,
        "product_id": str(review.product_id),
    }
    assert row["after_data"] == {
        "is_hidden": True,
        "hidden_at": NOW.isoformat(),
        "product_id": str(review.product_id),
        "reason": reason,
    }
    dumped = json.dumps([row["before_data"], row["after_data"]])
    assert BODY not in dumped and str(review.user_id) not in dumped


def test_the_reason_is_trimmed_blank_is_none_and_the_max_holds() -> None:
    assert normalise_reason("  spam  ") == "spam"
    assert normalise_reason("   ") is None
    assert normalise_reason(None) is None
    assert normalise_reason("x" * MODERATION_REASON_MAX) == "x" * MODERATION_REASON_MAX
    with pytest.raises(ValueError, match="at most 500"):
        normalise_reason("x" * (MODERATION_REASON_MAX + 1))
