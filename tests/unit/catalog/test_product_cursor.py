"""Product list cursors: round-trip per sort and search mode; every tamper is a 422."""

import base64
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError

from app.catalog.api.product_cursor import decode_cursor, decode_search_cursor, encode_cursor
from app.catalog.domain.storefront import CursorKey, SearchMode

PRODUCT_ID = uuid.uuid4()
KEYS: dict[str, CursorKey] = {
    "price": 1999,
    "-price": 0,
    "-average_rating": Decimal("4.50"),
    "-created_at": datetime(2026, 10, 8, 9, 30, 15, 123456, tzinfo=UTC),
    # A float4 ts_rank widened to a double: the round trip must be exact.
    "-relevance": 1.0607927083969116,
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
        ("-average_rating", "10"),
        ("-average_rating", "-0.01"),
        ("-average_rating", "4.255"),
        ("price", -1),
        ("price", 9_223_372_036_854_775_808),
        ("-created_at", "2026-10-08T09:30:15"),
        ("-created_at", 12345),
        ("-relevance", 1),
        ("-relevance", "1.5"),
        ("-relevance", -0.5),
        ("-relevance", float("nan")),
        ("-relevance", float("inf")),
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


@pytest.mark.parametrize("mode", list(SearchMode))
@pytest.mark.parametrize(("sort", "key"), KEYS.items())
def test_a_search_cursor_round_trips_with_its_mode(
    sort: str, key: CursorKey, mode: SearchMode
) -> None:
    decoded = decode_search_cursor(encode_cursor(sort, key, PRODUCT_ID, mode), sort)
    assert decoded == ((key, PRODUCT_ID), mode)


def test_a_search_cursor_is_refused_without_a_search_and_vice_versa() -> None:
    searching = encode_cursor("price", 1, PRODUCT_ID, SearchMode.FUZZY)
    browsing = encode_cursor("price", 1, PRODUCT_ID)
    with pytest.raises(RequestValidationError):
        decode_cursor(searching, "price")
    with pytest.raises(RequestValidationError):
        decode_search_cursor(browsing, "price")


@pytest.mark.parametrize("mode", ["exact", None, 1, ["fuzzy"]])
def test_an_unknown_search_mode_is_refused(mode: Any) -> None:
    raw = _raw({"s": "price", "k": 1, "i": str(PRODUCT_ID), "m": mode})
    with pytest.raises(RequestValidationError):
        decode_search_cursor(raw, "price")
