"""The two checkout holds, read together (VS-024 D4, ADR-049 d6)."""

from datetime import timedelta

from app.ordering.application.ports import SettingsSource
from app.ordering.domain.payment_recovery import Holds

ONLINE_HOLD_SETTING = "checkout_hold_period"
MANUAL_HOLD_SETTING = "manual_payment_hold_period"


async def read_holds(settings: SettingsSource) -> Holds:
    online = await settings.get_duration_seconds(ONLINE_HOLD_SETTING)
    manual = await settings.get_duration_seconds(MANUAL_HOLD_SETTING)
    return Holds(online=timedelta(seconds=online), manual=timedelta(seconds=manual))
