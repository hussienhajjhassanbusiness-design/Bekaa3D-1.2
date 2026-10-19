"""A retry just before the hold deadline is not cancelled (VS-024 plan 6.2, D4): the hold
restarts from the newest attempt, so the release job waits a full hold after the retry,
and then still releases only on the provider's explicit `expired`."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from app.payments.infrastructure.release import release_stale
from app.payments.infrastructure.verification import verify_payment
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user, csrf, login
from tests.integration.payments.recovery_support import (
    HOLD,
    ORDER_STATE,
    PAYMENT_STATE,
    drop_alert_emails,  # noqa: F401
    factory,
    keyset_start,
    one,
    seed_attempt,
    seed_order,
)
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]

SECOND = timedelta(seconds=1)


async def _retried_a_second_before_the_deadline(
    db_session: AsyncSession,
) -> tuple[Any, uuid.UUID]:
    user = await create_user(db_session)
    placed = datetime.now(UTC) - HOLD + 3 * SECOND
    order = await seed_order(db_session, placed_at=placed, user_id=user.id)
    await seed_attempt(db_session, order, initiated_at=placed, status="failed")
    with client_for(main_app) as client:
        login(client, user.email)
        response = client.post(
            f"/api/v1/me/orders/{order.order_id}/payments",
            json={},
            headers=csrf(client) | {"Idempotency-Key": f"hold-{uuid.uuid4().hex}"},
        )
    assert response.status_code == 201, response.text
    return order, uuid.UUID(response.json()["payment"]["id"])


async def _release(engine: AsyncEngine, mock: MockPaymentProvider, order: Any, at: datetime) -> Any:
    return await release_stale(
        factory(engine), {"mock": mock}, now=at, start_after=keyset_start(order.placed_at)
    )


async def test_a_retry_just_before_the_hold_deadline_is_not_cancelled(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    order, payment_id = await _retried_a_second_before_the_deadline(db_session)
    placed = order.placed_at
    for at in (
        placed + HOLD + SECOND,
        placed + 2 * HOLD - SECOND,
        placed + 2 * HOLD + timedelta(hours=1),
    ):
        counts = await _release(db_engine, mock, order, at)
        assert counts["released"] == 0, (at - placed, counts)
        state = await one(db_engine, ORDER_STATE, o=order.order_id)
        assert (state.status, state.lines) == ("pending_payment", ["pending"]), at - placed
        assert (await one(db_engine, PAYMENT_STATE, p=payment_id)).status == "pending"
    await mock.simulate(payment_id, "paid")
    await verify_payment(factory(db_engine), {"mock": mock}, payment_id)
    paid = await one(db_engine, ORDER_STATE, o=order.order_id)
    assert (paid.status, paid.lines) == ("in_progress", ["awaiting_delivery"])


async def test_an_expired_retry_is_released_only_a_full_hold_after_it(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    """The provider says `expired` at once; the hold still runs from the retry (D4)."""
    order, payment_id = await _retried_a_second_before_the_deadline(db_session)
    await mock.simulate(payment_id, "expired")
    placed = order.placed_at
    for at in (placed + HOLD + SECOND, placed + 2 * HOLD - 5 * SECOND):
        assert (await _release(db_engine, mock, order, at))["released"] == 0, at - placed
        assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "pending_payment"
    assert (await _release(db_engine, mock, order, placed + 2 * HOLD + SECOND))["released"] == 1
    assert (await one(db_engine, ORDER_STATE, o=order.order_id)).status == "cancelled"
