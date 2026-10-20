"""VS-028 PR A (migration fcd589e89e59): every new constraint refuses its violation by
name, and the same row is accepted once that constraint is dropped in a rolled-back
transaction, so each test is shown to bite."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.identity.domain.enums import UserRole
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user
from tests.integration.ordering.test_order_payment_schema import (
    NOW,
    Ctx,
    Stmt,
    cash_delivery_order,
    ins,
    online_order,
    pickup_order,
    run,
)

pytestmark = pytest.mark.integration

HASH = "0123456789abcdef" * 4


@pytest_asyncio.fixture
async def ctx(db_session: AsyncSession) -> Ctx:
    user = await create_user(db_session)
    admin = await create_user(db_session, role=UserRole.ADMIN)
    refs = await seed_refs(db_session)
    physical = await seed_product(db_session, refs)
    stl = await seed_product(db_session, refs, type=ProductType.STL)
    return Ctx(user.id, admin.id, stl.id, physical.id)


def block(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    row = {
        "user_id": c.user_id,
        "contact_phone_hash": HASH,
        "order_id": oid,
        "reason": "refused",
    }
    return ins("cash_payment_blocks", row | over)


Build = Callable[[Ctx, uuid.UUID], tuple[list[Stmt], Stmt]]


@dataclass(frozen=True)
class Case:
    id: str
    table: str
    constraint: str
    sqlstate: str
    build: Build
    # What refuses the row once this constraint is dropped; None means it goes in.
    without: tuple[str, str] | None = None


CASES: list[Case] = [
    Case(
        "block-reason-other",
        "cash_payment_blocks",
        "ck_cash_payment_blocks_reason",
        "23514",
        lambda c, a: ([pickup_order(c, a)], block(c, a, reason="other")),
    ),
    Case(
        "block-marked-online",
        "cash_payment_blocks",
        "ck_cash_payment_blocks_cash_only",
        "23514",
        lambda c, a: ([pickup_order(c, a)], block(c, a, order_payment_method="online")),
        # Q4's second guard: no orders row has (id, 'online'), so the composite FK refuses.
        ("23503", "fk_cash_payment_blocks_order_payment_method"),
    ),
    Case(
        "block-cleared-without-admin",
        "cash_payment_blocks",
        "ck_cash_payment_blocks_cleared_pair",
        "23514",
        lambda c, a: ([pickup_order(c, a)], block(c, a, cleared_at=NOW)),
    ),
    Case(
        "block-admin-without-cleared",
        "cash_payment_blocks",
        "ck_cash_payment_blocks_cleared_pair",
        "23514",
        lambda c, a: ([pickup_order(c, a)], block(c, a, cleared_by=c.admin_id)),
    ),
    Case(
        "block-readable-phone",
        "cash_payment_blocks",
        "ck_cash_payment_blocks_hash_format",
        "23514",
        lambda c, a: ([pickup_order(c, a)], block(c, a, contact_phone_hash="+96170123456")),
    ),
    Case(
        "block-uppercase-hash",
        "cash_payment_blocks",
        "ck_cash_payment_blocks_hash_format",
        "23514",
        lambda c, a: ([pickup_order(c, a)], block(c, a, contact_phone_hash=HASH.upper())),
    ),
    # Q4: a block on an online order is refused by the composite FK, whatever it claims.
    Case(
        "block-on-online-order",
        "cash_payment_blocks",
        "fk_cash_payment_blocks_order_payment_method",
        "23503",
        lambda c, a: ([online_order(c, a)], block(c, a)),
    ),
    Case(
        "second-block-for-one-order",
        "cash_payment_blocks",
        "uq_cash_payment_blocks_order",
        "23505",
        lambda c, a: ([pickup_order(c, a), block(c, a)], block(c, a, reason="no_show")),
    ),
    Case(
        "order-phone-not-e164",
        "orders",
        "ck_orders_contact_phone_e164",
        "23514",
        lambda c, a: ([], pickup_order(c, a, contact_phone_snapshot="03 123 456")),
    ),
    Case(
        "order-phone-foreign",
        "orders",
        "ck_orders_contact_phone_e164",
        "23514",
        lambda c, a: ([], pickup_order(c, a, contact_phone_snapshot="+33612345678")),
    ),
    Case(
        "order-hash-not-hex",
        "orders",
        "ck_orders_phone_hash_format",
        "23514",
        lambda c, a: ([], cash_delivery_order(c, a, contact_phone_hash="hash")),
    ),
    Case(
        "order-hash-too-short",
        "orders",
        "ck_orders_phone_hash_format",
        "23514",
        lambda c, a: ([], pickup_order(c, a, contact_phone_hash="a" * 63)),
    ),
]
_IDS = [case.id for case in CASES]


@pytest.mark.parametrize("case", CASES, ids=_IDS)
async def test_the_constraint_refuses_the_row(db_engine: AsyncEngine, ctx: Ctx, case: Case) -> None:
    setup, probe = case.build(ctx, uuid.uuid4())
    assert await run(db_engine, setup, probe) == (case.sqlstate, case.constraint)


@pytest.mark.parametrize("case", CASES, ids=_IDS)
async def test_without_the_constraint_the_row_is_accepted(
    db_engine: AsyncEngine, ctx: Ctx, case: Case
) -> None:
    """The proof the refusal above is that constraint's: dropped (and rolled back) inside
    the same transaction, the identical row goes in, or meets the named backstop."""
    setup, probe = case.build(ctx, uuid.uuid4())
    drop: Stmt = (f"ALTER TABLE {case.table} DROP CONSTRAINT {case.constraint}", {})
    assert await run(db_engine, [drop, *setup], probe) == case.without


ACCEPTED: list[tuple[str, Build]] = [
    ("refused-block", lambda c, a: ([pickup_order(c, a)], block(c, a))),
    ("no-show-block", lambda c, a: ([pickup_order(c, a)], block(c, a, reason="no_show"))),
    (
        "cleared-block",
        lambda c, a: (
            [pickup_order(c, a)],
            block(c, a, cleared_at=NOW, cleared_by=c.admin_id),
        ),
    ),
    (
        "seven-digit-landline",
        lambda c, a: ([], pickup_order(c, a, contact_phone_snapshot="+9613123456")),
    ),
    ("digital-order-no-phone", lambda c, a: ([], online_order(c, a))),
]


@pytest.mark.parametrize(("name", "build"), ACCEPTED, ids=[name for name, _ in ACCEPTED])
async def test_the_database_accepts_the_row(
    db_engine: AsyncEngine, ctx: Ctx, name: str, build: Build
) -> None:
    setup, probe = build(ctx, uuid.uuid4())
    assert await run(db_engine, setup, probe) is None, name


async def test_a_block_defaults_to_cash_and_records_its_time(
    db_engine: AsyncEngine, ctx: Ctx
) -> None:
    oid = uuid.uuid4()
    async with db_engine.connect() as conn:
        try:
            for sql, params in (pickup_order(ctx, oid), block(ctx, oid)):
                await conn.execute(text(sql), params)
            row = (
                await conn.execute(
                    text(
                        "SELECT order_payment_method::text AS method, created_at "
                        "FROM cash_payment_blocks WHERE order_id = :o"
                    ),
                    {"o": oid},
                )
            ).one()
        finally:
            await conn.rollback()
    assert row.method == "cash"
    assert row.created_at is not None


async def test_the_partial_indexes_exist(db_engine: AsyncEngine) -> None:
    expected = {
        "ix_cash_payment_blocks_user_active": "cleared_at IS NULL",
        "ix_cash_payment_blocks_phone_active": "cleared_at IS NULL",
        "ix_orders_open_cash_phone": "payment_method = 'cash'",
    }
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE indexname = ANY(:n)"),
            {"n": list(expected)},
        )
        found = {row.indexname: row.indexdef for row in rows}
    assert set(found) == set(expected)
    for name, fragment in expected.items():
        assert fragment in found[name].replace("'cash'::payment_method", "'cash'"), name
    assert "in_progress" in found["ix_orders_open_cash_phone"]
