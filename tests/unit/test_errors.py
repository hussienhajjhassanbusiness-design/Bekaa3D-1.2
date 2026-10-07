import json

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from app.api.errors import unhandled_exception_handler, validation_exception_handler


def _make_request(path: str = "/test") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)
    request.state.request_id = "req_test"
    return request


@pytest.mark.asyncio
async def test_validation_error_maps_to_422_problem_shape() -> None:
    exc = RequestValidationError(
        errors=[{"loc": ("body", "name"), "msg": "field required", "type": "missing"}]
    )

    response = await validation_exception_handler(_make_request(), exc)

    assert response.status_code == 422
    body = json.loads(bytes(response.body))
    assert body["code"] == "VALIDATION_ERROR"
    assert body["request_id"] == "req_test"
    assert body["errors"] == [{"loc": ["body", "name"], "msg": "field required", "type": "missing"}]


@pytest.mark.asyncio
async def test_json_decode_error_maps_to_400_malformed_request() -> None:
    """The negative control for the test above: pydantic reports an unparseable
    body through the same RequestValidationError, but api-endpoints.md 5.1 gives
    it a different status and code. The two must not collapse into one."""
    exc = RequestValidationError(
        errors=[{"loc": ("body", 1), "msg": "JSON decode error", "type": "json_invalid"}]
    )

    response = await validation_exception_handler(_make_request(), exc)

    assert response.status_code == 400
    body = json.loads(bytes(response.body))
    assert body["code"] == "MALFORMED_REQUEST"
    assert body["status"] == 400


@pytest.mark.asyncio
async def test_unhandled_exception_maps_to_500_without_leaking_internals() -> None:
    exc = RuntimeError("db password is hunter2")

    response = await unhandled_exception_handler(_make_request(), exc)

    assert response.status_code == 500
    body = json.loads(bytes(response.body))
    assert body["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in body["detail"]
    assert body["request_id"] == "req_test"
