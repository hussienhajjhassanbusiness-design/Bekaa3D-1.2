"""BR-132, ADR-050: a refused login leaves one counted audit row per account, IP and 15 minutes,
in its own transaction, so the request's rollback cannot erase it."""

import uuid
from typing import Any

import pyotp
import pytest
import redis.asyncio as redis_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.identity.application.services.login_throttle import LOCKOUT_AT_ATTEMPT, LoginThrottle
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from app.platform.infrastructure.repositories import AuditLogRepository
from tests.integration.deep_support import (
    PASSWORD,
    client_for,
    create_user,
    fresh_ip,
    mfa_admin,
    unique_email,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]
LOGIN = "/api/v1/auth/login"
ACTION = "user.login_failed"


def _fail(ip: str, email: str, times: int = 1, password: str = "wrong-password-1") -> Any:
    with client_for(main_app, ip) as client:
        for _ in range(times):
            response = client.post(LOGIN, json={"email": email, "password": password})
    return response


async def _rows(db: AsyncSession, entity_id: uuid.UUID | None = None) -> list[AuditLogModel]:
    await db.commit()
    stmt = select(AuditLogModel).where(AuditLogModel.action == ACTION)
    if entity_id is not None:
        stmt = stmt.where(AuditLogModel.entity_id == entity_id)
    return list((await db.scalars(stmt.order_by(AuditLogModel.created_at))).all())


async def test_a_wrong_password_commits_a_row_despite_the_401(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    response = _fail(fresh_ip(), user.email)
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"
    (row,) = await _rows(db_session, user.id)
    assert (row.actor_user_id, row.entity_type) == (None, "User")
    assert row.ip_hash is not None
    assert row.request_id == response.headers["x-request-id"]
    assert row.after_data is not None
    assert (row.after_data["count"], row.after_data["reasons"]) == (1, {"invalid_credentials": 1})


async def test_repeats_from_one_ip_count_on_one_row(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    _fail(fresh_ip(), user.email, times=3)
    (row,) = await _rows(db_session, user.id)
    assert row.after_data is not None
    assert row.after_data["count"] == 3
    assert row.after_data["reasons"] == {"invalid_credentials": 3}
    assert row.after_data["last_failed_at"] >= row.created_at.isoformat()


async def test_another_ip_gets_its_own_row(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    _fail(fresh_ip(), user.email)
    _fail(fresh_ip(), user.email)
    rows = await _rows(db_session, user.id)
    assert [r.after_data["count"] for r in rows if r.after_data] == [1, 1]
    assert len({r.ip_hash for r in rows}) == 2


async def test_a_new_row_starts_once_the_window_has_passed(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    ip = fresh_ip()
    _fail(ip, user.email)
    await db_session.execute(
        text(
            "UPDATE audit_logs SET created_at = created_at - interval '16 minutes'"
            " WHERE action = :a AND entity_id = :e"
        ),
        {"a": ACTION, "e": user.id},
    )
    await db_session.commit()
    _fail(ip, user.email)
    assert [r.after_data["count"] for r in await _rows(db_session, user.id) if r.after_data] == [
        1,
        1,
    ]


async def test_an_unknown_email_is_counted_without_storing_the_address(
    db_session: AsyncSession,
) -> None:
    email = unique_email("nobody")
    ip = fresh_ip()
    before = {r.id for r in await _rows(db_session)}
    assert _fail(ip, email).status_code == 401
    assert _fail(ip, unique_email("nobody2")).status_code == 401
    (row,) = [r for r in await _rows(db_session) if r.id not in before]
    assert row.entity_id is None
    assert row.after_data is not None
    assert row.after_data["count"] == 2
    assert email not in str(row.after_data)


async def test_a_correct_password_writes_no_failure_row(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    assert _fail(fresh_ip(), user.email, password=PASSWORD).status_code == 200
    assert await _rows(db_session, user.id) == []


async def test_a_locked_out_attempt_is_counted(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    ip = fresh_ip()
    redis = redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    await redis.set(LoginThrottle._key(user.email, ip), LOCKOUT_AT_ATTEMPT)
    await redis.aclose()
    assert _fail(ip, user.email).status_code == 429
    (row,) = await _rows(db_session, user.id)
    assert row.after_data is not None
    assert row.after_data["reasons"] == {"locked_out": 1}


async def test_a_disabled_account_is_counted_with_the_same_403(db_session: AsyncSession) -> None:
    user = await create_user(db_session, active=False)
    response = _fail(fresh_ip(), user.email, password=PASSWORD)
    assert (response.status_code, response.json()["code"]) == (403, "ACCOUNT_DISABLED")
    (row,) = await _rows(db_session, user.id)
    assert row.after_data is not None
    assert row.after_data["reasons"] == {"account_disabled": 1}


async def test_a_wrong_second_factor_is_counted(db_session: AsyncSession) -> None:
    ip = fresh_ip()
    with client_for(main_app, ip) as client:
        admin, secret, _ = await mfa_admin(client, db_session)
        client.cookies.clear()
        challenge = client.post(LOGIN, json={"email": admin.email, "password": PASSWORD})
        assert challenge.status_code == 202, challenge.text
        real = pyotp.TOTP(secret).now()
        wrong = "000000" if real != "000000" else "111111"
        refused = client.post(
            "/api/v1/auth/mfa/verify",
            json={"challenge_id": challenge.json()["challenge_id"], "code": wrong},
        )
    assert refused.status_code == 401
    (row,) = await _rows(db_session, admin.id)
    assert row.after_data is not None
    assert row.after_data["reasons"] == {"mfa_invalid": 1}


async def test_a_failing_audit_write_does_not_change_the_answer(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("audit storage is down")

    monkeypatch.setattr(AuditLogRepository, "count_in_window", broken)
    user = await create_user(db_session)
    response = _fail(fresh_ip(), user.email)
    assert (response.status_code, response.json()["code"]) == (401, "INVALID_CREDENTIALS")
    assert await _rows(db_session, user.id) == []


async def test_an_account_disabled_between_the_two_login_steps_is_counted(
    db_session: AsyncSession,
) -> None:
    ip = fresh_ip()
    with client_for(main_app, ip) as client:
        admin, _secret, codes = await mfa_admin(client, db_session)
        admin_id = admin.id
        client.cookies.clear()
        challenge = client.post(LOGIN, json={"email": admin.email, "password": PASSWORD})
        assert challenge.status_code == 202, challenge.text
        await db_session.execute(
            text("UPDATE users SET is_active = false WHERE id = :u"), {"u": admin_id}
        )
        await db_session.commit()
        refused = client.post(
            "/api/v1/auth/mfa/verify",
            json={"challenge_id": challenge.json()["challenge_id"], "recovery_code": codes[0]},
        )
    assert (refused.status_code, refused.json()["code"]) == (403, "ACCOUNT_DISABLED")
    (row,) = await _rows(db_session, admin_id)
    assert row.after_data is not None
    assert row.after_data["reasons"] == {"account_disabled": 1}
