"""The report's own session (ADR-045 d5): one READ ONLY, REPEATABLE READ snapshot with a statement
timeout, on its own connection, so a report never writes and never holds an operational
transaction (FR-18)."""

from collections.abc import AsyncGenerator
from typing import Final

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApiError

REPORT_TIMEOUT_MS: Final = 5_000
QUERY_CANCELED: Final = "57014"


def _sqlstate(exc: DBAPIError) -> str | None:
    for source in (exc.orig, getattr(exc.orig, "__cause__", None)):
        state = getattr(source, "sqlstate", None)
        if isinstance(state, str):
            return state
    return None


def report_unavailable() -> ApiError:
    return ApiError(
        status_code=503,
        code="SERVICE_UNAVAILABLE",
        title="Service temporarily unavailable",
        detail="A required service is temporarily unavailable. Retry later.",
    )


async def report_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """`SET TRANSACTION` is the first statement, so it holds whatever the driver's BEGIN said.
    Nothing commits: closing the session rolls the snapshot back. A timeout answers 503."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            await session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            await session.execute(text(f"SET LOCAL statement_timeout = {REPORT_TIMEOUT_MS}"))
            yield session
        except DBAPIError as exc:
            if _sqlstate(exc) == QUERY_CANCELED:
                raise report_unavailable() from exc
            raise
