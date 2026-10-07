"""`/api/v1/me/notifications`: ownership, filtering, pagination and read state.

The authentication boundary itself is VS-003/VS-006 work and is not
reimplemented here - these tests check that it is genuinely inherited, and then
concentrate on what is new: that a customer sees only their own rows, that the
read filter and cursor behave, and that marking read is idempotent.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engagement.domain.enums import NotificationType
from app.engagement.infrastructure.models import NotificationModel
from tests.integration.identity.test_login import PASSWORD, register_and_verify
from tests.integration.identity.test_mfa_enrollment import csrf_headers, unique_email

PATH = "/api/v1/me/notifications"


def _login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


async def _register_unverified(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 202, response.text


async def seed(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    *,
    count: int = 1,
    created_at: datetime | None = None,
    stagger: bool = True,
    read: bool = False,
) -> list[uuid.UUID]:
    """Insert notifications directly.

    Straight to the model rather than through `create_notification`, because
    these tests need control over `created_at` - which the writer service
    correctly does not offer, since real notifications are always "now".
    """
    base = created_at or datetime.now(UTC)
    ids: list[uuid.UUID] = []
    for index in range(count):
        row = NotificationModel(
            user_id=user_id,
            type=NotificationType.ACCOUNT,
            payload={"event": "account.test", "n": index},
            created_at=base + timedelta(seconds=index) if stagger else base,
            read_at=base if read else None,
        )
        db_session.add(row)
        await db_session.flush()
        ids.append(row.id)
    await db_session.commit()
    return ids


async def _user_with_session(client: TestClient, db_session: AsyncSession) -> tuple[uuid.UUID, str]:
    email = unique_email()
    user = await register_and_verify(client, db_session, email)
    _login(client, email)
    return user.id, email


def _page(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(PATH, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_listing_without_a_session_is_unauthenticated() -> None:
    from app.main import app

    with TestClient(app) as client:
        client.cookies.clear()
        response = client.get(PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_patching_without_a_session_is_unauthenticated() -> None:
    from app.main import app

    with TestClient(app) as client:
        client.cookies.clear()
        response = client.patch(f"{PATH}/{uuid.uuid4()}", json={"read": True})

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unverified_customer_may_read_but_not_mark(db_session: AsyncSession) -> None:
    """api-endpoints.md 14.3: reading is `Authenticated`, marking is
    `Verified Customer`. Both halves in one test, because the interesting claim
    is the *difference* between them."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await _register_unverified(client, email)
        _login(client, email)

        listing = client.get(PATH)
        patch = client.patch(
            f"{PATH}/{uuid.uuid4()}", json={"read": True}, headers=csrf_headers(client)
        )

    assert listing.status_code == 200, listing.text
    assert patch.status_code == 403
    assert patch.json()["code"] == "EMAIL_VERIFICATION_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_patch_without_the_csrf_header_is_rejected(db_session: AsyncSession) -> None:
    """SEC-03 covers every unsafe cookie-authenticated method. Distinguished
    from the verification refusal by its code, since both are 403."""
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        (notification_id,) = await seed(db_session, user_id)
        response = client.patch(f"{PATH}/{notification_id}", json={"read": True})

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_INVALID"


