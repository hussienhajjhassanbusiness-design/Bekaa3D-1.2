"""VS-011 / BUG-38: refusing to leave the system with no active administrator.

The HTTP behaviour (409 INVALID_STATE_TRANSITION) is also covered by
`test_deep_vs009_admin_users.py::test_the_last_active_administrator_cannot_be_deactivated`;
these tests pin the rule's edges and what a refusal leaves behind.

`SetUserActive` is the only code path in V1 that can reduce the active
administrator count: there is no role change, no account deletion and no
anonymisation of administrators, and the unverified-account purge is limited to
customers (`test_purge_unverified.py`).
"""

import uuid
from typing import Any

import pytest
import sqlalchemy.exc
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import SessionModel, UserModel
from app.identity.infrastructure.repositories import UserRepository
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import assert_problem, client_for, create_user, csrf, mfa_admin

USERS = "/api/v1/admin/users"


async def _stand_down_other_admins(db: AsyncSession, keep: list[uuid.UUID]) -> None:
    await db.execute(
        update(UserModel)
        .where(UserModel.role == UserRole.ADMIN, UserModel.id.not_in(keep))
        .values(is_active=False)
    )
    await db.commit()


async def _audit_count(db: AsyncSession, entity_id: uuid.UUID) -> int:
    db.expire_all()
    return int(
        await db.scalar(
            select(func.count())
            .select_from(AuditLogModel)
            .where(AuditLogModel.entity_id == entity_id)
        )
        or 0
    )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_sole_administrator_cannot_deactivate_themselves_and_nothing_changes(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        admin_id = admin.id
        await _stand_down_other_admins(db_session, [admin_id])
        audit_before = await _audit_count(db_session, admin_id)

        refused = client.patch(
            f"{USERS}/{admin_id}", json={"is_active": False}, headers=csrf(client)
        )
        # Counted before the read below, which is itself audited (BUG-39).
        audit_after_refusal = await _audit_count(db_session, admin_id)
        # Still signed in: nothing was revoked, so the same session still works.
        still_in = client.get(f"{USERS}/{admin_id}")

    assert_problem(refused, 409, "INVALID_STATE_TRANSITION")
    assert still_in.status_code == 200
    db_session.expire_all()
    row = await db_session.scalar(select(UserModel).where(UserModel.id == admin_id))
    assert row is not None and row.is_active is True and row.auth_epoch == 0
    live = await db_session.scalar(
        select(func.count())
        .select_from(SessionModel)
        .where(SessionModel.user_id == admin_id, SessionModel.revoked_at.is_(None))
    )
    assert live and live >= 1, "the refusal must not revoke sessions"
    assert audit_after_refusal == audit_before, "no audit row"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_unrelated_changes_are_unaffected_while_only_one_administrator_is_active(
    db_session: AsyncSession,
) -> None:
    """Deactivating a customer, or reactivating an administrator, is unaffected
    even when exactly one administrator is active."""
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        await _stand_down_other_admins(db_session, [admin.id])
        customer = await create_user(db_session)
        dormant = await create_user(db_session, role=UserRole.ADMIN, active=False)

        off = client.patch(
            f"{USERS}/{customer.id}", json={"is_active": False}, headers=csrf(client)
        )
        on = client.patch(f"{USERS}/{dormant.id}", json={"is_active": True}, headers=csrf(client))
        already_off = client.patch(
            f"{USERS}/{customer.id}", json={"is_active": False}, headers=csrf(client)
        )

    assert off.status_code == 200 and off.json()["is_active"] is False
    assert on.status_code == 200 and on.json()["is_active"] is True
    assert already_off.status_code == 200, "restating an inactive state is a no-op, not a refusal"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_administrator_can_be_deactivated_while_another_remains(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        other = await create_user(db_session, role=UserRole.ADMIN)
        await _stand_down_other_admins(db_session, [admin.id, other.id])

        response = client.patch(
            f"{USERS}/{other.id}", json={"is_active": False}, headers=csrf(client)
        )
        # Now `admin` is the last one: deactivating themselves is refused.
        last = client.patch(f"{USERS}/{admin.id}", json={"is_active": False}, headers=csrf(client))

    assert response.status_code == 200 and response.json()["is_active"] is False
    assert_problem(last, 409, "INVALID_STATE_TRANSITION")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_inactive_and_anonymised_administrators_do_not_count_as_remaining(
    db_session: AsyncSession,
) -> None:
    from datetime import UTC, datetime

    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        inactive = await create_user(db_session, role=UserRole.ADMIN, active=False)
        anonymised = await create_user(db_session, role=UserRole.ADMIN)
        await db_session.execute(
            update(UserModel)
            .where(UserModel.id == anonymised.id)
            .values(anonymized_at=datetime.now(UTC))
        )
        await db_session.commit()
        await _stand_down_other_admins(db_session, [admin.id, inactive.id, anonymised.id])

        response = client.patch(
            f"{USERS}/{admin.id}", json={"is_active": False}, headers=csrf(client)
        )
    assert_problem(response, 409, "INVALID_STATE_TRANSITION")


_LEAKY = "SELECT count(*) FROM users WHERE role='admin' -- host=10.9.8.7 user=leakuser"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (
            sqlalchemy.exc.OperationalError(_LEAKY, {}, Exception("conn refused")),
            503,
            "SERVICE_UNAVAILABLE",
        ),
        (sqlalchemy.exc.ProgrammingError(_LEAKY, {}, Exception("syntax")), 500, "INTERNAL_ERROR"),
    ],
    ids=["operational", "programming"],
)
async def test_a_database_error_inside_the_guard_changes_nothing_and_leaks_nothing(
    error: Exception,
    status: int,
    code: str,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure injection between the advisory lock and the write: the request's
    transaction rolls back, so the target is untouched and no audit row exists,
    and the problem document carries none of the driver's text."""

    async def broken(*_args: Any, **_kwargs: Any) -> int:
        raise error

    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        other_id = (await create_user(db_session, role=UserRole.ADMIN)).id
        audit_before = await _audit_count(db_session, other_id)
        monkeypatch.setattr(UserRepository, "count_other_active_administrators", broken)
        response = client.patch(
            f"{USERS}/{other_id}", json={"is_active": False}, headers=csrf(client)
        )

    assert_problem(response, status, code)
    for leak in ("leakuser", "10.9.8.7", "SELECT", "count(*)", "syntax", "refused"):
        assert leak not in response.text, leak
    db_session.expire_all()
    row = await db_session.scalar(select(UserModel).where(UserModel.id == other_id))
    assert row is not None and row.is_active is True and row.auth_epoch == 0
    assert await _audit_count(db_session, other_id) == audit_before
