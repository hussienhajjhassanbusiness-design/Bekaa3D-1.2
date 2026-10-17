"""VS-008 deep edge cases: the notification centre and its write port."""

import asyncio
import base64
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.engagement.domain.enums import NotificationType
from app.engagement.domain.exceptions import InvalidNotificationPayloadError
from app.engagement.infrastructure.models import NotificationModel
from app.engagement.public import create_notification
from app.main import app as main_app
from tests.integration.deep_support import (
    assert_problem,
    async_client,
    client_for,
    create_user,
    csrf,
    login,
    running_app,
)

LIST = "/api/v1/me/notifications"


async def _notify(db: AsyncSession, user_id: uuid.UUID, count: int = 1) -> list[uuid.UUID]:
    ids = []
    for n in range(count):
        row = await create_notification(
            db,
            user_id=user_id,
            notification_type=NotificationType.ACCOUNT,
            payload={"event": f"deep.{n}"},
        )
        ids.append(row.id)
    await db.commit()
    return ids


def _cursor(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


# --------------------------------------------------------------------------
# PATCH body and id shapes
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="empty"),
        pytest.param({"read": None}, id="null"),
        pytest.param({"read": []}, id="array"),
        pytest.param({"read": {}}, id="object"),
        pytest.param({"read": "maybe"}, id="word"),
        pytest.param({"read": 2}, id="two"),
        pytest.param({"read": True, "read_at": "2020-01-01T00:00:00Z"}, id="read-at-smuggled"),
        pytest.param({"read": True, "user_id": str(uuid.uuid4())}, id="user-id-smuggled"),
    ],
)
async def test_patch_body_shapes_are_422_and_change_nothing(
    body: dict[str, Any], db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    [nid] = await _notify(db_session, user.id)
    with client_for(main_app) as client:
        login(client, user.email)
        response = client.patch(f"{LIST}/{nid}", json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")
    db_session.expire_all()
    row = await db_session.get(NotificationModel, nid)
    assert row is not None and row.read_at is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("notification_id", "status"),
    [
        pytest.param("not-a-uuid", 422, id="not-uuid"),
        pytest.param("00000000-0000-0000-0000-000000000000", 404, id="nil"),
        pytest.param(str(uuid.uuid4()), 404, id="random"),
        pytest.param("1", 422, id="sequential-guess"),
        pytest.param("%00", 422, id="nul"),
    ],
)
async def test_patch_id_shapes(notification_id: str, status: int, db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        response = client.patch(
            f"{LIST}/{notification_id}", json={"read": True}, headers=csrf(client)
        )
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_another_users_notification_is_indistinguishable_and_untouched(
    db_session: AsyncSession,
) -> None:
    owner = await create_user(db_session)
    intruder = await create_user(db_session)
    [nid] = await _notify(db_session, owner.id)
    with client_for(main_app) as client:
        login(client, intruder.email)
        foreign = client.patch(f"{LIST}/{nid}", json={"read": True}, headers=csrf(client))
        missing = client.patch(f"{LIST}/{uuid.uuid4()}", json={"read": True}, headers=csrf(client))
        listed = client.get(LIST).json()["items"]
    assert (foreign.status_code, foreign.json()["code"], foreign.json()["detail"]) == (
        missing.status_code,
        missing.json()["code"],
        missing.json()["detail"],
    )
    assert listed == []
    db_session.expire_all()
    row = await db_session.get(NotificationModel, nid)
    assert row is not None and row.read_at is None


# --------------------------------------------------------------------------
# List query shapes and cursors
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=-1",
        "limit=abc",
        "read=maybe",
        "cursor=",
        "cursor=!!!",
        "cursor=" + _cursor("no-separator"),
        "cursor=" + _cursor("2026-01-01T00:00:00|not-a-uuid"),
        "cursor=" + _cursor(f"2026-01-01T00:00:00|{uuid.uuid4()}"),
        "cursor=" + _cursor(f"yesterday|{uuid.uuid4()}"),
        "cursor=" + _cursor(f"\u0000|{uuid.uuid4()}"),
        "cursor=" + "A" * 10_000,
    ],
    ids=[
        "limit-0",
        "limit-101",
        "limit-neg",
        "limit-word",
        "read-word",
        "cursor-empty",
        "cursor-junk",
        "cursor-no-sep",
        "cursor-bad-uuid",
        "cursor-naive-datetime",
        "cursor-word-date",
        "cursor-nul",
        "cursor-10k",
    ],
)
async def test_list_query_shapes_are_422(query: str, db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, user.email)
        response = client.get(f"{LIST}?{query}")
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "stamp",
    ["0001-01-01T00:00:00+00:00", "9999-12-31T23:59:59+00:00"],
    ids=["year-1-utc", "year-9999-utc"],
)
async def test_extreme_but_representable_cursors_are_answered(
    stamp: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await _notify(db_session, user.id)
    with client_for(main_app) as client:
        login(client, user.email)
        response = client.get(f"{LIST}?cursor={_cursor(f'{stamp}|{uuid.uuid4()}')}")
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "stamp",
    ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"],
    ids=["year-0-after-utc", "year-10000-after-utc"],
)
async def test_an_out_of_range_cursor_is_a_client_error(
    stamp: str, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, user.email)
        response = client.get(f"{LIST}?cursor={_cursor(f'{stamp}|{uuid.uuid4()}')}")
    assert_problem(response, 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------
# The write port
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"event": "x", "blob": "y" * (16 * 1024)}, id="over-16KiB"),
        pytest.param({"event": ""}, id="empty-event"),
        pytest.param({"event": "   "}, id="blank-event"),
        pytest.param({"event": 1}, id="numeric-event"),
        pytest.param({"no": "event"}, id="missing-event"),
        pytest.param({"event": "x", "n": float("nan")}, id="nan"),
        pytest.param({"event": "x", "n": float("inf")}, id="inf"),
        pytest.param({"event": "x", "s": {1, 2}}, id="set"),
        pytest.param({"event": "x", "s": "\ud800"}, id="lone-surrogate"),
        pytest.param({1: "x", "event": "y"}, id="int-key"),
        pytest.param(["event"], id="not-a-dict"),
    ],
)
async def test_invalid_payloads_are_rejected_before_the_database(
    payload: Any, db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        with pytest.raises(InvalidNotificationPayloadError):
            await create_notification(
                session,
                user_id=user.id,
                notification_type=NotificationType.ACCOUNT,
                payload=payload,
            )


@pytest.mark.integration
async def test_a_payload_of_exactly_16_kib_is_accepted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    import json

    user = await create_user(db_session)
    base = {"event": "x", "blob": ""}
    overhead = len(json.dumps(base, separators=(",", ":"), sort_keys=True).encode())
    payload = {"event": "x", "blob": "y" * (16 * 1024 - overhead)}
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        row = await create_notification(
            session, user_id=user.id, notification_type=NotificationType.ORDER, payload=payload
        )
    assert row.payload == payload


@pytest.mark.integration
async def test_a_nul_in_a_payload_is_rejected_by_the_port(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        with pytest.raises(InvalidNotificationPayloadError):
            await create_notification(
                session,
                user_id=user.id,
                notification_type=NotificationType.ORDER,
                payload={"event": "order.shipped", "product_name": "Lamp\u0000"},
            )


@pytest.mark.integration
async def test_a_deeply_nested_payload_is_rejected_by_the_port(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    nested: dict[str, Any] = {"event": "x"}
    cursor = nested
    for _ in range(5000):
        cursor["n"] = {}
        cursor = cursor["n"]
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        with pytest.raises(InvalidNotificationPayloadError):
            await create_notification(
                session, user_id=user.id, notification_type=NotificationType.ORDER, payload=nested
            )


@pytest.mark.integration
async def test_a_notification_rides_the_callers_transaction(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    uid = user.id
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        await session.begin()
        await create_notification(
            session,
            user_id=uid,
            notification_type=NotificationType.PAYMENT,
            payload={"event": "rolled.back"},
        )
        await session.rollback()
    db_session.expire_all()
    rows = (
        await db_session.scalars(select(NotificationModel).where(NotificationModel.user_id == uid))
    ).all()
    assert rows == []


@pytest.mark.integration
async def test_every_notification_type_round_trips_and_nothing_else_is_accepted(
    db_engine: AsyncEngine, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        for kind in NotificationType:
            await create_notification(
                session, user_id=user.id, notification_type=kind, payload={"event": kind.value}
            )
    async with factory() as session:
        with pytest.raises(InvalidNotificationPayloadError):
            await create_notification(
                session,
                user_id=user.id,
                notification_type="order",  # type: ignore[arg-type]
                payload={"event": "x"},
            )
    assert {k.value for k in NotificationType} == {
        "account",
        "order",
        "payment",
        "refund",
        "offer",
        "download",
        "custom_request",
    }


# --------------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_twenty_parallel_toggles_leave_one_consistent_state(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    [nid] = await _notify(db_session, user.id)
    async with running_app(make_app) as app:
        async with async_client(app) as seed:
            await seed.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "correct-horse-battery"},
            )
            cookies = dict(seed.cookies.items())
        clients = [async_client(app) for _ in range(20)]
        for c in clients:
            for name, value in cookies.items():
                c.cookies.set(name, value)
        try:
            responses = await asyncio.gather(
                *(
                    c.patch(
                        f"{LIST}/{nid}",
                        json={"read": n % 2 == 0},
                        headers={"X-CSRF-Token": cookies["csrf_token"]},
                    )
                    for n, c in enumerate(clients)
                )
            )
        finally:
            for c in clients:
                await c.aclose()
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    db_session.expire_all()
    row = await db_session.get(NotificationModel, nid)
    assert row is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_the_first_read_timestamp_survives_twenty_parallel_marks(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    [nid] = await _notify(db_session, user.id)
    async with running_app(make_app) as app:
        async with async_client(app) as seed:
            await seed.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "correct-horse-battery"},
            )
            cookies = dict(seed.cookies.items())
            first = await seed.patch(
                f"{LIST}/{nid}",
                json={"read": True},
                headers={"X-CSRF-Token": cookies["csrf_token"]},
            )
            assert first.status_code == 200
        db_session.expire_all()
        original = (await db_session.get(NotificationModel, nid)).read_at  # type: ignore[union-attr]
        clients = [async_client(app) for _ in range(20)]
        for c in clients:
            for name, value in cookies.items():
                c.cookies.set(name, value)
        try:
            await asyncio.gather(
                *(
                    c.patch(
                        f"{LIST}/{nid}",
                        json={"read": True},
                        headers={"X-CSRF-Token": cookies["csrf_token"]},
                    )
                    for c in clients
                )
            )
        finally:
            for c in clients:
                await c.aclose()
    db_session.expire_all()
    assert (await db_session.get(NotificationModel, nid)).read_at == original  # type: ignore[union-attr]
