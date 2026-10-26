"""VS-036 plan 8.1, read from the SQL sent: the badge hook on a payment path, with and
without a review row, and the review paths' own order (R_user -> products -> reviews)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.catalog.domain.enums import ProductType
from app.engagement.application.services.reviews import create_review, delete_review, edit_review
from app.engagement.infrastructure.reviews import CatalogReviewableProducts, SqlReviewStore
from app.ordering.public import lock_order_for_change, mark_order_paid, purchase_evidence
from app.payments.domain.enums import PaymentProvider
from app.payments.infrastructure.payments import SqlPaymentStore
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.catalog.storefront_support import seed_product, seed_refs
from tests.integration.deep_support import create_user
from tests.integration.ordering.test_lock_order import captured
from tests.integration.payments.support import NOW, seed_online_order

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _lock_steps(statements: list[str]) -> list[str]:
    """Each lock-taking statement, named by what it locks."""
    steps = []
    for s in statements:
        if "pg_advisory_xact_lock" in s:
            steps.append("R_user" if "hashtext" in s else "advisory")
        elif s.endswith(("FOR UPDATE", "FOR NO KEY UPDATE OF products")):
            steps.append(s.split(" FROM ")[1].split()[0])
        elif s.startswith(("INSERT INTO", "UPDATE")):
            steps.append(s.split()[0] + " " + s.split()[2 if s.startswith("INSERT") else 1])
    return steps


async def _locked_elsewhere(engine: AsyncEngine, review_id: uuid.UUID) -> bool:
    async with engine.connect() as conn:
        try:
            await conn.execute(
                text("SELECT id FROM reviews WHERE id = :r FOR UPDATE NOWAIT"), {"r": review_id}
            )
        except DBAPIError as exc:
            await conn.rollback()
            assert "55P03" in str(getattr(exc.orig, "sqlstate", "")) or "lock" in str(exc)
            return True
        await conn.rollback()
        return False


@pytest.mark.parametrize("with_review", [False, True])
async def test_the_payment_hook_locks_a_review_row_only_when_one_exists(
    with_review: bool, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    stl = (await seed_product(db_session, await seed_refs(db_session), type=ProductType.STL)).id
    order_id = await seed_online_order(db_session, user_id=user.id, stl_id=stl)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        payment = await SqlPaymentStore(session).insert_pending(
            order_id=order_id,
            provider=PaymentProvider.MOCK,
            amount_cents=1000,
            currency="USD",
            at=NOW,
        )
    review_id = None
    if with_review:
        async with factory() as session, session.begin():
            review_id = (
                await create_review(
                    SqlReviewStore(session),
                    CatalogReviewableProducts(session),
                    purchase_evidence(session),
                    user_id=user.id,
                    product_id=stl,
                    rating=5,
                    body=None,
                )
            ).id
    with captured(db_engine.sync_engine) as statements:
        async with factory() as session, session.begin():
            locked = await lock_order_for_change(session, order_id)
            assert locked is not None
            await SqlPaymentStore(session).lock(payment.id)
            await mark_order_paid(session, locked, at=datetime.now(UTC))
            held = await _locked_elsewhere(db_engine, review_id) if review_id else None
    steps = _lock_steps(statements)
    print(f"\nPAY with_review={with_review}", *steps, sep="\n  ")
    # The statement is sent either way; a row is locked, and evidence read, only with a row.
    assert steps[:4] == ["orders", "order_items", "payments", "UPDATE order_items"]
    assert steps.index("R_user") < steps.index("reviews")
    evidence = [s for s in statements if "UNION" in s and "FROM order_items" in s]
    assert bool(evidence) is with_review
    assert held is (True if with_review else None)
    if with_review:
        assert any(s.startswith("UPDATE reviews") for s in statements)


async def _review_path_steps(engine: AsyncEngine, work: Any) -> list[str]:
    with captured(engine.sync_engine) as statements:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s, s.begin():
            await work(s)
    return _lock_steps(statements)


async def test_review_create_edit_delete_lock_r_user_then_product_then_review(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    product = (await seed_product(db_session, await seed_refs(db_session))).id
    user = (await create_user(db_session)).id
    made: dict[str, uuid.UUID] = {}

    def ports(s: AsyncSession) -> tuple[Any, Any]:
        return SqlReviewStore(s), CatalogReviewableProducts(s)

    async def create(s: AsyncSession) -> None:
        review = await create_review(
            *ports(s), purchase_evidence(s), user_id=user, product_id=product, rating=4, body=None
        )
        made["id"] = review.id

    async def edit(s: AsyncSession) -> None:
        await edit_review(
            *ports(s),
            purchase_evidence(s),
            user_id=user,
            review_id=made["id"],
            rating=2,
            body=None,
            body_given=False,
        )

    async def delete(s: AsyncSession) -> None:
        await delete_review(*ports(s), user_id=user, review_id=made["id"])

    created = await _review_path_steps(db_engine, create)
    edited = await _review_path_steps(db_engine, edit)
    deleted = await _review_path_steps(db_engine, delete)
    for name, steps in (("CREATE", created), ("EDIT", edited), ("DELETE", deleted)):
        print(f"\n{name}", *steps, sep="\n  ")
    assert created == ["R_user", "products", "INSERT reviews", "UPDATE products"]
    assert edited == ["R_user", "products", "reviews", "UPDATE reviews", "UPDATE products"]
    assert deleted == ["R_user", "products", "reviews", "UPDATE reviews", "UPDATE products"]
    for steps in (created, edited, deleted):
        assert not {"orders", "order_items", "payments", "refunds", "carts"} & set(steps)
