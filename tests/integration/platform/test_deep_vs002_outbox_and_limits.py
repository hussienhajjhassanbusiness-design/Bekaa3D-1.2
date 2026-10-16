"""VS-002 deep edge cases: the outbox worker, its schedule, and the core rate limiter.

The worker tests drive `dispatch_outbox` directly with a recording provider,
so delivery is observed exactly rather than inferred from row state. Other
tests' pending rows share the table, so every assertion is scoped to this
test's own recipients and the dispatch loops run until *those* are done.
"""

import asyncio
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import redis.asyncio as redis_asyncio
import redis.exceptions
import time_machine
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.integrations.captcha.fake import FAKE_CAPTCHA_PASS
from app.jobs import outbox as outbox_job
from app.jobs.purge_unverified import purge_unverified_accounts
from app.jobs.registry import CRON_JOBS, FUNCTIONS
from app.platform.domain.entities import REDACTED
from app.platform.domain.enums import OutboxStatus
from app.platform.infrastructure.models import EmailOutboxModel
from tests.integration.deep_support import (
    PASSWORD,
    assert_problem,
    async_client,
    fresh_ip,
    running_app,
    unique_email,
)

REGISTER = "/api/v1/auth/register"


class RecordingProvider:
    """Stands in for the email port. Fails for chosen recipients, and yields to
    the event loop inside `send` so concurrent workers genuinely interleave."""

    def __init__(self, fail_for: set[str] | None = None, error: str = "provider down") -> None:
        self.sent: list[str] = []
        self.fail_for = fail_for or set()
        self.error = error

    async def send(self, *, to: str, template: str, payload: dict[str, Any]) -> None:
        await asyncio.sleep(0.002)
        if to in self.fail_for:
            raise RuntimeError(self.error.format(**payload) if "{" in self.error else self.error)
        self.sent.append(to)


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


async def _enqueue(
    db: AsyncSession, count: int, *, send_after: datetime | None = None
) -> list[str]:
    recipients = [unique_email("outbox") for _ in range(count)]
    for recipient in recipients:
        row = EmailOutboxModel(
            recipient_email=recipient,
            template="verification_email",
            payload={"token": f"raw-{uuid.uuid4().hex}", "n": recipient},
        )
        if send_after is not None:
            row.send_after = send_after
        db.add(row)
    await db.commit()
    return recipients


async def _rows(db: AsyncSession, recipients: list[str]) -> list[EmailOutboxModel]:
    db.expire_all()
    result = await db.scalars(
        select(EmailOutboxModel).where(EmailOutboxModel.recipient_email.in_(recipients))
    )
    return list(result.all())


