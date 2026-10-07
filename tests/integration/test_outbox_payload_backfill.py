"""The one-off payload redaction carried by migration 8bd689bf2024.

Redacting payloads in `EmailOutboxMessage` only closes the exposure going
forward. Rows written before that shipped still hold the raw verification token
in plaintext, and those tokens stay redeemable until they expire, so the
migration has to reach back and clean what is already in the table.

A data migration cannot be tested through the `db_engine` fixture, which arrives
already at head with the backfill long since run. These tests stop the chain at
`c42f47ccac47`, seed the table as it would have looked before the fix, then run
the remaining upgrade and inspect the result.
"""

import asyncio
import os
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings

# The revision immediately before the one under test: the last point at which an
# unredacted payload could legitimately exist.
BEFORE = "c42f47ccac47"

RAW_TOKEN = "0f8c1d2e3a4b5c6d7e8f90a1b2c3d4e5"


@pytest.fixture
def pg() -> Iterator[str]:
    """A database migrated as far as the revision before the backfill."""
    with PostgresContainer("postgres:16", driver="asyncpg") as container:
        url = container.get_connection_url()
        previous = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()

        command.upgrade(Config("alembic.ini"), BEFORE)
        yield url

        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()


async def _seed(url: str, rows: list[tuple[str, str, str]]) -> None:
    """Insert (label, status, payload-as-json-literal) rows.

    The payload is interpolated as a SQL literal rather than bound, because part
    of the point is to store shapes SQLAlchemy's JSONB binding would never
    produce - a bare array, a scalar, a JSON null.
    """
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        for label, status, payload in rows:
            await conn.execute(
                text(
                    "INSERT INTO email_outbox (recipient_email, template, payload, status) "
                    f"VALUES (:email, :template, '{payload}'::jsonb, :status)"
                ),
                {
                    "email": f"{label}@example.com",
                    "template": label,
                    "status": status,
                },
            )
    await engine.dispose()


async def _payloads(url: str) -> dict[str, Any]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT template, payload FROM email_outbox"))
        found = {row[0]: row[1] for row in result}
    await engine.dispose()
    return found


def _upgrade_to_head() -> None:
    command.upgrade(Config("alembic.ini"), "head")


@pytest.mark.integration
def test_the_backfill_redacts_raw_tokens_and_leaves_everything_else_intact(pg: str) -> None:
    """One pass over every payload shape the table can hold.

    Kept as a single test on purpose: these rows are migrated together by one
    statement pair, and asserting them together is what proves the guards
    interact correctly rather than each working in isolation.
    """
    asyncio.run(
        _seed(
            pg,
            [
                # The actual exposure: a delivered message still holding the token.
                (
                    "sent_raw",
                    "sent",
                    f'{{"token": "{RAW_TOKEN}", "url": "https://x/v/{RAW_TOKEN}"}}',
                ),
                # Permanently failed is terminal too - nothing retries it.
                ("failed_raw", "failed", f'{{"token": "{RAW_TOKEN}"}}'),
                # Empty must survive as empty. jsonb_object_agg over zero rows
                # returns NULL, and the column is NOT NULL, so a missing guard
                # here fails the migration outright rather than corrupting quietly.
                ("sent_empty", "sent", "{}"),
                # Already redacted: the statement must skip it, not rewrite it.
                ("sent_redacted", "sent", '{"token": "[redacted]"}'),
                # Still deliverable - the worker needs this payload.
                ("pending_raw", "pending", f'{{"token": "{RAW_TOKEN}"}}'),
            ],
        )
    )

    _upgrade_to_head()
    found = asyncio.run(_payloads(pg))

    assert found["sent_raw"] == {"token": "[redacted]", "url": "[redacted]"}
    assert found["failed_raw"] == {"token": "[redacted]"}
    assert found["sent_empty"] == {}
    assert found["sent_redacted"] == {"token": "[redacted]"}
    # Untouched: a pending row has not been delivered yet.
    assert found["pending_raw"] == {"token": RAW_TOKEN}

    # The property that matters, stated directly rather than row by row.
    terminal = {k: v for k, v in found.items() if not k.startswith("pending")}
    assert RAW_TOKEN not in str(terminal)


