"""Contract checks: observed responses against the OpenAPI document and the
stable error-code catalogue in docs/requirments/api-endpoints.md section 5.

One scripted tour drives the API into as many distinct outcomes as VS-001..009
can produce, recording (method, route template, response) for each; the tests
then judge that record against the documents.
"""

import re
from pathlib import Path
from typing import Any

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.enums import UserRole
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.main import app as main_app
from tests.integration.deep_support import (
    CONFIRM_PATH,
    PASSWORD,
    SETUP_PATH,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
    unique_email,
)

DOCS = Path(__file__).resolve().parents[2] / "docs" / "requirments" / "api-endpoints.md"
CATALOGUE = set(
    re.findall(r"^\|\s*\d{3}\s*\|\s*`([A-Z_]+)`", DOCS.read_text(encoding="utf-8"), re.M)
)

# Every catalogue code the V1 identity/platform/engagement surface can emit.
REACHABLE_IN_VS001_VS009 = {
    "MALFORMED_REQUEST",
    "AUTH_REQUIRED",
    "EMAIL_VERIFICATION_REQUIRED",
    "NOT_FOUND",
    "RATE_LIMITED",
    "VALIDATION_ERROR",
    "INVALID_TOKEN",
    "INVALID_CREDENTIALS",
    "MFA_REQUIRED",
    "MFA_INVALID",
    "ACCOUNT_DISABLED",
    "CSRF_INVALID",
    "INVALID_STATE_TRANSITION",
    "RESOURCE_EXPIRED",
    "SETTING_INVALID",
}

Record = list[tuple[str, str, Any]]


def _call(
    record: Record,
    client: TestClient,
    method: str,
    template: str,
    path: str | None = None,
    **kw: Any,
) -> Any:
    response = client.request(method, path or template, **kw)
    record.append((method, template, response))
    return response


@pytest.fixture
async def tour(db_session: AsyncSession, configured_app: None) -> Record:
    record: Record = []
    r = record
    with client_for(main_app) as c:
        _call(r, c, "GET", "/health/live")
        _call(r, c, "GET", "/health/ready")
        _call(r, c, "GET", "/api/v1/settings/public")
        _call(r, c, "GET", "/api/v1/me")
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/register",
            content=b"{",
            headers={"content-type": "application/json"},
        )
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/register",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": "bad"},
        )
        email = unique_email()
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/register",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": email, "password": PASSWORD},
        )
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/resend-verification",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": email},
        )
        _call(r, c, "POST", "/api/v1/auth/verify-email", json={"token": "nope"})
        _call(
            r, c, "POST", "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/password-reset/request",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": email},
        )
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/password-reset/confirm",
            json={"token": "nope", "new_password": "long-enough-1"},
        )
        _call(
            r, c, "POST", "/api/v1/auth/mfa/verify", json={"challenge_id": "nope", "code": "123456"}
        )
        _call(r, c, "POST", "/api/v1/auth/refresh")
        for _ in range(4):
            _call(
                r,
                c,
                "POST",
                "/api/v1/auth/register",
                json={
                    "captcha_token": FAKE_CAPTCHA_PASS,
                    "email": unique_email(),
                    "password": PASSWORD,
                },
            )

    disabled = await create_user(db_session, active=False)
    with client_for(main_app) as c:
        _call(
            r, c, "POST", "/api/v1/auth/login", json={"email": disabled.email, "password": PASSWORD}
        )

    unverified = await create_user(db_session, verified=False)
    with client_for(main_app) as c:
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/login",
            json={"email": unverified.email, "password": PASSWORD},
        )
        _call(r, c, "GET", "/api/v1/me")
        _call(r, c, "GET", "/api/v1/me/notifications")
        _call(
            r,
            c,
            "PATCH",
            "/api/v1/me/notifications/{notification_id}",
            "/api/v1/me/notifications/00000000-0000-0000-0000-000000000000",
            json={"read": True},
            headers=csrf(c),
        )
        _call(r, c, "POST", "/api/v1/auth/logout")
        _call(r, c, "GET", "/api/v1/admin/settings")
        _call(r, c, "POST", "/api/v1/auth/refresh", headers=csrf(c))
        _call(r, c, "POST", "/api/v1/auth/logout", headers=csrf(c))

    customer = await create_user(db_session)
    with client_for(main_app) as c:
        login(c, customer.email)
        _call(
            r,
            c,
            "PATCH",
            "/api/v1/me/notifications/{notification_id}",
            "/api/v1/me/notifications/00000000-0000-0000-0000-000000000000",
            json={"read": True},
            headers=csrf(c),
        )

    bare_admin = await create_user(db_session, role=UserRole.ADMIN)
    with client_for(main_app) as c:
        login(c, bare_admin.email)
        _call(r, c, "GET", "/api/v1/admin/settings")
        _call(
            r, c, "POST", SETUP_PATH, json={"current_password": "wrong-password"}, headers=csrf(c)
        )
        secret = _call(
            r, c, "POST", SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(c)
        ).json()["secret"]
        _call(r, c, "POST", CONFIRM_PATH, json={"code": "000000"}, headers=csrf(c))
        _call(r, c, "POST", CONFIRM_PATH, json={"code": pyotp.TOTP(secret).now()}, headers=csrf(c))
        _call(r, c, "POST", SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(c))
        c.cookies.clear()
        challenge = _call(
            r,
            c,
            "POST",
            "/api/v1/auth/login",
            json={"email": bare_admin.email, "password": PASSWORD},
        ).json()["challenge_id"]
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/mfa/verify",
            json={"challenge_id": challenge, "code": "000000"},
        )

    with client_for(main_app) as c:
        await mfa_admin(c, db_session)
        _call(r, c, "GET", "/api/v1/admin/settings")
        _call(
            r, c, "GET", "/api/v1/admin/settings/{key}", "/api/v1/admin/settings/accepting_orders"
        )
        _call(
            r,
            c,
            "PATCH",
            "/api/v1/admin/settings/{key}",
            "/api/v1/admin/settings/accepting_orders",
            json={"value": "yes"},
            headers=csrf(c),
        )
        _call(r, c, "GET", "/api/v1/admin/users")
        _call(r, c, "GET", "/api/v1/admin/users/{user_id}", f"/api/v1/admin/users/{customer.id}")
        _call(
            r,
            c,
            "PATCH",
            "/api/v1/admin/users/{user_id}",
            f"/api/v1/admin/users/{customer.id}",
            json={"is_active": True},
            headers=csrf(c),
        )
        _call(
            r,
            c,
            "POST",
            "/api/v1/auth/mfa/recovery-codes/regenerate",
            json={"current_password": PASSWORD},
            headers=csrf(c),
        )
        _call(r, c, "GET", "/api/v1/me/notifications")
        _call(r, c, "GET", "/api/v1/me")
        _call(r, c, "DELETE", "/api/v1/me")
    return record


