# FVS-027 — Payment Result & Verification UX — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: CRITICAL — must never display "Payment Successful" on the strength of a redirect alone.

**Goal:** Build the normalized payment-status model (with local polling outcomes kept structurally separate from backend status), a contract-neutral return-identifier boundary, a dumb polling-schedule controller, and the full set of presentational result states — while proving, with the single most important test in this slice, that a manipulated success-looking return query string can never produce a "Payment Successful" render while the backend-verified status remains `pending`.

**Architecture:** Provider return means only "the browser returned from a payment attempt" — never success/failure/expiry. `extractReturnIdentifier` is a generic, dumb helper that reads exactly one configured query key and never inspects any status-like field (`#SECURITY-PAYMENT-RETURN-UNTRUSTED`). `PaymentVerificationState` is the one type every result component consumes, and it has FOUR variants — `verifying`, `status` (wrapping a backend-verified `PaymentStatus`), `timeout`, `network-error` — so a local polling outcome can never masquerade as a backend payment status (`#ARCHITECTURE-PAYMENT-STATUS-ADAPTER`). `usePaymentStatusPoller` only decides *whether* and *when* to poll (mirroring FVS-018's `useScanStatusPolling` precedent exactly) — it never fetches, never interprets a response, and never turns a timeout into a failure.

**Spec:** `vertical-slice-plan.md`'s VS-022 entry and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-027 entry (lines 714-730).

---

## 0. Repository / Contract Audit

Read: `vertical-slice-plan.md` (VS-021, VS-022, VS-023's own endpoint line for `GET /me/orders/{id}`), `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-025/026/027 entries), `FVS-025/026/020-IMPLEMENTATION-PLAN.md`, `docs/frontend-setup.md`. Inspected `src/lib/checkout/`, `src/lib/cart/`, `src/lib/entitlements/`, `src/lib/admin/useScanStatusPolling.ts` (the governing polling precedent), `src/components/feedback/`, `src/lib/api/apiClient.ts`. Grepped the whole `src/` tree for `payment|paid|pending|processing|failed|expired|provider|Whish|reconcile|poll|backoff` — zero existing payment-related code anywhere (hits are only FVS-023/025's own negative-space assertions and FVS-021's cap/revoked-notice copy, unrelated).

**Confirmed by repository evidence:**
- VS-022's own "Endpoint / entrypoint" line is **entirely prose**: "Whish-shaped payment webhook route backed by mock in dev; admin payment list/detail/reconcile/confirm" — zero literal paths anywhere. No dedicated payment/order-status read endpoint is confirmed.
- `GET /api/v1/me/orders/{id}` **is** literal/confirmed — but it belongs to VS-023/FVS-029, which has **not landed yet** in this build's sequence (FM-C's own strict order is FVS-025→026→**027**→029→030→031→032 — FVS-029 comes *after* this slice). So even though this path exists as a fact, two separate things remain unresolved: (a) whether it is even the *intended* read for payment-result polling (vs. a dedicated, still-unnamed payment-status endpoint), and (b) it is not yet available to this slice's own build sequence regardless. Both are recorded as open questions, not resolved by assumption.
- `FRONTEND-VERTICAL-SLICE-PLAN.md`'s own FVS-027 entry states explicitly: query parameters on the return URL "are used only to identify *which* order to check, never to decide success/failure" — this is the confirmed product rule the whole slice is built around.
- `useScanStatusPolling` (FVS-018) is the governing architectural precedent for `PaymentStatusPoller`: a **dumb** hook that only decides *whether* to keep polling, delegating *what polling does* entirely to the caller. `usePaymentStatusPoller` follows this exactly, extended only with the max-duration/timeout concept FVS-018's own asset-scan polling didn't need.

**What is genuinely unconfirmed:** the exact payment-result return route and query parameter name; whether it carries an order id or a payment id; whether additional provider parameters are present and whether they should be stripped from the URL/history after parsing; the authoritative status-read endpoint (dedicated vs. `/me/orders/{id}`); its exact response schema/status field/status literals; recommended polling interval/backoff/max-duration/timeout values; whether STL entitlements are guaranteed available by the time `paid` is first observed.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Return** | Exact return route/query field | **NEEDS BACKEND CONFIRMATION** |
| **Return** | Order id vs. payment id | **NEEDS BACKEND CONFIRMATION** |
| **Return** | Query params are never authoritative for status | **CONFIRMED** (FVS-027's own entry, this plan's core invariant) |
| **Status read** | Dedicated endpoint vs. `GET /me/orders/{id}` | **UNRESOLVED — not guessed; `/me/orders/{id}` also not yet available (FVS-029 unbuilt)** |
| **Status read** | Response schema/status field/literals | **NEEDS BACKEND CONFIRMATION** |
| **Polling** | Interval/backoff/max-duration values | **NEEDS BACKEND/PRODUCT CONFIRMATION — never hardcoded as a hidden default** |
| **Terminal states** | `paid`/`failed`/`expired` concept; `pending`/`processing` concept | **CONFIRMED concept** (VS-022 Logic line, FVS-027's own UX-states line); **no literal backend enum value** |
| **Entitlement timing** | When STL entitlements are guaranteed available after `paid` | **NEEDS BACKEND CONFIRMATION** |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Normalized payment-status model + terminal helper + verification-state union | **CAN IMPLEMENT NOW** |
| T02 | Contract-neutral return-identifier boundary | **CAN IMPLEMENT NOW** |
| T03 | `usePaymentStatusPoller` (dumb polling-schedule controller) | **CAN IMPLEMENT NOW** |
| T04 | `PaymentPendingState` | **CAN IMPLEMENT NOW** |
| T05 | `PaymentSuccessState` | **CAN IMPLEMENT NOW** |
| T06 | `PaymentFailedState` + `PaymentExpiredState` + `PaymentVerificationTimeoutState` + `PaymentVerificationErrorState` | **CAN IMPLEMENT NOW** |
| T07 | `PaymentResultView` composition (incl. the single most important test) | **CAN IMPLEMENT NOW** |
| T08 | Real status query/API integration | **BLOCKED ON BACKEND CONTRACT** |
| T09 | Production return route + integration/E2E/docs | **BLOCKED** until T08 unblocks |
| T10 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01–T07. T08–T10 are each blocked for a distinct, documented reason.

---

## 4. Backend Questions For Tomorrow

**Return:** 1. Exact payment return route. 2. Exact identifier parameter. 3. Order id or payment id? 4. Are additional provider query parameters supplied? 5. Should the frontend ignore/strip them after identification? 6. Should return parameters be removed from browser history/address bar?

**Status:** 7. Dedicated payment-status endpoint, or `/me/orders/{id}`? 8. Exact response schema. 9. Exact status field name. 10. Exact status literals. 11. `pending` representation. 12. `processing` representation. 13. `paid` representation. 14. `failed` representation. 15. `expired`/interrupted representation. 16. Any `cancelled` state distinct from `expired`? 17. Is payment verification eventually consistent with order status (could they briefly disagree)?

**Polling:** 18. Recommended initial polling interval. 19. Backoff policy. 20. Recommended maximum duration. 21. Request timeout. 22. Is `Retry-After` ever returned? 23. Rate-limit behavior. 24. Recommended behavior after a local timeout.

**Success:** 25. When is an order safe to display as paid? 26. When are STL entitlements guaranteed available? 27. Should the frontend refetch entitlement/cart/order data after `paid`? 28. Destination after success (pending FVS-029/020 routes).

**Failure:** 29. Failed-payment retry flow. 30. Does retry reuse the same order? 31. Does the user return to checkout or create another payment attempt? 32. Expired-payment retry semantics.

**Security:** 33. Independently re-confirm return query status is never authoritative (already the product's own stated rule). 34. Does the return identifier need additional validation/signature? 35. Can one authenticated user query another user's order/payment id? 36. Expected unauthorized/not-found behavior.

**Testing:** 37. Pending fixture. 38. Processing fixture. 39. Paid fixture. 40. Failed fixture. 41. Expired fixture. 42. Reconciliation-delay fixture. 43. Manipulated-success-query acceptance procedure. 44. Polling-timeout fixture.

---

## 5. Task Detail (Safe Batch)

### FVS027-T01 — Normalized Payment Status Model

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/payment/paymentStatusModel.ts` (+test).
**Design:** `PaymentStatus = "pending" | "processing" | "paid" | "failed" | "expired"` — frontend-normalized concepts, never a claimed backend enum literal. `isTerminalPaymentStatus(status)` → `true` for `paid`/`failed`/`expired`, `false` for `pending`/`processing`. `PaymentVerificationState = {kind:"verifying"} | {kind:"status"; status: PaymentStatus} | {kind:"timeout"} | {kind:"network-error"}` — this is the critical structural separation: a local poller outcome (`timeout`/`network-error`) can **never** be represented as a `PaymentStatus` value, so nothing downstream can accidentally treat "we stopped checking" as "the payment failed."
**Marker:** `#ARCHITECTURE-PAYMENT-STATUS-ADAPTER`.
**Tests:** `isTerminalPaymentStatus` true for all three terminal statuses, false for both non-terminal ones; type-only tests (RED-confirmed via `tsc`) proving `PaymentVerificationState`'s `timeout`/`network-error` variants carry no `status` field at all — structurally impossible to confuse with a backend status.

### FVS027-T02 — Return Identifier Boundary

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/payment/paymentReturnIdentifier.ts` (+test).
**Design:** `extractReturnIdentifier(params: URLSearchParams, identifierKey: string): string | null` — reads exactly the one configured key and returns it (or `null`). Never reads, inspects, or branches on any other parameter. Deliberately **not** named `parsePaymentSuccessFromUrl`/`providerStatusFromQuery` or anything implying it extracts meaning beyond "which record to check."
**Marker:** `#SECURITY-PAYMENT-RETURN-UNTRUSTED`.
**Tests:** extracts the configured key's value; returns `null` when the key is absent; **a dedicated test passes a query string containing `status=success&paid=true&payment_status=paid` alongside the identifier key, and asserts the function's return value is unaffected by any of them** — proving this helper is identification-only, never a status-reader.

### FVS027-T03 — `usePaymentStatusPoller`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/payment/usePaymentStatusPoller.ts` (+test).
**Design:** mirrors `useScanStatusPolling`'s own "dumb hook, caller does the actual work" architecture exactly — extended with the max-duration concept this slice's own UX-states line requires. `usePaymentStatusPoller({status: PaymentStatus | null, getDelayMs: (attempt: number) => number, maxDurationMs: number, onPoll: () => void})` → `{isTimedOut: boolean, retry: () => void}`. `status === null` (nothing known yet) and `pending`/`processing` are all "keep polling"; any terminal status or `isTimedOut` stops scheduling further polls. `getDelayMs`/`maxDurationMs` are **required** — no built-in production interval is hidden inside this hook, mirroring `useScanStatusPolling`'s own `intervalMs`-required precedent exactly. `retry()` resets the elapsed-time clock and attempt counter, resuming polling after a local timeout — it does **not** by itself re-interpret any status; it only resumes the schedule. **This hook does not itself fetch or interpret a response** — a thrown network error during whatever `onPoll` triggers is the caller's own concern (surfaced as `{kind:"network-error"}` in `PaymentVerificationState` one layer up, T07) — exactly matching the precedent's own "what polling does is the caller's concern" principle, and avoiding a second, duplicated single-flight/dedup mechanism this hook has no way to observe anyway.
**Marker:** none new — same architectural pattern as `#ARCHITECTURE-SCAN-POLLING`, no second marker needed for a repeated pattern.
**Tests (fake timers, mirroring `useScanStatusPolling.test.ts`'s own conventions):** polls while `status` is `null`/`pending`/`processing` at the exact delay `getDelayMs(attempt)` returns; uses a custom backoff policy (delay grows per attempt) correctly; stops scheduling further polls the instant `status` becomes `paid`/`failed`/`expired`; sets `isTimedOut` once `maxDurationMs` elapses while still non-terminal, without ever calling `onPoll` again afterward; cleans up its timer on unmount (no `onPoll` call after unmount); never schedules a second outstanding timer while one is already pending (re-rendering with the same `status` does not multiply scheduled polls); `retry()` clears `isTimedOut` and resumes polling.

### FVS027-T04 — `PaymentPendingState`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/payment/PaymentPendingState.tsx` (+test).
**Design:** honest copy only — "Confirming your payment…" with a spinner (reusing the same `motion-reduce`-safe pattern established elsewhere). **No fake percentage/progress bar** — a spinner never implies a measurable fraction of completion, and the copy never implies the provider has already approved anything.
**Tests:** renders the honest copy; renders no numeric/percentage progress indicator of any kind; spinner respects `motion-reduce`.

### FVS027-T05 — `PaymentSuccessState`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/payment/PaymentSuccessState.tsx` (+test).
**Design:** `{orderDisplayId?: string, actionSlot?: ReactNode}` — **accepts no provider/query-derived props of any kind**; it has no `providerSaidSuccess`/`queryStatus` prop at all, structurally — the only way to render this component is for a caller to have already decided, from `PaymentVerificationState.kind === "status" && status === "paid"`, that it's appropriate. `actionSlot` (e.g. a future order-history/library link) is optional and renders nothing when omitted — no dead link to FVS-029's or FVS-020's still-unmounted routes.
**Tests:** renders success copy; renders the optional order id when supplied; renders no action link of any kind when `actionSlot` is omitted; renders the supplied `actionSlot` when given; **the component's own prop type has no field that could carry raw provider/query data** (a structural, not just behavioral, guarantee — verified by the type-only test in T07's model, not re-tested here).

### FVS027-T06 — Failed / Expired / Timeout / Network-Error States

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/payment/PaymentFailedState.tsx`, `PaymentExpiredState.tsx`, `PaymentVerificationTimeoutState.tsx`, `PaymentVerificationErrorState.tsx` (each +test).
**Design:** `PaymentFailedState({actionSlot?: ReactNode})` — safe retry guidance copy, no invented working Checkout/Cart link (seam only). `PaymentExpiredState({actionSlot?: ReactNode})` — copy kept distinct from Failed's ("your payment session expired" vs. "your payment could not be completed"), never claiming a provider-specific reason like "card declined." `PaymentVerificationTimeoutState({onRetry: () => void})` — "We're still confirming your payment" copy, explicitly **not** failure language, with a single retry-polling action; this is a local-poller-stopped state, never dressed up as a payment outcome. `PaymentVerificationErrorState({onRetry: () => void})` — "Verification is temporarily unavailable" copy; never renders a raw network/server exception message.
**Tests (per component):** renders its own distinct copy; `PaymentFailedState`/`PaymentExpiredState` render no CTA at all when `actionSlot` is omitted (no dead link); `PaymentVerificationTimeoutState`/`PaymentVerificationErrorState` call `onRetry` only on an explicit click, never automatically; `PaymentVerificationTimeoutState`'s copy is asserted to differ from `PaymentFailedState`'s (both rendered, text compared) — proving the timeout fallback can never be mistaken for a failure message.

### FVS027-T07 — `PaymentResultView` (incl. the single most important test)

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/payment/PaymentResultView.tsx` (+test).
**Design:** `{verificationState: PaymentVerificationState, orderDisplayId?: string, successActionSlot?: ReactNode, failedActionSlot?: ReactNode, expiredActionSlot?: ReactNode, onRetryTimeout?: () => void, onRetryError?: () => void}` — a pure `switch` over `verificationState.kind`/`verificationState.status`, rendering exactly one of T04-T06's components. **Accepts no raw provider/query prop of any kind** — there is no `providerQueryParams`/`rawStatus` prop anywhere in its type, so there is nothing for a future caller to even mistakenly wire a query-string value into. Owns the **one** `aria-live="polite"` region wrapping whichever child state renders — none of T04-T06's own components carries its own live region, avoiding nested/duplicate announcements.
**Marker:** `#SECURITY-BACKEND-VERIFIED-PAYMENT`.
**Tests:** renders `PaymentPendingState` for `{kind:"verifying"}` and for `{kind:"status", status:"pending"|"processing"}`; renders `PaymentSuccessState` only for `{kind:"status", status:"paid"}`; renders `PaymentFailedState`/`PaymentExpiredState`/`PaymentVerificationTimeoutState`/`PaymentVerificationErrorState` for their respective states; exactly one `aria-live="polite"` region exists in the rendered output regardless of which state is active (no nested duplicates). **The single most important test in this slice:** renders with a `URLSearchParams` built from `"?order_id=123&status=success&paid=true&payment_status=paid"` parsed only for its `order_id` via `extractReturnIdentifier` (proving the identifier extraction is exercised, not just asserted by name), while `verificationState` is explicitly `{kind:"status", status:"pending"}` (the stand-in for "backend says still pending") — and asserts the rendered output is `PaymentPendingState`'s own copy, with `screen.queryByText(/payment successful/i)` returning `null`. This exercises real result-state composition end-to-end, not merely a helper's name.

---

## 6. Deferred / Blocked Tasks (Rationale)

**T08 — Real status query/API integration:** Blocked — no confirmed status-read endpoint (dedicated or otherwise), no confirmed response schema. Per the task's own explicit instruction, **no dedicated payment-status query-key family is created yet** — whether this data is a payment resource or an order resource is undecided, and FVS-029 may establish the canonical order query-key architecture this slice would otherwise have to guess at or duplicate. Recorded as an open architectural gate, not solved here.

**T09 — Production return route + integration/E2E/docs:** Blocked until T08 unblocks — the exact return path/identifier parameter is unconfirmed, and a route reading `?status=success` as truth is explicitly forbidden regardless.

**T10 — Real backend acceptance:** Blocked on backend availability.

**Independent-review follow-up (FVS-027 Important finding, resolved):** `usePaymentStatusPoller`'s `maxDurationMs` was a soft, not hard, ceiling under backoff — `elapsed` was only checked *before* scheduling the next wait, so a large backoff delay near the deadline could let one more poll fire after the configured budget had already elapsed (bounded by one extra interval, not unbounded). Classified **FRONTEND-SAFE TO FIX NOW** — pure polling-schedule logic, no backend dependency. Fixed via TDD: the scheduled delay is now capped to the remaining budget, and the timer callback re-checks elapsed time before calling `onPoll` — so no poll can ever fire after `maxDurationMs` has elapsed, confirmed by a new dedicated test using a backoff delay (10s) that alone exceeds the entire budget (5s). A second, non-defect observation from the same review — `PaymentResultView`'s `timeout`/`network-error` retry callbacks silently no-op when a caller omits them, rather than being required props — was left as-is, explicitly characterized by the review itself as low-severity and defensible for a presentational-only batch with no real integration yet.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; one `test:e2e` regression run suffices (no route/page work this batch).
- No new runtime dependency.
- No real status query/mutation, no guessed return route/identifier param, no guessed status endpoint, no production `/checkout/payment-result` route, no payment-status query-key family, no dead success/order-history links, until the respective gates in §6 unblock.
- Query-string-derived values are used only to identify a record, never to decide a rendered state — enforced structurally (no component accepts a raw query/provider prop), not just by convention.
