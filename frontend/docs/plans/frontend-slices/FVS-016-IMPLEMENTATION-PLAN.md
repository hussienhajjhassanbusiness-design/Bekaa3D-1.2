# FVS-016 — Public Contact Form — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: Medium — guest abuse surface.

**Goal:** A visitor eventually sends a name/email/message contact request, protected by the same captcha/rate-limit pattern as BYI, receiving a safe receipt. This batch extracts the shared guest-submission feedback vocabulary FVS-015 already needed, builds `ContactForm`, and generalizes `SuccessReceipt` into a truly shared primitive — then correctly defers the captcha widget, the real submission adapter, and the `/contact` route.

**Architecture:** `src/components/forms/guestSubmissionFeedback.ts` is the one shared captcha/rate-limit/generic vocabulary + copy, used by both `BringYourIdeaForm` (FVS-015, refactored) and the new `ContactForm`. `SuccessReceipt` moved from `src/components/byi/` to `src/components/feedback/` as a genuinely generic primitive (required `message`, no BYI-flavored default). `ContactForm` is presentational-only, rendering exactly the three VS-015-confirmed fields.

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-015 entry (guest half) and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-016 entry.

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-015), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-016, existing §17 captcha/rate-limit gaps), `docs/plans/frontend-slices/FVS-015-IMPLEMENTATION-PLAN.md`, `docs/plans/frontend-slices/FVS-007-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`, `package.json` (no captcha package installed, confirmed again). Inspected `src/components/byi/`, `src/components/forms/`, `src/components/feedback/`, `src/lib/api/`, `src/app/`. Searched for `contact`/`contact message`/`captcha`/`rate limit`/`Retry-After`/`guest submission`/`SuccessReceipt`/`ByiErrorKind`/`captchaSlot`/`public form`/`contact-messages` and any OpenAPI source — **none exists beyond what FVS-015 already built.**

**Shared-pattern audit (explicitly required before building anything):** FVS-016's own source line says to reuse FVS-015's captcha pattern, but FVS-015 has no concrete `CaptchaWidget` (provider unconfirmed) — so "reuse" cannot mean reusing a real widget. What **is** real and reusable is FVS-015's safe captcha/rate-limit/generic copy and its `captchaSlot` rendering seam. Rather than let `ContactForm` define its own near-identical `FIXED_ERROR_COPY` object (producing two slightly-divergent guest-submission vocabularies over time), that copy was extracted into `src/components/forms/guestSubmissionFeedback.ts` (`GuestSubmissionErrorKind = "captcha" | "rate-limit" | "generic"` + `GUEST_SUBMISSION_ERROR_COPY`), and `BringYourIdeaForm`'s own `ByiErrorKind` now extends it (`GuestSubmissionErrorKind | "attachment"`) instead of duplicating the three shared kinds. This is a small, flat extraction — no inheritance framework, no elaborate type hierarchy.

**Confirmed by repository evidence:**
- Exactly three public fields exist anywhere in either governing document: name, email, message (VS-015's Model-change line: `contact_messages`; FVS-016's own capability line: "name/email/message") — no phone/subject/company/order-number/account-id was invented.
- No login, no `ProtectedRoute`, no `AuthProvider` requirement (VS-015's own guest-half description; FVS-016's own State line: "Form state only").
- Captcha provider is explicitly unconfirmed — same already-open §17 "Captcha provider" gap as FVS-015, not duplicated.
- Rate-limit (429) response detail is the same already-open §17 gap as FVS-015, not duplicated.
- `SuccessReceipt` (FVS-015) was already fully generic in *behavior* but not in *API* — its optional `message` prop defaulted to BYI-flavored copy ("…received your idea…"). Generalized: `message` is now **required**, no default, so Contact supplies its own exact copy without inheriting BYI's wording.

**What is genuinely unconfirmed:** exact request Content-Type/field names for name/email/message; validation constraints (required? min/max length? trimming?); exact success status/response and which fields are receipt-safe; whether Contact shares BYI's exact captcha proof field/rate-limit policy or has its own; exact rate-limit dimension and `Retry-After` presence/format; validation-error shape.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Request** | Endpoint path | **CONFIRMED** (literal) |
| **Request** | Exact field names, requiredness, length constraints, trimming | **NEEDS BACKEND CONFIRMATION** |
| **Request** | Success status/response, receipt-safe fields | **NEEDS BACKEND CONFIRMATION** |
| **Captcha** | Shared vocabulary/copy with BYI | **RESOLVED — extracted this batch** (§0) |
| **Captcha** | Real provider/token/field | **NEEDS BACKEND CONFIRMATION** — same open §17 gap as FVS-015 |
| **Rate limit** | Shared with BYI or separate policy; `Retry-After` | **NEEDS BACKEND CONFIRMATION** — same open §17 gap |
| **Route** | `/contact` | **CORRECTLY DEFERRED** — would visually imply abuse protection with no real captcha/API behind it |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Shared guest-submission feedback pattern (extraction + BYI refactor) | **DONE** |
| T02 | `ContactForm` presentation | **CAN IMPLEMENT NOW** |
| T03 | `SuccessReceipt` generalization/reuse | **DONE** |
| T04 | `CaptchaWidget`/provider integration | **BLOCKED ON FVS-015/backend provider** |
| T05 | Contact API adapter | **BLOCKED ON BACKEND CONTRACT** |
| T06 | `/contact` route | **CORRECTLY DEFERRED** (see above) |
| T07 | Integration/accessibility/E2E/docs | **BLOCKED** |
| T08 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01 (done), T02, T03 (done). T04/T05/T06 deferred/blocked; T07/T08 blocked.

