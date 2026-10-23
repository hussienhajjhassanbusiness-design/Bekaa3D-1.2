"""VS-030 PR A on real Postgres (migration c01e53ab3e0f, plan 4.2): every constraint refuses
its row by name, and the same statement passes once that constraint alone is dropped (in a
rolled-back transaction). No application code writes these tables yet."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.fulfillment.order_support import seed_physical_order

pytestmark = pytest.mark.integration

_CASTS = {
    "payment_provider": "payment_provider",
    "kind": "refund_kind",
    "status": "refund_status",
}
_LINE_ENUMS = {
    "product_type": "product_type",
    "fulfillment_status": "order_item_status",
    "payment_method": "payment_method",
}


def constraint_of(error: IntegrityError) -> str | None:
    """asyncpg's `constraint_name`, the driver's equivalent of psycopg's `diag.constraint_name`."""
    name = getattr(getattr(error.orig, "__cause__", None), "constraint_name", None)
    return name if isinstance(name, str) else None


def insert_sql(table: str, values: Mapping[str, Any]) -> str:
    columns = ", ".join(values)
    params = ", ".join(f"CAST(:{c} AS {_CASTS[c]})" if c in _CASTS else f":{c}" for c in values)
    return f"INSERT INTO {table} ({columns}) VALUES ({params})"


async def _execute(conn: AsyncConnection, sql: str, params: Mapping[str, Any]) -> None:
    await conn.execute(text(sql), dict(params))


