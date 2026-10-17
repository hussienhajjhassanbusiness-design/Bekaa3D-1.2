"""VS-011: the admin rule (SEC-10) holds for every path, method and slash variant.

For every `/api/v1/admin` path - real or imaginary, any method, with or without a
trailing slash - an anonymous caller gets 401, a customer gets the imaginary-path
404 and an administrator without MFA gets 401 `MFA_REQUIRED`. Only an
MFA-complete administrator reaches routing and so sees a 405 or a real 404.
"""

import asyncio
import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.v1.admin as admin_module
from app.api.v1.admin import ADMIN_RATE_LIMIT, admin_fallthrough
from app.core.config import get_settings
from app.identity.api.dependencies import (
    AdminBoundaryRoute,
    current_claims,
    require_admin,
    require_csrf,
    verified_user_short_read,
)
from app.identity.domain.enums import UserRole
from app.main import app as main_app
from tests.integration.deep_support import (
    assert_problem,
    async_client,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
    running_app,
)
from tests.integration.identity.test_deep_vs005_admin_mfa import (
    ADMIN_OPERATIONS,
    IMAGINARY,
    _admin_wrong_methods,
)

ADMIN_PREFIX = "/api/v1/admin"
UNSAFE = ("POST", "PUT", "PATCH", "DELETE")
# Everything the catch-all must answer: the root, imaginary paths, a trailing
# slash on real paths, and every method the real routes do not serve.
ROOTS = [(m, p) for m in ("GET", "POST", "OPTIONS") for p in (ADMIN_PREFIX, ADMIN_PREFIX + "/")]
IMAGINARY_VARIANTS = [
    (method, path)
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    for path in (IMAGINARY, IMAGINARY + "/", IMAGINARY + "/a/b")
]
SLASH_VARIANTS = sorted({("GET", path + "/") for _, path in ADMIN_OPERATIONS})
WRONG_METHODS = _admin_wrong_methods()  # once: path ids are random per call
VARIANTS = ROOTS + IMAGINARY_VARIANTS + SLASH_VARIANTS + WRONG_METHODS


def _canonical(response: Any) -> tuple[Any, ...]:
    """Everything a caller can observe, minus what legitimately differs between
    two requests: the request id, and the path echoed in `instance`."""
    body = response.json() if response.content else {}
    body.pop("request_id", None)
    body.pop("instance", None)
    headers = {
        k: v
        for k, v in response.headers.items()
        if k not in ("x-request-id", "content-length", "date")
    }
    return (response.status_code, json.dumps(body, sort_keys=True), tuple(sorted(headers.items())))


def _code(response: Any) -> str | None:
    """The problem `code`; a HEAD response has no body, so there is none."""
    return response.json().get("code") if response.content else None


def _request_all(client: TestClient, variants: list[tuple[str, str]]) -> dict[Any, Any]:
    return {
        (method, path): client.request(
            method, path, headers=csrf(client) if client.cookies.get("csrf_token") else {}
        )
        for method, path in variants
    }


