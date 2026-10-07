"""The three cookies that carry a browser session, and their flags.

Kept in one module so cookie names and security flags cannot drift apart
between login, refresh and logout - a mismatched `path` is the classic reason
a "logged out" user silently keeps a live refresh token."""

from typing import Literal

from fastapi import Response

from app.core.config import get_settings

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"

# The refresh cookie is scoped to the auth routes rather than "/" so the
# longest-lived credential is not attached to every catalogue and image request.
REFRESH_COOKIE_PATH = "/api/v1/auth"

# Lax, not Strict: Strict would withhold cookies on any inbound navigation from
# another site, so following the verification link from an email client would
# land the user on a page that believes they are logged out (SEC-02).
_SAME_SITE: Literal["lax"] = "lax"


def _secure() -> bool:
    """Secure cookies are HTTPS-only, and local development is plain http on
    localhost - so this must be off there, and on everywhere else."""
    return get_settings().environment != "development"


def set_access_cookie(response: Response, access_token: str) -> None:
    """Replace only the access cookie, leaving the session's refresh and CSRF
    cookies alone.

    Used by the MFA step-up, which re-mints the access token so it carries the
    `mfa_completed` claim. Rotating the refresh token there would be wrong -
    the session is not being renewed, only re-described - and rotating CSRF
    would break any request the client already has in flight."""
    settings = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=_secure(),
        samesite=_SAME_SITE,
        path="/",
    )


def set_session_cookies(
    response: Response, *, access_token: str, refresh_token: str, csrf_token: str
) -> None:
    settings = get_settings()

    set_access_cookie(response, access_token)
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=_secure(),
        samesite=_SAME_SITE,
        path=REFRESH_COOKIE_PATH,
    )
    # Deliberately readable by JavaScript: the client must copy this value into
    # the X-CSRF-Token header. That is the "double submit" - a cross-site
    # attacker can make the browser send cookies, but cannot read them.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=False,
        secure=_secure(),
        samesite=_SAME_SITE,
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    """Deletion only takes effect if path and flags match the original cookie,
    which is why they are spelled out identically here."""
    response.delete_cookie(
        ACCESS_COOKIE, path="/", httponly=True, secure=_secure(), samesite=_SAME_SITE
    )
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=_secure(),
        samesite=_SAME_SITE,
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", httponly=False, secure=_secure(), samesite=_SAME_SITE
    )
