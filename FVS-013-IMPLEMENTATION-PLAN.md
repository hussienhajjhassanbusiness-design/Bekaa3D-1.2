# FVS-013 — Public Catalogue & Product Discovery — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: Medium — first storefront discovery experience.

**Goal:** A visitor eventually browses/searches/filters/sorts the product grid with the URL as the single source of truth for filters/sort/search/cursor. This batch builds every genuinely contract-independent presentational primitive and URL-state helper, and correctly defers `ProductCard`/`ProductGrid`, the real `/shop` route, and all API integration.

**Architecture:** `shopUrlState` is pure URL-state helpers (not the backend query adapter). `FilterPanel`/`SortSelect`/`SearchBar` are fully data-driven presentational components with zero hardcoded facet/sort values. `EmptyState`/`LoadMore` are small generic feedback primitives. `ProductCard`/`ProductGrid` and the `/shop` route itself are deferred — VS-013 names `ProductListItem` as a schema with no field list, so building a card now would mean inventing display fields.

**Spec:** `vertical-slice-plan.md`'s VS-013 entry and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-013 entry, §9 (API Integration Architecture), §14 (Responsive Strategy).

---

## 0. Repository / Contract Audit

Read: `vertical-slice-plan.md` (VS-013), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-013, §9, §14, §17's existing cursor-pagination and image/asset-URL gaps), `FVS-010/011-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/components/layout/`, `src/components/forms/`, `src/components/feedback/`, `src/lib/api/`, `src/app/` (no `/shop` route exists), `package.json`, `playwright.config.ts`. Searched for `shop`/`catalog`/`ProductCard`/`ProductGrid`/`FilterPanel`/`SortSelect`/`SearchBar`/`Pagination`/`LoadMore`/`facet`/`cursor`/`suggestions`/`searchParams` and any OpenAPI source — **none exists beyond the two planning documents' own text.**

