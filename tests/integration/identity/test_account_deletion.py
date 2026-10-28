"""VS-045 `DELETE /api/v1/me` on real PostgreSQL (BR-125, BR-126, FR-03; ADR-047): all or
nothing, no personal value left in any table, records kept, login gone, email reusable."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.security import hash_phone
from app.identity.domain.enums import UserRole
from app.identity.infrastructure import account_erasure
from app.identity.infrastructure.repositories import SessionRepository
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.main import app as main_app
from app.ordering.infrastructure.cash import SqlCashChecks
from app.platform.domain.entities import REDACTED
from app.platform.infrastructure.audit_writer import SqlAuditWriter
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    PASSWORD,
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.identity.deletion_support import (
    ADMIN_REASON,
    ADMIN_REPLY,
    ME,
    Customer,
    delete_me,
    one,
    run,
    scalar,
    seed_customer,
    traces,
)
from tests.integration.payments.refund_support import create, ok, payment_of

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _delete_as(email: str, password: str = PASSWORD) -> Any:
    with client_for(main_app) as client:
        login(client, email)
        return delete_me(client, password)


async def _untouched(engine: AsyncEngine, c: Customer) -> None:
    """Nothing the deletion writes has moved: the all-or-nothing check."""
    user = await one(engine, "SELECT email, anonymized_at FROM users WHERE id = :u", u=c.user_id)
    assert (user.email, user.anonymized_at) == (c.email, None)
    assert await scalar(
        engine,
        "SELECT count(*) FROM orders WHERE user_id = :u AND anonymized_at IS NULL"
        " AND contact_phone_snapshot IS NOT NULL",
        u=c.user_id,
    ) == len(c.orders)
    assert (
        await scalar(
            engine,
            "SELECT count(*) FROM addresses WHERE user_id = :u AND phone IS NOT NULL",
            u=c.user_id,
        )
        == 2
    )
    assert await scalar(
        engine,
        "SELECT count(*) FROM offers WHERE user_id = :u AND status <> 'withdrawn'",
        u=c.user_id,
    ) == len(c.offers)
    assert (
        await scalar(
            engine,
            "SELECT count(*) FROM wishlist_items WHERE user_id = :u AND deleted_at IS NULL",
            u=c.user_id,
        )
        == 2
    )
    assert (
        await scalar(
            engine,
            "SELECT count(*) FROM contact_messages WHERE user_id = :u AND email = :e",
            u=c.user_id,
            e=c.email,
        )
        == 1
    )
    assert (
        await scalar(
            engine,
            "SELECT count(*) FROM email_outbox WHERE user_id = :u AND status = 'pending'",
            u=c.user_id,
        )
        == 1
    )
    assert (
        await scalar(
            engine,
            "SELECT count(*) FROM audit_logs WHERE entity_id = :u AND action = 'user.anonymized'",
            u=c.user_id,
        )
        == 0
    )


async def test_deletion_strips_every_personal_value_from_every_table(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    response = _delete_as(c.email)
    assert response.status_code == 204, response.text
    assert await traces(db_engine, c.pii | {c.password_hash}) == {}


async def test_the_user_row_is_anonymised_and_its_credentials_void(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    before = await scalar(db_engine, "SELECT auth_epoch FROM users WHERE id = :u", u=c.user_id)
    with client_for(main_app) as client:
        login(client, c.email)
        assert delete_me(client).status_code == 204
        assert "access_token" not in client.cookies
        user = await one(db_engine, "SELECT * FROM users WHERE id = :u", u=c.user_id)
        assert user.email == f"deleted+{c.user_id}@invalid"
        assert (user.is_active, user.anonymized_at is not None, user.deleted_at) == (
            False,
            True,
            None,
        )
        assert user.auth_epoch == before + 1 and user.password_hash != c.password_hash
        assert (
            await scalar(
                db_engine,
                "SELECT count(*) FROM sessions WHERE user_id = :u AND revoked_at IS NULL",
                u=c.user_id,
            )
            == 0
        )
        for table in ("verification_tokens", "password_reset_tokens"):
            assert (
                await scalar(
                    db_engine,
                    f"SELECT count(*) FROM {table} WHERE user_id = :u AND used_at IS NULL",
                    u=c.user_id,
                )
                == 0
            )


async def test_the_old_credentials_and_tokens_no_longer_work(db_session: AsyncSession) -> None:
    c = await seed_customer(db_session)
    with client_for(main_app) as client:
        login(client, c.email)
        jar = dict(client.cookies)
        assert delete_me(client).status_code == 204
        for name, value in jar.items():
            client.cookies.set(name, value)
        assert client.get(ME).status_code == 401  # the old access token, epoch advanced
        refreshed = client.post("/api/v1/auth/refresh", headers=csrf(client))
        assert_problem(refreshed, 401)  # the session row was revoked
        refused = client.post("/api/v1/auth/login", json={"email": c.email, "password": PASSWORD})
        assert_problem(refused, 401, "INVALID_CREDENTIALS")


async def test_the_email_can_be_registered_again(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    assert _delete_as(c.email).status_code == 204
    with client_for(main_app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": c.email, "password": PASSWORD},
        )
    assert registered.status_code < 300, registered.text
    again = await one(db_engine, "SELECT id, anonymized_at FROM users WHERE email = :e", e=c.email)
    assert again.id != c.user_id and again.anonymized_at is None


async def test_financial_and_delivery_records_remain_without_personal_data(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    counts = (
        "SELECT (SELECT count(*) FROM orders WHERE user_id = :u), (SELECT count(*) FROM"
        " order_items WHERE user_id = :u), (SELECT count(*) FROM payments p JOIN orders o ON"
        " o.id = p.order_id WHERE o.user_id = :u)"
    )
    before = tuple(await one(db_engine, counts, u=c.user_id))
    assert _delete_as(c.email).status_code == 204
    assert tuple(await one(db_engine, counts, u=c.user_id)) == before
    rows = (
        await db_session.execute(
            text(
                "SELECT customer_email_snapshot, recipient_name, contact_phone_snapshot,"
                " contact_phone_hash, governorate, city, street, landmark_notes, customer_note,"
                " admin_note, anonymized_at, status FROM orders WHERE user_id = :u"
            ),
            {"u": c.user_id},
        )
    ).all()
    for row in rows:
        assert row.customer_email_snapshot == f"deleted+{c.user_id}@invalid"
        assert (row.recipient_name, row.contact_phone_snapshot) == (None, None)
        assert row.contact_phone_hash is not None  # ADR-038 d23's cash hold matches it
        assert (row.city, row.street, row.landmark_notes, row.customer_note) == (
            None,
            None,
            None,
            None,
        )
        assert row.governorate == "Beqaa" and row.admin_note == "Called twice"
        assert row.anonymized_at is not None
    assert sorted(r.status for r in rows) == ["cancelled", "completed"]
    stl = await one(
        db_engine,
        "SELECT fulfillment_status, fulfilled_at FROM order_items WHERE user_id = :u"
        " AND product_type = 'stl'",
        u=c.user_id,
    )
    assert stl.fulfillment_status == "delivered" and stl.fulfilled_at is not None


async def test_addresses_wishlist_offers_messages_and_mail_are_closed_out(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    assert _delete_as(c.email).status_code == 204
    addresses = (
        await db_session.execute(
            text("SELECT * FROM addresses WHERE user_id = :u"), {"u": c.user_id}
        )
    ).all()
    assert len(addresses) == 2
    for a in addresses:
        assert a.deleted_at is not None and a.anonymized_at is not None and not a.is_default
        assert (a.recipient_name, a.phone, a.city, a.street, a.landmark_notes) == (None,) * 5
        assert (a.label, a.governorate) == ("Home", "beqaa")
    assert (
        await scalar(
            db_engine,
            "SELECT count(*) FROM wishlist_items WHERE user_id = :u AND deleted_at IS NULL",
            u=c.user_id,
        )
        == 0
    )
    for product in c.products:
        count = await scalar(
            db_engine, "SELECT wishlist_count FROM products WHERE id = :p", p=product
        )
        assert count == 0
    assert (
        await scalar(
            db_engine,
            "SELECT count(*) FROM cart_items ci JOIN carts ca ON ca.id = ci.cart_id"
            " WHERE ca.user_id = :u",
            u=c.user_id,
        )
        == 0
    )
    for offer in c.offers:
        state = await one(db_engine, "SELECT status, turn FROM offers WHERE id = :o", o=offer)
        assert (state.status, state.turn) == ("withdrawn", None)
        last = await one(
            db_engine,
            "SELECT actor, action FROM offer_rounds WHERE offer_id = :o ORDER BY sequence DESC"
            " LIMIT 1",
            o=offer,
        )
        assert (last.actor, last.action) == ("system", "withdrawn")
    message = await one(db_engine, "SELECT * FROM contact_messages WHERE user_id = :u", u=c.user_id)
    assert (message.name, message.email, message.phone, message.message) == (
        "Deleted customer",
        f"deleted+{c.user_id}@invalid",
        None,
        "[deleted]",
    )
    assert (message.subject, message.order_id) == ("Problem with my order", c.orders[0])
    mail = (
        await db_session.execute(
            text("SELECT * FROM email_outbox WHERE user_id = :u ORDER BY created_at"),
            {"u": c.user_id},
        )
    ).all()
    assert {m.recipient_email for m in mail} == {f"deleted+{c.user_id}@invalid"}
    assert sorted((m.status, m.last_error) for m in mail) == [
        ("failed", "account_deleted"),
        ("sent", None),
    ]
    assert all(m.payload == {"name": REDACTED} for m in mail if m.status == "failed")


async def test_reviews_keep_their_text_and_show_no_author(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    await run(
        db_session,
        "INSERT INTO reviews (user_id, product_id, rating, body) VALUES (:u, :p, 5, 'Lovely')",
        u=c.user_id,
        p=c.products[1],
    )
    assert _delete_as(c.email).status_code == 204
    review = await one(
        db_engine, "SELECT body, deleted_at FROM reviews WHERE user_id = :u", u=c.user_id
    )
    assert (review.body, review.deleted_at) == ("Lovely", None)


async def test_one_audit_row_with_counts_and_no_personal_data(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    assert _delete_as(c.email).status_code == 204
    row = await one(
        db_engine,
        "SELECT actor_user_id, entity_type, after_data::text AS data FROM audit_logs"
        " WHERE entity_id = :u AND action = 'user.anonymized'",
        u=c.user_id,
    )
    assert (row.actor_user_id, row.entity_type) == (c.user_id, "User")
    assert c.email not in row.data and '"orders": 2' in row.data
    assert '"offers_withdrawn": 2' in row.data and '"addresses": 2' in row.data
    assert '"offer_messages": 1' in row.data and '"idempotency_records": 1' in row.data


@pytest.mark.parametrize(
    ("payment_method", "payment_status", "lines", "status"),
    [
        pytest.param("online", None, ("pending",), "pending_payment", id="pending_payment"),
        pytest.param("cash", None, ("ready_to_ship",), "in_progress", id="cash_in_progress"),
        pytest.param(
            "online",
            "paid",
            ("refunded", "ready_to_ship"),
            "partially_refunded",
            id="partially_refunded_with_a_live_line",
        ),
        pytest.param("online", "paid", ("returned",), "completed", id="returned_line"),
        pytest.param("online", "paid", ("delivered",), "completed", id="stl_awaiting_delivery"),
    ],
)
async def test_an_open_order_blocks_and_changes_nothing(
    request: pytest.FixtureRequest,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    payment_method: str,
    payment_status: str | None,
    lines: tuple[str, ...],
    status: str,
) -> None:
    c = await seed_customer(db_session)
    order = await seed_physical_order(
        db_session,
        user_id=c.user_id,
        payment_method=payment_method,
        payment_status=payment_status,
        line_states=lines,
        order_status=status,
        stl_line="awaiting_delivery" if "stl" in request.node.callspec.id else None,
    )
    c.orders.append(order.order_id)
    response = _delete_as(c.email)
    assert_problem(response, 409, "ACCOUNT_DELETION_BLOCKED")
    assert response.json()["reason"] == "open_order"
    await _untouched(db_engine, c)


async def _refund(
    db: AsyncSession,
    order_id: uuid.UUID,
    payment_id: uuid.UUID,
    *,
    kind: str,
    status: str,
    by: uuid.UUID,
    reissued: bool = False,
) -> None:
    await run(
        db,
        "INSERT INTO refunds (order_id, payment_id, payment_provider, kind, status, amount_cents,"
        " reason, requested_by, initiated_at, failed_at, settled_at, voided_at, void_reason,"
        " reissued_at) VALUES (:o, :p, 'mock', CAST(:k AS refund_kind), CAST(:s AS"
        " refund_status), 300, 'test', :by, now(), :failed, :settled, :voided, :why, :reissued)",
        o=order_id,
        p=payment_id,
        k=kind,
        s=status,
        by=None if kind == "late_capture" else by,
        failed=datetime.now(UTC) if status == "failed" else None,
        settled=datetime.now(UTC) if status == "settled" else None,
        voided=datetime.now(UTC) if status == "voided" else None,
        why="test" if status == "voided" else None,
        reissued=datetime.now(UTC) if reissued else None,
    )


async def _closed_paid_order(
    db: AsyncSession, c: Customer, db_engine: AsyncEngine
) -> tuple[uuid.UUID, uuid.UUID]:
    paid = await seed_physical_order(
        db,
        user_id=c.user_id,
        payment_method="online",
        payment_status="paid",
        line_states=("delivered",),
        order_status="partially_refunded",
    )
    c.orders.append(paid.order_id)
    return paid.order_id, await payment_of(db_engine, paid.order_id)


@pytest.mark.parametrize(
    ("kind", "status"),
    [("admin", "pending"), ("admin", "failed"), ("late_capture", "pending")],
    ids=["pending", "owed", "pending_late_capture"],
)
async def test_an_unsettled_refund_blocks_and_changes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, kind: str, status: str
) -> None:
    c = await seed_customer(db_session)
    order_id, payment_id = await _closed_paid_order(db_session, c, db_engine)
    await _refund(db_session, order_id, payment_id, kind=kind, status=status, by=c.user_id)
    response = _delete_as(c.email)
    assert_problem(response, 409, "ACCOUNT_DELETION_BLOCKED")
    assert response.json()["reason"] == "unsettled_refund"
    await _untouched(db_engine, c)


@pytest.mark.parametrize(
    ("kind", "status"),
    [("admin", "voided"), ("late_capture", "settled"), ("admin", "settled")],
)
async def test_a_settled_or_voided_refund_does_not_block(
    db_engine: AsyncEngine, db_session: AsyncSession, kind: str, status: str
) -> None:
    c = await seed_customer(db_session)
    order_id, payment_id = await _closed_paid_order(db_session, c, db_engine)
    await _refund(db_session, order_id, payment_id, kind=kind, status=status, by=c.user_id)
    assert _delete_as(c.email).status_code == 204


async def test_a_reissued_failed_refund_does_not_block(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    order_id, payment_id = await _closed_paid_order(db_session, c, db_engine)
    common: dict[str, Any] = {"kind": "admin", "by": c.user_id}
    await _refund(db_session, order_id, payment_id, status="failed", reissued=True, **common)
    await _refund(db_session, order_id, payment_id, status="settled", **common)
    assert _delete_as(c.email).status_code == 204


async def test_a_wrong_password_is_401_and_changes_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    assert_problem(_delete_as(c.email, "not my password"), 401, "INVALID_CREDENTIALS")
    await _untouched(db_engine, c)


async def test_an_administrator_is_refused(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        response = delete_me(client)
    assert_problem(response, 409, "ACCOUNT_DELETION_BLOCKED")
    assert response.json()["reason"] == "administrator"
    row = await one(db_engine, "SELECT role, anonymized_at FROM users WHERE id = :u", u=admin.id)
    assert (row.role, row.anonymized_at) == (UserRole.ADMIN.value, None)


async def test_anonymous_unverified_and_missing_csrf_are_refused(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        assert_problem(
            client.request("DELETE", ME, json={"current_password": PASSWORD}), 401, "AUTH_REQUIRED"
        )
    unverified = await create_user(db_session, verified=False)
    with client_for(main_app) as client:
        login(client, unverified.email)
        assert_problem(delete_me(client), 403, "EMAIL_VERIFICATION_REQUIRED")
    c = await seed_customer(db_session)
    with client_for(main_app) as client:
        login(client, c.email)
        assert_problem(delete_me(client, headers={}), 403, "CSRF_INVALID")


async def test_the_sixth_attempt_in_an_hour_is_rate_limited(db_session: AsyncSession) -> None:
    c = await seed_customer(db_session)
    with client_for(main_app) as client:
        login(client, c.email)
        for _ in range(5):
            assert_problem(delete_me(client, "wrong"), 401, "INVALID_CREDENTIALS")
        assert_problem(delete_me(client), 429, "RATE_LIMITED")


def _boom(*_: Any, **__: Any) -> Any:
    raise RuntimeError("injected failure")


@pytest.mark.parametrize(
    "target",
    ["anonymise_outbox", "anonymise_contact_messages", "revoke_all_for_user", "audit"],
)
async def test_a_failure_midway_rolls_everything_back(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    """Each point runs after earlier writes: orders, offers and wishlist are already changed."""
    c = await seed_customer(db_session)
    if target == "revoke_all_for_user":
        monkeypatch.setattr(SessionRepository, target, _boom)
    elif target == "audit":
        real = SqlAuditWriter.record

        async def record(self: SqlAuditWriter, **row: Any) -> None:
            if row.get("action") == "user.anonymized":
                raise RuntimeError("injected failure")
            await real(self, **row)

        monkeypatch.setattr(SqlAuditWriter, "record", record)
    else:
        monkeypatch.setattr(account_erasure, target, _boom)
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, c.email)
        assert delete_me(client).status_code == 500
    monkeypatch.undo()
    await _untouched(db_engine, c)
    with client_for(main_app) as client:
        login(client, c.email)  # still able to sign in


async def test_admin_text_survives_while_the_customers_is_gone(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-047 d4: the administrator's offer reply and history note stay, as admin_note does."""
    c = await seed_customer(db_session)
    assert _delete_as(c.email).status_code == 204
    rounds = await scalar(
        db_engine,
        "SELECT count(*) FROM offer_rounds WHERE offer_id = :o AND message = :m",
        o=c.offers[0],
        m=ADMIN_REPLY,
    )
    notes = await scalar(
        db_engine, "SELECT count(*) FROM order_status_history WHERE reason = :r", r=ADMIN_REASON
    )
    assert rounds >= 1 and notes >= 1
    claims = await scalar(
        db_engine, "SELECT count(*) FROM idempotency_records WHERE user_id = :u", u=c.user_id
    )
    assert claims == 0


