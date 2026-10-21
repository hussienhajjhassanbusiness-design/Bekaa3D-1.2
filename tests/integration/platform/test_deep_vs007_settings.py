"""VS-007 deep edge cases: the typed settings editor and the public allowlist."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app as main_app
from app.platform.domain.settings_registry import ALL_KEYS, PUBLIC_KEYS, REGISTRY
from app.platform.infrastructure.models import AuditLogModel
from tests.integration.deep_support import (
    assert_problem,
    async_client,
    client_for,
    csrf,
    mfa_admin,
    running_app,
)

SETTINGS = "/api/v1/admin/settings"
PUBLIC = "/api/v1/settings/public"


def _patch(client: Any, key: str, value: Any) -> Any:
    return client.patch(f"{SETTINGS}/{key}", json={"value": value}, headers=csrf(client))


# --------------------------------------------------------------------------
# Values per type
# --------------------------------------------------------------------------

_INT_KEYS = [k for k in ALL_KEYS if REGISTRY[k].type.value in ("integer", "duration")]
_BAD_NUMBERS: list[Any] = [
    pytest.param(True, id="true"),
    pytest.param(False, id="false"),
    pytest.param(1.0, id="float-1.0"),
    pytest.param(1.5, id="float-1.5"),
    pytest.param("100", id="numeric-string"),
    pytest.param([100], id="array"),
    pytest.param({"v": 100}, id="object"),
    pytest.param(10**30, id="10e30"),
    pytest.param(-(10**30), id="-10e30"),
]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("key", _INT_KEYS)
async def test_numeric_settings_accept_exactly_their_range(
    key: str, db_session: AsyncSession
) -> None:
    definition = REGISTRY[key]
    assert definition.minimum is not None and definition.maximum is not None
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        lo, hi = definition.minimum, definition.maximum
        results = {
            lo - 1: _patch(client, key, lo - 1).status_code,
            lo: _patch(client, key, lo).status_code,
            hi: _patch(client, key, hi).status_code,
            hi + 1: _patch(client, key, hi + 1).status_code,
        }
        _patch(client, key, definition.default)
    assert results == {lo - 1: 422, lo: 200, hi: 200, hi + 1: 422}


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("value", _BAD_NUMBERS)
async def test_non_integers_are_setting_invalid_never_a_500(
    value: Any, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _patch(client, "minimum_offer_percentage", value)
    assert_problem(response, 422, "SETTING_INVALID")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("value", "status"),
    [
        # VS-028: the only money setting is now cash_max_order_total, never null nor 0.
        pytest.param(None, 422, id="null"),
        pytest.param({"amount_cents": 0, "currency": "USD"}, 422, id="zero"),
        pytest.param({"amount_cents": 1, "currency": "USD"}, 200, id="min"),
        pytest.param({"amount_cents": 1_000_000, "currency": "USD"}, 200, id="max"),
        pytest.param({"amount_cents": 1_000_001, "currency": "USD"}, 422, id="max-plus-1"),
        pytest.param({"amount_cents": -1, "currency": "USD"}, 422, id="negative"),
        pytest.param({"amount_cents": 10.5, "currency": "USD"}, 422, id="fractional-cents"),
        pytest.param({"amount_cents": True, "currency": "USD"}, 422, id="bool-cents"),
        pytest.param({"amount_cents": 100, "currency": "usd"}, 422, id="lowercase-currency"),
        pytest.param({"amount_cents": 100, "currency": "LBP"}, 422, id="other-currency"),
        pytest.param({"amount_cents": 100}, 422, id="no-currency"),
        pytest.param({"amount_cents": 100, "currency": "USD", "x": 1}, 422, id="extra-key"),
        pytest.param(100, 422, id="bare-number"),
        pytest.param("100 USD", 422, id="string"),
    ],
)
async def test_money_shapes(value: Any, status: int, db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _patch(client, "cash_max_order_total", value)
        _patch(client, "cash_max_order_total", REGISTRY["cash_max_order_total"].default)
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("value", "status"),
    [
        pytest.param("  Beirut, Hamra St.  ", 200, id="trimmed"),
        pytest.param("بيروت", 200, id="arabic"),
        pytest.param("\U0001f3ed workshop", 200, id="emoji"),
        pytest.param("x" * 500, 200, id="max-500"),
        pytest.param("x" * 501, 422, id="501"),
        pytest.param("   ", 422, id="whitespace-only"),
        pytest.param("", 422, id="empty"),
        pytest.param(None, 200, id="null"),
        pytest.param(12, 422, id="number"),
        pytest.param("<script>alert(1)</script>", 200, id="html-stored-verbatim"),
    ],
)
async def test_free_text_shapes(value: Any, status: int, db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _patch(client, "pickup_address", value)
        _patch(client, "pickup_address", None)
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_nul_in_a_string_setting_is_setting_invalid(db_session: AsyncSession) -> None:
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = _patch(client, "pickup_hours", "Mon-Fri\u00009-5")
    assert_problem(response, 422, "SETTING_INVALID")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "invisible", ["​", "​‌‍", "﻿", "⁠"], ids=["zwsp", "zw-mix", "bom", "word-joiner"]
)
async def test_an_invisible_only_string_is_refused(
    invisible: str, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _patch(client, "pickup_hours", invisible)
        _patch(client, "pickup_hours", None)
    assert_problem(response, 422, "SETTING_INVALID")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("number", "status"),
    [
        pytest.param("+9613123456", 200, id="valid"),
        pytest.param("+123456789012345", 200, id="15-digits"),
        pytest.param("+1234567890123456", 422, id="16-digits"),
        pytest.param("9613123456", 422, id="no-plus"),
        pytest.param("+0961312345", 422, id="leading-zero"),
        pytest.param("+961 3 123456", 422, id="spaces"),
        pytest.param("+961-3-123456", 422, id="dashes"),
        pytest.param("+", 422, id="plus-only"),
        pytest.param(" +9613123456 ", 200, id="padded-is-trimmed"),
    ],
)
async def test_whatsapp_number_e164_shapes(
    number: str, status: int, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _patch(client, "whatsapp_number", number)
        _patch(client, "whatsapp_number", None)
    assert response.status_code == status, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "number",
    ["+9\u0666\u0661\u0663\u0661\u0662\u0663\u0664\u0665\u0666", "+9\uff16\uff11\uff13"],
    ids=["arabic-indic", "fullwidth"],
)
async def test_non_ascii_digits_are_not_e164(number: str, db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = _patch(client, "whatsapp_number", number)
        _patch(client, "whatsapp_number", None)
    assert_problem(response, 422, "SETTING_INVALID")


# --------------------------------------------------------------------------
# Envelope, keys and query parameters
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        pytest.param({}, 422, "VALIDATION_ERROR", id="no-value"),
        pytest.param({"value": True, "type": "integer"}, 422, "VALIDATION_ERROR", id="extra-field"),
        pytest.param({"value": None}, 422, "SETTING_INVALID", id="null-non-nullable"),
        pytest.param({"value": "true"}, 422, "SETTING_INVALID", id="string-bool"),
        pytest.param({"value": 1}, 422, "SETTING_INVALID", id="int-bool"),
    ],
)
async def test_boolean_envelope_shapes(
    body: dict[str, Any], status: int, code: str, db_session: AsyncSession
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.patch(f"{SETTINGS}/accepting_orders", json=body, headers=csrf(client))
    assert_problem(response, status, code)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    "key",
    [
        "ACCEPTING_ORDERS",
        "accepting_orders ",
        "accepting-orders",
        "unknown_key",
        "x" * 5000,
        "..%2f..%2fusers",
        "\u0430ccepting_orders",
    ],
    ids=[
        "upper",
        "trailing-space",
        "dash",
        "unknown",
        "5000-chars",
        "traversal",
        "cyrillic-a",
    ],
)
async def test_every_non_registry_key_is_a_plain_404(key: str, db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        read = client.get(f"{SETTINGS}/{key}")
        write = client.patch(f"{SETTINGS}/{key}", json={"value": True}, headers=csrf(client))
    for response in (read, write):
        assert_problem(response, 404, "NOT_FOUND")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("key", ["%00", "accepting_orders%00"], ids=["nul", "suffix-nul"])
async def test_a_key_with_a_control_character_is_a_422(key: str, db_session: AsyncSession) -> None:
    """BUG-03: a control character anywhere in the path is refused before
    routing - never looked up, so never a database error."""
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        read = client.get(f"{SETTINGS}/{key}")
        write = client.patch(f"{SETTINGS}/{key}", json={"value": True}, headers=csrf(client))
    for response in (read, write):
        assert_problem(response, 422, "VALIDATION_ERROR")


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize(
    ("query", "status"),
    [
        pytest.param("limit=0", 422, id="limit-0"),
        pytest.param("limit=101", 422, id="limit-101"),
        pytest.param("limit=1e2", 422, id="limit-float"),
        pytest.param("type=nonsense", 422, id="bad-type"),
        pytest.param("prefix=" + "p" * 65, 422, id="prefix-65"),
        pytest.param("prefix=%25", 200, id="percent-literal"),
        pytest.param("prefix=_", 200, id="underscore-literal"),
    ],
)
async def test_list_query_shapes(query: str, status: int, db_session: AsyncSession) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        response = client.get(f"{SETTINGS}?{query}")
    assert response.status_code == status, response.text
    if query in ("prefix=%25", "prefix=_"):
        assert response.json()["items"] == [], "a wildcard character must match only itself"


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_nul_prefix_is_a_client_error(db_session: AsyncSession) -> None:
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = client.get(f"{SETTINGS}?prefix=%00")
    assert_problem(response, 422, "VALIDATION_ERROR")


# --------------------------------------------------------------------------
# Public endpoint
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
async def test_a_change_is_public_immediately_and_only_for_allowlisted_keys(
    db_session: AsyncSession,
) -> None:
    with client_for(main_app) as client:
        await mfa_admin(client, db_session)
        assert _patch(client, "whatsapp_number", "+9613123456").status_code == 200
        assert _patch(client, "minimum_offer_percentage", 42).status_code == 200
        public = client.get(PUBLIC).json()
        _patch(client, "whatsapp_number", None)
        _patch(client, "minimum_offer_percentage", REGISTRY["minimum_offer_percentage"].default)
    assert set(public) == set(PUBLIC_KEYS)
    assert public["whatsapp_number"] == "+9613123456"
    assert "42" not in str(public)


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.parametrize("query", ["?key=minimum_offer_percentage", "?include=all", "?fields=*"])
def test_the_public_endpoint_ignores_every_widening_parameter(query: str) -> None:
    with client_for(main_app) as client:
        body = client.get(PUBLIC + query).json()
    assert set(body) == set(PUBLIC_KEYS)


# --------------------------------------------------------------------------
# Concurrency: 20 administrators, one key
# --------------------------------------------------------------------------


async def _race_twenty_patches(
    make_app: Callable[[], FastAPI], db_session: AsyncSession, key: str
) -> list[AuditLogModel]:
    """Twenty administrators' sessions PATCH one key at once; returns the twenty
    `setting.updated` rows those requests wrote."""
    async with running_app(make_app) as app:
        with client_for(main_app) as enrol:
            await mfa_admin(enrol, db_session)
            cookies = dict(enrol.cookies.items())
        clients = [async_client(app) for _ in range(20)]
        for c in clients:
            for name, value in cookies.items():
                c.cookies.set(name, value)
        headers = {"X-CSRF-Token": cookies["csrf_token"]}
        request_ids = []
        try:
            responses = await asyncio.gather(
                *(
                    c.patch(f"{SETTINGS}/{key}", json={"value": 50 + n}, headers=headers)
                    for n, c in enumerate(clients)
                )
            )
        finally:
            for c in clients:
                await c.aclose()
        request_ids = [r.headers["x-request-id"] for r in responses]
        assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
        # Restore the default through the same app, so later tests see it.
        async with async_client(app) as reset:
            for name, value in cookies.items():
                reset.cookies.set(name, value)
            await reset.patch(
                f"{SETTINGS}/{key}", json={"value": REGISTRY[key].default}, headers=headers
            )
    db_session.expire_all()
    rows = (
        await db_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.request_id.in_(request_ids),
                AuditLogModel.action == "setting.updated",
            )
        )
    ).all()
    assert len(rows) == 20
    return list(rows)


def _causal_chain(rows: list[AuditLogModel]) -> list[AuditLogModel]:
    """Order the rows by following value links: each change's `before` is the
    previous change's `after`. Values 50..69 are unique, so the path is unique."""
    afters = {_value(row.after_data) for row in rows}
    [first] = [row for row in rows if _value(row.before_data) not in afters]
    by_before = {_value(row.before_data): row for row in rows}
    chain = [first]
    while len(chain) < len(rows):
        chain.append(by_before[_value(chain[-1].after_data)])
    return chain


def _value(data: dict[str, Any] | None) -> Any:
    assert data is not None, "a setting change always records before and after"
    return data["value"]


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_twenty_parallel_patches_leave_a_gapless_audit_chain(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    """No lost update: the twenty before/after pairs link into one unbroken
    path that visits every change exactly once."""
    rows = await _race_twenty_patches(make_app, db_session, "minimum_offer_percentage")
    chain = _causal_chain(rows)
    assert len({row.id for row in chain}) == 20


@pytest.mark.integration
@pytest.mark.usefixtures("configured_app")
@pytest.mark.concurrency
async def test_the_audit_log_chronology_matches_the_order_of_changes(
    make_app: Callable[[], FastAPI], db_session: AsyncSession
) -> None:
    rows = await _race_twenty_patches(make_app, db_session, "minimum_offer_percentage")
    chain = _causal_chain(rows)
    stamps = [row.created_at for row in chain]
    assert stamps == sorted(stamps), "the log's time order disagrees with the causal order"
