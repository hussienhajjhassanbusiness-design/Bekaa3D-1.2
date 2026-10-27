"""VS-037 plan 6.5: moving the review cursor to a shared module kept its bytes (the public
list's cursor is part of the contract) and its 422 on a tampered value."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.exceptions import RequestValidationError

from app.engagement.api.review_cursor import decode_review_cursor, encode_review_cursor
from app.engagement.domain.reviews import Review

AT = datetime(2026, 10, 27, 9, 30, 15, 123456, tzinfo=UTC)
ID = UUID("0b6f1c2e-3d4a-4b5c-8d6e-7f8091a2b3c4")
GOLDEN = (
    "MjAyNi0xMC0yN1QwOTozMDoxNS4xMjM0NTYrMDA6MDB8MGI2ZjFjMmUtM2Q0YS00YjVjLThkNmUtN2Y4MDkxYTJiM2M0"
)


def _review() -> Review:
    return Review(ID, ID, ID, 3, None, False, False, None, None, AT, AT)


def test_the_cursor_bytes_are_unchanged_and_round_trip() -> None:
    assert encode_review_cursor(_review()) == GOLDEN
    assert decode_review_cursor(GOLDEN) == (AT, ID)
    assert decode_review_cursor(None) is None


@pytest.mark.parametrize("raw", ["not-a-cursor", "MjAyNi0xMC0yN1QwOTozMDoxNXx4"])
def test_a_tampered_cursor_is_a_validation_error(raw: str) -> None:
    with pytest.raises(RequestValidationError):
        decode_review_cursor(raw)
