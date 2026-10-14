# FVS-008 — Notification Center — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per task, STOP after the safe frontend batch.

**Goal:** A logged-in customer sees an unread-count badge (header bell) and a notification list (`/account/notifications`) with mark-read/unread and pagination. Zero concrete event-specific renderers ship in this slice — every notification type the frontend doesn't yet recognize renders safely via a generic title/body fallback.

**Architecture:** A small frontend-normalized `NotificationItemModel` isolates `NotificationItem`/`NotificationList`/`NotificationBell` from the unconfirmed backend response shape. A type-keyed renderer registry starts with zero concrete entries — later slices append their own event-specific renderer, never this slice. No WebSocket/SSE/push — polling only, per the already-established architecture rule (§7/§9 of `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`), with the exact interval left unresolved pending evidence. No new runtime dependency.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-008 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-008 entry (plus its own §17 items explicitly logging the pagination-shape and type-taxonomy gaps — not newly discovered here).

---

## 0. Repository / Contract Audit (Part A)

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-008), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-008 entry, §17's two VS-008-relevant gap items), `docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md`, `docs/plans/frontend-slices/FVS-006-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/layout/` (`Header.tsx`, `AppLayout.tsx`), `src/components/account/` (`accountNavItems.ts`), `src/components/feedback/`, `src/lib/api/`, `src/lib/auth/`, `src/app/account/`, `src/app/layout.tsx`, `playwright.config.ts`. Searched for `notification`/`bell`/`badge`/`popover`/`sheet`/`drawer`/`pagination`/`poll`/`refetchInterval` — **no notification/bell/popover/sheet/pagination code exists anywhere.** `Header.tsx` has no nav items at all yet (confirmed, same finding as every prior slice's own audit) — a real bell cannot be mounted into it with fabricated data (see §2 T04 scope note). The one existing polling precedent in this repository is `useReadiness.ts`'s `refetchInterval: 15_000` — a documented **frontend-only operational default, not a backend contract** (FVS-001's own words) — useful precedent that frontend-owned intervals are an accepted pattern here, but not itself evidence for what a notification-count interval should be.

**Confirmed by repository evidence:**
- Both endpoint paths are literal in `docs/plans/backend/vertical-slice-plan.md`.
- `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §9/§17 names the pagination mechanism as **cursor-based** (not page-number-based) — confirmed as a *named mechanism*, with field-level shape still unconfirmed (§17 explicitly lists this gap for VS-008 by name).
- The generic-renderer-with-safe-fallback requirement is explicit in the capability text itself — a frontend architecture decision, not contract-gated.
- No WebSocket/SSE/push mechanism is mentioned anywhere for VS-008 (or anywhere in `docs/plans/backend/vertical-slice-plan.md`) — polling is the only architecture ever named for this slice.
- The accessible bell label format (`aria-label="Notifications, N unread"`) and the mobile-sheet/desktop-dropdown responsive split are both already specified in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own text — not invented here.
- `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 explicitly logs the notification `type`-taxonomy gap, recommending a shared living registry — exactly matching this plan's own "zero concrete types" rule.

**What is genuinely unconfirmed:** every list-response field name (envelope, id, type, title, body, read-state, timestamp, link), the cursor/page-size field names, ordering, how/whether unread-count is exposed, the PATCH body/response/CSRF/validation/idempotency, and the polling interval value. None of this is guessed below.

---

## 1. Contract Confidence Table

