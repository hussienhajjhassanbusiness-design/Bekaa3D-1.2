"""`/api/v1/admin/users`: the VS-009 account-management surface.

The admin boundary itself is not re-implemented by these routes - the router
inherits `require_admin` - so the first group of tests checks that it is
genuinely inherited, and the rest concentrate on what is new: filtering, cursor
pagination, the activation state machine, and the revocation and audit side
effects of a deactivation.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import REFRESH_COOKIE_PATH
from app.identity.infrastructure.models import SessionModel, UserModel
from app.identity.infrastructure.repositories import SessionRepository
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.identity.test_login import (
    PASSWORD,
    cookie_value,
    register_and_verify,
)
from tests.integration.identity.test_mfa_enrollment import (
    csrf_headers,
    enrol_admin,
    login,
    login_challenged,
    login_totp,
    make_admin,
    unique_email,
)

USERS_PATH = "/api/v1/admin/users"
VERIFY_PATH = "/api/v1/auth/mfa/verify"

# Python's cookiejar appends ".local" to a dotless host, so the jar keys the
# TestClient's "testserver" cookies under this domain.
TEST_DOMAIN = "testserver.local"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


async def admin_session(client: TestClient, db_session: AsyncSession) -> uuid.UUID:
    """An administrator with a fully MFA-complete session.

    One MFA login per test on purpose: `login_totp` returns a code for a single
    time-step and VS-005's replay guard correctly refuses the same OTP twice, so
    a second login inside one test would fail for a reason unrelated to VS-009.
    """
    email = unique_email()
    user = await make_admin(client, db_session, email)
    login(client, email)
    secret, _ = enrol_admin(client)
    challenge = login_challenged(client, email)
    completed = client.post(
        VERIFY_PATH, json={"challenge_id": challenge, "code": login_totp(secret)}
    )
    assert completed.status_code == 204, completed.text
    return user.id


async def register_unverified(
    client: TestClient, db_session: AsyncSession, email: str
) -> UserModel:
    """Register without redeeming the verification token."""
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 202, response.text
    user = await db_session.scalar(select(UserModel).where(UserModel.email == email))
    assert user is not None
    return user


def snapshot_cookies(response: Response) -> dict[str, str]:
    """Capture one login's cookies off Set-Cookie, so a second identity can be
    replayed through the single client without a second event loop."""
    cookies = {}
    for name in ("access_token", "refresh_token", "csrf_token"):
        value = cookie_value(response, name)
        assert value is not None, f"login did not set {name}"
        cookies[name] = value
    return cookies


def restore_cookies(client: TestClient, cookies: dict[str, str]) -> None:
    client.cookies.clear()
    client.cookies.set("access_token", cookies["access_token"], domain=TEST_DOMAIN, path="/")
    client.cookies.set("csrf_token", cookies["csrf_token"], domain=TEST_DOMAIN, path="/")
    client.cookies.set(
        "refresh_token", cookies["refresh_token"], domain=TEST_DOMAIN, path=REFRESH_COOKIE_PATH
    )


def patch_active(client: TestClient, user_id: uuid.UUID, *, is_active: bool) -> Response:
    response: Response = client.patch(
        f"{USERS_PATH}/{user_id}",
        json={"is_active": is_active},
        headers=csrf_headers(client),
    )
    return response


async def audit_rows(db_session: AsyncSession, user_id: uuid.UUID) -> list[AuditLogModel]:
    """This slice's audit rows for one account, oldest first.

    Filtered to the two VS-009 actions on purpose. `user.registered` and
    `user.email_verified` already write `entity_type="User"` rows against the
    same id, so an unfiltered query is never empty and "no audit row was
    written" could not be asserted at all.
    """
    db_session.expire_all()
    rows = await db_session.scalars(
        select(AuditLogModel)
        .where(
            AuditLogModel.entity_id == user_id,
            AuditLogModel.entity_type == "User",
            AuditLogModel.action.in_(("user.activated", "user.deactivated")),
        )
        .order_by(AuditLogModel.created_at)
    )
    return list(rows)


async def reload_user(db_session: AsyncSession, user_id: uuid.UUID) -> UserModel:
    db_session.expire_all()
    row = await db_session.scalar(select(UserModel).where(UserModel.id == user_id))
    assert row is not None
    return row


@pytest.fixture
def revoke_spy(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[uuid.UUID]]:
    """Records every `revoke_all_for_user` call, still delegating to the real
    implementation.

    Needed because "reactivation revoked nothing" has no observable trace to
    assert on - the account has no live sessions by then, so the real call would
    also report zero. Only a spy can tell "did not run" from "ran and found
    nothing"."""
    calls: list[uuid.UUID] = []
    original = SessionRepository.revoke_all_for_user

    async def spy(self: SessionRepository, *, user_id: uuid.UUID, at: datetime) -> int:
        calls.append(user_id)
        return await original(self, user_id=user_id, at=at)

    monkeypatch.setattr(SessionRepository, "revoke_all_for_user", spy)
    yield calls


