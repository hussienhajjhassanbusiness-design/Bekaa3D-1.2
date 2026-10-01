# FVS-004 — Password Reset Flow — Implementation Plan

> **For agentic workers:** One task at a time, TDD where marked, full verification before every commit, one local commit per task, STOP after each batch — mirrors FVS-001/002/003's workflow. This plan is deliberately shorter than FVS-003's — see the Workflow Change note in the session that created it.

**Goal:** A customer who forgot their password can request a reset link (enumeration-safe), follow it to `/reset-password`, set a new password, and is told — correctly — that this logged them out everywhere and they must sign in again. No invented backend contract; only what's actually confirmed is built.

**Architecture:** Reuse `Form`/`TextField`/`PasswordField`/`Alert`/`Button` unchanged. Reuse `apiClient`, `ApiError`, the existing `AUTH_SESSION_QUERY_KEY` clear pattern from `useLogout.ts`. No new form primitives, no new runtime dependency.

**Tech Stack:** Next.js App Router, TanStack Query v5, React Hook Form + Zod (all existing).

**Spec:** `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-004 entry and `vertical-slice-plan.md`'s VS-004 entry are the governing specs. Neither carries field-level JSON contract detail (see §1 below) — this plan's own Contract Confidence Table (§2) governs what can actually be built.

---

## 0. Repository / Contract Audit (Part A)

Read in full for this plan: `vertical-slice-plan.md` (VS-004, lines 97-112), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-004 entry, lines 129-149), `FVS-003-IMPLEMENTATION-PLAN.md` (for the already-confirmed cross-cutting CSRF/refresh-exclusion facts that already name password-reset endpoints explicitly), `docs/frontend-setup.md`. Searched the repository for any OpenAPI spec, contract file, or additional VS-004 documentation beyond these two plan documents — **none exists**. No field-level JSON shape, exact status code, or RFC 9457 `code` value for either password-reset endpoint appears anywhere in this repository.

**What the repository actually confirms (verbatim-sourced):**
- `vertical-slice-plan.md` VS-004: model `password_reset_tokens`; schemas named `PasswordResetRequest`/`PasswordResetConfirm` (names only, no fields); logic described as "**Enumeration-safe request**, hashed token, expiry/use validation, password replacement, **revoke all sessions**, outbox email, audit event"; endpoints `POST /api/v1/auth/password-reset/request`, `/confirm`.
- `FRONTEND-VERTICAL-SLICE-PLAN.md` FVS-004: routes `/forgot-password`, `/reset-password` (token query param); reuses FVS-002 form primitives; confirm step "distinguishes expired/used token from password-policy validation failure"; success state explicitly must say sessions were revoked everywhere, then redirect to `/login`.
- `FVS-003-IMPLEMENTATION-PLAN.md` §2 rows 31/35: password-reset endpoints are already confirmed, as a class, to be CSRF-exempt and excluded from the refresh-aware `authenticatedRequest` wrapper (anonymous auth endpoints, same bucket as login/logout/refresh/MFA).

**What is genuinely not specified anywhere:** every field name, every exact status code, every RFC 9457 `code` value, password policy for reset (vs. registration's), token format, rate limiting, and whether the confirm response itself clears cookies or merely revokes sessions server-side. None of this is guessed below (§2).

---

## 1. Already-Confirmed Auth Architecture (carried over from FVS-003, not reopened)

1. Password-reset endpoints are anonymous auth endpoints.
2. They do **not** use CSRF.
3. They must never be called through `authenticatedRequest` and must never trigger a silent refresh.
4. Canonical auth state is `["auth","session"]`, owned by TanStack Query / `AuthProvider` (`src/lib/auth/authSession.ts`'s `AUTH_SESSION_QUERY_KEY`).
5. Successful password reset globally revokes sessions (backend-side fact, confirmed by VS-004's own text).
6. Therefore, on a successful confirm, the frontend must transition `AUTH_SESSION_QUERY_KEY` to anonymous and clear any auth-scoped private cache (today: just that one key — same convention `useLogout.ts` already established).
7. `access_token`/`refresh_token` remain backend-managed httpOnly cookies; frontend never reads them.

No repository evidence contradicts any of these; none are reopened.

---

## 2. Contract Confidence Table

| # | Contract item | Status | Evidence | Frontend consequence |
|---|---|---|---|---|
| 1 | Request body fields | **NEEDS BACKEND CONFIRMATION** | No field-level schema anywhere | T02 cannot be written — exact body unknown (likely `{email}` by analogy to resend-verification, but analogy is not confirmation) |
| 2 | Request email normalization | **NEEDS BACKEND CONFIRMATION** | — | T02 blocked |
| 3 | Request success status/body | **NEEDS BACKEND CONFIRMATION** | — | T02 blocked |
| 4 | Request enumeration-safe behavior | **CONFIRMED** | `vertical-slice-plan.md` VS-004: "Enumeration-safe request" is stated backend logic, not a frontend guess | T02's UI must show one fixed success copy regardless of account existence — the *intent* is confirmed even though the exact body isn't |
| 5 | Request rate limiting / `Retry-After` | **NEEDS BACKEND CONFIRMATION** | No per-endpoint limit stated for this endpoint (unlike FVS-002's resend, which had confirmed numbers) | T02 blocked; `ApiError.retryAfterSeconds` plumbing already exists generically and would be reused as-is if confirmed, not rebuilt |
| 6 | Request validation failures / problem codes | **NEEDS BACKEND CONFIRMATION** | — | T02 blocked |
| 7 | Confirm body fields (token field name, password field name) | **NEEDS BACKEND CONFIRMATION** | — | T03 cannot be written |
| 8 | Confirm success status/body | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 9 | Confirm password policy | **NEEDS BACKEND CONFIRMATION** | Explicitly must **not** assume registration's 8–256 rule applies unchanged | T03 blocked — a reset-specific policy might differ |
| 10 | Invalid-token signal (status + code) | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 11 | Expired-token signal (status + code) | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 12 | Already-used-token signal (status + code) | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 13 | Confirm rate limiting | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 14 | Reset-link query parameter name | **CONFIRMED** | `FRONTEND-VERTICAL-SLICE-PLAN.md` FVS-004 routing: `/reset-password` (token query param) | Settled: `token` |
| 15 | Any other reset-link query parameter | **ASSUMED NONE** | No evidence of a second parameter anywhere | T01/T04 never look for one; nothing invented |
| 16 | Token format/length/alphabet | **FRONTEND ARCHITECTURE DECISION — opaque** | Explicit instruction + no backend evidence of any format | Treated as an opaque string everywhere; no regex/length/alphabet validation anywhere in this slice |
| 17 | Session revocation on successful confirm | **CONFIRMED** | `vertical-slice-plan.md` VS-004: "revoke all sessions" | T04 clears local auth state unconditionally after a successful confirm |
| 18 | Exact confirm response body re: revocation | **NEEDS BACKEND CONFIRMATION** | — | T04 does not parse the confirm body for revocation detail — clears state because the *endpoint succeeded*, not because a body field says so |
| 19 | Whether the confirm response itself clears cookies | **NEEDS BACKEND CONFIRMATION** | — | Not needed either way: T04's local clear + the existing `/me`-is-canonical architecture (FVS-003) already makes the next `/me` call the source of truth regardless |
| 20 | What a previously-authenticated tab sees next | **NEEDS BACKEND CONFIRMATION (exact status)**, but **ARCHITECTURALLY ALREADY HANDLED** | FVS-003's existing `authenticatedRequest`/bootstrap 401-handling already treats any `AUTH_REQUIRED` as "session gone" | No new code needed for this — existing FVS-003 mechanisms compose correctly once a real backend is reachable; nothing to build in this slice |
| 21 | Anonymous reset endpoints — no CSRF | **CONFIRMED** | `FVS-003-IMPLEMENTATION-PLAN.md` §2 row 31 | T02/T03 never pass `{csrf:true}` |
| 22 | No `authenticatedRequest` for reset endpoints | **CONFIRMED** | `FVS-003-IMPLEMENTATION-PLAN.md` §2 row 35 | T02/T03 call `apiClient` directly |
| 23 | No silent refresh triggered by reset endpoints | **CONFIRMED** | Same source | Enforced by construction (never imported) |

Nothing marked **NEEDS BACKEND CONFIRMATION** above is implemented in this batch. Nothing is silently converted to CONFIRMED.

---

## 3. Final Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Password-reset token extraction + URL sanitization (pure, contract-independent) | **CAN IMPLEMENT NOW** |
| T02 | `usePasswordResetRequest` mutation + `/forgot-password` page | **BLOCKED ON BACKEND CONTRACT** (rows 1–6) |
| T03 | `usePasswordResetConfirm` mutation + `/reset-password` page | **BLOCKED ON BACKEND CONTRACT** (rows 7–13) |
| T04 | Session-state clearing wiring on successful confirm | **BLOCKED ON BACKEND CONTRACT** (depends on T03 existing) |
| T05 | Deterministic E2E (request → confirm → forced re-login) | **BLOCKED ON BACKEND CONTRACT** (depends on T02–T04) |
| T06 | Documentation (auth architecture: reset revokes every session) | **BLOCKED ON BACKEND CONTRACT** (depends on T02–T04 being real; drafting against an unbuilt flow risks documenting speculation) |
| T07 | Real-backend acceptance (request → real outbox token → confirm → forced re-login against the real backend) | **BLOCKED ON BACKEND AVAILABILITY** (separate gate, mirrors FVS-001/002/003's own T14 pattern) |

7 tasks. No micro-tasks invented; integration tests are listed inside each implementing task (T02/T03/T04), not split out, matching FVS-003's own task-shape.

---

## 4. Optimized Batches

| Batch | Contents | Status |
|---|---|---|
| **Safe Batch 1** | T01 | **This session** |
| Batch 2 | T02, T03, T04 | Gate: backend answers §5 below |
| Batch 3 | T05, T06 | Gate: Batch 2 lands |
| Real backend acceptance | T07 | Gate: real backend reachable |

---

## 5. Backend Questions For Tomorrow (Part C — consolidated, nothing already answered by repository evidence)

**PASSWORD RESET REQUEST**
1. Exact JSON request body (confirm field name(s) — e.g. `email`?).
2. Success HTTP status and body (202 + `{message}` matching resend-verification's own shape, or something else?).
3. Any request-side validation beyond basic email shape, and its exact RFC 9457 `code`?
4. Is this endpoint rate-limited? If so, by what key (IP/email), and does it carry `Retry-After`?
5. Confirm the enumeration-safe behavior's exact mechanics (does it always return the same status/body regardless of account existence, matching resend-verification's pattern?).

**PASSWORD RESET CONFIRM**
6. Exact JSON request body — token field name, new-password field name.
7. Exact password policy for a reset password (same 8–256 rule as registration, or different?).
8. Success HTTP status and body.
9. Invalid-token status + exact `code`.
10. Expired-token status + exact `code` (same as invalid, or distinguishable?).
11. Already-used-token status + exact `code` (same as invalid/expired, or distinguishable?).
12. Is this endpoint rate-limited? Same questions as #4.

**TOKEN / LINK**
13. Token lifetime (how long is a reset link valid)?
14. One-time-use semantics — confirmed by VS-004's model name (`password_reset_tokens`, "expiry/use validation"), but: does re-requesting a reset invalidate a previously-issued, still-valid token?
15. Exact reset link the backend's outbox email actually generates (to confirm the `token` query-parameter name and `/reset-password` path match what the frontend expects).

**SESSION REVOCATION**
16. Does the confirm response body say anything about revocation, or is "all sessions revoked" purely a server-side side effect with no body signal?
17. Are auth cookies cleared via `Set-Cookie` on the confirm response itself, or only invalidated server-side (cookies remain present client-side but meaningless on next use)?
18. What does a previously-authenticated tab's next authenticated request actually receive (expected: `401 AUTH_REQUIRED`, consistent with the existing FVS-003 contract — confirm this isn't a different code).

**REAL TESTING**
19. Local `email_outbox` query shape for a password-reset email (template name, payload field names — likely mirrors `verification_email`'s `payload->>'token'`/`payload->>'verification_url'` pattern, but confirm the template name and field names for password reset specifically).
20. Supported way to prepare a disposable account with a real, already-verified login for this flow (reuse the same account-prep procedure FVS-003's real-backend session used, once attempted).

---

## 6. Task Detail

### FVS004-T01 — Password Reset Token Handling

**Status:** CAN IMPLEMENT NOW.
**Purpose:** The one contract-independent, security-sensitive piece this slice can build today — safe extraction of the opaque `token` query parameter, and safe removal of it from the visible URL after capture.
**Depends on:** None.
**Contract gate:** None — pure frontend logic; the token itself is treated as fully opaque (no format/length/alphabet assumption).
**Files:** `src/lib/auth/passwordResetToken.ts`, `passwordResetToken.test.ts`.
**Implementation actions:**
1. RED: write the 15-item test matrix (see session instructions) — exactly-one-non-empty-token accepted; missing/empty/multiple rejected (fail closed, return `null`); content returned byte-for-byte unchanged (no trim/lowercase/normalize beyond `URLSearchParams`'s own standard percent-decoding); sanitized-URL preserves pathname/other-query-params/hash while removing `token`; no browser storage touched; malformed input never throws.
2. GREEN: implement `extractResetToken(params: URLSearchParams): string | null` and `removeTokenFromUrl(url: string): string`.
**Do NOT:** invent a token length/alphabet/regex; trim/lowercase/normalize the token; write to any storage; log the token; implement `/reset-password` itself (that's T03, contract-blocked).
**Tests:** TDD required.
**Acceptance criteria:** All 15 matrix items pass; the sanitization helper never leaves the literal token value anywhere in its output.
**Verification:** `npm run test -- passwordResetToken`, then full suite.
**Skills/tools:** `superpowers:test-driven-development`.
**Commit message:** `feat: add password reset token extraction and URL sanitization`

### FVS004-T02 — Password Reset Request (`/forgot-password`)

**Status:** BLOCKED ON BACKEND CONTRACT (table rows 1–6).
**Purpose:** The enumeration-safe request mutation + page.
**Depends on:** None architecturally; execution blocked until §5's REQUEST questions are answered.
**Files (once unblocked):** `src/lib/auth/usePasswordResetRequest.ts` (+test), `src/app/forgot-password/page.tsx` (+test).
**Implementation actions (once unblocked):** Mirror `useResendVerification`/`verify-email/resend` page's own proven pattern exactly — one fixed enumeration-safe success copy regardless of backend response detail, safe generic failure copy for every other outcome, no invented rate-limit duration beyond a confirmed `retryAfterSeconds`.
**Do NOT:** invent the request body shape; assume resend-verification's exact contract carries over without confirmation.
**Tests:** TDD required once unblocked — enumeration-safe success (two different mocked underlying outcomes, identical rendered copy), rate-limited, network/timeout.
**Commit message:** `feat: add password reset request flow` (once unblocked).

### FVS004-T03 — Password Reset Confirm (`/reset-password`)

**Status:** BLOCKED ON BACKEND CONTRACT (table rows 7–13).
**Purpose:** The confirm mutation + page: capture token (T01), submit new password, map invalid/expired/used/policy failures to safe copy.
**Depends on:** T01 (token helper), T02's pattern (once it exists).
**Files (once unblocked):** `src/lib/auth/usePasswordResetConfirm.ts` (+test), `src/app/reset-password/page.tsx` (+test).
**Implementation actions (once unblocked):** On mount, extract token via T01's `extractResetToken`, strip it from the visible URL via `removeTokenFromUrl` immediately (no navigation/reload), hold it only in component state, send it once on submit. Map the backend's confirmed invalid/expired/used-token codes to distinct (or shared, if the backend doesn't distinguish — mirror whatever is actually confirmed) safe copy; map the confirmed password-policy failure to inline field feedback; success hands off to T04.
**Do NOT:** invent a token shape check beyond "non-empty" (T01 already enforces this); invent a password policy; keep the token in the URL after capture; persist it anywhere.
**Tests:** TDD required once unblocked.
**Commit message:** `feat: add password reset confirm flow` (once unblocked).

### FVS004-T04 — Session-State Clearing on Successful Reset

**Status:** BLOCKED ON BACKEND CONTRACT (depends on T03 existing to have a success event to hook).
**Purpose:** On a successful confirm, clear the canonical auth query and show the required "logged out everywhere, please sign in again" success copy before redirecting to `/login`.
**Depends on:** T03.
**Files (once unblocked):** Edits inside `src/app/reset-password/page.tsx`'s success handler; reuses `AUTH_SESSION_QUERY_KEY` from `src/lib/auth/authSession.ts` exactly as `useLogout.ts` already does (`queryClient.setQueryData(AUTH_SESSION_QUERY_KEY, null)`) — no new cache-clearing mechanism invented.
**Implementation actions (once unblocked):** Clear the auth query synchronously on confirm success (same convention as logout — no new private query exists to also clear, same as FVS-003's §13 convention). Render the required explicit copy. Navigate to `/login` (not auto-navigate instantly without the user reading the message — exact UX timing is this task's own call at execution time, not pre-decided here).
**Do NOT:** invent a second auth-state-clearing mechanism; silently auto-redirect before the "logged out everywhere" message is readable; route this through `authenticatedRequest`.
**Tests:** TDD required once unblocked — success clears `AUTH_SESSION_QUERY_KEY`, success copy is present and uses `role="status"`.
**Commit message:** `feat: clear auth state on password reset success` (once unblocked) — may be folded into T03's own commit if the two land together; this plan does not mandate a forced split if that reads more clearly at execution time.

### FVS004-T05 — Deterministic E2E

**Status:** BLOCKED ON BACKEND CONTRACT (depends on T02–T04).
**Purpose:** request → confirm with token → forced re-login, route-interception only, added to the existing `smoke` Playwright project.
**Files (once unblocked):** `e2e/password-reset.spec.ts` (or folded into `login-session.spec.ts` if that reads more clearly at execution time — this plan does not pre-decide which).
**Commit message:** `test: add password reset E2E coverage` (once unblocked).

### FVS004-T06 — Documentation

**Status:** BLOCKED ON BACKEND CONTRACT (depends on T02–T04 being real; see rationale in §3).
**Purpose:** Add the FVS-004 section to `docs/frontend-setup.md`, stating plainly that password reset revokes every session — so support/QA never treat the resulting forced-logout as a bug.
**Commit message:** `docs: document password reset architecture` (once unblocked).

### FVS004-T07 — Real Backend Acceptance

**Status:** BLOCKED ON BACKEND AVAILABILITY.
**Purpose:** Prove the real request→outbox→confirm→forced-relogin loop against a real backend, mirroring FVS-001/002/003's own T14/real-acceptance pattern.
**Depends on:** T05, a real backend reachable.
**Commit message:** `test: add real-backend password reset acceptance verification` (once unblocked).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`, plus `test:e2e` for route/page work) before every commit.
- One local commit per task.
- Never invent a backend contract item marked `NEEDS BACKEND CONFIRMATION` in §2.
- Reuse FVS-002/003 primitives/conventions unchanged; no new form primitives, no new runtime dependency.
- Default `npm run test:e2e` must remain fully backend-independent.
