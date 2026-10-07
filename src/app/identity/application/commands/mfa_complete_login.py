"""VS-005: the second half of a login that stopped at the MFA challenge.

api-endpoints.md:270 makes `/auth/mfa/verify` the step that "Completes admin
login; sets full auth + CSRF cookies". VS-003's `Login` deliberately stops
before minting a session for an administrator with MFA enabled, so this is
where that session is finally created.

On the structural similarity to the tail of `Login.execute`: it is intentional
and it is not a parallel session mechanism. Both build a session out of exactly
the same primitives - `SessionStore.add`, `issue_refresh_token`,
`issue_access_token`, `csrf_token_for_session`, `hash_token` - and both write
the same `user.logged_in` audit row, so a session is a session however it was
reached. Reusing the primitives rather than refactoring VS-003's login into a
shared helper is a deliberate scope choice: VS-005 owns this file, and VS-003's
login keeps the shape its own author gave it.

The one genuine difference is the access token, which carries
`mfa_completed=True` from the moment it is minted - this session never exists
in an MFA-incomplete state."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.security import csrf_token_for_session
from app.identity.application.ports import SessionStore, UserStore
from app.identity.application.security.session_tokens import issue_access_token, issue_refresh_token
from app.identity.application.security.token_service import hash_token
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import AccountDisabledError, InvalidCredentialsError
from app.platform.application.ports.audit_writer import AuditWriter


@dataclass(frozen=True)
class CompleteMfaLoginResult:
    user_id: UUID
    email: str
    session_id: UUID
    session_expires_at: datetime
    role: UserRole
    email_verified: bool
    access_token: str
    refresh_token: str
    csrf_token: str


class CompleteMfaLogin:
    """Create the authenticated session for an account that has just cleared
    its second factor."""

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
        user_id: UUID,
        challenge_epoch: int,
        ip_hash: str | None,
        user_agent: str | None,
        request_id: str | None,
    ) -> CompleteMfaLoginResult:
        """`user_id` comes from the resolved challenge, never from the request
        body - the caller never gets to name the account they are completing
        login for.

        The read takes a row lock, and that lock is what makes this safe against
        a password reset arriving at the same moment (SEC-08). Both operations
        hold it, so they cannot interleave, and only two orderings exist:

        - **Reset first.** It bumps the account's challenge epoch and commits
          before this transaction gets the lock, so the epoch check below fails
          and no session is ever created.
        - **This first.** The session is inserted and committed before the reset
          gets the lock, so the reset's `revoke_all_for_user` sees the row and
          revokes it.

        Without the lock there is a third ordering - this transaction inserting
        its session after the reset's revocation UPDATE has already run - which
        would leave a live session created from a pre-reset challenge.
        """
        user = await self._users.get_by_id_for_update(user_id)
        if user is None:
            # The account vanished between the password check and the second
            # factor. Nothing here is a useful signal to an attacker, and the
            # route maps it to the same MFA_INVALID everything else gets.
            raise InvalidCredentialsError()

        # Re-checked rather than assumed: the challenge is valid for five
        # minutes, and an account can be deactivated inside that window. The
        # password half of this login already passed the same check, so
        # skipping it here would make the MFA path the weaker of the two.
        if not user.can_authenticate:
            raise AccountDisabledError(user.id)

        # Straight off the row this transaction holds locked, so a reset that
        # committed before this point is always visible and one that has not
        # committed cannot be. A challenge minted before the account's last
        # password reset carries a stale epoch and buys nothing.
        if challenge_epoch != user.auth_epoch:
            raise InvalidCredentialsError()

        settings = get_settings()
        now = datetime.now(UTC)
        session_id = uuid4()
        expires_at = now + timedelta(days=settings.refresh_token_days)

        refresh_token = issue_refresh_token(
            session_id=session_id, token_version=1, expires_at=expires_at, now=now
        )
        await self._sessions.add(
            session_id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=expires_at,
            ip_hash=ip_hash,
            user_agent=user_agent,
        )
        # The same action VS-003 writes for an ordinary login. A session
        # reached through MFA is still a login, and splitting the audit
        # vocabulary would make "when did this account sign in?" a two-query
        # question. What the second factor added is recorded separately by
        # VerifyMfa as `mfa.verified` / `mfa.recovery_code_used`.
        await self._audit.record(
            actor_user_id=user.id,
            action="user.logged_in",
            entity_type="Session",
            entity_id=session_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )

        return CompleteMfaLoginResult(
            user_id=user.id,
            email=user.email,
            session_id=session_id,
            session_expires_at=expires_at,
            role=user.role,
            email_verified=user.is_verified,
            access_token=issue_access_token(
                user_id=user.id,
                session_id=session_id,
                role=user.role,
                email_verified=user.is_verified,
                now=now,
                # Born MFA-complete. There is no window in which this session
                # exists without the claim.
                mfa_completed=True,
                # From the locked row, so this token cannot be stamped with an
                # epoch a concurrent reset has already moved past.
                auth_epoch=user.auth_epoch,
            ),
            refresh_token=refresh_token,
            csrf_token=csrf_token_for_session(session_id),
        )