# --------------------------------------------------------------------------
# The admin boundary is inherited, not reimplemented
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_an_unauthenticated_caller_is_told_to_authenticate() -> None:
    from app.main import app

    with TestClient(app) as client:
        client.cookies.clear()
        response = client.get(USERS_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_customer_gets_404_on_every_route(db_session: AsyncSession) -> None:
    """SEC-10: a 403 would confirm the routes exist. All three must hide, not
    just the list - a customer who could tell `PATCH /admin/users/{id}` apart
    from an unimplemented path learns the admin surface by probing it."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

        responses = [
            client.get(USERS_PATH),
            client.get(f"{USERS_PATH}/{user.id}"),
            patch_active(client, user.id, is_active=False),
        ]

    for response in responses:
        assert response.status_code == 404, response.text
        assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_without_completed_mfa_is_refused(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        response = client.get(USERS_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "MFA_REQUIRED"


# --------------------------------------------------------------------------
# List: filters and search
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_search_matches_a_partial_email_case_insensitively(
    db_session: AsyncSession,
) -> None:
    """`email` is CITEXT, so LIKE is already case-insensitive - this is the test
    that would fail if the column type or the predicate ever changed."""
    from app.main import app

    token = uuid.uuid4().hex[:12]
    with TestClient(app) as client:
        wanted = await register_and_verify(client, db_session, f"vs009-{token}-a@example.com")
        await register_and_verify(client, db_session, unique_email())
        client.cookies.clear()
        await admin_session(client, db_session)

        exact = client.get(USERS_PATH, params={"search": token})
        upper = client.get(USERS_PATH, params={"search": token.upper()})

    assert exact.status_code == 200, exact.text
    assert [item["id"] for item in exact.json()["items"]] == [str(wanted.id)]
    assert [item["id"] for item in upper.json()["items"]] == [str(wanted.id)]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_verified_filter_separates_verified_from_unverified(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    token = uuid.uuid4().hex[:12]
    with TestClient(app) as client:
        verified = await register_and_verify(client, db_session, f"vs009-{token}-v@example.com")
        unverified = await register_unverified(client, db_session, f"vs009-{token}-u@example.com")
        client.cookies.clear()
        await admin_session(client, db_session)

        only_verified = client.get(USERS_PATH, params={"search": token, "verified": True})
        only_unverified = client.get(USERS_PATH, params={"search": token, "verified": False})

    assert [i["id"] for i in only_verified.json()["items"]] == [str(verified.id)]
    assert [i["id"] for i in only_unverified.json()["items"]] == [str(unverified.id)]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_active_filter_separates_active_from_deactivated(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    token = uuid.uuid4().hex[:12]
    with TestClient(app) as client:
        stays = await register_and_verify(client, db_session, f"vs009-{token}-on@example.com")
        goes = await register_and_verify(client, db_session, f"vs009-{token}-off@example.com")
        client.cookies.clear()
        await admin_session(client, db_session)
        assert patch_active(client, goes.id, is_active=False).status_code == 200

        active = client.get(USERS_PATH, params={"search": token, "active": True})
        inactive = client.get(USERS_PATH, params={"search": token, "active": False})

    assert [i["id"] for i in active.json()["items"]] == [str(stays.id)]
    assert [i["id"] for i in inactive.json()["items"]] == [str(goes.id)]


# --------------------------------------------------------------------------
# List: cursor pagination
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_cursor_walks_every_row_exactly_once(db_session: AsyncSession) -> None:
    from app.main import app

    token = uuid.uuid4().hex[:12]
    created: list[str] = []
    with TestClient(app) as client:
        for index in range(3):
            user = await register_and_verify(
                client, db_session, f"vs009-{token}-{index}@example.com"
            )
            created.append(str(user.id))
        client.cookies.clear()
        await admin_session(client, db_session)

        seen: list[str] = []
        cursor: str | None = None
        for _ in range(5):  # bounded: a cursor that never terminates fails here
            params: dict[str, Any] = {"search": token, "limit": 2}
            if cursor is not None:
                params["cursor"] = cursor
            page = client.get(USERS_PATH, params=params)
            assert page.status_code == 200, page.text
            body = page.json()
            seen.extend(item["id"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break

    assert cursor is None, "pagination did not terminate"
    # Newest first, so the creation order reverses.
    assert seen == list(reversed(created))


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_malformed_cursor_is_422_not_a_silently_truncated_list(
    db_session: AsyncSession,
) -> None:
    """The VS-007 regression. A tampered cursor was once accepted verbatim, used
    as a raw comparison key, and pagination never terminated - so the failure
    mode under test is a 200, not a 500."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        responses = [
            client.get(USERS_PATH, params={"cursor": "not-a-cursor"}),
            # Valid base64, but not a cursor payload.
            client.get(USERS_PATH, params={"cursor": "Zm9vYmFy"}),
            # Right shape, unparseable timestamp.
            client.get(USERS_PATH, params={"cursor": "bm9wZXxub3Bl"}),
        ]

    for response in responses:
        assert response.status_code == 422, response.text
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert any("cursor" in error["loc"] for error in body["errors"])


