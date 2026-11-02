"""The per-customer cap on unpaid `manual` orders at placement (VS-050 audit Q-1,
ADR-049 d14). A retry adds no order, so it is not capped."""

from uuid import UUID

from app.ordering.application.ports import OrderStore, PaymentAttempts, SettingsSource
from app.ordering.domain.manual_orders import MAX_OPEN_SETTING, manual_order_limit
from app.ordering.domain.payment_recovery import MANUAL_PROVIDER


async def require_manual_room(
    *, orders: OrderStore, attempts: PaymentAttempts, settings: SettingsSource, user_id: UUID
) -> None:
    """Takes the customer's lock before any INSERT, so two placements count one by one."""
    await orders.lock_manual_orders(user_id)
    unpaid = await orders.unpaid_online_order_ids(user_id)
    manual_order_limit(
        open_orders=await attempts.count_latest_on(unpaid, MANUAL_PROVIDER),
        max_open=await settings.get_int(MAX_OPEN_SETTING),
    )
