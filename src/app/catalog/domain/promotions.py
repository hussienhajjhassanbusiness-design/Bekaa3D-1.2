"""Seasonal promotions (Eid, Ramadan, Christmas...): administrator-created price campaigns.

A promotion is not an offer (a negotiation with one customer) and not a coupon (nothing is
redeemed). While it is active it lowers the price the shop charges for the products in its
scope. The rules here are the only place an effective price is worked out; cart, checkout,
orders, offers and the storefront all read it through the catalogue, never compute it.

Rules (v1):
- `percentage`: a whole percent from 1 to 100; the discount is rounded half up to a cent.
- `fixed`: a positive amount in cents, in the shop's one currency.
- The effective price is never negative: a discount larger than the price makes it 0.
- A promotion applies only while `active` and `starts_at <= now < ends_at`.
- No stacking: when several promotions cover a product, the one giving the lowest price
  applies (ties: the one ending first, then the lowest id), and only that one.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.catalog.domain.enums import ProductType
from app.core.text import has_control_characters

MAX_NAME_LENGTH = 80
MAX_BADGE_LENGTH = 24
MAX_SELECTED_PRODUCTS = 200
MAX_FIXED_DISCOUNT_CENTS = 100_000_000  # $1,000,000: a guard against a typo, not a policy.


class DiscountType(StrEnum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class PromotionScope(StrEnum):
    ALL = "all"
    PHYSICAL = "physical"
    STL = "stl"
    SELECTED = "selected"


class PromotionStatus(StrEnum):
    """Derived from `active` and the window, never stored."""

    SCHEDULED = "scheduled"
    ACTIVE = "active"
    ENDED = "ended"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class PromotionFields:
    """Everything an administrator sets; validated as a whole by `validate_promotion`."""

    name: str
    discount_type: DiscountType
    discount_value: int
    scope: PromotionScope
    product_ids: frozenset[UUID]
    starts_at: datetime
    ends_at: datetime
    active: bool
    badge_text: str | None = None


@dataclass(frozen=True)
class Promotion:
    id: UUID
    fields: PromotionFields
    created_at: datetime
    updated_at: datetime

    def status(self, now: datetime) -> PromotionStatus:
        f = self.fields
        if not f.active:
            return PromotionStatus.INACTIVE
        if now < f.starts_at:
            return PromotionStatus.SCHEDULED
        if now >= f.ends_at:
            return PromotionStatus.ENDED
        return PromotionStatus.ACTIVE

    def covers(self, product_id: UUID, product_type: ProductType) -> bool:
        scope = self.fields.scope
        if scope is PromotionScope.ALL:
            return True
        if scope is PromotionScope.PHYSICAL:
            return product_type is ProductType.PHYSICAL
        if scope is PromotionScope.STL:
            return product_type is ProductType.STL
        return product_id in self.fields.product_ids


@dataclass(frozen=True)
class AppliedPromotion:
    """The one promotion behind a product's price right now."""

    promotion: Promotion
    list_price_cents: int
    price_cents: int


def discounted_cents(list_price_cents: int, discount_type: DiscountType, value: int) -> int:
    """The price after one discount: never below 0, never above the list price."""
    if discount_type is DiscountType.PERCENTAGE:
        discount = (list_price_cents * value + 50) // 100
    else:
        discount = value
    return max(list_price_cents - min(discount, list_price_cents), 0)


def apply_best(
    *,
    product_id: UUID,
    product_type: ProductType,
    list_price_cents: int,
    promotions: list[Promotion],
    now: datetime,
) -> AppliedPromotion | None:
    """The single promotion that applies (no stacking), or None. A promotion that would not
    lower the price at all (e.g. 1% of 10 cents) does not apply."""
    best: tuple[int, datetime, UUID, Promotion] | None = None
    for promotion in promotions:
        if promotion.status(now) is not PromotionStatus.ACTIVE:
            continue
        if not promotion.covers(product_id, product_type):
            continue
        f = promotion.fields
        price = discounted_cents(list_price_cents, f.discount_type, f.discount_value)
        if price >= list_price_cents:
            continue
        key = (price, f.ends_at, promotion.id, promotion)
        if best is None or key[:3] < best[:3]:
            best = key
    if best is None:
        return None
    return AppliedPromotion(
        promotion=best[3], list_price_cents=list_price_cents, price_cents=best[0]
    )


def _clean(text: str | None) -> str | None:
    return None if text is None else text.strip()


def normalized(fields: PromotionFields) -> PromotionFields:
    """Trimmed text; an empty badge means none."""
    badge = _clean(fields.badge_text)
    return PromotionFields(
        name=_clean(fields.name) or "",
        discount_type=fields.discount_type,
        discount_value=fields.discount_value,
        scope=fields.scope,
        product_ids=fields.product_ids,
        starts_at=fields.starts_at,
        ends_at=fields.ends_at,
        active=fields.active,
        badge_text=badge or None,
    )


def validate_promotion(fields: PromotionFields) -> dict[str, str]:
    """Field -> reason for every broken rule; empty when the promotion is valid.
    Expects `normalized` fields."""
    errors: dict[str, str] = {}
    if not fields.name:
        errors["name"] = "must not be blank"
    elif len(fields.name) > MAX_NAME_LENGTH:
        errors["name"] = f"must be at most {MAX_NAME_LENGTH} characters"
    elif has_control_characters(fields.name):
        errors["name"] = "must not contain control characters"
    badge = fields.badge_text
    if badge is not None:
        if len(badge) > MAX_BADGE_LENGTH:
            errors["badge_text"] = f"must be at most {MAX_BADGE_LENGTH} characters"
        elif has_control_characters(badge):
            errors["badge_text"] = "must not contain control characters"
    if fields.discount_type is DiscountType.PERCENTAGE:
        if not 1 <= fields.discount_value <= 100:
            errors["discount_value"] = "a percentage must be a whole number from 1 to 100"
    elif not 1 <= fields.discount_value <= MAX_FIXED_DISCOUNT_CENTS:
        errors["discount_value"] = "a fixed discount must be a positive amount in cents"
    if fields.starts_at.tzinfo is None or fields.ends_at.tzinfo is None:
        errors["starts_at"] = "must include a UTC offset"
    elif fields.starts_at >= fields.ends_at:
        errors["ends_at"] = "must be after starts_at"
    if fields.scope is PromotionScope.SELECTED:
        if not fields.product_ids:
            errors["product_ids"] = "must name at least one product for a selected scope"
        elif len(fields.product_ids) > MAX_SELECTED_PRODUCTS:
            errors["product_ids"] = f"must name at most {MAX_SELECTED_PRODUCTS} products"
    elif fields.product_ids:
        errors["product_ids"] = "must be empty unless scope is selected"
    return errors
