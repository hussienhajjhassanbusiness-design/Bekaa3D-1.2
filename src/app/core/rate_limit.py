from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.core.exceptions import ApiError

# INCR, then give the key a TTL if it has none - atomically, server-side.
_INCR_WITH_TTL = """
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {count, ttl}
"""


async def enforce_rate_limit(
    request: Request,
    response: Response,
    *,
    key_prefix: str,
    subject: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Count one request against `subject` in a fixed window; raises
    ApiError(429, RATE_LIMITED) once the window's limit is exceeded, otherwise
    sets standard RateLimit-* response headers.

    `subject` is whatever the limit is keyed on: the client IP for the public
    limiters, an administrator's user id for the admin router (VS-011)."""
    redis = request.app.state.redis
    key = f"ratelimit:{key_prefix}:{subject}"

    # One atomic step (BUG-12): INCR and EXPIRE as separate calls left a
    # counter with no TTL whenever anything failed between them, and that
    # subject was then limited forever. The script also heals such a key.
    count, ttl = await redis.eval(_INCR_WITH_TTL, 1, key, window_seconds)
    count, ttl = int(count), int(ttl)
    reset_seconds = ttl if ttl > 0 else window_seconds

    headers = {
        "RateLimit-Limit": str(limit),
        "RateLimit-Remaining": str(max(limit - count, 0)),
        "RateLimit-Reset": str(reset_seconds),
    }

    if count > limit:
        raise ApiError(
            status_code=429,
            code="RATE_LIMITED",
            title="Too many requests",
            detail="Rate limit exceeded. Try again later.",
            # Retry-After as well (RFC 9110 10.2.3), exactly as the login
            # throttle sends it - clients get one machine-readable wait
            # time from every 429 (BUG-11).
            headers={**headers, "Retry-After": str(reset_seconds)},
        )

    for name, value in headers.items():
        response.headers[name] = value


def rate_limiter(
    *, key_prefix: str, limit: int, window_seconds: int
) -> Callable[[Request, Response], Awaitable[None]]:
    """Fixed-window Redis rate limiter keyed by client IP. Returns a FastAPI
    dependency; see `enforce_rate_limit` for the behaviour."""

    async def dependency(request: Request, response: Response) -> None:
        client_ip = request.client.host if request.client else "unknown"
        await enforce_rate_limit(
            request,
            response,
            key_prefix=key_prefix,
            subject=client_ip,
            limit=limit,
            window_seconds=window_seconds,
        )

    return dependency
