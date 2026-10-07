# ADR-006: Use secure cookie authentication, rotating refresh sessions, and admin MFA

**Status:** Accepted  
**Date:** 2026-08-10  
**Source basis:** SRS §14.3, §22.1, §26; database-design.md

## Context

The storefront/admin are browser clients and must resist XSS token theft, CSRF, refresh replay, brute-force attempts, and privileged-account takeover.

## Decision

Use short-lived signed access tokens and rotating refresh tokens in httpOnly, Secure, SameSite cookies. Store hashed refresh-session state with token-version reuse detection. Protect unsafe methods with double-submit CSRF. Hash passwords with Argon2id. Require verified email for normal writes and TOTP MFA for admin access, with hashed one-time recovery codes.

## Consequences

+ Reduces token exposure to browser JavaScript
+ Supports revocation and replay detection
+ Explicit CSRF defense
+ Strong admin boundary
- More complex than simple bearer tokens
- Requires server-side session state and MFA recovery flows

## Alternatives rejected

- **Tokens in localStorage** — XSS can directly steal them.
- **Long-lived stateless JWT only** — Weak revocation/replay handling.
- **No admin MFA** — Contradicts the approved security requirements.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
