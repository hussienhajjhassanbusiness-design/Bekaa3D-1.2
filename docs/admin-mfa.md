# Administrator MFA and the admin security boundary

VS-005. Implements **F-118** (Admin MFA), **SEC-04** (admin MFA treated as
required) and **SEC-10** (admin routes return 404 to non-admins).

Persistence follows [`requirments/database-design.md`](requirments/database-design.md)
§5.6–5.7 exactly: `mfa_credentials` and `mfa_recovery_codes`, no added columns.

Both tables are created by Alembic revision **`c42f47ccac47`**
(`mfa credentials and recovery codes`), which revises `33a9f7a809ea` and is the
single head. Its downgrade drops the `mfa_method` enum type explicitly —
autogenerate omits that, and without it the upgrade/downgrade/upgrade round-trip
CONTRIBUTING.md requires fails on `type "mfa_method" already exists`.

## Enrollment

An administrator enrols once, from an ordinary authenticated session. No admin
route is reachable until this is done.

```
POST /api/v1/auth/mfa/setup            { "current_password": "..." }
  -> 200 { secret, otpauth_uri, issuer, account_name }
```

The password is re-checked even though the caller already holds a valid
session: enrollment decides *what the second factor is*, so a borrowed session
must not be enough to point it at someone else's authenticator.

The response carries the raw TOTP secret. This is the only response in the
system that ever does — feed `otpauth_uri` to an authenticator app (usually as
a QR code) and discard it. The stored copy is encrypted; there is no endpoint
that can show it again.

**MFA is not enabled yet.** `enabled_at` stays `NULL`, so an enrollment that is
started and abandoned leaves the account exactly as it was.

```
POST /api/v1/auth/mfa/setup/confirm    { "code": "123456" }
  -> 200 { recovery_codes: [...10 codes...], generated_at }
```

Confirming proves the authenticator actually stored the secret, which is what
stops an administrator locking themselves out. Only now is `enabled_at` set.

The ten recovery codes are returned **once** and never again — only their
hashes are stored. Print them or put them in a password manager before closing
the response. Confirming also completes MFA for the current session, so there
is no immediate second challenge.

Re-enrolling while MFA is already enabled is refused with `409
INVALID_STATE_TRANSITION`. A single `secret_ciphertext` column cannot hold a
live and a pending secret at once, so allowing it would either void a working
factor before its replacement is proven or mark an unconfirmed secret as
enabled. Both lock the account out.

## Signing in as an administrator

Login is **gated**, not stepped up. An administrator with MFA enabled never
receives a session from `/auth/login` — only a challenge (api-endpoints.md:252):

```
POST /api/v1/auth/login        { "email": "...", "password": "..." }
  -> 202 { challenge_id: "...", expires_in_seconds: 300 }
     No access cookie. No refresh cookie. No CSRF cookie.

POST /api/v1/auth/mfa/verify   { "challenge_id": "...", "code": "123456" }
  -> 204   sets the full auth + CSRF cookie set

GET /api/v1/admin/<anything>
  -> 200
```

A correct password on its own therefore buys nothing but a five-minute
challenge. There is no window in which an administrator holds a real session
without having proved a second factor, and the session that `/verify` creates
is born with the MFA claim already set.

`POST /auth/mfa/verify` is the one authenticated-feeling route in the system
that takes **no session cookie and no CSRF header** — neither exists yet, which
is the entire point. What authenticates the caller is the challenge id: 192
bits of randomness, single-use, five-minute expiry, and issued only to someone
who has already presented the correct password. The rate limit below is what
stands between that and the six-digit TOTP keyspace.

The challenge is **single-use and spent on the attempt**, not on success: a
wrong code burns it and the administrator logs in again for a fresh one. That
costs a mistyped code one extra round trip and denies an attacker a
five-minute window to sit and guess against.

Two cases deliberately do *not* produce a challenge, because in both the
account has no working second factor to prove and challenging it would be a
lockout bug — the endpoints that fix it need the very session the challenge
would be withholding:

- an administrator who has never enrolled;
- an administrator whose enrollment was started but never confirmed
  (`enabled_at IS NULL`).

Both get an ordinary `200` session, which the admin boundary still refuses with
`401 MFA_REQUIRED` until enrollment is confirmed.

MFA completion is *session* state. It survives token rotation on
`POST /api/v1/auth/refresh`, and it disappears when the session does.

## Recovery

If the authenticator is lost, substitute a recovery code for the TOTP at the
same point in the login:

