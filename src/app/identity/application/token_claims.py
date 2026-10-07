"""The token-claims port: how a session token is read.

Identity's routers, and through `app.identity.public` every other context, read
an access or refresh token's claims from here - never from the JWT
implementation in `app.identity.application.security.session_tokens`, which also
*issues* tokens and is Identity's own business (BUG-41). Read-only on purpose:
nothing reachable from this module can mint a credential.
"""

from app.identity.application.security.session_tokens import (
    AccessTokenClaims,
    RefreshTokenClaims,
    decode_access_token,
    decode_refresh_token,
)

__all__ = ["AccessTokenClaims", "RefreshTokenClaims", "decode_access_token", "decode_refresh_token"]
