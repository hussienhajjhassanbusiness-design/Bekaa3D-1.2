"""The `addresses` table refuses bad rows itself (VS-026): one live default per user, no
deleted default, Lebanese phone and governorate, required landmark notes, no user purge."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker

from app.identity.application.commands.address_book import SetDefaultAddress
from app.identity.infrastructure.addresses import SqlAddressRepository
from app.identity.infrastructure.models import AddressModel
from tests.integration.deep_support import create_user

pytestmark = pytest.mark.integration

VALID: dict[str, Any] = {
    "label": "Home",
    "recipient_name": "Rima",
    "phone": "+9613123456",
    "governorate": "beqaa",
    "city": "Zahle",
    "area": None,
    "street": None,
    "landmark_notes": "Blue gate",
    "is_default": False,
    "deleted_at": None,
}
DELETED_AT = datetime(2026, 10, 15, tzinfo=UTC)
INSERT = text(
    "INSERT INTO addresses (user_id, label, recipient_name, phone, governorate, city, area, "
    "street, landmark_notes, is_default, deleted_at) VALUES (:user_id, :label, "
    ":recipient_name, :phone, :governorate, :city, :area, :street, :landmark_notes, "
    ":is_default, :deleted_at) RETURNING id"
)


async def _user(engine: AsyncEngine) -> uuid.UUID:
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        return (await create_user(db)).id


async def _insert(conn: AsyncConnection, user_id: uuid.UUID, **values: Any) -> uuid.UUID:
    result = await conn.scalar(INSERT, VALID | {"user_id": user_id} | values)
    assert isinstance(result, uuid.UUID)
    return result


async def test_a_second_live_default_is_refused(db_engine: AsyncEngine) -> None:
    user_id = await _user(db_engine)
    async with db_engine.connect() as conn:
        await _insert(conn, user_id, is_default=True)
        await _insert(conn, user_id, is_default=False)
        with pytest.raises(IntegrityError, match="uq_addresses_one_default_per_user"):
            await _insert(conn, user_id, is_default=True)


async def test_defaults_are_per_user(db_engine: AsyncEngine) -> None:
    first, second = await _user(db_engine), await _user(db_engine)
    async with db_engine.connect() as conn:
        await _insert(conn, first, is_default=True)
        await _insert(conn, second, is_default=True)
        await conn.rollback()


async def test_a_deleted_address_cannot_be_default(db_engine: AsyncEngine) -> None:
    user_id = await _user(db_engine)
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match="ck_addresses_deleted_not_default"):
            await _insert(
                conn, user_id, is_default=True, deleted_at=datetime(2026, 10, 15, tzinfo=UTC)
            )


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("phone", "03123456", "ck_addresses_phone_e164"),
        ("phone", "+96131234", "ck_addresses_phone_e164"),
        ("phone", "+331234567", "ck_addresses_phone_e164"),
        ("phone", "+9613123456 ", "ck_addresses_phone_e164"),
        ("governorate", "Beqaa", "ck_addresses_governorate"),
        ("governorate", "paris", "ck_addresses_governorate"),
        ("label", "  ", "ck_addresses_label_length"),
        ("label", "l" * 51, "ck_addresses_label_length"),
        ("recipient_name", "r" * 101, "ck_addresses_recipient_name_length"),
        ("city", "\t", "ck_addresses_city_length"),
        ("landmark_notes", " \n ", "ck_addresses_landmark_notes_length"),
        ("landmark_notes", "n" * 501, "ck_addresses_landmark_notes_length"),
        ("area", "", "ck_addresses_area_length"),
        ("street", "s" * 201, "ck_addresses_street_length"),
    ],
)
async def test_the_database_refuses_an_invalid_field(
    db_engine: AsyncEngine, field: str, value: str, constraint: str
) -> None:
    user_id = await _user(db_engine)
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match=constraint):
            await _insert(conn, user_id, **{field: value})


@pytest.mark.parametrize("field", ["label", "governorate"])
async def test_required_fields_are_not_null(db_engine: AsyncEngine, field: str) -> None:
    user_id = await _user(db_engine)
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match="not-null"):
            await _insert(conn, user_id, **{field: None})


@pytest.mark.parametrize("field", ["recipient_name", "phone", "city", "landmark_notes"])
async def test_personal_fields_are_required_until_anonymised(
    db_engine: AsyncEngine, field: str
) -> None:
    user_id = await _user(db_engine)
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match="ck_addresses_required_unless_anonymised"):
            await _insert(conn, user_id, **{field: None})


_SCRUB = (
    "recipient_name = NULL, phone = NULL, city = NULL, area = NULL, street = NULL,"
    " landmark_notes = NULL"
)


@pytest.mark.parametrize(
    "assignments",
    [
        pytest.param("anonymized_at = now(), deleted_at = now()", id="keeps_personal_fields"),
        pytest.param(f"anonymized_at = now(), {_SCRUB}", id="not_deleted"),
        pytest.param(
            "anonymized_at = now(), deleted_at = now(), "
            + _SCRUB.replace("street = NULL", "street = 'x'"),
            id="keeps_the_street",
        ),
    ],
)
async def test_an_anonymised_address_must_be_deleted_and_hold_no_personal_field(
    db_engine: AsyncEngine, assignments: str
) -> None:
    """VS-045: ck_addresses_anonymised_shape, so a bug cannot keep a phone on such a row."""
    user_id = await _user(db_engine)
    async with db_engine.connect() as conn:
        address = await _insert(conn, user_id)
        with pytest.raises(IntegrityError, match="ck_addresses_anonymised_shape"):
            await conn.execute(
                text(f"UPDATE addresses SET {assignments} WHERE id = :a"), {"a": address}
            )


async def test_a_fully_scrubbed_deleted_address_is_accepted(db_engine: AsyncEngine) -> None:
    user_id = await _user(db_engine)
    async with db_engine.connect() as conn:
        address = await _insert(conn, user_id)
        await conn.execute(
            text(
                f"UPDATE addresses SET anonymized_at = now(), deleted_at = now(), {_SCRUB}"
                " WHERE id = :a"
            ),
            {"a": address},
        )
        await conn.rollback()


async def test_addresses_never_block_the_unverified_purge(db_engine: AsyncEngine) -> None:
    """The purge is the only hard delete of a user; its addresses go with it."""
    user_id = await _user(db_engine)
    async with db_engine.connect() as conn:
        await _insert(conn, user_id, is_default=True)
        await conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        remaining = await conn.scalar(
            text("SELECT count(*) FROM addresses WHERE user_id = :id"), {"id": user_id}
        )
        await conn.rollback()
    assert remaining == 0


class _FailAfterClear(SqlAddressRepository):
    async def clear_default(self, user_id: uuid.UUID) -> None:
        await super().clear_default(user_id)
        raise RuntimeError("injected failure after clearing the old default")


async def test_a_failed_switch_keeps_the_old_default(db_engine: AsyncEngine) -> None:
    user_id = await _user(db_engine)
    async with db_engine.begin() as conn:
        old = await _insert(conn, user_id, is_default=True)
        new = await _insert(conn, user_id)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    with pytest.raises(RuntimeError, match="injected"):
        async with factory() as db, db.begin():
            await SetDefaultAddress(_FailAfterClear(db)).execute(user_id=user_id, address_id=new)
    async with factory() as db:
        stmt = select(AddressModel.id).where(
            AddressModel.user_id == user_id, AddressModel.is_default
        )
        assert list((await db.scalars(stmt)).all()) == [old]
