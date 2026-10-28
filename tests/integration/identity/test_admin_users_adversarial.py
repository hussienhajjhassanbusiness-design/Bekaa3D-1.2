"""VS-009 adversarial suite: attacks on `/api/v1/admin/users`.

Separate from `test_admin_users.py`, which tests the slice's intended behaviour.
Everything here is written from the attacker's side - malformed input, forged
credentials, hostile cursors, enumeration probes - and asserts the *contract*
rather than the implementation, so it stays meaningful if the implementation
changes.

The two findings from the adversarial review were fixed in VS-011 (an unrouted
method no longer leaks route existence; the last administrator is protected), and
their `xfail` markers removed.
"""

import base64
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import UserModel
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.identity.test_admin_users import (
    TEST_DOMAIN,
    admin_session,
    audit_rows,
    patch_active,
    register_unverified,
    reload_user,
    snapshot_cookies,
)
from tests.integration.identity.test_login import PASSWORD, register_and_verify
from tests.integration.identity.test_mfa_enrollment import (
    csrf_headers,
    make_admin,
    unique_email,
)

P = "/api/v1/admin/users"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def jar(client: TestClient) -> dict[str, str]:
    return {n: client.cookies[n] for n in ("access_token", "refresh_token", "csrf_token")}


def set_cookies(client: TestClient, cookies: dict[str, str]) -> None:
    client.cookies.clear()
    for name, value in cookies.items():
        path = "/api/v1/auth" if name == "refresh_token" else "/"
        client.cookies.set(name, value, domain=TEST_DOMAIN, path=path)


