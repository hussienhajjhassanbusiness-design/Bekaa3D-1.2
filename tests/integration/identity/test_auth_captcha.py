"""VS-033 / ADR-025: captcha on register, resend and reset request. It runs before any
account lookup, so its refusal reads the same for every address."""

import time
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.infrastructure.models import UserModel
from app.identity.infrastructure.repositories import UserRepository
from app.integrations.captcha.factory import get_captcha_verifier
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS, FakeCaptcha
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel, EmailOutboxModel
from tests.integration.deep_support import (
    PASSWORD,
    TIMING_SAMPLES,
    assert_problem,
    client_for,
    create_user,
    describe,
    distinguishable,
    unique_email,
    untraced_clock,
)

ROUTES = [
    pytest.param("/api/v1/auth/register", True, id="register"),
    pytest.param("/api/v1/auth/resend-verification", False, id="resend"),
    pytest.param("/api/v1/auth/password-reset/request", False, id="reset-request"),
]
# Per-request values; everything else about a refusal must be identical.
VARYING_HEADERS = {"x-request-id", "date", "content-length"}


@pytest.fixture
def captcha() -> Iterator[FakeCaptcha]:
    fake = FakeCaptcha()
    main_app.dependency_overrides[get_captcha_verifier] = lambda: fake
    yield fake
    main_app.dependency_overrides.pop(get_captcha_verifier, None)


def _body(path_takes_password: bool, email: str, token: str) -> dict[str, Any]:
    body: dict[str, Any] = {"email": email, "captcha_token": token}
    if path_takes_password:
        body["password"] = PASSWORD
    return body


async def _side_effects(db: AsyncSession, emails: list[str]) -> tuple[int, int, int]:
    db.expire_all()
    users = await db.scalar(
        select(func.count()).select_from(UserModel).where(UserModel.email.in_(emails))
    )
    outbox = await db.scalar(
        select(func.count())
        .select_from(EmailOutboxModel)
        .where(EmailOutboxModel.recipient_email.in_(emails))
    )
    audits = await db.scalar(select(func.count()).select_from(AuditLogModel))
    return int(users or 0), int(outbox or 0), int(audits or 0)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "takes_password"), ROUTES)
@pytest.mark.parametrize(
    ("token", "available", "status", "code"),
    [
        pytest.param("", True, 400, "CAPTCHA_INVALID", id="empty"),
        pytest.param("forged", True, 400, "CAPTCHA_INVALID", id="refused"),
        pytest.param(FAKE_CAPTCHA_PASS, False, 503, "SERVICE_UNAVAILABLE", id="unavailable"),
    ],
)
async def test_a_refused_captcha_answers_identically_for_every_address_and_writes_nothing(
    db_session: AsyncSession,
    captcha: FakeCaptcha,
    path: str,
    takes_password: bool,
    token: str,
    available: bool,
    status: int,
    code: str,
) -> None:
    captcha.available = available
    unverified = await create_user(db_session, verified=False)
    verified = await create_user(db_session)
    emails = [unique_email(), unverified.email, verified.email]
    before = await _side_effects(db_session, emails)
    shapes = set()
    with client_for(main_app) as client:
        for email in emails:
            response = client.post(path, json=_body(takes_password, email, token))
            assert_problem(response, status, code)
            body = response.json()
            del body["request_id"]
            headers = tuple(
                sorted((k, v) for k, v in response.headers.items() if k not in VARYING_HEADERS)
            )
            shapes.add((response.status_code, repr(sorted(body.items())), headers))
    assert len(shapes) == 1, shapes
    assert await _side_effects(db_session, emails) == before


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "takes_password"), ROUTES)
async def test_a_missing_token_is_a_validation_error(
    captcha: FakeCaptcha, path: str, takes_password: bool
) -> None:
    body = _body(takes_password, unique_email(), "x")
    del body["captcha_token"]
    with client_for(main_app) as client:
        response = client.post(path, json=body)
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert response.json()["errors"][0]["loc"] == ["body", "captcha_token"]
    assert captcha.calls == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "takes_password"), ROUTES)
async def test_the_captcha_is_checked_before_any_account_lookup(
    captcha: FakeCaptcha,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    takes_password: bool,
) -> None:
    async def lookup_forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("account looked up before the captcha passed")

    monkeypatch.setattr(UserRepository, "get_by_email_for_update", lookup_forbidden)
    with client_for(main_app, raise_server_exceptions=False) as client:
        refused = client.post(path, json=_body(takes_password, unique_email(), "forged"))
        accepted = client.post(path, json=_body(takes_password, unique_email(), FAKE_CAPTCHA_PASS))
    assert_problem(refused, 400, "CAPTCHA_INVALID")
    # The patch is live: a passing captcha does reach the lookup.
    assert accepted.status_code == 500


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "takes_password"), ROUTES)
async def test_an_accepted_token_reaches_the_flow(
    captcha: FakeCaptcha, path: str, takes_password: bool
) -> None:
    with client_for(main_app) as client:
        response = client.post(path, json=_body(takes_password, unique_email(), FAKE_CAPTCHA_PASS))
    assert response.status_code == 202, response.text
    assert captcha.calls == [FAKE_CAPTCHA_PASS]


@pytest.mark.timing
@untraced_clock
@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "takes_password"), ROUTES)
async def test_a_refused_captcha_takes_as_long_for_a_known_address_as_an_unknown_one(
    db_session: AsyncSession, captcha: FakeCaptcha, path: str, takes_password: bool
) -> None:
    known = (await create_user(db_session)).email
    timings: dict[bool, list[float]] = {True: [], False: []}
    with client_for(main_app) as client:
        for _ in range(TIMING_SAMPLES):
            for is_known in (True, False):
                email = known if is_known else unique_email()
                started = time.perf_counter()
                client.post(path, json=_body(takes_password, email, "forged"))
                timings[is_known].append(time.perf_counter() - started)
    print("TIMING", describe(timings[True], timings[False]))
    assert not distinguishable(timings[True], timings[False]), describe(
        timings[True], timings[False]
    )
