# FVS-028 — Admin Payment Management — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: CRITICAL — payment operations/security.

**Goal:** Build the normalized admin-payment presentation model (reusing FVS-027's `PaymentStatus` rather than inventing a second, incompatible union), a `PaymentDetail` view with a reconciliation seam, a high-risk `ManualConfirmDialog` that reuses `DialogShell` directly, and an `AdminPaymentList` composed from the existing generic `AdminTable` — while treating all four admin payment endpoints as unconfirmed placeholders and deferring every real request.

**Architecture:** `AdminPaymentModel` holds only the concepts VS-022/FVS-028 actually confirm (status, amount, provider display label, provider reference, linked order, a server-authoritative `canManualConfirm` capability) — no backend field name, no provider secret, no raw payload. Manual confirmation can never be a single casual click: `ManualConfirmDialog` requires a non-empty reason and an explicit acknowledgment checkbox before Confirm is even enabled, and `canManualConfirm`/`manualConfirmBlockedReason` are server-authoritative inputs this dialog never second-guesses (`#SECURITY-MANUAL-PAYMENT-CONFIRMATION`). Reconciliation never optimistically changes status — only a future server response/refetch is authoritative.

**Spec:** `vertical-slice-plan.md`'s VS-022 entry (admin half) and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-028 entry (lines 737-753).

---

## 0. Repository / Contract Audit

Read: `vertical-slice-plan.md` (VS-022), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-028 entry), `FVS-005-IMPLEMENTATION-PLAN.md`, `FVS-017-IMPLEMENTATION-PLAN.md`, `FVS-019-IMPLEMENTATION-PLAN.md`, `FVS-027-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/components/admin/{AdminTable,StatusBadge,SearchableCombobox}.tsx`, `src/components/feedback/{DialogShell,ConfirmDialog}.tsx`, `src/components/catalog/PriceDisplay.tsx`, `src/lib/admin/`, `src/lib/payment/paymentStatusModel.ts`. Confirmed via directory listing that **`src/app/admin/` still does not exist at all** — the same pre-existing, cross-cutting FVS-005 gate every prior admin slice has recorded. Grepped the whole `src/` tree for `payment|reconcile|manual.confirm|provider.reference` outside `src/lib/payment/`/`src/components/payment/` (FVS-027's own files) — zero hits beyond one unrelated comment in `entitlementKeys.ts` mentioning "payment-driven grant" in passing.

**Confirmed by repository evidence:**
- VS-022's own "Endpoint / entrypoint" line is **entirely prose**: "admin payment list/detail/reconcile/confirm" — zero literal paths. All four of FVS-028's own listed endpoints (`GET /admin/payments`, `GET /admin/payments/{id}`, `POST /admin/payments/{id}/reconcile`, `POST /admin/payments/{id}/confirm`) are **frontend-derived placeholders**, exactly matching `FRONTEND-VERTICAL-SLICE-PLAN.md`'s own disclaimer on its FVS-028 entry.
- VS-022's Logic line confirms, at the concept level only: "transactionally mark paid, grant STL entitlements... append history/audit/outbox/notifications. Add `reconcile_payments` scheduled job and manual confirmation fallback." No field name, request body, or status code is given anywhere.
- FVS-028's own entry confirms the normalized concepts this slice needs: "status, provider reference, amount, linked order" (detail), and that manual confirm "requires the admin to acknowledge they've independently verified the payment... audited server-side."
- `AdminTable` (`src/components/admin/AdminTable.tsx`) is entirely columns/rows-generic — it carries zero payment-specific knowledge and needs no confirmed backend field name to compose with, only a frontend-normalized row type. This differs from FVS-017's own deferred `AdminTable` composition (which was blocked on a genuine list-vs-detail field *guarantee* ambiguity) — here the normalized concepts (status/amount/provider-ref/order-link) are clearly confirmed by FVS-028's own Components/Frontend-capability lines, so composing `AdminPaymentList` is safe this batch.
- `DialogShell` (with its FVS-025 `panelClassName` extension) and `StatusBadge`/`PriceDisplay` are all directly reusable with zero further modification.

**What is genuinely unconfirmed:** all four endpoint paths; the list response envelope/pagination/filter fields; the detail response's exact field names; the reconcile/confirm request bodies; the manual-confirm allowed-source-status matrix and already-paid response; CSRF/admin-MFA-freshness requirements; the exact audit data captured server-side.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Endpoints** | All four admin payment paths | **NEEDS BACKEND CONFIRMATION** — prose-only in VS-022 |
| **Model** | Status/amount/provider-ref/order-link concepts | **CONFIRMED concept** (FVS-028's own entry); **no field names** |
| **Model** | `PaymentStatus` reuse from FVS-027 | **CONFIRMED architecturally correct** — same lifecycle concept, no incompatible second union |
| **Reconcile** | Request body / success response / idempotency | **NEEDS BACKEND CONFIRMATION** |
| **Manual confirm** | Request body / reason field / allowed-source-status matrix / already-paid behavior | **NEEDS BACKEND CONFIRMATION** |
| **Admin shell** | `/admin/*` route + `AdminProtectedRoute` | **BLOCKED ON FVS-005** (pre-existing, cross-cutting, not reopened here) |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized admin payment model + status descriptor | **CAN IMPLEMENT NOW** |
| T02 | `PaymentDetail` presentation (incl. T03 reconciliation seam folded in) | **CAN IMPLEMENT NOW** |
| T03 | Reconciliation action presentation | **Folded into T02** (a seam within the detail view, not a separate file) |
| T04 | `ManualConfirmDialog` | **CAN IMPLEMENT NOW** |
| T05 | `AdminPaymentList` (`AdminTable` composition) | **CAN IMPLEMENT NOW** — normalized concepts are sufficiently confirmed |
| T06 | Real API/query/mutations | **BLOCKED ON BACKEND CONTRACT** |
| T07 | `/admin/payments` routes | **BLOCKED ON FVS-005 (no admin shell exists) + T06** |
| T08 | Integration/security/a11y review | Covered inline in T04's own test suite + independent review |
| T09 | E2E/docs | **BLOCKED** — no real route exists to exercise end-to-end |
| T10 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02 (incl. T03), T04, T05. T06/T07/T09/T10 are each blocked for a distinct, documented reason.

---

## 4. Backend Questions For Tomorrow

**Endpoints:** 1. Exact admin payment list endpoint. 2. Exact detail endpoint. 3. Exact reconcile endpoint. 4. Exact manual-confirm endpoint.

**List:** 5. Response envelope. 6. Pagination. 7. Filter fields. 8. Sort/order. 9. Payment id field. 10. Status field/literals. 11. Amount-cents field. 12. Currency. 13. Provider field. 14. Is the provider reference included in the list response, or only in detail? 15. Linked order id field. 16. Timestamps.

**Detail:** 17. Exact detail schema. 18. Exact provider-reference field. 19. Which provider metadata is safe for admins to see at all? 20. Reconciliation timestamps/status fields? 21. Linked-order representation. 22. Any callback/webhook metadata intentionally excluded from the admin-facing response?

**Reconcile:** 23. Request body. 24. Success status/body. 25. Does reconcile block until the provider answers, or enqueue work and return immediately? 26. Can the result remain pending after reconciling? 27. Provider-unavailable behavior. 28. Rate limit. 29. Idempotency. 30. CSRF/admin-MFA requirement.

**Manual confirm:** 31. Exact request body. 32. Reason field name. 33. Reason validation/max length (not invented here). 34. Is acknowledgment represented in the request body at all, or purely a UX gate? 35. Allowed source statuses. 36. Already-paid response. 37. Is manual confirm idempotent? 38. Concurrent reconcile/manual-confirm conflict behavior. 39. Required admin MFA freshness? 40. CSRF. 41. Exact audit data captured. 42. Is a second admin approval ever required? 43. Does manual confirm immediately mark the order paid? 44. Does it create entitlements synchronously?

**Security:** 45. Which provider identifiers are actually safe to render to an admin? 46. Any fields that must never reach the frontend at all? 47. Can an admin copy the provider reference (clipboard), or is even that restricted?

**Testing:** 48. Disposable admin fixture (blocked transitively on FVS-005). 49. Pending-payment fixture. 50. Paid-payment fixture. 51. Provider-callback-lost fixture. 52. Reconcile fixture. 53. Already-paid confirm test. 54. Manual-confirm acceptance procedure. 55. Audit-verification procedure for FVS-042.

---

## 5. Task Detail (Safe Batch)

### FVS028-T01 — Normalized Admin Payment Model + Status Descriptor

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/admin/adminPaymentModel.ts` (+test).
**Design:** `AdminPaymentModel {id, status: PaymentStatus, amountCents, currency, providerDisplayLabel, providerReferenceDisplayValue, linkedOrderDisplayId, canManualConfirm, manualConfirmBlockedReason?}` — reuses FVS-027's `PaymentStatus` directly (imported, never redeclared) rather than inventing a second, incompatible payment-status union; if the admin lifecycle ever needs additional states, they are added through this adapter once the backend confirms them, not guessed now. `canManualConfirm`/`manualConfirmBlockedReason` are the server-authoritative capability this slice's gating relies on — never a locally-computed allowed-status matrix. `describeAdminPaymentStatus(status): {label, tone}` — direct `StatusBadge` reuse, mirroring `describeScanStatus`/`describeAdminAccountStatus`'s own precedent exactly; no new badge component. No provider secret, webhook signature, raw provider payload, credential, or internal reconciliation detail exists on this type at all.
**Marker:** `#ARCHITECTURE-ADMIN-PAYMENT-ADAPTER`, `#SECURITY-PAYMENT-OPERATIONS-DATA` (payment references are sensitive operational data — never logged, never persisted in browser storage, never embedded in a query key or URL; a future query key uses the stable payment id only).
**Tests:** `describeAdminPaymentStatus` covers all five `PaymentStatus` values with distinct, textual labels (never color-only); type-only tests (RED-confirmed via `tsc`) proving `AdminPaymentModel` has no provider-secret/webhook-signature/raw-payload field.

### FVS028-T02 — `PaymentDetail` (incl. T03 Reconciliation Seam)

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/PaymentDetail.tsx` (+test).
**Design:** renders only confirmed conceptual fields — status via `StatusBadge`+descriptor, amount via `PriceDisplay` (reused, integer cents only, currency always from the normalized model, never hardcoded), provider display label and provider reference as plain text (never a link, never embedded in a URL/query key), linked order as plain display text (no link — no admin order-detail route exists). No raw provider-response JSON blob viewer of any kind. Reconciliation is a seam within this same view: `onReconcile: (paymentId) => void`, `isReconciling?: boolean` — the button shows clear "Reconciling…" progress text and is disabled while pending; this component never optimistically changes the displayed status — only a future server response/refetch is authoritative, so a reconcile action never locally flips `status` to `"paid"`.
**Marker:** `#SECURITY-PAYMENT-OPERATIONS-DATA` (carried over from T01).
**Tests:** renders status/amount/provider/order fields from the normalized model only; amount uses `PriceDisplay` with the model's own currency, never a hardcoded one; renders no raw JSON/payload viewer; `Reconcile` button calls `onReconcile` with the exact payment id; disabled with progress text while `isReconciling`; does **not** change the displayed status itself after the click (it stays whatever the model says until a new model is supplied); no network; no storage.

### FVS028-T04 — `ManualConfirmDialog`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/ManualConfirmDialog.tsx` (+test).
**Design:** composes `DialogShell` directly — zero new focus-trap code. `{open, onClose, paymentId, acknowledgmentLabel: string, canManualConfirm: boolean, manualConfirmBlockedReason?: string, isConfirming?: boolean, onConfirm: (paymentId: string, reason: string) => void}`. `acknowledgmentLabel` is **required, caller-supplied, no default** — per the task's own explicit instruction, since no approved operational-acknowledgment wording exists in this repository; inventing one (even a "concept" placeholder) would encode unapproved legal/operational copy. A reason `<textarea>` (local state only — never persisted, logged, or placed in a URL) and the acknowledgment checkbox (default unchecked) must both be filled/checked before Confirm enables; `canManualConfirm === false` keeps Confirm disabled regardless of reason/acknowledgment input, and `manualConfirmBlockedReason` (e.g. "This payment has already been confirmed.") renders visibly when supplied — the server remains the final authority regardless of what this dialog computes locally. `onConfirm` receives the exact `paymentId` plus the typed `reason` text — never anything else.
**Marker:** `#SECURITY-MANUAL-PAYMENT-CONFIRMATION`.
**Tests (14, matching the task's own minimum list):** dialog focus/Escape/backdrop behavior is the real, unmodified `DialogShell` mechanics (role=dialog, aria-modal, Escape closes); Confirm disabled with an empty reason; Confirm disabled without the acknowledgment checkbox; Confirm disabled with only the reason filled; Confirm disabled with only acknowledgment checked; Confirm enabled once both are satisfied; `isConfirming` disables Confirm regardless of reason/acknowledgment; `canManualConfirm: false` disables Confirm regardless of reason/acknowledgment; an already-paid-style `manualConfirmBlockedReason` renders visibly and still blocks Confirm; `onConfirm` is called with the exact `(paymentId, reason)` pair; no network call anywhere; no `localStorage`/`sessionStorage` write of the reason or anything else; no raw provider payload rendered anywhere in this dialog (structural — no such prop exists on its type); Cancel calls `onClose` and never `onConfirm`.

### FVS028-T05 — `AdminPaymentList`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/admin/AdminPaymentList.tsx` (+test).
**Design:** composes the existing, fully generic `AdminTable` directly (no second table implementation) with columns derived purely from `AdminPaymentModel`: Status (`StatusBadge`+descriptor), Amount (`PriceDisplay`), Provider, Provider Reference, Linked Order — each a plain, non-clickable value, since no admin order/payment-detail route exists yet to link to. A `rowActions` seam renders a "View" trigger that calls an optional `onSelectPayment(id)` callback rather than a real link — presentational navigation intent only, never a route the caller doesn't actually have yet.
**Marker:** none new — reuses `#SHARED-ADMIN-TABLE` (FVS-009) as-is.
**Tests:** renders every row's normalized fields via the correct shared components (`StatusBadge`, `PriceDisplay`); loading/empty states delegate to `AdminTable`'s own existing behavior (not re-tested here beyond composition); `View` trigger calls `onSelectPayment` with the exact payment id, never a navigation; renders no clickable link anywhere in the table; no network; no storage.

---

## 6. Deferred / Blocked Tasks (Rationale)

**T06 — Real API/query/mutations:** Blocked — no confirmed request/response body for any of the four admin payment operations.

**T07 — `/admin/payments` routes:** Blocked on two independent gates: (1) the admin API contract (T06), and (2) the pre-existing, cross-cutting FVS-005 gate — no admin route shell/`AdminProtectedRoute` exists anywhere in this repository yet, a blocker every prior admin slice (FVS-007, FVS-010, FVS-024) has already recorded independently. Not reopened or re-litigated here.

**T09 — E2E/docs:** Blocked — no real route exists yet to exercise end-to-end.

**T10 — Real backend acceptance:** Blocked on backend availability.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; one `test:e2e` regression run suffices (no route/page work this batch).
- No new runtime dependency.
- No invented admin endpoint path/body, no provider secret/webhook signature/raw payload ever rendered, no optimistic paid state, no locally-computed manual-confirm allowed-status matrix, no production `/admin/payments` route, no real reconcile/confirm request, until the respective gates in §6 unblock.
- Payment references are sensitive operational data: never logged, never persisted in browser storage, never embedded in a query key or URL (`#SECURITY-PAYMENT-OPERATIONS-DATA`).
