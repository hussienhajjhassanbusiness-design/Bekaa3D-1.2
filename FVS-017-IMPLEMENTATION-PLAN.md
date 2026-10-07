# FVS-017 — Admin Contact Message Queue — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: Low.

**Goal:** Admin eventually lists/filters/reads/transitions contact messages through `new → read → replied → archived`. This batch builds the normalized status workflow, generalizes the shared `StatusBadge`, builds `MessageDetail`, and a key-agnostic URL-filter normalizer — then correctly defers the actual `AdminTable` queue composition, since the list-row field guarantee is unconfirmed.

**Architecture:** `contactMessageWorkflow.ts` is the one pure source of legal transitions + status descriptions. `StatusBadge` (FVS-009) is generalized from a fixed `"active"|"deactivated"` union to a small `{label, tone}` descriptor so it serves both domains without losing type safety. `MessageDetail` composes the workflow + badge + `ConfirmDialog`-free action button. `contactQueueFilter.ts` normalizes an already-extracted URL value without choosing the parameter's key name.

**Spec:** `vertical-slice-plan.md`'s VS-015 entry (admin half) and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-017 entry.

---

## 0. Repository / Contract Audit

Read: `vertical-slice-plan.md` (VS-015), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-017), `FVS-009-IMPLEMENTATION-PLAN.md`, `FVS-016-IMPLEMENTATION-PLAN.md`, `FVS-005-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/components/admin/AdminTable.tsx`, `StatusBadge.tsx`, `src/components/feedback/ConfirmDialog.tsx`, `src/lib/admin/`, `src/app/admin/` (does not exist). Searched for `contact message`/`MessageDetail`/`contact status`/`new`/`read`/`replied`/`archived`/`status filter`/`AdminTable`/`StatusBadge`/`searchParams`/`contact-messages` — confirms no prior contact-queue code exists, and `StatusBadge` has exactly one existing consumer concept (FVS-009's admin-account status, itself not yet wired into any production page).

**Confirmed by repository evidence:**
- The status set and its linear order are both confirmed PRODUCT behavior, not an invented workflow engine: VS-015's own Logic line lists "new/read/replied/archived state," and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s own FVS-017 capability line states the sequence explicitly: **"new → read → replied → archived."** No skip transitions, no reverse transitions are given anywhere — so none are built.
- VS-015's own admin-half endpoint line is prose-only, already flagged `NEEDS BACKEND CONFIRMATION` by the source itself (§17) — every path/body/field below is treated accordingly.
- `AdminTable`/`ConfirmDialog` already exist (FVS-009/007) and need no further implementation — reused conceptually (action buttons), not duplicated.
- **No literal URL parameter name is given anywhere** for the status filter — `FRONTEND-VERTICAL-SLICE-PLAN.md` only says "URL-synced status filter" conceptually, unlike `/shop`'s own confirmed `category=`/`material=`/`colour=` keys (FVS-013). The key name stays an explicit, recorded open decision — not silently chosen.
- `StatusBadge`'s only existing consumer is its own test file — no production code imports it yet, confirmed by repo search before refactoring its API.

**What is genuinely unconfirmed:** every list/detail/PATCH endpoint path, pagination model, response envelope, list-row fields (is name/email even included in the list, or only in detail?), exact status field/literals on the wire, PATCH request body/target-status representation, CSRF/MFA (inherits FVS-005's own open gate), conflict/concurrency behavior, audit automaticity, and the URL filter's own parameter name.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Workflow** | Status set (new/read/replied/archived) and linear order | **CONFIRMED** (VS-015 Logic line + FVS-017's own capability line) |
| **Workflow** | Exact backend-serialized enum literals | **NEEDS BACKEND CONFIRMATION** — normalized union only, no literal claimed |
| **List** | Endpoint path, pagination, response envelope, row fields | **NEEDS BACKEND CONFIRMATION** — prose-only, already an open §17 item |
| **Detail** | Exact schema, PII scope | **NEEDS BACKEND CONFIRMATION** |
| **PATCH** | Endpoint, body, target-status field, CSRF/MFA/conflict/audit | **NEEDS BACKEND CONFIRMATION** (MFA inherits FVS-005's open gate, not reopened) |
| **URL filter** | Parameter key name | **NOT CONFIRMED — left explicitly open**, only value-normalization is built (§0/§5/T04) |
| **Shared components** | `AdminTable`/`ConfirmDialog`/`StatusBadge` availability | **CONFIRMED** — all exist; `StatusBadge` generalized this batch |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized contact-message status workflow | **CAN IMPLEMENT NOW** |
| T02 | `StatusBadge` generalization (label+tone) | **CAN IMPLEMENT NOW** |
| T03 | `MessageDetail` presentation | **CAN IMPLEMENT NOW** |
| T04 | URL status-filter value normalizer (key-agnostic) | **CAN IMPLEMENT NOW** |
| T05 | `AdminTable` contact queue composition | **CORRECTLY DEFERRED** — list-row field guarantee (name/email in list) unconfirmed |
| T06 | API/query/mutation adapters | **BLOCKED ON BACKEND CONTRACT** |
| T07 | `/admin/contact-messages` routes | **BLOCKED ON FVS-005 + T06** |
| T08 | Integration/E2E/docs | **BLOCKED** |
| T09 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02, T03, T04. T05 correctly deferred (not merely blocked — building it now would mean guessing which fields the list actually returns). T06–T09 blocked.

---

## 4. Backend Questions For Tomorrow

**List:** 1. Exact list endpoint. 2. Exact pagination query/model. 3. Exact status-filter query parameter. 4. Exact response envelope. 5. Exact list-row fields. 6. Is name included in the list? 7. Is email included in the list? 8. Status field/literals. 9. Created-timestamp field. 10. Default ordering. 11. Any search capability?

**Detail:** 12. Exact detail endpoint. 13. Exact `AdminContactMessage` schema. 14. Name field. 15. Email field. 16. Message field. 17. Status field. 18. Timestamp fields. 19. Any fields intentionally excluded for PII/security? 20. Not-found behavior.

**Workflow:** 21. Confirm the legal transition graph (new → read → replied → archived) server-side. 22. Any direct-skip transitions allowed? 23. Any reverse transitions allowed? 24. Is a transition idempotent (re-marking "read" on an already-read message)? 25. Concurrent-update conflict behavior.

**PATCH:** 26. Exact request body. 27. Exact target-status field. 28. Success status/body. 29. Validation/error response. 30. CSRF. 31. Admin/MFA requirement (inherits FVS-005's open gate). 32. Non-admin route hiding (inherits FVS-005's established pattern). 33. Is audit automatic? 34. Version/`updated_at`/ETag concurrency field?

**Filter/URL:** 35. Preferred frontend URL parameter name, if the product team has an opinion (not strictly a backend question, but unresolved).

**Testing:** 36. Supported way to create a disposable contact message. 37. Disposable admin setup (shared with FVS-005/009). 38. Real sequence test: submit → read → replied → archived. 39. Any captcha/rate-limit bypass or test mode needed to seed a public message for this admin-side testing?

---

## 5. Task Detail (Safe Batch)

### FVS017-T01 — Status Workflow

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/admin/contactMessageWorkflow.ts` (+test).
**Design:** `ContactMessageStatus = "new" | "read" | "replied" | "archived"` — frontend-normalized, never a claimed backend literal. `getNextContactMessageAction(status)` returns the single legal `{nextStatus, label}` or `null` at the terminal state — no generic workflow engine, just one lookup table mirroring the confirmed linear sequence. `describeContactMessageStatus(status)` returns `{label, tone}` for `StatusBadge` (T02).
**Marker:** `#ARCHITECTURE-CONTACT-STATUS-WORKFLOW`.
**Tests:** 6 (each status's single legal action, archived has none, every tone is bounded).

### FVS017-T02 — `StatusBadge` Generalization

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/StatusBadge.tsx` (+test).
**Design:** `StatusBadgeProps` changed from `{status: "active"|"deactivated"}` to `{label: string; tone: StatusBadgeTone}`, where `StatusBadgeTone = "neutral"|"positive"|"negative"|"warning"` — a small, still-bounded union, never `color: string` (which would destroy the component's own type guarantees, as the task explicitly warned against). FVS-009's `AdminAccountStatus` union and a new `describeAdminAccountStatus` function are preserved in the same file, so existing callers of that concept keep the same two-literal type; only the internal lookup became an explicit describe-step. Confirmed via repo search that `StatusBadge` has no production consumer yet, so this is a safe, non-breaking API change.
**Marker:** `#SHARED-STATUS-BADGE` (unchanged).
**Tests:** 6 (generic label rendering, no network, both `describeAdminAccountStatus` outputs regression-tested standalone and end-to-end through `StatusBadge`).

### FVS017-T03 — `MessageDetail`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/MessageDetail.tsx` (+test).
**Design:** `MessageDetailModel {name, email, message, status}` — only VS-015-confirmed fields plus the normalized status; no IP/user-agent/captcha-score/internal-notes/database-metadata/moderation-flags (`#SECURITY-CONTACT-PII`). Email renders as a `mailto:` link (a safe, uncontroversial frontend UX choice, not a backend assumption). Message renders as plain text with CSS `whiteSpace: pre-wrap` to preserve line breaks — never `dangerouslySetInnerHTML` (proven with a literal `"<b>bold</b>"` test). Only the single legal next action (via `getNextContactMessageAction`) ever renders as a real, clearly-labeled button ("Mark read"/"Mark replied"/"Archive") — no dropdown, no free text, no icon-only control. `isPending` disables the action; `error` renders caller-supplied safe text only.
**Marker:** `#FVS017-MESSAGE-DETAIL`.
**Tests:** 14 (name/email/mailto/message rendering, multiline preservation, HTML-literal safety, status badge text, exactly-one-legal-action per status × 2 statuses, no action when archived, transition callback with exact next status, pending-disables-action, safe error display, no network, no storage).

### FVS017-T04 — URL Status-Filter Normalizer

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/admin/contactQueueFilter.ts` (+test).
**Design:** `ContactStatusFilter = "all" | ContactMessageStatus`. `normalizeContactStatusFilter(rawValue: string | null): ContactStatusFilter` takes an already-extracted raw string (the caller decides which URL key to read it from — not this function) and normalizes any unknown/garbage/empty/missing value to `"all"`, never passing a raw value through to a future API call. The actual URL parameter **key name** is explicitly left open (§0) — building `parseContactQueueUrlState(params)`/`buildContactQueueUrlParams` (the `/shop`-style pair) would require choosing that key now, which no governing document confirms.
**Marker:** `#ARCHITECTURE-CONTACT-QUEUE-URL-STATE`.
**Tests:** 5 (missing→all, each known status round-trips, explicit "all" round-trips, unknown/garbage→all, empty string→all).

### FVS017-T05 — `AdminTable` Contact Queue Composition (correctly deferred)

**Status:** NOT IMPLEMENTED. VS-015's admin-half schema is prose-only; neither governing document guarantees that `name`/`email` (vs. only an id + status) appear in the **list** response specifically (as opposed to the detail response, which does confirm them conceptually). Building the actual `AdminTable` columns now would mean guessing which fields the list endpoint returns. `AdminTable` itself (FVS-009) is complete and needs no further implementation — only its *use* here is deferred.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency.
- No production API call, no guessed list/detail/PATCH DTOs, no pagination assumption, no `/admin/contact-messages` routes, no `AdminProtectedRoute` integration, no real status-filter API wiring, no E2E against an assumed endpoint, until T06/T07 unblock.
