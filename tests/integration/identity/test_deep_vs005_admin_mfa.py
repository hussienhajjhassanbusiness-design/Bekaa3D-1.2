"""VS-005 deep edge cases: the admin boundary (SEC-10) and administrator MFA.

The authorisation matrix is driven from the OpenAPI document, so every admin
operation - including ones later slices add - is attacked as every kind of
caller.
"""

import asyncio
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
import pytest
import redis.asyncio as redis_asyncio
import time_machine
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.identity.domain.enums import UserRole
from app.identity.infrastructure.models import (
    MfaCredentialModel,
    MfaRecoveryCodeModel,
    UserModel,
)
from app.main import app as main_app
from tests.integration.deep_support import (
    CONFIRM_PATH,
    PASSWORD,
    SETUP_PATH,
    assert_problem,
    async_client,
    client_for,
    create_user,
    csrf,
    login,
    mfa_admin,
    running_app,
)

VERIFY = "/api/v1/auth/mfa/verify"
REGENERATE = "/api/v1/auth/mfa/recovery-codes/regenerate"
LOGIN = "/api/v1/auth/login"
ALL_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _concrete(path: str) -> str:
    return re.sub(
        r"\{(\w+)\}",
        lambda m: "accepting_orders" if m.group(1) == "key" else str(uuid.uuid4()),
        path,
    )


def _admin_operations() -> list[tuple[str, str]]:
    paths = main_app.openapi()["paths"]
    return sorted(
        (method.upper(), _concrete(path))
        for path, operations in paths.items()
        if path.startswith("/api/v1/admin")
        for method in operations
    )


def _admin_wrong_methods() -> list[tuple[str, str]]:
    paths = main_app.openapi()["paths"]
    return sorted(
        (method, _concrete(path))
        for path, operations in paths.items()
        if path.startswith("/api/v1/admin")
        for method in (*ALL_METHODS, "OPTIONS", "HEAD")
        if method.lower() not in operations
    )


ADMIN_OPERATIONS = _admin_operations()
IMAGINARY = "/api/v1/admin/definitely-not-a-route"


def _fingerprint(response: Any) -> tuple[int, str, str, str]:
    body = response.json() if response.content else {}
    return (
        response.status_code,
        body.get("code", ""),
        body.get("title", ""),
        body.get("detail", ""),
    )


def _hit_all(client: TestClient) -> dict[tuple[str, str], Any]:
    return {
        (method, path): client.request(
            method,
            path,
            json={} if method in ("POST", "PATCH", "PUT") else None,
            headers=csrf(client) if client.cookies.get("csrf_token") else {},
        )
        for method, path in ADMIN_OPERATIONS
    }


def test_the_matrix_covers_the_admin_surface() -> None:
    assert len(ADMIN_OPERATIONS) >= 15, ADMIN_OPERATIONS


