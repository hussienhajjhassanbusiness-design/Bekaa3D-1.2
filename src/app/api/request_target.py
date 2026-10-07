"""Refuse control characters in the request target - path and query (BUG-03).

A NUL in `?search=`, `?prefix=` or a path segment used to travel all the way
to asyncpg, which cannot send it to PostgreSQL, and the request answered 500.
Checked once here, before routing, so no route, dependency or future query
parameter can forget to: such a request is a 422 VALIDATION_ERROR naming the
offending parameter, identically for real and imaginary paths.

Request bodies are validated field by field instead (see `app.api.text`),
because some fields - a setting's value - answer with their own error code.
"""

from typing import Any
from urllib.parse import parse_qsl

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import problem_response
from app.core.text import CONTROL_CHARACTER_MESSAGE, has_control_characters


def _offending(scope: Scope) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if has_control_characters(scope["path"]):
        errors.append({"loc": ["path"], "msg": CONTROL_CHARACTER_MESSAGE, "type": "value_error"})
    # Decoded exactly as Starlette decodes it for the routes (latin-1 bytes,
    # then percent-decoding), so `%00` is seen as the NUL it becomes.
    query = scope.get("query_string", b"").decode("latin-1")
    for name, value in parse_qsl(query, keep_blank_values=True):
        if has_control_characters(name) or has_control_characters(value):
            errors.append(
                {"loc": ["query", name], "msg": CONTROL_CHARACTER_MESSAGE, "type": "value_error"}
            )
    return errors


class RequestTargetMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            errors = _offending(scope)
            if errors:
                response = problem_response(
                    Request(scope),
                    status_code=422,
                    code="VALIDATION_ERROR",
                    title="Request failed validation",
                    detail="The request path or query contains control characters.",
                    errors=errors,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
