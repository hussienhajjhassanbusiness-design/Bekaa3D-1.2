# FVS-007 — Admin Business Settings Editor — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per task, STOP after the safe frontend batch. Mirrors FVS-004/005's "fast plan" discipline — concise audit, build only what's genuinely backend-independent, log the rest as real questions.

**Goal:** An admin views and edits backend-defined business settings through typed controls (boolean toggle, number input, string input) rendered generically from a settings list — never a hand-built form per key, never a raw JSON editor.

**Architecture:** A small frontend-normalized `EditableSetting` UI model, isolated from the unconfirmed backend response shape by a future API adapter. One generic `SettingControl` picks the right native control by declared type. `SettingRow` composes label/description/control/save-seam, responsive per `bekaa3d-brand-ui`'s existing stacked-card convention. `ConfirmDialog` is new, generic, reusable modal infrastructure (none existed in this repo before this slice) with no setting-specific knowledge. No new runtime dependency.

**Spec:** `vertical-slice-plan.md`'s VS-007 entry and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-007 entry. The settings-**list** endpoint is explicitly `NEEDS BACKEND CONFIRMATION` in both this plan and `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 itself — not discovered here, already logged — and is not treated as confirmed merely because it appears in prose.

---

## 0. Repository / Contract Audit (Part A)

Read: `vertical-slice-plan.md` (VS-007), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-007 entry, §9 "API Integration Architecture," §17's VS-007 contract-gap item, the admin-table responsive note), `FVS-005-IMPLEMENTATION-PLAN.md`, `FVS-006-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/lib/api/`, `src/lib/auth/`, `src/components/forms/`, `src/components/feedback/`, `src/components/auth/`, `src/components/account/`, `playwright.config.ts`. Searched for `settings`/`accepting_orders`/`free_shipping`/`offer_floor`/`SettingRead`/`SettingUpdate`/`ConfirmDialog`/any OpenAPI or setting-registry doc — **none exist anywhere in this repository.** No `src/app/admin/` directory exists yet (expected — gated on FVS-005).

