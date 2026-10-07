"""Product list cursors: round-trip per sort, and every tamper is a 422 (VS-015)."""

import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError

from app.catalog.api.product_cursor import decode_cursor, encode_cursor
from app.catalog.domain.storefront import CursorKey

PRODUCT_ID = uuid.uuid4()
KEYS: dict[str, CursorKey] = {
    "price": 1999,
    "-price": 0,
    "-average_rating": Decimal("4.50"),
    "-created_at": datetime(2026, 10, 8, 9, 30, 15, 123456, tzinfo=UTC),
}


def _raw(payload: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.mark.parametrize(("sort", "key"), KEYS.items())
def test_a_cursor_round_trips_under_its_own_sort(sort: str, key: CursorKey) -> None:
    decoded = decode_cursor(encode_cursor(sort, key, PRODUCT_ID), sort)
    assert decoded == (key, PRODUCT_ID)
    assert type(decoded[0]) is type(key)


def test_no_cursor_is_the_first_page() -> None:
    assert decode_cursor(None, "price") is None


@pytest.mark.parametrize(("sort", "key"), KEYS.items())
def test_a_cursor_from_another_sort_is_refused(sort: str, key: CursorKey) -> None:
    cursor = encode_cursor(sort, key, PRODUCT_ID)
    for other in KEYS.keys() - {sort}:
        with pytest.raises(RequestValidationError):
            decode_cursor(cursor, other)


@pytest.mark.parametrize(
    ("sort", "key"),
    [
        ("price", "1999"),
        ("price", 19.99),
        ("price", True),
        ("-average_rating", 4.5),
        ("-average_rating", "NaN"),
        ("-average_rating", "Infinity"),
        ("-average_rating", "four"),
        ("-created_at", "2026-10-08T09:30:15"),
        ("-created_at", 12345),
    ],
)
def test_a_key_of_the_wrong_kind_is_refused(sort: str, key: Any) -> None:
    with pytest.raises(RequestValidationError):
        decode_cursor(_raw({"s": sort, "k": key, "i": str(PRODUCT_ID)}), sort)


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-cursor",
        _raw(["price", 1, str(PRODUCT_ID)]),
        _raw({"s": "price", "k": 1}),
        _raw({"s": "price", "k": 1, "i": "not-a-uuid"}),
        "%%%",
    ],
)
def test_a_malformed_cursor_is_refused(raw: str) -> None:
    with pytest.raises(RequestValidationError) as caught:
        decode_cursor(raw, "price")
    assert caught.value.errors()[0]["loc"] == ("query", "cursor")
