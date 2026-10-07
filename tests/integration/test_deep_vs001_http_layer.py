"""VS-001 deep edge cases: the HTTP layer, error contract and health probes.

Every route in the application is enumerated at import time, so a route added
later is attacked automatically rather than only if someone remembers to.
Admin-namespace behaviour (the SEC-10 information-hiding rule) lives in the
VS-005 deep suite; this file covers the generic layer underneath it.
"""

import asyncio
import json
import os
import re
import time
import uuid
from collections.abc import AsyncGenerator, Callable

import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.config import get_settings
from app.main import app as main_app
from tests.integration.deep_support import asgi_client, assert_problem, client_for

ALL_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _concrete(path: str) -> str:
    """Fill every path parameter with a syntactically valid value."""
    return re.sub(
        r"\{(\w+)\}",
        lambda m: "accepting_orders" if m.group(1) == "key" else str(uuid.uuid4()),
        path,
    )


def _routes() -> list[tuple[str, frozenset[str]]]:
    """Every documented route and its methods.

    Read from the OpenAPI document rather than `app.routes`: FastAPI 0.141
    nests included routers (`_IncludedRouter`), so `app.routes` no longer lists
    them flat. The OpenAPI paths are also the contract, which is the right
    thing to enumerate."""
    paths = main_app.openapi()["paths"]
    return sorted(
        (path, frozenset(method.upper() for method in operations))
        for path, operations in paths.items()
    )


# Admin paths are excluded here on purpose: a wrong method there is the SEC-10
# oracle, locked in by the VS-005/VS-009 suites. Everywhere else a 405 is the
# correct, RFC 9110-mandated answer.
_NON_ADMIN_WRONG_METHODS = [
    (path, method)
    for path, methods in _routes()
    if not path.startswith("/api/v1/admin")
    for method in ALL_METHODS
    if method not in methods
]


# --------------------------------------------------------------------------
# Methods
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "method"), _NON_ADMIN_WRONG_METHODS)
def test_every_wrong_method_is_a_405_problem_with_an_allow_header(path: str, method: str) -> None:
    with client_for(main_app) as client:
        response = client.request(method, _concrete(path))
    assert_problem(response, 405, "METHOD_NOT_ALLOWED")
    allowed = {m.strip() for m in response.headers["allow"].split(",")}
    assert method not in allowed
    assert allowed, "Allow must name at least one method"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/api/v1/settings/public"])
