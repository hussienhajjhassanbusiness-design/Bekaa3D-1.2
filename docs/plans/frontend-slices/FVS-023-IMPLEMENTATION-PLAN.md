# FVS-023 — Customer Address Book — Implementation Plan

> **Superseded by Phase 5B (2026-11-10/11).** This plan predates the real backend contract. Every "unconfirmed" item below is now confirmed by the current `openapi.json` (backend `2dfb27b`): the real fields are `label, recipient_name, phone, governorate (9-value enum), city, area|null, street|null, landmark_notes, is_default`; the default switch is `PUT /me/addresses/{id}/default` (or `PATCH is_default`); delete is a soft delete that promotes no new default; the list is hard-capped (20), not paginated. T04–T10 are done; see `docs/backend-handoff/REAL-BACKEND-ACCEPTANCE.md` (Phase 5B). `DefaultAddressSelector` and `addressDefaultOptimistic` remain unmounted: the address book uses per-card "Set as default" plus a server refetch instead.

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch.

**Goal:** Give the customer account area the presentation layer for a saved-address book — canonical query-key architecture, a normalized address model that claims nothing about the real backend schema, list/card presentation, and a properly-accessible single-choice "default address" selector — while correctly deferring `AddressForm` and everything downstream of it, since essentially no individual address field is confirmed anywhere in the repository.

**Architecture:** `addressKeys` (`.root`/`.list()`/`.detail(id)`) is the ONE canonical TanStack Query key family for the address resource, documented as the key FVS-026 checkout must reuse/invalidate rather than inventing a checkout-local address cache. `AddressModel` is a frontend-only presentation shape (`{id, displayLines, isDefault}`) — never a claim about `AddressRead`'s real field names, since none are confirmed. `DefaultAddressSelector` is a real `fieldset`/radio-group (never independent checkboxes), separate from `AddressCard`'s own content/delete actions. A pure `addressDefaultOptimistic` helper models the optimistic-then-server-truth lifecycle the product requires, without any real mutation/endpoint code. Zone selection is explicitly out of scope — nothing here infers, stores, or references a shipping zone (`#ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE`).

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-019 entry (address half) and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-023 entry (lines 608-627).

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-019, §17's "Shipping-zone response shape" gap), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-023/024 entries, §14 responsive patterns, §17), `docs/setup/frontend-setup.md` (account nav/shell conventions), `docs/plans/frontend-slices/FVS-020-IMPLEMENTATION-PLAN.md` (`entitlementKeys`/`entitlementModel` precedent). Inspected `src/components/account/` (`EntitlementList.tsx`, `EntitlementCard.tsx`, `AccountLayout.tsx`, `accountNavItems.ts`), `src/components/feedback/DialogShell.tsx`/`ConfirmDialog.tsx`, `src/components/admin/StatusBadge.tsx`. Grepped the entire `src/` tree for `address|Address|governorate|shipping.?zone` — only incidental matches ("email address") exist; **zero existing address-book code anywhere**.