---

## 4. Backend Questions For Tomorrow

**Request:** 1. Exact Content-Type. 2. Exact name field. 3. Is name required? 4. Name min/max length? 5. Name trimming/normalization? 6. Exact email field. 7. Email validation/normalization? 8. Exact message field. 9. Message min/max length? 10. Message whitespace behavior. 11. Any fields besides name/email/message? 12. Unknown-field behavior. 13. Exact success status. 14. Exact success response. 15. Which response fields are safe for the receipt?

**Captcha:** 16. Same provider/proof field as BYI, or separate? 17. Exact failure status/code. 18. Reset/retry semantics.

**Rate limit:** 19. Exact rate. 20. Same policy as BYI or separate? 21. Is `Retry-After` supplied? 22. Exact rate-limit code/body.

**Errors:** 23. Validation-error shape. 24. Safe human-readable field. 25. Generic server-error behavior.

**Testing:** 26. Supported captcha test mode. 27. Disposable happy-path contact fixture. 28. Rate-limit acceptance-test procedure.

---

## 5. Task Detail (Safe Batch)

### FVS016-T01 — Shared Guest-Submission Feedback Pattern

**Status:** DONE. **Files:** `src/components/forms/guestSubmissionFeedback.ts` (+test); `src/components/byi/byiTypes.ts` (refactored), `BringYourIdeaForm.tsx` (refactored).
**Design:** See §0. `GuestSubmissionErrorKind`/`GuestSubmissionError`/`GUEST_SUBMISSION_ERROR_COPY` are the one shared vocabulary; BYI's `ByiErrorKind` extends it with `"attachment"`. All 20 of FVS-015's pre-existing BYI tests pass unchanged after the refactor — proof the extraction is behavior-preserving.
**Marker:** `#SHARED-GUEST-SUBMISSION-FEEDBACK`.
**Tests:** 3 (exact captcha/rate-limit/generic copy).

### FVS016-T02 — `ContactForm`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/contact/ContactForm.tsx` (+test).
**Design:** Exactly three fields — `name` (text input), `email` (`type="email"` for native browser semantics only, never treated as authoritative validation), `message` (textarea). No phone/subject/company was added. Reuses `GUEST_SUBMISSION_ERROR_COPY` for `captcha`/`rate-limit`/`generic` guidance — identical wording to BYI, by construction, not by coincidence. `captchaSlot` is the same plain `ReactNode` seam pattern as BYI — no fake captcha. Duplicate submission prevented by disabling the submit button while `isSubmitting` and guarding the handler. No aggressive client-side trimming/normalization beyond what the native `<input>`/`<textarea>` already do, since no backend constraint is confirmed.
**Marker:** `#FVS016-CONTACT-FORM`.
**Tests:** accessible name/email/message fields, no unconfirmed fields (phone/subject/company absent), submit payload shape, duplicate-submit guard, three shared-copy error kinds, success-receipt-ready (via the shared `SuccessReceipt`, composed by a future parent), no raw backend object, no network, no storage.

### FVS016-T03 — `SuccessReceipt` Generalization

**Status:** DONE. **Files:** `src/components/feedback/SuccessReceipt.tsx` (+test) — moved from `src/components/byi/`, old files removed (no other consumer existed, confirmed by repo search before deleting).
**Design:** `message` is now a required prop with no default — the original BYI version's default text ("…received your idea…") would have been wrong copy for Contact. Still exposes a `role="status"` region; still no internal id/storage-key/attachment-URL/captcha-proof exposure.
**Marker:** `#SHARED-SUCCESS-RECEIPT`.
**Tests:** 3 (renders supplied message with two different callers' own copy, proving genericity; `role="status"` present).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency — no captcha package installed.
- No production API call, no real request body, no `/contact` route, no real E2E, until T04/T05/T06 unblock.
