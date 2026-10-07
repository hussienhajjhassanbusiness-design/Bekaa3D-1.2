"""The authentication epoch: the one number that decides whether a credential
minted earlier is still good (ADR-018).

It lives on `users.auth_epoch`, not in Redis, and several of these tests exist
to insist on that. A cache that answers *successfully* with a lost key - a
restarted container, an evicted entry, a restored snapshot - would silently
re-validate credentials a password reset had already revoked, and that failure
looks exactly like normal operation from the application's side.

Most of these drive `current_claims` through a real request rather than calling
it directly, because what matters is the status code a caller receives.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import redis.asyncio as redis_asyncio
from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cookies import ACCESS_COOKIE
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestIDMiddleware
from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.identity.api.dependencies import current_claims
from app.identity.application.security.session_tokens import (
    AccessTokenClaims,
    decode_access_token,
    issue_access_token,
)
from app.identity.application.security.token_service import generate_raw_token, hash_token
from app.identity.application.services.password_reset import PASSWORD_RESET_TOKEN_TTL
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import InvalidSessionError
from app.identity.infrastructure.models import PasswordResetTokenModel, UserModel
from app.identity.infrastructure.repositories import UserRepository
from app.main import lifespan
from tests.integration.identity.test_login import PASSWORD, register_and_verify
from tests.integration.identity.test_mfa_enrollment import unique_email

PROBE_PATH = "/probe"
LOGIN_PATH = "/api/v1/auth/login"
REFRESH_PATH = "/api/v1/auth/refresh"
RESET_CONFIRM_PATH = "/api/v1/auth/password-reset/confirm"
ME_PATH = "/api/v1/me"

NEW_PASSWORD = "a-completely-different-password"


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token is not None
    return {"X-CSRF-Token": token}


def _token(*, user_id: uuid.UUID, auth_epoch: int) -> str:
    return issue_access_token(
        user_id=user_id,
        session_id=uuid.uuid4(),
        role=UserRole.CUSTOMER,
        email_verified=True,
        now=datetime.now(UTC),
        auth_epoch=auth_epoch,
    )


def _probe_app() -> FastAPI:
    """The real application plus one route that does nothing but report the
    epoch `current_claims` accepted.

    Mirrors src/app/main.py rather than hand-building a bare FastAPI, following
    tests/integration/test_admin_boundary.py: the real lifespan is what wires up
    `app.state.db_session_factory`, and `get_session` opens its session from
    there - inside the TestClient's own event loop, which is the only loop those
    connections may be used on.
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with lifespan(app):
            yield

    app = FastAPI(title="Bekaa3D API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    app.include_router(v1_router)

    @app.get(PROBE_PATH)
    async def probe(claims: AccessTokenClaims = Depends(current_claims)) -> Response:
        return Response(str(claims.auth_epoch), media_type="text/plain")

    return app


def _probe(token: str) -> tuple[int, str]:
    with TestClient(_probe_app(), raise_server_exceptions=False) as client:
        client.cookies.set(ACCESS_COOKIE, token)
        response = client.get(PROBE_PATH)
    return response.status_code, response.text


async def _seed_user(db_session: AsyncSession, *, auth_epoch: int = 0) -> uuid.UUID:
    model = UserModel(email=unique_email(), password_hash="not-a-real-hash", auth_epoch=auth_epoch)
    db_session.add(model)
    await db_session.commit()
    return model.id


# --------------------------------------------------------------------------
# The epoch comparison
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_epoch_0_on_a_never_reset_account_is_accepted(db_session: AsyncSession) -> None:
    """The compatibility case, and the one that matters most on deploy day.

    Every token minted before this claim existed decodes as epoch 0, and the
    column defaults to 0 for every row that already exists. Those two zeros have
    to agree, or shipping this would sign out every logged-in user at once.
    """
    user_id = await _seed_user(db_session)

    status_code, body = _probe(_token(user_id=user_id, auth_epoch=0))

    assert status_code == 200
    assert body == "0"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_stale_epoch_is_rejected(db_session: AsyncSession) -> None:
    """The whole point: a credential from before the reset stops working."""
    user_id = await _seed_user(db_session, auth_epoch=1)

    status_code, _ = _probe(_token(user_id=user_id, auth_epoch=0))

    assert status_code == 401


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_matching_epoch_is_accepted(db_session: AsyncSession) -> None:
    """Forward progress: the account has reset once and this token was minted
    after that, so it is current."""
    user_id = await _seed_user(db_session, auth_epoch=1)

    status_code, body = _probe(_token(user_id=user_id, auth_epoch=1))

    assert status_code == 200
    assert body == "1"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_epoch_ahead_of_the_account_is_rejected(db_session: AsyncSession) -> None:
    """Equality, not `<=`. A token claiming an epoch the account has not reached
    cannot have been minted honestly, and accepting "ahead" would let a forged
    claim outlive every future reset."""
    user_id = await _seed_user(db_session, auth_epoch=1)

    status_code, _ = _probe(_token(user_id=user_id, auth_epoch=99))

    assert status_code == 401


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_token_for_a_vanished_account_is_rejected(db_session: AsyncSession) -> None:
    """No row means no epoch to match. The unverified-purge job is the only
    thing that hard-deletes a user, but a live token outliving its account must
    not fall through to "accepted"."""
    status_code, _ = _probe(_token(user_id=uuid.uuid4(), auth_epoch=0))

    assert status_code == 401


# --------------------------------------------------------------------------
# Malformed claims
# --------------------------------------------------------------------------


def _forge(auth_epoch: object) -> str:
    """A validly *signed* token carrying a malformed epoch claim. Signed with
    the real key on purpose: the question is what the claim reader does with a
    well-signed token whose contents are wrong."""
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "typ": "access",
            "sub": str(uuid.uuid4()),
            "sid": str(uuid.uuid4()),
            "role": UserRole.CUSTOMER.value,
            "ver": True,
            "mfa": False,
            "auth_epoch": auth_epoch,
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        settings.jwt_signing_key,
        algorithm="HS256",
    )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "malformed",
    [
        pytest.param("1", id="numeric-string"),
        pytest.param(1.5, id="float"),
        pytest.param(-1, id="negative"),
        pytest.param(None, id="null"),
        pytest.param([1], id="list"),
        # `bool` is a subclass of `int` in Python, so a naive isinstance check
        # reads this as epoch 1. It is the malformed value most likely to slip
        # through.
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
    ],
)
def test_a_malformed_epoch_claim_is_rejected(malformed: object) -> None:
    """None of these may fall back to the default of 0: that is the one value
    which matches a never-reset account, so defaulting would be a bypass rather
    than a compatibility shim."""
    with pytest.raises(InvalidSessionError):
        decode_access_token(_forge(malformed))


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_token_with_no_epoch_claim_reads_as_zero() -> None:
    """Distinct from malformed: a token minted before the claim existed is
    absent, not wrong, and must keep working until its account resets."""
    settings = get_settings()
    now = datetime.now(UTC)
    legacy = jwt.encode(
        {
            "typ": "access",
            "sub": str(uuid.uuid4()),
            "sid": str(uuid.uuid4()),
            "role": UserRole.CUSTOMER.value,
            "ver": True,
            "mfa": False,
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        settings.jwt_signing_key,
        algorithm="HS256",
    )

    assert decode_access_token(legacy).auth_epoch == 0


# --------------------------------------------------------------------------
# Redis state loss - the reason the epoch is not in Redis
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_losing_all_redis_state_does_not_revive_a_revoked_token(
    db_session: AsyncSession,
) -> None:
    """The regression that decided the architecture.

    An earlier draft kept the epoch in Redis, where a missing key meant "epoch
    0". That is indistinguishable from "this account has never been
    invalidated", so a Redis restart - and `docker-compose.yml` runs
    `redis:7-alpine` with no volume and `restart: unless-stopped`, so a restart
    means an empty, *healthy* keyspace - would have silently re-validated every
    token a reset had just revoked. The outage itself failed closed; the
    recovery did not.

    `FLUSHALL` is the strongest form of that: every key the application holds,
    gone, with Redis answering normally throughout. The revoked token must still
    be refused, because the authority is a `users` column the flush cannot
    touch.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        assert (
            client.post(LOGIN_PATH, json={"email": email, "password": PASSWORD}).status_code == 200
        )
        revoked_token = client.cookies[ACCESS_COOKIE]
        assert client.get(ME_PATH).status_code == 200

        raw = generate_raw_token()
        db_session.add(
            PasswordResetTokenModel(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=datetime.now(UTC) + PASSWORD_RESET_TOKEN_TTL,
            )
        )
        await db_session.commit()
        assert (
            client.post(
                RESET_CONFIRM_PATH, json={"token": raw, "new_password": NEW_PASSWORD}
            ).status_code
            == 204
        )

        # Simulate the restart: every key gone, Redis still serving.
        redis = redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
        await redis.flushall()
        assert await redis.dbsize() == 0
        await redis.aclose()

        client.cookies.set(ACCESS_COOKIE, revoked_token)
        after_flush = client.get(ME_PATH)

    epoch = await db_session.scalar(select(UserModel.auth_epoch).where(UserModel.id == user.id))

    # The authority survived the flush.
    assert epoch == 1
    assert after_flush.status_code == 401, (
        "a token revoked by a password reset was accepted again after Redis lost "
        "its state - the epoch is not durably authoritative"
    )


@pytest.mark.integration
async def test_the_epoch_persists_and_is_monotonic(db_session: AsyncSession) -> None:
    """Read back through the repository rather than the in-memory entity, so
    what is asserted is what the database actually holds."""
    user_id = await _seed_user(db_session)
    repo = UserRepository(db_session)

    assert await repo.get_auth_epoch(user_id) == 0

    user = await repo.get_by_id(user_id)
    assert user is not None
    user.invalidate_credentials(datetime.now(UTC))
    await repo.save(user)
    await db_session.commit()
    db_session.expunge_all()

    assert await repo.get_auth_epoch(user_id) == 1


# --------------------------------------------------------------------------
# End to end: every minting path stamps the current epoch
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_refresh_mints_a_token_carrying_the_accounts_current_epoch(
    db_session: AsyncSession,
) -> None:
    """Refresh rotation is a minting path like any other.

    Checked on both sides of a reset. Before it, rotation must not invent an
    epoch the account has not reached - that would fail the very next request.
    After it, the rotated token must carry the *new* epoch rather than copying
    whatever the old one said.
    """
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await register_and_verify(client, db_session, email)
        assert (
            client.post(LOGIN_PATH, json={"email": email, "password": PASSWORD}).status_code == 200
        )

        assert client.post(REFRESH_PATH, headers=_csrf(client)).status_code == 204
        before = decode_access_token(client.cookies[ACCESS_COOKIE]).auth_epoch

        raw = generate_raw_token()
        db_session.add(
            PasswordResetTokenModel(
                user_id=user.id,
                token_hash=hash_token(raw),
                expires_at=datetime.now(UTC) + PASSWORD_RESET_TOKEN_TTL,
            )
        )
        await db_session.commit()
        assert (
            client.post(
                RESET_CONFIRM_PATH, json={"token": raw, "new_password": NEW_PASSWORD}
            ).status_code
            == 204
        )

        assert (
            client.post(LOGIN_PATH, json={"email": email, "password": NEW_PASSWORD}).status_code
            == 200
        )
        after_login = decode_access_token(client.cookies[ACCESS_COOKIE]).auth_epoch

        assert client.post(REFRESH_PATH, headers=_csrf(client)).status_code == 204
        after_refresh = decode_access_token(client.cookies[ACCESS_COOKIE]).auth_epoch

    assert before == 0
    assert after_login == 1
    assert after_refresh == 1
