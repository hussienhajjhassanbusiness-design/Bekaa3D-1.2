"""`/api/v1/admin/settings`: the typed editor behind the VS-005 admin boundary.

The boundary itself is not re-implemented here - the router inherits
`require_admin` - so these tests check that it is genuinely inherited, and then
concentrate on what is new: typed validation, the audit trail, and cursor
pagination.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.domain.settings_registry import REGISTRY
from app.platform.infrastructure.models import AuditLogModel, SettingModel
from app.platform.infrastructure.repositories import AuditLogRepository
from tests.integration.identity.test_login import PASSWORD, register_and_verify
from tests.integration.identity.test_mfa_enrollment import (
    csrf_headers,
    enrol_admin,
    login,
    login_challenged,
    login_totp,
    make_admin,
    unique_email,
)

SETTINGS_PATH = "/api/v1/admin/settings"
VERIFY_PATH = "/api/v1/auth/mfa/verify"


async def _admin_session(client: TestClient, db_session: AsyncSession) -> uuid.UUID:
    """An administrator with a fully MFA-complete session.

    One MFA login per test on purpose: `login_totp` returns a code for a single
    time-step, and VS-005's replay guard correctly refuses to accept the same
    OTP twice, so a second login inside one test would fail for a reason that
    has nothing to do with settings.
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


async def _value_of(db_session: AsyncSession, key: str) -> Any:
    db_session.expire_all()
    row = await db_session.scalar(select(SettingModel).where(SettingModel.key == key))
    assert row is not None
    return row.value


async def _restore(db_session: AsyncSession, key: str) -> None:
    row = await db_session.scalar(select(SettingModel).where(SettingModel.key == key))
    assert row is not None
    row.value = REGISTRY[key].default
    row.updated_by = None
    await db_session.commit()


