from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.catalog.domain.product_image import (
    MAX_ALT_TEXT_LENGTH,
    MAX_IMAGES_PER_PRODUCT,
    ProductImage,
)
from app.core.text import reject_control_characters


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


AltText = Annotated[
    str | None,
    Field(max_length=MAX_ALT_TEXT_LENGTH),
    AfterValidator(lambda v: reject_control_characters(v) if v is not None else None),
    AfterValidator(_blank_to_none),
]


def media_url(base_url: str, storage_key: str) -> str:
    return f"{base_url.rstrip('/')}/{storage_key}"


class ProductImageRead(BaseModel):
    id: UUID
    product_id: UUID
    url: str
    alt_text: str | None
    sort_order: int
    is_cover: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, image: ProductImage, base_url: str) -> Self:
        return cls(
            id=image.id,
            product_id=image.product_id,
            url=media_url(base_url, image.storage_key),
            alt_text=image.alt_text,
            sort_order=image.sort_order,
            is_cover=image.is_cover,
            created_at=image.created_at,
            updated_at=image.updated_at,
        )


class ProductImageList(BaseModel):
    items: list[ProductImageRead]


class ProductImageUpdate(BaseModel):
    """`alt_text` is required; null or blank clears it."""

    model_config = ConfigDict(extra="forbid")

    alt_text: AltText


class ProductImageOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_ids: list[UUID] = Field(max_length=MAX_IMAGES_PER_PRODUCT * 2)
