# FVS-006 — Customer Account Shell & Profile — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per task, STOP before real-backend acceptance. Low-risk slice — kept to one working session, not split into artificial micro-batches, unlike FVS-004/005's contract-gated plans.

**Goal:** A logged-in customer sees an account shell (nav + content region) and a read-only profile (email, verification status). `/account` redirects to `/account/profile`. No edit form — VS-006 is deliberately read-only.

**Architecture:** Reuse FVS-003's `AuthProvider`/`ProtectedRoute`/canonical `["auth","session"]` query unchanged in spirit (one fix applied — see T01). Reuse `Alert`/`Button`/`LoadingSpinner`. No new state store, no second `/me` fetch, no `CustomerProtectedRoute`.

**Spec:** `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-006 entry and `vertical-slice-plan.md`'s VS-006 entry. Unlike FVS-004/005, the core contract (`GET /api/v1/me`) is already fully confirmed by FVS-003's own BATCH 3A contract sync — this plan does not reopen it.

---

## 0. Repository / Contract Audit (Part A)

Read: `vertical-slice-plan.md` (VS-006), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-006 entry), `FVS-003-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/lib/auth/AuthProvider.tsx`, `authSession.ts`, `authenticatedRequest.ts`, `src/components/auth/ProtectedRoute.tsx`, `src/components/layout/` (`AppLayout.tsx`, `Header.tsx`), `src/app/layout.tsx`, `src/app/not-found.tsx`, `src/app/login/`, `src/app/verify-email/resend/`, `playwright.config.ts`, `src/app/globals.css` (breakpoint tokens). Searched for any existing `/account`, `ProfileCard`, `AccountLayout`, `useAuthSession`, `authQueryKey.ts` — **none exist**; this slice starts from nothing.

**Confirmed, not reopened (FVS-003 §2 row 41, BATCH 3A):** `GET /api/v1/me` → `200 {id,email,role,email_verified,email_verified_at,created_at}`; `401 AUTH_REQUIRED` on anonymous/expired access; "account-active state rechecked server-side on every call" (this exact phrase is the evidence for §2 row 4 below).

**Found during this audit — a real cross-slice defect (not cosmetic, fixed as T01):** `bootstrapAuthSession()` (`authSession.ts`) caught *every* non-`AUTH_REQUIRED` failure — including `network`/`timeout`/`parse`/`5xx` — and resolved anonymous (`null`). Since the query never rejected, `AuthProvider` had no way to distinguish "confirmed logged out" from "the server/network just broke for a second." A customer with a perfectly valid session hitting a transient failure would be silently treated as anonymous and bounced to `/login` by `ProtectedRoute` — exactly the scenario FVS-006's own spec's UX-states line ("error state (retry button) if `/me` fails after a session is otherwise considered valid") requires NOT happen. Fixed minimally (§2 row 4, T01 detail below) before building anything that depends on it.

**Existing landmark structure (why the content region can't be a second `<main>`):** `src/components/layout/AppLayout.tsx` already renders `<main id="main-content" tabIndex={-1}>{children}</main>` at the root layout for every route. A second `<main>` inside `AccountLayout` would be an invalid nested-landmark structure. The account content region uses `<section aria-label="Account content">` instead.

---

## 1. Contract Confidence Table (concise — `/me` itself is not reopened)

| # | Item | Status | Evidence | Consequence |
|---|---|---|---|---|
| 1 | `/me` response shape, 401 behavior | **CONFIRMED (FVS-003 BATCH 3A)** | §2 row 41 of that plan | Reused as-is via `getAuthSessionQueryOptions()`/`AUTH_SESSION_QUERY_KEY` |
| 2 | Canonical query reuse (no second `/me` fetch) | **CONFIRMED by this audit** | `AuthProvider` already mounts the one `useQuery(getAuthSessionQueryOptions())`; `useAuth()` is the one place to read it | Profile reads `useAuth().user` directly — no new hook needed |
| 3 | A literal `account_state`/`status`/`enabled` field on `/me` | **DOES NOT EXIST** | Confirmed shape (row 1) has no such field; `vertical-slice-plan.md`'s "verification/account state" and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s "account state" are both pre-contract-sync prose, never updated with the real field names | Never fabricate `user.accountState`/`status:"active"` |
| 4 | Is a successful `/me` 200 a safe basis for a *derived* "Active" display | **FRONTEND ARCHITECTURE DECISION, evidence-based** | FVS-003's own confirmed row 41 text: "account-active state **rechecked server-side on every call**" — a 200 response could not have been returned for an inactive account under that confirmed behavior | ProfileCard may show a derived "Account status: Active" line, **explicitly commented as derived, never as a field read from the response** |
| 5 | Unverified-account banner trigger/destination | **CONFIRMED** | `email_verified: false` (confirmed field) → banner linking to `/verify-email/resend` (confirmed existing FVS-002 route) | Built exactly as specified |
| 6 | Available account-nav destinations today | **CONFIRMED — Profile only** | No other `/account/*` slice exists in this repository yet | `ACCOUNT_NAV_ITEMS` contains exactly one entry; no dead links |
| 7 | Real-backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** | Same standing gate as every prior slice | Not attempted this session (T07) |

Nothing here is guessed; row 4 is the one judgment call, made explicitly and recorded as derived rather than invented as a field.

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Canonical auth-query error-state fix (found during audit) | **CAN IMPLEMENT NOW — done this session** |
| T02 | `AccountLayout` + responsive nav registry | **CAN IMPLEMENT NOW** |
| T03 | `ProfileCard` + unverified banner | **CAN IMPLEMENT NOW** |
| T04 | `/account` + `/account/profile` routes | **CAN IMPLEMENT NOW** (depends on T02/T03) |
| T05 | Integration/accessibility/security review | **CAN IMPLEMENT NOW** (depends on T02–T04) |
| T06 | Deterministic E2E + docs | **CAN IMPLEMENT NOW** (depends on T05) |
| T07 | Real-backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

6 of 7 tasks fully buildable this session — the contract is already confirmed, unlike FVS-004/005.

---

## 3. Task Detail

### FVS006-T01 — Canonical Auth-Query Error-State Fix

**Status:** CAN IMPLEMENT NOW — **done this session, first, before anything else depended on it.**
**Purpose:** Close the real defect found during the audit (§0) before building a profile page whose entire reason for existing is to show a retryable error in exactly the scenario that defect broke.
**Files:** `src/lib/auth/authSession.ts` (+test), `src/lib/auth/AuthProvider.tsx` (+test), `src/components/auth/ProtectedRoute.tsx` (+test).
**What changed:**
1. `bootstrapAuthSession()` now re-throws a genuine transport/server failure (`network`/`timeout`/`parse`/any `5xx`) instead of resolving anonymous — a new `isUnexpectedTransportError()` helper draws this line. A definitive non-`AUTH_REQUIRED` 4xx (e.g. an unrecognized 401 code) still safely resolves anonymous, unchanged — a real 4xx is still a real "not authenticated" signal.
2. `AuthContextValue` gains exactly one new field, `isError: boolean` (`query.isError`, passed through) — no other field, no new hook, no second store.
3. `ProtectedRoute` no longer redirects when `isError` is true — it renders `children` (not a login redirect) so the page itself can show its own retry UI via `useAuth().isError`. The real security boundary remains each page's own API calls.
**Preserved, verified by the existing FVS-003 test suite plus new tests:** `401 AUTH_REQUIRED` → refresh → retry-once behavior; refresh failure → anonymous; no false "authenticated"; every pre-existing `authSession`/`AuthProvider`/`ProtectedRoute` test still passes.
**Tests:** TDD — RED confirmed against the actual pre-fix code (not assumed) for 5 new `authSession` cases, 2 new `AuthProvider` cases, 2 new `ProtectedRoute` cases.
**Commit message:** `fix: preserve unexpected /me failures as a retryable error state`.

### FVS006-T02 — Account Layout

**Status:** CAN IMPLEMENT NOW.
**Purpose:** The one reusable shell every later `/account/*` slice plugs into.
**Files:** `src/components/account/AccountLayout.tsx` (+test), `src/components/account/accountNavItems.ts`, `src/app/account/layout.tsx` (thin Next.js layout composing the component, same pattern `src/app/layout.tsx` already uses for `AppLayout`).
**Design:**
- `ACCOUNT_NAV_ITEMS: readonly {label: string; href: string}[]` in its own file, marked `#SHARED-ACCOUNT-NAVIGATION` — today exactly one entry (`{label: "Profile", href: "/account/profile"}`). Future slices add themselves here; no disabled/dead placeholder entries.
- `AccountLayout` wraps `children` in `ProtectedRoute` (reused, not duplicated), renders `<nav aria-label="Account">` (active item gets `aria-current="page"` via `usePathname()`) and a `<section aria-label="Account content">` (never a second `<main>` — see §0).
- Responsive via Tailwind's existing named breakpoints only (no JS viewport detection): mobile (default) — horizontal `overflow-x-auto` tab row; `tablet:` (≥768px, this project's own confirmed breakpoint name for 768px) — vertical sidebar beside the content region.
**Tests:** TDD — renders nav/content landmarks, exactly one `ACCOUNT_NAV_ITEMS`-driven link today, `aria-current="page"` on the active route, no second `<main>`, wraps `ProtectedRoute` (mocked `useAuth` proving loading/anonymous/authenticated/error states all behave as `ProtectedRoute` itself already guarantees).
**Commit message:** `feat: add customer account shell`.

### FVS006-T03 — Profile Card

**Status:** CAN IMPLEMENT NOW.
**Purpose:** The read-only profile display.
**Files:** `src/components/account/ProfileCard.tsx` (+test).
**Design:** Reads `useAuth()` directly (no new fetch). Displays email, a human-readable verified/unverified status, and the §1 row 4 derived "Active" status line (clearly commented as derived). Unverified (`emailVerified === false`) shows an `Alert` linking to `/verify-email/resend`; verified shows no banner. Loading: a simple skeleton matching the card's own shape (no library). Error (`useAuth().isError`): safe generic message + a Retry button that calls `queryClient.refetchQueries({queryKey: AUTH_SESSION_QUERY_KEY})` — the same canonical query, never a second fetch path. No editable field, no Save/Cancel/Edit control of any kind.
**Tests:** TDD — email rendered, verified/unverified copy, banner visibility both ways, resend link's exact `href`, loading skeleton, error state, retry re-triggers the canonical query (spy on `refetchQueries`, never a direct `apiClient.get`), no raw `ApiError` text, no editable inputs anywhere in the rendered output.
**Commit message:** `feat: add read-only customer profile card`.

### FVS006-T04 — Account Routes

**Status:** CAN IMPLEMENT NOW (depends on T02/T03).
**Purpose:** Wire the shell and card into real routes.
**Files:** `src/app/account/page.tsx` (redirect), `src/app/account/profile/page.tsx`.
**Design:** `/account` uses Next's `redirect()` (a static/server redirect, no client effect) to `/account/profile` — no auth check performed here; the destination's own `layout.tsx` (T02) owns protection via `ProtectedRoute`, so this file does nothing else. `/account/profile` renders `<ProfileCard/>` only — `AccountLayout` (mounted once via `src/app/account/layout.tsx`) already supplies the `ProtectedRoute` boundary, nav, and content landmark; the page itself does not wrap its own second `ProtectedRoute`.
**Tests:** Covered by T02/T03's own tests plus T06's E2E (redirect behavior, protection, `returnTo` preservation are genuinely browser-level concerns).
**Commit message:** `feat: add customer account profile routes`.

### FVS006-T05 — Integration / Accessibility / Security Review

**Status:** CAN IMPLEMENT NOW (depends on T02–T04).
**Purpose:** The whole-slice verification gate, same discipline as every prior slice's own T11-equivalent.
**Actions:** Walk `bekaa3d-frontend-slice-dod`; real-browser viewport/keyboard checks (320/375/768/1024/1440/1920); dispatch an independent review scoped to T01–T04's diff, focused on: duplicate `/me` requests, cache divergence, anonymous content flash, nested landmarks, mobile nav keyboard usability, dead links, invented profile fields, raw backend errors, banner visibility correctness, retry's actual target, redirect loops, `returnTo` preservation.
**Commit message:** `fix: address FVS-006 integration findings` (only if a fix is needed; no empty commit otherwise).

### FVS006-T06 — Deterministic E2E + Documentation

**Status:** CAN IMPLEMENT NOW (depends on T05).
**Purpose:** Permanent backend-independent coverage, and the docs update.
**Files:** `e2e/account-profile.spec.ts`; `docs/frontend-setup.md` (new FVS-006 section).
**Commit messages:** `test: add account profile E2E coverage`; `docs: document customer account shell and profile`.

### FVS006-T07 — Real Backend Acceptance

**Status:** BLOCKED ON BACKEND AVAILABILITY.
**Purpose:** Prove the real loop against a real backend, mirroring every prior slice's own final gate. Not attempted this session.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`, plus `test:e2e` for route/page work) before every commit.
- One local commit per task.
- No `CustomerProtectedRoute`, no second `/me` query, no new state library.
- No dead/placeholder account-nav links for unbuilt slices.
- No edit-profile form, no mutation of any kind — VS-006 is read-only.
- Default `npm run test:e2e` must remain fully backend-independent.
