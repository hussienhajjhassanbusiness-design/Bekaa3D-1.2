# ADR-018: Store a per-user authentication epoch in PostgreSQL and check it on every authenticated request

**Status:** Accepted
**Date:** 2026-09-10
**Source basis:** SRS SEC-08, §22.1; api-endpoints.md §5; ADR-006; ADR-017

Supersedes, in part, the revocation-latency half of ADR-006. The cookie shapes, rotating refresh sessions, CSRF defence, Argon2id hashing and admin MFA that ADR-006 decided are all unchanged.

## Context

ADR-006 settled that an access token is trusted for its full ~15-minute life and that no `sessions` row is read on an ordinary authenticated request. That kept authenticated reads free of a database round-trip, and the accepted cost was revocation latency: revoking a session took effect at the next refresh rather than immediately.

VS-004 makes that cost unacceptable for one specific operation. A password reset exists because somebody else may hold the credential, and SEC-08 requires it to end the attacker's access. Under ADR-006 alone it did not:

- **Access tokens.** Signed and self-contained. `POST /auth/password-reset/confirm` revoked every `sessions` row, and an attacker's already-issued access token kept reading `/api/v1/me` and every other authenticated route for the remainder of its fifteen minutes. Demonstrated, not assumed: the test asserted the session row was revoked *and* that `GET /me` still answered `200`.
- **MFA login challenges.** VS-005 issues a five-minute challenge as soon as an administrator's password checks out, and stores it in Redis rather than in `sessions` (there is no MFA column, and the frozen entity inventory adds no `mfa_challenges` table). A `sessions` `UPDATE` cannot reach it, so a challenge minted with the *old* password remained redeemable into a brand-new session after the reset.

Three kinds of credential, three storage mechanisms, three expiry clocks, and one operation that has to end all of them at once.

## Decision

Each account carries a monotonic **authentication epoch** in `users.auth_epoch` (`BIGINT NOT NULL DEFAULT 0`).

- Every credential records the epoch it was minted under. Access tokens carry it as an explicit `auth_epoch` JWT claim; MFA login challenges store it alongside the user id in their Redis value.
- Every authentication decision compares the recorded stamp against the account's current epoch and refuses anything that does not match exactly.
- A successful password reset advances it by one, in the same transaction and on the same locked row as the password change, session revocation and reset-token consumption.

`current_claims` validates the JWT signature and standard claims first — a forged or expired token is refused with no database traffic at all — and then reads one indexed scalar. **JWT validation itself remains database-free**; what changes is that an authenticated request now costs one primary-key lookup, and "trusted for its full lifetime" becomes "trusted for its full lifetime unless the account has moved on".

### Why PostgreSQL and not Redis

An earlier draft of this ADR put the epoch in Redis at `auth:epoch:{user_id}`, with a missing key meaning epoch 0. That is wrong, and the failure mode is worse than an outage.

A missing key does not only mean "this account has never been invalidated". It also means Redis restarted, was flushed, evicted the key under memory pressure, or was restored from an older snapshot. In those cases Redis answers **successfully**, the epoch reads as 0, and every token a password reset had just revoked starts working again. The outage failed closed; the recovery did not, and it looks exactly like normal operation.

This deployment offers nothing to lean on. `docker-compose.yml` runs `redis:7-alpine` with no volume, no `redis.conf`, no `appendonly`, and no `maxmemory` policy — the default RDB snapshot writes to a container-local path that dies with the container — under `restart: unless-stopped`. A restart therefore produces an empty, healthy keyspace automatically. Nothing short of an explicit durability and no-eviction guarantee would make Redis acceptable as authentication authority, and there is no such guarantee here.

Redis is deliberately **not** used as a cache for the epoch either. A cache whose miss resolves against the database is correct only if invalidation is, and the write-invalidate ordering against a concurrent reader is its own race; bounded staleness is precisely what this mechanism exists to eliminate. One indexed lookup is cheap, and correct immediate revocation is worth more than a database-free hot path.

Redis keeps the roles it already had: rate limiting, the login throttle, and MFA challenge and completion state. Losing any of those degrades or blocks a request; none of them can silently re-validate a revoked credential.

### Compatibility

A token minted before this claim existed decodes with `auth_epoch = 0`, and the column's server default makes every pre-existing row 0. Those agree, so **existing sessions survive deployment** and begin failing only once their account's epoch actually moves.

