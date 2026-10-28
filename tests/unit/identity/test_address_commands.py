from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.identity.application.commands.address_book import (
    CreateAddress,
    DeleteAddress,
    SetDefaultAddress,
    UpdateAddress,
)
from app.identity.application.ports import AddressStore
from app.identity.domain.address import MAX_LIVE_ADDRESSES, Address, AddressDetails
from app.identity.domain.exceptions import (
    AccountDisabledError,
    AddressLimitReachedError,
    AddressNotFoundError,
)

DETAILS = AddressDetails.of(
    label="Home",
    recipient_name="Rima Haddad",
    phone="03 123 456",
    governorate="beqaa",
    city="Zahle",
    area=None,
    street=None,
    landmark_notes="Blue gate",
)
NOW = datetime(2026, 10, 15, tzinfo=UTC)


class FakeAddresses:
    """In memory; records calls so a test can see the lock came first."""

    def __init__(self) -> None:
        self.rows: dict[UUID, Address] = {}
        self.calls: list[str] = []
        self.locked: set[UUID] = set()
        self.anonymised: set[UUID] = set()

    def _live(self, user_id: UUID) -> list[Address]:
        return [a for a in self.rows.values() if a.user_id == user_id and a.deleted_at is None]

    def _guard(self, name: str, user_id: UUID) -> None:
        self.calls.append(name)
        assert user_id in self.locked, f"{name} before lock_address_book"

    async def lock_address_book(self, user_id: UUID) -> bool:
        self.calls.append("lock")
        self.locked.add(user_id)
        return user_id not in self.anonymised

    async def list_live(self, user_id: UUID) -> list[Address]:
        return self._live(user_id)

    async def get_live(self, *, address_id: UUID, user_id: UUID) -> Address | None:
        self._guard("get_live", user_id)
        return next((a for a in self._live(user_id) if a.id == address_id), None)

    async def count_live(self, user_id: UUID) -> int:
        self._guard("count_live", user_id)
        return len(self._live(user_id))

    async def clear_default(self, user_id: UUID) -> None:
        self._guard("clear_default", user_id)
        for address in self._live(user_id):
            self.rows[address.id] = replace(address, is_default=False)

    async def add(self, *, user_id: UUID, details: AddressDetails, is_default: bool) -> Address:
        self._guard("add", user_id)
        address = Address(uuid4(), user_id, details, is_default, None, NOW, NOW)
        self.rows[address.id] = address
        return address

    async def update(
        self, address_id: UUID, *, user_id: UUID, details: AddressDetails, is_default: bool
    ) -> Address:
        address = replace(self.rows[address_id], details=details, is_default=is_default)
        assert address.user_id == user_id and address.deleted_at is None
        self._guard("update", user_id)
        self.rows[address_id] = address
        return address

    async def soft_delete(self, address_id: UUID, *, user_id: UUID) -> None:
        address = self.rows[address_id]
        assert address.user_id == user_id and address.deleted_at is None
        self._guard("soft_delete", user_id)
        self.rows[address_id] = replace(address, is_default=False, deleted_at=NOW)

    async def anonymise_all(self, user_id: UUID, *, at: datetime) -> int:
        raise NotImplementedError

    def defaults(self, user_id: UUID) -> list[UUID]:
        return [a.id for a in self._live(user_id) if a.is_default]


def _store() -> FakeAddresses:
    store = FakeAddresses()
    _: AddressStore = store
    return store


async def _create(store: FakeAddresses, user_id: UUID, *, make_default: bool = False) -> Address:
    return await CreateAddress(store).execute(
        user_id=user_id, details=DETAILS, make_default=make_default
    )


async def test_first_address_becomes_default_later_ones_do_not() -> None:
    store, user = _store(), uuid4()
    first = await _create(store, user)
    second = await _create(store, user)
    assert (first.is_default, second.is_default) == (True, False)
    assert store.calls[0] == "lock"


async def test_first_address_is_default_even_when_false_is_sent() -> None:
    store, user = _store(), uuid4()
    assert (await _create(store, user, make_default=False)).is_default


