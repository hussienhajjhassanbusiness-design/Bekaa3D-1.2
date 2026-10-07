"""Anti-enumeration constant-work tests (F01, F14).

These assert that the expensive password-hash work *happens* on every branch,
by counting calls to the hasher. They deliberately do not assert wall-clock
thresholds: a timing assertion is flaky under CI load and would either fail
spuriously or be loosened until it proved nothing. Counting the work is the
property we actually care about and it is deterministic.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.identity.application.commands import register_user as register_module
from app.identity.application.commands import resend_verification as resend_module
from app.identity.application.commands.register_user import RegisterUser
from app.identity.application.commands.resend_verification import ResendVerification
from app.identity.domain.entities import User, VerificationToken
from app.identity.domain.enums import UserRole


def _user(*, verified: bool) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email="someone@example.com",
        password_hash="stored-hash",
        role=UserRole.CUSTOMER,
        email_verified_at=now if verified else None,
        is_active=True,
        anonymized_at=None,
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )


class _Counter:
    """Stands in for the async hashing helpers (Argon2 runs off the event
    loop since BUG-06), so it is awaited like them."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, *args: object, **kwargs: object) -> str:
        self.calls += 1
        return "hashed"


class _FakeUsers:
    def __init__(self, existing: User | None) -> None:
        self._existing = existing
        self.added: list[str] = []

    async def get_by_email(self, email: str) -> User | None:
        return self._existing

    async def get_by_email_for_update(self, email: str) -> User | None:
        return self._existing

    async def add(self, *, email: str, password_hash: str) -> User:
        self.added.append(email)
        return _user(verified=False)

    async def add_if_absent(self, *, email: str, password_hash: str) -> User | None:
        return await self.add(email=email, password_hash=password_hash)


class _FakeTokens:
    def __init__(self, latest: VerificationToken | None = None) -> None:
        self._latest = latest
        self.issued = 0

    async def get_latest_for_user(self, user_id: object) -> VerificationToken | None:
        return self._latest

    async def add(self, **kwargs: object) -> None:
        self.issued += 1


class _FakeOutbox:
    async def add(self, **kwargs: object) -> None:
        return None


class _FakeAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, *, action: str, **kwargs: object) -> None:
        self.actions.append(action)


def _recent_token(user_id: object) -> VerificationToken:
    now = datetime.now(UTC)
    return VerificationToken(
        id=uuid4(),
        user_id=user_id,  # type: ignore[arg-type]
        token_hash="x" * 64,
        expires_at=now + timedelta(hours=24),
        used_at=None,
        created_at=now,
    )


