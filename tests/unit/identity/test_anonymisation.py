"""VS-045 rules decidable without a database: the anonymised email, the blocks, `User.anonymise`,
and `DeleteAccount`'s order of checks and locks (ADR-047) against one recording fake."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from app.identity.application.commands.delete_account import DeleteAccount
from app.identity.application.ports import (
    AccountErasure,
    AddressStore,
    ErasureCounts,
    PasswordResetTokenStore,
    SessionStore,
    UserStore,
    VerificationTokenStore,
)
from app.identity.application.security.password_hasher import hash_password, verify_password
from app.identity.domain.anonymisation import (
    DeletionBlock,
    administrator_block,
    anonymised_email,
    deletion_block,
)
from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import (
    AccountAlreadyAnonymisedError,
    AccountDeletionBlockedError,
    AccountDisabledError,
    InvalidCredentialsError,
)
from app.platform.application.ports.audit_writer import AuditWriter

AT = datetime(2026, 10, 28, tzinfo=UTC)
PASSWORD = "correct horse battery"
HASH = hash_password(PASSWORD)
LOCKS = ["lock_orders", "lock_cart", "lock_live_offers", "lock_for_anonymisation"]


def _user(*, role: UserRole = UserRole.CUSTOMER, password_hash: str = HASH) -> User:
    return User(
        id=uuid.uuid4(),
        email="someone@example.com",
        password_hash=password_hash,
        role=role,
        email_verified_at=AT,
        is_active=True,
        anonymized_at=None,
        deleted_at=None,
        created_at=AT,
        updated_at=AT,
        auth_epoch=3,
    )


def test_anonymised_email_is_per_account_and_invalid() -> None:
    user_id = uuid.uuid4()
    assert anonymised_email(user_id) == f"deleted+{user_id}@invalid"
    assert anonymised_email(user_id) != anonymised_email(uuid.uuid4())


def test_only_an_administrator_is_blocked_by_role() -> None:
    assert administrator_block(_user(role=UserRole.ADMIN)) is DeletionBlock.ADMINISTRATOR
    assert administrator_block(_user()) is None


@pytest.mark.parametrize(
    ("open_order", "unsettled", "expected"),
    [
        (False, False, None),
        (True, False, DeletionBlock.OPEN_ORDER),
        (False, True, DeletionBlock.UNSETTLED_REFUND),
        (True, True, DeletionBlock.OPEN_ORDER),
    ],
)
def test_deletion_block(open_order: bool, unsettled: bool, expected: DeletionBlock | None) -> None:
    assert deletion_block(open_order=open_order, unsettled_refund=unsettled) is expected


def test_anonymise_strips_the_login_and_voids_credentials() -> None:
    user = _user()
    user.anonymise(email="deleted+x@invalid", password_hash="new-hash", at=AT)
    assert (user.email, user.password_hash) == ("deleted+x@invalid", "new-hash")
    assert (user.is_active, user.anonymized_at, user.auth_epoch) == (False, AT, 4)
    assert not user.can_authenticate
    with pytest.raises(AccountAlreadyAnonymisedError):
        user.anonymise(email="deleted+y@invalid", password_hash="h", at=AT)


@dataclass
class _World:
    """Every port `DeleteAccount` calls, recording the calls in order."""

    user: User
    locked: User | None = None
    open_order: bool = False
    unsettled: bool = False
    calls: list[str] = field(default_factory=list)
    saved: User | None = None
    audit: dict[str, Any] = field(default_factory=dict)

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        self.calls.append("get_by_id")
        return self.user

    async def lock_orders(self, user_id: uuid.UUID) -> None:
        self.calls.append("lock_orders")

    async def lock_cart(self, user_id: uuid.UUID) -> None:
        self.calls.append("lock_cart")

    async def lock_live_offers(self, user_id: uuid.UUID) -> None:
        self.calls.append("lock_live_offers")

    async def lock_for_anonymisation(self, user_id: uuid.UUID) -> User | None:
        self.calls.append("lock_for_anonymisation")
        return self.locked

    async def open_order_exists(self, user_id: uuid.UUID) -> bool:
        self.calls.append("open_order_exists")
        return self.open_order

    async def unsettled_refund_exists(self, user_id: uuid.UUID) -> bool:
        self.calls.append("unsettled_refund_exists")
        return self.unsettled

    async def erase(self, user_id: uuid.UUID, *, email: str, at: datetime) -> ErasureCounts:
        self.calls.append("erase")
        return ErasureCounts(2, 1, 5, 3, 1, 4, 6)

    async def anonymise_all(self, user_id: uuid.UUID, *, at: datetime) -> int:
        self.calls.append("anonymise_all")
        return 2

    async def consume_outstanding_for_user(self, *, user_id: uuid.UUID, at: datetime) -> int:
        self.calls.append("consume_tokens")
        return 1

    async def save_anonymised(self, user: User) -> None:
        self.calls.append("save_anonymised")
        self.saved = user

    async def revoke_all_for_user(self, *, user_id: uuid.UUID, at: datetime) -> int:
        self.calls.append("revoke_all_for_user")
        return 2

    async def record(self, **kwargs: Any) -> None:
        self.calls.append("audit")
        self.audit = kwargs


async def _delete(world: _World, password: str = PASSWORD) -> None:
    fake: Any = world
    await DeleteAccount(
        users=cast(UserStore, fake),
        sessions=cast(SessionStore, fake),
        addresses=cast(AddressStore, fake),
        verification_tokens=cast(VerificationTokenStore, fake),
        reset_tokens=cast(PasswordResetTokenStore, fake),
        erasure=cast(AccountErasure, fake),
        audit=cast(AuditWriter, fake),
    ).execute(user_id=world.user.id, password=password, request_id="r", ip_hash=None)


async def test_success_locks_in_order_then_writes_everything_once() -> None:
    user = _user()
    world = _World(user, locked=_user(password_hash=HASH))
    await _delete(world)
    assert world.calls[1:5] == LOCKS
    assert world.calls[5:] == [
        "open_order_exists",
        "unsettled_refund_exists",
        "erase",
        "anonymise_all",
        "consume_tokens",
        "consume_tokens",
        "save_anonymised",
        "revoke_all_for_user",
        "audit",
    ]
    assert world.saved is not None and world.saved.anonymized_at is not None
    assert not verify_password(password=PASSWORD, password_hash=world.saved.password_hash)
    assert world.audit["action"] == "user.anonymized"
    assert world.audit["after_data"] == {
        "orders": 2,
        "offers_withdrawn": 1,
        "offer_messages": 5,
        "wishlist_items": 3,
        "contact_messages": 1,
        "outbox_rows": 4,
        "idempotency_records": 6,
        "addresses": 2,
        "tokens_consumed": 2,
        "sessions_revoked": 2,
    }
    assert "someone@example.com" not in repr(world.audit)


async def test_wrong_password_takes_no_lock() -> None:
    world = _World(_user(), locked=_user())
    with pytest.raises(InvalidCredentialsError):
        await _delete(world, password="wrong")
    assert world.calls == ["get_by_id"]


async def test_administrator_is_refused_before_any_lock() -> None:
    world = _World(_user(role=UserRole.ADMIN), locked=_user())
    with pytest.raises(AccountDeletionBlockedError) as caught:
        await _delete(world)
    assert caught.value.reason == "administrator"
    assert world.calls == ["get_by_id"]


@pytest.mark.parametrize(
    ("open_order", "unsettled", "reason"),
    [(True, False, "open_order"), (False, True, "unsettled_refund")],
)
async def test_block_is_read_under_the_locks_and_writes_nothing(
    open_order: bool, unsettled: bool, reason: str
) -> None:
    world = _World(_user(), locked=_user(), open_order=open_order, unsettled=unsettled)
    with pytest.raises(AccountDeletionBlockedError) as caught:
        await _delete(world)
    assert caught.value.reason == reason
    assert world.calls[1:5] == LOCKS
    assert "erase" not in world.calls and "audit" not in world.calls


async def test_password_changed_while_waiting_is_refused() -> None:
    world = _World(_user(), locked=_user(password_hash=hash_password("another one")))
    with pytest.raises(InvalidCredentialsError):
        await _delete(world)
    assert "open_order_exists" not in world.calls


async def test_account_anonymised_while_waiting_is_refused() -> None:
    gone = _user()
    gone.anonymise(email="deleted+z@invalid", password_hash=HASH, at=AT)
    world = _World(_user(), locked=gone)
    with pytest.raises(AccountDisabledError):
        await _delete(world)
    assert "erase" not in world.calls
