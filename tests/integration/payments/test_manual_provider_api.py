"""The `manual` provider over HTTP (VS-050, ADR-049): cart and offer checkouts wait for the
administrator's call (a phone is required for it), confirm pays them, a wrong amount is a
late capture the customer may retry, the admin work list, and no webhooks."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from app.ordering.api import checkout as checkout_api
from app.payments.infrastructure.providers.manual import ManualPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import (
    assert_problem,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
)
from tests.integration.negotiation.offer_support import offer_state, seed_offer
from tests.integration.ordering.checkout_support import (
    Rows,
    add_to_cart,
    checkout_body,
    new_key,
    post_checkout,
    rows,
    shop_open,  # noqa: F401
)
from tests.integration.ordering.physical_support import (
    physical,
    random_phone,
    seed_address,
    setting,
    spaced,
    stl,
)
from tests.integration.payments.recovery_support import (
    ORDER_STATE,
    PAYMENT_STATE,
    YEARS_AHEAD,
    alerts,
    drop_alert_emails,  # noqa: F401
    one,
    seed_attempt,
    seed_order,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "shop_open", "drop_alert_emails"),
]

MANUAL_HOLD = timedelta(days=7)
PHONE: dict[str, Any] = {"contact_phone_snapshot": "+96171555123", "contact_phone_hash": "c" * 64}
AWAIT = "await_admin_contact"
REASON = "customer paid by OMT; receipt seen by the administrator"
ORDER_ROW = "SELECT contact_phone_snapshot, contact_phone_hash FROM orders WHERE id = :o"
LATEST_PAYMENT = """
    SELECT id, provider, status, provider_payment_id FROM payments WHERE order_id = :o
    ORDER BY initiated_at DESC, id DESC LIMIT 1
"""
NOTICES = """
    SELECT
      (SELECT count(*) FROM email_outbox WHERE template = 'order_awaiting_payment'
         AND payload->>'order_id' = :o) AS emails,
      (SELECT count(*) FROM notifications WHERE payload->>'event' = 'order.awaiting_payment'
         AND payload->>'order_id' = :o) AS notices,
      (SELECT count(*) FROM email_outbox WHERE payload::text LIKE '%' || :phone || '%')
        + (SELECT count(*) FROM notifications WHERE payload::text LIKE '%' || :phone || '%')
        AS phone_leaks
"""


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The app with `PAYMENT_PROVIDER=manual`, as production runs it."""
    with client_for(main_app) as c:
        monkeypatch.setattr(
            main_app.state, "payment_providers", {"manual": ManualPaymentProvider()}
        )
        yield c


def _post(client: TestClient, path: str, body: dict[str, Any], **headers: str) -> httpx.Response:
    response: httpx.Response = client.post(path, json=body, headers=csrf(client) | headers)
    return response


def _capture(client: TestClient, payment_id: Any, cents: int, **over: Any) -> httpx.Response:
    body = {"captured_amount_cents": cents, "captured_currency": "USD", "reason": REASON}
    path = f"/api/v1/admin/payments/{payment_id}/record-capture"
    return _post(client, path, body | over, **{"Idempotency-Key": new_key()})


def _confirm(client: TestClient, payment_id: Any, cents: int, **over: Any) -> httpx.Response:
    body = {"verified_amount_cents": cents, "reason": REASON} | over
    return _post(client, f"/api/v1/admin/payments/{payment_id}/confirm", body)


async def _buyer(client: TestClient, db: AsyncSession, *products: uuid.UUID) -> uuid.UUID:
    user = await create_user(db)
    login(client, user.email)
    for product_id in products:
        add_to_cart(client, product_id)
    return user.id


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


# --- Cart checkout ---------------------------------------------------------------------------


