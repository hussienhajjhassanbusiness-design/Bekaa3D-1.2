from datetime import UTC, datetime

from app.identity.application.ports import UserStore, VerificationTokenStore
from app.identity.application.security.token_service import hash_token
from app.identity.domain.exceptions import InvalidVerificationTokenError
from app.platform.application.ports.audit_writer import AuditWriter


class VerifyEmail:
    def __init__(
        self,
        user_repo: UserStore,
        token_repo: VerificationTokenStore,
        audit_writer: AuditWriter,
    ) -> None:
        self._users = user_repo
        self._tokens = token_repo
        self._audit = audit_writer

    async def execute(self, *, raw_token: str, request_id: str | None, ip_hash: str | None) -> None:
        token_hash = hash_token(raw_token)
        # Unlocked peek to learn the owner; then lock the user, then the token,
        # and decide only on the locked re-read (BUG-07). Without the lock N
        # simultaneous redemptions all read an unused token and all succeeded.
        # `users` before dependents, as everywhere else.
        peek = await self._tokens.get_by_hash(token_hash)
        if peek is None:
            raise InvalidVerificationTokenError()

        user = await self._users.get_by_id_for_update(peek.user_id)
        if user is None:
            raise InvalidVerificationTokenError()

        token = await self._tokens.get_by_hash_for_update(token_hash)
        if token is None:
            raise InvalidVerificationTokenError()

        now = datetime.now(UTC)
        # Domain entities enforce their own invariants (used/expired/already-verified);
        # this call is what actually raises InvalidVerificationTokenError /
        # VerificationTokenExpiredError / AlreadyVerifiedError when applicable.
        token.mark_used(now)
        user.mark_verified(now)

        await self._users.save(user)
        await self._tokens.save(token)
        await self._audit.record(
            actor_user_id=user.id,
            action="user.email_verified",
            entity_type="User",
            entity_id=user.id,
            request_id=request_id,
            ip_hash=ip_hash,
        )
