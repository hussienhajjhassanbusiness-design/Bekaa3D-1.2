# Deep edge-case testing — VS-001 to VS-009

- **Branch:** `test/deep-vs001-vs009` (not pushed, not merged)
- **Date:** 2026-09-29
- **Scope:** VS-001…VS-009 in depth, plus cross-cutting checks. The audit's known VS-010 issues are locked in too.

## Summary

- **631 new tests**: 555 pass and 76 are strict `xfail`s.
  - Every xfail locks a confirmed bug, and each one was re-run with `--runxfail` to check it fails *for its stated reason*.
- **45 bugs (BUG-01 … BUG-45)**: 0 Critical, 3 High, 17 Medium, 25 Low. All 45 were confirmed by running them.
  - 23 are new; 22 are the audit's known issues, now locked in tests.
- **Final full suite: 1,176 passed, 78 xfailed, 0 failed, 0 errors, 0 skipped in 554 s.**
  - That's the 623 original tests plus 631 new ones.
  - The 78 xfails are 76 new plus the 2 pre-existing strict xfails in `test_admin_users_adversarial.py`.
- **Coverage (whole `src/app`):**
  - lines 95.2% → 96.5%
  - branches 82.6% → 85.5%
  - missed lines 169 → 123
- **No application code, migrations or docs were changed.** The only non-test edits:
  - `pyproject.toml`: dev dependencies added.
  - `.gitignore`: `.hypothesis/` added.
  - `tests/integration/test_health.py`: a test-isolation fix (see *Test-suite weaknesses*).

## How it was run

- **Isolation.**
  - Only throwaway testcontainers Postgres 16 and Redis 7 were used. The compose stack and `C:\My_project\Bekaa3D` were never touched.
  - There is no `.env` file. Throwaway secrets were generated and exported as environment variables.
  - A separate venv in the session scratchpad was used.
- **Dev dependencies added** to `[project.optional-dependencies].dev`:
  - `hypothesis>=6.100` (6.168.3 installed): property-based tests.
  - `time-machine>=2.14` (3.5.1 installed): frozen-clock time-boundary tests.
- **Coverage method.**
  - Every async DB call runs inside SQLAlchemy greenlets, so coverage **must** use `concurrency = greenlet,thread`.
  - Without that setting, the baseline undercounted at 87% and 368 missed lines. The corrected baseline is 94% and 169 missed lines.
  - The baseline came from a clean worktree of `main`; the after numbers came from this branch. Both used the same config.
  - Per-module tables: `reports/coverage-before.txt` and `reports/coverage-after.txt`.
- **Concurrency.** Races use one app instance driven with `httpx.ASGITransport`, each client with its own IP, fired with `asyncio.gather`. That means 10–50 transactions are genuinely in flight at once against real PostgreSQL.
- **Time boundaries** are pinned with `time_machine.travel(..., tick=False)` at expiry −1 s, exactly at expiry, and +1 s. Redis TTLs can't be frozen, so they're forced with `PEXPIRE`.
- **Timing oracles.**
  - Each timing test takes 12 alternating samples per branch on warmed connections.
  - A branch counts as distinguishable when the **interquartile ranges don't overlap**.
  - Timing tests skip themselves under a coverage or debug tracer, because tracing slows branches unevenly.
  - One oracle (BUG-05) also has a deterministic, machine-independent test that counts Argon2 operations.

## Per-slice results

Coverage for each slice aggregates the modules that slice owns. Test counts are new tests only.

### VS-001 — HTTP layer, error contract, health

- **Tests added:** 130. 121 passed, 9 xfail.
- **Coverage:** lines 100% → 100%, branches 100% → 100%.

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-40 | **High** | An unhandled DB error is logged with SQLAlchemy's `[parameters: …]`. A registration race writes the new account's **email and Argon2 password hash** into the log. | `test_deep_logs_and_leaks.py::test_a_server_error_never_logs_sql_parameters` | `core/database.py:16`, `api/errors.py:125` | `create_async_engine(..., hide_parameters=True)`, and log exception type and SQLSTATE rather than the full message. |
| BUG-13 | Low | A caller-supplied `X-Request-ID` is echoed and logged unbounded; 20,000 characters come straight back. | `test_deep_vs001_http_layer.py::test_a_hostile_request_id_is_not_echoed_verbatim` | `api/middleware.py:19` | Accept only `^[A-Za-z0-9._-]{1,128}$`; otherwise generate one. |
| BUG-14 | Low | `/health/ready` has no timeout. A Redis or Postgres that accepts but never answers hangs the probe instead of returning 503. | `…::test_readiness_answers_503_quickly_when_{redis,postgres}_hangs` | `api/health.py:38-53` | Wrap each probe in `asyncio.wait_for(…, 2)`; set a connect timeout on the engine and Redis client. |
| BUG-15 | Low | A Redis or Postgres outage surfaces as **500 INTERNAL_ERROR** on every endpoint, not 503. | `…::test_a_{redis,postgres}_outage_on_a_public_endpoint_is_a_503` | `api/errors.py:124`, `core/rate_limit.py:20` | Map connection errors (redis `ConnectionError`, `OperationalError`/`InterfaceError`) to 503 `SERVICE_UNAVAILABLE`. |
| BUG-20 | Low | `HEAD` returns 405 on every GET route, including `/health/*`. RFC 9110 §9.1 requires HEAD wherever GET is supported. | `…::test_head_is_answered_wherever_get_is` | FastAPI default (`main.py:31`) | Add `HEAD` to GET routes (`api_route(methods=["GET","HEAD"])`) or add a small HEAD middleware. |
| BUG-42 | Low | The API emits stable codes that aren't in the api-endpoints.md §5 catalogue (`METHOD_NOT_ALLOWED`, `SERVICE_UNAVAILABLE`, `INTERNAL_ERROR`). OpenAPI also omits most real error statuses (login 401/403/429, register 400/429, logout 403, MFA setup 409, refresh 401…). | `test_deep_contract.py::test_every_emitted_code_is_in_the_catalogue`, `::test_every_observed_status_is_documented_in_openapi` | `api/errors.py:17-22`, route `responses=` | Add the three codes to the catalogue; declare error responses on each route. |