async def test_the_cash_hold_on_a_self_cancelled_phone_survives_deletion(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-038 d23: delete and re-register must not reopen cash for the same phone."""
    c = await seed_customer(db_session)
    order = await seed_physical_order(
        db_session, user_id=c.user_id, line_states=("cancelled",), order_status="cancelled"
    )
    await run(
        db_session,
        "UPDATE orders SET customer_cancelled_at = now() WHERE id = :o",
        o=order.order_id,
    )
    assert _delete_as(c.email).status_code == 204
    newcomer = await create_user(db_session, email=c.email)
    async with AsyncSession(db_engine) as session:
        held = await SqlCashChecks(session).open_order_count(
            newcomer.id, hash_phone(order.phone), at=datetime.now(UTC)
        )
    assert held == 1


_FINANCIAL = (
    "SELECT array_agg(t::text ORDER BY t::text) FROM (SELECT p.* FROM payments p"
    " JOIN orders o ON o.id = p.order_id WHERE o.user_id = :u) t"
    " UNION ALL SELECT array_agg(t::text ORDER BY t::text) FROM (SELECT r.* FROM refunds r"
    " JOIN orders o ON o.id = r.order_id WHERE o.user_id = :u) t"
    " UNION ALL SELECT array_agg(t::text ORDER BY t::text) FROM"
    " (SELECT i.* FROM order_items i WHERE i.user_id = :u) t"
)


async def test_payments_refunds_and_lines_are_unchanged_column_by_column(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    c = await seed_customer(db_session)
    order_id, payment_id = await _closed_paid_order(db_session, c, db_engine)
    await _refund(db_session, order_id, payment_id, kind="admin", status="settled", by=c.user_id)

    async def snapshot() -> list[Any]:
        async with db_engine.connect() as conn:
            return list((await conn.execute(text(_FINANCIAL), {"u": c.user_id})).scalars())

    before = await snapshot()
    assert all(before)
    assert _delete_as(c.email).status_code == 204
    assert await snapshot() == before


async def test_an_admin_refund_on_an_anonymised_order_still_works(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """A VS-031 return after deletion: the money path passes every relaxed CHECK."""
    c = await seed_customer(db_session)
    assert _delete_as(c.email).status_code == 204
    line = await scalar(
        db_engine,
        "SELECT id FROM order_items WHERE order_id = :o AND product_type = 'physical'",
        o=c.orders[0],
    )
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        ok(create(admin, c.orders[0], [(line, 300)]), 201)
    status = await scalar(db_engine, "SELECT status FROM orders WHERE id = :o", o=c.orders[0])
    assert status == "partially_refunded"


async def test_an_administrator_can_still_list_and_read_an_anonymised_account(
    db_session: AsyncSession,
) -> None:
    c = await seed_customer(db_session)
    assert _delete_as(c.email).status_code == 204
    with client_for(main_app) as admin:
        await mfa_admin(admin, db_session)
        detail = admin.get(f"/api/v1/admin/users/{c.user_id}")
        listed = admin.get("/api/v1/admin/users", params={"search": f"deleted+{c.user_id}"})
    assert detail.status_code == 200, detail.text
    assert detail.json()["email"] == f"deleted+{c.user_id}@invalid"
    assert listed.status_code == 200, listed.text
    assert [u["id"] for u in listed.json()["items"]] == [str(c.user_id)]
