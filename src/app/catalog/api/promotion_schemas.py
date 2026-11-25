"""Promotion payloads. `discount_value` is a whole percent for `percentage` and cents (USD)
for `fixed`; `status` is derived from `active` and the window, never stored."""

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.catalog.domain.promotions import (
    MAX_BADGE_LENGTH,
    MAX_NAME_LENGTH,
    MAX_SELECTED_PRODUCTS,
    DiscountType,
    Promotion,
    PromotionFields,
    PromotionScope,
    PromotionStatus,
)

_VALUE_DESCRIPTION = "A whole percent from 1 to 100 for `percentage`; cents for `fixed`."


class AdminPromotionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    badge_text: str | None = Field(default=None, max_length=MAX_BADGE_LENGTH)
    discount_type: DiscountType
    discount_value: int = Field(ge=1, description=_VALUE_DESCRIPTION)
    scope: PromotionScope
    product_ids: list[UUID] = Field(
        default_factory=list,
        max_length=MAX_SELECTED_PRODUCTS,
        description="The products of a `selected` scope; empty for any other scope.",
    )
    starts_at: AwareDatetime
    ends_at: AwareDatetime = Field(description="Exclusive.")
    active: bool = True

    def to_fields(self) -> PromotionFields:
        return PromotionFields(
            name=self.name,
            badge_text=self.badge_text,
            discount_type=self.discount_type,
            discount_value=self.discount_value,
            scope=self.scope,
            product_ids=frozenset(self.product_ids),
            starts_at=self.starts_at,
            ends_at=self.ends_at,
            active=self.active,
        )


class AdminPromotionUpdate(BaseModel):
    """Only the fields sent change; the merged promotion is validated as a whole.
    `active: false` switches a promotion off at once; `true` switches it back on."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    badge_text: str | None = Field(default=None, max_length=MAX_BADGE_LENGTH)
    discount_type: DiscountType | None = None
    discount_value: int | None = Field(default=None, ge=1, description=_VALUE_DESCRIPTION)
    scope: PromotionScope | None = None
    product_ids: list[UUID] | None = Field(default=None, max_length=MAX_SELECTED_PRODUCTS)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    active: bool | None = None

    def merged(self, current: PromotionFields) -> PromotionFields:
        sent: dict[str, Any] = self.model_dump(exclude_unset=True)
        # A null for a required field is "not sent", never "clear it".
        for key in ("name", "discount_type", "discount_value", "scope", "starts_at", "ends_at"):
            if sent.get(key, ...) is None:
                sent.pop(key)
        if sent.get("active", ...) is None:
            sent.pop("active", None)
        product_ids = sent.pop("product_ids", None)
        changes: dict[str, Any] = {**sent}
        if product_ids is not None:
            changes["product_ids"] = frozenset(product_ids)
        elif "scope" in sent and sent["scope"] is not PromotionScope.SELECTED:
            # Moving off `selected` drops its product list instead of failing on it.
            changes["product_ids"] = frozenset()
        values = {
            "name": current.name,
            "badge_text": current.badge_text,
            "discount_type": current.discount_type,
            "discount_value": current.discount_value,
            "scope": current.scope,
            "product_ids": current.product_ids,
            "starts_at": current.starts_at,
            "ends_at": current.ends_at,
            "active": current.active,
        } | changes
        return PromotionFields(**values)


class AdminPromotionRead(BaseModel):
    id: UUID
    name: str
    badge_text: str | None
    discount_type: DiscountType
    discount_value: int = Field(description=_VALUE_DESCRIPTION)
    scope: PromotionScope
    product_ids: list[UUID]
    starts_at: datetime
    ends_at: datetime
    active: bool
    status: PromotionStatus = Field(description="Derived now: scheduled, active, ended, inactive.")
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, promotion: Promotion, now: datetime) -> Self:
        f = promotion.fields
        return cls(
            id=promotion.id,
            name=f.name,
            badge_text=f.badge_text,
            discount_type=f.discount_type,
            discount_value=f.discount_value,
            scope=f.scope,
            product_ids=sorted(f.product_ids),
            starts_at=f.starts_at,
            ends_at=f.ends_at,
            active=f.active,
            status=promotion.status(now),
            created_at=promotion.created_at,
            updated_at=promotion.updated_at,
        )


class AdminPromotionList(BaseModel):
    items: list[AdminPromotionRead] = Field(description="Newest first, at most 200.")


class PublicPromotionRead(BaseModel):
    """An active promotion, for the storefront's campaign banner. No product list: the
    products are `GET /api/v1/products?promotion_id=`, priced by the server."""

    id: UUID
    name: str
    badge_text: str | None
    discount_type: DiscountType
    discount_value: int = Field(description=_VALUE_DESCRIPTION)
    scope: PromotionScope
    starts_at: datetime
    ends_at: datetime

    @classmethod
    def of(cls, promotion: Promotion) -> Self:
        f = promotion.fields
        return cls(
            id=promotion.id,
            name=f.name,
            badge_text=f.badge_text,
            discount_type=f.discount_type,
            discount_value=f.discount_value,
            scope=f.scope,
            starts_at=f.starts_at,
            ends_at=f.ends_at,
        )


class PublicPromotionList(BaseModel):
    items: list[PublicPromotionRead] = Field(description="Active now, soonest ending first.")
