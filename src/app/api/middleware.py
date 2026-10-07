import re
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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
