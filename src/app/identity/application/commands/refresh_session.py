from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.core.security import csrf_token_for_session
from app.identity.application.ports import SessionStore, UserStore
from app.identity.application.security.session_tokens import (
    decode_refresh_token,
    issue_access_token,
    issue_refresh_token,
)
from app.identity.application.security.token_service import hash_token
from app.identity.domain.exceptions import (
    InvalidSessionError,
    RefreshTokenReuseError,
    SessionOwnerRevokedError,
)
from app.platform.application.ports.audit_writer import AuditWriter


@dataclass(frozen=True)
class RefreshResult:
    session_id: UUID
    access_token: str
    refresh_token: str
    csrf_token: str


class RefreshSession:
    def __init__(
        self,
        user_repo: UserStore,
        session_repo: SessionStore,
        audit_writer: AuditWriter,
    ) -> None:
        self._users = user_repo
        self._sessions = session_repo
        self._audit = audit_writer

    async def execute(
        self,
        *,
        raw_refresh_token: str,
        request_id: str | None,
        ip_hash: str | None,
        mfa_completed: bool = False,
    ) -> RefreshResult:
        claims = decode_refresh_token(raw_refresh_token)

        # Lock order: `users` first, then `sessions`. A password reset takes the
        # user row and then updates that user's session rows, so acquiring them
        # the other way round here would close a deadlock cycle - which is
        # exactly what this path used to do, since VS-003 locked the session row
        # straight away and never touched the user row at all.
        #
        # Getting the user id therefore needs an unlocked peek first. Nothing is
        # decided on it: it identifies which user row to lock and nothing more,
        # and every condition that matters is revalidated below against the
        # locked re-read.
        owner_id = await self._sessions.get_owner_id(claims.session_id)
        if owner_id is None:
            raise InvalidSessionError()

        # 1. The user row. Held for the rest of the transaction, so a reset
        #    either finished before this line or cannot start until after this
        #    transaction ends.
        user = await self._users.get_by_id_for_update(owner_id)

        # 2. Now the session row. `populate_existing` matters: the unlocked peek
        #    above may have put a stale instance in the identity map, and
        #    without it SQLAlchemy would hand that back instead of the row as it
        #    stands under the lock.
        session = await self._sessions.get_for_update(claims.session_id)
        if session is None:
            raise InvalidSessionError()

        now = datetime.now(UTC)
        try:
            session.authorize_rotation(
                presented_token_hash=hash_token(raw_refresh_token),
                presented_version=claims.token_version,
                at=now,
            )
        except RefreshTokenReuseError:
            # A stolen token was replayed. Kill the session rather than merely
            # rejecting this request, so the thief cannot keep trying and the
            # real user is forced through a fresh login.
            #
            # The caller MUST commit this before returning the 401 - see the
            # refresh route, which does so explicitly. Letting the exception
            # roll the transaction back would leave the stolen session alive.
            session.mark_reuse_detected(now)
            await self._sessions.save(session)
            await self._audit.record(
                actor_user_id=session.user_id,
                action="session.reuse_detected",
                entity_type="Session",
                entity_id=session.id,
                request_id=request_id,
                ip_hash=ip_hash,
            )
            raise

        if user is None or not user.can_authenticate:
            # Deactivated or anonymised between login and refresh: the session
            # must not survive its owner. Like the reuse branch above, this
            # revocation has to be committed by the caller despite the 401.
            session.revoke(now)
            await self._sessions.save(session)
            raise SessionOwnerRevokedError(session.id)

        # rotate() increments token_version itself, so the token is minted for
        # the version rotate() is about to produce - test_rotate_advances_
        # version_and_replaces_the_hash is what keeps these two in agreement.
        refresh_token = issue_refresh_token(
            session_id=session.id,
            token_version=session.token_version + 1,
            expires_at=session.expires_at,
            now=now,
        )
        session.rotate(new_token_hash=hash_token(refresh_token), at=now)
        await self._sessions.save(session)

        return RefreshResult(
            session_id=session.id,
            access_token=issue_access_token(
                user_id=user.id,
                session_id=session.id,
                role=user.role,
                email_verified=user.is_verified,
                now=now,
                # Carried across rotation, or an administrator would drop back
                # to MFA-incomplete every time the access token is renewed.
                # Defaults False so a caller that does not track it fails closed.
                mfa_completed=mfa_completed,
                # From the locked user row, so a reset cannot land between the
                # rotation and the stamp. A reset that landed *before* this
                # transaction got the lock has already revoked the session, and
                # `authorize_rotation` above refuses a revoked session - so this
                # line is never reached with a stale epoch.
                auth_epoch=user.auth_epoch,
            ),
            refresh_token=refresh_token,
            csrf_token=csrf_token_for_session(session.id),
        )
