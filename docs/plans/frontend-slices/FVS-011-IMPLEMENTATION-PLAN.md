# FVS-011 — Admin Product Management — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: HIGH — central catalogue authoring.

**Goal:** Admin eventually creates/edits both physical and STL products through one product form that adapts to an immutable, create-time-only product-type choice. This batch builds the two genuinely contract-independent primitives (`MoneyInput`, `ProductTypeSelector`) and explicitly defers `ProductForm`/section-nav until the backend's exact field matrix is confirmed.

**Architecture:** `MoneyInput` is a cents-safe, currency-agnostic controlled input — domain value is always integer cents, parsed from decimal text via a deterministic string parser (never `price * 100` on a float). `ProductTypeSelector` is a normalized two-literal (`"physical" | "stl"`) radio group, locked with an accessible explanation in edit mode. Neither component claims any backend field name, enum string, or endpoint path.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-011 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-011 entry.

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-011, and §2's external-risk-track line on USD settlement), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-011, §17's existing RFC-9457 field-shape gap, §30's forms-stack line, line 1593's money-authority rule), `docs/plans/frontend-slices/FVS-010-IMPLEMENTATION-PLAN.md`, `docs/plans/frontend-slices/FVS-007-IMPLEMENTATION-PLAN.md`, `docs/plans/frontend-slices/FVS-009-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/admin/`, `src/components/forms/` (incl. `Form.tsx`'s existing React Hook Form + Zod wiring), `src/lib/api/`, `src/lib/admin/`, `package.json`. Searched for `product`/`physical`/`STL`/`digital`/`price`/`money`/`cents`/`currency`/`slug`/`purchase mode`/`availability`/`publication`/`published`/`ProductForm`/`MoneyInput` and any OpenAPI/product-registry source — **none exists beyond the search terms' own appearance in the two planning documents.**

**Confirmed by repository evidence:**
- **Every FVS-011 endpoint path is a frontend-constructed placeholder** — `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` line 322 says so explicitly ("VS-011's endpoint line is prose only... every path above is a frontend-constructed placeholder, NEEDS BACKEND CONFIRMATION"). No production call is implemented in this batch.
- Product type is immutable after creation — VS-011's own Logic line ("Immutable product type").
- Money uses integer cents globally — `docs/plans/backend/vertical-slice-plan.md` line 756 ("Money uses integer cents; timestamps use UTC; server remains price/status authority"), and line 1593 of the frontend plan repeats the same authority rule. **Currency itself is not settled** — `docs/plans/backend/vertical-slice-plan.md` §2 lists "Confirm USD settlement/support" as a still-open *external* item, so `MoneyInput` must not hardcode USD or any other currency.
- React Hook Form + Zod are the approved, already-installed form stack (`package.json`: `react-hook-form@^7.89.0`, `zod@^4.6.5`; `src/components/forms/Form.tsx` already wires both generically). This settles the "is RHF/Zod approved" question — they are — but does **not** by itself unblock `ProductForm`, since the form stack being available doesn't supply the missing field matrix.
- "Cents rounding" and "money validation" are named only as **test-summary phrases** in both planning documents — neither document defines an actual rounding rule (half-up, banker's, truncate). Inventing one would silently encode an unconfirmed financial policy (see §5/T01 below for the resolution).
- VS-011's field matrix is prose-only ("physical purchase modes; no stock quantity; required name..."), not an exhaustive, typed field list — insufficient to build a real `ProductForm` without inventing fields.

**What is genuinely unconfirmed:** every endpoint path; the product-type discriminator field name and its exact backend literals; the complete shared/physical-only/STL-only field matrix and per-field requiredness; create-vs-update schema differences; currency/currencies supported, min/max amount, whether zero is allowed, and the >2-decimal rounding policy; category/material/colour relationship shape and multiplicity; slug editability and collision status/code; whether publication is modeled at all; delete/soft-delete semantics and restoration; the exact field-error response shape (cross-referenced to the already-open `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 RFC 9457 gap, not duplicated); CSRF/MFA/audit/concurrency; list pagination/search/ordering.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Endpoints** | List/create/detail/update/delete paths | **NEEDS BACKEND CONFIRMATION** — explicitly placeholder per the source itself |
| **Product types** | Discriminator field name, allowed literals, response field | **NEEDS BACKEND CONFIRMATION** |
| **Product types** | Immutability after creation | **CONFIRMED** (VS-011 Logic line) |
| **Field matrix** | Common/physical-only/STL-only fields, requiredness, create-vs-edit differences | **NEEDS BACKEND CONFIRMATION** — prose examples only, not an exhaustive contract |
| **Money** | Currency/currencies supported | **NEEDS BACKEND CONFIRMATION** (`docs/plans/backend/vertical-slice-plan.md` §2: USD itself unconfirmed) |
| **Money** | Integer-cents domain representation | **CONFIRMED** (`docs/plans/backend/vertical-slice-plan.md` line 756/1593) |
| **Money** | Min/max amount, zero allowed | **NEEDS BACKEND CONFIRMATION** |
| **Money** | >2-decimal admin input handling / rounding policy | **NOT DEFINED — discrepancy recorded, not guessed** (see T01) |
| **Reference data** | Category/material/colour relationship, id type, multiplicity, archived-value behavior | **NEEDS BACKEND CONFIRMATION** (also open in `docs/plans/frontend-slices/FVS-010-IMPLEMENTATION-PLAN.md` §1) |
| **Slug** | Editable vs. generated; collision status/code | **NEEDS BACKEND CONFIRMATION** |
| **Publication** | Whether modeled at all; field/state; publish/unpublish mechanism | **NEEDS BACKEND CONFIRMATION** — "if modeled by the product's fields" is explicitly conditional in the source |
| **Delete** | Soft-delete behavior, restoration, slug-reuse-after-delete | **NEEDS BACKEND CONFIRMATION** (slug-reuse-after-soft-delete is named as a *test*, not given a mechanism) |
| **Validation** | Field-error response shape | **NEEDS BACKEND CONFIRMATION** — same open item as `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17's existing RFC 9457 gap |
| **Admin security** | CSRF/MFA/non-admin hiding/audit/concurrency | **BLOCKED ON FVS-005** (not reopened here) |
| **List** | Pagination/search/ordering contract | **NEEDS BACKEND CONFIRMATION** |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | `MoneyInput` (cents-safe money input) | **CAN IMPLEMENT NOW** |
| T02 | `ProductTypeSelector` (create/edit presentation) | **CAN IMPLEMENT NOW** |
| T03 | `ProductForm` architecture/field registry | **CORRECTLY DEFERRED** — field matrix evidence insufficient (see §5) |
| T04 | Section-nav shell (General/Pricing/Category-Material-Colour/Publication) | **CORRECTLY DEFERRED** — depends entirely on T03's nonexistent form content; no decorative shell with nonexistent controls |
| T05 | Product API/query/mutation adapters | **BLOCKED ON BACKEND CONTRACT** |
| T06 | Product list using `AdminTable` | **BLOCKED** on schema/admin route |
| T07 | New/edit routes + reference-data wiring | **BLOCKED** (depends on FVS-010's own T05/T06, also blocked) |
| T08 | Integration/security/accessibility review | **BLOCKED** (nothing contract-dependent exists yet to review) |
| T09 | E2E/docs | **BLOCKED** |
| T10 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02. T03/T04 are correctly deferred, not skipped — see §5 for why building either now would mean inventing fields or a shell with no real controls. T05–T10 blocked.

---

## 4. Backend Questions For Tomorrow

**Endpoints**
1. Exact admin product list path.
2. Exact create path.
3. Exact detail path.
4. Exact update path.
5. Exact delete/archive path.

**Product model**
6. Exact product-type discriminator field name.
7. Exact allowed type literal values.
8. Exact shared fields across both types.
9. Exact physical-only fields.
10. Exact STL-only fields.
11. Required/optional fields by type.
12. Create vs. update schema differences.

**Money**
13. Currency/currencies actually supported (cross-referenced to `docs/plans/backend/vertical-slice-plan.md` §2's own open USD-settlement item).
14. Exact cents field name(s) on the product schema.
15. Minimum amount, if any.
16. Maximum amount, if any.
17. Is zero an allowed price?
18. How should admin input with more than 2 decimal places be handled — rejected (current frontend behavior) or rounded by some defined rule?
19. If rounded, the exact rounding policy.

**Reference data**
20. Category relationship shape and id type.
21. Material relationship/multiplicity.
22. Colour relationship/multiplicity.
23. Can an archived category/material/colour remain attached to an existing product?
24. Can an archived value be newly selected for a product being created?

**Slug**
25. Is the product slug admin-editable or server-generated?
26. Exact collision status/code/error field.

**Publication**
27. Is publication modeled on the product at all?
28. If so, the exact field/state.
29. Publish/unpublish request semantics.

**Delete**
30. Confirm soft-delete (not hard delete).
31. Exact status field/response shape.
32. Is restoration supported?
33. Exact slug-reuse-after-soft-delete behavior.

**Validation**
34. Exact field-error response structure (same open item as `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17's RFC 9457 gap).
35. Exact type-mismatch error code (e.g. "purchase mode not allowed for STL").
36. Exact safe human-message field.
37. Unknown-field behavior on write.

**Admin/security** (inherits FVS-005's open gate, listed for completeness, not reopened)
38. CSRF requirement specifics for this endpoint group.
39. Admin/MFA requirement.
40. Non-admin route-hiding behavior.
41. Audit behavior.
42. Concurrency/version semantics.

**List**
43. Pagination contract.
44. Search/filter parameters.
45. Ordering/sorting.

**Testing**
46. Supported reference-data setup for real product-creation tests (depends on FVS-010's own T05/T09).
47. Supported disposable-product creation procedure for real backend testing.

---

## 5. Task Detail (Safe Batch)

### FVS011-T01 — `MoneyInput`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/forms/MoneyInput.tsx` (+test).
**Design:** Domain value is always `number | null` **integer cents** (`valueCents`/`onChangeCents`), never a float. The decimal-string-to-cents parser (`parseDecimalToCents`, exported for direct unit testing) works entirely on string digits — it never does `parseFloat(text) * 100` — specifically so a value like `"0.10"` can never produce a floating-point artifact. Raw edit text is kept in local state while the user types (e.g. `"12."` is a valid in-progress state that doesn't yet resolve to a cents value) and only synced from the external `valueCents` prop when that prop changes to something other than what this component itself last emitted — this avoids reformatting the field out from under an in-progress keystroke. Currency is **never hardcoded**: `currencyLabel` is a required prop, and the accessible name is `"{label} ({currencyLabel})"` on the `<label>` itself (not placeholder-only), satisfying `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own accessibility line for this component.
**Rounding decision — recorded discrepancy, not guessed:** neither governing document defines a rounding rule for more than 2 decimal places (§0). The parser **rejects** (does not silently round) input with more than 2 decimal digits, surfacing an explicit, accessible (`role="alert"`) message — "Enter an amount with at most 2 decimal places." This keeps the component correct and usable without inventing a financial policy; §4 Q18/Q19 ask the backend team to define one if rounding (rather than rejection) is actually wanted.
**Negative handling:** rejected outright, never clamped to 0 — an explicit, accessible error message, consistent with the source's own "negative rejection" requirement.
**Marker:** `#SHARED-MONEY-INPUT`.
**Tests:** TDD — 9 parser unit tests (whole number, 1 decimal, 2 decimals, no float artifact for 0.10, negative rejected, >2-decimals rejected, empty rejected, non-numeric rejected, whitespace trimmed) + 16 component tests (accessible label incl. currency, currency not placeholder-only, cents→decimal display, whole/1-decimal/2-decimal/0.10 round-trip, negative rejected + accessible, >2-decimal rejected without rounding, clearing emits `null`, a partial unparseable edit never emits a corrupted value, whitespace trimmed end-to-end, controlled external update, no network, no storage). 25 tests total.

### FVS011-T02 — `ProductTypeSelector`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/admin/ProductTypeSelector.tsx` (+test).
**Design:** Internal frontend UI literals `"physical" | "stl"` — explicitly not a claim about the backend's discriminator field name or enum strings (§1). A native `<fieldset>`/`role="radiogroup"` with two real, labeled radio inputs — no custom keyboard handling needed since native radios are already fully keyboard-operable. In `mode="create"` both options are enabled; in `mode="edit"` both are disabled **and** the radiogroup carries `aria-describedby` pointing to a visible explanation ("Product type can't be changed after creation.") — communicating the lock through an accessible relationship, not a bare grayed-out look.
**Marker:** `#FVS011-PRODUCT-TYPE`.
**Tests:** TDD — exactly two choices rendered, both selectable in create mode, current value reflected as checked, `onChange` fires with the internal literal, both options disabled in edit mode, a click in edit mode never calls `onChange`, the lock explanation is referenced via `aria-describedby` and only present in edit mode, keyboard-reachability via `Tab`, no network. 10 tests.

### FVS011-T03 — `ProductForm` (correctly deferred)

**Status:** NOT IMPLEMENTED — field-matrix evidence is insufficient (§0/§1). VS-011's "purchase modes/availability/no stock quantity" examples are illustrative prose, not an exhaustive, typed field contract; building real form fields from them would mean inventing the rest of the matrix, which the task explicitly forbids ("Do NOT implement a fake ProductForm just to satisfy the task list"). No speculative JSX was written for this task.

### FVS011-T04 — Section Nav (correctly deferred)

**Status:** NOT IMPLEMENTED — depends entirely on T03's content, which does not exist. Building a decorative section shell (General/Pricing/Category-Material-Colour/Publication) with no real controls inside it was explicitly disallowed ("No decorative shell with nonexistent controls").

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency (React Hook Form/Zod already installed; not newly added, and not yet wired to a real `ProductForm`).
- No production API calls, no `/admin/products*` routes, no product DTOs, no product list columns, no category/material/colour dropdown wiring, no slug-error mapping, no publish toggle, no soft-delete mutation, no create/update mutation, no product E2E, no admin-route integration until T05–T10 unblock.