# --------------------------------------------------------------------------
# The authorisation matrix
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_anonymous_callers_get_401_on_every_admin_operation() -> None:
    with client_for(main_app) as client:
        results = _hit_all(client)
    wrong = {k: r.status_code for k, r in results.items() if r.status_code != 401}
    assert not wrong, wrong


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("verified", [True, False], ids=["verified", "unverified"])
async def test_customers_get_the_imaginary_path_404_on_every_admin_operation(
    verified: bool, db_session: AsyncSession
) -> None:
    user = await create_user(db_session, verified=verified)
    with client_for(main_app) as client:
        login(client, user.email)
        imaginary = _fingerprint(client.get(IMAGINARY))
        results = _hit_all(client)
    wrong = {k: _fingerprint(r) for k, r in results.items() if _fingerprint(r) != imaginary}
    assert imaginary[0] == 404
    assert not wrong, wrong


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_without_mfa_gets_401_mfa_required_everywhere(
    db_session: AsyncSession,
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    with client_for(main_app) as client:
        login(client, admin.email)
        results = _hit_all(client)
    wrong = {
        k: _fingerprint(r)
        for k, r in results.items()
        if _fingerprint(r)[:2] != (401, "MFA_REQUIRED")
    }
    assert not wrong, wrong


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_admin_with_mfa_passes_the_boundary_everywhere(db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        results = _hit_all(client)
    # Past the boundary a route may still refuse the request (empty body, unknown
    # id) - but never with the boundary's own 401 or its information-hiding 404
    # for a route that exists.
    blocked = {
        k: _fingerprint(r)
        for k, r in results.items()
        if r.status_code == 401
        or (r.status_code == 404 and "{" not in k[1] and k[0] == "GET" and k[1].count("/") <= 4)
    }
    assert not blocked, blocked
    assert all(r.status_code != 500 for r in results.values())


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_deactivated_admins_live_mfa_session_is_refused_everywhere(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        admin, _, _ = await mfa_admin(client, db_session)
        admin_id = admin.id
        await db_session.execute(
            update(UserModel)
            .where(UserModel.id == admin_id)
            .values(is_active=False, auth_epoch=UserModel.auth_epoch + 1)
        )
        await db_session.commit()
        results = _hit_all(client)
    wrong = {k: r.status_code for k, r in results.items() if r.status_code != 401}
    assert not wrong, wrong


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_malformed_id_under_admin_is_hidden_from_customers(
    db_session: AsyncSession,
) -> None:
    """Path validation runs after the router dependency, so a customer never
    learns that an admin path parameter is typed."""
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        malformed = client.get("/api/v1/admin/users/not-a-uuid")
        imaginary = client.get(IMAGINARY)
    assert _fingerprint(malformed) == _fingerprint(imaginary)


# --------------------------------------------------------------------------
# The SEC-10 oracles
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
def test_anonymous_callers_cannot_tell_real_admin_paths_from_imaginary_ones() -> None:
    with client_for(main_app) as client:
        imaginary = _fingerprint(client.get(IMAGINARY))
        real = {
            path: _fingerprint(client.get(path))
            for method, path in ADMIN_OPERATIONS
            if method == "GET"
        }
    assert all(fp == imaginary for fp in real.values()), real


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_customer_cannot_enumerate_admin_routes_with_wrong_methods(
    db_session: AsyncSession,
) -> None:
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        imaginary = _fingerprint(client.get(IMAGINARY))
        leaks = {
            (method, path): client.request(method, path, headers=csrf(client)).status_code
            for method, path in _admin_wrong_methods()
        }
    assert all(status == imaginary[0] for status in leaks.values()), leaks


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("as_customer", [True, False], ids=["customer", "anonymous"])
async def test_a_trailing_slash_does_not_reveal_admin_routes(
    as_customer: bool, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    with client_for(main_app, follow_redirects=False) as client:
        if as_customer:
            login(client, user.email)
        real = client.get("/api/v1/admin/settings/")
        imaginary = client.get(IMAGINARY + "/")
    assert real.status_code == imaginary.status_code


# --------------------------------------------------------------------------
# MFA inputs
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("code", "status", "problem"),
    [
        pytest.param("12345", 422, "VALIDATION_ERROR", id="5-digits"),
        pytest.param("12345678901", 422, "VALIDATION_ERROR", id="11-chars"),
        pytest.param(123456, 422, "VALIDATION_ERROR", id="number"),
        pytest.param(None, 422, "VALIDATION_ERROR", id="null"),
        pytest.param("abcdef", 422, "MFA_INVALID", id="letters"),
        pytest.param("000000", 422, "MFA_INVALID", id="zeros"),
        pytest.param("١٢٣٤٥٦", 422, "MFA_INVALID", id="arabic-indic"),
        pytest.param("12 34 56", 422, "MFA_INVALID", id="spaced"),
        # A control character is refused at the schema (BUG-03).
        pytest.param("123456\u0000", 422, "VALIDATION_ERROR", id="nul"),
    ],
)
async def test_confirm_code_shapes(
    code: Any, status: int, problem: str, db_session: AsyncSession
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    with client_for(main_app) as client:
        login(client, admin.email)
        assert (
            client.post(
                SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(client)
            ).status_code
            == 200
        )
        response = client.post(CONFIRM_PATH, json={"code": code}, headers=csrf(client))
    assert_problem(response, status, problem)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_valid_code_with_surrounding_whitespace_is_accepted(
    db_session: AsyncSession,
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    with client_for(main_app) as client:
        login(client, admin.email)
        secret = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(client)
        ).json()["secret"]
        response = client.post(
            CONFIRM_PATH, json={"code": f" {pyotp.TOTP(secret).now()} "}, headers=csrf(client)
        )
    assert response.status_code == 200, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_setup_material_is_well_formed_and_the_secret_is_never_stored_plain(
    db_session: AsyncSession,
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    admin_id, email = admin.id, admin.email
    with client_for(main_app) as client:
        login(client, email)
        body = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(client)
        ).json()
    assert re.fullmatch(r"[A-Z2-7]{32}", body["secret"])
    assert body["otpauth_uri"].startswith("otpauth://totp/")
    assert f"secret={body['secret']}" in body["otpauth_uri"]
    db_session.expire_all()
    row = await db_session.scalar(
        select(MfaCredentialModel).where(MfaCredentialModel.user_id == admin_id)
    )
    assert row is not None and row.enabled_at is None
    assert body["secret"].encode() not in row.secret_ciphertext


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"challenge_id": "x"}, id="no-factor"),
        pytest.param(
            {"challenge_id": "x", "code": "123456", "recovery_code": "AAAA-BBBB-CCCC"},
            id="both-factors",
        ),
        pytest.param({"challenge_id": "x" * 129, "code": "123456"}, id="challenge-129"),
        pytest.param({"code": "123456"}, id="no-challenge"),
        # A control character is refused at the schema (BUG-03).
        pytest.param({"challenge_id": "\u0000", "code": "123456"}, id="challenge-nul"),
        pytest.param({"challenge_id": "x", "recovery_code": "A" * 65}, id="recovery-65"),
        pytest.param(
            {"challenge_id": "x", "code": "123456", "user_id": str(uuid.uuid4())},
            id="user-id-smuggled",
        ),
    ],
)
def test_verify_body_shapes(body: dict[str, Any]) -> None:
    with client_for(main_app) as client:
        response = client.post(VERIFY, json=body)
    assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "challenge_id",
    ["unknown", "*", "mfa:challenge:*", "../../etc", " ", "a" * 128],
)
def test_an_unknown_or_hostile_challenge_id_is_gone(challenge_id: str) -> None:
    with client_for(main_app) as client:
        response = client.post(VERIFY, json={"challenge_id": challenge_id, "code": "123456"})
    assert_problem(response, 410, "RESOURCE_EXPIRED")


