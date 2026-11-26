# FVS-018 — Admin STL Asset Upload & Version Management — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: HIGH — digital-asset security.

**Goal:** Admin eventually uploads a multi-file STL bundle as a new asset version, watches per-file scan status, and publishes atomically only once every file is clean. This batch builds the normalized scan/version model, the pure publish-eligibility gate, the version-list presentation, the bundle-selection uploader (reusing `FileUploader`), and a contract-independent polling hook — then correctly defers everything touching the real endpoints.

**Architecture:** `assetVersionWorkflow.ts` is the one source of normalized scan/version states, pure eligibility helpers, and `StatusBadge` descriptors — no separate `ScanStatusBadge` component, since the generalized `StatusBadge` (FVS-017) already fits. `AssetVersionList` composes these into a presentational view with a server-truth-driven (never client-timer-driven) publish gate. `AssetVersionUploader` is a thin wrapper around the shared `FileUploader` in deferred mode. `useScanStatusPolling` is a small, transport-agnostic hook that only decides *whether* to keep polling.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-016 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-018 entry.

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-016), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-018, existing §17 gaps), `FVS-011/012/005-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/forms/FileUploader.tsx`/`uploadTypes.ts`, `src/components/admin/`, `src/components/feedback/`, `src/lib/admin/`, `src/lib/api/`, `package.json`. Searched for `asset version`/`asset-version`/`scan`/`infected`/`clean`/`pending`/`publish`/`superseded`/`STL`/`bundle`/`poll`/`refetchInterval`/`version` and any OpenAPI source — **none exists beyond what this batch itself adds.**

