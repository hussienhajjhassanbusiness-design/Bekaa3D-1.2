"""Product type integrity, merge-then-validate updates and soft delete (VS-013)."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.catalog.domain.enums import AcceptedPaymentMethods, ProductType, PurchaseMode
from app.catalog.domain.exceptions import ArchivedValueNotMutableError, ProductValidationError
from app.catalog.domain.product import (
    PHYSICAL_ONLY_FIELDS,
    PHYSICAL_REQUIRED_FIELDS,
    Dimensions,
    Product,
    ProductAttributes,
    ProductDraft,
    with_create_defaults,
)

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)

STL = ProductAttributes(category_id=uuid.uuid4(), name="Dragon", slug="dragon", price_cents=500)
PHYSICAL = replace(
    STL,
    purchase_mode=PurchaseMode.ONLINE_ONLY,
    accepted_payment_methods=AcceptedPaymentMethods.ONLINE_OR_CASH,
    production_lead_time_days=3,
    batch_size=4,
    max_quantity_per_line=10,
)
# A value each physical-only field may legally hold, so the STL test sets one at a time.
PHYSICAL_VALUES: dict[str, Any] = {
    "purchase_mode": PurchaseMode.BOTH,
    "accepted_payment_methods": AcceptedPaymentMethods.CASH,
    "material_id": uuid.uuid4(),
    "colour_id": uuid.uuid4(),
    "dimensions": Dimensions(10, 20, 30),
    "production_lead_time_days": 2,
    "batch_size": 1,
    "max_quantity_per_line": 1,
    "weight_grams": 100,
}


def _with(attrs: ProductAttributes, name: str, value: Any) -> ProductAttributes:
    changes: dict[str, Any] = {name: value}
    return replace(attrs, **changes)


def _product(product_type: ProductType, attrs: ProductAttributes, **kw: Any) -> Product:
    return Product(
        id=uuid.uuid4(),
        type=product_type,
        attributes=attrs,
        version=1,
        created_at=NOW,
        updated_at=NOW,
        **kw,
    )


def test_valid_drafts_of_both_types_build() -> None:
    ProductDraft(ProductType.STL, STL)
    ProductDraft(ProductType.PHYSICAL, PHYSICAL)


def test_physical_only_fields_cover_every_required_one() -> None:
    assert set(PHYSICAL_REQUIRED_FIELDS) <= set(PHYSICAL_ONLY_FIELDS)
    assert set(PHYSICAL_VALUES) == set(PHYSICAL_ONLY_FIELDS)


@pytest.mark.parametrize("name", PHYSICAL_ONLY_FIELDS)
def test_an_stl_product_refuses_each_physical_only_field(name: str) -> None:
    with pytest.raises(ProductValidationError) as raised:
        ProductDraft(ProductType.STL, _with(STL, name, PHYSICAL_VALUES[name]))
    assert raised.value.errors == {name: "is not allowed on an STL product"}


@pytest.mark.parametrize("name", PHYSICAL_REQUIRED_FIELDS)
def test_a_physical_product_requires_each_production_field(name: str) -> None:
    with pytest.raises(ProductValidationError) as raised:
        ProductDraft(ProductType.PHYSICAL, _with(PHYSICAL, name, None))
    assert raised.value.errors == {name: "is required on a physical product"}


def test_material_and_colour_stay_optional_on_a_physical_product() -> None:
    ProductDraft(ProductType.PHYSICAL, replace(PHYSICAL, material_id=None, colour_id=None))


@pytest.mark.parametrize(
    ("name", "bad", "edge"),
    [
        ("production_lead_time_days", -1, 0),
        ("batch_size", 0, 1),
        ("max_quantity_per_line", 0, 1),
        ("weight_grams", 0, 1),
    ],
)
def test_physical_bounds_hold_at_the_edge(name: str, bad: int, edge: int) -> None:
    ProductDraft(ProductType.PHYSICAL, _with(PHYSICAL, name, edge))
    with pytest.raises(ProductValidationError) as raised:
        ProductDraft(ProductType.PHYSICAL, _with(PHYSICAL, name, bad))
    assert set(raised.value.errors) == {name}


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"name": "   "}, "name"),
        ({"price_cents": -1}, "price"),
        ({"currency": "EUR"}, "price"),
    ],
)
def test_common_rules_apply_to_both_types(changes: dict[str, Any], field: str) -> None:
    for product_type, attrs in ((ProductType.STL, STL), (ProductType.PHYSICAL, PHYSICAL)):
        with pytest.raises(ProductValidationError) as raised:
            ProductDraft(product_type, replace(attrs, **changes))
        assert field in raised.value.errors


@pytest.mark.parametrize("bad", [0, -5, 1.5, True])
def test_dimensions_must_be_positive_integers(bad: Any) -> None:
    with pytest.raises(ProductValidationError):
        Dimensions(bad, 1, 1)


def test_an_update_is_validated_against_the_merged_state() -> None:
    product = _product(ProductType.STL, STL)
    with pytest.raises(ProductValidationError):
        product.apply_update({"production_lead_time_days": 3}, LATER)
    assert product.attributes == STL
    assert product.updated_at == NOW


def test_a_physical_update_cannot_clear_a_required_field() -> None:
    product = _product(ProductType.PHYSICAL, PHYSICAL)
    with pytest.raises(ProductValidationError):
        product.apply_update({"batch_size": None}, LATER)
    assert product.attributes == PHYSICAL


def test_a_real_change_moves_updated_at() -> None:
    product = _product(ProductType.PHYSICAL, PHYSICAL)
    assert product.apply_update({"purchase_mode": PurchaseMode.WHATSAPP_ONLY}, LATER) is True
    assert product.attributes.purchase_mode is PurchaseMode.WHATSAPP_ONLY
    assert product.updated_at == LATER


def test_an_update_to_the_stored_values_changes_nothing() -> None:
    product = _product(ProductType.STL, STL)
    assert product.apply_update({"name": STL.name, "is_visible": False}, LATER) is False
    assert product.updated_at == NOW


def test_type_and_aggregates_are_not_editable() -> None:
    product = _product(ProductType.STL, STL)
    for name in ("type", "average_rating", "review_count", "wishlist_count", "version"):
        with pytest.raises(ValueError, match="not editable"):
            product.apply_update({name: 1}, LATER)


def test_delete_stamps_once_and_leaves_visibility_alone() -> None:
    """Visibility, availability and deletion stay separate (entities doc, Product)."""
    product = _product(ProductType.STL, replace(STL, is_visible=True))
    product.delete(LATER)
    assert product.deleted_at == LATER
    assert product.attributes.is_visible is True
    with pytest.raises(ArchivedValueNotMutableError):
        product.delete(LATER)
    with pytest.raises(ArchivedValueNotMutableError):
        product.apply_update({"name": "Other"}, LATER)


def test_the_audit_snapshot_is_json_ready_and_omits_aggregates() -> None:
    attrs = replace(PHYSICAL, dimensions=Dimensions(1, 2, 3))
    snapshot = _product(ProductType.PHYSICAL, attrs, review_count=4).audit_snapshot()
    assert snapshot["type"] == "physical"
    assert snapshot["purchase_mode"] == "online_only"
    assert snapshot["category_id"] == str(PHYSICAL.category_id)
    assert snapshot["dimensions"] == {"length_mm": 1, "width_mm": 2, "height_mm": 3}
    assert snapshot["version"] == 1
    assert not {"average_rating", "review_count", "wishlist_count"} & set(snapshot)


def test_a_physical_product_created_without_accepted_methods_accepts_both() -> None:
    bare = replace(PHYSICAL, accepted_payment_methods=None)
    filled = with_create_defaults(ProductType.PHYSICAL, bare)
    assert filled == replace(
        PHYSICAL, accepted_payment_methods=AcceptedPaymentMethods.ONLINE_OR_CASH
    )
    ProductDraft(ProductType.PHYSICAL, filled)


@pytest.mark.parametrize("given", list(AcceptedPaymentMethods))
def test_create_defaults_keep_a_given_value(given: AcceptedPaymentMethods) -> None:
    attrs = replace(PHYSICAL, accepted_payment_methods=given)
    assert with_create_defaults(ProductType.PHYSICAL, attrs) == attrs


def test_create_defaults_leave_an_stl_product_without_accepted_methods() -> None:
    assert with_create_defaults(ProductType.STL, STL) == STL


def test_an_audit_snapshot_records_accepted_methods_as_text() -> None:
    product = _product(ProductType.PHYSICAL, PHYSICAL)
    assert product.audit_snapshot()["accepted_payment_methods"] == "online_or_cash"
