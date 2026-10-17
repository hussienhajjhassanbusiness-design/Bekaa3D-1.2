"""VS-005: the OpenAPI security scheme for the cookie-authenticated API.

Required by the VS-005 deliverable list ("Admin enrollment/recovery runbook and
OpenAPI security scheme", vertical-slice-plan.md:128). Without it the generated
schema shows every route as though it were public, which is misleading in the
one place a client integrator is most likely to look.

Deliberately implemented as a post-processing pass over the generated schema
rather than as FastAPI security dependencies on the routes themselves. Adding
`APIKeyCookie(...)` to `current_claims` or `require_csrf` would put a second
credential-reading mechanism next to the one those functions already implement,
in shared VS-003 code, for a documentation-only benefit. This changes no route's
runtime behaviour at all - it only describes what the routes already do."""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.identity.api.dependencies import CSRF_HEADER

_SECURITY_SCHEMES: dict[str, Any] = {
    "sessionCookie": {
        "type": "apiKey",
        "in": "cookie",
        "name": ACCESS_COOKIE,
        "description": (
            "Short-lived signed access token, set httpOnly by "
            "`POST /auth/login` or `POST /auth/mfa/verify` (ADR-006). The "
            f"browser sends it automatically; `{REFRESH_COOKIE}` rotates it "
            "through `POST /auth/refresh`."
        ),
    },
    "csrfToken": {
        "type": "apiKey",
        "in": "header",
        "name": CSRF_HEADER,
        "description": (
            f"Double-submit CSRF defence (SEC-03). Copy the readable "
            f"`{CSRF_COOKIE}` cookie into this header on every "
            "cookie-authenticated unsafe method."
        ),
    },
}

# Routes that authenticate by something other than a session cookie, and so
# must not be described as requiring one.
_UNAUTHENTICATED_PATHS = frozenset(
    {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/verify-email",
        "/api/v1/auth/resend-verification",
        # Authenticated by the single-use login challenge in its body, before
        # any session exists (api-endpoints.md:270).
        "/api/v1/auth/mfa/verify",
        # Authenticated by the single-use reset token, or not at all.
        "/api/v1/auth/password-reset/request",
        "/api/v1/auth/password-reset/confirm",
        # Public reads. Listed since BUG-42: they were described as needing a
        # session cookie, and would now also be documented as answering 401.
        "/api/v1/settings/public",
        "/api/v1/categories",
        "/api/v1/materials",
        "/api/v1/colours",
        # The storefront (VS-015, VS-016): anonymous visitors browse and search.
        "/api/v1/products",
        "/api/v1/products/{slug}",
        "/api/v1/search/suggestions",
        # VS-023: a provider calls it; the HMAC signature is the authentication.
        "/api/v1/webhooks/payments/{provider}",
        "/health/live",
        "/health/ready",
    }
)

_ADMIN_PREFIX = "/api/v1/admin"

# The RFC 9457 problem document every error response carries (app.api.errors).
_PROBLEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["type", "title", "status", "detail", "instance", "code", "request_id", "errors"],
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "detail": {"type": "string"},
        "instance": {"type": "string"},
        "code": {
            "type": "string",
            "description": "Stable error code (api-endpoints.md section 5).",
        },
        "request_id": {"type": "string"},
        "errors": {"type": "array", "items": {"type": "object"}},
    },
}
_PROBLEM_CONTENT = {
    "application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}
}


def _error_statuses(
    path: str, operation: dict[str, Any], requirements: list[dict[str, list[str]]] | None
) -> dict[str, str]:
    """The error statuses an operation can answer with whatever its route does,
    each with a description (BUG-42: most were missing, so generated clients
    could not see them). Route-specific ones - 409, 410, 429 - are declared on
    the routes themselves."""
    statuses = {
        "422": "VALIDATION_ERROR: a field, or a control character in the path or query.",
        "500": "INTERNAL_ERROR: unexpected fault; details are logged, never returned.",
        "503": "SERVICE_UNAVAILABLE: the database or Redis is unreachable; retry later.",
    }
    if "requestBody" in operation:
        statuses["400"] = "MALFORMED_REQUEST: the body is not valid JSON."
    if requirements is not None:
        statuses["401"] = "AUTH_REQUIRED: no valid session."
        if any("csrfToken" in requirement for requirement in requirements):
            statuses["403"] = "CSRF_INVALID, or a role/verification requirement unmet."
    if path.startswith(_ADMIN_PREFIX):
        statuses["401"] = "AUTH_REQUIRED, or MFA_REQUIRED for an administrator."
        statuses["404"] = "Not an administrator (SEC-10), or no such resource."
    return statuses


_SAFE_METHODS = frozenset({"get", "head", "options"})


def _requirements(path: str, method: str) -> list[dict[str, list[str]]] | None:
    """What a caller must present for one operation, or None if it is public.

    CSRF is required only for cookie-authenticated unsafe methods, which is
    exactly the rule `require_csrf` enforces - a `GET` never carries the header,
    so claiming it does would send integrators chasing a token they don't need."""
    if path in _UNAUTHENTICATED_PATHS:
        return None
    if method in _SAFE_METHODS:
        return [{"sessionCookie": []}]
    return [{"sessionCookie": [], "csrfToken": []}]


def custom_openapi(app: FastAPI) -> dict[str, Any]:
    """Generate the schema once, annotate it, and cache it on the app.

    Caching is FastAPI's own convention (`app.openapi_schema`): the schema is
    deterministic and rebuilding it per request is pure waste."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=(
            "Bekaa3D API. Authentication is cookie-based (ADR-006): short-lived "
            "access tokens and rotating refresh tokens in httpOnly cookies, with "
            "double-submit CSRF on unsafe methods.\n\n"
            "Administrator routes under `/api/v1/admin` additionally require a "
            "completed second factor (SEC-04). An administrator with MFA enabled "
            "receives `202 MfaChallengeRead` from `POST /auth/login` instead of a "
            "session, and completes login at `POST /auth/mfa/verify`. A route "
            "under `/api/v1/admin` answers `404` rather than `403` to an "
            "authenticated non-administrator (SEC-10), so its absence from a "
            "caller's view is not evidence that it does not exist."
        ),
        routes=app.routes,
    )

    components = schema.setdefault("components", {})
    components["securitySchemes"] = _SECURITY_SCHEMES
    components.setdefault("schemas", {})["Problem"] = _PROBLEM_SCHEMA

    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if not isinstance(operation, dict):
                continue
            requirements = _requirements(path, method.lower())
            if requirements is not None:
                operation["security"] = requirements
            responses = operation.setdefault("responses", {})
            for code, description in _error_statuses(path, operation, requirements).items():
                # A route's own, more specific description wins.
                responses.setdefault(code, {"description": description})
            for code, response in responses.items():
                if code[0] in "45":
                    response["content"] = _PROBLEM_CONTENT

    app.openapi_schema = schema
    return schema
