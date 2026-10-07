# FVS-024 — Admin Shipping Zone Management — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch.

**Goal:** Build the canonical shipping-zone query-key architecture and normalized admin/public models, plus a focused, presentational `ShippingZoneManager` that reuses `MoneyInput` (editing) and `PriceDisplay` (display) for cents-safe, never-hardcoded-currency rate handling — while correctly deferring everything that needs a confirmed admin endpoint contract or the (still-nonexistent) admin route shell.

**Architecture:** `shippingZoneKeys` (`.root`/`.adminList()`/`.publicList()`) is the ONE canonical query-key family for the shipping-zone resource, shared by this slice's admin management and FVS-026's future checkout zone-picker. `ShippingZoneAdminModel`/`ShippingZoneOption` are frontend-only presentation shapes — no backend field name, no hardcoded currency, no min/max rate rule invented. `ShippingZoneManager` is a focused component (not a forced extension of `ReferenceDataManager`, since money semantics don't fit its string-only draft shape) using the exact same stacked-card/inline-form/`ConfirmDialog`-archive pattern already established. The server remains the sole shipping-rate authority (`#SECURITY-SERVER-SHIPPING-RATE-AUTHORITY`); V1 has no automatic address-to-zone mapping (`#ARCHITECTURE-EXPLICIT-SHIPPING-ZONE`); archiving a zone never touches a past order's immutable snapshot (`#ARCHITECTURE-SHIPPING-SNAPSHOT-IMMUTABLE`).

**Spec:** `vertical-slice-plan.md`'s VS-019 entry (shipping-zone half) and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-024 entry (lines 634-653).

---

## 0. Repository / Contract Audit

Read: `vertical-slice-plan.md` (VS-019, §17's "Shipping-zone response shape" gap, §2's "Confirm USD settlement/support" open item, §13's "Money uses integer cents" global rule), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-024 entry, §14 responsive patterns), `FVS-007-IMPLEMENTATION-PLAN.md`, `FVS-010-IMPLEMENTATION-PLAN.md`, `FVS-011-IMPLEMENTATION-PLAN.md`, `FVS-023-IMPLEMENTATION-PLAN.md`, `FVS-005-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/components/admin/ReferenceDataManager.tsx`/`referenceDataTypes.ts`, `src/components/forms/MoneyInput.tsx`, `src/components/catalog/PriceDisplay.tsx`, `src/components/feedback/{DialogShell,ConfirmDialog}.tsx`, `src/lib/admin/`, `src/lib/settings/`. Confirmed via directory listing that **`src/app/admin/` does not exist at all** — no admin route, layout, or `AdminProtectedRoute` has ever been mounted in this repository. Grepped the whole `src/` tree for `ShippingZone|shippingZone|shipping-zone` — the only hits are FVS-023's own negative-space assertions ("never renders zone/rate information") — **zero existing shipping-zone code anywhere**.

**Confirmed by repository evidence:**
- VS-019's own "Endpoint / entrypoint" line gives `GET /api/v1/shipping-zones` (literal) and, separately, only the prose "admin shipping-zone CRUD" — no literal admin paths anywhere in the backend plan. `FRONTEND-VERTICAL-SLICE-PLAN.md`'s own FVS-024 entry independently flags this exact gap: *"VS-019's admin half is prose only... placeholders above, `NEEDS BACKEND CONFIRMATION`, §17."* The four admin paths this task lists (`GET`/`POST`/`PATCH /api/v1/admin/shipping-zones...`) are therefore **frontend-derived placeholders, not backend-confirmed**, in sharp contrast to the public `GET /api/v1/shipping-zones` path, which **is** literal.
- `vertical-slice-plan.md`'s own §17 "Shipping-zone response shape" gap entry states plainly: *"What is missing: Exact field names/shape of a shipping-zone object."* No field name (name, rate, currency, active flag) is confirmed anywhere — only that FVS-024/026 will need something like them.
- Global, confirmed rules apply regardless of this slice's own gaps: "Money uses integer cents" (vertical-slice-plan.md §13) and server-side rate/shipping authority (VS-019 Logic line: "rates server-owned"; VS-019 Tests line: "no automatic governorate mapping").
- **No admin route infrastructure exists at all.** `FVS-005-IMPLEMENTATION-PLAN.md` (admin MFA / `AdminProtectedRoute`) itself remains blocked on backend MFA contract confirmation — confirmed by reading its own plan, which lists `AdminProtectedRoute`/layout boundary as still **BLOCKED**. Every prior admin slice (`FVS-007`, `FVS-010`) independently recorded the identical blocker for its own `/admin/*` route. This is **not a new, slice-specific gate** — it is the same long-standing cross-cutting FVS-005 dependency every admin slice has hit, recorded here without reopening or re-litigating FVS-005 itself.
- `MoneyInput` (`src/components/forms/MoneyInput.tsx`) and `PriceDisplay` (`src/components/catalog/PriceDisplay.tsx`) both already take a required, non-defaulted `currencyLabel`/`currency` string — exactly the "never hardcode USD/LBP" shape this slice needs; both are directly reusable with zero modification.
- `ReferenceDataManager`'s draft/config shape (`referenceDataTypes.ts`) is **string-only** (`swatchValue?: string`) — money needs a numeric cents value with `MoneyInput`'s own parse/error state, which does not fit that shape without an invasive, risky change to a widely-reused shared component. Per the task's own explicit permission ("do not force an abstraction merely to satisfy wording"), this plan builds a focused `ShippingZoneManager` instead, reusing the exact same responsive/editor/archive **pattern**, not the component itself.

**What is genuinely unconfirmed:** every admin shipping-zone endpoint's exact path/body/status; the exact `ShippingZoneRead` field names (id, name/label, rate, currency, active/archive flag, ordering); whether currency is global or per-zone; min/max rate constraints (if any); archive mechanism (dedicated endpoint vs. `PATCH` field); whether an archived zone can be restored; whether a zone referenced by an active order can be archived.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Admin** | List/create/update/archive endpoint paths | **NEEDS BACKEND CONFIRMATION** — prose-only in VS-019, frontend-derived placeholders only |
| **Public** | `GET /api/v1/shipping-zones` path | **CONFIRMED** (literal) |
| **Public** | Response fields/shape | **NEEDS BACKEND CONFIRMATION** — VS-019's own §17 gap entry |
| **Model** | `ShippingZoneRead` field names (id/name/rate/currency/active) | **UNCONFIRMED — none repeated as fact** |
| **Money** | Integer cents | **CONFIRMED** (global rule, vertical-slice-plan.md §13) |
| **Money** | Currency (global vs. per-zone, exact code) | **NEEDS BACKEND/PRODUCT CONFIRMATION** — "Confirm USD settlement/support" is an explicitly open external item |
| **Authority** | Server owns shipping-rate computation | **CONFIRMED** (VS-019 Logic line) |
| **Zone selection** | No automatic address/governorate mapping in V1 | **CONFIRMED** (VS-019 Logic + Tests lines) |
| **Order snapshot** | Archiving/editing a zone never changes a past order's snapshot | **CONFIRMED as a product rule** (FVS-024's own "API integration" line); no literal backend mechanism confirmed |
| **Admin shell** | `/admin/*` route + `AdminProtectedRoute` | **BLOCKED ON FVS-005** (pre-existing, cross-cutting, not reopened here) |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Canonical shipping-zone query keys + normalized admin/public models | **CAN IMPLEMENT NOW** |
| T02 | Rate field presentation using `MoneyInput` | **Folded into T03** — `MoneyInput`'s existing API already fits directly; a one-line pass-through wrapper adds no value |
| T03 | `ShippingZoneManager` presentation (incl. archive confirmation) | **CAN IMPLEMENT NOW** |
| T04 | Archive confirmation presentation | **Folded into T03** (same inline `ConfirmDialog` pattern as `ReferenceDataManager`/`AddressList`) |
| T05 | Public checkout-zone option model | **Folded into T01** — model only, no selection UI (that belongs to FVS-026) |
| T06 | Real admin/public API adapters | **BLOCKED ON CONTRACT** |
| T07 | `/admin/shipping-zones` route | **BLOCKED ON FVS-005 (no admin shell exists) + T06** |
| T08 | Integration/accessibility review | Covered inline in T03's own test suite this batch |
| T09 | E2E/docs | **BLOCKED** — no real route exists to exercise end-to-end |
| T10 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01 (incl. T05) and T03 (incl. T02/T04). T06/T07/T09/T10 are each blocked for a distinct, documented reason.

---

## 4. Backend Questions For Tomorrow

**Endpoints:** 1. Exact admin shipping-zone list endpoint. 2. Exact create endpoint. 3. Exact update endpoint. 4. Exact archive mechanism (dedicated endpoint, or a `PATCH` field?). 5. Independently re-confirm the public `GET /api/v1/shipping-zones` path (already literal in VS-019, but its *response* is not).

**Model:** 6. Exact `ShippingZoneRead` schema. 7. Exact id field/type. 8. Name/label field. 9. Rate-cents field name. 10. Currency field (present at all, or implied globally?). 11. Archive/active field name. 12. Created/updated timestamps, if any. 13. Ordering.

**Money:** 14. Is rate always integer cents (strongly implied by the global rule, but not independently re-confirmed for this specific resource)? 15. Is currency global across the app or set per zone? 16. Exact currency code (`USD` remains an explicitly open external item per vertical-slice-plan.md §2). 17. Can a rate be zero (free shipping to a zone)? 18. Any min/max constraint? 19. Decimal/rounding rule beyond the already-established 2-decimal-max `MoneyInput` behavior.

**Create:** 20. Exact request body. 21. Required fields. 22. Success status/body. 23. CSRF/admin-session requirement (same project-wide mechanism, or anything zone-specific?). 24. Duplicate-name behavior.

**Update:** 25. Exact `PATCH` body. 26. Partial or full update? 27. Can rate and name change while a zone is active/in use? 28. Success status/body. 29. Concurrency behavior.

**Archive:** 30. Exact archive mutation. 31. Can an archived zone be restored? 32. Can a zone referenced by an active order be archived? 33. Independently confirm existing order snapshots never change as a result. 34. Any warning/confirmation metadata returned by the API itself?

**Public:** 35. Exact public-list response shape. 36. Confirm archived zones are excluded server-side (never sent to the frontend at all). 37. Exact fields exposed to checkout (same as admin, or a subset?). 38. Ordering. 39. Any caching guidance. 40. Are the returned rates directly, authoritatively displayable with no frontend adjustment?

**Checkout relationship:** 41. Independently re-confirm explicit zone selection at checkout (already strongly implied by VS-019). 42. Re-confirm no address/governorate auto-mapping in V1. 43. Can checkout choose any active zone, or are there eligibility rules? 44. Does the backend re-validate the selected zone independently at order-placement time?

**Testing:** 45. Disposable admin fixture (blocked transitively on FVS-005). 46. Create-zone fixture/procedure. 47. Archive-zone fixture/procedure. 48. Public-list acceptance check. 49. FVS-026 checkout-visibility cross-check procedure.

---

## 5. Task Detail (Safe Batch)

### FVS024-T01 — Canonical Shipping-Zone Query Keys + Normalized Models

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/shippingZones/shippingZoneKeys.ts` (+test), `src/lib/shippingZones/shippingZoneModels.ts` (+test).
**Design:** `shippingZoneKeys = {root: ["shippingZones"], adminList: () => [...root,"adminList"], publicList: () => [...root,"publicList"]}` — one shared root distinguishes the admin and public reads of the same underlying resource without inventing two unrelated caches; no page/filter argument is baked in (pagination/filter contract unconfirmed). `ShippingZoneAdminModel {id, displayName, rateCents, currency, isArchived}` and `ShippingZoneOption {id, displayName, rateCents, currency}` (T05 folded in — public option has no `isArchived` field at all, matching FVS-020's "the backend excludes revoked rows entirely, so there's nothing to hide" precedent: if the public endpoint never sends archived zones, there is nothing for this model to filter or badge). Neither type claims a backend field name; `currency` is always a required, caller-supplied string, never defaulted to `"USD"`/`"LBP"` anywhere.
**Marker:** `#ARCHITECTURE-CANONICAL-SHIPPING-ZONES`, `#ARCHITECTURE-SHIPPING-ZONE-ADAPTER`, `#ARCHITECTURE-EXPLICIT-SHIPPING-ZONE`.
**Tests:** query-key stability/derivation for both `adminList()`/`publicList()`, distinguishable from each other and the root (mirrors `addressKeys.test.ts`); model type-only tests (RED-confirmed via `tsc`) proving no hardcoded currency literal, no `archived` field on the public option, and no governorate/address field on either model.

### FVS024-T03 — `ShippingZoneManager`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/ShippingZoneManager.tsx` (+test).
**Design:** A focused component (not a forced `ReferenceDataManager` extension — see §0's rationale), using the exact same responsive stacked-card pattern (`flex-col` below `tablet:`, `flex-row` at `tablet:`+) and the exact same inline-form/`ConfirmDialog`-archive composition `ReferenceDataManager` and `AddressList` already use. Create/edit form: a `TextField` for `displayName` plus `MoneyInput` directly (T02 folded in — `label="Rate"`, `currencyLabel={currency}`, `valueCents`/`onChangeCents`) for the rate — no separate rate-field wrapper component. List view: each zone's rate rendered via `PriceDisplay` (`amountCents={zone.rateCents} currency={zone.currency}`), never a second, duplicated currency-formatting routine. Archive (never "Delete," matching the product's archive — not hard-delete — semantics) reuses `ConfirmDialog` inline (T04 folded in), with `onArchive(zoneId)` firing only after confirmation. `currency` is a required prop supplied by the caller (no currency picker UI — no evidence any exists yet); `rateCents` accepts `0` (a free-shipping zone) without any invented minimum.
**Marker:** `#FVS024-SHIPPING-ZONE-MANAGER`, `#SECURITY-SERVER-SHIPPING-RATE-AUTHORITY` (this component only displays/edits values the server will authoritatively validate — it never computes a price, a zone match, or a free-shipping decision itself), `#ARCHITECTURE-SHIPPING-SNAPSHOT-IMMUTABLE` (comment-only: archiving/editing a zone here never touches a past order's immutable snapshot — this component has no order-related code at all).
**Tests:** loading, empty, populated (every zone's `displayName` and rate via `PriceDisplay` rendered, using the exact caller-supplied `currency`, never a hardcoded one), create/edit form uses `MoneyInput` (proven by the same cents-safe behavior `MoneyInput.test.tsx` already covers — this test only proves composition, not re-testing `MoneyInput` itself), zero-rate accepted, archive opens `ConfirmDialog` then calls `onArchive` with the exact target id only after confirming, cancel never calls `onArchive`, never renders "Delete," no network, no storage, no shipping-price/zone-matching computation anywhere in the component.

---

## 6. Deferred / Blocked Tasks (Rationale)

**T06 — Real admin/public API adapters:** Blocked — no confirmed request/response body for any admin shipping-zone operation; the public response shape is also unconfirmed (§0/§1's §17 citation).

**T07 — `/admin/shipping-zones` route:** Blocked on two independent gates: (1) the admin API contract (T06), and (2) the pre-existing, cross-cutting FVS-005 gate — no admin route shell/`AdminProtectedRoute` exists anywhere in this repository yet, a blocker every prior admin slice (`FVS-007`, `FVS-010`) already recorded independently. Not reopened or re-litigated here.

**T09 — Integration/E2E/docs:** Blocked — no real route exists yet to exercise end-to-end; this batch's coverage stays at the unit/component level.

**T10 — Real backend acceptance:** Blocked on backend availability.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; one `test:e2e` regression run suffices (no route/page work this batch).
- No new runtime dependency.
- No invented admin endpoint path/body, no hardcoded currency, no floating-point money conversion (`parseFloat(value) * 100` or equivalent), no invented min/max rate, no governorate/address-to-zone mapping, no frontend-computed shipping price, no production API call, no `/admin/shipping-zones` route, until the respective gates in §6 unblock.
- No duplicated money-parsing or currency-formatting logic — `MoneyInput` and `PriceDisplay` are reused exactly as they already exist, unmodified.
