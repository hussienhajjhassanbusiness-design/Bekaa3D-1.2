"""The `contact_messages` table refuses bad rows itself, whatever the application sends."""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

VALID: dict[str, Any] = {
    "name": "Rima",
    "email": "rima@example.com",
    "phone": None,
    "subject": None,
    "message": "Hello",
}
INSERT = text(
    "INSERT INTO contact_messages (name, email, phone, subject, message) "
    "VALUES (:name, :email, :phone, :subject, :message) RETURNING status"
)


@pytest.mark.integration
async def test_a_valid_row_defaults_to_new(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        status = await conn.scalar(INSERT, VALID)
        await conn.rollback()
    assert status == "new"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("name", "   ", "ck_contact_messages_name_length"),
        ("name", "\t\n", "ck_contact_messages_name_length"),
        ("name", "n" * 101, "ck_contact_messages_name_length"),
        ("email", "no-at-sign", "ck_contact_messages_email_shape"),
        ("email", "@x.y", "ck_contact_messages_email_shape"),
        ("email", "a@" + "b" * 253, "ck_contact_messages_email_shape"),
        ("phone", " ", "ck_contact_messages_phone_length"),
        ("phone", "1" * 33, "ck_contact_messages_phone_length"),
        ("subject", "", "ck_contact_messages_subject_length"),
        ("subject", "\r\n", "ck_contact_messages_subject_length"),
        ("subject", "s" * 201, "ck_contact_messages_subject_length"),
        ("message", " \n ", "ck_contact_messages_message_length"),
        ("message", "m" * 5001, "ck_contact_messages_message_length"),
    ],
)
async def test_the_database_refuses_an_invalid_field(
    db_engine: AsyncEngine, field: str, value: str, constraint: str
) -> None:
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match=constraint):
            await conn.execute(INSERT, VALID | {field: value})


@pytest.mark.integration
@pytest.mark.parametrize("field", ["name", "email", "message"])
async def test_required_fields_are_not_null(db_engine: AsyncEngine, field: str) -> None:
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match="not-null"):
            await conn.execute(INSERT, VALID | {field: None})


@pytest.mark.integration
async def test_an_unknown_status_is_refused(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        with pytest.raises(DBAPIError, match="contact_message_status"):
            await conn.execute(
                text(
                    "INSERT INTO contact_messages (name, email, message, status) "
                    "VALUES ('R', 'r@example.com', 'hi', 'spam')"
                )
            )


@pytest.mark.integration
async def test_timestamps_are_timestamptz_and_the_queue_index_exists(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as conn:
        types: dict[str, str] = dict(
            (
                await conn.execute(
                    text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = 'contact_messages'"
                    )
                )
            ).all()
        )
        index = await conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_contact_messages_queue'")
        )
    assert types["created_at"] == types["updated_at"] == "timestamp with time zone"
    assert types["email"] == "USER-DEFINED"
    assert index is not None and "(status, created_at, id)" in index
