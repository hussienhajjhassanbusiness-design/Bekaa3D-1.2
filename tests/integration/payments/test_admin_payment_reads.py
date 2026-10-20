"""`GET /api/v1/admin/payments` and `GET /api/v1/admin/payments/{id}` (VS-024 plan 2.2):
admin-only reads, a reversible keyset cursor and its edges, the late-capture listing and
its index, and no provider metadata, redirect URL, payload or customer email."""

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.identity.domain.enums import UserRole
from app.main import app as main_app
from app.payments.api.admin_payments import decode_cursor, encode_cursor
from app.payments.infrastructure.admin_reads import PaymentFilters, payment_page_query
from app.payments.infrastructure.providers.mock import MockPaymentProvider
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import client_for, create_user, login, mfa_admin
from tests.integration.payments.recovery_support import (
    HOLD,
    YEARS_AHEAD,
    SeededOrder,
    explain,
    seed_attempt,
    seed_event,
    seed_order,
)
from tests.integration.payments.test_verification_recovery import NoStatus
from tests.integration.payments.verification_support import mock_fixture  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

LIST = "/api/v1/admin/payments"
GRACE = timedelta(hours=24)
REDIRECT = "https://pay.example/session-ADMIN-READ-SECRET"


class QuietNoStatus(NoStatus):
    async def aclose(self) -> None:
        return None


