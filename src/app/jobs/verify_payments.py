"""Every minute: the fallback for verification lost after a webhook's 200 (VS-023 plan
2.4). Up to 50 unprocessed events, oldest first; overlapping runs are safe."""

from typing import Any

from app.payments.public import verify_unprocessed


async def verify_payments(ctx: dict[str, Any]) -> dict[str, int]:
    """arq job. Returns events seen, applied and deferred (provider did not answer)."""
    return await verify_unprocessed(ctx["session_factory"], ctx["payment_providers"])