# --------------------------------------------------------------------------
# TOTP window, pinned in time
# --------------------------------------------------------------------------


async def _enrolled_admin(db: AsyncSession) -> tuple[str, str]:
    admin = await create_user(db, role=UserRole.ADMIN)
    with client_for(main_app) as client:
        login(client, admin.email)
        secret = client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(client)
        ).json()["secret"]
        assert (
            client.post(
                CONFIRM_PATH, json={"code": pyotp.TOTP(secret).now()}, headers=csrf(client)
            ).status_code
            == 200
        )
    return admin.email, secret


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("step_offset", "status"),
    [
        pytest.param(-2, 401, id="two-steps-behind"),
        pytest.param(-1, 204, id="one-step-behind"),
        pytest.param(0, 204, id="current-step"),
        pytest.param(1, 204, id="one-step-ahead"),
        pytest.param(2, 401, id="two-steps-ahead"),
    ],
)
async def test_the_totp_drift_window_is_exactly_one_step(
    step_offset: int, status: int, db_session: AsyncSession
) -> None:
    email, secret = await _enrolled_admin(db_session)
    # Twenty steps later, in the middle of a step, so enrolment's spent step is
    # far behind and no boundary is ambiguous.
    now = datetime.now(UTC)
    moment = datetime.fromtimestamp((int(now.timestamp()) // 30 + 20) * 30 + 15, UTC)
    code = pyotp.TOTP(secret).at(moment + timedelta(seconds=30 * step_offset))
    with client_for(main_app) as client, time_machine.travel(moment, tick=False):
        challenge = client.post(LOGIN, json={"email": email, "password": PASSWORD}).json()[
            "challenge_id"
        ]
        response = client.post(VERIFY, json={"challenge_id": challenge, "code": code})
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("second_of_step", [0, 29], ids=["first-second", "last-second"])
async def test_a_code_is_valid_at_both_edges_of_its_step(
    second_of_step: int, db_session: AsyncSession
) -> None:
    email, secret = await _enrolled_admin(db_session)
    base = (int(datetime.now(UTC).timestamp()) // 30 + 20) * 30
    moment = datetime.fromtimestamp(base + second_of_step, UTC)
    with client_for(main_app) as client, time_machine.travel(moment, tick=False):
        challenge = client.post(LOGIN, json={"email": email, "password": PASSWORD}).json()[
            "challenge_id"
        ]
        response = client.post(
            VERIFY, json={"challenge_id": challenge, "code": pyotp.TOTP(secret).at(moment)}
        )
    assert response.status_code == 204, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_an_older_step_is_refused_after_a_newer_one_was_used(
    db_session: AsyncSession,
) -> None:
    """The replay guard is a high-water mark: using step n+1 spends n and n-1 too."""
    email, secret = await _enrolled_admin(db_session)
    base = (int(datetime.now(UTC).timestamp()) // 30 + 20) * 30 + 15
    moment = datetime.fromtimestamp(base, UTC)
    totp = pyotp.TOTP(secret)
    with client_for(main_app) as client, time_machine.travel(moment, tick=False):
        first = client.post(LOGIN, json={"email": email, "password": PASSWORD}).json()[
            "challenge_id"
        ]
        ahead = client.post(
            VERIFY, json={"challenge_id": first, "code": totp.at(moment + timedelta(seconds=30))}
        )
        second = client.post(LOGIN, json={"email": email, "password": PASSWORD}).json()[
            "challenge_id"
        ]
        current = client.post(VERIFY, json={"challenge_id": second, "code": totp.at(moment)})
    assert ahead.status_code == 204
    assert_problem(current, 401, "MFA_INVALID")


# --------------------------------------------------------------------------
# Challenges
# --------------------------------------------------------------------------


async def _redis() -> Any:
    return redis_asyncio.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_challenge_lives_five_minutes_and_dies_on_expiry(db_session: AsyncSession) -> None:
    email, secret = await _enrolled_admin(db_session)
    with client_for(main_app) as client:
        challenge = client.post(LOGIN, json={"email": email, "password": PASSWORD}).json()[
            "challenge_id"
        ]
        probe = await _redis()
        try:
            ttl = await probe.ttl(f"mfa:challenge:{challenge}")
            await probe.pexpire(f"mfa:challenge:{challenge}", 1)
        finally:
            await probe.aclose()
        await asyncio.sleep(0.05)
        code = pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))
        response = client.post(VERIFY, json={"challenge_id": challenge, "code": code})
    assert 290 <= ttl <= 300
    assert_problem(response, 410, "RESOURCE_EXPIRED")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_challenge_dies_when_its_account_is_deactivated(db_session: AsyncSession) -> None:
    email, secret = await _enrolled_admin(db_session)
    with client_for(main_app) as client:
        challenge = client.post(LOGIN, json={"email": email, "password": PASSWORD}).json()[
            "challenge_id"
        ]
        await db_session.execute(
            update(UserModel)
            .where(UserModel.email == email)
            .values(is_active=False, auth_epoch=UserModel.auth_epoch + 1)
        )
        await db_session.commit()
        code = pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))
        response = client.post(VERIFY, json={"challenge_id": challenge, "code": code})
    assert response.status_code in (403, 410)
    assert not client.cookies.get("access_token")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_one_challenge_buys_exactly_one_guess_under_concurrency(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    email, _ = await _enrolled_admin(db_session)
    async with running_app(make_app) as app:
        async with async_client(app) as seed:
            challenge = (
                await seed.post(LOGIN, json={"email": email, "password": PASSWORD})
            ).json()["challenge_id"]
        clients = [async_client(app) for _ in range(10)]
        try:
            responses = await asyncio.gather(
                *(
                    c.post(VERIFY, json={"challenge_id": challenge, "code": f"{n:06d}"})
                    for n, c in enumerate(clients)
                )
            )
        finally:
            for c in clients:
                await c.aclose()
    evaluated = [r.status_code for r in responses if r.status_code == 401]
    assert len(evaluated) <= 1, [r.status_code for r in responses]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_one_valid_code_across_parallel_challenges_logs_in_once(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    email, secret = await _enrolled_admin(db_session)
    async with running_app(make_app) as app:
        clients = [async_client(app) for _ in range(8)]
        try:
            challenges = [
                (await c.post(LOGIN, json={"email": email, "password": PASSWORD})).json()[
                    "challenge_id"
                ]
                for c in clients
            ]
            code = pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))
            responses = await asyncio.gather(
                *(
                    c.post(VERIFY, json={"challenge_id": ch, "code": code})
                    for c, ch in zip(clients, challenges, strict=True)
                )
            )
        finally:
            for c in clients:
                await c.aclose()
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [204] + [401] * 7, statuses


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_one_recovery_code_across_parallel_challenges_logs_in_once(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    email = admin.email
    with client_for(main_app) as enrol:
        login(enrol, email)
        secret = enrol.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(enrol)
        ).json()["secret"]
        codes = enrol.post(
            CONFIRM_PATH, json={"code": pyotp.TOTP(secret).now()}, headers=csrf(enrol)
        ).json()["recovery_codes"]
    async with running_app(make_app) as app:
        clients = [async_client(app) for _ in range(8)]
        try:
            challenges = [
                (await c.post(LOGIN, json={"email": email, "password": PASSWORD})).json()[
                    "challenge_id"
                ]
                for c in clients
            ]
            responses = await asyncio.gather(
                *(
                    c.post(VERIFY, json={"challenge_id": ch, "recovery_code": codes[0].lower()})
                    for c, ch in zip(clients, challenges, strict=True)
                )
            )
        finally:
            for c in clients:
                await c.aclose()
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [204] + [401] * 7, statuses