**Confirmed by repository evidence:**
- VS-019's own "Endpoint / entrypoint" line gives `/api/v1/me/addresses*` (a wildcard, not four individually spelled-out paths) and, separately, `GET /api/v1/shipping-zones` (FVS-024's concern, not this one). `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-023 entry independently expands that wildcard into the four literal method/path pairs (`GET`/`POST /api/v1/me/addresses`, `PATCH`/`DELETE /api/v1/me/addresses/{id}`) — a reasonable, standard REST expansion of the backend's own wildcard notation, not a second independent backend confirmation. Treated as **CONFIRMED at the resource/verb level**; the literal `{id}` path shape is the conventional (near-certain, but not independently backend-spelled) expansion of that wildcard.
- VS-019's Logic line confirms, at the **concept** level only: "Own address book; one default; explicit active-zone selection; rates server-owned... free-shipping threshold read from Setting" and its Tests line confirms "Default switching; ownership;... no automatic governorate mapping". This is the explicit textual basis for `#ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE`.
- **No individual address field name is confirmed anywhere.** VS-019 says only "Address CRUD/default schemas" — a generic phrase, not a field list. `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-023 entry never lists field names either. This is the single most important audit finding for this slice: `name`/`phone`/`street`/`city`/`governorate`/`postalCode`/`country`/`building`/`floor`/`landmark` are **all UNCONFIRMED** — none is repeated here as fact.
- The default-mechanism's exact transport (a plain `PATCH` with some boolean field vs. a dedicated action) is nowhere specified. VS-019 only asserts the product behavior ("one default... server-authoritative").
- Delete behavior (hard delete vs. archive, delete-default promotion rule, order-reference handling) is nowhere specified.
- `ACCOUNT_NAV_ITEMS` (`src/components/account/accountNavItems.ts`) still contains only `Profile` — confirmed via direct read; `docs/setup/frontend-setup.md`'s own account-navigation section explicitly names "Addresses" as a future entry added "as its own route lands," never ahead of time.
- `DialogShell`/`ConfirmDialog` (FVS-007/FVS-019) are reusable as-is for a future create/edit dialog and for delete confirmation respectively — no change needed to either this batch.
- `StatusBadge` (`{label, tone}`, generalized in FVS-017) is directly reusable for a "Default" indicator — no new badge component needed.

**What is genuinely unconfirmed:** the exact `AddressRead`/`AddressCreate`/`AddressUpdate` schemas (every field); the list response envelope/pagination/ordering; the exact default-indicator field name and default-mutation mechanism; delete semantics (hard vs. soft, default-promotion, order-reference); CSRF/validation-error shape (same mechanism as every other mutating endpoint in this app, but not independently re-confirmed here).

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Endpoints** | Resource/verb set (`/me/addresses*`) | **CONFIRMED** (literal wildcard) |
| **Endpoints** | Exact `{id}` path shape for PATCH/DELETE | Standard REST expansion of the wildcard — **treated as confirmed**, not independently backend-spelled |
| **List** | Response envelope / pagination / ordering | **NEEDS BACKEND CONFIRMATION** |
| **List** | Address id field/type | **NEEDS BACKEND CONFIRMATION** |
| **Fields** | Every individual address field (name/phone/street/city/governorate/postal/country/etc.) | **UNCONFIRMED — none repeated as fact** |
| **Default** | Exact mutation mechanism (field name, PATCH vs. dedicated action) | **NEEDS BACKEND CONFIRMATION** |
| **Default** | Concept: exactly one default, server-authoritative | **CONFIRMED** (VS-019 Logic line) |
| **Delete** | Hard delete vs. archive; default-promotion; order-reference handling | **NEEDS BACKEND CONFIRMATION** |
| **Zone separation** | No automatic governorate→zone mapping in V1 | **CONFIRMED** (VS-019 Logic + Tests lines) |
| **Account nav** | `Addresses` entry | **CORRECTLY WITHHELD** — no real route exists yet |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Canonical address query keys + normalized address model | **CAN IMPLEMENT NOW** |
| T02 | `AddressCard` / `AddressList` presentation (incl. delete confirmation) | **CAN IMPLEMENT NOW** |
| T03 | `DefaultAddressSelector` (radio-group presentation) | **CAN IMPLEMENT NOW** |
| — | Pure optimistic default-address state helper | **CAN IMPLEMENT NOW** |
| T04 | `AddressForm` | **CORRECTLY DEFERRED — no confirmed field matrix** |
| T05 | Create/edit dialog composition | **BLOCKED — depends on T04** |
| T06 | Delete confirmation presentation | **Folded into T02** (same pattern `ReferenceDataManager` uses for its own inline `ConfirmDialog`, not a separate file) |
| T07 | Real API/query/mutations + optimistic reconciliation | **BLOCKED ON BACKEND CONTRACT** |
| T08 | `/account/addresses` route + account nav entry | **BLOCKED** until T07 unblocks |
| T09 | Integration/E2E/docs | **BLOCKED** — no real route exists to exercise end-to-end |
| T10 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02 (incl. T06), T03, and the pure optimistic-state helper. T04/T05/T07/T08/T09/T10 are each deferred/blocked for a distinct, documented reason.

---

## 4. Backend Questions For Tomorrow

**Endpoints:** 1. Confirm the exact four address endpoint paths beyond the `/me/addresses*` wildcard (i.e., independently confirm the `{id}` shape).

**List:** 2. Exact response envelope. 3. Paginated? 4. Ordering? 5. Exact address id field/type. 6. Exact default-indicator field name.

**Fields:** 7. Exact complete `AddressRead` schema. 8. Exact complete `AddressCreate` schema. 9. Exact `AddressUpdate` schema. 10. Which fields are required vs. optional? 11. Exact name/recipient field(s). 12. Exact phone field and validation rule, if any. 13. Exact address-line field(s). 14. City/locality field. 15. Governorate/region field. 16. Postal code field (does Lebanon addressing even use one here?). 17. Country field (fixed to Lebanon, or free text?). 18. Any label field (Home/Work)? 19. Any normalization/trimming rules the frontend must match?

**Default:** 20. How is an address made default — `PATCH {is_default:true}` or a separate endpoint/action? 21. What happens to the previous default on success? 22. Does success return one updated address or the authoritative full list? 23. Concurrency semantics (two simultaneous default-switch requests)? 24. Can there be zero defaults? 25. Does the first created address automatically become default?

**Create:** 26. Success status/body. 27. CSRF mechanism (same project-wide pattern, or anything address-specific?). 28. Validation error shape.

**Update:** 29. Partial `PATCH` or full replace? 30. Success status/body. 31. Concurrent-edit behavior.

**Delete:** 32. Success status/body. 33. Can the default address be deleted? 34. What becomes default afterward? 35. Can an address referenced by a historical/active order be deleted? 36. Hard delete or archive?

**Checkout relationship:** 37. Independently re-confirm (already strongly implied by VS-019's own Tests line) that address data carries no shipping-zone inference, and that FVS-026 selects a zone as an explicit, separate action.

**Testing:** 38. Disposable customer fixture. 39. Address fixture. 40. Two-address/default-switch acceptance procedure. 41. Delete-default acceptance procedure.

---

## 5. Task Detail (Safe Batch)

### FVS023-T01 — Canonical Address Query Keys + Normalized Model

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/addresses/addressKeys.ts` (+test), `src/lib/addresses/addressModel.ts` (+test).
**Design:** `addressKeys = {root: ["addresses"], list: () => [...root, "list"], detail: (addressId) => [...root, "detail", addressId]}` — `list()` takes no page/cursor argument (pagination unconfirmed, §1). `AddressModel {id: string, displayLines: readonly string[], isDefault: boolean}` — `displayLines` is pre-formatted, caller-agnostic presentation text (never individual field names, since none is confirmed); no zone/rate field exists on this type at all.
**Marker:** `#ARCHITECTURE-CANONICAL-ADDRESSES-QUERY`, `#ARCHITECTURE-ADDRESS-ADAPTER`, `#ARCHITECTURE-ADDRESS-NO-ZONE-INFERENCE`, `#SECURITY-CUSTOMER-ADDRESS` (query keys carry resource/id only, never address content).
**Tests:** query-key stability/derivation (mirrors `entitlementKeys.test.ts`); model type-only tests (RED-confirmed via `tsc`, mirrors `entitlementModel.test.ts`) proving no raw field (name/phone/street/etc.) exists on the type and that the key never embeds address content.