def _b64(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _epoch(year: int) -> datetime:
    return datetime(year + YEARS_AHEAD, 8, 1, tzinfo=UTC)


async def _late(
    db: AsyncSession, mock: MockPaymentProvider, at: datetime, cents: int = 1000
) -> tuple[SeededOrder, uuid.UUID]:
    """An expired attempt that captured `cents` afterwards, with a stored redirect URL."""
    order = await seed_order(db, placed_at=at)
    payment_id = await seed_attempt(db, order, initiated_at=at, mock=mock, status="expired")
    await db.execute(
        text(
            "UPDATE payments SET late_captured_at = :t, captured_amount_cents = :c,"
            " captured_currency = 'USD', provider_metadata = CAST(:m AS jsonb) WHERE id = :p"
        ),
        {
            "t": at + timedelta(hours=1),
            "c": cents,
            "m": json.dumps({"redirect_url": REDIRECT}),
            "p": payment_id,
        },
    )
    await db.commit()
    return order, payment_id


def _window(at: datetime, **params: Any) -> dict[str, Any]:
    """This test's rows only: the shared database keeps every other test's payments."""
    return {
        "initiated_after": at.isoformat(),
        "initiated_before": (at + timedelta(days=1)).isoformat(),
    } | params


def _get(client: TestClient, path: str, **params: Any) -> httpx.Response:
    response: httpx.Response = client.get(path, params=params)
    return response


# --- Authorization -----------------------------------------------------------------------


async def test_both_reads_are_admin_only(
    db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    _, payment_id = await _late(db_session, mock, _epoch(1700))
    paths = [LIST, f"{LIST}/{payment_id}"]
    imaginary = f"{LIST}/x/definitely-not-a-route"
    with client_for(main_app) as client:
        anonymous = [client.get(p) for p in paths]
        login(client, (await create_user(db_session)).email)
        customer = [client.get(p) for p in [*paths, imaginary]]
    with client_for(main_app) as client:
        login(client, (await create_user(db_session, role=UserRole.ADMIN)).email)
        no_mfa = [client.get(p) for p in paths]

    def canonical(r: httpx.Response) -> tuple[int, str]:
        body = r.json()
        body.pop("request_id", None)
        body.pop("instance", None)
        return r.status_code, json.dumps(body, sort_keys=True)

    assert {(r.status_code, r.json()["code"]) for r in anonymous} == {(401, "AUTH_REQUIRED")}
    assert len({canonical(r) for r in customer}) == 1 and customer[0].status_code == 404
    assert {(r.status_code, r.json()["code"]) for r in no_mfa} == {(401, "MFA_REQUIRED")}


# --- The late-capture listing and the cursor ---------------------------------------------------


async def test_late_captures_page_oldest_first_with_a_reversible_cursor(
    db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = _epoch(1701)
    late = [(await _late(db_session, mock, at + timedelta(minutes=m)))[1] for m in range(5)]
    order = await seed_order(db_session, placed_at=at)
    await seed_attempt(db_session, order, initiated_at=at, mock=mock, status="failed")  # no capture
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        first = _get(client, LIST, **_window(at, late_captured="true", limit=2))
        second = _get(
            client,
            LIST,
            **_window(at, late_captured="true", limit=2, cursor=first.json()["next_cursor"]),
        )
        third = _get(
            client,
            LIST,
            **_window(at, late_captured="true", limit=2, cursor=second.json()["next_cursor"]),
        )
        exact = _get(client, LIST, **_window(at, late_captured="true", limit=5))
        everything = _get(client, LIST, **_window(at))
    pages = [first, second, third]
    assert all(r.status_code == 200 for r in pages), [r.text for r in pages]
    ids = [item["id"] for r in pages for item in r.json()["items"]]
    assert ids == [str(p) for p in late]
    assert [len(r.json()["items"]) for r in pages] == [2, 2, 1]
    assert third.json()["next_cursor"] is None
    assert exact.json()["next_cursor"] is None and len(exact.json()["items"]) == 5
    assert len(everything.json()["items"]) == 6
    item = first.json()["items"][0]
    assert (item["captured_amount_cents"], item["captured_currency"]) == (1000, "USD")
    assert item["late_captured_at"] is not None and item["order_number"].startswith("B3D-")
    cursor = first.json()["next_cursor"]
    moment, row_id = decode_cursor(cursor) or (None, None)
    assert row_id == late[1] and encode_cursor(moment, row_id) == cursor  # type: ignore[arg-type]
    for response in pages:
        flat = response.text
        assert REDIRECT not in flat and "provider_metadata" not in flat
        assert "buyer@example.com" not in flat and "redirect_url" not in flat


@pytest.mark.parametrize(
    "params",
    [
        {"cursor": "not-a-cursor"},
        {"cursor": _b64("2026-01-01T00:00:00+00:00|not-a-uuid")},
        {"cursor": _b64(f"2026-01-01T00:00:00|{uuid.UUID(int=0)}")},  # a naive time
        {"limit": 0},
        {"limit": 101},
        {"initiated_after": "2026-01-01T00:00:00"},  # no offset
        {"status": "nonsense"},
    ],
    ids=["garbage", "bad-uuid", "naive-time", "limit-0", "limit-101", "naive-filter", "status"],
)
async def test_bad_cursors_and_filters_are_422(
    db_session: AsyncSession, params: dict[str, Any]
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _get(client, LIST, **params)
    assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR"), (
        response.text
    )


async def test_status_is_a_repeatable_filter_and_limit_100_is_allowed(
    db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    at = _epoch(1702)
    kinds = {}
    for minute, status in enumerate(("pending", "failed", "expired")):
        order = await seed_order(db_session, placed_at=at)
        kinds[status] = await seed_attempt(
            db_session, order, initiated_at=at + timedelta(minutes=minute), status=status
        )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(
            LIST,
            params=[
                ("status", "failed"),
                ("status", "expired"),
                ("limit", "100"),
                *_window(at).items(),
            ],
        )
    assert response.status_code == 200, response.text
    assert [i["id"] for i in response.json()["items"]] == [
        str(kinds["failed"]),
        str(kinds["expired"]),
    ]


async def test_the_late_capture_listing_uses_its_index(db_engine: AsyncEngine) -> None:
    """A manual check (printed); asserted with seq scans off, as the plan's EXPLAIN tests."""
    query = payment_page_query(PaymentFilters(late_captured=True), after=None, limit=21)
    natural = await explain(db_engine, query, seqscan=True)
    forced = await explain(db_engine, query, seqscan=False)
    print(f"\nEXPLAIN late captures (planner's choice):\n{natural}")
    print(f"EXPLAIN late captures (enable_seqscan = off):\n{forced}")
    assert "ix_payments_late_captured" in forced, forced


# --- The detail --------------------------------------------------------------------------------


async def test_the_detail_shows_order_events_history_and_actions_without_secrets(
    db_session: AsyncSession, mock: MockPaymentProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    placed = datetime.now(UTC) - HOLD - GRACE - timedelta(minutes=5)
    order = await seed_order(db_session, placed_at=placed)
    payment_id = await seed_attempt(db_session, order, initiated_at=placed, mock=mock)
    await db_session.execute(
        text("UPDATE payments SET provider_metadata = CAST(:m AS jsonb) WHERE id = :p"),
        {"m": json.dumps({"redirect_url": REDIRECT}), "p": payment_id},
    )
    await db_session.commit()
    done = await seed_event(db_session, payment_id, received_at=placed - timedelta(minutes=1))
    await db_session.execute(
        text("UPDATE webhook_events SET processed_at = now() WHERE id = :e"), {"e": done}
    )
    await db_session.commit()
    event = await seed_event(db_session, payment_id, received_at=placed)
    young_order = await seed_order(db_session, placed_at=datetime.now(UTC))
    young = await seed_attempt(db_session, young_order, initiated_at=datetime.now(UTC), mock=mock)
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        before_grace = _get(client, f"{LIST}/{young}")
        status_provider = _get(client, f"{LIST}/{payment_id}")
        monkeypatch.setattr(main_app.state, "payment_providers", {"mock": QuietNoStatus()})
        manual = _get(client, f"{LIST}/{payment_id}")
        unknown = _get(client, f"{LIST}/{uuid.uuid4()}")
    assert status_provider.status_code == 200, status_provider.text
    body = status_provider.json()
    assert body["payment"]["id"] == str(payment_id)
    assert (
        body["payment"]["unprocessed_event_count"],
        body["payment"]["needs_manual_confirmation"],
    ) == (1, False)
    assert body["order"]["order_number"] == order.order_number
    assert datetime.fromisoformat(body["order"]["hold_expires_at"]) == placed + HOLD
    assert (
        datetime.fromisoformat(body["order"]["manual_release_available_at"])
        == placed + HOLD + GRACE
    )
    assert [e["id"] for e in body["events"]] == [str(done), str(event)]
    assert all("payload" not in e for e in body["events"])
    assert body["available_actions"] == ["reconcile", "release_order"]
    assert before_grace.json()["available_actions"] == ["reconcile"]
    assert manual.json()["available_actions"] == ["confirm", "release_order"]
    for response in (status_provider, manual):
        assert REDIRECT not in response.text and "buyer@example.com" not in response.text
        assert "provider_metadata" not in response.text
    assert unknown.status_code == 404


async def test_the_detail_history_is_the_payments_audit_rows_newest_first(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: MockPaymentProvider
) -> None:
    order, payment_id = await _late(db_session, mock, _epoch(1703))
    async with db_engine.begin() as conn:
        for action in ("payment.failed", "payment.late_capture"):
            await conn.execute(
                text(
                    "INSERT INTO audit_logs (action, entity_type, entity_id, after_data)"
                    " VALUES (:a, 'payment', :p, CAST(:d AS jsonb))"
                ),
                {"a": action, "p": payment_id, "d": json.dumps({"order_id": str(order.order_id)})},
            )
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        body = _get(client, f"{LIST}/{payment_id}").json()
    assert [h["action"] for h in body["history"]] == ["payment.late_capture", "payment.failed"]
    hold_expires = datetime.fromisoformat(body["order"]["hold_expires_at"])
    assert hold_expires == _epoch(1703) + HOLD
    assert body["available_actions"] == ["reconcile", "release_order"]  # 2003: grace passed
