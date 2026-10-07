"""VS-002 deep edge cases: registration, verification, resend and purge.

Inputs are attacked field by field, time boundaries are pinned with
time-machine, and the races are run with genuinely concurrent requests against
one app instance and the real PostgreSQL.
"""

import time
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
import time_machine
from fastapi import FastAPI
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.engagement.infrastructure.models import NotificationModel
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import (
    MfaCredentialModel,
    PasswordResetTokenModel,
    SessionModel,
    UserModel,
    VerificationTokenModel,
)
from app.jobs.purge_unverified import purge_unverified_accounts
from app.main import app as main_app
from app.platform.infrastructure.models import AuditLogModel, EmailOutboxModel, SettingModel
from tests.integration.deep_support import (
    PASSWORD,
    TIMING_SAMPLES,
    assert_problem,
    async_client,
    client_for,
    create_user,
    describe,
    distinguishable,
    fresh_ip,
    running_app,
    unique_email,
    untraced_clock,
)

REGISTER = "/api/v1/auth/register"
VERIFY = "/api/v1/auth/verify-email"
RESEND = "/api/v1/auth/resend-verification"


async def _rows_for(db: AsyncSession, email: str) -> list[UserModel]:
    db.expire_all()
    result = await db.scalars(select(UserModel).where(func.lower(UserModel.email) == email.lower()))
    return list(result.all())


async def _latest_token(db: AsyncSession, email: str) -> tuple[str, datetime]:
    """The raw token from the newest outbox row, and the token row's expiry."""
    db.expire_all()
    outbox = await db.scalar(
        select(EmailOutboxModel)
        .where(EmailOutboxModel.recipient_email == email)
        .order_by(EmailOutboxModel.created_at.desc())
        .limit(1)
    )
    assert outbox is not None
    token = await db.scalar(
        select(VerificationTokenModel)
        .join(UserModel, UserModel.id == VerificationTokenModel.user_id)
        .where(UserModel.email == email)
        .order_by(VerificationTokenModel.created_at.desc())
        .limit(1)
    )
    assert token is not None
    return str(outbox.payload["token"]), token.expires_at


# --------------------------------------------------------------------------
# Register: every field, every wrong shape
# --------------------------------------------------------------------------