### FVS023-T02 — `AddressCard` / `AddressList`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/AddressCard.tsx` (+test), `src/components/account/AddressList.tsx` (+test).
**Design:** `AddressCard` renders `displayLines` as plain text lines, a `StatusBadge label="Default" tone="positive"` when `isDefault`, an optional `onEdit` seam (renders an Edit button only when supplied — there is no `AddressForm` to open yet this batch, so no caller supplies it, and no dead button renders), and an always-present `Delete` button (delete is fully safe to build presentationally this batch). `AddressList` reuses `EntitlementList`'s exact loading/error/retry/empty/populated state shape, owns its own delete-confirmation `ConfirmDialog` internally (mirroring `ReferenceDataManager`'s inline `onArchive`/`ConfirmDialog` pattern rather than a separate wrapper file — T06 folded in here), and exposes a required `onDelete: (addressId) => void` presentation seam. Never renders zone/rate information anywhere.
**Marker:** `#FVS023-ADDRESS-LIST`, `#SECURITY-CUSTOMER-ADDRESS` (no `console.log`/analytics of address content, no browser storage).
**Tests:** loading, error+retry, empty (no fake addresses), populated (every `displayLine` rendered), default badge shown as visible text, no zone/rate text anywhere, delete opens `ConfirmDialog` then calls `onDelete` with the exact target id, Edit button absent when `onEdit` omitted / present when supplied, no network, no storage.

