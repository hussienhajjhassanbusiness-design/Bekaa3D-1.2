"""The kinds of operational alert Payments raises (VS-024 plan 3.5). Pure: delivery and
de-duplication live in `infrastructure.alerts`."""

from enum import StrEnum
from typing import Any
from uuid import UUID


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
