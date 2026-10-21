"""The database guarantees behind orders and payments (VS-023 plan 4, 4.10): every
constraint is hit with direct SQL, asserting the SQLSTATE and the constraint name."""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.catalog.domain.enums import ProductType
from app.identity.domain.enums import UserRole
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user

pytestmark = pytest.mark.integration

Stmt = tuple[str, dict[str, Any]]
_JSONB = {"payload", "response_body", "provider_metadata"}
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class Ctx:
    user_id: uuid.UUID
    admin_id: uuid.UUID
    stl_id: uuid.UUID
    physical_id: uuid.UUID


@pytest_asyncio.fixture
async def ctx(db_session: AsyncSession) -> Ctx:
    user = await create_user(db_session)
    admin = await create_user(db_session, role=UserRole.ADMIN)
    refs = await seed_refs(db_session)
    physical = await seed_product(db_session, refs)
    stl = await seed_product(db_session, refs, type=ProductType.STL)
    return Ctx(user.id, admin.id, stl.id, physical.id)


def ins(table: str, row: dict[str, Any]) -> Stmt:
    cols = ", ".join(row)
    vals = ", ".join(f"CAST(:{k} AS jsonb)" if k in _JSONB else f":{k}" for k in row)
    params = {k: json.dumps(v) if k in _JSONB and v is not None else v for k, v in row.items()}
    return f"INSERT INTO {table} ({cols}) VALUES ({vals})", params


