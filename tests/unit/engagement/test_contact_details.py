import pytest

from app.engagement.domain.contact_message import (
    MESSAGE_MAX,
    NAME_MAX,
    SUBJECT_MAX,
    ContactDetails,
)
from app.engagement.domain.exceptions import InvalidContactDetailsError

VALID = {
    "name": "Rima",
    "email": "rima@example.com",
    "phone": "+961 3 123 456",
    "subject": "Bulk order",
    "message": "Can you print 40 keychains?",
}


def test_trims_and_blanks_optionals() -> None:
    details = ContactDetails.of(
        **{**VALID, "name": "  Rima ", "phone": "   ", "subject": "", "message": " hi \n"}
    )
    assert (details.name, details.phone, details.subject, details.message) == (
        "Rima",
        None,
        None,
        "hi",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "   "),
        ("name", "x" * (NAME_MAX + 1)),
        ("email", "@example.com"),
        ("email", "no-at-sign"),
        ("phone", "call me"),
        ("phone", "12345"),
        ("phone", "(((--)))"),
        ("phone", "+٠٣١٢٣٤٥٦٧"),
        ("phone", "1" * 33),
        ("subject", "s" * (SUBJECT_MAX + 1)),
        ("message", " \n\t "),
        ("message", "m" * (MESSAGE_MAX + 1)),
    ],
)
def test_refuses_invalid_field(field: str, value: str) -> None:
    with pytest.raises(InvalidContactDetailsError) as caught:
        ContactDetails.of(**{**VALID, field: value})
    assert caught.value.fields == [field]
    assert value.strip() not in str(caught.value) or not value.strip()


@pytest.mark.parametrize("phone", ["+96170123456", "03 123 456", "(01) 234-567", "01.234.567"])
def test_accepts_common_phone_shapes(phone: str) -> None:
    assert ContactDetails.of(**{**VALID, "phone": phone}).phone == phone


def test_limits_are_inclusive() -> None:
    ContactDetails.of(
        **{
            **VALID,
            "name": "n" * NAME_MAX,
            "subject": "s" * SUBJECT_MAX,
            "message": "m" * MESSAGE_MAX,
        }
    )