**Attacked and held**
- Every wrong method on every non-admin route returns a 405 problem with `Allow`.
- Odd paths return a plain 404 problem: case changes, `//`, `%2e%2e`, `..%2f`, `%00`, a 16k-character path, `/api/v2`, `;jsessionid`.
- Request IDs are always generated when missing or empty, and are unique.
- Malformed bodies get the documented problem: empty, `{`, trailing comma, invalid UTF-8, `null`, `[]`, `"string"`, number, `{}`, `NaN`.
- A JSON body sent as a **form content type** (`text/plain`, urlencoded, multipart) is refused, so a cross-site form cannot drive a JSON endpoint.
- Duplicate JSON keys can't smuggle a field.
- A 5 MB body is refused in under 5 s.
- A DB-error 500 body leaks no SQL or driver text.
- Liveness stays up with both dependencies dead.
- Readiness and outage bodies leak no DSN or host.
- No CORS header is ever returned to a hostile `Origin`, including on preflight.

### VS-002 — Registration, verification, outbox, worker

- **Tests added:** 107 (93 registration + 14 outbox/limiter). 91 passed, 16 xfail.
- **Coverage:** lines 95.5% → 96.1%, branches 83.3% → 87.5%.

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-45 | **High** | **Register is a timing oracle.** Both branches hash, but only a *new* address then writes user, token, outbox and audit rows. Timings: new p25/p50/p75 133/146/158 ms vs existing 92/98/107 ms; the quartiles are disjoint. | `test_deep_vs002_registration.py::test_register_timing_does_not_reveal_existing_accounts` | `register_user.py:40-62` | Make the existing-account branches do equivalent DB work, or answer before the writes. |
| BUG-01 | Medium | Concurrent registrations of one new address: the losers' `UniqueViolationError` on `ix_users_email_live` escapes as **500**. 9 of 10 got 500, which also breaks the uniform 202. | `…::test_concurrent_registration_of_one_address_is_uniformly_202` | `identity/infrastructure/repositories.py:233-238` | Catch that constraint's IntegrityError and fall through to the "existing account" branch. |
| BUG-05 | Medium | **Resend-verification is a reverse timing oracle.** Silent branches burn one Argon2 hash (85/93/104 ms) but the issuing branch burns none (52/59/61 ms). A deterministic test counts Argon2 operations per branch: `[1, 0, 1]`. | `…::test_resend_timing_does_not_reveal_which_branch_ran`, `…::test_resend_does_the_same_argon2_work_on_every_branch` | `resend_verification.py:31-44` | Burn the dummy hash on the issuing branch too, or make every branch do equal work. |
| BUG-07 | Medium | The verification token is read without a lock, so **one token is redeemed 3–5 times** when 20 redemptions run in parallel. That violates single-use (SEC-07) and writes duplicate audit rows. | `…::test_one_verification_token_redeemed_concurrently_succeeds_once` | `verify_email.py:21`, `repositories.py:398` | Read the token `FOR UPDATE`, as reset tokens already are. |
| BUG-09 | Medium | Both emails link to `GET …?token=`, but verify-email and reset-confirm are POST-only, so **following a link returns 405**. The token also sits in the URL and access logs. | `…::test_the_emailed_verification_link_is_followable`, `test_deep_vs004…::test_the_emailed_reset_link_is_followable` | `services/verification.py:34`, `services/password_reset.py:50-52` | Point links at a frontend route (token in the fragment), or add a GET landing page that POSTs. |
| BUG-19 | Medium | The purge has no role filter. An **unverified administrator is physically deleted** after the retention period. | `…::test_purge_never_deletes_an_administrator` | `identity/infrastructure/repositories.py:271-274` | Add `role = 'customer'` to the purge filter. |
| BUG-11 | Low | `429 RATE_LIMITED` from `core/rate_limit.py` has no `Retry-After` (the login throttle's does). | `test_deep_vs002_outbox_and_limits.py::test_every_429_carries_retry_after` | `core/rate_limit.py:26-39` | Add `Retry-After: <ttl>` (already scheduled for VS-011). |
| BUG-12 | Low | INCR and EXPIRE are separate calls. A failure between them leaves the counter with **TTL −1 (never expires)**, so that IP is eventually limited forever. | `…::test_a_blip_between_incr_and_expire_cannot_leave_an_immortal_counter` | `core/rate_limit.py:20-22` | Use a pipeline or Lua (`INCR` + `EXPIRE NX`), or `SET key 0 EX w NX` before `INCR`. |
| BUG-16 | Low | The `token` fields on verify-email and reset-confirm are unbounded; a 1 MB token is read and hashed, returning 400 rather than 422. | `…::test_a_megabyte_token_is_refused_at_the_schema` | `identity/api/schemas.py:23,188` | `Field(max_length=128)`. |
| BUG-17 | Low | The resend and reset-request cooldowns are check-then-insert. **10 simultaneous requests queue 10 emails** to the victim. | `…::test_concurrent_resends_issue_at_most_one_email`, `test_deep_vs004…::test_concurrent_reset_requests_queue_one_email` | `services/verification.py:40-46`, `services/password_reset.py:58-69` | Lock the user row (or use an advisory lock) around the cooldown check and insert. |
| BUG-18 | Low | Re-registering an unverified address after the cooldown queues a new verification email but writes **no audit row** (resend audits the same event). | `…::test_re_registration_that_reissues_mail_is_audited` | `register_user.py:57-62` | Audit `user.verification_resent` on that branch. |
| BUG-21 | Low | email-validator 2.3 no longer enforces RFC 5321's 64-octet local-part limit, so undeliverable addresses (65 and 200 characters) are registered. | `…::test_a_local_part_over_64_octets_is_refused` | `identity/api/schemas.py:13` (`EmailStr`) | Add an `AfterValidator` checking `len(local.encode()) <= 64`. |
| BUG-22 | Low | Redaction clears the payload but **not `last_error`**. A provider whose error text echoes the request (common with HTTP APIs) leaves the raw token in `email_outbox.last_error` permanently. Shown with a fake provider; the console adapter can't trigger it. | `…::test_a_provider_error_cannot_smuggle_the_raw_token_past_redaction` | `platform/domain/entities.py:48-50`, `jobs/outbox.py:160` | Scrub payload values from `last_error`, or store only the exception type. |
| BUG-23 | Low | SRS §23 names the job `purge_unverified_users`; the code and plan use `purge_unverified_accounts`. The SRS wins. | `…::test_every_srs_job_name_is_registered` | `jobs/registry.py:7,16` | Rename the job or amend the SRS. |

BUG-06 (Argon2 blocking the event loop) also affects registration; it's listed under VS-003.

**Attacked and held**
- **Email inputs:** 26 invalid shapes return 422 and create no row: null, bool, array, NUL, bell, zero-width, RTL override, newline, `\r\nBcc:` header injection, SQL quote, 10k characters, and others.
- **Passwords:** 7/8/256/257-character boundaries, 1 MB, number, array, bool, emoji, 256 emoji (1 KiB), embedded NUL, RTL. Argon2 cost can't be amplified; the longest input took under 3 s.
- **Mass assignment:** `role`, `is_verified`, `email_verified_at`, `is_active`, `id`, `auth_epoch` and `password_hash` are all refused.
- **One mailbox, one account:** ASCII case, Unicode case, NFC vs NFD, IDN Unicode vs punycode and IDN case all map to **one** account. Surrounding whitespace too. Plus-addressing is a distinct account stored verbatim.
- **Enumeration (responses):** register responses are byte-identical for new, unverified and verified addresses; resend responses are identical for all four account states.
- **Enumeration (work):** register does equal Argon2 work on every branch.
- **Verification tokens:**
  - Expiry at −1 s → 204, exactly at expiry → 410, +1 s → 410.
  - A used token stays 400 after it expires.
  - The older token still works after a resend.
- **Resend cooldown:** 119/120/121 s boundaries exact.
- Concurrent registrations never create two rows.
- **Purge:**
  - The cutoff is exact (strict `<`).
  - Every FK is cascaded or nulled; nothing blocks the purge.
  - Two racing purges delete each account once.
- **Rate limit:**
  - Exactly 5 per hour, `RateLimit-Remaining` 4→0.
  - Spoofed `X-Forwarded-For`/`X-Real-IP` are ignored, and another IP is unaffected.
  - The window resets when the key expires.
  - A limited request does no work.
  - 20 parallel requests give exactly 5 successes.
- **Outbox:**
  - 2 and 6 concurrent workers deliver 40 messages **exactly once** (the audit's missing test).
  - A future-scheduled message isn't sent early.
  - Backoff is exactly 60/120/240/480 s, then `failed` at attempt 5 with no retry 30 days later; the payload is redacted on failure.
  - Oversized errors are truncated to 1000 characters.
  - Cron schedules are correct.

### VS-003 — Login, logout, sessions, CSRF

- **Tests added:** 72. 64 passed, 8 xfail.
- **Coverage:** lines 97.6% → 99.1%, branches 92.9% → 92.9%.

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-06 | Medium | **Argon2 runs synchronously on the event loop.** Every login or register hash freezes the whole worker for about one hash; the event loop froze for 151 ms with 4 logins. | `test_deep_vs003_sessions.py::test_password_hashing_does_not_block_the_event_loop` | `password_hasher.py:12-17`; callers `login.py:74,82`, `register_user.py:39` | `await asyncio.to_thread(...)` (argon2-cffi releases the GIL). |
| BUG-25 | Medium | **The throttle is check-then-record.** 20 simultaneous wrong guesses were **all** checked against the password, and none was locked out. (The coarse 20 per hour per IP limit still applies.) | `…::test_parallel_guesses_cannot_outrun_the_lockout` | `login_throttle.py:49-75` | `INCR` first, then decide from the returned value. |
| BUG-26 | Medium | Logout needs a live access token. Once it has expired (15 min idle), `POST /logout` returns 401, the **httpOnly cookies are not cleared, and the 30-day refresh session stays alive**; refresh after "logout" returns 204. | `…::test_logout_after_the_access_token_expired_still_ends_the_session` | `identity/api/auth.py:241-257` | Let logout authenticate via the refresh cookie (plus CSRF) and always clear cookies. |
| BUG-24 | Low | Passwords aren't Unicode-normalised. A password set as NFC is refused when typed as NFD (macOS input). | `…::test_a_password_matches_in_any_unicode_normalisation_form` | `password_hasher.py:12-20` | NFKC-normalise before hashing and verifying (NIST 800-63B). Needs a rehash path for existing hashes. |
| BUG-27 | Low (accepted trade-off) | An access token keeps working ≤ 15 min after logout; only the account-wide epoch is checked (ADR-006/018). | `…::test_an_access_token_is_refused_after_logout` | `identity/api/dependencies.py:59-77` | Accept and document it, or check `sessions.revoked_at` on sensitive routes. |
| BUG-28 | Low | `jwt.decode` doesn't require `exp` (or `iat`/`sub`/`sid`). A correctly signed token without `exp` never expires. Needs the signing key (defence in depth). | `…::test_a_signed_token_without_exp_is_refused` | `session_tokens.py:100` | `options={"require": ["exp", "iat", "sub", "sid", "typ"]}`. |
| BUG-43 | Low | A signed token whose `sub`/`sid` is a JSON number makes `UUID()` raise `AttributeError`, which the decoders don't catch, so the request 500s. Needs the signing key. | `test_deep_properties.py::test_signed_but_malformed_claims_only_ever_raise_invalid_session` | `session_tokens.py:138-139,146` | Also catch `AttributeError`/`TypeError`, or check the type first. |
| BUG-44 | Low | A non-ASCII `X-CSRF-Token` makes `secrets.compare_digest` raise `TypeError`, so **every CSRF-protected route returns 500**, not 403. Found by Hypothesis, confirmed over HTTP. | `test_deep_vs003_sessions.py::test_a_non_ascii_csrf_header_is_a_403_not_a_500`, `test_deep_properties.py::test_only_the_exact_csrf_token_verifies` | `core/security.py:26-29` | Compare `.encode()`d bytes, or return False for non-ASCII input. |

**Attacked and held**
- **Login input matrix** (11 shapes). An empty password is 401, not 422, as intended.
- **Email and password handling:**
  - Email is case-insensitive.
  - The password is case- and whitespace-sensitive.
  - A disabled account with a *wrong* password looks exactly like an unknown one.
  - Sessions store a salted 64-hex IP hash (never the raw IP) and truncate the user agent to 512 characters.
  - **Login timing** doesn't reveal existence (IQRs overlap).
- **Throttle:**
  - Exact per-attempt delays `[0,0,0,1,2,4,8,8,8]`, then the 10th attempt is 429 with `Retry-After: 900` **even with the right password**.
  - An unknown email locks out identically.
  - The lock is per (email, IP), case-insensitive, and doesn't lock the victim out from another IP or block other accounts.
  - Success clears the counter.
- **Cookies:**
  - Flags are correct per environment: `Secure` off only in `development`; `HttpOnly`/`SameSite=Lax`/paths/max-age correct.
  - The refresh cookie is never sent outside `/api/v1/auth`.
  - Logout expires all three cookies on their own paths.
- **Access tokens:**
  - 22 tamperings return 401: expired, wrong key, HS512, `alg: none`, truncated, extended signature, swapped payload, garbage, empty, `typ=refresh`, missing typ/sub/sid/role, unknown role, bad sub, unknown user, future/negative/string/bool/2^70 epoch.
  - The expiry boundary is exact (15 min −1 s → 200, exactly → 401).
  - A token with `iat` in the future is refused.
- **CSRF:** missing, empty, wrong, uppercased, padded, and attacker-chosen cookie+header all return 403 with the session intact. The token is bound to the session and survives refresh.
- **Refresh:**
  - Access and refresh tokens aren't interchangeable.
  - The expiry boundary is exact (30 d −1 s → 204, exactly → 401).
  - Refresh after logout is refused.
  - **20 parallel refreshes of one token give exactly 1 winner and 19 × 401.** The session is then revoked with `reuse_detected_at` set: no 500s and no deadlock.

### VS-004 — Password reset

- **Tests added:** 29. 25 passed, 4 xfail.
- **Coverage:** lines 98.5% → 100%, branches 91.7% → 100%.

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-04 | **High** | **Reset-request is a strong timing oracle.** An unknown address answers in 11/17/24 ms, a known one in 52/57/63 ms (token + outbox + audit writes), with no constant-work equaliser; the quartiles are disjoint. api-endpoints.md §5 forbids leaking existence through timing. | `test_deep_vs004_password_reset.py::test_reset_request_timing_does_not_reveal_whether_the_account_exists` | `request_password_reset.py:32-36` | Do equal work on every branch, or enqueue the known-branch work asynchronously and answer first. |
| BUG-02 | Medium | **Deadlock.** Confirm locks token → user, then UPDATEs the user's *other* tokens. Two tokens for one account confirmed together deadlock; the loser gets **500** (`DeadlockDetectedError`) in 3 of 3 runs. | `…::test_two_tokens_for_one_account_confirmed_together_never_500` | `confirm_password_reset.py:59,67,92`; `repositories.py:632` | Look the token up unlocked, lock the user, then lock all of that user's tokens in id order. |

BUG-09, BUG-16 and BUG-17 also cover reset; they're listed under VS-002.

**Attacked and held**
- Request input matrix.
- Byte-identical 202 for unknown, known, unverified, deactivated and in-cooldown addresses.
- Cooldown boundary exact at 119/120 s.
- Confirm:
  - password 7/8/256/257, null, number
  - extra fields → 422, with the token left **unspent**
  - expiry exact (−1 s → 204, exactly → 410)
  - an expired confirm changes nothing
- **A successful reset ends everything:**
  - the token can't be replayed
  - a spare token is burned
  - stale access and refresh tokens are 401 on **both** devices
  - the old password is refused and the new one works
  - exactly one live session remains afterwards
- A reset doesn't verify an unverified address or revive a disabled one.
- **One token confirmed 20× at once gives exactly `[204] + 19 × 400`**, and the epoch advances once.

### VS-005 — Admin boundary and MFA

- **Tests added:** 56. 49 passed, 7 xfail.
- **Coverage:** lines 94.5% → 94.8%, branches 87.1% → 87.1%.

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-08 | Medium | **Anonymous callers can map the admin surface**: real admin paths answer 401, imaginary ones 404. The `api/v1/admin.py` docstring claims otherwise. | `test_deep_vs005_admin_mfa.py::test_anonymous_callers_cannot_tell_real_admin_paths_from_imaginary_ones` | `api/v1/admin.py:14-25` | Decide the rule. Either 404 for anonymous callers too, or a catch-all admin route that runs the boundary so unknown paths also 401. |
| BUG-10 | Medium | A wrong method (including HEAD/OPTIONS) on **any** admin path answers 405 with `Allow` before the boundary runs, so a customer can enumerate every admin route (SEC-10). Scheduled for VS-011. | `…::test_a_customer_cannot_enumerate_admin_routes_with_wrong_methods` (and the existing xfail) | `api/v1/admin.py:25` | Catch-all per admin prefix, or a 405→404 override for non-admins. |
| BUG-29 | Medium | **Trailing-slash oracle.** `/api/v1/admin/settings/` answers **307** (redirect_slashes) while an imaginary path answers 404, for customers *and* anonymous callers. The VS-011 wrong-method fix won't cover it. | `…::test_a_trailing_slash_does_not_reveal_admin_routes[customer,anonymous]` | FastAPI `redirect_slashes` (`main.py:31`, `api/v1/router.py`) | `redirect_slashes=False` on the admin router, or 404 unknown admin paths before redirecting. |
| BUG-30 | Medium | **One MFA challenge buys many guesses.** `/mfa/verify` reads, then deletes, the challenge in two Redis calls; 10 parallel requests with one challenge got **9** second-factor checks. (The 10 per 15 min per IP limit still caps totals.) | `…::test_one_challenge_buys_exactly_one_guess_under_concurrency` | `identity/api/mfa.py:294-295`; `mfa_session.py:105-133` | `GETDEL` (atomic read and delete). |
| BUG-31 | Low | Parallel first-time `/mfa/setup` for one admin races on `UNIQUE(user_id)`; 2 of 3 rounds returned **500**. | `…::test_parallel_first_time_setups_never_500` | `mfa_setup.py:67-82` | Lock (`get_by_user_id_for_update`) or upsert. |
| BUG-32 | Low | Parallel recovery-code regeneration leaves **40 live codes** (4 sets) instead of 10. | `…::test_parallel_regenerations_leave_exactly_one_code_set` | `mfa_regenerate_recovery_codes.py:56-65` | Lock the credential row before delete-and-insert. |

**Attacked and held**
- **The authorisation matrix, driven from OpenAPI (every admin operation):**
  - anonymous → 401 everywhere
  - verified and unverified customers → the byte-identical imaginary-path 404 everywhere
  - admin without MFA → 401 `MFA_REQUIRED` everywhere
  - admin with MFA passes everywhere, with no 500s
  - a deactivated admin's live MFA session → 401 everywhere
  - a malformed UUID is hidden from customers
- **MFA inputs:**
  - Confirm code shapes all get documented errors: 5/11 characters, number, null, letters, zeros, **Arabic-Indic digits**, spaced, NUL.
  - A whitespace-padded valid code is accepted.
  - Setup material is well-formed and the secret is never stored in plain text.
  - Verify body shapes are refused, including smuggled `user_id` and both factors at once.
  - Hostile challenge IDs (`*`, key patterns, traversal, NUL, 128 characters) → 410.
- **TOTP:**
  - The drift window is exactly ±1 step (−2 → 401, −1/0/+1 → 204, +2 → 401).
  - A code is valid at both edges of its step.
  - The high-water mark refuses an older step.
- **Challenges:**
  - A challenge's TTL is 290–300 s and it dies on expiry and on deactivation.
  - One valid TOTP across 8 parallel challenges → exactly one 204.
  - One recovery code across 8 parallel challenges → exactly one 204.
- **Enrolment and regeneration:**
  - Parallel confirms → one 200 and five 409, leaving exactly 10 live codes.
  - Regeneration refusals: no CSRF → 403, wrong password → 401, MFA incomplete → 401, customer → 404.

### VS-006 — Current profile

- **Tests added:** 14. 14 passed, 0 xfail.
- **Coverage:** lines 100% → 100% (no branches).
- **Bugs:** none.

**Attacked and held**
- Every live account kind (unverified, verified, admin without MFA, admin with MFA) reads exactly the contract fields and its own ID.
- A live token stops working **immediately** when the account is deactivated, anonymised, soft-deleted or hard-deleted.
- Verification shows up without a new token.
- Query parameters (`id`, `user_id`, `email`) can't select someone else.
- There's no write path: PUT/PATCH/POST/DELETE → 405, and the role is unchanged.

### VS-007 — Settings

- **Tests added:** 83. 74 passed, 9 xfail.
- **Coverage:** lines 90.6% → 90.9%, branches 73.6% → 75.0%.

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-03 | Medium | **NUL reaches PostgreSQL → 500** instead of 422: string setting values, `?prefix=%00`, `?search=%00` (existing xfail), notification cursors, and (VS-010) category/material/colour names and admin cursors. | `test_deep_vs007_settings.py::test_a_nul_in_a_string_setting_is_setting_invalid`, `…::test_a_nul_prefix_is_a_client_error`, `test_deep_vs010_known_bugs.py::*`, `test_deep_properties.py::test_no_accepted_string_contains_nul` | `settings_registry.py:282`; `platform/api/settings.py:149`; `identity/api/admin_users.py:174`; `catalog/api/schemas.py:16`; `catalog/api/reference_data.py:128` | Reject `\x00` (and C0 controls) in every text validator and query parameter. VS-011 only covers query and path parameters. |
| BUG-33 | Low | The "not empty" rule uses `str.strip()`, so strings made only of invisible characters (ZWSP, ZWNJ/ZWJ, BOM, word joiner) are stored as a blank-looking setting. | `…::test_an_invisible_only_string_is_refused[4 cases]` | `settings_registry.py:285-288` | Strip `Cf`-category characters before the emptiness check. |
| BUG-34 | Low | The E.164 check uses `\d` without `re.ASCII`, so **Arabic-Indic and full-width digits** are accepted as the WhatsApp number. | `…::test_non_ascii_digits_are_not_e164`, `test_deep_properties.py::test_every_accepted_whatsapp_number_is_ascii` | `settings_registry.py:38` | `re.compile(r"^\+[1-9][0-9]{0,14}$")`, or add `re.ASCII`. |
| BUG-35 | Low | `audit_logs.created_at` is `now()`, the **transaction start** time. Under contention the audit log's time order contradicts the real order of changes (3 of 3 runs). VS-012's viewer will sort by it. | `…::test_the_audit_log_chronology_matches_the_order_of_changes` | `platform/infrastructure/models.py:79` (migration `42601a09ada6`) | Use `clock_timestamp()`, or add a monotonic sequence column for ordering. |

**Attacked and held**
- **Numeric keys:** all 7 accept exactly [min, max] (min−1 → 422, min → 200, max → 200, max+1 → 422).
- Bools, 1.0, 1.5, numeric strings, arrays, objects and ±10^30 → 422 `SETTING_INVALID`, never 500.
- **Money:** 13 shapes, including fractional cents, a bool amount, a lowercase or other currency, and extra keys.
- **Free text:** 10 shapes. HTML is stored verbatim; output encoding is the client's job under SEC-22.
- **E.164:** 9 ASCII shapes.
- The envelope is enforced.
- **Nine non-registry keys** (uppercase, trailing space, dash, 5000 characters, traversal, `%00`, suffix NUL, Cyrillic homoglyph) → 404 on both read and write.
- **List queries:** `%` and `_` match literally.
- **Public endpoint:** a change is public immediately; exactly the 5 allowlisted keys, never an internal value; widening query parameters are ignored.
- **20 parallel PATCHes leave a gapless causal audit chain: no lost update.**

### VS-008 — Notifications

- **Tests added:** 49. 45 passed, 4 xfail.
- **Coverage:** lines 99.0% → 99.0%, branches 100% → 100%.

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-36 | Low | A cursor timestamp whose UTC equivalent falls outside years 1–9999 (e.g. `0001-01-01T00:00+14:00`) passes the parser, then overflows in asyncpg's encoder → **500**. The same happens on admin users. | `test_deep_vs008_notifications.py::test_an_out_of_range_cursor_is_a_client_error[2]`, `test_deep_vs009…::test_an_out_of_range_cursor_is_a_client_error`, `test_deep_properties.py::test_every_accepted_cursor_time_is_representable_in_utc` | `engagement/api/notifications.py:64-92`; `identity/api/admin_users.py:79-107` | In `_parse_cursor`, try `created_at.astimezone(UTC)` and raise `ValueError` on `OverflowError`. |
| BUG-37 | Low | The write port `create_notification` accepts NUL strings (JSONB then rejects them with a DB error) and crashes with a raw `RecursionError` on a 5000-deep payload, instead of raising `InvalidNotificationPayloadError`. | `…::test_a_nul_in_a_payload_is_rejected_by_the_port`, `…::test_a_deeply_nested_payload_is_rejected_by_the_port`, `test_deep_properties.py::test_no_accepted_payload_contains_nul` | `engagement/domain/payload.py:29-70` | Reject `\x00` in any string; catch `RecursionError` in `validate_payload`. |

**Attacked and held**
- PATCH bodies: 8 shapes, including smuggled `read_at` and `user_id` → 422, with nothing changed.
- ID shapes, including nil and sequential guesses.
- **Another user's notification** is indistinguishable from a missing one, untouched and never listed.
- 13 list and cursor shapes → 422, including NUL, naive datetimes and 10k characters.
- Extreme but representable cursors → 200.
- **The write port rejects 11 invalid payloads before the DB:** > 16 KiB, empty/blank/numeric event, missing event, NaN, Inf, set, lone surrogate, int key, non-dict.
- Exactly 16 KiB is accepted.
- A notification rolls back with the caller's transaction.
- Every type round-trips, and a plain-string type is rejected.
- 20 parallel toggles leave a consistent state.
- The first-read timestamp survives 20 parallel marks.

### VS-009 — Admin user management

- **Tests added:** 24. 20 passed, 4 xfail.
- **Coverage:** lines 100% → 100%, branches 100% → 100%.

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-38 | Medium | **The last active administrator can deactivate themselves** (200). Nobody can then reach the admin surface; recovery needs DB access. Scheduled for VS-011. | `test_deep_vs009_admin_users.py::test_the_last_active_administrator_cannot_be_deactivated` | `set_user_active.py`; `identity/api/admin_users.py:244-252` | Count active admins under lock and return 409 when the target is the last one. |
| BUG-39 | Medium | api-endpoints.md 530 requires admin PII access to be "audited/redacted from logs". **Neither holds.** List, search and detail write no audit row, and **uvicorn's access log records every `?search=<email>`**, even for 401 responses. That was proven with a real uvicorn process. | `…::test_admin_reads_of_account_pii_are_audited`, `…::test_an_admin_email_search_never_reaches_the_server_log` | `identity/api/admin_users.py:169-220` (docstring 187-190); uvicorn access log | Audit PII reads, and filter query strings out of the access log (custom log config or `--no-access-log` plus own logging). |

BUG-03 (`?search=%00`), BUG-10 (wrong method) and BUG-36 (cursor overflow) also apply here.

**Attacked and held**
- PATCH body shapes, including smuggled `role`/`email`/`auth_epoch` → 422, with nothing changed.
- ID shapes for an admin.
- Search shapes (control character, RTL override, emoji, 254/255 characters, SQL, backslash).
- **Deactivation kills 5 devices at once**: `/me` and refresh return 401 on all five, and 0 live sessions remain.
- **20 parallel activate/deactivate toggles** keep the audit and the epoch in step: epoch equals the number of real deactivations, and every audit row is a real transition.

### Cross-cutting suites

| Suite | Tests | Passed | xfail | Bugs |
|---|---|---|---|---|
| `test_deep_db_constraints_and_migrations.py` | 17 | 17 | 0 | none |
| `test_deep_logs_and_leaks.py` | 6 | 5 | 1 | BUG-40 |
| `test_deep_contract.py` | 6 | 4 | 2 | BUG-42 |
| `unit/test_deep_architecture.py` | 13 | 11 | 2 | BUG-41 |
| `unit/test_deep_properties.py` (Hypothesis) | 21 | 15 | 6 | BUG-03, 34, 36, 37, 43, 44 |
| `catalog/test_deep_vs010_known_bugs.py` | 4 | 0 | 4 | BUG-03 |

| Bug | Sev | What happens | Reproduce | Location | Suggested fix |
|---|---|---|---|---|---|
| BUG-41 | Medium | The architecture rules are broken. Contexts import each other's **infrastructure**: Identity writes Platform's audit and outbox via `app.platform.infrastructure.repositories`; Platform and Catalog import `app.identity.infrastructure.session_tokens`. Application layers import infrastructure everywhere. | `unit/test_deep_architecture.py::test_no_context_imports_another_contexts_infrastructure`, `::test_the_application_layer_depends_on_the_domain_only` | `identity/api/auth.py:58`, `identity/api/mfa.py:66`, `identity/application/commands/*`, `platform/api/settings.py:24`, `catalog/api/reference_data.py:67` | Route audit writes through `AuditWriter`, add an outbox port, and expose claims via an Identity port. |

**Held**
- **Every DB constraint fires with the right SQLSTATE when violated directly:**
  - case-insensitive live-email uniqueness, released by soft delete
  - role, status, type and method enums
  - `NOT NULL`s
  - FKs
  - `token_version > 0`
  - `attempt_count >= 0`
  - unique token, refresh and recovery hashes (the latter across accounts)
  - one MFA credential per user
  - unique settings key
- **Schema-wide invariants:**
  - every timestamp is `timestamptz`
  - every PK is a UUID
  - every FK to `users` is CASCADE or SET NULL, so nothing blocks the purge
  - no float or numeric columns
- **Migrations:** every step goes down and up with data present; base → head with data; a partial round trip keeps data and re-added columns take their defaults.
- **Logs and responses:**
  - No password, raw token, TOTP secret, recovery code, JWT or CSRF value reaches the logs across register → verify → login → refresh → reset → MFA enrol → recovery login → regenerate → outbox dispatch. This test has a positive control.
  - Validation errors never echo the submitted password.
- **Contract:**
  - Every V1-relevant catalogue code is reachable.
  - Every error is RFC 9457 with a matching `request_id`.
  - Every 2xx body matches its OpenAPI schema.
- **Architecture:** domain layers are pure in all 9 contexts; notifications are written only through the port.
- **Properties:**
  - The token decoders never crash on arbitrary text.
  - The cursor parsers only raise `ValueError`, and cursors round-trip.
  - Recovery-code normalisation is idempotent and tolerant of retyping.
  - Numeric settings accept exactly their range and never a non-integer.
  - Strings are trimmed, bounded and idempotent; money is accepted only as in-range USD cents with exact keys.
  - Payloads are bounded.
  - Email normalisation is idempotent.
  - IP hashes are opaque and fixed-width.
  - Only the exact CSRF token verifies (apart from BUG-44).
  - The TOTP verifier never raises.
  - The throttle curve is monotone and capped.

## Master bug table (by severity)

| Bug | Sev | Slice | Summary | New / known from audit |
|---|---|---|---|---|
| BUG-04 | High | VS-004 | Reset-request timing oracle (≈3.5×, disjoint quartiles) | New |
| BUG-40 | High | VS-001 | Email + Argon2 password hash written to logs on DB errors | New |
| BUG-45 | High | VS-002 | Register timing oracle (new vs existing address, disjoint quartiles) | New |
| BUG-01 | Medium | VS-002 | Concurrent duplicate registration → 500 | Known |
| BUG-02 | Medium | VS-004 | Two reset tokens for one account deadlock → 500 | Known |
| BUG-03 | Medium | VS-007/009/010 | NUL in body, query or cursor text → 500 | Known (extended) |
| BUG-05 | Medium | VS-002 | Resend reverse timing oracle; Argon2 work `[1,0,1]` | New |
| BUG-06 | Medium | VS-003 | Argon2 blocks the event loop (~150 ms freezes) | New |
| BUG-07 | Medium | VS-002 | Verification token redeemed 3–5× under concurrency | New |
| BUG-08 | Medium | VS-005 | Anonymous admin-route oracle (401 vs 404) | Known |
| BUG-09 | Medium | VS-002/004 | Emailed verify/reset links return 405 | Known |
| BUG-10 | Medium | VS-005/009 | Wrong-method 405 admin-route oracle | Known (VS-011) |
| BUG-19 | Medium | VS-002 | Purge deletes unverified administrators | Known |
| BUG-25 | Medium | VS-003 | Parallel guesses bypass the login lockout | Known |
| BUG-26 | Medium | VS-003 | Logout after access expiry leaves the session alive | New |
| BUG-29 | Medium | VS-005 | Trailing-slash 307 admin-route oracle | New |
| BUG-30 | Medium | VS-005 | One MFA challenge buys many guesses | Known |
| BUG-38 | Medium | VS-009 | Last active admin can be deactivated | Known (VS-011) |
| BUG-39 | Medium | VS-009 | Admin PII reads not audited; search emails in access log | Known |
| BUG-41 | Medium | cross | Cross-context infrastructure imports; application→infrastructure | Known |
| BUG-11 | Low | VS-002 | 429 lacks `Retry-After` | Known (VS-011) |
| BUG-12 | Low | VS-002 | Rate-limit counter can become immortal | Known |
| BUG-13 | Low | VS-001 | `X-Request-ID` unbounded echo | Known |
| BUG-14 | Low | VS-001 | Readiness hangs on a hung dependency | Known |
| BUG-15 | Low | VS-001 | Dependency outage → 500 not 503 | New |
| BUG-16 | Low | VS-002/004 | Token fields unbounded | Known |
| BUG-17 | Low | VS-002/004 | Cooldown races → mail bombing | New |
| BUG-18 | Low | VS-002 | Re-registration reissue not audited | Known |
| BUG-20 | Low | VS-001 | HEAD unsupported | New |
| BUG-21 | Low | VS-002 | Local part > 64 octets accepted | New |
| BUG-22 | Low | VS-002 | `last_error` can retain the raw token | New |
| BUG-23 | Low | VS-002 | Job name differs from SRS §23 | Known |
| BUG-24 | Low | VS-003 | Passwords not Unicode-normalised | New |
| BUG-27 | Low | VS-003 | Access token valid ≤ 15 min after logout (accepted trade-off) | Known |
| BUG-28 | Low | VS-003 | `exp` not a required claim | New |
| BUG-31 | Low | VS-005 | Parallel MFA setup → 500 | Known (suspected, now confirmed) |
| BUG-32 | Low | VS-005 | Parallel regeneration → 40 live codes | Known (suspected, now confirmed) |
| BUG-33 | Low | VS-007 | Invisible-only strings accepted | New |
| BUG-34 | Low | VS-007 | Unicode digits pass E.164 | New |
| BUG-35 | Low | VS-007 | Audit chronology is transaction-start time | New |
| BUG-36 | Low | VS-008/009 | Cursor time overflow → 500 | New |
| BUG-37 | Low | VS-008 | Notification port leaks NUL / RecursionError | New |
| BUG-42 | Low | VS-001 | Error catalogue and OpenAPI incomplete | New |
| BUG-43 | Low | VS-003 | Malformed signed claims → AttributeError | New |
| BUG-44 | Low | VS-003 | Non-ASCII CSRF header → 500 | New |

**Audit items not tied to a bug here.** These were all doc-only: stale comments at `auth.py:409-411` and `confirm_password_reset.py:29`, the recovery-code entropy figure, and the "VS-011 owns products" pointers. None is testable, so none became a test.

## Test-suite weaknesses found (not application bugs)

1. **`test_health.py` deleted `REDIS_URL`**, so without a `.env` file every later test that built `Settings` failed. **Fixed on this branch** by using `monkeypatch.setenv`. This fix is what makes the suite green without a `.env`.
2. **`caplog`-based log assertions are vacuous.**
   - `configure_logging()` runs at every app start and *replaces* the root handlers, which removes caplog's handler; a probe confirmed caplog captures **0 records** afterwards.
   - `test_mfa_secret_hygiene.py::test_no_secret_or_recovery_code_reaches_the_logs` therefore **cannot fail**.
   - Not modified here. The new all-flows leak test covers the same secrets with a working capture and a positive control.
3. **Migrations mute the app's loggers.**
   - `migrations/env.py` calls `logging.config.fileConfig()` (default `disable_existing_loggers=True`).
   - After any in-process migration test, every `app.*` logger is disabled for the rest of the session.
   - This briefly made BUG-40 look fixed during this run. The new suite re-enables loggers for its own tests.
4. **Coverage needs `concurrency = greenlet,thread`.** Without it, reports undercount by about 200 lines (87% vs a true 94%).
5. From the audit: CI type-checks `src` only; `tests/` has 9 pre-existing mypy errors.

## What could not be tested, and why

- **Security headers (CSP, HSTS; SEC-23)** belong to nginx (VS-020), which doesn't exist yet.
- **Behaviour behind a reverse proxy.** The limiters and the throttle key on the socket IP, and a spoofed `X-Forwarded-For` is correctly ignored. Once nginx sits in front, every client may share one IP and one bucket. That's **suspected, not confirmed**, because there's no proxy to test with.
- **Real email providers.** Only the console adapter exists, so BUG-22 is demonstrated with a fake provider whose error echoes the request.
- **Slow (not hung, not dead) dependencies**, e.g. with latency injection. Only hung and dead dependencies were tested. Worker jobs that exceed arq's job timeout weren't tested either.
- **OS-level worker kills mid-job.** The existing suite covers the transactional outcome; no real process was killed.
- **Wire-level malformed HTTP** (raw invalid bytes in request lines or headers, oversized headers, uvicorn/h11 limits). The in-process transports normalise these. A non-ASCII header value was sent as bytes for BUG-44.
- **Remaining uncovered lines (123):** mostly defensive "row vanished between two reads" branches that need fault injection *inside* a transaction; `SettingsReader.get_int/get_bool/updated_by`, which have no consumer yet; and the worker's process entrypoint.
- **Load and throughput NFR targets** were not measured. BUG-06 shows the Argon2 limit qualitatively.
- **Timing tests are machine-sensitive.**
  - They were stable across repeated runs here, but CI hardware may shift the gaps. BUG-04's gap is large; BUG-05 and BUG-45 are narrower.
  - They skip under coverage.
  - BUG-05 also has a deterministic twin.
- **Hypothesis depth** is bounded to 300 derandomised examples per property.

## Full-suite result (final)

- **Without coverage (authoritative):** **1,176 passed, 78 xfailed, 0 failed, 0 errors, 0 skipped**, 554 s.
- **With coverage:** 1,175 passed, 4 skipped (the timing tests, which correctly skip under a tracer), 75 xfailed, 0 failed, 798 s. Totals: 95% lines (123 missed of 3,549), 53 partial branches.
- **Lint and types:** `ruff check .`, `ruff format --check .` and `mypy src` are clean.
- **Nothing is `failed` other than the strict xfails that lock real bugs.**

### Correction made during this run

Register timing was first judged "held" using a ratio of medians (1.46, just under a 1.5 bound). A 20-sample re-measurement showed disjoint quartiles, so it's a real oracle, now **BUG-45**. Every timing test was then switched to the interquartile-overlap criterion.