async def test_after_deleting_every_address_the_next_is_default_again() -> None:
    store, user = _store(), uuid4()
    first = await _create(store, user)
    await DeleteAddress(store).execute(user_id=user, address_id=first.id)
    assert (await _create(store, user)).is_default


async def test_requested_default_on_create_moves_the_default() -> None:
    store, user = _store(), uuid4()
    await _create(store, user)
    newer = await _create(store, user, make_default=True)
    assert store.defaults(user) == [newer.id]


async def test_create_refused_at_the_cap() -> None:
    store, user = _store(), uuid4()
    for _ in range(MAX_LIVE_ADDRESSES):
        await _create(store, user)
    with pytest.raises(AddressLimitReachedError):
        await _create(store, user)
    assert len(store.rows) == MAX_LIVE_ADDRESSES


async def test_create_for_an_account_deleted_while_waiting_is_refused() -> None:
    """VS-045: the lock read sees the anonymised owner, so no new personal row is stored."""
    store, user = _store(), uuid4()
    store.anonymised.add(user)
    with pytest.raises(AccountDisabledError):
        await _create(store, user)
    assert store.rows == {} and store.calls == ["lock"]


async def test_deleted_addresses_do_not_count_toward_the_cap() -> None:
    store, user = _store(), uuid4()
    first = await _create(store, user)
    for _ in range(MAX_LIVE_ADDRESSES - 1):
        await _create(store, user)
    await DeleteAddress(store).execute(user_id=user, address_id=first.id)
    await _create(store, user)


async def test_set_default_switches_and_is_idempotent() -> None:
    store, user = _store(), uuid4()
    first = await _create(store, user)
    second = await _create(store, user)
    await SetDefaultAddress(store).execute(user_id=user, address_id=second.id)
    await SetDefaultAddress(store).execute(user_id=user, address_id=second.id)
    assert store.defaults(user) == [second.id]
    assert not store.rows[first.id].is_default


async def test_delete_default_leaves_none() -> None:
    store, user = _store(), uuid4()
    first = await _create(store, user)
    await _create(store, user)
    await DeleteAddress(store).execute(user_id=user, address_id=first.id)
    assert store.defaults(user) == []


@pytest.mark.parametrize("make_default", [True, False, None])
async def test_update_default_flag(make_default: bool | None) -> None:
    store, user = _store(), uuid4()
    first = await _create(store, user)
    second = await _create(store, user)
    updated = await UpdateAddress(store).execute(
        user_id=user, address_id=second.id, changes={"city": "Chtaura"}, make_default=make_default
    )
    assert updated.details.city == "Chtaura"
    expected = {True: [second.id], False: [first.id], None: [first.id]}[make_default]
    assert store.defaults(user) == expected


async def test_update_false_clears_the_current_default() -> None:
    store, user = _store(), uuid4()
    first = await _create(store, user)
    await UpdateAddress(store).execute(
        user_id=user, address_id=first.id, changes={}, make_default=False
    )
    assert store.defaults(user) == []


Command = Callable[[FakeAddresses, UUID, UUID], Awaitable[object]]
COMMANDS: dict[str, Command] = {
    "set_default": lambda s, u, a: SetDefaultAddress(s).execute(user_id=u, address_id=a),
    "delete": lambda s, u, a: DeleteAddress(s).execute(user_id=u, address_id=a),
    "update": lambda s, u, a: UpdateAddress(s).execute(
        user_id=u, address_id=a, changes={}, make_default=True
    ),
}


@pytest.mark.parametrize("name", COMMANDS)
async def test_foreign_deleted_and_unknown_addresses_are_not_found(name: str) -> None:
    store, owner, other = _store(), uuid4(), uuid4()
    mine = await _create(store, owner)
    gone = await _create(store, owner)
    await DeleteAddress(store).execute(user_id=owner, address_id=gone.id)
    for user, address_id in ((other, mine.id), (owner, gone.id), (owner, uuid4())):
        with pytest.raises(AddressNotFoundError):
            await COMMANDS[name](store, user, address_id)
    assert store.defaults(owner) == [mine.id]
