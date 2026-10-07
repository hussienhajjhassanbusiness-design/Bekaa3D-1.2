# FVS-020 — Customer STL Library — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: Low — read-only.

**Goal:** A logged-in customer eventually sees every active STL entitlement — product name, thumbnail, current version, a path toward download. This batch establishes the canonical entitlement query-key family FVS-019 deliberately deferred, a normalized library model, `EntitlementCard`, and `EntitlementList` — then correctly defers the real route, account-nav link, and API integration.

**Architecture:** `entitlementKeys` (`src/lib/entitlements/entitlementKeys.ts`) is the one canonical query-key family for the entitlement resource — FVS-019's manual grant and any future payment/revocation flow invalidate this, never a parallel cache. `EntitlementModel` is a normalized presentation shape with no storage/download/revoked field. `EntitlementCard`/`EntitlementList` are presentational, with a generic `actionSlot`/`renderActionSlot` seam FVS-021 populates with its own `DownloadButton`.

**Spec:** `vertical-slice-plan.md`'s VS-017 entry (customer-facing read half) and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-020 entry.

---

## 0. Repository / Contract Audit

Read: `vertical-slice-plan.md` (VS-017), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-020), `FVS-006/019/018-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/components/account/` (`AccountLayout.tsx`, `accountNavItems.ts` — confirmed only `{label:"Profile", href:"/account/profile"}` exists, no dead links), `src/components/catalog/`, `src/lib/auth/` (`AUTH_SESSION_QUERY_KEY = ["auth","session"]` — the existing flat-tuple query-key convention), `src/lib/admin/`, `src/lib/api/`, `src/app/account/`. Searched for `entitlement`/`library`/`downloads`/`accountNavItems`/`query key`/`TanStack`/`thumbnail`/`version`/`ownership` and any OpenAPI source.

