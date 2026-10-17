"""The idempotency request fingerprint (VS-023 plan 3.7, 6.1)."""

from app.platform.domain.idempotency import request_hash


def test_key_order_and_spacing_do_not_matter() -> None:
    a = request_hash("checkout", {"b": 1, "a": [1, 2], "c": {"y": None, "x": "é"}})
    b = request_hash("checkout", {"c": {"x": "é", "y": None}, "a": [1, 2], "b": 1})
    assert a == b
    assert len(a) == 64 and int(a, 16) >= 0


def test_a_different_body_or_scope_is_a_different_request() -> None:
    body = {"payment_method": "online"}
    assert request_hash("checkout", body) != request_hash("checkout", {"payment_method": "cash"})
    assert request_hash("checkout", body) != request_hash("refund", body)


def test_list_order_matters() -> None:
    assert request_hash("s", {"a": [1, 2]}) != request_hash("s", {"a": [2, 1]})
