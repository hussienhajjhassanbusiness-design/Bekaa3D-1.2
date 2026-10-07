"""Deep leak checks: nothing secret may reach the logs, on any path.

Capture is deliberately not left to `caplog`/`capsys`. `configure_logging()`
runs at every app start and *replaces* the root logger's handlers, which
silently removes pytest's caplog handler, and its StreamHandler binds whatever
`sys.stdout` happens to be at that moment - so an absence assertion over those
captures can pass vacuously. Instead `app_logs` patches `logging.StreamHandler`
so every configuration the app performs writes, through its real formatter,
into a buffer this test owns; and each test first asserts that the events it
expects were captured before asserting that secrets were not.
"""

import io
import logging
from collections.abc import Callable
from typing import Any

import pyotp
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_session
from app.identity.application.security.password_hasher import hash_password
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import UserModel
from app.jobs.outbox import dispatch_outbox
from app.main import app as main_app
from app.platform.infrastructure.models import EmailOutboxModel
from tests.integration.deep_support import (
    CONFIRM_PATH,
    PASSWORD,
    SETUP_PATH,
    async_client,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
    running_app,
    unique_email,
)


async def _outbox_token(db: AsyncSession, email: str, template: str) -> str:
    db.expire_all()
    row = await db.scalar(
        select(EmailOutboxModel)
        .where(EmailOutboxModel.recipient_email == email, EmailOutboxModel.template == template)
        .order_by(EmailOutboxModel.created_at.desc())
        .limit(1)
    )
    assert row is not None
    return str(row.payload["token"])


