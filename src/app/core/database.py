from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. Every context's ORM models register their tables here
    so Alembic autogenerate can see the full schema from one metadata object."""


# How long opening a connection to PostgreSQL or Redis may take. asyncpg waits
# 60s by default and Redis indefinitely, so a dependency that accepts the TCP
# connection and then never answers held requests - and the readiness probe -
# hostage (BUG-14).
CONNECT_TIMEOUT_SECONDS = 5


def make_engine(database_url: str) -> AsyncEngine:
    """`hide_parameters=True` keeps bound SQL parameters (emails, password
    hashes, token hashes) out of every exception message SQLAlchemy builds, so
    an error that reaches a log line or an error tracker cannot carry them."""
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
