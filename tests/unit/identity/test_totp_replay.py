"""The two primitives behind TOTP replay rejection (RFC 6238 5.2).

The endpoint-level proof lives in
tests/integration/identity/test_mfa_replay_and_reconfirm.py. These cover the
arithmetic underneath it, which is where an off-by-one would hide: the window
walk that reports *which* step matched, and the high-water mark that decides
whether that step is already spent.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pyotp

from app.identity.application.security.totp import (
    TOTP_STEP_SECONDS,
    current_step,
    generate_secret,
    verify_code_step,
)
from app.identity.domain.entities import MfaCredential
from app.identity.domain.enums import MfaMethod


def _credential(last_totp_step: int | None = None) -> MfaCredential:
    now = datetime.now(UTC)
    return MfaCredential(
        id=uuid4(),
        user_id=uuid4(),
        method=MfaMethod.TOTP,
        secret_ciphertext=b"ciphertext",
        enabled_at=now,
        last_used_at=None,
        last_totp_step=last_totp_step,
        created_at=now,
        updated_at=now,
    )


# --------------------------------------------------------------------------
# verify_code_step
# --------------------------------------------------------------------------


def test_a_current_code_reports_the_current_step() -> None:
    secret = generate_secret()
    now = datetime.now(UTC)

    matched = verify_code_step(secret=secret, code=pyotp.TOTP(secret).now(), now=now)

    assert matched == current_step(now)


def test_a_previous_and_next_code_report_their_own_steps() -> None:
    """The window reaches one step either way for clock drift, and the step it
    returns has to be the code's own - returning the current step would let a
    drifted code be replayed once."""
    secret = generate_secret()
    now = datetime.now(UTC)
    totp = pyotp.TOTP(secret)

    before = verify_code_step(
        secret=secret, code=totp.at(now - timedelta(seconds=TOTP_STEP_SECONDS)), now=now
    )
    after = verify_code_step(
        secret=secret, code=totp.at(now + timedelta(seconds=TOTP_STEP_SECONDS)), now=now
    )

    assert before == current_step(now) - 1
    assert after == current_step(now) + 1


def test_a_code_outside_the_window_matches_nothing() -> None:
    secret = generate_secret()
    now = datetime.now(UTC)
    stale = pyotp.TOTP(secret).at(now - timedelta(seconds=TOTP_STEP_SECONDS * 3))

    assert verify_code_step(secret=secret, code=stale, now=now) is None


def test_malformed_input_is_rejected_rather_than_raising() -> None:
    """Garbage and a wrong code get the same answer. Distinguishing them would
    hand an attacker an oracle for what the server considers well-formed."""
    secret = generate_secret()
    now = datetime.now(UTC)

    assert verify_code_step(secret=secret, code="", now=now) is None
    assert verify_code_step(secret=secret, code="abcdef", now=now) is None
    assert verify_code_step(secret=secret, code="1234567890", now=now) is None
    # Non-ASCII must not blow up hmac.compare_digest, which rejects non-ASCII
    # str operands with TypeError rather than returning False. Written as
    # escapes so the literal stays readable and ruff's ambiguous-character rule
    # has nothing to complain about: fullwidth digits, the realistic way this
    # arrives from a phone keyboard.
    fullwidth = "\uff11\uff12\uff13\uff14\uff15\uff16"
    assert verify_code_step(secret=secret, code=fullwidth, now=now) is None


def test_surrounding_whitespace_is_still_tolerated() -> None:
    secret = generate_secret()
    now = datetime.now(UTC)

    assert (
        verify_code_step(secret=secret, code=f"  {pyotp.TOTP(secret).now()}  ", now=now) is not None
    )


# --------------------------------------------------------------------------
# MfaCredential.is_totp_step_replayed / record_totp_step
# --------------------------------------------------------------------------


def test_a_credential_that_never_accepted_a_totp_replays_nothing() -> None:
    assert not _credential().is_totp_step_replayed(current_step(datetime.now(UTC)))


def test_the_step_just_accepted_is_refused() -> None:
    step = current_step(datetime.now(UTC))

    assert _credential(last_totp_step=step).is_totp_step_replayed(step)


def test_an_earlier_step_is_refused_too() -> None:
    """`<=`, not `==`. The window looks backwards as well, so a code from the
    previous step is just as replayable if only equality were checked."""
    step = current_step(datetime.now(UTC))

    assert _credential(last_totp_step=step).is_totp_step_replayed(step - 1)


def test_a_later_step_is_allowed() -> None:
    """Otherwise the guard would latch and the administrator could never log in
    again."""
    step = current_step(datetime.now(UTC))

    assert not _credential(last_totp_step=step).is_totp_step_replayed(step + 1)


def test_recording_a_step_marks_it_spent_and_counts_as_a_use() -> None:
    credential = _credential()
    step = current_step(datetime.now(UTC))
    at = datetime.now(UTC)

    credential.record_totp_step(step, at)

    assert credential.last_totp_step == step
    assert credential.is_totp_step_replayed(step)
    assert credential.last_used_at == at


def test_the_mark_never_moves_backwards() -> None:
    """Two requests can interleave. If a late-arriving earlier step could pull
    the mark back, an already-spent step would become redeemable again."""
    step = current_step(datetime.now(UTC))
    credential = _credential(last_totp_step=step)

    credential.record_totp_step(step - 1, datetime.now(UTC))

    assert credential.last_totp_step == step
    assert credential.is_totp_step_replayed(step - 1)


def test_marking_a_plain_use_does_not_spend_a_totp_step() -> None:
    """`mark_used` is what a recovery-code redemption calls. A recovery code
    and a TOTP are separate one-time credentials; spending one must not consume
    a step of the other."""
    credential = _credential()

    credential.mark_used(datetime.now(UTC))

    assert credential.last_totp_step is None
    assert not credential.is_totp_step_replayed(current_step(datetime.now(UTC)))