**Confirmed by repository evidence (not guessed):**
- `vertical-slice-plan.md` VS-007 gives **literal paths** for three of the four endpoints: `GET/PATCH /api/v1/admin/settings/{key}` and `GET /api/v1/settings/public`. The fourth — the settings **list** — is prose-only ("list settings," no literal path), and `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 explicitly logs this exact gap for VS-007 by name. This plan does not treat the list path as confirmed.
- `FRONTEND-VERTICAL-SLICE-PLAN.md` §9: "settings boolean toggle" is explicitly named in the frontend's own confirmed optimistic-update allowlist — this is a **frontend architecture decision**, already made, not contract-gated. (Its actual wiring still waits on the PATCH contract, same as everything else in T05.)
- `FRONTEND-VERTICAL-SLICE-PLAN.md`'s admin-table responsive note names FVS-007 directly as one of the slices using the "stacked-card fallback" pattern (vs. a horizontal-scroll table) — the responsive direction for `SettingRow` (T03) is therefore a confirmed convention, not invented.
- `vertical-slice-plan.md` VS-007: "audit every change" is a **backend-side** side effect — `FRONTEND-VERTICAL-SLICE-PLAN.md` confirms "no separate frontend audit UI needed here (that's FVS-042)." No frontend action is required for audit; nothing to build.
- The source capability's "accepting-orders" high-impact example is explicitly an "e.g." — not an exhaustive contract. No production high-impact-key set is hardcoded anywhere in this plan.

**What is genuinely unconfirmed:** the settings-list path/shape, every field name on a list item (key/type-discriminator/value/label/description/numeric-or-string-constraints/ordering/high-impact-flag), the PATCH request/response shape, validation-error shape and its safe-message field, CSRF/admin/MFA requirements at the endpoint level, and the actual source of "which keys require confirmation before saving." None of this is guessed below.

---

## 1. Contract Confidence Table (concise)

| Area | Item | Status | Consequence |
|---|---|---|---|
| **List** | Path | **NEEDS BACKEND CONFIRMATION** | Not called; T05 blocked |
| **List** | Response shape, key/type/value/label/description/constraints/ordering/high-impact fields | **NEEDS BACKEND CONFIRMATION** | `EditableSetting` (T01) is a UI model only; the future adapter maps whatever this turns out to be |
| **List** | Allowed type-discriminator values | **FRONTEND REQUIREMENT, backend enum unconfirmed** | Frontend supports exactly `boolean`/`number`/`string` per the source capability; adapter will map backend's real enum onto this, once known |
| **List** | Secret-setting exclusion | **NEEDS BACKEND CONFIRMATION** | Not assumed either way |
| **Single GET** | `GET /api/v1/admin/settings/{key}` path | **CONFIRMED** | Literal path in `vertical-slice-plan.md` |
| **Single GET** | Response shape, not-found behavior, error codes | **NEEDS BACKEND CONFIRMATION** | T05 blocked |
| **PATCH** | `PATCH /api/v1/admin/settings/{key}` path | **CONFIRMED** | Literal path |
| **PATCH** | Request body shape (`{value: ...}` or otherwise) | **NEEDS BACKEND CONFIRMATION** | T05 blocked |
| **PATCH** | Response status/body, validation-error shape, safe inline-message field, conflict/versioning, rate limit | **NEEDS BACKEND CONFIRMATION** | T05 blocked |
| **PATCH** | CSRF requirement | **NEEDS BACKEND CONFIRMATION** (pattern suggests yes, per every other authenticated write — not assumed) | T05 blocked |
| **PATCH** | Audit | **CONFIRMED — backend-automatic, no frontend action** | Nothing to build |
| **Boolean optimistic update** | Allowed as a frontend pattern | **CONFIRMED (frontend architecture, §9)** | T05 may implement optimistic+rollback once PATCH contract lands; not before |
| **High-impact keys** | Source of "requires confirmation before save" | **NEEDS BACKEND CONFIRMATION / PRODUCT-GATED** | `ConfirmDialog` (T04) built generic and key-agnostic now; the key→requires-confirmation mapping is not hardcoded anywhere |
| **Public settings** | `GET /api/v1/settings/public` path | **CONFIRMED** | Literal path; **no FVS-007 UI consumes it** — later slices' job |
| **Public settings** | Response shape, which keys are public | **NEEDS BACKEND CONFIRMATION** | Not built here regardless |
| **Admin security** | `/admin/settings` route protection, admin/MFA | **BLOCKED ON FVS-005** | Not reopened here; T06 waits for FVS-005's `AdminProtectedRoute` |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Frontend setting domain model (`EditableSetting` UI types) | **CAN IMPLEMENT NOW** |
| T02 | `SettingControl` typed renderer (boolean/number/string) | **CAN IMPLEMENT NOW** |
| T03 | `SettingRow` responsive card/row | **CAN IMPLEMENT NOW** |
| T04 | `ConfirmDialog` (new, generic, reusable) | **CAN IMPLEMENT NOW** |
| T05 | API/query/mutation integration | **BLOCKED ON BACKEND CONTRACT + FVS-005** |
| T06 | `/admin/settings` route + admin guard | **BLOCKED ON FVS-005** |
| T07 | Integration/accessibility/security review | **BLOCKED** (depends on T05/T06) |
| T08 | Deterministic E2E + docs | **BLOCKED** (depends on T07) |
| T09 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Optimized Batches

| Batch | Contents | Status |
|---|---|---|
| **Safe Batch 1** | T01–T04 | **This session** |
| Backend-unlocked batch | T05–T06 | Gate: §4 answered + FVS-005 lands |
| Closure | T07–T08 | Gate: previous batch lands |
| Real backend acceptance | T09 | Gate: real backend reachable |

---

## 4. Backend Questions For Tomorrow (Part E — consolidated)

**LIST**
1. Exact list path and HTTP verb.
2. Exact list response schema — is it `{items: [...]}`, a bare array, paginated, or something else?
3. Per item: key field name, declared-type discriminator field + its exact allowed values, current-value field, label field, description/help-text field, numeric `min`/`max`/`step` field names (if present), string constraint fields (if any), ordering/grouping field (if any), high-impact flag (if any).
4. Is label/help text supplied by the backend, or must the frontend maintain its own mirror of the setting-key registry?

**SINGLE GET**
5. Exact `GET /api/v1/admin/settings/{key}` response shape.
6. Not-found behavior and its exact status/code.

**PATCH**
7. Exact request body — is the new value wrapped (`{value: ...}`) or something else?
8. Success status and body.
9. Exact validation-failure status and RFC 9457 `code`.
10. Exact field containing the human-safe validation message the UI may render inline.
11. Does a validation error identify which field/key failed (an `errors[]`-style shape)?
12. Does PATCH require CSRF? (Likely yes under this project's existing authenticated-write convention — not assumed, confirm against VS-007 specifically.)
13. Exact admin/MFA requirement for this endpoint.
14. Non-admin/non-MFA error behavior — 404? `MFA_REQUIRED`? something else?
15. Any optimistic-concurrency field (`updated_at`/`version`/ETag)?
16. Confirm no frontend audit action is required (backend-automatic, per the current plan text) — or correct this if wrong.
17. List cache/staleness expectations (should the frontend poll, or only refetch on explicit mutation success?).

**PUBLIC SETTINGS**
18. Exact `GET /api/v1/settings/public` response shape.
19. Which keys are public.
20. Are secret/internal keys guaranteed excluded from this endpoint server-side?

**HIGH-IMPACT CONFIRMATION**
21. Is "requires confirmation before save" backend metadata on the setting itself, a separately published registry doc, or a frontend/product-maintained key list? Provide the authoritative source.
22. The full, authoritative setting-key registry (not just examples) — accepting-orders, offer window/cooldown/floor, checkout hold, unverified-purge window, daily download cap, free-shipping threshold, pickup address/hours, WhatsApp number, and any others that exist.

**REAL TESTING**
23. Supported way to prepare a disposable admin account with settings-editing access, once FVS-005 is available.

---

## 5. Task Detail (Safe Batch 1)

### FVS007-T01 — Frontend Setting Domain Model

**Status:** CAN IMPLEMENT NOW.
**Purpose:** A small, frontend-owned UI model — not a claim about the backend response — that isolates `SettingControl`/`SettingRow` from whatever the real API shape turns out to be.
**Files:** `src/components/admin/settings/settingTypes.ts` (+ test only if genuinely needed — this file is types only, likely no runtime behavior to test).
**Design:** A discriminated union (`type: "boolean" | "number" | "string"`), each variant carrying only the fields its own control genuinely needs — numeric `min`/`max`/`step` as optional, string with no invented constraints yet. Tagged `#ARCHITECTURE-SETTINGS-ADAPTER` with a comment explaining the backend response is intentionally isolated from the renderer; a future API adapter maps the confirmed backend schema onto this model, so a contract change touches one place, not every component.
**Do NOT:** claim this is `SettingRead`; add `any`; add fields not yet needed by T02/T03.
**Commit:** folded into T02's commit (type-only, naturally belongs together) per this plan's own "don't create meaningless micro-commits" instruction.