def cursor_for(created_at: datetime, user_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{user_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


async def seed(
    db: AsyncSession, token: str, count: int, *, same_time: bool = False
) -> list[uuid.UUID]:
    """Users created directly, so `created_at` can be controlled precisely."""
    base = datetime.now(UTC)
    ids = []
    for index in range(count):
        created = base if same_time else base - timedelta(seconds=index)
        model = UserModel(
            id=uuid.uuid4(),
            email=f"adv-{token}-{index:03d}@example.com",
            password_hash="x",
            created_at=created,
            updated_at=created,
        )
        db.add(model)
        ids.append(model.id)
    await db.commit()
    return ids


def walk_all(client: TestClient, params: dict[str, object], cap: int = 60) -> list[str]:
    """Page to exhaustion. Raises if pagination fails to terminate."""
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(cap):
        query = dict(params)
        if cursor is not None:
            query["cursor"] = cursor
        response = client.get(P, params=query)
        assert response.status_code == 200, response.text
        body = response.json()
        seen.extend(item["id"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return seen
    raise AssertionError(f"pagination did not terminate after {cap} pages")


# --------------------------------------------------------------------------
# 1. Authorization
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unverified_customer_is_hidden_from_every_route(
    db_session: AsyncSession,
) -> None:
    """Unverified accounts may authenticate (`can_authenticate` allows it), so
    this is a real session hitting the admin boundary - not an unauthenticated
    request in disguise."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        user = await register_unverified(client, db_session, email)
        uid = user.id
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            ).status_code
            == 200
        )
        csrf = csrf_headers(client)
        responses = [
            client.get(P),
            client.get(f"{P}/{uid}"),
            client.patch(f"{P}/{uid}", json={"is_active": False}, headers=csrf),
        ]

    for response in responses:
        assert response.status_code == 404, response.text
        assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_deactivated_admins_live_token_stops_working_at_once(
    db_session: AsyncSession,
) -> None:
    """The reason deactivation bumps the epoch at all. `require_admin` never
    re-reads `is_active`, so without the bump this token would keep full admin
    rights - including the right to turn the account back on - for the rest of
    its fifteen minutes."""
    from app.main import app

    with TestClient(app) as client:
        actor = await admin_session(client, db_session)
        csrf = csrf_headers(client)
        assert patch_active(client, actor, is_active=False).status_code == 200

        after = [
            client.get(P),
            client.get(f"{P}/{actor}"),
            client.patch(f"{P}/{actor}", json={"is_active": True}, headers=csrf),
        ]

    for response in after:
        assert response.status_code == 401, response.text
        assert response.json()["code"] == "AUTH_REQUIRED"
    assert (await reload_user(db_session, actor)).is_active is False


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_customer_cannot_forge_their_way_across_the_admin_boundary(
    db_session: AsyncSession,
) -> None:
    """Role and MFA state are read from the signed token, so the attack is to
    re-sign it. Only possession of the real signing key may work - and that is
    a key-compromise scenario, not an authorization bypass."""
    from app.main import app

    settings = get_settings()
    with TestClient(app) as client:
        email = unique_email()
        await register_and_verify(client, db_session, email)
        response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        customer = snapshot_cookies(response)

        client.cookies.clear()
        await admin_session(client, db_session)
        admin = jar(client)

        claims = jwt.decode(
            customer["access_token"], settings.jwt_signing_key, algorithms=["HS256"]
        )
        escalated = {**claims, "role": "admin", "mfa": True}

        attacks = {
            "alg=none": jwt.encode(escalated, key="", algorithm="none"),
            "wrong key": jwt.encode(escalated, "not-the-signing-key", algorithm="HS256"),
            "inflated epoch": jwt.encode(
                {**claims, "auth_epoch": 99999}, settings.jwt_signing_key, algorithm="HS256"
            ),
        }
        results = {}
        for label, token in attacks.items():
            set_cookies(client, {**customer, "access_token": token})
            results[label] = client.get(P)

        # Borrowing the administrator's other cookies must not help either: the
        # access token is the only credential the boundary reads.
        set_cookies(client, {**customer, "csrf_token": admin["csrf_token"]})
        results["admin csrf"] = client.get(P)
        set_cookies(client, {**customer, "refresh_token": admin["refresh_token"]})
        results["admin refresh"] = client.get(P)
        set_cookies(client, {"csrf_token": admin["csrf_token"]})
        results["admin csrf alone"] = client.get(P)

    for label, response in results.items():
        assert response.status_code in (401, 404), f"{label} -> {response.status_code}"
        assert response.json()["code"] in ("AUTH_REQUIRED", "NOT_FOUND"), label


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_patch_is_refused_without_this_sessions_own_csrf_token(
    db_session: AsyncSession,
) -> None:
    """And a refused PATCH must leave no trace: no state change, no audit row."""
    from app.main import app

    with TestClient(app) as client:
        email = unique_email()
        await register_and_verify(client, db_session, email)
        other = snapshot_cookies(
            client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        )
        client.cookies.clear()
        await admin_session(client, db_session)
        admin = jar(client)
        target = await register_and_verify(client, db_session, unique_email())
        tid = target.id

        refused = {}
        for label, headers in {
            "missing": {},
            "empty": {"X-CSRF-Token": ""},
            "wrong": {"X-CSRF-Token": "f" * 64},
            "another session's": {"X-CSRF-Token": other["csrf_token"]},
        }.items():
            set_cookies(client, admin)
            refused[label] = client.patch(f"{P}/{tid}", json={"is_active": False}, headers=headers)

    for label, response in refused.items():
        assert response.status_code == 403, f"{label} -> {response.status_code}"
        assert response.json()["code"] == "CSRF_INVALID", label
    assert (await reload_user(db_session, tid)).is_active is True
    assert await audit_rows(db_session, tid) == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_wrong_method_does_not_reveal_that_the_route_exists(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app) as client:
        email = unique_email()
        user = await register_and_verify(client, db_session, email)
        uid = user.id
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        real = client.delete(f"{P}/{uid}")
        imaginary = client.delete("/api/v1/admin/no-such-route")

    assert real.status_code == imaginary.status_code, (
        f"real admin path answered {real.status_code}, imaginary one "
        f"{imaginary.status_code} - the difference enumerates the admin surface"
    )


# --------------------------------------------------------------------------
# 2. Information disclosure
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_response_carries_exactly_the_contracted_fields(
    db_session: AsyncSession,
) -> None:
    """api-endpoints.md 531 fixes the schema name, and the slice fixes the field
    list. Anything extra is a leak, because every remaining `users` column is
    either a credential, a security counter or an internal lifecycle marker."""
    from app.main import app

    expected = {"id", "email", "role", "is_active", "email_verified_at", "created_at"}
    with TestClient(app) as client:
        await admin_session(client, db_session)
        target = await register_and_verify(client, db_session, unique_email())
        detail = client.get(f"{P}/{target.id}").json()
        page = client.get(P, params={"limit": 5}).json()

    assert set(detail) == expected
    assert set(page) == {"items", "next_cursor"}
    for item in page["items"]:
        assert set(item) == expected

    blob = (str(detail) + str(page)).lower()
    for forbidden in (
        "password",
        "hash",
        "auth_epoch",
        "token",
        "session",
        "secret",
        "anonymized",
        "deleted_at",
        "updated_at",
        "mfa",
        "salt",
        "ip_hash",
    ):
        assert forbidden not in blob, f"{forbidden!r} leaked into the response"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_non_administrator_cannot_tell_a_real_account_from_an_invented_one(
    db_session: AsyncSession,
) -> None:
    """The detail route is the obvious enumeration oracle: feed it ids and read
    the status. Every answer must be identical."""
    from app.main import app

    with TestClient(app) as client:
        email = unique_email()
        customer = await register_and_verify(client, db_session, email)
        real_id = customer.id
        admin = await make_admin(client, db_session, unique_email())
        admin_id = admin.id
        anonymised = UserModel(
            email=unique_email(), password_hash="x", anonymized_at=datetime.now(UTC)
        )
        db_session.add(anonymised)
        await db_session.commit()
        anon_id = anonymised.id

        client.cookies.clear()
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        answers = {
            label: client.get(f"{P}/{ident}")
            for label, ident in {
                "self": real_id,
                "an administrator": admin_id,
                "an anonymised account": anon_id,
                "a random uuid": uuid.uuid4(),
                "the nil uuid": uuid.UUID(int=0),
            }.items()
        }

    shapes = {(r.status_code, r.json()["code"]) for r in answers.values()}
    assert shapes == {(404, "NOT_FOUND")}, f"distinguishable answers: {shapes}"


# --------------------------------------------------------------------------
# 3. Search abuse
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_search_is_not_injectable_and_never_widens_the_result_set(
    db_session: AsyncSession,
) -> None:
    """Every hostile string must be treated as a literal substring. The danger
    is not a crash, it is a query that matches more than it should - so these
    assert empty results, not merely "no 500"."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        token = uuid.uuid4().hex[:10]
        await seed(db_session, token, 3)

        hostile = [
            "'",
            '"',
            "''",
            "\\",
            "\\%",
            "%",
            "_",
            "%%",
            "___",
            "%_%",
            "' OR 1=1 --",
            '" OR "1"="1',
            "; DROP TABLE users; --",
            "') OR ('1'='1",
            "%' OR email LIKE '%",
            "\\' OR 1=1 #",
            "[a-z]",
            ".*",
            "*",
            "?",
            "..",
            "../../etc/passwd",
            "<script>",
        ]
        results = {probe: client.get(P, params={"search": probe}) for probe in hostile}
        # The table is definitely non-empty, so "everything matched" is visible.
        everything = len(client.get(P, params={"limit": 100}).json()["items"])

    assert everything >= 3
    for probe, response in results.items():
        assert response.status_code == 200, f"{probe!r} -> {response.status_code}"
        assert response.json()["items"] == [], (
            f"{probe!r} matched rows - it was not treated as a literal"
        )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_wildcards_in_a_search_term_match_only_themselves(
    db_session: AsyncSession,
) -> None:
    """`%` and `_` are ordinary characters in an email address. If they reached
    LIKE unescaped, `_` would match any character and `%` would match every
    row - silently widening an administrator's view."""
    from app.main import app

    token = uuid.uuid4().hex[:10]
    with TestClient(app) as client:
        await admin_session(client, db_session)
        literal = UserModel(email=f"pct-{token}-100%_off@example.com", password_hash="x")
        plain = UserModel(email=f"pct-{token}-100xyoff@example.com", password_hash="x")
        db_session.add_all([literal, plain])
        await db_session.commit()
        literal_id, plain_id = str(literal.id), str(plain.id)

        exact = client.get(P, params={"search": "100%_off"}).json()["items"]
        wildcardish = client.get(P, params={"search": f"pct-{token}-100_"}).json()["items"]

    assert [i["id"] for i in exact] == [literal_id]
    # `_` must not act as "any character": it may match the literal row only.
    assert plain_id not in [i["id"] for i in wildcardish]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_search_folds_case_including_accents_but_not_diacritics(
    db_session: AsyncSession,
) -> None:
    """CITEXT folds case, and that is all it claims to do. Pinned because the
    behaviour depends on the column type: a change to `text` would silently make
    the search case-sensitive."""
    from app.main import app

    token = uuid.uuid4().hex[:8]
    with TestClient(app) as client:
        await admin_session(client, db_session)
        db_session.add(UserModel(email=f"MiXeD-{token}-été@Example.COM", password_hash="x"))
        await db_session.commit()

        def count(term: str) -> int:
            return len(client.get(P, params={"search": term}).json()["items"])

        matches = {
            "same case": count(f"MiXeD-{token}"),
            "lowered": count(f"mixed-{token}"),
            "uppered": count(f"MIXED-{token}"),
            "accent lower": count(f"{token}-été"),
            "accent upper": count(f"{token}-ÉTÉ"),
            "diacritic stripped": count(f"{token}-ete"),  # anonymised emails contain "ete"
        }

    assert matches["same case"] == 1
    assert matches["lowered"] == 1
    assert matches["uppered"] == 1
    assert matches["accent lower"] == 1
    assert matches["accent upper"] == 1, "citext must fold non-ASCII case too"
    assert matches["diacritic stripped"] == 0, "citext folds case, not diacritics"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_nul_byte_in_search_is_a_client_error_not_a_server_error(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        await admin_session(client, db_session)
        responses = [
            client.get(P, params={"search": "\x00"}),
            client.get(P, params={"search": "abc\x00def"}),
        ]

    for response in responses:
        assert response.status_code < 500, (
            f"NUL byte in search produced {response.status_code}: {response.text[:200]}"
        )


# --------------------------------------------------------------------------
# 4. Filters and limits
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_page_size_cannot_be_pushed_past_its_ceiling(
    db_session: AsyncSession,
) -> None:
    """No caller may force an unbounded scan or an unbounded response."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        rejected = {
            value: client.get(P + f"?limit={value}")
            for value in (
                "0",
                "-1",
                "101",
                "1000",
                "10000",
                "100000",
                "999999999",
                "1.5",
                "abc",
                "",
                "1e3",
                "9" * 40,
                "-0",
                "+101",
            )
        }
        accepted = {value: client.get(P + f"?limit={value}") for value in ("1", "2", "100")}

    for value, response in rejected.items():
        assert response.status_code == 422, f"limit={value} -> {response.status_code}"
        assert response.json()["code"] == "VALIDATION_ERROR"
    for value, response in accepted.items():
        assert response.status_code == 200, f"limit={value} -> {response.text}"
        assert len(response.json()["items"]) <= int(value)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_every_filter_combination_is_self_consistent(
    db_session: AsyncSession,
) -> None:
    """The four verified/active quadrants must partition the searched set
    exactly: no row in two quadrants, none missing from all four."""
    from app.main import app

    token = uuid.uuid4().hex[:10]
    with TestClient(app) as client:
        await admin_session(client, db_session)
        verified_active = await register_and_verify(
            client, db_session, f"adv-{token}-va@example.com"
        )
        unverified = await register_unverified(client, db_session, f"adv-{token}-uv@example.com")
        va_id, uv_id = str(verified_active.id), str(unverified.id)
        assert patch_active(client, unverified.id, is_active=False).status_code == 200

        everything = {i["id"] for i in client.get(P, params={"search": token}).json()["items"]}
        quadrants = {}
        for verified in (True, False):
            for active in (True, False):
                body = client.get(
                    P, params={"search": token, "verified": verified, "active": active}
                ).json()
                quadrants[(verified, active)] = {i["id"] for i in body["items"]}

    assert everything == {va_id, uv_id}
    assert quadrants[(True, True)] == {va_id}
    assert quadrants[(False, False)] == {uv_id}
    assert quadrants[(True, False)] == set()
    assert quadrants[(False, True)] == set()

    union: set[str] = set()
    for rows in quadrants.values():
        assert not (union & rows), "a row appeared in two quadrants"
        union |= rows
    assert union == everything, "the quadrants do not cover the searched set"


# --------------------------------------------------------------------------
# 5. Cursor attacks
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_no_hostile_cursor_is_ever_accepted_as_a_position(
    db_session: AsyncSession,
) -> None:
    """The VS-007 regression in its general form: a cursor the server cannot
    fully understand must be refused, never coerced into some position."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        token = uuid.uuid4().hex[:10]
        ids = await seed(db_session, token, 4)

        good = client.get(P, params={"search": token, "limit": 2}).json()["next_cursor"]
        assert good is not None

        hostile = {
            "garbage": "garbage",
            "not base64": "!!!!",
            "valid b64, no delimiter": "Zm9vYmFy",
            "delimiter, junk halves": "bm9wZXxub3Bl",
            "empty": "",
            "only padding": "====",
            "json": "eyJhIjoxfQ",
            "path-ish": "../../etc/passwd",
            "very long": "a" * 5000,
            "extra base64 char": good + "A",
            "truncated": good[:-1],
            "head removed": good[1:],
            "case flipped": good.upper(),
            "second delimiter": good + "fHg",
            "naive timestamp": cursor_for(datetime.now(), uuid.uuid4()),
            "bad uuid half": base64.urlsafe_b64encode(
                f"{datetime.now(UTC).isoformat()}|not-a-uuid".encode()
            )
            .decode()
            .rstrip("="),
            "bad timestamp half": base64.urlsafe_b64encode(f"not-a-time|{uuid.uuid4()}".encode())
            .decode()
            .rstrip("="),
        }
        responses = {
            label: client.get(P, params={"search": token, "cursor": c})
            for label, c in hostile.items()
        }

    assert len(ids) == 4
    for label, response in responses.items():
        assert response.status_code == 422, f"{label} -> {response.status_code}"
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR", label
        assert any("cursor" in error["loc"] for error in body["errors"]), label


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_cursor_the_parser_tolerates_still_addresses_the_same_row(
    db_session: AsyncSession,
) -> None:
    """base64 decoding discards characters outside its alphabet, so a few
    mutations survive. That is acceptable only while they cannot move the
    position - a tolerated cursor that paged from somewhere else would skip or
    repeat rows silently."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        token = uuid.uuid4().hex[:10]
        await seed(db_session, token, 6)

        good = client.get(P, params={"search": token, "limit": 2}).json()["next_cursor"]
        baseline = client.get(P, params={"search": token, "limit": 2, "cursor": good}).json()[
            "items"
        ]

        tolerated = {
            "leading spaces": "   " + good,
            "trailing space": good + " ",
            "extra padding": good + "==",
            "punctuation inserted": good[:10] + "!" + good[10:],
            "newline inserted": good[:10] + "\n" + good[10:],
            "quoted": f'"{good}"',
        }
        results = {
            label: client.get(P, params={"search": token, "limit": 2, "cursor": c})
            for label, c in tolerated.items()
        }

    for label, response in results.items():
        if response.status_code == 422:
            continue  # rejecting is also correct
        assert response.status_code == 200, label
        assert response.json()["items"] == baseline, (
            f"{label} was accepted but paged from a different position"
        )


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_identical_timestamps_are_paged_without_loss_or_repetition(
    db_session: AsyncSession,
) -> None:
    """The tie-breaker under direct attack. `created_at` alone cannot address a
    row when several share it; without the `id` half, rows straddling a page
    boundary are served twice or never."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        token = uuid.uuid4().hex[:10]
        ids = await seed(db_session, token, 9, same_time=True)
        expected = sorted((str(i) for i in ids), reverse=True)

        walks = {
            size: walk_all(client, {"search": token, "limit": size})
            for size in (1, 2, 3, 4, 5, 9, 100)
        }

    for size, seen in walks.items():
        assert len(seen) == len(set(seen)), f"limit={size} repeated rows"
        assert set(seen) == set(expected), f"limit={size} lost rows"
        assert seen == expected, f"limit={size} broke the id-descending tie-break"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_ordering_is_created_at_desc_then_id_desc_and_is_not_selectable(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        token = uuid.uuid4().hex[:10]
        await seed(db_session, token, 5)
        items = client.get(P, params={"search": token, "limit": 100}).json()["items"]
        # A caller must not be able to choose the order.
        tampered = client.get(
            P, params={"search": token, "limit": 100, "sort": "created_at", "order": "asc"}
        ).json()["items"]

    keys = [(i["created_at"], i["id"]) for i in items]
    assert keys == sorted(keys, reverse=True)
    assert [i["id"] for i in tampered] == [i["id"] for i in items]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_rows_inserted_mid_walk_are_never_served_twice(
    db_session: AsyncSession,
) -> None:
    """Keyset pagination may miss rows that appear ahead of the cursor - that is
    inherent. What it must never do is duplicate one."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        token = uuid.uuid4().hex[:10]
        await seed(db_session, token, 6)

        page1 = client.get(P, params={"search": token, "limit": 3}).json()
        await seed(db_session, f"{token}-late", 3)  # newer rows, ahead of the cursor
        seen = [i["id"] for i in page1["items"]]
        cursor = page1["next_cursor"]
        while cursor is not None:
            body = client.get(P, params={"search": token, "limit": 3, "cursor": cursor}).json()
            seen.extend(i["id"] for i in body["items"])
            cursor = body["next_cursor"]

    assert len(seen) == len(set(seen)), "a row was served twice across the insert"


# --------------------------------------------------------------------------
# 6. PATCH state machine
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_four_transitions_produce_exactly_the_right_side_effects(
    db_session: AsyncSession,
) -> None:
    """All four corners in one account's lifetime, checking the state, the
    epoch and the audit trail after each step."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        target = await register_and_verify(client, db_session, unique_email())
        tid = target.id

        steps = []
        for requested in (True, False, False, True, True):
            response = patch_active(client, tid, is_active=requested)
            row = await reload_user(db_session, tid)
            steps.append(
                (
                    requested,
                    response.status_code,
                    row.is_active,
                    row.auth_epoch,
                    len(await audit_rows(db_session, tid)),
                )
            )

    # requested, status, stored, epoch, cumulative audit rows
    assert steps == [
        (True, 200, True, 0, 0),  # no-op: nothing at all happens
        (False, 200, False, 1, 1),  # real deactivation: epoch + audit
        (False, 200, False, 1, 1),  # no-op again: no second bump, no second row
        (True, 200, True, 1, 2),  # reactivation: audited, epoch untouched
        (True, 200, True, 1, 2),  # no-op
    ], steps


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_no_field_beyond_is_active_can_be_written(db_session: AsyncSession) -> None:
    """Both halves matter: the request must be refused, *and* nothing on the row
    may move. A silently ignored `role` would read to the caller as a
    successful privilege change."""
    from app.main import app

    tracked = (
        "email",
        "password_hash",
        "role",
        "email_verified_at",
        "anonymized_at",
        "deleted_at",
        "created_at",
    )
    with TestClient(app) as client:
        await admin_session(client, db_session)
        csrf = csrf_headers(client)
        target = await register_and_verify(client, db_session, unique_email())
        tid = target.id
        before_row = await reload_user(db_session, tid)
        before = {name: getattr(before_row, name) for name in tracked}

        bodies: tuple[object, ...] = (
            {},
            {"is_active": None},
            {"role": "admin"},
            {"is_active": False, "role": "admin"},
            {"is_active": False, "email": "attacker@example.com"},
            {"is_active": False, "auth_epoch": 0},
            {"is_active": False, "password_hash": "x"},
            {"is_active": False, "deleted_at": None},
            {"IS_ACTIVE": False},
            {"is_active": []},
            {"is_active": {}},
            [],
            "string",
            123,
        )
        rejected = [client.patch(f"{P}/{tid}", json=body, headers=csrf) for body in bodies]

    for response in rejected:
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "VALIDATION_ERROR"

    after_row = await reload_user(db_session, tid)
    assert {name: getattr(after_row, name) for name in tracked} == before
    assert after_row.is_active is True
    assert after_row.auth_epoch == 0
    assert await audit_rows(db_session, tid) == []


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_successful_deactivation_touches_only_is_active_and_its_two_consequences(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    untouched = (
        "email",
        "password_hash",
        "role",
        "email_verified_at",
        "anonymized_at",
        "deleted_at",
        "created_at",
    )
    with TestClient(app) as client:
        await admin_session(client, db_session)
        target = await register_and_verify(client, db_session, unique_email())
        tid = target.id
        before_row = await reload_user(db_session, tid)
        before = {name: getattr(before_row, name) for name in untouched}
        before_updated = before_row.updated_at

        assert patch_active(client, tid, is_active=False).status_code == 200

    after = await reload_user(db_session, tid)
    assert {name: getattr(after, name) for name in untouched} == before
    assert after.is_active is False
    assert after.auth_epoch == 1
    assert after.updated_at > before_updated


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_malformed_json_is_a_400_and_a_bad_type_is_a_422(
    db_session: AsyncSession,
) -> None:
    """The project's documented split (api-endpoints.md error catalogue): a body
    that cannot be parsed is MALFORMED_REQUEST, one that parses but fails
    validation is VALIDATION_ERROR."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        csrf = csrf_headers(client)
        target = await register_and_verify(client, db_session, unique_email())
        broken = client.patch(
            f"{P}/{target.id}",
            content=b"{not json",
            headers={**csrf, "Content-Type": "application/json"},
        )
        empty = client.patch(f"{P}/{target.id}", content=b"", headers=csrf)

    assert broken.status_code == 400
    assert broken.json()["code"] == "MALFORMED_REQUEST"
    assert empty.status_code == 422
    assert empty.json()["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------
# 7. Terminal states
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_terminal_accounts_refuse_both_directions_and_audit_neither(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        rows = {
            "anonymised": UserModel(
                email=unique_email(), password_hash="x", anonymized_at=datetime.now(UTC)
            ),
            "soft-deleted": UserModel(
                email=unique_email(), password_hash="x", deleted_at=datetime.now(UTC)
            ),
            "both, already inactive": UserModel(
                email=unique_email(),
                password_hash="x",
                is_active=False,
                anonymized_at=datetime.now(UTC),
                deleted_at=datetime.now(UTC),
            ),
        }
        db_session.add_all(list(rows.values()))
        await db_session.commit()
        ids = {label: row.id for label, row in rows.items()}

        answers = {}
        for label, uid in ids.items():
            answers[label] = (
                patch_active(client, uid, is_active=False),
                patch_active(client, uid, is_active=True),
            )

    for label, (deactivate, activate) in answers.items():
        for response in (deactivate, activate):
            assert response.status_code == 409, f"{label} -> {response.status_code}"
            assert response.json()["code"] == "INVALID_STATE_TRANSITION", label
    for label, uid in ids.items():
        assert await audit_rows(db_session, uid) == [], f"{label} was audited"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_patch_against_an_unknown_id_is_a_404_and_writes_nothing(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    ghost = uuid.uuid4()
    with TestClient(app) as client:
        await admin_session(client, db_session)
        response = patch_active(client, ghost, is_active=False)

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert await audit_rows(db_session, ghost) == []


# --------------------------------------------------------------------------
# 8. Audit exactness
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_audit_row_names_the_acting_admin_and_carries_no_pii(
    db_session: AsyncSession,
) -> None:
    """`audit_logs` is retained permanently, so PII written here outlives the
    account's own anonymisation."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        actor = await admin_session(client, db_session)
        target = await register_and_verify(client, db_session, email)
        tid = target.id
        assert patch_active(client, tid, is_active=False).status_code == 200
        assert patch_active(client, tid, is_active=True).status_code == 200

    rows = await audit_rows(db_session, tid)
    assert [r.action for r in rows] == ["user.deactivated", "user.activated"]
    for row in rows:
        assert row.actor_user_id == actor, "the acting administrator must be recorded"
        assert row.entity_type == "User"
        assert row.entity_id == tid
        assert row.request_id is not None, "correlation id must reach the audit row"
        assert row.ip_hash is not None, "the actor's hashed IP must be recorded"
        payload = f"{row.before_data}{row.after_data}"
        assert "@" not in payload
        assert email not in payload
        assert email.split("@")[0] not in payload
        for banned in ("password", "hash", "role", "epoch", "token"):
            assert banned not in payload.lower(), banned

    assert rows[0].before_data == {"is_active": True}
    assert rows[0].after_data == {"is_active": False, "sessions_revoked": 0}
    assert rows[1].before_data == {"is_active": False}
    assert rows[1].after_data == {"is_active": True}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_audit_trail_is_not_pollutable_by_unauthorised_attempts(
    db_session: AsyncSession,
) -> None:
    """A customer hammering the endpoint must not be able to write rows into a
    permanently-retained table, nor make it look as though a transition
    happened."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        target = await register_and_verify(client, db_session, unique_email())
        tid = target.id

        client.cookies.clear()
        email = unique_email()
        await register_and_verify(client, db_session, email)
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        csrf = csrf_headers(client)
        for _ in range(5):
            client.patch(f"{P}/{tid}", json={"is_active": False}, headers=csrf)
        client.cookies.clear()
        for _ in range(5):
            client.patch(f"{P}/{tid}", json={"is_active": False})

    assert await audit_rows(db_session, tid) == []
    assert (await reload_user(db_session, tid)).is_active is True


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_revoked_session_count_is_accurate_and_omitted_on_activation(
    db_session: AsyncSession,
) -> None:
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, email)
        tid = target.id
        for _ in range(3):
            client.cookies.clear()
            assert (
                client.post(
                    "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
                ).status_code
                == 200
            )

        client.cookies.clear()
        await admin_session(client, db_session)
        assert patch_active(client, tid, is_active=False).status_code == 200
        assert patch_active(client, tid, is_active=True).status_code == 200

    deactivated, activated = await audit_rows(db_session, tid)
    assert deactivated.after_data == {"is_active": False, "sessions_revoked": 3}
    assert "sessions_revoked" not in (activated.after_data or {})


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_administrator_may_deactivate_a_peer_administrator(
    db_session: AsyncSession,
) -> None:
    """V1 decision: no self- or peer-protection rule. Pinned so that adding one
    later is a deliberate change rather than a silent one - and to prove the
    role column is untouched by the operation."""
    from app.main import app

    with TestClient(app) as client:
        await admin_session(client, db_session)
        peer = UserModel(email=unique_email(), password_hash="x", role=UserRole.ADMIN)
        db_session.add(peer)
        await db_session.commit()
        peer_id = peer.id
        response = patch_active(client, peer_id, is_active=False)

    assert response.status_code == 200
    row = await reload_user(db_session, peer_id)
    assert row.is_active is False
    assert row.auth_epoch == 1
    assert row.role is UserRole.ADMIN


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_unverified_administrator_still_passes_the_boundary(
    db_session: AsyncSession,
) -> None:
    """Guards an easy mistake in the opposite direction: the admin boundary is
    role + MFA, and `current_verified_user` is deliberately not in its chain, so
    a verified-email check must not creep in here."""
    from app.main import app

    with TestClient(app) as client:
        actor = await admin_session(client, db_session)
        async with db_session.begin_nested():
            row = await db_session.scalar(select(UserModel).where(UserModel.id == actor))
            assert row is not None
            row.email_verified_at = None
        await db_session.commit()
        response = client.get(P)

    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_the_login_route_still_refuses_a_deactivated_account_by_password(
    db_session: AsyncSession,
) -> None:
    """Enumeration safety at the far end of the slice: `ACCOUNT_DISABLED` is
    only reachable after the password verifies, so it cannot be used to probe
    which addresses exist."""
    from app.main import app

    email = unique_email()
    with TestClient(app) as client:
        target = await register_and_verify(client, db_session, email)
        client.cookies.clear()
        await admin_session(client, db_session)
        assert patch_active(client, target.id, is_active=False).status_code == 200

        client.cookies.clear()
        right = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        wrong = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pw"})
        unknown = client.post(
            "/api/v1/auth/login", json={"email": unique_email(), "password": PASSWORD}
        )

    assert right.status_code == 403
    assert right.json()["code"] == "ACCOUNT_DISABLED"
    # A wrong password on a disabled account is indistinguishable from a wrong
    # password on an account that does not exist.
    assert (wrong.status_code, wrong.json()["code"]) == (
        unknown.status_code,
        unknown.json()["code"],
    )


def test_audit_log_model_is_imported() -> None:
    """Keeps the AuditLogModel import meaningful for readers of this file."""
    assert AuditLogModel.__tablename__ == "audit_logs"
