# FVS-029 — Customer Order History & Detail — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: Medium — ownership/IDOR.

**Goal:** Build the canonical customer-order query-key architecture (resolving the gate FVS-027 deliberately left open), customer-safe normalized order models, the shared `OrderLineItem`/`StatusTimeline` primitives, `OrderList`, and `OrderDetail` (with its not-found boundary folded in) — while keeping every historical value an immutable snapshot, never recomputed from current catalogue data, and never leaking a foreign-vs-nonexistent distinction to the customer.

**Architecture:** `orderKeys` (`.root`/`.list(filters)`/`.detail(id)`) is the ONE canonical query key for the customer order resource — if the backend later confirms `GET /me/orders/{id}` is also the authoritative payment-verification read FVS-027 needs, FVS-027 MUST invalidate `orderKeys.detail(id)` rather than inventing a second cache for the same truth. `OrderLineModel`/`OrderDetailModel`/`OrderListItemModel` hold only customer-visible, presentation-ready values — no internal note, no staff identifier, no provider raw payload (`#SECURITY-CUSTOMER-ORDER-PROJECTION`) — and no field is ever derived from a live product/price lookup (`#ARCHITECTURE-ORDER-SNAPSHOT-IMMUTABLE`). A foreign order and a nonexistent order render byte-for-byte identical output — the exact same, already-existing `NotFoundContent` the app's global 404 uses — never a distinct "forbidden" message (`#SECURITY-ORDER-IDOR-HIDING`).

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-023 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-029 entry (lines 763-786).

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-023), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-006/013/020/025/027/029 entries), `FVS-006/013/020/025/027-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/account/`, `src/components/admin/StatusBadge.tsx`, `src/components/catalog/PriceDisplay.tsx`, `src/lib/{payment,cart,entitlements,catalog}/`, `src/lib/catalog/shopUrlState.ts` (the governing customer-facing URL-state precedent), `src/app/not-found.tsx`+its test. Grepped the whole `src/` tree for `order|Order` outside comments — zero existing order code anywhere.

