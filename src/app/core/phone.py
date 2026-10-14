"""Lebanese phone numbers, normalised to E.164 (BR-078). Pure, so any domain may use it:
the address book (VS-026) and the pickup contact phone (VS-028) must agree on one form."""

import re

COUNTRY_CODE = "961"
E164_PATTERN = re.compile(r"\+961[0-9]{7,8}")
INPUT_MAX = 32

_ALLOWED = re.compile(r"\+?[0-9 ().\-]+")
# 7 digits: a one-digit area code (landlines, 03); 8 digits: the 7x and 8x mobile ranges.
_NATIONAL = re.compile(r"[13-9][0-9]{6}|[78][0-9]{7}")


class InvalidPhoneNumberError(ValueError):
    """Never carries the number itself, which is personal data."""

    def __init__(self) -> None:
        super().__init__("must be a Lebanese phone number, e.g. +961 3 123 456 or 71 123 456")


def normalise_lebanese_phone(raw: object) -> str:
    """`+961 3 123 456`, `03123456`, `9613123456`, `00961…` all give `+9613123456`."""
    if not isinstance(raw, str):
        raise InvalidPhoneNumberError()
    text = raw.strip()
    if len(text) > INPUT_MAX or _ALLOWED.fullmatch(text) is None:
        raise InvalidPhoneNumberError()
    digits = re.sub(r"[^0-9]", "", text)
    national = _national_number(digits, international=text.startswith("+"))
    if national is None or _NATIONAL.fullmatch(national) is None:
        raise InvalidPhoneNumberError()
    return f"+{COUNTRY_CODE}{national}"


def _national_number(digits: str, *, international: bool) -> str | None:
    if international:
        return _strip_trunk(digits[3:]) if digits.startswith(COUNTRY_CODE) else None
    if digits.startswith("00"):
        return _strip_trunk(digits[5:]) if digits[2:5] == COUNTRY_CODE else None
    # A bare 961 prefix only when what follows is national-length; 9612345 is a 09 landline.
    if digits.startswith(COUNTRY_CODE) and len(digits) - 3 in (7, 8, 9):
        return _strip_trunk(digits[3:])
    return _strip_trunk(digits)


def _strip_trunk(national: str) -> str:
    """People write `+961 03 …` as often as `03 …`; the trunk 0 is never part of E.164."""
    return national[1:] if national.startswith("0") else national
