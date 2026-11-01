"""Table T2, row by row, and the property that only an explicit `failed` or `expired` ever
releases an order (VS-024 plan 3.1, 6.1; Revision 1 item 1): the provider's, or for
`manual` the platform's own at the hold's end (ADR-049 d6)."""

import itertools

import pytest

from app.payments.domain.alerts import AlertKind
from app.payments.domain.outcome import ProviderResult, ProviderState
from app.payments.domain.release import (
    Capability,
    ProviderAnswer,
    ReleaseKind,
    ReleaseVerdict,
    Unavailable,
    must_skip_unasked,
    release_action,
)
from app.payments.infrastructure.release import MANUAL_HOLD_ENDED

STATES: tuple[ProviderState, ...] = (
    "pending",
    "processing",
    "paid",
    "failed",
    "expired",
    "unknown",
)
ANSWERS: tuple[ProviderAnswer | None, ...] = (
    None,
    Unavailable.UNAVAILABLE,
    *(ProviderResult(state, 1000, "USD") for state in STATES),
    ProviderResult("paid", 999, "USD"),
    ProviderResult("paid", None, None),
)


def act(
    answer: ProviderAnswer | None,
    *,
    events: int = 0,
    capability: Capability = Capability.STATUS_QUERY,
    stuck: bool = False,
    grace: bool = False,
) -> ReleaseVerdict:
    return release_action(
        unprocessed_events=events,
        capability=capability,
        answer=answer,
        stuck=stuck,
        grace_passed=grace,
    )


def answer(state: ProviderState) -> ProviderResult:
    return ProviderResult(state, 1000, "USD")


def test_only_failed_and_expired_ever_release() -> None:
    """Every answer x capability x event count x stuck x grace: RELEASE needs explicit."""
    released: set[str] = set()
    combos = itertools.product(ANSWERS, Capability, (0, 1, 3), (False, True), (False, True))
    for ans, capability, events, stuck, grace in combos:
        try:
            verdict = act(ans, events=events, capability=capability, stuck=stuck, grace=grace)
        except ValueError:
            assert ans is None, "only a missing answer may be refused"
            continue
        if verdict.kind is ReleaseKind.RELEASE:
            assert isinstance(ans, ProviderResult)
            assert capability in (Capability.STATUS_QUERY, Capability.MANUAL) and events == 0
            released.add(ans.state)
    assert released == {"failed", "expired"}


@pytest.mark.parametrize("capability", list(Capability))
@pytest.mark.parametrize("ans", ANSWERS)
def test_an_unprocessed_event_beats_every_answer(
    capability: Capability, ans: ProviderAnswer | None
) -> None:
    verdict = act(ans, events=1, capability=capability)
    expected = (
        AlertKind.MANUAL_CONFIRMATION_DUE
        if capability in (Capability.NO_STATUS_QUERY, Capability.MANUAL)
        else AlertKind.EVENT_UNVERIFIED
    )
    assert verdict == ReleaseVerdict(ReleaseKind.SKIP, expected)


@pytest.mark.parametrize("capability", [Capability.NO_STATUS_QUERY, Capability.NOT_CONFIGURED])
@pytest.mark.parametrize("ans", ANSWERS)
def test_a_provider_that_cannot_answer_never_releases(
    capability: Capability, ans: ProviderAnswer | None
) -> None:
    assert act(ans, capability=capability) == ReleaseVerdict(ReleaseKind.SKIP, None)
    due = act(ans, capability=capability, grace=True)
    assert due == ReleaseVerdict(ReleaseKind.SKIP, AlertKind.RELEASE_DUE)


@pytest.mark.parametrize("state", ["failed", "expired"])
def test_an_explicit_end_releases(state: ProviderState) -> None:
    assert act(answer(state)) == ReleaseVerdict(ReleaseKind.RELEASE)
    assert act(answer(state), stuck=True, grace=True) == ReleaseVerdict(ReleaseKind.RELEASE)


@pytest.mark.parametrize("amount", [1000, 999, None])
def test_paid_is_applied_and_never_released(amount: int | None) -> None:
    verdict = act(ProviderResult("paid", amount, "USD" if amount else None), grace=True)
    assert verdict == ReleaseVerdict(ReleaseKind.APPLY_ONLY)


@pytest.mark.parametrize("state", ["pending", "processing"])
def test_a_provider_still_working_is_skipped_with_the_right_alert(state: ProviderState) -> None:
    assert act(answer(state)) == ReleaseVerdict(ReleaseKind.SKIP, None)
    assert act(answer(state), stuck=True) == ReleaseVerdict(ReleaseKind.SKIP, AlertKind.STUCK)
    due = act(answer(state), stuck=True, grace=True)
    assert due == ReleaseVerdict(ReleaseKind.SKIP, AlertKind.RELEASE_DUE)


@pytest.mark.parametrize("grace", [False, True])
def test_unknown_is_skipped_and_alerted(grace: bool) -> None:
    verdict = act(answer("unknown"), stuck=True, grace=grace)
    assert verdict == ReleaseVerdict(ReleaseKind.SKIP, AlertKind.REFERENCE_UNKNOWN)


@pytest.mark.parametrize("grace", [False, True])
def test_no_answer_is_skipped_and_alerted(grace: bool) -> None:
    verdict = act(Unavailable.UNAVAILABLE, stuck=True, grace=grace)
    assert verdict == ReleaseVerdict(ReleaseKind.SKIP, AlertKind.PROVIDER_UNAVAILABLE)


def test_the_provider_must_be_asked_when_no_row_decides_unasked() -> None:
    assert (
        must_skip_unasked(
            unprocessed_events=0, capability=Capability.STATUS_QUERY, grace_passed=True
        )
        is None
    )
    with pytest.raises(ValueError, match="answer"):
        act(None)


def test_a_manual_attempt_is_answered_by_the_platform_and_released() -> None:
    """ADR-049 d6: nobody can be asked about `manual`, so the job answers `expired` itself."""
    manual = Capability.MANUAL
    assert must_skip_unasked(unprocessed_events=0, capability=manual, grace_passed=False) is None
    ended = act(MANUAL_HOLD_ENDED, capability=manual)
    assert ended == ReleaseVerdict(ReleaseKind.RELEASE)
    assert ProviderResult("expired", None, None) == MANUAL_HOLD_ENDED