# --------------------------------------------------------------------------
# Enrolment and regeneration races
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_parallel_first_time_setups_never_500(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    outcomes = []
    async with running_app(make_app) as app:
        for _ in range(3):
            admin = await create_user(db_session, role=UserRole.ADMIN)
            async with async_client(app) as seed:
                await seed.post(LOGIN, json={"email": admin.email, "password": PASSWORD})
                cookies = dict(seed.cookies.items())
            clients = [async_client(app) for _ in range(4)]
            for c in clients:
                for name, value in cookies.items():
                    c.cookies.set(name, value)
            try:
                responses = await asyncio.gather(
                    *(
                        c.post(
                            SETUP_PATH,
                            json={"current_password": PASSWORD},
                            headers={"X-CSRF-Token": cookies["csrf_token"]},
                        )
                        for c in clients
                    )
                )
            finally:
                for c in clients:
                    await c.aclose()
            outcomes.append(sorted(r.status_code for r in responses))
    assert all(500 not in statuses for statuses in outcomes), outcomes


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_parallel_confirms_enable_mfa_once(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    admin = await create_user(db_session, role=UserRole.ADMIN)
    admin_id = admin.id
    async with running_app(make_app) as app:
        async with async_client(app) as seed:
            await seed.post(LOGIN, json={"email": admin.email, "password": PASSWORD})
            token = csrf(seed)
            secret = (
                await seed.post(SETUP_PATH, json={"current_password": PASSWORD}, headers=token)
            ).json()["secret"]
            cookies = dict(seed.cookies.items())
        clients = [async_client(app) for _ in range(6)]
        for c in clients:
            for name, value in cookies.items():
                c.cookies.set(name, value)
        code = pyotp.TOTP(secret).now()
        try:
            responses = await asyncio.gather(
                *(c.post(CONFIRM_PATH, json={"code": code}, headers=token) for c in clients)
            )
        finally:
            for c in clients:
                await c.aclose()
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200] + [409] * 5, statuses
    db_session.expire_all()
    live_codes = await db_session.scalar(
        select(func.count())
        .select_from(MfaRecoveryCodeModel)
        .join(MfaCredentialModel, MfaCredentialModel.id == MfaRecoveryCodeModel.mfa_credential_id)
        .where(MfaCredentialModel.user_id == admin_id, MfaRecoveryCodeModel.used_at.is_(None))
    )
    assert live_codes == 10


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_parallel_regenerations_leave_exactly_one_code_set(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    async with running_app(make_app) as app:
        with client_for(main_app) as enrol:
            admin, _, _ = await mfa_admin(enrol, db_session)
            cookies = dict(enrol.cookies.items())
        admin_id = admin.id
        clients = [async_client(app) for _ in range(4)]
        for c in clients:
            for name, value in cookies.items():
                c.cookies.set(name, value)
        try:
            responses = await asyncio.gather(
                *(
                    c.post(
                        REGENERATE,
                        json={"current_password": PASSWORD},
                        headers={"X-CSRF-Token": cookies["csrf_token"]},
                    )
                    for c in clients
                )
            )
        finally:
            for c in clients:
                await c.aclose()
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    db_session.expire_all()
    live_codes = await db_session.scalar(
        select(func.count())
        .select_from(MfaRecoveryCodeModel)
        .join(MfaCredentialModel, MfaCredentialModel.id == MfaRecoveryCodeModel.mfa_credential_id)
        .where(MfaCredentialModel.user_id == admin_id, MfaRecoveryCodeModel.used_at.is_(None))
    )
    assert live_codes == 10


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("setup", "status", "code"),
    [
        pytest.param("no-csrf", 403, "CSRF_INVALID", id="no-csrf"),
        pytest.param("wrong-password", 401, "INVALID_CREDENTIALS", id="wrong-password"),
        pytest.param("mfa-incomplete", 401, "MFA_REQUIRED", id="mfa-incomplete"),
        pytest.param("customer", 404, "NOT_FOUND", id="customer"),
    ],
)
async def test_regeneration_refusals(
    setup: str, status: int, code: str, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        if setup == "customer":
            user = await create_user(db_session)
            login(client, user.email)
        elif setup == "mfa-incomplete":
            admin = await create_user(db_session, role=UserRole.ADMIN)
            login(client, admin.email)
        else:
            await mfa_admin(client, db_session)
        headers = {} if setup == "no-csrf" else csrf(client)
        password = "wrong-password" if setup == "wrong-password" else PASSWORD
        response = client.post(REGENERATE, json={"current_password": password}, headers=headers)
    assert_problem(response, status, code)
