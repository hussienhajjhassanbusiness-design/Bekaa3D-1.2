import pytest

from app.core.phone import E164_PATTERN, InvalidPhoneNumberError, normalise_lebanese_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The three spellings VS-028 must match to one hash.
        ("+961 3 123 456", "+9613123456"),
        ("03123456", "+9613123456"),
        ("9613123456", "+9613123456"),
        ("00961 3 123 456", "+9613123456"),
        ("+961 03 123 456", "+9613123456"),
        ("(03) 123-456", "+9613123456"),
        ("03.123.456", "+9613123456"),
        ("  03 123 456  ", "+9613123456"),
        ("71 123 456", "+96171123456"),
        ("+961 71 123 456", "+96171123456"),
        ("96181123456", "+96181123456"),
        ("076 123 456", "+96176123456"),
        ("01 234 567", "+9611234567"),
        ("07 123 456", "+9617123456"),
        # A 09 landline that happens to start 961 is not a country code.
        ("09 612 345", "+9619612345"),
        ("9612345", "+9619612345"),
    ],
)
def test_normalises_to_e164(raw: str, expected: str) -> None:
    assert normalise_lebanese_phone(raw) == expected
    assert E164_PATTERN.fullmatch(expected)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "call me",
        "+33 6 12 34 56 78",
        "0033612345678",
        "+1 202 555 0143",
        "03 123 45",
        "03 123 4567 8",
        "02 123 456",
        "0 123 456",
        "61 123 456",
        "+961 71 123 4567",
        "03+123456",
        "++9613123456",
        "03_123_456",
        "0" * 40,
        "٠٣١٢٣٤٥٦",
    ],
)
def test_refuses_non_lebanese_or_malformed(raw: str) -> None:
    with pytest.raises(InvalidPhoneNumberError):
        normalise_lebanese_phone(raw)


def test_error_never_echoes_the_number() -> None:
    with pytest.raises(InvalidPhoneNumberError) as caught:
        normalise_lebanese_phone("+33 6 12 34 56 78")
    assert "612" not in str(caught.value)


def test_normalising_is_idempotent() -> None:
    once = normalise_lebanese_phone("03 123 456")
    assert normalise_lebanese_phone(once) == once
