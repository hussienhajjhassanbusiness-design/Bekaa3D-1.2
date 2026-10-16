"""VS-046 "Done when": after a rotation, the same IP hashes differently (SEC-25).

Rotation runs through the real job; the API picks the new salt up via its middleware."""

import time
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import ip_hash_keyring
from app.identity.infrastructure.models import SessionModel
from app.jobs.rotate_ip_salt import rotate_ip_salt
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import PASSWORD, client_for, create_user, csrf, fresh_ip
from tests.integration.identity.test_keyed_ip_hash import _expected_hash
from tests.integration.platform.test_rotate_ip_salt import make_due

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"


async def _session_hashes(db_session: AsyncSession, user_id: Any) -> list[str | None]:
    db_session.expire_all()
    rows = await db_session.scalars(
        select(SessionModel.ip_hash)
        .where(SessionModel.user_id == user_id)
        .order_by(SessionModel.created_at)
    )
    hashes = list(rows.all())
    await db_session.rollback()
    return hashes


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_login_after_rotation_stores_a_different_hash_for_the_same_ip(
    db_session: AsyncSession, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await create_user(db_session)
    user_id, email = user.id, user.email
    ip = fresh_ip()

    with client_for(main_app, ip=ip) as client:
        assert client.post(LOGIN, json={"email": email, "password": PASSWORD}).status_code == 200
        [before] = await _session_hashes(db_session, user_id)

        await make_due(db_engine)
        ctx = {"session_factory": async_sessionmaker(db_engine, expire_on_commit=False)}
        assert await rotate_ip_salt(ctx) is True
        # Past REFRESH_SECONDS: the next request reloads the key in the middleware.
        later = time.monotonic() + ip_hash_keyring.REFRESH_SECONDS + 1
        monkeypatch.setattr(ip_hash_keyring, "monotonic", lambda: later)

        assert client.post(REFRESH, headers=csrf(client)).status_code == 204
        with client_for(main_app, ip=ip) as second:
            response = second.post(LOGIN, json={"email": email, "password": PASSWORD})
        assert response.status_code == 200

    first_hash, second_hash = await _session_hashes(db_session, user_id)
    assert first_hash == before
    assert second_hash is not None and second_hash != before
    assert second_hash == await _expected_hash(db_session, ip)
    db_session.expire_all()
    audited = await db_session.scalars(
        select(AuditLogModel.ip_hash).where(
            AuditLogModel.action == "user.logged_in", AuditLogModel.actor_user_id == user_id
        )
    )
    assert set(audited.all()) == {before, second_hash}
    await db_session.rollback()
