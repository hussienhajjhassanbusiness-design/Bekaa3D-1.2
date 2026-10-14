import pytest

from app.identity.domain.address import (
    LABEL_MAX,
    LANDMARK_NOTES_MAX,
    MAX_LIVE_ADDRESSES,
    STREET_MAX,
    AddressDetails,
    becomes_default,
    check_capacity,
)
from app.identity.domain.enums import Governorate
from app.identity.domain.exceptions import AddressLimitReachedError, InvalidAddressError

VALID = {
    "label": "Home",
    "recipient_name": "Rima Haddad",
    "phone": "03 123 456",
    "governorate": "beqaa",
    "city": "Zahle",
    "area": "Hoch el Oumara",
    "street": "Main street",
    "landmark_notes": "Blue gate opposite the bakery",
}


def test_trims_normalises_and_blanks_optionals() -> None:
    details = AddressDetails.of(**{**VALID, "label": " Home ", "area": "  ", "street": None})
    assert details.label == "Home"
    assert details.phone == "+9613123456"
    assert details.governorate is Governorate.BEQAA
    assert (details.area, details.street) == (None, None)


def test_landmark_notes_may_span_lines() -> None:
    details = AddressDetails.of(**{**VALID, "landmark_notes": "Blue gate\nthird floor"})
    assert details.landmark_notes == "Blue gate\nthird floor"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("label", "   "),
        ("label", "x" * (LABEL_MAX + 1)),
        ("label", "Home\nWork"),
        ("recipient_name", ""),
        ("city", None),
        # Required by SRS 14.4 (VS-026 Q1), unlike database-design.md's nullable column.
        ("landmark_notes", "   "),
        ("landmark_notes", None),
        ("landmark_notes", "x" * (LANDMARK_NOTES_MAX + 1)),
        ("landmark_notes", "gate\x00"),
        ("street", "x" * (STREET_MAX + 1)),
        ("area", "Ham\tra"),
        ("phone", "+33 6 12 34 56 78"),
        ("phone", "not a phone"),
        ("governorate", "paris"),
        ("governorate", "Beqaa"),
    ],
)
def test_refuses_invalid_field(field: str, value: object) -> None:
    with pytest.raises(InvalidAddressError) as caught:
        AddressDetails.of(**{**VALID, field: value})
    assert caught.value.fields == [field]


def test_reports_every_bad_field_without_values() -> None:
    with pytest.raises(InvalidAddressError) as caught:
        AddressDetails.of(**{**VALID, "phone": "+33 612345678", "city": "", "governorate": "x"})
    assert caught.value.fields == ["city", "governorate", "phone"]
    assert "612345678" not in str(caught.value)


def test_changed_revalidates_the_whole() -> None:
    details = AddressDetails.of(**VALID)
    updated = details.changed(phone="71 123 456", street=None)
    assert (updated.phone, updated.street, updated.city) == ("+96171123456", None, "Zahle")
    with pytest.raises(InvalidAddressError):
        details.changed(landmark_notes=" ")


def test_capacity_allows_up_to_the_cap() -> None:
    check_capacity(MAX_LIVE_ADDRESSES - 1)
    with pytest.raises(AddressLimitReachedError):
        check_capacity(MAX_LIVE_ADDRESSES)


@pytest.mark.parametrize(
    ("requested", "live_count", "expected"),
    [(False, 0, True), (True, 0, True), (False, 1, False), (True, 1, True), (False, 5, False)],
)
def test_first_live_address_is_default(requested: bool, live_count: int, expected: bool) -> None:
    assert becomes_default(requested=requested, live_count=live_count) is expected