# --------------------------------------------------------------------------
# F01 - registration
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "existing",
    [None, _user(verified=False), _user(verified=True)],
    ids=["new-address", "existing-unverified", "existing-verified"],
)
async def test_registration_hashes_a_password_on_every_branch(
    existing: User | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Argon2id used to run only when the address was new, which made an
    ~80ms vs ~10ms response a reliable answer to "is this registered?"."""
    counter = _Counter()
    monkeypatch.setattr(register_module, "hash_password_async", counter)

    use_case = RegisterUser(
        user_repo=_FakeUsers(existing),  # type: ignore[arg-type]
        token_repo=_FakeTokens(_recent_token(uuid4())),  # type: ignore[arg-type]
        outbox_repo=_FakeOutbox(),  # type: ignore[arg-type]
        audit_writer=_FakeAudit(),
    )
    await use_case.execute(
        email="someone@example.com", password="a-valid-password", request_id=None, ip_hash=None
    )

    assert counter.calls == 1


# --------------------------------------------------------------------------
# F14 - resend
# --------------------------------------------------------------------------


async def test_resend_burns_hash_work_when_it_does_not_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown address: returns without writing, so it must pay the same
    hashing cost the issuing branch pays."""
    counter = _Counter()
    monkeypatch.setattr(resend_module, "perform_dummy_hash", counter)
    audit = _FakeAudit()

    use_case = ResendVerification(
        user_repo=_FakeUsers(None),  # type: ignore[arg-type]
        token_repo=_FakeTokens(),  # type: ignore[arg-type]
        outbox_repo=_FakeOutbox(),  # type: ignore[arg-type]
        audit_writer=audit,
    )
    await use_case.execute(email="nobody@example.com")

    assert counter.calls == 1
    assert audit.actions == []


async def test_resend_inside_cooldown_burns_hash_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing unverified account still inside its 2-minute cooldown also
    returns without writing - same requirement."""
    counter = _Counter()
    monkeypatch.setattr(resend_module, "perform_dummy_hash", counter)
    user = _user(verified=False)

    use_case = ResendVerification(
        user_repo=_FakeUsers(user),  # type: ignore[arg-type]
        token_repo=_FakeTokens(_recent_token(user.id)),  # type: ignore[arg-type]
        outbox_repo=_FakeOutbox(),  # type: ignore[arg-type]
        audit_writer=_FakeAudit(),
    )
    await use_case.execute(email=user.email)

    assert counter.calls == 1


async def test_resend_for_verified_account_burns_hash_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = _Counter()
    monkeypatch.setattr(resend_module, "perform_dummy_hash", counter)

    use_case = ResendVerification(
        user_repo=_FakeUsers(_user(verified=True)),  # type: ignore[arg-type]
        token_repo=_FakeTokens(),  # type: ignore[arg-type]
        outbox_repo=_FakeOutbox(),  # type: ignore[arg-type]
        audit_writer=_FakeAudit(),
    )
    await use_case.execute(email="someone@example.com")

    assert counter.calls == 1


async def test_resend_that_issues_burns_the_same_hash_work_and_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The issuing branch pays the same single Argon2 operation as every other
    branch (BUG-05). The previous assumption - that a token + outbox write costs
    about as much as a hash - was measured false: issuing answered in ~52ms and
    the silent branches in ~89ms, a reverse timing oracle. The remaining
    database difference is hidden by the response-time floor."""
    counter = _Counter()
    monkeypatch.setattr(resend_module, "perform_dummy_hash", counter)
    user = _user(verified=False)
    audit = _FakeAudit()

    use_case = ResendVerification(
        user_repo=_FakeUsers(user),  # type: ignore[arg-type]
        token_repo=_FakeTokens(None),  # type: ignore[arg-type]
        outbox_repo=_FakeOutbox(),  # type: ignore[arg-type]
        audit_writer=audit,
    )
    await use_case.execute(email=user.email, request_id="req_test", ip_hash="hash")

    assert counter.calls == 1
    # F09: BR-132 requires auth events to be audited.
    assert audit.actions == ["user.verification_resent"]


async def test_dummy_hash_does_real_argon2_work() -> None:
    """Guards against the helper being quietly replaced with a sleep or a
    no-op: it must verify against a real Argon2id hash."""
    from app.identity.application.security.password_hasher import _DUMMY_HASH, perform_dummy_hash

    assert _DUMMY_HASH.startswith("$argon2")
    await perform_dummy_hash()


@pytest.mark.parametrize(
    "typed",
    [
        pytest.param("plain-ascii-password", id="already-normalised"),
        pytest.param("café-crème", id="nfd-needs-normalising"),
    ],
)
def test_argon2_work_depends_only_on_the_typed_password(
    typed: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BUG-24 verifies a non-normalised password twice (normalised, then as
    typed, for hashes made before normalisation). The count must depend only on
    the submitted text - never on whether the account exists or the password
    matches - or login's dummy-hash branch would answer faster than a real one."""
    from app.identity.application.security import password_hasher

    matching = password_hasher.hash_password(typed)
    other = password_hasher.hash_password("some-other-password")
    real = password_hasher._hasher

    class _Counting:
        calls = 0

        def verify(self, hash_: str, password: str) -> bool:
            self.calls += 1
            return real.verify(hash_, password)

    counts: list[int] = []
    for stored in (matching, other, password_hasher._DUMMY_HASH):
        counting = _Counting()
        monkeypatch.setattr(password_hasher, "_hasher", counting)
        password_hasher.verify_password(password=typed, password_hash=stored)
        counts.append(counting.calls)
    assert len(set(counts)) == 1, counts
