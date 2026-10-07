import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.security import csrf_token_for_session
from app.identity.application.ports import SessionStore, UserStore
from app.identity.application.security.password_hasher import hash_password, verify_password_async
from app.identity.application.security.session_tokens import issue_access_token, issue_refresh_token
from app.identity.application.security.token_service import hash_token
from app.identity.application.services.admin_mfa_gate import AdminMfaGate, MfaChallengeRequired
from app.identity.application.services.login_throttle import LoginThrottle
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import AccountDisabledError, InvalidCredentialsError
from app.platform.application.ports.audit_writer import AuditWriter

# Argon2 verification is deliberately slow, so skipping it for an unknown email
# would make "no such account" measurably faster to answer than "wrong
# password" - an attacker can time that difference and enumerate addresses.
# Verifying against this throwaway hash keeps both paths equally slow.
_DUMMY_PASSWORD_HASH = hash_password("timing-equalisation-placeholder")


@dataclass(frozen=True)
class LoginResult:
    user_id: UUID
    email: str
    session_id: UUID
    session_expires_at: datetime
    role: UserRole
    email_verified: bool
    access_token: str
    refresh_token: str
    csrf_token: str


class Login:
    def __init__(
        self,
        user_repo: UserStore,
        session_repo: SessionStore,
        audit_writer: AuditWriter,
        throttle: LoginThrottle,
        # VS-005 MFA integration.
        mfa_gate: AdminMfaGate,
    ) -> None:
        self._users = user_repo
        self._sessions = session_repo
        self._audit = audit_writer
        self._throttle = throttle
        self._mfa_gate = mfa_gate

    async def execute(
        self,
        *,
        email: str,
        password: str,
        ip: str | None,
        ip_hash: str | None,
        user_agent: str | None,
        request_id: str | None,
    ) -> LoginResult | MfaChallengeRequired:
        await self._throttle.check(email=email, ip=ip)

        # Unlocked. Argon2 costs ~80ms by design, and this is a public,
        # unauthenticated endpoint: holding a `users` row lock across that would
        # let anyone who knows an address serialise every operation touching it
        # - other logins, a refresh, a password reset - for 80ms per request,
        # simply by guessing. The lock is taken below instead, after the
        # expensive work is done, and the credential is re-checked under it.
        user = await self._users.get_by_email(email)
        if user is None:
            await verify_password_async(password=password, password_hash=_DUMMY_PASSWORD_HASH)
            await self._throttle.record_failure(email=email, ip=ip)
            raise InvalidCredentialsError()

        # Captured, not re-read. This exact string is the credential version
        # Argon2 is about to authenticate, and it is what the locked row is
        # compared against afterwards - see below.
        verified_hash = user.password_hash
        if not await verify_password_async(password=password, password_hash=verified_hash):
            await self._throttle.record_failure(email=email, ip=ip)
            raise InvalidCredentialsError()

        # Only now, after the password has proven the caller owns this account,
        # is it safe to be specific about why login is refused. Doing this check
        # before verification would let anyone probe which addresses are
        # suspended (FR-02: errors must not reveal whether an email exists).
        if not user.can_authenticate:
            raise AccountDisabledError(user.id)

        # Before the lock: the password was correct, so the counters for this
        # (email, IP) should clear regardless of how the rest of this request
        # turns out. Keeps the throttle Redis round-trip outside the lock too.
        await self._throttle.reset(email=email, ip=ip)

        # The lock, taken now that the expensive work is behind us. Everything
        # from here to the session insert runs against a row nothing else can
        # change, in the project's canonical `users`-then-`sessions` order.
        user = await self._users.get_by_id_for_update(user.id)
        if user is None:
            # The account was deleted between the two reads.
            raise InvalidCredentialsError()

        # Re-checked under the lock rather than trusted from the unlocked read:
        # an account can be deactivated inside the ~80ms window above.
        if not user.can_authenticate:
            raise AccountDisabledError(user.id)

        # The credential-version check, and the reason the lock can be taken
        # late at all. A password reset committing during the verification above
        # would otherwise leave this login minting a session from a credential
        # the database no longer holds - and worse, stamping it with the *new*
        # `auth_epoch` read below, so it would sail past every revocation check
        # the reset had just armed (ADR-018).
        #
        # Comparing the encoded hashes establishes that the stored credential is
        # still the exact one Argon2 authenticated. Nothing rehashes on login,
        # so the string is stable for an unchanged password; if a
        # rehash-on-verify policy is ever added, this needs an explicit
        # credential-version column instead. `compare_digest` rather than `==`
        # to keep the comparison free of a timing signal, matching
        # `Session.authorize_rotation`.
        if not secrets.compare_digest(user.password_hash, verified_hash):
            # Deliberately the ordinary invalid-credentials answer. A distinct
            # error here would tell the caller that this address exists *and*
            # that its password was being changed at that moment.
            raise InvalidCredentialsError()

        # ---- VS-005 MFA integration (SEC-04, api-endpoints.md:252) ----------
        # The password has proven the caller owns this account, but for an
        # administrator with MFA enabled that is only half of a login. Return
        # before anything is minted: no session row, no tokens, no cookies, so
        # a stolen password on its own buys nothing but a five-minute challenge.
        #
        # Placed after the throttle reset on purpose - the password *was*
        # correct, so the failure counters for this (email, IP) should clear
        # exactly as they would for any other correct password. Everything
        # above this point is VS-003's original login, unchanged.
        if await self._mfa_gate.challenge_required(user):
            # BR-132 requires auth events to be audited, and this is one: the
            # password for an administrator account was correct. Without a row
            # here the half-login is invisible - someone holding a stolen admin
            # password could confirm it works, repeatedly, and the audit log
            # would show nothing at all unless they also cleared the second
            # factor. `user.logged_in` is deliberately not reused: no session
            # exists yet, and recording one that was never created would make
            # "when did this account sign in?" answer wrongly.
            await self._audit.record(
                actor_user_id=user.id,
                action="user.mfa_challenge_issued",
                entity_type="User",
                entity_id=user.id,
                request_id=request_id,
                ip_hash=ip_hash,
            )
            return MfaChallengeRequired(user_id=user.id, auth_epoch=user.auth_epoch)
        # ---- end VS-005 MFA integration -------------------------------------

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
        await self._audit.record(
            actor_user_id=user.id,
            action="user.logged_in",
            entity_type="Session",
            entity_id=session_id,
            request_id=request_id,
            ip_hash=ip_hash,
        )

        return LoginResult(
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
                # From the locked row. A later reset advances it and invalidates
                # this token immediately rather than at its next refresh.
                auth_epoch=user.auth_epoch,
            ),
            refresh_token=refresh_token,
            csrf_token=csrf_token_for_session(session_id),
        )
