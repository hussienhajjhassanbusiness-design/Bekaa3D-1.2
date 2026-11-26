# FVS-025 — Shopping Cart (Mixed Physical + STL) — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: HIGH — core purchase funnel.

**Goal:** Build the canonical cart query-key architecture, a normalized cart model, pure invariant helpers (STL quantity lock, ownership precheck), and the full presentational layer — `CartLineItem`, `EmptyCartState`/`LoggedOutCartPrompt`, `CartPage`, `MiniCartDrawer` — while resolving a genuine contradiction in the governing frontend plan about `/cart`'s anonymous-visitor behavior, and correctly deferring all real API integration until the add/update/delete mutation paths are backend-confirmed.

**Architecture:** `cartKeys` (`.root`/`.current()`) is the ONE canonical query key for the single, user-scoped cart resource — `MiniCartDrawer`, `CartPage`, checkout, and the product-page add-to-cart mutation must all share it. `CartModel`/`CartLineModel` are frontend-only presentation shapes holding only the concepts VS-020/FVS-025 actually confirm (merge-on-duplicate, STL qty=1, max quantity, price snapshot vs. current price) — no cart-read totals field is modeled, since neither source confirms the cart-read response carries one. The server remains the sole authority for cart contents/price/availability/quantity (`#SECURITY-CART-SERVER-AUTHORITY`); every presentational seam this batch builds (`onQuantityChange`, `onRemove`) is a callback only, never a real request.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-020 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-025 entry (lines 661-680).

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-020, VS-021 for forward context), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-014/020/025/026 entries, §17), `docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md`, `docs/plans/frontend-slices/FVS-014-IMPLEMENTATION-PLAN.md`, `docs/plans/frontend-slices/FVS-020-IMPLEMENTATION-PLAN.md`, `docs/plans/frontend-slices/FVS-024-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/catalog/{AddToCartButton,PriceDisplay}.tsx`, `src/components/auth/ProtectedRoute.tsx`, `src/lib/auth/returnTo.ts`, `src/lib/entitlements/{entitlementKeys,entitlementModel}.ts`, `src/components/feedback/{DialogShell,ConfirmDialog,EmptyState}.tsx`. Grepped the whole `src/` tree for `cart|Cart|MiniCart|quantity` — **zero existing cart code anywhere**.

