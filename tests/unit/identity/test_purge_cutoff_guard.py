"""The purge refuses a cutoff that is not in the past (VS-046, SEC-07): live rows are safe."""

from datetime import UTC, datetime, timedelta

import pytest

from app.identity.application.commands.purge_expired_security_records import (
    PurgeExpiredSecurityRecords,
)

NOW = datetime(2026, 10, 16, tzinfo=UTC)


class _Store:
    def __init__(self) -> None:
        self.calls: list[tuple[datetime, int]] = []

    async def delete_expired_batch(self, *, cutoff: datetime, limit: int) -> int:
        self.calls.append((cutoff, limit))
        return 1

    async def delete_ended_batch(self, *, cutoff: datetime, limit: int) -> int:
        self.calls.append((cutoff, limit))
        return 2


def _use_case(store: _Store) -> PurgeExpiredSecurityRecords:
    return PurgeExpiredSecurityRecords(store, store, store, clock=lambda: NOW)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("token_cutoff", "session_cutoff"),
    [
        (NOW, NOW - timedelta(days=1)),
        (NOW - timedelta(days=1), NOW),
        (NOW + timedelta(seconds=1), NOW - timedelta(days=1)),
    ],
    ids=["token-at-now", "session-at-now", "token-in-future"],
)
async def test_a_cutoff_at_or_after_now_raises_before_any_delete(
    token_cutoff: datetime, session_cutoff: datetime
) -> None:
    store = _Store()
    with pytest.raises(ValueError, match="in the past"):
        await _use_case(store).execute_batch(
            token_cutoff=token_cutoff, session_cutoff=session_cutoff, limit=10
        )
    assert store.calls == []


async def test_a_past_cutoff_runs_one_batch_per_table() -> None:
    store = _Store()
    token_cutoff, session_cutoff = NOW - timedelta(days=7), NOW - timedelta(days=30)
    result = await _use_case(store).execute_batch(
        token_cutoff=token_cutoff, session_cutoff=session_cutoff, limit=10
    )
    assert (result.verification_tokens, result.password_reset_tokens, result.sessions) == (1, 1, 2)
    assert store.calls == [(token_cutoff, 10), (token_cutoff, 10), (session_cutoff, 10)]