def _codes(record: Record) -> set[str]:
    codes = set()
    for _, _, response in record:
        if response.headers.get("content-type", "").startswith("application/problem+json"):
            codes.add(response.json()["code"])
    return codes


@pytest.mark.integration
def test_the_catalogue_was_parsed() -> None:
    assert {"AUTH_REQUIRED", "SETTING_INVALID", "RATE_LIMITED"} <= CATALOGUE


@pytest.mark.integration
def test_every_v1_catalogue_code_is_reachable(tour: Record) -> None:
    assert REACHABLE_IN_VS001_VS009 <= CATALOGUE
    assert REACHABLE_IN_VS001_VS009 - _codes(tour) == set()


@pytest.mark.integration
def test_every_error_is_an_rfc9457_problem(tour: Record) -> None:
    for method, template, response in tour:
        if response.status_code >= 400:
            assert response.headers["content-type"].startswith("application/problem+json"), (
                method,
                template,
            )
            body = response.json()
            assert body["status"] == response.status_code
            assert body["request_id"] == response.headers["x-request-id"]


@pytest.mark.integration
def test_every_emitted_code_is_in_the_catalogue(tour: Record) -> None:
    with client_for(main_app) as c:
        method_not_allowed = c.delete("/health/live").json()["code"]
    emitted = _codes(tour) | {method_not_allowed, "SERVICE_UNAVAILABLE", "INTERNAL_ERROR"}
    assert emitted - CATALOGUE == set()


@pytest.mark.integration
def test_every_observed_status_is_documented_in_openapi(tour: Record) -> None:
    paths = main_app.openapi()["paths"]
    undocumented = sorted(
        {
            (method, template, str(response.status_code))
            for method, template, response in tour
            # A 405 is an unrouted method: there is no operation to document it on.
            if template in paths
            and method.lower() in paths[template]
            and str(response.status_code) not in paths[template][method.lower()]["responses"]
        }
    )
    assert undocumented == [], undocumented


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = components[schema["$ref"].split("/")[-1]]
    return schema


def _conforms(
    value: Any, schema: dict[str, Any], components: dict[str, Any], where: str
) -> list[str]:
    schema = _resolve(schema, components)
    problems: list[str] = []
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [_conforms(value, option, components, where) for option in schema[key]]
            return [] if any(not o for o in options) else [f"{where}: matches no {key} branch"]
    kind = schema.get("type")
    if kind == "object" and isinstance(value, dict):
        properties = schema.get("properties", {})
        problems += [f"{where}.{k}: missing" for k in schema.get("required", []) if k not in value]
        if properties and schema.get("additionalProperties") is not True:
            problems += [f"{where}.{k}: undocumented" for k in value if k not in properties]
        for k, v in value.items():
            if k in properties:
                problems += _conforms(v, properties[k], components, f"{where}.{k}")
    elif kind == "array":
        if not isinstance(value, list):
            return [f"{where}: not an array"]
        for n, item in enumerate(value):
            problems += _conforms(item, schema.get("items", {}), components, f"{where}[{n}]")
    elif kind in {"string", "integer", "boolean", "null", "number"}:
        types: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "integer": int,
            "boolean": bool,
            "null": type(None),
            "number": (int, float),
        }
        python = types[kind]
        if not isinstance(value, python) or (kind == "integer" and isinstance(value, bool)):
            problems.append(f"{where}: {type(value).__name__} is not {kind}")
    return problems


@pytest.mark.integration
def test_every_2xx_body_matches_its_documented_schema(tour: Record) -> None:
    spec = main_app.openapi()
    components = spec["components"]["schemas"]
    checked = 0
    problems: list[str] = []
    for method, template, response in tour:
        if not 200 <= response.status_code < 300 or not response.content:
            continue
        documented = spec["paths"][template][method.lower()]["responses"].get(
            str(response.status_code)
        )
        assert documented is not None, (method, template, response.status_code)
        schema = documented.get("content", {}).get("application/json", {}).get("schema")
        if schema:
            checked += 1
            problems += _conforms(response.json(), schema, components, f"{method} {template}")
    assert checked >= 10
    assert problems == [], problems
