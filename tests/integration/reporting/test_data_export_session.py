"""VS-044 failure and snapshot guarantees (ADR-046): a failed first read is a 503 with no audit
row and no body; every port reads one READ ONLY, REPEATABLE READ snapshot."""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.main import app as main_app
from app.reporting.api import session as report_session_module
from app.reporting.infrastructure import export_adapters
from tests.integration.deep_support import assert_problem, client_for, create_user, login
from tests.integration.reporting.export_support import export

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("configured_app")]


async def _audits(engine: AsyncEngine, user_id: Any) -> int:
    async with engine.connect() as conn:
        found = await conn.scalar(
            text(
                "SELECT count(*) FROM audit_logs"
                " WHERE action = 'user.data_exported' AND entity_id = :u"
            ),
            {"u": user_id},
        )
    return int(found or 0)


async def test_a_statement_timeout_on_the_first_read_is_503_with_no_audit_row(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def slow(self: Any, user_id: Any) -> Any:
        await self._session.execute(text("SELECT pg_sleep(1)"))
        raise AssertionError("the statement timeout did not fire")

    monkeypatch.setattr(report_session_module, "REPORT_TIMEOUT_MS", 50)
    monkeypatch.setattr(export_adapters.SqlExportAddresses, "all", slow)
    user = await create_user(db_session)
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, user.email)
        response = export(client)
    assert_problem(response, 503, "SERVICE_UNAVAILABLE")
    assert await _audits(db_engine, user.id) == 0


async def test_a_lost_connection_on_the_first_read_is_503_with_no_audit_row(
    db_engine: AsyncEngine, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def down(self: Any, user_id: Any) -> Any:
        raise OperationalError("SELECT 1", {}, Exception("connection lost"))

    monkeypatch.setattr(export_adapters.SqlExportAddresses, "all", down)
    user = await create_user(db_session)
    with client_for(main_app, raise_server_exceptions=False) as client:
        login(client, user.email)
        response = export(client)
    assert response.status_code == 503, response.text
    assert "profile" not in response.text
    assert await _audits(db_engine, user.id) == 0


@pytest.mark.parametrize(
    ("port", "method"),
    [
        ("SqlExportAddresses", "all"),
        ("SqlExportOrders", "page"),
        ("SqlExportReviews", "all"),
        ("SqlExportOffers", "all"),
        ("SqlExportContactMessages", "all"),
    ],
)
async def test_every_port_reads_the_read_only_repeatable_read_snapshot(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, port: str, method: str
) -> None:
    cls = getattr(export_adapters, port)
    original = getattr(cls, method)
    seen: list[tuple[str, str]] = []

    async def probe(self: Any, *args: Any, **kwargs: Any) -> Any:
        isolation = await self._session.scalar(text("SHOW transaction_isolation"))
        read_only = await self._session.scalar(text("SHOW transaction_read_only"))
        seen.append((isolation, read_only))
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(cls, method, probe)
    user = await create_user(db_session)
    with client_for(main_app) as client:
        login(client, user.email)
        assert export(client).status_code == 200
    assert seen and set(seen) == {("repeatable read", "on")}
