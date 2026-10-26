"""VS-036 races on real Postgres (plan 6.3). Forced commit orders queue both racers on the
per-user lock `R_user`, held from outside; Postgres grants it in queue order, so the first
racer listed commits first. No run may deadlock or fail."""

import asyncio
import random
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.engagement.application.services.reviews import create_review, delete_review, edit_review
from app.engagement.domain.reviews import REVIEW_LOCK_NS
from app.engagement.infrastructure.reviews import CatalogReviewableProducts, SqlReviewStore
from app.fulfillment.application.cancel_lines import (
    CancelContext,
    CancelDeps,
    cancel_by_admin,
    cancel_by_customer,
)
from app.fulfillment.infrastructure.delivery_side import (
    SqlDeliveryNotices,
    SqlDeliveryOrders,
    SqlOrderPayments,
)
from app.identity.domain.enums import UserRole
from app.ordering.public import CancelReason, purchase_evidence
from app.payments.application.services.refunds import AuditContext, create_refund
from app.payments.domain.enums import RefundKind
from app.payments.domain.refunds import ItemFact
from app.payments.infrastructure.refund_side import refund_deps
from app.platform.public import SqlAuditWriter
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.concurrency.barrier import meet_or_fail
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import PASSWORD, async_client, create_user, running_app
from tests.integration.engagement.review_support import (
    REVIEWS,
    fresh_totals,
    product_of_line,
    stored_totals,
)
from tests.integration.fulfillment.cancel_support import blocks_of, refunds_of
from tests.integration.fulfillment.order_support import seed_physical_order
from tests.integration.payments.refund_support import paid_online, statuses

pytestmark = [
    pytest.mark.integration,
    pytest.mark.concurrency,
    pytest.mark.usefixtures("configured_app"),
]
REPEATS = 20
RACE_TIMEOUT_SECONDS = 20
Racer = Callable[[], Coroutine[Any, Any, str]]
_R_USER = "SELECT pg_advisory_xact_lock(:ns, hashtext(:u))"


@asynccontextmanager
async def _held_user_lock(engine: AsyncEngine, user_id: uuid.UUID) -> AsyncIterator[Any]:
    async with engine.connect() as conn:
        await conn.execute(text(_R_USER), {"ns": REVIEW_LOCK_NS, "u": str(user_id)})
        try:
            yield conn
        finally:
            await conn.rollback()


async def _advisory_waiters(engine: AsyncEngine, count: int, seconds: float = 10.0) -> None:
    """Block until `count` backends wait on an advisory lock (`R_user`), or fail."""
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        async with engine.connect() as conn:
            waiting = await conn.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                    " AND wait_event = 'advisory' AND datname = current_database()"
                )
            )
        if waiting is not None and waiting >= count:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"fewer than {count} transactions ever waited on R_user")


async def queued_on_user(engine: AsyncEngine, user_id: uuid.UUID, *racers: Racer) -> list[str]:
    """Each racer starts once the one before it waits on `R_user`; they commit in order."""
    async with _held_user_lock(engine, user_id) as held:
        tasks = []
        for n, racer in enumerate(racers, start=1):
            tasks.append(asyncio.create_task(racer()))
            await _advisory_waiters(engine, n)
        await held.rollback()
    return await asyncio.wait_for(asyncio.gather(*tasks), timeout=RACE_TIMEOUT_SECONDS)


async def together(*racers: Racer) -> list[str]:
    barrier = asyncio.Barrier(len(racers))

    async def run(racer: Racer) -> str:
        await meet_or_fail(barrier)
        return await racer()

    return await asyncio.wait_for(
        asyncio.gather(*(run(r) for r in racers)), timeout=RACE_TIMEOUT_SECONDS
    )


