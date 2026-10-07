"""The "never zero active administrators" rule (BUG-38).

One helper, so every operation that can take an administrator out of the active
set asks the same question the same way. Today only deactivation can
(`SetUserActive`): V1 has no role change, no account deletion and no
anonymisation of administrators, and the unverified-account purge is limited to
customers. A future operation that removes an administrator from the active set
must call `ensure_an_active_administrator_remains` too.
"""

from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import LastActiveAdministratorError

# Arbitrary fixed key for `pg_advisory_xact_lock`, shared by every operation that
# shrinks the active administrator set. Taken before any `users` row lock.
ADMINISTRATOR_SET_LOCK_KEY = 0x62656B6141444D49  # "bekaADMI"


def is_active_administrator(user: User) -> bool:
    """MFA enrolment is deliberately ignored: the rule protects the set of
    accounts that are administrators and live, not the set that can log in today."""
    return user.role is UserRole.ADMIN and user.can_authenticate


def ensure_an_active_administrator_remains(user: User, *, other_active_administrators: int) -> None:
    """Raise if removing `user` from the active set would empty it.

    A no-op for anyone who is not an active administrator now: removing a
    customer, or an administrator already inactive, cannot change the count.
    """
    if is_active_administrator(user) and other_active_administrators < 1:
        raise LastActiveAdministratorError(user.id)