A *malformed* claim is a different case from a *missing* one and is rejected outright. 0 is the one value that matches a never-reset account, so a malformed claim falling back to it would be a bypass rather than a compatibility shim. `bool` is a subclass of `int` in Python, so `"auth_epoch": true` is explicitly excluded rather than being read as epoch 1.

### Lock order and concurrency boundary

The guarantee is precise, and worth stating in the negative as well:

> Once a password reset successfully completes, no subsequent authentication decision can accept a credential issued before it.

It is **not** a guarantee that requests already in flight are retroactively unauthenticated. A request that passed `current_claims` before the reset committed has already been authenticated, and it completes. This is inherent to any check-then-act system; the alternative would be holding a lock across the whole request lifetime.

Operations that both read the account and mint or revoke credentials are serialised on the `users` row, and the lock order is **`users` before `sessions`, everywhere**:

| Operation | Order |
|---|---|
| `ConfirmPasswordReset` | `users` FOR UPDATE → epoch/password/tokens → `sessions` UPDATE |
| `Login` | `users` FOR UPDATE (**before** password verification) → `sessions` INSERT |
| `CompleteMfaLogin` | `users` FOR UPDATE → epoch check → `sessions` INSERT |
| `RefreshSession` | unlocked read of `sessions.user_id` → `users` FOR UPDATE → `sessions` FOR UPDATE (`populate_existing`) → revalidate → rotate |

`RefreshSession` had to be restructured for this. VS-003 locked the session row first and never touched the user row; bolting a user lock on after it closes a cycle against the reset's user-then-sessions order, and PostgreSQL reports `DeadlockDetectedError` when both run concurrently. The unlocked peek that opens the sequence decides nothing — it identifies which user row to lock, and every condition is revalidated against the locked re-read.

Login takes the lock *before* verifying the password specifically so a reset committing mid-login cannot leave login validating a hash the database no longer holds.

## Consequences

+ A password reset ends every credential the account holds, immediately: access tokens, sessions, and outstanding MFA challenges
+ The authority is durable and transactional. It cannot be lost by a cache restart, and it advances in the same transaction as the change that justifies it — either both are true or neither is
+ The same mechanism extends to any future operation needing global invalidation (admin-forced logout, account lockout) without new storage
+ Existing tokens keep working across the deploy
- Every authenticated request now costs one indexed primary-key lookup, which ADR-006 had deliberately avoided. This is the trade being reversed, knowingly
- One more column on the hottest table in the system
- MFA enrolment, TOTP secrets and recovery codes are deliberately **not** touched by a reset. A reset proves control of the mailbox, which is exactly what the second factor exists to be independent of; clearing it would turn a mailbox compromise into a full account takeover

## Alternatives rejected

- **The epoch in Redis** (an earlier version of this ADR). A successful read of a lost key is indistinguishable from "never invalidated", so a restart silently re-validates revoked credentials. Rejected on durability, not performance.
- **The epoch in Redis, cached from PostgreSQL.** Removes the durability hole but adds a cache-invalidation race for a saving of one indexed lookup. Correctness first; this can be revisited if that lookup ever shows up in a profile.
- **Read the `sessions` row on every authenticated request.** Closes the access-token window, but costs the same round-trip while reaching neither the MFA challenge nor a future non-session credential. The epoch answers "is any credential for this account still valid?" in one column.
- **A denylist of revoked tokens.** Needs a key per revoked token, and finding every token for one account needs a `SCAN` or a secondary index. `SCAN` on the password-reset path is O(keyspace) work reachable from a public, unauthenticated endpoint: a denial-of-service lever as much as a performance problem.
- **Compare `iat` against a "credentials changed at" timestamp.** Ties a security decision to clock skew and to second-granularity timestamps; two credentials minted in the same second as a reset would be indistinguishable. A monotonic counter has neither problem.
- **A separate MFA-challenge marker alongside a separate token marker.** What VS-004 built first. Two independent markers means two places to remember, two ways to drift, and a third artefact later needing a third marker.
- **Shorten the access-token lifetime instead.** Reduces the window without closing it, and multiplies refresh traffic.
- **Accept the gap and document it.** The original VS-004 proposal. A password reset that leaves the attacker authenticated for fifteen minutes does not do the one thing users believe it does.

## Revisit when

Revisit if the per-request lookup becomes measurable under load — a Redis cache in front of the column is the obvious next step, and would need its invalidation protocol designed properly rather than assumed. Also revisit if a future slice needs per-session rather than per-account invalidation: the epoch is deliberately account-wide and cannot express "revoke this one session immediately".
