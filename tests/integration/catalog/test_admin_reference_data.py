"""`/api/v1/admin/{categories,materials,colours}`.

The admin boundary itself is VS-005 work and is not reimplemented here - these
tests check that it is genuinely inherited, then concentrate on what is new:
the three-state lifecycle, slug conflicts, the audit trail, and cursor
pagination.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.infrastructure.models import CategoryModel
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.identity.test_login import PASSWORD, register_and_verify
from tests.integration.identity.test_mfa_enrollment import (
    csrf_headers,
    enrol_admin,
    login,
    login_challenged,
    login_totp,
    make_admin,
    unique_email,
)

CATEGORIES = "/api/v1/admin/categories"
MATERIALS = "/api/v1/admin/materials"
COLOURS = "/api/v1/admin/colours"
VERIFY_PATH = "/api/v1/auth/mfa/verify"


async def _admin_session(client: TestClient, db_session: AsyncSession) -> uuid.UUID:
    """An administrator with a fully MFA-complete session.

    One MFA login per test on purpose: `login_totp` returns a code for a single
    time-step and VS-005's replay guard correctly refuses to accept the same OTP
    twice, so a second login inside one test would fail for a reason that has
    nothing to do with reference data.
    """
    email = unique_email()
    user = await make_admin(client, db_session, email)
    login(client, email)
    secret, _ = enrol_admin(client)
    challenge = login_challenged(client, email)
    completed = client.post(
        VERIFY_PATH, json={"challenge_id": challenge, "code": login_totp(secret)}
    )
    assert completed.status_code == 204, completed.text
    return user.id


def _slug() -> str:
    return f"cat-{uuid.uuid4().hex[:12]}"


def _create_category(client: TestClient, **overrides: Any) -> dict[str, Any]:
    body = {"name": "Lamps", "slug": _slug()} | overrides
    response = client.post(CATEGORIES, json=body, headers=csrf_headers(client))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


# The three admin resources, for tests that must hold on every one of them. The
# material and colour routes are separate copies of the category ones, so a
# test written against categories alone proves nothing about the other two
# (audit A-01/A-03/A-04/A-07).
RESOURCES = [
    pytest.param(CATEGORIES, "category", "Category", id="category"),
    pytest.param(MATERIALS, "material", "Material", id="material"),
    pytest.param(COLOURS, "colour", "Colour", id="colour"),
]
PUBLIC_PATHS = {
    CATEGORIES: "/api/v1/categories",
    MATERIALS: "/api/v1/materials",
    COLOURS: "/api/v1/colours",
}


def _unique_name(prefix: str = "val") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _create(client: TestClient, path: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"name": _unique_name()}
    if path == CATEGORIES:
        body["slug"] = _slug()
    body |= overrides
    response = client.post(path, json=body, headers=csrf_headers(client))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def _public_ids(client: TestClient, path: str, sentinel_id: str) -> set[str]:
    """IDs on the capped public list, refusing to answer vacuously.

    `sentinel_id` is a live row the test created to sort after the rows it
    asserts are hidden. If the sentinel is missing, those rows may simply lie
    past the 100-row cap, and "not in the list" would prove nothing (A-06).
    """
    response = client.get(PUBLIC_PATHS[path])
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert sentinel_id in ids, "sentinel outside the capped public window"
    return ids


async def _audit_rows(db_session: AsyncSession, entity_id: str) -> list[AuditLogModel]:
    db_session.expire_all()
    return list(
        await db_session.scalars(
            select(AuditLogModel)
            .where(AuditLogModel.entity_id == uuid.UUID(entity_id))
            .order_by(AuditLogModel.created_at)
        )
    )


# --------------------------------------------------------------------------
# The admin boundary is inherited, not reimplemented
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("path", [CATEGORIES, MATERIALS, COLOURS])
def test_an_unauthenticated_caller_is_told_to_authenticate(path: str) -> None:
    from app.main import app

    with TestClient(app) as client:
        client.cookies.clear()
        response = client.get(path)

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("path", [CATEGORIES, MATERIALS, COLOURS])
async def test_a_customer_gets_404_not_403(db_session: AsyncSession, path: str) -> None:
    """SEC-10: a 403 would confirm the route exists."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await register_and_verify(client, db_session, email)
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        response = client.get(path)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_without_completed_mfa_is_refused(db_session: AsyncSession) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        await make_admin(client, db_session, email)
        login(client, email)
        response = client.get(CATEGORIES)

    assert response.status_code == 401
    assert response.json()["code"] == "MFA_REQUIRED"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "prefix", "entity_type"), RESOURCES)
