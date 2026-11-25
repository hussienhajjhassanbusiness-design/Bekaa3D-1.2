"""Seasonal promotions: the discount, the window, the scope, no stacking, and validation."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.catalog.domain.enums import ProductType
from app.catalog.domain.promotions import (
    AppliedPromotion,
    DiscountType,
    Promotion,
    PromotionFields,
    PromotionScope,
    PromotionStatus,
    apply_best,
    discounted_cents,
    normalized,
    validate_promotion,
)

NOW = datetime(2026, 12, 1, 12, tzinfo=UTC)
PRODUCT = uuid.UUID("00000000-0000-4000-8000-000000000001")
OTHER = uuid.UUID("00000000-0000-4000-8000-000000000002")


def fields(**over: object) -> PromotionFields:
    base = PromotionFields(
        name="Eid Sale",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=20,
        scope=PromotionScope.ALL,
        product_ids=frozenset(),
        starts_at=NOW - timedelta(days=1),
        ends_at=NOW + timedelta(days=1),
        active=True,
    )
    return replace(base, **over)  # type: ignore[arg-type]


def promotion(**over: object) -> Promotion:
    return Promotion(id=uuid.uuid4(), fields=fields(**over), created_at=NOW, updated_at=NOW)


def best(
    promotions: list[Promotion], *, price: int = 2500, kind: ProductType = ProductType.STL
) -> AppliedPromotion | None:
    return apply_best(
        product_id=PRODUCT,
        product_type=kind,
        list_price_cents=price,
        promotions=promotions,
        now=NOW,
    )


class TestDiscount:
    def test_percentage(self) -> None:
        assert discounted_cents(2500, DiscountType.PERCENTAGE, 20) == 2000

    def test_percentage_rounds_the_discount_half_up_to_a_cent(self) -> None:
        # 15% of 999 = 149.85 -> 150 off.
        assert discounted_cents(999, DiscountType.PERCENTAGE, 15) == 849

    def test_fixed(self) -> None:
        assert discounted_cents(2500, DiscountType.FIXED, 500) == 2000

    def test_never_negative(self) -> None:
        assert discounted_cents(300, DiscountType.FIXED, 500) == 0
        assert discounted_cents(300, DiscountType.PERCENTAGE, 100) == 0


class TestStatus:
    @pytest.mark.parametrize(
        ("over", "expected"),
        [
            ({}, PromotionStatus.ACTIVE),
            ({"active": False}, PromotionStatus.INACTIVE),
            ({"starts_at": NOW + timedelta(hours=1)}, PromotionStatus.SCHEDULED),
            ({"ends_at": NOW}, PromotionStatus.ENDED),  # `ends_at` is exclusive
            ({"starts_at": NOW}, PromotionStatus.ACTIVE),  # `starts_at` is inclusive
        ],
    )
    def test_status(self, over: dict[str, object], expected: PromotionStatus) -> None:
        assert promotion(**over).status(NOW) is expected

    def test_inactive_wins_over_the_window(self) -> None:
        assert promotion(active=False, ends_at=NOW).status(NOW) is PromotionStatus.INACTIVE


class TestApply:
    def test_active_promotion_lowers_the_price(self) -> None:
        applied = best([promotion()])
        assert applied is not None
        assert (applied.list_price_cents, applied.price_cents) == (2500, 2000)

    @pytest.mark.parametrize(
        "over",
        [
            {"active": False},
            {"starts_at": NOW + timedelta(minutes=1)},
            {"ends_at": NOW - timedelta(minutes=1), "starts_at": NOW - timedelta(days=2)},
        ],
        ids=["inactive", "future", "expired"],
    )
    def test_promotion_outside_its_window_or_off_does_not_apply(
        self, over: dict[str, object]
    ) -> None:
        assert best([promotion(**over)]) is None

    def test_physical_and_stl_scopes(self) -> None:
        physical_only = promotion(scope=PromotionScope.PHYSICAL)
        stl_only = promotion(scope=PromotionScope.STL)
        assert best([physical_only], kind=ProductType.STL) is None
        assert best([physical_only], kind=ProductType.PHYSICAL) is not None
        assert best([stl_only], kind=ProductType.PHYSICAL) is None
        assert best([stl_only], kind=ProductType.STL) is not None

    def test_selected_scope(self) -> None:
        assert (
            best([promotion(scope=PromotionScope.SELECTED, product_ids=frozenset({OTHER}))]) is None
        )
        assert (
            best([promotion(scope=PromotionScope.SELECTED, product_ids=frozenset({PRODUCT}))])
            is not None
        )

    def test_no_stacking_the_lowest_price_wins_alone(self) -> None:
        ten, five_dollars = (
            promotion(discount_value=10),
            promotion(discount_type=DiscountType.FIXED, discount_value=500),
        )
        applied = best([ten, five_dollars])
        assert applied is not None
        # $25 - $5 = $20 beats $25 - 10% = $22.50; never $25 - 10% - $5.
        assert applied.price_cents == 2000
        assert applied.promotion is five_dollars

    def test_tie_goes_to_the_one_ending_first(self) -> None:
        later = promotion(ends_at=NOW + timedelta(days=5))
        sooner = promotion(ends_at=NOW + timedelta(days=2))
        applied = best([later, sooner])
        assert applied is not None and applied.promotion is sooner

    def test_a_discount_that_changes_nothing_does_not_apply(self) -> None:
        assert best([promotion(discount_value=1)], price=10) is None  # 1% of 10c rounds to 0
        assert best([promotion()], price=0) is None


class TestValidation:
    def errors(self, **over: object) -> dict[str, str]:
        return validate_promotion(normalized(fields(**over)))

    def test_valid(self) -> None:
        assert self.errors() == {}

    @pytest.mark.parametrize("value", [0, 101, -5])
    def test_percentage_must_be_1_to_100(self, value: int) -> None:
        assert "discount_value" in self.errors(discount_value=value)

    def test_percentage_of_100_is_allowed(self) -> None:
        assert self.errors(discount_value=100) == {}

    def test_fixed_must_be_positive(self) -> None:
        assert "discount_value" in self.errors(discount_type=DiscountType.FIXED, discount_value=0)
        assert self.errors(discount_type=DiscountType.FIXED, discount_value=150) == {}

    def test_window_must_be_ordered(self) -> None:
        assert "ends_at" in self.errors(ends_at=NOW - timedelta(days=1))
        assert "ends_at" in self.errors(starts_at=NOW, ends_at=NOW)

    def test_window_needs_an_offset(self) -> None:
        assert "starts_at" in self.errors(starts_at=datetime(2026, 12, 1))

    def test_selected_needs_products_and_others_take_none(self) -> None:
        assert "product_ids" in self.errors(scope=PromotionScope.SELECTED)
        assert "product_ids" in self.errors(product_ids=frozenset({PRODUCT}))

    def test_text_rules(self) -> None:
        assert "name" in self.errors(name="   ")
        assert "badge_text" in self.errors(badge_text="x" * 25)
        assert "name" in self.errors(name="Eid\x00Sale")

    def test_normalized_trims_and_drops_an_empty_badge(self) -> None:
        clean = normalized(fields(name="  Eid Sale ", badge_text="   "))
        assert (clean.name, clean.badge_text) == ("Eid Sale", None)
