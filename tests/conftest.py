import asyncio
import os
from collections.abc import AsyncGenerator, Callable, Generator

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from app.core.config import get_settings
from tests.smoke.test_vs012_smoke import SMOKE_ELSEWHERE as VS012_SMOKE
from tests.smoke.test_vs013_smoke import SMOKE_ELSEWHERE as VS013_SMOKE
from tests.smoke.test_vs014_smoke import SMOKE_ELSEWHERE as VS014_SMOKE
from tests.smoke.test_vs015_smoke import SMOKE_ELSEWHERE as VS015_SMOKE
from tests.smoke.test_vs016_smoke import SMOKE_ELSEWHERE as VS016_SMOKE
from tests.smoke.test_vs026_smoke import SMOKE_ELSEWHERE as VS026_SMOKE
from tests.smoke.test_vs033_smoke import SMOKE_ELSEWHERE as VS033_SMOKE
from tests.smoke.test_vs038_smoke import SMOKE_ELSEWHERE as VS038_SMOKE

# Tests never call Cloudflare; a local .env predating VS-033 may not set this.
os.environ.setdefault("CAPTCHA_PROVIDER", "fake")

_SMOKE_NODE_IDS = frozenset(
    node_id
    for suite in (
        VS012_SMOKE,
        VS013_SMOKE,
        VS014_SMOKE,
        VS015_SMOKE,
        VS016_SMOKE,
        VS026_SMOKE,
        VS033_SMOKE,
        VS038_SMOKE,
    )
    for ids in suite.values()
    for node_id in ids
)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark the existing tests a smoke suite lists, so `-m smoke` selects them
    without copying them (tests/smoke/). `tryfirst`, so the markers are on the
    items before pytest's own `-m` deselection runs on the same hook."""
    for item in items:
        if item.nodeid.split("[", 1)[0] in _SMOKE_NODE_IDS:
            item.add_marker(pytest.mark.smoke)


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer]:
    with PostgresContainer("postgres:16", driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def db_engine(postgres_container: PostgresContainer) -> Generator[AsyncEngine]:
    """Runs the real Alembic migration chain against a throwaway Postgres once
    per test session, so tests exercise the same schema path as production
    rather than an ORM-generated shortcut."""
    os.environ["DATABASE_URL"] = postgres_container.get_connection_url()
    get_settings.cache_clear()

    command.upgrade(Config("alembic.ini"), "head")

    engine = create_async_engine(postgres_container.get_connection_url(), pool_pre_ping=True)
    yield engine
    asyncio.run(engine.dispose())

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def configured_app(
    postgres_container: PostgresContainer, redis_container: RedisContainer, db_engine: AsyncEngine
) -> AsyncGenerator[None]:
    """Points Settings at the shared migrated Postgres/Redis containers for the
    duration of one test. db_engine is depended on purely to force migrations
    to run first."""
    os.environ["DATABASE_URL"] = postgres_container.get_connection_url()
    redis_url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    os.environ["REDIS_URL"] = redis_url
    get_settings.cache_clear()

    # Rate-limit counters must not leak between tests sharing this Redis
    # container, or later tests silently start seeing 429s from earlier ones.
    client = redis_asyncio.from_url(redis_url)  # type: ignore[no-untyped-call]
    await client.flushdb()
    await client.aclose()

    yield
    get_settings.cache_clear()


@pytest.fixture
def make_app() -> Callable[[], FastAPI]:
    """Builds independent app instances, each with its own `app.state`.

    `app.main.app` is a module-level singleton, so entering two `TestClient`s
    against it runs two lifespans over one `app.state`: the second overwrites
    the first's engine and Redis client, and a request through the first client
    then awaits a connection owned by the second client's event loop and hangs
    forever. A test holding more than one client open at once must build them
    from here rather than importing the singleton.

    This mirrors the wiring in `src/app/main.py` - keep the two in step when a
    router or middleware is added there.
    """

    def _make() -> FastAPI:
        from app.api.enumeration import EnumerationFloorMiddleware
        from app.api.errors import register_exception_handlers
        from app.api.head import HeadAsGetMiddleware
        from app.api.health import router as health_router
        from app.api.middleware import IpHashKeyRefreshMiddleware, RequestIDMiddleware
        from app.api.request_target import RequestTargetMiddleware
        from app.api.v1.router import router as v1_router
        from app.main import lifespan

        app = FastAPI(title="Bekaa3D API", version="0.1.0", lifespan=lifespan)
        app.add_middleware(HeadAsGetMiddleware)
        app.add_middleware(RequestTargetMiddleware)
        app.add_middleware(IpHashKeyRefreshMiddleware)
        app.add_middleware(RequestIDMiddleware)
        app.add_middleware(EnumerationFloorMiddleware)
        register_exception_handlers(app)
        app.include_router(health_router)
        app.include_router(v1_router)
        return app

    return _make


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """A plain session against the shared schema for test setup/assertions -
    not isolated per test, so tests must use unique data (e.g. random emails)
    rather than relying on rollback between tests."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
