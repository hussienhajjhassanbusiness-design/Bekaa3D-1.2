from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    CursorResult,
    DateTime,
    delete,
    func,
    literal,
    or_,
    select,
    tuple_,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.administrators import ADMINISTRATOR_SET_LOCK_KEY
from app.identity.domain.entities import (
    MfaCredential,
    MfaRecoveryCode,
    PasswordResetToken,
    Session,
    User,
    VerificationToken,
)
from app.identity.domain.enums import MfaMethod, UserRole
from app.identity.infrastructure.models import (
    MfaCredentialModel,
    MfaRecoveryCodeModel,
    PasswordResetTokenModel,
    SessionModel,
    UserModel,
    VerificationTokenModel,
)


async def _delete_batch_skip_locked(
    session: AsyncSession, model: Any, predicate: ColumnElement[bool], limit: int
) -> int:
    """Delete up to `limit` matching rows, skipping any another transaction holds (VS-046).
    It never waits on a row lock, so it cannot join a deadlock cycle (ADR-018 lock order)."""
    victims = (
        select(model.id).where(predicate).limit(limit).with_for_update(skip_locked=True)
    ).scalar_subquery()
    stmt = (
        delete(model)
        .where(model.id.in_(victims))
        .returning(model.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.scalars(stmt)).all())


# Naming note: `self._session` throughout this module is the SQLAlchemy
# AsyncSession (the unit of work). `Session` is our own login-session entity.
# Different things that unfortunately share a word.

LIVE_EMAIL_INDEX = "ix_users_email_live"


def _violates(error: IntegrityError, constraint: str) -> bool:
    """Whether this IntegrityError is specifically `constraint`, read from the
    driver's own `constraint_name` (same approach as the catalogue's slug index)."""
    cause = getattr(error.orig, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    if isinstance(name, str):
        return name == constraint
    return constraint in str(getattr(error, "orig", error))


def _user_to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        email=str(model.email),
        password_hash=model.password_hash,
        role=model.role,
        email_verified_at=model.email_verified_at,
        is_active=model.is_active,
        anonymized_at=model.anonymized_at,
        deleted_at=model.deleted_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        auth_epoch=model.auth_epoch,
    )


def _session_to_domain(model: SessionModel) -> Session:
    return Session(
        id=model.id,
        user_id=model.user_id,
        refresh_token_hash=model.refresh_token_hash,
        token_version=model.token_version,
        expires_at=model.expires_at,
        last_used_at=model.last_used_at,
        rotated_at=model.rotated_at,
        revoked_at=model.revoked_at,
        reuse_detected_at=model.reuse_detected_at,
        ip_hash=model.ip_hash,
        user_agent=model.user_agent,
        created_at=model.created_at,
    )


def _token_to_domain(model: VerificationTokenModel) -> VerificationToken:
    return VerificationToken(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        expires_at=model.expires_at,
        used_at=model.used_at,
        created_at=model.created_at,
    )