```
POST /api/v1/auth/login        { "email": "...", "password": "..." }
  -> 202 { challenge_id: "...", expires_in_seconds: 300 }

POST /api/v1/auth/mfa/verify   { "challenge_id": "...", "recovery_code": "A7KM-3PQR-XT29" }
  -> 204
```

Codes are case-insensitive and dash-insensitive — they are read off paper, so
`a7km3pqrxt29` works too. Each code works exactly **once**; concurrent attempts
to spend the same one are serialised in the database so exactly one wins.

Replace the set after using one:

```
POST /api/v1/auth/mfa/recovery-codes/regenerate   { "current_password": "..." }
  -> 200 { recovery_codes: [...10 new codes...], generated_at }
```

Regeneration voids every *unused* code and issues ten fresh ones. Already-spent
codes are retained, not deleted: `code_hash` is `UNIQUE` table-wide, and
forgetting that a code was redeemed would let the same string be reissued later
and accepted a second time.

There is no "disable MFA" endpoint. SEC-04 treats admin MFA as required, so
turning it off is not a normal V1 operation. An administrator who loses both
their authenticator and every recovery code needs an out-of-band procedure with
database access — which is exactly why the recovery codes are worth storing
properly.

## The admin boundary

`require_admin` (`src/app/identity/api/dependencies.py`) is the single
enforcement point. `src/app/api/v1/admin.py` applies it to the whole
`/api/v1/admin` prefix, so VS-007 and VS-009 mount routes there and inherit it
rather than repeating the check.

| Caller | Response |
|---|---|
| No session | `401 AUTH_REQUIRED` |
| Authenticated customer | `404 NOT_FOUND` |
| Administrator, enrollment unconfirmed | `401 MFA_REQUIRED` |
| Administrator, MFA complete | proceeds |

The boundary does **not** mint a challenge. Under the login-gated flow the only
source of a challenge is `POST /auth/login`, and an administrator who reaches
the `MFA_REQUIRED` branch is mid-enrollment — they need `/auth/mfa/setup` and
`/setup/confirm`, which their existing session can already call. Handing out a
challenge here would create a second, session-bound route to an MFA-complete
session, which is exactly the parallel authentication path this slice is meant
not to have.

The 404 is SEC-10: a 403 would confirm the route exists. Its `title`, `detail`
and `type` reproduce byte for byte what a genuinely missing route returns —
matching only the status code would leave the wording as an oracle.

Since VS-011 the rule covers **every** path under `/api/v1/admin`, not just the
real routes: two hidden catch-all routes (`src/app/api/v1/admin.py`) run the same
`require_admin` for any path, method (including `HEAD` and `OPTIONS`) and
trailing-slash variant that no real route serves. An anonymous caller therefore
gets `401 AUTH_REQUIRED` and a customer the imaginary-path `404` everywhere, and
neither ever sees a `405`/`Allow` or a `307` redirect that would reveal a real
route. Only an MFA-complete administrator reaches `405` (with an `Allow` header
computed from the route table) or a true `404`. The catch-alls match every method, including
ones they do not list (`TRACE`, `PROPFIND`, made-up methods), and every admin route
uses `AdminBoundaryRoute`, which runs the boundary before FastAPI parses the
request body, so a malformed body cannot answer `400` ahead of authentication. The router also carries its own
rate limit, 300 requests per 60 s per administrator, applied after the boundary.

## OpenAPI security scheme

`src/app/api/openapi.py` annotates the generated schema so `/docs` describes
what the routes actually require rather than showing everything as public:

| Scheme | Where | Applies to |
|---|---|---|
| `sessionCookie` | `access_token` cookie | every authenticated operation |
| `csrfToken` | `X-CSRF-Token` header | cookie-authenticated **unsafe** methods only |

`POST /auth/login`, `POST /auth/mfa/verify` and the public auth routes are
declared with no security requirement — `/verify` genuinely has none beyond the
challenge in its body, which is the point worth documenting.

This is a post-processing pass over the generated document, not a set of
FastAPI security dependencies on the routes. Declaring `APIKeyCookie` on
`current_claims` or `require_csrf` would put a second credential-reading
mechanism beside the one those functions already implement, in shared VS-003
code, for a documentation-only benefit. No route's runtime behaviour changes.

## Rate limits

Far tighter than the customer auth limits, because a TOTP is only six digits:

| Endpoint | Limit |
|---|---|
| `/auth/mfa/setup` | 5 / hour |
| `/auth/mfa/setup/confirm` | 10 / hour |
| `/auth/mfa/verify` | 10 / 15 min |
| `/auth/mfa/recovery-codes/regenerate` | 5 / hour |

