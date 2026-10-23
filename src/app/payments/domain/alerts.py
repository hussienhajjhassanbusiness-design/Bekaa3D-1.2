"""The kinds of operational alert Payments raises (VS-024 plan 3.5). Pure: delivery and
de-duplication live in `infrastructure.alerts`."""

from datetime import timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.payments.domain.limits import ALERT_REPEAT_PER_PAYMENT, ALERT_REPEAT_PER_PROVIDER


class AlertKind(StrEnum):
    LATE_CAPTURE = "late_capture"
    STUCK = "stuck"
    MANUAL_CONFIRMATION_DUE = "manual_confirmation_due"
    EVENT_UNVERIFIED = "event_unverified"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    RELEASE_DUE = "release_due"
    PROVIDER_UNREACHABLE = "provider_unreachable"
    PROVIDER_NOT_CONFIGURED = "provider_not_configured"
    REFERENCE_UNKNOWN = "reference_unknown"
    REFUND_INTEGRITY = "refund_integrity"  # VS-030 Q-2: order total != its lines


# What an admin needs to act, and nothing else: no redirect URL, provider reference or
# customer data ever reaches a notification, email or audit row (VS-024 2.1).
DETAIL_KEYS = frozenset(
    {
        "order_number",
        "reason",
        "attempt_status",
        "provider",
        "captured_amount_cents",
        "captured_currency",
        "expected_amount_cents",
    }
)


def alert_payload(
    kind: AlertKind, *, payment_id: UUID | None, order_id: UUID | None, details: dict[str, Any]
) -> dict[str, Any]:
    """The notification and email payload: the kind, the ids and the allowed details only."""
    kept = {key: value for key, value in details.items() if key in DETAIL_KEYS}
    return {
        "event": f"payment.alert.{kind}",
        "kind": str(kind),
        "payment_id": str(payment_id) if payment_id else None,
        "order_id": str(order_id) if order_id else None,
    } | kept


_REPEAT = {
    AlertKind.STUCK: ALERT_REPEAT_PER_PAYMENT,
    AlertKind.EVENT_UNVERIFIED: ALERT_REPEAT_PER_PAYMENT,
    AlertKind.PROVIDER_UNAVAILABLE: ALERT_REPEAT_PER_PAYMENT,
    AlertKind.PROVIDER_NOT_CONFIGURED: ALERT_REPEAT_PER_PAYMENT,
    AlertKind.REFUND_INTEGRITY: ALERT_REPEAT_PER_PAYMENT,
    AlertKind.PROVIDER_UNREACHABLE: ALERT_REPEAT_PER_PROVIDER,
}


def repeat_window(kind: AlertKind) -> timedelta | None:
    """Plan 3.5: how soon the same alert may repeat; None means once per entity, ever."""
    return _REPEAT.get(kind)