# --------------------------------------------------------------------------
# The admin boundary is inherited, not reimplemented
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_an_unauthenticated_caller_is_told_to_authenticate() -> None:
    from app.main import app

    with TestClient(app) as client:
        client.cookies.clear()
        response = client.get(SETTINGS_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_customer_gets_404_not_403(db_session: AsyncSession) -> None:
    """SEC-10: a 403 would confirm the route exists. The customer cannot tell
    the settings editor apart from a path that was never implemented."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        response = client.get(SETTINGS_PATH)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_without_completed_mfa_is_refused(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        response = client.get(SETTINGS_PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "MFA_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_patch_without_the_csrf_header_is_rejected(db_session: AsyncSession) -> None:
    """SEC-03 covers every unsafe cookie-authenticated method, even though the
    endpoint table in api-endpoints.md does not spell it out for this route."""
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.patch(f"{SETTINGS_PATH}/daily_download_cap", json={"value": 50})

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_INVALID"
    assert await _value_of(db_session, "daily_download_cap") == 20


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_list_returns_every_setting_ordered_by_key(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        body = client.get(SETTINGS_PATH).json()

    keys = [item["key"] for item in body["items"]]
    assert set(keys) == set(REGISTRY)
    assert keys == sorted(keys)
    # Twelve rows fit inside the default page of 20.
    assert body["next_cursor"] is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_cursor_walks_every_setting_exactly_once(db_session: AsyncSession) -> None:
    """Real pagination, not a next_cursor that is always null: with limit=5 the
    twelve settings take three pages."""
    from app.main import app

    seen: list[str] = []
    with TestClient(app) as client:
        await _admin_session(client, db_session)
        cursor: str | None = None
        for _ in range(10):  # generous bound; a loop that never ends is a bug
            params: dict[str, Any] = {"limit": 5}
            if cursor:
                params["cursor"] = cursor
            body = client.get(SETTINGS_PATH, params=params).json()
            seen.extend(item["key"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break

    assert cursor is None, "pagination did not terminate"
    assert seen == sorted(REGISTRY)
    assert len(seen) == len(set(seen))


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_list_can_be_filtered_by_prefix_and_type(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        by_prefix = client.get(SETTINGS_PATH, params={"prefix": "offer_"}).json()
        by_type = client.get(SETTINGS_PATH, params={"type": "duration"}).json()

    assert {item["key"] for item in by_prefix["items"]} == {
        "offer_response_window",
        "offer_checkout_window",
        "offer_rejection_cooldown",
    }
    assert {item["key"] for item in by_type["items"]} == {
        key for key, spec in REGISTRY.items() if spec.type.value == "duration"
    }


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_tampered_cursor_is_a_validation_error(db_session: AsyncSession) -> None:
    """The project's ordinary contract for a bad query parameter, so a tampered
    cursor needs no error code of its own."""
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.get(SETTINGS_PATH, params={"cursor": "!!!not-base64!!!"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_reading_one_setting_includes_its_validation_metadata(
    db_session: AsyncSession,
) -> None:
    """`unit`, `minimum`, `maximum`, `nullable` and `is_public` come from the
    code registry rather than from columns - an admin UI needs them to render
    the right editor, and storing them would make a range something an
    administrator could widen at runtime."""
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        body = client.get(f"{SETTINGS_PATH}/offer_response_window").json()

    assert body["key"] == "offer_response_window"
    assert body["type"] == "duration"
    assert body["value"] == 172_800
    assert body["unit"] == "seconds"
    assert body["minimum"] == 3_600
    assert body["maximum"] == 604_800
    assert body["nullable"] is False
    assert body["is_public"] is False


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unknown_key_is_not_found(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.get(f"{SETTINGS_PATH}/not_a_real_setting")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_valid_change_is_stored_and_audited(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        admin_id = await _admin_session(client, db_session)
        response = client.patch(
            f"{SETTINGS_PATH}/daily_download_cap",
            json={"value": 50},
            headers=csrf_headers(client),
        )

    assert response.status_code == 200, response.text
    assert response.json()["value"] == 50
    assert await _value_of(db_session, "daily_download_cap") == 50

    entry = await db_session.scalar(
        select(AuditLogModel)
        .where(AuditLogModel.action == "setting.updated")
        .order_by(AuditLogModel.created_at.desc())
    )
    assert entry is not None
    assert entry.entity_type == "Setting"
    assert entry.actor_user_id == admin_id
    assert entry.before_data == {"key": "daily_download_cap", "value": 20}
    assert entry.after_data == {"key": "daily_download_cap", "value": 50}
    # BR-132 admin-action conventions: correlation and the hashed caller IP.
    assert entry.request_id is not None
    assert entry.ip_hash is not None

    await _restore(db_session, "daily_download_cap")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_value_outside_its_range_is_refused(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        too_big = client.patch(
            f"{SETTINGS_PATH}/minimum_offer_percentage",
            json={"value": 101},
            headers=csrf_headers(client),
        )

    assert too_big.status_code == 422
    assert too_big.json()["code"] == "SETTING_INVALID"
    assert await _value_of(db_session, "minimum_offer_percentage") == 70


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_wrongly_typed_value_is_refused(db_session: AsyncSession) -> None:
    """`true` is an `int` in Python, so an integer setting that accepted it
    would quietly store 1 - here, an offer floor of 1% of list price."""
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.patch(
            f"{SETTINGS_PATH}/minimum_offer_percentage",
            json={"value": True},
            headers=csrf_headers(client),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "SETTING_INVALID"
    assert await _value_of(db_session, "minimum_offer_percentage") == 70


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unknown_key_cannot_be_created_by_patching_it(
    db_session: AsyncSession,
) -> None:
    """api-endpoints.md:632 - keys are schema-defined. A PATCH is not an upsert."""
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.patch(
            f"{SETTINGS_PATH}/invented_key",
            json={"value": 1},
            headers=csrf_headers(client),
        )

    assert response.status_code == 404
    row = await db_session.scalar(select(SettingModel).where(SettingModel.key == "invented_key"))
    assert row is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_money_setting_round_trips_through_the_api(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.patch(
            f"{SETTINGS_PATH}/free_shipping_threshold",
            json={"value": {"amount_cents": 5_000, "currency": "USD"}},
            headers=csrf_headers(client),
        )

    assert response.status_code == 200, response.text
    assert response.json()["value"] == {"amount_cents": 5_000, "currency": "USD"}
    assert await _value_of(db_session, "free_shipping_threshold") == {
        "amount_cents": 5_000,
        "currency": "USD",
    }

    await _restore(db_session, "free_shipping_threshold")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_write_and_its_audit_row_are_one_transaction(
    db_session: AsyncSession,
) -> None:
    """If the audit insert fails, the setting must not change.

    A committed change with no audit row is precisely the gap BR-132 exists to
    close, and `get_session` wrapping the request in one transaction is what
    makes the two inseparable - so this forces the audit write to fail and
    checks the value is untouched.
    """
    from app.main import app

    async def _explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit store unavailable")

    monkey = pytest.MonkeyPatch()
    with TestClient(app, raise_server_exceptions=False) as client:
        # The admin session is established *before* the audit store is broken.
        # Registration and login write audit rows of their own, so patching
        # first would fail the setup rather than the thing under test.
        await _admin_session(client, db_session)
        monkey.setattr(AuditLogRepository, "add", _explode)
        try:
            response = client.patch(
                f"{SETTINGS_PATH}/daily_download_cap",
                json={"value": 99},
                headers=csrf_headers(client),
            )
        finally:
            monkey.undo()

    assert response.status_code == 500
    assert await _value_of(db_session, "daily_download_cap") == 20
