"""The daily idempotency purge is registered where the worker loads it (VS-023 plan 2.4)."""

from app.jobs.purge_idempotency import purge_expired_idempotency_records
from app.jobs.registry import CRON_JOBS, FUNCTIONS


def test_the_idempotency_purge_runs_daily_at_03_53() -> None:
    (entry,) = [j for j in CRON_JOBS if j.coroutine is purge_expired_idempotency_records]
    assert (entry.hour, entry.minute, entry.second) == (3, 53, 0)
    assert purge_expired_idempotency_records in FUNCTIONS
