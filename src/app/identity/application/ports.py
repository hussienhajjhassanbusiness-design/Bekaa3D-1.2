"""Identity's repository ports.

Pure `Protocol`s, one per repository: the application layer depends on these,
never on `app.identity.infrastructure` (CLAUDE.md, architecture rules; BUG-41).
Each is generated to match its implementation's public methods exactly, so the
concrete repositories - and every test subclass of them - satisfy it
structurally. The routers (composition) pass the concrete classes in.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.identity.domain.entities import (
    MfaCredential,
    MfaRecoveryCode,
    PasswordResetToken,
    Session,
    User,
    VerificationToken,
)
from app.identity.domain.enums import MfaMethod


class UserStore(Protocol):
    """Implemented by `app.identity.infrastructure.repositories.UserRepository`."""

    async def get_by_email(self, email: str) -> User | None: ...

    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def get_by_email_for_update(self, email: str) -> User | None: ...

    async def list_page(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None = None,
        verified: bool | None = None,
        active: bool | None = None,
        search: str | None = None,
    ) -> list[User]: ...

    async def get_auth_epoch(self, user_id: UUID) -> int | None: ...

    async def lock_administrator_set(self) -> None: ...

    async def count_other_active_administrators(self, *, excluding: UUID) -> int: ...

    async def get_by_id_for_update(self, user_id: UUID) -> User | None: ...

    async def add(self, *, email: str, password_hash: str) -> User: ...

    async def add_if_absent(self, *, email: str, password_hash: str) -> User | None: ...

    async def save(self, user: User) -> None: ...

    async def purge_never_verified_before(self, cutoff: datetime) -> int: ...


class SessionStore(Protocol):
    """Implemented by `app.identity.infrastructure.repositories.SessionRepository`."""

    async def get_owner_id(self, session_id: UUID) -> UUID | None: ...

    async def get_for_update(self, session_id: UUID) -> Session | None: ...

    async def add(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        ip_hash: str | None,
        user_agent: str | None,
    ) -> Session: ...

    async def save(self, session: Session) -> None: ...

    async def revoke_all_for_user(self, *, user_id: UUID, at: datetime) -> int: ...


class VerificationTokenStore(Protocol):
    """Implemented by `app.identity.infrastructure.repositories.VerificationTokenRepository`."""

    async def get_by_hash(self, token_hash: str) -> VerificationToken | None: ...

    async def get_by_hash_for_update(self, token_hash: str) -> VerificationToken | None: ...

    async def get_latest_for_user(self, user_id: UUID) -> VerificationToken | None: ...

    async def add(
        self, *, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> VerificationToken: ...

    async def save(self, token: VerificationToken) -> None: ...


class MfaCredentialStore(Protocol):
    """Implemented by `app.identity.infrastructure.repositories.MfaCredentialRepository`."""

    async def get_by_user_id(self, user_id: UUID) -> MfaCredential | None: ...

    async def get_by_user_id_for_update(self, user_id: UUID) -> MfaCredential | None: ...

    async def add(
        self, *, user_id: UUID, method: MfaMethod, secret_ciphertext: bytes
    ) -> MfaCredential: ...

    async def save(self, credential: MfaCredential) -> None: ...


class MfaRecoveryCodeStore(Protocol):
    """Implemented by `app.identity.infrastructure.repositories.MfaRecoveryCodeRepository`."""

    async def get_unused_by_hash(
        self, *, mfa_credential_id: UUID, code_hash: str
    ) -> MfaRecoveryCode | None: ...

    async def add_set(
        self, *, mfa_credential_id: UUID, code_hashes: Sequence[str]
    ) -> list[MfaRecoveryCode]: ...

    async def count_unused(self, mfa_credential_id: UUID) -> int: ...

    async def delete_unused(self, mfa_credential_id: UUID) -> int: ...

    async def save(self, code: MfaRecoveryCode) -> None: ...


class PasswordResetTokenStore(Protocol):
    """Implemented by `app.identity.infrastructure.repositories.PasswordResetTokenRepository`."""

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None: ...

    async def lock_all_for_user(self, user_id: UUID) -> list[PasswordResetToken]: ...

    async def get_latest_for_user(self, user_id: UUID) -> PasswordResetToken | None: ...

    async def add(
        self, *, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken: ...

    async def save(self, token: PasswordResetToken) -> None: ...

    async def consume_outstanding_for_user(self, *, user_id: UUID, at: datetime) -> int: ...
