"""Deep checks on the schema itself: every constraint violated directly, the
schema-wide invariants from CLAUDE.md, and the migration chain walked step by
step with data in the tables.

Constraints are exercised with raw SQL on purpose. An application check that
happens to run first proves nothing about the database; only a statement that
reaches PostgreSQL does.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator, Sequence
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings


@pytest.fixture
async def conn(db_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    """A connection whose transaction is always rolled back."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()


async def _user(conn: AsyncConnection, email: str | None = None) -> uuid.UUID:
    row = await conn.execute(
        text("INSERT INTO users (email, password_hash) VALUES (:e, 'x') RETURNING id"),
        {"e": email or f"db-{uuid.uuid4().hex}@example.com"},
    )
    return row.scalar_one()


async def _violates(conn: AsyncConnection, sql: str, params: dict[str, Any] | None = None) -> str:
    """Run `sql` in a savepoint and return the SQLSTATE it failed with."""
    savepoint = await conn.begin_nested()
    try:
        await conn.execute(text(sql), params or {})
    except (IntegrityError, DBAPIError) as exc:
        await savepoint.rollback()
        return str(
            getattr(exc.orig, "sqlstate", "")
            or getattr(getattr(exc.orig, "__cause__", None), "sqlstate", "")
        )
    await savepoint.rollback()
    raise AssertionError(f"the database accepted: {sql}")


# --------------------------------------------------------------------------
# Every constraint, violated directly
# --------------------------------------------------------------------------


@pytest.mark.integration
async def test_email_uniqueness_is_case_insensitive_and_only_among_live_rows(
    conn: AsyncConnection,
) -> None:
    email = f"Case-{uuid.uuid4().hex}@Example.com"
    await _user(conn, email)
    assert (
        await _violates(
            conn, "INSERT INTO users (email, password_hash) VALUES (:e, 'x')", {"e": email.lower()}
        )
        == "23505"
    )
    await conn.execute(text("UPDATE users SET deleted_at = now() WHERE email = :e"), {"e": email})
    await _user(conn, email.upper())  # the soft-deleted row no longer holds the address


@pytest.mark.integration
@pytest.mark.parametrize(
    ("sql", "sqlstate"),
    [
        pytest.param(
            "INSERT INTO users (email, password_hash, role) VALUES ('r@x.co', 'x', 'superadmin')",
            "22P02",
            id="users.role-enum",
        ),
        pytest.param(
            "INSERT INTO users (email) VALUES ('n@x.co')",
            "23502",
            id="users.password_hash-not-null",
        ),
        pytest.param(
            "INSERT INTO users (password_hash) VALUES ('x')", "23502", id="users.email-not-null"
        ),
        pytest.param(
            (
                "INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), 'h', now())"
            ),
            "23503",
            id="sessions.user-fk",
        ),
        pytest.param(
            (
                "INSERT INTO notifications (user_id, type, payload) VALUES (gen_random_uuid(), "
                "'account', '{}')"
            ),
            "23503",
            id="notifications.user-fk",
        ),
        pytest.param(
            "INSERT INTO settings (key, type, value) VALUES ('deep_bad', 'float', '1')",
            "22P02",
            id="settings.type-enum",
        ),
        pytest.param(
            (
                "INSERT INTO settings (key, type, value) VALUES ('accepting_orders', 'boolean', "
                "'true')"
            ),
            "23505",
            id="settings.key-unique",
        ),
        pytest.param(
            (
                "INSERT INTO email_outbox (recipient_email, template, payload, attempt_count) "
                "VALUES ('a@x.co', 't', '{}', -1)"
            ),
            "23514",
            id="outbox.attempt_count-check",
        ),
        pytest.param(
            (
                "INSERT INTO email_outbox (recipient_email, template, payload, status) "
                "VALUES ('a@x.co', 't', '{}', 'lost')"
            ),
            "22P02",
            id="outbox.status-enum",
        ),
    ],
)
async def test_standalone_constraints(sql: str, sqlstate: str, conn: AsyncConnection) -> None:
    assert await _violates(conn, sql) == sqlstate


