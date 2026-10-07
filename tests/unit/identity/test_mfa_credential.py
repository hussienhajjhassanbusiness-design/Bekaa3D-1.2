from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.identity.domain.entities import MfaCredential
from app.identity.domain.enums import MfaMethod


def _credential(enabled_at: datetime | None = None) -> MfaCredential:
    now = datetime.now(UTC)
    return MfaCredential(
        id=uuid4(),
        user_id=uuid4(),
        method=MfaMethod.TOTP,
        secret_ciphertext=b"ciphertext",
        enabled_at=enabled_at,
        last_used_at=None,
        last_totp_step=None,
        created_at=now,
        updated_at=now,
    )


def test_a_freshly_enrolled_credential_is_not_enabled() -> None:
    """Enrollment must not open the admin boundary on its own - `enabled_at`
    stays NULL until a real TOTP is confirmed (database-design.md 5.6)."""
    assert not _credential().is_enabled


def test_enable_marks_the_credential_enabled() -> None:
    credential = _credential()
    at = datetime.now(UTC)

    credential.enable(at)

    assert credential.is_enabled
    assert credential.enabled_at == at
    assert credential.updated_at == at


def test_enable_keeps_the_first_timestamp_when_called_again() -> None:
    """`enabled_at` records when MFA was first trusted, not when it was last
    exercised; `last_used_at` is what tracks the latter."""
    first = datetime.now(UTC) - timedelta(days=30)
    credential = _credential(enabled_at=first)

    credential.enable(datetime.now(UTC))

    assert credential.enabled_at == first


def test_mark_used_records_last_use_without_enabling() -> None:
    credential = _credential()
    at = datetime.now(UTC)

    credential.mark_used(at)

    assert credential.last_used_at == at
    assert not credential.is_enabled


def test_the_domain_never_exposes_a_readable_secret() -> None:
    """secret_ciphertext is opaque bytes precisely so no domain rule can read,
    format or log the raw TOTP secret."""
    credential = _credential()

    assert isinstance(credential.secret_ciphertext, bytes)
    assert not hasattr(credential, "secret")
