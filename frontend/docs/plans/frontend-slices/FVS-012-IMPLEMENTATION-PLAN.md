# FVS-012 — Admin Product Image Management — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: HIGH — upload/security integration.

**Goal:** Admin eventually uploads multiple product images, sees per-file progress, sets a cover, reorders the gallery, and deletes with confirmation. This batch builds the two genuinely contract-independent, reusable primitives — `FileUploader` and `ImageGallery` — and defers everything that requires the still-placeholder image endpoints.

**Architecture:** `FileUploader` is shared upload UX with zero knowledge of what it's uploading (no "product", "image", "STL", "BYI") — transport is an injected `UploadDriver` seam, so no real HTTP exists in this component. `ImageGallery` is a frontend-normalized gallery presentation (`GalleryImageModel`) with explicit Move-up/Move-down reorder controls (not pointer drag) and cover/delete seams, reusing the existing `ConfirmDialog`.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-012 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-012 entry and §11 (Upload Architecture).

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-012), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-012, §11 Upload Architecture, §14 Responsive Strategy, §17's existing image/asset-URL and cursor gaps), `docs/plans/frontend-slices/FVS-011-IMPLEMENTATION-PLAN.md`, `FVS-007/009-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`, `package.json`. Inspected `src/components/forms/`, `src/components/admin/`, `src/components/feedback/`, `src/lib/api/`, `src/app/admin/` (does not exist). Searched for `upload`/`FileUploader`/`dropzone`/`drag`/`progress`/`AbortController`/`XMLHttpRequest`/`multipart`/`FormData`/`image`/`gallery`/`cover`/`reorder` and any OpenAPI/storage-contract source — **none exists beyond the planning documents' own text.**