# --------------------------------------------------------------------------
# Detail
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_detail_returns_the_account_and_404s_for_an_unknown_id(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        client.cookies.clear()
        await admin_session(client, db_session)

        found = client.get(f"{USERS_PATH}/{user.id}")
        missing = client.get(f"{USERS_PATH}/{uuid.uuid4()}")

    assert found.status_code == 200, found.text
    body = found.json()
    assert body == {
        "id": str(user.id),
        "email": email,
        "role": "customer",
        "is_active": True,
        "email_verified_at": body["email_verified_at"],
        "created_at": body["created_at"],
    }
    assert body["email_verified_at"] is not None

    assert missing.status_code == 404
    assert missing.json()["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------
# PATCH: deactivation ends live access
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_deactivating_revokes_sessions_and_bumps_the_epoch(
    db_session: AsyncSession,
) -> None:
    """`require_admin` and `current_claims` authorise from the token plus the
    epoch and never re-read `is_active`, so without the bump a deactivated
    account keeps working for the rest of its access token's fifteen minutes.
    This is the test that would fail if either half were dropped."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, email)
        signed_in = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert signed_in.status_code == 200
        victim_cookies = snapshot_cookies(signed_in)

        # The token works right up until the deactivation.
        restore_cookies(client, victim_cookies)
        assert client.get("/api/v1/me").status_code == 200

        client.cookies.clear()
        await admin_session(client, db_session)
        before_epoch = (await reload_user(db_session, target.id)).auth_epoch
        response = patch_active(client, target.id, is_active=False)
        assert response.status_code == 200, response.text
        assert response.json()["is_active"] is False

        # Same cookies, which still look perfectly valid to the browser holding
        # them. Immediately, not after the token expires.
        restore_cookies(client, victim_cookies)
        refused = client.get("/api/v1/me")
        # With the header, so this is a 401 about the revocation rather than a
        # 403 about CSRF - refresh checks the token against the refresh cookie's
        # own session precisely because the access token is expected to be dead.
        refreshed = client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": victim_cookies["csrf_token"]}
        )

    assert refused.status_code == 401
    assert refused.json()["code"] == "AUTH_REQUIRED"
    assert refreshed.status_code == 401, refreshed.text

    row = await reload_user(db_session, target.id)
    assert row.is_active is False
    assert row.auth_epoch == before_epoch + 1

    sessions = list(
        await db_session.scalars(select(SessionModel).where(SessionModel.user_id == target.id))
    )
    assert sessions
    assert all(session.revoked_at is not None for session in sessions)
    # A deactivation is a legitimate revocation, not theft detection - marking
    # these as stolen would poison the reuse signal (same rule as VS-004).
    assert all(session.reuse_detected_at is None for session in sessions)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reactivating_touches_neither_sessions_nor_the_epoch(
    db_session: AsyncSession, revoke_spy: list[uuid.UUID]
) -> None:
    """There is nothing to void on the way back up: the deactivation already
    revoked every session, and a revoked session stays revoked."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, email)
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        client.cookies.clear()
        await admin_session(client, db_session)

        assert patch_active(client, target.id, is_active=False).status_code == 200
        after_deactivation = await reload_user(db_session, target.id)
        epoch_after_deactivation = after_deactivation.auth_epoch

        response = patch_active(client, target.id, is_active=True)

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True

    row = await reload_user(db_session, target.id)
    assert row.is_active is True
    assert row.auth_epoch == epoch_after_deactivation

    # Once, for the deactivation. The reactivation must not have called it at
    # all - which is not the same as calling it and finding nothing.
    assert revoke_spy == [target.id]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_no_op_patch_succeeds_and_writes_no_audit_row(
    db_session: AsyncSession, revoke_spy: list[uuid.UUID]
) -> None:
    """Asking for the state the account is already in is not an error - and not
    an event either."""
    from app.main import app

    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, unique_email())
        client.cookies.clear()
        await admin_session(client, db_session)
        before_epoch = (await reload_user(db_session, target.id)).auth_epoch

        response = patch_active(client, target.id, is_active=True)

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is True

    row = await reload_user(db_session, target.id)
    assert row.is_active is True
    assert row.auth_epoch == before_epoch
    assert revoke_spy == []
    assert await audit_rows(db_session, target.id) == []


# --------------------------------------------------------------------------
# PATCH: audit trail
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_audit_trail_records_both_transitions_without_any_pii(
    db_session: AsyncSession,
) -> None:
    """`audit_logs` is retained permanently, so an email address written here
    would outlive the account's own anonymisation and quietly defeat it."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, email)
        client.cookies.clear()
        actor_id = await admin_session(client, db_session)

        assert patch_active(client, target.id, is_active=False).status_code == 200
        assert patch_active(client, target.id, is_active=True).status_code == 200

    rows = await audit_rows(db_session, target.id)
    assert [row.action for row in rows] == ["user.deactivated", "user.activated"]

    deactivated, activated = rows
    assert deactivated.actor_user_id == actor_id
    assert deactivated.entity_type == "User"
    assert deactivated.before_data == {"is_active": True}
    assert deactivated.after_data == {"is_active": False, "sessions_revoked": 0}
    assert activated.before_data == {"is_active": False}
    # `sessions_revoked` is omitted rather than zeroed: it never applies here.
    assert activated.after_data == {"is_active": True}

    local = email.split("@")[0]
    for row in rows:
        payload = f"{row.before_data}{row.after_data}"
        assert email not in payload
        assert local not in payload
        assert "@" not in payload
        # Nothing derived from the credential, at any remove.
        assert "password" not in payload.lower()
        assert "role" not in payload.lower()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_revoked_session_count_reaches_the_audit_row(
    db_session: AsyncSession,
) -> None:
    """The count is what an investigator actually needs: how much access this
    deactivation cut off."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, email)
        for _ in range(2):
            client.cookies.clear()
            signed_in = client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
            assert signed_in.status_code == 200

        client.cookies.clear()
        await admin_session(client, db_session)
        assert patch_active(client, target.id, is_active=False).status_code == 200

    rows = await audit_rows(db_session, target.id)
    assert len(rows) == 1
    assert rows[0].after_data == {"is_active": False, "sessions_revoked": 2}


# --------------------------------------------------------------------------
# PATCH: guards
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_anonymised_account_cannot_be_activated_or_deactivated(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, unique_email())
        row = await db_session.scalar(select(UserModel).where(UserModel.id == target.id))
        assert row is not None
        row.anonymized_at = datetime.now(UTC)
        await db_session.commit()

        client.cookies.clear()
        await admin_session(client, db_session)
        deactivate = patch_active(client, target.id, is_active=False)
        activate = patch_active(client, target.id, is_active=True)

    for response in (deactivate, activate):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "INVALID_STATE_TRANSITION"

    assert await audit_rows(db_session, target.id) == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_soft_deleted_account_cannot_be_activated_or_deactivated(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, unique_email())
        row = await db_session.scalar(select(UserModel).where(UserModel.id == target.id))
        assert row is not None
        row.deleted_at = datetime.now(UTC)
        await db_session.commit()

        client.cookies.clear()
        await admin_session(client, db_session)
        response = patch_active(client, target.id, is_active=False)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_patching_an_unknown_user_is_404(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        response = patch_active(client, uuid.uuid4(), is_active=False)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_no_field_other_than_is_active_is_writable(db_session: AsyncSession) -> None:
    """`extra="forbid"` is the guard. A silently ignored `role` would read as a
    successful privilege change to the caller."""
    from app.main import app

    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, unique_email())
        client.cookies.clear()
        await admin_session(client, db_session)

        rejected = [
            client.patch(
                f"{USERS_PATH}/{target.id}",
                json={"is_active": False, "role": "admin"},
                headers=csrf_headers(client),
            ),
            client.patch(
                f"{USERS_PATH}/{target.id}",
                json={"is_active": False, "email": "attacker@example.com"},
                headers=csrf_headers(client),
            ),
            client.patch(
                f"{USERS_PATH}/{target.id}",
                json={"password": "hunter2hunter2"},
                headers=csrf_headers(client),
            ),
        ]

    for response in rejected:
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "VALIDATION_ERROR"

    row = await reload_user(db_session, target.id)
    assert row.is_active is True
    assert row.role.value == "customer"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_patch_requires_a_csrf_token(db_session: AsyncSession) -> None:
    """SEC-03. The GETs are safe methods and carry no such requirement."""
    from app.main import app

    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, unique_email())
        client.cookies.clear()
        await admin_session(client, db_session)
        response = client.patch(f"{USERS_PATH}/{target.id}", json={"is_active": False})

    assert response.status_code == 403, response.text

    row = await reload_user(db_session, target.id)
    assert row.is_active is True


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_may_deactivate_their_own_account(db_session: AsyncSession) -> None:
    """V1 decision: no self-protection rule. Deactivating yourself ends your own
    session immediately, which is a consequence of the revocation rather than a
    special case in it."""
    from app.main import app

    with TestClient(app) as client:
        actor_id = await admin_session(client, db_session)
        response = patch_active(client, actor_id, is_active=False)
        assert response.status_code == 200, response.text
        # The epoch bump applies to the acting administrator's own token too.
        after = client.get(USERS_PATH)

    assert after.status_code == 401
    assert after.json()["code"] == "AUTH_REQUIRED"

    row = await reload_user(db_session, actor_id)
    assert row.is_active is False
