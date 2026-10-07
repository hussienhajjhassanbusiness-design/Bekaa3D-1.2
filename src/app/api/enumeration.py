"""A response-time floor for enumeration-sensitive endpoints (SEC-06).

Register, resend-verification and password-reset request must not reveal
through timing whether an address has an account (api-endpoints.md 195). Each
of them does exactly one Argon2 operation on every branch, which equalises the
expensive work - but the branches still differ in database work: only a new
registration inserts a user, token, outbox and audit row, only an eligible
reset request writes a token. Those writes, and the commit that follows them,
took 30-50ms and were measurable from outside (BUG-04, BUG-05, BUG-45).

Rather than inventing decoy writes, every response on these paths is held back
until a fixed floor has elapsed since the request arrived. The floor is set
well above the slowest branch's normal work, so every branch answers at the
same moment. It is applied twice:

- at `http.response.start`, so the moment the answer arrives is constant. The
  session commits *before* the response is sent (BUG-46, see
  `app.api.dependencies`), so this floor already covers the commit that only
  the writing branches pay; and
- when the ASGI call completes. Anything that still runs after the response
  has started - request-scoped cleanup, closing the session - is padded too,
  so it cannot show up through a keep-alive connection that stays busy until
  it finishes.

If the real work ever exceeds the floor (a badly overloaded database), timing
could separate again; the `timing`-marked tests are how to notice.
"""

import asyncio
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

ENUMERATION_SENSITIVE_PATHS = frozenset(
    {
        "/api/v1/auth/register",
        "/api/v1/auth/resend-verification",
        "/api/v1/auth/password-reset/request",
    }
)

RESPONSE_FLOOR_SECONDS = 0.3
# Completion (after any post-response cleanup) is padded to a later floor.
COMPLETION_FLOOR_SECONDS = 0.4


class EnumerationFloorMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        paths: frozenset[str] = ENUMERATION_SENSITIVE_PATHS,
        floor_seconds: float = RESPONSE_FLOOR_SECONDS,
        completion_floor_seconds: float = COMPLETION_FLOOR_SECONDS,
    ) -> None:
        self.app = app
        self._paths = paths
        self._floor = floor_seconds
        self._completion_floor = completion_floor_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] not in self._paths:
            await self.app(scope, receive, send)
            return

        started = time.monotonic()

        async def send_after_floor(message: Message) -> None:
            if message["type"] == "http.response.start":
                remaining = self._floor - (time.monotonic() - started)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            await send(message)

        await self.app(scope, receive, send_after_floor)
        remaining = self._completion_floor - (time.monotonic() - started)
        if remaining > 0:
            await asyncio.sleep(remaining)
