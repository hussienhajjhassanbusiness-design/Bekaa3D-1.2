# FVS-030 — Admin Order Fulfillment Console — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: HIGH — fulfillment state machine/concurrency.

**Goal:** Build the admin-order presentation layer by composing around FVS-029's customer-visible primitives (never forking them), a server-provided transition-affordance architecture (never a locally-invented state machine), the high-visibility `InternalNoteEditor`, and a concurrency-conflict notice — while deferring the admin order queue table entirely, since its list-row fields are far less specified than FVS-028's payment list was.

**Architecture:** `AdminOrderLineModel extends OrderLineModel` and `AdminOrderModel` reuses `OrderSummaryModel` directly — admin-only concepts (`internalNote`, `availableActions`) are layered additions, never a forked copy of the customer shape (`#ARCHITECTURE-ADMIN-ORDER-PROJECTION`). `TransitionAffordance {id, label, requiresConfirmation}` is a frontend-normalized, server-authoritative action — the frontend renders exactly the actions it is given and never derives legality from status itself (`#SECURITY-SERVER-FULFILLMENT-STATE-MACHINE`). `OrderLineItem` (FVS-029) is reused completely unmodified — `AdminOrderLine` composes it with transition controls rendered alongside, never inside it, and a regression test proves the customer component cannot even accept an internal note (`#SECURITY-INTERNAL-NOTE-BOUNDARY`). No transition or reconciliation ever optimistically changes a displayed status.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-024 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-030 entry (lines 787-811).

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-024), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-005/009/017/019/028/029/030 entries), `FVS-005/009/017/019/028/029-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/admin/{AdminTable,StatusBadge}.tsx`, `src/components/feedback/ConfirmDialog.tsx`, `src/components/account/{OrderLineItem,OrderDetail}.tsx` (FVS-029), `src/lib/orders/orderModel.ts`. Confirmed via directory listing that **`src/app/admin/` still does not exist at all** — the same pre-existing, cross-cutting FVS-005 gate every prior admin slice has recorded. Grepped the whole `src/` tree for `internalNote|InternalNote|transition|Transition|availableActions` outside unrelated hits (CSS transitions, an email-resend cooldown, FVS-029's own negative-space comments) — zero existing admin-order code anywhere.

**Confirmed by repository evidence:**
- VS-024's own "Endpoint / entrypoint" line is **entirely prose**: "Admin orders list/detail/update; line transition endpoint" — zero literal paths anywhere, for any of the four endpoints FVS-030's own entry lists as placeholders.
- VS-024's Logic line confirms, at the **concept** level only: filter/search queue, edit-internal-note-only, legal delivery/pickup transitions, row lock, **order status is server-derived** (not independently settable), audit/history append, notification side effects. Schema names are only `AdminOrderPage/Detail`, `AdminOrderUpdate`, `OrderItemTransitionRequest` — no field names.
- **No exact backend state diagram exists anywhere.** FVS-030's own entry explicitly conditions a client-side mirrored transition table on "the backend's documented state diagram" existing — it doesn't, so this plan builds **only** the server-provided-affordances architecture (option A), never a hardcoded table (option B), per the task's own explicit instruction.
- The example statuses in both the backend plan and the frontend plan ("paid," "production," "out for delivery," "delivered") are explicitly flagged by the governing prompt as illustrative, not literal — none is repeated here as fact.
- `OrderLineItem`/`OrderDetail` (FVS-029) are directly reusable; neither needs modification. `AdminTable`/`StatusBadge`/`ConfirmDialog` are all directly reusable with zero change.
- Unlike FVS-028's payment list (whose own entry explicitly enumerated "status, provider reference, amount, linked order" as detail concepts), **FVS-030's own entry does not enumerate specific admin-queue list-row fields** with comparable specificity — it only says "searchable/filterable order queue." This is a materially weaker evidentiary basis than FVS-028 had, so (unlike FVS-028's `AdminPaymentList`) this plan defers the admin order queue table entirely rather than composing one from guessed columns.

**What is genuinely unconfirmed:** all four admin endpoint paths; the list/detail response envelopes and every field name within them; whether the backend returns an explicit per-line affordance list at all (and if so, its exact field/shape); the internal-note update mechanism (dedicated endpoint vs. full-order `PATCH`); the concurrency/version-token mechanism and its conflict response shape; search/filter query-parameter names.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Endpoints** | All four admin order paths | **NEEDS BACKEND CONFIRMATION** — prose-only in VS-024 |
| **Model** | Admin internal note exists, never customer-visible | **CONFIRMED concept** (VS-024 Logic line); **no field name** |
| **Model** | Order status is server-derived from line statuses | **CONFIRMED concept** (VS-024 Logic line: "derive order status") |
| **State machine** | Server-provided per-line affordance list | **UNCONFIRMED whether it exists** — built as the only safe architecture regardless |
| **State machine** | Exact backend state diagram (fallback option B) | **DOES NOT EXIST in either source** — option B is not buildable at all this batch |
| **Concurrency** | Row-lock concept | **CONFIRMED concept** (VS-024 Logic line: "row lock"); **no conflict-response shape** |
| **Admin queue** | List-row fields | **WEAKER evidentiary basis than FVS-028's payment list — deferred, not composed** |
| **Admin shell** | `/admin/*` route + `AdminProtectedRoute` | **BLOCKED ON FVS-005** (pre-existing, cross-cutting, not reopened here) |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized admin-order models + customer/admin boundary regression test | **CAN IMPLEMENT NOW** |
| T02 | `InternalNoteEditor` | **CAN IMPLEMENT NOW** |
| T03 | Transition-affordance model | **Folded into T01** |
| T04 | `TransitionActions` | **CAN IMPLEMENT NOW** |
| T05 | `AdminOrderLine` (composes `OrderLineItem` + `TransitionActions`) | **CAN IMPLEMENT NOW** |
| T06 | `AdminOrderDetail` (incl. `OrderSummaryDisplay` extraction) | **CAN IMPLEMENT NOW** |
| T07 | Admin order queue (`AdminTable` composition) | **CORRECTLY DEFERRED — list-row fields too weakly evidenced** |
| T08 | Concurrency-conflict notice | **CAN IMPLEMENT NOW** |
| T09 | Real API/query/mutations | **BLOCKED ON BACKEND CONTRACT** |
| T10 | `/admin/orders` routes + E2E | **BLOCKED ON FVS-005 (no admin shell exists) + T09** |
| T11 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02, T04, T05, T06, T08. T07 is deferred for a distinct, documented reason; T09–T11 are blocked.

---

## 4. Backend Questions For Tomorrow

**Endpoints:** 1. Exact admin order list endpoint. 2. Exact admin order detail endpoint. 3. Exact internal-note update endpoint. 4. Exact per-line transition endpoint.

**List:** 5. Response envelope. 6. Pagination/cursor. 7. Search query field. 8. Filter query fields. 9. Sort/order. 10. Exact list-row fields. 11. Order id. 12. Customer display identifier fields. 13. Status summary. 14. Payment summary. 15. Fulfillment summary. 16. Total/currency. 17. Timestamps.

**Detail:** 18. Exact admin `OrderRead`/`AdminOrderDetail` schema. 19. Which customer-order fields are reused verbatim vs. re-shaped? 20. Internal-note field name. 21. Internal-note nullable/empty semantics. 22. Line-item fields beyond the customer projection. 23. Per-line current status field. 24. **Does the response include an explicit available-actions field?** 25. If yes, its exact schema (action id vs. destination state; is a display label server-supplied?). 26. Concurrency/version token field. 27. Operational timestamps.

**State machine:** 28. If no affordance list exists, provide the exact authoritative transition diagram/table (option B) — otherwise this plan stays on option A indefinitely. 29. Which transitions require confirmation? 30. Are digital/STL lines ever transition-bearing, or always `availableActions: []`? 31. Are any transitions reversible? 32. Are any terminal?

**Internal note:** 33. Exact save request body. 34. Dedicated action, or full-order `PATCH`? 35. Max length (not invented here). 36. Empty/null allowed? 37. CSRF/MFA/admin requirements. 38. Concurrency behavior on save. 39. Success response.

**Transition:** 40. Exact mutation body. 41. Required line id. 42. Action id/destination-status field. 43. Success response — does it return the whole authoritative order? 44. Illegal-transition error shape. 45. Concurrency-conflict error shape. 46. CSRF. 47. Admin/MFA freshness requirement.

**Concurrency:** 48. Optimistic-lock/version mechanism, if any. 49. Row-lock conflict representation. 50. Should the UI automatically refetch after a conflict, or only offer to? 51. Is retry-after-refetch safe/expected?

**Security:** 52. Independently re-confirm the internal note never appears in any customer-facing endpoint. 53. Which admin order fields must never be exposed publicly? 54. Any payment-provider metadata intentionally excluded from this endpoint (FVS-028 owns that surface)?

**Testing:** 55. Disposable admin fixture (blocked transitively on FVS-005). 56. Mixed-order fixture. 57. Physical-line-with-legal-transition fixture. 58. Digital-line fixture. 59. Concurrency-conflict fixture. 60. Illegal-transition fixture. 61. Internal-note fixture. 62. Transition-acceptance sequence. 63. Customer-projection leak check.

---

## 5. Task Detail (Safe Batch)

### FVS030-T01 — Normalized Admin-Order Models + Boundary Regression Test

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/admin/adminOrderModel.ts` (+test).
**Design:** `TransitionAffordance {id: string, label: string, requiresConfirmation: boolean}` — a frontend-normalized, server-authoritative action; never derived from status locally (`#SECURITY-SERVER-FULFILLMENT-STATE-MACHINE`). `AdminOrderLineModel extends OrderLineModel { availableActions: readonly TransitionAffordance[] }` — reuses FVS-029's `OrderLineModel` directly via extension, not a forked copy (T03 folded in here). `AdminOrderModel {id, displayDate, statusLabel, lines: readonly AdminOrderLineModel[], summary: OrderSummaryModel, internalNote: string}` — `summary` reuses FVS-029's `OrderSummaryModel` directly, unmodified.
**Marker:** `#ARCHITECTURE-ADMIN-ORDER-PROJECTION`, `#SECURITY-SERVER-FULFILLMENT-STATE-MACHINE`, `#SECURITY-INTERNAL-NOTE-BOUNDARY`.
**Tests:** `AdminOrderLineModel` accepts all `OrderLineModel` fields plus `availableActions` (proving genuine extension, not duplication); `availableActions: []` is valid (digital/STL lines may legitimately have none); **the critical cross-slice regression test**: a `@ts-expect-error`-backed compile-time proof that FVS-029's `OrderLineItemProps`/`OrderDetailProps` (imported directly from their real modules) cannot accept an object carrying `internalNote` — proving the customer components have no internal-note prop/render path at all, not merely "don't currently use one."

### FVS030-T02 — `InternalNoteEditor`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/InternalNoteEditor.tsx` (+test).
**Design:** `{note: string, onSave: (note: string) => void, isSaving?: boolean, errorMessage?: string}`. An explicit, screen-reader-read label — "Internal note — not visible to customers" — never conveyed by styling alone. Local draft state, independent from line-transition state; Save is an explicit button click only — **no auto-save, no save-on-blur**. No invented max length, no required/non-required rule beyond what the caller enforces via `errorMessage`. The note is never persisted to browser storage, never logged, never placed in a URL or query key.
**Marker:** `#SECURITY-INTERNAL-NOTE-BOUNDARY`.
**Tests:** renders the explicit customer-invisibility label as real, readable text; typing edits only local draft state (does not call `onSave` on every keystroke); `onSave` fires only on an explicit Save click, with the exact typed text; `isSaving` disables Save with visible progress text; `errorMessage` renders as a safe, caller-supplied string (never a raw exception); no network; no storage.

### FVS030-T04 — `TransitionActions`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/TransitionActions.tsx` (+test).
**Design:** `{actions: readonly TransitionAffordance[], pendingActionId?: string | null, onSelectAction: (actionId: string) => void}` — renders exactly the supplied legal actions, zero actions renders nothing (never a locally-invented "Next" fallback). Each button's accessible name is the action's own `label` (describing the destination/action, never generic "Next"). An action with `requiresConfirmation: true` opens the existing `ConfirmDialog` (reused, no second focus-trap) before calling `onSelectAction`; one without fires immediately. While any action is pending, **all** buttons in this group are disabled (preventing a second transition from firing concurrently with the first) — this component never optimistically assumes the transition succeeded.
**Marker:** none new — reuses `#SECURITY-SERVER-FULFILLMENT-STATE-MACHINE` (T01) and `ConfirmDialog` (FVS-007/FVS-019) as-is.
**Tests:** renders exactly one button per supplied action, with that action's own label as the accessible name; renders nothing when `actions` is empty; an action with `requiresConfirmation: false` calls `onSelectAction` immediately on click; an action with `requiresConfirmation: true` opens `ConfirmDialog` first, and `onSelectAction` fires only after confirming (never on the initial click, never on Cancel); all buttons disabled while `pendingActionId` is set; no optimistic status mutation of any kind (this component has no status field to mutate — structurally proven by its own prop type); no network.

### FVS030-T05 — `AdminOrderLine`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/AdminOrderLine.tsx` (+test).
**Design:** `{line: AdminOrderLineModel, pendingActionId?: string | null, onSelectAction: (lineId: string, actionId: string) => void}` — composes `OrderLineItem` (FVS-029, reused completely unmodified, rendering `line` directly since `AdminOrderLineModel` is a superset) alongside `TransitionActions` rendered **separately**, never injecting admin state into `OrderLineItem` itself.
**Marker:** `#ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY` (carried over from FVS-029).
**Tests:** renders the exact same output `OrderLineItem` alone would for the line's customer-visible fields (proving genuine reuse, not a reimplementation); renders `TransitionActions` for the line's own `availableActions`; selecting an action calls the composed callback with `(line.id, actionId)`; a digital/STL line with `availableActions: []` renders no transition controls at all, with no special-cased "STL lines never transition" logic anywhere in this component (the absence comes naturally from the empty array, never a hardcoded product-type check).

### FVS030-T06 — `AdminOrderDetail` (incl. `OrderSummaryDisplay` Extraction)

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/OrderSummaryDisplay.tsx` (extracted from `OrderDetail`, +test; `OrderDetail.tsx` updated to reuse it, zero behavior change), `src/components/admin/AdminOrderDetail.tsx` (+test).
**Design:** `OrderDetail`'s existing summary-rendering block is extracted into `OrderSummaryDisplay({summary: OrderSummaryModel})` — a second genuine reuse case (admin needs the identical summary rendering) justifies this now, mirroring this engagement's established extraction pattern. `AdminOrderDetail` composes: `OrderSummaryDisplay` (reused, unmodified), `InternalNoteEditor`, and a list of `AdminOrderLine` — never a payment-provider secret/raw payload (FVS-028 owns that surface entirely; this component has no such field to render).
**Marker:** `#SECURITY-INTERNAL-NOTE-BOUNDARY`.
**Tests (`OrderSummaryDisplay`):** `OrderDetail.test.tsx`'s own existing summary-rendering assertions re-run unmodified and green after the extraction. **Tests (`AdminOrderDetail`):** renders the internal note editor; renders every line via `AdminOrderLine` with independent transition actions; never renders a payment-provider secret/raw payload field (structural — no such prop exists anywhere in this component's type); no current-catalogue fetch.

### FVS030-T08 — Concurrency-Conflict Notice

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/OrderConcurrencyConflictNotice.tsx` (+test).
**Design:** `{message: string, onRefresh: () => void}` — a reusable, generic presentational notice: explains that the order changed elsewhere, offers an explicit refresh action, never silently overwrites, never pretends a local action succeeded. No invented `409`/`412`/version-mismatch code anywhere — `message` is always an already-safe, caller-supplied string.
**Marker:** `#SECURITY-ORDER-CONCURRENCY-REFETCH`.
**Tests:** renders the exact supplied message as an alert; `onRefresh` fires only on an explicit click; renders no raw RFC/HTTP-status detail of any kind; no network.

---

## 6. Deferred / Blocked Tasks (Rationale)

**T07 — Admin order queue (`AdminTable` composition):** Deferred — unlike FVS-028's payment list (whose own governing entry explicitly enumerated "status, provider reference, amount, linked order" as detail concepts with comparable specificity), FVS-030's own entry only says "searchable/filterable order queue" with no comparable list-row field enumeration. Composing a table now would mean guessing columns (customer email/phone/delivery address/total/status) exactly as the task's own instruction forbids. No adapter/model seam is built either, since there is nothing confirmed yet to seam.

**T09 — Real API/query/mutations:** Blocked — no confirmed request/response body for any of the four admin order operations, and no confirmed affordance-list schema.

**T10 — `/admin/orders` routes + E2E:** Blocked on two independent gates: (1) the admin API contract (T09), and (2) the pre-existing, cross-cutting FVS-005 gate — no admin route shell/`AdminProtectedRoute` exists anywhere in this repository yet, the same blocker every prior admin slice has recorded independently.

**T11 — Real backend acceptance:** Blocked on backend availability.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; one `test:e2e` regression run suffices (no route/page work this batch; `OrderDetail.tsx`'s own extraction-driven edit is re-verified to leave its existing tests green).
- No new runtime dependency.
- No invented admin endpoint path/body, no hardcoded transition/state-machine table, no generic status dropdown/free-text status field, no optimistic fulfillment status, no guessed concurrency-conflict code, no customer-component rendering of an internal note, no browser-persisted admin note, no production `/admin/orders` route, until the respective gates in §6 unblock.
- `OrderLineItem`/`OrderDetail` (FVS-029) and `AdminTable`/`StatusBadge`/`ConfirmDialog` are reused completely unmodified except for the one documented, test-verified `OrderSummaryDisplay` extraction.
