"""VS-024 payment alerts on Postgres (plan 3.5): who receives them, what they carry, the
audit-row de-duplication, and that a failed delivery never rolls back the money write."""

import io
import json
import logging
import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.logging import configure_logging
from app.identity.domain.enums import UserRole
from app.identity.public import active_administrator_contacts
from app.payments.domain.alerts import AlertKind
from app.payments.domain.outcome import Outcome
from app.payments.infrastructure import alerts
from app.payments.infrastructure.alerts import SqlPaymentAlerts
from app.payments.infrastructure.verification import verify_payment
from tests.catalog_seed import retire_seeded_catalog_values  # noqa: F401
from tests.integration.deep_support import create_user
from tests.integration.payments.recovery_support import drop_alert_emails  # noqa: F401
from tests.integration.payments.test_verification import _factory
from tests.integration.payments.verification_support import (
    Seeded,
    mock_fixture,  # noqa: F401
    pending_payment,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("configured_app", "drop_alert_emails"),
]

REDIRECT = "https://pay.example/session-SECRET-REDIRECT"
# Exactly what a late-capture alert may carry (plan 3.5; VS-024 2.1).
PAYLOAD_KEYS = {
    "event",
    "kind",
    "payment_id",
    "order_id",
    "order_number",
    "reason",
    "attempt_status",
    "captured_amount_cents",
    "captured_currency",
    "expected_amount_cents",
}
DELIVERIES = """
    SELECT
      (SELECT count(*) FROM audit_logs WHERE entity_id = :p
         AND action = 'payment.alert_raised') AS raised,
      (SELECT count(*) FROM notifications WHERE user_id = :u
         AND payload->>'payment_id' = CAST(:p AS text)) AS notifications,
      (SELECT count(*) FROM email_outbox WHERE user_id = :u AND template = 'admin_payment_alert'
         AND payload->>'payment_id' = CAST(:p AS text)) AS emails
"""
LATE = """
    SELECT status, late_captured_at, captured_amount_cents, captured_currency,
      (SELECT count(*) FROM audit_logs WHERE entity_id = :p
         AND action = 'payment.late_capture') AS late_audits
    FROM payments WHERE id = :p
"""


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Through the application's own formatter (see test_ip_salt_never_leaks)."""
    buffer = io.StringIO()
    original = logging.StreamHandler
    monkeypatch.setattr(logging, "StreamHandler", lambda *_a, **_k: original(buffer))
    configure_logging()
    return buffer


async def _row(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).one()


async def _admins(db: AsyncSession) -> list[tuple[uuid.UUID, str]]:
    """At least one verified admin, then everyone who will be alerted."""
    await create_user(db, role=UserRole.ADMIN)
    contacts = await active_administrator_contacts(db)
    await db.commit()
    return contacts


async def _late_capture(engine: AsyncEngine, db: AsyncSession, mock: Any) -> Seeded:
    """A live attempt with a redirect URL that the provider says was underpaid."""
    seeded = await pending_payment(db, mock, total_cents=1000)
    await db.execute(
        text("UPDATE payments SET provider_metadata = CAST(:m AS jsonb) WHERE id = :p"),
        {"m": json.dumps({"redirect_url": REDIRECT}), "p": seeded.payment_id},
    )
    await db.commit()
    await mock.simulate(seeded.payment_id, "paid", 900)
    outcome = await verify_payment(_factory(engine), {"mock": mock}, seeded.payment_id)
    assert outcome is Outcome.LATE_CAPTURE_AND_FAIL
    return seeded


async def test_contacts_are_only_active_verified_live_administrators(
    db_session: AsyncSession,
) -> None:
    kept = await create_user(db_session, role=UserRole.ADMIN)
    unverified = await create_user(db_session, role=UserRole.ADMIN, verified=False)
    inactive = await create_user(db_session, role=UserRole.ADMIN, active=False)
    customer = await create_user(db_session)
    deleted = await create_user(db_session, role=UserRole.ADMIN)
    anonymized = await create_user(db_session, role=UserRole.ADMIN)
    await db_session.execute(
        text("UPDATE users SET deleted_at = now() WHERE id = :u"), {"u": deleted.id}
    )
    await db_session.execute(
        text("UPDATE users SET anonymized_at = now() WHERE id = :u"), {"u": anonymized.id}
    )
    await db_session.commit()
    contacts = dict(await active_administrator_contacts(db_session))
    assert contacts[kept.id] == kept.email
    for user in (unverified, inactive, customer, deleted, anonymized):
        assert user.id not in contacts


