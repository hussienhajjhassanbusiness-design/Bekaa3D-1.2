"""Account deletion by anonymisation (VS-045, F-035, BR-125, BR-126; ADR-047). Argon2 runs
before any lock. Lock order: orders, cart, live offers, `users`, then the rows written."""

from dataclasses import asdict
from datetime import UTC, datetime
from secrets import token_urlsafe
from uuid import UUID

import structlog

from app.identity.application.ports import (
    AccountErasure,
    AddressStore,
    PasswordResetTokenStore,
    SessionStore,
    UserStore,
    VerificationTokenStore,
)
from app.identity.application.security.password_hasher import (
    hash_password_async,
    verify_password_async,
)
from app.identity.domain.anonymisation import (
    administrator_block,
    anonymised_email,
    deletion_block,
)
from app.identity.domain.exceptions import (
    AccountDeletionBlockedError,
    AccountDisabledError,
    InvalidCredentialsError,
)
from app.platform.application.ports.audit_writer import AuditWriter

logger = structlog.get_logger()

ENTITY_TYPE = "User"


class DeleteAccount:
    def __init__(
        self,
        *,
        users: UserStore,
        sessions: SessionStore,
        addresses: AddressStore,
        verification_tokens: VerificationTokenStore,
        reset_tokens: PasswordResetTokenStore,
        erasure: AccountErasure,
        audit: AuditWriter,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._addresses = addresses
        self._verification_tokens = verification_tokens
        self._reset_tokens = reset_tokens
        self._erasure = erasure
        self._audit = audit

    async def execute(
        self, *, user_id: UUID, password: str, request_id: str | None, ip_hash: str | None
    ) -> None:
        user = await self._users.get_by_id(user_id)
        if user is None or not user.can_authenticate:
            raise AccountDisabledError(user_id)
        if not await verify_password_async(password=password, password_hash=user.password_hash):
            raise InvalidCredentialsError()
        if (block := administrator_block(user)) is not None:
            raise AccountDeletionBlockedError(block.value)
        unusable_hash = await hash_password_async(token_urlsafe(32))

        await self._erasure.lock_orders(user_id)
        await self._erasure.lock_cart(user_id)
        await self._erasure.lock_live_offers(user_id)
        locked = await self._users.lock_for_anonymisation(user_id)
        if locked is None or not locked.can_authenticate:
            raise AccountDisabledError(user_id)
        if locked.password_hash != user.password_hash:  # changed since it was verified
            raise InvalidCredentialsError()
        block = deletion_block(
            open_order=await self._erasure.open_order_exists(user_id),
            unsettled_refund=await self._erasure.unsettled_refund_exists(user_id),
        )
        if block is not None:
            raise AccountDeletionBlockedError(block.value)

        now = datetime.now(UTC)
        email = anonymised_email(user_id)
        counts = await self._erasure.erase(user_id, email=email, at=now)
        addresses = await self._addresses.anonymise_all(user_id, at=now)
        tokens = await self._verification_tokens.consume_outstanding_for_user(
            user_id=user_id, at=now
        )
        tokens += await self._reset_tokens.consume_outstanding_for_user(user_id=user_id, at=now)
        locked.anonymise(email=email, password_hash=unusable_hash, at=now)
        await self._users.save_anonymised(locked)
        sessions = await self._sessions.revoke_all_for_user(user_id=user_id, at=now)
        # Counts only: audit_logs outlive the account, so no email or name goes in.
        await self._audit.record(
            actor_user_id=user_id,
            action="user.anonymized",
            entity_type=ENTITY_TYPE,
            entity_id=user_id,
            after_data=asdict(counts)
            | {"addresses": addresses, "tokens_consumed": tokens, "sessions_revoked": sessions},
            request_id=request_id,
            ip_hash=ip_hash,
        )
        await logger.ainfo("account_anonymised", user_id=str(user_id))
