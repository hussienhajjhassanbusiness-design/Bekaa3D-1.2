"""A real login writes the keyed IP hash (VS-046, ADR-028) to sessions and audit_logs.

The expected digest is recomputed from the stored salt and the env pepper."""

import hashlib
import hmac
import re

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ip_hash_keyring import reset_ip_hash_keyring
from app.identity.infrastructure.models import SessionModel
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import PASSWORD, client_for, create_user, fresh_ip

HEX64 = re.compile(r"^[0-9a-f]{64}$")


async def _expected_hash(db_session: AsyncSession, ip: str) -> str:
    salt = await db_session.scalar(text("SELECT salt FROM ip_hash_salts WHERE is_current"))
    pepper = get_settings().ip_hash_salt.get_secret_value().encode("utf-8")
    key = hmac.new(pepper, b"bekaa3d/ip-hash/v2:" + salt, hashlib.sha256).digest()
    return hmac.new(key, ip.encode("utf-8"), hashlib.sha256).hexdigest()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_login_stores_the_keyed_hash_in_the_session_and_the_audit_row(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    user_id = user.id  # read before expire_all(), which would make it a lazy load
    ip = fresh_ip()
    with client_for(main_app, ip=ip) as client:
        response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
        )
    assert response.status_code == 200, response.text

    db_session.expire_all()
    session_row = await db_session.scalar(
        select(SessionModel).where(SessionModel.user_id == user_id)
    )
    assert session_row is not None
    audit_row = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.action == "user.logged_in", AuditLogModel.entity_id == session_row.id
        )
    )
    assert audit_row is not None

    session_hash, audit_hash = session_row.ip_hash, audit_row.ip_hash
    expected = await _expected_hash(db_session, ip)
    await db_session.rollback()
    assert session_hash is not None and HEX64.match(session_hash)
    assert session_hash == audit_hash == expected


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_middleware_loads_the_key_when_none_is_loaded(db_session: AsyncSession) -> None:
    """Amendment B: a process whose boot-time load failed hashes again on the next request."""
    user = await create_user(db_session)
    user_id = user.id
    ip = fresh_ip()
    with client_for(main_app, ip=ip) as client:
        reset_ip_hash_keyring()  # as if the lifespan load had failed
        response = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
        )
    assert response.status_code == 200, response.text

    db_session.expire_all()
    stored = await db_session.scalar(
        select(SessionModel.ip_hash).where(SessionModel.user_id == user_id)
    )
    expected = await _expected_hash(db_session, ip)
    await db_session.rollback()
    assert stored == expected
