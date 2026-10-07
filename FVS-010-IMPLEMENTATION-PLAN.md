# FVS-010 — Admin Reference Data (Categories, Materials, Colours) — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch.

**Goal:** Admin creates/edits/archives categories, materials, and colours through one generic, configured component — never three bespoke screens — so products can later reference controlled facet values.

**Architecture:** `ReferenceDataManager` is a single presentational component configured per entity (`ReferenceDataEntityConfig`); it never branches internally on which entity it renders. A normalized `ReferenceDataEntry`/`ReferenceDataDraft` UI shape isolates it from the unconfirmed backend Category/Material/Colour contracts. Archive reuses the existing `ConfirmDialog` (FVS-007) — no new modal. Responsive behavior is the FVS-007 stacked-card pattern, not FVS-009's `AdminTable` horizontal-scroll table — the two patterns serve different list shapes by design (`FRONTEND-VERTICAL-SLICE-PLAN.md` §14).

**Spec:** `vertical-slice-plan.md`'s VS-010 entry and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-010 entry.

---

## 0. Repository / Contract Audit

Read: `vertical-slice-plan.md` (VS-010), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-010/§14/§17), `FVS-005-IMPLEMENTATION-PLAN.md`, `FVS-007-IMPLEMENTATION-PLAN.md`, `FVS-009-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/components/admin/` (only FVS-007's `settings/` + FVS-009's `AdminTable`/`StatusBadge` exist — no reference-data code), `src/components/feedback/ConfirmDialog.tsx`, `src/components/forms/`, `src/lib/admin/` (only FVS-009's URL-state helpers), `src/app/admin/` (does not exist), `package.json`. Searched for `categories`/`materials`/`colours`/`colors`/`reference data`/`archive`/`slug`/`hex`/`swatch`/`AdminTable`/`StatusBadge`/`ConfirmDialog` and any OpenAPI source — **none exists beyond what FVS-007/009 already built.**

**Confirmed by repository evidence:**
- All six endpoint groups are literal in `vertical-slice-plan.md`, but the source itself flags exact admin path shapes as needing OpenAPI confirmation (`FRONTEND-VERTICAL-SLICE-PLAN.md` line 294) — **not treated as production-confirmed** despite being spelled out.
- Archive is explicitly **soft** ("Active/soft-delete behavior" — VS-010's own Logic line); archived entries stay admin-visible, excluded from public consumption (VS-010 Tests line: "archived values hidden publicly"). **DELETE meaning soft-archive is not itself confirmed** — VS-010 never states what HTTP verb triggers the soft behavior.
- `FRONTEND-VERTICAL-SLICE-PLAN.md` §14 explicitly assigns the **stacked-card fallback** to FVS-007/FVS-010 specifically, and reserves `AdminTable`'s horizontal-scroll pattern for other (larger) admin lists — this resolves the plan's own "AdminTable MAY be reused only if it fits" question: here it does not fit, so `ReferenceDataManager` does not use `AdminTable`.
- `ConfirmDialog` (FVS-007) already supports everything the archive-confirmation flow needs — reused as-is, no changes.
- Colour accessibility rule is explicit and followed literally: "Colour swatches include a text label, never color-only identification" (FVS-010 Accessibility line).

**What is genuinely unconfirmed:** exact admin collection/detail paths and whether they differ from the frontend-constructed literal paths; whether DELETE performs the soft archive or some other mechanism does; whether unarchive/reactivation exists; the exact Category/Material/Colour schemas (field names beyond "name" are not given — slug and any ordering field are assumed nowhere); which entities actually have a slug at all; slug generation/editability and collision status code; colour's exact value format/validation; public-read response shapes and ordering guarantees; whether an archived value can remain attached to products that already reference it.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Admin CRUD** | Collection/detail path shapes | **NEEDS BACKEND CONFIRMATION** — source itself says "confirm final paths against OpenAPI" |
| **Admin CRUD** | DELETE = soft archive? | **NEEDS BACKEND CONFIRMATION** — soft behavior is confirmed conceptually, the triggering mechanism is not |
| **Admin CRUD** | Unarchive/reactivation support | **NEEDS BACKEND CONFIRMATION** |
| **Admin CRUD** | Response schemas, CSRF/admin/MFA, status/error codes | **NEEDS BACKEND CONFIRMATION** (MFA inherits FVS-005's own still-open gate, not reopened here) |
| **Entity schema** | Category fields (slug?, ordering?) | **NEEDS BACKEND CONFIRMATION** beyond "name" |
| **Entity schema** | Material fields | **NEEDS BACKEND CONFIRMATION** beyond "name" |
| **Entity schema** | Colour fields (hex format/validation) | **NEEDS BACKEND CONFIRMATION** beyond "name" |
| **Public reads** | Paths, response shapes, archived-filtering guarantee, ordering | **NEEDS BACKEND CONFIRMATION** (archived-exclusion is confirmed as a behavior; the response shape proving it is not) |
| **Slug** | Which entities have one; generated vs. editable; collision status/message | **NEEDS BACKEND CONFIRMATION** |
| **Cross-cutting** | Can a product reference an archived value it already used? | **NEEDS BACKEND CONFIRMATION** |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized reference-data UI model (`referenceDataTypes.ts`) | **CAN IMPLEMENT NOW** |
| T02 | `ReferenceDataManager` generic presentational manager (incl. archive confirmation wiring — T04 is absorbed here, see below) | **CAN IMPLEMENT NOW** |
| T03 | Colour swatch presentation seam | **CAN IMPLEMENT NOW** |
| T04 | Archive confirmation | **Absorbed into T02** — `ConfirmDialog` needed no change and archive-confirmation is integral to the manager's own interaction, not a separable component; see §5 |
| T05 | API/query/mutation adapters | **BLOCKED ON BACKEND CONTRACT + FVS-005** |
| T06 | Admin routes (`/admin/categories` etc.) | **BLOCKED ON FVS-005 + T05** |
| T07 | Integration/accessibility review | **BLOCKED** (depends on T05/T06 existing to review) |
| T08 | E2E/docs | **BLOCKED** |
| T09 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01–T03 (T04 absorbed into T02, no separate commit). T05–T09 blocked.

---

## 4. Backend Questions For Tomorrow

1. Exact admin collection/detail endpoint shapes for categories.
2. Same for materials.
3. Same for colours.
4. Does DELETE perform the soft archive, or is there a separate archive action/endpoint?
5. If not DELETE, the exact archive mechanism.
6. Is unarchive/reactivation supported?
7. Exact category schema (fields beyond name — slug? ordering?).
8. Exact material schema.
9. Exact colour schema (hex field name/format).
10. Which entities have slugs?
11. Is slug generated server-side or editable by the admin?
12. Exact slug-collision status/code and human-safe message field.
13. Exact field-level validation error shape (shared with FVS-011/§17's existing open RFC 9457 field-shape question — not duplicated, cross-referenced).
14. Exact archive/status field name and its literal values.
15. Colour's exact value format (hex string? named token? something else?).
16. Colour validation rules, if any beyond format.
17. POST request schema per entity.
18. PATCH request schema per entity.
19. Success status/response bodies.
20. CSRF requirement (pattern suggests yes, not assumed).
21. Admin/MFA requirement (inherits FVS-005's open gate).
22. Non-admin route-hiding behavior (inherits FVS-005's established pattern, not reopened).
23. Exact public endpoint response schemas.
24. Are archived records guaranteed excluded from the public endpoints' response, or only from default filtering?
25. Ordering guarantees for public lists.
26. Can a product keep referencing a value that is later archived?
27. Supported disposable-reference-data setup for real backend testing.

---

## 5. Task Detail (Safe Batch)

### FVS010-T01 — Normalized Reference-Data Model

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/admin/referenceDataTypes.ts`.
**Design:** `ReferenceDataEntry` (`id`, `name`, `isArchived`, optional `swatchValue`), `ReferenceDataDraft`, `ReferenceDataFieldErrors` (`Partial<Record<"name"|"swatchValue", string>>`), and `ReferenceDataEntityConfig` (labels, empty-state copy, optional `hasSwatchField`/`swatchFieldLabel`/`renderSwatch`). No backend field name is claimed anywhere in this file. Tagged `#ARCHITECTURE-REFERENCE-DATA-ADAPTER`.

### FVS010-T02 — `ReferenceDataManager`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/admin/ReferenceDataManager.tsx` (+test, parameterized across category/material/colour-shaped configs).
**Design:** Presentational only — no fetch, no TanStack Query, no production mutation. Renders entries in a stacked-card list (FVS-007 pattern: `flex-col` below `tablet:`, `flex-row` at `tablet:` and above). Archived entries stay in the list with visible "Archived" text (not color alone) and have their own further-archive action disabled (no unarchive exists yet to wire). Create/edit uses a single inline form with ephemeral local draft state (no persistence, no autosave) and an external `fieldErrors` seam the component never derives itself. Archive goes through the existing `ConfirmDialog`. Marked `#FVS010-REFERENCE-DATA`.
**Why T04 has no separate commit:** archive confirmation is not a separable concern from the manager's own row interaction — it is the manager wiring an existing shared dialog, exactly as FVS-009's own T04 found no code change necessary in `ConfirmDialog` itself.
**Why `StatusBadge` was not reused:** FVS-009's `StatusBadge` is a two-value customer-account union (`"active"|"deactivated"`) with customer-account wording. Reference-data archive state is a different domain concept; forcing it into that union would misuse a narrowly-scoped shared component rather than genuinely generalize one. A plain text badge inline in the manager is simpler and correct for this single need.
**Why `AdminTable` was not reused:** `FRONTEND-VERTICAL-SLICE-PLAN.md` §14 explicitly assigns the stacked-card fallback to FVS-007/FVS-010-shaped lists and reserves `AdminTable`'s horizontal-scroll table for other admin lists — using `AdminTable` here would contradict the plan's own responsive-behavior line for this slice.
**Tests:** TDD — the 20-item matrix (adapted): label/config render, empty state, entries render, archived-state text, archived entry retained, archive-action disabled once archived, create/edit/cancel/save seams (typed draft + editing id), pending-save disables Save, inline field error, archive-confirm open/cancel/confirm via the real `ConfirmDialog`, responsive stacked structure, no network, no persistence — each parameterized across category/material/colour configs; colour-only tests for the supplemental swatch never replacing the text label. No-network/no-storage checks run once (the code path is identical regardless of config). 58 tests total.

### FVS010-T03 — Colour Swatch Presentation

**Status:** CAN IMPLEMENT NOW.
**Design decision:** No new component file. `ReferenceDataEntityConfig.renderSwatch` is the generic seam (T01); the colour entity's own future page config supplies a swatch renderer, exercised in `ReferenceDataManager.test.tsx`'s colour-specific tests using a minimal inline swatch (`<span style={{backgroundColor}}>`), proving the manager renders whatever a config supplies without ever hardcoding "colour" logic itself. A dedicated `ColourSwatch` primitive was **not** built separately because there is nothing colour-specific left to extract beyond what the test already demonstrates — building one now, with no confirmed hex/value contract, would risk a premature abstraction the plan explicitly warns against ("do not create a complex colour picker unless the backend/input contract is confirmed"). The real colour page's config (T06, blocked) supplies its own small `renderSwatch` function when the value format is confirmed.
**Accessibility:** proven by the T02 test asserting the name text renders alongside the swatch, never alone.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run at the batch boundary (no route/page work this batch).
- No new runtime dependency.
- No production API calls, no `/admin/categories`/`/admin/materials`/`/admin/colours` routes, no real Category/Material/Colour DTOs, no slug-collision mapping, no public reference-data query hooks, no reference-data E2E, no real backend testing until T05–T09 unblock.
