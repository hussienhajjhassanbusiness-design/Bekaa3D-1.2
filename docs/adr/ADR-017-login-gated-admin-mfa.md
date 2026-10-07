# ADR-017: Gate admin login on MFA rather than stepping up an existing session

**Status:** Accepted
**Date:** 2026-08-26
**Source basis:** api-endpoints.md §3, §8.1–8.2, §29.2; SRS SEC-04, SEC-10; ADR-006

## Context

`api-endpoints.md` describes admin MFA in two incompatible ways.

- Line 252 makes `POST /auth/login` return `202 MfaChallengeRead` for an administrator needing MFA, and line 270 makes `POST /auth/mfa/verify` the step that "Completes admin login; sets full auth + CSRF cookies". Together these gate the session on the second factor.
- Line 105 says an "admin without completed MFA → `401/403 MFA_REQUIRED` according to login/session state", which presumes a session already exists to be refused.

An implementation cannot satisfy both readings: if login withholds the session, there is no session for line 105 to challenge. VS-005 first built the line-105 reading (an authenticated admin session stepped up at the boundary). That left a real gap — between login and step-up an administrator held a genuine session that satisfied every `Authenticated` and `Verified Customer` route — so the conflict was escalated rather than settled in code.

## Decision

Implement the line 252/270 reading. An administrator with a **confirmed** MFA credential receives `202 MfaChallengeRead` from `POST /auth/login` and **no cookies of any kind**; `POST /auth/mfa/verify` validates the challenge plus a TOTP or recovery code and is the only place that creates the session, which is minted with the MFA claim already set.

Line 105 is retained for the one case that still needs it: an administrator whose enrollment is unconfirmed holds an ordinary session and is refused at the boundary with `401 MFA_REQUIRED`. The boundary never mints a challenge — the only source of one is login.

The integration into VS-003 is confined to two files. `Login` takes an injected `AdminMfaGate` and returns `MfaChallengeRequired` instead of creating a session; the login route turns that into the `202`. All MFA reasoning lives behind the gate, in VS-005-owned modules.

## Ratified alongside it: the schemas the contract never defined

`api-endpoints.md` names four MFA schemas in its endpoint tables but defines
fields for none of them — §29.2 lists only the three *request* schemas. A
search of the SRS, database design, vertical-slice plan and the other ADRs
found no field definitions anywhere. Rather than leave that ambiguity for
VS-007 and VS-009 to trip over, the V1 shapes are fixed here.

| Schema | Fields | Why exactly these |
|---|---|---|
| `MfaSetupRead` | `secret`, `otpauth_uri`, `issuer`, `account_name` | An authenticator cannot be provisioned without the secret, so this is the one response in the system that deliberately carries one. `otpauth_uri` is what a QR code encodes; `issuer`/`account_name` let a client render the pairing without parsing the URI. Returned once, never readable again. |
| `MfaRecoveryCodesRead` | `recovery_codes`, `generated_at` | Only hashes are stored, so this is the sole moment the plaintext exists. `generated_at` is retained: regeneration silently voids a previously printed sheet, and an administrator holding two sheets needs to tell which is live. |
| `MfaChallengeRead` | `challenge_id`, `expires_in_seconds` | The minimum a client needs to call `/auth/mfa/verify`. Deliberately carries no user id, email, role, or list of available factors — the caller has proven a password and nothing more, and this response must not confirm who the account belongs to or that it is an administrator. |
| `MfaRecoveryRegenerateRequest` | `current_password` | Mirrors `MfaSetupRequest`. Regeneration voids the codes the administrator is currently holding, so it is re-authenticated the same way enrollment is even though the caller is already Admin + MFA. |

No secret appears in any response other than `MfaSetupRead`, and none appears
in an audit row, log line, or error body.

**Recovery-code set size: ten.** No project document fixes this number — not
the SRS, not `database-design.md` §5.7, not `api-endpoints.md`. Ten is ratified
here as a V1 design decision on the usual grounds (enough that losing a few
does not mean losing access; few enough to print on one sheet), and it is the
common industry figure. `CODES_PER_SET` in
`identity/domain/recovery_codes.py` is the single source of truth; changing it
needs no schema change.

## Consequences

+ A correct admin password alone yields no session, no CSRF token, and no customer-level access — only a five-minute, single-use challenge
+ The session is born MFA-complete, so no window exists in which an admin session lacks the claim
+ `/auth/mfa/verify` has no session cookie and no CSRF header available, so the challenge id is its sole credential; the endpoint rate limit therefore carries real security weight rather than being defence in depth
- A merged slice (VS-003) was modified, against the general rule that slices are self-contained
- Administrators who enrol are challenged on their *next* login, not the current one
- `api-endpoints.md` line 105 now describes only the unconfirmed-enrollment case and should be narrowed to say so

## Alternatives rejected

- **Boundary step-up (the line-105 reading).** Leaves an MFA-incomplete admin holding a session with full customer-level access, and needs a second, session-bound path to an MFA-complete session.
- **Challenge every administrator, enrolled or not.** Deadlocks enrollment: `/auth/mfa/setup` and `/setup/confirm` need the session the challenge withholds.
- **Leaving the contract conflict unresolved.** Blocks VS-007 and VS-009, which depend on a settled admin boundary.

## Revisit when

Revisit only if requirements, scale, security, provider capabilities, or the deployment model materially change.