async def test_unsafe_methods_require_the_csrf_header(
    db_session: AsyncSession, path: str, prefix: str, entity_type: str
) -> None:
    """SEC-03 covers every unsafe cookie-authenticated method, on every resource."""
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        created = _create(client, path)
        body: dict[str, Any] = {"name": _unique_name()}
        if path == CATEGORIES:
            body["slug"] = _slug()

        post = client.post(path, json=body)
        patch = client.patch(f"{path}/{created['id']}", json={"name": _unique_name()})
        delete = client.delete(f"{path}/{created['id']}")
        after = client.get(f"{path}/{created['id']}").json()

    for response in (post, patch, delete):
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "CSRF_INVALID"
    # Refused means refused: nothing was renamed or archived.
    assert after["name"] == created["name"]
    assert after["deleted_at"] is None


# --------------------------------------------------------------------------
# Categories: create, read, update, archive
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_creating_a_category_returns_operational_state(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        created = _create_category(client, name="Desk Lamps")

    assert set(created) == {
        "id",
        "name",
        "slug",
        "is_active",
        "deleted_at",
        "created_at",
        "updated_at",
    }
    assert created["name"] == "Desk Lamps"
    assert created["is_active"] is True
    assert created["deleted_at"] is None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_duplicate_live_slug_is_a_conflict(db_session: AsyncSession) -> None:
    """Enforced by the partial unique index, not by a read-then-write check."""
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        slug = _slug()
        _create_category(client, slug=slug)
        response = client.post(
            CATEGORIES, json={"name": "Other", "slug": slug}, headers=csrf_headers(client)
        )

    assert response.status_code == 409
    assert response.json()["code"] == "SLUG_CONFLICT"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_patching_onto_a_live_slug_is_a_conflict(db_session: AsyncSession) -> None:
    """The second write path the live-slug index guards (audit A-02).

    A re-slug is caught when `CategoryRepository.save` flushes, not on insert,
    so it needs its own test: without the translation there, the unique
    violation escapes as an unhandled IntegrityError. The uppercase attempt
    proves normalisation runs before the write rather than letting a case
    variant slip past the index.
    """
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        taken = _create_category(client)
        mine = _create_category(client)
        headers = csrf_headers(client)

        exact = client.patch(
            f"{CATEGORIES}/{mine['id']}", json={"slug": taken["slug"]}, headers=headers
        )
        upper = client.patch(
            f"{CATEGORIES}/{mine['id']}", json={"slug": taken["slug"].upper()}, headers=headers
        )
        after = client.get(f"{CATEGORIES}/{mine['id']}").json()

    for response in (exact, upper):
        assert response.status_code == 409, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["code"] == "SLUG_CONFLICT"
    assert after["slug"] == mine["slug"], "a refused re-slug must not be stored"
    actions = [row.action for row in await _audit_rows(db_session, mine["id"])]
    assert "category.updated" not in actions, "a refused PATCH must not be audited"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_malformed_slug_is_rejected(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.post(
            CATEGORIES, json={"name": "Bad", "slug": "Not A Slug"}, headers=csrf_headers(client)
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_empty_patch_is_rejected(db_session: AsyncSession) -> None:
    """A PATCH that sets nothing can only mean the caller built the request
    wrongly - distinct from one that submits the values already stored."""
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        created = _create_category(client)
        response = client.patch(
            f"{CATEGORIES}/{created['id']}", json={}, headers=csrf_headers(client)
        )

    assert response.status_code == 422


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_disabled_category_can_be_reactivated(db_session: AsyncSession) -> None:
    """The documented route back from `is_active=false`, and the reason disable
    and archive have to stay distinct states."""
    from app.main import app

    with TestClient(app) as client:
        admin_id = await _admin_session(client, db_session)
        created = _create_category(client)
        headers = csrf_headers(client)

        disabled = client.patch(
            f"{CATEGORIES}/{created['id']}", json={"is_active": False}, headers=headers
        )
        public_while_disabled = client.get("/api/v1/categories").json()["items"]
        reactivated = client.patch(
            f"{CATEGORIES}/{created['id']}", json={"is_active": True}, headers=headers
        )
        public_after = client.get("/api/v1/categories").json()["items"]

    assert disabled.json()["is_active"] is False
    assert disabled.json()["deleted_at"] is None, "disabling must not archive"
    assert created["id"] not in {item["id"] for item in public_while_disabled}

    assert reactivated.json()["is_active"] is True
    assert created["id"] in {item["id"] for item in public_after}
    assert admin_id


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_archiving_hides_publicly_but_stays_admin_readable(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        prefix = f"00-{uuid.uuid4().hex[:12]}"
        created = _create_category(client, name=f"{prefix}-a")
        sentinel = _create_category(client, name=f"{prefix}-z")

        archived = client.delete(f"{CATEGORIES}/{created['id']}", headers=csrf_headers(client))
        detail = client.get(f"{CATEGORIES}/{created['id']}")
        public = _public_ids(client, CATEGORIES, sentinel["id"])

    assert archived.status_code == 204
    assert detail.status_code == 200
    body = detail.json()
    # Archiving sets both columns together.
    assert body["deleted_at"] is not None
    assert body["is_active"] is False
    assert created["id"] not in public


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "prefix", "entity_type"), RESOURCES)
async def test_an_archived_value_cannot_be_mutated(
    db_session: AsyncSession, path: str, prefix: str, entity_type: str
) -> None:
    """V1 ships no restore endpoint, so archiving is terminal for the ordinary
    admin surface - on all three resources (audit A-03). Reuses the
    catalogue's existing state-machine code rather than inventing one.

    Checks the row and the audit trail as well as the status: a refusal that
    still wrote the change, or audited it, would be a different bug with the
    same status code.
    """
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        created = _create(client, path)
        headers = csrf_headers(client)
        assert client.delete(f"{path}/{created['id']}", headers=headers).status_code == 204
        archived = client.get(f"{path}/{created['id']}").json()

        renamed = client.patch(
            f"{path}/{created['id']}", json={"name": _unique_name()}, headers=headers
        )
        reactivated = client.patch(
            f"{path}/{created['id']}", json={"is_active": True}, headers=headers
        )
        rearchived = client.delete(f"{path}/{created['id']}", headers=headers)
        after = client.get(f"{path}/{created['id']}").json()

    for response in (renamed, reactivated, rearchived):
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "INVALID_STATE_TRANSITION"
    assert after == archived, "a refused mutation changed the archived row"

    actions = [row.action for row in await _audit_rows(db_session, created["id"])]
    assert actions == [f"{prefix}.created", f"{prefix}.archived"], actions


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_archiving_releases_the_slug_through_the_api(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        slug = _slug()
        first = _create_category(client, slug=slug)
        client.delete(f"{CATEGORIES}/{first['id']}", headers=csrf_headers(client))
        second = client.post(
            CATEGORIES, json={"name": "Reused", "slug": slug}, headers=csrf_headers(client)
        )

    assert second.status_code == 201, second.text
    assert second.json()["id"] != first["id"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unknown_id_is_a_hidden_404(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.get(f"{CATEGORIES}/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------
# Materials and colours
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("path", "public_path"), [(MATERIALS, "/api/v1/materials"), (COLOURS, "/api/v1/colours")]
)
async def test_simple_values_round_trip_through_their_lifecycle(
    db_session: AsyncSession, path: str, public_path: str
) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        headers = csrf_headers(client)
        # Sorts near the front of the capped public list, with a live sentinel
        # after it, so the final "not public" check cannot pass vacuously (A-06).
        name = f"00-{uuid.uuid4().hex[:12]}-resin"
        sentinel = _create(client, path, name=f"{name}-z")

        created = client.post(path, json={"name": name}, headers=headers)
        assert created.status_code == 201, created.text
        value_id = created.json()["id"]
        assert "slug" not in created.json(), "materials and colours have no slug"

        renamed = client.patch(
            f"{path}/{value_id}", json={"name": f"{name}-tough"}, headers=headers
        )
        detail = client.get(f"{path}/{value_id}")
        archived = client.delete(f"{path}/{value_id}", headers=headers)
        after_archive = client.get(f"{path}/{value_id}")
        public = _public_ids(client, path, sentinel["id"])

    assert public_path == PUBLIC_PATHS[path]
    assert renamed.json()["name"] == f"{name}-tough"
    assert detail.status_code == 200
    assert archived.status_code == 204
    assert after_archive.json()["deleted_at"] is not None
    assert value_id not in public


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("path", "prefix"),
    [
        pytest.param(MATERIALS, "material", id="material"),
        pytest.param(COLOURS, "colour", id="colour"),
    ],
)
async def test_a_live_name_is_unique_ignoring_case(
    db_session: AsyncSession, path: str, prefix: str
) -> None:
    """Q-1: materials and colours are facet values, so "PLA" beside "pla" would
    split one filter into two (SRS 592). Both write paths - create and rename -
    answer with the existing `409 SLUG_CONFLICT`, store nothing and audit
    nothing; archiving releases the name, as archiving a category releases its
    slug."""
    from app.main import app

    name = f"Pla-{uuid.uuid4().hex[:8]}"
    with TestClient(app) as client:
        await _admin_session(client, db_session)
        headers = csrf_headers(client)
        first = _create(client, path, name=name)
        other = _create(client, path)

        duplicate = client.post(path, json={"name": name.upper()}, headers=headers)
        renamed_onto = client.patch(
            f"{path}/{other['id']}", json={"name": name.lower()}, headers=headers
        )
        other_after = client.get(f"{path}/{other['id']}").json()

        assert client.delete(f"{path}/{first['id']}", headers=headers).status_code == 204
        reused = client.post(path, json={"name": name.upper()}, headers=headers)

    for response in (duplicate, renamed_onto):
        assert response.status_code == 409, response.text
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["code"] == "SLUG_CONFLICT"
    assert other_after["name"] == other["name"], "a refused rename must not be stored"
    actions = [row.action for row in await _audit_rows(db_session, other["id"])]
    assert f"{prefix}.updated" not in actions, "a refused rename must not be audited"

    assert reused.status_code == 201, "archiving must release the name"
    assert reused.json()["id"] != first["id"]


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(("path", "prefix", "entity_type"), RESOURCES)
async def test_every_mutation_is_audited(
    db_session: AsyncSession, path: str, prefix: str, entity_type: str
) -> None:
    """BR-132 / FR-04: every administrator write leaves exactly one audit row,
    naming the actor, the entity and what changed - on all three resources
    (audit A-04)."""
    from app.main import app

    with TestClient(app) as client:
        admin_id = await _admin_session(client, db_session)
        headers = csrf_headers(client)
        created = _create(client, path)
        new_name = _unique_name("renamed")
        patched = client.patch(f"{path}/{created['id']}", json={"name": new_name}, headers=headers)
        archived = client.delete(f"{path}/{created['id']}", headers=headers)

    assert patched.status_code == 200, patched.text
    assert archived.status_code == 204, archived.text

    rows = await _audit_rows(db_session, created["id"])
    assert [row.action for row in rows] == [
        f"{prefix}.created",
        f"{prefix}.updated",
        f"{prefix}.archived",
    ]
    assert all(row.entity_type == entity_type for row in rows)
    assert all(row.actor_user_id == admin_id for row in rows)

    create, update, archive = rows
    assert create.before_data is None
    assert create.after_data is not None and create.after_data["name"] == created["name"]
    assert update.before_data is not None and update.before_data["name"] == created["name"]
    assert update.after_data is not None and update.after_data["name"] == new_name
    assert archive.before_data is not None and archive.before_data["deleted_at"] is None
    assert archive.after_data is not None and archive.after_data["deleted_at"] is not None


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_no_op_patch_is_audited_without_moving_the_timestamp(
    db_session: AsyncSession,
) -> None:
    """The VS-007 convention: submitting the values already stored is a
    successful request that changes nothing, still audited, with `updated_at`
    describing when the row last actually moved."""
    from app.main import app

    with TestClient(app) as client:
        admin_id = await _admin_session(client, db_session)
        created = _create_category(client, name="Steady")
        response = client.patch(
            f"{CATEGORIES}/{created['id']}",
            json={"name": "Steady"},
            headers=csrf_headers(client),
        )

    assert response.status_code == 200
    assert response.json()["updated_at"] == created["updated_at"]

    db_session.expire_all()
    rows = list(
        await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.actor_user_id == admin_id,
                AuditLogModel.action == "category.updated",
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].before_data == rows[0].after_data


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_rejected_create_writes_no_audit_row(db_session: AsyncSession) -> None:
    """Mutation and audit share one transaction."""
    from app.main import app

    with TestClient(app) as client:
        admin_id = await _admin_session(client, db_session)
        slug = _slug()
        _create_category(client, slug=slug)
        refused = client.post(
            CATEGORIES, json={"name": "Refused", "slug": slug}, headers=csrf_headers(client)
        )

    assert refused.status_code == 409

    db_session.expire_all()
    rows = list(
        await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.actor_user_id == admin_id,
                AuditLogModel.action == "category.created",
            )
        )
    )
    assert len(rows) == 1, "only the successful create should be audited"


# --------------------------------------------------------------------------
# Cursor pagination
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_admin_cursor_walks_every_row_exactly_once(db_session: AsyncSession) -> None:
    """Every seeded row shares one name.

    That is the point: with distinct names this test passes even with the `id`
    tie-breaker removed, so it would be decorative. Identical names make the
    sort ambiguous unless `id` disambiguates it, and an ambiguous sort serves
    one row twice and another never.
    """
    shared = f"same-{uuid.uuid4().hex[:8]}"
    for _ in range(7):
        db_session.add(CategoryModel(name=shared, slug=_slug(), is_active=True))
    await db_session.commit()

    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)

        seen: list[str] = []
        cursor: str | None = None
        for _ in range(20):
            params: dict[str, Any] = {"limit": 2}
            if cursor:
                params["cursor"] = cursor
            body = client.get(CATEGORIES, params=params).json()
            seen.extend(item["id"] for item in body["items"] if item["name"] == shared)
            cursor = body["next_cursor"]
            if cursor is None:
                break

    assert cursor is None, "pagination did not terminate"
    assert len(seen) == len(set(seen)), f"a row was served twice: {seen}"
    assert len(seen) == 7


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_tampered_cursor_is_a_validation_error(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        response = client.get(CATEGORIES, params={"cursor": "!!!not-base64!!!"})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_admin_page_size_is_bounded(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        too_large = client.get(CATEGORIES, params={"limit": 101})
        largest = client.get(CATEGORIES, params={"limit": 100})

    assert too_large.status_code == 422
    assert largest.status_code == 200


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_archived_rows_appear_only_when_asked_for(db_session: AsyncSession) -> None:
    from app.main import app

    with TestClient(app) as client:
        await _admin_session(client, db_session)
        created = _create_category(client)
        client.delete(f"{CATEGORIES}/{created['id']}", headers=csrf_headers(client))

        default_page = client.get(CATEGORIES, params={"limit": 100}).json()
        with_deleted = client.get(CATEGORIES, params={"limit": 100, "include_deleted": True}).json()

    assert created["id"] not in {item["id"] for item in default_page["items"]}
    assert created["id"] in {item["id"] for item in with_deleted["items"]}
