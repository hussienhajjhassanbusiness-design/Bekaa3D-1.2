"""Table T2: what `release_stale_checkouts` does with one order past its hold (VS-024 plan
3.1, D5). Pure. Only an explicit `failed` or `expired` ever releases: the provider's, or
for `manual` the platform's own `expired` at the hold's end (ADR-049)."""

from dataclasses import dataclass
from enum import StrEnum

from app.payments.domain.alerts import AlertKind
from app.payments.domain.outcome import ProviderResult


class Capability(StrEnum):
    """What the adapter named on the payment row can tell us (ADR-024 d13)."""

    STATUS_QUERY = "status_query"
    NO_STATUS_QUERY = "no_status_query"
    NOT_CONFIGURED = "not_configured"
    # ADR-049: no one to ask; the platform itself answers `expired` at the hold's end.
    MANUAL = "manual"


class Unavailable(StrEnum):
    """The provider was asked and did not answer: an error, a timeout or an open breaker."""

    UNAVAILABLE = "unavailable"


ProviderAnswer = ProviderResult | Unavailable


class ReleaseKind(StrEnum):
    RELEASE = "release"  # apply the explicit answer, then release the order
    APPLY_ONLY = "apply_only"  # money arrived: apply it (paid or late capture), never release
    SKIP = "skip"  # write nothing this run


@dataclass(frozen=True)
class ReleaseVerdict:
    kind: ReleaseKind
    alert: AlertKind | None = None


_EXPLICIT = frozenset({"failed", "expired"})


def must_skip_unasked(
    *, unprocessed_events: int, capability: Capability, grace_passed: bool
) -> ReleaseVerdict | None:
    """The rows decided without asking the provider; None means "ask it"."""
    if unprocessed_events > 0:
        if capability in (Capability.NO_STATUS_QUERY, Capability.MANUAL):
            return ReleaseVerdict(ReleaseKind.SKIP, AlertKind.MANUAL_CONFIRMATION_DUE)
        return ReleaseVerdict(ReleaseKind.SKIP, AlertKind.EVENT_UNVERIFIED)
    if capability not in (Capability.STATUS_QUERY, Capability.MANUAL):
        return ReleaseVerdict(ReleaseKind.SKIP, AlertKind.RELEASE_DUE if grace_passed else None)
    return None


def release_action(
    *,
    unprocessed_events: int,
    capability: Capability,
    answer: ProviderAnswer | None,
    stuck: bool,
    grace_passed: bool,
) -> ReleaseVerdict:
    """T2 for the latest attempt. `answer` is None only when `must_skip_unasked` decides."""
    unasked = must_skip_unasked(
        unprocessed_events=unprocessed_events, capability=capability, grace_passed=grace_passed
    )
    if unasked is not None:
        return unasked
    if answer is None:
        raise ValueError("T2 needs the provider's answer for this order")
    if isinstance(answer, Unavailable):
        return ReleaseVerdict(ReleaseKind.SKIP, AlertKind.PROVIDER_UNAVAILABLE)
    if answer.state in _EXPLICIT:
        return ReleaseVerdict(ReleaseKind.RELEASE)
    if answer.state == "paid":
        return ReleaseVerdict(ReleaseKind.APPLY_ONLY)
    if answer.state == "unknown":
        return ReleaseVerdict(ReleaseKind.SKIP, AlertKind.REFERENCE_UNKNOWN)
    if grace_passed:
        return ReleaseVerdict(ReleaseKind.SKIP, AlertKind.RELEASE_DUE)
    return ReleaseVerdict(ReleaseKind.SKIP, AlertKind.STUCK if stuck else None)
