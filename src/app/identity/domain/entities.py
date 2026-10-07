import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.identity.domain.enums import MfaMethod, UserRole
from app.identity.domain.exceptions import (
    AlreadyVerifiedError,
    InvalidPasswordResetTokenError,
    InvalidRecoveryCodeError,
    InvalidSessionError,
    InvalidVerificationTokenError,
    PasswordResetTokenExpiredError,
    RefreshTokenReuseError,
    SessionExpiredError,
    SessionRevokedError,
    VerificationTokenExpiredError,
)


@dataclass
class User:
    id: UUID
    email: str
    password_hash: str
    role: UserRole
    email_verified_at: datetime | None
    is_active: bool
    anonymized_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Monotonic generation counter for this account's credentials (ADR-018).
    # Every access token and MFA login challenge records the value it was minted
    # under; advancing it invalidates all of them at once. Lives on `users`
    # rather than in Redis because it is the authority for an authentication
    # decision, and losing it must not silently re-validate revoked credentials.
    auth_epoch: int = 0

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def can_authenticate(self) -> bool:
        """Unverified accounts may still log in - they just cannot perform
        protected writes (entities-and-business-rules.md: "Unverified users may
        browse but cannot perform protected write actions"). Only deactivation,
        anonymisation and deletion actually block authentication."""
        return self.is_active and self.anonymized_at is None and self.deleted_at is None

    def mark_verified(self, at: datetime) -> None:
        if self.is_verified:
            raise AlreadyVerifiedError(self.id)
        self.email_verified_at = at
        self.updated_at = at

    def change_password(self, *, new_password_hash: str, at: datetime) -> None:
        """Replace the stored hash.

        Deliberately takes a hash, not a plaintext password: hashing is an
        infrastructure concern (Argon2id), and a domain entity that accepted a
        plaintext password would have to import the hasher and stop being pure.

        Changing the password does not by itself end the user's sessions -
        SEC-08 requires that, but revocation spans the whole `sessions` table
        and so belongs to the use case that owns both repositories."""
        self.password_hash = new_password_hash
        self.updated_at = at

    def invalidate_credentials(self, at: datetime) -> None:
        """Advance the authentication epoch, voiding every credential minted
        under the old one.

        Separate from `change_password` on purpose. They happen together today,
        but they are different statements: one replaces a secret, the other ends
        everything issued while the old secret was current. A future
        admin-forced logout needs the second without the first."""
        self.auth_epoch += 1
        self.updated_at = at

    def set_active(self, *, is_active: bool, at: datetime) -> bool:
        """Activate or deactivate the account. Returns whether anything moved.

        The boolean return is what lets the caller tell a real transition from a
        PATCH restating the current value: only the former should end sessions
        or write an audit row (VS-009).

        Deliberately does *not* touch `auth_epoch`. Deactivation must also void
        credentials already issued, but that is `invalidate_credentials`, and
        keeping the two apart means this method stays usable for the
        reactivation direction, where there is nothing to void. The use case
        owns the decision about which transitions need both, the same way
        `change_password` leaves session revocation to its caller."""
        if is_active is self.is_active:
            return False
        self.is_active = is_active
        self.updated_at = at
        return True


@dataclass
class VerificationToken:
    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def mark_used(self, at: datetime) -> None:
        if self.is_used:
            raise InvalidVerificationTokenError()
        if at >= self.expires_at:
            raise VerificationTokenExpiredError(self.id)
        self.used_at = at


@dataclass
class Session:
    """One browser/device login session, holding rotating refresh-token state.

    Rotation and reuse detection follow database-design.md 5.3 exactly."""

    id: UUID
    user_id: UUID
    refresh_token_hash: str
    token_version: int
    expires_at: datetime
    last_used_at: datetime | None
    rotated_at: datetime | None
    revoked_at: datetime | None
    reuse_detected_at: datetime | None
    ip_hash: str | None
    user_agent: str | None
    created_at: datetime

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, at: datetime) -> bool:
        return at >= self.expires_at

    def is_live(self, at: datetime) -> bool:
        return not self.is_revoked and not self.is_expired(at)

    def authorize_rotation(
        self, *, presented_token_hash: str, presented_version: int, at: datetime
    ) -> None:
        """Decide whether a presented refresh token may rotate this session.

        Order matters. The reuse check must come before the hash check: a
        replayed old token fails both, and reporting it as merely "invalid"
        would leave the stolen session alive."""
        if self.is_revoked:
            raise SessionRevokedError(self.id)
        if self.is_expired(at):
            raise SessionExpiredError(self.id)
        if presented_version < self.token_version:
            raise RefreshTokenReuseError(self.id)
        if presented_version != self.token_version:
            raise InvalidSessionError()
        # compare_digest, not ==, so response time cannot leak how many leading
        # characters of the stored hash an attacker has guessed correctly.
        if not secrets.compare_digest(presented_token_hash, self.refresh_token_hash):
            raise InvalidSessionError()

    def rotate(self, *, new_token_hash: str, at: datetime) -> None:
        self.refresh_token_hash = new_token_hash
        self.token_version += 1
        self.rotated_at = at
        self.last_used_at = at

    def revoke(self, at: datetime) -> None:
        if self.is_revoked:
            return
        self.revoked_at = at

    def mark_reuse_detected(self, at: datetime) -> None:
        """Stolen-token response: record the detection and kill the session."""
        self.reuse_detected_at = at
        self.revoke(at)