**Confirmed by repository evidence:**
- Every production endpoint path is explicitly prose-only (`docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` line 498: "VS-016's endpoint line is prose only — placeholders above, NEEDS BACKEND CONFIRMATION") — no production call is implemented.
- The scan-state vocabulary (`pending`/`clean`/`infected`) and version-state vocabulary (`current`/`superseded`, with uploaded-but-unpublished as a third conceptual state) are both named verbatim in FVS-018's own capability/component lines — not invented, but still explicitly **frontend-normalized**, never claimed as the backend's real enum literals.
- "Cannot publish until clean," "publish entire version atomically," and "superseded files retained" are confirmed server-side invariants (VS-016's Logic line) — the frontend's own publish-disabling logic is explicitly UX-only and never the real security boundary.
- Scan status is **polled, no push mechanism exists** (FVS-018's own State line) — confirms polling (not WebSocket/SSE) as the only correct mechanism, and that no fixed interval is given anywhere.
- `FileUploader`'s deferred-selection mode (added in the FVS-015 follow-up) is directly reusable here with zero further changes — confirmed by inspecting its current API (`driver` optional, `onSelectionChange` callback).

**What is genuinely unconfirmed:** every endpoint path/body/response schema (list/create/detail/publish); exact file metadata and scan-status field names; whether the create request is one multipart bundle and its field name(s); allowed file types/size/count limits; whether scanning is synchronous on upload or always async; the recommended polling interval; the publish request body and conflict/race response; and the exact behavior for a non-STL product id (404 vs. a different signal).

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Endpoints** | All four paths | **NEEDS BACKEND CONFIRMATION** — explicitly prose-only |
| **Model** | Scan-state vocabulary (pending/clean/infected) | **CONFIRMED as frontend-normalized concept** (not a backend literal claim) |
| **Model** | Version-state vocabulary (current/superseded/pending-publish) | **CONFIRMED as frontend-normalized concept** |
| **Publish** | "Cannot publish until clean," atomic bundle publish | **CONFIRMED** (server-side invariant) |
| **Publish** | Exact request/response/conflict shape | **NEEDS BACKEND CONFIRMATION** |
| **Scan** | Polling (not push) is the correct mechanism | **CONFIRMED** |
| **Scan** | Recommended polling interval | **NOT CONFIRMED — left as a required caller-supplied parameter, never a built-in default** |
| **Create** | Multipart? One bundled request? Field names? Limits? | **NEEDS BACKEND CONFIRMATION** — no number/type hardcoded |
| **Product type gate** | Non-STL direct-access behavior | **NEEDS BACKEND CONFIRMATION** — no client-only guessed check built |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized asset-version/scan model + pure eligibility helpers | **CAN IMPLEMENT NOW** |
| T02 | `ScanStatusBadge` | **Absorbed into T01/T03** — direct `StatusBadge` reuse via `describeScanStatus`/`describeAssetVersionState`, no separate wrapper component |
| T03 | `AssetVersionList` presentation + publish gating + scan-status `aria-live` summary | **CAN IMPLEMENT NOW** |
| T04 | `AssetVersionUploader` (bundle selection via `FileUploader`) | **CAN IMPLEMENT NOW** |
| T05 | Scan-status polling hook | **CAN IMPLEMENT NOW** — stayed contract-independent, no premature TanStack Query coupling (see §5/T05) |
| T06 | Real API/query/upload/publish integration | **BLOCKED ON BACKEND CONTRACT** |
| T07 | `/admin/products/:id/assets` route + product-type gate | **BLOCKED ON FVS-011/FVS-005/T06** |
| T08 | Integration/security/a11y review | **BLOCKED** (nothing contract-dependent exists yet) |
| T09 | E2E/docs | **BLOCKED** |
| T10 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T03, T04, T05 (T02 absorbed). T06/T07 blocked; T08–T10 blocked.

---

## 4. Backend Questions For Tomorrow

**Endpoints:** 1. Exact asset-version list endpoint. 2. Exact create endpoint. 3. Exact detail endpoint. 4. Exact publish endpoint.

**Version model:** 5. Exact version-list response envelope. 6. Exact version id field/type. 7. Exact current/published representation. 8. Exact superseded representation. 9. Version label/number field. 10. Created/published timestamps. 11. Ordering. 12. Pagination?

**Files:** 13. Exact file metadata. 14. File id. 15. Display filename. 16. Size. 17. Scan-status field. 18. Exact scan-status literals. 19. Any failure/rejection reason field. 20. Are infected files retained in version detail?

**Create:** 21. Multipart? 22. One bundled request? 23. File field name(s). 24. Any manifest/metadata fields? 25. Allowed file content/types. 26. Max files/version. 27. Max bytes/file. 28. Max total bundle size. 29. Success status/body. 30. Initial scan-state behavior. 31. CSRF/admin/MFA.

**Scan:** 32. Synchronous upload acceptance vs. async scan. 33. Recommended polling interval. 34. Poll the list or detail endpoint? 35. Cache/ETag guidance. 36. Scan timeout/stuck-state semantics. 37. Any statuses besides pending/clean/infected?

**Publish:** 38. Request body. 39. Success status/body. 40. Server all-clean enforcement error. 41. Concurrent-publish conflict status/code. 42. Does a failed publish return the authoritative current version? 43. Is publish idempotent?

**Product type:** 44. Exact behavior for a physical-product id. 45. Should the wrong-type route become a 404? 46. Exact product-type signal available to the frontend.

**Testing:** 47. Disposable STL product setup. 48. Clean-scan fixture. 49. Infected-scan fixture/test mechanism. 50. Publish-conflict acceptance procedure.

---

## 5. Task Detail (Safe Batch)

### FVS018-T01 — Normalized Asset-Version Model + Eligibility Helpers

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/admin/assetVersionWorkflow.ts` (+test).
**Design:** `ScanStatus = "pending"|"clean"|"infected"`; `AssetFile {id, displayName, scanStatus}`; `AssetVersionState = "current"|"superseded"|"pending"` (a third state beyond the source's literal "current vs superseded" wording, needed to correctly distinguish a newly-uploaded, never-yet-published candidate from a version that *was* current and got replaced — otherwise a brand-new bundle would be mislabeled "superseded"); `AssetVersion {id, label, files, state}`. No storage URL/path/hash field — none of that is a confirmed-safe frontend concern.
**Eligibility helpers (`#SECURITY-ASSET-PUBLISH-GATE`):** `areAllAssetFilesClean` (explicitly `false` for an empty list — `[].every(...)`'s vacuous truth would otherwise make an empty bundle publishable), `hasPendingAssetFiles`, `hasInfectedAssetFiles`, `getPublishBlockedReason` (infected takes priority over pending in the message — a bundle with both is blocked for the more serious reason). All UI gating only; the backend must independently enforce the same rule.
**Describe helpers:** `describeScanStatus`/`describeAssetVersionState` return `{label, tone}` for direct `StatusBadge` reuse; `summarizeScanStatuses` produces the aria-live summary text (T03).
**Marker:** `#ARCHITECTURE-ASSET-VERSION-ADAPTER`, `#SECURITY-ASSET-PUBLISH-GATE`.
**Tests:** 14 (empty-list vacuous-truth guard, all-clean, pending-flag, infected-flag, mixed bundle, blocked-reason priority ×4, scan-status labels/tones, version-state labels, scan-status summary ×2).

### FVS018-T02 — `ScanStatusBadge` (absorbed)

**Status:** Absorbed into T01/T03. `describeScanStatus`/`describeAssetVersionState` + the existing generalized `StatusBadge` (FVS-017) already give exactly the needed `{label, tone}` semantics — building a separate `ScanStatusBadge` wrapper component would add a layer with no behavior of its own. No spinner was added to the badge itself: the required polling-update announcement is handled once, at the list level (T03's `aria-live` summary), not per-badge, matching the task's own "prefer a containing status region... rather than per-badge live regions" guidance.

### FVS018-T03 — `AssetVersionList`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/AssetVersionList.tsx` (+test).
**Design:** Presentational, no network. Renders every version's state badge, per-file scan badges, and — only for a `"pending"` (not-yet-published) version — a `Publish` button. The button is disabled (not merely discouraged) whenever `getPublishBlockedReason` returns non-null, with the reason rendered as visible text linked via `aria-describedby` (never relying on the disabled state alone to convey why). `onPublish(versionId)` is a pure callback — this component never optimistically marks a version current; that stays server/parent-driven. One `role="status" aria-live="polite"` region per version renders `summarizeScanStatuses(files)` — its text naturally re-announces across a re-render when scan results change (e.g. a poll resolving pending → clean), without the component needing to track "what changed" itself, and without spamming a separate announcement per file badge.
**Tests:** 16 (pending/clean/infected file badges, current/superseded version identification, publish enabled on all-clean, disabled on pending/infected/mixed/empty, visible+linked disabled reason, exact-version-id callback, no publish action for current/superseded, aria-live summary, no network, no storage).

### FVS018-T04 — `AssetVersionUploader`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/AssetVersionUploader.tsx` (+test).
**Design:** A thin wrapper mounting the shared `FileUploader` (FVS-012) in its deferred-selection mode (no `driver`) — reused directly, not duplicated. `config: UploadValidationConfig` has no hardcoded MIME/size/count default; VS-016 never confirms allowed bundle formats, and `.stl`/`.zip`/`3mf` extensions are never inferred from this slice's own name. Selected files reach the parent via `onSelectionChange`; no per-file upload is attempted (proven: no `progressbar`, no "Uploaded" text after selection), since the real bundle-create request shape is unconfirmed.
**Tests:** 8 (shared dropzone reuse proof, native multi-file input, selection reaches parent without uploading, no hardcoded type/size limit, supplied `maxFiles` precheck applies, no network, no storage).

### FVS018-T05 — Scan-Status Polling Hook

**Status:** CAN IMPLEMENT NOW — stayed genuinely contract-independent, so it was **not** deferred. **Files:** `src/lib/admin/useScanStatusPolling.ts` (+test).
**Why it didn't need deferring:** the task's own instruction was to defer this hook only if building it cleanly would require coupling it to TanStack Query. It doesn't: `useScanStatusPolling({files, intervalMs, onPoll})` only decides **whether** to keep polling (derived purely from `hasPendingAssetFiles`, already built in T01) — what `onPoll` actually does (a future TanStack refetch) is entirely the caller's own concern, never referenced inside the hook. `intervalMs` is a required parameter with no default, so no production interval is embedded; "scan should be done by now" is never inferred from elapsed client time, only from the current `files` prop (ultimately server-sourced once wired).
**Marker:** `#ARCHITECTURE-SCAN-POLLING`.
**Tests:** 7 (fake timers via `vi.useFakeTimers`/`renderHook`) — polls at the exact supplied interval, never a different one; no polling at all for an already-terminal initial state (all-clean, and clean+infected); stops once a rerender reports all-clean; stops once a rerender reports a terminal clean+infected mix; stops on unmount.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency.
- No production API call, no guessed list/detail/create/publish DTOs, no real polling interval, no `/admin/products/:id/assets` route, no client-only product-type security gate, no real E2E, until T06/T07 unblock.
