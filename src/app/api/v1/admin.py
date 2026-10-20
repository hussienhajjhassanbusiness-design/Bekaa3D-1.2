"""The `/api/v1/admin` security boundary.

Every route mounted on this router inherits `require_admin`, so authentication,
the administrator role and a completed second factor are enforced once here
rather than being repeated - and re-derived, occasionally wrongly - on each
admin endpoint.

The boundary must also hold for paths that match no route (SEC-10, VS-011). A
router answers an unrouted method with 405, a missing trailing slash with a 307
and an unknown path with 404 *before* any dependency runs, so each of those would
tell a customer - or an anonymous caller - which admin routes exist. Two hidden
catch-all routes, registered after every real one, close that: any request under
`/api/v1/admin` that no real route fully matches lands on them and runs the same
`require_admin` first. So, for every path, real or imaginary, any method, with or
without a trailing slash:

- no session             -> 401 AUTH_REQUIRED
- authenticated customer -> 404 NOT_FOUND, byte-identical to an imaginary path
- admin without MFA      -> 401 MFA_REQUIRED
- MFA-complete admin     -> 405 + `Allow` (a real path, wrong method) or 404

The catch-alls carry no `require_csrf` on purpose: a 403 for some callers and a
404 for others would be a new oracle. They never read the body.

A path that does not start with exactly `/api/v1/admin` (other case, `//`,
`/admin-x`) is not an admin path and answers the ordinary global 404."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.routing import iter_route_contexts
from starlette.routing import Match, compile_path
from starlette.types import Receive, Scope, Send

from app.catalog.api.product_images import admin_router as product_images_router
from app.catalog.api.product_images import upload_router as product_image_upload_router
from app.catalog.api.products import admin_router as products_router
from app.catalog.api.reference_data import admin_router as catalogue_router
from app.core.rate_limit import enforce_rate_limit
from app.engagement.api.admin_analytics import admin_router as engagement_analytics_router
from app.engagement.api.contact_messages import admin_router as contact_messages_router
from app.engagement.api.custom_request_admin import admin_router as custom_requests_router
from app.identity.api.admin_users import router as admin_users_router
from app.identity.public import (
    AccessTokenClaims,
    AdminBoundaryRoute,
    not_found_error,
    require_admin,
)
from app.negotiation.api.admin_offers import admin_router as offers_router
from app.ordering.api.admin_release import admin_router as order_release_router
from app.payments.api.admin_payments import admin_router as admin_payments_router
from app.platform.api.audit_logs import admin_router as audit_logs_router
from app.platform.api.settings import admin_router as settings_router

# SRS 22.4: the admin router has its own rate limit. Keyed per administrator,
# not per IP: until the reverse proxy forwards client addresses (VS-020) every
# caller shares one IP, and an IP key would make the limit a global admin lockout.
ADMIN_RATE_LIMIT = 300
ADMIN_RATE_WINDOW_SECONDS = 60

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


async def admin_rate_limit(
    request: Request,
    response: Response,
    claims: AccessTokenClaims = Depends(require_admin),
) -> None:
    """Depends on `require_admin` itself, so the limiter cannot run before the
    boundary whatever order the router lists them in: an anonymous or customer
    request never consumes an administrator's budget, and a non-administrator
    never sees a 429 where an imaginary path would answer 404."""
    await enforce_rate_limit(
        request,
        response,
        key_prefix="admin",
        subject=str(claims.user_id),
        limit=ADMIN_RATE_LIMIT,
        window_seconds=ADMIN_RATE_WINDOW_SECONDS,
    )


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin), Depends(admin_rate_limit)],
    route_class=AdminBoundaryRoute,
)
# VS-007. Mounted here rather than carrying its own guard, so the settings
# editor inherits the one boundary instead of re-deriving it.
router.include_router(settings_router)
# VS-010. Category/material/colour CRUD, inheriting the same boundary.
router.include_router(catalogue_router)
# VS-013. Product CRUD with optimistic versioning.
router.include_router(products_router)
# VS-014. Product image upload, cover, order and soft delete.
router.include_router(product_images_router)
router.include_router(product_image_upload_router)
# VS-012b. The read-only audit-log viewer.
router.include_router(audit_logs_router)
# VS-009. Account list/detail/activation, inheriting the same boundary.
router.include_router(admin_users_router)
# VS-033. The contact message queue.
router.include_router(contact_messages_router)
# VS-035. The Bring Your Idea pipeline and attachment download.
router.include_router(custom_requests_router)
# VS-038 wishlist totals and the VS-035 Bring Your Idea funnel.
router.include_router(engagement_analytics_router)
# VS-024. Payment reconcile and manual confirm; the manual hold release.
router.include_router(admin_payments_router)
router.include_router(order_release_router)
# VS-039. The offer queue and offer detail (api-endpoints.md 21).
router.include_router(offers_router)


def _allowed_methods(request: Request) -> list[str]:
    """Methods the real admin routes accept for this exact path, read from the
    registered route table rather than hard-coded."""
    path = request.scope["path"]
    allowed: set[str] = set()
    for context in iter_route_contexts(request.app.router.routes):
        if context.endpoint is admin_fallthrough or not context.path or not context.methods:
            continue
        regex, _, _ = compile_path(context.path)
        if regex.match(path):
            allowed |= set(context.methods)
    if "GET" in allowed:
        allowed.add("HEAD")
    return sorted(allowed)


async def admin_fallthrough(request: Request) -> None:
    """Reached only by an MFA-complete administrator (the router's dependencies
    have already refused everyone else). Not a route anyone calls: it is the
    answer for a path or method no real route serves."""
    allowed = _allowed_methods(request)
    if allowed:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            headers={"Allow": ", ".join(allowed)},
        )
    raise not_found_error()


class _AnyMethodRoute(AdminBoundaryRoute):
    """The catch-all must catch *every* method, not only the seven it lists.

    A route answers a method it does not list with a PARTIAL match, and a
    router whose only matches are partial answers 405 + `Allow` from the first
    one - before any dependency runs. So `TRACE`, `PROPFIND` or any made-up
    method on a real admin path answered `405 Allow: GET`, and on an imaginary
    one listed the catch-all's methods: an unauthenticated oracle. Here a path
    match is always FULL, and the request is handled as a GET (the catch-all
    never reads the body or looks at the method)."""

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child_scope = super().matches(scope)
        return (Match.FULL if match is Match.PARTIAL else match), child_scope

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["method"] not in (self.methods or ()):
            scope = {**scope, "method": "GET"}
        await super().handle(scope, receive, send)


def _fallthrough_kwargs() -> dict[str, Any]:
    return {
        "endpoint": admin_fallthrough,
        "methods": _ALL_METHODS,
        "include_in_schema": False,
        "response_model": None,
        "route_class_override": _AnyMethodRoute,
    }


# Registered LAST: a real route that fully matches always wins; these only catch
# what is left, including a real path with the wrong method or a trailing slash.
router.add_api_route("", **_fallthrough_kwargs())
router.add_api_route("/{path:path}", **_fallthrough_kwargs())
