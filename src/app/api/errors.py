import socket
from typing import Any

import redis.exceptions
import sqlalchemy.exc
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.api.middleware import REQUEST_ID_HEADER
from app.core.config import get_settings
from app.core.exceptions import ApiError

logger = structlog.get_logger()

PROBLEM_MEDIA_TYPE = "application/problem+json"

_STATUS_CODE_NAMES: dict[int, str] = {
    400: "MALFORMED_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    503: "SERVICE_UNAVAILABLE",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    settings = get_settings()
    request_id = _request_id(request)
    body = {
        **(extensions or {}),
        "type": f"{settings.base_url}/problems/{code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
        "code": code,
        "request_id": request_id,
        "errors": errors or [],
    }
    # The correlation header is set here rather than left to RequestIDMiddleware.
    # Starlette installs ServerErrorMiddleware *outside* the user middleware
    # stack (applications.py build_middleware_stack), so an unhandled exception
    # produces a response that never travels back through RequestIDMiddleware -
    # the body carried request_id but the header was silently lost on exactly
    # the responses a caller most needs to correlate.
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_MEDIA_TYPE,
        headers={**(headers or {}), REQUEST_ID_HEADER: request_id},
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODE_NAMES.get(exc.status_code, "HTTP_ERROR")
    # Starlette attaches semantically required headers to some HTTPExceptions -
    # notably `Allow` on a 405, which RFC 9110 15.5.6 makes mandatory. Converting
    # the exception into a problem document must not drop them.
    return problem_response(
        request,
        status_code=exc.status_code,
        code=code,
        title="Request cannot be completed",
        detail=str(exc.detail),
        headers=dict(exc.headers) if exc.headers else None,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    # A body that is not JSON at all is a different failure from a body whose
    # fields are wrong, and api-endpoints.md 5.1 gives them different codes:
    # 400 MALFORMED_REQUEST for "body cannot be parsed", 422 VALIDATION_ERROR
    # for field-level failures. Pydantic reports both through one exception
    # type, so the split has to be made here. A decode failure yields exactly
    # one error and no field errors - there are no fields to validate yet.
    if any(error["type"] == "json_invalid" for error in errors):
        return problem_response(
            request,
            status_code=400,
            code="MALFORMED_REQUEST",
            title="Request body could not be parsed",
            detail="The request body is not valid JSON.",
            errors=errors,
        )
    return problem_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        title="Request body failed validation",
        detail="One or more fields failed validation.",
        errors=errors,
    )


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return problem_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        headers=exc.headers,
        errors=exc.errors,
        extensions=exc.extensions,
    )


# A dependency the request needs - PostgreSQL or Redis - is down, refusing,
# timing out or out of connections. api-endpoints.md 5.2 answers that with 503
# SERVICE_UNAVAILABLE ("retrying later is safe"), not 500 (BUG-15). asyncpg
# raises OSError subclasses while connecting, which SQLAlchemy passes through
# unwrapped; once connected, failures arrive as OperationalError/InterfaceError.
DEPENDENCY_UNAVAILABLE_ERRORS: tuple[type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    socket.gaierror,
    redis.exceptions.ConnectionError,
    redis.exceptions.TimeoutError,
    sqlalchemy.exc.OperationalError,
    sqlalchemy.exc.InterfaceError,
    sqlalchemy.exc.TimeoutError,
)


async def dependency_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    # The type only: a driver message can carry a host, a user or a query.
    await logger.awarning("dependency_unavailable", path=request.url.path, error=type(exc).__name__)
    return problem_response(
        request,
        status_code=503,
        code="SERVICE_UNAVAILABLE",
        title="Service temporarily unavailable",
        detail="A required service is temporarily unavailable. Retry later.",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    await logger.aexception("unhandled_exception", path=request.url.path)
    return problem_response(
        request,
        status_code=500,
        code="INTERNAL_ERROR",
        title="An unexpected error occurred",
        detail="An unexpected error occurred. It has been logged for investigation.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ApiError, api_error_handler)
    for error_type in DEPENDENCY_UNAVAILABLE_ERRORS:
        app.add_exception_handler(error_type, dependency_unavailable_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
