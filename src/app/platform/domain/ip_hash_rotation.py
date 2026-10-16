"""When the IP-hash salt is due for rotation (SEC-25, ADR-028): a pure rule."""

from datetime import UTC, datetime


def rotation_due(current_created_at: datetime | None, now: datetime) -> bool:
    """Due when there is no salt or it predates the current UTC calendar month."""
    if current_created_at is None:
        return True
    month_start = now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return current_created_at < month_start
