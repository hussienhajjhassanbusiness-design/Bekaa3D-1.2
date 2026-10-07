"""VS-005: the only question VS-003's login asks about MFA.

Login has to know whether an account must prove a second factor before it is
given a session. It must not know *how* MFA works. This module is that
boundary: `AdminMfaGate.challenge_required` is the entire MFA surface that
`identity/application/commands/login.py` can see, and everything behind it -
credentials, TOTP, recovery codes, challenges, ciphertext - stays in VS-005.

Keeping the gate in its own VS-005 file rather than inlining the check inside
login.py is deliberate. It is what lets a reader months from now separate
VS-003's original login implementation from the VS-005 integration added to
it: in login.py the integration is one constructor argument and one branch,
and every line of MFA reasoning lives here."""

from dataclasses import dataclass
from uuid import UUID

from app.identity.application.ports import MfaCredentialStore
from app.identity.domain.entities import User
from app.identity.domain.enums import UserRole


@dataclass(frozen=True)
class MfaChallengeRequired:
    """Login stopped short of issuing a session: this account must clear MFA.

    Carries the user id and the account's authentication epoch, and
    deliberately nothing else. At this point no session row exists, no token has
    been minted, and no cookie has been set - so there is nothing here that
    would be safe to hand back to the caller. The route converts it into an
    opaque, short-lived challenge id, which is what `202 MfaChallengeRead`
    actually returns (api-endpoints.md:252).

    The epoch travels with it because the challenge has to be stamped with the
    value read under login's row lock, not one re-read afterwards - a reset
    landing in between would otherwise mint a challenge that looks current
    (ADR-018)."""

    user_id: UUID
    auth_epoch: int


class AdminMfaGate:
    """Answers "must this account clear a second factor before it gets a
    session?" for VS-003's login."""

    def __init__(self, credential_repo: MfaCredentialStore) -> None:
        self._credentials = credential_repo

    async def challenge_required(self, user: User) -> bool:
        """Administrators with *confirmed* MFA, and nobody else.

        Two conditions, both load-bearing:

        - Role. SEC-04 requires the second factor for administrators; making a
          customer answer a challenge would be inventing a requirement no
          document states.
        - `enabled_at IS NOT NULL`. A credential row whose enrollment was never
          confirmed is an abandoned or in-progress setup, not a working second
          factor. Treating it as a requirement would be a lockout bug: the
          administrator would be challenged for a secret their authenticator
          never stored, and the endpoints that would let them fix it
          (`/auth/mfa/setup`, `/setup/confirm`) need the very session the
          challenge is withholding.

        The second condition is why this asks `is_enabled` rather than merely
        whether a row exists."""
        if user.role is not UserRole.ADMIN:
            return False

        credential = await self._credentials.get_by_user_id(user.id)
        return credential is not None and credential.is_enabled
