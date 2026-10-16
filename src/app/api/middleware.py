import re
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.ip_hash_keyring import maybe_refresh_ip_hash_key

REQUEST_ID_HEADER = "X-Request-ID"

# What a caller-supplied id may look like. Anything else - too long, spaces,
# control characters - is replaced rather than echoed into the response header
# and every log line of the request (BUG-13).
_ACCEPTABLE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a stable request ID to every request, echoes it back as a response
    header, and binds it into the structlog context for the request's lifetime."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied = request.headers.get(REQUEST_ID_HEADER)
        if supplied is not None and _ACCEPTABLE_REQUEST_ID.fullmatch(supplied):
            request_id = supplied
        else:
            request_id = f"req_{uuid.uuid4().hex}"
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class IpHashKeyRefreshMiddleware:
    """Refreshes the IP-hash key before the handler when it is stale or missing (VS-046).
    Inside RequestID, so a refresh warning carries the request's id."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            factory = getattr(scope["app"].state, "db_session_factory", None)
            if factory is not None:
                await maybe_refresh_ip_hash_key(factory)
        await self.app(scope, receive, send)
