from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.api.captcha import CaptchaToken
from app.api.text import Email, PlainStr
from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole

# Verification and reset tokens (BUG-16). Generously above the 43 characters
# `generate_raw_token` produces, so a future longer token needs no API change.
MAX_TOKEN_LENGTH = 128


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    # V1 design assumption (SRS §30.3 leaves this to implementation time):
    # 8 characters minimum, no composition rules - BR-120 explicitly favours
    # minimal registration friction over a stricter policy.
    password: PlainStr = Field(min_length=8, max_length=256)
    captcha_token: CaptchaToken


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Issued tokens are 43 characters; the bound only stops a megabyte-long
    # value being read and hashed before it is refused (BUG-16).
    token: PlainStr = Field(max_length=MAX_TOKEN_LENGTH)


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    captcha_token: CaptchaToken


class RegistrationAccepted(BaseModel):
    message: str = "If eligible, a verification email has been sent."


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    # No min_length here, unlike RegisterRequest: rejecting a short password at
    # the schema would answer before the throttle runs, turning a 422 into a
    # free oracle for "that password is too short to be this account's".
    password: PlainStr = Field(max_length=256)


class SessionRead(BaseModel):
    """What the client learns from a successful login.

    V1 design assumption: api-endpoints.md names `SessionRead` but does not fix
    its fields. Deliberately carries no tokens - those live only in httpOnly
    cookies, and echoing them into a JSON body would hand them straight back to
    any XSS the cookies were meant to defend against."""

    user_id: UUID
    email: EmailStr
    role: UserRole
    email_verified: bool
    session_expires_at: datetime


class MfaSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: PlainStr = Field(max_length=256)


class AccountDeletionRequest(BaseModel):
    """`DELETE /me`: the current password is the fresh-auth check (VS-045)."""

    model_config = ConfigDict(extra="forbid")

    current_password: PlainStr = Field(max_length=256)


class MfaSetupConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: PlainStr = Field(min_length=6, max_length=10)


