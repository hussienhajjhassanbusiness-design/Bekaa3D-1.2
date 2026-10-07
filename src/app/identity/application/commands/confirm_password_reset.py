from datetime import UTC, datetime

from app.identity.application.ports import (
    PasswordResetTokenStore,
    SessionStore,
    UserStore,
)
from app.identity.application.security.password_hasher import hash_password_async
from app.identity.application.security.token_service import hash_token
from app.identity.domain.exceptions import InvalidPasswordResetTokenError
from app.platform.application.ports.audit_writer import AuditWriter


class ConfirmPasswordReset:
    """Redeem a reset token: replace the password and end every live session.

    The session revocation is not a nicety. SEC-08 requires it because the
    normal reason to reset a password is that someone else may have it - and if
    the attacker is already logged in, changing the password alone leaves their
    session working for the next 30 days. Password change and revocation
    therefore happen in one transaction: a reset that committed the new hash but
    not the revocation would report success while leaving the intruder in.

    Sessions are not the only pre-reset authentication state, and revoking rows
    does not reach the other two. An access token is signed and self-contained,
    good for its full fifteen minutes; an MFA login challenge lives in Redis.
    Both would survive a reset that only touched `sessions`. All three are
    therefore invalidated together by incrementing the account's authentication
    epoch - see `_invalidate_pre_reset_auth` for the ordering and the failure
    behaviour, and ADR-018 for the design.

    What is deliberately *not* touched: MFA enrolment, the TOTP secret, and the
    recovery codes. A password reset proves control of the mailbox, which is
    exactly the thing the second factor exists to be independent of. Clearing it
    would turn a mailbox compromise into a full account takeover."""

    def __init__(
        self,
        user_repo: UserStore,
        token_repo: PasswordResetTokenStore,
        session_repo: SessionStore,
        audit_writer: AuditWriter,
    ) -> None:
        self._users = user_repo
        self._tokens = token_repo
        self._sessions = session_repo
        self._audit = audit_writer

    async def execute(
        self,
        *,
        raw_token: str,
        new_password: str,
        request_id: str | None,
        ip_hash: str | None,
    ) -> None:
        token_hash = hash_token(raw_token)
        # Unlocked peek, only to learn whose token this is (BUG-02). Locking the
        # token first and the user second - then UPDATE-ing the user's *other*
        # tokens - deadlocked two different tokens of one account confirmed at
        # once. Lock order is now: the user, then every one of that user's reset
        # tokens in id order, then decide on the re-read token.
        peek = await self._tokens.get_by_hash(token_hash)
        if peek is None:
            raise InvalidPasswordResetTokenError()

        # Locked read. This is also the serialisation point against an MFA login
        # challenge being redeemed at the same instant: CompleteMfaLogin takes
        # the same lock, so its session INSERT and the revocation below cannot
        # interleave. See UserStore.get_by_id_for_update.
        user = await self._users.get_by_id_for_update(peek.user_id)

        # Single-use under concurrency: a second confirm of the same token
        # queues on these locks and re-reads the row the first already burned.
        tokens = await self._tokens.lock_all_for_user(peek.user_id)
        token = next((t for t in tokens if t.token_hash == token_hash), None)
        if token is None:
            raise InvalidPasswordResetTokenError()
        # A deactivated, anonymised or deleted account is not recoverable, and
        # says so as "invalid token" rather than "disabled account" - this
        # endpoint is public, so a distinct error here would confirm the address
        # exists to anyone holding a stale link.
        if user is None or not user.can_authenticate:
            raise InvalidPasswordResetTokenError()

        now = datetime.now(UTC)
        # Raises InvalidPasswordResetTokenError (already used) or
        # PasswordResetTokenExpiredError; the entity owns that rule.
        token.mark_used(now)
        user.change_password(new_password_hash=await hash_password_async(new_password), at=now)

        # Advanced on the row this transaction already holds locked, and
        # persisted by the same `save` below as the new password hash. There is
        # no separate store to fail independently and no window in which the
        # password has changed but the old credentials still work: either the
        # transaction commits and both are true, or neither is.
        user.invalidate_credentials(now)

        await self._tokens.save(token)
        await self._users.save(user)
        # Any *other* link the user requested is burned too, so one reset closes
        # every outstanding route into the account rather than just this one.
        await self._tokens.consume_outstanding_for_user(user_id=user.id, at=now)
        revoked = await self._sessions.revoke_all_for_user(user_id=user.id, at=now)

        await self._audit.record(
            actor_user_id=user.id,
            action="user.password_reset",
            entity_type="User",
            entity_id=user.id,
            # No password material in either direction - the audit log is read by
            # humans and retained permanently. The session count is what an
            # investigator actually needs: how much access this reset cut off.
            after_data={"sessions_revoked": revoked},
            request_id=request_id,
            ip_hash=ip_hash,
        )