**Confirmed by repository evidence:**
- URL keys are literal and confirmed: `category`, `material`, `colour`, `sort`, `q`, `cursor` (`FRONTEND-VERTICAL-SLICE-PLAN.md`'s own Routes line) — URL state is explicitly the source of truth, not component/store state.
- Facets combine with **AND** semantics (VS-013 Logic line: "allowlisted facets/sorts"; FVS-013's own API-integration line repeats the AND rule) — no client-side OR-implying copy.
- Cursor pagination is confirmed as the mechanism (VS-013 Logic line); the exact cursor field name is **already an open item** in `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 ("Cursor pagination response shape") — cross-referenced, not duplicated. "Load more"/"Next", never a numbered page picker, unless that gap's resolution later proves random-access support.
- `ProductListItem` is named as a schema (VS-013's Request/response schema line) with **zero field names given anywhere** — confirms `ProductCard`/`ProductGrid` must be deferred, not built on guessed fields.
- Route examples show only **singular** facet keys (`category=`, `material=`, `colour=`), but the source separately requires *checkbox-based* facets — checkboxes inherently support selecting more than one option per group. Neither document states whether a facet is restricted to one selected value, nor (if not) how multiple values would serialize (repeated params vs. comma-separated vs. something else). **FVS-013 FOLLOW-UP correction:** T01's model was initially built as single-value-only, which over-read the singular route example as a cardinality decision rather than just the one case it actually shows. The model (`ShopUrlState.category/material/colour: readonly string[]`) is now cardinality-neutral — zero, one, or many — while *writing* more than one value per facet stays an explicit, loud gate (`#BACKEND-GATE-FACET-SERIALIZATION`) rather than a guessed encoding. See §5/T01.
- §14 confirms the responsive grid/filter pattern (3–4 cols desktop → 2 tablet → 1–2 mobile; sidebar → collapsible panel → full-screen sheet) — recorded for when `/shop` itself is built, not actionable without `ProductCard`.

**What is genuinely unconfirmed:** every query-parameter name on the real `GET /products` request (search/facet/sort/cursor); the response envelope and `ProductListItem`/`ProductPage` field names; whether multiple values per facet are supported and how they'd serialize; the exhaustive allowed-sort-values list; the suggestions endpoint's exact query/response shape, debounce interval, and minimum query length; category/material/colour public response shapes (shared gap with `FVS-010-IMPLEMENTATION-PLAN.md`).

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Product list** | Endpoint path | **CONFIRMED** (literal) |
| **Product list** | Query parameter names, response envelope, `ProductListItem` fields | **NEEDS BACKEND CONFIRMATION** |
| **Product list** | AND semantics across facets | **CONFIRMED** |
| **Product list** | Cursor request/response field names | **NEEDS BACKEND CONFIRMATION** — existing §17 gap, cross-referenced |
| **Sort** | Exact allowed values (incl. "most-downloaded" eligibility) | **NEEDS BACKEND CONFIRMATION** — `SortSelect` is data-driven specifically because of this |
| **Facets** | Category/material/colour response shape | **NEEDS BACKEND CONFIRMATION** — shared gap with `FVS-010-IMPLEMENTATION-PLAN.md` §1 |
| **Facets** | Multi-value-per-facet support | **NOT CONFIRMED — model is cardinality-neutral (arrays); not restricted to single-select** (§0, corrected in follow-up) |
| **Facets** | Multi-value URL serialization (repeated params vs. comma/pipe/JSON) | **NOT CONFIRMED — writing >1 value is an explicit gate, not guessed** (`#BACKEND-GATE-FACET-SERIALIZATION`) |
| **Search** | `q` semantics, typo-tolerance behavior | **CONFIRMED conceptually** (VS-013 Logic line), **NOT** at the field/behavior level |
| **Suggestions** | Endpoint query/response shape, debounce ms, min chars | **NEEDS BACKEND/PRODUCT CONFIRMATION** |
| **Product card** | Exact list-item display fields, detail route/slug mechanism | **NEEDS BACKEND CONFIRMATION** — `ProductListItem` named with no fields given |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | `shopUrlState` URL-state helpers | **CAN IMPLEMENT NOW** |
| T02 | `FilterPanel` + applied-filter chips | **CAN IMPLEMENT NOW** |
| T03 | `SortSelect` (allowlisted) | **CAN IMPLEMENT NOW** |
| T04 | `SearchBar` + suggestion presentation seam | **CAN IMPLEMENT NOW** |
| T05 | `ProductCard`/`ProductGrid` | **CORRECTLY DEFERRED** — `ProductListItem` has no confirmed field list (§0) |
| T06 | `EmptyState` + `LoadMore` | **CAN IMPLEMENT NOW** |
| T07 | Real API/query/facet/suggestion integration | **BLOCKED ON BACKEND CONTRACT** |
| T08 | `/shop` route + responsive composition | **CORRECTLY DEFERRED** — depends entirely on T05 (nonexistent) and T07 (blocked); no decorative shell with nothing real inside it |
| T09 | Integration/accessibility/review | **BLOCKED** (nothing contract-dependent exists yet to review) |
| T10 | Deterministic E2E/docs | **BLOCKED** |
| T11 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02, T03, T04, T06. T05/T08 correctly deferred (not merely blocked — building them now would mean inventing fields or a shell with no real controls). T07/T09–T11 blocked.

A generic mobile filter "sheet" primitive was considered for T08's responsive shell and **not built**: there is no concrete consumer yet (T08 itself is deferred), and building one in isolation would be scope expansion ahead of actual need — deferred alongside T08, not built as speculative infrastructure.

---

## 4. Backend Questions For Tomorrow

**Product list:** 1. Exact `GET /products` query parameters. 2. Exact response envelope. 3. Exact `ProductListItem` schema. 4. Exact cursor request parameter (shared with the existing §17 gap). 5. Exact next-cursor response field. 6. Is the cursor opaque? 7. Page size default/max. 8. Ordering guarantee.

**Filters:** 9. Exact category filter parameter. 10. Exact material filter parameter. 11. Exact colour filter parameter. 12. Are multiple values per facet supported? 13. If yes, exact serialization. 14. AND-across-distinct-facets is confirmed — is it AND or OR *within* multiple values of the same facet? 15. IDs, slugs, or names used in the query?

**Sort:** 16. Exact sort parameter name. 17. Exact allowed values. 18. User-facing label/ordering meaning per value. 19. Which product types support "most-downloaded"? 20. What happens if an unsupported/unknown sort value is sent?

**Search:** 21. Exact `q` semantics. 22. Typo-tolerance behavior detail. 23. Any normalization (case/diacritics)? 24. Min/max query length?

**Suggestions:** 25. Exact suggestions endpoint query fields. 26. Exact response envelope/item fields. 27. Are suggestions products, terms, categories, or mixed? 28. Exact destination data, if any, per suggestion. 29. Recommended debounce interval. 30. Minimum characters. 31. Max suggestions returned. 32. Rate-limit/cache guidance.

**Facet public endpoints:** 33. Exact category/material/colour response schemas (shared with FVS-010's own open gap). 34. Are archived items guaranteed excluded? 35. Ordering. 36. Colour visual-value field, if any.

**Product card:** 37. Exact fields safe/available in the list result. 38. Product detail route/id/slug mechanism. 39. Primary image representation (shared with the existing §17 image/asset-URL gap). 40. Price/currency representation. 41. Product-type field. 42. Availability/publication fields. 43. Rating/review/download-count fields, if any.

**Caching/errors:** 44. Cache/ETag guidance. 45. Error behavior for an invalid/stale cursor. 46. Invalid facet/sort value behavior.

**Testing:** 47. Supported public catalogue seed/setup. 48. Supported typo-tolerant search fixture. 49. Supported cursor-pagination acceptance fixture.

---

## 5. Task Detail (Safe Batch)

### FVS013-T01 — Shop URL-State Helpers

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/lib/catalog/shopUrlState.ts` (+test).
**Design:** `parseShopUrlState`/`buildShopUrlParams`, pure functions over `URLSearchParams`, handling exactly the six confirmed keys. `sort`/`q`/`cursor` are single values (nothing about them is a checkbox-style facet). `category`/`material`/`colour` are `readonly string[]` — **cardinality-neutral by design** (FVS-013 FOLLOW-UP correction: an earlier version typed these as `string | null`, over-reading the route example's singular key as a cardinality restriction rather than just the one case it actually shows). Parsing uses `URLSearchParams.getAll`, the web platform's own neutral read of however many same-named params already exist — not this module choosing an encoding. An empty facet value (`category=`) parses to `[]`, not a one-element empty-string array. Writing exactly one value per facet reuses the only encoding the source confirms (`key=value`); writing more than one value **throws**, loudly refusing to guess between repeated-params/comma/pipe/JSON encoding (`#BACKEND-GATE-FACET-SERIALIZATION`) rather than silently picking one. **Stale-cursor handling:** changing `category`/`material`/`colour`/`sort`/`q` always clears `cursor` — a frontend URL-hygiene invariant (a cursor is only valid for the query that produced it), not a claim about the backend's cursor format, needing no backend confirmation to be correct. Setting `cursor` alone (pagination) never touches the other keys.
**Marker:** `#ARCHITECTURE-CATALOGUE-URL-STATE`, `#BACKEND-GATE-FACET-SERIALIZATION`.
**Tests:** TDD — empty-URL defaults (facets as `[]`), `q`/`sort` round-trip, cursor opacity, empty-facet-as-empty-array, single-facet-value-to-one-element-array, multiple-same-named-params-to-multi-element-array (proves the model itself is cardinality-neutral), URL-encoding correctness, unrelated-param preservation, single-value facet write (regression), multi-value facet write throws the gated error, cursor cleared on each of category/q/sort change, cursor preserved when only cursor itself changes, full round-trip. 17 tests.
**`FilterPanel` audit (no change needed):** re-inspected as part of the same follow-up — `FacetOption.checked` is already independent per option with a per-option `onChange(groupId, value, checked)` callback, so the component itself never restricted a group to one checked option; the cardinality restriction lived entirely in `shopUrlState.ts`'s type, now corrected above.

### FVS013-T02 — `FilterPanel`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/catalog/FilterPanel.tsx` (+test).
**Design:** `FacetGroup`/`FacetOption` supplied entirely by the caller — zero hardcoded facet entries (proven in tests using deliberately non-domain group names). Real `<fieldset>/<legend>` per group, real checkboxes, text labels always (colour facets get no special swatch treatment in this component — that stays FVS-010's `renderSwatch` concern in a different context). An empty group renders a safe "No options available." message instead of an empty, confusing fieldset. Applied-filter chips are real, individually-labeled (`aria-label="Remove {label} filter"`) buttons; `onClearAll` is a separate optional seam.
**Marker:** `#FVS013-CATALOGUE-FILTERS`.
**Tests:** TDD — fieldset/legend per group, real checkboxes with visible labels, checked-state reflection, `onChange(groupId, value, checked)`, empty-group safety, colour-group text-only labels, chip removal, clear-all, no network, no storage. 10 tests.

### FVS013-T03 — `SortSelect`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/catalog/SortSelect.tsx` (+test).
**Design:** Native `<select>`, fully data-driven from `options` — no sort value (including "most-downloaded") is ever embedded in the component itself. An empty `options` array disables the control rather than rendering a guessed default. Custom accessible label supported via a prop, defaulting to "Sort by".
**Marker:** `#FVS013-SORT-ALLOWLIST`.
**Tests:** TDD — native select, accessible label (default + custom), exactly the supplied options render, an unsupplied option (explicitly "most-downloaded") never appears, `onChange` fires with the selected value, empty-options disables the control, no network. 8 tests.

### FVS013-T04 — `SearchBar`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/catalog/SearchBar.tsx` (+test).
**Design:** Controlled `<input type="search">` with a Clear button (visible only when non-empty) and a submit seam (`onSubmit`, form-based, `preventDefault`). No debounce is implemented inside this component — `onChange` fires on every keystroke; debouncing is a future caller's job once the real suggestions contract exists, since the actual interval/min-chars are unconfirmed (§1) and inventing one here would bake an unconfirmed product decision into shared UI. Suggestions render as plain text (tested with a literal `"<b>...</b>"` label to prove no HTML interpretation) inside real, keyboard-reachable `<button>`s rather than a full ARIA combobox/listbox pattern the task explicitly warned against inventing. Three suggestion states are distinguished: not supplied (no UI at all), loading, and resolved-empty (safe "No suggestions found." message).
**Marker:** `#FVS013-SEARCH-BAR`.
**Tests:** TDD — accessible search input, `onChange` on typing, Clear button shown/hidden by value presence and resets to `""`, submit seam fires with current value, loading state, resolved-empty-suggestions message, suggestions-not-supplied renders nothing, suggestion text safety, suggestion selection callback with the exact object, suggestions are real buttons, no network, no storage. 13 tests.

### FVS013-T05 — `ProductCard`/`ProductGrid` (correctly deferred)

**Status:** NOT IMPLEMENTED. VS-013 names `ProductListItem` as a schema with zero field names anywhere in either governing document. Building a card now would mean inventing price/image/rating/badge/availability fields the task explicitly forbids guessing. No speculative JSX was written.

### FVS013-T06 — `EmptyState` + `LoadMore`

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/feedback/EmptyState.tsx` (+test), `src/components/feedback/LoadMore.tsx` (+test).
**Design:** `EmptyState` follows `bekaa3d-brand-ui`'s exact convention (centered neutral/non-brand-colored icon, `aria-hidden`, one-line message, at most one primary action) — fully generic, not catalogue-specific, living in `src/components/feedback/` alongside `Alert`/`Toast`. `LoadMore` is `hasMore`/`onLoadMore`/`isLoading` only — it never interprets or constructs a cursor, and renders nothing (not even a disabled button) once `hasMore` is false, consistent with "no numbered page picker."
**Tests:** `EmptyState` — message renders, action button present/absent based on both props being supplied, decorative icon `aria-hidden`, no network (5 tests). `LoadMore` — renders/absent by `hasMore`, click calls `onLoadMore`, disabled while loading, no network (5 tests).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency.
- No production API calls, no guessed `ProductListItem`/facet/sort/suggestion DTOs, no `/shop` route, no mock/fake production data, no debounce-millisecond or minimum-character decision baked into shared UI, until T07/T05/T08 unblock.