@pytest.mark.integration
def test_a_malformed_payload_cannot_abort_the_migration(pg: str) -> None:
    """`jsonb_object_keys()` raises on anything that is not a JSON object.

    Nothing in the application writes a scalar or an array into `payload`, but
    the migration runs against history rather than against the current writer,
    and one such row anywhere in the table would abort the whole upgrade partway
    through. Since their contents are unknown, the safe reading is that they may
    carry a token, so they are replaced outright rather than left alone.
    """
    asyncio.run(
        _seed(
            pg,
            [
                ("sent_array", "sent", f'["{RAW_TOKEN}"]'),
                ("sent_scalar", "sent", f'"{RAW_TOKEN}"'),
                ("sent_number", "sent", "42"),
                ("sent_json_null", "sent", "null"),
                ("failed_array", "failed", f'["{RAW_TOKEN}"]'),
                # A well-formed row alongside them: the malformed rows must not
                # stop the ordinary redaction from happening.
                ("sent_object", "sent", f'{{"token": "{RAW_TOKEN}"}}'),
            ],
        )
    )

    # The assertion is partly that this call returns at all.
    _upgrade_to_head()
    found = asyncio.run(_payloads(pg))

    assert found["sent_array"] == {}
    assert found["sent_scalar"] == {}
    assert found["sent_number"] == {}
    assert found["sent_json_null"] == {}
    assert found["failed_array"] == {}
    assert found["sent_object"] == {"token": "[redacted]"}
    assert RAW_TOKEN not in str(found)


@pytest.mark.integration
def test_running_the_backfill_twice_changes_nothing(pg: str) -> None:
    """Idempotence, exercised through the migration itself rather than by
    asserting the SQL looks idempotent.

    A downgrade cannot restore the plaintext - deliberately, it must not - so
    stepping back and forward over the revision runs the backfill a second time
    against already-redacted data. That is also exactly what a re-run after a
    partial failure would do.
    """
    asyncio.run(
        _seed(
            pg,
            [
                ("sent_raw", "sent", f'{{"token": "{RAW_TOKEN}"}}'),
                ("sent_empty", "sent", "{}"),
            ],
        )
    )

    _upgrade_to_head()
    once = asyncio.run(_payloads(pg))

    command.downgrade(Config("alembic.ini"), "-1")
    _upgrade_to_head()
    twice = asyncio.run(_payloads(pg))

    assert once == twice
    assert twice["sent_raw"] == {"token": "[redacted]"}
    assert twice["sent_empty"] == {}


@pytest.mark.integration
def test_the_constraint_and_partial_index_land_with_the_right_definitions(pg: str) -> None:
    """Both objects are database-level, so both are asserted against real
    PostgreSQL catalogues rather than against the model that declared them.

    The index predicate is checked textually, not merely counted: a partial index
    that silently lost its `WHERE` clause would still be found by a name lookup
    while covering every redeemed token row the purge never reads.
    """
    _upgrade_to_head()

    async def inspect() -> tuple[str | None, str | None, Exception | None]:
        engine = create_async_engine(pg)
        async with engine.connect() as conn:
            check = await conn.scalar(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'ck_email_outbox_attempt_count_non_negative'"
                )
            )
            index = await conn.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'ix_verification_tokens_expires_at_live'"
                )
            )
        # A separate connection: the failed INSERT poisons the transaction.
        rejected: Exception | None = None
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO email_outbox (recipient_email, template, payload, "
                        "attempt_count) VALUES ('x@example.com', 't', '{}'::jsonb, -1)"
                    )
                )
        except Exception as exc:
            rejected = exc
        await engine.dispose()
        return check, index, rejected

    check, index, rejected = asyncio.run(inspect())

    assert check is not None
    assert "attempt_count >= 0" in check
    assert index is not None
    assert "used_at IS NULL" in index
    assert "expires_at" in index
    assert rejected is not None, "a negative attempt_count was accepted"
    assert "ck_email_outbox_attempt_count_non_negative" in str(rejected)
