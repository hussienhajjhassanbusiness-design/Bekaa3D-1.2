"""VS-035 / F-128, BR-114: the Bring Your Idea funnel, counted by submission-date cohort."""

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.integrations.storage.local import LocalStorage
from app.main import app as main_app
from tests.integration.deep_support import assert_problem, client_for, mfa_admin, unique_email
from tests.integration.engagement.custom_request_support import seed_lead

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

FUNNEL = "/api/v1/admin/analytics/custom-requests/funnel"
SPAN = timedelta(days=10)


def _window() -> datetime:
    """A random far-past cohort, so other tests' leads never fall inside it."""
    start = datetime(1990, 1, 1, tzinfo=UTC)
    return start + timedelta(seconds=random.randrange(600_000_000))


def _reached(stage: str, at: datetime, amount: int | None = None) -> dict[str, Any]:
    """The columns a lead carries once it has reached `stage` through the API."""
    later = at + timedelta(hours=1)
    contacted = {"contacted_at": later}
    quoted = contacted | {"quoted_at": later, "quoted_amount_cents": amount, "currency": "USD"}
    stages: dict[str, dict[str, Any]] = {
        "new": {},
        "contacted": {"status": "contacted"} | contacted,
        "lost_contacted": {"status": "lost", "outcome": "lost", "closed_at": later} | contacted,
        "quoted": {"status": "quoted"} | quoted,
        "lost_quoted": {"status": "lost", "outcome": "lost", "closed_at": later} | quoted,
        "in_progress": {"status": "in_progress", "outcome": "won"} | quoted,
        "closed": {"status": "closed", "outcome": "won", "completed_at": later, "closed_at": later}
        | quoted,
    }
    return stages[stage]


async def test_funnel_counts_match_seeded_data_and_respect_the_cohort_bounds(
    db_session: AsyncSession, db_engine: AsyncEngine, tmp_path: Path
) -> None:
    """Done-when: the funnel shows won and lost counts (F-128)."""
    storage = LocalStorage(tmp_path)
    base = _window()
    inside = [
        ("new", base, None),
        ("contacted", base + timedelta(days=1), None),
        ("lost_contacted", base + timedelta(days=2), None),
        ("quoted", base + timedelta(days=3), 500),
        ("lost_quoted", base + timedelta(days=4), 700),
        ("in_progress", base + timedelta(days=5), 1_000),
        ("closed", base + SPAN - timedelta(microseconds=1), 2_000),
    ]
    outside = [
        ("closed", base + SPAN, 99_999),
        ("lost_quoted", base - timedelta(microseconds=1), 88_888),
    ]
    for stage, at, amount in inside + outside:
        await seed_lead(
            db_engine,
            storage,
            email=unique_email("funnel"),
            submitted_at=at,
            **_reached(stage, at, amount),
        )
    params = {"from": base.isoformat(), "to": (base + SPAN).isoformat()}
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(FUNNEL, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert datetime.fromisoformat(body.pop("from")) == base
    assert datetime.fromisoformat(body.pop("to")) == base + SPAN
    assert body == {
        "submitted": 7,
        "contacted": 6,
        "quoted": 4,
        "won": 2,
        "lost": 2,
        "open": 3,
        "quoted_total_cents": 4_200,
        "won_total_cents": 3_000,
        "currency": "USD",
    }


async def test_an_empty_cohort_is_all_zeros(db_session: AsyncSession) -> None:
    base = _window()
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        body = client.get(
            FUNNEL, params={"from": base.isoformat(), "to": (base + SPAN).isoformat()}
        ).json()
    assert {k: v for k, v in body.items() if k not in {"from", "to"}} == {
        "submitted": 0,
        "contacted": 0,
        "quoted": 0,
        "won": 0,
        "lost": 0,
        "open": 0,
        "quoted_total_cents": 0,
        "won_total_cents": 0,
        "currency": "USD",
    }


async def test_the_default_range_is_the_last_90_days(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        before = datetime.now(UTC)
        body = client.get(FUNNEL).json()
        only_to = client.get(FUNNEL, params={"to": "2026-01-31T00:00:00Z"}).json()
    upper = datetime.fromisoformat(body["to"])
    assert before <= upper <= datetime.now(UTC)
    assert upper - datetime.fromisoformat(body["from"]) == timedelta(days=90)
    assert datetime.fromisoformat(only_to["from"]) == datetime(2025, 11, 2, tzinfo=UTC)


@pytest.mark.parametrize(
    "params",
    [
        pytest.param({"from": "2026-01-01T00:00:00"}, id="naive-from"),
        pytest.param({"to": "2026-01-01T00:00:00"}, id="naive-to"),
        pytest.param({"from": "2026-01-02T00:00Z", "to": "2026-01-02T00:00Z"}, id="empty"),
        pytest.param({"from": "2026-01-03T00:00Z", "to": "2026-01-02T00:00Z"}, id="reversed"),
        pytest.param({"from": "2025-01-01T00:00Z", "to": "2026-01-03T00:00Z"}, id="367-days"),
        pytest.param({"from": "2999-01-01T00:00Z"}, id="from-after-now"),
        pytest.param({"from": "not-a-date"}, id="garbage"),
        pytest.param({"to": "0001-01-02T00:00Z"}, id="default-from-overflows"),
    ],
)
async def test_a_bad_range_is_422(db_session: AsyncSession, params: dict[str, str]) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert_problem(client.get(FUNNEL, params=params), 422, "VALIDATION_ERROR")


async def test_a_366_day_range_is_allowed(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        params = {"from": "2025-01-01T00:00Z", "to": "2026-01-02T00:00Z"}
        assert client.get(FUNNEL, params=params).status_code == 200
