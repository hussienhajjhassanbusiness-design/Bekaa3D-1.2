import asyncio
import contextlib
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

_hasher = PasswordHasher()


def _normalise(password: str) -> str:
    """NFKC, per NIST SP 800-63B 5.1.1.2 (BUG-24): the same password typed on
    two keyboards - "é" precomposed on one, "e" + combining accent on another -
    must be the same password."""
    return unicodedata.normalize("NFKC", password)


def hash_password(password: str) -> str:
    """Synchronous - for import time and tests only. Request paths must use
    `hash_password_async`, or the ~80ms hash freezes the event loop."""
    return _hasher.hash(_normalise(password))


def verify_password(*, password: str, password_hash: str) -> bool:
    """Synchronous - see `hash_password`. Request paths use `verify_password_async`.

    Tries the normalised form, and - only when it differs - the password as
    typed, because hashes written before normalisation was introduced were made
    from the raw input. Every candidate is always verified, with no early exit:
    how many Argon2 operations run then depends only on the submitted text,
    never on the account, so the dummy-hash branches stay equally expensive."""
    normalised = _normalise(password)
    candidates = [normalised] if normalised == password else [normalised, password]
    matched = False
    for candidate in candidates:
        with contextlib.suppress(VerificationError):
            matched = _hasher.verify(password_hash, candidate) or matched
    return matched


# Argon2 is deliberately CPU-expensive (~80ms). Run inline on the event loop it
# stalls every other request on the worker for the whole hash, so a burst of
# logins becomes a denial of service. argon2-cffi releases the GIL while
# hashing, so a worker thread runs it truly in parallel with the loop.


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(*, password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(verify_password, password=password, password_hash=password_hash)


# Anti-enumeration constant work: a real hash to verify against, so branches
# that have no account to check still pay for exactly one Argon2 verification.
_DUMMY_PASSWORD = "bekaa3d-constant-work-placeholder"
_DUMMY_HASH = _hasher.hash(_DUMMY_PASSWORD)


async def perform_dummy_hash() -> None:
    """Spend one Argon2id verification's worth of work and discard the result.

    Anti-enumeration control (SEC-06, api-endpoints.md 195: account existence
    must not leak through "response body, status, or timing"). Branches that
    return without touching a password would otherwise answer in ~8ms while the
    branch that hashes answers in ~80ms, which is a reliable existence oracle.

    This is deliberately real hashing work rather than a sleep: a sleep is
    trivially tuned out by load, and it does not track the hasher's parameters
    if they are ever hardened.
    """
    await verify_password_async(password=_DUMMY_PASSWORD, password_hash=_DUMMY_HASH)
