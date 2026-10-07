"""The "never zero active administrators" rule, decided without a database."""

import uuid
from datetime import UTC, datetime

import pytest

from app.identity.domain.administrators import (
    ensure_an_active_administrator_remains,
    is_active_administrator,
)
from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole
from app.identity.domain.exceptions import LastActiveAdministratorError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def make_user(
    *,
    role: UserRole = UserRole.ADMIN,
    is_active: bool = True,
    anonymized: bool = False,
    deleted: bool = False,
) -> User:
    return User(
        id=uuid.uuid4(),
        email="someone@example.com",
        password_hash="argon2-hash",
        role=role,
        email_verified_at=NOW,
        is_active=is_active,
        anonymized_at=NOW if anonymized else None,
        deleted_at=NOW if deleted else None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_the_last_active_administrator_cannot_be_removed() -> None:
    with pytest.raises(LastActiveAdministratorError):
        ensure_an_active_administrator_remains(make_user(), other_active_administrators=0)


def test_an_administrator_may_be_removed_while_another_remains() -> None:
    ensure_an_active_administrator_remains(make_user(), other_active_administrators=1)


@pytest.mark.parametrize(
    "user",
    [
        make_user(role=UserRole.CUSTOMER),
        make_user(is_active=False),
        make_user(anonymized=True),
        make_user(deleted=True),
    ],
    ids=["customer", "already-inactive", "anonymised", "deleted"],
)
def test_removing_someone_who_is_not_an_active_administrator_changes_nothing(user: User) -> None:
    assert is_active_administrator(user) is False
    ensure_an_active_administrator_remains(user, other_active_administrators=0)
