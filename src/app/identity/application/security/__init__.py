"""Identity's security services: password hashing, token generation and hashing,
session JWTs, TOTP and the MFA secret cipher.

Pure computation over argon2, PyJWT, pyotp and Fernet - no database, network or
filesystem I/O - so they are application services rather than infrastructure
adapters, and the application layer calls them directly. Moved here from
`app.identity.infrastructure` in VS-012c (BUG-41)."""
