"""The kinds of operational alert Payments raises (VS-024 plan 3.5). Pure: delivery and
de-duplication live in `infrastructure.alerts`."""

from enum import StrEnum


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
