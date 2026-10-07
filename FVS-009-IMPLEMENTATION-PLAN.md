# FVS-009 — Admin Customer Management — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per task, STOP after the safe frontend batch.

**Goal:** An admin searches/paginates a customer list, opens a customer detail view, and activates/deactivates an account — no other field is editable. `AdminTable`/`StatusBadge`/`ConfirmDialog` (the last reused, not recreated) become the shared primitives every later admin list slice (orders, offers, reviews, BYI, audit log) builds on.

**Architecture:** `AdminTable` is a generic, reusable, generics-typed table shell (rows/columns/row-key/loading/empty/search/pagination/row-actions) with **zero customer-specific knowledge**. `StatusBadge` is a small frontend-normalized active/deactivated union, isolated from whatever the real backend enum turns out to be. Browser URL state (`?q=&page=`) is a separate, pure concern from the backend's own query-parameter contract — the two are never assumed to be the same thing. `ConfirmDialog` (FVS-007) is reused as-is. No new runtime dependency.

**Spec:** `vertical-slice-plan.md`'s VS-009 entry and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-009 entry.

---

## 0. Repository / Contract Audit (Part A)

Read: `vertical-slice-plan.md` (VS-009), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-009 entry), `FVS-005-IMPLEMENTATION-PLAN.md`, `FVS-007-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/components/admin/` (only FVS-007's `settings/` subfolder exists — no `AdminTable`/`StatusBadge`/customer code anywhere), `src/components/feedback/ConfirmDialog.tsx` (+its test), `src/components/forms/`, `src/lib/api/`, `src/lib/auth/`, `src/app/admin/` (does not exist — confirms FVS-005's gate still holds), `playwright.config.ts`. Searched for `AdminTable`/`StatusBadge`/`admin users`/`customers`/`deactivate`/`AdminUser`/`search params`/`sort`/`q=`/`page=` and any OpenAPI source — **none exists.**

