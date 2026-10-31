"""VS-024 step 10, pure parts: how often each alert may repeat (plan 3.5) and the two
cron entries (2.4, 3.8), read from the registry the worker loads."""

from datetime import timedelta

import pytest

from app.jobs.reconcile_payments import reconcile_payments
from app.jobs.registry import CRON_JOBS, FUNCTIONS
from app.jobs.release_stale_checkouts import release_stale_checkouts
from app.payments.domain.alerts import AlertKind, repeat_window


@pytest.mark.parametrize(
    ("kind", "window"),
    [
        (AlertKind.LATE_CAPTURE, None),
        (AlertKind.MANUAL_CONFIRMATION_DUE, None),
        (AlertKind.RELEASE_DUE, None),
        (AlertKind.REFERENCE_UNKNOWN, None),
        (AlertKind.STUCK, timedelta(hours=24)),
        (AlertKind.EVENT_UNVERIFIED, timedelta(hours=24)),
        (AlertKind.PROVIDER_UNAVAILABLE, timedelta(hours=24)),
        (AlertKind.PROVIDER_NOT_CONFIGURED, timedelta(hours=24)),
        (AlertKind.PROVIDER_UNREACHABLE, timedelta(hours=1)),
    ],
)
def test_each_alert_repeats_as_the_plan_says(kind: AlertKind, window: timedelta | None) -> None:
    assert repeat_window(kind) == window


def test_every_alert_kind_has_a_decided_window() -> None:
    assert {kind for kind in AlertKind if repeat_window(kind) is None} == {
        AlertKind.LATE_CAPTURE,
        AlertKind.MANUAL_CONFIRMATION_DUE,
        AlertKind.MANUAL_PAYMENT_DUE,
        AlertKind.RELEASE_DUE,
        AlertKind.REFERENCE_UNKNOWN,
    }


@pytest.mark.parametrize(
    ("job", "minutes", "second"),
    [
        (reconcile_payments, {0, 15, 30, 45}, 30),
        (release_stale_checkouts, set(range(2, 60, 5)), 45),
    ],
)
def test_the_recovery_jobs_are_registered_with_their_cadence(
    job: object, minutes: set[int], second: int
) -> None:
    (entry,) = [j for j in CRON_JOBS if j.coroutine is job]
    assert (entry.minute, entry.second, entry.run_at_startup) == (minutes, second, True)
    assert job in FUNCTIONS
