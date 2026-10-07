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
    InvalidRecoveryCodeError,
    MfaCodeReplayedError,
    MfaNotEnrolledError,
)
from app.identity.domain.recovery_codes import normalize_code
from app.platform.application.ports.audit_writer import AuditWriter


@dataclass(frozen=True)
class MfaVerifyResult:
    used_recovery_code: bool
    remaining_recovery_codes: int


class VerifyMfa:
    """Complete the admin second factor for an already-authenticated session.

    This is a step-up, not a login: the caller already holds a valid session,
    and what happens here is that the session becomes MFA-complete. Marking the
    session and re-issuing its access token is the route's job - this command
    decides only whether the factor was proven."""

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
        code: str | None,
        recovery_code: str | None,
        request_id: str | None,
        ip_hash: str | None,
    ) -> MfaVerifyResult:
        # Locked, not merely read: this method decides whether a TOTP step is
        # spent and then writes the new mark, and two concurrent verifications
        # of the same code must not both pass that check. See
        # MfaCredentialStore.get_by_user_id_for_update.
        credential = await self._credentials.get_by_user_id_for_update(user_id)
        if credential is None or not credential.is_enabled:
            raise MfaNotEnrolledError()

        now = datetime.now(UTC)

        if recovery_code is not None:
            # FOR UPDATE inside the repository: two requests racing the same
            # code serialise there, so exactly one redemption can win.
            stored = await self._recovery.get_unused_by_hash(
                mfa_credential_id=credential.id,
                code_hash=hash_token(normalize_code(recovery_code)),
            )
            if stored is None:
                raise InvalidRecoveryCodeError()
            stored.redeem(now)
            await self._recovery.save(stored)
            remaining = await self._recovery.count_unused(credential.id)

            # Recovery use is the security-sensitive branch SEC-04 wants
            # visible: it means the administrator's authenticator is gone.
            # The code itself is never recorded - only that one was spent.
            await self._audit.record(
                actor_user_id=user_id,
                action="mfa.recovery_code_used",
                entity_type="MfaCredential",
                entity_id=credential.id,
                after_data={"remaining_recovery_codes": remaining},
                request_id=request_id,
                ip_hash=ip_hash,
            )
            # Counts as a use of the credential, but deliberately does not
            # touch `last_totp_step`: a recovery code and a TOTP are separate
            # one-time credentials, and spending one must not consume a step
            # of the other. Recovery codes are already single-use in their own
            # right, enforced by `used_at` plus the row lock.
            credential.mark_used(now)
        else:
            matched_step = (
                None
                if code is None
                else verify_code_step(
                    secret=decrypt_secret(credential.secret_ciphertext), code=code, now=now
                )
            )
            if matched_step is None:
                raise InvalidMfaCodeError()

            if credential.is_totp_step_replayed(matched_step):
                # Recorded, then refused. A correct code arriving a second time
                # is not a typo - it means one was captured - so this is the
                # branch an operator needs to be able to see. Neither the code
                # nor the secret is written: the step number identifies *which*
                # 30-second bucket without being redeemable, and knowing that
                # a replay happened is the whole point.
                await self._audit.record(
                    actor_user_id=user_id,
                    action="mfa.replay_rejected",
                    entity_type="MfaCredential",
                    entity_id=credential.id,
                    after_data={"time_step": matched_step},
                    request_id=request_id,
                    ip_hash=ip_hash,
                )
                # Distinct type so the route can persist that row before
                # answering; the answer itself is the ordinary MFA_INVALID.
                raise MfaCodeReplayedError()

            credential.record_totp_step(matched_step, now)
            remaining = await self._recovery.count_unused(credential.id)
            await self._audit.record(
                actor_user_id=user_id,
                action="mfa.verified",
                entity_type="MfaCredential",
                entity_id=credential.id,
                request_id=request_id,
                ip_hash=ip_hash,
            )

        await self._credentials.save(credential)

        return MfaVerifyResult(
            used_recovery_code=recovery_code is not None,
            remaining_recovery_codes=remaining,
        )