**Confirmed by repository evidence:**
- **Every FVS-012 endpoint path is a frontend-constructed placeholder** — `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` line 348 says so explicitly, matching FVS-011's own placeholder treatment. No production call is implemented.
- Transport mechanism is partially confirmed by §11: **multipart POST, not chunked/resumable** ("nothing in the backend plan describes a resumable/chunked upload protocol, so none is assumed"). The *exact* choice between `XMLHttpRequest` and `fetch` for progress events is left open by the same section ("via XMLHttpRequest/fetch upload-progress events") — not resolved further here, and native `fetch` upload-progress support is inconsistent across browser engines, so this stays recorded as integration work for T06.
- §11 also describes an intended future **"scanning" polling phase** as a frontend architecture idea — but this is the frontend plan's own anticipated UX, not a confirmed backend response shape; VS-012's backend text never states whether the upload response is synchronous accept/reject or async-with-a-pending-scan-state. **Not modeled in T01's safe local states** — recorded as a discrepancy, not guessed (see §5/T01).
- Backend is authoritative for real file-content inspection, MIME acceptance, size/count limits, and malware scanning (VS-012's own Logic line: "inspect content not extension... MalwareScannerPort"). Client prechecks are UX-only, never a security boundary — enforced throughout T01/T02 via `#SECURITY-UPLOAD-PRECHECK`.
- Accessibility: drag-reorder must have a keyboard-operable alternative (FVS-012 Accessibility line) — resolved here by building **only** explicit Move-up/Move-down buttons this batch, deferring pointer drag entirely (see §5/T04) rather than building both.
- Cover-selection race is explicitly named ("server rejects a second concurrent cover-set — UI refetches and shows the actual current cover") — confirms the UI must never locally declare cover success before a server response; `ImageGallery`'s `onSetCover` is a pure presentation seam with no optimistic local cover state.

**What is genuinely unconfirmed:** exact upload/update/delete/cover/reorder endpoint paths; multipart field name(s); one-file-per-request vs. multiple; upload success status/response schema; exact image id/URL/order/cover field names; whether SVG is allowed; exact MIME/size/count limits; whether scanning is synchronous or returns a pending state, and its rejection status/code; CSRF/MFA; cover/reorder/delete request bodies and conflict semantics; whether deleting the current cover auto-selects another.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Upload** | Exact path, multipart field name(s), one-file-vs-many, success status/response schema | **NEEDS BACKEND CONFIRMATION** — explicitly placeholder |
| **Upload** | Transport mechanism (`multipart POST`, not chunked) | **CONFIRMED** (§11) — exact `XHR` vs `fetch` choice still open |
| **Upload** | CSRF/MFA | **BLOCKED ON FVS-005** (not reopened) |
| **Limits** | Allowed MIME types, max bytes, max count, dimension constraints, SVG allowed | **NEEDS BACKEND CONFIRMATION** — no number/type is hardcoded anywhere in this batch |
| **Scanning** | Synchronous vs. async-with-pending-state; rejection status/code/message field | **NOT CONFIRMED — discrepancy recorded** (§0) |
| **Image model** | Exact id/URL/order/cover/caption field names | **NEEDS BACKEND CONFIRMATION** (also open as the existing §17 "Image/asset URL format" gap) |
| **Cover** | Exact endpoint/body, conflict/race behavior, authoritative-response guarantee | **NEEDS BACKEND CONFIRMATION** — race is named conceptually, mechanism is not |
| **Reorder** | Exact endpoint/body, id-vs-position representation, conflict behavior | **NEEDS BACKEND CONFIRMATION** |
| **Delete** | Exact endpoint/response, deleting-current-cover behavior, soft/hard semantics | **NEEDS BACKEND CONFIRMATION** |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Upload domain model + precheck config seam | **CAN IMPLEMENT NOW** |
| T02 | `FileUploader` (absorbs T03 — see below) | **CAN IMPLEMENT NOW** |
| T03 | Upload controller/driver seam | **Absorbed into T02** — see §5 |
| T04 | `ImageGallery` + accessible reorder + cover/delete seams | **CAN IMPLEMENT NOW** |
| T05 | Cover/delete presentation + `ConfirmDialog` reuse | **Absorbed into T04** — delete-confirmation is integral to the gallery's own row interaction, exactly like FVS-009/010's own T04 precedent |
| T06 | Real upload/image API adapter | **BLOCKED ON BACKEND CONTRACT** |
| T07 | Embedding in `ProductForm` edit page | **BLOCKED ON FVS-011 (ProductForm itself still deferred) + T06** |
| T08 | Integration/accessibility/security review | **BLOCKED** (nothing contract-dependent exists yet to review) |
| T09 | Deterministic E2E/docs | **BLOCKED** |
| T10 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02 (incl. T03), T04 (incl. T05). T06–T10 blocked.

---

## 4. Backend Questions For Tomorrow

**Upload:** 1. Exact upload path. 2. One file per request or many? 3. Multipart field name(s). 4. Extra multipart fields? 5. Upload success status. 6. Exact response schema. 7. Exact image id field. 8. Exact image URL/storage representation (shared with the existing §17 image/asset-URL gap). 9. CSRF specifics. 10. Admin/MFA (inherits FVS-005's open gate).

**Limits:** 11. Exact allowed content/MIME types. 12. Maximum file bytes. 13. Maximum images/product. 14. Dimension constraints. 15. Is SVG allowed? 16. Any filename rules?

**Scanning:** 17. Is scanning synchronous before success, or can the response return a pending state? 18. Exact scan-rejection status/code. 19. Exact human-safe rejection message field. 20. Are validation and malware failures distinguishable? 21. Is a rejected upload persisted anywhere?

**Progress/cancel:** 22. Recommended upload transport (`XHR` vs `fetch`). 23. Does cancelling require server-side cleanup? 24. Any resumable upload support (not assumed)?

**Image model:** 25. Exact returned metadata. 26. Cover field. 27. Order field. 28. Caption/alt metadata? 29. Version/concurrency field?

**Cover:** 30. Exact cover endpoint/body. 31. Success response. 32. Concurrent-cover-conflict status/code. 33. Does the response return the authoritative current gallery/cover?

**Reorder:** 34. Exact reorder endpoint. 35. Exact request body (ids or positions?). 36. Success response. 37. Conflict behavior.

**Delete:** 38. Exact delete endpoint. 39. Success response. 40. What happens when deleting the current cover — does the server auto-select another? 41. Soft/hard delete semantics?

**Testing:** 42. Supported disposable product/image upload setup. 43. Supported way to simulate a scan rejection. 44. Supported file fixtures/size limits for acceptance tests.

---

## 5. Task Detail (Safe Batch)

### FVS012-T01 — Upload Domain Model

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/forms/uploadTypes.ts` (+test).
**Design:** `UploadStatus = "queued" | "uploading" | "failed" | "done"` — deliberately **not** `"accepted"|"scanning"|"quarantined"|"stored"` (§0's recorded discrepancy). `UploadQueueItem` (`id`, `file`, `status`, `progress`, `rejectionReason?`); ids are locally generated, never derived from filename. `UploadValidationConfig` (`allowedMimeTypes?`, `maxBytes?`, `maxFiles?`) — every field optional, no field ever defaulted to a real-world number/type. `precheckFiles(files, config, currentAcceptedCount)` is the pure precheck function, UX-only (`#SECURITY-UPLOAD-PRECHECK`).
**Marker:** `#ARCHITECTURE-UPLOAD-ADAPTER`.
**Tests:** 7 pure-function tests (no config → accept-all; MIME allow/reject; size allow/reject; `maxFiles` counted against both the current batch and a nonzero starting count).

### FVS012-T02 — `FileUploader` (absorbs T03)

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/forms/FileUploader.tsx` (+test).
**Why T03 is absorbed:** the plan's own instruction permits this when "FileUploader itself cleanly handles these concerns with an injected driver." The `UploadDriver` type (`(file, {onProgress, signal}) => Promise<{ok:true}|{ok:false;reason}>`) *is* that transport seam — a separate controller/hook wrapping it would add no real separation of concerns, since no production HTTP exists in either task yet.
**Design:** Real `<input type="file">` (never a div-only picker) plus a drop-zone wrapper; `multiple` is a prop. Selection runs `precheckFiles`; locally-rejected files render as `role="alert"` text and never reach the driver. Accepted files are queued and immediately started via the injected driver. Cancel aborts via `AbortController`; a cancelled upload's late-settling promise is ignored via a cancelled-ids guard (never overwrites a cancelled item with a stale "done"). Retry re-invokes the driver with the exact same `File` object — never re-reads from disk, never persists it. A single `aria-live="polite"` status region announces state *transitions* (not every progress tick) to avoid screen-reader spam; the visual per-file progress uses a native `<progress>` element (implicit `role="progressbar"`). "Uploaded" text is shown only after the driver's promise resolves `{ok:true}` — never from progress reaching 100%, satisfying the "100% transferred ≠ accepted" rule. A thrown/rejected driver (vs. a declared `{ok:false,reason}`) never has its raw error rendered — a generic fallback message is shown instead.
**Marker:** `#FVS012-UPLOAD`.
**Tests:** TDD — the 20-of-22-item matrix that applies without a real network (native input; `multiple`; drop accepted; picker accepted; exact File passed to the driver; MIME/size/count prechecks reject locally and never call the driver; no hardcoded limit when none configured, for both size and MIME; progress indicator present; native `<progress>`; `aria-live="polite"` region always present; 100%-bytes ≠ success; cancel aborts the signal; retry reuses the same File; driver's specific rejection reason shown; raw exception never rendered; no storage; no real `fetch`). Two items from the source's suggested matrix — "no product-specific knowledge" and "no real network call from presentational unit test" — are satisfied by construction/by the no-`fetch` test respectively rather than needing their own separate assertion. 20 tests.

### FVS012-T04 — `ImageGallery` (absorbs T05)

**Status:** CAN IMPLEMENT NOW.
**Files:** `src/components/admin/ImageGallery.tsx` (+test).
**Why T05 is absorbed:** delete-confirmation is not a separable concern from the gallery's own row interaction — same reasoning as FVS-009/010's own T04 precedent (`ConfirmDialog` needs no change, it's just wired in).
**Design:** `GalleryImageModel` (`id`, `src`, `accessibleLabel`, `isCover`) — a UI shape only, no backend field names claimed. Renders a real `<ul>/<li>` list with `<img alt={accessibleLabel}>`. Cover state is a visible text badge ("Cover"), never icon/color alone. Reorder is explicit "Move up"/"Move down" buttons — **pointer drag is deliberately deferred** (see below); buttons are disabled at the first/last boundary and call `onReorder(nextIds)` with the full resulting id order, never persisting anything locally. `onSetCover`/`onDelete` are pure presentation seams — no optimistic local cover state (the cover race is explicitly named in the source; this component never pre-empts the server's answer). Delete goes through the existing `ConfirmDialog`.
**Drag-reorder decision:** per the task's own instruction ("if drag implementation becomes disproportionately complex without adding value, prioritize explicit Move Up/Down controls now"), pointer drag was not built this batch. The `onReorder(nextIds)` callback shape already matches what a future drag enhancement would call — adding it later needs no redesign, only an additional input mechanism alongside the existing buttons. This also directly satisfies the source's own touch-device requirement without any `isTouchDevice` detection: the same buttons work for mouse, keyboard, and touch alike.
**Tests:** TDD — images render with accessible labels; cover shown as exact text ("Cover", disambiguated from the "Set as cover" button's own text); set-cover/move-up/move-down callbacks fire with expected data; first/last boundary buttons disabled; buttons are real `<button>` elements; delete opens the real `ConfirmDialog` (`aria-modal="true"`); cancel/confirm wiring; no network; no storage. 13 tests.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency.
- No production API calls, no multipart field names, no server-response DTOs, no scanning-error parser, no real MIME/size/count limits, no product-specific `FileUploader` configuration, no `/admin/products/:id/edit` embedding, no image TanStack Query, no real upload E2E until T06–T10 unblock.