# --------------------------------------------------------------------------
# Concurrency: N workers never send one row twice
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.concurrency
@pytest.mark.parametrize("workers", [2, 6])
async def test_concurrent_workers_deliver_every_message_exactly_once(
    workers: int,
    db_engine: AsyncEngine,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingProvider()
    monkeypatch.setattr(outbox_job, "get_email_provider", lambda _settings: provider)
    mine = await _enqueue(db_session, 40)

    for _ in range(100):
        await asyncio.gather(*(outbox_job.dispatch_outbox(_ctx(db_engine)) for _ in range(workers)))
        if all(row.status is OutboxStatus.SENT for row in await _rows(db_session, mine)):
            break

    delivered = [to for to in provider.sent if to in set(mine)]
    assert sorted(delivered) == sorted(mine), "a message was lost or delivered twice"
    for row in await _rows(db_session, mine):
        assert row.status is OutboxStatus.SENT
        assert row.sent_at is not None
        assert set(row.payload.values()) == {REDACTED}


@pytest.mark.integration
async def test_a_message_scheduled_for_later_is_not_sent_early(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingProvider()
    monkeypatch.setattr(outbox_job, "get_email_provider", lambda _settings: provider)
    later = datetime.now(UTC) + timedelta(hours=1)
    mine = await _enqueue(db_session, 1, send_after=later)
    for _ in range(30):
        if await outbox_job.dispatch_outbox(_ctx(db_engine)) == 0:
            break
    assert mine[0] not in provider.sent
    [row] = await _rows(db_session, mine)
    assert row.status is OutboxStatus.PENDING


# --------------------------------------------------------------------------
# Backoff: the exact schedule, pinned in time
# --------------------------------------------------------------------------


async def _drain(engine: AsyncEngine) -> None:
    for _ in range(50):
        if await outbox_job.dispatch_outbox(_ctx(engine)) == 0:
            return


@pytest.mark.integration
async def test_the_backoff_schedule_is_60_120_240_480_then_failed(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    t0 = datetime.now(UTC).replace(microsecond=0)
    mine = await _enqueue(db_session, 1, send_after=t0)
    provider = RecordingProvider(fail_for=set(mine))
    monkeypatch.setattr(outbox_job, "get_email_provider", lambda _settings: provider)

    moment = t0
    for attempt, delay in enumerate([60, 120, 240, 480], start=1):
        with time_machine.travel(moment, tick=False):
            await _drain(db_engine)
        [row] = await _rows(db_session, mine)
        assert (row.attempt_count, row.status) == (attempt, OutboxStatus.PENDING)
        assert row.send_after == moment + timedelta(seconds=delay)
        # One second early: not due, nothing may change.
        with time_machine.travel(row.send_after - timedelta(seconds=1), tick=False):
            await _drain(db_engine)
        [early] = await _rows(db_session, mine)
        assert early.attempt_count == attempt
        moment = row.send_after

    with time_machine.travel(moment, tick=False):
        await _drain(db_engine)
    [row] = await _rows(db_session, mine)
    assert (row.attempt_count, row.status) == (5, OutboxStatus.FAILED)
    assert set(row.payload.values()) == {REDACTED}

    with time_machine.travel(moment + timedelta(days=30), tick=False):
        await _drain(db_engine)
    [still] = await _rows(db_session, mine)
    assert still.attempt_count == 5, "a failed message must never be retried again"


@pytest.mark.integration
async def test_a_provider_error_cannot_smuggle_the_raw_token_past_redaction(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    t0 = datetime.now(UTC)
    mine = await _enqueue(db_session, 1, send_after=t0)
    provider = RecordingProvider(fail_for=set(mine), error="400 Bad Request: token={token}")
    monkeypatch.setattr(outbox_job, "get_email_provider", lambda _settings: provider)
    moment = t0
    for _ in range(5):
        with time_machine.travel(moment, tick=False):
            await _drain(db_engine)
        [row] = await _rows(db_session, mine)
        moment = row.send_after
    [row] = await _rows(db_session, mine)
    assert row.status is OutboxStatus.FAILED
    assert "raw-" not in (row.last_error or "")


@pytest.mark.integration
async def test_an_oversized_provider_error_is_truncated(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = await _enqueue(db_session, 1, send_after=datetime.now(UTC) - timedelta(seconds=1))
    provider = RecordingProvider(fail_for=set(mine), error="E" * 100_000)
    monkeypatch.setattr(outbox_job, "get_email_provider", lambda _settings: provider)
    await _drain(db_engine)
    [row] = await _rows(db_session, mine)
    assert row.last_error is not None and len(row.last_error) == 1000


# --------------------------------------------------------------------------
# The job registry against SRS 23
# --------------------------------------------------------------------------


def test_dispatch_outbox_runs_every_minute_and_at_startup() -> None:
    [job] = [j for j in CRON_JOBS if j.coroutine is outbox_job.dispatch_outbox]
    assert job.run_at_startup is True
    assert job.second == 0 and job.minute is None and job.hour is None


def test_the_purge_runs_once_a_day() -> None:
    # By coroutine, not a "purge" substring: VS-046 added a second purge job.
    [job] = [j for j in CRON_JOBS if j.coroutine is purge_unverified_accounts]
    assert job.hour is not None and job.minute is not None and job.second == 0


def test_every_srs_job_name_is_registered() -> None:
    """BUG-23: SRS 23 named the purge purge_unverified_users while the code, the
    plan and the settings registry said purge_unverified_accounts. The SRS now
    uses the code's name; every registered job must be one the SRS lists, so
    the two cannot drift apart again."""
    srs = (Path(__file__).resolve().parents[3] / "docs" / "SRS.md").read_text(encoding="utf-8")
    srs_jobs = set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|", srs, re.M))
    names = {function.__qualname__ for function in FUNCTIONS}
    assert {"dispatch_outbox", "purge_unverified_accounts"} <= names
    assert names <= srs_jobs, names - srs_jobs


# --------------------------------------------------------------------------
# The core rate limiter
# --------------------------------------------------------------------------


class _ExpireFailsOnce:
    """A Redis client whose first EXPIRE fails, as a crash or network blip
    between INCR and EXPIRE would."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.failed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    async def expire(self, *args: Any, **kwargs: Any) -> Any:
        if not self.failed:
            self.failed = True
            raise redis.exceptions.ConnectionError("simulated blip between INCR and EXPIRE")
        return await self._real.expire(*args, **kwargs)


async def _redis() -> Any:
    return redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_blip_between_incr_and_expire_cannot_leave_an_immortal_counter(
    make_app: Callable[[], FastAPI],
) -> None:
    ip = fresh_ip()
    async with running_app(make_app) as app:
        app.state.redis = _ExpireFailsOnce(app.state.redis)
        async with async_client(app, ip=ip) as client:
            await client.post(
                REGISTER,
                json={
                    "captcha_token": FAKE_CAPTCHA_PASS,
                    "email": unique_email(),
                    "password": PASSWORD,
                },
            )
    probe = await _redis()
    try:
        ttl = await probe.ttl(f"ratelimit:auth:register:{ip}")
    finally:
        await probe.aclose()
    assert ttl > 0, f"counter TTL is {ttl} (-1 means it never expires)"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_counter_already_left_without_a_ttl_is_healed_on_its_next_hit(
    make_app: Callable[[], FastAPI],
) -> None:
    """BUG-12, the other half: a key stranded with no TTL (by the old
    two-call code, or anything else) gets one the next time it is counted,
    instead of limiting that IP forever."""
    ip = fresh_ip()
    key = f"ratelimit:auth:register:{ip}"
    probe = await _redis()
    try:
        await probe.set(key, 3)
        assert await probe.ttl(key) == -1
        async with running_app(make_app) as app, async_client(app, ip=ip) as client:
            response = await client.post(
                REGISTER,
                json={
                    "captcha_token": FAKE_CAPTCHA_PASS,
                    "email": unique_email(),
                    "password": PASSWORD,
                },
            )
        ttl = await probe.ttl(key)
    finally:
        await probe.aclose()
    assert response.status_code == 202
    assert response.headers["ratelimit-remaining"] == "1"
    assert 0 < ttl <= 3600


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_every_429_carries_retry_after(make_app: Callable[[], FastAPI]) -> None:
    async with running_app(make_app) as app, async_client(app) as client:
        responses = [
            await client.post(
                REGISTER,
                json={
                    "captcha_token": FAKE_CAPTCHA_PASS,
                    "email": unique_email(),
                    "password": PASSWORD,
                },
            )
            for _ in range(6)
        ]
    limited = responses[-1]
    assert_problem(limited, 429, "RATE_LIMITED")
    assert int(limited.headers["retry-after"]) > 0


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_limit_window_resets_when_its_key_expires(
    make_app: Callable[[], FastAPI],
) -> None:
    ip = fresh_ip()
    async with running_app(make_app) as app, async_client(app, ip=ip) as client:
        for _ in range(5):
            ok = await client.post(
                REGISTER,
                json={
                    "captcha_token": FAKE_CAPTCHA_PASS,
                    "email": unique_email(),
                    "password": PASSWORD,
                },
            )
            assert ok.status_code == 202
        limited = await client.post(
            REGISTER,
            json={
                "captcha_token": FAKE_CAPTCHA_PASS,
                "email": unique_email(),
                "password": PASSWORD,
            },
        )
        assert limited.status_code == 429
        assert limited.headers["ratelimit-remaining"] == "0"
        assert 0 < int(limited.headers["ratelimit-reset"]) <= 3600
        probe = await _redis()
        try:
            await probe.pexpire(f"ratelimit:auth:register:{ip}", 50)
        finally:
            await probe.aclose()
        await asyncio.sleep(0.2)
        again = await client.post(
            REGISTER,
            json={
                "captcha_token": FAKE_CAPTCHA_PASS,
                "email": unique_email(),
                "password": PASSWORD,
            },
        )
    assert again.status_code == 202
    assert again.headers["ratelimit-remaining"] == "4"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_limited_request_does_no_work(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    """The 6th registration is refused before the body is acted on - no user,
    no token, no outbox row."""
    blocked = unique_email()
    async with running_app(make_app) as app, async_client(app) as client:
        for _ in range(5):
            await client.post(
                REGISTER,
                json={
                    "captcha_token": FAKE_CAPTCHA_PASS,
                    "email": unique_email(),
                    "password": PASSWORD,
                },
            )
        limited = await client.post(
            REGISTER,
            json={"captcha_token": FAKE_CAPTCHA_PASS, "email": blocked, "password": PASSWORD},
        )
    assert limited.status_code == 429
    db_session.expire_all()
    assert (
        await db_session.scalar(
            select(EmailOutboxModel).where(EmailOutboxModel.recipient_email == blocked)
        )
        is None
    )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_parallel_requests_cannot_overshoot_the_limit(
    make_app: Callable[[], FastAPI],
) -> None:
    """INCR is atomic, so 20 simultaneous requests from one IP get exactly
    5 successes however they interleave."""
    async with running_app(make_app) as app, async_client(app) as client:
        responses = await asyncio.gather(
            *(
                client.post(
                    REGISTER,
                    json={
                        "captcha_token": FAKE_CAPTCHA_PASS,
                        "email": unique_email(),
                        "password": PASSWORD,
                    },
                )
                for _ in range(20)
            )
        )
    statuses = [r.status_code for r in responses]
    assert statuses.count(202) == 5, statuses
    assert statuses.count(429) == 15
