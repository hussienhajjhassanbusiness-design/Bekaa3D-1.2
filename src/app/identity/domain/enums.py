from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class MfaMethod(StrEnum):
    """V1 defines exactly one method (database-design.md 5.6). It is still an
    enum rather than a bare column so adding WebAuthn later is a migration, not
    a hunt for every string literal that assumed TOTP."""

    TOTP = "totp"
