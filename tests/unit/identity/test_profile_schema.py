import uuid
from datetime import UTC, datetime

from app.identity.api.schemas import UserProfileRead
from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole

CONTRACT_FIELDS = {"id", "email", "role", "email_verified", "email_verified_at", "created_at"}


def _user(*, email_verified_at: datetime | None) -> User:
    now = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    return User(
        id=uuid.uuid4(),
        email="customer@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$secret",
        role=UserRole.CUSTOMER,
        email_verified_at=email_verified_at,
        is_active=True,
        anonymized_at=None,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )


def test_from_user_reports_a_verified_account() -> None:
    verified_at = datetime(2026, 8, 2, 10, 30, tzinfo=UTC)
    profile = UserProfileRead.from_user(_user(email_verified_at=verified_at))

    assert profile.email_verified is True
    assert profile.email_verified_at == verified_at


def test_from_user_reports_an_unverified_account() -> None:
    profile = UserProfileRead.from_user(_user(email_verified_at=None))

    assert profile.email_verified is False
    assert profile.email_verified_at is None


def test_from_user_copies_identity_fields() -> None:
    user = _user(email_verified_at=None)
    profile = UserProfileRead.from_user(user)

    assert profile.id == user.id
    assert profile.email == user.email
    assert profile.role is UserRole.CUSTOMER
    assert profile.created_at == user.created_at


def test_the_serialised_profile_carries_exactly_the_contract_fields() -> None:
    """A regression guard on the response contract in both directions: a field
    quietly added to `users` must not leak, and one in the contract must not
    quietly disappear."""
    dumped = UserProfileRead.from_user(_user(email_verified_at=None)).model_dump()

    assert set(dumped) == CONTRACT_FIELDS