_GOOD_EMAIL = "valid@example.com"
_BAD_EMAILS: list[Any] = [
    pytest.param(None, id="null"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="spaces"),
    pytest.param(123, id="number"),
    pytest.param(True, id="bool"),
    pytest.param(["a@example.com"], id="array"),
    pytest.param({"email": "a@example.com"}, id="object"),
    pytest.param("no-at-sign", id="no-at"),
    pytest.param("a@", id="no-domain"),
    pytest.param("@example.com", id="no-local"),
    pytest.param("a@localhost", id="dotless-domain"),
    pytest.param("a b@example.com", id="space-in-local"),
    pytest.param("a@exa mple.com", id="space-in-domain"),
    pytest.param("a@example..com", id="double-dot-domain"),
    pytest.param(".a@example.com", id="leading-dot-local"),
    pytest.param("a..b@example.com", id="double-dot-local"),
    pytest.param("a\u0000b@example.com", id="nul"),
    pytest.param("a\u0007b@example.com", id="bell"),
    pytest.param("a​b@example.com", id="zero-width-space"),
    pytest.param("a‮b@example.com", id="rtl-override"),
    pytest.param("a\nb@example.com", id="newline"),
    pytest.param("a@example.com\r\nBcc: x@evil.com", id="header-injection"),
    pytest.param("a@" + "b" * 250 + ".com", id="domain-255"),
    pytest.param("a" * 10_000 + "@example.com", id="10k"),
    pytest.param("a@-example.com", id="leading-hyphen-domain"),
    pytest.param("' OR 1=1 --@example.com", id="sql-quote"),
]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("email", _BAD_EMAILS)
async def test_an_invalid_email_is_a_422_and_creates_nothing(
    email: Any, db_session: AsyncSession
) -> None:
    before = await db_session.scalar(select(func.count()).select_from(UserModel))
    with client_for(main_app) as client:
        response = client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert_problem(response, 422, "VALIDATION_ERROR")
    db_session.expire_all()
    assert await db_session.scalar(select(func.count()).select_from(UserModel)) == before


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("length", [65, 200])
def test_a_local_part_over_64_octets_is_refused(length: int) -> None:
    with client_for(main_app) as client:
        response = client.post(
            REGISTER, json={"email": "x" * length + "@example.com", "password": PASSWORD}
        )
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("password", "status"),
    [
        pytest.param(None, 422, id="null"),
        pytest.param("", 422, id="empty"),
        pytest.param("a" * 7, 422, id="len-7"),
        pytest.param("a" * 8, 202, id="len-8"),
        pytest.param("a" * 256, 202, id="len-256"),
        pytest.param("a" * 257, 422, id="len-257"),
        pytest.param("a" * 1_000_000, 422, id="1MB"),
        pytest.param(12345678, 422, id="number"),
        pytest.param(["abcdefgh"], 422, id="array"),
        pytest.param(True, 422, id="bool"),
        pytest.param("\U0001f600" * 8, 202, id="8-emoji"),
        pytest.param("\U0001f600" * 256, 202, id="256-emoji-1KiB-utf8"),
        # Control characters are refused in every request field (BUG-03).
        pytest.param("pass\u0000word", 422, id="embedded-nul"),
        pytest.param("שלוםעולם", 202, id="rtl"),
    ],
)
def test_password_length_and_type_boundaries(password: Any, status: int) -> None:
    with client_for(main_app) as client:
        response = client.post(REGISTER, json={"email": unique_email(), "password": password})
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "extra",
    [
        {"role": "admin"},
        {"is_verified": True},
        {"email_verified_at": "2020-01-01T00:00:00Z"},
        {"is_active": False},
        {"id": str(uuid.uuid4())},
        {"auth_epoch": 7},
        {"password_hash": "$argon2id$forged"},
    ],
    ids=lambda extra: next(iter(extra)),
)
async def test_mass_assignment_fields_are_refused(
    extra: dict[str, Any], db_session: AsyncSession
) -> None:
    email = unique_email()
    with client_for(main_app) as client:
        response = client.post(REGISTER, json={"email": email, "password": PASSWORD, **extra})
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert await _rows_for(db_session, email) == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_argon2_sized_attack_cannot_be_amplified(db_session: AsyncSession) -> None:
    """The longest accepted password is 256 characters - 1 KiB of UTF-8 at
    most - so one request can never make Argon2 hash megabytes."""
    with client_for(main_app) as client:
        started = time.perf_counter()
        client.post(REGISTER, json={"email": unique_email(), "password": "\U0001f600" * 256})
        elapsed = time.perf_counter() - started
    assert elapsed < 3