def test_head_is_answered_wherever_get_is(path: str) -> None:
    with client_for(main_app) as client:
        get = client.get(path)
        head = client.head(path)
    assert head.status_code == get.status_code
    assert head.content == b""


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("path", ["/api/v1/auth/login", "/api/v1/me", "/api/v1/settings/public"])
def test_a_cors_preflight_grants_no_cross_origin_access(path: str) -> None:
    """No CORS middleware exists, so a hostile origin must never be echoed back.
    That absence is what stops a cross-site `fetch` with a JSON body."""
    with client_for(main_app) as client:
        preflight = client.options(
            path,
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        simple = client.get(path, headers={"Origin": "https://evil.example"})
    for response in (preflight, simple):
        assert "access-control-allow-origin" not in response.headers
        assert "access-control-allow-credentials" not in response.headers
    assert preflight.status_code == 405


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "path",
    [
        "/API/V1/ME",
        "/Health/Live",
        "//api/v1/me",
        "/api//v1/me",
        "/api/v1/auth/%2e%2e/me",
        "/api/v1/auth/..%2fme",
        pytest.param("/api/v1/" + "a" * 16_000, id="16k-path"),
        "/api/v2/me",
        "/api/v1/me;jsessionid=1",
    ],
)
def test_odd_paths_are_plain_404_problems(path: str) -> None:
    with client_for(main_app) as client:
        response = client.get(path, follow_redirects=False)
    assert_problem(response, 404, "NOT_FOUND")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "path",
    ["/api/v1/me%00", "/api/v1/no-such-route%00", "/api/v1/me%01", "/health/live%7F"],
)
def test_a_control_character_in_the_path_is_a_422(path: str) -> None:
    """BUG-03: refused before routing, so a real path and an imaginary one
    answer identically and nothing reaches the database."""
    with client_for(main_app) as client:
        response = client.get(path, follow_redirects=False)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert response.json()["errors"][0]["loc"] == ["path"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_trailing_slash_on_a_public_route_redirects_to_the_canonical_path() -> None:
    with client_for(main_app) as client:
        response = client.get("/health/live/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].endswith("/health/live")


# --------------------------------------------------------------------------
# Request correlation
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("supplied", [None, ""])
def test_a_missing_or_empty_request_id_is_generated(supplied: str | None) -> None:
    headers = {} if supplied is None else {"X-Request-ID": supplied}
    with client_for(main_app) as client:
        response = client.get("/health/live", headers=headers)
    assert re.fullmatch(r"req_[0-9a-f]{32}", response.headers["x-request-id"])


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_generated_request_ids_are_unique() -> None:
    with client_for(main_app) as client:
        ids = {client.get("/health/live").headers["x-request-id"] for _ in range(50)}
    assert len(ids) == 50


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "supplied",
    [
        pytest.param("x" * 20_000, id="20k-chars"),
        pytest.param("id with spaces and \t tab", id="whitespace"),
    ],
)
def test_a_hostile_request_id_is_not_echoed_verbatim(supplied: str) -> None:
    with client_for(main_app) as client:
        response = client.get(
            "/health/live", headers={"X-Request-ID": supplied.encode("latin-1").decode("latin-1")}
        )
    echoed = response.headers["x-request-id"]
    assert echoed != supplied
    assert len(echoed) <= 128


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_spoofed_forwarded_for_header_is_not_reflected_anywhere() -> None:
    with client_for(main_app) as client:
        response = client.get(
            "/api/v1/nope", headers={"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}
        )
    assert "1.2.3.4" not in response.text
    assert "5.6.7.8" not in response.text


# --------------------------------------------------------------------------
# Request bodies
# --------------------------------------------------------------------------

REGISTER = "/api/v1/auth/register"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("content", "content_type", "status", "code"),
    [
        (b"", "application/json", 422, "VALIDATION_ERROR"),
        (b"{", "application/json", 400, "MALFORMED_REQUEST"),
        (b'{"email": "a@b.co",}', "application/json", 400, "MALFORMED_REQUEST"),
        (b"\xff\xfe\x00garbage", "application/json", 400, "MALFORMED_REQUEST"),
        (b"null", "application/json", 422, "VALIDATION_ERROR"),
        (b"[]", "application/json", 422, "VALIDATION_ERROR"),
        (b'"string"', "application/json", 422, "VALIDATION_ERROR"),
        (b"12", "application/json", 422, "VALIDATION_ERROR"),
        (b"{}", "application/json", 422, "VALIDATION_ERROR"),
        (b"NaN", "application/json", 422, "VALIDATION_ERROR"),
    ],
)
def test_malformed_bodies_get_the_documented_problem(
    content: bytes, content_type: str, status: int, code: str
) -> None:
    with client_for(main_app) as client:
        response = client.post(REGISTER, content=content, headers={"content-type": content_type})
    assert_problem(response, status, code)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"],
)
def test_a_json_body_under_a_form_content_type_is_refused(content_type: str) -> None:
    """The cross-site-form CSRF path: a browser form can only send these three
    content types, and a JSON endpoint must not parse any of them."""
    body = json.dumps({"email": "victim@example.com", "password": "attacker-chosen-1"})
    with client_for(main_app) as client:
        response = client.post(
            "/api/v1/auth/login", content=body, headers={"content-type": content_type}
        )
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_duplicate_json_keys_resolve_to_the_last_and_cannot_smuggle_a_field() -> None:
    content = b'{"email": "a@example.com", "password": "short", "password": "long-enough-1"}'
    with client_for(main_app) as client:
        response = client.post(
            REGISTER, content=content, headers={"content-type": "application/json"}
        )
    assert response.status_code == 202, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_five_megabyte_body_is_refused_without_a_server_error() -> None:
    body = {"email": "a@example.com", "password": "x" * (5 * 1024 * 1024)}
    with client_for(main_app) as client:
        started = time.perf_counter()
        response = client.post(REGISTER, json=body)
        elapsed = time.perf_counter() - started
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert elapsed < 5, f"a rejected 5 MB body took {elapsed:.1f}s"


