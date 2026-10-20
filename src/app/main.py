from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api.enumeration import EnumerationFloorMiddleware
from app.api.errors import register_exception_handlers
from app.api.head import HeadAsGetMiddleware
from app.api.health import router as health_router
from app.api.middleware import IpHashKeyRefreshMiddleware, RequestIDMiddleware
from app.api.openapi import custom_openapi
from app.api.request_target import RequestTargetMiddleware
from app.api.v1.router import router as v1_router
from app.core import models as _models  # noqa: F401 - registers models onto Base.metadata
from app.core.config import get_settings
from app.core.database import CONNECT_TIMEOUT_SECONDS, make_engine, make_session_factory
from app.core.ip_hash_keyring import refresh_ip_hash_key
from app.core.logging import configure_logging
from app.core.security import check_phone_hash_salt
from app.integrations.captcha.factory import captcha_verifier
from app.payments.public import configured_payment_providers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    settings = get_settings()
    # Fail at boot, not on the first form, when captcha is misconfigured (ADR-026).
    captcha_verifier(settings)
    # VS-028: a weak PHONE_HASH_SALT outside dev/test refuses to boot (plan Q5).
    check_phone_hash_salt(settings)
    # VS-023: production + mock, or an unknown provider, refuses to boot (plan 3.9).
    app.state.payment_providers = configured_payment_providers(settings)
    app.state.db_engine = make_engine(settings.database_url)
    app.state.db_session_factory = make_session_factory(app.state.db_engine)
    # Best-effort: a database outage at boot leaves hash_ip returning None until
    # IpHashKeyRefreshMiddleware's next attempt (ADR-028).
    await refresh_ip_hash_key(app.state.db_session_factory)
    # redis-py ships py.typed but Redis.from_url itself isn't fully annotated upstream.
    # A connect timeout, so a Redis that accepts but never answers cannot hang a
    # request forever (BUG-14); the default is to wait indefinitely.
    app.state.redis = redis.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url, socket_connect_timeout=CONNECT_TIMEOUT_SECONDS
    )
    yield
    for provider in app.state.payment_providers.values():
        await provider.aclose()
    await app.state.redis.aclose()
    await app.state.db_engine.dispose()


app = FastAPI(title="Bekaa3D API", version="0.1.0", lifespan=lifespan)

# Innermost first. HEAD runs as GET (BUG-20); a control character anywhere in
# the path or query is a 422 before routing (BUG-03) - inside RequestID, so the
# problem response carries the request's id.
app.add_middleware(HeadAsGetMiddleware)
app.add_middleware(RequestTargetMiddleware)
# VS-046: reload the IP-hash key before any handler can hash, inside RequestID.
app.add_middleware(IpHashKeyRefreshMiddleware)
app.add_middleware(RequestIDMiddleware)
# SEC-06: equal response time on register / resend / reset-request (BUG-04/05/45).
app.add_middleware(EnumerationFloorMiddleware)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(v1_router)

# VS-005: describe the cookie/CSRF/MFA security schemes in the generated
# OpenAPI document. Documentation only - no route's behaviour changes.
app.openapi = lambda: custom_openapi(app)  # type: ignore[method-assign]