# --------------------------------------------------------------------------
# Email identity: case, whitespace, unicode forms and IDN must not split one
# mailbox into several accounts
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("first", "second"),
    [
        pytest.param("Case{}@Example.COM", "case{}@example.com", id="ascii-case"),
        pytest.param("Élodie{}@example.com", "élodie{}@example.com", id="unicode-case"),
        pytest.param(
            unicodedata.normalize("NFC", "josé{}@example.com"),
            unicodedata.normalize("NFD", "josé{}@example.com"),
            id="nfc-vs-nfd",
        ),
        pytest.param("u{}@bücher.de", "u{}@xn--bcher-kva.de", id="idn-unicode-vs-punycode"),
        pytest.param("u{}@BÜCHER.DE", "u{}@bücher.de", id="idn-case"),
    ],
)
async def test_two_spellings_of_one_address_are_one_account(
    first: str, second: str, db_session: AsyncSession
) -> None:
    tag = uuid.uuid4().hex[:10]
    first, second = first.format(tag), second.format(tag)
    with client_for(main_app) as client:
        a = client.post(REGISTER, json={"email": first, "password": PASSWORD})
        b = client.post(REGISTER, json={"email": second, "password": PASSWORD})
    assert a.status_code == b.status_code == 202, (a.text, b.text)
    db_session.expire_all()
    rows = (await db_session.scalars(select(UserModel).where(UserModel.email.contains(tag)))).all()
    assert len(rows) == 1, [row.email for row in rows]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_surrounding_whitespace_never_creates_a_second_account(
    db_session: AsyncSession,
) -> None:
    tag = uuid.uuid4().hex[:10]
    with client_for(main_app) as client:
        client.post(REGISTER, json={"email": f"ws{tag}@example.com", "password": PASSWORD})
        padded = client.post(
            REGISTER, json={"email": f"  ws{tag}@example.com  ", "password": PASSWORD}
        )
    assert padded.status_code in (202, 422)
    db_session.expire_all()
    rows = (await db_session.scalars(select(UserModel).where(UserModel.email.contains(tag)))).all()
    assert [row.email for row in rows] == [f"ws{tag}@example.com"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_plus_addressing_is_a_distinct_account_and_stored_verbatim(
    db_session: AsyncSession,
) -> None:
    tag = uuid.uuid4().hex[:10]
    with client_for(main_app) as client:
        for email in (f"p{tag}@example.com", f"p{tag}+shop@example.com"):
            assert (
                client.post(REGISTER, json={"email": email, "password": PASSWORD}).status_code
                == 202
            )
    db_session.expire_all()
    rows = (await db_session.scalars(select(UserModel).where(UserModel.email.contains(tag)))).all()
    assert sorted(row.email for row in rows) == [f"p{tag}+shop@example.com", f"p{tag}@example.com"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_registered_account_is_a_customer_unverified_active_epoch_zero(
    db_session: AsyncSession,
) -> None:
    email = unique_email()
    with client_for(main_app) as client:
        client.post(REGISTER, json={"email": email, "password": PASSWORD})
    [row] = await _rows_for(db_session, email)
    assert (row.role, row.email_verified_at, row.is_active, row.auth_epoch) == (
        UserRole.CUSTOMER,
        None,
        True,
        0,
    )
    assert row.password_hash.startswith("$argon2id$")
    assert PASSWORD not in row.password_hash


# --------------------------------------------------------------------------
# Enumeration: status, body, headers and timing
# --------------------------------------------------------------------------


def _shape(response: Any) -> tuple[int, bytes, list[str]]:
    varying = {"x-request-id", "date", "ratelimit-remaining", "ratelimit-reset"}
    return (
        response.status_code,
        response.content,
        sorted(name for name in response.headers if name not in varying),
    )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_register_is_byte_identical_for_new_unverified_and_verified_addresses(
    db_session: AsyncSession,
) -> None:
    unverified = await create_user(db_session, verified=False)
    verified = await create_user(db_session, verified=True)
    with client_for(main_app) as client:
        shapes = [
            _shape(client.post(REGISTER, json={"email": email, "password": PASSWORD}))
            for email in (unique_email(), unverified.email, verified.email)
        ]
    assert shapes[0] == shapes[1] == shapes[2]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_resend_is_byte_identical_for_every_account_state(db_session: AsyncSession) -> None:
    unverified = await create_user(db_session, verified=False)
    verified = await create_user(db_session, verified=True)
    deactivated = await create_user(db_session, verified=False, active=False)
    with client_for(main_app) as client:
        shapes = [
            _shape(client.post(RESEND, json={"email": email}))
            for email in (unique_email(), unverified.email, verified.email, deactivated.email)
        ]
    assert len(set(map(repr, shapes))) == 1


async def _paired_timings(
    db_session: AsyncSession, path: str, make_body: Any, *, verified: bool
) -> tuple[list[float], list[float]]:
    """Time one request per branch on a warm client, alternating the order so
    neither branch always pays for going first. Returns (existing, unknown)."""
    existing: list[float] = []
    unknown: list[float] = []
    for i in range(TIMING_SAMPLES):
        user = await create_user(db_session, verified=verified)
        with client_for(main_app) as client:
            # Warm the pool with a request that touches PostgreSQL, or whichever
            # request goes first pays for opening a connection.
            client.get("/api/v1/settings/public")
            order = [(existing, user.email), (unknown, unique_email())]
            for bucket, email in order if i % 2 else reversed(order):
                started = time.perf_counter()
                client.post(path, json=make_body(email))
                bucket.append(time.perf_counter() - started)
    return existing, unknown


@pytest.mark.timing
@untraced_clock
@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_register_timing_does_not_reveal_existing_accounts(db_session: AsyncSession) -> None:
    existing, new = await _paired_timings(
        db_session, REGISTER, lambda email: {"email": email, "password": PASSWORD}, verified=True
    )
    print("TIMING", describe(existing, new))
    assert not distinguishable(existing, new), describe(existing, new)


@pytest.mark.timing
@untraced_clock
@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_resend_timing_does_not_reveal_which_branch_ran(db_session: AsyncSession) -> None:
    issuing, silent = await _paired_timings(
        db_session, RESEND, lambda email: {"email": email}, verified=False
    )
    print("TIMING", describe(issuing, silent))
    assert not distinguishable(issuing, silent), describe(issuing, silent)


class _Argon2Counter:
    """Counts Argon2 operations - the cost the constant-work defence is built on
    - independently of how fast this machine happens to run them."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.identity.application.security import password_hasher

        self.calls = 0
        real = password_hasher._hasher

        class Wrapped:
            def hash(inner, *a: Any, **k: Any) -> str:  # noqa: N805
                self.calls += 1
                return real.hash(*a, **k)

            def verify(inner, *a: Any, **k: Any) -> bool:  # noqa: N805
                self.calls += 1
                return real.verify(*a, **k)

        monkeypatch.setattr(password_hasher, "_hasher", Wrapped())


async def _argon2_per_branch(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: Any,
    emails: list[str],
) -> list[int]:
    counter = _Argon2Counter(monkeypatch)
    counts = []
    for email in emails:
        with client_for(main_app) as client:
            before = counter.calls
            client.post(path, json=body(email))
            counts.append(counter.calls - before)
    return counts


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_register_does_the_same_argon2_work_on_every_branch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    unverified = await create_user(db_session, verified=False)
    verified = await create_user(db_session)
    counts = await _argon2_per_branch(
        db_session,
        monkeypatch,
        REGISTER,
        lambda e: {"email": e, "password": PASSWORD},
        [unique_email(), unverified.email, verified.email],
    )
    assert counts == [1, 1, 1]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_resend_does_the_same_argon2_work_on_every_branch(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    unverified = await create_user(db_session, verified=False)
    verified = await create_user(db_session)
    counts = await _argon2_per_branch(
        db_session,
        monkeypatch,
        RESEND,
        lambda e: {"email": e},
        [unique_email(), unverified.email, verified.email],
    )
    assert len(set(counts)) == 1, counts


# --------------------------------------------------------------------------
# Verify email
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("token", "status"),
    [
        pytest.param(None, 422, id="null"),
        pytest.param(123, 422, id="number"),
        pytest.param(["x"], 422, id="array"),
        pytest.param("", 400, id="empty"),
        pytest.param("   ", 400, id="spaces"),
        # Refused at the schema like any control character (BUG-03).
        pytest.param("a\u0000b", 422, id="nul"),
        pytest.param("' OR '1'='1", 400, id="sql"),
    ],
)
def test_verify_token_shapes(token: Any, status: int) -> None:
    with client_for(main_app) as client:
        response = client.post(VERIFY, json={"token": token})
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_a_megabyte_token_is_refused_at_the_schema() -> None:
    with client_for(main_app) as client:
        response = client.post(VERIFY, json={"token": "t" * 1_000_000})
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("offset", "status"),
    [
        pytest.param(timedelta(seconds=-1), 204, id="expiry-minus-1s"),
        pytest.param(timedelta(0), 410, id="exactly-expiry"),
        pytest.param(timedelta(seconds=1), 410, id="expiry-plus-1s"),
    ],
)
async def test_verification_token_expiry_boundary(
    offset: timedelta, status: int, db_session: AsyncSession
) -> None:
    email = unique_email()
    with client_for(main_app) as client:
        client.post(REGISTER, json={"email": email, "password": PASSWORD})
        raw, expires_at = await _latest_token(db_session, email)
        with time_machine.travel(expires_at + offset, tick=False):
            response = client.post(VERIFY, json={"token": raw})
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_used_token_stays_400_even_after_it_expires(db_session: AsyncSession) -> None:
    email = unique_email()
    with client_for(main_app) as client:
        client.post(REGISTER, json={"email": email, "password": PASSWORD})
        raw, expires_at = await _latest_token(db_session, email)
        assert client.post(VERIFY, json={"token": raw}).status_code == 204
        with time_machine.travel(expires_at + timedelta(days=1), tick=False):
            response = client.post(VERIFY, json={"token": raw})
    assert_problem(response, 400, "INVALID_TOKEN")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_older_token_still_works_after_a_resend(db_session: AsyncSession) -> None:
    """Resend issues a new token without burning the old one - both links in
    the inbox work, and the first one used wins."""
    email = unique_email()
    with client_for(main_app) as client:
        client.post(REGISTER, json={"email": email, "password": PASSWORD})
        first, _ = await _latest_token(db_session, email)
        with time_machine.travel(datetime.now(UTC) + timedelta(minutes=3), tick=True):
            client.post(RESEND, json={"email": email})
        second, _ = await _latest_token(db_session, email)
        assert first != second
        assert client.post(VERIFY, json={"token": first}).status_code == 204
        assert_problem(client.post(VERIFY, json={"token": second}), 400, "INVALID_TOKEN")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_one_verification_token_redeemed_concurrently_succeeds_once(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    """Five rounds of twenty simultaneous redemptions, each round with its own
    token. One interleaving can serialise by luck; five in a row cannot."""
    import asyncio

    winners_per_round: list[int] = []
    async with running_app(make_app) as app:
        for _ in range(5):
            email = unique_email()
            async with async_client(app) as client:
                await client.post(REGISTER, json={"email": email, "password": PASSWORD})
            raw, _ = await _latest_token(db_session, email)
            clients = [async_client(app) for _ in range(20)]
            try:
                responses = await asyncio.gather(
                    *(c.post(VERIFY, json={"token": raw}) for c in clients)
                )
            finally:
                for c in clients:
                    await c.aclose()
            statuses = [r.status_code for r in responses]
            assert 500 not in statuses
            winners_per_round.append(statuses.count(204))
    assert winners_per_round == [1] * 5, winners_per_round


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_emailed_verification_link_is_followable(db_session: AsyncSession) -> None:
    """BUG-09: the link used to point at the POST-only API route with `?token=`,
    so following it answered 405. It now opens the frontend's verify page with
    the token in the fragment, and the frontend POSTs that token to the API."""
    email = unique_email()
    with client_for(main_app) as client:
        client.post(REGISTER, json={"email": email, "password": PASSWORD})
        db_session.expire_all()
        outbox = await db_session.scalar(
            select(EmailOutboxModel).where(EmailOutboxModel.recipient_email == email)
        )
        assert outbox is not None
        link = urlsplit(str(outbox.payload["verification_url"]))
        frontend = urlsplit(get_settings().frontend_base_url)
        assert (link.scheme, link.netloc) == (frontend.scheme, frontend.netloc)
        assert link.path == f"{frontend.path.rstrip('/')}/verify-email"
        # Never in the query string: a fragment is not sent to any server.
        assert link.query == ""
        fragment = parse_qs(link.fragment, strict_parsing=True)
        assert list(fragment) == ["token"]
        [token] = fragment["token"]
        assert token == outbox.payload["token"]
        # The API stays POST-only, and the token from the link works there.
        assert client.get(VERIFY, params={"token": token}).status_code == 405
        assert client.post(VERIFY, json={"token": token}).status_code == 204
    db_session.expire_all()
    [user] = await _rows_for(db_session, email)
    assert user.email_verified_at is not None


# --------------------------------------------------------------------------
# Resend cooldown
# --------------------------------------------------------------------------


async def _token_count(db: AsyncSession, email: str) -> int:
    db.expire_all()
    count = await db.scalar(
        select(func.count())
        .select_from(VerificationTokenModel)
        .join(UserModel, UserModel.id == VerificationTokenModel.user_id)
        .where(UserModel.email == email)
    )
    return int(count or 0)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("elapsed", "issues"),
    [
        pytest.param(timedelta(seconds=119), False, id="cooldown-minus-1s"),
        pytest.param(timedelta(seconds=120), True, id="exactly-cooldown"),
        pytest.param(timedelta(seconds=121), True, id="cooldown-plus-1s"),
    ],
)
async def test_resend_cooldown_boundary(
    elapsed: timedelta, issues: bool, db_session: AsyncSession
) -> None:
    email = unique_email()
    with client_for(main_app) as client:
        client.post(REGISTER, json={"email": email, "password": PASSWORD})
        db_session.expire_all()
        created = await db_session.scalar(
            select(VerificationTokenModel.created_at)
            .join(UserModel, UserModel.id == VerificationTokenModel.user_id)
            .where(UserModel.email == email)
        )
        assert created is not None
        with time_machine.travel(created + elapsed, tick=False):
            assert client.post(RESEND, json={"email": email}).status_code == 202
    assert await _token_count(db_session, email) == (2 if issues else 1)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_concurrent_resends_issue_at_most_one_email(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    import asyncio

    user = await create_user(db_session, verified=False)
    async with running_app(make_app) as app:
        clients = [async_client(app) for _ in range(10)]
        try:
            responses = await asyncio.gather(
                *(c.post(RESEND, json={"email": user.email}) for c in clients)
            )
        finally:
            for c in clients:
                await c.aclose()
    assert {r.status_code for r in responses} == {202}
    assert await _token_count(db_session, user.email) == 1


# --------------------------------------------------------------------------
# Duplicate registration race
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_concurrent_registration_of_one_address_is_uniformly_202(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    import asyncio

    email = unique_email()
    async with running_app(make_app) as app:
        clients = [async_client(app) for _ in range(10)]
        try:
            responses = await asyncio.gather(
                *(c.post(REGISTER, json={"email": email, "password": PASSWORD}) for c in clients)
            )
        finally:
            for c in clients:
                await c.aclose()
    assert sorted(r.status_code for r in responses) == [202] * 10
    assert len(await _rows_for(db_session, email)) == 1


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_concurrent_registration_never_creates_two_accounts(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    """The half of the race that holds: whatever the losers see, the database
    index guarantees exactly one row."""
    import asyncio

    email = unique_email()
    async with running_app(make_app) as app:
        clients = [async_client(app) for _ in range(10)]
        try:
            await asyncio.gather(
                *(c.post(REGISTER, json={"email": email, "password": PASSWORD}) for c in clients)
            )
        finally:
            for c in clients:
                await c.aclose()
    assert len(await _rows_for(db_session, email)) == 1


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_re_registration_that_reissues_mail_is_audited(db_session: AsyncSession) -> None:
    email = unique_email()
    with client_for(main_app) as client:
        client.post(REGISTER, json={"email": email, "password": PASSWORD})
        with time_machine.travel(datetime.now(UTC) + timedelta(minutes=3), tick=True):
            client.post(REGISTER, json={"email": email, "password": PASSWORD})
    assert await _token_count(db_session, email) == 2
    [user] = await _rows_for(db_session, email)
    actions = (
        await db_session.scalars(
            select(AuditLogModel.action).where(AuditLogModel.entity_id == user.id)
        )
    ).all()
    assert actions.count("user.registered") == 1
    assert "user.verification_resent" in actions


# --------------------------------------------------------------------------
# Purge
# --------------------------------------------------------------------------


def _ctx(engine: AsyncEngine) -> dict[str, Any]:
    return {"session_factory": async_sessionmaker(engine, expire_on_commit=False)}


async def _period(db: AsyncSession) -> int:
    db.expire_all()
    value = await db.scalar(
        select(SettingModel.value).where(SettingModel.key == "unverified_account_purge_period")
    )
    assert isinstance(value, int)
    return value


@pytest.mark.integration
@pytest.mark.parametrize(
    ("age_offset", "purged"),
    [
        pytest.param(timedelta(seconds=-1), False, id="one-second-younger-than-cutoff"),
        pytest.param(timedelta(0), False, id="exactly-at-cutoff"),
        pytest.param(timedelta(microseconds=1), True, id="one-microsecond-older"),
    ],
)
async def test_purge_cutoff_boundary(
    age_offset: timedelta, purged: bool, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    now = datetime.now(UTC).replace(microsecond=500_000)
    period = await _period(db_session)
    user = await create_user(db_session, verified=False)
    uid = user.id
    await db_session.execute(
        update(UserModel)
        .where(UserModel.id == uid)
        .values(created_at=now - timedelta(seconds=period) - age_offset)
    )
    await db_session.commit()
    with time_machine.travel(now, tick=False):
        await purge_unverified_accounts(_ctx(db_engine))
    db_session.expire_all()
    assert (await db_session.get(UserModel, uid) is None) is purged


@pytest.mark.integration
async def test_purge_takes_every_child_row_and_nulls_every_reference(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    """Every table that points at `users` must let the purge through: a single
    RESTRICT foreign key anywhere would make the daily job fail outright."""
    user = await create_user(db_session, verified=False)
    uid, email = user.id, user.email
    now = datetime.now(UTC)
    db_session.add_all(
        [
            SessionModel(
                id=uuid.uuid4(),
                user_id=uid,
                refresh_token_hash=uuid.uuid4().hex,
                expires_at=now + timedelta(days=1),
            ),
            PasswordResetTokenModel(user_id=uid, token_hash=uuid.uuid4().hex, expires_at=now),
            VerificationTokenModel(user_id=uid, token_hash=uuid.uuid4().hex, expires_at=now),
            MfaCredentialModel(user_id=uid, secret_ciphertext=b"x"),
            NotificationModel(user_id=uid, type="account", payload={"event": "x"}),
            AuditLogModel(actor_user_id=uid, action="deep.test", entity_type="User", entity_id=uid),
            EmailOutboxModel(user_id=uid, recipient_email=email, template="t", payload={}),
        ]
    )
    await db_session.commit()
    await db_session.execute(
        update(UserModel).where(UserModel.id == uid).values(created_at=now - timedelta(days=400))
    )
    await db_session.commit()

    await purge_unverified_accounts(_ctx(db_engine))

    db_session.expire_all()
    assert await db_session.get(UserModel, uid) is None
    for model in (
        SessionModel,
        PasswordResetTokenModel,
        VerificationTokenModel,
        MfaCredentialModel,
        NotificationModel,
    ):
        assert (
            await db_session.scalar(
                select(func.count()).select_from(model).where(model.user_id == uid)
            )
            == 0
        ), model.__name__
    audit = await db_session.scalar(
        select(AuditLogModel).where(
            AuditLogModel.entity_id == uid, AuditLogModel.action == "deep.test"
        )
    )
    assert audit is not None and audit.actor_user_id is None
    outbox = await db_session.scalar(
        select(EmailOutboxModel).where(EmailOutboxModel.recipient_email == email)
    )
    assert outbox is not None and outbox.user_id is None


@pytest.mark.integration
async def test_purge_never_deletes_an_administrator(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    admin = await create_user(db_session, verified=False, role=UserRole.ADMIN)
    admin_id = admin.id
    await db_session.execute(
        update(UserModel)
        .where(UserModel.id == admin_id)
        .values(created_at=datetime.now(UTC) - timedelta(days=400))
    )
    await db_session.commit()
    await purge_unverified_accounts(_ctx(db_engine))
    db_session.expire_all()
    assert await db_session.get(UserModel, admin_id) is not None


@pytest.mark.integration
async def test_two_purges_racing_delete_each_account_once(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    import asyncio

    ids = []
    for _ in range(5):
        user = await create_user(db_session, verified=False)
        ids.append(user.id)
    await db_session.execute(
        update(UserModel)
        .where(UserModel.id.in_(ids))
        .values(created_at=datetime.now(UTC) - timedelta(days=400))
    )
    await db_session.commit()
    results = await asyncio.gather(
        purge_unverified_accounts(_ctx(db_engine)), purge_unverified_accounts(_ctx(db_engine))
    )
    assert sum(results) >= 5
    db_session.expire_all()
    remaining = await db_session.scalar(
        select(func.count()).select_from(UserModel).where(UserModel.id.in_(ids))
    )
    assert remaining == 0


# --------------------------------------------------------------------------
# Registration rate limit
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_the_register_limit_is_exact_and_ignores_spoofed_forwarding_headers() -> None:
    ip = fresh_ip()
    with client_for(main_app, ip=ip) as client:
        remaining = []
        for n in range(5):
            response = client.post(
                REGISTER,
                json={"email": unique_email(), "password": PASSWORD},
                headers={"X-Forwarded-For": f"203.0.113.{n}", "X-Real-IP": f"198.51.100.{n}"},
            )
            assert response.status_code == 202
            remaining.append(response.headers["ratelimit-remaining"])
        sixth = client.post(
            REGISTER,
            json={"email": unique_email(), "password": PASSWORD},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
    assert remaining == ["4", "3", "2", "1", "0"]
    assert_problem(sixth, 429, "RATE_LIMITED")
    with client_for(main_app) as other:
        assert (
            other.post(REGISTER, json={"email": unique_email(), "password": PASSWORD}).status_code
            == 202
        )