**Genuine inconsistency found and resolved, not silently guessed:** `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-009 **Testing** line says `AdminTable component tests (sorting/pagination/search wiring)` — the word "sorting" appears **exactly once**, in that one test-summary bullet, nowhere else. The actual **Frontend capability** line, the **State** line, and VS-009's own backend text (`vertical-slice-plan.md`) all describe only "search/paginate" — never sort/order. No sort field, sort-parameter name, or sort-order contract is given anywhere. **Decision: no sorting is built in this safe batch.** This is recorded here explicitly rather than either (a) silently adding a sorting seam because the word appears once, or (b) silently dropping it without comment. If a later backend confirmation or product decision establishes real sort support, add it then — not now, not from one incidental word.

**Confirmed by repository evidence:**
- All three endpoint paths are literal in `vertical-slice-plan.md`.
- Browser URL state (`?q=&page=`) is an explicit **frontend architecture decision** in `FRONTEND-VERTICAL-SLICE-PLAN.md`'s own **State** line — confirmed, not contract-gated. The backend's own query-parameter names for search/page are a **separate, unconfirmed** question (§1 below) — browser `q` is never assumed to map 1:1 onto whatever the backend calls it.
- `ConfirmDialog` (FVS-007, `src/components/feedback/ConfirmDialog.tsx`) already supports everything the eventual deactivation flow needs: `title`/`description`/`confirmLabel`/`cancelLabel`/`isConfirming`/`onConfirm`/`onCancel`, a Tab focus trap, `Escape` handling, and focus restored to the triggering element on close (all already tested, 11/11 passing). **No enhancement is needed** — T04 is verification-only this batch (§2).
- `vertical-slice-plan.md` VS-009: "PII-safe audit/logging" is a backend-side logic effect, matching VS-007/VS-008's own already-established pattern — no frontend audit action is required.
- FVS-005's own plan already confirms the backend's `/api/v1/admin` boundary independently 404s non-admin API calls — the real security boundary, inherited here, not reopened.

**What is genuinely unconfirmed:** the backend's own search/page query-parameter names, page size, response envelope, every list-row field name (including the account-state and verification-state field names/values), the full `AdminUserDetail` schema (and therefore exactly which PII fields are safe to display), and the full PATCH contract (editable field name, activate/deactivate representation, body, status, CSRF, validation, concurrency, session-revocation effect). None of this is guessed below.

---

## 1. Contract Confidence Table

| Area | Item | Status | Consequence |
|---|---|---|---|
| **List** | `GET /api/v1/admin/users` path | **CONFIRMED** | Literal path |
| **List** | Browser URL `?q=&page=` | **CONFIRMED (frontend architecture)** | T03 builds pure helpers for this; never claims to be the backend's own query contract |
| **List** | Backend search parameter name | **NEEDS BACKEND CONFIRMATION** | Not assumed to be `q` |
| **List** | Backend page parameter name/model | **NEEDS BACKEND CONFIRMATION** | Not assumed to be `page` or page-number-based |
| **List** | Page size, response envelope, total/page count | **NEEDS BACKEND CONFIRMATION** | T05 blocked |
| **List** | List-row fields (incl. account-state, verification fields) | **NEEDS BACKEND CONFIRMATION** | `AdminTable`'s columns for this specific table wait on T05; the table component itself is schema-neutral |
| **List** | Sort behavior | **NOT CONFIRMED — inconsistency recorded, not built** | See §0; no sorting seam added this batch |
| **Detail** | Exact `AdminUserDetail` schema / allowed PII | **NEEDS BACKEND CONFIRMATION** | T05/T06 blocked; nothing beyond the confirmed schema will ever be displayed |
| **Detail** | Not-found behavior | **NEEDS BACKEND CONFIRMATION** | T05 blocked |
| **PATCH** | Exact editable field, activate/deactivate representation, body, status, CSRF, validation, concurrency | **NEEDS BACKEND CONFIRMATION** | T07 blocked |
| **PATCH** | Effect on existing sessions | **NEEDS BACKEND CONFIRMATION** | Not assumed either way |
| **PATCH** | Audit | **CONFIRMED — backend-automatic** | Nothing to build |
| **Security** | `/admin/customers*` route protection | **BLOCKED ON FVS-005** | T06 waits for `AdminProtectedRoute` |
| **Security** | Backend 404/route-hiding | **CONFIRMED (inherited from FVS-005)** | Not reopened |
| **Security** | PII scope | **ARCHITECTURE RULE — display only confirmed `AdminUserDetail` fields** | No invented columns ever |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Generic `AdminTable` | **CAN IMPLEMENT NOW** |
| T02 | `StatusBadge` | **CAN IMPLEMENT NOW** |
| T03 | `q`/`page` URL-state helpers | **CAN IMPLEMENT NOW** |
| T04 | `ConfirmDialog` audit | **CAN IMPLEMENT NOW — verification-only, no code change, no commit** |
| T05 | Customers API/query adapter | **BLOCKED ON BACKEND CONTRACT + FVS-005** |
| T06 | Customer list/detail routes + `AdminProtectedRoute` | **BLOCKED ON FVS-005** |
| T07 | Activate/deactivate mutation | **BLOCKED ON BACKEND CONTRACT** |
| T08 | Integration/E2E/docs | **BLOCKED** (depends on T05–T07) |
| T09 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Optimized Batches

| Batch | Contents | Status |
|---|---|---|
| **Safe Batch 1** | T01–T04 | **This session** |
| Backend-unlocked batch | T05–T07 | Gate: §4 answered + FVS-005 lands |
| Closure | T08 | Gate: previous batch lands |
| Real backend acceptance | T09 | Gate: real backend reachable |

---

## 4. Backend Questions For Tomorrow

**LIST**
1. Exact list query parameters (and their names — is search `q`, `search`, `email`, something else?).
2. Search semantics — email-only, id-inclusive, something broader?
3. Exact pagination model (page-number, cursor, offset?) and its request/response field names.
4. Default/max page size.
5. Exact response envelope.
6. Exact list-row fields.
7. Exact account-state field name and its allowed literal values.
8. Exact email-verification field representation.
9. Any supported sort field/order? (Repository evidence for this slice currently shows none beyond one incidental test-summary word — see §0. If sorting is actually intended, this is the question that resolves it.)

**DETAIL**
10. Exact `AdminUserDetail` schema.
11. Which PII fields are intentionally exposed to an admin via this endpoint?
12. Which fields are guaranteed omitted (password hash, internal notes, etc. — confirm these are never returned, not just "we wouldn't display them")?
13. Not-found/error behavior and exact status/code.

**PATCH**
14. Exact request body.
15. Is the editable field named `active`/`enabled`/`status`/something else?
16. Exact activation representation.
17. Exact deactivation representation.
18. Success status/body.
19. CSRF requirement (pattern suggests yes — not assumed).
20. Admin/MFA requirement (inherited from FVS-005's own open question — not re-asked here, cross-referenced only).
21. Validation-error shape.
22. Concurrency/version behavior.
23. Does deactivation immediately revoke the customer's existing sessions?
24. If yes, what does an already-logged-in session receive on its next request (`401 AUTH_REQUIRED`? something customer-account-specific?).
25. Does reactivation restore login eligibility immediately?
26. Is a reason/note required when deactivating, or is it a bare toggle?

**SECURITY / TESTING**
27. Supported way to prepare a disposable admin account (shared question with FVS-005).
28. Supported way to prepare a disposable customer account to deactivate/reactivate for real testing.
29. Real test procedure: deactivate → login denied → reactivate → login restored.

---

## 5. Task Detail (Safe Batch 1)

### FVS009-T01 — Generic `AdminTable`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/admin/AdminTable.tsx` (+test).
**Design:** Generic over a row type (`<T,>`), with `columns: {header: string; render: (row: T) => ReactNode}[]`, `rows: readonly T[]`, `getRowKey: (row: T) => string`, `isLoading`, `emptyMessage`, a presentational search seam (`searchValue`/`onSearchChange` — controlled, no fetch, no debounce), controlled pagination (`hasPrevious`/`hasNext`/`onPrevious`/`onNext` — no total-page arithmetic invented), and an optional `rowActions: (row: T) => ReactNode` column. Real `<table>`/`<thead>`/`<tbody>`/`<th scope="col">` semantics. Row actions are real buttons/links, keyboard-reachable, never hover-only. Wrapped in a horizontal-scroll container on narrow viewports (`overflow-x-auto`) — **no column-dropping, no stacked-card fallback** (this batch's own explicit instruction: admin tables scroll, they don't drop identity/security columns). No sorting prop (§0).
**Tests:** TDD — the 13-item matrix (table semantics, `scope="col"` headers, rows render, empty state, loading state, search callback, pagination previous/next, boundary-disabled behavior, keyboard-reachable row actions, horizontal-scroll wrapper present, no network, no persistence).
**Commit message:** `feat: add reusable admin table`.

