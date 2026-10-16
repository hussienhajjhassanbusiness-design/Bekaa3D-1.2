"""The `rotate_ip_salt` job against PostgreSQL (VS-046, SEC-25, ADR-028).

The table holds one global salt. A test makes it due by backdating `created_at`;
the job then replaces that row, so nothing backdated survives the test."""

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.jobs import rotate_ip_salt as rotate_module
from app.jobs.registry import CRON_JOBS, FUNCTIONS
from app.jobs.rotate_ip_salt import IpHashSaltRotationError, rotate_ip_salt
from app.platform.application.commands.rotate_ip_hash_salt import RotateIpHashSalt
from app.platform.infrastructure.models import AuditLogModel
from app.platform.public import SqlAuditWriter, ip_hash_salt_store


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


async def _salts(engine: AsyncEngine) -> list[tuple[UUID, datetime, bytes]]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT id, created_at, salt FROM ip_hash_salts"))
        return [(r.id, r.created_at, bytes(r.salt)) for r in rows]


async def make_due(engine: AsyncEngine) -> UUID:
    """Backdate the current salt into an earlier month; returns its id."""
    async with engine.begin() as conn:
        salt_id: UUID = await conn.scalar(
            text(
                "UPDATE ip_hash_salts SET created_at = created_at - interval '40 days' "
                "WHERE is_current RETURNING id"
            )
        )
    return salt_id


async def _rotation_audits(engine: AsyncEngine, entity_id: UUID) -> list[AuditLogModel]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        rows = await session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.action == "ip_hash_salt.rotated",
                AuditLogModel.entity_id == entity_id,
            )
        )
        return list(rows.all())


@pytest.mark.integration
async def test_a_salt_from_this_month_is_left_alone(db_engine: AsyncEngine) -> None:
    await rotate_ip_salt(_ctx(db_engine))  # whatever the shared state, now it is this month's
    [(before, _, _)] = await _salts(db_engine)
    assert await rotate_ip_salt(_ctx(db_engine)) is False
    [(after, _, _)] = await _salts(db_engine)
    assert after == before
    async with db_engine.connect() as conn:
        later = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs WHERE action = 'ip_hash_salt.rotated' "
                "AND before_data->>'previous_salt_id' = :id"
            ),
            {"id": str(before)},
        )
    assert later == 0


@pytest.mark.integration
async def test_a_due_salt_is_replaced_and_audited_with_ids_only(db_engine: AsyncEngine) -> None:
    old_id = await make_due(db_engine)
    assert await rotate_ip_salt(_ctx(db_engine)) is True

    [(new_id, created_at, salt)] = await _salts(db_engine)
    assert new_id != old_id
    assert created_at.month == datetime.now(UTC).month and len(salt) == 32
    [row] = await _rotation_audits(db_engine, new_id)
    assert row.actor_user_id is None and row.entity_type == "IpHashSalt"
    assert row.before_data == {"previous_salt_id": str(old_id)}
    assert row.after_data is None and row.ip_hash is None
    stored = json.dumps([row.before_data, row.after_data])
    assert salt.hex() not in stored and salt.hex().upper() not in stored


@pytest.mark.integration
async def test_a_second_run_with_the_same_now_is_a_no_op(db_engine: AsyncEngine) -> None:
    await make_due(db_engine)
    now = datetime.now(UTC)
    assert await rotate_ip_salt(_ctx(db_engine), now=now) is True
    [(first, _, _)] = await _salts(db_engine)
    assert await rotate_ip_salt(_ctx(db_engine), now=now) is False
    [(second, _, _)] = await _salts(db_engine)
    assert second == first
    assert len(await _rotation_audits(db_engine, first)) == 1


@pytest.mark.integration
async def test_an_empty_table_self_heals(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM ip_hash_salts"))
    assert await rotate_ip_salt(_ctx(db_engine)) is True
    [(new_id, _, _)] = await _salts(db_engine)
    [row] = await _rotation_audits(db_engine, new_id)
    assert row.before_data == {"previous_salt_id": None}


class _UnpartitionedMonthAuditWriter:
    """Writes the audit row into 2999-01, a month with no audit_logs partition."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, **fields: Any) -> None:
        await self._session.execute(
            text(
                "INSERT INTO audit_logs (action, entity_type, entity_id, created_at) "
                "VALUES (:action, :entity_type, :entity_id, '2999-01-15 00:00:00+00')"
            ),
            {k: fields[k] for k in ("action", "entity_type", "entity_id")},
        )


async def _assert_no_2999_partition(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        assert await conn.scalar(text("SELECT to_regclass('audit_logs_y2999m01')")) is None


@pytest.mark.integration
async def test_a_missing_audit_partition_rolls_the_whole_rotation_back(
    db_engine: AsyncEngine,
) -> None:
    """Amendment D: no partition is touched; PostgreSQL itself refuses the 2999 row."""
    await _assert_no_2999_partition(db_engine)
    old_id = await make_due(db_engine)
    [(_, old_created, old_salt)] = await _salts(db_engine)

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    with pytest.raises(DBAPIError, match="no partition"):
        async with factory() as session, session.begin():
            await RotateIpHashSalt(
                ip_hash_salt_store(session), _UnpartitionedMonthAuditWriter(session)
            ).execute(now=datetime.now(UTC))

    assert await _salts(db_engine) == [(old_id, old_created, old_salt)]
    await _assert_no_2999_partition(db_engine)
    assert await rotate_ip_salt(_ctx(db_engine)) is True  # the next run retries and succeeds


@pytest.mark.integration
async def test_the_job_raises_a_class_only_error_and_the_next_run_retries(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _assert_no_2999_partition(db_engine)
    old_id = await make_due(db_engine)
    monkeypatch.setattr(rotate_module, "SqlAuditWriter", _UnpartitionedMonthAuditWriter)
    with pytest.raises(IpHashSaltRotationError) as raised:
        await rotate_ip_salt(_ctx(db_engine))
    # The class name only: no SQL, no values, no driver message.
    assert re.fullmatch(r"[A-Za-z]+Error", str(raised.value)), str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    [(still, _, _)] = await _salts(db_engine)
    assert still == old_id

    monkeypatch.setattr(rotate_module, "SqlAuditWriter", SqlAuditWriter)
    assert await rotate_ip_salt(_ctx(db_engine)) is True


def test_the_worker_checks_daily_and_at_startup() -> None:
    assert rotate_ip_salt in FUNCTIONS
    [job] = [j for j in CRON_JOBS if j.coroutine is rotate_ip_salt]
    assert job.run_at_startup is True
    assert job.day is None and job.hour == 0 and job.minute == 23


@pytest.mark.integration
async def test_reading_the_age_never_selects_the_salt_bytes(db_engine: AsyncEngine) -> None:
    statements: list[str] = []

    def spy(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        statements.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", spy)
    try:
        async with async_sessionmaker(db_engine)() as session:
            current = await ip_hash_salt_store(session).current_created_at()
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", spy)
    assert current is not None
    [select_sql] = [s for s in statements if "FROM ip_hash_salts" in s]
    assert "ip_hash_salts.salt" not in select_sql and "ip_hash_salts.id" in select_sql