async def assert_refused(
    engine: AsyncEngine,
    constraint: str,
    sql: str,
    params: Mapping[str, Any],
    *,
    drop: str,
) -> None:
    """Refused by `constraint` (by name), then accepted once `drop` removes it; all rolled back."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            with pytest.raises(IntegrityError) as caught:
                async with conn.begin_nested():
                    await _execute(conn, sql, params)
            assert constraint_of(caught.value) == constraint, caught.value
            await conn.execute(text(drop))
            await _execute(conn, sql, params)  # the scratch proof: nothing else refuses it
        finally:
            await outer.rollback()


def drop_constraint(table: str, name: str) -> str:
    return f"ALTER TABLE {table} DROP CONSTRAINT {name}"


async def insert(engine: AsyncEngine, table: str, values: Mapping[str, Any]) -> None:
    async with engine.begin() as conn:
        await _execute(conn, insert_sql(table, values), values)


@dataclass(frozen=True)
class Paid:
    order_id: uuid.UUID
    user_id: uuid.UUID
    line_ids: tuple[uuid.UUID, ...]
    payment_id: uuid.UUID
    provider: str
    admin_id: uuid.UUID


async def _payment_of(engine: AsyncEngine, order_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT id, provider::text FROM payments WHERE order_id = :o"),
                {"o": order_id},
            )
        ).one()
    return row.id, row.provider


async def paid_order(
    engine: AsyncEngine, db: AsyncSession, *, cash: bool = False, lines: int = 1
) -> Paid:
    """A paid order: online with a `mock` payment, or cash with its handover payment."""
    admin = await create_user(db, role=UserRole.ADMIN)
    order = await seed_physical_order(
        db,
        payment_method="cash" if cash else "online",
        payment_status=None if cash else "paid",
        line_states=["delivered"] * lines,
    )
    if cash:
        at = datetime.now(UTC)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO payments (order_id, provider, order_payment_method, status,"
                    " amount_cents, initiated_at, verified_at, recorded_by)"
                    " VALUES (:o, 'cash', 'cash', 'paid', :a, :at, :at, :by)"
                ),
                {"o": order.order_id, "a": 1000 * lines, "at": at, "by": admin.id},
            )
    await db.commit()
    payment_id, provider = await _payment_of(engine, order.order_id)
    return Paid(order.order_id, order.user_id, order.line_ids, payment_id, provider, admin.id)


def refund_row(order: Paid, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "order_id": order.order_id,
        "payment_id": order.payment_id,
        "payment_provider": order.provider,
        "kind": "admin",
        "status": "pending",
        "amount_cents": 100,
        "currency": "USD",
        "reason": "Goodwill.",
        "requested_by": order.admin_id,
        "initiated_at": datetime.now(UTC),
    }
    return row | over


def late_capture_row(order: Paid, **over: Any) -> dict[str, Any]:
    return refund_row(order, kind="late_capture", requested_by=None) | over


def chargeback_row(order: Paid, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "order_id": order.order_id,
        "payment_id": order.payment_id,
        "payment_provider": order.provider,
        "provider_dispute_reference": f"dp-{uuid.uuid4().hex}",
        "charged_cents": 1000,
        "applied_cents": 1000,
        "excess_cents": 0,
        "currency": "USD",
        "reason": "Bank reversal.",
        "recorded_by": order.admin_id,
        "received_at": datetime.now(UTC),
    }
    return row | over


def item_row(parent_column: str, parent_id: uuid.UUID, order: Paid, **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        parent_column: parent_id,
        "order_id": order.order_id,
        "order_item_id": order.line_ids[0],
        "amount_cents": 100,
    }
    return row | over


async def refused(
    engine: AsyncEngine,
    table: str,
    constraint: str,
    values: Mapping[str, Any],
    *,
    index: bool = False,
) -> None:
    drop = f"DROP INDEX {constraint}" if index else drop_constraint(table, constraint)
    await assert_refused(engine, constraint, insert_sql(table, values), values, drop=drop)


# --------------------------------------------------------------------------- refunds


async def test_a_valid_refund_and_item_are_accepted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    refund = refund_row(order)
    await insert(db_engine, "refunds", refund)
    await insert(db_engine, "refund_items", item_row("refund_id", refund["id"], order))


async def test_ck_refunds_amount(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_order(db_engine, db_session)
    await refused(db_engine, "refunds", "ck_refunds_amount", refund_row(order, amount_cents=0))


async def test_ck_refunds_currency_and_late_capture_keeps_its_currency(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Q6: only a late capture may carry a non-USD currency, stored as reported."""
    order = await paid_order(db_engine, db_session)
    await refused(db_engine, "refunds", "ck_refunds_currency", refund_row(order, currency="LBP"))
    await refused(
        db_engine, "refunds", "ck_refunds_currency", late_capture_row(order, currency="lbp")
    )
    await insert(db_engine, "refunds", late_capture_row(order, currency="LBP"))


