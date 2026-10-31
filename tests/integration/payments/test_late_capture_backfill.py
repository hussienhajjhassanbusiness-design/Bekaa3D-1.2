"""I16 (VS-030 plan 4.3) on its own throwaway Postgres: the backfill migration creates one
`late_capture` refund per late-captured payment without a live one, skips and reports
malformed audit rows, reruns idempotently, batches, and downgrades only its pending rows."""

import asyncio
import importlib.util
import json
import os
import uuid
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings
from tests.integration.fulfillment.order_support import seed_physical_order

BACKFILL = "80e56abf0969"
PARENT = "c01e53ab3e0f"
LIVE_REASON = "late capture: attempt_not_live"
MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "versions"
# A malformed amount whose text cannot occur in a uuid, a revision id or a reason code
# (uppercase, non-hex letters), so finding it in the skip report means the payload leaked.
PAYLOAD_MARKER = "NOT-A-NUMBER-backfill-payload-marker"


def _module() -> ModuleType:
    path = next(MIGRATION.glob(f"{BACKFILL}_*.py"))
    spec = importlib.util.spec_from_file_location("backfill_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# case: (captured amount, captured currency, audit after_data or None for no audit row)
CASES: dict[str, tuple[int | None, str | None, Any]] = {
    "a": (1100, "USD", None),
    "b": (None, None, {"captured_amount_cents": 900, "captured_currency": "USD"}),
    "c": (None, None, {"captured_amount_cents": PAYLOAD_MARKER}),
    "d": (None, None, {"captured_amount_cents": -5}),
    "e": (None, None, "not an object"),
    "f": (None, None, None),
    "g": (700, "USD", None),  # already has a live late-capture refund (the live sink's)
    "h": (50000, "LBP", None),
    "i": (None, None, {"captured_amount_cents": None, "captured_currency": None}),
    "j": (None, None, {"captured_amount_cents": 12.5}),
    "k": (None, None, {"captured_amount_cents": None, "captured_currency": "LBP"}),
}


async def _late_payment(engine: AsyncEngine, case: str) -> uuid.UUID:
    captured, currency, audit = CASES[case]
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        order = await seed_physical_order(
            db, payment_method="online", payment_status="expired", before_vs049=True
        )
        payment_id = await db.scalar(
            text(
                "UPDATE payments SET late_captured_at = now(), captured_amount_cents = :a,"
                " captured_currency = :c WHERE order_id = :o RETURNING id"
            ),
            {"a": captured, "c": currency, "o": order.order_id},
        )
        if audit is not None:
            await db.execute(
                text(
                    "INSERT INTO audit_logs (action, entity_type, entity_id, after_data)"
                    " VALUES ('payment.late_capture', 'payment', :p, CAST(:d AS jsonb))"
                ),
                {"p": payment_id, "d": json.dumps(audit)},
            )
        if case == "g":
            await db.execute(
                text(
                    "INSERT INTO refunds (order_id, payment_id, payment_provider, kind,"
                    " amount_cents, reason, initiated_at)"
                    " VALUES (:o, :p, 'mock', 'late_capture', 700, :r, now())"
                ),
                {"o": order.order_id, "p": payment_id, "r": LIVE_REASON},
            )
        await db.commit()
    assert isinstance(payment_id, uuid.UUID)
    return payment_id


async def _seed(url: str) -> dict[str, uuid.UUID]:
    engine = create_async_engine(url)
    seeded = {case: await _late_payment(engine, case) for case in CASES}
    await engine.dispose()
    return seeded


async def _rows(url: str) -> dict[uuid.UUID, list[Any]]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT payment_id, status::text AS status, amount_cents, currency, reason,"
                    " requested_by FROM refunds WHERE kind = 'late_capture' ORDER BY created_at"
                )
            )
        ).all()
        skipped: Sequence[Any] = (
            (
                await conn.execute(
                    text(
                        "SELECT after_data FROM audit_logs WHERE action = 'refund.backfill_skipped'"
                        " ORDER BY created_at"
                    )
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    by_payment: dict[uuid.UUID, list[Any]] = {}
    for row in rows:
        by_payment.setdefault(row.payment_id, []).append(row)
    by_payment[uuid.UUID(int=0)] = list(skipped)
    return by_payment


async def _rerun(url: str, module: ModuleType, batch_size: int = 500) -> dict[str, int]:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        counts: dict[str, int] = await conn.run_sync(
            lambda sync: module.backfill(sync, batch_size=batch_size)
        )
    await engine.dispose()
    return counts


async def _execute(url: str, sql: str, **params: Any) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)
    await engine.dispose()


async def _seed_many(url: str, count: int) -> None:
    """`count` late-captured attempts on one order (only live attempts are unique)."""
    engine = create_async_engine(url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        order = await seed_physical_order(
            db, payment_method="online", payment_status="expired", before_vs049=True
        )
        await db.execute(
            text(
                "INSERT INTO payments (order_id, provider, order_payment_method,"
                " provider_payment_id, status, amount_cents, initiated_at, expired_at,"
                " late_captured_at, captured_amount_cents, captured_currency)"
                " SELECT :o, 'mock', 'online', 'bulk-' || n, 'expired', 1000, now(), now(),"
                " now(), 1000, 'USD' FROM generate_series(1, :n) AS n"
            ),
            {"o": order.order_id, "n": count},
        )
        await db.commit()
    await engine.dispose()


@pytest.mark.integration
def test_i16_the_backfill_migration() -> None:
    previous = os.environ.get("DATABASE_URL")
    module = _module()
    try:
        with PostgresContainer("postgres:16", driver="asyncpg") as postgres:
            url = postgres.get_connection_url()
            os.environ["DATABASE_URL"] = url
            get_settings.cache_clear()
            config = Config("alembic.ini")
            command.upgrade(config, PARENT)
            ids = asyncio.run(_seed(url))
            command.upgrade(config, BACKFILL)

            rows = asyncio.run(_rows(url))
            marker = f"late capture (backfill {BACKFILL})"
            flagged = f"{marker}; provider reported no amount; check the dashboard"
            expected = {
                "a": (1100, "USD", marker),
                "b": (900, "USD", marker),
                "f": (1000, "USD", flagged),
                "h": (50000, "LBP", marker),  # never converted
                "i": (1000, "USD", flagged),
                "k": (1000, "USD", flagged),  # the attempt's amount, in its own currency
            }
            for case, (amount, currency, reason) in expected.items():
                (row,) = rows[ids[case]]
                assert (row.status, row.amount_cents, row.currency, row.reason) == (
                    "pending",
                    amount,
                    currency,
                    reason,
                ), case
                assert row.requested_by is None
            for case in ("c", "d", "e", "j"):
                assert ids[case] not in rows, case
            (live,) = rows[ids["g"]]
            assert (live.amount_cents, live.reason) == (700, LIVE_REASON)
            (report,) = rows[uuid.UUID(int=0)]
            assert report["revision"] == BACKFILL
            assert {s["payment_id"]: s["reason"] for s in report["skipped"]} == {
                str(ids[c]): "audit_malformed" for c in ("c", "d", "e", "j")
            }
            assert PAYLOAD_MARKER not in str(report)  # ids and reason codes only, never the payload

            again = asyncio.run(_rerun(url, module))
            assert (again["created"], again["existing"], again["skipped"]) == (0, 7, 4)
            assert sum(len(v) for k, v in asyncio.run(_rows(url)).items() if k.int) == 7

            for case, change in (
                ("a", "status = 'settled', settled_at = now()"),
                ("f", "status = 'failed', failed_at = now()"),
                ("h", "status = 'voided', voided_at = now(), void_reason = 'mistake'"),
            ):
                asyncio.run(
                    _execute(url, f"UPDATE refunds SET {change} WHERE payment_id = :p", p=ids[case])
                )
            command.downgrade(config, PARENT)
            after = asyncio.run(_rows(url))
            kept = {case: [r.status for r in after[ids[case]]] for case in ("a", "f", "h")}
            assert kept == {"a": ["settled"], "f": ["failed"], "h": ["voided"]}  # money history
            assert [r.reason for r in after[ids["g"]]] == [LIVE_REASON]
            for case in ("b", "i", "k"):
                assert ids[case] not in after, case

            asyncio.run(_seed_many(url, 1200))
            counts = asyncio.run(_rerun(url, module))
            assert counts["batches"] == 3 and counts["scanned"] == 1200 + len(CASES)
            # b, i and k again; a (settled), f (owed), h (voided) and g (live) are handled.
            assert counts["created"] == 1200 + 3
            final = asyncio.run(_rows(url))
            assert [r.status for r in final[ids["f"]]] == ["failed"]
            assert [r.status for r in final[ids["h"]]] == ["voided"]
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
