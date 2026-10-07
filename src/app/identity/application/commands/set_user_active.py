"""Administrator activation/deactivation of an account (VS-009, F-116).

The only mutation `PATCH /api/v1/admin/users/{user_id}` performs. It is small,
but it is the one admin operation that revokes somebody else's access, so the
ordering below is deliberate rather than incidental.

Why deactivation also ends sessions and bumps the epoch
-------------------------------------------------------
`require_admin` and `current_claims` authorise from the signed access token plus
one scalar read of `users.auth_epoch` (ADR-018). Neither re-reads `is_active`.
Clearing the column alone would therefore leave the deactivated account's
current access token working for the remainder of its fifteen minutes - and for
an administrator that includes the very endpoint that could turn the account
back on. Advancing the epoch closes that window immediately, and revoking the
session rows stops refresh from minting a replacement.

Nothing in the SRS requires this: SEC-08 mandates revocation on *password
change* only, and no document states what deactivation does to a live session.
This is a V1 decision recorded here and in the slice's PR rather than a
requirement being implemented.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from app.identity.application.ports import SessionStore, UserStore
from app.identity.domain.administrators import ensure_an_active_administrator_remains
from app.identity.domain.entities import User
from app.identity.domain.exceptions import AccountNotMutableError, LastActiveAdministratorError
from app.platform.application.ports.audit_writer import AuditWriter

logger = structlog.get_logger()

ENTITY_TYPE = "User"


@dataclass(frozen=True)
class SetUserActiveResult:
    """What the route needs to answer with, and nothing more.

    `changed` is false for a PATCH that restated the value already stored. That
    is a successful no-op, not an error: the caller asked for a state the account
    is already in, and it is in it.
    """

    user: User
    changed: bool
    sessions_revoked: int


class SetUserActive:
    def __init__(
        self,
        users: UserStore,
        sessions: SessionStore,
        audit: AuditWriter,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._audit = audit

    async def execute(
        self,
        *,
        user_id: UUID,
        is_active: bool,
        actor_user_id: UUID,
        request_id: str | None,
        ip_hash: str | None,
    ) -> SetUserActiveResult | None:
        """Returns None when no such user exists, so the route can 404.

        A `None` return rather than an exception because "no such row" is the one
        outcome here that is not a domain rule - it is the absence of anything to
        apply a rule to, and the route's answer to it (`not_found_error()`) is
        the same 404 the admin boundary already gives an unauthorised caller.
        """
        if not is_active:
            # Before ANY row lock (BUG-38): the last-administrator count is only
            # meaningful if no other deactivation can commit between it and our
            # write. Serialises deactivations only; reactivation needs no count.
            await self._users.lock_administrator_set()

        # Locked read first. Everything below - the terminal-state guard, the
        # audit "before", the save - has to act on the row as it is now rather
        # than as it was before a concurrent transaction committed.
        #
        # LOCK ORDER: `users` before `sessions`, always, matching
        # confirm_password_reset.py. Taking the session rows first here would
        # close a cycle against a password reset running concurrently on the same
        # account and PostgreSQL would resolve it as DeadlockDetectedError. Do not
        # reorder the save and the revocation below to "save a round trip".
        user = await self._users.get_by_id_for_update(user_id)
        if user is None:
            return None

        if user.anonymized_at is not None or user.deleted_at is not None:
            # Terminal states. See AccountNotMutableError for why neither
            # direction is meaningful on such a row.
            raise AccountNotMutableError(user_id)

        before_active = user.is_active
        now = datetime.now(UTC)

        if before_active and not is_active:
            try:
                ensure_an_active_administrator_remains(
                    user,
                    other_active_administrators=await self._users.count_other_active_administrators(
                        excluding=user.id
                    ),
                )
            except LastActiveAdministratorError:
                # Nothing has been written: the request's transaction rolls back
                # with the exception. No audit row for an action that did not
                # happen; ids only in the log (never the address).
                await logger.awarning(
                    "last_active_administrator_protected",
                    user_id=str(user.id),
                    actor_user_id=str(actor_user_id),
                )
                raise

        if not user.set_active(is_active=is_active, at=now):
            # No transition. No session revocation, no epoch bump, and
            # deliberately no audit row: the account's state is untouched, and a
            # row showing an identical before/after would describe an event that
            # did not happen. (VS-007 and VS-010 audit unconditionally because
            # their PATCHes carry several fields and a "nothing moved" row is
            # still evidence of an administrator touching the resource; this
            # endpoint has one field, so "nothing moved" means nothing happened.)
            return SetUserActiveResult(user=user, changed=False, sessions_revoked=0)

        # Deactivation only. On reactivation there is nothing to void: the
        # deactivation that preceded it already revoked every session, and a
        # revoked session stays revoked.
        deactivating = before_active and not is_active
        if deactivating:
            user.invalidate_credentials(now)

        await self._users.save(user)

        sessions_revoked = 0
        if deactivating:
            sessions_revoked = await self._sessions.revoke_all_for_user(user_id=user.id, at=now)

        action = "user.activated" if is_active else "user.deactivated"
        # No email, role, password material or verification state in either
        # payload. `audit_logs` is retained permanently, so an address written
        # here would outlive the account's own anonymisation and quietly defeat
        # it - which is why this does not follow VS-010's whole-row
        # `audit_snapshot()` convention. Reference data has no PII; users do.
        after_data: dict[str, Any] = {"is_active": is_active}
        if not is_active:
            after_data["sessions_revoked"] = sessions_revoked

        await self._audit.record(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=ENTITY_TYPE,
            entity_id=user.id,
            before_data={"is_active": before_active},
            after_data=after_data,
            request_id=request_id,
            ip_hash=ip_hash,
        )

        # Identifiers only. `core/logging.py` redacts as a last line of defence,
        # but SEC-26 is kept here by never binding the address in the first place.
        await logger.ainfo(
            "admin_user_active_changed",
            user_id=str(user.id),
            actor_user_id=str(actor_user_id),
            is_active=is_active,
            sessions_revoked=sessions_revoked,
        )

        return SetUserActiveResult(user=user, changed=True, sessions_revoked=sessions_revoked)
