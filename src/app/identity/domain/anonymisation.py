"""Account deletion by anonymisation (VS-045, ADR-047). Pure: no framework or database imports."""

from enum import StrEnum
from uuid import UUID

from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole

ANONYMISED_EMAIL_DOMAIN = "invalid"


class DeletionBlock(StrEnum):
    """The `reason` of `409 ACCOUNT_DELETION_BLOCKED`."""

    ADMINISTRATOR = "administrator"
    OPEN_ORDER = "open_order"
    UNSETTLED_REFUND = "unsettled_refund"


def anonymised_email(user_id: UUID) -> str:
    """Unique per account and unregistrable (RFC 6761 `.invalid`), so the old address is free."""
    return f"deleted+{user_id}@{ANONYMISED_EMAIL_DOMAIN}"


def administrator_block(user: User) -> DeletionBlock | None:
    """An administrator is closed by deactivation (VS-011), which keeps the last-admin guard."""
    return DeletionBlock.ADMINISTRATOR if user.role is UserRole.ADMIN else None


def deletion_block(*, open_order: bool, unsettled_refund: bool) -> DeletionBlock | None:
    """BR-126, read under the deletion's locks."""
    if open_order:
        return DeletionBlock.OPEN_ORDER
    if unsettled_refund:
        return DeletionBlock.UNSETTLED_REFUND
    return None
