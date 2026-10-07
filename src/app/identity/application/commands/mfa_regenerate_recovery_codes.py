from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.identity.application.ports import (
    MfaCredentialStore,
    MfaRecoveryCodeStore,
    UserStore,
)
from app.identity.application.security.password_hasher import verify_password_async
from app.identity.application.security.token_service import hash_token
from app.identity.domain.exceptions import InvalidCredentialsError, MfaNotEnrolledError
from app.identity.domain.recovery_codes import generate_code_set, normalize_code
from app.platform.application.ports.audit_writer import AuditWriter


@dataclass(frozen=True)
class MfaRecoveryCodesResult:
    recovery_codes: list[str]
    generated_at: datetime


class RegenerateRecoveryCodes:
    """Replace the unused recovery-code set with a fresh one."""

    def __init__(
        self,
        user_repo: UserStore,
        credential_repo: MfaCredentialStore,
        recovery_repo: MfaRecoveryCodeStore,
        audit_writer: AuditWriter,
    ) -> None:
        self._users = user_repo
        self._credentials = credential_repo
        self._recovery = recovery_repo
        self._audit = audit_writer

    async def execute(
        self,
        *,
        user_id: UUID,
        current_password: str,
        request_id: str | None,
        ip_hash: str | None,
    ) -> MfaRecoveryCodesResult:
        user = await self._users.get_by_id(user_id)
        if user is None or not user.can_authenticate:
            raise MfaNotEnrolledError()

        # Regeneration both voids the codes the administrator is holding and
        # mints replacements, so it is worth a password even though the caller
        # is already Admin + MFA.
        if not await verify_password_async(
            password=current_password, password_hash=user.password_hash
        ):
            raise InvalidCredentialsError()

        # Locked: simultaneous regenerations each deleted the unused set and
        # inserted a new one, leaving several live sets (BUG-32). Serialised on
        # the credential row, each one replaces the set the previous one left.
        credential = await self._credentials.get_by_user_id_for_update(user_id)
        if credential is None or not credential.is_enabled:
            raise MfaNotEnrolledError()

        invalidated = await self._recovery.delete_unused(credential.id)
        codes = generate_code_set()
        await self._recovery.add_set(
            mfa_credential_id=credential.id,
            code_hashes=[hash_token(normalize_code(plaintext)) for plaintext in codes],
        )

        await self._audit.record(
            actor_user_id=user_id,
            action="mfa.recovery_codes_regenerated",
            entity_type="MfaCredential",
            entity_id=credential.id,
            # Counts only, on both sides. No code, hash, or password.
            before_data={"unused_codes_invalidated": invalidated},
            after_data={"recovery_codes_issued": len(codes)},
            request_id=request_id,
            ip_hash=ip_hash,
        )

        return MfaRecoveryCodesResult(recovery_codes=codes, generated_at=datetime.now(UTC))