class World:
    def __init__(self, engine: AsyncEngine, admin: uuid.UUID) -> None:
        self.factory = async_sessionmaker(engine, expire_on_commit=False)
        self.admin = admin

    async def _tx(self, work: Callable[[AsyncSession], Coroutine[Any, Any, str]]) -> str:
        async with self.factory() as session, session.begin():
            return await work(session)

    def create(self, user_id: uuid.UUID, product_id: uuid.UUID, rating: int = 5) -> Racer:
        async def work(session: AsyncSession) -> str:
            review = await create_review(
                SqlReviewStore(session),
                CatalogReviewableProducts(session),
                purchase_evidence(session),
                user_id=user_id,
                product_id=product_id,
                rating=rating,
                body=None,
            )
            return f"created:{review.id}"

        return lambda: self._tx(work)

    def edit(self, user_id: uuid.UUID, review_id: uuid.UUID, rating: int) -> Racer:
        async def work(session: AsyncSession) -> str:
            await edit_review(
                SqlReviewStore(session),
                CatalogReviewableProducts(session),
                purchase_evidence(session),
                user_id=user_id,
                review_id=review_id,
                rating=rating,
                body=None,
                body_given=False,
            )
            return "edited"

        return lambda: self._tx(work)

    def delete(self, user_id: uuid.UUID, review_id: uuid.UUID) -> Racer:
        async def work(session: AsyncSession) -> str:
            await delete_review(
                SqlReviewStore(session),
                CatalogReviewableProducts(session),
                user_id=user_id,
                review_id=review_id,
            )
            return "deleted"

        return lambda: self._tx(work)

    def refund(self, order_id: uuid.UUID, line_id: uuid.UUID, amount: int) -> Racer:
        async def work(session: AsyncSession) -> str:
            await create_refund(
                refund_deps(session),
                order_id=order_id,
                kind=RefundKind.ADMIN,
                items=[ItemFact(line_id, amount)],
                reason="race",
                ctx=AuditContext(self.admin),
                at=datetime.now(UTC),
            )
            return "refunded"

        return lambda: self._tx(work)

    def _deps(self, session: AsyncSession) -> CancelDeps:
        return CancelDeps(
            SqlDeliveryOrders(session),
            SqlOrderPayments(session),
            SqlAuditWriter(session),
            SqlDeliveryNotices(session),
        )

    def _ctx(self, actor: uuid.UUID) -> CancelContext:
        return CancelContext(actor, datetime.now(UTC), None, None, None)

    def customer_cancel(self, order_id: uuid.UUID, user_id: uuid.UUID) -> Racer:
        async def work(session: AsyncSession) -> str:
            out = await cancel_by_customer(
                self._deps(session), order_id=order_id, ctx=self._ctx(user_id)
            )
            return f"cancelled:{out.order_status}"

        return lambda: self._tx(work)

    def admin_refusal(self, order_id: uuid.UUID) -> Racer:
        async def work(session: AsyncSession) -> str:
            out = await cancel_by_admin(
                self._deps(session),
                order_id=order_id,
                cancel_reason=CancelReason.REFUSED,
                ctx=self._ctx(self.admin),
            )
            return f"cancelled:{out.order_status}:{out.blocked}"

        return lambda: self._tx(work)


@pytest.fixture
async def world(db_engine: AsyncEngine, db_session: AsyncSession) -> World:
    return World(db_engine, (await create_user(db_session, role=UserRole.ADMIN)).id)


async def _one_review(engine: AsyncEngine, user_id: uuid.UUID, product_id: uuid.UUID) -> Any:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT id, rating, is_verified_purchase FROM reviews"
                    " WHERE user_id = :u AND product_id = :p AND deleted_at IS NULL"
                ),
                {"u": user_id, "p": product_id},
            )
        ).one()


# --- C9: review create vs a full refund of the same line, both commit orders --------------


