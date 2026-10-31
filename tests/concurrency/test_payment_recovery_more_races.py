"""The rest of VS-024's race list on real Postgres (plan 6.3 #1-#3, #5-#8, #10, #12-#14),
plus #1 and #6 repeated 50 times. Racers meet at a barrier on their first `orders` lock;
a stagger picks who locks first, and the first locker holds the lock past the stagger."""

import asyncio
import contextvars
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.identity.domain.enums import UserRole
from app.ordering.infrastructure.orders import SqlOrderStore
from app.payments.domain.exceptions import ManualReleaseRefusedError
from app.payments.domain.outcome import Outcome, ProviderResult
from app.payments.infrastructure import manual, ordering_side, release
from app.payments.infrastructure.manual import confirm_payment_manually
from app.payments.infrastructure.payments import SqlPaymentAttempts
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.release import release_order_by_admin, release_stale
from app.payments.infrastructure.verification import (
    apply_provider_result,
    verify_event,
    verify_payment,
)
from app.platform.infrastructure.idempotency import SqlIdempotencyStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency import test_payment_retry_races as retry_races
from tests.concurrency.barrier import meet_or_fail
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.ordering.checkout_support import checkout_body, shop_open  # noqa: F401
from tests.integration.payments.recovery_support import (
    HOLD,
    ORDER_STATE,
    PAYMENT_STATE,
    YEARS_AHEAD,
    drop_alert_emails,  # noqa: F401
    factory,
    keyset_start,
    one,
    seed_attempt,
    seed_event,
    seed_order,
)
from tests.integration.payments.test_verification_recovery import NoStatus
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.concurrency,
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]
STAGGER, HELD = 0.15, 0.5
GRACE = timedelta(hours=24)
NO_STATUS: Any = {"mock": NoStatus()}
_racer: contextvars.ContextVar[int] = contextvars.ContextVar("racer", default=0)
_synced: contextvars.ContextVar[bool] = contextvars.ContextVar("synced", default=False)


async def _as(racer: int, work: Callable[[], Any]) -> Any:
    _racer.set(racer)
    return await work()


def _sync(monkeypatch: pytest.MonkeyPatch, order_id: uuid.UUID) -> None:
    """Every module's `lock_order_for_change` (and the retry's lock): first lock of the
    order per racer meets the other's; racer 2 waits; racer 1 then holds HELD seconds."""
    barrier = asyncio.Barrier(2)

    async def meet(locked_id: uuid.UUID) -> bool:
        if locked_id != order_id or _synced.get():
            return False
        _synced.set(True)
        await meet_or_fail(barrier)
        if _racer.get() == 2:
            await asyncio.sleep(STAGGER)
        return _racer.get() == 1

    for module in (ordering_side, release, manual):
        real = module.lock_order_for_change

        async def synced(session: Any, locked_id: uuid.UUID, _real: Any = real) -> Any:
            first = await meet(locked_id)
            locked = await _real(session, locked_id)
            if first:
                await asyncio.sleep(HELD)
            return locked

        monkeypatch.setattr(module, "lock_order_for_change", synced)
    real_owned = SqlOrderStore.lock_owned_order

    async def owned(self: SqlOrderStore, locked_id: uuid.UUID, user_id: uuid.UUID) -> Any:
        first = await meet(locked_id)
        locked = await real_owned(self, locked_id, user_id)
        if first:
            await asyncio.sleep(HELD)
        return locked

    monkeypatch.setattr(SqlOrderStore, "lock_owned_order", owned)


async def _statuses(engine: AsyncEngine, order_id: uuid.UUID) -> list[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT status FROM payments WHERE order_id = :o ORDER BY initiated_at, id"),
            {"o": order_id},
        )
        return list(rows.scalars())


def _epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 2, 1, tzinfo=UTC)


async def _customer_order(
    db: AsyncSession, user_id: uuid.UUID, mock: MockPaymentProvider, **attempt: Any
) -> Any:
    placed = datetime.now(UTC) - timedelta(minutes=5)
    order = await seed_order(db, placed_at=placed, user_id=user_id)
    payment_id = await seed_attempt(db, order, initiated_at=placed, mock=mock, **attempt)
    return order, payment_id


# --- #1 and #6, 50 times each ----------------------------------------------------------------


