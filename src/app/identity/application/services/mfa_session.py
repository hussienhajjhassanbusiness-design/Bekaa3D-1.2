"""Per-session MFA state, and the short-lived login challenge that establishes it.

Why Redis rather than Postgres. `sessions` (database-design.md 5.3) has no MFA
column and the frozen entity inventory adds no `mfa_challenges` table, so both
of these would mean deviating from the approved schema. They are also exactly
what Redis expiry is for: the completion flag dies with the session and the
challenge dies in minutes. This follows the precedent LoginThrottle already set
for the SEC-05 counters.

Two distinct pieces of state live here, and the difference matters:

- **The login challenge** is *pre-authentication*. It is created by
  `POST /auth/login` when an administrator's password is right but their second
  factor is still outstanding (api-endpoints.md:252). At that moment there is
  no session, so the challenge is bound to the **user**. It is the only thing
  standing between the caller and a session, which is why it is random,
  single-use and short-lived.
- **The completion flag** is *post-authentication* session state, keyed by
  session id. It records that a session was born MFA-complete so the claim
  survives refresh rotation.

Neither is a source of truth about whether an account has MFA enabled -
`mfa_credentials.enabled_at` is."""

import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID

# Long enough to open an authenticator app or find a printed recovery sheet,
# short enough that an abandoned challenge is not left lying around. This is
# the window in which a correct password alone is worth something, so it is
# kept tight.
CHALLENGE_TTL_SECONDS = 5 * 60


@dataclass(frozen=True)
class PendingLoginChallenge:
    """A resolved login challenge: whose it is, and which authentication epoch
    it was minted in.

    The epoch is the account-wide one from `auth_epoch`, not a marker of this
    module's own: a challenge is an authentication artefact like any other, and
    a password reset has to invalidate all of them together. It is carried here
    rather than checked here because the authoritative check has to happen under
    the user row lock - see CompleteMfaLogin."""

    user_id: UUID
    epoch: int


class MfaSessionStore:
    def __init__(self, redis: Any) -> None:
        self._redis = redis

    @staticmethod
    def _completed_key(session_id: UUID) -> str:
        return f"mfa:completed:{session_id}"

    @staticmethod
    def _challenge_key(challenge_id: str) -> str:
        return f"mfa:challenge:{challenge_id}"

    async def mark_completed(self, *, session_id: UUID, ttl_seconds: int) -> None:
        """Record that this session cleared MFA.

        The TTL is the maximum session lifetime, so the flag is garbage
        collected rather than accumulating forever. It is not a capability on
        its own: reaching an admin route still needs the session cookie and an
        access token carrying the claim, so a flag that outlives a revoked
        session grants nothing by itself."""
        await self._redis.set(self._completed_key(session_id), "1", ex=max(ttl_seconds, 1))

    async def is_completed(self, session_id: UUID) -> bool:
        return await self._redis.get(self._completed_key(session_id)) is not None

    async def clear_completed(self, session_id: UUID) -> None:
        await self._redis.delete(self._completed_key(session_id))

    async def create_login_challenge(self, user_id: UUID, auth_epoch: int) -> str:
        """Open a pending-login challenge for one account and return its id.

        The id is random and opaque rather than anything derived from the
        account: it is handed out in a `202` body to a caller who is, at this
        point, only half authenticated. A guessable or user-derived value would
        let someone who knows an administrator's id skip straight to submitting
        second factors.

        24 bytes of `secrets.token_urlsafe` is ~192 bits, so the id itself is
        not the weak link; the TOTP behind it is, which is why
        `/auth/mfa/verify` is rate limited on top of this."""
        challenge_id = secrets.token_urlsafe(24)
        # The account's authentication epoch is stamped into the challenge at
        # issuance. A password reset increments that epoch, so every challenge
        # minted before it is left carrying a stale number and is refused on
        # redemption (SEC-08, ADR-018). The caller supplies it rather than this
        # store reading it, so the epoch has exactly one owner.
        await self._redis.set(
            self._challenge_key(challenge_id),
            f"{user_id}:{auth_epoch}",
            ex=CHALLENGE_TTL_SECONDS,
        )
        return challenge_id

    async def take_login_challenge(self, challenge_id: str) -> PendingLoginChallenge | None:
        """Resolve and spend a pending-login challenge in one atomic step.

        Returns the account it belongs to, or None if the id is unknown, already
        spent, or expired. The three are deliberately indistinguishable to the
        caller: all three surface as the same `410`, so the endpoint cannot be
        used to probe which challenge ids were ever real.

        Single-use: a challenge is spent whether or not the factor turns out to
        be correct. `GETDEL` makes that hold under concurrency too (BUG-30) - a
        separate GET then DELETE let N simultaneous requests all read the same
        challenge before any deleted it, buying N guesses at the second factor
        with one password."""
        raw = await self._redis.getdel(self._challenge_key(challenge_id))
        if raw is None:
            return None
        value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        user_part, _, epoch_part = value.partition(":")
        try:
            user_id = UUID(user_part)
        except ValueError:
            return None
        try:
            # A value with no epoch segment cannot be trusted to predate any
            # invalidation, so it is given an epoch that matches nothing.
            epoch = int(epoch_part) if epoch_part else -1
        except ValueError:
            epoch = -1
        return PendingLoginChallenge(user_id=user_id, epoch=epoch)
