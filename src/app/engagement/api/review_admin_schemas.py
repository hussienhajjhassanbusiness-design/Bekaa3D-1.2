"""Admin review bodies (VS-037 plan 2.1, api-endpoints.md 22 and 29.8). No author identity
beyond `user_id`; the badge is shown as stored (evidence) and as the storefront shows it."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict

from app.catalog.application.ports import ReviewableProduct
from app.core.text import CONTROL_CHARACTER_MESSAGE, has_control_characters
from app.engagement.domain.reviews import Review, badge_shown, normalise_reason


def _reason(value: str | None) -> str | None:
    if value is not None and has_control_characters(value):
        raise ValueError(CONTROL_CHARACTER_MESSAGE)
    return normalise_reason(value)


class ReviewModerationRequest(BaseModel):
    """The optional reason, kept only in the audit row (D6)."""

    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str | None, AfterValidator(_reason)] = None


class AdminReviewRead(BaseModel):
    id: UUID
    product_id: UUID
    product_slug: str | None
    user_id: UUID
    rating: int
    body: str | None
    is_verified_purchase: bool
    badge_shown: bool
    is_hidden: bool
    hidden_at: datetime | None
    created_at: datetime
    updated_at: datetime
    edited: bool

    @classmethod
    def of(cls, review: Review, product: ReviewableProduct | None) -> Self:
        mode = product.purchase_mode if product is not None else None
        return cls(
            id=review.id,
            product_id=review.product_id,
            product_slug=product.slug if product is not None and product.live else None,
            user_id=review.user_id,
            rating=review.rating,
            body=review.body,
            is_verified_purchase=review.is_verified_purchase,
            badge_shown=badge_shown(review.is_verified_purchase, mode),
            is_hidden=review.is_hidden,
            hidden_at=review.hidden_at,
            created_at=review.created_at,
            updated_at=review.updated_at,
            edited=review.edited,
        )


class AdminReviewDetail(AdminReviewRead):
    """The same fields as a list item, under the api-endpoints name."""


class AdminReviewPage(BaseModel):
    items: list[AdminReviewRead]
    next_cursor: str | None
