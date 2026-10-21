"""`GET /api/v1/me/orders` and `/{order_id}` (VS-025): ownership in SQL, fixed customer
schemas, snapshots, masking, flags and stable pages. Orders are seeded with SQL, so the
physical and cash shapes VS-028 will write can be read here already."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.domain.enums import ProductType
from app.main import app as main_app
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import Refs, seed_product, seed_refs
from tests.integration.deep_support import assert_problem, client_for, create_user, login
from tests.integration.ordering.checkout_support import (  # noqa: F401
    buyer,
    post_checkout,
    shop_open,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

ORDERS = "/api/v1/me/orders"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
ADMIN_NOTE = "ADMIN-NOTE-SENTINEL"
# A valid phone hash (ck_orders_phone_hash_format, VS-028) that must still never be shown.
HASH_SENTINEL = "ab" * 32
SECRETS = (ADMIN_NOTE, "mock_REFERENCE_SENTINEL", HASH_SENTINEL, "REASON-SENTINEL")

SUMMARY_KEYS = {
    "id",
    "order_number",
    "status",
    "payment_method",
    "fulfillment_method",
    "payment_due",
    "total",
    "placed_at",
}
DETAIL_KEYS = {
    "id",
    "order_number",
    "source",
    "status",
    "fulfillment_method",
    "payment_method",
    "payment_due",
    "can_cancel",
    "can_retry_payment",
    "hold_expires_at",
    "subtotal",
    "tax",
    "total",
    "delivery_address",
    "contact_phone",
    "delivery_fee_note",
    "estimated_dispatch_at",
    "placed_at",
    "completed_at",
    "cancelled_at",
    "customer_note",
    "lines",
    "payment",
    "status_history",
}
LINE_KEYS = {
    "id",
    "product_id",
    "product_type",
    "name",
    "image_url",
    "unit_price",
    "quantity",
    "line_total",
    "fulfillment_status",
    "fulfilled_at",
    "cancelled_at",
}


@dataclass(frozen=True)
class Ctx:
    owner_id: uuid.UUID
    owner_email: str
    other_id: uuid.UUID
    refs: Refs
    physical_id: uuid.UUID


@pytest_asyncio.fixture
async def ctx(db_session: AsyncSession) -> Ctx:
    owner = await create_user(db_session)
    other = await create_user(db_session)
    refs = await seed_refs(db_session)
    physical = await seed_product(db_session, refs)
    return Ctx(owner.id, owner.email, other.id, refs, physical.id)


async def _insert(db: AsyncSession, table: str, row: dict[str, Any]) -> None:
    cols, vals = ", ".join(row), ", ".join(f":{k}" for k in row)
    await db.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({vals})"), row)


async def seed_order(
    db: AsyncSession,
    c: Ctx,
    *,
    user_id: uuid.UUID | None = None,
    kind: str = "stl",
    line_status: str = "pending",
    status: str = "pending_payment",
    placed_at: datetime = T0,
    method: str = "cash",
    **over: Any,
) -> uuid.UUID:
    """`kind`: `stl` (online, digital) or `pickup` / `delivery` (one physical line, paid by
    `method`)."""
    oid, owner = uuid.uuid4(), user_id or c.owner_id
    order: dict[str, Any] = {
        "id": oid,
        "order_number": f"B3D-{uuid.uuid4().hex[:8].upper()}",
        "user_id": owner,
        "customer_email_snapshot": "EMAIL-SENTINEL@example.com",
        "source": "cart",
        "status": status,
        "subtotal_cents": 1500,
        "total_cents": 1500,
        "terms_accepted_at": T0,
        "placed_at": placed_at,
        "admin_note": ADMIN_NOTE,
    }
    line: dict[str, Any] = {
        "order_id": oid,
        "user_id": owner,
        "product_name_snapshot": "Bought name",
        "image_snapshot": "products/bought.webp",
        "unit_price_cents": 1500,
        "quantity": 1,
        "line_total_cents": 1500,
        "fulfillment_status": line_status,
    }
    if kind == "stl":
        order |= {
            "payment_method": "online",
            "digital_terms_accepted_at": T0,
            "digital_terms_version": "2026-10",
        }
        # A fresh STL each time: one live line per (user, product), uq_order_items_stl_ownership.
        stl = await seed_product(db, c.refs, type=ProductType.STL)
        line |= {"product_id": stl.id, "product_type": "stl", "payment_method": "online"}
        if line_status == "delivered":
            line |= {"fulfilled_at": T0 + timedelta(days=1), "delivered_by": c.other_id}
    else:
        order |= {
            "payment_method": method,
            "fulfillment_method": kind,
            "cash_terms_accepted_at": T0 if method == "cash" else None,
            "contact_phone_snapshot": "+96170123456",
            "contact_phone_hash": HASH_SENTINEL,
        }
        if kind == "delivery":
            order |= {
                "recipient_name": "Rana",
                "governorate": "Bekaa",
                "city": "Zahle",
                "landmark_notes": "Blue gate",
            }
        line |= {
            "product_id": c.physical_id,
            "product_type": "physical",
            "payment_method": method,
            "lead_time_days_snapshot": 3,
            "batch_size_snapshot": 2,
        }
    await _insert(db, "orders", order | over)
    await _insert(db, "order_items", line)
    await db.commit()
    return oid


async def seed_payment(
    db: AsyncSession, order_id: uuid.UUID, status: str, *, at: datetime = T0, **over: Any
) -> None:
    row: dict[str, Any] = {
        "order_id": order_id,
        "provider": "mock",
        "order_payment_method": "online",
        "status": status,
        "amount_cents": 1500,
        "initiated_at": at,
        "provider_payment_id": f"mock_REFERENCE_SENTINEL_{uuid.uuid4().hex}",
    } | over
    if status in ("paid", "partially_refunded", "refunded"):
        row["verified_at"] = at
    if status == "failed":
        row["failed_at"] = at
    if status == "expired":
        row["expired_at"] = at
    await _insert(db, "payments", row)
    await db.commit()


async def seed_cash_handover(db: AsyncSession, order_id: uuid.UUID, admin_id: uuid.UUID) -> None:
    """The one `cash` row the handover writes (ADR-024; `ck_payments_cash_shape`)."""
    await seed_payment(
        db,
        order_id,
        "paid",
        provider="cash",
        order_payment_method="cash",
        provider_payment_id=None,
        recorded_by=admin_id,
    )


async def seed_history(
    db: AsyncSession, order_id: uuid.UUID, *steps: tuple[str | None, str], line: bool = True
) -> None:
    item = await db.scalar(text("SELECT id FROM order_items WHERE order_id = :o"), {"o": order_id})
    for n, (before, after) in enumerate(steps):
        await _insert(
            db,
            "order_status_history",
            {
                "order_id": order_id,
                "order_item_id": item if line else None,
                "from_status": before,
                "to_status": after,
                "reason": "REASON-SENTINEL",
                "created_at": T0 + timedelta(minutes=n),
            },
        )
    await db.commit()


@pytest.fixture
def client(ctx: Ctx) -> Any:
    with client_for(main_app) as test_client:
        login(test_client, ctx.owner_email)
        yield test_client


def _detail(client: TestClient, order_id: uuid.UUID) -> dict[str, Any]:
    response = client.get(f"{ORDERS}/{order_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# -------------------------------------------------------------- authentication


@pytest.mark.parametrize("path", [ORDERS, f"{ORDERS}/{uuid.uuid4()}"])
def test_anonymous_is_401(path: str) -> None:
    with client_for(main_app) as anonymous:
        assert_problem(anonymous.get(path), 401)


async def test_an_unverified_customer_reads_their_orders(
    db_session: AsyncSession, ctx: Ctx
) -> None:
    user = await create_user(db_session, verified=False)
    oid = await seed_order(db_session, ctx, user_id=user.id)
    with client_for(main_app) as unverified:
        login(unverified, user.email)
        assert [o["id"] for o in unverified.get(ORDERS).json()["items"]] == [str(oid)]
        assert unverified.get(f"{ORDERS}/{oid}").status_code == 200


# -------------------------------------------------------------- ownership


async def test_another_users_order_is_404_like_an_unknown_one(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    theirs = await seed_order(db_session, ctx, user_id=ctx.other_id)
    foreign, unknown = client.get(f"{ORDERS}/{theirs}"), client.get(f"{ORDERS}/{uuid.uuid4()}")
    assert_problem(foreign, 404)
    assert_problem(unknown, 404)
    strip = {"instance", "request_id"}
    assert {k: v for k, v in foreign.json().items() if k not in strip} == {
        k: v for k, v in unknown.json().items() if k not in strip
    }


async def test_the_list_never_contains_another_users_orders(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    mine = await seed_order(db_session, ctx)
    await seed_order(db_session, ctx, user_id=ctx.other_id, placed_at=T0 + timedelta(hours=1))
    assert [o["id"] for o in client.get(ORDERS).json()["items"]] == [str(mine)]


# -------------------------------------------------------------- what they bought


@pytest.mark.usefixtures("shop_open")
async def test_detail_shows_what_checkout_charged_and_survives_product_edits(
    db_session: AsyncSession,
) -> None:
    refs = await seed_refs(db_session)
    stl = (await seed_product(db_session, refs, type=ProductType.STL, price_cents=900)).id
    with client_for(main_app) as test_client:
        await buyer(test_client, db_session, stl)
        placed = post_checkout(test_client).json()["order"]
        await db_session.execute(
            text(
                "UPDATE products SET name = 'Renamed', price_cents = 4200, deleted_at = now()"
                " WHERE id = :i"
            ),
            {"i": stl},
        )
        await db_session.commit()
        detail = _detail(test_client, placed["id"])

    for key in ("order_number", "status", "payment_method", "subtotal", "tax", "total"):
        assert detail[key] == placed[key]
    [line], [bought] = detail["lines"], placed["lines"]
    assert line["name"] == bought["name"] == "Lamp"
    assert line["unit_price"] == line["line_total"] == {"amount_cents": 900, "currency": "USD"}
    assert line["fulfillment_status"] == "pending"
    assert detail["payment"] == {
        "status": "pending",
        "provider": "mock",
        "amount": {"amount_cents": 900, "currency": "USD"},
    }
    assert (detail["payment_due"], detail["can_cancel"]) == (False, False)


async def test_the_line_image_is_the_snapshot_url(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    oid = await seed_order(db_session, ctx)
    [line] = _detail(client, oid)["lines"]
    assert line["image_url"].endswith("/products/bought.webp")


# -------------------------------------------------------------- never shown


@pytest.mark.parametrize("route", ["list", "detail"])
async def test_internal_fields_never_appear(
    db_session: AsyncSession, ctx: Ctx, client: TestClient, route: str
) -> None:
    """`admin_note`, provider reference, phone hash, checkout email and history reason."""
    oid = await seed_order(db_session, ctx, kind="delivery", status="in_progress")
    await seed_history(db_session, oid, (None, "pending"))
    online = await seed_order(db_session, ctx, placed_at=T0 - timedelta(days=1))
    await seed_payment(db_session, online, "pending")
    for target in (oid, online):
        response = client.get(ORDERS if route == "list" else f"{ORDERS}/{target}")
        assert response.status_code == 200
        for secret in (*SECRETS, "EMAIL-SENTINEL"):
            assert secret not in response.text
        assert "admin_note" not in response.text


async def test_the_schemas_carry_exactly_the_customer_fields(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    oid = await seed_order(db_session, ctx)
    await seed_payment(db_session, oid, "pending")
    [summary] = client.get(ORDERS).json()["items"]
    detail = _detail(client, oid)
    assert set(summary) == SUMMARY_KEYS
    assert set(detail) == DETAIL_KEYS
    assert set(detail["lines"][0]) == LINE_KEYS
    assert set(detail["payment"]) == {"status", "provider", "amount"}


# -------------------------------------------------------------- STL purchases (F-027)


async def test_an_stl_line_shows_awaiting_delivery_then_delivered_with_fulfilled_at(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    owed = await seed_order(db_session, ctx, line_status="awaiting_delivery", status="in_progress")
    await seed_payment(db_session, owed, "paid")
    [line] = _detail(client, owed)["lines"]
    assert (line["fulfillment_status"], line["fulfilled_at"]) == ("awaiting_delivery", None)

    await db_session.execute(
        text(
            "UPDATE order_items SET fulfillment_status = 'delivered', fulfilled_at = :t,"
            " delivered_by = :a WHERE order_id = :o"
        ),
        {"t": T0 + timedelta(days=2), "a": ctx.other_id, "o": owed},
    )
    await db_session.commit()
    [line] = _detail(client, owed)["lines"]
    assert line["fulfillment_status"] == "delivered"
    assert datetime.fromisoformat(line["fulfilled_at"]) == T0 + timedelta(days=2)


# -------------------------------------------------------------- flags and masking


async def test_an_unpaid_cash_pickup_order_is_due_and_cancellable(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    oid = await seed_order(db_session, ctx, kind="pickup", status="in_progress")
    detail = _detail(client, oid)
    assert (detail["payment_due"], detail["can_cancel"], detail["payment"]) == (True, True, None)
    assert (detail["delivery_address"], detail["delivery_fee_note"]) == (None, None)
    assert detail["contact_phone"] == "+96170123456"
    [summary] = client.get(ORDERS).json()["items"]
    assert summary["payment_due"] is True


async def test_a_delivery_order_shows_its_address_and_the_courier_fee_note(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    oid = await seed_order(db_session, ctx, kind="delivery", status="in_progress")
    detail = _detail(client, oid)
    assert detail["delivery_address"] == {
        "recipient_name": "Rana",
        "governorate": "Bekaa",
        "city": "Zahle",
        "area": None,
        "street": None,
        "landmark_notes": "Blue gate",
    }
    assert "courier" in detail["delivery_fee_note"]


async def test_in_production_is_masked_in_lines_and_history(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    oid = await seed_order(
        db_session, ctx, kind="delivery", status="in_progress", line_status="ready_to_ship"
    )
    await seed_history(
        db_session,
        oid,
        (None, "pending"),
        ("pending", "in_production"),
        ("in_production", "ready_to_ship"),
    )
    detail = _detail(client, oid)
    steps = [(h["from_status"], h["to_status"]) for h in detail["status_history"]]
    assert steps == [(None, "pending"), ("pending", "ready_to_ship")]
    assert "in_production" not in str(detail)

    await db_session.execute(
        text("UPDATE order_items SET fulfillment_status = 'in_production' WHERE order_id = :o"),
        {"o": oid},
    )
    await db_session.commit()
    detail = _detail(client, oid)
    assert detail["lines"][0]["fulfillment_status"] == "pending"
    assert detail["can_cancel"] is False
    assert detail["payment_due"] is True


async def test_the_order_level_history_is_shown_without_actor_or_reason(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    oid = await seed_order(db_session, ctx)
    await seed_history(db_session, oid, (None, "pending_payment"), line=False)
    [entry] = _detail(client, oid)["status_history"]
    assert entry == {
        "order_item_id": None,
        "from_status": None,
        "to_status": "pending_payment",
        "at": entry["at"],
    }


# -------------------------------------------------------------- payment summary


@pytest.mark.parametrize(
    ("statuses", "shown"),
    [
        (["pending"], "pending"),
        (["failed"], "failed"),
        (["failed", "expired"], "expired"),
        (["pending", "failed"], "pending"),
        (["paid", "expired"], "paid"),
    ],
    ids=["pending", "failed", "latest-ended", "live-over-newer-ended", "paid-over-newer-ended"],
)
async def test_the_payment_shown_is_the_live_or_paid_one_else_the_latest(
    db_session: AsyncSession,
    ctx: Ctx,
    client: TestClient,
    statuses: list[str],
    shown: str,
) -> None:
    """`statuses` oldest first; at most one is live (`uq_payments_one_live`)."""
    oid = await seed_order(db_session, ctx)
    for n, status in enumerate(statuses):
        await seed_payment(db_session, oid, status, at=T0 + timedelta(minutes=n))
    detail = _detail(client, oid)
    assert detail["payment"]["status"] == shown


# -------------------------------------------------------------- flags through the real reader


HOLD = timedelta(seconds=1800)  # `checkout_hold_period`'s default


async def test_a_failed_attempt_inside_the_hold_can_be_retried(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    placed = datetime.now(UTC).replace(microsecond=0)
    oid = await seed_order(db_session, ctx, placed_at=placed)
    await seed_payment(db_session, oid, "failed", at=placed + timedelta(minutes=1))
    detail = _detail(client, oid)
    assert detail["can_retry_payment"] is True
    expires = datetime.fromisoformat(detail["hold_expires_at"])
    assert expires == placed + timedelta(minutes=1) + HOLD


@pytest.mark.parametrize("status", ["pending", "processing"])
async def test_a_live_attempt_cannot_be_retried_but_shows_its_hold(
    db_session: AsyncSession, ctx: Ctx, client: TestClient, status: str
) -> None:
    placed = datetime.now(UTC).replace(microsecond=0)
    oid = await seed_order(db_session, ctx, placed_at=placed)
    await seed_payment(db_session, oid, status, at=placed)
    detail = _detail(client, oid)
    assert detail["can_retry_payment"] is False
    assert datetime.fromisoformat(detail["hold_expires_at"]) == placed + HOLD


async def test_after_the_hold_an_unpaid_order_cannot_be_retried(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    oid = await seed_order(db_session, ctx)  # placed at T0, long ago
    await seed_payment(db_session, oid, "failed")
    detail = _detail(client, oid)
    assert detail["can_retry_payment"] is False
    assert datetime.fromisoformat(detail["hold_expires_at"]) == T0 + HOLD


async def test_a_paid_or_cash_order_has_no_retry_and_no_hold(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    paid = await seed_order(db_session, ctx, line_status="awaiting_delivery", status="in_progress")
    await seed_payment(db_session, paid, "paid")
    cash = await seed_order(db_session, ctx, kind="pickup", status="in_progress")
    for oid in (paid, cash):
        detail = _detail(client, oid)
        assert (detail["can_retry_payment"], detail["hold_expires_at"]) == (False, None)


async def test_a_paid_cash_order_still_in_progress_is_not_due(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    """A returned line can bring a paid cash order back to `in_progress` (SRS 20.2):
    only the cash payment row keeps it from asking for the money again."""
    oid = await seed_order(
        db_session, ctx, kind="delivery", status="in_progress", line_status="returned"
    )
    await seed_cash_handover(db_session, oid, ctx.other_id)
    detail = _detail(client, oid)
    assert detail["payment_due"] is False
    assert detail["payment"] == {
        "status": "paid",
        "provider": "cash",
        "amount": {"amount_cents": 1500, "currency": "USD"},
    }
    [summary] = client.get(ORDERS).json()["items"]
    assert summary["payment_due"] is False


@pytest.mark.parametrize(
    ("order_status", "payment_status"),
    [("in_progress", "paid"), ("partially_refunded", "partially_refunded")],
)
async def test_a_paid_online_physical_order_can_be_cancelled(
    db_session: AsyncSession,
    ctx: Ctx,
    client: TestClient,
    order_status: str,
    payment_status: str,
) -> None:
    oid = await seed_order(db_session, ctx, kind="pickup", method="online", status=order_status)
    await seed_payment(db_session, oid, payment_status)
    detail = _detail(client, oid)
    assert (detail["can_cancel"], detail["payment_due"]) == (True, False)


@pytest.mark.parametrize(("second", "expected"), [("cancelled", True), ("in_production", False)])
async def test_a_line_an_admin_cancelled_does_not_block_self_cancel(
    db_session: AsyncSession, ctx: Ctx, client: TestClient, second: str, expected: bool
) -> None:
    """Owner decision 2026-10-19 (ADR-033 d4): only live (not cancelled) lines count."""
    oid = await seed_order(db_session, ctx, kind="pickup", method="online", status="in_progress")
    await _insert(
        db_session,
        "order_items",
        {
            "order_id": oid,
            "user_id": ctx.owner_id,
            "product_id": ctx.physical_id,
            "product_type": "physical",
            "payment_method": "online",
            "product_name_snapshot": "Second",
            "unit_price_cents": 500,
            "quantity": 1,
            "line_total_cents": 500,
            "fulfillment_status": second,
            "lead_time_days_snapshot": 3,
            "batch_size_snapshot": 2,
        },
    )
    await seed_payment(db_session, oid, "paid")
    assert _detail(client, oid)["can_cancel"] is expected


async def test_can_cancel_asks_payments_not_the_order_status(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    """ADR-033 d4: an `in_progress` online order whose only attempt failed is not paid."""
    oid = await seed_order(db_session, ctx, kind="pickup", method="online", status="in_progress")
    await seed_payment(db_session, oid, "failed")
    assert _detail(client, oid)["can_cancel"] is False


async def test_a_late_captured_attempt_on_a_cancelled_order_counts_for_nothing(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    oid = await seed_order(
        db_session,
        ctx,
        kind="pickup",
        method="online",
        status="cancelled",
        line_status="cancelled",
        cancelled_at=T0,
    )
    await seed_payment(
        db_session,
        oid,
        "failed",
        late_captured_at=T0,
        captured_amount_cents=987654,
        captured_currency="USD",
    )
    response = client.get(f"{ORDERS}/{oid}")
    detail = response.json()
    assert (detail["can_cancel"], detail["payment_due"]) == (False, False)
    assert detail["payment"]["status"] == "failed"
    assert "987654" not in response.text and "captured" not in response.text


# -------------------------------------------------------------- pages and filters


async def test_pages_cover_every_order_once_when_placed_at_ties(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    ids = {str(await seed_order(db_session, ctx)) for _ in range(7)}
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(4):
        params: dict[str, Any] = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        page = client.get(ORDERS, params=params).json()
        seen += [o["id"] for o in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == sorted(ids, key=uuid.UUID, reverse=True)
    assert cursor is None


async def test_the_default_page_is_20_and_100_is_allowed(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    for n in range(21):
        await seed_order(db_session, ctx, placed_at=T0 - timedelta(minutes=n))
    default = client.get(ORDERS).json()
    assert (len(default["items"]), default["next_cursor"] is None) == (20, False)
    widest = client.get(ORDERS, params={"limit": 100}).json()
    assert (len(widest["items"]), widest["next_cursor"]) == (21, None)


async def test_an_order_placed_between_pages_is_neither_repeated_nor_skipping_one(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    older = [
        str(await seed_order(db_session, ctx, placed_at=T0 - timedelta(hours=n))) for n in range(4)
    ]
    first = client.get(ORDERS, params={"limit": 2}).json()
    await seed_order(db_session, ctx, placed_at=T0 + timedelta(days=1))
    second = client.get(ORDERS, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [o["id"] for o in first["items"] + second["items"]] == older
    assert second["next_cursor"] is None


async def test_status_and_date_filters(
    db_session: AsyncSession, ctx: Ctx, client: TestClient
) -> None:
    early = await seed_order(db_session, ctx, placed_at=T0)
    edge = await seed_order(
        db_session, ctx, placed_at=T0 + timedelta(days=1), kind="pickup", status="in_progress"
    )
    late = await seed_order(db_session, ctx, placed_at=T0 + timedelta(days=2))

    def ids(**params: str) -> list[str]:
        return [o["id"] for o in client.get(ORDERS, params=params).json()["items"]]

    assert ids(status="in_progress") == [str(edge)]
    assert ids(status="pending_payment") == [str(late), str(early)]
    day1 = (T0 + timedelta(days=1)).isoformat()
    assert ids(placed_after=day1) == [str(late), str(edge)]
    assert ids(placed_before=day1) == [str(early)]
    assert ids(placed_after=day1, placed_before=(T0 + timedelta(days=2)).isoformat()) == [str(edge)]


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("limit", "0"),
        ("limit", "101"),
        ("status", "shipped"),
        ("placed_after", "2026-10-01T12:00:00"),
        ("placed_before", "0001-01-01T00:00:00+05:00"),
        ("cursor", "not-a-cursor"),
        ("cursor", "MjAyNi0xMC0wMVQxMjowMDowMHxub3QtYS11dWlk"),
    ],
)
def test_a_bad_query_is_422(client: TestClient, param: str, value: str) -> None:
    response = client.get(ORDERS, params={param: value})
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert response.json()["errors"][0]["loc"][-1] == param