Per-IP, on the shared `rate_limiter`, with the usual `RateLimit-*` headers.
These are V1 design assumptions — the SRS fixes no numbers.

## Audit events

Written through the existing `AuditLogRepository`, `entity_type =
"MfaCredential"`:

| Action | When | Recorded |
|---|---|---|
| `mfa.enrollment_started` | `/setup` | — |
| `mfa.enabled` | `/setup/confirm` | `recovery_codes_issued` |
| `mfa.verified` | TOTP accepted at `/verify` | — |
| `mfa.recovery_code_used` | recovery code accepted at `/verify` | `remaining_recovery_codes` |
| `mfa.replay_rejected` | a *correct* TOTP was submitted whose step was already spent | `time_step` |
| `mfa.recovery_codes_regenerated` | regeneration | `unused_codes_invalidated`, `recovery_codes_issued` |

One more is written against `entity_type = "User"`:

| Action | When | Recorded |
|---|---|---|
| `user.mfa_challenge_issued` | a correct admin password reached the challenge at `/auth/login` | — |

That row exists because BR-132 requires auth events to be audited and a correct
administrator password is one. Without it a half-login is invisible: someone
holding a stolen admin password could confirm it works, repeatedly, and the log
would show nothing unless they also cleared the second factor. It is
deliberately *not* `user.logged_in` — no session was created, and recording one
that never existed would make "when did this account sign in?" answer wrongly.

A completed challenge also writes the ordinary VS-003 `user.logged_in` row
against the new session. A session reached through MFA is still a login, and
splitting the audit vocabulary would make "when did this account sign in?" a
two-query question.

`mfa.replay_rejected` is the one row written on a *failed* request. A wrong
code is noise and is not recorded; a correct code arriving twice means one was
captured somewhere, and an operator needs to be able to see that. Because
`get_session` runs one transaction per request, the route commits this row
before answering — otherwise the evidence would roll back with the rest of the
failed request. `time_step` names the 30-second bucket and is not redeemable
for anything.

Counts only. No secret, code, hash, password or token is ever written to an
audit row, and `test_recovery_use_is_audited_without_recording_the_code` and
`test_a_detected_replay_is_audited_without_recording_the_code` hold that line.

## One code, one use

An accepted TOTP cannot be presented again. RFC 6238 §5.2 requires it: the
window reaches one step either side of now, so a code stays live for roughly 90
seconds, and without this rule an attacker who intercepted a single code — a
phishing proxy, a glance at a screen — could spend it a second time. That is
precisely the interception a second factor is supposed to survive.

`mfa_credentials.last_totp_step` holds the RFC 6238 time-step of the last TOTP
the credential accepted, and any code matching that step **or earlier** is
refused. It is a high-water mark, not a list of spent codes: nothing
accumulates and nothing needs collecting. `<=` rather than `==` because the
window looks one step backwards as well, and the mark never moves backwards, so
two interleaved requests cannot make a spent step redeemable again.

**Only an accepted TOTP spends a TOTP step.** The scope is deliberately narrow:

- **Recovery codes are independent.** Redeeming one leaves `last_totp_step`
  untouched, so a TOTP submitted in the same 30-second bucket still works. A
  recovery code and a TOTP are separate one-time credentials, and spending one
  must not consume the other. Recovery codes are single-use in their own right
  — `mfa_recovery_codes.used_at` plus the `SELECT … FOR UPDATE` row lock — and
  that mechanism is untouched by any of this.
- **A recovery redemption still updates `last_used_at`.** That column means
  "last authenticated by any means" and is unchanged in meaning; it is simply
  no longer what replay protection reads.
- **Enrollment confirmation does spend its step.** `/setup/confirm` accepts a
  real code, so that code cannot then log in. No administrator meets this in
  practice — confirmation already leaves the session MFA-complete, so there is
  nothing to log in *for*. Tests that enrol and immediately sign in use the
  `login_totp` helper, which returns the next step's code.

The check is serialised in the database, not in Python. Deciding whether a step
is spent and then writing the new mark is a read-modify-write, and `max()` in
the entity only orders values already inside one process's memory: two
transactions reading the same stale mark would both conclude the step was
unspent, both accept, and one intercepted code would open two admin sessions.
`MfaCredentialRepository.get_by_user_id_for_update` takes a `SELECT ... FOR
UPDATE` row lock, so the second transaction blocks, re-reads the advanced row,
and correctly refuses. `/auth/mfa/verify` and `/auth/mfa/setup/confirm` both
take it; the login gate deliberately does not, since it only asks a question
and locking there would serialise every administrator login. Proven in
`tests/concurrency/test_totp_step_single_use.py`.