@dataclass
class MfaCredential:
    """One account's second factor (database-design.md 5.6).

    `secret_ciphertext` is the encrypted TOTP secret and is deliberately typed
    as opaque bytes: nothing in the domain layer can read it, so no domain rule
    can accidentally end up logging or returning the raw secret."""

    id: UUID
    user_id: UUID
    method: MfaMethod
    secret_ciphertext: bytes
    enabled_at: datetime | None
    last_used_at: datetime | None
    # The RFC 6238 time-step of the last TOTP this credential accepted, or None
    # if it has never accepted one. Deliberately separate from `last_used_at`:
    # that column means "last authenticated by any means", and a recovery-code
    # redemption must not consume a TOTP step it has nothing to do with.
    last_totp_step: int | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_enabled(self) -> bool:
        """Enrollment alone does not grant admin access - only confirmation
        does. Everything gating the admin boundary must ask this, never merely
        whether a credential row exists."""
        return self.enabled_at is not None

    def enable(self, at: datetime) -> None:
        """Called only once a real TOTP has been verified against the enrolled
        secret. Re-confirming an already-enabled credential keeps the original
        timestamp, so this records when MFA was first trusted rather than when
        it was last exercised - `last_used_at` is what tracks the latter."""
        if not self.is_enabled:
            self.enabled_at = at
        self.updated_at = at

    def mark_used(self, at: datetime) -> None:
        self.last_used_at = at
        self.updated_at = at

    def is_totp_step_replayed(self, step: int) -> bool:
        """Whether this credential has already accepted a TOTP at `step`.

        RFC 6238 5.2: a verifier must not accept the same OTP twice. The
        validity window is roughly 90 seconds wide, so without this an attacker
        who captures one live code - a phishing proxy, a glance at a screen -
        can replay it, which is precisely the interception MFA is supposed to
        make useless.

        A high-water mark rather than a list of spent codes: `<=` rather than
        `==`, because the window looks one step backwards as well, and a code
        from the previous step is just as replayable if only equality were
        checked."""
        if self.last_totp_step is None:
            return False
        return step <= self.last_totp_step

    def record_totp_step(self, step: int, at: datetime) -> None:
        """Spend a TOTP step, and count it as a use of the credential.

        Only ever called with a step this credential has just accepted a code
        for. `max` guards the ordering: two requests can interleave, and the
        mark must never move backwards or an already-spent step would become
        redeemable again."""
        self.last_totp_step = (
            step if self.last_totp_step is None else max(self.last_totp_step, step)
        )
        self.mark_used(at)


@dataclass
class MfaRecoveryCode:
    """A single one-time recovery code (database-design.md 5.7).

    Only the hash is held here; the plaintext exists solely in the response
    that generated it and in whatever the administrator wrote down."""

    id: UUID
    mfa_credential_id: UUID
    code_hash: str
    used_at: datetime | None
    created_at: datetime

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def redeem(self, at: datetime) -> None:
        """Consume this code, or refuse if it is already spent.

        The guard is what makes the code one-time-use in the domain, but it is
        not on its own sufficient under concurrency: two requests that both read
        an unused row would both pass here. The repository takes a row lock for
        that reason - see MfaRecoveryCodeRepository.get_unused_by_hash."""
        if self.is_used:
            raise InvalidRecoveryCodeError()
        self.used_at = at


@dataclass
class PasswordResetToken:
    """A single-use, short-lived permission to replace one account's password.

    Structurally the same as VerificationToken but deliberately a separate type:
    the two prove different things (control of the mailbox vs. authority to
    change a credential), and one shared class would make it possible to redeem
    a verification token on the reset endpoint."""

    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def mark_used(self, at: datetime) -> None:
        # Used is checked before expiry so a replayed token always reads as
        # "invalid" (400) rather than eventually turning into "expired" (410)
        # once its window passes - the status code must not depend on timing.
        if self.is_used:
            raise InvalidPasswordResetTokenError()
        if at >= self.expires_at:
            raise PasswordResetTokenExpiredError(self.id)
        self.used_at = at
