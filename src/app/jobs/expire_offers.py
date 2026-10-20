"""Every 5 minutes (SRS 23, BR-084): expire offers whose turn deadline has passed. A capped
run leaves the rest for the next tick; overlapping runs are safe (SKIP LOCKED + re-check)."""

from datetime import UTC, datetime
from typing import Any

from app.negotiation.public import expire_overdue_offers
from app.payments.public import payment_in_flight

BATCH_SIZE = 200


async def expire_offers(
    ctx: dict[str, Any], *, now: datetime | None = None, limit: int = BATCH_SIZE
) -> dict[str, int]:
    """arq job. Returns candidates seen and offers expired."""
    return await expire_overdue_offers(
        ctx["session_factory"],
        now=now or datetime.now(UTC),
        limit=limit,
        in_flight=payment_in_flight,
    )
