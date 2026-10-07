"""Generating, formatting and hashing MFA recovery codes.

Why these are hashed with SHA-256 rather than Argon2id, when passwords are not:
`database-design.md` 5.7 freezes `code_hash TEXT UNIQUE`. A UNIQUE constraint
and a hash lookup both need the hash to be *deterministic*, and Argon2id salts
every hash randomly - the same code would produce a different digest each time,
so UNIQUE would never fire and redemption could not find the row. The frozen
schema therefore decides the algorithm, and the security has to come from
entropy instead of from a slow KDF.

That is why the codes below are deliberately long. 12 characters over a
32-symbol alphabet is 60 bits, so even at 10^10 guesses/second an offline
attacker who stole the table faces tens of years per code. A shorter,
friendlier code would not survive the same arithmetic - the length is doing the
work Argon2id does for passwords."""

import secrets

# Crockford-style: no O/0, I/1 or L, because these get read off a printed sheet
# and transcribed by hand. Ambiguity here turns into support tickets, not
# security incidents, but it turns into them constantly.
_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
_CODE_LENGTH = 12
_GROUP_SIZE = 4

# The single source of truth for the set size.
#
# No project document fixes this number - not the SRS, not database-design.md
# 5.7, not api-endpoints.md. Ten is therefore a VS-005 design decision rather
# than an inherited requirement, and it is ratified as such in
# docs/adr/ADR-017-login-gated-admin-mfa.md so it does not survive as an
# undocumented assumption. Changing it needs no schema change; regeneration
# reads the same constant, so both paths stay in step automatically.
CODES_PER_SET = 10


def generate_code() -> str:
    """One display-formatted recovery code, e.g. `A7KM-3PQR-XT29`."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
    groups = [raw[i : i + _GROUP_SIZE] for i in range(0, _CODE_LENGTH, _GROUP_SIZE)]
    return "-".join(groups)


def generate_code_set() -> list[str]:
    """A full set of plaintext codes. Returned to the administrator exactly
    once, at generation; only the hashes are ever persisted."""
    return [generate_code() for _ in range(CODES_PER_SET)]


def normalize_code(code: str) -> str:
    """Reduce a submitted code to its canonical form before hashing.

    Someone reading a code off paper will type it lowercase, with spaces, or
    without the dashes. All of those are the same code, so normalising here
    means the stored hash has exactly one preimage and redemption does not fail
    on formatting alone."""
    return "".join(character for character in code.upper() if character in _ALPHABET)
