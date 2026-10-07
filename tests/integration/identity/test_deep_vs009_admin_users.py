"""VS-009 deep edge cases: admin user management."""

import asyncio
import base64
import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pyotp
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import SessionModel, UserModel
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import (
    CONFIRM_PATH,
    PASSWORD,
    SETUP_PATH,
    assert_problem,
    async_client,
    client_for,
    create_user,
    csrf,
    mfa_admin,
    running_app,
)

USERS = "/api/v1/admin/users"


def _cursor(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty"),
        pytest.param({"is_active": None}, id="null"),
        pytest.param({"is_active": []}, id="array"),
        pytest.param({"is_active": "maybe"}, id="word"),
        pytest.param({"is_active": 2}, id="two"),
        pytest.param({"is_active": False, "role": "admin"}, id="role"),
        pytest.param({"is_active": False, "email": "x@example.com"}, id="email"),
        pytest.param({"is_active": False, "auth_epoch": 0}, id="epoch"),
    ],
)
async def test_patch_body_shapes_are_422_and_change_nothing(
    body: dict[str, Any], db_session: AsyncSession
) -> None:
    target = await create_user(db_session)
    tid = target.id
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.patch(f"{USERS}/{tid}", json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")
    db_session.expire_all()
    row = await db_session.get(UserModel, tid)
    assert row is not None and row.is_active is True and row.role is UserRole.CUSTOMER


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("user_id", "status"),
    [("not-a-uuid", 422), (str(uuid.uuid4()), 404), ("00000000-0000-0000-0000-000000000000", 404)],
    ids=["not-uuid", "random", "nil"],
)
async def test_id_shapes_for_an_administrator(
    user_id: str, status: int, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        read = client.get(f"{USERS}/{user_id}")
        write = client.patch(f"{USERS}/{user_id}", json={"is_active": False}, headers=csrf(client))
    assert read.status_code == write.status_code == status


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("search", "status"),
    [
        # Control characters are refused in every query parameter (BUG-03).
        pytest.param("\u0001", 422, id="control-char"),
        pytest.param("‮", 200, id="rtl-override"),
        pytest.param("\U0001f600", 200, id="emoji"),
        pytest.param("a" * 254, 200, id="254"),
        pytest.param("a" * 255, 422, id="255"),
        pytest.param("' OR ''='", 200, id="sql"),
        pytest.param("\\", 200, id="backslash"),
    ],
)
async def test_search_shapes(search: str, status: int, db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(USERS, params={"search": search})
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_out_of_range_cursor_is_a_client_error(db_session: AsyncSession) -> None:
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = client.get(
            USERS, params={"cursor": _cursor(f"0001-01-01T00:00:00+14:00|{uuid.uuid4()}")}
        )
    assert_problem(response, 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------
# The last administrator
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_last_active_administrator_cannot_be_deactivated(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        admin_id = admin.id
        # Other administrators in this shared test database are leftovers from
        # earlier tests; standing them down makes this one the last.
        await db_session.execute(
            update(UserModel)
            .where(UserModel.role == UserRole.ADMIN, UserModel.id != admin_id)
            .values(is_active=False)
        )
        await db_session.commit()
        response = client.patch(
            f"{USERS}/{admin_id}", json={"is_active": False}, headers=csrf(client)
        )
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")


# --------------------------------------------------------------------------
# PII access
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_admin_reads_of_account_pii_are_audited(db_session: AsyncSession) -> None:
    target = await create_user(db_session)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        request_ids = [
            client.get(USERS, params={"search": target.email[:12]}).headers["x-request-id"],
            client.get(f"{USERS}/{target.id}").headers["x-request-id"],
        ]
    db_session.expire_all()
    audited = await db_session.scalar(
        select(func.count())
        .select_from(AuditLogModel)
        .where(AuditLogModel.request_id.in_(request_ids))
    )
    assert audited == 2


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_pii_read_audit_rows_name_the_admin_and_hold_no_pii(
    db_session: AsyncSession,
) -> None:
    """BUG-39: the rows say who looked, and at what, but never what they typed or
    saw - an audit row with the searched address in it would just move the leak
    from the server log into the database."""
    target = await create_user(db_session)
    target_id, fragment = target.id, target.email[:12]
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        admin_id = admin.id
        listed = client.get(USERS, params={"search": fragment, "active": "true"})
        read = client.get(f"{USERS}/{target_id}")
    assert listed.status_code == read.status_code == 200
    db_session.expire_all()
    rows = {
        row.request_id: row
        for row in await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.request_id.in_(
                    [listed.headers["x-request-id"], read.headers["x-request-id"]]
                )
            )
        )
    }
    listing = rows[listed.headers["x-request-id"]]
    assert (listing.action, listing.entity_type, listing.entity_id) == (
        "user.list_viewed",
        "user",
        None,
    )
    assert listing.after_data == {
        "filters": {"verified": None, "active": True, "search": True},
        "result_count": len(listed.json()["items"]),
    }
    detail = rows[read.headers["x-request-id"]]
    assert (detail.action, detail.entity_type, detail.entity_id) == (
        "user.viewed",
        "user",
        target_id,
    )
    for row in (listing, detail):
        assert row.actor_user_id == admin_id
        assert row.ip_hash is not None
        stored = f"{row.before_data}{row.after_data}"
        assert "@" not in stored and fragment not in stored


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reading_an_unknown_account_writes_no_audit_row(db_session: AsyncSession) -> None:
    """A 404 discloses nothing, so there is no PII access to record."""
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        missing = client.get(f"{USERS}/{uuid.uuid4()}")
    assert_problem(missing, 404, "NOT_FOUND")
    db_session.expire_all()
    audited = await db_session.scalar(
        select(func.count())
        .select_from(AuditLogModel)
        .where(AuditLogModel.request_id == missing.headers["x-request-id"])
    )
    assert audited == 0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def _uvicorn(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """The real app under a real uvicorn, logging exactly as it would in
    production; yields its base URL and the file its output goes to. The
    access log is uvicorn's own, so only a real server proves BUG-39."""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log = tmp_path / "uvicorn.log"
    env = {
        **os.environ,
        "DATABASE_URL": get_settings().database_url,
        "REDIS_URL": get_settings().redis_url,
    }
    with log.open("w") as sink:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--port",
                str(port),
                "--app-dir",
                "src",
            ],
            stdout=sink,
            stderr=subprocess.STDOUT,
            env=env,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    if httpx.get(f"{base}/health/live", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.2)
            yield base, log
            time.sleep(0.5)
        finally:
            server.terminate()
            server.wait(timeout=10)
    assert "/health/live" in log.read_text(errors="replace"), (
        "the server never came up; the test proves nothing"
    )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_an_admin_email_search_never_reaches_the_server_log(tmp_path: Path) -> None:
    with _uvicorn(tmp_path) as (base, log):
        httpx.get(f"{base}{USERS}", params={"search": "victim.person@example.com"})
    assert "victim.person" not in log.read_text(errors="replace")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_authenticated_admin_email_search_never_reaches_the_server_log(
    tmp_path: Path, db_session: AsyncSession
) -> None:
    """The anonymous search above is answered 401. This one is the real case: an
    MFA-complete administrator searches by a full address, gets a 200 with the
    account in it, and the line uvicorn logs for it still has no query string."""
    target = await create_user(db_session)
    admin = await create_user(db_session, role=UserRole.ADMIN)
    searched, admin_email = target.email, admin.email
    with _uvicorn(tmp_path) as (base, log):
        async with httpx.AsyncClient(base_url=base) as client:
            signed_in = await client.post(
                "/api/v1/auth/login", json={"email": admin_email, "password": PASSWORD}
            )
            assert signed_in.status_code == 200, signed_in.text
            setup = await client.post(
                SETUP_PATH,
                json={"current_password": PASSWORD},
                headers={"X-CSRF-Token": client.cookies["csrf_token"]},
            )
            assert setup.status_code == 200, setup.text
            confirm = await client.post(
                CONFIRM_PATH,
                json={"code": pyotp.TOTP(setup.json()["secret"]).now()},
                headers={"X-CSRF-Token": client.cookies["csrf_token"]},
            )
            assert confirm.status_code == 200, confirm.text
            found = await client.get(USERS, params={"search": searched})
    assert found.status_code == 200, found.text
    assert [item["email"] for item in found.json()["items"]] == [searched]
    text = log.read_text(errors="replace")
    assert f'"GET {USERS} HTTP/1.1" 200' in text, "the admin search was not logged at all"
    assert searched.split("@")[0] not in text


# --------------------------------------------------------------------------
# Deactivation reach and races
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_deactivation_kills_every_device_at_once(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    target = await create_user(db_session)
    tid, email = target.id, target.email
    async with running_app(make_app) as app:
        devices = [async_client(app) for _ in range(5)]
        try:
            for device in devices:
                await device.post(
                    "/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
                )
                assert (await device.get("/api/v1/me")).status_code == 200
            with client_for(main_app) as admin:
                await mfa_admin(admin, db_session)
                assert (
                    admin.patch(
                        f"{USERS}/{tid}", json={"is_active": False}, headers=csrf(admin)
                    ).status_code
                    == 200
                )
            statuses = [(await d.get("/api/v1/me")).status_code for d in devices]
            refreshes = [
                (await d.post("/api/v1/auth/refresh", headers=csrf(d))).status_code for d in devices
            ]
        finally:
            for d in devices:
                await d.aclose()
    assert statuses == [401] * 5
    assert refreshes == [401] * 5
    db_session.expire_all()
    live = await db_session.scalar(
        select(func.count())
        .select_from(SessionModel)
        .where(SessionModel.user_id == tid, SessionModel.revoked_at.is_(None))
    )
    assert live == 0


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_twenty_parallel_toggles_keep_audit_and_epoch_in_step(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    target = await create_user(db_session)
    tid = target.id
    async with running_app(make_app) as app:
        with client_for(main_app) as enrol:
            await mfa_admin(enrol, db_session)
            cookies = dict(enrol.cookies.items())
        clients = [async_client(app) for _ in range(20)]
        for c in clients:
            for name, value in cookies.items():
                c.cookies.set(name, value)
        wanted = [n % 3 != 0 for n in range(20)]
        try:
            responses = await asyncio.gather(
                *(
                    c.patch(
                        f"{USERS}/{tid}",
                        json={"is_active": want},
                        headers={"X-CSRF-Token": cookies["csrf_token"]},
                    )
                    for c, want in zip(clients, wanted, strict=True)
                )
            )
        finally:
            for c in clients:
                await c.aclose()
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    db_session.expire_all()
    row = await db_session.get(UserModel, tid)
    assert row is not None
    audits = (
        await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.entity_id == tid,
                AuditLogModel.action.in_(["user.activated", "user.deactivated"]),
            )
        )
    ).all()
    deactivations = sum(a.action == "user.deactivated" for a in audits)
    activations = len(audits) - deactivations
    assert row.auth_epoch == deactivations, "each real deactivation advances the epoch exactly once"
    # Transitions alternate from an active start, so the counts tell the end state.
    assert deactivations - activations in (0, 1)
    assert row.is_active is (deactivations == activations)
    for audit in audits:
        assert audit.before_data is not None and audit.after_data is not None
        assert audit.before_data["is_active"] != audit.after_data["is_active"]