def _mfa_credential_to_domain(model: MfaCredentialModel) -> MfaCredential:
    return MfaCredential(
        id=model.id,
        user_id=model.user_id,
        method=model.method,
        secret_ciphertext=bytes(model.secret_ciphertext),
        enabled_at=model.enabled_at,
        last_used_at=model.last_used_at,
        last_totp_step=model.last_totp_step,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _mfa_recovery_code_to_domain(model: MfaRecoveryCodeModel) -> MfaRecoveryCode:
    return MfaRecoveryCode(
        id=model.id,
        mfa_credential_id=model.mfa_credential_id,
        code_hash=model.code_hash,
        used_at=model.used_at,
        created_at=model.created_at,
    )


def _reset_token_to_domain(model: PasswordResetTokenModel) -> PasswordResetToken:
    return PasswordResetToken(
        id=model.id,
        user_id=model.user_id,
        token_hash=model.token_hash,
        expires_at=model.expires_at,
        used_at=model.used_at,
        created_at=model.created_at,
    )


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email, UserModel.deleted_at.is_(None))
        model = await self._session.scalar(stmt)
        return _user_to_domain(model) if model else None

    async def get_by_id(self, user_id: UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return _user_to_domain(model) if model else None

    async def get_by_email_for_update(self, email: str) -> User | None:
        """The live account for `email`, row-locked until the transaction ends.

        Serialises the check-then-insert cooldowns (resend, reset request,
        re-registration): concurrent requests for one account queue here, and
        each one after the first sees the token its predecessor issued (BUG-17).
        Lock order is `users` first, like everywhere else."""
        stmt = (
            select(UserModel)
            .where(UserModel.email == email, UserModel.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(stmt)
        return _user_to_domain(model) if model else None

    async def list_page(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None = None,
        verified: bool | None = None,
        active: bool | None = None,
        search: str | None = None,
    ) -> list[User]:
        """One page of accounts for the admin list, newest first (VS-009).

        Sort is fixed to `-created_at` with `id` as the tie-breaker
        (api-endpoints.md 530) and is not client-selectable: a caller-chosen sort
        column would need a matching index per column to stay a range scan, and
        the contract names exactly one order.

        Anonymised and soft-deleted rows are included: this is the
        administrator's own view of the account table, and an invisible filter
        would hide accounts from the one role that may need to find them. Note
        the consequence - `AdminUserDetail` carries neither `anonymized_at` nor
        `deleted_at`, so such a row is not visually distinct in the list and
        announces itself only as a 409 from the PATCH. Nothing in V1 sets either
        column (the purge job hard-deletes instead), so no row reaches that state
        yet; revisit the schema alongside whichever slice introduces the first
        writer.
        """
        stmt = select(UserModel)

        if verified is True:
            stmt = stmt.where(UserModel.email_verified_at.is_not(None))
        elif verified is False:
            stmt = stmt.where(UserModel.email_verified_at.is_(None))

        if active is not None:
            stmt = stmt.where(UserModel.is_active.is_(active))

        if search:
            # `email` is CITEXT, whose LIKE operator is case-insensitive, so this
            # needs no lower() wrapper - and adding one would cast away the type
            # and defeat any index on it. `autoescape` neutralises `%` and `_`
            # in the search term, which are ordinary characters in an address and
            # must not act as wildcards the caller did not ask for.
            stmt = stmt.where(UserModel.email.contains(search, autoescape=True))

        if after is not None:
            # Row-value comparison, matching the ORDER BY below so the predicate
            # can be satisfied by a single range scan. The `id` half is not
            # decoration: `created_at` is not unique, and without a tie-breaker
            # two accounts sharing a timestamp straddle a page boundary - one is
            # served twice and the other never.
            after_created_at, after_id = after
            stmt = stmt.where(
                tuple_(UserModel.created_at, UserModel.id)
                < tuple_(
                    # Typed literals rather than bare values: asyncpg binds
                    # parameters with an explicit type, and an untyped datetime or
                    # UUID here is sent as text for PostgreSQL to guess at.
                    literal(after_created_at, DateTime(timezone=True)),
                    literal(after_id, postgresql.UUID(as_uuid=True)),
                )
            )

        stmt = stmt.order_by(UserModel.created_at.desc(), UserModel.id.desc()).limit(limit)
        models = (await self._session.scalars(stmt)).all()
        return [_user_to_domain(model) for model in models]

    async def get_auth_epoch(self, user_id: UUID) -> int | None:
        """The account's current authentication epoch, or None if no such user.

        Deliberately one indexed scalar rather than `get_by_id`: this runs on
        every authenticated request (ADR-018), and hydrating a whole `User` -
        password hash included - to read one integer would be wasteful and would
        put the credential in memory on a path that has no use for it."""
        stmt = select(UserModel.auth_epoch).where(UserModel.id == user_id)
        epoch: int | None = await self._session.scalar(stmt)
        return epoch

    async def lock_administrator_set(self) -> None:
        """Serialise every operation that can shrink the active administrator set.

        A transaction-scoped advisory lock, taken BEFORE any `users` row lock.
        Row locks alone cannot protect a count: two administrators deactivating
        each other each lock only their own target, each still sees the other
        active, and both succeed. Holders of this lock only ever wait on row
        locks, and nobody holding a row lock waits on it, so it cannot form a
        cycle with the password-reset or session-revocation lock order
        (`users` before `sessions`)."""
        await self._session.execute(select(func.pg_advisory_xact_lock(ADMINISTRATOR_SET_LOCK_KEY)))

    async def count_other_active_administrators(self, *, excluding: UUID) -> int:
        """Active administrators other than `excluding`, read fresh (READ
        COMMITTED), so it must be called after `lock_administrator_set`."""
        count = await self._session.scalar(
            select(func.count())
            .select_from(UserModel)
            .where(
                UserModel.role == UserRole.ADMIN,
                UserModel.is_active.is_(True),
                UserModel.anonymized_at.is_(None),
                UserModel.deleted_at.is_(None),
                UserModel.id != excluding,
            )
        )
        return int(count or 0)

    async def active_administrator_ids(self) -> list[UUID]:
        """Who receives an administrator notification (VS-034); oldest first, for stable tests."""
        stmt = (
            select(UserModel.id)
            .where(
                UserModel.role == UserRole.ADMIN,
                UserModel.is_active.is_(True),
                UserModel.anonymized_at.is_(None),
                UserModel.deleted_at.is_(None),
            )
            .order_by(UserModel.created_at, UserModel.id)
        )
        return list((await self._session.scalars(stmt)).all())

    async def active_administrator_contacts(self) -> list[tuple[UUID, str]]:
        """Active, live administrators with a verified email: who gets a payment alert."""
        stmt = (
            select(UserModel.id, UserModel.email)
            .where(
                UserModel.role == UserRole.ADMIN,
                UserModel.is_active.is_(True),
                UserModel.email_verified_at.is_not(None),
                UserModel.anonymized_at.is_(None),
                UserModel.deleted_at.is_(None),
            )
            .order_by(UserModel.created_at, UserModel.id)
        )
        return [(row.id, row.email) for row in await self._session.execute(stmt)]

    async def get_by_id_for_update(self, user_id: UUID) -> User | None:
        """Read one user and hold a row lock on them until the transaction ends.

        This is the serialisation point between a password reset and the
        completion of an MFA login challenge that was issued before it. Both
        take this lock, so the reset's `revoke_all_for_user` and
        `CompleteMfaLogin`'s session INSERT can never interleave: whichever
        arrives second sees the other's committed work.

        `populate_existing` for the same reason MfaCredentialRepository needs
        it - without it SQLAlchemy hands back the instance already in this
        session's identity map, and the post-lock read would return pre-lock
        data."""
        stmt = (
            select(UserModel)
            .where(UserModel.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(stmt)
        return _user_to_domain(model) if model else None

    async def add(self, *, email: str, password_hash: str) -> User:
        model = UserModel(email=email, password_hash=password_hash)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _user_to_domain(model)

    async def add_if_absent(self, *, email: str, password_hash: str) -> User | None:
        """Insert a new account, or return None if a live one already holds the
        address.

        The partial unique index is the authority, not a prior read: two
        simultaneous registrations of one address both pass a `SELECT`, and the
        loser's INSERT used to escape as a 500 (BUG-01). The INSERT runs in a
        SAVEPOINT so losing the race rolls back only itself and the request's
        transaction carries on down the "address already registered" branch."""
        model = UserModel(email=email, password_hash=password_hash)
        try:
            async with self._session.begin_nested():
                self._session.add(model)
                await self._session.flush()
        except IntegrityError as exc:
            if not _violates(exc, LIVE_EMAIL_INDEX):
                raise
            return None
        await self._session.refresh(model)
        return _user_to_domain(model)

    async def save(self, user: User) -> None:
        model = await self._session.get(UserModel, user.id)
        if model is None:
            raise ValueError(f"User {user.id} not found")
        # password_hash is written back because VS-004 lets a password change
        # after the row exists. `email` is still absent on purpose - changing an
        # address is a verification flow of its own, not a silent field update.
        model.password_hash = user.password_hash
        model.email_verified_at = user.email_verified_at
        model.is_active = user.is_active
        model.anonymized_at = user.anonymized_at
        model.deleted_at = user.deleted_at
        model.auth_epoch = user.auth_epoch
        await self._session.flush()

    async def purge_never_verified_before(self, cutoff: datetime) -> int:
        """Physically delete accounts that were never verified and are older
        than `cutoff`. Returns how many went.

        FR-02 requires this ("Never-verified accounts are purged after the
        configured period") and database-design.md 5.1 explicitly permits a
        physical purge for this one case, in contrast to the anonymise-rather-
        than-delete rule that governs verified customers. The filter is
        `email_verified_at IS NULL`, so a verified account can never be caught
        by it regardless of age.

        Child rows go with the user through the schema's own foreign keys:
        verification_tokens and sessions are ON DELETE CASCADE, while
        email_outbox and audit_logs are ON DELETE SET NULL so the delivery and
        audit history survives the account it referred to.

        Customers only (BUG-19). An administrator is provisioned by promotion
        rather than self-registration, may never have verified an address, and
        deleting one is irreversible - the purge exists to clear abandoned
        sign-ups, not staff accounts.
        """
        stmt = (
            delete(UserModel)
            .where(
                UserModel.email_verified_at.is_(None),
                UserModel.created_at < cutoff,
                UserModel.role == UserRole.CUSTOMER,
            )
            .returning(UserModel.id)
        )
        purged_ids = (await self._session.scalars(stmt)).all()
        await self._session.flush()
        return len(purged_ids)


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owner_id(self, session_id: UUID) -> UUID | None:
        """Whose session this is, without taking any lock.

        Exists solely so refresh can obey the `users`-before-`sessions` lock
        order: it has a session id and needs the user row locked first, and it
        cannot learn which user that is without looking. Deliberately reads one
        column and decides nothing - every condition that matters is revalidated
        afterwards against the locked re-read of the session."""
        stmt = select(SessionModel.user_id).where(SessionModel.id == session_id)
        owner_id: UUID | None = await self._session.scalar(stmt)
        return owner_id

    async def get_for_update(self, session_id: UUID) -> Session | None:
        """Read one session row and hold a row lock until the transaction ends.

        `SELECT ... FOR UPDATE` is what makes rotation safe under concurrency:
        if the same refresh token is submitted twice at once, the second
        transaction blocks here until the first commits, then reads the
        *already rotated* row and correctly sees its own token as stale.

        Without the lock both would read version N, both would pass validation,
        and a replayed token would go undetected (FR-02: "when the same refresh
        token is submitted concurrently, at most one rotation succeeds").

        **Lock order: `users` before `sessions`.** A caller that needs both -
        refresh does, since VS-004 - must take the user lock first. A password
        reset locks the user row and then updates that user's session rows, so a
        caller acquiring them the other way round closes a deadlock cycle. See
        `RefreshSession.execute`.

        `populate_existing` because that caller reads the session unlocked first
        (to learn whose it is), which leaves a stale instance in the identity
        map; without it SQLAlchemy would hand that back instead of the row as it
        stands under the lock."""
        stmt = (
            select(SessionModel)
            .where(SessionModel.id == session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(stmt)
        return _session_to_domain(model) if model else None

    async def add(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        ip_hash: str | None,
        user_agent: str | None,
    ) -> Session:
        """The id is supplied by the caller rather than the database default,
        because the refresh token has to embed the session id *before* the row
        exists - the row stores that token's hash. Minting first and inserting
        once is simpler than inserting a placeholder and updating it."""
        model = SessionModel(
            id=session_id,
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            ip_hash=ip_hash,
            user_agent=user_agent,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _session_to_domain(model)

    async def save(self, session: Session) -> None:
        # expires_at is deliberately absent: rotation does not extend a
        # session's lifetime, so a stolen-and-refreshed session still dies on
        # the original deadline (database-design.md 5.3 lists no expiry update).
        model = await self._session.get(SessionModel, session.id)
        if model is None:
            raise ValueError(f"Session {session.id} not found")
        model.refresh_token_hash = session.refresh_token_hash
        model.token_version = session.token_version
        model.last_used_at = session.last_used_at
        model.rotated_at = session.rotated_at
        model.revoked_at = session.revoked_at
        model.reuse_detected_at = session.reuse_detected_at
        await self._session.flush()

    async def revoke_all_for_user(self, *, user_id: UUID, at: datetime) -> int:
        """Revoke every live session this user has. Returns how many died.

        SEC-08 requires this on password change, and it is deliberately one
        UPDATE rather than a load-mutate-save loop over Session entities: the
        point of the operation is that no session survives it, and a loop leaves
        a window in which a session created after the read is missed. The
        `revoked_at IS NULL` filter makes it idempotent and keeps an earlier
        revocation timestamp - including a `reuse_detected_at` one - intact.

        A session created *concurrently* by an in-flight MFA login is handled by
        the caller holding the user row lock, not by this statement - see
        UserRepository.get_by_id_for_update."""
        stmt = (
            update(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
            .values(revoked_at=at)
            .returning(SessionModel.id)
        )
        revoked_ids = (await self._session.scalars(stmt)).all()
        await self._session.flush()
        return len(revoked_ids)

    async def delete_ended_batch(self, *, cutoff: datetime, limit: int) -> int:
        """Sessions that ended (expired or revoked, whichever came first) before `cutoff`.
        A live row has revoked_at NULL and expires_at in the future, so cannot match."""
        ended = or_(SessionModel.expires_at < cutoff, SessionModel.revoked_at < cutoff)
        return await _delete_batch_skip_locked(self._session, SessionModel, ended, limit)


class VerificationTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, token_hash: str) -> VerificationToken | None:
        stmt = select(VerificationTokenModel).where(VerificationTokenModel.token_hash == token_hash)
        model = await self._session.scalar(stmt)
        return _token_to_domain(model) if model else None

    async def get_by_hash_for_update(self, token_hash: str) -> VerificationToken | None:
        """Read one verification token under a row lock (BUG-07): without it, N
        simultaneous redemptions all read an unused token and all succeed. The
        caller takes the owning user's lock first (`users` before dependents)."""
        stmt = (
            select(VerificationTokenModel)
            .where(VerificationTokenModel.token_hash == token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(stmt)
        return _token_to_domain(model) if model else None

    async def get_latest_for_user(self, user_id: UUID) -> VerificationToken | None:
        stmt = (
            select(VerificationTokenModel)
            .where(VerificationTokenModel.user_id == user_id)
            .order_by(VerificationTokenModel.created_at.desc())
            .limit(1)
        )
        model = await self._session.scalar(stmt)
        return _token_to_domain(model) if model else None

    async def add(
        self, *, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> VerificationToken:
        model = VerificationTokenModel(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _token_to_domain(model)

    async def delete_expired_batch(self, *, cutoff: datetime, limit: int) -> int:
        """Verification tokens, used or not, that expired before `cutoff` (VS-046)."""
        expired = VerificationTokenModel.expires_at < cutoff
        return await _delete_batch_skip_locked(
            self._session, VerificationTokenModel, expired, limit
        )

    async def save(self, token: VerificationToken) -> None:
        model = await self._session.get(VerificationTokenModel, token.id)
        if model is None:
            raise ValueError(f"VerificationToken {token.id} not found")
        model.used_at = token.used_at
        await self._session.flush()


class MfaCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: UUID) -> MfaCredential | None:
        """Plain read, no lock. For callers that only ask a question - the
        login gate asking whether a challenge is needed, for instance. Locking
        there would serialise every administrator login for no benefit."""
        stmt = select(MfaCredentialModel).where(MfaCredentialModel.user_id == user_id)
        model = await self._session.scalar(stmt)
        return _mfa_credential_to_domain(model) if model else None

    async def get_by_user_id_for_update(self, user_id: UUID) -> MfaCredential | None:
        """Read the credential and hold a row lock until the transaction ends.

        Required by anything that decides *and then writes* `last_totp_step`.
        The replay check is a read-modify-write - read the mark, compare the
        matched step against it, write the new mark - and `max()` in the entity
        only orders values already in one process's memory. Two transactions
        that both read the same stale mark would both conclude the step was
        unspent, both accept, and one intercepted code would open two admin
        sessions. That is the exact failure the second factor exists to
        prevent, so the serialisation has to be in the database.

        With the lock the second transaction blocks here, then re-reads the row
        the first has already advanced and correctly finds the step spent.

        `populate_existing` matters: without it SQLAlchemy would hand back the
        instance already in this session's identity map and the post-lock
        re-read would silently return pre-lock data. Requests get a fresh
        session so the map is normally empty, but a guarantee that depends on
        that staying true is not a guarantee.

        Same idiom as `SessionRepository.get_for_update` and
        `MfaRecoveryCodeRepository.get_unused_by_hash`."""
        stmt = (
            select(MfaCredentialModel)
            .where(MfaCredentialModel.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        model = await self._session.scalar(stmt)
        return _mfa_credential_to_domain(model) if model else None

    async def add(
        self, *, user_id: UUID, method: MfaMethod, secret_ciphertext: bytes
    ) -> MfaCredential:
        model = MfaCredentialModel(
            user_id=user_id, method=method, secret_ciphertext=secret_ciphertext
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _mfa_credential_to_domain(model)

    async def save(self, credential: MfaCredential) -> None:
        model = await self._session.get(MfaCredentialModel, credential.id)
        if model is None:
            raise ValueError(f"MfaCredential {credential.id} not found")
        model.secret_ciphertext = credential.secret_ciphertext
        model.enabled_at = credential.enabled_at
        model.last_used_at = credential.last_used_at
        model.last_totp_step = credential.last_totp_step
        await self._session.flush()


class MfaRecoveryCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_unused_by_hash(
        self, *, mfa_credential_id: UUID, code_hash: str
    ) -> MfaRecoveryCode | None:
        """Find one unused code and hold a row lock until the transaction ends.

        `SELECT ... FOR UPDATE` is what actually makes a recovery code
        one-time-use. Without it, two requests submitting the same code
        concurrently both read `used_at IS NULL`, both pass the domain guard in
        MfaRecoveryCode.redeem, and the code is spent twice - which for a
        recovery credential means two admin sessions from one stolen code. With
        the lock, the second transaction blocks here, then re-reads the row the
        first already marked used and correctly finds nothing."""
        stmt = (
            select(MfaRecoveryCodeModel)
            .where(
                MfaRecoveryCodeModel.mfa_credential_id == mfa_credential_id,
                MfaRecoveryCodeModel.code_hash == code_hash,
                MfaRecoveryCodeModel.used_at.is_(None),
            )
            .with_for_update()
        )
        model = await self._session.scalar(stmt)
        return _mfa_recovery_code_to_domain(model) if model else None

    async def add_set(
        self, *, mfa_credential_id: UUID, code_hashes: Sequence[str]
    ) -> list[MfaRecoveryCode]:
        models = [
            MfaRecoveryCodeModel(mfa_credential_id=mfa_credential_id, code_hash=code_hash)
            for code_hash in code_hashes
        ]
        self._session.add_all(models)
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [_mfa_recovery_code_to_domain(model) for model in models]

    async def count_unused(self, mfa_credential_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(MfaRecoveryCodeModel)
            .where(
                MfaRecoveryCodeModel.mfa_credential_id == mfa_credential_id,
                MfaRecoveryCodeModel.used_at.is_(None),
            )
        )
        return (await self._session.scalar(stmt)) or 0

    async def delete_unused(self, mfa_credential_id: UUID) -> int:
        """Wipe the unused half of a code set, for regeneration.

        Only unused rows are removed. Spent codes stay, because `code_hash` is
        UNIQUE table-wide and deleting the evidence that a code was already
        redeemed would let the identical string be issued again later and
        accepted a second time. Deletion rather than soft-delete is what
        database-design.md 5.7 calls for ("invalidates/removes prior unused code
        set"), and these rows carry no audit value - the regeneration event
        itself is what gets audited."""
        stmt = (
            delete(MfaRecoveryCodeModel)
            .where(
                MfaRecoveryCodeModel.mfa_credential_id == mfa_credential_id,
                MfaRecoveryCodeModel.used_at.is_(None),
            )
            .execution_options(synchronize_session=False)
        )
        # execute() is typed as returning Result; rowcount is a CursorResult
        # attribute, and a DML statement always produces one.
        result = cast("CursorResult[Any]", await self._session.execute(stmt))
        return result.rowcount

    async def save(self, code: MfaRecoveryCode) -> None:
        model = await self._session.get(MfaRecoveryCodeModel, code.id)
        if model is None:
            raise ValueError(f"MfaRecoveryCode {code.id} not found")
        model.used_at = code.used_at
        await self._session.flush()


class PasswordResetTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        """Unlocked peek, only to learn whose token this is. Nothing is decided on
        it: the caller locks the user, then every token of that user, and
        re-reads this one under those locks."""
        stmt = select(PasswordResetTokenModel).where(
            PasswordResetTokenModel.token_hash == token_hash
        )
        model = await self._session.scalar(stmt)
        return _reset_token_to_domain(model) if model else None

    async def lock_all_for_user(self, user_id: UUID) -> list[PasswordResetToken]:
        """Row-lock every reset token this user holds, in id order.

        BUG-02: confirm used to lock its own token, then the user, then UPDATE
        the user's *other* tokens - so two different tokens of one account
        confirmed together each held one token and waited for the other:
        a deadlock. Taking the user lock first and then all of that user's
        tokens in a fixed order leaves only one ordering to queue in."""
        stmt = (
            select(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
            .order_by(PasswordResetTokenModel.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        models = (await self._session.scalars(stmt)).all()
        return [_reset_token_to_domain(model) for model in models]

    async def get_latest_for_user(self, user_id: UUID) -> PasswordResetToken | None:
        stmt = (
            select(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.user_id == user_id)
            .order_by(PasswordResetTokenModel.created_at.desc())
            .limit(1)
        )
        model = await self._session.scalar(stmt)
        return _reset_token_to_domain(model) if model else None

    async def add(
        self, *, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken:
        model = PasswordResetTokenModel(
            user_id=user_id, token_hash=token_hash, expires_at=expires_at
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _reset_token_to_domain(model)

    async def save(self, token: PasswordResetToken) -> None:
        model = await self._session.get(PasswordResetTokenModel, token.id)
        if model is None:
            raise ValueError(f"PasswordResetToken {token.id} not found")
        model.used_at = token.used_at
        await self._session.flush()

    async def consume_outstanding_for_user(self, *, user_id: UUID, at: datetime) -> int:
        """Burn every unused reset token this user holds. Returns how many.

        Called after a successful reset. Without it, a second link the user
        requested earlier stays redeemable for the rest of its window, so an
        attacker who later reaches that older email can reset the password
        again - the account would be recoverable by someone who was never
        supposed to hold a live token. Same reasoning as revoking sessions:
        one successful reset must end every other route in."""
        stmt = (
            update(PasswordResetTokenModel)
            .where(
                PasswordResetTokenModel.user_id == user_id,
                PasswordResetTokenModel.used_at.is_(None),
            )
            .values(used_at=at)
            .returning(PasswordResetTokenModel.id)
        )
        consumed_ids = (await self._session.scalars(stmt)).all()
        await self._session.flush()
        return len(consumed_ids)

    async def delete_expired_batch(self, *, cutoff: datetime, limit: int) -> int:
        """Reset tokens, used or not, that expired before `cutoff` (VS-046)."""
        expired = PasswordResetTokenModel.expires_at < cutoff
        return await _delete_batch_skip_locked(
            self._session, PasswordResetTokenModel, expired, limit
        )
