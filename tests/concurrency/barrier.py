"""Release concurrent racers together, or fail the test.

A race test proves something only if its transactions really overlap. The
earlier helpers swallowed a barrier timeout, so a slow racer quietly turned the
race into a sequential run that still passed (audit A-12). This one fails
instead.

`pytest.fail` raises `Failed`, a `BaseException`, so the racers' own
`except Exception` handlers - which record *expected* refusals such as
`SlugConflictError` - cannot absorb it, and `asyncio.gather` propagates it.
"""

import asyncio

import pytest

# Generous: both racers only have to open a transaction before arriving. A
# genuine miss means the test no longer races, which is exactly what must fail.
SYNC_TIMEOUT_SECONDS = 5.0


async def meet_or_fail(barrier: asyncio.Barrier) -> None:
    try:
        await asyncio.wait_for(barrier.wait(), timeout=SYNC_TIMEOUT_SECONDS)
    except (TimeoutError, asyncio.BrokenBarrierError):
        pytest.fail(
            f"the racers never met at the barrier within {SYNC_TIMEOUT_SECONDS}s, "
            "so the transactions did not overlap and this run proved nothing"
        )