A rejected replay is reported as plain `MFA_INVALID`, byte for byte what a
simply-wrong code returns. Saying "already used" would confirm to an attacker
that they hold a genuine code. Internally it is not silent: see
`mfa.replay_rejected` in the audit table above.

## Configuration

```
MFA_SECRET_KEY=<openssl rand -hex 32>    # encrypts stored TOTP secrets
MFA_ISSUER=Bekaa3D                       # shown in the authenticator app
```

`MFA_SECRET_KEY` is separate from `JWT_SIGNING_KEY` and `CSRF_SECRET` on
purpose — one key, one job. **Losing it locks every administrator out of MFA
and forces re-enrollment; leaking it exposes every stored secret.** It is not
rotatable without re-enrolling, since existing ciphertext cannot be read with a
new key.

## Cryptography

Deliberate, and asymmetric between the two kinds of material:

- **TOTP secret — encrypted, not hashed.** Verifying a TOTP means recomputing
  it, which needs the original back. Fernet (AES-128-CBC + HMAC-SHA256) rather
  than raw AES, so tampering with a stored secret fails loudly instead of
  steering it toward an attacker-chosen value.
- **Recovery codes — hashed, and with SHA-256 rather than Argon2id.** The frozen
  schema specifies `code_hash TEXT UNIQUE`, and both the constraint and the
  lookup need a *deterministic* hash; Argon2's random salt would break each.
  The schema therefore picks the algorithm, so security comes from entropy
  instead: 12 characters over a 32-symbol alphabet is 60 bits, which at 10^10
  guesses/second is tens of years per code.

The alphabet excludes `O/0`, `I/1` and `L` because these get transcribed by
hand.

## Outstanding work

- **Admin routes.** VS-005 mounts none — `/api/v1/admin` is the boundary only.
  VS-007 (settings) and VS-009 (user management) add the endpoints.

Deliberately deferred from the VS-005 review, in rough priority order. None is
a blocker; each is real and should be picked up when the surrounding code is
next touched.

- **No per-account MFA throttle.** Every limit in the table above is keyed on
  client IP, and the VS-003 login throttle is per `(email, IP)` — so an
  attacker who already holds the password and can rotate source addresses faces
  no account-level counter at all, only the ~1-in-333,000 odds of the code
  itself. The single-use challenge is what carries the defence today, since
  each guess costs a full password login. A failure counter on
  `mfa_credentials` that locks the second factor after N consecutive misses
  would close it.
- **Proxy IP handling.** `core/rate_limit.py` keys on `request.client.host`
  directly. Behind a reverse proxy every caller collapses onto the proxy's
  address and each limit becomes global rather than per-client. Pre-existing
  from VS-002, but it now guards the admin boundary, which raises the stakes.
  Fixing it means deciding which forwarding header is trusted and where.
- **`MFA_SECRET_KEY` cannot be rotated.** Stored ciphertext carries no key
  identifier, so a new key orphans every secret and forces every administrator
  to re-enrol. A `key_version` column on `mfa_credentials` and a dual-read
  decrypt would make rotation possible, and it is far cheaper to add now than
  once real administrators exist.
- **`MfaSessionStore.clear_completed` is unused.** Logout never clears the
  completion flag. Not exploitable — session ids are UUIDs and are never
  reused, a revoked session cannot refresh, and the flag grants nothing on its
  own — but an unused method that reads like a safeguard is worse than no
  method. Either call it from logout or delete it.
- **Recovery-code normalisation drops unknown characters.** `normalize_code`
  strips anything outside the alphabet rather than mapping Crockford
  confusables, so an administrator who types `O` for `0` or `I` for `1` gets a
  silently shortened code and a rejection they cannot explain. Mapping the
  confusables would be friendlier and no less safe.
- **Entropy comment is off.** `domain/recovery_codes.py` describes a
  "32-symbol alphabet"; it is 30 symbols, so a 12-character code carries 58.9
  bits rather than 60. The conclusion stands — the codes are long enough — but
  the arithmetic in the docstring should say what the code actually does.

Everything else this slice deferred is now closed: the Alembic migration
(`c42f47ccac47`) creates both tables, the temporary `mfa_tables` test fixture is
gone, and the recovery-code count plus the four previously undefined MFA
schemas are ratified in
[ADR-017](adr/ADR-017-login-gated-admin-mfa.md).