async def test_an_stl_checkout_waits_for_the_administrators_call(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    phone = random_phone()
    await _buyer(client, db_session, await stl(db_session))
    response = post_checkout(client, checkout_body(contact_phone=spaced(phone)))
    assert response.status_code == 201, response.text
    body = response.json()
    payment, order_id = body["payment"], body["order"]["id"]
    assert (payment["provider"], payment["status"], payment["redirect_url"]) == (
        "manual",
        "pending",
        None,
    )
    assert payment["next_step"] == AWAIT
    placed = _parse(body["order"]["placed_at"])
    assert _parse(payment["hold_expires_at"]) == placed + MANUAL_HOLD
    stored = await one(db_engine, LATEST_PAYMENT, o=order_id)
    assert (stored.provider, stored.status, stored.provider_payment_id) == (
        "manual",
        "pending",
        None,
    )
    order = await one(db_engine, ORDER_ROW, o=order_id)
    assert order.contact_phone_snapshot == phone and order.contact_phone_hash
    notices = await one(db_engine, NOTICES, o=order_id, phone=phone)
    assert (notices.emails, notices.notices, notices.phone_leaks) == (1, 1, 0)
    assert await alerts(db_engine, stored.id) == {"manual_payment_due": 1}


async def test_a_manual_stl_checkout_without_a_phone_writes_nothing(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user_id = await _buyer(client, db_session, await stl(db_session))
    response = post_checkout(client)
    assert_problem(response, 422, "CONTACT_PHONE_REQUIRED")
    assert await rows(db_engine, user_id) == Rows(0, 0, 0, 0, 1, 0)


async def test_confirm_without_a_reference_pays_a_mixed_order(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Pickup already gives the phone to call; the STL line goes to `awaiting_delivery`, the
    physical one stays `pending` and workable (BR-042, BR-148)."""
    phone = random_phone()
    lamp, model = await physical(db_session), await stl(db_session)
    await _buyer(client, db_session, lamp, model)
    async with setting(db_engine, "pickup_address", "Workshop, Zahle"):
        placed = post_checkout(
            client, checkout_body(fulfillment_method="pickup", contact_phone=phone)
        )
    assert placed.status_code == 201, placed.text
    order_id, payment = placed.json()["order"]["id"], placed.json()["payment"]
    assert payment["next_step"] == AWAIT
    total = placed.json()["order"]["total"]["amount_cents"]
    await mfa_admin(client, db_session)
    confirmed = _confirm(client, payment["id"], total)
    assert confirmed.status_code == 200, confirmed.text
    assert (confirmed.json()["outcome"], confirmed.json()["payment"]["status"]) == (
        "apply_paid",
        "paid",
    )
    state = await one(db_engine, ORDER_STATE, o=order_id)
    assert state.status == "in_progress"
    lines = await one(
        db_engine,
        "SELECT array_agg(fulfillment_status::text ORDER BY product_type::text) AS s"
        " FROM order_items WHERE order_id = :o",
        o=order_id,
    )
    assert lines.s == ["pending", "awaiting_delivery"]  # physical, then stl
    assert (await one(db_engine, PAYMENT_STATE, p=payment["id"])).provider_payment_id is None


async def test_a_given_reference_must_be_unique_and_others_still_need_one(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    at = datetime(2020 + YEARS_AHEAD, 1, 1, tzinfo=UTC)
    first, second = (
        await seed_order(db_session, placed_at=at),
        await seed_order(db_session, placed_at=at),
    )
    one_id = await seed_attempt(db_session, first, initiated_at=at, provider="manual")
    two_id = await seed_attempt(db_session, second, initiated_at=at, provider="manual")
    reference = f"OMT-{uuid.uuid4().hex[:8]}"
    await mfa_admin(client, db_session)
    assert _confirm(client, one_id, 1000, provider_reference=reference).status_code == 200
    duplicate = _confirm(client, two_id, 1000, provider_reference=reference)
    assert_problem(duplicate, 409, "PAYMENT_REFERENCE_MISMATCH")
    assert (await one(db_engine, PAYMENT_STATE, p=two_id)).status == "pending"


CONFIRM_AUDITS = """
    SELECT count(*) AS n FROM audit_logs
    WHERE entity_id = :p AND action = 'payment.manual_confirmation'
"""


@pytest.mark.parametrize("first_reference", [None, "OMT-first"])
async def test_a_paid_attempt_keeps_its_reference_and_flags_a_second_transfer(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession, first_reference: Any
) -> None:
    """VS-050 audit A-01: same or no reference is a no-op; another one is refused, unwritten."""
    at = datetime(2022 + YEARS_AHEAD, 1, 1, tzinfo=UTC)
    stored = f"{first_reference}-{uuid.uuid4().hex[:6]}" if first_reference else None
    order = await seed_order(db_session, placed_at=at)
    payment_id = await seed_attempt(db_session, order, initiated_at=at, provider="manual")
    await mfa_admin(client, db_session)
    paid = _confirm(client, payment_id, 1000, **({"provider_reference": stored} if stored else {}))
    assert paid.json()["outcome"] == "apply_paid", paid.text
    same = {"provider_reference": stored} if stored else {}
    for repeat in ({}, same):
        again = _confirm(client, payment_id, 1000, **repeat)
        assert (again.status_code, again.json()["outcome"]) == (200, "noop"), again.text
    second = _confirm(client, payment_id, 1000, provider_reference=f"Whish-{uuid.uuid4().hex[:6]}")
    assert_problem(second, 409, "PAYMENT_ALREADY_PAID_OTHER_REFERENCE")
    state = await one(db_engine, PAYMENT_STATE, p=payment_id)
    assert (state.status, state.provider_payment_id) == ("paid", stored)
    assert (await one(db_engine, CONFIRM_AUDITS, p=payment_id)).n == 3  # the 409 wrote none


async def test_another_payments_reference_on_a_paid_attempt_is_a_mismatch_not_a_transfer(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Money review: a reference another payment owns is never reported as a second transfer."""
    at = datetime(2023 + YEARS_AHEAD, 1, 1, tzinfo=UTC)
    first, second = (
        await seed_order(db_session, placed_at=at),
        await seed_order(db_session, placed_at=at),
    )
    one_id = await seed_attempt(db_session, first, initiated_at=at, provider="manual")
    two_id = await seed_attempt(db_session, second, initiated_at=at, provider="manual")
    own, other = f"WH-{uuid.uuid4().hex[:6]}", f"WH-{uuid.uuid4().hex[:6]}"
    await mfa_admin(client, db_session)
    assert _confirm(client, one_id, 1000, provider_reference=own).status_code == 200
    assert _confirm(client, two_id, 1000, provider_reference=other).status_code == 200
    reused = _confirm(client, one_id, 1000, provider_reference=other)
    assert_problem(reused, 409, "PAYMENT_REFERENCE_MISMATCH")
    assert (await one(db_engine, PAYMENT_STATE, p=one_id)).provider_payment_id == own


# --- A wrong amount, then the customer's retry ------------------------------------------------


async def test_a_wrong_amount_is_refused_recorded_as_a_late_capture_and_retried(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    customer = await create_user(db_session)
    placed_at = datetime.now(UTC) - timedelta(hours=1)
    order = await seed_order(db_session, placed_at=placed_at, user_id=customer.id, **PHONE)
    payment_id = await seed_attempt(db_session, order, initiated_at=placed_at, provider="manual")
    other = await seed_order(db_session, placed_at=placed_at)
    other_id = await seed_attempt(db_session, other, initiated_at=placed_at, provider="manual")
    reference = f"Whish-{uuid.uuid4().hex[:8]}"
    await mfa_admin(client, db_session)
    assert_problem(_confirm(client, payment_id, 999), 422, "PAYMENT_AMOUNT_MISMATCH")
    recorded = _capture(client, payment_id, 900, dashboard_reference=f" {reference} ")
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["outcome"] == "late_capture_and_fail"
    state = await one(db_engine, PAYMENT_STATE, p=payment_id)
    assert state.status == "failed" and state.captured_amount_cents == 900
    assert state.provider_payment_id == reference  # stored, so it is unique (ADR-049 d5)
    reused = _capture(client, other_id, 900, dashboard_reference=reference)
    assert_problem(reused, 409, "PAYMENT_REFERENCE_MISMATCH")
    assert_problem(_confirm(client, other_id, 1000, provider_reference=reference), 409)
    assert (await one(db_engine, PAYMENT_STATE, p=other_id)).status == "pending"
    login(client, customer.email)
    retried = _post(
        client,
        f"/api/v1/me/orders/{order.order_id}/payments",
        {},
        **{"Idempotency-Key": new_key()},
    )
    assert retried.status_code == 201, retried.text
    again = retried.json()["payment"]
    assert (again["provider"], again["next_step"], again["redirect_url"]) == ("manual", AWAIT, None)
    expires = _parse(retried.json()["order"]["hold_expires_at"])
    assert expires > datetime.now(UTC) + MANUAL_HOLD - timedelta(minutes=5)
    assert await alerts(db_engine, uuid.UUID(again["id"])) == {"manual_payment_due": 1}


async def test_a_manual_retry_on_an_order_without_a_phone_is_422(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """An STL-only order placed on another provider has no phone for the administrator."""
    customer = await create_user(db_session)
    placed_at = datetime.now(UTC) - timedelta(minutes=5)
    order = await seed_order(db_session, placed_at=placed_at, user_id=customer.id)
    await seed_attempt(db_session, order, initiated_at=placed_at, status="failed")  # mock
    login(client, customer.email)
    path = f"/api/v1/me/orders/{order.order_id}/payments"
    refused = _post(client, path, {}, **{"Idempotency-Key": new_key()})
    assert_problem(refused, 422, "CONTACT_PHONE_REQUIRED")
    assert (await one(db_engine, LATEST_PAYMENT, o=order.order_id)).provider == "mock"


# --- Offer checkout --------------------------------------------------------------------------


async def test_an_offer_checkout_needs_the_phone_and_is_paid_by_confirm(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    customer = await create_user(db_session)
    login(client, customer.email)
    product = await stl(db_session, price_cents=1000)
    offer = await seed_offer(
        db_session, user_id=customer.id, product_id=product, status="accepted", responds_by=None
    )
    path = f"/api/v1/me/offers/{offer}/checkout"
    body: dict[str, Any] = {"accept_terms": True, "accept_digital_final_sale": True}
    refused = _post(client, path, body, **{"Idempotency-Key": new_key()})
    assert_problem(refused, 422, "CONTACT_PHONE_REQUIRED")
    assert await rows(db_engine, customer.id) == Rows(0, 0, 0, 0, 0, 0)
    phone = random_phone()
    placed = _post(client, path, body | {"contact_phone": phone}, **{"Idempotency-Key": new_key()})
    assert placed.status_code == 201, placed.text
    order_id, payment = placed.json()["order"]["id"], placed.json()["payment"]
    assert (payment["provider"], payment["next_step"]) == ("manual", AWAIT)
    assert placed.json()["order"]["total"]["amount_cents"] == 800  # the agreed price
    assert (await one(db_engine, ORDER_ROW, o=order_id)).contact_phone_snapshot == phone
    placed_at = _parse(placed.json()["order"]["placed_at"])
    assert _parse(payment["hold_expires_at"]) == placed_at + MANUAL_HOLD
    notices = await one(db_engine, NOTICES, o=order_id, phone=phone)
    assert (notices.emails, notices.notices, notices.phone_leaks) == (1, 1, 0)
    assert await alerts(db_engine, uuid.UUID(payment["id"])) == {"manual_payment_due": 1}
    await mfa_admin(client, db_session)
    assert _confirm(client, payment["id"], 800).status_code == 200
    assert (await one(db_engine, ORDER_STATE, o=order_id)).lines == ["awaiting_delivery"]
    assert (await offer_state(db_engine, offer))["status"] == "paid"


async def test_another_provider_refuses_a_phone_on_an_offer_checkout(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: Any
) -> None:
    customer = await create_user(db_session)
    login(client, customer.email)
    product = await stl(db_session)
    offer = await seed_offer(
        db_session, user_id=customer.id, product_id=product, status="accepted", responds_by=None
    )
    monkeypatch.setattr(main_app.state, "payment_providers", {"mock": ManualPaymentProvider()})
    body = {"accept_terms": True, "accept_digital_final_sale": True}
    refused = _post(
        client,
        f"/api/v1/me/offers/{offer}/checkout",
        body | {"contact_phone": random_phone()},
        **{"Idempotency-Key": new_key()},
    )
    assert_problem(refused, 422, "INVALID_FULFILLMENT")
    assert await rows(db_engine, customer.id) == Rows(0, 0, 0, 0, 0, 0)


async def test_a_physical_delivery_order_is_paid_with_the_address_phone(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The plan's "physical" path: delivery already carries the phone the admin calls."""
    lamp = await physical(db_session)
    user_id = await _buyer(client, db_session, lamp)
    phone = random_phone()
    address = await seed_address(db_session, user_id, phone)
    placed = post_checkout(
        client, checkout_body(fulfillment_method="delivery", address_id=str(address))
    )
    assert placed.status_code == 201, placed.text
    order_id, payment = placed.json()["order"]["id"], placed.json()["payment"]
    assert payment["next_step"] == AWAIT
    assert (await one(db_engine, ORDER_ROW, o=order_id)).contact_phone_snapshot == phone
    total = placed.json()["order"]["total"]["amount_cents"]
    await mfa_admin(client, db_session)
    assert _confirm(client, payment["id"], total).status_code == 200
    state = await one(db_engine, ORDER_STATE, o=order_id)
    assert (state.status, state.lines) == ("in_progress", ["pending"])


async def test_the_alert_commits_with_the_order_even_if_the_second_transaction_fails(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """Money review F3: reconciliation skips `manual`, so a lost alert would never return."""

    async def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Tx2 lost")

    monkeypatch.setattr(checkout_api, "record_provider_reference", broken)
    with client_for(main_app, raise_server_exceptions=False) as client:
        monkeypatch.setattr(
            main_app.state, "payment_providers", {"manual": ManualPaymentProvider()}
        )
        user_id = await _buyer(client, db_session, await stl(db_session))
        failed = post_checkout(client, checkout_body(contact_phone=random_phone()))
    assert failed.status_code == 500
    async with db_engine.connect() as conn:
        payment = await conn.scalar(
            text(
                "SELECT p.id FROM payments p JOIN orders o ON o.id = p.order_id"
                " WHERE o.user_id = :u"
            ),
            {"u": user_id},
        )
    assert await alerts(db_engine, payment) == {"manual_payment_due": 1}


# --- The open-order cap (VS-050 audit Q-1, ADR-049 d14) --------------------------------------


async def _attempts(db: AsyncSession, order: Any, *steps: tuple[str, str]) -> uuid.UUID:
    """Attempts one minute apart, as (provider, status); returns the last one's id."""
    start = datetime.now(UTC) - timedelta(hours=1)
    last = uuid.uuid4()
    for minute, (provider, state) in enumerate(steps):
        at = start + timedelta(minutes=minute)
        last = await seed_attempt(db, order, initiated_at=at, provider=provider, status=state)
    return last


async def test_the_cap_counts_only_the_customers_unpaid_orders_whose_latest_attempt_is_manual(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    customer, stranger = await create_user(db_session), await create_user(db_session)
    placed_at = datetime.now(UTC) - timedelta(hours=2)

    async def order(user: uuid.UUID, *steps: tuple[str, str]) -> uuid.UUID:
        seeded = await seed_order(db_session, placed_at=placed_at, user_id=user, **PHONE)
        return await _attempts(db_session, seeded, *steps)

    await order(customer.id, ("mock", "failed"), ("manual", "pending"))  # counts
    waiting = await order(customer.id, ("manual", "pending"))  # counts
    for _ in range(2):  # latest is mock: twice, so counting the earliest attempt shows
        await order(customer.id, ("manual", "failed"), ("mock", "pending"))
    await order(stranger.id, ("manual", "pending"))  # another customer's
    login(client, customer.email)
    add_to_cart(client, await stl(db_session))
    before = await rows(db_engine, customer.id)
    async with setting(db_engine, "manual_max_open_orders", 2):
        refused = post_checkout(client, checkout_body(contact_phone=random_phone()))
        assert_problem(refused, 422, "MANUAL_ORDER_LIMIT_REACHED")
        assert refused.json()["max_open_orders"] == 2
        assert await rows(db_engine, customer.id) == before  # nothing written
        await mfa_admin(client, db_session)
        assert _confirm(client, waiting, 1000).json()["outcome"] == "apply_paid"
        login(client, customer.email)  # paying one order frees its place
        placed = post_checkout(client, checkout_body(contact_phone=random_phone()))
    assert placed.status_code == 201, placed.text


async def test_at_the_cap_a_retry_still_works_and_a_release_frees_a_place(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """ADR-049 d14: a retry adds no order; releasing an unpaid order frees its place."""
    customer = await create_user(db_session)
    placed_at = datetime.now(UTC) - timedelta(hours=1)
    order = await seed_order(db_session, placed_at=placed_at, user_id=customer.id, **PHONE)
    await _attempts(db_session, order, ("manual", "failed"))
    login(client, customer.email)
    add_to_cart(client, await stl(db_session))
    async with setting(db_engine, "manual_max_open_orders", 1):
        path = f"/api/v1/me/orders/{order.order_id}/payments"
        retried = _post(client, path, {}, **{"Idempotency-Key": new_key()})
        assert retried.status_code == 201, retried.text
        refused = post_checkout(client, checkout_body(contact_phone=random_phone()))
        assert_problem(refused, 422, "MANUAL_ORDER_LIMIT_REACHED")
        await mfa_admin(client, db_session)
        released = _post(
            client,
            f"/api/v1/admin/orders/{order.order_id}/release",
            {"reason": "customer said by phone they will not pay"},
        )
        assert released.status_code == 200, released.text
        login(client, customer.email)
        placed = post_checkout(client, checkout_body(contact_phone=random_phone()))
    assert placed.status_code == 201, placed.text


async def test_the_cap_applies_to_the_manual_provider_only(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: Any
) -> None:
    """A customer at the manual cap may still pay through another provider (ADR-049 d14)."""
    customer = await create_user(db_session)
    placed_at = datetime.now(UTC) - timedelta(hours=1)
    order = await seed_order(db_session, placed_at=placed_at, user_id=customer.id, **PHONE)
    await _attempts(db_session, order, ("manual", "pending"))
    monkeypatch.setattr(main_app.state, "payment_providers", {"mock": ManualPaymentProvider()})
    login(client, customer.email)
    add_to_cart(client, await stl(db_session))
    async with setting(db_engine, "manual_max_open_orders", 1):
        placed = post_checkout(client)
    assert placed.status_code == 201, placed.text
    assert placed.json()["payment"]["provider"] == "mock"


async def test_the_default_cap_of_three_refuses_an_offer_checkout_writing_nothing(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    customer = await create_user(db_session)
    placed_at = datetime.now(UTC) - timedelta(hours=2)
    for _ in range(3):
        seeded = await seed_order(db_session, placed_at=placed_at, user_id=customer.id, **PHONE)
        await _attempts(db_session, seeded, ("manual", "pending"))
    product = await stl(db_session, price_cents=1000)
    offer = await seed_offer(
        db_session, user_id=customer.id, product_id=product, status="accepted", responds_by=None
    )
    login(client, customer.email)
    before = await rows(db_engine, customer.id)
    body = {
        "accept_terms": True,
        "accept_digital_final_sale": True,
        "contact_phone": random_phone(),
    }
    refused = _post(
        client, f"/api/v1/me/offers/{offer}/checkout", body, **{"Idempotency-Key": new_key()}
    )
    assert_problem(refused, 422, "MANUAL_ORDER_LIMIT_REACHED")
    assert refused.json()["max_open_orders"] == 3
    assert await rows(db_engine, customer.id) == before
    assert (await offer_state(db_engine, offer))["status"] == "accepted"


# --- Reads -----------------------------------------------------------------------------------


async def test_the_admin_work_list_holds_only_live_manual_attempts(
    client: TestClient, db_session: AsyncSession
) -> None:
    at = datetime(2021 + YEARS_AHEAD, 1, 1, tzinfo=UTC)
    waiting = await seed_order(db_session, placed_at=at)
    paid = await seed_order(db_session, placed_at=at)
    other = await seed_order(db_session, placed_at=at)
    live = await seed_attempt(
        db_session, waiting, initiated_at=at + timedelta(minutes=1), provider="manual"
    )
    await seed_attempt(db_session, paid, initiated_at=at, provider="manual", status="paid")
    await seed_attempt(db_session, other, initiated_at=at, reference=False)  # mock, pending
    await mfa_admin(client, db_session)
    window = {"initiated_after": at.isoformat(), "initiated_before": (at + MANUAL_HOLD).isoformat()}
    listed = client.get("/api/v1/admin/payments", params={"awaiting_confirmation": "true"} | window)
    assert listed.status_code == 200, listed.text
    (item,) = listed.json()["items"]
    assert (item["id"], item["provider"], item["needs_manual_confirmation"]) == (
        str(live),
        "manual",
        True,
    )
    assert item["order_number"] == waiting.order_number
    assert _parse(item["hold_expires_at"]) == at + timedelta(minutes=1) + MANUAL_HOLD
    assert "buyer@example.com" not in listed.text
    everything = client.get("/api/v1/admin/payments", params=window)
    assert len(everything.json()["items"]) == 3


async def test_the_order_detail_shows_the_next_step_only_while_waiting(
    client: TestClient, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    customer = await create_user(db_session)
    placed_at = datetime.now(UTC) - timedelta(minutes=10)
    order = await seed_order(db_session, placed_at=placed_at, user_id=customer.id)
    payment_id = await seed_attempt(db_session, order, initiated_at=placed_at, provider="manual")
    login(client, customer.email)
    detail = client.get(f"/api/v1/me/orders/{order.order_id}").json()
    assert (detail["payment"]["provider"], detail["payment"]["next_step"]) == ("manual", AWAIT)
    assert _parse(detail["hold_expires_at"]) == placed_at + MANUAL_HOLD
    async with db_engine.begin() as conn:  # paid by hand meanwhile
        await conn.execute(
            text("UPDATE payments SET status = 'paid', verified_at = now() WHERE id = :p"),
            {"p": payment_id},
        )
    assert client.get(f"/api/v1/me/orders/{order.order_id}").json()["payment"]["next_step"] is None


async def test_the_manual_provider_takes_no_webhooks(
    client: TestClient, db_engine: AsyncEngine
) -> None:
    """Plan T9: 404 and nothing stored (VS-050 audit A-04)."""
    stored = "SELECT count(*) AS n FROM webhook_events"
    before = (await one(db_engine, stored)).n
    response = client.post("/api/v1/webhooks/payments/manual", content=b'{"event_id": "e-1"}')
    assert_problem(response, 404, "NOT_FOUND")
    assert (await one(db_engine, stored)).n == before