def online_order(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    """A digital-only online order (the only kind VS-023 writes)."""
    row = {
        "id": oid,
        "order_number": f"B3D-{uuid.uuid4().hex[:8].upper()}",
        "user_id": c.user_id,
        "customer_email_snapshot": "buyer@example.com",
        "source": "cart",
        "status": "pending_payment",
        "payment_method": "online",
        "subtotal_cents": 1000,
        "total_cents": 1000,
        "terms_accepted_at": NOW,
        "digital_terms_accepted_at": NOW,
        "digital_terms_version": "2026-10",
        "placed_at": NOW,
    }
    return ins("orders", row | over)


def cash_delivery_order(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    """A VS-028 cash delivery order with every snapshot its CHECKs require."""
    row = {
        "id": oid,
        "order_number": f"B3D-{uuid.uuid4().hex[:8].upper()}",
        "user_id": c.user_id,
        "customer_email_snapshot": "buyer@example.com",
        "source": "cart",
        "status": "in_progress",
        "fulfillment_method": "delivery",
        "payment_method": "cash",
        "subtotal_cents": 2000,
        "total_cents": 2000,
        "recipient_name": "Rana",
        "contact_phone_snapshot": "+96170123456",
        "contact_phone_hash": "a" * 64,
        "governorate": "Bekaa",
        "city": "Zahle",
        "landmark_notes": "Blue gate",
        "terms_accepted_at": NOW,
        "cash_terms_accepted_at": NOW,
        "placed_at": NOW,
    }
    return ins("orders", row | over)


def pickup_order(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    row = {
        "id": oid,
        "order_number": f"B3D-{uuid.uuid4().hex[:8].upper()}",
        "user_id": c.user_id,
        "customer_email_snapshot": "buyer@example.com",
        "source": "cart",
        "status": "in_progress",
        "fulfillment_method": "pickup",
        "payment_method": "cash",
        "subtotal_cents": 2000,
        "total_cents": 2000,
        "contact_phone_snapshot": "+96170123456",
        "contact_phone_hash": "a" * 64,
        "terms_accepted_at": NOW,
        "cash_terms_accepted_at": NOW,
        "placed_at": NOW,
    }
    return ins("orders", row | over)


def stl_line(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    row = {
        "order_id": oid,
        "user_id": c.user_id,
        "product_id": c.stl_id,
        "product_type": "stl",
        "product_name_snapshot": "Dragon STL",
        "unit_price_cents": 1000,
        "quantity": 1,
        "line_total_cents": 1000,
        "fulfillment_status": "pending",
        "payment_method": "online",
    }
    return ins("order_items", row | over)


def physical_line(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    row = {
        "order_id": oid,
        "user_id": c.user_id,
        "product_id": c.physical_id,
        "product_type": "physical",
        "product_name_snapshot": "Lamp",
        "unit_price_cents": 1000,
        "quantity": 2,
        "line_total_cents": 2000,
        "fulfillment_status": "pending",
        "lead_time_days_snapshot": 3,
        "batch_size_snapshot": 2,
        "payment_method": "cash",
    }
    return ins("order_items", row | over)


def online_payment(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    row = {
        "order_id": oid,
        "provider": "mock",
        "order_payment_method": "online",
        "status": "pending",
        "amount_cents": 1000,
        "initiated_at": NOW,
    }
    return ins("payments", row | over)


def cash_payment(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    row = {
        "order_id": oid,
        "provider": "cash",
        "order_payment_method": "cash",
        "status": "paid",
        "amount_cents": 2000,
        "initiated_at": NOW,
        "verified_at": NOW,
        "recorded_by": c.admin_id,
    }
    return ins("payments", row | over)


def paid_capture(c: Ctx, oid: uuid.UUID, **over: Any) -> Stmt:
    """A verified online payment that records what the provider captured (VS-024)."""
    row = {"status": "paid", "verified_at": NOW, "captured_amount_cents": 1000}
    return online_payment(c, oid, **({"captured_currency": "USD"} | row | over))


def webhook(**over: Any) -> Stmt:
    row = {"provider": "mock", "provider_event_id": f"evt-{uuid.uuid4().hex}", "payload": {}}
    return ins("webhook_events", row | over)


def claim(c: Ctx, **over: Any) -> Stmt:
    row = {
        "user_id": c.user_id,
        "scope": "checkout",
        "key": f"key-{uuid.uuid4().hex}",
        "request_hash": "b" * 64,
        "state": "in_progress",
        "expires_at": NOW,
    }
    return ins("idempotency_records", row | over)


async def run(engine: AsyncEngine, setup: list[Stmt], probe: Stmt) -> tuple[str, str] | None:
    """Setup then probe in one rolled-back transaction: (SQLSTATE, constraint) or None."""
    async with engine.connect() as conn:
        try:
            for sql, params in setup:
                await conn.execute(text(sql), params)
            try:
                await conn.execute(text(probe[0]), probe[1])
            except DBAPIError as exc:
                cause = getattr(exc.orig, "__cause__", None)
                return (
                    str(getattr(exc.orig, "sqlstate", None)),
                    str(getattr(cause, "constraint_name", None)),
                )
            return None
        finally:
            await conn.rollback()


Build = Callable[[Ctx, uuid.UUID, uuid.UUID], tuple[list[Stmt], Stmt]]


@dataclass(frozen=True)
class Case:
    id: str
    build: Build
    sqlstate: str
    constraint: str


def _c(id_: str, constraint: str, build: Build, sqlstate: str = "23514") -> Case:
    return Case(id_, build, sqlstate, constraint)


# `a` and `b` are fresh order ids for each case.
REFUSALS: list[Case] = [
    # orders
    _c(
        "negative-money",
        "ck_orders_money_non_negative",
        lambda c, a, b: ([], online_order(c, a, subtotal_cents=-1, total_cents=-1)),
    ),
    _c(
        "tax-not-zero",
        "ck_orders_tax_zero",
        lambda c, a, b: ([], online_order(c, a, tax_cents=5, total_cents=1005)),
    ),
    _c(
        "total-mismatch",
        "ck_orders_total_arithmetic",
        lambda c, a, b: ([], online_order(c, a, total_cents=999)),
    ),
    _c(
        "eur-order",
        "ck_orders_currency_usd",
        lambda c, a, b: ([], online_order(c, a, currency="EUR")),
    ),
    _c(
        "pickup-without-phone",
        "ck_orders_physical_has_phone",
        lambda c, a, b: (
            [],
            pickup_order(c, a, contact_phone_snapshot=None, contact_phone_hash=None),
        ),
    ),
    _c(
        "digital-only-cash",
        "ck_orders_digital_only_online",
        lambda c, a, b: ([], online_order(c, a, payment_method="cash", cash_terms_accepted_at=NOW)),
    ),
    _c(
        "cash-without-terms",
        "ck_orders_cash_terms",
        lambda c, a, b: ([], cash_delivery_order(c, a, cash_terms_accepted_at=None)),
    ),
    _c(
        "delivery-without-city",
        "ck_orders_delivery_address",
        lambda c, a, b: ([], cash_delivery_order(c, a, city=None)),
    ),
    _c(
        "phone-without-hash",
        "ck_orders_phone_hash_pair",
        lambda c, a, b: ([], pickup_order(c, a, contact_phone_hash=None)),
    ),
    _c(
        "digital-terms-without-version",
        "ck_orders_digital_terms_version",
        lambda c, a, b: ([], online_order(c, a, digital_terms_version=None)),
    ),
    _c(
        "digital-version-without-terms",
        "ck_orders_digital_terms_version",
        lambda c, a, b: ([], online_order(c, a, digital_terms_accepted_at=None)),
    ),
    _c(
        "duplicate-order-number",
        "uq_orders_order_number",
        lambda c, a, b: (
            [online_order(c, a, order_number="B3D-DUPLICATE")],
            online_order(c, b, order_number="B3D-DUPLICATE"),
        ),
        "23505",
    ),
    # order_items
    _c(
        "cash-line-on-online-order",
        "fk_order_items_order_payment_method",
        lambda c, a, b: ([online_order(c, a)], physical_line(c, a, payment_method="cash")),
        "23503",
    ),
    _c(
        "line-type-snapshot-wrong",
        "fk_order_items_product_type",
        lambda c, a, b: ([online_order(c, a)], stl_line(c, a, product_id=c.physical_id)),
        "23503",
    ),
    _c(
        "line-total-mismatch",
        "ck_order_items_money",
        lambda c, a, b: ([online_order(c, a)], stl_line(c, a, line_total_cents=999)),
    ),
    _c(
        "line-quantity-zero",
        "ck_order_items_money",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            physical_line(c, a, quantity=0, line_total_cents=0),
        ),
    ),
    _c(
        "stl-quantity-two",
        "ck_order_items_stl_quantity_one",
        lambda c, a, b: (
            [online_order(c, a)],
            stl_line(c, a, quantity=2, line_total_cents=2000),
        ),
    ),
    _c(
        "stl-line-on-cash-order",
        "ck_order_items_cash_is_physical",
        lambda c, a, b: ([cash_delivery_order(c, a)], stl_line(c, a, payment_method="cash")),
    ),
    _c(
        "cancel-reason-on-pending-line",
        "ck_order_items_cancel_reason_state",
        lambda c, a, b: ([cash_delivery_order(c, a)], physical_line(c, a, cancel_reason="refused")),
    ),
    _c(
        "physical-without-lead-time",
        "ck_order_items_snapshots_by_type",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            physical_line(c, a, lead_time_days_snapshot=None),
        ),
    ),
    _c(
        "physical-batch-zero",
        "ck_order_items_snapshots_by_type",
        lambda c, a, b: ([cash_delivery_order(c, a)], physical_line(c, a, batch_size_snapshot=0)),
    ),
    _c(
        "stl-with-batch-size",
        "ck_order_items_snapshots_by_type",
        lambda c, a, b: ([online_order(c, a)], stl_line(c, a, batch_size_snapshot=2)),
    ),
    _c(
        "stl-delivered-without-admin",
        "ck_order_items_stl_delivery_record",
        lambda c, a, b: (
            [online_order(c, a)],
            stl_line(c, a, fulfillment_status="delivered", fulfilled_at=NOW),
        ),
    ),
    _c(
        "physical-with-delivered-by",
        "ck_order_items_physical_no_delivered_by",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            physical_line(c, a, fulfillment_status="delivered", delivered_by=c.admin_id),
        ),
    ),
    _c(
        "physical-awaiting-delivery",
        "ck_order_items_status_by_type",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            physical_line(c, a, fulfillment_status="awaiting_delivery"),
        ),
    ),
    _c(
        "stl-shipped",
        "ck_order_items_status_by_type",
        lambda c, a, b: ([online_order(c, a)], stl_line(c, a, fulfillment_status="shipped")),
    ),
    _c(
        "second-live-stl-line",
        "uq_order_items_stl_ownership",
        lambda c, a, b: (
            [online_order(c, a), stl_line(c, a), online_order(c, b)],
            stl_line(c, b),
        ),
        "23505",
    ),
    # payments
    _c(
        "cash-payment-on-online-order",
        "ck_payments_cash_iff_cash_order",
        lambda c, a, b: (
            [online_order(c, a)],
            cash_payment(c, a, order_payment_method="online", amount_cents=1000),
        ),
    ),
    _c(
        "cash-payment-claims-cash-on-online-order",
        "fk_payments_order_payment_method",
        lambda c, a, b: ([online_order(c, a)], cash_payment(c, a)),
        "23503",
    ),
    _c(
        "online-payment-on-cash-order",
        "ck_payments_cash_iff_cash_order",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            online_payment(c, a, order_payment_method="cash"),
        ),
    ),
    _c(
        "second-cash-payment",
        "uq_payments_one_cash",
        lambda c, a, b: ([cash_delivery_order(c, a), cash_payment(c, a)], cash_payment(c, a)),
        "23505",
    ),
    _c(
        "second-live-payment",
        "uq_payments_one_live",
        lambda c, a, b: ([online_order(c, a), online_payment(c, a)], online_payment(c, a)),
        "23505",
    ),
    _c(
        "duplicate-provider-reference",
        "uq_payments_provider_reference",
        lambda c, a, b: (
            [
                online_order(c, a),
                online_payment(c, a, provider_payment_id="mock_1"),
                online_order(c, b),
            ],
            online_payment(c, b, provider_payment_id="mock_1"),
        ),
        "23505",
    ),
    _c(
        "negative-payment",
        "ck_payments_amount_currency",
        lambda c, a, b: ([online_order(c, a)], online_payment(c, a, amount_cents=-1)),
    ),
    _c(
        "cash-payment-pending",
        "ck_payments_cash_shape",
        lambda c, a, b: ([cash_delivery_order(c, a)], cash_payment(c, a, status="pending")),
    ),
    _c(
        "cash-payment-without-recorder",
        "ck_payments_cash_shape",
        lambda c, a, b: ([cash_delivery_order(c, a)], cash_payment(c, a, recorded_by=None)),
    ),
    _c(
        "cash-payment-without-verified-at",
        "ck_payments_cash_shape",
        lambda c, a, b: ([cash_delivery_order(c, a)], cash_payment(c, a, verified_at=None)),
    ),
    _c(
        "cash-payment-zero",
        "ck_payments_cash_shape",
        lambda c, a, b: ([cash_delivery_order(c, a)], cash_payment(c, a, amount_cents=0)),
    ),
    _c(
        "late-capture-on-paid",
        "ck_payments_late_capture",
        lambda c, a, b: (
            [online_order(c, a)],
            online_payment(c, a, status="paid", verified_at=NOW, late_captured_at=NOW),
        ),
    ),
    _c(
        "late-capture-on-cash",
        "ck_payments_late_capture",
        lambda c, a, b: ([cash_delivery_order(c, a)], cash_payment(c, a, late_captured_at=NOW)),
    ),
    _c(
        "online-payment-with-recorder",
        "ck_payments_online_not_recorded",
        lambda c, a, b: ([online_order(c, a)], online_payment(c, a, recorded_by=c.admin_id)),
    ),
    _c(
        "paid-without-verified-at",
        "ck_payments_paid_verified",
        lambda c, a, b: ([online_order(c, a)], online_payment(c, a, status="paid")),
    ),
    _c(
        "failed-without-failed-at",
        "ck_payments_terminal_timestamps",
        lambda c, a, b: ([online_order(c, a)], online_payment(c, a, status="failed")),
    ),
    _c(
        "expired-without-expired-at",
        "ck_payments_terminal_timestamps",
        lambda c, a, b: ([online_order(c, a)], online_payment(c, a, status="expired")),
    ),
    # payments.captured_* (VS-024, migration 00ce1ce252a6); each row breaks one CHECK only
    _c(
        "captured-amount-negative",
        "ck_payments_captured_shape",
        lambda c, a, b: ([online_order(c, a)], paid_capture(c, a, captured_amount_cents=-1)),
    ),
    _c(
        "captured-currency-lowercase",
        "ck_payments_captured_shape",
        lambda c, a, b: ([online_order(c, a)], paid_capture(c, a, captured_currency="usd")),
    ),
    _c(
        "captured-currency-without-amount",
        "ck_payments_captured_shape",
        lambda c, a, b: ([online_order(c, a)], paid_capture(c, a, captured_amount_cents=None)),
    ),
    _c(
        "captured-on-a-pending-attempt",
        "ck_payments_captured_when",
        lambda c, a, b: (
            [online_order(c, a)],
            online_payment(c, a, captured_amount_cents=1000, captured_currency="USD"),
        ),
    ),
    _c(
        "captured-on-a-failed-attempt-without-late-capture",
        "ck_payments_captured_when",
        lambda c, a, b: (
            [online_order(c, a)],
            online_payment(
                c,
                a,
                status="failed",
                failed_at=NOW,
                captured_amount_cents=1000,
                captured_currency="USD",
            ),
        ),
    ),
    _c(
        "captured-on-a-cash-payment",
        "ck_payments_captured_when",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            cash_payment(c, a, captured_amount_cents=2000, captured_currency="USD"),
        ),
    ),
    # webhook_events
    _c(
        "duplicate-webhook-event",
        "uq_webhook_events_provider_event",
        lambda c, a, b: (
            [webhook(provider_event_id="evt-dup")],
            webhook(provider_event_id="evt-dup"),
        ),
        "23505",
    ),
    _c(
        "oversized-webhook-payload",
        "ck_webhook_events_payload_size",
        lambda c, a, b: ([], webhook(payload={"blob": "x" * 70_000})),
    ),
    # idempotency_records
    _c(
        "duplicate-claim",
        "uq_idempotency_records_scope_user_key",
        lambda c, a, b: ([claim(c, key="k-dup")], claim(c, key="k-dup")),
        "23505",
    ),
    _c(
        "duplicate-claim-null-user",
        "uq_idempotency_records_scope_user_key",
        lambda c, a, b: (
            [claim(c, user_id=None, key="k-null")],
            claim(c, user_id=None, key="k-null"),
        ),
        "23505",
    ),
    _c("empty-key", "ck_idempotency_records_key_length", lambda c, a, b: ([], claim(c, key=""))),
    _c(
        "unknown-state",
        "ck_idempotency_records_state",
        lambda c, a, b: ([], claim(c, state="started")),
    ),
    _c(
        "done-without-response",
        "ck_idempotency_records_done_has_response",
        lambda c, a, b: ([], claim(c, state="done")),
    ),
    _c(
        "in-progress-with-response",
        "ck_idempotency_records_done_has_response",
        lambda c, a, b: ([], claim(c, status_code=201, response_body={"ok": True})),
    ),
    _c(
        "status-code-out-of-range",
        "ck_idempotency_records_status_code",
        lambda c, a, b: ([], claim(c, state="done", status_code=700, response_body={})),
    ),
]


@pytest.mark.parametrize("case", REFUSALS, ids=[case.id for case in REFUSALS])
async def test_the_database_refuses_the_row(db_engine: AsyncEngine, ctx: Ctx, case: Case) -> None:
    setup, probe = case.build(ctx, uuid.uuid4(), uuid.uuid4())
    assert await run(db_engine, setup, probe) == (case.sqlstate, case.constraint)


ACCEPTED: list[tuple[str, Build]] = [
    (
        "online-stl-order-line-and-pending-payment",
        lambda c, a, b: ([online_order(c, a), stl_line(c, a)], online_payment(c, a)),
    ),
    (
        "cash-delivery-order-physical-line-and-cash-payment",
        lambda c, a, b: ([cash_delivery_order(c, a), physical_line(c, a)], cash_payment(c, a)),
    ),
    ("pickup-order-with-phone-and-hash", lambda c, a, b: ([], pickup_order(c, a))),
    (
        "online-order-without-digital-terms",
        lambda c, a, b: (
            [],
            online_order(c, a, digital_terms_accepted_at=None, digital_terms_version=None),
        ),
    ),
    (
        "cancel-reason-on-cancelled-line",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            physical_line(c, a, fulfillment_status="cancelled", cancel_reason="refused"),
        ),
    ),
    (
        "stl-delivered-with-record",
        lambda c, a, b: (
            [online_order(c, a)],
            stl_line(
                c, a, fulfillment_status="delivered", fulfilled_at=NOW, delivered_by=c.admin_id
            ),
        ),
    ),
    (
        "physical-delivered-without-delivered-by",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            physical_line(c, a, fulfillment_status="delivered"),
        ),
    ),
    (
        "physical-in-production",
        lambda c, a, b: (
            [cash_delivery_order(c, a)],
            physical_line(c, a, fulfillment_status="in_production"),
        ),
    ),
    (
        "stl-line-again-after-the-first-was-cancelled",
        lambda c, a, b: (
            [
                online_order(c, a),
                stl_line(c, a, fulfillment_status="cancelled"),
                online_order(c, b),
            ],
            stl_line(c, b),
        ),
    ),
    (
        "new-attempt-after-a-failed-one",
        lambda c, a, b: (
            [online_order(c, a), online_payment(c, a, status="failed", failed_at=NOW)],
            online_payment(c, a),
        ),
    ),
    (
        "late-capture-on-a-failed-attempt",
        lambda c, a, b: (
            [online_order(c, a)],
            online_payment(c, a, status="failed", failed_at=NOW, late_captured_at=NOW),
        ),
    ),
    (
        "paid-online-payment-with-verified-at",
        lambda c, a, b: (
            [online_order(c, a)],
            online_payment(c, a, status="paid", verified_at=NOW),
        ),
    ),
    (
        "captured-amount-on-a-paid-attempt",
        lambda c, a, b: ([online_order(c, a)], paid_capture(c, a)),
    ),
    (
        "captured-overpayment-in-another-currency-on-a-late-capture",
        lambda c, a, b: (
            [online_order(c, a)],
            online_payment(
                c,
                a,
                status="failed",
                failed_at=NOW,
                late_captured_at=NOW,
                captured_amount_cents=1500,
                captured_currency="EUR",
            ),
        ),
    ),
    (
        "captured-amount-without-currency-on-an-expired-late-capture",
        lambda c, a, b: (
            [online_order(c, a)],
            online_payment(
                c,
                a,
                status="expired",
                expired_at=NOW,
                late_captured_at=NOW,
                captured_amount_cents=900,
            ),
        ),
    ),
    (
        "cash-payment-without-captured-columns",
        lambda c, a, b: ([cash_delivery_order(c, a)], cash_payment(c, a)),
    ),
    (
        "webhook-linked-to-a-payment",
        lambda c, a, b: (
            [online_order(c, a), online_payment(c, a, id=b, provider_payment_id="mock_9")],
            webhook(provider_payment_id="mock_9", payment_id=b),
        ),
    ),
    ("claim-in-progress", lambda c, a, b: ([], claim(c, resource_id=a))),
    (
        "claim-done",
        lambda c, a, b: ([], claim(c, state="done", status_code=201, response_body={"ok": True})),
    ),
    (
        "same-key-for-another-user",
        lambda c, a, b: ([claim(c, key="k-shared")], claim(c, key="k-shared", user_id=c.admin_id)),
    ),
    (
        "status-history-row",
        lambda c, a, b: (
            [online_order(c, a)],
            ins(
                "order_status_history",
                {"order_id": a, "from_status": None, "to_status": "pending_payment"},
            ),
        ),
    ),
]