**Confirmed by repository evidence:**
- Both `GET /api/v1/me/orders` and `GET /api/v1/me/orders/{id}` are literal/confirmed (VS-023's own "Endpoint / entrypoint" line gives both exactly). Response schema names are only `OrderPage`/`OrderDetail` — **no field name is given anywhere**.
- VS-023's Logic line confirms, at the **concept** level only: own-order filtering, no admin-note leak, cursor pagination, status/date filters. Its Tests line confirms: IDOR/404 hiding, mixed-order detail, snapshot values surviving product/address edits, pagination.
- **The foreign-vs-nonexistent IDOR rule is explicit and literal**: FVS-029's own "API integration" line states a foreign order id "returns 404 (IDOR-hidden, not 403) — the frontend renders the app's standard not-found page."
- **No literal URL query-parameter example exists for `/account/orders`** — unlike FVS-013's own Routes line, which gives the exact literal example `/shop?category=&material=&colour=&sort=&q=&cursor=` (the direct evidentiary basis `shopUrlState.ts`'s own key names rely on). FVS-029's Routes line gives only `/account/orders`, `/account/orders/:id` — no query string. This plan therefore does **not** build a URL-serialization layer this batch (§6) — building one would mean inventing the same kind of literal key-naming decision `shopUrlState.ts` only made because a literal example backed it.
- **The FVS-027 payment-verification relationship is NOT confirmed.** VS-023's Request/response schema line groups "payment/refund/history projections" generically under `OrderDetail` — it does not name a specific payment-status field, literal, or confirm that this field (if any) is suitable for FVS-027's polling needs. FVS-027's own status-read gate stays unresolved; this endpoint is not forced to serve it.
- `src/app/not-found.tsx` (+ its own passing test, + `e2e/smoke.spec.ts`'s "unknown route" test) is the app's one existing not-found experience. There was previously no second use case for it (its own comment says so, explicitly YAGNI) — this slice introduces the second one, justifying extraction into a shared `NotFoundContent` component this batch, reused by both.

**What is genuinely unconfirmed:** the list/detail response envelopes and every field name within them; cursor request/response field names; accepted status-filter values; date-filter parameter names/timezone/inclusive-exclusive semantics; whether detail exposes a payment-status field at all; refund amount/reason shape; the admin-note field name (confirmed only that one exists and must never leak).

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Endpoints** | Both list/detail paths | **CONFIRMED** (literal) |
| **List** | Response envelope / fields / cursor fields | **NEEDS BACKEND CONFIRMATION** |
| **List** | Status/date filter concept | **CONFIRMED concept** (VS-023 Logic line); **no query-param names** |
| **List** | URL display key-naming (frontend's own, not backend) | **NO LITERAL EXAMPLE — deferred, unlike FVS-013's shop precedent** |
| **Detail** | Response envelope / every field name | **NEEDS BACKEND CONFIRMATION** |
| **Detail** | Per-line independent status concept | **CONFIRMED concept** (FVS-029's own "per-line-item view" line) |
| **Security** | Foreign order → 404, not 403 | **CONFIRMED** (literal, FVS-029's own API-integration line) |
| **Security** | No admin-note leak | **CONFIRMED concept** (VS-023 Logic line) |
| **Payment** | Detail exposes FVS-027's authoritative status | **UNRESOLVED — not guessed** |
| **Snapshot** | Values survive product/address edits | **CONFIRMED** (VS-023 Tests line) |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Canonical order query keys | **CAN IMPLEMENT NOW** |
| T02 | Normalized customer-order projection models | **CAN IMPLEMENT NOW** |
| T03 | `OrderLineItem` | **CAN IMPLEMENT NOW** |
| T04 | `StatusTimeline` | **CAN IMPLEMENT NOW** |
| T05 | `OrderList` | **CAN IMPLEMENT NOW** |
| T06 | `OrderDetail` (incl. T08 not-found boundary) | **CAN IMPLEMENT NOW** |
| T07 | URL/filter transport helpers | **CORRECTLY DEFERRED — no literal URL-key evidence** |
| T08 | 404/not-found presentation boundary | **Folded into T06** |
| T09 | Real API/query integration | **BLOCKED ON RESPONSE/FILTER CONTRACT** |
| T10 | `/account/orders` routes/nav + E2E/docs | **BLOCKED** until T09 unblocks |
| T11 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01–T06. T07 is deferred for a distinct, documented reason; T09–T11 are blocked.

---

## 4. Backend Questions For Tomorrow

**List:** 1. Exact response envelope. 2. Order id field/type. 3. Display date field. 4. Date timezone/format. 5. Order-level status field/literals. 6. Amount/total in the list response? 7. Currency. 8. Cursor request field. 9. Cursor response field. 10. Forward-only or bi-directional pagination? 11. Default ordering. 12. Status-filter query parameter. 13. Accepted status-filter values. 14. Date-filter parameter(s). 15. Date timezone. 16. Inclusive/exclusive date boundaries.

**Detail:** 17. Exact `OrderRead`/`OrderDetail` schema. 18. Exact line-item schema. 19. Line id. 20. Product id? 21. Product-type field/literals. 22. Product-name snapshot field. 23. Thumbnail snapshot, if any. 24. Quantity. 25. Purchase-time unit price. 26. Purchase-time line total. 27. Currency. 28. Per-line status field/literals. 29. Per-line status/timeline history, if any. 30. Delivery/pickup snapshot. 31. Shipping-zone snapshot. 32. Address snapshot. 33. Order subtotal. 34. Shipping snapshot. 35. Discount snapshot, if any. 36. Final total. 37. Payment-summary fields. 38. Refund-status fields. 39. Refund amount? 40. Customer-visible timestamps.

**Security:** 41. Independently re-confirm foreign-order-id → 404 (already literal in the governing plan). 42. Confirm nonexistent-order returns the identical 404 shape. 43. Exact RFC/problem code for not-found, if the frontend ever needs to branch on it. 44. Independently re-confirm internal/admin notes are never in the customer projection. 45. Confirm manual-payment/admin metadata is excluded from this endpoint.

**Payment/FVS-027:** 46. Does detail expose authoritative verified payment status at all? 47. If yes, exact field/literals. 48. Is it suitable for FVS-027's polling? 49. Recommended polling/cache behavior if so. 50. Does reconciliation update order detail atomically or eventually? 51. Is a dedicated payment-status endpoint still preferred over reusing this one?

**Refunds:** 52. Exact customer-visible refund states. 53. Are partial refunds supported? 54. How are mixed/per-line refunds represented?

**Testing:** 55. Customer-with-empty-history fixture. 56. Mixed-order fixture. 57. Foreign-order fixture. 58. Nonexistent-order fixture/procedure. 59. Purchase-price-vs-current-price fixture. 60. Refund fixture. 61. Cursor-pagination fixture. 62. Status/date-filter acceptance procedure.

---

## 5. Task Detail (Safe Batch)

### FVS029-T01 — Canonical Order Query Keys

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/orders/orderKeys.ts` (+test).
**Design:** `orderKeys = {root: ["orders"], list: (filters: OrderListFilters) => [...root, "list", filters], detail: (orderId) => [...root, "detail", orderId]}`. The key carries the order id only — never address/customer PII, never a payment-provider reference. `filters` is embedded directly as a key segment (a plain object with a fixed property shape); TanStack Query's own key-hashing already sorts object keys deterministically, so no extra manual canonicalization step is needed beyond using a consistent object shape. Explicitly documented: **if the backend later confirms `GET /me/orders/{id}` is also FVS-027's authoritative payment-verification read, FVS-027 must invalidate `orderKeys.detail(id)` — never a second, parallel payment/order cache for the same backend truth.**
**Marker:** `#ARCHITECTURE-CANONICAL-ORDERS-QUERY`.
**Tests:** stable root; `list()`/`detail(id)` both derive from the root and stay distinguishable from it and from each other; two structurally-identical filter objects produce `toEqual` keys (deterministic); the detail key carries the order id only (no PII fields possible — proven by the key's own shape).

### FVS029-T02 — Normalized Customer-Order Projection Models

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/orders/orderModel.ts` (+test).
**Design:** `OrderLineModel {id, productDisplayName, productType: "physical"|"stl", quantity, unitPriceCents, lineTotalCents, currency, statusLabel, thumbnailSrc?}` — `statusLabel` is presentation-ready text, never a claimed backend enum literal (per-line statuses are unconfirmed, §0/§1). `OrderSummaryModel {currency, paymentStatusLabel?, refundStatusLabel?, subtotalCents?, shippingCents?, totalCents?}` — payment/refund are optional presentation labels only, never a claimed amount/reason/provider-reference shape (none confirmed); address/zone snapshots are **not modeled at all** this batch — the schema isn't confirmed enough to model them safely, so they stay absent rather than guessed. `OrderDetailModel {id, displayDate, statusLabel, lines: readonly OrderLineModel[], summary: OrderSummaryModel}`. `OrderListItemModel {id, displayDate, statusLabel, totalCents?, currency?}`. **None of these four types has an `internalNote`/`adminNote`/`staffId`/`providerRawPayload`/`manualConfirmReason` field anywhere** (`#SECURITY-CUSTOMER-ORDER-PROJECTION`) — this is the customer/admin boundary FVS-030 must respect by composition, never by adding such a field here.
**Marker:** `#SECURITY-CUSTOMER-ORDER-PROJECTION`, `#ARCHITECTURE-ORDER-SNAPSHOT-IMMUTABLE` (comment-only on every price/display field: these are purchase-time values a future adapter populates from the order projection, never from a live product/price query).
**Tests:** type-only tests (RED-confirmed via `tsc`) proving none of the four types has any internal/admin/provider field; `OrderLineModel` accepts both `"physical"` and `"stl"` product types independently.

### FVS029-T03 — `OrderLineItem`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/OrderLineItem.tsx` (+test).
**Design:** `{line: OrderLineModel}` — renders only supplied immutable snapshot data: product name, quantity, unit price and line total via `PriceDisplay` (reused), and per-line status via `StatusBadge` with a uniform `neutral` tone (per-line status literals are unconfirmed, so no positive/negative/warning semantics are guessed — the label is still always visible text, never color-only). No fetch, no product link (no confirmed product identifier/link exists for a purchased snapshot), no internal note or admin-action prop of any kind — this is the **customer-visible shared primitive** FVS-030 must compose around, never modify to add admin fields (`#ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY`). Rendered as a real `<li>` inside a semantic list from its caller (`OrderDetail`).
**Marker:** `#ARCHITECTURE-CUSTOMER-ADMIN-ORDER-BOUNDARY`.
**Tests:** renders the exact supplied product name/quantity/price/status; a physical and an STL line render independently (different `productType`, both render correctly); **never substitutes a supplied "current price" for the snapshot price** — a dedicated test passes a deliberately different number labeled as a hypothetical current price nowhere in the component's own props, proving the architecture makes it structurally impossible to pass one at all; has no internal-note prop or render path (type-level, confirmed by the component's own prop type having no such field); no network.

### FVS029-T04 — `StatusTimeline`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/StatusTimeline.tsx` (+test).
**Design:** `{entries: readonly {label: string, timeLabel?: string, isCurrent?: boolean, isCompleted?: boolean}[]}` — fully caller-supplied; this component never encodes a fulfillment state machine itself, and never invents `paid`/`production`/`printing`/`delivery`/`delivered` as a canonical graph. Current/completed presentation is always paired with visible text (e.g. "Current"), never color alone.
**Marker:** none new — a plain, small presentational component.
**Tests:** renders every supplied entry's label (and `timeLabel` when given) in order; a current/completed entry's status is conveyed via visible text, not only a CSS class; renders zero entries gracefully (empty list, no crash); no hardcoded status literal anywhere in the component.

### FVS029-T05 — `OrderList`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/OrderList.tsx` (+test).
**Design:** loading/error/retry/empty/populated states, mirroring `EntitlementList`/`AddressList`'s established shape. Populated state uses the `DownloadHistoryTable` dual-render pattern (`hidden tablet:table` / `tablet:hidden`) for a desktop table vs. mobile stacked cards — no JS viewport detection, no duplicate screen-reader content. Filters are presentational-only this batch: `statusOptions: readonly {value, label}[]` (caller/config-driven, never hardcoded statuses), native `<input type="date">` for `dateFrom`/`dateTo`, and a forward-only `hasNext`/`onNext` cursor seam — **no previous-page control**, since VS-023 only confirms "cursor pagination," not bidirectional support. No fake rows ever rendered.
**Marker:** none new.
**Tests:** loading, error+retry, empty (no fake rows), populated renders every list item; desktop table and mobile card markup both present with the correct CSS-hidden classes; status filter renders only the supplied `statusOptions` (never a hardcoded list); date inputs call `onFiltersChange` with the typed value; `onNext` fires only when `hasNext` is true, and no "Previous" control exists anywhere; no network; no storage.

### FVS029-T06 — `OrderDetail` (incl. T08 Not-Found Boundary)

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/feedback/NotFoundContent.tsx` (extracted, +test), `src/app/not-found.tsx` (updated to reuse it, zero behavior change), `src/components/account/OrderDetail.tsx` (+test).
**Design:** `src/app/not-found.tsx`'s own content is extracted into a new, reusable `NotFoundContent` component — its own prior comment said extraction was YAGNI "no known reuse case yet"; this slice is the second real use case, justifying it now (mirroring this engagement's `DialogShell` extraction precedent). `not-found.tsx` renders `<NotFoundContent />` with **zero change to its own rendered output** — its existing unit test and `e2e/smoke.spec.ts`'s "unknown route" test are re-run **unmodified** to prove this. `OrderDetail` accepts `{result: OrderDetailLoadResult}` where `OrderDetailLoadResult = {kind: "loaded"; order: OrderDetailModel} | {kind: "not-found"}` — there is **no `"forbidden"`/`"forbidden-foreign"` variant anywhere in this type**, a structural guarantee that no consumer could render a distinct "you don't own this order" message even by mistake (`#SECURITY-ORDER-IDOR-HIDING`). The `"not-found"` branch renders the exact same `<NotFoundContent />` the global 404 uses — proven by a dedicated test asserting byte-identical output between a "foreign order" fixture and a "nonexistent order" fixture, both collapsing to `{kind: "not-found"}` before this component ever sees them. The `"loaded"` branch renders a two-column layout (line items via `OrderLineItem` + summary sidebar) on desktop, summary-above-lines stacked on mobile; renders only confirmed-concept summary fields (payment/refund labels, totals) when present on the model, never fabricating a section for an absent one; no current-catalogue fetch anywhere.
**Marker:** `#SECURITY-ORDER-IDOR-HIDING`, `#ARCHITECTURE-ORDER-SNAPSHOT-IMMUTABLE`.
**Tests (`NotFoundContent`):** `not-found.tsx`'s pre-existing 3 tests re-run unmodified and green. **Tests (`OrderDetail`):** renders every line via `OrderLineItem`, each with independent status (mixed physical+STL order); renders the summary's present fields only, omitting absent ones; renders `NotFoundContent`'s exact output for `{kind: "not-found"}`; **a foreign-order fixture and a nonexistent-order fixture (both already reduced to `{kind:"not-found"}` before reaching this component) render identical DOM output** — the core IDOR-hiding proof; renders no "forbidden"/"unauthorized"/"belongs to another" text anywhere, for any input; no current-catalogue fetch/network call.

---

## 6. Deferred / Blocked Tasks (Rationale)

**T07 — URL/filter transport helpers:** Deferred, not blocked on the backend — no literal URL query-parameter example exists for `/account/orders` (unlike FVS-013's own literal `/shop?...` example, the direct evidentiary basis `shopUrlState.ts` relied on). Building a URL-serialization layer now would mean inventing the same kind of key-naming decision without the same evidence. The normalized `OrderListFilters` shape (T02-adjacent, embedded directly in `OrderList`'s props) is the safe stopping point; a URL-state helper can be added once either a literal routing example appears or product/backend confirms the intended filter keys.

**T09 — Real API/query integration:** Blocked — no confirmed response envelope/field names for either endpoint, no confirmed filter/cursor parameter names.

**T10 — `/account/orders` routes + nav + E2E/docs:** Blocked until T09 unblocks. Adding `Orders` to `ACCOUNT_NAV_ITEMS` now would be exactly the dead-link pattern this engagement's own convention forbids.

**T11 — Real backend acceptance:** Blocked on backend availability.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; one `test:e2e` regression run suffices (no new route; `not-found.tsx`'s own extraction must leave its existing E2E assertion green, re-verified explicitly).
- No new runtime dependency.
- No invented order field/status literal/filter-or-cursor query-parameter name, no current-catalogue refetch, no admin/internal field in any customer model, no `/account/orders` route, no account-nav `Orders` entry, no "forbidden" messaging, until the respective gates in §6 unblock.
- Every price/display field on `OrderLineModel`/`OrderDetailModel` is a purchase-time snapshot; nothing in this batch ever re-derives one from a live product/price lookup.
