"""VS-030 smoke (plan 6.6 E2): the refund routes exist, the schema is at PR C's backfill
head, and the obligations index the queue reads is there."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import app as main_app

pytestmark = [pytest.mark.smoke, pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

ROUTES = {
    ("post", "/api/v1/admin/orders/{order_id}/refunds"),
    ("get", "/api/v1/admin/refunds"),
    ("get", "/api/v1/admin/refunds/{refund_id}"),
    ("post", "/api/v1/admin/refunds/{refund_id}/settle"),
    ("post", "/api/v1/admin/refunds/{refund_id}/fail"),
    ("post", "/api/v1/admin/refunds/{refund_id}/void"),
    ("post", "/api/v1/admin/refunds/{refund_id}/reissue"),
    ("post", "/api/v1/admin/orders/{order_id}/chargebacks"),
    ("get", "/api/v1/admin/orders/{order_id}/chargebacks"),
    ("get", "/api/v1/admin/chargebacks/{chargeback_id}"),
    ("post", "/api/v1/admin/payments/{payment_id}/record-capture"),
}


def test_the_refund_routes_exist() -> None:
    with TestClient(main_app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert {(m, p) for p, ops in paths.items() for m in ops} >= ROUTES


async def test_the_schema_is_at_the_refund_head_with_the_obligations_index(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.connect() as conn:
        head = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        index = await conn.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_refunds_obligations'")
        )
    assert head == "80e56abf0969"
    assert index is not None and "refunds" in index