class MfaVerifyRequest(BaseModel):
    """api-endpoints.md 29.2: "Exactly one second-factor credential is supplied."

    Enforced rather than merely documented, so a caller cannot send both and
    leave the server to pick - which factor was actually checked would then
    depend on evaluation order rather than on the request."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: PlainStr = Field(max_length=128)
    code: PlainStr | None = Field(default=None, min_length=6, max_length=10)
    recovery_code: PlainStr | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def exactly_one_factor(self) -> "MfaVerifyRequest":
        if (self.code is None) == (self.recovery_code is None):
            raise ValueError("Supply exactly one of `code` or `recovery_code`.")
        return self


class MfaRecoveryRegenerateRequest(BaseModel):
    """V1 design assumption: api-endpoints.md names this schema in the endpoint
    table but never lists its fields. Mirrors `MfaSetupRequest` - regeneration
    voids the codes the administrator currently holds, so it is re-authenticated
    the same way enrollment is."""

    model_config = ConfigDict(extra="forbid")

    current_password: PlainStr = Field(max_length=256)


class MfaSetupRead(BaseModel):
    """Enrollment material, returned exactly once by `/auth/mfa/setup`.

    V1 design assumption: api-endpoints.md fixes the name and says "Returns TOTP
    setup material once; secret remains protected", without listing fields.

    This is the one response in the system that deliberately carries a secret,
    because an authenticator app cannot be provisioned without it. It is never
    returned again: `/setup/confirm` and everything after it expose only state,
    and the stored copy is encrypted."""

    secret: str
    otpauth_uri: str
    issuer: str
    account_name: str


class MfaRecoveryCodesRead(BaseModel):
    """The one-time plaintext codes, returned only at generation/regeneration.

    V1 design assumption: named in api-endpoints.md without a field list. Only
    hashes are stored, so there is no endpoint that can ever show these again -
    which is the point, and worth the client telling the administrator."""

    recovery_codes: list[str]
    generated_at: datetime


class MfaChallengeRead(BaseModel):
    """The `202` body from `POST /auth/login` when an administrator still owes
    a second factor (api-endpoints.md:252).

    V1 design assumption: api-endpoints.md names this schema but never lists
    its fields. `challenge_id` is the minimum the client needs in order to call
    `/auth/mfa/verify`; `expires_in_seconds` saves it from having to discover
    the five-minute window by being rejected.

    Note what is deliberately absent. No user id, no email, no role, no
    indication of which second factors are available - the caller has proven a
    password and nothing more, and this response is not the place to confirm
    who the account belongs to or that it is an administrator."""

    challenge_id: str
    expires_in_seconds: int


class UserProfileRead(BaseModel):
    """The authenticated user's own account profile (F-024).

    V1 design assumption: api-endpoints.md 9.1 fixes the response *name* and
    describes its content as "ID, email, verification/account state" without
    listing fields. Deliberately narrow - `updated_at` means nothing to a
    customer, and `anonymized_at`/`deleted_at`/`is_active` would always read
    the same way here because such an account cannot authenticate at all.
    Nothing derived from `password_hash` appears, at any remove."""

    id: UUID
    email: EmailStr
    role: UserRole
    email_verified: bool
    email_verified_at: datetime | None
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "UserProfileRead":
        return cls(
            id=user.id,
            email=user.email,
            role=user.role,
            email_verified=user.is_verified,
            email_verified_at=user.email_verified_at,
            created_at=user.created_at,
        )


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    captcha_token: CaptchaToken


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Issued tokens are 43 characters; the bound only stops a megabyte-long
    # value being read and hashed before it is refused (BUG-16).
    token: PlainStr = Field(max_length=MAX_TOKEN_LENGTH)
    # Same floor as RegisterRequest, and for the same BR-120 reason. A password
    # set through a reset must be no weaker than one set at registration, so the
    # two constraints are deliberately identical rather than merely similar.
    new_password: PlainStr = Field(min_length=8, max_length=256)


class PasswordResetAccepted(BaseModel):
    """Separate from RegistrationAccepted despite the same shape: the message is
    the only thing a caller ever learns from this endpoint, so it must not start
    talking about verification if the registration copy is ever reworded."""

    message: str = "If an account exists for that address, a reset email has been sent."


# --------------------------------------------------------------------------
# Admin user management (VS-009)
# --------------------------------------------------------------------------


class AdminUserDetail(BaseModel):
    """One account as an administrator sees it (api-endpoints.md 530-532).

    V1 design assumption: the endpoint catalogue fixes the schema *names* and
    describes the content as "account status and admin-safe customer summary"
    without listing fields. This is VS-006's `UserProfileRead` plus the two
    pieces of account state an administrator manages and a customer cannot see -
    `is_active`, and `created_at` as the account's age.

    Used for both the list items and the detail response. There is no separate
    profile table, so a narrower list row would differ from this one only by
    omitting fields the same query already loaded.

    Nothing derived from `password_hash` appears, at any remove, and neither
    `anonymized_at` nor `deleted_at` is exposed: V1 has no endpoint that sets
    them, so they would be a column this API describes but cannot explain.
    """

    id: UUID
    email: str  # not EmailStr: an anonymised account's `@invalid` address fails it (VS-045)
    role: UserRole
    is_active: bool
    email_verified_at: datetime | None
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "AdminUserDetail":
        return cls(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            email_verified_at=user.email_verified_at,
            created_at=user.created_at,
        )


class AdminUserPage(BaseModel):
    """The project's standard cursor page (api-endpoints.md 2.1):
    `next_cursor = null` means there is no next page."""

    items: list[AdminUserDetail]
    next_cursor: str | None


class AdminUserUpdate(BaseModel):
    """The only writable field on an account, for anyone, in V1.

    `extra="forbid"` is doing real work here rather than following the house
    style: it is what makes a request carrying `role` or `email` a loud 422
    instead of a silent no-op that the caller reasonably reads as success.
    api-endpoints.md 532 is explicit that this endpoint offers
    "activation/deactivation controls" and no arbitrary field editing.
    """

    model_config = ConfigDict(extra="forbid")

    is_active: bool
