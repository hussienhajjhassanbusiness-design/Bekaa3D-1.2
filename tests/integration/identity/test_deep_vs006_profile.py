"""VS-006 deep edge cases: GET /api/v1/me for every kind of caller and account state."""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import UserModel
from app.main import app as main_app
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)

ME = "/api/v1/me"
CONTRACT = {"id", "email", "role", "email_verified", "email_verified_at", "created_at"}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("kind", ["unverified", "verified", "admin-without-mfa", "admin-with-mfa"])
async def test_every_live_account_reads_exactly_its_own_contract_fields(
    kind: str, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        if kind == "admin-with-mfa":
            user, _, _ = await mfa_admin(client, db_session)
        else:
            user = await create_user(
                db_session,
                verified=kind != "unverified",
                role=UserRole.ADMIN if kind.startswith("admin") else UserRole.CUSTOMER,
            )
            login(client, user.email)
        body = client.get(ME).json()
    assert set(body) == CONTRACT
    assert body["id"] == str(user.id)
    assert body["email_verified"] is (kind != "unverified")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("state", ["deactivated", "anonymised", "soft-deleted", "hard-deleted"])
async def test_a_live_token_stops_reading_the_profile_the_moment_the_account_ends(
    state: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    uid = user.id
    with client_for(main_app) as client:
        login(client, user.email)
        assert client.get(ME).status_code == 200
        now = datetime.now(UTC)
        if state == "hard-deleted":
            await db_session.execute(delete(UserModel).where(UserModel.id == uid))
        else:
            by_state: dict[str, dict[str, Any]] = {
                "deactivated": {"is_active": False},
                "anonymised": {"anonymized_at": now},
                "soft-deleted": {"deleted_at": now},
            }
            values = by_state[state]
            await db_session.execute(update(UserModel).where(UserModel.id == uid).values(**values))
        await db_session.commit()
        response = client.get(ME)
    assert_problem(response, 401, "AUTH_REQUIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_verification_shows_up_immediately_without_a_new_token(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session, verified=False)
    uid = user.id
    with client_for(main_app) as client:
        login(client, user.email)
        assert client.get(ME).json()["email_verified"] is False
        await db_session.execute(
            update(UserModel).where(UserModel.id == uid).values(email_verified_at=datetime.now(UTC))
        )
        await db_session.commit()
        assert client.get(ME).json()["email_verified"] is True


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_query_parameters_cannot_select_someone_else(db_session: AsyncSession) -> None:
    me = await create_user(db_session)
    other = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, me.email)
        for query in (f"?id={other.id}", f"?user_id={other.id}", f"?email={other.email}"):
            body = client.get(ME + query).json()
            assert body["id"] == str(me.id), query


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("method", ["PUT", "PATCH", "POST"])
async def test_the_profile_has_no_write_path_whatever_the_body(
    method: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    uid = user.id
    with client_for(main_app) as client:
        login(client, user.email)
        response = client.request(
            method, ME, json={"role": "admin", "email": "hijack@example.com"}, headers=csrf(client)
        )
    assert_problem(response, 405, "METHOD_NOT_ALLOWED")
    db_session.expire_all()
    row = await db_session.get(UserModel, uid)
    assert row is not None and row.role is UserRole.CUSTOMER


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_delete_takes_only_the_current_password(db_session: AsyncSession) -> None:
    """VS-045 added `DELETE /me`; a hijack body is a 422 and changes nothing."""
    user = await create_user(db_session)
    uid = user.id
    with client_for(main_app) as client:
        login(client, user.email)
        response = client.request(
            "DELETE",
            ME,
            json={"role": "admin", "email": "hijack@example.com"},
            headers=csrf(client),
        )
    assert_problem(response, 422, "VALIDATION_ERROR")
    db_session.expire_all()
    row = await db_session.get(UserModel, uid)
    assert row is not None and row.role is UserRole.CUSTOMER and row.anonymized_at is None