@pytest.fixture
def unlimited_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The matrix sends several hundred requests as one administrator."""
    monkeypatch.setattr(admin_module, "ADMIN_RATE_LIMIT", 1_000_000)


# --------------------------------------------------------------------------
# The spike: the catch-all outranks a method mismatch
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_the_catch_all_wins_over_a_method_mismatch_on_a_real_admin_path() -> None:
    """`/admin/settings` is a real GET route. DELETE is a PARTIAL match for it;
    the boundary's 401 proves a FULL catch-all match outranked that, in this
    FastAPI/Starlette version. If this breaks after an upgrade the router would
    start answering 405 to anonymous callers again (BUG-10)."""
    with client_for(main_app) as client:
        response = client.delete(f"{ADMIN_PREFIX}/settings")
    assert_problem(response, 401, "AUTH_REQUIRED")


# --------------------------------------------------------------------------
# The matrix: every caller x every path/method/slash variant
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_anonymous_callers_get_401_on_every_variant() -> None:
    with client_for(main_app) as client:
        results = _request_all(client, VARIANTS)
    wrong = {
        k: (r.status_code, _code(r))
        for k, r in results.items()
        if r.status_code != 401 or _code(r) not in ("AUTH_REQUIRED", None)
    }
    assert not wrong, wrong


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("verified", [True, False], ids=["verified", "unverified"])
async def test_customers_get_the_imaginary_404_on_every_variant(
    verified: bool, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, verified=verified)
    with client_for(main_app) as client:
        login(client, user.email)
        expected = {
            "GET": _canonical(client.get(IMAGINARY)),
            "HEAD": _canonical(client.head(IMAGINARY)),
        }
        results = _request_all(client, VARIANTS)
    assert expected["GET"][0] == 404
    wrong = {
        k: r.status_code
        for k, r in results.items()
        if _canonical(r) != expected["HEAD" if k[0] == "HEAD" else "GET"]
    }
    assert not wrong, wrong


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_without_mfa_gets_401_mfa_required_on_every_variant(
    db_session: AsyncSession,
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    with client_for(main_app) as client:
        login(client, admin.email)
        results = _request_all(client, VARIANTS)
    wrong = {
        k: (r.status_code, _code(r))
        for k, r in results.items()
        if (r.status_code, _code(r)) not in {(401, "MFA_REQUIRED"), (401, None)}
    }
    assert not wrong, wrong


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app", "unlimited_admin")
async def test_an_mfa_admin_gets_a_real_404_405_and_no_redirect(db_session: AsyncSession) -> None:
    with client_for(main_app, follow_redirects=False) as client:
        await mfa_admin(client, db_session)
        results = _request_all(client, VARIANTS)
        # HEAD is answered as GET, so it is "wrong" only where GET is.
        get_status = {p: client.get(p).status_code for m, p in WRONG_METHODS if m == "HEAD"}

    assert not [k for k, r in results.items() if r.status_code in (301, 302, 307, 308)]
    assert not [k for k, r in results.items() if r.status_code >= 500]
    wrong_methods = set(WRONG_METHODS)
    for key, response in results.items():
        if key in wrong_methods:
            if key[0] == "HEAD":  # answered as GET, so no body
                assert response.status_code == get_status[key[1]], key
                if response.status_code != 405:
                    continue
            else:
                assert_problem(response, 405, "METHOD_NOT_ALLOWED")
            allow = {m.strip() for m in response.headers["allow"].split(",")}
            assert key[0] not in allow and allow, (key, allow)
        else:
            assert response.status_code == 404, key


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app", "unlimited_admin")
async def test_the_allow_header_is_computed_from_the_registered_routes(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        settings_key = client.get(f"{ADMIN_PREFIX}/settings/accepting_orders")
        wrong = client.post(f"{ADMIN_PREFIX}/settings/accepting_orders", headers=csrf(client))
        listing = client.delete(f"{ADMIN_PREFIX}/settings", headers=csrf(client))
    assert settings_key.status_code == 200
    registered = {
        method
        for ctx in iter_route_contexts(main_app.router.routes)
        if ctx.path == f"{ADMIN_PREFIX}/settings/{{key}}" and ctx.methods
        for method in ctx.methods
    }
    allow = {m.strip() for m in wrong.headers["allow"].split(",")}
    assert allow - {"HEAD"} == registered
    assert "GET" in {m.strip() for m in listing.headers["allow"].split(",")}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("caller", ["anonymous", "customer"])
async def test_head_matches_get_on_admin_paths(caller: str, db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    paths = [IMAGINARY, IMAGINARY + "/", f"{ADMIN_PREFIX}/settings", f"{ADMIN_PREFIX}/settings/"]
    with client_for(main_app) as client:
        if caller == "customer":
            login(client, user.email)
        for path in paths:
            get, head = client.get(path), client.head(path)
            assert head.status_code == get.status_code, path
            assert head.content == b""


# --------------------------------------------------------------------------
# Paths outside the prefix are not admin paths (D4)
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/ADMIN/settings",
        "/API/V1/admin/settings",
        "/api/v1//admin/settings",
        "//api/v1/admin/settings",
        "/api/v1/admin-x",
        "/api/v1/adminsettings",
    ],
)
async def test_lookalike_paths_get_the_ordinary_global_404(
    path: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    with client_for(main_app, follow_redirects=False) as client:
        anonymous = [client.get(path), client.get("/api/v1/nowhere/at/all")]
        login(client, user.email)
        customer = [client.get(path), client.get("/api/v1/nowhere/at/all")]
    for lookalike, nowhere in (anonymous, customer):
        assert_problem(lookalike, 404, "NOT_FOUND")
        assert _canonical(lookalike) == _canonical(nowhere)


# --------------------------------------------------------------------------
# Control characters stay ahead of the boundary
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("caller", ["anonymous", "customer", "admin"])
@pytest.mark.parametrize(
    "target",
    [
        f"{ADMIN_PREFIX}/users?search=a%00b",
        f"{ADMIN_PREFIX}/nothing?x=%01",
        f"{ADMIN_PREFIX}/no%00thing",
        f"{ADMIN_PREFIX}/settings/%1F",
    ],
)
async def test_a_control_character_is_422_for_every_caller_before_auth(
    caller: str, target: str, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        if caller == "customer":
            login(client, (await create_user(db_session)).email)
        elif caller == "admin":
            await mfa_admin(client, db_session)
        response = client.get(target)
    assert_problem(response, 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app", "unlimited_admin")
async def test_every_admin_write_without_the_csrf_token_is_refused(
    db_session: AsyncSession,
) -> None:
    writes = [(m, p) for m, p in ADMIN_OPERATIONS if m in UNSAFE]
    assert len(writes) >= 8, writes
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        refused = {(m, p): client.request(m, p, json={}) for m, p in writes}
        wrong_token = {
            (m, p): client.request(m, p, json={}, headers={"X-CSRF-Token": "x" * 40})
            for m, p in writes
        }
    for label, responses in (("absent", refused), ("wrong", wrong_token)):
        bad = {k: r.status_code for k, r in responses.items() if r.status_code != 403}
        assert not bad, (label, bad)
        assert all(r.json()["code"] == "CSRF_INVALID" for r in responses.values()), label


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unsafe_request_to_an_imaginary_admin_path_needs_no_csrf_to_be_a_404(
    db_session: AsyncSession,
) -> None:
    """Adding CSRF to the catch-all would answer 403 here and 404 on a GET - a
    new oracle for customers."""
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        expected = _canonical(client.get(IMAGINARY))
        for method in UNSAFE:
            assert _canonical(client.request(method, IMAGINARY)) == expected, method


# --------------------------------------------------------------------------
# Malformed input is a 4xx, never a 500, on every admin write
# --------------------------------------------------------------------------


def _bodies() -> Iterator[tuple[str, Any]]:
    yield "not-json", b"{not json"
    yield "empty-string", b""
    yield "array", b"[1, 2, 3]"
    yield "wrong-types", b'{"name": 123, "slug": [], "is_active": "maybe", "value": {}}'
    yield "nul", b'{"name": "a\\u0000b", "slug": "x\\u0000", "value": "\\u0000"}'
    yield "control", b'{"name": "a\\u0007b", "slug": "x\\u001f", "is_active": true}'
    yield "huge-field", b'{"name": "' + b"a" * 20_000 + b'", "slug": "ok"}'


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app", "unlimited_admin")
async def test_hostile_bodies_on_admin_writes_are_never_a_server_error(
    db_session: AsyncSession,
) -> None:
    writes = [(m, p) for m, p in ADMIN_OPERATIONS if m in UNSAFE]
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        statuses = {
            (m, p, label): client.request(
                m,
                p,
                content=body,
                headers={**csrf(client), "Content-Type": "application/json"},
            ).status_code
            for m, p in writes
            for label, body in _bodies()
        }
    bad = {k: s for k, s in statuses.items() if not 400 <= s < 500}
    # A 4xx of any kind is the contract; a 2xx would mean junk was accepted.
    assert not bad, bad


# --------------------------------------------------------------------------
# Structural: nothing under /api/v1/admin can skip the boundary; every
# authenticated write has CSRF
# --------------------------------------------------------------------------


def _walk(dependant: Any) -> set[Any]:
    found = {dependant.call}
    for child in dependant.dependencies:
        found |= _walk(child)
    return found


def _calls(context: Any) -> set[Any]:
    """Every dependency the route runs, router-level ones included. Routes that
    are not API routes (static, mounts) run none."""
    dependant = getattr(context, "dependant", None)
    return _walk(dependant) if dependant is not None else set()


def _contexts() -> list[Any]:
    return list(iter_route_contexts(main_app.router.routes))


def test_every_route_under_admin_runs_require_admin() -> None:
    admin = [c for c in _contexts() if c.path and c.path.startswith(ADMIN_PREFIX)]
    assert len(admin) >= 20, [c.path for c in admin]
    escaping = [(c.path, sorted(c.methods or [])) for c in admin if require_admin not in _calls(c)]
    assert not escaping, escaping
    # And the two catch-alls are among the routes walked, so the walk proves them too.
    assert [c for c in admin if c.endpoint is admin_fallthrough]


def test_nothing_authenticated_hides_under_a_non_admin_prefix_by_accident() -> None:
    """A route that requires an administrator must live under /api/v1/admin, or
    the catch-all (and the 404-for-customers rule) would not cover it - except
    the MFA routes, which are admin-only by design but are auth endpoints."""
    outside = [
        c.path
        for c in _contexts()
        if c.path and not c.path.startswith(ADMIN_PREFIX) and require_admin in _calls(c)
    ]
    assert sorted(outside) == ["/api/v1/auth/mfa/recovery-codes/regenerate"], outside


# Authenticated unsafe routes that check CSRF inline instead of via `require_csrf`:
# they authenticate from the refresh cookie, not from `current_claims`.
_INLINE_CSRF = {"/api/v1/auth/logout", "/api/v1/auth/refresh"}


def test_every_authenticated_write_enforces_csrf() -> None:
    authenticated_writes = []
    for ctx in _contexts():
        methods = set(ctx.methods or []) - {"GET", "HEAD", "OPTIONS"}
        if not methods or ctx.path is None:
            continue
        calls = _calls(ctx)
        if verified_user_short_read in calls:
            # VS-023: authenticates in its own short transaction and checks CSRF itself.
            authenticated_writes.append(ctx.path)
            continue
        if current_claims not in calls:
            continue
        authenticated_writes.append(ctx.path)
        if ctx.endpoint is admin_fallthrough:
            continue  # deliberately CSRF-free: see the catch-all docstring
        assert require_csrf in calls, f"{sorted(methods)} {ctx.path} authenticates without CSRF"
    assert len(authenticated_writes) >= 10, authenticated_writes
    assert "/api/v1/checkout" in authenticated_writes
    assert all(path not in _INLINE_CSRF for path in authenticated_writes)


# --------------------------------------------------------------------------
# The admin rate limit
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_admin_rate_limit_is_per_administrator_and_after_the_boundary(
    db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    assert ADMIN_RATE_LIMIT == 300
    with client_for(main_app) as first, client_for(make_app()) as second:
        await mfa_admin(first, db_session)
        await mfa_admin(second, db_session)
        customer = await create_user(db_session)
        with client_for(make_app()) as anonymous, client_for(make_app()) as other:
            login(other, customer.email)
            # Strangers hammering the admin surface spend nobody's budget.
            for _ in range(5):
                assert anonymous.get(IMAGINARY).status_code == 401
                assert other.get(IMAGINARY).status_code == 404

        statuses = [first.get(IMAGINARY).status_code for _ in range(ADMIN_RATE_LIMIT)]
        assert set(statuses) == {404}, "the 300 requests in the window are all served"
        limited = first.get(IMAGINARY)
        independent = second.get(IMAGINARY)

    assert_problem(limited, 429, "RATE_LIMITED")
    assert int(limited.headers["retry-after"]) > 0
    assert limited.headers["ratelimit-limit"] == "300"
    assert limited.headers["ratelimit-remaining"] == "0"
    assert independent.status_code == 404, "a second administrator has their own budget"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_redis_outage_on_an_admin_route_is_a_503_like_every_other_limiter(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import redis.exceptions

    with client_for(main_app) as client:
        await mfa_admin(client, db_session)

        async def broken(*_args: Any, **_kwargs: Any) -> Any:
            raise redis.exceptions.ConnectionError("redis is down")

        monkeypatch.setattr(client.app.state.redis, "eval", broken)  # type: ignore[attr-defined]
        response = client.get(f"{ADMIN_PREFIX}/settings")
    assert_problem(response, 503, "SERVICE_UNAVAILABLE")


# ==========================================================================
# Independent review (VS-011 verify): adversarial cases
# ==========================================================================


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("method", ["TRACE", "PROPFIND", "CONNECT", "FOO", "MKCOL"])
async def test_an_unlisted_method_answers_per_the_admin_rule_on_real_and_imaginary_paths(
    method: str, db_session: AsyncSession
) -> None:
    """A method the catch-all does not list used to fall through to Starlette's
    405, whose `Allow` header named a real route's methods (`GET`) but the
    catch-all's seven on an imaginary path - before authentication."""
    user = await create_user(db_session)
    with client_for(main_app) as client:
        anonymous = [client.request(method, p) for p in (f"{ADMIN_PREFIX}/settings", IMAGINARY)]
        login(client, user.email)
        customer = [client.request(method, p) for p in (f"{ADMIN_PREFIX}/settings", IMAGINARY)]
    for response in anonymous:
        assert_problem(response, 401, "AUTH_REQUIRED")
        assert "allow" not in response.headers
    assert _canonical(customer[0]) == _canonical(customer[1])
    assert customer[0].status_code == 404


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app", "unlimited_admin")
async def test_an_mfa_admin_gets_405_for_an_unlisted_method_on_a_real_path(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        real = client.request("TRACE", f"{ADMIN_PREFIX}/settings")
        imaginary = client.request("TRACE", IMAGINARY)
    assert_problem(real, 405, "METHOD_NOT_ALLOWED")
    assert {m.strip() for m in real.headers["allow"].split(",")} == {"GET", "HEAD"}
    assert_problem(imaginary, 404, "NOT_FOUND")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("label", "body", "content_type"),
    [
        ("not-json", b"{bad", "application/json"),
        ("truncated", b'{"name": "a', "application/json"),
        ("form", b"a=b", "application/x-www-form-urlencoded"),
        ("big", b"[" + b"1," * 200_000 + b"1]", "application/json"),
    ],
    ids=["not-json", "truncated", "form", "big"],
)
async def test_the_boundary_runs_before_the_body_is_parsed(
    label: str, body: bytes, content_type: str, db_session: AsyncSession
) -> None:
    """FastAPI parses a JSON body before solving dependencies, so a malformed
    body on a real admin write answered 400 MALFORMED_REQUEST where an imaginary
    path answered 401/404 (`AdminBoundaryRoute` fixes it)."""
    user = await create_user(db_session)
    writes = sorted({p for m, p in ADMIN_OPERATIONS if m == "POST"})
    assert writes
    headers = {"Content-Type": content_type}
    with client_for(main_app) as client:
        anonymous = [client.post(p, content=body, headers=headers) for p in [*writes, IMAGINARY]]
        login(client, user.email)
        customer = [
            client.post(p, content=body, headers={**headers, **csrf(client)})
            for p in [*writes, IMAGINARY]
        ]
    assert {(r.status_code, _code(r)) for r in anonymous} == {(401, "AUTH_REQUIRED")}, label
    assert len({_canonical(r) for r in customer}) == 1, label
    assert customer[0].status_code == 404


