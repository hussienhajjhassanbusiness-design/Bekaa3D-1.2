# FVS-005 — Admin Login & MFA — Implementation Plan

> **For agentic workers:** One task at a time, TDD where marked, full verification before every commit, one local commit per task, STOP after each batch — mirrors FVS-003/004's workflow. Kept deliberately shorter than FVS-003, same discipline as FVS-004.

**Goal:** An admin logs in through the existing FVS-003 mechanism, is challenged for TOTP, can enroll MFA the first time, can recover via a one-time code, and can regenerate recovery codes. Every `/admin/*` route is invisible to a non-admin (genuine 404, never a "forbidden" page). No invented backend contract; only `FVS005-T01` is built today.

**Architecture:** Reuse FVS-003's `useLogin()` as-is for `/admin/login` (it already discriminates the `200`/`202` shapes generically — no admin-specific login mutation is created). Reuse `Form`/`TextField`/`PasswordField`/`Alert`/`Button` unchanged. Layer admin-specific auth state over `AuthProvider` rather than duplicating it. No new runtime dependency without an explicit, confirmed justification (§6).

**Spec:** `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-005 entry and `docs/plans/backend/vertical-slice-plan.md`'s VS-005 entry are the governing specs — neither carries field-level JSON contract (§0). `docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md` already confirms the login→MFA handoff shape and the 401 code split; not reopened (§1).

---

## 0. Repository / Contract Audit (Part A)

Read for this plan: `docs/plans/backend/vertical-slice-plan.md` (VS-005, VS-009 and other `Depends on: VS-005` entries — none add MFA field detail), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-005 entry, lines 153-176), `docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md`, `docs/plans/frontend-slices/FVS-004-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/lib/api/`, `src/lib/auth/`, `src/components/auth/`, `src/components/forms/`, `src/components/feedback/`, `src/app/login/`, `src/app/not-found.tsx`, `src/app/layout.tsx`, `next.config.ts`, `playwright.config.ts`. Grepped the whole repository for `VS-005`/`MFA`/`TOTP`/`challenge_id`/`MFA_REQUIRED`/`recovery`/`admin`/`AdminProtectedRoute`/`setup_uri`/`otpauth`/`qr` — **no admin/MFA code exists anywhere yet**; every hit is either FVS-003's own already-built `401 MFA_REQUIRED`-passthrough plumbing or `useLogin.ts`'s existing `202` discrimination. No OpenAPI/contract file exists in this repository (same finding as FVS-004's audit).

**What the repository already confirms, verbatim-sourced:**
- `docs/plans/backend/vertical-slice-plan.md` VS-005: models `mfa_credentials`, `mfa_recovery_codes`; "TOTP enrollment/confirmation, challenge, recovery-code use/regeneration, admin dependency requiring MFA, **non-admin admin-route 404 behavior**, separate admin rate-limit policy"; endpoints exactly as listed in this plan's header, **plus** "protected `/api/v1/admin` boundary" — i.e., the backend's own admin API routes already 404 non-admins. This is the real security boundary; any frontend-side admin check is a UX nicety on top of it (`bekaa3d-api-contract`'s own rule: hiding is never authorization).
- `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` FVS-005: full capability/route/component list (reproduced in this session's own prompt); notably states admin state as "`isAdmin`, `mfaVerified`" — this is the **frontend plan's own aspirational design**, not a backend-confirmed field source (see §2's admin-auth-state rows).
- `docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md` §2 rows 5/5b/42: login's `202` body is `{challenge_id, expires_in_seconds}`, establishes no session, sets no cookies; `401 MFA_REQUIRED` is a distinct, non-refreshable RFC 9457 `code`, already excluded from `authenticatedRequest`/refresh by construction.
- `src/lib/auth/useLogin.ts`: already implements the full `200`-session-vs-`202`-challenge discrimination generically (not customer-specific) — `/admin/login` can reuse this hook unchanged; FVS-005 does not need a second login mutation.
- `/me`'s confirmed `SafeUser` shape already includes `role: string` (FVS-003 §2 row 41) — the field exists, but **no concrete value** (`"admin"` or otherwise) is confirmed anywhere, and FVS-003 deliberately shipped "no speculative authorization/role system." Whether `role` is even the intended admin signal (vs. a dedicated endpoint/response field) is unconfirmed.

**What is genuinely not specified anywhere:** every MFA endpoint's exact request/response field names and status/problem codes, challenge_id's security properties (storage-safety, URL-safety), TOTP/QR/otpauth format, recovery-code format and one-time semantics, rate limits, CSRF requirements per MFA endpoint, and the actual mechanism (and exact value) behind `isAdmin`/`mfaVerified`. None of this is guessed below.

---

## 1. Already-Confirmed Auth Facts (carried over from FVS-003, not reopened)

1. `POST /api/v1/auth/login` normal session → `200 SessionRead`; admin-with-MFA → `202 {challenge_id, expires_in_seconds}`, no cookies, not authenticated.
2. `401 MFA_REQUIRED` never triggers silent refresh; only `401 AUTH_REQUIRED` is refreshable.
3. Canonical identity is `GET /api/v1/me` → `SafeUser {id, email, role, emailVerified, emailVerifiedAt, createdAt}`.
4. `access_token`/`refresh_token` are never read by frontend code; `csrf_token`/`X-CSRF-Token` is the one confirmed CSRF mechanism — but which MFA endpoints require it is **not** assumed (§2).

---

## 2. Contract Confidence Table

| # | Contract item | Status | Evidence | Frontend consequence |
|---|---|---|---|---|
| 1 | Login `202` shape, `challenge_id` meaning | **CONFIRMED** | FVS-003 §2 row 5b | T02 reuses `useLogin()`'s existing discrimination unchanged |
| 2 | Is `challenge_id` secret/bearer-like | **NEEDS BACKEND CONFIRMATION** | Not stated anywhere — only that it identifies the challenge | T02 must treat it as sensitive by default until told otherwise (memory-only, never logged — same discipline `passwordResetToken.ts` already applies to reset tokens) |
| 3 | Challenge expiration | **CONFIRMED (value only)** | `expires_in_seconds` is part of the already-confirmed `202` body | T02 can display/use this once built; exact UX (countdown? silent re-request?) is T02's own design, not pre-decided |
| 4 | May `challenge_id` safely appear in a URL | **NEEDS BACKEND CONFIRMATION** | — | Default-deny: not placed in a URL unless confirmed safe |
| 5 | May `challenge_id` go in `sessionStorage` | **NEEDS BACKEND CONFIRMATION** | — | Default-deny: memory-only (component/hook state) until confirmed otherwise, consistent with reset-token handling |
| 6 | Page-reload-during-MFA behavior | **NEEDS BACKEND CONFIRMATION / ARCHITECTURE DECISION** | If `challenge_id` is memory-only, a reload loses it by construction | Likely answer: re-submit credentials (re-enter the login→challenge handoff) rather than attempt to resume a stale challenge — but not decided here without knowing challenge lifetime/replay rules |
| 7 | `/admin/login` vs `/login` — same backend endpoint? | **FRONTEND ARCHITECTURE DECISION, reasoned** | `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` FVS-005: "reusing FVS-003's login"; only one login endpoint exists anywhere in the contract | `/admin/login` is a distinct **route** (different page, different post-MFA destination) calling the **same** `useLogin()`/`POST /api/v1/auth/login` — not a second backend endpoint |
| 8 | `POST /api/v1/auth/mfa/verify` request body (challenge field, TOTP field, recovery-code field) | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 9 | Verify success status/body, cookies set | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 10 | Verify invalid-code / expired-challenge status+code | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 11 | Verify rate limit / `Retry-After` / lockout | **NEEDS BACKEND CONFIRMATION** | — | T03 blocked |
| 12 | Verify CSRF requirement | **NEEDS BACKEND CONFIRMATION** | Not assumed from login's own CSRF-exemption — verify is a *different* endpoint with different semantics (it may establish a session) | T03 blocked |
| 13 | `POST /api/v1/auth/mfa/setup` — who may call, required auth/challenge state, CSRF, response (secret/QR/otpauth) | **NEEDS BACKEND CONFIRMATION** | — | T04 blocked |
| 14 | `POST /api/v1/auth/mfa/setup/confirm` — body, response, recovery codes returned here? | **NEEDS BACKEND CONFIRMATION** | — | T04 blocked |
| 15 | TOTP digit length, QR format, otpauth URI, secret shape | **NEEDS BACKEND CONFIRMATION** | — | Nothing invented; §6's dependency policy stays unresolved until this lands |
| 16 | Does `/mfa/verify` accept a recovery code; discriminator field | **NEEDS BACKEND CONFIRMATION** | — | T05 blocked |
| 17 | Recovery-code one-time-use mechanics, forced re-enrollment after use | **NEEDS BACKEND CONFIRMATION** | `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own UX-states line says "forces re-enrollment prompt afterward per typical MFA UX — confirm backend supports this, else just log in" — the plan document itself flags this as unconfirmed | T05 must not build a forced-re-enrollment flow unless confirmed |
| 18 | `POST /api/v1/auth/mfa/recovery-codes/regenerate` — auth/MFA-session requirement, CSRF, body, response, old-codes-invalidated-immediately, re-retrievable? | **NEEDS BACKEND CONFIRMATION** | — | T05 blocked |
| 19 | Rate limits across all four MFA endpoints | **NEEDS BACKEND CONFIRMATION** | — | — |
| 20 | Source of `isAdmin` | **NEEDS BACKEND CONFIRMATION** | `role` exists on `SafeUser` (FVS-003 §2 row 41) but no value is confirmed, and whether `role` is even the intended signal (vs. a dedicated field/endpoint) is unconfirmed | T06 blocked — **not** silently derived from `role === "admin"` |
| 21 | Source of `mfaVerified`-for-this-session | **NEEDS BACKEND CONFIRMATION** | No `/me` field, login field, or session endpoint for this is confirmed anywhere | T06 blocked |
| 22 | Should `AuthProvider` itself gain `isAdmin`/`mfaVerified`, or should FVS-005 layer a separate derived `AdminAuth` abstraction | **ARCHITECTURE DECISION — deferred to T06** | `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own wording ("layered on top of FVS-003's AuthProvider") favors derivation over duplication, matching this plan's own preference, but the exact shape waits on rows 20/21 | Not decided now — deciding the shape before knowing the data source would be designing against a guess |
| 23 | Non-admin (any kind) → `/admin/*` frontend route: genuine 404 | **CONFIRMED** | `docs/plans/backend/vertical-slice-plan.md` VS-005: "non-admin admin-route 404 behavior"; `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` FVS-005: explicit, matches this session's own instruction verbatim | T06 renders the real 404 experience, never a distinct "forbidden" page |
| 24 | Does "non-admin" include a fully anonymous visitor (404, not redirect-to-admin-login) | **ASSUMED (reasoned from the spec's own literal scope, not guessed)** | The capability text says "non-admin users" without carving out anonymous as a special case — an anonymous visitor is trivially non-admin under that wording | T06's design leans 404-for-anonymous-too, but this is listed as a backend question (§4) to turn ASSUMED into CONFIRMED before building |
| 25 | Backend's own `/api/v1/admin` boundary independently 404s non-admin API calls | **CONFIRMED** | `docs/plans/backend/vertical-slice-plan.md` VS-005 endpoint line: "plus protected `/api/v1/admin` boundary" | The frontend's `AdminProtectedRoute` is UX-only; it is never the actual security boundary — matches `bekaa3d-api-contract`'s explicit hiding-is-not-authorization rule |
| 26 | Admin-with-MFA-incomplete-this-session → `/admin/*` | **CONFIRMED (behavior), NEEDS BACKEND CONFIRMATION (mfaVerified source, row 21)** | This session's own instruction + FVS-005's UX-states line | Must redirect to the verify step before any admin content renders — mechanism blocked on row 21 |

Nothing marked **NEEDS BACKEND CONFIRMATION** is implemented this batch. Nothing is silently converted to CONFIRMED.

---

## 3. Final Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | `RecoveryCodeList` presentational/security component | **CAN IMPLEMENT NOW** |
| T02 | `/admin/login` → MFA challenge handoff (reuses `useLogin()`) | **BLOCKED ON BACKEND CONTRACT** (§2 rows 2/4/5/6) + **BLOCKED ON ARCHITECTURE DECISION** (challenge_id storage, row 6) |
| T03 | MFA verification (`/admin/mfa/verify`) | **BLOCKED ON BACKEND CONTRACT** (rows 8–12) |
| T04 | First-time MFA setup wizard (`/admin/mfa/setup` + `/setup/confirm`) | **BLOCKED ON BACKEND CONTRACT** (rows 13–15) |
| T05 | Recovery-code verification + regeneration flow (wires T01) | **BLOCKED ON BACKEND CONTRACT** (rows 16–19) |
| T06 | Admin-auth derived state + `AdminProtectedRoute`/layout boundary | **BLOCKED ON ARCHITECTURE DECISION** (row 22) + **BLOCKED ON BACKEND CONTRACT** (rows 20/21); depends on T02–T05 for `mfaVerified` to be real, not fabricated |
| T07 | Integration/accessibility/security pass | **BLOCKED** (depends on T02–T06) |
| T08 | Deterministic E2E + docs | **BLOCKED** (depends on T07) |
| T09 | Real-backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

9 tasks, matching this session's own suggested shape — repository evidence didn't surface a reason to deviate from it.

---

## 4. Optimized Batches

| Batch | Contents | Status |
|---|---|---|
| **Safe Batch 1** | T01 | **This session** |
| Batch 2 | T02, T03, T04 | Gate: backend answers §6 below |
| Batch 3 | T05, T06 | Gate: Batch 2 lands + admin-signal questions answered |
| Batch 4 | T07, T08 | Gate: Batch 3 lands |
| Real backend acceptance | T09 | Gate: real backend reachable |

---

## 5. Non-Admin Route Hiding — Design Note (not yet built)

The backend's own `/api/v1/admin` boundary is the real enforcement (§2 row 25) — `AdminProtectedRoute` only prevents a non-admin from momentarily seeing admin UI *structure* before any real API call would have refused them anyway (same "hiding is not authorization" principle `ProtectedRoute`/`bekaa3d-api-contract` already apply). For the genuine-404 rendering itself: Next.js App Router's own `notFound()` function (`next/navigation`) is the idiomatic way to render the nearest `not-found.tsx` boundary from inside a conditional check, rather than duplicating `src/app/not-found.tsx`'s content into a second component — this is the leading implementation candidate for T06, not decided/built now.

---

## 6. Dependency Policy

No QR package installed. Whether the backend returns a QR image, an `otpauth://` URI (frontend would then need a QR-rendering library), or a secret string only (no QR need) is **unconfirmed** (§2 row 15). Any QR-related dependency requires an explicit, justified entry in this plan *after* that's answered — not before.

---

## 7. Backend Questions For Tomorrow (Part D — consolidated, nothing already answered by repository evidence)

**LOGIN → MFA HANDOFF**
1. Is `challenge_id` itself sensitive/bearer-like (i.e., does possessing it allow completing MFA without the original credentials), or is it merely a correlation ID?
2. Is it safe to carry `challenge_id` in a URL (e.g. a query param) if a multi-step flow needed it there, or must it stay request-body/memory-only?
3. Is it safe to hold `challenge_id` in `sessionStorage` to survive an accidental reload mid-MFA, or must it never persist beyond page memory?
4. What should happen if the user reloads mid-MFA-challenge — does the backend support resuming a challenge by ID, or must the frontend restart from login?
5. Confirm: is `/admin/login` simply a distinct frontend route calling the same `POST /api/v1/auth/login`, or does the backend expect a different request for admin logins?

**MFA VERIFY**
6. Exact request JSON for `POST /api/v1/auth/mfa/verify` — challenge field name, TOTP code field name, and (if supported) the recovery-code field/discriminator.
7. Success status and body — are cookies (access/refresh/csrf) set on this response, same as normal login's `200`?
8. Invalid-code status + exact RFC 9457 `code`.
9. Expired-challenge status + exact `code` (same as invalid, or distinguishable?).
10. Rate limiting / lockout behavior and whether `Retry-After` is present.
11. Does this endpoint require CSRF?

**MFA SETUP**
12. `POST /api/v1/auth/mfa/setup` — who may call it (any authenticated admin, or only one without MFA yet?), what auth/challenge state is required, CSRF requirement.
13. Success response — secret field name, and is a QR image returned directly, an `otpauth://` URI for the frontend to render, or secret-only (manual entry)?
14. `POST /api/v1/auth/mfa/setup/confirm` — request body (confirmation-code field name), success response, and does this response include recovery codes, or is regeneration the only way to get them?
15. Error/status codes for setup/confirm, and rate limiting.

**RECOVERY CODES**
16. Does `/mfa/verify` genuinely accept a recovery code as an alternative to TOTP? If so, the exact field/discriminator.
17. Are recovery codes strictly one-time-use? What happens to a session after one is accepted — does the backend force re-enrollment, or does the user simply finish logging in?
18. Can the frontend distinguish a TOTP-success from a recovery-code-success in the verify response (relevant only if re-enrollment prompting is confirmed to exist)?
19. `POST /api/v1/auth/mfa/recovery-codes/regenerate` — auth/current-session-MFA requirement, CSRF, request body (any confirmation required?), success response (returned codes field name), whether old codes are invalidated immediately, whether the same batch can be retrieved again if the user navigates away before saving them.
20. Rate limits on regeneration.

**ADMIN SESSION STATE**
21. What is the actual source of "this user is an admin" — a `role` value on `/me` (and if so, the exact string), a dedicated field, or something else entirely?
22. What is the actual source of "MFA is complete for this session" — a `/me` field, a response from `/mfa/verify`, a separate session-status endpoint, or something else?
23. Does a non-admin (including a fully anonymous visitor) hitting any `/admin/*` **frontend** route correspond to any backend-side signal the frontend should check, or is frontend-side 404 rendering purely a UX nicety with the real boundary entirely server-side (per VS-005's own `/api/v1/admin` 404 behavior)?

**REAL TESTING**
24. Supported way to prepare a disposable admin test account with MFA already enrolled (or the supported way to enroll one through this flow) for real E2E/acceptance testing.
25. Local `email_outbox` or equivalent, if any backend-side audit/notification artifact needs inspecting for MFA setup/recovery (VS-005 mentions "audit event" — confirm whether this is queryable the same way `email_outbox` was for FVS-002/004, or irrelevant to frontend testing).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`, plus `test:e2e` for route/page work) before every commit.
- One local commit per task.
- Never invent a backend contract item marked `NEEDS BACKEND CONFIRMATION` in §2.
- Reuse FVS-002/003/004 primitives/conventions unchanged; no new form primitives.
- No QR/clipboard/print dependency without an explicit, confirmed justification in this plan.
- Default `npm run test:e2e` must remain fully backend-independent.