### FVS023-T03 — `DefaultAddressSelector`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/DefaultAddressSelector.tsx` (+test).
**Design:** named (not `SetDefaultToggle`, per the task's own explicit "accessibility wins over the component name" instruction) to avoid implying checkbox/toggle semantics it must not have. A single `<fieldset><legend>` wrapping one native `<input type="radio" name="default-address">` per address option — true single-selection semantics, never independent checkboxes/switches. `pendingId` prop disables all radios and exposes an `aria-busy` fieldset plus a `role="status"` message while a switch is in flight, without removing any option's accessible label.
**Marker:** `#FVS023-DEFAULT-ADDRESS-SELECTOR`.
**Tests:** exactly one radio group rendered; each option has a clear accessible label; exactly one radio is checked (the current default); selecting a different option calls `onSelect` with that id; `pendingId` disables inputs and announces a pending status without removing labels; no network, no storage.

### FVS023 — Pure Optimistic Default-Address Helper

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/addresses/addressDefaultOptimistic.ts` (+test).
**Design:** `beginSetDefault(current, nextDefaultId)` returns a new array with exactly one `isDefault: true` (the requested id) and a `pendingId`; `rollbackSetDefault(previousSnapshot)` restores the exact prior array (failure path); `settleSetDefault(authoritative)` replaces local state with whatever the server/refetch actually returns (success path) — **the UI always ends on server truth, never the optimistic guess**, satisfying VS-019's own "server-authoritative, never locally flip two toggles and assume final" rule. No endpoint, no body, no status code is invented — this is pure array transformation only, wired to a real mutation in T07 once the contract exists.
**Tests:** `beginSetDefault` flips exactly one address and never mutates its input; `rollbackSetDefault` restores the exact previous snapshot; `settleSetDefault` adopts the authoritative array verbatim even when it differs from the optimistic guess (proving server-truth reconciliation, not blind trust in the local guess).

---

## 6. Deferred / Blocked Tasks (Rationale)

**T04 — `AddressForm`:** Not built. Zero individual address fields are confirmed anywhere (§0/§1) — building the standard e-commerce set (name/phone/street/city/governorate/postal/country) from general knowledge would mean inventing a DTO, exactly what this task explicitly forbids. Deferred until VS-019's real `AddressCreate`/`AddressUpdate` schema is confirmed.

**T05 — Create/edit dialog composition:** Blocked by T04. `DialogShell` itself needs no change to support this once unblocked.

**T07 — Real API/query/mutations:** Blocked — no confirmed request/response bodies for any address operation.

**T08 — `/account/addresses` route + nav:** Blocked until T07 unblocks. Adding `Addresses` to `ACCOUNT_NAV_ITEMS` now would be exactly the dead-link pattern `docs/setup/frontend-setup.md`'s own convention forbids.

**T09 — Integration/E2E/docs:** Blocked — no real route exists yet to exercise end-to-end; this batch's coverage stays at the unit/component level.

**T10 — Real backend acceptance:** Blocked on backend availability.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; one `test:e2e` regression run suffices (no route/page work this batch).
- No new runtime dependency.
- No invented address field, no governorate/zone mapping, no shipping price, no guessed default-mutation shape, no guessed delete behavior, no production API call, no `/account/addresses` route, no account-nav `Addresses` entry, until the respective gates in §6 unblock.
- No address content in `console.log`, browser storage, query keys, URLs, or analytics (`#SECURITY-CUSTOMER-ADDRESS`).