@pytest.mark.integration
async def test_user_owned_constraints(conn: AsyncConnection) -> None:
    uid = await _user(conn)
    p = {"u": uid}
    await conn.execute(
        text(
            "INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at) "
            "VALUES (gen_random_uuid(), :u, 'dup-hash', now())"
        ),
        p,
    )
    checks = {
        "sessions.refresh_hash-unique": (
            (
                "INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at) "
                "VALUES (gen_random_uuid(), :u, 'dup-hash', now())"
            ),
            "23505",
        ),
        "sessions.token_version-positive": (
            (
                "INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at, token_version) "
                "VALUES (gen_random_uuid(), :u, 'v0', now(), 0)"
            ),
            "23514",
        ),
        "notifications.type-enum": (
            "INSERT INTO notifications (user_id, type, payload) VALUES (:u, 'marketing', '{}')",
            "22P02",
        ),
        "notifications.payload-not-null": (
            "INSERT INTO notifications (user_id, type, payload) VALUES (:u, 'account', NULL)",
            "23502",
        ),
    }
    await conn.execute(
        text(
            "INSERT INTO verification_tokens (user_id, token_hash, expires_at) VALUES (:u, 'vh', "
            "now())"
        ),
        p,
    )
    checks["verification.hash-unique"] = (
        (
            "INSERT INTO verification_tokens (user_id, token_hash, expires_at) VALUES (:u, 'vh', "
            "now())"
        ),
        "23505",
    )
    await conn.execute(
        text(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (:u, "
            "'rh', now())"
        ),
        p,
    )
    checks["reset.hash-unique"] = (
        (
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (:u, 'rh', "
            "now())"
        ),
        "23505",
    )
    cred: uuid.UUID = (
        await conn.execute(
            text(
                "INSERT INTO mfa_credentials (user_id, secret_ciphertext) VALUES (:u, 'x') "
                "RETURNING id"
            ),
            p,
        )
    ).scalar_one()
    checks["mfa.one-per-user"] = (
        "INSERT INTO mfa_credentials (user_id, secret_ciphertext) VALUES (:u, 'y')",
        "23505",
    )
    checks["mfa.method-enum"] = (
        "UPDATE mfa_credentials SET method = 'sms' WHERE user_id = :u",
        "22P02",
    )
    await conn.execute(
        text(
            "INSERT INTO mfa_recovery_codes (mfa_credential_id, code_hash) VALUES (:c, 'code-hash')"
        ),
        {"c": cred},
    )
    other = await _user(conn)
    other_cred: uuid.UUID = (
        await conn.execute(
            text(
                "INSERT INTO mfa_credentials (user_id, secret_ciphertext) VALUES (:u, 'x') "
                "RETURNING id"
            ),
            {"u": other},
        )
    ).scalar_one()
    failures = {}
    for name, (sql, state) in checks.items():
        failures[name] = (await _violates(conn, sql, p), state)
    failures["recovery.hash-unique-across-accounts"] = (
        await _violates(
            conn,
            (
                "INSERT INTO mfa_recovery_codes (mfa_credential_id, code_hash) VALUES (:c, "
                "'code-hash')"
            ),
            {"c": other_cred},
        ),
        "23505",
    )
    assert all(got == want for got, want in failures.values()), failures


# --------------------------------------------------------------------------
# Schema-wide invariants (CLAUDE.md "Non-negotiable invariants")
# --------------------------------------------------------------------------


@pytest.mark.integration
async def test_every_timestamp_column_is_timestamptz(conn: AsyncConnection) -> None:
    naive: Sequence[str] = (
        (
            await conn.execute(
                text(
                    "SELECT table_name || '.' || column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND data_type = 'timestamp without time zone'"
                )
            )
        )
        .scalars()
        .all()
    )
    assert naive == []


@pytest.mark.integration
async def test_every_primary_key_is_a_uuid(conn: AsyncConnection) -> None:
    rows = (
        await conn.execute(
            text(
                "SELECT tc.table_name, c.column_name, c.data_type "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage k USING (constraint_name, table_schema) "
                "JOIN information_schema.columns c ON c.table_name = k.table_name "
                "AND c.column_name = k.column_name AND c.table_schema = k.table_schema "
                "WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public' "
                "AND tc.table_name <> 'alembic_version'"
            )
        )
    ).all()
    # The one sanctioned exception: a partitioned table must carry its partition
    # key in the primary key (database-design.md 13.2, ADR-015), so audit_logs and
    # its monthly partitions are keyed (id uuid, created_at timestamptz).
    keyed = [
        (table, column, dtype)
        for table, column, dtype in rows
        if not (table.startswith("audit_logs") and column == "created_at")
    ]
    assert keyed and all(dtype == "uuid" for _, _, dtype in keyed), rows


# Financial rows keep their owner: database-design.md 14 mandates RESTRICT, and the purge
# never reaches them because it deletes only never-verified users, who cannot check out.
RESTRICT_TO_USERS_ALLOWED = {
    ("orders", "user_id"),  # database-design.md:1879
    ("order_items", "user_id"),  # database-design.md:1890
    ("order_items", "delivered_by"),  # database-design.md:1891
    ("payments", "recorded_by"),  # database-design.md:1892
}

_FKS_TO_USERS = (
    "SELECT c.conrelid::regclass::text, a.attname, c.confdeltype::text FROM pg_constraint c "
    "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
    "WHERE c.contype = 'f' AND c.confrelid = 'users'::regclass"
)


@pytest.mark.integration
async def test_no_foreign_key_to_users_can_block_the_purge(conn: AsyncConnection) -> None:
    rules = (await conn.execute(text(_FKS_TO_USERS))).all()
    # c = CASCADE, n = SET NULL. a (NO ACTION) or r (RESTRICT) would make the daily purge
    # fail on the first account that owned such a row, unless the pair is allowlisted.
    blocking = {
        (table, column, rule)
        for table, column, rule in rules
        if rule not in ("c", "n")
        and not (rule == "r" and (table, column) in RESTRICT_TO_USERS_ALLOWED)
    }
    assert rules and blocking == set(), blocking
    restrict = {(table, column) for table, column, rule in rules if rule == "r"}
    assert restrict == RESTRICT_TO_USERS_ALLOWED, restrict


NON_MONEY_NUMERIC = {"products.average_rating"}


@pytest.mark.integration
async def test_money_is_never_stored_as_a_float(conn: AsyncConnection) -> None:
    floats: Sequence[str] = (
        (
            await conn.execute(
                text(
                    "SELECT table_name || '.' || column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND data_type IN ('real', "
                    "'double precision', 'numeric')"
                )
            )
        )
        .scalars()
        .all()
    )
    # Exact decimals that are not money, each by design (database-design.md 6.4).
    assert set(floats) <= NON_MONEY_NUMERIC, floats


# --------------------------------------------------------------------------
# Migrations with data in the tables
# --------------------------------------------------------------------------


_SEED = [
    (
        "INSERT INTO users (id, email, password_hash) "
        "VALUES ('11111111-1111-1111-1111-111111111111', 'seed@example.com', 'x')"
    ),
    (
        "INSERT INTO sessions (id, user_id, refresh_token_hash, expires_at) "
        "VALUES (gen_random_uuid(), '11111111-1111-1111-1111-111111111111', 'seed', now())"
    ),
    (
        "INSERT INTO verification_tokens (user_id, token_hash, expires_at) "
        "VALUES ('11111111-1111-1111-1111-111111111111', 'seed', now())"
    ),
    (
        "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
        "VALUES ('11111111-1111-1111-1111-111111111111', 'seed', now())"
    ),
    (
        "INSERT INTO mfa_credentials (user_id, secret_ciphertext) "
        "VALUES ('11111111-1111-1111-1111-111111111111', 'x')"
    ),
    (
        "INSERT INTO email_outbox (recipient_email, template, payload, status, attempt_count) "
        "VALUES ('seed@example.com', 'verification_email', '{\"token\": \"raw\"}', 'sent', 1)"
    ),
    "INSERT INTO audit_logs (action, entity_type) VALUES ('seed', 'User')",
    (
        "INSERT INTO notifications (user_id, type, payload) "
        "VALUES ('11111111-1111-1111-1111-111111111111', 'order', '{\"event\": \"seed\"}')"
    ),
    "UPDATE settings SET value = 'true' WHERE key = 'accepting_orders'",
    "INSERT INTO categories (name, slug) VALUES ('Seed', 'seed')",
    "INSERT INTO materials (name) VALUES ('Seed')",
    "INSERT INTO colours (name) VALUES ('Seed')",
    "INSERT INTO carts (user_id) VALUES ('11111111-1111-1111-1111-111111111111')",
]


async def _execute(url: str, statements: list[str]) -> list[Any]:
    engine = create_async_engine(url)
    results = []
    async with engine.begin() as connection:
        for statement in statements:
            result = await connection.execute(text(statement))
            results.append(result.all() if result.returns_rows else None)
    await engine.dispose()
    return results


@pytest.mark.integration
def test_every_migration_step_goes_down_and_up_with_data_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = Config("alembic.ini")
    revisions = [
        r.revision for r in ScriptDirectory.from_config(config).walk_revisions()
    ]  # head first
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        try:
            command.upgrade(config, "head")
            asyncio.run(_execute(url, _SEED))
            # One step down and back up at every level, then all the way down.
            for _ in revisions[:-1]:
                command.downgrade(config, "-1")
                command.upgrade(config, "+1")
                command.downgrade(config, "-1")
            command.downgrade(config, "base")
            command.upgrade(config, "head")
            asyncio.run(_execute(url, _SEED))
            [count] = asyncio.run(_execute(url, ["SELECT count(*) FROM users"]))
            assert count == [(1,)]
        finally:
            get_settings.cache_clear()
    assert revisions, "no migrations found"


@pytest.mark.integration
def test_data_survives_a_partial_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Down to the first identity revision and back up: surviving tables keep
    their rows, and re-added columns take their documented defaults."""
    config = Config("alembic.ini")
    with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        monkeypatch.setenv("DATABASE_URL", url)
        get_settings.cache_clear()
        try:
            command.upgrade(config, "head")
            asyncio.run(_execute(url, [*_SEED[:1], "UPDATE users SET auth_epoch = 5"]))
            command.downgrade(config, "42601a09ada6")
            command.upgrade(config, "head")
            [rows] = asyncio.run(_execute(url, ["SELECT email, auth_epoch FROM users"]))
        finally:
            get_settings.cache_clear()
    assert rows == [("seed@example.com", 0)]
