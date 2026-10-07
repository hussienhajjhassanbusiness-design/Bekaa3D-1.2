from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def _unit_of_work(request: Request) -> AsyncGenerator[AsyncSession]:
    """One transaction per request: everything a route does through this session
    commits or rolls back together (e.g. account creation + outbox insert must
    land atomically).

    Mounted with `scope="function"` by `get_session`, so its exit - the COMMIT -
    runs when FastAPI leaves the function scope: after the handler has returned
    and its response has been built, but *before* that response is sent. With
    the default request scope FastAPI exits yield dependencies only after the
    response has gone out, so a commit that then failed (a deferred constraint,
    a serialisation failure, a dropped connection) left the client holding a
    2xx for a write that never happened (BUG-46). Now a failed commit raises
    through the normal exception handlers and the client gets an error."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session, session.begin():
        yield session


async def get_session(
    session: AsyncSession = Depends(_unit_of_work, scope="function"),
) -> AsyncSession:
    """The request's unit of work - the one place that decides when a request's
    writes are committed (see `_unit_of_work`).

    A plain coroutine rather than the generator itself on purpose. FastAPI fixes
    a dependency's scope at each `Depends(...)` site and keys its per-request
    cache on it; routing every existing `Depends(get_session)` through this
    function keeps them all on the one function-scoped session without touching
    any of them, and without two scopes ever producing two sessions."""
    return session


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