@pytest.mark.parametrize("run", range(50))
async def test_retry_against_retry_50_times(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    run: int,
) -> None:
    await retry_races.test_retry_against_retry_opens_one_attempt(
        db_engine, db_session, make_app, monkeypatch
    )


@pytest.mark.parametrize("first", ["release", "retry"])
@pytest.mark.parametrize("run", range(25))
async def test_retry_against_the_release_job_50_times(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    run: int,
    first: str,
) -> None:
    """25 runs of each ordering: 50 runs of #6."""
    await retry_races.test_retry_against_the_release_job(
        db_engine, db_session, mock, make_app, monkeypatch, first
    )


# --- #2: the same key twice at once -------------------------------------------------------------


async def test_retry_against_retry_with_the_same_key_opens_one_attempt(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = asyncio.Barrier(2)
    real_claim = SqlIdempotencyStore.claim

    async def claim(self: SqlIdempotencyStore, **kw: Any) -> Any:
        await meet_or_fail(barrier)
        if _racer.get() == 2:
            await asyncio.sleep(STAGGER)
        return await real_claim(self, **kw)

    monkeypatch.setattr(SqlIdempotencyStore, "claim", claim)
    key = f"same-{uuid.uuid4().hex}"
    async with running_app(make_app) as app:
        client, user_id = await retry_races._signed_in(app, db_session)
        order, _ = await _customer_order(db_session, user_id, mock, status="failed")

        async def post() -> httpx.Response:
            return await client.post(
                f"/api/v1/me/orders/{order.order_id}/payments",
                json={},
                headers={"X-CSRF-Token": client.cookies["csrf_token"], "Idempotency-Key": key},
            )

        try:
            first, second = await asyncio.gather(_as(1, post), _as(2, post))
        finally:
            await client.aclose()
    print(f"\nSAME KEY: {first.status_code} / {second.status_code} {second.text[:70]}")
    assert first.status_code == 201
    assert (second.status_code == 201 and second.headers.get("Idempotent-Replayed") == "true") or (
        second.status_code == 409 and second.json()["code"] == "IDEMPOTENCY_REQUEST_IN_PROGRESS"
    )
    assert await _statuses(db_engine, order.order_id) == ["failed", "pending"]


# --- #3: a lock-free writer cannot slip in between the read and the INSERT ------------------------


async def test_a_lock_free_live_insert_waits_behind_the_retrys_orders_lock(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plan's #3 has the rival commit while the retry is held: it cannot. Its INSERT
    takes FOR KEY SHARE on the `orders` row the retry holds FOR UPDATE, so it waits (here,
    until its lock_timeout). The index-to-409 path itself is the API test's in-transaction rival."""
    held, go_on = asyncio.Event(), asyncio.Event()
    real = SqlPaymentAttempts.open_retry_attempt

    async def held_at_insert(self: SqlPaymentAttempts, **kw: Any) -> Any:
        held.set()
        await go_on.wait()
        return await real(self, **kw)

    monkeypatch.setattr(SqlPaymentAttempts, "open_retry_attempt", held_at_insert)
    async with running_app(make_app) as app:
        client, user_id = await retry_races._signed_in(app, db_session)
        order, _ = await _customer_order(db_session, user_id, mock, status="failed")
        retry = asyncio.create_task(retry_races._retry(client, order.order_id)())
        try:
            await asyncio.wait_for(held.wait(), 10)
            rival_error: Exception | None = None
            try:
                async with db_engine.begin() as conn:
                    await conn.execute(text("SET LOCAL lock_timeout = '500ms'"))
                    await conn.execute(
                        text(
                            "INSERT INTO payments (order_id, provider, order_payment_method,"
                            " status, amount_cents, initiated_at)"
                            " VALUES (:o, 'mock', 'online', 'pending', 1000, now())"
                        ),
                        {"o": order.order_id},
                    )
            except DBAPIError as exc:
                rival_error = exc
            go_on.set()
            response = await asyncio.wait_for(retry, 10)
        finally:
            go_on.set()
            await client.aclose()
    assert rival_error is not None and "lock timeout" in str(rival_error).lower()
    assert response.status_code == 201, response.text
    assert await _statuses(db_engine, order.order_id) == ["failed", "pending"]


# --- #5: a late success on an old attempt during a retry ------------------------------------------


@pytest.mark.parametrize("first", ["retry", "webhook"])
async def test_retry_against_a_late_success_on_the_old_attempt(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    async with running_app(make_app) as app:
        client, user_id = await retry_races._signed_in(app, db_session)
        order, old = await _customer_order(db_session, user_id, mock, status="failed", state="paid")
        event_id = await seed_event(db_session, old, received_at=datetime.now(UTC))
        _sync(monkeypatch, order.order_id)

        async def webhook() -> Outcome | None:
            return await verify_event(factory(db_engine), {"mock": mock}, event_id)

        roles = (1, 2) if first == "retry" else (2, 1)
        try:
            response, outcome = await asyncio.gather(
                _as(roles[0], retry_races._retry(client, order.order_id)), _as(roles[1], webhook)
            )
        finally:
            await client.aclose()
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    print(f"\nLATE SUCCESS vs RETRY first={first}: {response.status_code} {outcome} {state.status}")
    assert response.status_code == 201, response.text
    assert outcome is Outcome.LATE_CAPTURE
    assert (await one(db_engine, PAYMENT_STATE, p=old)).late_captured_at is not None
    assert (state.status, await _statuses(db_engine, order.order_id)) == (
        "pending_payment",
        ["failed", "pending"],
    )


# --- #7, #8, #13: two verifiers of one payment ----------------------------------------------------


@pytest.mark.parametrize("first", ["reconcile", "webhook"])
async def test_reconcile_against_webhook_applies_once(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    order = await seed_order(db_session, placed_at=_epoch(1500))
    payment_id = await seed_attempt(
        db_session, order, initiated_at=_epoch(1500), mock=mock, state="paid"
    )
    event_id = await seed_event(db_session, payment_id, received_at=_epoch(1500))
    _sync(monkeypatch, order.order_id)

    async def reconcile() -> Outcome:
        return await verify_payment(factory(db_engine), {"mock": mock}, payment_id)

    async def webhook() -> Outcome | None:
        return await verify_event(factory(db_engine), {"mock": mock}, event_id)

    roles = (1, 2) if first == "reconcile" else (2, 1)
    outcomes = await asyncio.gather(_as(roles[0], reconcile), _as(roles[1], webhook))
    print(f"\nRECONCILE vs WEBHOOK first={first}: {outcomes}")
    assert sorted(outcomes) == sorted([Outcome.APPLY_PAID, Outcome.NOOP])
    async with db_engine.connect() as conn:
        emails = await conn.scalar(
            text(
                "SELECT count(*) FROM email_outbox WHERE template = 'order_payment_confirmed'"
                " AND payload->>'order_id' = :o"
            ),
            {"o": str(order.order_id)},
        )
    assert emails == 1


async def _confirm(engine: AsyncEngine, payment_id: uuid.UUID, admin_id: uuid.UUID) -> Outcome:
    async with async_sessionmaker(engine)() as session, session.begin():
        return await confirm_payment_manually(
            session,
            NO_STATUS,
            payment_id,
            admin_id=admin_id,
            provider_reference=f"dash_{payment_id.hex}",
            amount_cents=1000,
            currency="USD",
            reason="dashboard shows 10.00 USD captured",
        )


@pytest.mark.parametrize("first", ["confirm", "webhook"])
async def test_manual_confirm_against_webhook_applies_once(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    order = await seed_order(db_session, placed_at=_epoch(1501))
    payment_id = await seed_attempt(
        db_session, order, initiated_at=_epoch(1501), mock=mock, reference=False
    )
    _sync(monkeypatch, order.order_id)

    async def webhook() -> Outcome:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            return await apply_provider_result(
                session,
                payment_id,
                ProviderResult("paid", 1000, "USD"),
                source="webhook",
                actor_user_id=None,
            )

    roles = (1, 2) if first == "confirm" else (2, 1)
    outcomes = await asyncio.gather(
        _as(roles[0], lambda: _confirm(db_engine, payment_id, admin.id)), _as(roles[1], webhook)
    )
    print(f"\nCONFIRM vs WEBHOOK first={first}: {outcomes}")
    assert sorted(outcomes) == sorted([Outcome.APPLY_PAID, Outcome.NOOP])
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "paid"


async def test_two_admins_confirming_one_payment_apply_it_once(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_admin = await create_user(db_session, role=UserRole.ADMIN)
    second_admin = await create_user(db_session, role=UserRole.ADMIN)
    order = await seed_order(db_session, placed_at=_epoch(1502))
    payment_id = await seed_attempt(
        db_session, order, initiated_at=_epoch(1502), mock=mock, reference=False
    )
    _sync(monkeypatch, order.order_id)
    outcomes = await asyncio.gather(
        _as(1, lambda: _confirm(db_engine, payment_id, first_admin.id)),
        _as(2, lambda: _confirm(db_engine, payment_id, second_admin.id)),
    )
    print(f"\nTWO ADMINS: {outcomes}")
    assert list(outcomes) == [Outcome.APPLY_PAID, Outcome.NOOP]
    async with db_engine.connect() as conn:
        emails = await conn.scalar(
            text(
                "SELECT count(*) FROM email_outbox WHERE template = 'order_payment_confirmed'"
                " AND payload->>'order_id' = :o"
            ),
            {"o": str(order.order_id)},
        )
    assert emails == 1


# --- #10: manual release against a paid answer ----------------------------------------------------


@pytest.mark.parametrize("first", ["release", "paid"])
async def test_manual_release_against_a_paid_answer(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    at = _epoch(1503 if first == "release" else 1504)
    order = await seed_order(db_session, placed_at=at)
    payment_id = await seed_attempt(db_session, order, initiated_at=at, mock=mock)
    _sync(monkeypatch, order.order_id)

    async def released() -> Any:
        try:
            async with async_sessionmaker(db_engine)() as session, session.begin():
                return await release_order_by_admin(
                    session,
                    order.order_id,
                    admin_id=admin.id,
                    reason="dashboard shows no payment; customer unreachable",
                    events_reviewed=False,
                    now=at + HOLD + GRACE,
                )
        except ManualReleaseRefusedError as exc:
            return exc.reason

    async def paid() -> Outcome:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            return await apply_provider_result(
                session,
                payment_id,
                ProviderResult("paid", 1000, "USD"),
                source="webhook",
                actor_user_id=None,
            )

    roles = (1, 2) if first == "release" else (2, 1)
    result, outcome = await asyncio.gather(_as(roles[0], released), _as(roles[1], paid))
    state = await one(db_engine, ORDER_STATE, o=order.order_id)
    print(f"\nMANUAL RELEASE vs PAID first={first}: {result} {outcome} {state.status}")
    if first == "release":
        assert outcome is Outcome.LATE_CAPTURE and state.status == "cancelled"
    else:
        assert (result, outcome, state.status) == (
            "order_not_payable",
            Outcome.APPLY_PAID,
            "in_progress",
        )


# --- #12: release against a checkout of the same STL by the same customer -------------------------


@pytest.mark.usefixtures("shop_open")
@pytest.mark.parametrize("first", ["release", "checkout"])
async def test_release_against_a_checkout_of_the_same_stl(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    """The old order's `pending` line holds the STL. A checkout before the release is a 409;
    during it, the INSERT waits on the ownership index and succeeds once it commits."""
    stl = (await seed_product(db_session, await seed_refs(db_session), type=ProductType.STL)).id
    user = await create_user(db_session)
    placed = _epoch(1505 if first == "release" else 1506)
    old = await seed_order(db_session, placed_at=placed, user_id=user.id, stl_id=stl)
    await seed_attempt(db_session, old, initiated_at=placed, mock=mock, state="expired")
    in_tx_b, may_commit = asyncio.Event(), asyncio.Event()
    real_release = getattr(release, "release_unpaid_order")  # noqa: B009

    async def releasing(*args: Any, **kw: Any) -> Any:
        lines = await real_release(*args, **kw)
        in_tx_b.set()
        await asyncio.wait_for(may_commit.wait(), 10)
        return lines

    monkeypatch.setattr(release, "release_unpaid_order", releasing)
    async with running_app(make_app) as app:
        client = async_client(app)
        try:
            await client.post(
                "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
            )
            csrf = {"X-CSRF-Token": client.cookies["csrf_token"]}
            added = await client.post(
                "/api/v1/cart/items", json={"product_id": str(stl)}, headers=csrf
            )
            assert added.status_code == 200, added.text

            async def checkout() -> httpx.Response:
                return await client.post(
                    "/api/v1/checkout",
                    json=checkout_body(),
                    headers=csrf | {"Idempotency-Key": f"race-{uuid.uuid4().hex}"},
                )

            def run_release() -> asyncio.Task[dict[str, int]]:
                return asyncio.create_task(
                    release_stale(
                        factory(db_engine),
                        {"mock": mock},
                        now=placed + timedelta(hours=1),
                        start_after=keyset_start(placed),
                    )
                )

            if first == "checkout":
                response = await checkout()  # before the release starts
                may_commit.set()
                counts = await asyncio.wait_for(run_release(), 15)
            else:
                run = run_release()
                await asyncio.wait_for(in_tx_b.wait(), 10)
                buying = asyncio.create_task(checkout())
                await asyncio.sleep(HELD)  # the checkout's INSERT now waits on the index
                assert not buying.done()
                may_commit.set()
                counts = await asyncio.wait_for(run, 15)
                response = await asyncio.wait_for(buying, 15)
        finally:
            may_commit.set()
            await client.aclose()
    print(f"\nRELEASE vs CHECKOUT first={first}: {response.status_code} {counts}")
    assert counts["released"] == 1
    if first == "checkout":
        assert (response.status_code, response.json()["code"]) == (409, "PRODUCT_ALREADY_OWNED")
    else:
        assert response.status_code == 201, response.text
    assert (await one(db_engine, ORDER_STATE, o=old.order_id)).status == "cancelled"


# --- #14: reconcile against release; retry Tx2 against reconcile Tx B ---------------------------


@pytest.mark.parametrize("first", ["release", "reconcile"])
async def test_reconcile_against_release_has_one_outcome(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
) -> None:
    at = _epoch(1507 if first == "release" else 1508)
    order = await seed_order(db_session, placed_at=at)
    payment_id = await seed_attempt(db_session, order, initiated_at=at, mock=mock, state="expired")
    _sync(monkeypatch, order.order_id)

    async def released() -> dict[str, int]:
        return await release_stale(
            factory(db_engine),
            {"mock": mock},
            now=at + timedelta(hours=1),
            start_after=keyset_start(at),
        )

    async def reconcile() -> Outcome:
        return await verify_payment(factory(db_engine), {"mock": mock}, payment_id)

    roles = (1, 2) if first == "release" else (2, 1)
    counts, outcome = await asyncio.gather(_as(roles[0], released), _as(roles[1], reconcile))
    print(f"\nRECONCILE vs RELEASE first={first}: {counts} {outcome}")
    assert counts["released"] == 1
    assert outcome is (Outcome.NOOP if first == "release" else Outcome.MARK_EXPIRED)
    assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "expired"
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "cancelled"


async def test_retry_tx2_against_reconcile_tx_b_never_deadlocks(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: MockPaymentProvider,
    make_app: Callable[[], FastAPI],
) -> None:
    """Tx2 updates only the new attempt's row; Tx B takes orders, lines, then that row. The
    provider has already said `paid`, so whoever stores the reference first wins, once."""
    entered, go_on = asyncio.Event(), asyncio.Event()
    created: list[uuid.UUID] = []
    async with running_app(make_app) as app:
        provider = app.state.payment_providers["mock"]
        real_create = provider.create_payment

        async def create_then_wait(request: Any) -> Any:
            answer = await real_create(request)
            await mock.simulate(request.payment_id, "paid")
            created.append(request.payment_id)
            entered.set()
            await go_on.wait()
            return answer

        provider.create_payment = create_then_wait
        client, user_id = await retry_races._signed_in(app, db_session)
        order, _ = await _customer_order(db_session, user_id, mock, status="failed")
        retry = asyncio.create_task(retry_races._retry(client, order.order_id)())
        try:
            await asyncio.wait_for(entered.wait(), 10)
            reconcile = asyncio.create_task(
                verify_payment(factory(db_engine), {"mock": mock}, created[0])
            )
            await asyncio.sleep(0.05)
            go_on.set()
            response, outcome = await asyncio.wait_for(asyncio.gather(retry, reconcile), 15)
        finally:
            go_on.set()
            await client.aclose()
    print(f"\nRETRY TX2 vs RECONCILE: {response.status_code} {outcome}")
    assert response.status_code == 201, response.text
    assert outcome is Outcome.APPLY_PAID
    payment = await one(db_engine, PAYMENT_STATE, p=created[0])
    assert payment.status == "paid" and payment.provider_payment_id is not None