### FVS009-T02 — `StatusBadge`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/admin/StatusBadge.tsx` (+test).
**Design:** Accepts a normalized frontend union — `"active" | "deactivated"` — explicitly not a claim about the backend's real enum literal (§1). Status conveyed in text, never color alone, styled per `bekaa3d-brand-ui`'s existing badge convention (pill radius, semantic-color tint + full-opacity text, paired with a label). Marked `#SHARED-STATUS-BADGE` since it is genuinely intended for reuse by every later admin list.
**Tests:** TDD — active text, deactivated text, accessible/readable (text present, not color-only).
**Commit message:** `feat: add admin status badge`.

### FVS009-T03 — `q`/`page` URL-State Helpers

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/lib/admin/adminListUrlState.ts` (+test).
**Design:** Pure functions only (no `useEffect` synchronization loop, no App Router wiring yet — that lands with the real route in T06). `q` defaults to `""`; `page` defaults to `1`; a malformed/non-positive/non-numeric page value safely resolves to `1`; updating one field preserves every other existing search parameter untouched. **Starting a new search resets to page 1 is NOT built as an automatic side effect inside these pure helpers** — nothing in the governing plans confirms this as the required behavior at the helper level (it reads as reasonable *product* UX, but inventing it inside a "pure, URL-state-only" helper would silently encode a product decision this plan hasn't actually been given). Recorded as an open product question, not guessed into the helper. Tagged `#ARCHITECTURE-ADMIN-LIST-URL-STATE` with an explicit note that this is browser-URL state only — never the backend's own query-parameter contract (§1).
**Tests:** TDD — defaults, malformed-page fallback, unrelated-param preservation, round-trip parse/build.
**Commit message:** `feat: add admin list URL-state helpers`.

### FVS009-T04 — `ConfirmDialog` Audit

**Status:** CAN IMPLEMENT NOW — **verification-only.**
**Finding:** `ConfirmDialog` (FVS-007) already supports every capability the eventual deactivation flow needs (§0). No enhancement is required.
**Action:** None. No empty commit.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run at the batch boundary (no route/page work this batch).
- No new runtime dependency.
- No `/admin/customers*` route, no `AdminProtectedRoute` integration, no customer API/DTO code, no PII field invented, no activate/deactivate mutation, no customer-schema E2E until T05–T07 unblock.
- Never convert a `NEEDS BACKEND CONFIRMATION` item to CONFIRMED without an actual answer; never silently resolve the sorting inconsistency either direction.
