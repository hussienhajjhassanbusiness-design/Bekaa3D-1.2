"""Every 5 minutes: release unpaid online orders past their hold, only on the provider's
explicit `failed` or `expired` (VS-024 plan 2.4, 3.1 T2). Overlapping runs are safe."""

from datetime import UTC, datetime
from typing import Any

from app.payments.public import release_stale


async def release_stale_checkouts(ctx: dict[str, Any]) -> dict[str, int]:
    """arq job; returns the run's counters."""
    return await release_stale(
        ctx["session_factory"], ctx["payment_providers"], now=datetime.now(UTC)
    )
