# FVS-019 — Admin Entitlement Management — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: HIGH — authorization/ownership model.

**Goal:** Admin eventually grants an STL entitlement to a customer from either the customer-detail or product-detail page. This batch builds the normalized picker models, a small accessible combobox primitive (none existed in the repo), the `GrantEntitlementDialog` itself, and — as a required prerequisite — extracts a shared `DialogShell` out of FVS-007's `ConfirmDialog` so neither dialog needs its own independent focus-trap implementation.

**Architecture:** `DialogShell` (new, shared) owns the accessible-dialog mechanics; `ConfirmDialog` now delegates to it, behavior unchanged (proven by its own pre-existing, untouched test suite still passing). `entitlementGrantModels.ts` reuses FVS-011's `ProductTypeOption` rather than inventing a third product-type union. `SearchableCombobox` is a small, newly-built accessible combobox (no suitable one existed). `GrantEntitlementDialog` composes all three.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-017 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-019 entry.

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-017), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-019), `FVS-018/009/011/005-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/feedback/ConfirmDialog.tsx`, `src/components/admin/`, `src/components/forms/`, `src/lib/admin/`, `src/lib/api/`. Searched for `entitlement`/`grant`/`ownership`/`library`/`customer picker`/`product picker`/`combobox`/`listbox`/`dialog`/`focus trap`/`toast`/`useToast`/`STL` and any OpenAPI source.

**Endpoint-path audit (explicitly required before declaring anything production-confirmed):** unlike every other slice in this engagement so far, `docs/plans/backend/vertical-slice-plan.md`'s VS-017 entry states the grant endpoint **literally** in its own "Endpoint / entrypoint" line — `POST /api/v1/admin/users/{user_id}/entitlements` — not as prose later paraphrased by the frontend plan. **This path is genuinely CONFIRMED**, unlike FVS-018's explicitly-flagged placeholder paths. The **request body fields** are a different matter: `AdminEntitlementGrant` is named as a schema with zero fields given — so the path is confirmed, the body is not.

**Dialog-infrastructure audit:** `ConfirmDialog` (FVS-007) has its own ~90-line manually-managed focus-trap/Escape/backdrop/focus-restoration implementation, with no generic content seam — it only ever renders a fixed title+description+confirm/cancel shape. `GrantEntitlementDialog` needs pickers, a different button label, pending/error states — too different to force into `ConfirmDialog`'s existing shape, but copying its ~90 lines a second time was exactly what the task forbade. **Resolution:** extracted `DialogShell` (`#SHARED-DIALOG-SHELL`) containing only the accessible-dialog mechanics; `ConfirmDialog` now builds its exact same fixed content on top of it, and `GrantEntitlementDialog` builds its own different content on top of the same shell. `ConfirmDialog`'s own pre-existing test suite (11 tests) was re-run **unmodified** after the refactor and passed unchanged, proving the extraction is behavior-preserving.

**Picker/combobox audit:** no existing accessible combobox, searchable select, or such a dependency was found anywhere in the repository or `package.json`. A large UI package was not installed solely for this — a small, purpose-built `SearchableCombobox` was built instead, scoped to local substring filtering only (no server search yet, since customer/product data-fetching itself is blocked).

**Product-type-union audit:** FVS-011's `ProductTypeSelector.tsx` already exports `ProductTypeOption = "physical" | "stl"`. Reused directly (`entitlementGrantModels.ts` imports it) rather than introducing a third, incompatible product-type definition — this is legitimate here because both files are admin-scoped, unlike FVS-014's public catalog code, which deliberately avoided importing from `admin/`.