@pytest.fixture
def app_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Every handler `configure_logging()` builds while this test runs writes
    into this buffer, through the application's own formatter."""
    buffer = io.StringIO()
    original = logging.StreamHandler

    def into_buffer(*_args: Any, **_kwargs: Any) -> logging.Handler:
        return original(buffer)

    monkeypatch.setattr(logging, "StreamHandler", into_buffer)
    return buffer


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_no_credential_or_token_reaches_the_logs_across_every_flow(
    db_session: AsyncSession,
    db_engine: AsyncEngine,
    app_logs: io.StringIO,
) -> None:
    secrets: dict[str, str] = {}
    email = unique_email()
    secrets["first password"] = "first-Secret-pa55word"
    secrets["second password"] = "second-Secret-pa55word"
    with client_for(main_app) as client:
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": secrets["first password"]}
        )
        secrets["verification token"] = await _outbox_token(db_session, email, "verification_email")
        client.post("/api/v1/auth/verify-email", json={"token": secrets["verification token"]})
        client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong-" + secrets["first password"]},
        )
        login(client, email, secrets["first password"])
        for name in ("access_token", "refresh_token", "csrf_token"):
            secrets[name] = client.cookies.get(name) or ""
        client.post("/api/v1/auth/refresh", headers=csrf(client))
        secrets["rotated refresh"] = client.cookies.get("refresh_token") or ""
        client.post("/api/v1/auth/password-reset/request", json={"email": email})
        secrets["reset token"] = await _outbox_token(db_session, email, "password_reset_email")
        client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": secrets["reset token"], "new_password": secrets["second password"]},
        )

    admin = await create_user(db_session, role=UserRole.ADMIN)
    with client_for(main_app) as client:
        login(client, admin.email)
        setup = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(client)
        ).json()
        secrets["totp secret"] = setup["secret"]
        codes = client.post(
            CONFIRM_PATH, json={"code": pyotp.TOTP(setup["secret"]).now()}, headers=csrf(client)
        ).json()["recovery_codes"]
        client.cookies.clear()
        challenge = client.post(
            "/api/v1/auth/login", json={"email": admin.email, "password": PASSWORD}
        ).json()["challenge_id"]
        secrets["mfa challenge"] = challenge
        client.post(
            "/api/v1/auth/mfa/verify", json={"challenge_id": challenge, "recovery_code": codes[0]}
        )
        regenerated = client.post(
            "/api/v1/auth/mfa/recovery-codes/regenerate",
            json={"current_password": PASSWORD},
            headers=csrf(client),
        ).json()["recovery_codes"]
    for n, code in enumerate([*codes, *regenerated]):
        secrets[f"recovery code {n}"] = code
        secrets[f"recovery code {n} (normalised)"] = code.replace("-", "")

    await dispatch_outbox(
        {"session_factory": async_sessionmaker(db_engine, expire_on_commit=False)}
    )

    logs = app_logs.getvalue()
    # Proof the capture works before trusting any absence below: the outbox
    # dispatch must have logged its console sends.
    assert "console_email_send" in logs, "log capture is not working; the test proves nothing"
    leaked = [name for name, value in secrets.items() if value and value in logs]
    assert leaked == [], leaked


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_database_error_never_logs_personal_data_or_credentials(
    make_app: Callable[[], FastAPI],
    app_logs: io.StringIO,
) -> None:
    """BUG-40. A unique violation's message carries the SQL parameters (email,
    Argon2 hash) and the constraint DETAIL ("Key (email)=(...)"). None of it may
    reach the log - while the exception type, which the operator needs, must.

    The error is produced deliberately by a test-only route rather than by the
    registration race, so this guarantee does not depend on BUG-01 existing."""
    email = unique_email()
    password_hash = hash_password("a-password-that-must-not-leak")
    app = make_app()

    @app.post("/__deep_duplicate_user")
    async def duplicate(session: AsyncSession = Depends(get_session)) -> None:
        for _ in range(2):
            session.add(UserModel(email=email, password_hash=password_hash))
            await session.flush()

    async with running_app(lambda: app) as running, async_client(running) as client:
        response = await client.post("/__deep_duplicate_user")
    assert response.status_code == 500
    logs = app_logs.getvalue()
    assert "unhandled_exception" in logs, "log capture is not working; the test proves nothing"
    assert "IntegrityError" in logs, "redaction must keep the exception type for the operator"
    assert password_hash not in logs
    assert "$argon2id$" not in logs
    assert email not in logs
    assert "[parameters:" not in logs


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/auth/login", {"email": "x@example.com", "password": "p" * 300}),
        (
            "POST",
            "/api/v1/auth/register",
            {"email": "not-an-email", "password": "Secret-in-422-body"},
        ),
        ("POST", "/api/v1/auth/password-reset/confirm", {"token": "t", "new_password": "Zq9!xW"}),
        ("POST", "/api/v1/auth/mfa/setup", {"current_password": "Secret-in-401-body"}),
    ],
    ids=["login-422", "register-422", "reset-422", "mfa-401"],
)
def test_error_bodies_never_echo_the_submitted_secret(
    method: str, path: str, body: dict[str, Any]
) -> None:
    """Pydantic's default error entries carry an `input` field; the error
    handler must not pass it through, or a validation error echoes the password
    straight back (and into any response logging)."""
    with client_for(main_app) as client:
        response = client.request(method, path, json=body)
    secret = next(v for k, v in body.items() if "password" in k)
    assert secret not in response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_admin_boundary_refusals_log_no_email_token_cookie_or_csrf_value(
    db_session: AsyncSession, app_logs: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    """401, 404, 405, 409 and 429 on the admin surface (VS-011) are all refusals
    a hostile caller can provoke; none may write a secret to the log."""
    import app.api.v1.admin as admin_module

    monkeypatch.setattr(admin_module, "ADMIN_RATE_LIMIT", 8)
    customer = await create_user(db_session)
    no_mfa = await create_user(db_session, role=UserRole.ADMIN)
    secrets: dict[str, str] = {}

    with client_for(main_app) as client:
        assert client.get("/api/v1/admin/users").status_code == 401
        login(client, customer.email)
        assert client.get("/api/v1/admin/users/").status_code == 404
        assert client.delete("/api/v1/admin/settings").status_code == 404
        client.cookies.clear()
        login(client, no_mfa.email)
        assert client.get("/api/v1/admin/users").status_code == 401
        client.cookies.clear()

        admin, _, _ = await mfa_admin(client, db_session)
        await db_session.execute(
            update(UserModel)
            .where(UserModel.role == UserRole.ADMIN, UserModel.id != admin.id)
            .values(is_active=False)
        )
        await db_session.commit()
        for name in ("access_token", "refresh_token", "csrf_token"):
            secrets[name] = client.cookies.get(name) or ""
        secrets["admin email"] = admin.email
        secrets["customer email"] = customer.email
        secrets["no-mfa email"] = no_mfa.email

        assert client.post("/api/v1/admin/settings", headers=csrf(client)).status_code == 405
        assert client.get("/api/v1/admin/nothing-here").status_code == 404
        refused = client.patch(
            f"/api/v1/admin/users/{admin.id}", json={"is_active": False}, headers=csrf(client)
        )
        assert refused.status_code == 409
        statuses = [client.get("/api/v1/admin/nothing-here").status_code for _ in range(12)]
        assert 429 in statuses

    logs = app_logs.getvalue()
    assert "last_active_administrator_protected" in logs, "log capture proves nothing without it"
    leaked = [name for name, value in secrets.items() if value and value in logs]
    assert leaked == [], leaked


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_vs011_adversarial_requests_log_no_email_token_cookie_or_csrf_value(
    db_session: AsyncSession, app_logs: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The VS-011 verification's hostile inputs - path fuzz, unlisted methods,
    malformed bodies, a database failure inside the last-administrator guard and
    a rate-limit burst - with every credential the callers hold, then a scan of
    everything logged. The DB failure must log `dependency_unavailable` (proof the
    capture works) and nothing of the driver's message."""
    import sqlalchemy.exc

    import app.api.v1.admin as admin_module
    from app.identity.infrastructure.repositories import UserRepository

    monkeypatch.setattr(admin_module, "ADMIN_RATE_LIMIT", 15)
    leaky = "SELECT 1 -- user=leakuser@example.com"

    async def broken(*_args: Any, **_kwargs: Any) -> int:
        raise sqlalchemy.exc.OperationalError(leaky, {}, Exception("leakuser@example.com"))

    customer = await create_user(db_session)
    secrets: dict[str, str] = {"customer email": customer.email, "driver text": "leakuser"}
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, customer.email)
        for name in ("access_token", "refresh_token", "csrf_token"):
            secrets[f"customer {name}"] = client.cookies.get(name) or ""
        for path in (
            "/api/v1/admin%2Fsettings",
            "/api/v1/admin/settings/%FF%FE",
            "/api/v1/admin/settings%00",
            "/api/v1/admin/" + "a" * 8192,
        ):
            client.get(path)
        client.request("TRACE", "/api/v1/admin/settings", headers=csrf(client))
        client.post(
            "/api/v1/admin/categories",
            content=b"{bad",
            headers={**csrf(client), "Content-Type": "application/json"},
        )
        client.cookies.clear()

        admin, _, _ = await mfa_admin(client, db_session)
        other = await create_user(db_session, role=UserRole.ADMIN)
        secrets["admin email"] = admin.email
        secrets["other admin email"] = other.email
        for name in ("access_token", "refresh_token", "csrf_token"):
            secrets[f"admin {name}"] = client.cookies.get(name) or ""
        monkeypatch.setattr(UserRepository, "count_other_active_administrators", broken)
        failed = client.patch(
            f"/api/v1/admin/users/{other.id}", json={"is_active": False}, headers=csrf(client)
        )
        assert failed.status_code == 503
        statuses = [client.get("/api/v1/admin/nothing").status_code for _ in range(20)]
        assert 429 in statuses

    logs = app_logs.getvalue()
    assert "dependency_unavailable" in logs, "log capture proves nothing without it"
    leaked = [name for name, value in secrets.items() if value and value in logs]
    assert leaked == [], leaked
