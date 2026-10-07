# FVS-015 — Bring Your Idea (BYI) Public Submission — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: HIGH — unauthenticated upload/security.

**Goal:** A guest (no login) eventually submits a description + attachments, protected by a captcha, and receives a safe receipt. This batch builds the form/attachment/receipt presentation and resolves the critical FileUploader-compatibility question the task required auditing before writing any code; the real submission, captcha, and route all stay correctly deferred/blocked.

**Architecture:** `BringYourIdeaForm` collects only the two VS-014-confirmed public fields (description, attachments) using plain local state — no RHF/Zod schema yet, since the real request body isn't confirmed. Attachments reuse FVS-012's `FileUploader` component directly, mounted in its deferred-selection mode (see §0's UPLOADER-REUSE FOLLOW-UP) — not a duplicated picker. `byiTypes.ts` defines UI-only error categories; `SuccessReceipt` is a generic confirmation.

**Spec:** `vertical-slice-plan.md`'s VS-014 entry and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-015 entry.

---

## 0. Repository / Contract Audit — Including the Required FileUploader-Compatibility Finding

Read: `vertical-slice-plan.md` (VS-014), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-015, existing §17 captcha/rate-limit gaps), `FVS-012-IMPLEMENTATION-PLAN.md`, `FVS-007-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`, `package.json`. Inspected `src/components/forms/FileUploader.tsx`, `uploadTypes.ts`, `Form.tsx`, `src/components/feedback/`, `src/lib/api/`, `src/app/`. Searched for `custom request`/`bring your idea`/`BYI`/`captcha`/`recaptcha`/`hcaptcha`/`turnstile`/`attachment`/`retention`/`rate limit`/`Retry-After`/`custom-requests`/`multipart` and any OpenAPI source. **No captcha package is installed** (`package.json` checked directly).

**Critical finding, now resolved by an architecture correction (UPLOADER-REUSE FOLLOW-UP) — superseding this plan's original conclusion:**

`vertical-slice-plan.md`'s VS-014 entry states the request/response schema as **"Multipart `CustomRequestCreate`, safe receipt response"** — a single combined request. This is option **B** from the original task's A/B/C question: one multipart POST containing description + captcha + all attachments together, not a two-phase "upload each attachment first, then reference its id" flow (option A), confirmed directly by the backend's own authoritative plan.

The **original** version of this plan concluded `FileUploader` (the component) could not be reused at all, because its `startUpload` began an independent async upload **the moment a file is accepted** via an injected driver — a model built for "each file is its own resource" (admin product images, genuinely POSTed individually), not "every field and file travel together in one request fired once, at form submit." That conclusion was correct about the *conflict*, but drew the wrong-sized consequence: it treated the whole component as unreusable and fell back to reusing only the bare `precheckFiles` pure function, leaving `BringYourIdeaForm` with its own duplicated selection/list/announce logic.

**Correction:** `FileUploader` was refactored (not replaced) so its `driver` prop is now **optional**. The selection/dropzone/precheck/list/announce layer was always transport-independent in spirit — it just hadn't been given a way to say "don't start uploading." With `driver` supplied, behavior is 100% unchanged (immediate upload, progress, cancel, retry — proven by the full existing FVS-012 test suite still passing untouched). With `driver` omitted, accepted files are held in memory as a new, honest `"selected"` status (never `"done"`/`"uploaded"` — nothing is sent) and reported to the parent via a new `onSelectionChange` callback; Cancel/Retry never render for a merely-selected file (nothing is in flight) — only a `Remove` control. `BringYourIdeaForm` now mounts `<FileUploader driver={undefined}>` (i.e., omits `driver`) instead of its own picker, removing the duplicated precheck/list/announce code entirely. **`FRONTEND-VERTICAL-SLICE-PLAN.md`'s own FVS-015 line ("reuses `FileUploader` from FVS-012") is now actually true in implementation, not just in planning prose.**