@pytest.mark.parametrize(("name", "build"), ACCEPTED, ids=[name for name, _ in ACCEPTED])
async def test_the_database_accepts_the_row(
    db_engine: AsyncEngine, ctx: Ctx, name: str, build: Build
) -> None:
    setup, probe = build(ctx, uuid.uuid4(), uuid.uuid4())
    assert await run(db_engine, setup, probe) is None, name


_NON_UNIQUE_INDEXES = {
    "ix_orders_user_placed": "orders",
    "ix_orders_status_placed": "orders",
    "ix_order_items_order_id": "order_items",
    "ix_order_items_physical_status": "order_items",
    "ix_order_items_stl_awaiting": "order_items",
    "ix_order_status_history_order": "order_status_history",
    "ix_payments_order": "payments",
    "ix_payments_unsettled": "payments",
    "ix_payments_late_captured": "payments",
    "ix_webhook_events_unprocessed": "webhook_events",
    "ix_webhook_events_payment_unprocessed": "webhook_events",
    "ix_idempotency_records_expires_at": "idempotency_records",
}


async def test_every_lookup_index_exists(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT indexname, tablename FROM pg_indexes WHERE indexname = ANY(:names)"),
            {"names": list(_NON_UNIQUE_INDEXES)},
        )
        assert {row.indexname: row.tablename for row in rows} == _NON_UNIQUE_INDEXES


