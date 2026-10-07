from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.identity.application.security.token_service import hash_token
from app.identity.domain.entities import MfaRecoveryCode
from app.identity.domain.exceptions import InvalidRecoveryCodeError
from app.identity.domain.recovery_codes import (
    CODES_PER_SET,
    generate_code,
    generate_code_set,
    normalize_code,
)


def _code(code_hash: str = "hash", used_at: datetime | None = None) -> MfaRecoveryCode:
    return MfaRecoveryCode(
        id=uuid4(),
        mfa_credential_id=uuid4(),
        code_hash=code_hash,
        used_at=used_at,
        created_at=datetime.now(UTC),
    )


def test_generate_code_set_returns_the_documented_number_of_codes() -> None:
    assert len(generate_code_set()) == CODES_PER_SET


def test_generated_codes_are_unique_within_a_set() -> None:
    codes = generate_code_set()
    assert len(set(codes)) == len(codes)


def test_generated_codes_avoid_visually_ambiguous_characters() -> None:
    """These get transcribed off paper, so O/0, I/1 and L must never appear."""
    for code in generate_code_set():
        assert not set(code) & set("O0I1L")


def test_generated_codes_carry_enough_entropy_to_survive_a_stolen_table() -> None:
    """The frozen `code_hash TEXT UNIQUE` forces a fast deterministic hash, so
    length is the only thing standing between a leaked table and an offline
    brute force. 12 alphabet characters is the floor that reasoning assumed."""
    for code in generate_code_set():
        assert len(normalize_code(code)) == 12


def test_normalize_code_accepts_how_a_human_actually_types_it() -> None:
    canonical = generate_code()
    stripped = canonical.replace("-", "")

    assert normalize_code(canonical.lower()) == stripped
    assert normalize_code(f"  {canonical}  ") == stripped
    assert normalize_code(canonical.replace("-", " ")) == stripped


def test_normalize_code_is_idempotent() -> None:
    once = normalize_code(generate_code())
    assert normalize_code(once) == once


def test_redeem_marks_the_code_used() -> None:
    code = _code()
    at = datetime.now(UTC)

    code.redeem(at)

    assert code.is_used
    assert code.used_at == at


def test_redeeming_a_spent_code_is_refused() -> None:
    already_used = datetime.now(UTC) - timedelta(hours=1)
    code = _code(used_at=already_used)

    with pytest.raises(InvalidRecoveryCodeError):
        code.redeem(datetime.now(UTC))

    # The original timestamp must survive the failed attempt - overwriting it
    # would rewrite when the code was really spent.
    assert code.used_at == already_used


def test_a_code_is_never_recoverable_from_its_stored_hash() -> None:
    """The plaintext exists only in the generation response. Storing anything
    reversible would defeat the point of hashing at all."""
    plaintext = generate_code()
    stored = hash_token(normalize_code(plaintext))

    assert plaintext not in stored
    assert normalize_code(plaintext) not in stored
    assert stored == hash_token(normalize_code(plaintext.lower()))