# --------------------------------------------------------------------------
# Ownership
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_list_contains_only_the_callers_own_notifications(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app) as client:
        mine, _ = await _user_with_session(client, db_session)
        stranger = uuid.uuid4()

        # A second real account, so the foreign rows are genuinely reachable
        # data rather than orphans the query could miss for another reason.
        other_email = unique_email()
        other = await register_and_verify(client, db_session, other_email)
        stranger = other.id

        my_ids = await seed(db_session, mine, count=3)
        their_ids = await seed(db_session, stranger, count=3)

        # Log back in as the first user; register_and_verify above did not
        # change the session, but be explicit rather than rely on that.
        body = _page(client, limit=100)

    returned = {item["id"] for item in body["items"]}
    assert returned >= {str(i) for i in my_ids}
    assert returned.isdisjoint({str(i) for i in their_ids})


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_marking_someone_elses_notification_is_indistinguishable_from_a_missing_one(
    db_session: AsyncSession,
) -> None:
    """The IDOR test, and the existence-oracle test, are the same test.

    A 403 for "not yours" and a 404 for "no such thing" would let a customer
    enumerate other people's notification ids by watching which code comes back.
    """
    from app.main import app

    with TestClient(app) as client:
        await _user_with_session(client, db_session)

        stranger = await register_and_verify(client, db_session, unique_email())
        (theirs,) = await seed(db_session, stranger.id)

        # Log back in as the first user - registering the stranger replaced the
        # session cookies on this client.
        mine_email = unique_email()
        user = await register_and_verify(client, db_session, mine_email)
        _login(client, mine_email)
        (mine,) = await seed(db_session, user.id)

        headers = csrf_headers(client)
        foreign = client.patch(f"{PATH}/{theirs}", json={"read": True}, headers=headers)
        missing = client.patch(f"{PATH}/{uuid.uuid4()}", json={"read": True}, headers=headers)
        own = client.patch(f"{PATH}/{mine}", json={"read": True}, headers=headers)

    assert own.status_code == 200, own.text

    assert foreign.status_code == 404
    assert missing.status_code == 404
    # Byte-for-byte the same problem document, apart from the per-request fields.
    ignored = {"instance", "request_id"}
    assert {k: v for k, v in foreign.json().items() if k not in ignored} == {
        k: v for k, v in missing.json().items() if k not in ignored
    }

    # And the foreign row was not silently modified on the way to being refused.
    row = await db_session.get(NotificationModel, theirs)
    assert row is not None
    await db_session.refresh(row)
    assert row.read_at is None


