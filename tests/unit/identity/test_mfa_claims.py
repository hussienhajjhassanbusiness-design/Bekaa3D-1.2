"""The `mfa_completed` access-token claim, and the MFA request schemas.

Kept separate from test_session_tokens.py so VS-005 adds a file rather than
editing VS-003's tests."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.identity.api.schemas import MfaVerifyRequest
from app.identity.application.security.session_tokens import decode_access_token, issue_access_token
from app.identity.domain.enums import UserRole


@pytest.fixture(autouse=True)
def _token_settings() -> None:
    os.environ.setdefault("JWT_SIGNING_KEY", "unit-test-signing-key")
    os.environ.setdefault("MFA_SECRET_KEY", "0" * 64)
    get_settings.cache_clear()


def _issue(*, role: UserRole = UserRole.ADMIN, mfa_completed: bool) -> str:
    return issue_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        role=role,
        email_verified=True,
        now=datetime.now(UTC),
        mfa_completed=mfa_completed,
    )


def test_the_claim_round_trips_when_set() -> None:
    assert decode_access_token(_issue(mfa_completed=True)).mfa_completed is True


def test_the_claim_round_trips_when_unset() -> None:
    assert decode_access_token(_issue(mfa_completed=False)).mfa_completed is False


def test_the_claim_defaults_to_false_when_omitted_by_the_issuer() -> None:
    """Customer login does not pass the flag at all. It must default closed, or
    every customer token would silently satisfy the admin boundary's MFA half."""
    token = issue_access_token(
        user_id=uuid4(),
        session_id=uuid4(),
        role=UserRole.CUSTOMER,
        email_verified=True,
        now=datetime.now(UTC),
    )

    assert decode_access_token(token).mfa_completed is False


def test_a_token_predating_the_claim_still_decodes_without_mfa() -> None:
    """A validly signed token minted before this claim existed must not become
    undecodable - it simply is not MFA-complete."""
    import jwt

    settings = get_settings()
    now = datetime.now(UTC)
    legacy = jwt.encode(
        {
            "typ": "access",
            "sub": str(uuid4()),
            "sid": str(uuid4()),
            "role": UserRole.ADMIN.value,
            "ver": True,
            "iat": now,
            "exp": now.timestamp() + 900,
        },
        settings.jwt_signing_key,
        algorithm="HS256",
    )

    assert decode_access_token(legacy).mfa_completed is False


def test_verify_request_accepts_a_totp_code_alone() -> None:
    request = MfaVerifyRequest(challenge_id="abc", code="123456")

    assert request.code == "123456"
    assert request.recovery_code is None


def test_verify_request_accepts_a_recovery_code_alone() -> None:
    request = MfaVerifyRequest(challenge_id="abc", recovery_code="ABCD-EFGH-JKLM")

    assert request.recovery_code == "ABCD-EFGH-JKLM"
    assert request.code is None


def test_verify_request_rejects_both_factors_at_once() -> None:
    """ "Exactly one second-factor credential is supplied" (api-endpoints.md
    29.2). Accepting both would make which factor was checked depend on
    evaluation order rather than on the request."""
    with pytest.raises(ValidationError):
        MfaVerifyRequest(challenge_id="abc", code="123456", recovery_code="ABCD-EFGH-JKLM")


def test_verify_request_rejects_neither_factor() -> None:
    with pytest.raises(ValidationError):
        MfaVerifyRequest(challenge_id="abc")


def test_verify_request_rejects_unknown_fields() -> None:
    """`extra="forbid"`: a caller cannot smuggle an extra field past the schema.

    Built through `model_validate` rather than the constructor because the
    whole point is a field the model does not declare, which a typed
    constructor call cannot express."""
    with pytest.raises(ValidationError):
        MfaVerifyRequest.model_validate({"challenge_id": "abc", "code": "123456", "role": "admin"})