| Area | Item | Status | Consequence |
|---|---|---|---|
| **GET list** | Path | **CONFIRMED** | Literal in `docs/plans/backend/vertical-slice-plan.md` |
| **GET list** | Query parameters | **NEEDS BACKEND CONFIRMATION** | T05 blocked |
| **GET list** | Pagination model | **CONFIRMED — cursor-based (named)**; field names **NEEDS BACKEND CONFIRMATION** | T05's adapter waits for the field names; the mechanism itself is settled |
| **GET list** | Page size / max page size | **NEEDS BACKEND CONFIRMATION** | T05 blocked |
| **GET list** | Ordering | **NEEDS BACKEND CONFIRMATION** | Not assumed (e.g. newest-first is typical but not confirmed) |
| **GET list** | Response envelope, item id/type/title/body/read-state/timestamp/link fields | **NEEDS BACKEND CONFIRMATION** | `NotificationItemModel` (T01) is a UI model only |
| **GET list** | Unread-count exposure (list field? separate endpoint? derived?) | **NEEDS BACKEND CONFIRMATION** | T05 blocked; `NotificationBell` (T04) takes `unreadCount` as a prop regardless of source |
| **GET list** | Unknown-type safety | **CONFIRMED (frontend architecture)** | Generic fallback render, never a crash — built in T01/T02 |
| **PATCH** | Path | **CONFIRMED** | Literal |
| **PATCH** | Request body, read/unread representation | **NEEDS BACKEND CONFIRMATION** | T05 blocked; no `{read: true}`/`{is_read: true}` guessed |
| **PATCH** | Success status/body, CSRF, validation/not-found, idempotency, rate limit | **NEEDS BACKEND CONFIRMATION** | T05 blocked |
| **Realtime** | WebSocket/SSE/push | **CONFIRMED — none; polling only** | No realtime transport invented anywhere |
| **Polling** | Interval value | **UNRESOLVED — recorded, not guessed** | T05 decides once there's evidence (backend guidance, or an explicit frontend-owned default decision point) |
| **Security** | Customer auth | **CONFIRMED — reuses FVS-003/006 as-is** | No new auth mechanism; `ProtectedRoute`/`AccountLayout` own protection once T06 lands |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized notification UI model + renderer registry boundary | **CAN IMPLEMENT NOW** |
| T02 | `NotificationItem` generic fallback renderer | **CAN IMPLEMENT NOW** |
| T03 | `NotificationList` presentational states | **CAN IMPLEMENT NOW** |
| T04 | `NotificationBell` presentational shell | **CAN IMPLEMENT NOW** (standalone — see scope note below) |
| T05 | API/query/pagination/polling + optimistic read/unread | **BLOCKED ON BACKEND CONTRACT** |
| T06 | `/account/notifications` route + account-nav integration + mounting the bell into `Header` with real data | **BLOCKED** (depends on T05) |
| T07 | Integration/accessibility review | **BLOCKED** (depends on T05/T06) |
| T08 | Deterministic E2E + docs | **BLOCKED** (depends on T07) |
| T09 | Real-backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

**Scope note on T04/Header:** `NotificationBell` is built and fully tested as a standalone presentational component this batch, but is **not** wired into `Header.tsx` yet. Mounting it now would mean showing a permanently-zero/fabricated unread count in production — the same "no fabricated production wiring on fake data" principle every prior slice in this engagement has followed. Wiring happens in T06, alongside the real unread-count source.

**Scope note on account nav:** `Notifications` is **not** added to `ACCOUNT_NAV_ITEMS` this batch — `/account/notifications` isn't a real route yet. Adding it is explicitly T06's job, once the route exists, per `docs/plans/frontend-slices/FVS-006-IMPLEMENTATION-PLAN.md`'s own "no dead nav links" rule.

## 3. Optimized Batches

| Batch | Contents | Status |
|---|---|---|
| **Safe Batch 1** | T01–T04 | **This session** |
| Backend-unlocked batch | T05–T06 | Gate: §4 answered |
| Closure | T07–T08 | Gate: previous batch lands |
| Real backend acceptance | T09 | Gate: real backend reachable |

---

## 4. Backend Questions For Tomorrow

