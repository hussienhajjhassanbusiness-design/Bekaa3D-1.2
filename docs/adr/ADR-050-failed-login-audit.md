# ADR-050: Failed login audit - one counted row per account, IP and 15 minutes, in a transaction of its own

**Status:** Accepted (2026-11-05).
**Date:** 2026-11-05
**Source basis:** Owner decision of 2026-11-05 after the end-to-end rehearsal found that a refused login left no audit row; SRS BR-132 ("every... auth event... is audit-logged"), SEC-05; `entities-and-business-rules.md` AuditLog; [ADR-028](ADR-028-keyed-monthly-rotated-ip-hashes.md).
**Amends:** "AuditLog is append-only" (`entities-and-business-rules.md`, `database-design.md` §13.2, the glossary) with one exception, decision 4. [`admin-mfa.md`](../admin-mfa.md)'s "a wrong code is noise and is not recorded" (decision 2).
**Applies first to:** `POST /api/v1/auth/login`, `POST /api/v1/auth/mfa/verify`; audit action `user.login_failed`. No migration.

## Context

BR-132 requires every auth event in the audit log, but a refused login wrote nothing. Writing a row in the request's transaction cannot work: `get_session` rolls back when the route raises. A row per attempt is not safe either: the endpoint is public, so anyone could grow the audit table at will.

## Decision

1. **A separate transaction.** `record_failed_login` opens its own session and commits on its own, so the request's rollback cannot erase the row. The route rolls the request back first: holding its connection while waiting for a second one would let a burst of bad logins deadlock the pool.
2. **What counts.** `reasons` counts each kind of refusal: `invalid_credentials` (a wrong password or an unknown email), `locked_out` (SEC-05's lockout), `account_disabled` and `mfa_invalid` (a wrong TOTP or recovery code, an administrator's half-login). A request stopped earlier by the per-IP rate limit evaluates no credential and is not counted. `mfa.replay_rejected` keeps its own row.
3. **One row per account, IP hash and 15 minutes.** The row has `action = user.login_failed`, `entity_type = User`, `entity_id` = the account and `actor_user_id` NULL, because the caller proved nothing. `after_data` is `{count, reasons, last_failed_at}`. The window starts at the row's `created_at`. An advisory lock on the key makes simultaneous failures share one row and lose no count.
4. **The one audit row that is ever updated.** A count cannot be kept append-only without a row per attempt, which is what this ADR must avoid. Only `count_in_window` updates a row, and only `after_data` of its own action. No business API edits audit rows, as before.
5. **An unknown email stores no address.** Those attempts have `entity_id` NULL and share one row per IP hash. People type passwords into the email field, so the attempted text never reaches the log. The answer stays the same whether or not the account exists: `INVALID_CREDENTIALS`.
6. **An audit failure never changes the answer.** `record_failed_login` catches any exception and logs `failed_login_audit_lost`, with the reason and the error's type only. An outage must not turn a 401 into a 500, which would also tell an attacker something changed.

## Consequences

+ An operator can see password guessing against an account, and a stolen admin password failing at the second factor.
+ Rows are bounded by the number of distinct IP hashes per account per 15 minutes, and the per-IP login limit bounds what one address can do.
- A failed login costs one more short transaction, after the password check.
- A wide botnet can still write one row per address per window. That is the accepted bound: fewer rows would hide the addresses.
- The monthly IP salt rotation (ADR-028) splits a window across it into two rows.
- A wrong `current_password` on `DELETE /me` or MFA setup stays unaudited: the caller already holds a session, and those are not logins.

## Alternatives rejected

- **A row per attempt:** an unauthenticated caller could grow the audit table without limit.
- **A separate counters table:** failed logins would be missing from `GET /api/v1/admin/audit-logs`, and an operator would have two places to look.
- **Committing the request's session and raising, as `mfa.replay_rejected` does:** it works for one row, but holds the request's connection through the lock wait.
- **A hash of the attempted email for unknown addresses:** a plain hash is reversible by dictionary and would survive the account's later deletion; grouping by IP is enough to see an attack.
