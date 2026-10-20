"""Every 15 minutes: ask the provider about live attempts older than RECONCILE_MIN_AGE and
apply its answer (VS-024 plan 2.4, 3.2). Overlapping runs are safe: Tx B re-checks."""

from datetime import UTC, datetime
from typing import Any

from app.payments.public import reconcile_stuck


async def reconcile_payments(ctx: dict[str, Any]) -> dict[str, int]:
    """arq job; returns the run's counters."""
    return await reconcile_stuck(
        ctx["session_factory"], ctx["payment_providers"], now=datetime.now(UTC)
    )