**LIST**
1. Exact `GET /api/v1/me/notifications` query parameters.
2. Cursor field name(s) — request and response — and whether the cursor is opaque or frontend-constructible (it should be treated as opaque regardless, but confirm).
3. Default/max page size.
4. Sort/order guarantee (newest-first assumed nowhere, confirm).
5. Exact response envelope shape.
6. Exact per-item field names: id, type, title, body, read-state, timestamp (if any), link/destination (if any).
7. Are `title`/`body` already safe, ready-to-render display copy, or do they need any frontend transformation?
8. Can `title`/`body` ever contain HTML/markdown, or must the frontend always render them as plain text? (This plan assumes plain text only until told otherwise.)
9. How is unread count exposed — a list-response field, separate metadata, a separate endpoint, or must the frontend derive it by counting unread items across pages? Is the first page's count (if any) authoritative, or does the frontend need every page to know the true total?
10. Recommended polling interval, or confirmation that this is a frontend-owned decision (matching `useReadiness.ts`'s own precedent, §0).
11. Any `ETag`/cache-header guidance for this endpoint.
12. Can every future notification `type` always be safely rendered from generic title/body alone, or will some types need an additional lookup the generic renderer can't provide?

**PATCH**
13. Exact request body for marking read.
14. Exact request body for marking unread (same shape, inverted; or different?).
15. Success status and body.
16. CSRF requirement (pattern suggests yes, per this project's every other authenticated write — not assumed).
17. Missing-id/not-found error behavior and its exact status/code.
18. Is setting the same read-state twice idempotent (no error on a no-op PATCH)?
19. Any per-user rate limit on this endpoint.

**REAL TESTING**
20. Supported way to insert/emit a disposable notification for a test account, once a real backend is reachable.

---

## 5. Task Detail (Safe Batch 1)

### FVS008-T01 — Normalized Notification Model + Renderer Registry

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/notifications/notificationTypes.ts`.
**Design:** `NotificationItemModel` — `id: string`, `type: string`, `title: string`, `body: string`, `isRead: boolean`. No timestamp/link field added (no current UI requirement needs one; add only when a real consumer does). Tagged `#ARCHITECTURE-NOTIFICATION-ADAPTER` — explains the backend response shape is isolated here; a future adapter maps whatever the confirmed contract turns out to be, so a contract change touches one place, not `NotificationItem`/`NotificationList`. A renderer-registry seam (`#SHARED-NOTIFICATION-RENDERERS`) starts with **zero concrete entries** — explicitly not even an example commerce type — future slices append their own.
**Commit:** folded into T02 (type-only).

### FVS008-T02 — `NotificationItem`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/notifications/NotificationItem.tsx` (+test).
**Design:** Renders as an `<li>`-compatible element (no `<li>` of its own — the parent `<ul>` in `NotificationList` owns list semantics; this component renders the row content). Title/body rendered as plain text (`{title}`/`{body}` JSX interpolation — never `dangerouslySetInnerHTML`, never HTML interpretation). Read/unread conveyed via visible text (not color alone). A callback seam (`onToggleRead(id, nextIsRead)`) for a future mark-read/unread action, with an optional `isPending` prop to disable the action control while a future mutation is in flight. No network call, no TanStack Query, no persistence.
**Tests:** TDD — the 12-item matrix (known data renders, unknown type renders safely via the same generic path — there is no "special" path to diverge from, exact title/body text, no HTML interpretation, textual read/unread indication both ways, callback receives the right id/intent, pending disables the action, no network, no persistence, and a structural check that no concrete event-type renderer exists in the registry).
**Commit message:** `feat: add generic notification renderer`.

### FVS008-T03 — `NotificationList`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/notifications/NotificationList.tsx` (+test).
**Design:** `<ul>`/`<li>` semantics, states: loading (skeleton, same motion-reduce-safe pattern as `ProfileCard`'s), error (safe generic message + retry callback — never parses a backend error), empty (safe neutral copy), populated (maps items through `NotificationItem`). Pagination UI is fully generic — `canLoadMore`/`isLoadingMore`/`onLoadMore` props — no `page`/`cursor` field assumed anywhere in this component.
**Tests:** TDD — the 12-item matrix (loading/error/retry/empty/populated/multiple-items, load-more present/absent/disabled-while-loading, child action forwarding, no network, no storage).
**Commit message:** `feat: add notification list presentation`.

### FVS008-T04 — `NotificationBell`

**Status:** CAN IMPLEMENT NOW (standalone — see §2's scope note; not mounted into `Header` this batch).
**Files:** `src/components/notifications/NotificationBell.tsx` (+test).
**Design:** Pure presentation — `unreadCount: number`, controlled `open`/`onOpenChange`, a content seam (`children`) for whatever `NotificationList` instance a future consumer renders inside it. `aria-label` exactly `` `Notifications, ${unreadCount} unread` `` for every count including zero (matching `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own specified format verbatim — no silent reinterpretation for zero). No large-count formatting (`99+`) invented — large-value display is explicitly product-owned and not decided here. Desktop: anchored dropdown panel (CSS-only positioning). Mobile (`<768px`): full-screen sheet instead of a small popover — pure CSS responsive classes, no JS viewport detection. Reuses the same accessible-dialog primitives `ConfirmDialog` (FVS-007) already proved out (a Tab focus trap, `Escape`-closes, outside-click-closes) rather than inventing a second pattern — but is its own component, since `ConfirmDialog`'s API is confirm/cancel-shaped and a notification panel is not a confirmation (per this batch's own explicit instruction not to misuse `ConfirmDialog` for this). No data fetch, no polling, no mutation.
**Tests:** TDD — accessibility (`aria-label` format including the zero case, keyboard open/close, focus trap, `Escape`) and responsive structural classes — never a fake API/unread-count-fetching behavior.
**Commit message:** `feat: add notification bell presentation`.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run at the batch boundary (no route/page work this batch, so it should stay unchanged).
- No new runtime dependency.
- No `/account/notifications` route, no API/query/polling code, no concrete `type` renderer, no notification E2E until T05/T06 unblock.
- Never convert a `NEEDS BACKEND CONFIRMATION` item to CONFIRMED without an actual answer.
