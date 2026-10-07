from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.identity.application.ports import (
    MfaCredentialStore,
    MfaRecoveryCodeStore,
)
from app.identity.application.security.secret_cipher import decrypt_secret
from app.identity.application.security.token_service import hash_token
from app.identity.application.security.totp import verify_code_step
from app.identity.domain.exceptions import (
    InvalidMfaCodeError,
    MfaAlreadyEnabledError,
    MfaNotEnrolledError,
)
from app.identity.domain.recovery_codes import generate_code_set, normalize_code
from app.platform.application.ports.audit_writer import AuditWriter


@dataclass(frozen=True)
class MfaConfirmSetupResult:
    recovery_codes: list[str]
    generated_at: datetime


class ConfirmMfaSetup:
    """Finish enrollment: prove the authenticator works, then enable MFA.

    Enabling only after a real code has been produced is what stops an
    administrator locking themselves out by enrolling against a secret their
    phone never actually stored."""

    def __init__(
        self,
        credential_repo: MfaCredentialStore,
        recovery_repo: MfaRecoveryCodeStore,
        audit_writer: AuditWriter,
    ) -> None:
        self._credentials = credential_repo
        self._recovery = recovery_repo
        self._audit = audit_writer

    async def execute(
        self,
        *,
        user_id: UUID,
        code: str,
        request_id: str | None,
        ip_hash: str | None,
    ) -> MfaConfirmSetupResult:
        # Locked for the same reason as the verify path: this writes both
        # `enabled_at` and `last_totp_step` after reading them.
        credential = await self._credentials.get_by_user_id_for_update(user_id)
        if credential is None:
            raise MfaNotEnrolledError()

        # Confirmation is a one-time step in enrollment, not a repeatable
        # operation. Without this guard a caller holding an admin session and a
        # single valid TOTP could re-confirm an already-enabled credential,
        # which wipes the unused recovery-code set and issues a fresh one -
        # i.e. a second route to regeneration that skips the password
        # `/auth/mfa/recovery-codes/regenerate` deliberately demands. Two doors
        # to one action, and the weaker lock is the one that counts.
        #
        # Re-enrolling a *new* secret is likewise refused here and in
        # `MfaSetup`; it is a disable-then-enrol flow, which V1 does not define.
        if credential.is_enabled:
            raise MfaAlreadyEnabledError()

        now = datetime.now(UTC)
        matched_step = verify_code_step(
            secret=decrypt_secret(credential.secret_ciphertext), code=code, now=now
        )
        if matched_step is None:
            raise InvalidMfaCodeError()

        credential.enable(now)
        # Confirmation accepts a real TOTP, so its step is spent like any
        # other. Without this the very code that proved the authenticator
        # works would still be redeemable at `/auth/mfa/verify`.
        credential.record_totp_step(matched_step, now)
        await self._credentials.save(credential)

        # A first set replaces anything left over from an earlier abandoned
        # enrollment, so codes printed against a discarded secret cannot linger.
        await self._recovery.delete_unused(credential.id)
        codes = generate_code_set()
        await self._recovery.add_set(
            mfa_credential_id=credential.id,
            code_hashes=[hash_token(normalize_code(plaintext)) for plaintext in codes],
        )

        await self._audit.record(
            actor_user_id=user_id,
            action="mfa.enabled",
            entity_type="MfaCredential",
            entity_id=credential.id,
            # Counts only. The codes themselves must never reach an audit row.
            after_data={"recovery_codes_issued": len(codes)},
            request_id=request_id,
            ip_hash=ip_hash,
        )

        return MfaConfirmSetupResult(recovery_codes=codes, generated_at=now)