### FVS007-T02 — Typed `SettingControl`

**Status:** CAN IMPLEMENT NOW.
**Purpose:** The one renderer that picks boolean/number/string control by declared type.
**Files:** `src/components/admin/settings/SettingControl.tsx` (+test).
**Design:** Discriminated-union prop (`EditableSetting`) + `onChange`. Boolean → `<button type="button" role="switch" aria-checked>` (native button, fully keyboard-operable by default — no div-pretending-to-be-a-switch). Number → `<input type="number">` with `min`/`max`/`step` passed through when present. String → reuses `TextField` if its prop shape fits cleanly, else a focused controlled input matching its styling. Every control gets a programmatic label and `aria-describedby` when a description is supplied. No network calls, no server-state ownership, no draft persistence beyond its own props/callback.
**Tests:** TDD — the 20-item matrix in this session's own instructions (boolean switch semantics incl. keyboard activation, number min/max/step propagation, string exact-value preservation with no trim/normalize, label/description association, no network, no browser storage, no JSON editor).
**Commit message:** `feat: add typed settings field renderer`.

### FVS007-T03 — `SettingRow`

**Status:** CAN IMPLEMENT NOW.
**Purpose:** Label + description + `SettingControl` + save seam + status/error presentation, responsive per the confirmed stacked-card convention.
**Files:** `src/components/admin/settings/SettingRow.tsx` (+test).
**Design:** Accepts the `EditableSetting`, an `onSave(nextValue)` callback, and an already-normalized-safe `errorMessage?: string` (never parses an RFC error itself — that's the future adapter's job). Owns ephemeral current-value state locally (the open row's own draft, never persisted beyond the mounted component, no browser storage). UI states: idle/saving/saved/error, Save disabled while saving (no double-save). Desktop: row/table-like; `<768px`: stacked card (label → description → control → action/error), matching `bekaa3d-brand-ui`'s own already-documented FVS-007 convention.
**Tests:** TDD — the 12-item matrix (label/description/control rendered, save receives the current typed value, save disabled while saving, inline error shown near the control using only the passed-in safe string, responsive structure present at both breakpoints, no persistence, no network, no duplicate save while pending).
**Commit message:** `feat: add responsive settings row`.

### FVS007-T04 — `ConfirmDialog`

**Status:** CAN IMPLEMENT NOW.
**Purpose:** Generic, reusable confirmation modal — searched first; none exists in this repository, so this is genuinely new shared infrastructure, not a duplicate.
**Files:** `src/components/feedback/ConfirmDialog.tsx` (+test) — placed alongside `Alert`/`Toast` in `feedback/`, not `admin/settings/`, since nothing about it is settings-specific (it will be reused by any future high-impact-action confirmation across the app, not just settings).
**Design:** Props: `open`, `title`, `description`, `confirmLabel`, `cancelLabel`, `isConfirming`, `onConfirm`, `onCancel` — no setting key, no business-domain knowledge of any kind. Native `<dialog>` semantics (or an equivalent accessible pattern if native `<dialog>` proves inconsistent with this project's target browser in practice — decided during implementation, not pre-committed here) with an accessible title/description, keyboard operability, `Escape` closes when not mid-confirm, no click-through to the page behind it, Confirm disabled while `isConfirming`, focus managed sensibly and restored to the triggering element on close where the architecture supports it.
**Tests:** TDD — the 10-item matrix (closed is absent/non-interactive, open is visible, title/description associated, Cancel/Confirm call their callbacks, Confirm disabled while confirming, Escape behavior, keyboard navigation, no setting-key knowledge anywhere in the component).
**Commit message:** `feat: add reusable confirmation dialog`.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` stays untouched this batch (no route/page work yet).
- No new runtime dependency (no modal library, no schema-validation library for an unconfirmed backend shape).
- No `/admin/settings` route, no API/query/mutation code, no production high-impact-key list, no settings E2E until T05/T06 unblock.
- Never convert a `NEEDS BACKEND CONFIRMATION` item to CONFIRMED without an actual answer.
