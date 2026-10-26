"""Review request and response bodies (VS-036 plan 2, api-endpoints.md 29.8). No author
identity is ever exposed (D12); the badge is masked by D14 before it gets here."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.catalog.application.ports import ReviewableProduct
from app.core.text import CONTROL_CHARACTER_MESSAGE, has_control_characters
from app.engagement.domain.reviews import RATING_MAX, RATING_MIN, Review, normalise_body


def _body(value: str | None) -> str | None:
    if value is not None and has_control_characters(value, allow_line_breaks=True):
        raise ValueError(CONTROL_CHARACTER_MESSAGE)
    return normalise_body(value)


Rating = Annotated[int, Field(ge=RATING_MIN, le=RATING_MAX, strict=True)]
Body = Annotated[str | None, AfterValidator(_body)]


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    rating: Rating
    body: Body = None


class ReviewUpdate(BaseModel):
    """At least one field; `body: null` clears the text."""

    model_config = ConfigDict(extra="forbid")

    rating: Rating | None = None
    body: Body = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one of rating or body is required")
        if "rating" in self.model_fields_set and self.rating is None:
            raise ValueError("rating cannot be null")
        return self


class PublicReviewRead(BaseModel):
    id: UUID
    rating: int
    body: str | None
    is_verified_purchase: bool
    created_at: datetime
    edited: bool

    @classmethod
    def of(cls, review: Review, *, shown: bool) -> Self:
        return cls(
            id=review.id,
            rating=review.rating,
            body=review.body,
            is_verified_purchase=shown,
            created_at=review.created_at,
            edited=review.edited,
        )


class MyReviewRead(PublicReviewRead):
    product_id: UUID
    product_slug: str | None
    is_hidden: bool

    @classmethod
    def mine(cls, review: Review, product: ReviewableProduct | None, *, shown: bool) -> Self:
        return cls(
            **PublicReviewRead.of(review, shown=shown).model_dump(),
            product_id=review.product_id,
            product_slug=product.slug if product is not None and product.live else None,
            is_hidden=review.is_hidden,
        )


class ReviewPage(BaseModel):
    items: list[PublicReviewRead]
    next_cursor: str | None


class MyReviewPage(BaseModel):
    items: list[MyReviewRead]
    next_cursor: str | None