**Confirmed by repository evidence:**
- `GET /api/v1/cart` is literal/confirmed (VS-020's own "Endpoint / entrypoint" line). `POST /api/v1/cart/items`, `PATCH /api/v1/cart/items/{item_id}`, `DELETE /api/v1/cart/items/{item_id}` are **frontend-derived placeholders following REST convention, NOT backend-confirmed** — `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own FVS-025 entry says this explicitly in its own endpoints block.
- VS-020's Logic line confirms, at the concept level only: one persistent cart per user; merge duplicate product on add (a normal success, not an error); STL qty=1; reject owned STL; reject unavailable/WhatsApp-only physical; enforce current max quantity; store price snapshot. No field name for any of these is given anywhere.
- **No cart-read totals/subtotal concept is confirmed.** Neither VS-020's Logic/Tests lines nor FVS-025's own UX-states list mentions a cart-level total — totals computation is VS-021/checkout's job ("calculate trusted shipping/free threshold/totals"). This plan therefore does not model a totals field on `CartModel` at all this batch (§1).
- `AddToCartButton` (FVS-014, `src/components/catalog/AddToCartButton.tsx`) already resolves the anonymous-click case: a real anchor to `buildLoginRedirectPath(returnToPath)` (reused, not duplicated). For an authenticated visitor it currently renders `null` — "cart isn't built yet" — confirming FVS-025 is the slice that must eventually give it real content, which stays out of this batch's safe scope (blocked on the mutation contract).

**The `/cart` anonymous-visitor discrepancy (resolved):** `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own FVS-025 entry states BOTH "Routes: `/cart`, wrapped in `ProtectedRoute`" AND, in its UX-states line, "`/cart` itself shows `LoggedOutCartPrompt` rather than a 404/blank page if reached directly." These are **mutually incompatible** given `ProtectedRoute`'s actual, tested implementation (`src/components/auth/ProtectedRoute.tsx`): on confirmed-anonymous it returns `null` and `router.replace()`s to `/login?returnTo=...` — it **never renders its `children`** for an anonymous visitor, so no inline prompt inside the protected page could ever be reached.
- **Resolution adopted:** `/cart` (the route) stays wrapped in the real, unmodified `ProtectedRoute` — an anonymous visit redirects to `/login?returnTo=%2Fcart`, exactly like every `/account/*` page, with **no** inline anonymous content on that page. `LoggedOutCartPrompt` instead belongs to **`MiniCartDrawer`** — the header-mounted mini-cart is not a route and is not behind `ProtectedRoute` (the header renders on every public page regardless of auth state), so it is the one surface that legitimately needs to render an inline anonymous-visitor prompt rather than redirecting away from whatever page the visitor is currently on.
- This is recorded as a genuine inconsistency in the governing frontend plan, not silently "corrected" without comment — `ProtectedRoute`'s existing, tested, security-relevant redirect-only behavior is left completely unmodified (`#SECURITY` note in §5).

**What is genuinely unconfirmed:** the exact add/update/delete endpoint paths and bodies; the cart response envelope/field names (id, item id, product id/type/name, quantity, max quantity, snapshot/current price, currency, totals, server messages); the owned-STL/unavailable/WhatsApp-only/max-quantity rejection status codes; whether the backend auto-removes an unavailable line or flags it in place; whether cart read requires verified email.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Read** | `GET /api/v1/cart` path | **CONFIRMED** (literal) |
| **Read** | Response envelope / field names | **NEEDS BACKEND CONFIRMATION** |
| **Read** | Cart-level totals/subtotal | **UNCONFIRMED — not modeled this batch** |
| **Add/Update/Delete** | Endpoint paths | **NEEDS BACKEND CONFIRMATION** — frontend placeholders only |
| **Invariants** | One cart/user, no guest cart | **CONFIRMED** (VS-020 Model/Logic lines) |
| **Invariants** | STL qty fixed at 1 | **CONFIRMED** (concept only, no field name) |
| **Invariants** | Merge-on-duplicate-add is success, not error | **CONFIRMED** (concept only) |
| **Invariants** | Server owns max quantity / price snapshot | **CONFIRMED** (concept only) |
| **Auth** | `/cart` route behavior | **RESOLVED by this plan** — see §0 |
| **Ownership precheck** | `EntitlementModel` exposes a product id to match against a cart line | **GAP FOUND** — it does not (§5) |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Canonical cart query keys + normalized cart model | **CAN IMPLEMENT NOW** |
| T02 | Pure cart invariant helpers | **CAN IMPLEMENT NOW** |
| T03 | `CartLineItem` presentation | **CAN IMPLEMENT NOW** |
| T04 | `LoggedOutCartPrompt`; `EmptyCartState` folded into reusing `EmptyState` directly | **CAN IMPLEMENT NOW** |
| T05 | `CartPage` presentation | **CAN IMPLEMENT NOW** (not mounted to a route) |
| T06 | `MiniCartDrawer` presentation (+ minimal `DialogShell` extension) | **CAN IMPLEMENT NOW** |
| T07 | Optimistic update/rollback helpers | **CAN IMPLEMENT NOW** |
| T08 | Real API/query/mutations | **BLOCKED ON BACKEND CONTRACT** |
| T09 | `/cart` route + header integration | **BLOCKED** until T08 unblocks (architecture now resolved, contract still isn't) |
| T10 | Integration/E2E/docs | **BLOCKED** — no real route exists to exercise end-to-end |
| T11 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01–T07. T08–T11 are each blocked for a distinct, documented reason.

---

## 4. Backend Questions For Tomorrow

**Read:** 1. Exact `GET /cart` response envelope. 2. Cart id field? 3. Exact item schema. 4. Item id field. 5. Product id field. 6. Product-type field/literals. 7. Display name field. 8. Thumbnail field. 9. Quantity field. 10. Max-quantity field. 11. Snapshot-price field. 12. Current-price field. 13. Currency field. 14. How is an unavailable item represented — flagged in place, or removed with a separate signal? 15. Are totals returned at all? 16. Cart version/concurrency field?

**Add:** 17. Exact endpoint. 18. Exact body. 19. Quantity field. 20. Duplicate-add merge semantics (response on merge vs. fresh add). 21. Success status/body. 22. Owned-STL rejection status/code. 23. Unavailable-physical rejection. 24. WhatsApp-only rejection. 25. Max-quantity rejection. 26. CSRF/auth requirements.

**Update:** 27. Exact endpoint/body. 28. Absolute quantity or delta? 29. Success response. 30. Cap-changed-since-page-load conflict semantics.

**Delete:** 31. Exact endpoint. 32. Success response.

**Price/availability:** 33. Exact snapshot semantics. 34. How a price-changed line is represented in the read response. 35. How an item-becomes-unavailable transition is represented. 36. Does the server auto-remove invalid items? 37. Does the response include an explanatory reason string?

**Auth:** 38. Independently confirm `/cart`'s anonymous behavior matches this plan's resolution (redirect via `ProtectedRoute`, no inline content) — not contradicted by a future product decision. 39. Is verified email required to read the cart? 40. Is verified email required to mutate it?

**Ownership:** 41. Exact server-side ownership-check timing relative to add. 42. Already-owned error contract. 43. Can a user legitimately own an STL and still have a stale cart line for it (e.g., granted after adding)? 44. Does `GET /me/entitlements` (or a future adapter over it) expose a product id the frontend can match against a cart line's product id — needed to wire `canAddStlGivenOwnership` for real (§5 gap).

**Testing:** 45. Disposable verified customer. 46. Physical product fixture. 47. STL product fixture. 48. Already-owned STL fixture. 49. Quantity-cap fixture. 50. Price-change fixture. 51. Unavailable-item fixture.

---

## 5. Task Detail (Safe Batch)

### FVS025-T01 — Canonical Cart Query Keys + Normalized Model

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/cart/cartKeys.ts` (+test), `src/lib/cart/cartModel.ts` (+test).
**Design:** `cartKeys = {root: ["cart"], current: () => [...root, "current"]}` — `.current()`, not `.list()`/`.detail(id)`: there is exactly one cart per user (like `publicSettingsKeys`'s precedent for a singleton resource). `CartLineModel {id, productId, productDisplayName, productType: "physical" | "stl", quantity, maxQuantity?, snapshotPriceCents, currentPriceCents?, currency, thumbnailSrc?}`; `CartModel {id, lines: readonly CartLineModel[]}` — deliberately no availability/unavailable field on the line type (§0: the backend's unavailable-line mechanism — flag vs. removal — is unconfirmed) and no totals field on the cart type (§0/§1).
**Marker:** `#ARCHITECTURE-CANONICAL-CART-QUERY`, `#ARCHITECTURE-CART-ADAPTER`.
**Tests:** query-key stability/derivation (mirrors `publicSettingsKeys.test.ts`); model type-only tests (RED-confirmed via `tsc`) proving no availability/totals/storage field exists on either type.

### FVS025-T02 — Pure Cart Invariant Helpers

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/cart/cartInvariants.ts` (+test).
**Design:** `isStlLine(line)`, `canAdjustQuantity(line)` (physical only — STL always returns `false`, enforcing the fixed-qty-1 UI rule with no stepper ever rendered for an STL line), `hasPriceChanged(line)` (`currentPriceCents` present and different from `snapshotPriceCents`), `canAddStlGivenOwnership(productId, ownedProductIds: ReadonlySet<string>)` — a pure UX-only precheck, explicitly documented as never a security boundary.
**Found integration gap (recorded, not solved):** `canAddStlGivenOwnership`'s logic is buildable and tested in isolation against an arbitrary `ownedProductIds` set, but **cannot be wired against the real `EntitlementModel`** (`src/lib/entitlements/entitlementModel.ts`) — that model has no `productId` field, only `id`/`productDisplayName`/`thumbnailSrc`/`currentVersionLabel`. Wiring this precheck for real requires either a confirmed `productId` field on the entitlement model or a different backend ownership signal (§4 Q44) — not invented here.
**Marker:** `#SECURITY-CART-SERVER-AUTHORITY` — every helper here is explicitly documented as a UX nicety; a stale/incomplete client cache must never be treated as authorization, and the server is the final word regardless of what these helpers return.
**Tests:** `isStlLine`/`canAdjustQuantity` for both product types; `hasPriceChanged` true/false/undefined-current-price cases; `canAddStlGivenOwnership` true/false cases against a plain `Set<string>`.

### FVS025-T03 — `CartLineItem`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/cart/CartLineItem.tsx` (+test).
**Design:** `{line: CartLineModel, onQuantityChange: (lineId, nextQuantity) => void, onRemove: (lineId) => void, unavailableNotice?: string}` — required callback seams (mirroring `AddressList.onDelete`/`ShippingZoneManager.onArchive`'s precedent: presentational now, wired to a real mutation only once T08 unblocks). Physical lines render accessible increment/decrement buttons (`aria-label` includes the product name, e.g. "Increase quantity of Garden Gnome") with the current quantity in an `aria-live="polite"` region; increment disabled once `quantity >= maxQuantity` (only enforced client-side as a UI nicety when `maxQuantity` is supplied — server remains authoritative regardless). STL lines render a fixed "Qty: 1" with no stepper at all. `hasPriceChanged` lines show both the original (`PriceDisplay`, reused) and current price plus a "Price updated" note — never silently replacing one with the other. `unavailableNotice`, when supplied, renders as a `role="alert"` paragraph — a caller-supplied string, never a hardcoded/invented backend enum. Remove is always available on both line types.
**Marker:** `#FVS025-CART-LINE-ITEM`.
**Tests:** physical renders a working stepper with accessible names and announces quantity changes; STL renders fixed qty with no stepper controls at all; increment disabled at `maxQuantity`; `hasPriceChanged` shows both prices and the note; no note when prices match or `currentPriceCents` is absent; `unavailableNotice` renders as an alert when supplied, absent otherwise; Remove calls `onRemove` with the exact line id; reuses `PriceDisplay` (no duplicated currency formatting).

### FVS025-T04 — `LoggedOutCartPrompt`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/cart/LoggedOutCartPrompt.tsx` (+test).
**Design:** `{returnToPath?: string}` (default `"/cart"`) — a real anchor to `buildLoginRedirectPath(returnToPath)` (reused from FVS-003, never a duplicated redirect-safety implementation), labeled "Log in." No guest-cart affordance of any kind. `EmptyCartState` is **not** built as a separate component — `src/components/feedback/EmptyState.tsx` already fits exactly (message-only, no fake recommendations); `CartPage` (T05) reuses it directly.
**Marker:** `#FVS025-LOGGED-OUT-CART-PROMPT`.
**Tests:** renders a real link with the exact `buildLoginRedirectPath` href for the default and a custom `returnToPath`; no form, no guest-cart action of any kind; no network.

### FVS025-T05 — `CartPage`

**Status:** CAN IMPLEMENT NOW (not mounted to a route — T09 blocked). **Files:** `src/components/cart/CartPage.tsx` (+test).
**Design:** loading/error/retry/empty (`EmptyState`, reused, no fake recommendations)/populated states, mirroring `AddressList`/`EntitlementList`'s established shape. Populated state renders a `CartLineItem` per line; no summary/totals area is built this batch (§0/§1 — no confirmed cart-read totals concept to display); no Checkout button or link anywhere (`/checkout` doesn't exist yet — the dead-link rule applies exactly as in FVS-022).
**Marker:** `#FVS025-CART-PAGE`.
**Tests:** loading, error+retry, empty (`EmptyState`, no fake recommendations), populated renders every line, no Checkout link/button anywhere, no network, no storage.

### FVS025-T06 — `MiniCartDrawer`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/feedback/DialogShell.tsx` (minimal extension), `src/components/cart/MiniCartDrawer.tsx` (+test).
**Design:** `DialogShell` gains one new optional prop, `panelClassName?: string` (defaults to its exact existing centered-modal classes, so every current caller — `ConfirmDialog`, `GrantEntitlementDialog` — is byte-for-byte unaffected) — replacing the inner panel's class list when supplied, so a caller's own `fixed`-positioned classes can escape the backdrop's centering flexbox entirely rather than requiring a second focus-trap implementation. `MiniCartDrawer` supplies a responsive drawer/bottom-sheet `panelClassName` (bottom sheet on mobile, right-side slide-over at `tablet:`+) and composes `DialogShell` directly — zero new focus-trap code. Anonymous state renders `LoggedOutCartPrompt`; authenticated state renders cart lines once real data exists (presentational seam only this batch — accepts the same `CartModel`/loading/error shape `CartPage` does).
**Marker:** `#FVS025-MINI-CART-DRAWER`.
**Tests (DialogShell):** existing `DialogShell.test.tsx` suite re-run **unmodified** and green; new test confirms a supplied `panelClassName` replaces the default panel classes; new test confirms omitting it preserves the exact existing default. **Tests (MiniCartDrawer):** renders `LoggedOutCartPrompt` when anonymous; renders cart lines when authenticated data is supplied; reuses `DialogShell`'s real focus-trap/Escape/backdrop (proven by checking the real `role="dialog"`/`aria-modal` attributes are present, not a second implementation); responsive panel classes present for both breakpoints.

### FVS025-T07 — Optimistic Update/Rollback Helpers

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/cart/cartOptimistic.ts` (+test).
**Design:** mirrors FVS-023's `addressDefaultOptimistic.ts` precedent exactly. `beginQuantityChange(cart, lineId, nextQuantity)`, `beginRemoval(cart, lineId)`, `rollback(previousSnapshot)`, `settle(authoritative)` — `settle` always adopts the authoritative cart verbatim, never the optimistic guess. STL lines are structurally prevented from having their quantity changed by this helper (mirrors T02's `canAdjustQuantity`) — calling `beginQuantityChange` on an STL line is a no-op returning the unchanged cart, never silently "succeeding" with a wrong quantity. No endpoint, body, or status code is invented; no float money mutation anywhere (cents stay integers throughout).
**Marker:** none new — same architectural pattern as `#ARCHITECTURE-ADDRESS-ADAPTER`'s optimistic sibling, no new marker needed for a repeated pattern.
**Tests:** quantity optimistic update (physical); rollback restores the exact previous snapshot; removal optimistic update; rollback restores after a failed removal; `settle` replaces optimistic state with the authoritative cart verbatim, even when it disagrees with the optimistic guess; attempting a quantity change on an STL line is a no-op; no cents value is ever produced via float arithmetic.

---

## 6. Deferred / Blocked Tasks (Rationale)

**T08 — Real API/query/mutations:** Blocked — no confirmed request/response body for any cart mutation; `GET /cart`'s own response envelope is also unconfirmed.

**T09 — `/cart` route + header integration:** Blocked until T08 unblocks. The *architecture* question (§0's resolved discrepancy) is settled, but mounting a real route and wiring the header's `MiniCartDrawer` to a live query both require the actual contract.

**T10 — Integration/E2E/docs:** Blocked — no real route exists yet to exercise end-to-end.

**T11 — Real backend acceptance:** Blocked on backend availability.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; one `test:e2e` regression run suffices (no route/page work this batch).
- No new runtime dependency.
- No real cart API call, no guessed mutation paths/bodies/status codes, no guest cart, no `localStorage` cart mirror, no client-authoritative totals, no `/cart` route, no header `MiniCartDrawer` production mounting, until the respective gates in §6 unblock.
- `ProtectedRoute` (`src/components/auth/ProtectedRoute.tsx`) is reused completely unmodified — its redirect-only anonymous behavior is the real security boundary for `/cart` and must never be weakened.
