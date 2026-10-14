"""VS-026 / FR-03: `/api/v1/me/addresses` - ownership, the verified-write boundary, CSRF,
Lebanese validation, the cap, soft delete and the one-default rule."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.domain.address import MAX_LIVE_ADDRESSES
from app.identity.infrastructure.models import AddressModel, UserModel
from app.main import app as main_app
from tests.integration.deep_support import assert_problem, client_for, create_user, csrf, login

PATH = "/api/v1/me/addresses"
pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


def _body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "label": "Home",
        "recipient_name": "Rima Haddad",
        "phone": "03 123 456",
        "governorate": "beqaa",
        "city": "Zahle",
        "area": "Hoch el Oumara",
        "street": "Main street",
        "landmark_notes": "Blue gate opposite the bakery",
    }
    return body | overrides


async def _signed_in(client: TestClient, db: AsyncSession, *, verified: bool = True) -> UserModel:
    user = await create_user(db, verified=verified)
    login(client, user.email)
    return user


def _create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post(PATH, json=_body(**overrides), headers=csrf(client))
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def _rows(db: AsyncSession, user_id: uuid.UUID) -> list[AddressModel]:
    stmt = (
        select(AddressModel)
        .where(AddressModel.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return list((await db.scalars(stmt)).all())


async def _live_defaults(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    return [r.id for r in await _rows(db, user_id) if r.is_default and r.deleted_at is None]


async def _seed(db: AsyncSession, user_id: uuid.UUID, count: int) -> None:
    for index in range(count):
        db.add(
            AddressModel(
                user_id=user_id,
                label=f"Seeded {index}",
                recipient_name="Seed",
                phone="+9613123456",
                governorate="beirut",
                city="Beirut",
                landmark_notes="seeded",
            )
        )
    await db.commit()


# --------------------------------------------------------------------------
# Create, read, list
# --------------------------------------------------------------------------


async def test_create_normalises_and_returns_the_address(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        created = _create(client, label="  Home  ", phone="+961 71 123 456", area="  ")
        read = client.get(f"{PATH}/{created['id']}")
    assert read.status_code == 200
    assert read.json() == created
    assert set(created) == {
        "id",
        "label",
        "recipient_name",
        "phone",
        "governorate",
        "city",
        "area",
        "street",
        "landmark_notes",
        "is_default",
        "created_at",
        "updated_at",
    }
    assert (created["label"], created["phone"], created["area"]) == ("Home", "+96171123456", None)
    [row] = await _rows(db_session, user.id)
    assert row.phone == "+96171123456"


async def test_first_address_is_default_and_later_ones_are_not(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        first = _create(client, is_default=False)
        second = _create(client)
        listed = client.get(PATH).json()["items"]
    assert (first["is_default"], second["is_default"]) == (True, False)
    assert [item["id"] for item in listed] == [first["id"], second["id"]]
    assert await _live_defaults(db_session, user.id) == [uuid.UUID(first["id"])]


async def test_list_is_default_first_then_newest(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        ids = [_create(client, label=f"A{n}")["id"] for n in range(3)]
        listed = [item["id"] for item in client.get(PATH).json()["items"]]
    assert listed == [ids[0], ids[2], ids[1]]


async def test_create_with_is_default_moves_the_default(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        _create(client)
        newer = _create(client, is_default=True)
    assert await _live_defaults(db_session, user.id) == [uuid.UUID(newer["id"])]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phone", "+33 6 12 34 56 78"),
        ("phone", "123"),
        ("governorate", "paris"),
        ("label", "   "),
        ("recipient_name", "x" * 101),
        ("city", ""),
        ("landmark_notes", "   "),
        ("landmark_notes", None),
        ("street", "x" * 201),
        ("label", "Home\x00"),
        ("country", "LB"),
    ],
)
async def test_invalid_create_is_422_and_stores_nothing(
    db_session: AsyncSession, field: str, value: Any
) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        body = _body(**{field: value})
        if value is None:
            del body[field]
        response = client.post(PATH, json=body, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")
    assert field in {error["loc"][-1] for error in response.json()["errors"]}
    assert await _rows(db_session, user.id) == []


async def test_create_beyond_the_cap_is_refused(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        await _seed(db_session, user.id, MAX_LIVE_ADDRESSES)
        response = client.post(PATH, json=_body(), headers=csrf(client))
    assert_problem(response, 422, "ADDRESS_LIMIT_REACHED")
    assert len(await _rows(db_session, user.id)) == MAX_LIVE_ADDRESSES


# --------------------------------------------------------------------------
# Update, default, delete
# --------------------------------------------------------------------------


async def test_patch_updates_only_given_fields_and_null_clears_optionals(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        created = _create(client)
        response = client.patch(
            f"{PATH}/{created['id']}",
            json={"city": "Chtaura", "street": None, "phone": "76 123 456"},
            headers=csrf(client),
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["city"], body["street"], body["phone"]) == ("Chtaura", None, "+96176123456")
    assert (body["label"], body["area"], body["is_default"]) == ("Home", "Hoch el Oumara", True)


@pytest.mark.parametrize(
    "patch",
    [{}, {"landmark_notes": None}, {"label": None}, {"governorate": "paris"}, {"bogus": 1}],
)
async def test_invalid_patch_is_422_and_changes_nothing(
    db_session: AsyncSession, patch: dict[str, Any]
) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        created = _create(client)
        response = client.patch(f"{PATH}/{created['id']}", json=patch, headers=csrf(client))
    assert_problem(response, 422, "VALIDATION_ERROR")
    [row] = await _rows(db_session, user.id)
    assert (row.label, row.landmark_notes, row.governorate) == (
        "Home",
        "Blue gate opposite the bakery",
        "beqaa",
    )


async def test_patch_is_default_switches_or_clears(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        first, second = _create(client), _create(client)
        switched = client.patch(
            f"{PATH}/{second['id']}", json={"is_default": True}, headers=csrf(client)
        )
        assert switched.json()["is_default"] is True
        assert await _live_defaults(db_session, user.id) == [uuid.UUID(second["id"])]
        client.patch(f"{PATH}/{second['id']}", json={"is_default": False}, headers=csrf(client))
    assert await _live_defaults(db_session, user.id) == []
    assert first["is_default"] is True


async def test_put_default_switches_atomically_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        _create(client)
        second = _create(client)
        for _ in range(2):
            response = client.put(f"{PATH}/{second['id']}/default", headers=csrf(client))
            assert response.status_code == 200, response.text
            assert response.json()["is_default"] is True
    assert await _live_defaults(db_session, user.id) == [uuid.UUID(second["id"])]


async def test_delete_is_soft_and_deleting_the_default_leaves_none(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        first = _create(client)
        second = _create(client)
        response = client.delete(f"{PATH}/{first['id']}", headers=csrf(client))
        assert response.status_code == 204
        assert response.content == b""
        assert [item["id"] for item in client.get(PATH).json()["items"]] == [second["id"]]
        third = _create(client)
    rows = {row.id: row for row in await _rows(db_session, user.id)}
    deleted = rows[uuid.UUID(first["id"])]
    assert deleted.deleted_at is not None
    assert deleted.is_default is False
    assert third["is_default"] is False
    assert await _live_defaults(db_session, user.id) == []


async def test_after_deleting_every_address_the_next_is_default(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        only = _create(client)
        client.delete(f"{PATH}/{only['id']}", headers=csrf(client))
        assert _create(client)["is_default"] is True


def _request(client: TestClient, method: str, address_id: str) -> Any:
    target = f"{PATH}/{address_id}"
    calls = {
        "get": lambda: client.get(target),
        "patch": lambda: client.patch(target, json={"city": "X"}, headers=csrf(client)),
        "delete": lambda: client.delete(target, headers=csrf(client)),
        "default": lambda: client.put(f"{target}/default", headers=csrf(client)),
    }
    return calls[method]()


@pytest.mark.parametrize("method", ["get", "patch", "delete", "default"])
async def test_deleted_address_is_404(db_session: AsyncSession, method: str) -> None:
    with client_for(main_app) as client:
        await _signed_in(client, db_session)
        created = _create(client)
        client.delete(f"{PATH}/{created['id']}", headers=csrf(client))
        response = _request(client, method, created["id"])
    assert_problem(response, 404, "NOT_FOUND")


# --------------------------------------------------------------------------
# Boundaries: ownership, verification, CSRF, authentication
# --------------------------------------------------------------------------


def _comparable(response: Any) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    return {key: body[key] for key in ("status", "code", "title", "detail")}


@pytest.mark.parametrize("method", ["get", "patch", "delete", "default"])
async def test_another_users_address_is_indistinguishable_from_none(
    db_session: AsyncSession, method: str
) -> None:
    with client_for(main_app) as owner_client:
        owner = await _signed_in(owner_client, db_session)
        mine = _create(owner_client)
    with client_for(main_app) as intruder:
        await _signed_in(intruder, db_session)
        foreign = _request(intruder, method, mine["id"])
        unknown = _request(intruder, method, str(uuid.uuid4()))
        assert intruder.get(PATH).json()["items"] == []
    assert_problem(foreign, 404, "NOT_FOUND")
    assert _comparable(foreign) == _comparable(unknown)
    [row] = await _rows(db_session, owner.id)
    assert (row.city, row.is_default, row.deleted_at) == ("Zahle", True, None)


async def _seed_one(db: AsyncSession, user_id: uuid.UUID) -> str:
    await _seed(db, user_id, 1)
    return str((await _rows(db, user_id))[0].id)


@pytest.mark.parametrize("method", ["create", "patch", "delete", "default"])
async def test_an_unverified_user_cannot_write(db_session: AsyncSession, method: str) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session, verified=False)
        address_id = await _seed_one(db_session, user.id)
        if method == "create":
            response = client.post(PATH, json=_body(), headers=csrf(client))
        else:
            response = _request(client, method, address_id)
    assert_problem(response, 403, "EMAIL_VERIFICATION_REQUIRED")
    [row] = await _rows(db_session, user.id)
    assert (row.city, row.is_default, row.deleted_at) == ("Beirut", False, None)


async def test_an_unverified_user_can_read(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session, verified=False)
        address_id = await _seed_one(db_session, user.id)
        assert client.get(f"{PATH}/{address_id}").status_code == 200
        assert [item["id"] for item in client.get(PATH).json()["items"]] == [address_id]


@pytest.mark.parametrize("method", ["create", "patch", "delete", "default"])
async def test_a_write_without_csrf_is_refused(db_session: AsyncSession, method: str) -> None:
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        address_id = await _seed_one(db_session, user.id)
        target = f"{PATH}/{address_id}"
        response = {
            "create": lambda: client.post(PATH, json=_body()),
            "patch": lambda: client.patch(target, json={"city": "X"}),
            "delete": lambda: client.delete(target),
            "default": lambda: client.put(f"{target}/default"),
        }[method]()
    assert_problem(response, 403, "CSRF_INVALID")
    [row] = await _rows(db_session, user.id)
    assert (row.city, row.is_default, row.deleted_at) == ("Beirut", False, None)


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("GET", ""),
        ("POST", ""),
        ("GET", "/{id}"),
        ("PATCH", "/{id}"),
        ("DELETE", "/{id}"),
        ("PUT", "/{id}/default"),
    ],
)
async def test_anonymous_is_401(method: str, suffix: str) -> None:
    with client_for(main_app) as client:
        response = client.request(
            method, PATH + suffix.format(id=uuid.uuid4()), json=_body() if method != "GET" else None
        )
    assert_problem(response, 401, "AUTH_REQUIRED")


async def test_a_users_count_is_unaffected_by_other_users(db_session: AsyncSession) -> None:
    """The cap and the first-address default are per user, not global."""
    other = await create_user(db_session)
    await _seed(db_session, other.id, MAX_LIVE_ADDRESSES)
    with client_for(main_app) as client:
        user = await _signed_in(client, db_session)
        assert _create(client)["is_default"] is True
    count = await db_session.scalar(
        select(func.count()).select_from(AddressModel).where(AddressModel.user_id == user.id)
    )
    assert count == 1