async def test_the_stl_delivery_queue_index_is_partial_on_created_at_and_id(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as conn:
        definition = await conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_order_items_stl_awaiting'")
        )
        others = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_indexes WHERE tablename = 'order_items' "
                "AND indexdef LIKE '%awaiting_delivery%' AND indexname NOT IN "
                "('uq_order_items_stl_ownership', 'ix_order_items_stl_awaiting')"
            )
        )
    assert definition is not None
    assert "UNIQUE" not in definition
    assert "(created_at, id)" in definition
    assert "product_type = 'stl'" in definition
    assert "fulfillment_status = 'awaiting_delivery'" in definition
    assert others == 0


async def test_the_obsolete_daily_download_cap_setting_is_gone(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        found = await conn.scalar(
            text("SELECT count(*) FROM settings WHERE key = 'daily_download_cap'")
        )
    assert found == 0


async def test_a_never_verified_user_without_orders_is_purged(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The purge is a plain DELETE (identity repositories, purge_never_verified_before)."""
    user = await create_user(db_session, verified=False)
    c = Ctx(user.id, user.id, uuid.uuid4(), uuid.uuid4())
    setup = [claim(c), ("INSERT INTO carts (user_id) VALUES (:u)", {"u": user.id})]
    async with db_engine.connect() as conn:
        try:
            for sql, params in setup:
                await conn.execute(text(sql), params)
            await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user.id})
            left = await conn.scalar(
                text("SELECT count(*) FROM idempotency_records WHERE user_id = :u"), {"u": user.id}
            )
            assert left == 0
        finally:
            await conn.rollback()


async def test_deleting_a_user_who_owns_an_order_is_refused(
    db_engine: AsyncEngine, ctx: Ctx
) -> None:
    probe = ("DELETE FROM users WHERE id = :u", {"u": ctx.user_id})
    order = online_order(ctx, uuid.uuid4())
    assert await run(db_engine, [order], probe) == ("23503", "orders_user_id_fkey")


async def test_deleting_an_acting_user_keeps_the_history_row(
    db_engine: AsyncEngine, db_session: AsyncSession, ctx: Ctx
) -> None:
    """`actor_user_id` is SET NULL: the row survives and reads as a system change."""
    actor = await create_user(db_session, verified=False)
    oid = uuid.uuid4()
    row = {"order_id": oid, "to_status": "pending_payment", "actor_user_id": actor.id}
    async with db_engine.connect() as conn:
        try:
            for sql, params in [online_order(ctx, oid), ins("order_status_history", row)]:
                await conn.execute(text(sql), params)
            await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": actor.id})
            actors = await conn.execute(
                text("SELECT actor_user_id FROM order_status_history WHERE order_id = :o"),
                {"o": oid},
            )
            assert actors.scalars().all() == [None]
        finally:
            await conn.rollback()
