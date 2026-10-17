"""`custom_requests` and `custom_request_attachments` refuse bad rows themselves (VS-034)."""

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

pytestmark = pytest.mark.integration

REQUEST: dict[str, Any] = {
    "name": "Rima",
    "email": "rima@example.com",
    "phone": "+961 3 123 456",
    "project_title": "Lamp",
    "description": "A lamp.",
    "preferred_material": None,
    "preferred_colour": None,
    "dimensions": None,
    "admin_notes": None,
    "quoted_amount_cents": None,
    "currency": None,
}
INSERT_REQUEST = text(
    "INSERT INTO custom_requests (name, email, phone, project_title, description, "
    "preferred_material, preferred_colour, dimensions, admin_notes, quoted_amount_cents, "
    "currency, created_at, updated_at) VALUES (:name, :email, :phone, :project_title, "
    ":description, :preferred_material, :preferred_colour, :dimensions, :admin_notes, "
    ":quoted_amount_cents, :currency, now(), now()) RETURNING id, status"
)
# `expires_at` is spliced in as SQL so a test can state it relative to the row's now().
INSERT_ATTACHMENT = (
    "INSERT INTO custom_request_attachments (custom_request_id, storage_key, "
    "original_filename, mime_type, size_bytes, checksum, scan_status, expires_at, created_at) "
    "VALUES (:custom_request_id, :storage_key, :original_filename, :mime_type, :size_bytes, "
    ":checksum, CAST(:scan_status AS upload_scan_status), {expires_at}, now())"
)


async def _request(conn: AsyncConnection) -> uuid.UUID:
    row = (await conn.execute(INSERT_REQUEST, REQUEST)).one()
    request_id: uuid.UUID = row.id
    return request_id


def _attachment(request_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "custom_request_id": request_id,
        "storage_key": f"custom-requests/{uuid.uuid4()}.jpg",
        "original_filename": "photo.jpg",
        "mime_type": "image/jpeg",
        "size_bytes": 10,
        "checksum": "a" * 64,
        "scan_status": "clean",
        "expires_at": "now() + interval '90 days'",
    }
    return values | overrides


async def _insert_attachment(conn: AsyncConnection, values: dict[str, Any]) -> None:
    params = {k: v for k, v in values.items() if k != "expires_at"}
    await conn.execute(text(INSERT_ATTACHMENT.format(expires_at=values["expires_at"])), params)


async def test_a_valid_request_defaults_to_new(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        row = (await conn.execute(INSERT_REQUEST, REQUEST)).one()
        await conn.rollback()
    assert row.status == "new"


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("name", "   ", "ck_custom_requests_name_length"),
        ("name", "n" * 101, "ck_custom_requests_name_length"),
        ("email", "no-at-sign", "ck_custom_requests_email_shape"),
        ("email", "a@" + "b" * 253, "ck_custom_requests_email_shape"),
        ("phone", " ", "ck_custom_requests_phone_length"),
        ("phone", "1" * 33, "ck_custom_requests_phone_length"),
        ("project_title", "\t", "ck_custom_requests_project_title_length"),
        ("project_title", "t" * 201, "ck_custom_requests_project_title_length"),
        ("description", " \n ", "ck_custom_requests_description_length"),
        ("description", "d" * 5001, "ck_custom_requests_description_length"),
        ("preferred_material", "", "ck_custom_requests_preferred_material_length"),
        ("preferred_material", "m" * 101, "ck_custom_requests_preferred_material_length"),
        ("preferred_colour", " ", "ck_custom_requests_preferred_colour_length"),
        ("preferred_colour", "c" * 101, "ck_custom_requests_preferred_colour_length"),
        ("dimensions", "", "ck_custom_requests_dimensions_length"),
        ("dimensions", "x" * 201, "ck_custom_requests_dimensions_length"),
        ("admin_notes", " ", "ck_custom_requests_admin_notes_length"),
        ("admin_notes", "n" * 5001, "ck_custom_requests_admin_notes_length"),
    ],
)
async def test_the_database_refuses_an_invalid_request_field(
    db_engine: AsyncEngine, field: str, value: str, constraint: str
) -> None:
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match=constraint):
            await conn.execute(INSERT_REQUEST, REQUEST | {field: value})


@pytest.mark.parametrize(
    ("cents", "currency", "constraint"),
    [
        (-1, "USD", "ck_custom_requests_quote_money"),
        (100, "EUR", "ck_custom_requests_quote_money"),
        (100, None, "ck_custom_requests_currency_with_quote"),
        (None, "USD", "ck_custom_requests_currency_with_quote"),
    ],
)
async def test_a_quote_is_non_negative_usd_cents_with_its_currency(
    db_engine: AsyncEngine, cents: int | None, currency: str | None, constraint: str
) -> None:
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match=constraint):
            await conn.execute(
                INSERT_REQUEST, REQUEST | {"quoted_amount_cents": cents, "currency": currency}
            )