async def test_a_late_capture_alerts_every_admin_once_with_only_what_they_need(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: Any,
    captured_logs: io.StringIO,
) -> None:
    admins = await _admins(db_session)
    seeded = await _late_capture(db_engine, db_session, mock)
    for admin_id, _ in admins:
        row = await _row(db_engine, DELIVERIES, p=seeded.payment_id, u=admin_id)
        assert (row.raised, row.notifications, row.emails) == (1, 1, 1)
    async with db_engine.connect() as conn:
        payloads = [
            *(
                await conn.scalars(
                    text("SELECT payload FROM notifications WHERE payload->>'payment_id' = :p"),
                    {"p": str(seeded.payment_id)},
                )
            ),
            *(
                await conn.scalars(
                    text("SELECT payload FROM email_outbox WHERE payload->>'payment_id' = :p"),
                    {"p": str(seeded.payment_id)},
                )
            ),
            *(
                await conn.scalars(
                    text(
                        "SELECT after_data FROM audit_logs WHERE entity_id = :p"
                        " AND action = 'payment.alert_raised'"
                    ),
                    {"p": seeded.payment_id},
                )
            ),
        ]
    assert len(payloads) == 2 * len(admins) + 1
    expected = {
        "kind": "late_capture",
        "payment_id": str(seeded.payment_id),
        "order_id": str(seeded.order_id),
        "reason": "amount_mismatch",
        "attempt_status": "pending",
        "captured_amount_cents": 900,
        "captured_currency": "USD",
        "expected_amount_cents": 1000,
    }
    for payload in payloads:
        assert set(payload) <= PAYLOAD_KEYS and set(payload) >= PAYLOAD_KEYS - {"event"}
        assert expected.items() <= payload.items()
        flat = json.dumps(payload)
        assert REDIRECT not in flat and seeded.reference not in flat
        assert seeded.email not in flat
    logs = captured_logs.getvalue()
    assert "payment_alert" in logs and "late_capture" in logs
    for secret in (REDIRECT, seeded.reference, seeded.email, *(email for _, email in admins)):
        assert secret not in logs
    alert_lines = [line for line in logs.splitlines() if "payment_alert" in line]
    assert alert_lines and not any("amount" in line or "currency" in line for line in alert_lines)


async def test_the_alert_log_event_carries_ids_and_counts_only(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the formatter's redaction: the event itself never names an email or amount."""
    await _admins(db_session)
    events: list[dict[str, Any]] = []

    class Recorder:
        """The module's logger, replaced: structlog may have cached the real one."""

        def __getattr__(self, level: str) -> Any:
            async def record(event: str, **kw: Any) -> None:
                events.append({"event": event, "log_level": level.removeprefix("a"), **kw})

            return record

    monkeypatch.setattr(alerts, "logger", Recorder())
    seeded = await _late_capture(db_engine, db_session, mock)
    (alert,) = [e for e in events if e["event"] == "payment_alert"]
    assert set(alert) == {
        "event",
        "log_level",
        "kind",
        "payment_id",
        "order_id",
        "administrators",
        "failed_deliveries",
    }
    assert (alert["payment_id"], alert["order_id"]) == (
        str(seeded.payment_id),
        str(seeded.order_id),
    )
    assert isinstance(alert["administrators"], int) and alert["failed_deliveries"] == 0


async def test_an_alert_is_raised_once_per_payment_and_again_after_its_window(
    db_engine: AsyncEngine, db_session: AsyncSession, mock: Any
) -> None:
    await _admins(db_session)
    seeded = await pending_payment(db_session, mock)
    window = timedelta(hours=1)

    async def raise_(kind: AlertKind, dedupe: timedelta | None) -> bool:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            return await SqlPaymentAlerts(session).raise_alert(
                kind,
                payment_id=seeded.payment_id,
                order_id=seeded.order_id,
                details={},
                dedupe_window=dedupe,
            )

    assert await raise_(AlertKind.STUCK, window) is True
    assert await raise_(AlertKind.STUCK, window) is False
    assert await raise_(AlertKind.REFERENCE_UNKNOWN, None) is True  # another kind
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE audit_logs SET created_at = created_at - interval '2 hours'"
                " WHERE entity_id = :p AND action = 'payment.alert_raised'"
            ),
            {"p": seeded.payment_id},
        )
    assert await raise_(AlertKind.STUCK, window) is True
    assert await raise_(AlertKind.REFERENCE_UNKNOWN, None) is False  # once, ever


async def test_a_provider_alert_is_de_duplicated_per_provider(db_engine: AsyncEngine) -> None:
    provider = f"provider-{uuid.uuid4().hex}"

    async def raise_(name: str) -> bool:
        async with async_sessionmaker(db_engine)() as session, session.begin():
            return await SqlPaymentAlerts(session).raise_alert(
                AlertKind.PROVIDER_UNREACHABLE,
                payment_id=None,
                order_id=None,
                details={"provider": name},
                dedupe_window=timedelta(hours=1),
            )

    assert [await raise_(provider), await raise_(provider)] == [True, False]
    assert await raise_(f"{provider}-other") is True


def _breaking(target: str) -> Any:
    """A delivery that fails inside the database, aborting what it ran in."""

    async def broken(session: AsyncSession, *args: Any, **kwargs: Any) -> Any:
        await session.execute(text("SELECT 1 / 0"))

    if target == "notification":
        return broken

    class BrokenOutbox:
        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        async def add(self, **kwargs: Any) -> None:
            await broken(self._session)

    return BrokenOutbox


@pytest.mark.parametrize(
    ("target", "attribute"),
    [
        ("notification", "create_notification"),
        ("email", "SqlOutboxWriter"),
        ("recipients", "active_administrator_contacts"),
    ],
)
async def test_a_failing_alert_never_rolls_back_the_late_capture(
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    attribute: str,
) -> None:
    admins = await _admins(db_session)
    monkeypatch.setattr(
        alerts, attribute, _breaking("notification" if target == "recipients" else target)
    )
    seeded = await _late_capture(db_engine, db_session, mock)
    late = await _row(db_engine, LATE, p=seeded.payment_id)
    assert late.status == "failed" and late.late_captured_at is not None
    assert (late.captured_amount_cents, late.captured_currency, late.late_audits) == (
        900,
        "USD",
        1,
    )
    admin_id = admins[0][0]
    row = await _row(db_engine, DELIVERIES, p=seeded.payment_id, u=admin_id)
    expected = {
        "notification": (1, 0, 1),
        "email": (1, 1, 0),
        # The alert's own savepoint rolled back: no audit row, so the next run retries.
        "recipients": (0, 0, 0),
    }[target]
    assert (row.raised, row.notifications, row.emails) == expected
