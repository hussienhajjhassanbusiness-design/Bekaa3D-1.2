"""Text types for request bodies.

`PlainStr` refuses control characters (BUG-03, see `app.core.text`); every
string field of a request schema uses it, or a type built on it, so a NUL can
never reach PostgreSQL from a body.
"""

from typing import Annotated

from pydantic import AfterValidator, EmailStr

from app.core.text import (
    CONTROL_CHARACTER_MESSAGE,
    has_control_characters,
    reject_control_characters,
)

PlainStr = Annotated[str, AfterValidator(reject_control_characters)]


def _reject_control_except_line_breaks(value: str) -> str:
    if has_control_characters(value, allow_line_breaks=True):
        raise ValueError(CONTROL_CHARACTER_MESSAGE)
    return value


# Free text that may span lines, such as a contact message body.
MultilineStr = Annotated[str, AfterValidator(_reject_control_except_line_breaks)]

# RFC 5321 4.5.3.1.1. email-validator 2.3 stopped enforcing it, so addresses no
# compliant mail server can deliver to were registered (BUG-21).
MAX_LOCAL_PART_OCTETS = 64


def _local_part_fits(value: str) -> str:
    local_part = value.rpartition("@")[0]
    if len(local_part.encode("utf-8")) > MAX_LOCAL_PART_OCTETS:
        raise ValueError(
            f"the part before '@' must be at most {MAX_LOCAL_PART_OCTETS} octets (RFC 5321)"
        )
    return value


Email = Annotated[
    EmailStr, AfterValidator(reject_control_characters), AfterValidator(_local_part_fits)
]