async def test_a_zero_or_positive_usd_quote_is_accepted(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        for cents in (0, 150_000):
            await conn.execute(
                INSERT_REQUEST, REQUEST | {"quoted_amount_cents": cents, "currency": "USD"}
            )
        await conn.rollback()


@pytest.mark.parametrize("field", ["name", "email", "phone", "project_title", "description"])
async def test_required_request_fields_are_not_null(db_engine: AsyncEngine, field: str) -> None:
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match="not-null"):
            await conn.execute(INSERT_REQUEST, REQUEST | {field: None})


@pytest.mark.parametrize(("column", "value"), [("status", "spam"), ("outcome", "maybe")])
async def test_unknown_status_or_outcome_values_are_refused(
    db_engine: AsyncEngine, column: str, value: str
) -> None:
    async with db_engine.connect() as conn:
        request_id = await _request(conn)
        with pytest.raises(DBAPIError, match="invalid input value for enum"):
            await conn.execute(
                text(f"UPDATE custom_requests SET {column} = :v WHERE id = :id"),
                {"v": value, "id": request_id},
            )


async def test_a_valid_attachment_is_accepted(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        request_id = await _request(conn)
        for extension, mime in (
            ("jpg", "image/jpeg"),
            ("png", "image/png"),
            ("webp", "image/webp"),
        ):
            await _insert_attachment(
                conn,
                _attachment(
                    request_id,
                    storage_key=f"custom-requests/{uuid.uuid4()}.{extension}",
                    mime_type=mime,
                ),
            )
        await conn.rollback()


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"storage_key": "../etc/passwd"}, "storage_key_format"),
        ({"storage_key": "products/" + str(uuid.uuid4()) + ".jpg"}, "storage_key_format"),
        ({"storage_key": f"custom-requests/{uuid.uuid4()}.gif"}, "storage_key_format"),
        ({"storage_key": "custom-requests/photo.jpg"}, "storage_key_format"),
        ({"original_filename": ""}, "filename_length"),
        ({"original_filename": "f" * 256}, "filename_length"),
        ({"mime_type": "image/svg+xml"}, "mime_type"),
        ({"size_bytes": 0}, "size_positive"),
        ({"checksum": "A" * 64}, "checksum_sha256"),
        ({"checksum": "a" * 63}, "checksum_sha256"),
        ({"expires_at": "now()"}, "expires_after_created"),
        ({"expires_at": "now() - interval '1 second'"}, "expires_after_created"),
    ],
)
async def test_the_database_refuses_an_invalid_attachment(
    db_engine: AsyncEngine, overrides: dict[str, Any], constraint: str
) -> None:
    async with db_engine.connect() as conn:
        request_id = await _request(conn)
        with pytest.raises(IntegrityError, match=f"ck_custom_request_attachments_{constraint}"):
            await _insert_attachment(conn, _attachment(request_id, **overrides))


async def test_two_rows_never_share_a_file(db_engine: AsyncEngine) -> None:
    key = f"custom-requests/{uuid.uuid4()}.png"
    async with db_engine.connect() as conn:
        request_id = await _request(conn)
        values = _attachment(request_id, storage_key=key, mime_type="image/png")
        await _insert_attachment(conn, values)
        with pytest.raises(IntegrityError, match="uq_custom_request_attachments_storage_key"):
            await _insert_attachment(conn, values)


async def test_an_attachment_needs_a_real_request(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        with pytest.raises(IntegrityError, match="custom_request_id_fkey"):
            await _insert_attachment(conn, _attachment(uuid.uuid4()))


async def test_scan_status_admits_only_clean(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        request_id = await _request(conn)
        with pytest.raises(DBAPIError, match="upload_scan_status"):
            await _insert_attachment(conn, _attachment(request_id, scan_status="pending"))


async def test_timestamps_are_timestamptz_and_the_indexes_exist(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        types: dict[str, str] = dict(
            (
                await conn.execute(
                    text(
                        "SELECT table_name || '.' || column_name, data_type "
                        "FROM information_schema.columns "
                        "WHERE table_name IN ('custom_requests', 'custom_request_attachments') "
                        "AND column_name LIKE '%\\_at'"
                    )
                )
            ).all()
        )
        indexes = set(
            (
                await conn.scalars(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE tablename IN "
                        "('custom_requests', 'custom_request_attachments')"
                    )
                )
            ).all()
        )
    assert len(types) == 8
    assert set(types.values()) == {"timestamp with time zone"}
    assert {
        "ix_custom_requests_queue",
        "ix_custom_request_attachments_expires_at",
        "ix_custom_request_attachments_request",
    } <= indexes