async def test_ck_refunds_requester(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_order(db_engine, db_session)
    await refused(
        db_engine, "refunds", "ck_refunds_requester", refund_row(order, requested_by=None)
    )


async def test_ck_refunds_late_capture_online(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    cash = await paid_order(db_engine, db_session, cash=True)
    await refused(db_engine, "refunds", "ck_refunds_late_capture_online", late_capture_row(cash))
    await insert(db_engine, "refunds", refund_row(cash))  # an admin refund of cash is fine


async def test_ck_refunds_reissued_failed(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    """Also what keeps a voided refund from carrying `reissued_at`."""
    order = await paid_order(db_engine, db_session)
    now = datetime.now(UTC)
    for row in (
        refund_row(order, reissued_at=now),
        refund_row(order, status="voided", voided_at=now, void_reason="x", reissued_at=now),
    ):
        await refused(db_engine, "refunds", "ck_refunds_reissued_failed", row)


@pytest.mark.parametrize(
    "over",
    [
        {"status": "settled"},
        {"status": "failed"},
        {"settled_at": "now"},
        {"failed_at": "now"},
        {"voided_at": "now", "void_reason": "x"},
        {"status": "voided", "void_reason": "x"},
        {"status": "voided", "voided_at": "now"},
    ],
    ids=[
        "settled-without-stamp",
        "failed-without-stamp",
        "pending-with-settled-stamp",
        "pending-with-failed-stamp",
        "pending-with-void-stamp",
        "voided-without-stamp",
        "voided-without-reason",
    ],
)
async def test_ck_refunds_state_stamps(
    over: dict[str, Any], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    now = datetime.now(UTC)
    values = {k: now if v == "now" else v for k, v in over.items()}
    await refused(db_engine, "refunds", "ck_refunds_state_stamps", refund_row(order, **values))


async def test_every_legal_refund_state_is_accepted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    now = datetime.now(UTC)
    for over in (
        {"status": "settled", "settled_at": now},
        {"status": "failed", "failed_at": now},
        {"status": "failed", "failed_at": now, "reissued_at": now},
        {"status": "voided", "voided_at": now, "void_reason": "Mistake."},
        {"status": "voided", "voided_at": now, "void_reason": "Owed.", "failed_at": now},
    ):
        await insert(db_engine, "refunds", refund_row(order, **over))


async def test_ck_refunds_void_never_settled_on_insert_and_on_update(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """A settled refund can never become voided (plan 2.3), even through a bad UPDATE."""
    order = await paid_order(db_engine, db_session)
    now = datetime.now(UTC)
    row = refund_row(order, status="voided", voided_at=now, void_reason="x", settled_at=now)
    await refused(db_engine, "refunds", "ck_refunds_void_never_settled", row)
    settled = refund_row(order, status="settled", settled_at=now)
    await insert(db_engine, "refunds", settled)
    update = (
        "UPDATE refunds SET status = 'voided', voided_at = now(), void_reason = 'x' WHERE id = :id"
    )
    await assert_refused(
        db_engine,
        "ck_refunds_void_never_settled",
        update,
        {"id": settled["id"]},
        drop=drop_constraint("refunds", "ck_refunds_void_never_settled"),
    )


@pytest.mark.parametrize(
    "over",
    [
        {"reason": ""},
        {"reason": "x" * 1001},
        {"settlement_reference": ""},
        {"settlement_reference": "x" * 201},
        {"settlement_note": "x" * 1001},
        {"failure_reason": ""},
        {"void_reason": "x" * 1001},
    ],
    ids=["reason-empty", "reason-long", "ref-empty", "ref-long", "note", "failure", "void"],
)
async def test_ck_refunds_text_lengths(
    over: dict[str, Any], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    if "void_reason" in over:
        over = over | {"status": "voided", "voided_at": datetime.now(UTC)}
    await refused(db_engine, "refunds", "ck_refunds_text_lengths", refund_row(order, **over))


async def test_fk_refunds_payment_needs_the_orders_own_payment_and_provider(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    other = await paid_order(db_engine, db_session)
    cash = await paid_order(db_engine, db_session, cash=True)
    for row in (
        refund_row(order, payment_id=other.payment_id),  # another order's payment
        refund_row(cash, payment_provider="mock"),  # the provider column lying
        refund_row(order, payment_id=uuid.uuid4()),
    ):
        await refused(db_engine, "refunds", "fk_refunds_payment", row)


async def test_fk_refunds_reissue_of_refund_id(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    row = refund_row(order, reissue_of_refund_id=uuid.uuid4())
    await refused(db_engine, "refunds", "fk_refunds_reissue_of_refund_id", row)


@pytest.mark.parametrize(
    "column", ["requested_by", "approved_by", "settled_by", "failed_by", "voided_by"]
)
async def test_fk_refunds_users(
    column: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    row = refund_row(order, **{column: uuid.uuid4()})
    await refused(db_engine, "refunds", f"fk_refunds_{column}", row)


async def test_uq_refunds_reissue_of(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_order(db_engine, db_session)
    now = datetime.now(UTC)
    failed = refund_row(order, status="failed", failed_at=now, reissued_at=now)
    await insert(db_engine, "refunds", failed)
    await insert(db_engine, "refunds", refund_row(order, reissue_of_refund_id=failed["id"]))
    second = refund_row(order, reissue_of_refund_id=failed["id"])
    await refused(db_engine, "refunds", "uq_refunds_reissue_of", second)


async def test_uq_refunds_one_live_late_capture(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    await insert(db_engine, "refunds", late_capture_row(order))
    await refused(
        db_engine,
        "refunds",
        "uq_refunds_one_live_late_capture",
        late_capture_row(order),
        index=True,
    )


async def test_a_failed_or_voided_late_capture_frees_its_payment(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    for dead in (
        {"status": "failed", "failed_at": now},
        {"status": "voided", "voided_at": now, "void_reason": "Absorbed."},
    ):
        order = await paid_order(db_engine, db_session)
        await insert(db_engine, "refunds", late_capture_row(order, **dead))
        await insert(db_engine, "refunds", late_capture_row(order))
        await insert(db_engine, "refunds", refund_row(order))  # admin refunds are not limited


# --------------------------------------------------------------------- refund_items


async def _refund(engine: AsyncEngine, order: Paid) -> uuid.UUID:
    row = refund_row(order)
    await insert(engine, "refunds", row)
    return uuid.UUID(str(row["id"]))


async def test_ck_refund_items_amount(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_order(db_engine, db_session)
    row = item_row("refund_id", await _refund(db_engine, order), order, amount_cents=0)
    await refused(db_engine, "refund_items", "ck_refund_items_amount", row)


async def test_fk_refund_items_refund_id_needs_the_same_order(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    other = await paid_order(db_engine, db_session)
    # Another order's refund, naming this order's own line.
    row = item_row("refund_id", await _refund(db_engine, other), order)
    await refused(db_engine, "refund_items", "fk_refund_items_refund_id", row)


async def test_fk_refund_items_order_item_needs_the_refunds_order(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    other = await paid_order(db_engine, db_session)
    row = item_row(
        "refund_id", await _refund(db_engine, order), order, order_item_id=other.line_ids[0]
    )
    await refused(db_engine, "refund_items", "fk_refund_items_order_item", row)


async def test_uq_refund_items_line(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_order(db_engine, db_session)
    refund_id = await _refund(db_engine, order)
    await insert(db_engine, "refund_items", item_row("refund_id", refund_id, order))
    row = item_row("refund_id", refund_id, order)
    await refused(db_engine, "refund_items", "uq_refund_items_line", row)


# ---------------------------------------------------------------------- chargebacks


async def test_a_valid_chargeback_and_item_are_accepted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    chargeback = chargeback_row(order, applied_cents=0, excess_cents=1000)  # plan Must-resolve 3
    await insert(db_engine, "chargebacks", chargeback)
    row = chargeback_row(order, charged_cents=600, applied_cents=500, excess_cents=100)
    await insert(db_engine, "chargebacks", row)
    await insert(db_engine, "chargeback_items", item_row("chargeback_id", row["id"], order))


@pytest.mark.parametrize(
    "over",
    [
        {"charged_cents": 0, "applied_cents": 0, "excess_cents": 0},
        {"applied_cents": -1, "excess_cents": 1001},
        {"applied_cents": 1001, "excess_cents": -1},
        {"applied_cents": 900, "excess_cents": 0},
    ],
    ids=["zero", "negative-applied", "negative-excess", "split-not-summing"],
)
async def test_ck_chargebacks_money(
    over: dict[str, Any], db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    await refused(db_engine, "chargebacks", "ck_chargebacks_money", chargeback_row(order, **over))


async def test_ck_chargebacks_currency(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    order = await paid_order(db_engine, db_session)
    row = chargeback_row(order, currency="EUR")
    await refused(db_engine, "chargebacks", "ck_chargebacks_currency", row)


async def test_ck_chargebacks_online_only(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    """Plan I23: a cash payment can never be charged back, and the column cannot lie."""
    cash = await paid_order(db_engine, db_session, cash=True)
    await refused(db_engine, "chargebacks", "ck_chargebacks_online_only", chargeback_row(cash))
    lying = chargeback_row(cash, payment_provider="mock")
    await refused(db_engine, "chargebacks", "fk_chargebacks_payment", lying)


async def test_fk_chargebacks_payment_needs_the_orders_own_payment(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    other = await paid_order(db_engine, db_session)
    row = chargeback_row(order, payment_id=other.payment_id)
    await refused(db_engine, "chargebacks", "fk_chargebacks_payment", row)


async def test_uq_chargebacks_dispute(db_engine: AsyncEngine, db_session: AsyncSession) -> None:
    """Plan I24: one record per provider dispute reference, even on another order."""
    order = await paid_order(db_engine, db_session)
    other = await paid_order(db_engine, db_session)
    first = chargeback_row(order)
    await insert(db_engine, "chargebacks", first)
    again = chargeback_row(other, provider_dispute_reference=first["provider_dispute_reference"])
    await refused(db_engine, "chargebacks", "uq_chargebacks_dispute", again)


@pytest.mark.parametrize(
    ("over", "constraint"),
    [
        ({"provider_dispute_reference": ""}, "ck_chargebacks_dispute_reference"),
        ({"provider_dispute_reference": "x" * 201}, "ck_chargebacks_dispute_reference"),
        ({"reason": ""}, "ck_chargebacks_reason"),
        ({"reason": "x" * 1001}, "ck_chargebacks_reason"),
        ({"recorded_by": "random"}, "fk_chargebacks_recorded_by"),
    ],
    ids=["ref-empty", "ref-long", "reason-empty", "reason-long", "recorded-by"],
)
async def test_chargeback_text_and_recorder(
    over: dict[str, Any], constraint: str, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    values = {k: uuid.uuid4() if v == "random" else v for k, v in over.items()}
    await refused(db_engine, "chargebacks", constraint, chargeback_row(order, **values))


async def _chargeback(engine: AsyncEngine, order: Paid) -> uuid.UUID:
    row = chargeback_row(order)
    await insert(engine, "chargebacks", row)
    return uuid.UUID(str(row["id"]))


async def test_chargeback_item_constraints(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    order = await paid_order(db_engine, db_session)
    other = await paid_order(db_engine, db_session)
    mine = await _chargeback(db_engine, order)
    theirs = await _chargeback(db_engine, other)
    table = "chargeback_items"
    await refused(
        db_engine,
        table,
        "ck_chargeback_items_amount",
        item_row("chargeback_id", mine, order, amount_cents=0),
    )
    await refused(
        db_engine,
        table,
        "fk_chargeback_items_chargeback_id",
        item_row("chargeback_id", theirs, order),
    )
    await refused(
        db_engine,
        table,
        "fk_chargeback_items_order_item",
        item_row("chargeback_id", mine, order, order_item_id=other.line_ids[0]),
    )
    await insert(db_engine, table, item_row("chargeback_id", mine, order))
    await refused(
        db_engine, table, "uq_chargeback_items_line", item_row("chargeback_id", mine, order)
    )


# ------------------------------------------------------------- existing tables (Q-1)


async def test_fk_order_items_order_owner_refuses_another_customers_line(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """VS-041 audit Q-1: a line's `user_id` is always its order's, on INSERT and UPDATE."""
    order = await paid_order(db_engine, db_session)
    stranger = await create_user(db_session)
    await db_session.commit()
    line = await _line_values(db_engine, order.line_ids[0])
    copy = line | {"id": uuid.uuid4(), "user_id": stranger.id}
    columns = ", ".join(copy)
    params = ", ".join(
        f"CAST(:{c} AS {_LINE_ENUMS[c]})" if c in _LINE_ENUMS else f":{c}" for c in copy
    )
    await assert_refused(
        db_engine,
        "fk_order_items_order_owner",
        f"INSERT INTO order_items ({columns}) VALUES ({params})",
        copy,
        drop=drop_constraint("order_items", "fk_order_items_order_owner"),
    )
    await assert_refused(
        db_engine,
        "fk_order_items_order_owner",
        "UPDATE order_items SET user_id = :u WHERE id = :i",
        {"u": stranger.id, "i": order.line_ids[0]},
        drop=drop_constraint("order_items", "fk_order_items_order_owner"),
    )


async def _line_values(engine: AsyncEngine, line_id: uuid.UUID) -> dict[str, Any]:
    """The line's own columns, enums as text so a copy can be re-inserted as is."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT order_id, user_id, product_id, product_type, product_name_snapshot,"
                    " unit_price_cents, quantity, line_total_cents, fulfillment_status,"
                    " payment_method, lead_time_days_snapshot, batch_size_snapshot"
                    " FROM order_items WHERE id = :i"
                ),
                {"i": line_id},
            )
        ).one()
    return dict(row._mapping)


async def test_the_owner_fk_is_validated_and_every_new_fk_restricts(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT conname, convalidated, confdeltype::text, confupdtype::text"
                    " FROM pg_constraint WHERE contype = 'f' AND (conname ="
                    " 'fk_order_items_order_owner' OR conrelid IN ('refunds'::regclass,"
                    " 'refund_items'::regclass, 'chargebacks'::regclass,"
                    " 'chargeback_items'::regclass))"
                )
            )
        ).all()
    by_name = {row.conname: row for row in rows}
    # refunds 7 (payment, reissue, five users), each item table 2, chargebacks 2, owner 1.
    assert len(by_name) == 14, sorted(by_name)
    assert all(row.convalidated for row in rows)
    assert all(row.confdeltype == "r" for row in rows), rows


@pytest.mark.parametrize(
    ("table", "key", "dependent"),
    [
        ("orders", "uq_orders_id_user", "fk_order_items_order_owner"),
        ("order_items", "uq_order_items_id_order", "fk_refund_items_order_item"),
        ("payments", "uq_payments_id_order_provider", "fk_refunds_payment"),
        ("refunds", "uq_refunds_id_order", "fk_refund_items_refund_id"),
        ("chargebacks", "uq_chargebacks_id_order", "fk_chargeback_items_chargeback_id"),
    ],
)
async def test_each_composite_key_is_what_its_foreign_key_stands_on(
    table: str, key: str, dependent: str, db_engine: AsyncEngine
) -> None:
    """These keys extend a primary key, so no row can violate them; their refusal is the
    FK's (tested above), and PostgreSQL will not drop one while that FK needs it."""
    async with db_engine.connect() as conn:
        outer = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            with pytest.raises(DBAPIError) as caught:
                async with conn.begin_nested():
                    await conn.execute(text(drop_constraint(table, key)))
        finally:
            await outer.rollback()
    # PostgreSQL names the dependent FK in DETAIL, which asyncpg exposes as `detail`.
    detail = getattr(getattr(caught.value.orig, "__cause__", None), "detail", None)
    assert isinstance(detail, str) and f"constraint {dependent} on table" in detail, detail


async def test_the_obligations_and_late_capture_indexes_match_the_plan(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as conn:
        defs: dict[str, str] = dict(
            (
                await conn.execute(
                    text(
                        "SELECT indexname, indexdef FROM pg_indexes WHERE indexname IN"
                        " ('ix_refunds_obligations', 'uq_refunds_one_live_late_capture')"
                    )
                )
            ).all()
        )
    obligations = defs["ix_refunds_obligations"]
    assert "(created_at, id)" in obligations
    assert "status = 'pending'" in obligations and "reissued_at IS NULL" in obligations
    live = defs["uq_refunds_one_live_late_capture"]
    assert live.startswith("CREATE UNIQUE INDEX") and "(payment_id)" in live
