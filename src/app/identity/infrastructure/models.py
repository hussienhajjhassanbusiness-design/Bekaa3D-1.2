import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.identity.domain.enums import MfaMethod, UserRole


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
        server_default=UserRole.CUSTOMER.value,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    # ADR-018. BigInteger rather than Integer: it only ever increases, and while
    # overflowing a 32-bit counter would take an implausible number of resets,
    # the wider column costs nothing and a wrapped epoch would re-validate old
    # credentials. NOT NULL with a server default so every existing row migrates
    # to 0 - the same value a token minted before this claim existed decodes to.
    auth_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))

    __table_args__ = (
        Index(
            "ix_users_email_live",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class SessionModel(Base):
    """One row per browser/device login session (database-design.md 5.3).

    The refresh token itself is never stored - only its SHA-256 hash, so a
    database leak cannot be replayed as a login. `token_version` is what makes
    reuse detection possible without a token-history table: a validly signed
    token carrying an older version than this row is a replayed stolen token."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reuse_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_hash: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("token_version > 0", name="ck_sessions_token_version_positive"),
        Index("ix_sessions_user_id", "user_id"),
        # Supports the future session-purge job scanning for expired live rows;
        # revoked sessions are already dead and do not need to be found by date.
        Index(
            "ix_sessions_expires_at_live",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )


class VerificationTokenModel(Base):
    __tablename__ = "verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_verification_tokens_user_id", "user_id"),
        # database-design.md 19.11 lists verification_tokens(expires_at) for the
        # retention purge; the VS-002 migration omitted it. Partial on
        # used_at IS NULL: redeemed rows are found by the same scan and do not
        # need indexing by date.
        Index(
            "ix_verification_tokens_expires_at_live",
            "expires_at",
            postgresql_where=text("used_at IS NULL"),
        ),
    )


class PasswordResetTokenModel(Base):
    """database-design.md 5.5. Only the SHA-256 hash of the token is stored, so
    a database leak yields nothing that can be redeemed on the reset endpoint.

    Sits beside VerificationTokenModel rather than sharing it: the two prove
    different things, and one table would make a verification token redeemable
    at the reset endpoint."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
        # database-design.md 19.11 lists password_reset_tokens(expires_at) for
        # the retention purge. Partial on used_at IS NULL: rows already redeemed
        # are found by the same scan and do not need to be indexed by date.
        Index(
            "ix_password_reset_tokens_expires_at_live",
            "expires_at",
            postgresql_where=text("used_at IS NULL"),
        ),
    )


class MfaCredentialModel(Base):
    """Second-factor credential, at most one per account (database-design.md 5.6).

    The UNIQUE on `user_id` is the constraint that enforces "one MFA credential
    per account" - an application check alone would lose the race between two
    concurrent enrollments and leave an account with two secrets, either of
    which would then open the admin boundary."""

    __tablename__ = "mfa_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # CASCADE is correct only for a legitimate physical purge; ordinary
        # account closure is anonymisation and never reaches this (5.6 "FK Delete").
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    method: Mapped[MfaMethod] = mapped_column(
        Enum(MfaMethod, name="mfa_method", values_callable=lambda enum: [e.value for e in enum]),
        nullable=False,
        server_default=MfaMethod.TOTP.value,
    )
    # BYTEA, never TEXT: this is ciphertext, not an encoded string, and typing
    # it as bytes keeps it from being concatenated into a log line by accident.
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # RFC 6238 time-step of the last accepted TOTP, so the same one-time code
    # cannot be presented twice inside its ~90-second window (RFC 6238 5.2).
    # NULL until the first TOTP is accepted. BigInteger rather than Integer:
    # the value is a running step count and there is no reason to plan a
    # migration around its eventual width.
    last_totp_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class MfaRecoveryCodeModel(Base):
    """One-time recovery codes for an enabled credential (database-design.md 5.7).

    Codes are stored only as deterministic hashes. See
    identity/domain/recovery_codes.py for why the frozen `code_hash TEXT UNIQUE`
    rules out a salted KDF here."""

    __tablename__ = "mfa_recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    mfa_credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mfa_credentials.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # Exactly the partial index database-design.md 5.7 specifies. Every hot
        # query - redeem a code, count what is left, wipe the set on regeneration
        # - filters on unused rows, and spent codes are dead weight in the index.
        Index(
            "ix_mfa_recovery_codes_unused",
            "mfa_credential_id",
            postgresql_where=text("used_at IS NULL"),
        ),
    )
