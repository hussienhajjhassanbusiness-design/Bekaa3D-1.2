import hashlib
import secrets

# Verification tokens are high-entropy random values, not low-entropy secrets an
# attacker could brute force offline - a fast cryptographic hash is appropriate
# here and avoids the deliberate CPU/memory cost Argon2id spends on passwords.


def generate_raw_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