@pytest.mark.parametrize("refund_first", [True, False])
async def test_c9_review_create_vs_refund_of_the_same_line(
    refund_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(REPEATS):
        order = await paid_online(db_session, stl=None)
        line = order.physical[0]
        product_id = await product_of_line(db_engine, line)
        refund = world.refund(order.order_id, line, 1000)
        review = world.create(order.user_id, product_id, 4)
        racers = (refund, review) if refund_first else (review, refund)
        results = await queued_on_user(db_engine, order.user_id, *racers)
        assert {r.split(":")[0] for r in results} == {"refunded", "created"}
        row = await _one_review(db_engine, order.user_id, product_id)
        assert row.is_verified_purchase is False, "the badge equals the evidence after both"
        assert await stored_totals(db_engine, product_id) == (Decimal("4.00"), 1)


# --- C10: review create vs a VS-031 cancellation, both commit orders ----------------------


@pytest.mark.parametrize("cancel_first", [True, False])
async def test_c10a_review_create_vs_customer_self_cancel(
    cancel_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(REPEATS):
        order = await seed_physical_order(
            db_session, payment_method="online", payment_status="paid", line_states=["pending"]
        )
        product_id = await product_of_line(db_engine, order.line_ids[0])
        cancel = world.customer_cancel(order.order_id, order.user_id)
        review = world.create(order.user_id, product_id, 3)
        racers = (cancel, review) if cancel_first else (review, cancel)
        results = await queued_on_user(db_engine, order.user_id, *racers)
        assert {r.split(":")[0] for r in results} == {"cancelled", "created"}
        assert (
            await _one_review(db_engine, order.user_id, product_id)
        ).is_verified_purchase is False
        assert [r.amount_cents for r in await refunds_of(db_engine, order.order_id)] == [1000]
        assert await statuses(db_engine, order.order_id) == ("cancelled", "refunded")
        assert await stored_totals(db_engine, product_id) == await fresh_totals(
            db_engine, product_id
        )


@pytest.mark.parametrize("cancel_first", [True, False])
async def test_c10b_review_create_vs_admin_cash_refusal(
    cancel_first: bool, world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Also proves `R_user` sits before cart -> phone: the refusal's block comes after it."""
    for _ in range(REPEATS):
        order = await seed_physical_order(
            db_session, fulfillment="pickup", line_states=["ready_for_pickup"]
        )
        product_id = await product_of_line(db_engine, order.line_ids[0])
        cancel = world.admin_refusal(order.order_id)
        review = world.create(order.user_id, product_id, 2)
        racers = (cancel, review) if cancel_first else (review, cancel)
        results = await queued_on_user(db_engine, order.user_id, *racers)
        assert sorted(r.split(":")[0] for r in results) == ["cancelled", "created"]
        assert "cancelled:cancelled:True" in results
        assert (
            await _one_review(db_engine, order.user_id, product_id)
        ).is_verified_purchase is False
        assert len(await blocks_of(db_engine, order.order_id)) == 1
        assert await refunds_of(db_engine, order.order_id) == []
        assert await stored_totals(db_engine, product_id) == await fresh_totals(
            db_engine, product_id
        )


# --- aggregates under concurrency -----------------------------------------------------------


async def test_c4_concurrent_edits_and_a_delete_keep_the_aggregates_exact(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    rng = random.Random(36)
    for _ in range(REPEATS):
        product = await seed_product(db_session, await seed_refs(db_session))
        authors = [(await create_user(db_session)).id for _ in range(6)]
        reviews = []
        for author in authors:
            created = await world.create(author, product.id, rng.randint(1, 5))()
            reviews.append((author, uuid.UUID(created.split(":")[1])))
        racers = [world.edit(a, r, rng.randint(1, 5)) for a, r in reviews[:-1]]
        racers.append(world.delete(*reviews[-1]))
        results = await together(*racers)
        assert sorted(results) == ["deleted"] + ["edited"] * 5
        assert await stored_totals(db_engine, product.id) == await fresh_totals(
            db_engine, product.id
        )
        assert (await stored_totals(db_engine, product.id))[1] == 5


async def test_c3_concurrent_creates_by_different_users_count_exactly(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    for _ in range(3):
        product = await seed_product(db_session, await seed_refs(db_session))
        authors = [(await create_user(db_session)).id for _ in range(20)]
        ratings = [1 + n % 5 for n in range(20)]
        results = await together(
            *(world.create(a, product.id, r) for a, r in zip(authors, ratings, strict=True))
        )
        assert all(r.startswith("created") for r in results)
        assert await stored_totals(db_engine, product.id) == (Decimal("3.00"), 20)


# --- C5: one user, two POSTs for one product: one 201, one 409 -----------------------------


async def _customer(app: FastAPI, db: AsyncSession) -> httpx.AsyncClient:
    user = await create_user(db)
    client = async_client(app)
    login = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return client


async def test_c5_a_duplicate_create_is_one_201_and_one_409_never_a_500(
    db_engine: AsyncEngine, db_session: AsyncSession, make_app: Callable[[], FastAPI]
) -> None:
    async with running_app(make_app) as app:
        for _ in range(REPEATS):
            product = await seed_product(db_session, await seed_refs(db_session))
            client = await _customer(app, db_session)
            try:
                headers = {"X-CSRF-Token": client.cookies["csrf_token"]}
                body = {"product_id": str(product.id), "rating": 5}
                barrier = asyncio.Barrier(2)

                async def post(
                    c: httpx.AsyncClient = client,
                    h: dict[str, str] = headers,
                    b: dict[str, Any] = body,
                    bar: asyncio.Barrier = barrier,
                ) -> httpx.Response:
                    await meet_or_fail(bar)
                    return await c.post(REVIEWS, json=b, headers=h)

                first, second = await asyncio.gather(post(), post())
            finally:
                await client.aclose()
            assert sorted([first.status_code, second.status_code]) == [201, 409]
            loser = first if first.status_code == 409 else second
            assert loser.json()["code"] == "REVIEW_ALREADY_EXISTS"
            assert await stored_totals(db_engine, product.id) == (Decimal("5.00"), 1)


# --- C11: without R_user, a create racing a refund leaves a badge that disagrees ---------


async def _lock_waiters(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'"
                " AND datname = current_database()"
            )
        )
    return int(found or 0)


async def _until(engine: AsyncEngine, waiting: int, done: asyncio.Task[str] | None) -> None:
    """Until `waiting` backends wait on a lock, or `done` finished; else fail."""
    deadline = asyncio.get_running_loop().time() + 10.0
    while asyncio.get_running_loop().time() < deadline:
        if (done is not None and done.done()) or await _lock_waiters(engine) >= waiting:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"fewer than {waiting} transactions ever waited on a lock")


async def test_c11_the_stale_badge_window_r_user_closes(
    world: World, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """The create reads evidence (true), then a held `users` row stalls its INSERT (FK).
    The refund then runs; its hook must wait for the create (R_user), or the badge stays
    true on a refunded line. The real code passes; with R_user removed this fails."""
    for _ in range(REPEATS):
        order = await paid_online(db_session, stl=None)
        line = order.physical[0]
        product_id = await product_of_line(db_engine, line)
        async with db_engine.connect() as held:
            await held.execute(
                text("SELECT id FROM users WHERE id = :u FOR UPDATE"), {"u": order.user_id}
            )
            create = asyncio.create_task(world.create(order.user_id, product_id, 5)())
            await _until(db_engine, 1, None)
            refund = asyncio.create_task(world.refund(order.order_id, line, 1000)())
            await _until(db_engine, 2, refund)
            await held.rollback()
        results = await asyncio.wait_for(
            asyncio.gather(create, refund), timeout=RACE_TIMEOUT_SECONDS
        )
        assert results[1] == "refunded" and results[0].startswith("created")
        row = await _one_review(db_engine, order.user_id, product_id)
        assert row.is_verified_purchase is False, "badge disagrees with a refunded line"
