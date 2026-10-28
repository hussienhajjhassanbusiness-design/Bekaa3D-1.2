"""VS-044 `GET /api/v1/me/export` over HTTP on real PostgreSQL: the six data sets, only the
caller's rows, no internal value, soft-deleted rows marked, 3 a day, audited (ADR-046)."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from app.reporting.api.export_schemas import DataExportRead
from app.reporting.application.data_export import ORDER_PAGE_SIZE
from app.reporting.domain.data_export import SECTIONS
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user, login
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.reporting.export_support import (
    EXPORT,
    export,
    refund_settle_and_void,
    seed_customer,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _export_as(email: str) -> tuple[dict[str, Any], str]:
    with client_for(main_app) as client:
        login(client, email)
        response = export(client)
    assert response.status_code == 200, response.text
    return response.json(), response.text


def _ids(doc: dict[str, Any]) -> set[str]:
    found = {r["id"] for key in ("addresses", "orders", "reviews", "offers") for r in doc[key]}
    return found | {line["id"] for order in doc["orders"] for line in order["lines"]}


async def test_the_export_is_the_profile_and_exactly_the_six_sets(
    db_session: AsyncSession,
) -> None:
    s = await seed_customer(db_session, "six")
    doc, raw = _export_as(s.email)
    assert list(doc) == ["format_version", "exported_at", "profile", *SECTIONS]
    DataExportRead.model_validate_json(raw)
    assert doc["profile"]["id"] == str(s.user_id) and doc["profile"]["email"] == s.email
    counts = {k: len(doc[k]) for k in SECTIONS}
    assert counts == {"addresses": 2, "orders": 2, "reviews": 2, "offers": 1, "contact_messages": 1}
    assert s.ids <= _ids(doc)


async def test_only_the_callers_rows_appear_in_either_direction(
    db_session: AsyncSession,
) -> None:
    a, b = await seed_customer(db_session, "alpha"), await seed_customer(db_session, "bravo")
    for me, other in ((a, b), (b, a)):
        doc, raw = _export_as(me.email)
        assert _ids(doc) == me.ids
        assert {x for x in other.ids | other.own_text | other.sentinels if x in raw} == set()
        assert other.email not in raw and str(other.user_id) not in raw
        assert [m["message"] for m in doc["contact_messages"]] == [
            t for t in me.own_text if t.startswith("My parcel")
        ]


async def test_no_hash_secret_internal_note_or_provider_reference_is_exported(
    db_session: AsyncSession,
) -> None:
    s = await seed_customer(db_session, "leak")
    s.sentinels |= await refund_settle_and_void(db_session, s.paid_order, s.physical_line, "leak")
    _, raw = _export_as(s.email)
    leaked = {value for value in s.sentinels if value and value in raw}
    assert leaked == set()
    assert all(text_ in raw for text_ in s.own_text)  # the customer's own words are kept


@pytest.mark.parametrize("section", ["addresses", "reviews"])
async def test_soft_deleted_rows_are_exported_and_marked(
    db_session: AsyncSession, section: str
) -> None:
    s = await seed_customer(db_session, f"del-{section}")
    doc, _ = _export_as(s.email)
    marks = sorted((row["deleted"], row["deleted_at"] is not None) for row in doc[section])
    assert marks == [(False, False), (True, True)]


async def test_orders_carry_payment_method_payment_refunds_and_stl_delivery(
    db_session: AsyncSession,
) -> None:
    s = await seed_customer(db_session, "money")
    await refund_settle_and_void(db_session, s.paid_order, s.physical_line, "money")
    doc, _ = _export_as(s.email)
    orders = {o["id"]: o for o in doc["orders"]}
    paid, cash = orders[str(s.paid_order)], orders[str(s.cash_order)]
    assert (paid["payment_method"], paid["payment_due"], paid["amount_due"]) == (
        "online",
        False,
        None,
    )
    assert paid["payment"] == {
        "provider": "mock",
        "status": "partially_refunded",
        "amount": {"amount_cents": 1500, "currency": "USD"},
    }
    assert paid["refunds"] == [
        {
            "kind": "admin",
            "status": "refunded",
            "amount": {"amount_cents": 300, "currency": "USD"},
            "created_at": paid["refunds"][0]["created_at"],
        }
    ]  # the voided refund is never shown (VS-030 Q9)
    stl = next(line for line in paid["lines"] if line["id"] == str(s.stl_line))
    assert stl["product_type"] == "stl" and stl["fulfillment_status"] == "delivered"
    assert stl["fulfilled_at"] is not None and paid["delivery_email"] == s.email
    assert paid["status_history"] and "reason" not in paid["status_history"][0]
    assert (cash["payment_method"], cash["payment_due"], cash["payment"]) == ("cash", True, None)
    assert cash["amount_due"] == {"amount_cents": 1000, "currency": "USD"}
    assert cash["delivery_email"] is None  # no STL line, nothing was emailed


async def test_a_whatsapp_only_products_badge_is_masked(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    product = (await seed_product(db_session, await seed_refs(db_session))).id
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE products SET purchase_mode = 'whatsapp_only' WHERE id = :p"),
            {"p": product},
        )
        await conn.execute(
            text(
                "INSERT INTO reviews (user_id, product_id, rating, is_verified_purchase)"
                " VALUES (:u, :p, 5, true)"
            ),
            {"u": user.id, "p": product},
        )
    doc, _ = _export_as(user.email)
    assert [r["is_verified_purchase"] for r in doc["reviews"]] == [False]


async def test_offers_carry_their_rounds_in_sequence(db_session: AsyncSession) -> None:
    s = await seed_customer(db_session, "offer")
    doc, _ = _export_as(s.email)
    (offer,) = doc["offers"]
    assert offer["status"] == "rejected" and offer["cooldown_until"] is not None
    assert [(r["sequence"], r["actor"], r["message"]) for r in offer["rounds"]] == [
        (1, "customer", None),
        (2, "admin", "Too low, sorry offer"),
    ]


async def test_contact_messages_hold_only_what_the_customer_wrote(
    db_session: AsyncSession,
) -> None:
    s = await seed_customer(db_session, "contact")
    doc, _ = _export_as(s.email)
    (message,) = doc["contact_messages"]
    assert set(message) == {"subject", "message", "created_at"}
    assert message["subject"] == "Problem with my order"


async def test_anonymous_is_401_and_unverified_is_403_spending_no_budget(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        assert_problem(client.get(EXPORT), 401)
    user = await create_user(db_session, verified=False)
    with client_for(main_app) as client:
        login(client, user.email)
        for _ in range(4):
            assert_problem(export(client), 403, "EMAIL_VERIFICATION_REQUIRED")
    await db_session.execute(
        text("UPDATE users SET email_verified_at = now() WHERE id = :u"), {"u": user.id}
    )
    await db_session.commit()
    with client_for(main_app) as client:
        login(client, user.email)
        assert export(client).status_code == 200  # the refused calls spent none of the three


async def test_a_disabled_account_is_401(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        await db_session.execute(
            text("UPDATE users SET is_active = false WHERE id = :u"), {"u": user.id}
        )
        await db_session.commit()
        assert_problem(export(client), 401)


async def test_three_a_day_per_user_then_429_with_retry_after(
    db_session: AsyncSession,
) -> None:
    first, second = await create_user(db_session), await create_user(db_session)
    with client_for(main_app) as client:
        login(client, first.email)
        responses = [export(client) for _ in range(3)]
        assert [r.status_code for r in responses] == [200, 200, 200]
        assert [r.headers["RateLimit-Remaining"] for r in responses] == ["2", "1", "0"]
        assert int(responses[0].headers["RateLimit-Reset"]) > 86_000
        refused = export(client)
        assert_problem(refused, 429, "RATE_LIMITED")
        assert int(refused.headers["Retry-After"]) > 86_000
    with client_for(main_app) as client:
        login(client, second.email)
        assert export(client).status_code == 200  # another user's budget is untouched


async def test_each_export_writes_one_audit_row_with_no_data(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    s = await seed_customer(db_session, "audit")
    _export_as(s.email)
    async with db_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT actor_user_id, entity_type, entity_id, after_data, ip_hash"
                    " FROM audit_logs WHERE action = 'user.data_exported' AND entity_id = :u"
                ),
                {"u": s.user_id},
            )
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert (row.actor_user_id, row.entity_type, row.entity_id) == (s.user_id, "user", s.user_id)
    assert row.after_data == {"format_version": 1} and row.ip_hash is not None


async def test_the_response_is_a_no_store_attachment(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        response = export(client)
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="bekaa3d-data-export-')
    assert json.loads(response.text)["orders"] == []


async def test_an_in_production_line_reads_pending_and_its_step_is_hidden(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    order = await seed_physical_order(
        db_session,
        user_id=user.id,
        payment_method="online",
        payment_status="paid",
        line_states=("in_production",),
    )
    await db_session.execute(
        text(
            "INSERT INTO order_status_history (order_id, order_item_id, from_status, to_status)"
            " VALUES (:o, :i, 'pending', 'in_production')"
        ),
        {"o": order.order_id, "i": order.line_ids[0]},
    )
    await db_session.commit()
    doc, raw = _export_as(user.email)
    (exported,) = doc["orders"]
    assert [line["fulfillment_status"] for line in exported["lines"]] == ["pending"]
    assert exported["status_history"] == [] and "in_production" not in raw


async def test_each_order_matches_its_order_page(db_session: AsyncSession) -> None:
    """The export is the VS-025 projection: every field both show is equal (ADR-046 d3)."""
    s = await seed_customer(db_session, "parity")
    await refund_settle_and_void(db_session, s.paid_order, s.physical_line, "parity")
    cash = await seed_physical_order(
        db_session, user_id=s.user_id, line_states=("pending", "cancelled")
    )
    unpaid = await seed_physical_order(
        db_session,
        user_id=s.user_id,
        payment_method="online",
        payment_status="expired",
        order_status="cancelled",
        line_states=("cancelled",),
        stl_line="cancelled",
        email=s.email,
    )
    with client_for(main_app) as client:
        login(client, s.email)
        doc = export(client).json()
        pages = {o["id"]: client.get(f"/api/v1/me/orders/{o['id']}").json() for o in doc["orders"]}
    for exported in doc["orders"]:
        page = pages[exported["id"]]
        shared = (set(exported) & set(page)) - {"lines"}
        assert shared >= {"payment_due", "amount_due", "payment", "refunds", "status_history"}
        assert {k: exported[k] for k in shared} == {k: page[k] for k in shared}, exported["id"]
        for mine, shown in zip(exported["lines"], page["lines"], strict=True):
            common = set(mine) & set(shown)
            assert {k: mine[k] for k in common} == {k: shown[k] for k in common}
    by_id = {o["id"]: o for o in doc["orders"]}
    assert by_id[str(cash.order_id)]["amount_due"] == {"amount_cents": 1000, "currency": "USD"}
    assert by_id[str(cash.order_id)]["total"]["amount_cents"] == 2000
    assert by_id[str(unpaid.order_id)]["delivery_email"] is None  # nothing was ever emailed
    assert by_id[str(s.paid_order)]["delivery_email"] == s.email


async def test_more_than_a_page_of_orders_exports_each_once_in_order(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    seeded = []
    for n in range(ORDER_PAGE_SIZE + 2):
        moment = start + timedelta(minutes=min(n, ORDER_PAGE_SIZE - 1))  # 49 and 50 tie
        order = await seed_physical_order(db_session, user_id=user.id, placed_at=moment)
        seeded.append((moment, str(order.order_id)))
    doc, _ = _export_as(user.email)
    exported = [o["id"] for o in doc["orders"]]
    assert exported == [oid for _, oid in sorted(seeded, key=lambda m: (m[0], uuid.UUID(m[1])))]
