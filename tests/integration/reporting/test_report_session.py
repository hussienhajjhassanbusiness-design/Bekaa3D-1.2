"""VS-043 failure and snapshot guarantees (plan 6.2 R13, R14; ADR-045 d5): a failing port is
an error on every route (503 for the database, 500 otherwise), never zeros; a real statement
timeout is 503; the report session is REPEATABLE READ and READ ONLY, and a write through it
fails."""

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.main import app as main_app
from app.reporting.api import session as report_session_module
from app.reporting.api.session import report_session
from app.reporting.infrastructure import adapters
from tests.integration.deep_support import client_for, mfa_admin
from tests.integration.reporting.support import report

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]

_REVENUE = [
    ("SqlPaidPayments", "between"),
    ("SqlOrderLines", "lines"),
    ("SqlLineRefunds", "refunded_cents_by_line"),
    ("SqlLineRefunds", "covered_lines"),
    ("SqlPaidPayments", "excess_cents"),
]
PORTS: dict[str, list[tuple[str, str]]] = {
    "revenue": _REVENUE,
    "overview": [
        *_REVENUE,
        ("SqlCustomers", "counts"),
        ("SqlOfferCounts", "live_counts"),
        ("SqlOrderLines", "stl_awaiting_delivery"),
    ],
    "customers": [*_REVENUE, ("SqlCustomers", "counts")],
    "stl-sales": [
        *_REVENUE,
        ("SqlProductCatalog", "labels"),
        ("SqlOrderLines", "stl_awaiting_delivery"),
    ],
    "recent-purchases": [
        ("SqlPaidPayments", "page"),
        *_REVENUE[1:],
        ("SqlOrderLines", "labels"),
    ],
    "top-rated-products": [("SqlProductCatalog", "top_rated")],
}
CASES = [(route, port) for route, ports in PORTS.items() for port in ports]


def _raising(error: Exception) -> Any:
    async def fail(*args: Any, **kwargs: Any) -> Any:
        raise error

    return fail


@pytest.mark.parametrize(("route", "port"), CASES, ids=[f"{r}-{c}.{m}" for r, (c, m) in CASES])
async def test_r13_a_failing_port_is_an_error_never_zeros(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, route: str, port: tuple[str, str]
) -> None:
    cls = getattr(adapters, port[0])
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        assert report(client, route).status_code == 200  # the port is really on this route
        down = OperationalError("SELECT 1", {}, Exception("connection lost"))
        monkeypatch.setattr(cls, port[1], _raising(down))
        unavailable = report(client, route)
        monkeypatch.setattr(cls, port[1], _raising(RuntimeError("bug")))
        broken = report(client, route)
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "SERVICE_UNAVAILABLE"
    assert broken.status_code == 500
    for response in (unavailable, broken):
        found = response.json()
        assert not {"totals", "items", "net", "buckets", "buyers"} & set(found)


async def test_r13_a_real_statement_timeout_is_503(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolves plan 3.5's UNVERIFIED point: asyncpg's QueryCanceledError (57014) maps to 503."""

    async def slow(self: Any, created_from: Any, created_to: Any) -> Any:
        await self._session.execute(text("SELECT pg_sleep(1)"))
        raise AssertionError("the statement timeout did not fire")

    monkeypatch.setattr(report_session_module, "REPORT_TIMEOUT_MS", 50)
    monkeypatch.setattr(adapters.SqlCustomers, "counts", slow)
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = report(client, "customers")
    assert response.status_code == 503, response.text
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"


async def _snapshot(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_session_factory=async_sessionmaker(engine)))
    )
    async for session in report_session(request):  # type: ignore[arg-type]
        yield session


async def test_r14_the_report_session_is_one_read_only_repeatable_read_snapshot(
    db_engine: AsyncEngine,
) -> None:
    async for session in _snapshot(db_engine):
        isolation = await session.scalar(text("SHOW transaction_isolation"))
        read_only = await session.scalar(text("SHOW transaction_read_only"))
        timeout = await session.scalar(text("SHOW statement_timeout"))
        assert (isolation, read_only, timeout) == ("repeatable read", "on", "5s")
        with pytest.raises(DBAPIError) as caught:
            await session.execute(text("CREATE TEMPORARY TABLE vs043_probe (n int)"))
        assert "read-only transaction" in str(caught.value)


async def test_r14_a_write_through_a_report_route_fails_and_lands_nothing(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The routes really use the read-only session: a port that tries to write gets an error."""

    refused: list[str] = []

    async def write(self: Any, created_from: Any, created_to: Any) -> Any:
        try:
            await self._session.execute(text("UPDATE settings SET key = key WHERE false"))
        except DBAPIError as exc:
            refused.append(str(exc.orig))
            raise
        raise AssertionError("the write was accepted")

    monkeypatch.setattr(adapters.SqlCustomers, "counts", write)
    with client_for(main_app, raise_server_exceptions=False) as client:
        await mfa_admin(client, db_session)
        response = report(client, "customers")
    assert response.status_code == 500, response.text
    assert "totals" not in response.json()
    assert len(refused) == 1 and "read-only transaction" in refused[0], refused