**Confirmed by repository evidence:**
- "Only STL" is a literal VS-017 server-side test (`docs/plans/backend/vertical-slice-plan.md`'s own Tests line) — the frontend's STL-only product filter is explicitly UX-only; the server independently rejects a physical-product grant regardless.
- Active-uniqueness conflict ("already entitled") is a confirmed server-side invariant (VS-017's Model-change line: "partial unique active (user_id, product_id)") — but its exact status/code/message field is not given, so no `409`/`ENTITLEMENT_EXISTS` code was invented; `errorMessage` is a plain, already-safe string seam for a future adapter.
- FVS-019's own State line says success should invalidate "the customer's entitlement list query" — but FVS-020 (the slice that actually defines that canonical query) has not landed. Per the task's own instruction, **no temporary query key was invented**; this is recorded as a dependency gate, not worked around.

**What is genuinely unconfirmed:** the full `AdminEntitlementGrant` request body (exact product-id field name, any grant-source/reason field); success status/response schema; CSRF/MFA (inherits FVS-005's open gate); the exact already-entitled conflict status/code/message field; how admin obtains customer/product option lists (reuse FVS-009/011's own list endpoints? a dedicated search endpoint?); whether the STL product must have a published current asset version before being grantable; the canonical entitlement-list query key (depends on FVS-020).

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Grant** | Endpoint path | **CONFIRMED** (literal, unlike most other recent slices) |
| **Grant** | Request body fields | **NEEDS BACKEND CONFIRMATION** — schema named, no fields given |
| **Grant** | Success status/response, CSRF/MFA | **NEEDS BACKEND CONFIRMATION** (MFA inherits FVS-005's open gate) |
| **Uniqueness** | Active-uniqueness conflict exists | **CONFIRMED** (DB constraint); exact status/code/message **NEEDS BACKEND CONFIRMATION** |
| **Eligibility** | STL-only is a server-side rule | **CONFIRMED**; frontend filter is UX-only, never the real boundary |
| **Pickers** | How admin obtains customer/product option lists | **NEEDS BACKEND CONFIRMATION** |
| **Invalidation** | Canonical entitlement-list query key | **BLOCKED ON FVS-020** — not invented |
| **Dialog infrastructure** | Shared shell now exists | **DONE** (`DialogShell`, `ConfirmDialog` migrated, regression-proven) |
| **Combobox** | Accessible picker primitive | **DONE** (`SearchableCombobox`, newly built) |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized picker models + STL filtering helper | **CAN IMPLEMENT NOW** |
| T02 | Accessible reusable picker primitive (`SearchableCombobox`) | **CAN IMPLEMENT NOW** |
| T03 | `GrantEntitlementDialog` presentation | **CAN IMPLEMENT NOW** |
| T04 | Shared dialog infrastructure extraction (`DialogShell`) | **CAN IMPLEMENT NOW — done first, as a prerequisite for T03** |
| T05 | Real admin product/customer query adapters | **BLOCKED ON BACKEND CONTRACT/FVS-009/FVS-011** |
| T06 | Entitlement mutation/invalidation/toast | **BLOCKED ON BACKEND CONTRACT** (invalidation also blocked on FVS-020) |
| T07 | Embedding in admin customer/product routes | **BLOCKED ON FVS-005/009/011** |
| T08 | Integration/E2E/docs | **BLOCKED** |
| T09 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T04 (done first), T01, T02, T03. T05–T07 blocked; T08/T09 blocked.

---

## 4. Backend Questions For Tomorrow

**Grant:** 1. Confirm exact endpoint (done — `POST /api/v1/admin/users/{user_id}/entitlements`, literal). 2. Exact `user_id` path type. 3. Exact request body. 4. Product-id field name/type. 5. Any grant-source field? 6. Any reason/note field? 7. Success status. 8. Success response schema. 9. CSRF. 10. Admin/MFA requirement. 11. Non-admin route hiding. 12. Audit behavior.

**Uniqueness:** 13. Exact already-entitled status. 14. Exact RFC 9457 code. 15. Exact safe human-readable field. 16. Is granting an already-active entitlement idempotent or an error? 17. Can a revoked/expired entitlement be re-granted?

**Product eligibility:** 18. Exact server physical-product rejection response. 19. Exact STL product-type signal available to the frontend. 20. Must the product be published/current? 21. Must a clean current asset version exist before grant (ties to FVS-018)? 22. What happens if an STL product has no published asset version?

**Customer eligibility:** 23. Can an unverified customer receive an entitlement? 24. Can a deactivated customer receive one? 25. Exact user-not-found behavior.

**Pickers:** 26. Reuse `GET /admin/users` list? 27. Exact customer search fields/query. 28. Reuse the admin product list? 29. Exact product search/filter query. 30. Can the product list filter server-side by STL type?

**Invalidation/data:** 31. Exact entitlement-list endpoint/query for admin/customer, if one exists. 32. Should a successful grant return enough data to update cache directly, or should the frontend invalidate/refetch? 33. Canonical customer-library/entitlement query to align with FVS-020 (blocked until FVS-020 lands).

**Testing:** 34. Disposable customer setup. 35. Disposable STL product with a clean current asset version. 36. Already-entitled fixture/procedure. 37. Physical-product-rejection fixture. 38. End-to-end grant → library verification procedure.

---

## 5. Task Detail (Safe Batch)

### FVS019-T04 — Shared Dialog Infrastructure Extraction

**Status:** DONE (implemented first, as T03's prerequisite). **Files:** `src/components/feedback/DialogShell.tsx` (+test), `ConfirmDialog.tsx` (refactored, test file **unchanged**).
**Design:** `DialogShell {open, onClose, isBusy, labelledBy, describedBy, children}` owns role/aria-modal, the Tab focus trap, Escape handling (suppressed while `isBusy`), backdrop-click handling (suppressed while `isBusy`), and focus restoration to the triggering element — extracted verbatim from `ConfirmDialog`'s own prior implementation, with no behavior change. Also added mobile-safe sizing (`w-full max-w-md max-h-[90vh] overflow-y-auto`) that `ConfirmDialog` now inherits for free. `ConfirmDialog` keeps its exact external prop API (`title`/`description`/`confirmLabel`/`cancelLabel`/`isConfirming`/`onConfirm`/`onCancel`) and now renders its fixed title+description+buttons as `DialogShell`'s `children`.
**Marker:** `#SHARED-DIALOG-SHELL`.
**Regression proof:** `ConfirmDialog.test.tsx` (11 tests, written for FVS-007, **not edited for this refactor**) passes unchanged; `ReferenceDataManager.test.tsx` + `ImageGallery.test.tsx` (the two existing `ConfirmDialog` consumers, 71 tests combined) also pass unchanged.
**Tests:** `DialogShell` — 12 (closed/open, role/aria-modal, labelledby/describedby wiring, children rendering, Escape, Escape-suppressed-while-busy, backdrop click, backdrop-suppressed-while-busy, inside-click-does-not-close, Tab focus trap, focus restoration, mobile-safe width classes).

### FVS019-T01 — Normalized Picker Models + STL Filter

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/admin/entitlementGrantModels.ts` (+test).
**Design:** `CustomerOption {id, displayLabel}`; `ProductOption {id, displayLabel, productType: ProductTypeOption}` (reusing FVS-011's union, not a third one — see §0). `selectableStlProducts(products)` filters to `productType === "stl"` only, returns a new array (input never mutated), and is explicitly documented as UX-only (`#SECURITY-ENTITLEMENT-GRANT`) — the server independently rejects a non-STL grant regardless of what this ever returns.
**Tests:** 4 (STL included, physical excluded, mixed-list filtering, no input mutation).

### FVS019-T02 — `SearchableCombobox`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/SearchableCombobox.tsx` (+test).
**Design:** `{label, options, value, onChange, placeholder?}`. Real `role="combobox"` input with `aria-expanded`/`aria-controls`/`aria-activedescendant`, a real `role="listbox"` with `role="option"` items. Filtering is a local substring match over the supplied `options` — never a network call; a real debounced server search stays contract-gated, same precedent as FVS-013's `SearchBar`. Full keyboard support: typing opens/filters, `ArrowDown`/`ArrowUp` move the active option (starting from "none active," so the first `ArrowDown` highlights index 0, not index 1), `Enter` selects the active option, `Escape` closes without selecting. Mouse click on an option also selects it (`onMouseDown` with `preventDefault` so the input doesn't lose focus first) — proving selection is not mouse-only. A safe "No results found." message replaces the option list when nothing matches.
**Marker:** `#FVS019-SEARCHABLE-COMBOBOX`.
**Tests:** 12 (programmatic label, `aria-expanded` toggling, `aria-controls` → real listbox, local filtering, keyboard-only selection, selected label shown in the input, `Escape` without selecting, click-to-select, safe empty state, `aria-activedescendant` wiring, no network, no storage).

### FVS019-T03 — `GrantEntitlementDialog`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/GrantEntitlementDialog.tsx` (+test).
**Design:** Composes `DialogShell` + `SearchableCombobox` + `selectableStlProducts`. `fixedCustomer`/`fixedProduct` (optional `CustomerOption`/`ProductOption`) support the two context-driven entry points (known-customer-from-customer-detail, known-product-from-product-detail) without forcing the caller to re-select something already known — when fixed, that side renders as static text instead of a picker. `Grant` is disabled until both a customer id and a product id are resolved (fixed or selected) — never a backend call, never an optimistic success. `isSubmitting` disables both actions; `errorMessage` renders a caller-supplied, already-safe string only — no conflict code is invented, no raw error object is ever rendered.
**Marker:** `#FVS019-GRANT-ENTITLEMENT-DIALOG`, `#SECURITY-ENTITLEMENT-GRANT`.
**Tests:** 13 (real accessible dialog via the shared shell, Escape-closes proving shell reuse, labeled customer/product pickers, STL-only product options — physical never appears, known-customer mode, known-product mode, confirm disabled until both resolved, confirm enabled once both resolved, confirm callback receives exact ids, pending disables both actions, safe error rendering, no network, no storage).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency — no UI combobox package installed.
- No production API call, no guessed request body, no already-entitled code mapping, no customer/product API fetching, no invented query-invalidation key, no route embedding, no real E2E, until T05/T06/T07 unblock.