# --------------------------------------------------------------------------
# Error bodies never leak internals
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_database_error_leaks_no_sql_or_driver_detail(
    make_app: Callable[[], FastAPI],
) -> None:
    app = make_app()

    @app.get("/__deep_boom")
    async def boom(session: AsyncSession = Depends(get_session)) -> None:
        await session.execute(text("SELECT password_hash FROM users WHERE 1/0 = 1"))

    with client_for(app, raise_server_exceptions=False) as client:
        response = client.get("/__deep_boom")
    assert_problem(response, 500, "INTERNAL_ERROR")
    lowered = response.text.lower()
    for leak in ("select", "password_hash", "division", "traceback", "asyncpg", "sqlalchemy"):
        assert leak not in lowered, leak


# --------------------------------------------------------------------------
# Health probes against dependencies that are down, and that hang
# --------------------------------------------------------------------------


@pytest.fixture
async def blackhole_port() -> AsyncGenerator[int]:
    """A TCP port that accepts connections and then never says a word - a hung
    dependency, as opposed to a dead one that refuses immediately."""
    held: list[asyncio.StreamWriter] = []

    async def accept(_: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        held.append(writer)

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield port
    for writer in held:
        writer.close()
    server.close()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_readiness_answers_503_quickly_when_redis_hangs(
    make_app: Callable[[], FastAPI], blackhole_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", f"redis://127.0.0.1:{blackhole_port}/0")
    get_settings.cache_clear()
    try:
        async with asgi_client(make_app) as client:
            response = await asyncio.wait_for(client.get("/health/ready"), timeout=8)
        assert response.status_code == 503
    finally:
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_readiness_answers_503_quickly_when_postgres_hangs(
    make_app: Callable[[], FastAPI], blackhole_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"postgresql+asyncpg://u:p@127.0.0.1:{blackhole_port}/db")
    get_settings.cache_clear()
    try:
        async with asgi_client(make_app) as client:
            response = await asyncio.wait_for(client.get("/health/ready"), timeout=8)
        assert response.status_code == 503
    finally:
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_liveness_stays_up_when_both_dependencies_are_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/db")
    get_settings.cache_clear()
    try:
        with client_for(main_app) as client:
            live = client.get("/health/live")
            ready = client.get("/health/ready")
        assert live.status_code == 200
        assert_problem(ready, 503, "SERVICE_UNAVAILABLE")
        assert "u:p" not in ready.text and "127.0.0.1" not in ready.text
    finally:
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_redis_outage_on_a_public_endpoint_is_a_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    try:
        with client_for(main_app, raise_server_exceptions=False) as client:
            response = client.post(
                REGISTER, json={"email": "a@example.com", "password": "long-enough-1"}
            )
        assert_problem(response, 503, "SERVICE_UNAVAILABLE")
    finally:
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_postgres_outage_on_a_public_endpoint_is_a_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/db")
    get_settings.cache_clear()
    try:
        with client_for(main_app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/settings/public")
        assert_problem(response, 503, "SERVICE_UNAVAILABLE")
    finally:
        get_settings.cache_clear()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_an_outage_500_leaks_no_connection_details(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://leakuser:leakpass@127.0.0.1:1/db")
    get_settings.cache_clear()
    try:
        with client_for(main_app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/settings/public")
        assert response.status_code >= 500
        for leak in ("leakuser", "leakpass", "127.0.0.1", "asyncpg", "refused"):
            assert leak not in response.text, leak
    finally:
        get_settings.cache_clear()


def test_the_environment_is_left_as_found() -> None:
    """Guard for the isolation bug fixed in test_health.py: nothing above may
    leave REDIS_URL or DATABASE_URL removed for the tests that follow."""
    assert os.environ.get("REDIS_URL") is not None