def test_every_admin_route_authenticates_before_reading_the_body() -> None:
    """Structural: a future admin router created without
    `route_class=AdminBoundaryRoute` would reopen the body-parse oracle."""
    admin = [c for c in _contexts() if c.path and c.path.startswith(ADMIN_PREFIX)]
    plain = [c.path for c in admin if not isinstance(c.original_route, AdminBoundaryRoute)]
    assert not plain, plain


# --------------------------------------------------------------------------
# A. Path fuzz: consistent 401/404/422, never 500, real == imaginary
# --------------------------------------------------------------------------

# Each template is filled with a real segment and an imaginary one of equal length.
_FUZZ_TEMPLATES = [
    "/api/v1/admin%2F{seg}",
    "/api/v1/admin/{seg}%2F",
    "/api/v1/admin//{seg}",
    "/api/v1/admin/./{seg}",
    "/api/v1/admin/../admin/{seg}",
    "/api/v1/admin/{seg}/..",
    "/api/v1/admin/{seg}/./",
    "/API/V1/ADMIN/{seg}",
    "/api/v1/admin/{seg}/%C3%A9t%C3%A9",
    "/api/v1/admin/{seg}/%E2%80%AE",
    "/api/v1/admin/{seg}/%FF%FE",
    "/api/v1/admin/{seg}%00",
    "/api/v1/admin/{seg}/%0d%0aX-Injected:%201",
    "/api/v1/admin/{seg}/%7F",
    "/api/v1/admin/{seg}/" + "a" * 8192,
    "/api/v1/admin/{seg}?q=" + "b" * 8192,
]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("caller", ["anonymous", "customer"])
async def test_path_fuzz_never_tells_real_from_imaginary_and_never_500s(
    caller: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    with client_for(main_app, follow_redirects=False) as client:
        if caller == "customer":
            login(client, user.email)
        pairs = {
            template: (
                client.get(template.format(seg="settings")),
                client.get(template.format(seg="zzzzzzzz")),
            )
            for template in _FUZZ_TEMPLATES
        }
    allowed = {401, 404, 422} if caller == "anonymous" else {404, 422}
    for template, (real, imaginary) in pairs.items():
        assert real.status_code in allowed, (template, real.status_code, real.text[:200])
        assert _canonical(real) == _canonical(imaginary), template
        assert "x-injected" not in real.headers


# --------------------------------------------------------------------------
# B. Rate-limit race: exactly the limit is served, per administrator
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.usefixtures("configured_app")
async def test_310_concurrent_admin_requests_serve_exactly_300(
    db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    jars = []
    for _ in range(2):
        with client_for(main_app) as client:
            await mfa_admin(client, db_session)
            jars.append(dict(client.cookies.items()))

    async with (
        running_app(make_app) as app,
        async_client(app) as first,
        async_client(app) as second,
    ):
        first.cookies.update(jars[0])
        second.cookies.update(jars[1])
        responses = await asyncio.gather(
            *(first.get(IMAGINARY) for _ in range(ADMIN_RATE_LIMIT + 10))
        )
        other = await second.get(IMAGINARY)

    statuses = [r.status_code for r in responses]
    assert statuses.count(404) == ADMIN_RATE_LIMIT, sorted(set(statuses))
    assert statuses.count(429) == 10
    assert other.status_code == 404, "the second administrator's budget is untouched"


# --------------------------------------------------------------------------
# D. Redis unavailable: the same 503 as the existing limiters
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_redis_down_on_an_admin_route_matches_the_public_limiter_outage(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same technique as test_deep_vs001_http_layer's public-endpoint outage
    test: a real connection failure, not a mocked call."""
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        jar = dict(client.cookies.items())

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    try:
        with client_for(main_app, raise_server_exceptions=False) as client:
            client.cookies.update(jar)
            admin = client.get(f"{ADMIN_PREFIX}/settings")
            public = client.get("/api/v1/categories")
    finally:
        get_settings.cache_clear()
    assert_problem(admin, 503, "SERVICE_UNAVAILABLE")
    assert (admin.status_code, admin.json()["code"]) == (public.status_code, public.json()["code"])
    assert "127.0.0.1" not in admin.text and "redis" not in admin.text.lower()


# --------------------------------------------------------------------------
# F. Equal work: a customer's real and imaginary admin requests run the same SQL
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_customer_costs_the_same_queries_on_real_and_imaginary_admin_paths(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(" ".join(statement.split()))

    costs: dict[str, list[str]] = {}
    with client_for(main_app) as client:
        login(client, user.email)
        engine = main_app.state.db_engine.sync_engine
        event.listen(engine, "before_cursor_execute", record)
        try:
            for label, method, path, body in [
                ("real GET", "GET", f"{ADMIN_PREFIX}/users", None),
                ("imaginary GET", "GET", IMAGINARY, None),
                ("real POST", "POST", f"{ADMIN_PREFIX}/categories", b'{"name": "x"}'),
                ("imaginary POST", "POST", IMAGINARY, b'{"name": "x"}'),
                ("real, wrong method", "DELETE", f"{ADMIN_PREFIX}/settings", None),
            ]:
                statements.clear()
                response = client.request(
                    method,
                    path,
                    content=body,
                    headers={**csrf(client), "Content-Type": "application/json"},
                )
                assert response.status_code == 404, label
                costs[label] = list(statements)
        finally:
            event.remove(engine, "before_cursor_execute", record)
    assert len({tuple(v) for v in costs.values()}) == 1, costs
    assert any("auth_epoch" in s for s in costs["imaginary GET"]), costs