# --------------------------------------------------------------------------
# Read / unread
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_marking_read_then_unread_round_trips(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        (notification_id,) = await seed(db_session, user_id)
        headers = csrf_headers(client)

        read = client.patch(f"{PATH}/{notification_id}", json={"read": True}, headers=headers)
        unread = client.patch(f"{PATH}/{notification_id}", json={"read": False}, headers=headers)

    assert read.status_code == 200, read.text
    assert read.json()["read"] is True
    assert unread.json()["read"] is False

    # read_at is the persistence detail behind the flag and is not part of the
    # V1 contract.
    assert "read_at" not in read.json()


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_marking_read_twice_preserves_the_first_read_timestamp(
    db_session: AsyncSession,
) -> None:
    """`read_at` records when the customer *first* saw it. Pressing the button
    again is a successful no-op, not a new timestamp - which is what COALESCE in
    the UPDATE buys, and what makes the operation genuinely idempotent."""
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        (notification_id,) = await seed(db_session, user_id)
        headers = csrf_headers(client)

        first = client.patch(f"{PATH}/{notification_id}", json={"read": True}, headers=headers)
        assert first.status_code == 200, first.text

        row = await db_session.get(NotificationModel, notification_id)
        assert row is not None
        await db_session.refresh(row)
        stamp = row.read_at
        assert stamp is not None

        second = client.patch(f"{PATH}/{notification_id}", json={"read": True}, headers=headers)
        assert second.status_code == 200
        assert second.json()["read"] is True

        db_session.expire_all()
        again = await db_session.get(NotificationModel, notification_id)
        assert again is not None

    assert again.read_at == stamp


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_marking_unread_twice_stays_unread(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        (notification_id,) = await seed(db_session, user_id, read=True)
        headers = csrf_headers(client)

        first = client.patch(f"{PATH}/{notification_id}", json={"read": False}, headers=headers)
        second = client.patch(f"{PATH}/{notification_id}", json={"read": False}, headers=headers)

    assert first.json()["read"] is False
    assert second.status_code == 200
    assert second.json()["read"] is False


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unknown_body_field_is_rejected(db_session: AsyncSession) -> None:
    """`extra="forbid"`, per the project's request-schema convention."""
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        (notification_id,) = await seed(db_session, user_id)
        response = client.patch(
            f"{PATH}/{notification_id}",
            json={"read": True, "read_at": "2026-01-01T00:00:00Z"},
            headers=csrf_headers(client),
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_read_filter_selects_each_half(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        unread_ids = await seed(db_session, user_id, count=3)
        read_ids = await seed(db_session, user_id, count=2, read=True)

        unread_page = _page(client, limit=100, read=False)
        read_page = _page(client, limit=100, read=True)
        everything = _page(client, limit=100)

    unread_returned = {item["id"] for item in unread_page["items"]}
    read_returned = {item["id"] for item in read_page["items"]}

    assert unread_returned == {str(i) for i in unread_ids}
    assert read_returned == {str(i) for i in read_ids}
    assert all(item["read"] is False for item in unread_page["items"])
    assert all(item["read"] is True for item in read_page["items"])

    # Unfiltered is the union, so the filter is selecting rather than hiding.
    assert {item["id"] for item in everything["items"]} == unread_returned | read_returned


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_cursor_walks_every_notification_exactly_once(
    db_session: AsyncSession,
) -> None:
    """Real pagination, not a `next_cursor` that is always null.

    Every row shares one `created_at`. That is the whole point: with distinct
    timestamps this test passes even with the `id` tie-breaker removed, so it
    would be decorative. Identical timestamps mean the sort is ambiguous unless
    `id` disambiguates it, and an ambiguous sort serves one row twice and
    another never.
    """
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        seeded = await seed(
            db_session, user_id, count=7, created_at=datetime.now(UTC), stagger=False
        )

        seen: list[str] = []
        cursor: str | None = None
        for _ in range(20):  # a bound, so a non-terminating cursor fails loudly
            params: dict[str, Any] = {"limit": 2}
            if cursor:
                params["cursor"] = cursor
            body = _page(client, **params)
            seen.extend(item["id"] for item in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break

    assert cursor is None, "pagination did not terminate"
    assert len(seen) == len(set(seen)), f"a notification was served twice: {seen}"
    assert set(seen) == {str(i) for i in seeded}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_first_page_is_newest_first_and_reports_a_next_cursor(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        seeded = await seed(db_session, user_id, count=5)

        body = _page(client, limit=2)

    assert body["next_cursor"] is not None
    assert len(body["items"]) == 2
    # Newest first: the last two seeded, in reverse order.
    assert [item["id"] for item in body["items"]] == [str(seeded[4]), str(seeded[3])]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_last_page_reports_no_next_cursor(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        await seed(db_session, user_id, count=2)
        body = _page(client, limit=100)

    assert body["next_cursor"] is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_tampered_cursor_is_a_validation_error(db_session: AsyncSession) -> None:
    """422 VALIDATION_ERROR, the project's ordinary answer for a bad query
    parameter - a tampered cursor needs no error code of its own."""
    from app.main import app

    with TestClient(app) as client:
        await _user_with_session(client, db_session)
        response = client.get(PATH, params={"cursor": "!!!not-base64!!!"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_page_size_is_bounded(db_session: AsyncSession) -> None:
    """api-endpoints.md 2: maximum page size 100."""
    from app.main import app

    with TestClient(app) as client:
        await _user_with_session(client, db_session)
        too_large = client.get(PATH, params={"limit": 101})
        too_small = client.get(PATH, params={"limit": 0})
        largest = client.get(PATH, params={"limit": 100})

    assert too_large.status_code == 422
    assert too_small.status_code == 422
    assert largest.status_code == 200


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_empty_notification_centre_is_an_empty_list(db_session: AsyncSession) -> None:
    """api-endpoints.md 2: `"items": []`, not null and not a 404."""
    from app.main import app

    with TestClient(app) as client:
        await _user_with_session(client, db_session)
        body = _page(client)

    assert body["items"] == []
    assert body["next_cursor"] is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_payload_is_returned_verbatim(db_session: AsyncSession) -> None:
    """The payload is display data and is passed through unchanged - a client
    renders from it, so a field quietly dropped here is a blank in the UI."""
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        await seed(db_session, user_id)
        body = _page(client)

    assert body["items"][0]["payload"] == {"event": "account.test", "n": 0}
    assert body["items"][0]["type"] == "account"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_deleted_account_cannot_list_notifications(db_session: AsyncSession) -> None:
    """Consistency with `GET /me`: the token stays signed, but the account
    behind it no longer authenticates."""
    from app.identity.infrastructure.models import UserModel
    from app.main import app

    with TestClient(app) as client:
        user_id, _ = await _user_with_session(client, db_session)
        await seed(db_session, user_id)
        assert client.get(PATH).status_code == 200

        row = await db_session.scalar(select(UserModel).where(UserModel.id == user_id))
        assert row is not None
        row.is_active = False
        await db_session.commit()

        response = client.get(PATH)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
