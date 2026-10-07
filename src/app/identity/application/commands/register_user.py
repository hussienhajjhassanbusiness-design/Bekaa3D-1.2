from app.identity.application.ports import UserStore, VerificationTokenStore
from app.identity.application.security.password_hasher import hash_password_async
from app.identity.application.services.verification import (
    issue_verification_email,
    resend_eligible,
)
from app.platform.application.ports.audit_writer import AuditWriter
from app.platform.application.ports.outbox_writer import OutboxWriter


class RegisterUser:
    """Enumeration-safe per SRS §8.1: the caller always gets the same 202 shape
    regardless of which branch below actually ran."""

    def __init__(
        self,
        user_repo: UserStore,
        token_repo: VerificationTokenStore,
        outbox_repo: OutboxWriter,
        audit_writer: AuditWriter,
    ) -> None:
        self._users = user_repo
        self._tokens = token_repo
        self._outbox = outbox_repo
        self._audit = audit_writer

    async def execute(
        self,
        *,
        email: str,
        password: str,
        request_id: str | None,
        ip_hash: str | None,
    ) -> None:
        # Hashed before the branch on purpose, not inside the new-account arm.
        # Argon2id costs ~80ms and the other arms cost ~10ms, so hashing only
        # when the address is new made response time a reliable answer to
        # "is this address registered?" - which api-endpoints.md 195 forbids
        # as explicitly as it forbids leaking through body or status.
        password_hash = await hash_password_async(password)
        # Locked, so a concurrent re-registration of the same unverified
        # address cannot pass the cooldown twice (BUG-17).
        existing = await self._users.get_by_email_for_update(email)

        if existing is None:
            # The unique index decides, not the read above: a simultaneous
            # registration of the same new address loses here and falls through
            # to the "already registered" branch instead of a 500 (BUG-01).
            user = await self._users.add_if_absent(email=email, password_hash=password_hash)
            if user is not None:
                await issue_verification_email(
                    user=user, token_repo=self._tokens, outbox_repo=self._outbox
                )
                await self._audit.record(
                    actor_user_id=user.id,
                    action="user.registered",
                    entity_type="User",
                    entity_id=user.id,
                    request_id=request_id,
                    ip_hash=ip_hash,
                )
                return
            existing = await self._users.get_by_email_for_update(email)
            if existing is None:
                return

        if not existing.is_verified and await resend_eligible(
            user=existing, token_repo=self._tokens
        ):
            await issue_verification_email(
                user=existing, token_repo=self._tokens, outbox_repo=self._outbox
            )
            # The same event resend-verification audits (BR-132): mail was
            # issued to an existing account. Server-side only, so it leaks
            # nothing to the caller (BUG-18).
            await self._audit.record(
                actor_user_id=existing.id,
                action="user.verification_resent",
                entity_type="User",
                entity_id=existing.id,
                request_id=request_id,
                ip_hash=ip_hash,
            )

        # Existing verified account, or not yet resend-eligible: no mutation.
        # Returning silently here (same as the branches above) is what makes this
        # enumeration-safe - the caller cannot distinguish any of these outcomes.
