from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"


class MfaMethod(StrEnum):
    """V1 defines exactly one method (database-design.md 5.6). It is still an
    enum rather than a bare column so adding WebAuthn later is a migration, not
    a hunt for every string literal that assumed TOTP."""

    TOTP = "totp"


class Governorate(StrEnum):
    """Lebanon's nine governorates (VS-026 Q2); addresses are Lebanese only (BR-071)."""

    AKKAR = "akkar"
    BAALBEK_HERMEL = "baalbek_hermel"
    BEIRUT = "beirut"
    BEQAA = "beqaa"
    KESERWAN_JBEIL = "keserwan_jbeil"
    MOUNT_LEBANON = "mount_lebanon"
    NABATIEH = "nabatieh"
    NORTH = "north"
    SOUTH = "south"
