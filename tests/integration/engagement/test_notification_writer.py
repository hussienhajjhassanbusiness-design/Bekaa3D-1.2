"""`create_notification`: the sanctioned cross-context write port.

The property that matters most is the one that is easiest to lose accidentally -
that the service does **not** commit. A notification must live or die with the
business event that caused it, and a service that committed on its own would
announce changes that were still able to fail.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.engagement.domain.enums import NotificationType
from app.engagement.domain.exceptions import InvalidNotificationPayloadError
from app.engagement.domain.payload import MAX_PAYLOAD_BYTES
from app.engagement.infrastructure.models import NotificationModel
from app.engagement.public import create_notification
from app.identity.infrastructure.models import UserModel

PAYLOAD = {"event": "account.test"}


async def _user(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as db, db.begin():
        user = UserModel(email=f"test-{uuid.uuid4().hex}@example.com", password_hash="x")
        db.add(user)
        await db.flush()
        return user.id


async def _exists(
    session_factory: async_sessionmaker[AsyncSession], notification_id: uuid.UUID
) -> bool:
    async with session_factory() as db:
        return await db.get(NotificationModel, notification_id) is not None


@pytest.mark.integration
async def test_the_writer_persists_a_notification(db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _user(session_factory)

    async with session_factory() as db, db.begin():
        created = await create_notification(
            db, user_id=user_id, notification_type=NotificationType.ORDER, payload=PAYLOAD
        )

    assert await _exists(session_factory, created.id)
    assert created.type is NotificationType.ORDER
    assert created.payload == PAYLOAD
    # Born unread, with a server-assigned identity and timestamp.
    assert created.read_at is None
    assert created.read is False
    assert created.created_at is not None


@pytest.mark.integration
async def test_the_writer_does_not_commit_on_its_own(db_engine: AsyncEngine) -> None:
    """The central guarantee. The transaction is rolled back without the writer
    ever being told, and the row must be gone.

    If `create_notification` committed, this row would survive - and a future
    payment slice would be able to tell a customer their payment succeeded
    moments before the payment transaction rolled back.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _user(session_factory)

    async with session_factory() as db:
        await db.begin()
        created = await create_notification(
            db, user_id=user_id, notification_type=NotificationType.PAYMENT, payload=PAYLOAD
        )
        # Visible inside the transaction that created it...
        assert await db.get(NotificationModel, created.id) is not None
        await db.rollback()

    # ...and gone once that transaction goes.
    assert not await _exists(session_factory, created.id)


@pytest.mark.integration
async def test_a_failure_after_the_notification_takes_the_notification_with_it(
    db_engine: AsyncEngine,
) -> None:
    """The realistic shape of the same property: the notification is written
    first, and the business work that follows it fails."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _user(session_factory)

    created_id: uuid.UUID | None = None
    with pytest.raises(RuntimeError):
        async with session_factory() as db, db.begin():
            created = await create_notification(
                db, user_id=user_id, notification_type=NotificationType.OFFER, payload=PAYLOAD
            )
            created_id = created.id
            raise RuntimeError("the business operation failed after the notification")

    assert created_id is not None
    assert not await _exists(session_factory, created_id)


@pytest.mark.integration
async def test_the_writer_shares_the_callers_transaction(db_engine: AsyncEngine) -> None:
    """Two notifications and a business change commit together, which is the
    composition the port exists to allow."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _user(session_factory)

    async with session_factory() as db, db.begin():
        first = await create_notification(
            db, user_id=user_id, notification_type=NotificationType.ORDER, payload=PAYLOAD
        )
        second = await create_notification(
            db, user_id=user_id, notification_type=NotificationType.DOWNLOAD, payload=PAYLOAD
        )

    assert await _exists(session_factory, first.id)
    assert await _exists(session_factory, second.id)


@pytest.mark.integration
async def test_an_invalid_payload_is_refused_before_it_reaches_the_database(
    db_engine: AsyncEngine,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _user(session_factory)

    for payload in (
        {"detail": "no event"},
        {"event": ""},
        {"event": "a", "d": "x" * (MAX_PAYLOAD_BYTES + 1)},
        ["not", "an", "object"],
        # Strict-JSON cases, against a real PostgreSQL rather than only in the
        # unit tests: these are exactly the values that would otherwise pass
        # validation and then fail inside asyncpg at flush time.
        {"event": "account.test", "amount": float("nan")},
        {"event": "account.test", "amount": float("inf")},
        {"event": "account.test", "at": datetime.now(UTC)},
    ):
        async with session_factory() as db, db.begin():
            with pytest.raises(InvalidNotificationPayloadError):
                await create_notification(
                    db,
                    user_id=user_id,
                    notification_type=NotificationType.ACCOUNT,
                    payload=payload,  # type: ignore[arg-type]
                )

    async with session_factory() as db:
        rows = (
            await db.scalars(select(NotificationModel).where(NotificationModel.user_id == user_id))
        ).all()
    assert rows == []


@pytest.mark.integration
async def test_a_bare_string_type_is_refused(db_engine: AsyncEngine) -> None:
    """Otherwise it reaches asyncpg and fails as an opaque enum bind error a
    long way from the caller."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _user(session_factory)

    async with session_factory() as db, db.begin():
        with pytest.raises(InvalidNotificationPayloadError):
            await create_notification(
                db,
                user_id=user_id,
                notification_type="account",  # type: ignore[arg-type]
                payload=PAYLOAD,
            )


@pytest.mark.integration
async def test_deleting_a_user_cascades_to_their_notifications(db_engine: AsyncEngine) -> None:
    """FR-02 physically purges never-verified accounts, and `user_id` is NOT
    NULL - so SET NULL is not representable and CASCADE is not a preference but
    the only workable behaviour. Without it the purge job would fail on a
    foreign-key violation the first time an unverified account had a
    notification.

    Uses an isolated throwaway user so nothing else in the suite is affected.
    """
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    user_id = await _user(session_factory)

    async with session_factory() as db, db.begin():
        created = await create_notification(
            db, user_id=user_id, notification_type=NotificationType.ACCOUNT, payload=PAYLOAD
        )
    assert await _exists(session_factory, created.id)

    async with session_factory() as db, db.begin():
        user = await db.get(UserModel, user_id)
        assert user is not None
        await db.delete(user)

    assert not await _exists(session_factory, created.id)