**Confirmed by repository evidence:**
- Guest flow: no login, no `ProtectedRoute`, no `AuthProvider` requirement (VS-014's own description; FVS-015's own State line: "no auth/session involvement").
- Captcha provider is explicitly unconfirmed (VS-014: "Shared CaptchaPort"; already an open §17 item, "Captcha provider" — cross-referenced, not duplicated). No captcha package installed, none added this batch.
- Rate-limit (429) response detail is already an open §17 item ("Rate-limit response detail (429)") — cross-referenced, not duplicated.
- Only two public fields exist anywhere in either governing document: description and attachments (VS-014's Model-change line: `custom_requests`/`custom_request_attachments`) — no name/email/phone/address/budget was invented.
- VS-014's Logic line confirms strict attachment count/size limits, magic-byte validation, image re-encoding, and ClamAV scanning all happen **server-side** — client prechecks here are UX-only, exactly like FVS-012's own `#SECURITY-UPLOAD-PRECHECK` precedent.

**What is genuinely unconfirmed:** exact request Content-Type/field names; description validation (required? max length?); exact success status/response schema and which fields are safe to show; attachment MIME/size/count limits; whether scanning is synchronous; exact rejection status/code/message field; captcha provider/site-key mechanism/token format/backend field/failure status; exact rate-limit dimension and `Retry-After` presence/format.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Request** | Single bundled multipart request (not two-phase upload-then-reference) | **CONFIRMED** (§0) |
| **Request** | Exact Content-Type/field names, description validation, success status/response | **NEEDS BACKEND CONFIRMATION** |
| **Captcha** | Provider, site-key mechanism, token format, backend field, failure status | **NEEDS BACKEND CONFIRMATION** — existing §17 gap |
| **Attachments** | FileUploader-component compatibility | **RESOLVED — reused directly via a new deferred-selection mode** (§0, UPLOADER-REUSE FOLLOW-UP) |
| **Attachments** | Exact MIME/size/count limits | **NEEDS BACKEND CONFIRMATION** — no number hardcoded |
| **Attachments** | Scanning synchronicity, rejection status/code/message field | **NEEDS BACKEND CONFIRMATION** |
| **Rate limit** | Exact dimension, `Retry-After` presence/format | **NEEDS BACKEND CONFIRMATION** — existing §17 gap |
| **Route** | `/bring-your-idea` | **CORRECTLY DEFERRED** — shipping it now would visually imply a working secure submission with no real captcha/backend behind it |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized BYI error-kind model (`byiTypes.ts`) | **CAN IMPLEMENT NOW** |
| T02 | `BringYourIdeaForm` presentation | **CAN IMPLEMENT NOW** |
| T03 | FileUploader compatibility audit | **DONE — see §0; result: refactored `FileUploader` to support deferred selection, now reused directly** |
| T04 | Captcha integration boundary | **Design-only** — `captchaSlot` seam built into T02; actual `CaptchaWidget` **BLOCKED** (provider unconfirmed) |
| T05 | Submission API adapter | **BLOCKED ON BACKEND CONTRACT** |
| T06 | `/bring-your-idea` route | **CORRECTLY DEFERRED** (see above) |
| T07 | Integration/security/accessibility review | **BLOCKED** (nothing contract-dependent exists yet) |
| T08 | Deterministic E2E/docs | **BLOCKED** |
| T09 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

Also built this batch, not in the original suggested list: `SuccessReceipt` (safe generic confirmation presentation, folded into T02's scope since it's a small sibling to the form with no independent task weight).

## 3. Safe Batch

T01, T02 (incl. `SuccessReceipt`), T04 (design-only — the slot seam, not a real widget). T05/T06 deferred/blocked; T07–T09 blocked.

---

## 4. Backend Questions For Tomorrow

**Request:** 1. Exact request Content-Type. 2. Exact description field name. 3. Is description required? 4. Min/max length. 5. Whitespace/normalization behavior. 6. Any other public fields besides description + attachments? 7. Exact success status. 8. Exact success response schema. 9. Which response fields are safe to show a guest?

**Attachments:** 10. Confirmed: same POST, not pre-upload (§0) — exact multipart field name(s) for the files. 11. One field vs. multiple field semantics. 12. Allowed content types. 13. Max bytes/file. 14. Max number of files. 15. Total request-size limit. 16. Filename restrictions. 17. Is scanning synchronous before the success response? 18. Is there a pending/quarantine state? 19. Exact rejection status/code. 20. Exact safe rejection-message field. 21. Private-storage guarantee. 22. Retention period/source. 23. Cleanup behavior for a rejected request.

**Captcha:** 24. Exact provider. 25. Site-key distribution/env variable. 26. Client integration package/script. 27. Token/proof format. 28. Backend request field. 29. Token lifetime. 30. Single-use? 31. Retry/reset requirement. 32. Exact failure status/code. 33. Provider-down behavior. 34. Accessible/audio-challenge behavior expected from the provider (so the widget, once built, doesn't break it).

**Rate limit:** 35. Exact rate. 36. Dimension (IP/fingerprint/etc.). 37. Is `Retry-After` provided? 38. Seconds or date format? 39. Error code. 40. May the exact wait time be displayed?

**Errors:** 41. Validation-error shape. 42. Generic server-error shape. 43. Storage/disk-failure mapping. 44. Human-safe message fields.

**Testing:** 45. Supported captcha test mode/test key. 46. Supported guest test fixture. 47. Valid attachment fixture. 48. Invalid-type fixture. 49. Oversized fixture. 50. Scan-rejection fixture. 51. Rate-limit acceptance-test procedure.

---

## 5. Task Detail (Safe Batch)

### FVS015-T01 — Normalized Error Model

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/byi/byiTypes.ts` (no dedicated test — pure types, matching `settingTypes.ts`/`referenceDataTypes.ts` precedent).
**Design:** `ByiErrorKind = "captcha" | "rate-limit" | "attachment" | "generic"` — UI categories only, never a backend error-code claim. `ByiSubmissionError { kind, message }` — `message` for `"attachment"` must be the backend-confirmed human-safe field once it exists; a component never infers a kind from message text.
**Marker:** `#ARCHITECTURE-BYI-SUBMISSION-ADAPTER`.

### FVS015-T02 — `BringYourIdeaForm` + `SuccessReceipt`

**Status:** CAN IMPLEMENT NOW (revised after the UPLOADER-REUSE FOLLOW-UP). **Files:** `src/components/byi/BringYourIdeaForm.tsx` (+test), `SuccessReceipt.tsx` (+test).
**Design:** Only `description` (textarea) and `attachments` exist — no name/email/phone was invented. Attachment selection now reuses the **shared `FileUploader` component** (see §5/T03 below) in its deferred-selection mode (no `driver` prop) — not a bare `precheckFiles` call duplicated into this form. `BringYourIdeaForm` itself holds no precheck/rejection/announcement state of its own anymore; it only tracks `attachments: readonly File[]`, updated via `FileUploader`'s `onSelectionChange`. Duplicate submission is prevented by disabling the submit button while `isSubmitting` and guarding the handler itself. Error copy is fixed for `captcha`/`rate-limit`/`generic` (frontend-owned, matching the exact product copy the task itself supplied as acceptable); `attachment` always shows the caller-supplied `message` verbatim, never a client-invented generic. `captchaSlot` is a plain `ReactNode` rendering seam — no captcha logic, no fake widget, nothing rendered unless a caller supplies one. `SuccessReceipt` is a small, separate, generic confirmation component with a safe default message and no internal id/storage-key/attachment-URL/captcha-proof exposure.
**Markers:** `#FVS015-BYI-FORM`.
**Tests:** `BringYourIdeaForm` — 17 (accessible description field, no unconfirmed fields, submit payload shape, duplicate-submit guard, three fixed-copy error kinds + verbatim attachment message, local precheck rejection never reaching `onSubmit`, no hardcoded limit when unconfigured, remove-before-submit, captcha slot rendering, **uses the shared `FileUploader` dropzone, not a duplicated picker**, **no fake progress/upload-complete state while merely selected**, no network, no storage). `SuccessReceipt` — 3 (default message, custom message, `role="status"`).

### FVS015-T03 — FileUploader Compatibility Audit → Architecture Correction

**Status:** DONE — see §0 for the full finding and the UPLOADER-REUSE FOLLOW-UP's correction. `FileUploader.tsx`/`uploadTypes.ts` were refactored (not replaced): `driver` became optional, a new `"selected"` status and `onSelectionChange` callback were added for deferred mode, and all existing immediate-mode behavior (progress/cancel/retry/aria-live/precheck/no-hardcoded-limits) was proven unchanged by the full pre-existing FVS-012 test suite still passing. `BringYourIdeaForm` (T02) now mounts `FileUploader` directly instead of a second, duplicated attachment picker.

### FVS015-T04 — Captcha Integration Boundary

**Status:** Design-only this batch. The `captchaSlot` prop on `BringYourIdeaForm` **is** the entire boundary — a plain rendering seam with zero provider-specific code, env variable, token field, callback name, or expiry/refresh assumption. The actual `CaptchaWidget` stays blocked until the provider is confirmed (§4 Q24–34).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency — no captcha package installed.
- No production API call, no real `CustomRequestCreate` body, no multipart field names, no hardcoded attachment limits, no backend error-code mapping, no `/bring-your-idea` route, no real E2E, until T05/T06 unblock.
