"""`expire_offers` is registered to run every five minutes (SRS 23, VS-039)."""

from app.jobs.expire_offers import expire_offers
from app.jobs.registry import CRON_JOBS, FUNCTIONS


def test_expire_offers_runs_every_five_minutes_and_at_startup() -> None:
    [job] = [job for job in CRON_JOBS if job.coroutine is expire_offers]
    assert job.minute == set(range(0, 60, 5))
    assert job.run_at_startup
    assert expire_offers in FUNCTIONS