**Confirmed by repository evidence:**
- Both endpoint paths are literal/confirmed — `vertical-slice-plan.md`'s VS-017 "Endpoint / entrypoint" line states `GET /api/v1/me/entitlements*` directly (the same line that also literally confirms FVS-019's grant endpoint), not frontend-paraphrased prose.
- Revoked entitlements are excluded from the list entirely (VS-017's own Tests line: "revoked hidden/no download capability") — this is the authoritative reason no revoked UI variant was built (see §5/T03).
- The existing query-key convention in this codebase is a simple flat tuple (`AUTH_SESSION_QUERY_KEY`, `READINESS_QUERY_KEY`), not an elaborate factory framework — `entitlementKeys` follows the smallest extension of that pattern that still supports root/list/detail(id).
- `ACCOUNT_NAV_ITEMS` (`#SHARED-ACCOUNT-NAVIGATION`) explicitly documents "never as a disabled/dead placeholder ahead of time" — confirms the existing convention this plan continues, not a new rule.

**What is genuinely unconfirmed:** the full list/detail response envelope and field names; whether `/me/entitlements` is paginated; thumbnail/current-version representation; whether any entitlement-status field is returned at all (VS-017's "revoked hidden" rule suggests not); detail 404 behavior for a stale link; cache/invalidation guidance; whether a successful FVS-019 grant should produce an immediately-consistent list.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **List** | Endpoint path | **CONFIRMED** (literal, same line as FVS-019's grant endpoint) |
| **List** | Response envelope, pagination, row fields | **NEEDS BACKEND CONFIRMATION** |
| **List** | Revoked entitlements excluded | **CONFIRMED** (VS-017's own rule) — no revoked UI variant built |
| **Detail** | Endpoint path | **CONFIRMED** (literal) |
| **Detail** | Response schema, 404 behavior | **NEEDS BACKEND CONFIRMATION** |
| **Security** | No storage path/private URL/internal key ever exposed | **CONFIRMED architecture rule** — enforced by `EntitlementModel`'s own shape, not by a runtime filter |
| **Query keys** | Canonical entitlement key family | **DONE this batch** — resolves the gate FVS-019 deliberately left open |
| **Cache** | Invalidation guidance, grant-to-list consistency | **NEEDS BACKEND CONFIRMATION** |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Canonical entitlement query-key architecture + normalized library model | **CAN IMPLEMENT NOW** |
| T02 | `EntitlementCard` | **CAN IMPLEMENT NOW** |
| T03 | `EntitlementList` | **CAN IMPLEMENT NOW** |
| T04 | Account-library action seam for FVS-021 | **Absorbed into T02/T03** — `actionSlot`/`renderActionSlot` props |
| T05 | Real API/query integration | **BLOCKED ON RESPONSE CONTRACT** |
| T06 | `/account/library` route + account-nav registration | **BLOCKED** — cannot function without T05, and a dead nav link is explicitly disallowed |
| T07 | Integration/accessibility review | **BLOCKED** (nothing contract-dependent exists yet) |
| T08 | Deterministic E2E/docs | **BLOCKED** |
| T09 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02, T03 (T04 absorbed). T05/T06 blocked; T07–T09 blocked.

---

## 4. Backend Questions For Tomorrow

**List:** 1. Exact response envelope. 2. Is it paginated? 3. If yes, pagination model. 4. Exact entitlement id field/type. 5. Exact product id field/type. 6. Product name/title field. 7. Thumbnail representation. 8. Current-version representation. 9. Version label/number field. 10. Ordering. 11. Any entitlement-status field returned at all? 12. Confirm revoked entitlements never appear (already strongly implied by VS-017's own Tests line — asking for the exact mechanism).

**Detail:** 13. Exact detail schema. 14. Exact stale/revoked 404 response. 15. Does detail include files? 16. Does detail include authorized download data? 17. Does detail expose only logical metadata, never storage location?

**Ownership/cache:** 18. Is the entitlement list viewer-only and cache-private? 19. Cache guidance. 20. After a manual admin grant (FVS-019), is the list immediately consistent? 21. Recommended invalidation/refetch behavior. 22. After revocation, when should an already-open client observe the absence?

**Testing:** 23. Disposable customer. 24. Entitlement-grant fixture. 25. Revoked-entitlement fixture. 26. Stale-detail-404 procedure.

---

## 5. Task Detail (Safe Batch)

### FVS020-T01 — Canonical Query Keys + Normalized Model

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/entitlements/entitlementKeys.ts` (+test), `entitlementModel.ts` (+test).
**Design:** `entitlementKeys = {root: ["entitlements"], list: () => [...root, "list"], detail: (id) => [...root, "detail", id]}` — the smallest extension of the existing flat-tuple convention (`AUTH_SESSION_QUERY_KEY`) that supports root/list/detail. `list()` takes no page/cursor argument — pagination is unconfirmed, not baked in. **This is the canonical key FVS-019's manual grant (and any future payment-driven grant/revocation) must invalidate** — recorded explicitly so no parallel `libraryQueryKey`/`ownedProductsQueryKey` gets invented later. `EntitlementModel {id, productDisplayName, thumbnailSrc?, currentVersionLabel?}` — no storage path, private URL, download href, or revoked/status field (enforced by the type itself, not a runtime filter).
**Markers:** `#ARCHITECTURE-CANONICAL-ENTITLEMENTS-QUERY`, `#ARCHITECTURE-ENTITLEMENT-ADAPTER`.
**Tests:** 5 (query keys: stable root, list-from-root, detail-from-root-by-id, mutual distinguishability, no page argument accepted — enforced via `@ts-expect-error` plus `tsc`) + 3 (model: accepts the normalized fields, optional fields omittable, no revoked/status field present at the type level).

### FVS020-T02 — `EntitlementCard`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/EntitlementCard.tsx` (+test).
**Design:** Product name + optional current-version label + optional decorative thumbnail (`alt=""`, since the product name is already adjacent visible text — avoids a duplicate announcement) + a generic `actionSlot: ReactNode`. No overlapping click targets — proven by a test asserting exactly one interactive element exists when `actionSlot` supplies one, and zero when it supplies none. Plain `<img>`, not `next/image`: the real image host/URL format is still the same open `§17` gap as FVS-012/014's own galleries — recorded, not worked around.
**Marker:** `#FVS020-ENTITLEMENT-CARD`.
**Tests:** 9 (product name, version label present/absent-no-stray-text, decorative thumbnail attributes, no image when absent, action slot renders supplied content, no extra interactive element beyond the slot, no action slot when none supplied, no network).

### FVS020-T03 — `EntitlementList`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/account/EntitlementList.tsx` (+test).
**Design:** loading (skeleton, `role="status"`) / error (`Alert` + optional `Retry`) / empty (reuses `EmptyState` — "You don't own any STL products yet." + a `Browse the shop` action via `onBrowseShop`, a pure callback so this component stays router-agnostic) / populated (`<ul>`/`<li>` of `EntitlementCard`, with `renderActionSlot(entitlement)` wired through to each card's `actionSlot`). A responsive `grid-cols-1 tablet:grid-cols-2 desktop:grid-cols-3` wrapper — single column on mobile, multi-column on larger widths, via CSS only (no JS viewport detection). **No revoked badge/branch/filter exists anywhere in this component** — proven by a dedicated test asserting the word never appears, which is the more accurate test than constructing a fake revoked input and hiding it client-side (the backend never returns one to begin with).
**Marker:** `#FVS020-ENTITLEMENT-LIST`.
**Tests:** 11 (loading, error, retry, empty message + browse action, semantic list, every product name rendered, `renderActionSlot` reaches each item, responsive grid classes, no revoked text anywhere, no network, no storage).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency.
- No production API call, no guessed response DTOs, no storage/download-href field, no `/account/library` route, no account-nav `Library` link, no entitlement E2E, until T05/T06 unblock.
