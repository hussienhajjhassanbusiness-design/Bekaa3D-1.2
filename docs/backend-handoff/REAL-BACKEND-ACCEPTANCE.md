# Real Backend Acceptance

## Phase 6B-1: Contact (VS-033), 2026-11-11

| Item | Value |
|---|---|
| Frontend commit tested | `e0fe414` (public `/contact`, `/admin/contact-messages`, `/admin/contact-messages/[id]`, mocked E2E). Committed before the run |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json` equal to `docs/backend-handoff/openapi.json` except a `§` text-encoding artifact in two wishlist descriptions; then `engagement/api/contact_messages.py`, `contact_message_schemas.py`, `domain/contact_message.py`, `domain/enums.py`, `api/captcha.py`, `api/text.py` |
| Runtime | Docker Compose backend on :8000 (`CAPTCHA_PROVIDER=fake`, which accepts only Cloudflare's test token). `npm run dev` on :3000 for the run only |
| Method | real Edge through Playwright, real frontend and backend, **no route mocking** except one in-flight rewrite of `captcha_token` to get the real `400`; admin through the frontend proxy (password + TOTP). Scripts in the session scratchpad, never committed |
| Identities | a guest sender `accept-contact-<ts>@example.com`; admin from `%USERPROFILE%\.bekaa3d\dev-admin.json` (never printed); phase 5H's `accept-admin-e-<ts>` customer, re-entered through the real password-reset flow |
| Data | one disposable message moved `new` → `read` → `archived`, plus 4 disposable rate-limit probes; all 5 `accept-contact-*` rows deleted after the run (audit rows kept) |

**Overall: PASS, 21/21** (one script assertion corrected: it counted the shell's "Log out" as a status action; a re-check showed it is the only button left on an archived message).

### Current contract (as implemented)

- **Submit:** `POST /api/v1/contact-messages`, public (no session, no CSRF). JSON, `extra="forbid"`: `name` 1-100, `email` (an address ≤254), `phone?` ≤32 phone-shaped (`+`, digits, space `( ) . -`, ≥6 digits), `subject?` ≤200, `message` 1-5000 (line breaks allowed), `captcha_token` (Turnstile, ≤2048). Values are trimmed and blank optionals stored as null. `201 {id, created_at}`.
- **Order of checks:** 60 attempts/h, body validation (`422 VALIDATION_ERROR`, spends no quota), captcha (`400 CAPTCHA_INVALID`; `503 SERVICE_UNAVAILABLE` + `Retry-After: 30` when it can't be verified), then 5/h per IP and 5/h per email (`429 RATE_LIMITED` + `Retry-After`). A refused captcha spends neither quota. Domain-rule failures (for example a badly shaped phone) come back as a model-level `422` with `loc ["body"]`.
- **Admin:** `GET /api/v1/admin/contact-messages?cursor&limit(1-100, 20)&status&created_after&created_before&email` → `{items, next_cursor}`, new first then oldest first; dates must be aware (after inclusive, before exclusive); `email` exact and case-insensitive. `GET /{id}` (audited `contact_message.viewed`; reading does **not** mark it read). `PATCH /{id} {status}` with CSRF: forward only, skips allowed, backwards `409 INVALID_STATE_TRANSITION`; audited `contact_message.status_changed`. Statuses `new`, `read`, `replied`, `archived`. No notes, no assignment, no reply from the system (the admin replies by email). A customer's order problem report is a contact message with `user_id` and `order_id`. Non-admin `404`; no session or MFA incomplete `401`.

### Frontend behaviour

- `/contact` (header and footer link "Contact"): the exact fields, client checks mirroring the server's (UX only), the one `CaptchaWidget`; the token is reset after every attempt so a retry carries a fresh one. Success shows "Thanks — your message has been sent. We'll reply by email." (never the id) and offers "Send another message". Failures use frontend copy only: captcha (invalid / unavailable / missing), "Please check: Email." for a field `422`, a generic line for a model-level `422`, rate limit with the `Retry-After` minutes, network, timeout, generic.
- `/admin/contact-messages` (nav "Contact messages"): status, received from/to (local days) and exact sender email filters, cursor pagination; problem reports carry an "Order problem" badge. The email filter is component state only, never in the page URL.
- `/admin/contact-messages/[id]`: sender, email (mailto only for a plain address), phone, received, last updated, the message as plain pre-wrapped text, order and customer links for a problem report. One button per forward status ("Mark read", "Mark replied", "Archive"), each behind a confirmation; `409` shows "already moved on" and refetches. A malformed id renders the 404 page without a request.

### Results

| Scenario | Result | Evidence |
|---|---|---|
| Client validation | **PASS** | empty form + phone "call me" → inline errors, no request |
| `400 CAPTCHA_INVALID` (real) | **PASS** | token rewritten in flight → real `400`; UI showed the frontend captcha copy; backend `detail` not rendered |
| Refused captcha stores nothing | **PASS** | 0 rows for the sender |
| Retry with a fresh token | **PASS** | the next attempt carried a newly issued Turnstile test token → `201`; success copy; no id shown |
| Exact payload | **PASS** | keys `captcha_token, email, message, name, phone, subject` |
| Persistence | **PASS** | one row, values as sent, status `new`, no `user_id` |
| Server validation | **PASS** | bad phone `422` (`loc ["body"]`), bad email `422` `body.email`, missing token `422` `body.captcha_token`, extra field `422` |
| Admin MFA required | **PASS** | password-only login → queue `401 AUTH_REQUIRED` |
| Queue shows the submission | **PASS** | upper-cased email filter → 1 row; the address only in the API query, never the page URL |
| Status filter | **PASS** | `archived` → empty; `new` → the row |
| Detail | **PASS** | all fields; `<b>` in the message rendered as text |
| Read audited, not marked read | **PASS** | one `contact_message.viewed` row; status still `new` |
| Mark read (UI) | **PASS** | `PATCH {"status":"read"}` with `X-CSRF-Token`; database `read` |
| Persistence after reload | **PASS** | badge Read; actions Mark replied, Archive |
| Backwards refused | **PASS** | `read` → `new`: `409 INVALID_STATE_TRANSITION` |
| CSRF required | **PASS** | stale token → `403`; unchanged |
| Skip forward (UI) | **PASS** | `read` → `archived`; no action offered after |
| Status changes audited | **PASS** | 2 `contact_message.status_changed` rows |
| Customer gets 404 | **PASS** | list, detail, PATCH `404`; UI 404 page |
| `429` rate limit (real) | **PASS** | after 4 more disposable sends → `429 RATE_LIMITED`, `Retry-After` ~3600; UI "Too many submissions. Please try again in about 60 minutes." |
| No page errors | **PASS** | none |

### Not tested against the real backend

- `503` captcha unavailable (the fake verifier is always available): unit-tested.

---

## Phase 6A: Admin Operations Completion, 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `57ccc0c` (optional customer cancel reason), `1bf7b78` (manual release, late capture, chargeback create), `2a830a6` (`/admin/cash-blocks`), `6b43e13` (customer / date filters), `0fce5a9` (mocked E2E), `fe4a721` (backend handoff note). All committed before the run |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json` identical to `docs/backend-handoff/openapi.json`; then `ordering/api/admin_cash_blocks.py`, `admin_release.py`, `ordering/domain/payment_recovery.py`, `cancellation.py` (cash block rule), `payments/api/admin_payments.py` (record-capture), `admin_chargebacks.py`, `payments/domain/manual.py`, `refunds.py`, `payments/application/services/refunds.py`, `ordering/api/cancel.py`, and every admin list's query parameters |
| Runtime | Docker Compose backend on :8000 (`PAYMENT_PROVIDER=mock`). `npm run dev` on :3000 only for the run, stopped after it. `scripts/mock_pay.py` copied to the API container's `/tmp` and **removed after** (verified) |
| Method | real Edge through Playwright, real frontend and backend, **no route mocking**; admin through the frontend proxy (password + TOTP) |
| Identities | admin from `%USERPROFILE%\.bekaa3d\dev-admin.json` (never printed); phase 5H's `accept-admin-e-<ts>` customer, re-entered through the real password-reset flow; its own address phone read from the database only to drive the phone search (never printed or logged). No new registration |
| Data left behind | E: `B3D-9YNGBN8W` cash/delivery, line **cancelled** (`refused`) by the admin → its cash block created and then **cleared**; `B3D-RDERK66R` online (mock, paid), **cancelled by the customer** with a reason, cancellation refund pending. `B3D-WQMG40BW` (phase 5I): one **chargeback** $31.00 recorded (it voided and absorbed the pending reissue). One audit row from a cash-block phone search. No setting or product changed |

**Overall: PASS, 18/18** (one script assertion corrected: Postgres renders `text || boolean` as `true`, not `t`; the block row was confirmed directly).

### Audit of the remaining admin operations

| Operation | Class | Backend (2dfb27b) | Frontend now |
|---|---|---|---|
| Chargeback create | **A** built, was missing | `POST /admin/orders/{id}/chargebacks` + `Idempotency-Key` | **Built** (Record a chargeback on the admin order) |
| Chargeback update / resolve / acknowledge | **C** not built | no such routes; `GET /admin/orders/{id}/chargebacks`, `GET /admin/chargebacks/{id}` only | read-only rows, as before |
| Late capture | **A** | `POST /admin/payments/{id}/record-capture` + `Idempotency-Key` | **Built** (Record late capture on the payment) |
| Manual release of unpaid orders | **A** | `POST /admin/orders/{id}/release` | **Built** (Release order on the payment, on `release_order`) |
| Cash blocks | **A** (list, search, clear); creation **B** automatic only | `GET /admin/cash-blocks`, `POST …/search`, `POST …/{id}/clear` | **Built** `/admin/cash-blocks` |
| Admin filters | **A** | orders `customer_id`, `placed_after/before`; payments `order_id`, `initiated_after/before`; refunds `customer_id`, `order_id`, `created_from/to`; cash blocks `customer_id`, `active`; STL queue `product_id`, `customer_id` | **Built** for orders, payments, refunds, cash blocks (STL queue filters not added) |
| Customer cancel reason | **A** | `CustomerOrderCancelRequest {reason? ≤500}` | **Built** (optional field in the cancel dialog) |
| Admin order cancel reason | already built | `AdminOrderCancelRequest {reason 1-500, cancel_reason?}` (required) | unchanged |
| Void of a pending reissue after its line is `refunded` | **D** decision (intended rule with an operator consequence) | `refund_step`: "a void never reopens a closed line" | unchanged; backend handoff `REFUND-VOID-AFTER-REISSUE.md` |

### Current contract (as implemented)

- **Cash blocks:** a block is created **by the server** when every live line of a cash order ends `cancelled` with reason `refused` or `no_show` (`ordering/domain/cancellation.py cash_block_reason`); there is no manual create and no expiry. Read: `{id, customer_id, order_id, order_number, reason, created_at, active, cleared_at, cleared_by}` (never the phone or its hash). `GET /admin/cash-blocks?customer_id&active&limit(1-100, 25)&cursor` newest first; `POST /admin/cash-blocks/search {phone ≤32, active?, limit?, cursor?}` (CSRF; the phone only in the body, normalised and hashed server-side; `422` for a non-Lebanese number; one audit row per search without the phone); `POST /admin/cash-blocks/{id}/clear` (CSRF; clearing a cleared block returns it unchanged). 60/h. A block makes cash checkout `422 CASH_NOT_AVAILABLE`. It is not a deactivation, a payment failure or an order cancellation.
- **Manual release:** `POST /admin/orders/{id}/release {reason 10-1000, events_reviewed}` → `{order_id, status: "cancelled", cancelled_at, attempts_expired, events_dismissed}`; the payment detail lists `release_order` only for an unpaid online order after `hold_expires_at + 24 h`. `409 INVALID_STATE_TRANSITION` reasons `cash_order`, `order_cancelled`, `order_not_payable`, `grace_not_elapsed` (+ `release_available_at`), `unprocessed_events` (+ `count`). The provider is never called. 30/h.
- **Late capture:** `POST /admin/payments/{id}/record-capture` + `Idempotency-Key` `{captured_amount_cents > 0, captured_currency ^[A-Z]{3}$, dashboard_reference 1-255, reason 10-1000}` → `201 {outcome, payment, refund_id}` (a late-capture refund obligation). Refused for cash (`cash_payment`), a provider with a status API (`409 MANUAL_CONFIRMATION_NOT_ALLOWED`, i.e. always with the mock), `already_paid`, `already_late_captured`, `use_confirm` (matching amount).
- **Chargeback create:** `POST /admin/orders/{id}/chargebacks` + `Idempotency-Key` `{payment_id, provider_dispute_reference 1-200, charged_cents > 0, items [{order_item_id, amount_cents}] (optional, unique), reason 1-1000, received_at (aware)}` → `201 ChargebackDetail` (`applied_cents`, `excess_cents`). It voids and absorbs the payment's open refunds; items must total `chargeable_cents` (the charge left after absorption, capped by the balance). `409 ORDER_NOT_PAID`, `CHARGEBACK_DUPLICATE`, `ORDER_TOTAL_MISMATCH`, idempotency codes; `422 CHARGEBACK_NOT_ONLINE`, `CHARGEBACK_ITEMS_FORBIDDEN`, `CHARGEBACK_ALLOCATION_INVALID` (+ `available.lines`, `payment_cents`, `chargeable_cents`).
- **Date filters** are aware datetimes (a naive one is `422`); `placed_before`, `initiated_before`, `created_to` are exclusive.

### Frontend behaviour

- `/admin/cash-blocks` (nav "Cash blocks"): active / cleared / all, `?customer_id=` from the customer page, phone search through a mutation (the number never enters a URL or a query key), Clear block with confirmation; cleared rows offer nothing.
- Payment detail: **Release order** only on `release_order`, reason ≥ 10, an "I reviewed the N unprocessed events" tick required when the payment has any; **Record late capture** only on the `confirm` gate (a provider without a status API) for an attempt that never reached paid and has no late capture, keyed, linking to the created obligation.
- Admin order: **Record a chargeback** for a paid online order (cash attempts excluded), keyed, `received_at` from a local `datetime-local` as an aware instant; on `CHARGEBACK_ALLOCATION_INVALID` the form shows the server's `chargeable_cents` and line balances. Recorded chargebacks stay read-only.
- Filters: orders (`?customer_id`, placed from/to), payments (`?order_id`, started from/to), refunds (`?customer_id`, `?order_id`, recorded from/to). A day range is local midnight to the next local midnight (exclusive). A malformed id in the URL is ignored, never sent. The customer page links to Orders, Refunds and Cash blocks for that customer.
- Customer cancel: optional "Reason for cancelling" (≤500), sent as `{reason}` only when non-blank.
- Every write: CSRF, the shared admin MFA guard, explicit confirmation, a ref guard against double submits, never retried by itself; keyed writes keep their key only across uncertain outcomes; success re-reads the canonical admin queries.

### Results

| Scenario | Result | Evidence |
|---|---|---|
| Cash block created automatically | **PASS** | cash order `ready_to_ship` → UI Cancel line with reason `refused` → block row (reason `refused`, active) created by the server (confirmed in the database; the script's first check misread Postgres's `true`) |
| Block keeps the customer off cash | **PASS** | customer cash checkout → `422 CASH_NOT_AVAILABLE` |
| Cash blocks list | **PASS** | active list shows the order; `customer_id` filter → 1; no phone in the response |
| Phone search | **PASS** | invalid → `422`, "Enter a valid Lebanese phone number."; the real phone in a CSRF POST body → `200`, finds the block; the phone appeared in no URL |
| CSRF_INVALID on clear | **PASS** | stale cookie → `403`; "Unable to verify your session…"; block still active |
| Clear + idempotent repeat | **PASS** | UI clear → `200`; `cleared_at` + `cleared_by` set; repeat → `200` unchanged |
| Persistence after reload | **PASS** | "Cleared blocks" lists it |
| Customer cancel with optional reason | **PASS** | UI body `{reason}`; the `order.cancelled` audit row keeps it as `note`; order cancelled; cancellation refund pending |
| Chargeback allocation refused | **PASS** | items $5 with a $31 charge → `422 CHARGEBACK_ALLOCATION_INVALID`; the form showed the server's chargeable amount ($0: the pending $31 reissue absorbs it); nothing written |
| Chargeback recorded | **PASS** | UI POST → `201` with a new valid key; $31.00, applied 3100, excess 0; the pending reissue was voided and absorbed; order `refunded` |
| Chargeback idempotency + duplicate | **PASS** | same key + body → `201` replayed; new key, same dispute reference → `409 CHARGEBACK_DUPLICATE`; still 1 |
| Cash order: no chargeback | **PASS** | API → `422 CHARGEBACK_NOT_ONLINE`; the UI offers none |
| Manual release gated by the server | **PASS** | unpaid online order past its hold but inside the grace: `available_actions ["reconcile"]`, no Release button; POST → `409 grace_not_elapsed` with `release_available_at`; order unchanged |
| Late capture gated by the server | **PASS** | mock provider: POST → `409 MANUAL_CONFIRMATION_NOT_ALLOWED`; the UI offers none |
| Orders: customer + date filters | **PASS** | customer page → Orders: 5 rows = API 5 (all this customer); + placed today: 5 = API 5 |
| Refunds + payments filters | **PASS** | refunds `?customer_id`: 4 = API 4; payments `?order_id`: 1 = API 1 |
| Customer gets 404 | **PASS** | customer GET cash-blocks, clear, chargeback create → `404`; UI 404 page |
| No page errors | **PASS** | none |

### Not tested against the real backend (and why)

- **A successful manual release:** the oldest unpaid online order becomes releasable at 2026-11-11 23:56 UTC (hold + 24 h grace); the run ended before. The refusal path and the server gate were verified live; success, the events-reviewed tick and `unprocessed_events` are covered by unit and mocked E2E.
- **A successful late capture / manual confirm:** impossible with the mock provider (it has a status API). Covered by unit tests.
- **`CHARGEBACK_ITEMS_FORBIDDEN`** (a late-captured attempt), **`429`s:** not provoked.

### Refund void after reissue (phase 5I observation)

Verified against the implementation: `payments/domain/refunds.py refund_step` refuses a void with `line_already_refunded` whenever a line the refund names is `refunded` ("a void never reopens a closed line"), and the line becomes `refunded` once open refunds cover it. Intended by the current rule, but it leaves a full-line refund recorded by mistake impossible to void. Written up for the backend team in `docs/backend-handoff/REFUND-VOID-AFTER-REISSUE.md`. No frontend workaround: the dialog keeps the refusal, nothing is fabricated. (In this run the chargeback absorbed that pending reissue, which is the backend's own designed path.)

### Security review

- **Automated:** the security-guidance plugin's commit review (the project's existing workflow) ran on the phase 6A commits: "no security issues found". The phase 5I code commits (`18cceb1`, `e342025`, `52644c8`) had got no verdict (HTTP 429) and are not re-run by that hook; they were covered by the manual review below. The log file is outside the repository and was not committed.
- **Manual (all 5G-6A code):** every write sends CSRF through the shared `apiClient`/`adminRequest`; admin routes behind `AdminShell`/`AdminGuard` and the MFA signal, and the backend's boundary 404 verified for customers; every financial create (refund, reissue, late capture, chargeback) carries one `Idempotency-Key` bound to its body and kept only across uncertain outcomes; ref guards and `retry: false` on every mutation; no `dangerouslySetInnerHTML`, no redirects built from server data (navigation only to internal `/admin/...` paths from server ids), no browser storage, no secrets; backend `title`/`detail`/`msg`/`processing_error` never rendered; the phone search keeps the number out of URLs, keys and logs. No finding.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **2145/2145** (221 files) |
| `npm run build` | pass (`/admin/cash-blocks` static; search-param pages wrapped in `Suspense`) |
| `npm run test:e2e` | **151/151** in the one full run (3 new in `e2e/admin-operations.spec.ts`) |

### Remaining gaps

- Chargebacks cannot be updated or resolved (no backend route).
- STL delivery queue filters (`product_id`, `customer_id`) and the admin customer list's own link-back are not added.
- The void-after-reissue rule awaits the backend team's answer.

---

## Phase 5I: Admin Payments + Refunds (FVS-028), 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `18cceb1` (payment/refund contract, API, idempotency, write hook), `e342025` (`/admin/payments`, `/admin/payments/[id]`, `/admin/refunds`, `/admin/refunds/[id]`, Record a refund on the admin order; removal of the pre-contract payment code), `52644c8` (mocked E2E). All committed before the run |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json` identical to `docs/backend-handoff/openapi.json`; `AdminPaymentPage/Read/Detail`, `AdminPaymentOrderRead`, `AdminPaymentEventRead`, `AdminPaymentHistoryRead`, `ReconcileQueued`, `ManualPaymentConfirmRequest`, `RefundCreate`, `RefundDetail`, `RefundPage`, `RefundSettlementRequest`, `RefundFailureRequest`, `RefundVoidRequest` read field by field, then `payments/api/admin_payments.py`, `admin_refunds.py`, `admin_chargebacks.py`, `payments/domain/enums.py`, `refunds.py`, `manual.py`, `limits.py` |
| Runtime | Docker Compose backend on :8000 (`PAYMENT_PROVIDER=mock`). `npm run dev` on :3000 only for the run, stopped after it. `scripts/mock_pay.py` copied to the API container's `/tmp` and **removed after** (verified) |
| Method | real Edge through Playwright, real frontend and backend, **no route mocking**; the admin signed in through the frontend proxy (password + TOTP). Scripts in the session scratchpad, never committed |
| Identities | admin from `%USERPROFILE%\.bekaa3d\dev-admin.json` (never printed); phase 5H's `accept-admin-e-<ts>` customer, re-entered through the real password-reset flow. No new registration |
| Data left behind | `B3D-WQMG40BW` online (mock, **paid**) delivery, 2 × dragon, line delivered (admin transitions), order **`refunded`**: refund $5.00 **settled** (reference `MOCK-DASH-ACCEPT-1`), refund $31.00 **failed** (reissued), its reissue $31.00 **pending** (the void was refused by the backend, below). Phase 5H's cash payment on `B3D-NRAW56SC` was only read. No money moved (mock provider; refunds are records) |

**Overall: PASS, 18/18** for the frontend (two script assertions corrected; one backend observation recorded).

### Current contract (as implemented)

Admin + completed MFA; customers get `404`; writes need `X-CSRF-Token`; no refund route calls a provider (ADR-024 d16: the admin pays in the dashboard or by hand, then records it).

- **Payments:** `GET /api/v1/admin/payments` (`status` repeatable, `provider` `mock`|`cash`, `order_id`, `late_captured`, `initiated_after/before`, `limit` 1-100 (20), `cursor`; oldest first). `GET …/{id}` → `{payment, order (with hold_expires_at, manual_release_available_at), events (no payloads), history (audit), available_actions}`. `available_actions`: online with a status API → `reconcile`; online without one → `confirm`; cash → none; `release_order` after an unpaid order's grace.
- **Reconcile:** `POST …/{id}/reconcile` → `202 {payment, reconcile: "queued"}` (the provider is asked after the answer); cash → `409 INVALID_STATE_TRANSITION` `cash_payment`; no status API → `503 PAYMENT_VERIFICATION_UNAVAILABLE`. 60/h.
- **Manual confirm:** `POST …/{id}/confirm` `{provider_reference 1-255, verified_amount_cents, verified_currency, reason 10-1000}`; `409 MANUAL_CONFIRMATION_NOT_ALLOWED` / `PAYMENT_REFERENCE_MISMATCH`, `422 PAYMENT_AMOUNT_MISMATCH`. Never offered with the mock provider (it has a status API).
- **Refund create:** `POST /api/v1/admin/orders/{id}/refunds` + required `Idempotency-Key`, body `{items: [{order_item_id, amount_cents > 0}] (1-50), reason 1-1000}` → `201 RefundDetail` (kind `admin`, status `pending`). Per **line**, up to `refund_balance.lines`, total up to `payment_cents`; no shipping amount (ADR-024); STL lines like any other (ADR-019). `409 ORDER_NOT_PAID`, `ORDER_TOTAL_MISMATCH`, `IDEMPOTENCY_KEY_CONFLICT`, `IDEMPOTENCY_REQUEST_IN_PROGRESS`; `422 REFUND_EXCEEDS_AVAILABLE` (`available.lines[]`, `payment_cents`), `REFUND_REQUIRES_CANCELLATION` (`order_item_ids`: refunding an unfinished printed line in full needs a cancel). Same key + same body replays the 201 (`Idempotent-Replayed: true`).
- **Refund transitions:** `settle {reference? ≤200, note? ≤1000}`, `fail {reason}`, `void {reason}` (on a pending refund; a failed one stays `owed` until reissued or voided), `reissue` (+ `Idempotency-Key`: failed → a new pending refund). `409 INVALID_STATE_TRANSITION` reasons `not_pending`, `not_failed`, `already_settled`, `already_reissued` (+ `reissued_by_refund_id`), `line_already_refunded`, `line_already_cancelled`. 60 writes/h.
- **Refund lists:** `GET /api/v1/admin/refunds` (`queue=true` default: pending or owed, oldest first; `queue=false`: history; `status`, `kind`, `order_id`, `customer_id`, dates, `limit`, `cursor`); `GET …/{id}`.
- **Chargebacks:** `POST /api/v1/admin/orders/{id}/chargebacks` (+ `Idempotency-Key`) and the `GET` routes exist. **Not built in the frontend**: chargebacks show read-only on the admin order.
- **Effects seen:** a settled partial refund → order and payment `partially_refunded`; open refunds covering the rest → order `refunded`. The customer sees refunds as `processing` (pending) / `refunded` (settled).

### Frontend behaviour

- `/admin/payments` (filters: status, provider, late captures) and `/admin/payments/[id]`: events without payloads and without the backend's `processing_error` text (only "Processing failed"), the audit history in our own labels (no `data`), and exactly the server's `reconcile`/`confirm` actions, each confirmed.
- `/admin/refunds` (queue / history, kind, status) and `/admin/refunds/[id]`: actions offered from the documented state machine (pending → settle/fail/void; failed and owed → reissue/void), each confirmed; the server re-checks.
- **Record a refund** on `/admin/orders/[id]`: one amount per line that has a server balance, each up to that balance, total up to the payment's; a reason; one `Idempotency-Key` per intended refund (bound to the exact body, kept only across uncertain outcomes, retired by any definitive answer). On `REFUND_EXCEEDS_AVAILABLE` the form switches to the balances the server returned. Success opens the refund page.
- **Cache:** `["admin","payments"]` and `["admin","refunds"]` under the user-scoped `["admin"]` root. Every success stores the returned `RefundDetail` and re-reads payments, refunds and admin orders. No financial write is retried by itself; a ref guard drops double submits.

### Results

| Scenario | Result | Evidence |
|---|---|---|
| Payments list + provider filter | **PASS** | the new mock payment listed; `provider=cash` → phase 5H's `B3D-NRAW56SC` (API rows all cash) |
| Cash payment record | **PASS** | cash/paid, `available_actions []`, no actions in the UI; reconcile → `409` `cash_payment` |
| Online/mock payment + reconcile | **PASS** | `available_actions ["reconcile"]`, no "Confirm by hand"; UI POST → `202`, "Check requested…"; history gained `payment.reconcile_requested` |
| Full refund of an unfinished line | **PASS** | pending line, full amount → `422 REFUND_REQUIRES_CANCELLATION` (`order_item_ids`); no refund row |
| Refund over balance | **PASS** | 3700 > 3600 → `422 REFUND_EXCEEDS_AVAILABLE`, `available.lines[0].balance_cents 3600`, `payment_cents 3600` |
| Partial refund from the UI | **PASS** | UI POST → `201` with a valid `Idempotency-Key` + CSRF; body `{items:[{line, 500}], reason}`; refund pending/admin $5.00; its page opened |
| Refund idempotency | **PASS** | same key + body → `201 Idempotent-Replayed`, same refund id; same key + other body → `409 IDEMPOTENCY_KEY_CONFLICT`; still 1 row |
| Settle + post-refund state | **PASS** | settled, reference kept, no further actions; order and payment `partially_refunded`, balance left 3100; the customer sees `partially_refunded` with the refund |
| Void after settlement refused | **PASS** | `409` `already_settled` |
| CSRF_INVALID | **PASS** | stale cookie → UI POST fail `403`; "Unable to verify your session…"; refund still pending |
| Fail → reissue | **PASS** | failed (owed) → reissue `201` with a valid key; original failed, not owed, `reissued_by_refund_id` set; new refund pending $31.00 |
| Void refused by the backend (UI handling) | **PASS** | voiding the pending reissue → `409` `line_already_refunded`; the dialog stayed open with "One of these items is already fully refunded."; refund unchanged (backend observation below) |
| Queue vs history | **PASS** | queue for the order: 1 (the pending reissue), UI 1; history: 3 (pending, failed, settled), UI 3 |
| Persistence after reload | **PASS** | refund page reload: Settled |
| Order state after the refunds | **PASS** | order **`refunded`** (the pending reissue covers the rest); customer refunds `refunded` + `processing` |
| Customer gets 404 | **PASS** | customer `GET /admin/payments` and `/admin/refunds/{id}` → `404`; UI `/admin/refunds` → 404 page |
| Admin MFA/guard | **PASS** | the same `AdminShell`/`adminRequest` verified in the phase 5H run; this run used a real MFA-complete session |
| No page errors | **PASS** | none |

Script assertions corrected (not app defects): after the reissue the script still expected `partially_refunded`, but open refunds covering the rest make the order `refunded`; and a duplicate password-reset confirm in the resume script returned `400` (the first one had succeeded).

### Backend observation (not changed; for the backend team)

- **A pending reissue cannot be voided once its line is fully committed.** After a $5.00 settled refund and a $31.00 refund that failed and was reissued, voiding the $31.00 reissue answered `409 INVALID_STATE_TRANSITION` `reason: line_already_refunded`. The failed original is no longer owed (it was reissued), so the reissue looks like the only open obligation, and voiding it should probably free the balance. The frontend shows the refusal and changes nothing.

### Not tested against the real backend (and why)

- **Manual confirm** (`confirm`): never offered with the mock provider (it has a status API). Covered by unit tests (validation, exact body, `PAYMENT_AMOUNT_MISMATCH`).
- **A plain void of a pending refund:** the only pending refund at that point was the reissue (above). Covered by unit and mocked E2E.
- **Late captures** (`late_captured`, `record-capture`), **chargebacks** (create not built), **`IDEMPOTENCY_REQUEST_IN_PROGRESS`**, **`429`:** these need a provider race, an unbuilt form, a concurrent request or many writes.

### Defects found and fixed

- None in the app during the real run. During development (mocked E2E) the refund form correctly kept enforcing the server's newer balance after a refusal; the test was adjusted to reopen the form after the balance changed.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **2127/2127** (218 files; lower because the obsolete pre-contract payment tests were deleted) |
| `npm run build` | pass |
| `npm run test:e2e` | **148/148** in the one full run (5 new in `e2e/admin-payments.spec.ts`) |

### Remaining gaps

- Chargeback creation, `record-capture`, manual release (`release_order`) and cash blocks are not built in the frontend.
- No `customer_id`/date filters in the payment and refund list UIs.

---

## Phase 5H: Admin Orders + Fulfillment (FVS-030), 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `797cde3` (admin order contract, API, presentation, write hook), `9a43cc1` (`/admin/orders`, `/admin/orders/[id]`, `/admin/stl-deliveries`; removal of the pre-contract admin order code), `4e6613e` (mocked E2E), `7126f5d` (admin nav E2E update). All committed before the run; this document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json` identical to `docs/backend-handoff/openapi.json`. `AdminOrderPage`, `AdminOrderSummaryRead`, `AdminOrderDetail`, `AdminOrderLineRead`, `AvailableActionRead`, `AdminOrderPaymentRead`, `AdminHistoryRead`, `AdminOrderRefundRead`, `AdminOrderChargebackRead`, `AdminRefundBalanceRead`, `OrderItemTransitionRequest`, `CashHandoverRequest`, `AdminOrderUpdate`, `AdminOrderCancelRequest`, `StlDeliveryPage` read field by field, then `fulfillment/api/admin_orders.py`, `item_transition.py`, `stl_deliveries.py`, `admin_order_schemas.py`, `ordering/domain/line_transitions.py`, `handover.py`, `cancellation.py`, `fulfillment/domain/limits.py` |
| Runtime | Docker Compose backend on :8000. `npm run dev` on :3000 only for the run, stopped after it |
| Method | real Edge through Playwright, real frontend and backend, **no route mocking**. The admin signed in through the frontend proxy (real password login + TOTP), so the browser held a real MFA-complete admin session. API probes used the same browser contexts. Scripts in the session scratchpad, never committed |
| Identities | admin from `%USERPROFILE%\.bekaa3d\dev-admin.json` (never printed). Throwaway customer `accept-admin-e-<ts>@example.com` (real register + verify; re-entered once through the real password-reset flow after a script abort), and phase 5G's `accept-actions-d-<ts>` STL order. One unverified `accept-actions-u-<ts>` for phase 5G's deferred check |
| Data left behind | E: `B3D-NRAW56SC` cash/delivery **completed** (handover recorded, internal note set); `B3D-ND4X5EE4` cash/delivery **cancelled by the administrator**. D: `B3D-MHPCF8SG` STL line now **delivered** (marked emailed; no file was actually sent). U: no orders. No setting or product changed |

**Overall: PASS, 20/20** (19 for phase 5H plus phase 5G's deferred unverified-account check).

### Current contract (as implemented)

Admin with completed MFA; a customer gets `404 NOT_FOUND` from the admin boundary; a password-only login (MFA challenge pending) holds no session (`401 AUTH_REQUIRED`), and an admin whose MFA enrolment is incomplete gets `401 MFA_REQUIRED`. Writes need `X-CSRF-Token`. **No version / If-Match concurrency**: every write re-checks under the server's locks and answers `409`. Every write answers with the full `AdminOrderDetail`.

- **Queue:** `GET /api/v1/admin/orders` — `status` (never `pending_payment`: `422`; unpaid online orders are not in the queue), `fulfillment_method`, `payment_method`, `payment_due` (the "cash due" view), `customer_id`, `order_number` (1-40), `placed_after`/`placed_before`, `limit` 1-100 (default 25), opaque `cursor`. Newest first; `{items, next_cursor}`; no total.
- **Detail:** `GET /api/v1/admin/orders/{id}` — the real line states (`in_production` included), per line `available_actions [{target_status, cancel_reasons}]` (ADR-025), `payments[]` (newest first; `provider` `cash`/`mock`, `recorded_by` for cash), `status_history[]` with `actor_user_id` and `reason`, `refunds[]`, `chargebacks[]`, `refund_balance`, `admin_note`, `payment_reached_paid`.
- **Line transition:** `POST …/items/{item_id}/transition` `{target_status, reason? ≤500 (history note), cancel_reason?}`. Edges: delivery `pending→in_production→ready_to_ship→shipped→delivered|returned`, pickup `…→ready_for_pickup→picked_up`, STL `awaiting_delivery→delivered` (manual email, ADR-019), plus cancels (`cancel_reason` required from `ready_to_ship`/`ready_for_pickup`/`returned`/`shipped`). A **cash** line never offers `delivered`/`picked_up`: that is the cash handover. `409 INVALID_STATE_TRANSITION` with `reason` (`payment_required`, `cash_handover_required`, `not_a_legal_edge`, `line_closed`, `cancel_reason_required`, `cancel_reason_not_allowed`, `refund_exceeds_available`, STL `already_delivered` with `fulfilled_at`, `not_awaiting_delivery`) and `fulfillment_status`; `ORDER_TOTAL_MISMATCH`. 300/h per admin, shared by every line transition and the order cancel.
- **Cash handover:** `POST …/cash-handover` `{amount_cents, currency: "USD", note?}`. Every live line at the ready state (delivery `shipped`, pickup `ready_for_pickup`); the amount is exactly the live total (`422 CASH_AMOUNT_MISMATCH` with `amount_due`). Records a `cash` payment (`paid`, `recorded_by`) and marks every live line delivered / picked up. `409` reasons `not_a_cash_order`, `no_live_line`, `already_recorded`, `lines_not_ready`. 60/h.
- **Order cancel:** `POST …/cancel` `{reason (1-500), cancel_reason?}`: every physical line still `pending`/`in_production`/`ready_to_ship`/`ready_for_pickup`; refuses an unpaid online order (`payment_required`) or none left (`no_cancellable_line`). Paid lines are refunded (ADR-043). An admin cancel never sets `customer_cancelled_at` (no 24-hour cash hold).
- **Internal note:** `PATCH /api/v1/admin/orders/{id}` `{admin_note}` (≤5000; blank or null clears). Never in any customer response. 120/h.
- **STL delivery queue:** `GET /api/v1/admin/stl-deliveries` (`product_id`, `customer_id`, `limit`, `cursor`): every paid STL line still owed, oldest first. Recording a send is the line transition `awaiting_delivery → delivered`.
- **Not in scope here:** `POST /admin/orders/{id}/release` (manual release of an unpaid online order after the 24 h grace, payment recovery) and `/admin/cash-blocks` (cash eligibility blocks). Both are real routes, not built in the frontend yet.

### Frontend behaviour

- **Routes:** `/admin/orders` (queue), `/admin/orders/[id]` (detail), `/admin/stl-deliveries`; nav entries "Orders" and "STL deliveries". Protected by the existing `AdminShell`/`AdminGuard` (customer → 404, MFA incomplete → setup).
- **Server-provided actions only:** a line's buttons are exactly its `available_actions` (labels are ours; an unknown target reads "Update line"). Every write goes through an explicit confirmation (`AdminActionDialog`, on `DialogShell`), with an optional history note; a cancel that lists `cancel_reasons` requires one of exactly those.
- **Order-level offers** (no server flag; the POST re-checks): Record cash handover ⇔ unpaid cash order with every live line at the ready state; Cancel order ⇔ some physical line before shipping/collection that the server offers `cancelled` for (reason required; cancel reason required when a ready line takes one). The cash amount is **typed**, never prefilled.
- **Cache:** `adminOrderKeys` under the user-scoped `["admin"]` root. Each write stores the server's `AdminOrderDetail` in `adminOrderKeys.detail(id)` and invalidates the admin order family (queue, STL queue, detail). Refusals re-read too. Nothing marked paid or delivered locally. No silent retry of a state-changing conflict; a ref guard drops double submits.
- **Errors:** status + `code` + typed `reason`/`amount_due` only; frontend copy for every documented reason; unknown → neutral. Never `title`/`detail`/`msg`.
- **Payments/refunds/chargebacks** on the detail are read-only in this phase.
- **Removed (pre-contract, unmounted):** `adminOrderModel`, `AdminOrderDetail`, `AdminOrderLine`, `AdminOrderLineItem`, `AdminOrderSummaryDisplay`, `AdminCancelDialog` (per-line cancel with free text: not the contract), `TransitionActions`, `OrderConcurrencyConflictNotice` (no version concurrency exists), `OrderActionButtons`, `orderActionModel`. `InternalNoteEditor` reused (remounted by `key` on the server's note).

### Results

| Scenario | Result | Evidence |
|---|---|---|
| 5G deferred: unverified account | **PASS** | confirm-receipt (another customer's order) `403 EMAIL_VERIFICATION_REQUIRED`; report-problem and cancel (unknown ids) `403` — checked before ownership, reveals nothing |
| Customer gets 404 | **PASS** | customer `GET /admin/orders/{id}` and `GET /admin/orders` → `404 NOT_FOUND`; UI `/admin/orders/{id}` → 404 page |
| Admin MFA guard | **PASS** | password-only login `202` (challenge pending) → `GET /admin/orders` `401 AUTH_REQUIRED` |
| Queue + filters | **PASS** | nav "Orders" current; Cash due filter (API rows all `payment_due`); order-number lookup → 1 row; `status=pending_payment` → `422` |
| Detail = server state | **PASS** | server `available_actions ["in_production","cancelled"]` → UI "Start production", "Cancel line"; cash due, address, phone; no handover offered yet |
| Physical fulfillment transitions | **PASS** | 3 UI POSTs → `200` (pending → in_production → ready_to_ship → shipped); bodies `{target_status[, reason]}`; DB line `shipped`; history keeps the note and the admin actor |
| Cash line offers no "Mark delivered" | **PASS** | server actions at `shipped` (cash) `["returned"]`; UI "Mark returned"; Record cash handover offered |
| Illegal transition refused | **PASS** | shipped → delivered (cash) `409` `cash_handover_required`; shipped → in_production `409` `not_a_legal_edge`, `fulfillment_status: shipped`; line unchanged |
| CSRF_INVALID | **PASS** | stale cookie → UI POST cash-handover `403`; "Unable to verify your session…"; no payment row |
| Cash amount mismatch | **PASS** | $0.01 → `422 CASH_AMOUNT_MISMATCH`; "…exactly the amount due ($36.00)." from `amount_due`; no payment row |
| Cash handover | **PASS** | body exactly `{amount_cents: 3600, currency: "USD"}` (typed); order `completed`, `payment_due` false; payment `cash`/`paid`, `recorded_by` set; line `delivered` |
| Customer sees the handover | **PASS** | customer detail `completed`, payment `paid`, line `delivered` |
| Repeat handover refused | **PASS** | `409` `already_recorded`; still 1 payment |
| Internal note + persistence | **PASS** | PATCH `200`; reload shows it; absent from the customer's order detail |
| Reload persistence | **PASS** | Completed, Delivered, Staff history entries |
| STL manual delivery | **PASS** | queue row → Mark emailed → `{target_status: "delivered"}` `200`; `fulfilled_at` + `delivered_by` set; row left the queue; order `completed` |
| STL repeat refused | **PASS** | `409` `already_delivered` with `fulfilled_at` |
| STL line in the UI | **PASS** | "Sent by email", no actions, no download/upload |
| Admin order cancel | **PASS** | reason required client-side; POST `{reason}` → `200`; order and line `cancelled`; `customer_cancelled_at` stays null; history keeps the reason |
| No page errors | **PASS** | none |

The first attempt aborted on the acceptance script's own address payload (missing `landmark_notes`) after registering the customer; the rerun re-entered that customer through the real password-reset flow. Registration's 5/h per-IP limit was read from Redis (TTL only) rather than probed, after the phase 5G run showed that probing keeps the window full.

### Not tested against the real backend (and why)

- **Pickup flow** (`ready_for_pickup`, `picked_up`, pickup handover): delivery was used; the pickup edges come from the same server `available_actions` and are covered by unit tests.
- **`returned` and a cancel with `cancel_reason`** (from `ready_to_ship`/`ready_for_pickup`): not provoked; covered by unit and mocked E2E (reason required, exactly the server's reasons).
- **Online paid line → Mark delivered:** shown in phase 5G's admin precondition (API) and in mocked E2E.
- **`MFA_REQUIRED` for an admin with incomplete enrolment:** needs a second admin account; covered by the existing admin guard tests (phase 5A real run).
- **`429` limits:** not provoked.

### Defects found and fixed

- **During development (mocked E2E):** after a refused transition, the re-read line could offer nothing, and `LineActions` unmounted with its open dialog and error. Same for the order-level dialogs (handover, cancel) when the re-read withdrew the offer. Both now stay until dismissed (unit tests + E2E).
- **Expected test updates:** the admin nav tests (unit and E2E) asserted "no Orders entry"; updated now that orders are built.
- No app defect in the real run.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **2252/2252** (236 files; the removed pre-contract admin order tests account for the lower count) |
| `npm run build` | pass (`/admin/orders` static, `/admin/orders/[id]` dynamic, `/admin/stl-deliveries` static) |
| `npm run test:e2e` | **142/143** in the one full run; the one failure was `admin-routes.spec.ts` still asserting the nav had no "Orders" link — updated (5/5). 8 new tests in `e2e/admin-orders.spec.ts` |

### Remaining gaps

- Manual release (`POST /admin/orders/{id}/release`) and cash blocks (`/admin/cash-blocks`) are not built in the frontend.
- No customer filter (`customer_id`) or date-range filter in the queue UI (the backend supports them).
- STL queue filters (`product_id`, `customer_id`) not exposed.

---

## Phase 5G: Customer Order Actions (FVS-031), 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `74e2140` (action API, availability, error model), `cd70d6c` (Order actions section), `cf7cd5a` (mocked E2E), `11860ed` (smoke readiness-banner race, test only). The cash-cancel copy (ADR-038 d23, found by this run) is in the docs commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json` is identical to `docs/backend-handoff/openapi.json` (key-sorted). `CustomerOrderCancelRequest`, `ProblemReportCreate` and the three routes' responses read field by field, then the implementation (`ordering/api/cancel.py`, `ordering/api/receipt.py`, `ordering/application/services/receipt.py`, `ordering/domain/receipt.py`, `ordering/domain/customer_view.py`, `ordering/domain/cancellation.py`, `fulfillment/application/cancel_lines.py`; ADR-038 d23, ADR-043) |
| Runtime | Docker Compose backend on :8000 (`PAYMENT_PROVIDER=mock`). `npm run dev` on :3000, started only for the run and stopped after it. `scripts/mock_pay.py` copied to the API container's `/tmp` for the run and **removed after it** (verified) |
| Method | real Edge through Playwright against the real frontend and backend. **No route mocking.** API probes used the browser context's request client (same cookies). Scripts kept in the session scratchpad, never committed |
| Customer identities | throwaway `accept-actions-a-<ts>` and `accept-actions-d-<ts>@example.com` (real register with the Turnstile test token, real verify-email with the token read only from that account's `email_outbox` row; D re-entered once through the real password-reset flow). Random passwords, never printed or stored |
| Admin | credentials read only from `%USERPROFILE%\.bekaa3d\dev-admin.json` (real login + TOTP). Used **only** to move one test order through its real line transitions (`POST /api/v1/admin/orders/{id}/items/{item}/transition`): `in_production` → `ready_to_ship` → `shipped` → `delivered`. No admin frontend was built or used |
| Data left behind | A: `B3D-6QJMXDW1` and `B3D-AKX3XEAR` cash/delivery, **cancelled by the customer** (the first from an aborted script run); `B3D-5D0C9N6V` online (mock, paid)/delivery, **completed**, line `delivered`, receipt confirmed, 2 problem reports (2 `contact_messages` rows, status `new`). D: one STL-only online order, paid, line `awaiting_delivery` (never emailed). No setting or product changed |

**Overall: PASS, 33/33** (after correcting three script assertions, none an app defect). One product rule found and surfaced in the UI (below).

### Current contract (as implemented)

All three: `POST`, the order's owner, **verified email** (`403 EMAIL_VERIFICATION_REQUIRED`, checked before ownership), `X-CSRF-Token` (`403 CSRF_INVALID`), `401 AUTH_REQUIRED` without a session. Another customer's order and an unknown id: the same `404 NOT_FOUND`. Every success answers with the full **`OrderDetailRead`**.

- **Cancel:** `POST /api/v1/me/orders/{order_id}/cancel`. Optional body `CustomerOrderCancelRequest {reason?: string ≤500}` (`extra="forbid"`), an audit note only; the UI sends no body. `200`. **Order-level, all-or-nothing**: every live physical line, all still `pending`, cash or paid, order `in_progress`/`partially_refunded` (the same `can_cancel` the detail reports, re-checked under the locks). Otherwise `409 ORDER_NOT_CANCELLABLE` (no extensions): printing started, an unpaid online order, an STL-only order, nothing left. STL lines are never cancelled. A paid order's cancelled lines get a cancellation refund (pending until settled, ADR-043). `429 RATE_LIMITED` (10/h per user). Sets `orders.customer_cancelled_at`; **`orders.cancelled_at` stays null** (ADR-043 d7: it is the hold release's mark), each line gets its own `cancelled_at`.
- **Confirm receipt:** `POST …/confirm-receipt`, no body, `200`. Needs a **physical** line `delivered` or `picked_up` (an STL "delivered" is an emailed file), else `409 INVALID_STATE_TRANSITION` with `reason: "no_delivered_line"`. Stamps `receipt_confirmed_at` on those lines once; a repeat is a no-op (no audit row). Changes no line or order status. No rate limit.
- **Report a problem:** `POST …/report-problem`, body `ProblemReportCreate {message}` (`extra="forbid"`; 1-5000 characters, not blank, no control characters except tab/LF/CR), `201`. Same `409 no_delivered_line`. Every report is a new contact message for the team (no ticket number is returned); `problem_reported_at` keeps the **first**. No category or attachment. `422 VALIDATION_ERROR`; `429 RATE_LIMITED` (5/h per user, counting refused requests too).
- **ADR-038 d23:** a cash order the customer cancels counts toward `cash_max_open_orders` for **24 hours**, for the account and the phone. Cash checkout meanwhile is `422 CASH_NOT_AVAILABLE` (which never says why).
- **No capability flags for the receipt actions** on `OrderDetailRead` (logged in `FRONTEND-VERTICAL-SLICE-PLAN.md` §17).

### Frontend behaviour

- **Where:** `/account/orders/[id]`, a separate "Order actions" section under the items (`OrderCustomerActions`), apart from the FVS-027 payment section, which is unchanged.
- **Offered only when the server's state makes it meaningful** (`orderActions.ts`): Cancel order ⇔ `can_cancel`; I received my items ⇔ a delivered/picked-up physical line without `receipt_confirmed_at`; Report a problem ⇔ a delivered/picked-up physical line (repeats allowed). With nothing offered and nothing recorded, the section is absent. Recorded receipt / problem dates come from the server's line fields.
- **Cancel:** explicit dialog, focus on "Keep my order", effect described in frontend copy (printed items before production; STL files unaffected; paid online → refunded; cash → nothing to pay, and cash may be unavailable for a new order for 24 hours). Stays open with the error on failure; closes only on success.
- **Report a problem:** one textarea with a live character count; client validation mirrors the server (code points, not UTF-16 units). The text survives a failed send and a close/reopen; it is cleared only after success.
- **Cache:** one hook (`useOrderAction`). On success the POST's own `OrderDetailRead` is written to `orderKeys.detail(id)` and the user-scoped `orderKeys.root` family is invalidated (detail + history list). A refusal, 404 or unknown outcome also invalidates it. No second store; nothing set locally; history entries come only from the server.
- **Duplicate submits:** a synchronous ref guard plus pending/disabled controls; `retry: false`. The shared `authenticatedRequest` resends the identical request once after a silent refresh on `401`.
- **Errors** (`orderActionErrors.ts`, status + `code` + `reason` only): ORDER_NOT_CANCELLABLE, INVALID_STATE_TRANSITION/no_delivered_line (unknown reasons get neutral copy), NOT_FOUND, CSRF_INVALID (and the local missing-cookie case), AUTH_REQUIRED, EMAIL_VERIFICATION_REQUIRED, 422 on a report, RATE_LIMITED (with Retry-After), network/timeout/5xx ("couldn't confirm whether that went through", re-read). Never `title`, `detail` or `msg`.
- **Keeps a refusal visible:** if the re-read after a refusal leaves nothing to offer, the open dialog (and its error) or the receipt error stays until dismissed (found by mocked E2E during development).

### Results

| Scenario | Result | Evidence |
|---|---|---|
| Contract: new cash order cancellable | **PASS** | `in_progress`, `can_cancel: true`, `payment_due: true` |
| Cancel confirmation dialog | **PASS** | explicit confirmation; frontend copy incl. the 24-hour cash note; focus on "Keep my order" |
| Cancel POST from the UI | **PASS** | double-click → **1** POST → `200`; no body; `X-CSRF-Token` = cookie |
| Real cancel state transition | **PASS** | order `cancelled` (DB too), `customer_cancelled_at` set, detail `cancelled_at` null (ADR-043 d7), `can_cancel`/`payment_due` false, `amount_due` null, line `cancelled` with `cancelled_at`; history `order:in_progress→cancelled`, `line:pending→cancelled`; no refund, no payment (cash, unpaid) |
| UI shows the server's cancelled state | **PASS** | badge "Cancelled"; "Order updates" gained the server's entries; no Cancel |
| Cancel persists after reload | **PASS** | still Cancelled, no action |
| Order history reflects the cancel | **PASS** | card "Cancelled", no payment due |
| Repeat cancel refused | **PASS** | `409 ORDER_NOT_CANCELLABLE` |
| Self-cancelled cash order counts for 24 h | **PASS** | cash checkout right after → `422 CASH_NOT_AVAILABLE` (ADR-038 d23) |
| `no_delivered_line` (pending order) | **PASS** | confirm-receipt and report-problem → `409 INVALID_STATE_TRANSITION` `reason: no_delivered_line`; nothing stamped |
| Pending order offers no receipt actions | **PASS** | only Cancel order |
| Refused cancel once printing started | **PASS** | admin → `in_production`; the customer line still reads `pending`, `can_cancel: false`; POST → `409 ORDER_NOT_CANCELLABLE`; DB line still `in_production` |
| Refused cancel in the UI (stale page) | **PASS** | dialog kept open with "This order can no longer be cancelled, so nothing was changed…"; after closing, the re-read order offers no Cancel |
| Shipped is not received | **PASS** | line `shipped`: confirm-receipt → `409` `no_delivered_line` |
| Admin precondition: delivered | **PASS** | real transitions `in_production` → `ready_to_ship` → `shipped` → `delivered` (each `200`); customer: line `delivered`, order **`completed`**, payment `paid` |
| Delivered order offers receipt + report, no cancel | **PASS** | |
| Confirm receipt | **PASS** | UI POST → `200`, no body; `receipt_confirmed_at` set; order status unchanged (`completed`); line still `delivered` |
| UI after confirm | **PASS** | server date shown; action no longer offered |
| Repeat confirm is idempotent | **PASS** | `200`; `receipt_confirmed_at` unchanged; one `order.receipt_confirmed` audit row |
| Receipt persists after reload | **PASS** | |
| Report validation (client) | **PASS** | blank → "Describe the problem before sending.", no request |
| CSRF_INVALID | **PASS** | stale cookie → UI POST `403`; "Unable to verify your session…"; text kept; no contact message stored |
| Session refresh during report | **PASS** | access cookie dropped → `401` → silent refresh → identical request → `201`; body exactly `{message}` |
| Report a problem | **PASS** | `problem_reported_at` set; 1 contact message for the order; line and order state unchanged |
| UI after report | **PASS** | "Your report was sent. Our team will reply by email." + server date |
| Report persists after reload | **PASS** | date shown; Report a problem still offered |
| Repeat report | **PASS** | `201`; a second contact message; `problem_reported_at` keeps the first |
| Report validation (server) + rate limit | **PASS** | blank → `422`, 5001 characters → `422` `VALIDATION_ERROR`; the next (sixth this hour, refusals included) → `429 RATE_LIMITED`. No message stored for any |
| STL-only cancellation rule | **PASS** | paid STL-only order: `can_cancel: false`; POST cancel → `409 ORDER_NOT_CANCELLABLE`; line `awaiting_delivery` |
| STL-only order in the UI | **PASS** | no Order actions section; no download |
| Foreign vs unknown order | **PASS** | D on A's order vs a random id: cancel, confirm-receipt, report-problem each `404`/`404` with identical bodies (apart from `instance`/`request_id`); A's order untouched |
| Foreign order in the UI | **PASS** | "Order not found" (same as unknown) |
| No page errors | **PASS** | none |

Script assertions corrected during the run (not app defects): the first run expected the detail's `cancelled_at` to be set after a customer cancel (ADR-043 d7 says it stays null); it then expected a second cash order on the same account (ADR-038 d23 refuses it for 24 hours, so the receipt order became a paid online one); and the STL checkout lacked `accept_digital_final_sale`. The third validation probe met the real 5/h limit, which is recorded as evidence. Registration then hit its own 5/h per-IP limit (a sliding window that the script's own probes kept full), so the foreign check ran as D (a second verified customer).

### Not tested against the real backend (and why)

- **Cancelling a paid order** (refund created, `partially_refunded`/`refunded` status, Refunds row): the refund is settled by an administrator (Phase 5I). The dialog's refund copy and the Refunds section are covered by unit and mocked E2E.
- **Mixed physical + STL cancel** (STL line kept, order stays live): not provoked, to keep to one cancelled order; the rule was read from `customer_cancels` and is covered by unit tests.
- **Pickup `picked_up` receipt:** the delivery path was used; the rule (`delivered` or `picked_up`) is covered by unit tests.
- **`429` on cancel** (10/h): not provoked, to avoid extra orders.
- **Unverified account (`403 EMAIL_VERIFICATION_REQUIRED`):** registration was rate-limited for the rest of the run. Run in the Phase 5H run instead: **PASS** (see that section).

### Defects found and fixed

- **During development (mocked E2E):** after a refusal, the canonical re-read could leave the section with nothing to offer, and it unmounted, taking the open dialog and its error with it. The section now stays while a dialog is open or an error is showing (unit test + E2E).
- **Product rule surfaced by the real run:** ADR-038 d23 (cash held off for 24 hours after a self-cancel) was not in the cancel dialog. Added frontend copy for cash orders ("you may not be able to choose cash payment for a new order for 24 hours").
- **Flaky test (pre-existing, test only):** `smoke.spec.ts` readiness-banner test counted `role=status` regions and then waited on each by index (failed 1/3 alone). It now reads every region's text in one `allTextContents()` snapshot (8/8).

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **2272/2272** (239 files), re-run after the cash-copy change |
| `npm run build` | pass, re-run after the cash-copy change |
| `npm run test:e2e` | **134/135** in the one full run; the one failure was the pre-existing readiness-banner race (above), fixed test-only and then 8/8 on repeat. 10 new tests in `e2e/account-order-actions.spec.ts` (10/10 again after the copy change); `account-orders.spec.ts` updated in place |

### Remaining gaps

- No `can_confirm_receipt` / `can_report_problem` flags (§17): the page offers them on the backend's documented received-line rule.
- The cancel reason (`reason?`, an audit note) is not collected by the UI.
- A customer-cancelled order shows no "Cancelled on" date in the header, because the detail's `cancelled_at` is null by design; the date appears in "Order updates".

---

## Phase 5F: Payment Result + Payment Retry (FVS-027), 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `c2e4881` (retry API, idempotency, error model), `4b61218` (bounded polling on the canonical order detail), `841e587` (order-detail payment states, hold countdown, Retry payment), `f5cffde` (neutral `/checkout/return`), `d1ccb07` (mocked E2E). All committed before the run; this document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json`: `POST /api/v1/me/orders/{order_id}/payments`, `PaymentRetryRequest`, `PaymentRetryRead`, `RetryOrderRead`, `RetryPaymentRead`, `OrderPaymentRead` read field by field; `GET /api/v1/me/orders` query parameters are `status, placed_after, placed_before, cursor, limit` (no order-number lookup) |
| Runtime | Docker Compose backend on :8000 (`PAYMENT_PROVIDER=mock`, `ENVIRONMENT=development`, `checkout_hold_period` 1800 s). `npm run dev` on :3000 proxying to :8000, started only for this run and stopped after it |
| Mock provider | the backend's own `scripts/mock_pay.py` (sets the mock state in Redis, then posts a signed `POST /api/v1/webhooks/payments/mock`; the backend verifies it in the background and applies the result). The image has no `scripts/` folder, so the file was copied to the dev API container's `/tmp` for the run and **removed after it** (verified) |
| Method | real Edge browser through Playwright against the real frontend and backend. **No route mocking.** API probes used the browser context's request client (same cookies). Script kept in the session scratchpad, never committed |
| Customer identity | one throwaway `accept-payment-<ts>@example.com` (real register with the Turnstile test token, real verify-email with the token read only from that account's `email_outbox` row). Random password, never printed or stored. No admin session was needed |
| Products / settings | seeded `dragon` only **read**. No setting changed |
| Data left behind | **3 orders**, none waiting on payment: `B3D-5J17ZHHV` online, 1 attempt, **paid**, `in_progress`; `B3D-33BZ19KN` online, 3 attempts (failed, failed, **paid**), `in_progress`; `B3D-K8Y1QEXQ` cash/delivery `in_progress`, unpaid, no payment row. One address. Empty cart |

**Overall: PASS, 21/21.** No app defect found.

### Current contract (as implemented)

- **Retry route:** `POST /api/v1/me/orders/{order_id}/payments`. The order's owner, **verified email**, `X-CSRF-Token`, required `Idempotency-Key` (`^[A-Za-z0-9._:-]{8,255}$`). Body `PaymentRetryRequest` (`extra="forbid"`): only `payment_provider?` (1-32); the frontend sends `{}` (the server reuses the previous attempt's provider). The amount is always the order total. `201 PaymentRetryRead`: `order {id, order_number, status, total_cents, currency, hold_expires_at}` and `payment {id, status, provider, amount_cents, currency, redirect_url|null}`. 10 retries per user per hour (Redis outage refuses with 503).
- **Idempotency:** scope `payment_retry:{order_id}` per user, kept 24 h. The `201` and the `502` are replayed for the same key (`Idempotent-Replayed: true`); same key + different body → `409 IDEMPOTENCY_KEY_CONFLICT`; a running claim → `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` (`Retry-After: 2`); every other refusal rolls the claim back.
- **Problems:** `409 PAYMENT_ALREADY_ACTIVE` (`payment_id`, `payment_status`, `redirect_url`, null while `processing`); `409 INVALID_STATE_TRANSITION` with `reason` = `cash_order` | `order_cancelled` | `order_not_payable` | `checkout_hold_expired` | `offer_checkout_expired`; `409 IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS`; `422 PAYMENT_METHOD_NOT_ALLOWED` (`reason`), `422 VALIDATION_ERROR`; `429 RATE_LIMITED`; `502 PAYMENT_PROVIDER_UNAVAILABLE` (`order_id`, `order_number`; the attempt is failed, the order stays payable); `503 ONLINE_PAYMENT_UNAVAILABLE`; plus `401 AUTH_REQUIRED`, `403 CSRF_INVALID`, `403 EMAIL_VERIFICATION_REQUIRED`, `404 NOT_FOUND`. **There is no `PAYMENT_NOT_RETRYABLE` code.**
- **Payment status** (`OrderPaymentRead.status`, a plain string; backend `PaymentStatus`): `pending`, `processing`, `paid`, `partially_refunded`, `refunded`, `failed`, `expired`. Live attempt = `pending` | `processing`.
- **Customer payment read:** none of its own. `GET /me/orders/{id}`: `payment` (the live or paid attempt, else the latest), `can_retry_payment` (advisory: retry rules **and** no live attempt **and**, for an offer order, its window still open), `hold_expires_at` (`max(placed_at, latest attempt) + checkout_hold_period`, only while online, `pending_payment`, not cancelled).
- **Transitions seen:** checkout online → order `pending_payment`, payment `pending`. Mock `paid` + webhook → payment `paid`, order `in_progress`, `can_retry_payment` false, `hold_expires_at` null. Mock `failed` + webhook inside the hold → payment `failed`, order **still `pending_payment`**, `can_retry_payment` true. A retry → a new `pending` attempt and a later `hold_expires_at`. An unpaid order is released (cancelled) only by the `release_stale_checkouts` job after the hold, and only when the provider answers `failed`/`expired`; not provoked here.
- **Mock lifecycle:** `redirect_url` = `{FRONTEND_BASE_URL}/checkout/return?order=<order_number>`. There is no provider page: the mock state changes only through `mock_pay.py` (no HTTP route can change it).

### Frontend behaviour

- **Source of truth:** `/account/orders/[id]` through `orderKeys.detail(id)`; no separate payment cache. Every retry answer invalidates the `orders` root.
- **Bounded polling** (`usePolledOrder`): on only while the server reports online + `pending_payment` + not cancelled + payment `pending`/`processing`. Every 3 s for 30 s, then every 10 s, stopping 3 min after the window opened, or on the first response that is terminal. Paused while the tab is hidden (TanStack default), refetch on focus. One page, one interval. After the bound: "We haven't received a confirmation…" + **Check again** (re-reads now, opens one new window). Never for cash or for an order without a payment row.
- **Retry payment** (`useRetryPayment`): shown only while `can_retry_payment === true` (never for cash). One press = one logical attempt = one key, kept only across **uncertain** outcomes (network, timeout, unparseable body, 5xx other than the 502, `IDEMPOTENCY_REQUEST_IN_PROGRESS`; the silent refresh-and-retry resends inside the same call). Any definitive answer retires it. A separate tracker from checkout's, memory only, never shown. Ref guard + disabled button against double submits.
- **Redirect safety:** `redirect_url` (and `PAYMENT_ALREADY_ACTIVE`'s) is followed exactly as given, only if absolute http(s); never parsed, and nothing local is marked paid. `PAYMENT_ALREADY_ACTIVE` with a URL offers **Continue to payment**, which the customer has to press.
- **Hold countdown:** from the server's `hold_expires_at`, presentation only. At zero it re-reads the order once and says only that the order *may* be released.
- **States:** awaiting, processing, paid, failed, expired, refunded, partially refunded, each with its own copy; any other value → "Status unavailable". Refund rows stay in the Refunds section; no refund action.
- **Return page:** unchanged in substance: "Your payment hasn't been confirmed yet. Check your orders for the latest status." It reads nothing from the URL and links to `/account/orders`.

### Results

| Scenario | Result | Evidence |
|---|---|---|
| Contract: pending online order detail | **PASS** | `pending_payment`, payment `pending`/`mock`, `can_retry_payment: false` (live attempt), `hold_expires_at` set |
| Contract: checkout `redirect_url` (mock) | **PASS** | `{FRONTEND}/checkout/return?order=<number>` |
| Retry while an attempt is live | **PASS** | `409 PAYMENT_ALREADY_ACTIVE`, `payment_status: pending`, `redirect_url` present; still 1 payment row |
| Pending online in the UI | **PASS** | "Awaiting payment", "Checking for a payment update…", countdown; no Retry (server says false); no "Paid" |
| Real mock-provider completion | **PASS** | `mock_pay.py <payment> paid --send-to` → "webhook answered 200" |
| Server-side payment + order update | **PASS** | DB payment `paid`, order `in_progress`; detail `can_retry_payment: false`, `hold_expires_at: null` |
| Bounded polling sees the new state | **PASS** | UI showed "Paid" and "Your payment has been confirmed." 4.9 s after `mock_pay`, with no reload (2 re-reads) |
| Polling stops on a terminal state | **PASS** | 0 detail GETs in the 8 s after "Paid" |
| Retryable failed payment (real) | **PASS** | mock `failed` + webhook 200 → payment `failed`, order still `pending_payment`, `can_retry_payment: true` |
| Failed payment in the UI | **PASS** | "Payment failed", "Your last payment attempt didn't go through.", Retry payment shown; no polling (terminal attempt) |
| POST payment retry from the UI | **PASS** | one POST → `201`; body `{}`; key matches the pattern; `X-CSRF-Token` = cookie; payment rows 1 → 2 |
| Redirect handling | **PASS** | browser followed `redirect_url` exactly → `/checkout/return?order=<number>` |
| Return page remains truthful | **PASS** | no success/failure claim; links to `/account/orders` |
| Retry restarts the hold (server) | **PASS** | new attempt `pending`; `hold_expires_at` later; `can_retry_payment: false` while live |
| Idempotency-Key replay | **PASS** | the UI's key + same body → `201 Idempotent-Replayed: true`, same payment id, still 2 rows |
| Same key, different body | **PASS** | `{payment_provider: "mock"}` under the UI's key → `409 IDEMPOTENCY_KEY_CONFLICT` |
| CSRF_INVALID | **PASS** | stale cookie → UI POST `403`; "Unable to verify your session…"; no redirect; no new row |
| Session refresh during retry | **PASS** | access cookie removed → `401` → silent refresh → resend with the **same** key → `201`; the key differs from the refused CSRF attempt (a new logical attempt); rows 3 |
| Retried payment completes | **PASS** | third attempt paid via mock webhook; order `in_progress` |
| Cash order has no retry | **PASS** | server `can_retry_payment: false`, `payment: null`, `hold_expires_at: null`; UI: no button, countdown or polling (0 re-reads in 5 s); API retry → `409 INVALID_STATE_TRANSITION` `reason: cash_order` |
| No page errors | **PASS** | none |

### Not tested against the real backend (and why)

- **`expired` payment and a released (cancelled) order:** the release needs the hold to pass (30 min) and the 5-minute job; `mock_pay expired` was not run so as not to add another order. Both states are covered by unit and mocked E2E tests.
- **`processing`:** `mock_pay processing` works the same way as `paid`/`failed`; not run, to keep the run to three orders. Covered by unit and mocked E2E.
- **`refunded` / `partially_refunded`:** need an admin refund (VS-030), which is a later phase. Presentation covered by unit and mocked E2E.
- **`checkout_hold_expired`, `order_cancelled`, `offer_checkout_expired` refusals, `502 PAYMENT_PROVIDER_UNAVAILABLE`, `503 ONLINE_PAYMENT_UNAVAILABLE`, `IDEMPOTENCY_REQUEST_IN_PROGRESS`, `429 RATE_LIMITED`:** need a 30-minute wait, an offer, a provider outage, an env change, a concurrent request or 10+ retries. Not provoked; covered by unit tests and mocked E2E (refusal, 502).
- **Hold countdown reaching zero:** 30 minutes against the real backend; covered by unit and mocked E2E.
- **`PAYMENT_ALREADY_ACTIVE` → Continue to payment in the UI:** the UI shows Retry only when `can_retry_payment` is true, and the real backend makes it false while an attempt is live, so the UI cannot reach that answer against a consistent backend. The real `409` body was verified by API; the UI path is covered by mocked E2E.

### Defects found and fixed

- None in the app during the real run.
- During development (test-only): two mocked E2E locators matched the header's transient "Loading…" status region as well as the return page's own (`getByRole("status")` strict-mode violation, the same pattern as phase 5D); and the mocked hold-countdown test depended on dev-server compile time. Both fixed in the spec before `d1ccb07`.

### Backend observations (not changed; recorded for the backend team)

- **Retry eligibility vs. `hold_expires_at`.** `retry_refusal` refuses at `placed_at + checkout_hold_period`, while `hold_expires_at` is measured from the **latest attempt** (`docs/payment-recovery.md`: "a retry restarts it"). After a retry, the order page can show time left while a further retry is already refused with `checkout_hold_expired`. The frontend follows `can_retry_payment` (computed with the same rule), so it never offers a retry the server will refuse, but the countdown is about the release, not about retry eligibility.
- **No customer resume URL** for a `pending` attempt (see `FRONTEND-VERTICAL-SLICE-PLAN.md` §17).

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **2219/2219** (235 files) |
| `npm run build` | pass (`/account/orders/[id]` dynamic, `/checkout/return` static) |
| `npm run test:e2e` | **125/125** in the one full run (109 + 16 new in `e2e/payment-result.spec.ts`; `account-orders.spec.ts` updated in place). The known readiness-banner test passed in this run |

### Remaining gaps

- `/checkout/return` cannot open the order: its URL carries an order **number** and there is no customer lookup by number. It stays a neutral handoff to the orders list (§17).
- A customer who leaves the provider page while the attempt is still `pending` cannot resume it from the order page: `can_retry_payment` is false and the detail has no `redirect_url` (§17). With the mock provider this changes nothing.
- The live provider (VS-032) is not built: online payment runs against the mock only. Its return parameters and timing are unknown; the polling bound (3 min) may need tuning then.
- The old speculative `src/lib/payment/*` and `src/components/payment/*` (written before the real contract, e.g. a `PaymentStatus` without the refund values) are not used by the customer flow. Only the unmounted `src/lib/admin/adminPaymentModel.ts` imports from them; reconcile both with the real admin schemas in the admin-payments phase.
- FVS-031 (cancel, confirm receipt, report problem), admin orders/payments and refunds are not started.

---

## Phase 5E: Customer Orders (FVS-029), 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `eb2ce09` (order contract, adapters, labels, queries, views), `f6848b3` (`/account/orders`, `/account/orders/[id]`, nav), `34e2d7a` (user-scoped caches dropped before sign-in), `c4ea3fe` (checkout → order links, STL copy fix), `5d42afb` (mocked E2E). All committed before the run; this document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json` is identical to `docs/backend-handoff/openapi.json` after key-sorted comparison (every schema and path) |
| Runtime | Docker Compose backend on :8000 (`PAYMENT_PROVIDER=mock`). `npm run dev` on :3000 proxying to :8000, started only for this run and stopped after it. No media server |
| Method | real Edge browser through Playwright against the real frontend and backend. **No route mocking.** API probes used the browser context's request client (same cookies). Temporary scripts kept in the session scratchpad, never committed |
| Customer identity | throwaway `accept-orders-a-<ts>`, `accept-orders-b-<ts>` and `accept-orders-c-<ts>@example.com` (real register with the Turnstile test token, real verify-email with the token read only from that account's `email_outbox` row). Random passwords, never printed or stored. A and B were re-entered once through the real password-reset flow (below) |
| Admin | credentials read only from `%USERPROFILE%\.bekaa3d\dev-admin.json` (real login + TOTP), used only for `pickup_address` / `pickup_hours` |
| Products | seeded `dragon`, `moon-lamp`, `dragon-stl` only **read** and added to A's cart. None modified |
| Settings | `pickup_address` / `pickup_hours` set for the pickup order, then **restored to `null`** (verified in the DB). The first restore ran from the script's abort path as a direct DB update; the second, after the resumed run, through the admin API |
| Data left behind | **2 orders** on A (the minimum for cash + online): `B3D-833JEPMQ` cash/delivery/physical `in_progress`, unpaid, no payment row; `B3D-VCKV1V51` online (mock)/pickup/mixed physical+STL `pending_payment`, payment `pending`, never paid (the release job will expire it). B and C: no orders. One address on A. Empty carts |

**Overall: PASS, 22/22.** The run was split in two by an acceptance-script bug (see below). Two checks of the resumed run first reported FAIL because of script bugs and were re-verified (one by a targeted probe, one by later steps of the same run). The run found no app defect.

### Current contract (as implemented)

- `GET /api/v1/me/orders`: session cookie only (no verified email, no rate limit, no CSRF). Query `status?` (`OrderStatus`), `placed_after?` (inclusive), `placed_before?` (exclusive; both need a time zone or it is `422`), `cursor?` (opaque; malformed → `422`), `limit` 1-100 (default 20). Newest `placed_at` first, then `id` desc. `200 OrderPage {items: OrderSummaryRead[], next_cursor: string|null}`; no total. Anonymous: `401 AUTH_REQUIRED`.
- `OrderSummaryRead`: `id`, `order_number`, `status`, `payment_method` (`online`|`cash`), `fulfillment_method` (`delivery`|`pickup`|null = STL-only), `payment_due` (an unpaid cash order), `amount_due` (`PriceRead|null`: the live total of non-cancelled lines while `payment_due`), `total`, `placed_at`. **No lines, no payment status.**
- `GET /api/v1/me/orders/{order_id}` (`uuid`; anything else `422`): `200 OrderDetailRead`. `404 NOT_FOUND` for an unknown id **and** for another customer's order, with identical bodies apart from `instance` and `request_id`.
- `OrderDetailRead`: `id`, `order_number`, `source` (`cart`|`offer`), `status`, `fulfillment_method|null`, `payment_method`, `payment_due`, `amount_due|null`, `can_cancel`, `can_retry_payment` (advisory), `hold_expires_at|null` (unpaid online), `subtotal`, `tax`, `total`, `delivery_address|null` (snapshot with every field nullable: `recipient_name`, `governorate`, `city`, `area`, `street`, `landmark_notes`; delivery only), `contact_phone|null` (physical), `delivery_fee_note|null` (a fixed server sentence, delivery only), `estimated_dispatch_at|null`, `placed_at`, `completed_at|null`, `cancelled_at|null`, `customer_note|null`, `lines[]`, `payment|null` (`{status: string, provider, amount}`; **null while a cash order is unpaid**), `status_history[]` (`{order_item_id|null, from_status|null, to_status, at}`, oldest first), `refunds[]` (optional; `{kind: admin|cancellation|late_capture, status: processing|refunded, amount, created_at}`). No pickup snapshot: the pickup location comes from public settings.
- `OrderLineRead`: `id`, `product_id`, `product_type` (`physical`|`stl`), `name` (as bought), `image_url|null`, `unit_price`, `quantity`, `line_total`, `fulfillment_status` (`OrderItemStatus`; never `in_production` to a customer: printing reads `pending`), `fulfilled_at|null` (STL: when emailed), `cancelled_at|null`, `receipt_confirmed_at|null`, `problem_reported_at|null` (physical only).
- Enums: `OrderStatus` = pending_payment, in_progress, completed, partially_refunded, refunded, cancelled. `OrderItemStatus` = pending, awaiting_delivery, in_production, ready_to_ship, shipped, delivered, returned, ready_for_pickup, picked_up, cancelled, refunded. Payment status (backend `PaymentStatus`, a plain string on the wire) = pending, processing, paid, partially_refunded, refunded, failed, expired.
- Actions recorded for later phases and **not mounted**: `POST /me/orders/{id}/cancel` (FVS-031; order-level, `CustomerOrderCancelRequest`), `POST …/confirm-receipt` and `POST …/report-problem` (FVS-031; verified email + CSRF; `409 INVALID_STATE_TRANSITION` with `reason: no_delivered_line`), `POST …/payments` (FVS-027 retry; `Idempotency-Key` required).

### Results

| Check | Result | Evidence |
|---|---|---|
| Anonymous `/account/orders` | **PASS** | → `/login?returnTo=%2Faccount%2Forders`; API `401 AUTH_REQUIRED` |
| Empty history | **PASS** | new verified account: "You haven't placed any orders yet." + Browse the shop |
| Checkout → View order (cash) | **PASS** | real UI checkout (cash, delivery, 2 × dragon); the confirmation's "View order" → `/account/orders/{id}` → heading "Order B3D-833JEPMQ" |
| Cash representation | **PASS** | server `in_progress`/cash/3600, **0 payment rows**; UI "Payment due in cash to the courier on delivery: $36.00. This order hasn't been paid yet."; no payment-status row, no "Paid" |
| Delivery order | **PASS** | recipient, street, "Zahle, Beqaa", landmark, contact phone, estimated ready date; frontend courier-fee copy (the server note is not echoed) |
| Physical line | **PASS** | "Articulated Dragon $36.00 · Physical item · Qty 2 × $18.00 · Received" |
| No actions mounted | **PASS** | server `can_cancel: true`; 0 buttons inside the order |
| Detail after reload | **PASS** | the same order re-rendered from `GET /me/orders/{id}` |
| History after creating orders | **PASS** | `/checkout/return` → "View your orders" → `["Order B3D-VCKV1V51", "Order B3D-833JEPMQ"]` (newest first) |
| History cards | **PASS** | online: "Awaiting payment · $31.00 · Online payment · Pickup", no "paid"; cash: "In progress · $36.00 · Cash · Delivery · Payment due in cash: $36.00" |
| History after reload | **PASS** (re-verified) | see "Script bugs": two later full page loads of `/account/orders` in the same run rendered both orders |
| Pending online payment | **PASS** | server `pending_payment`, payment `pending`/`mock`; UI payment status "Awaiting payment", "This order hasn't been confirmed as paid…", "may be released after …" (`hold_expires_at`); no "Paid", no retry or redirect control |
| Pickup order | **PASS** | "You'll collect this order from us." + the current pickup location/hours from public settings + contact phone; no courier-fee copy |
| STL line (manual delivery) | **PASS** | server STL line `pending`, `fulfilled_at: null` (unpaid order); UI "STL file, sent by email" + "We'll email this file to you once your payment is confirmed."; no "download" text, link or button anywhere |
| Mixed order | **PASS** | moon lamp (physical) + dragon STL in one order |
| Unknown order | **PASS** | random UUID → API `404 NOT_FOUND` → "Order not found"; a malformed id → the same page with **0** API calls |
| Session refresh | **PASS** | `access_token` cookie removed → the page load refreshed the session (new `access_token`) and rendered the order (order request `200`) |
| 375px | **PASS** | horizontal overflow 0 px on history and detail |
| Keyboard | **PASS** | Tab reached "Order B3D-833JEPMQ" (13 presses); Enter opened the detail |
| Logout → relogin isolation | **PASS** | same tab: A logged out from the account nav, B logged in → empty history; none of A's order numbers rendered |
| Another customer's order | **PASS** (re-verified) | C → A's order id: API `404 NOT_FOUND`, body identical to an unknown id except `instance`/`request_id`; UI "Order not found", A's order number not rendered |
| Runtime errors | **PASS** | no page errors |

### Script bugs (not app defects)

1. The first run aborted right after placing the online order: a status query used `coalesce(enum, '')`, which PostgreSQL refuses. The abort path restored the pickup settings in the DB. The first 8 checks had passed. The rest was **resumed on the same accounts and the same two orders** (no new orders). A and B were re-entered through the real `POST /auth/password-reset/request` + `/confirm`, with the token read from that account's outbox row.
2. "History after reload" counted the order links straight after `reload()`, before the list rendered. The two later steps of the same run (375 px and keyboard) each loaded `/account/orders` from scratch and found the orders, which is the same check. Repeating it directly needed another reset, which was refused: a probe re-requested resets inside the 2-minute per-account cooldown and used up the per-IP limit (5 per hour).
3. "Another customer's order" compared whole problem bodies, but `request_id` differs per request (and `instance` contains the id). Re-verified with a fresh customer C that places no orders: the bodies are identical apart from those two fields.

Not run live, and why (all covered by unit and mocked E2E):

- **STL emailed** (`delivered` + `fulfilled_at`): needs a paid STL order and an admin "mark sent". Paying the mock payment belongs to FVS-027. Not done, so the mock payment stays untouched.
- **A paid online payment row, refunds, cancelled/completed orders, receipt/problem timestamps, line entries in `status_history`**: need payment, admin fulfilment, refunds or VS-029b actions. Out of scope for a read phase.
- **Load more against the real backend**: needs more than 20 orders on one account (the UI does not expose `limit`). The mocked E2E follows the real cursor contract. Not provoked, to avoid creating orders.
- **History `status` / date filters**: not used by the phase 5E UI.

### Defects found and fixed

14. **The old customer order frontend predated the backend** (fixed in `eb2ce09`, `f6848b3`). Audit result:
    - `lib/orders/orderModel.ts`: **contract-drifted**. Label-only shapes (`statusLabel`, `paymentStatusLabel`, `productDisplayName`) with no fulfillment, payment, address, phone, history or refund fields. Rewritten against `OrderSummaryRead` / `OrderDetailRead` with an adapter. The order enums now live in `lib/orders/orderTypes.ts`, and `checkoutTypes.ts` re-exports them.
    - `lib/orders/orderKeys.ts`: **reusable concept, drifted key** (keyed on invented `status/dateFrom/dateTo/cursor` filters). Rewritten; `["orders"]` added to the user-scoped roots.
    - `lib/orders/orderExceptionModel.ts`, `components/account/CancellableOrderLine`, `CancelOrderLineButton`: **speculative**. A per-line customer cancel the backend does not have (customer cancel is order-level, FVS-031). Removed.
    - `components/account/OrderList`: **speculative**. Status/date filters and a table bound to the label-only model. Replaced by `OrderHistoryList`.
    - `components/account/OrderDetail`: **contract-drifted**. Showed the raw id as the heading, with no payment or fulfillment. Replaced by `OrderDetailView`.
    - `components/account/OrderLineItem`, `OrderSummaryDisplay`: **used by the unmounted admin order screens**. Moved under `components/admin/` (`AdminOrderLineItem`, `AdminOrderSummaryDisplay`) with their legacy types inlined into `adminOrderModel.ts`, flagged for a rebuild against `AdminOrderDetail` in the admin-orders phase. A new customer `OrderLineItem` renders the real line.
    - `components/account/StatusTimeline`, `lib/orders/orderActionModel.ts`: **reusable**, kept unchanged (the timeline now renders `status_history`).
15. **A user switch without logout could show cached data** (`34e2d7a`). User-scoped caches were dropped only on logout. If a session expired and a different user then signed in in the same tab, the previous user's cached orders, cart or addresses could show briefly. The login page now drops every user-scoped root before reading the new session.
16. **Checkout copy promised STL downloads** (`c4ea3fe`). "You'll be able to download them…" and "STL file (digital download)" contradicted ADR-019 (an administrator emails each paid STL). Now "Our team emails each file to you once your payment is confirmed." and "STL file (sent by email)".
- The checkout confirmation and the `PAYMENT_PROVIDER_UNAVAILABLE` state had no way to reach the order (`c4ea3fe`). Both now link to `/account/orders/{id}` (`order.id`, or the problem's `order_id`). `/checkout/return` links to the history. Placing an order invalidates the orders queries.
- The account nav marked nothing active on `/account/orders/{id}` (`f6848b3`). Sub-routes now keep their section active.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **2119/2119** (229 files) |
| `npm run build` | pass (`/account/orders` static, `/account/orders/[id]` dynamic) |
| `npm run test:e2e` | **108/109** in the one full run (97 + 12 new in `e2e/account-orders.spec.ts`; `checkout.spec.ts` extended in place). The one failure was the existing `smoke.spec.ts` readiness-banner test, which counts transient `role="status"` regions and then reads one that has already gone. It passed 3/3 when re-run alone (`--repeat-each=3`). Unrelated to this phase; left as is |

### Remaining gaps

- **FVS-027**: no payment verification, polling or retry. A pending online order shows the server's `pending` state only; `can_retry_payment` is ignored on purpose.
- **FVS-031**: no cancel, confirm receipt or report problem, even when `can_cancel` is true or a line is delivered.
- `/checkout/return` links to the history, not to the order. Its URL carries an order **number**, and there is no customer lookup by number. The new order is first in the history (newest first).
- The history has no line summary: `OrderSummaryRead` has no lines (they are on the detail page).
- The pickup location on an order is the **current** public setting; the order has no pickup snapshot. If the setting changes, old orders show the new location.
- Dates are shown in the viewer's time zone (`en-GB` format).
- The admin order screens still use the legacy speculative shapes (moved, not rebuilt).
- The smoke readiness-banner test is timing-sensitive under full parallel load (pre-existing).

---

## Phase 5D: Checkout (FVS-026), 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `1398de1` (POST headers, Problem array reader), `563b0b7` (checkout contract, idempotency, errors), `5a90786` (`/checkout`, `/checkout/return`), `57eb95c` (cart CTA), `2124276` (mocked E2E). All committed before the run; this document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json` is identical to `docs/backend-handoff/openapi.json` after key-sorted comparison (211 schemas), including `CheckoutRequest`, `CheckoutRead` and the required `Idempotency-Key` header parameter |
| Runtime | Docker Compose backend on :8000 (`PAYMENT_PROVIDER=mock`). `npm run dev` on :3000 proxying to :8000, started only for this run and stopped after it. No media server |
| Method | real Edge browser through Playwright against the real frontend and backend. **No route mocking.** UI requests were recorded from the page; API probes used the context's request client (same cookies, never counted as UI requests). Temporary scripts kept in the session scratchpad, never committed |
| Customer identity | throwaway `accept-checkout-<ts>@example.com` and `accept-checkout-cash-<ts>@example.com` accounts (real register with the Turnstile test token, real verify-email with the token read only from that account's `email_outbox` row). Random passwords, never printed or stored. A random Lebanese phone per account |
| Admin | credentials read only from `%USERPROFILE%\.bekaa3d\dev-admin.json` (real login + TOTP), used only for disposable data and two settings |
| Products | seeded `dragon`, `moon-lamp`, `dragon-stl`, `phone-stand-stl` only **read** and added to throwaway carts. One disposable product `acceptance-checkout-<ts>` (physical, $15.00) was created for the price-change and refused-line cases, then **deleted** (`204`) |
| Settings | `pickup_address` / `pickup_hours` set for the pickup case, then **restored to `null`** (verified in the DB) |
| Data left behind | 5 orders on the two throwaway accounts: 3 online `pending_payment` (mock payment `pending`, never paid; the release job will expire them), 2 cash `in_progress` (unpaid). Empty carts. One address per account |

**Overall: PASS, 28/28.** The first run reported 27/28. The one FAIL was an acceptance-script bug, not an app defect: the cash-success check compared the request body with an order-sensitive `JSON.stringify`. That scenario was re-run once on a fresh account with an order-insensitive comparison and evidence read from the page, and passed (one extra order).

### Current contract (as implemented)

`POST /api/v1/checkout`: verified session (`403 EMAIL_VERIFICATION_REQUIRED` otherwise), `X-CSRF-Token`, required header `Idempotency-Key` matching `^[A-Za-z0-9._:-]{8,255}$`. Rate limit 30/hour/user (a replay counts).

Request (`extra="forbid"`, no amount or total ever): `payment_method` (`online`|`cash`), `payment_provider?` (omitted by the frontend: the single configured provider is used), `fulfillment_method?` (`delivery`|`pickup`), `address_id?`, `contact_phone?` (≤ 32, Lebanese, normalised to E.164), `customer_note?` (≤ 1000), `accept_terms: true`, `accept_digital_final_sale?: true` (required while an STL line remains), `accept_cash_terms?: true` (required for cash), `accepted_price_changes?: [{product_id, amount_cents, currency}]` (≤ 50, each the exact live price).

Fulfillment matrix (on the lines kept after already-owned STLs are dropped): STL-only → no fulfillment fields at all; delivery → `address_id` required and `contact_phone` **absent** (the address phone is used); pickup → `contact_phone` required and `address_id` **absent**, and only when `pickup_address` is set. Cash needs every kept line physical. No shipping fee, zone or threshold (ADR-024).

`201 CheckoutRead`: `order` (`id`, `order_number`, `source`, `status`, `payment_method`, `fulfillment_method|null`, `subtotal`, `tax`, `total`, `placed_at`, `estimated_dispatch_at|null`, `delivery_fee_note|null`, `delivery_address|null` snapshot without phone, `payment_due`, `amount_due|null`, `lines[]` with `unit_price`, `quantity`, `line_total`, `fulfillment_status`), `payment` (`id`, `status`, `provider`, `redirect_url|null`; **null for cash**), `dropped_lines[{product_id, reason: "already_owned"}]`. Online: order `pending_payment`, payment `pending`, `redirect_url` = `{FRONTEND_BASE_URL}/checkout/return?order=<number>` for the mock. Cash: order `in_progress`, `payment_due: true`, `amount_due` = total.

Idempotency: same key + same body replays the stored `201` (or the post-commit `502`) with `Idempotent-Replayed: true`; same key + different body → `409 IDEMPOTENCY_KEY_CONFLICT`; a running claim → `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` (`order_id`, `order_number`, `Retry-After: 2`); every other refusal rolls the claim back and leaves cart, orders and key untouched. Kept 24 h. The frontend binds one key to one exact body (in memory only): the same body reuses it, any change mints a new one, and a placed order retires it.

Problem codes: `409 CART_EMPTY` (`dropped_lines`), `409 CART_PRICE_CHANGED` (`price_changes[{product_id, old_amount_cents, new_amount_cents, currency}]`), `409 PRODUCT_ALREADY_OWNED` (`product_ids`), `422 PRODUCT_NOT_PURCHASABLE` / `QUANTITY_EXCEEDS_LIMIT` (`lines[{product_id, reason, max_quantity?}]`), `422 INVALID_FULFILLMENT`, `422 PAYMENT_METHOD_NOT_ALLOWED` (`reason`: `cash_requires_physical`, `cash_disabled`, `zero_total`, `provider_not_configured`, `provider_required`, `provider_not_applicable`), `422 CASH_PAYMENT_LIMIT_REACHED` (`reason: order_total`), `422 CASH_NOT_AVAILABLE` (no reason, by design), `422 VALIDATION_ERROR`, `429 RATE_LIMITED`, `502 PAYMENT_PROVIDER_UNAVAILABLE` (order exists unpaid; `order_id`, `order_number`), `503 ORDERS_PAUSED`, `503 ONLINE_PAYMENT_UNAVAILABLE`, plus `401 AUTH_REQUIRED`, `403 CSRF_INVALID`, `403 EMAIL_VERIFICATION_REQUIRED`.

### Results

| Check | Result | Evidence |
|---|---|---|
| Anonymous `/checkout` | **PASS** | → `/login?returnTo=%2Fcheckout` |
| Unverified account | **PASS** | guidance + "Resend the verification email", no form; real POST → `403 EMAIL_VERIFICATION_REQUIRED` |
| Empty cart | **PASS** | empty state, no form, no POST |
| `Idempotency-Key` required + pattern | **PASS** | missing → `422 VALIDATION_ERROR` (`loc ["header","Idempotency-Key"]`); `"short"` → `422` |
| CSRF (API) | **PASS** | wrong token → `403 CSRF_INVALID` |
| Request contract | **PASS** | a client `total` → `422 VALIDATION_ERROR`; delivery + `contact_phone` → `422 INVALID_FULFILLMENT`; pickup with no `pickup_address` → `422 INVALID_FULFILLMENT` |
| Refusals create nothing | **PASS** | orders 0 → 0 after every refusal above; cart unchanged |
| `CSRF_INVALID` in the UI | **PASS** | stale `csrf_token` cookie → UI POST `403` → "Unable to verify your session…"; cart kept |
| Refused line (real) | **PASS** | disposable product made unavailable after `/checkout` loaded → UI POST `422 PRODUCT_NOT_PURCHASABLE` → notice names it "is currently unavailable"; cart refetched to its blocked state; line kept |
| Real `CART_PRICE_CHANGED` | **PASS** | disposable product $15.00 → $17.00 after it was added → `409`; banner shows $15.00 → $17.00; Place order disabled until accepted |
| Explicit accepted-price retry | **PASS** | "Accept new prices" sent nothing by itself; the next Place order sent `accepted_price_changes: [{product_id, 1700, "USD"}]` under a **new** key → `201` |
| Mock online checkout | **PASS** | `201`, payment `pending` / `mock`; browser followed `redirect_url` to `/checkout/return?order=…`; the page claims no outcome |
| Online order state (server) | **PASS** | DB order/payment `pending_payment/pending`; nothing marked paid client-side |
| Cart cleared (online) | **PASS** | `GET /cart` → `items: []` |
| Cash refused for a mixed cart | **PASS** | UI cash radio disabled with the reason; real POST → `422 PAYMENT_METHOD_NOT_ALLOWED` `cash_requires_physical` |
| Mixed cart + pickup + online | **PASS** | body `{online, pickup, contact_phone, accept_terms, accept_digital_final_sale}`, no `address_id` → `201`; pickup address/hours shown from public settings; server stored `pickup` with an E.164 phone and no address |
| Cash above `cash_max_order_total` | **PASS** | 5 × $18 + $24 = $114 live → real `422 CASH_PAYMENT_LIMIT_REACHED`; copy names the public $100.00 limit; cart kept |
| Cash checkout (physical, delivery) | **PASS** (re-run) | body exactly `{payment_method: cash, fulfillment_method: delivery, address_id, accept_terms, accept_cash_terms}` → `201`; "Order placed", "Payment due in cash to the courier on delivery: $36.00. This order hasn't been paid yet."; no redirect; server `in_progress/cash/3600/delivery`, 0 payment rows |
| Cart + header cleared (cash) | **PASS** | `GET /cart` → `[]`; header back to "Cart" with no count; one new order |
| `Idempotency-Key` on every UI POST | **PASS** | 7 UI POSTs in run 1, each with a pattern-valid key and `X-CSRF-Token` |
| Real replay | **PASS** | the UI's key + body re-sent → `201`, `Idempotent-Replayed: true`, the same order number; no new order |
| Same key + different body | **PASS** | → `409 IDEMPOTENCY_KEY_CONFLICT` |
| Reload after success | **PASS** | `/checkout` shows the empty-cart state; nothing resubmitted; order count unchanged |
| Cash rejected (open cash order) | **PASS** | dev `cash_max_open_orders = 1`: a second cash order → real `422 CASH_NOT_AVAILABLE` (no reason); safe copy; cart kept; no order |
| STL-only online | **PASS** | no fulfillment fields; body `{online, accept_terms, accept_digital_final_sale}` → `201` → redirect |
| Session refresh during checkout | **PASS** | `access_token` removed → POST `401` → refresh → retried once with the **same** key and body → `201` |
| 375px | **PASS** | no horizontal overflow on `/checkout` |
| Runtime errors | **PASS** | no page errors |

Not run live, and why (all covered by unit and mocked E2E):

- `dropped_lines` on a successful checkout and `CART_EMPTY` with `dropped_lines`: needs an STL to become **owned** after it was added to the cart. The only way is a paid order of that STL outside this cart (an offer checkout plus a simulated mock payment), which is out of scope and creates more persistent data.
- `PRODUCT_ALREADY_OWNED` at checkout, `IDEMPOTENCY_REQUEST_IN_PROGRESS`, `502 PAYMENT_PROVIDER_UNAVAILABLE`, `503 ORDERS_PAUSED`, `503 ONLINE_PAYMENT_UNAVAILABLE`, `429 RATE_LIMITED`: need concurrent requests, a provider outage, a backend env change, a kill-switch toggle on a shared dev DB, or 30+ checkouts. Not provoked, to avoid excess orders and environment changes.
- An unknown outcome (timeout / dropped connection) with a same-key retry: covered by the mocked E2E (the fake places the order, drops the response, and the retry is replayed); the real replay semantics it relies on were verified above.
- Keyboard-only flow: mocked E2E only.
- Paying the mock payment: belongs to FVS-027 (payment result).

### Defects found and fixed

13. **The old checkout code predated the backend** (fixed in `563b0b7`, `5a90786`). Audit result:
    - `checkoutModels.ts`: **contract-drifted**. It had one digital consent per product (the backend has a single boolean) and a speculative conflict shape. Removed.
    - `useCheckoutAttempt.ts`: **speculative**. One key per mount, not per body, so a changed body could reuse a key (a guaranteed `IDEMPOTENCY_KEY_CONFLICT`). Replaced by `checkoutIdempotency.ts`.
    - `DeliveryMethodSelector`: **contract-drifted**. Addresses and pickup were in one radio group, with no contact phone and no pickup details. Replaced by `FulfillmentSection`.
    - `CartConflictNotice`: **speculative** (caller-supplied messages, invented kinds). Replaced by `CheckoutLineIssues`.
    - `CheckoutStepper`: **obsolete** (single-page checkout). Removed.
    - `ConsentCheckboxGroup`, `PriceChangeConflictBanner`: **reusable concept, contract-drifted props**. Rewritten.
    - `OrderSummary`, `CheckoutDisabledBanner`: **reusable**, kept unchanged.
    - `useIdempotencyAttempt` (shared): left in place for FVS-032, now unused by checkout.
- The `/cart` CTA said "Online checkout isn't available yet", and a price change alone read as blocking. It now links to `/checkout` only when the cart can proceed (`57eb95c`).
- `apiClient.post` could not send an `Idempotency-Key` header (`1398de1`).
- Mocked E2E locator ambiguity (`getByRole("status")` matched two regions on `/checkout/return`): test-only fix before `2124276`.
- Acceptance-script bug (above): not an app defect.

No integration defect was found in the frontend or the backend.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **2078/2078** (228 files) |
| `npm run build` | pass (`/checkout`, `/checkout/return` prerendered) |
| `npm run test:e2e` | **97/97** (84 + 13 new in `e2e/checkout.spec.ts`) |

### Remaining gaps

- Consent copy is **PENDING LEGAL REVIEW** (`src/lib/checkout/checkoutCopy.ts`; open item Q8).
- No order history/detail yet (FVS-029). The cash confirmation is shown once, from the `201` response. After a reload the order is real but only reachable once FVS-029 exists.
- `/checkout/return` is a minimal handoff: it reads nothing from the URL and shows no payment state. Verified payment status from `GET /me/orders/{id}` is FVS-027.
- After `502 PAYMENT_PROVIDER_UNAVAILABLE`, the UI says the order exists unpaid, but retrying its payment (`POST /me/orders/{id}/payments`) is FVS-027/029.
- A mixed cart whose STL is already owned is physical-only to the server (cash allowed). The UI cannot know that before checkout, so it still disables cash for any cart containing an STL. The customer can pay online, or remove the STL.
- `payment_provider` is never sent. If the backend ever configures more than one provider, checkout gets `422 PAYMENT_METHOD_NOT_ALLOWED provider_required` and the frontend shows "Online payment isn't available right now".

---

## Phase 5C: Cart (FVS-025), 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `0bbb859` (cart contract layer), `2195e9a` (`/cart`), `b4e9e1e` (product-page Add to cart), `2db5925` (header cart link), `472000c` (mocked E2E). All committed before the run; this document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged, no backend code touched) |
| Contract check | running `/openapi.json` has the same 4 cart operations and the same `CartRead`, `CartLineRead`, `CartItemAdd`, `CartItemQuantityUpdate`, `PurchaseRefusal` as `docs/backend-handoff/openapi.json` (129 operations each) |
| Runtime | Docker Compose backend on :8000. `npm run dev` on :3000 proxying to :8000, started only for this run and stopped after it. No media server (cover images 404 in the browser; irrelevant to cart behaviour) |
| Method | real Edge browser through Playwright against the real frontend and backend. **No route mocking.** Direct API probes ran inside the page (same cookies) and were tagged so they were never counted as UI requests. Temporary script kept in the session scratchpad, never committed |
| Customer identity | throwaway `accept-cart-<timestamp>@example.com` accounts made through the real register flow (real Turnstile test widget). Random passwords, never printed or stored. Verify token read only from that account's dev-DB `email_outbox` row |
| Products | seeded products only **read** and added to the throwaway cart: `dragon` (physical, cap 5), `phone-stand-stl` (STL), `knight` (unavailable), `name-sign` (WhatsApp-only). No product, category or setting was modified |
| Data left behind | two throwaway accounts (run 1 discarded for a script bug, see below), each with an **empty** cart (non-null `id`, 0 items) |

**Overall: PASS, 30/30 in one run.**

### Current contract (as implemented)

| Operation | Route | Auth | Result |
|---|---|---|---|
| Read | `GET /api/v1/cart` | session (unverified allowed) | `200 CartRead`; never creates a cart (`id: null` until the first write) |
| Add / merge | `POST /api/v1/cart/items` | session + CSRF + verified email | body `{product_id, quantity=1}` (integer ≥ 1, unknown fields refused) → `200 CartRead` |
| Set quantity | `PATCH /api/v1/cart/items/{product_id}` | session + CSRF + verified email | body `{quantity}` (absolute, ≥ 1) → `200 CartRead` |
| Remove | `DELETE /api/v1/cart/items/{product_id}` | session + CSRF + verified email | `204`; absent line → `404 NOT_FOUND` |

There is **no clear-cart route** (checkout clears the cart server-side). Lines are addressed by `product_id`; there is no line id.

`CartRead`: `id|null, items[], contains_physical, contains_digital, updated_at|null`. `CartLineRead`: `product_id, product_type, name|null, slug|null, cover_image|null, quantity, snapshot_price {amount_cents, currency}, current_price|null, price_changed, max_quantity|null, over_cap, purchasable, unpurchasable_reason (not_listed|unavailable|whatsapp_only)|null`. **No total, subtotal, line total, shipping, tax, discount or stock field.** `snapshot_price` is display only; checkout charges live prices.

Problem codes on writes: `422 PRODUCT_NOT_PURCHASABLE` (`reason`), `422 QUANTITY_EXCEEDS_LIMIT` (`max_quantity`, `requested`, `current_quantity`), `422 CART_LINE_LIMIT_REACHED` (`limit`, 50), `422 VALIDATION_ERROR`, `409 PRODUCT_ALREADY_OWNED` (`product_ids`, POST only), `404 NOT_FOUND`, `403 CSRF_INVALID` / `EMAIL_VERIFICATION_REQUIRED`, `401 AUTH_REQUIRED`, `429 RATE_LIMITED` (300 writes/hour/user).

### Results

| Check | Result | Evidence |
|---|---|---|
| Anonymous `/cart` | **PASS** | → `/login?returnTo=%2Fcart` |
| Anonymous product page | **PASS** | "Add to cart" is a link to `/login?returnTo=%2Fshop%2Fdragon`; the UI sent **no** cart request; real `GET /cart` without a session → `401` |
| Unverified customer | **PASS** | product page shows "Verify your email" link, no Add button; `/cart` shows the verification notice; real `GET /cart` → `200` with `id: null`; real `POST` → `403 EMAIL_VERIFICATION_REQUIRED` |
| Empty cart | **PASS** | real `GET` `200` (`id: null`, no items); empty state + "Browse the shop"; header link "Cart" with no count |
| Add physical | **PASS** | quantity 2 on `/shop/dragon` → `POST` body exactly `{"product_id":…,"quantity":2}`, `X-CSRF-Token` = `csrf_token` cookie → `200`; header "Cart, 2 items" |
| Reload after physical add | **PASS** | line quantity 2 persists; server `max_quantity` 5; summary has no money figure, says the total is calculated at checkout |
| Add STL | **PASS** | no quantity control; `POST` body `{"product_id":…,"quantity":1}` → `200`; header "Cart, 3 items" |
| Reload after STL add | **PASS** | STL line persists, no stepper, "sold one copy per order"; `contains_physical` and `contains_digital` both true; server order = first-added order |
| STL rules | **PASS** | re-adding from the product page → `200` no-op (still one line, qty 1); real `POST` quantity 2 and `PATCH` quantity 2 → `422 QUANTITY_EXCEEDS_LIMIT` with `max_quantity: 1` |
| Physical quantity | **PASS** | `+` → `PATCH /cart/items/{product_id}` body `{"quantity":3}` + CSRF → `200`; UI shows the server's 3; persists across reload; `−` → `{"quantity":2}`; PATCH sequence 3,2,3,4,5 (absolute values only); `+` disabled at 5 with "Maximum 5 per order" |
| Not optimistic | **PASS** | each line's controls disabled until the server answers (unit + mocked E2E); UI always ended on the server's value |
| Over-cap PATCH | **PASS** | real `PATCH` quantity 6 → `422 QUANTITY_EXCEEDS_LIMIT` (`max_quantity: 5`); unchanged |
| Merge over the cap | **PASS** | cart has 2, add 4 from the product page → real `422` (`current_quantity: 2`, `requested: 4`); UI: "You can have at most 5 of this product in your cart. You already have 2."; raw `detail` not on the page; cart unchanged |
| Validation | **PASS** | real quantity `0` → `422 VALIDATION_ERROR` (`loc ["body","quantity"]`); unknown body field → `422`; `PATCH`/`DELETE` of a product not in the cart → `404 NOT_FOUND` |
| Unavailable product | **PASS** | `knight`: unavailable notice, no Add button, the UI sent no write; real `POST` → `422 PRODUCT_NOT_PURCHASABLE`, `reason: unavailable` |
| WhatsApp-only product | **PASS** | `name-sign`: no Add button, the UI sent no write; real `POST` → `422 PRODUCT_NOT_PURCHASABLE`, `reason: whatsapp_only`; cart unchanged. The WhatsApp CTA is hidden because the dev settings have `whatsapp_number: null` (expected; the mocked E2E covers the CTA) |
| CSRF enforcement | **PASS** | wrong and missing token on `POST`, `PATCH`, `DELETE` → all `403 CSRF_INVALID`; cart unchanged |
| CSRF failure in the UI | **PASS** | stale `csrf_token` cookie → UI `PATCH` → real `403 CSRF_INVALID` → "Unable to verify your session…" on that line; cart unchanged |
| Session refresh | **PASS** | `access_token` cookie removed → UI `PATCH` `401` → `/auth/refresh` `204` → retried once → `200`, carrying the current CSRF cookie |
| Remove a line | **PASS** | `DELETE /cart/items/{product_id}` + CSRF → `204`; line gone; focus moves to the "Your cart" heading; persists across reload |
| Logout / re-login | **PASS** | mounted logout → header back to "Cart" with no count (cache dropped); `/cart` → login redirect; after re-login the server cart (qty 3) is back with "Cart, 3 items" |
| 375px + keyboard | **PASS** | no horizontal overflow on `/cart`; Tab from `−` reaches `+`, Enter sends a `PATCH` → `200` |
| Remove the final line | **PASS** | `204` → empty state; empty after reload; server `items: []` with the cart `id` kept |
| CSRF on all UI writes | **PASS** | 15 UI writes, every one with `X-CSRF-Token`: POST 200×3, POST 422×1, PATCH 200×7, PATCH 401×1 (then retried), PATCH 403×1 (deliberate stale cookie), DELETE 204×2 |
| Runtime errors | **PASS** | no page errors, no hydration errors |

Not exercised against the real backend: `409 PRODUCT_ALREADY_OWNED` (needs a paid STL order, i.e. checkout), `422 CART_LINE_LIMIT_REACHED` (needs 50 lines), `429 RATE_LIMITED` (needs 300 writes), a line becoming `over_cap` / unpurchasable / `price_changed` after it was added (needs admin product edits, which this phase does not make). All are unit-tested and the last three are covered by the mocked E2E.

### Defects found and fixed

12. **Mocked E2E were no longer self-contained** (fixed in `472000c`, test-only). The new header cart link reads `GET /api/v1/cart` for a signed-in viewer, so specs that mock a signed-in `/me` would have sent that read through the dev proxy to :8000. They now register `e2e/support/stubCart.ts` (exact `/api/v1/cart` GET only). The full suite also passes with `API_PROXY_TARGET` emptied.
- Login keyboard-walkthrough E2E: the header now has a Cart tab stop after About (expected change; assertion updated).
- Stale pre-contract cart code (drift audit §8): the `item_id`-based model, optimistic helpers, and the unmounted `MiniCartDrawer` / `LoggedOutCartPrompt` were replaced or removed (`0bbb859`).
- Acceptance-script bug in run 1 (not an app defect; 24/30): in-page API probes also fire `requestfinished`, so they were counted as UI writes. Probes are now tagged and excluded. The 30/30 result is from a full re-run with a fresh account.

No integration defect was found in the frontend or the backend.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **2000/2000** (221 files) |
| `npm run build` | pass (`/cart` prerendered) |
| `npm run test:e2e` | **84/84** (76 + 8 new) on three consecutive runs, plus a fourth run with `API_PROXY_TARGET` emptied |

### Remaining gaps

- No cart total by design: the frontend shows a unit count only and says the total is set at checkout (FVS-026 shows checkout's own figures).
- The STL ownership check (`GET /me/stl-ownership`) is not used before Add to cart; the backend's `409 PRODUCT_ALREADY_OWNED` is handled with frontend copy instead.
- Product cards (`ProductListItem`) have no `capabilities`, so there is no Add to cart on the shop grid; it lives on the product page only.
- No checkout CTA: `/checkout` does not exist yet (FVS-026).

---

## Phase 5B: Address Book (FVS-023), 2026-11-10 to 2026-11-11

| Item | Value |
|---|---|
| Frontend commits tested | `87d3454` (dialog focus fix), `dda1bfc` (secondary Button, TextAreaField), `05b0fb3` (address contract layer), `7acb321` (`/account/addresses`). The run used the working tree that became these commits. After the run, only a test-only exact-text matcher in `e2e/account-addresses.spec.ts` changed. This document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged) |
| Contract check | running `/openapi.json` == `docs/backend-handoff/openapi.json` == backend repo `docs/frontend-handoff/openapi.json` (deep-equal, all three) |
| Runtime | Docker Compose api/worker/postgres/redis/clamav `healthy`. At the start, Docker Desktop's engine was stopped (`:8000` accepted TCP but never answered); restarted with `docker desktop restart`. `npm run dev` on :3000 proxying to :8000. No media server needed |
| Method | real Edge browser through Playwright against the real frontend and backend. **No route mocking.** Temporary script kept in the session scratchpad, never committed |
| Customer identity | throwaway `accept-addr-<timestamp>@example.com` accounts made through the real register flow (real Turnstile test widget). Random passwords, never printed or stored. Verify token read only from that account's dev-DB `email_outbox` row. No seeded record was read or modified |
| Data left behind | two throwaway accounts (run 1 was discarded for script bugs, see below), each with **0 live addresses** (deleted through the UI; soft-deleted rows remain by backend design) |

**Overall: PASS, 27/27 in one run.**

### Current contract (as implemented)

| Operation | Route | Auth | Result |
|---|---|---|---|
| List | `GET /api/v1/me/addresses` | session | `200 {items: AddressRead[]}`, default first, hard-capped at 20, not paginated |
| Read one | `GET /api/v1/me/addresses/{id}` | session | `200 AddressRead`; another user's / deleted / unknown id → `404 NOT_FOUND` |
| Create | `POST /api/v1/me/addresses` | session + CSRF + verified email | `201 AddressRead`; the first live address is always the default; `422 ADDRESS_LIMIT_REACHED` at 20 |
| Edit | `PATCH /api/v1/me/addresses/{id}` | session + CSRF + verified email | `200 AddressRead`; omitted = unchanged, `null` clears `area`/`street` (null on a required field is a 422), `is_default` true/false sets/clears, empty body is a 422 |
| Delete | `DELETE /api/v1/me/addresses/{id}` | session + CSRF + verified email | `204`; soft delete; deleting the default leaves **no** default |
| Make default | `PUT /api/v1/me/addresses/{id}/default` | session + CSRF + verified email | `200 AddressRead`; the previous default is cleared atomically |

`AddressRead`: `id, label, recipient_name, phone (E.164), governorate, city, area|null, street|null, landmark_notes, is_default, created_at, updated_at`. `Governorate`: `akkar, baalbek_hermel, beirut, beqaa, keserwan_jbeil, mount_lebanon, nabatieh, north, south`. Limits: label 50, recipient_name 100, phone 32, city 100, area 100, street 200, landmark_notes 500 (required, multi-line). No zone, fee or threshold field exists (ADR-024).

### Results

| Check | Result | Evidence |
|---|---|---|
| Anonymous `/account/addresses` | **PASS** | → `/login?returnTo=%2Faccount%2Faddresses`; again after a mounted logout |
| Unverified customer write | **PASS** | warning notice + resend link shown; real `POST` → `403 EMAIL_VERIFICATION_REQUIRED`; dialog shows frontend copy; raw `detail` not on the page |
| Page load, nav | **PASS** | real `GET` `200`; "Addresses" nav link `aria-current="page"`; empty state; notice gone once verified |
| Client validation | **PASS** | empty submit shows field errors, focuses the first field, sends **no** request |
| Real `422 VALIDATION_ERROR` | **PASS** | phone `12` → `422`, `loc=body.phone`; shown on the Phone field ("Enter a Lebanese phone number…"), `aria-invalid`, focused; no `ValidationError.msg` on the page; nothing stored |
| Create (first) | **PASS** | `POST` `201`; body keys exactly the `AddressCreate` set; shown as Default (backend rule); phone `03 123 456` returned and shown as `+9613123456` |
| Refresh after create | **PASS** | street/area, city + governorate label, landmark notes and Default all persist |
| Create (second, not default) | **PASS** | `201`, `is_default=false`; blank street sent as `null`; `+961 71 123 456` → `+96171123456` |
| Edit | **PASS** | city changed + area cleared → `PATCH` body exactly `{"city":"Batroun","area":null}` → `200` |
| Refresh after edit | **PASS** | "Batroun, North"; area gone |
| Edit with no changes | **PASS** | no request sent; "No changes to save." |
| Set as default | **PASS** | `PUT …/default` `200`; badge moves after the refetch; server list default-first; persists across reload |
| Clear default via edit | **PASS** | untick → `PATCH {"is_default":false}` `200` → no default anywhere (UI + server) |
| Set default via edit | **PASS** | tick → `PATCH {"is_default":true}` `200` |
| CSRF on UI writes | **PASS** | the 8 UI writes made before this check (4 POST including the refused 403/422 ones, 3 PATCH, 1 PUT) all carried `X-CSRF-Token` equal to the `csrf_token` cookie. The two later UI `DELETE`s answered `204`, which the backend's CSRF check only allows with a valid token |
| CSRF enforcement | **PASS** | wrong/missing token on `POST`, `PATCH`, `PUT …/default`, `DELETE` → all `403 CSRF_INVALID`; state unchanged |
| Unknown id | **PASS** | `GET` and `DELETE` → `404 NOT_FOUND` |
| Read one | **PASS** | `GET /me/addresses/{id}` equals the list's record |
| Delete: cancel | **PASS** | Cancel sends nothing |
| Delete | **PASS** | confirm → `DELETE` `204` → dialog closes → gone after reload |
| Delete the default | **PASS** | dialog warns "you won't have a default address…"; `204`; empty list after reload (no promotion) |
| 375px + keyboard | **PASS** | no horizontal overflow (page or dialog); dialog opens focused on Label; Escape closes it and focus returns to the trigger |
| Runtime errors | **PASS** | no page errors, no hydration errors |

Not exercised against the real backend: `422 ADDRESS_LIMIT_REACHED` (needs 20 addresses; unit + component tested) and a real cross-user `404` (only an unknown id was used; the backend gives one 404 for all three cases).

### Defects found and fixed

11. **Dialog focus not restored after the address form auto-focuses** (fixed in `87d3454`, frontend). Found by the new mocked E2E. `DialogShell` recorded the trigger in a passive effect, after the child had already moved focus to its first field, so the input became the "trigger". It now records in a layout effect, and `AddressForm` focuses its first field in an effect instead of `autoFocus`. Regression test in `DialogShell.test.tsx`.
- Stale pre-contract address model (`{id, displayLines, isDefault}`, drift audit §5): replaced with the real contract (`05b0fb3`).
- Acceptance-script bugs in run 1 (not app defects; 25/27): `getByText("Default")` substring-matched "Set as default", and one step read the recorded write before Playwright's `requestfinished` fired. Fixed; the 27/27 result is from a full re-run with a fresh account. The mocked spec's matcher was tightened the same way.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **1943/1943** (217 files) |
| `npm run build` | pass (`/account/addresses` prerendered) |
| `npm run test:e2e` | **76/76** (66 + 10 new) on three consecutive runs |

### Remaining gaps

- `ADDRESS_LIMIT_REACHED` and cross-user `404` were not provoked at runtime (see above).
- `DefaultAddressSelector` and `addressDefaultOptimistic` remain unmounted (checkout may use the selector).
- Checkout (`DeliveryMethodSelector`) still reads only `displayLines`/`isDefault`; it is integrated in FVS-026.

---

## Phase 5A closure: 2026-11-10 (admin, VERSION_CONFLICT, mounted logout, hydration)

| Item | Value |
|---|---|
| Frontend commits tested | `80b8db6` (mounted logout, defect 7) + `838e160` (reset-password hydration, defect 6), on top of `3ea70b3`. This document is updated in the commit after them |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** (unchanged) |
| Runtime | same as the run below: Docker Compose api/worker/postgres/redis/clamav `healthy`, `npm run dev` on :3000 proxying to :8000, dev media server on :8001 |
| Method | real Edge browser through Playwright against the real frontend and backend. **No route mocking.** Temporary scripts kept outside the repo (session scratchpad), never committed |
| Admin credentials | read only from `%USERPROFILE%\.bekaa3d\dev-admin.json` (`admin_email`, `admin_password`, `admin_totp_secret`; the schema the earlier admin runner already used). The file was missing. It was created by running the backend's own `scripts/dev_seed.py --rotate-credentials` and piping its one-time output straight into a local parser that wrote only those three keys. Nothing was printed, logged or committed. Rotation also **retired the previously exposed seed credentials**. The new recovery codes and seed-customer password were discarded unseen. Local development database only: never reuse for staging/production |
| Customer identities | fresh throwaway `accept-<timestamp>@example.com` accounts made through the real register flow. Tokens read from that account's dev-DB `email_outbox` row only |
| Disposable admin data | `acceptance-physical-<ts>` / `acceptance-stl-<ts>` products (deleted at the end), `Accept Category/Material/Colour <ts>` reference values (archived at the end). The `pickup_hours` and `accepting_orders` settings were changed and then restored. The throwaway customer was deactivated, then reactivated. No seeded record was modified |

**Overall: admin PASS (17/17 in one run) · real VERSION_CONFLICT PASS (API + UI) · mounted logout PASS (customer + admin) · reset-password hydration FIXED · mounted regression PASS (16/16 in one run).**

### Admin auth and authorization

| Check | Result | Evidence |
|---|---|---|
| Login → MFA challenge | **PASS** | `POST /auth/login` → `202` with keys `challenge_id, expires_in_seconds`; the UI showed "Verification code" |
| Real TOTP verification | **PASS** | code computed from the local secret, typed into the real form; `POST /auth/mfa/verify` → `204` (the contracted status) |
| Session established, `/me` role | **PASS** | `/me` `200`, `role === "admin"`; landed on `returnTo` `/admin/settings`; admin nav rendered |
| Customer on `/admin/*` (UI) | **PASS** | signed-in customer on `/admin/settings` got the normal not-found page; no admin nav |
| Customer on backend admin endpoint | **PASS** | `GET /admin/settings?limit=1` and `GET /admin/users` → `404 NOT_FOUND` (documented in BACKEND-RESPONSE.md: "a customer gets `404` from every admin path") |
| Admin write with wrong CSRF | **PASS** | `POST /admin/products` with a bad `X-CSRF-Token` → `403 CSRF_INVALID` |

### Admin screens

| Area | Result | Evidence |
|---|---|---|
| Settings: load | **PASS** | `GET /admin/settings` `200` |
| Settings: edit a safe setting | **PASS** | `pickup_hours` edited in the UI → `PATCH` `200` → "Saved"; value persisted across reload; original restored (`PATCH` `200`) |
| Settings: `accepting_orders` confirmation | **PASS** | Save opens "Change checkout availability"; **Cancel sends no PATCH**; "Confirm change" → `PATCH` `200`; flipped value persisted across reload; restored to `true` with the same dialog, confirmed by `GET /settings/public` |
| Customers: list, detail | **PASS** | `GET /admin/users` `200`; detail page for the throwaway customer |
| Customers: deactivate / reactivate | **PASS** | confirm dialog → `PATCH /admin/users/{id}` `200` → "Deactivated" (after reload, and `is_active=f` in the DB); reactivate → `200` → "Active" (reload + DB) |
| Categories / materials / colours | **PASS** (each) | create `201` (category with slug) → edit `200` → Disable `200` ("Disabled" persists across reload) → Enable `200` → Archive dialog → `DELETE` `204` → "Archived" after reload |
| Products: list | **PASS** | `GET /admin/products` `200`, real catalogue |
| Products: create physical (UI) | **PASS** | `201`, `type=physical`, lead time 3, batch 2, max qty 4, material/colour/dimensions set, `purchase_mode=online_only` |
| Products: create STL (UI) | **PASS** | choosing "STL (digital)" removes the physical section; `201`, `type=stl` with every physical field `null`; edit page shows the type locked ("Product type can't be changed after creation.", radios disabled) |
| Products: edit (UI) | **PASS** | name + batch size → `PATCH` `200` (version 1 → 2); both persisted across reload |
| Products: delete disposable (UI) | **PASS** | confirm dialog → `DELETE` `204` → back on `/admin/products`; public `GET /products/{slug}` `404`. Admin `GET` still answers `200` with `deleted_at` set (soft delete; observation 3) |
| Images: upload | **PASS** | two PNGs through the real file input → two `POST …/images` `201`; thumbnails loaded |
| Images: alt text / cover / reorder | **PASS** | "Save alt text" `PATCH` `200`; "Set as cover" `PUT …/cover` `200`; "Move up" `PUT …/images/order` `200`; order, cover and alt text all confirmed persisted by a fresh `GET` |
| Images: delete | **PASS, with a defect** | confirm dialog → `DELETE` `204`; one image left after reload; the remaining image is served through `/media` (`200`). **The "Delete image" dialog stays open after the delete succeeds** (defect 10) |

### Real `409 VERSION_CONFLICT`

| Check | Result | Evidence |
|---|---|---|
| Backend | **PASS** | `GET` product at v1 → `PATCH` with v1 `200` (v2) → `PATCH` with stale v1 → **`409 code=VERSION_CONFLICT`**; the stale write was not applied |
| Frontend: no silent retry | **PASS** | exactly **one** `PATCH` (the 409) from the edit form; none in the following 3 s |
| Frontend: authoritative re-fetch | **PASS** | a `GET /admin/products/{id}` is issued after the 409 |
| Frontend: form reconciles to server state | **PASS** | the Name field, which held the stale local edit, now shows the server's value |
| Frontend: safe banner | **PASS** | "This product was changed by someone else. Review the latest version below and try again." No raw `detail`, `request_id` or problem `type` on the page |
| Frontend: explicit resubmit | **PASS** | the admin edits and clicks Save changes again → `PATCH` `200` with the fresh version |

### Mounted logout (defect 7, closes the earlier "API level only" gap)

| Check | Result | Evidence |
|---|---|---|
| Control visible to a signed-in user | **PASS** | "Log out" button in the account nav (customer) and the admin nav (admin), one shared `LogoutButton` |
| Real logout | **PASS** | click → `POST /auth/logout` `204` → lands on plain `/login` (no `returnTo`); no raw backend error text |
| Frontend session state cleared | **PASS** | auth query set anonymous; user-scoped caches (`admin`, `notifications`) dropped (unit-tested) |
| Cookies | **PASS** | `access_token` and `refresh_token` removed from the browser. Pre-logout refresh cookie replayed in a fresh context → `POST /auth/refresh` `401 AUTH_REQUIRED` (session revoked) |
| `/me` after logout | **PASS** | `401 AUTH_REQUIRED` |
| Protected routes | **PASS** | `/account/profile` → `/login?returnTo=%2Faccount%2Fprofile`; `/admin/settings` → `/login` |
| Login afterwards | **PASS** | customer login `200`, `/me` `200` |
| Replayed pre-logout **access** cookie | observation 1 | still accepted by `/me` (`200`) until it expires |

### Reset-password hydration (defect 6)

| Item | Detail |
|---|---|
| Reproduction | Edge against the dev server, `/reset-password#token=…`: SSR HTML contained the invalid-link alert and no form; the client rendered the form; React threw **"Hydration failed because the server rendered HTML didn't match the client"** |
| Root cause | the token exists only in the URL fragment, which never reaches the server. The page read `window.location.hash` in a `useState` initializer: `null` on the server (invalid-link branch), the token on the client's hydration render (form branch). FVS-002 BATCH 4 had already fixed the same cause on `/verify-email` |
| Fix (`838e160`) | token state starts `undefined` ("not read yet") on both sides and renders a neutral loading state. One client-only effect captures the token, removes the fragment and keeps the token in memory. A ref guard stops React Strict Mode's second effect run from re-reading the already-cleared fragment. No `suppressHydrationWarning` |
| Security behaviour | unchanged: token read from the fragment only, fragment removed immediately, token only in component memory, never stored or logged (a console scan for the token found none) |
| Real-runtime result | **PASS**: SSR HTML is the neutral state; 0 hydration errors; real reset `confirm` `204`; login with the new password `200` |
| Regression tests | `src/app/reset-password/page.test.tsx`: hydrates real `renderToString` server markup (made without a fragment, as the server sees it) and fails on any recoverable hydration error, with and without a token. Plus a Strict Mode test |

### Mounted-app regression pass (one run, 16/16)

`/`, `/shop`, `/shop/geometric-planter` (real products, `/media` images loaded) · register (real Turnstile test widget) `202` · verify-email `204` · login · profile · notifications list + mark read · customer admin guard (UI + API) · mounted logout (all rows above) · forgot-password `202` · reset-password `204`, no hydration error · login with the new password. Admin areas: the 17/17 admin run above. Rate-limited flows were not repeated beyond one attempt each, and no `429` was provoked on purpose.

### New defect and observations from this run

10. **Image delete dialog stays open after a successful delete** (open, frontend, `src/components/admin/ImageGallery.tsx`). `onConfirm` calls `onDelete` but never clears `deleteTargetId`. The image is deleted (`204`), but the dialog stays up, and a second "Delete" click would target an id that no longer exists. Not one of this phase's two fixes, so it is left for a follow-up. The reference-data Archive dialog does not have this problem.
- Observation 1 (backend): logout revokes the session and clears cookies, but a **copied** pre-logout `access_token` stays valid until its 15-minute lifetime ends (stateless JWT, per VS-003). The browser no longer holds it, so this matters only if the cookie was exfiltrated. Confirm this is the intended trade-off.
- Observation 2 (backend, harness only): the outbox worker replaces sent payloads with `[redacted]`. Acceptance scripts must read the dev-DB token immediately after the request. One regression run lost that race and was re-run; the results above are from the re-run.
- Observation 3 (backend): after `DELETE /admin/products/{id}` → `204`, admin `GET` of that id still answers `200` with `deleted_at` set, while the public slug answers `404`. Consistent with soft delete; noted in case the admin UI should treat it as gone.
- Mocked E2E: the first `npm run test:e2e` run had 1 failure, "the readiness banner, whatever it shows, never breaks the shell". It counts `role=status` regions, then checks each one, and the home page's loading skeleton vanished between the two steps, because the dev server is wired to the real (fast) backend. It passed 5/5 on repeat, and the full suite then passed **66/66**. This is a pre-existing count-then-iterate race on `/`, which none of this phase's code touches.

### Verification (this phase)

| Command | Result |
|---|---|
| `npm run lint` | 0 errors, 4 warnings (the known `<img>` warnings) |
| `npm run typecheck` | clean |
| `npm run test` | **1870/1870** (1858 + 12 new) |
| `npm run build` | pass |
| `npm run test:e2e` | **66/66** (after one flaky first run, see above) |

### Remaining gaps

- Defect 10 (image delete dialog) is open.
- `503` captcha-unavailable is still unit-tested only.
- Observations 1 and 3 need a backend decision. Earlier observations 8 (`commit: "unknown"`) and 9 (login before email verification) are still open.
- Out of Phase 5A scope by instruction: addresses, cart, checkout, orders.

---

## Phase 5A run: 2026-11-09 to 2026-11-10

| Item | Value |
|---|---|
| Frontend commit tested | `3ea70b3` (Phase 5A compatibility commit). This document is updated in the commit after it |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `main`, commit **`2dfb27b`** |
| Runtime | Docker Compose: api, worker, postgres, redis, clamav all `healthy`. `CAPTCHA_PROVIDER=fake`, `EMAIL_PROVIDER=console` |
| Frontend runtime | `npm run dev` on :3000. `.env.local` (git-ignored, **no credentials**) sets `API_PROXY_TARGET=http://localhost:8000` and `MEDIA_PROXY_TARGET=http://localhost:8001` |
| Media server | dev-only read-only static server over the backend's `storage/media_public` on :8001. `npx serve` hung at package download, so a minimal Node static server was used instead (same role) |
| Method | Real browser (system Edge through Playwright) driving the real frontend, which proxies to the real backend. **No route mocking**, with one exception: the CAPTCHA_INVALID check rewrites only the outgoing `captcha_token` so the real backend gives the refusal. The mocked `npm run test:e2e` suite is separate and is **not** counted here |
| Test identities | throwaway customers `accept-<timestamp>@example.com`, created by the run itself through the real register flow. No seed credentials were used or recorded. Verify and reset tokens were read from the dev DB `email_outbox` row of the throwaway account only (the console email adapter logs payload keys, not values; tokens are stored hashed) |

**Overall: public PASS · media PASS · auth PASS · account PASS · CSRF PASS · admin NOT RUN (blocked on credentials) · VERSION_CONFLICT NOT RUN (admin-only).** Admin and VERSION_CONFLICT were run and passed in the closure section above.

### Health and contract

| Check | Result | Evidence |
|---|---|---|
| `/api/health/live` through the frontend proxy | **PASS** | `200 {"status":"ok"}` |
| `/api/health/ready` through the frontend proxy | **PASS** | `200 {"status":"ok","version":"0.1.0","commit":"unknown"}` (the runtime does not report its own commit) |
| Running `/openapi.json` vs backend repo `docs/frontend-handoff/openapi.json` | **PASS: schema-equal** | sorted-key deep comparison is equal; bytes differ only in key order |
| Old snapshot (`d1c1cf1`) vs current: drift on pre-existing contract | 5 schemas, all fixed | `NotificationType`, `PasswordResetRequest`, `PublicSettingsRead`, `RegisterRequest`, `ResendVerificationRequest`. No pre-existing operation changed or was removed |

### Public

| Feature | Result | Evidence |
|---|---|---|
| Home (`/`) | **PASS** | real products; `/media` images loaded (`naturalWidth > 0`) |
| Shop (`/shop`) | **PASS** | real catalogue; images loaded through the frontend origin |
| Categories, materials, colours | **PASS** | filter options `Home Decor`, `PETG`, `Black` come from the backend |
| Search (`/shop?q=planter`) | **PASS** | only `geometric-planter` shown |
| Suggestions | **PASS** | typing `pla` gave `GET /api/v1/search/suggestions` → 200; "Geometric Planter" shown |
| Product detail (`/shop/geometric-planter`) | **PASS** | heading plus real image (see environment note 2) |
| About (`/about`) | **PASS** | renders |
| Public settings | **PASS** | keys exactly `accepting_orders, cash_max_order_total, cash_payment_enabled, pickup_address, pickup_hours, whatsapp_number`; no `free_shipping_threshold`; `cash_max_order_total = {amount_cents: 10000, currency: "USD"}` |

### Media

| Check | Result | Evidence |
|---|---|---|
| Seeded product image through the **frontend origin** | **PASS** | `GET http://localhost:3000/media/products/fa6c43bc-….png` → `200 image/png`, 3053 B, PNG magic bytes. Rendered in the browser on home, shop and detail |
| Production URL semantics | unchanged | the `/media` rewrite is registered only when `MEDIA_PROXY_TARGET` is set **and** `NODE_ENV !== "production"` (`src/lib/config/proxyRewrites.test.ts`) |

### Auth

| Feature | Result | Evidence |
|---|---|---|
| Register with captcha | **PASS** | real Cloudflare Turnstile widget, test site key `1x00000000000000000000AA`, issued the dummy token; body contained `captcha_token`; `202`; enumeration-safe copy |
| Resend verification with captcha | **PASS** | body contained `captcha_token`; `202` |
| `400 CAPTCHA_INVALID` (real backend) | **PASS** | refused token → real `400 code=CAPTCHA_INVALID`; UI showed frontend-owned copy; raw `detail` not rendered |
| `503` captcha unavailable | unit-tested only | can't be forced at runtime without reconfiguring the backend's fake provider |
| Verify-email fragment-token flow | **PASS** | `/verify-email#token=…` → `POST /auth/verify-email` `204`; token removed from the address bar |
| Login → `/me` | **PASS** | login `200`; `/me` `200`; `csrf_token` cookie present; `access_token` cookie is httpOnly |
| Refresh | **PASS** | with `access_token` removed, the protected page triggered `POST /auth/refresh` → `204`, and the profile rendered again |
| Logout | **PASS (API level)** | `POST /auth/logout` with the frontend CSRF contract → `204`; `/me` then `401`; `/account/profile` redirects to `/login`. **No mounted UI control calls logout** (defect 7). Superseded: mounted logout PASS in the closure section |
| Password-reset request with captcha | **PASS** | body contained `captcha_token`; `202` |
| Reset-password fragment-token flow | **PASS** | `/reset-password#token=…`, token sanitized from the URL; confirm `204`; login with the new password `200` |
| Real `429 RATE_LIMITED` | observed | after about 5 reset requests from one IP within minutes, the backend answered `429` (correct limiter behaviour, triggered by repeated acceptance runs) |

### Account

| Feature | Result | Evidence |
|---|---|---|
| Profile (`/account/profile`) | **PASS** | real account email rendered from `/me` |
| Notifications list | **PASS** | one `custom_request` notification inserted for the throwaway account renders with the new "Custom request" label |
| Mark read / mark unread | **PASS** | `PATCH /me/notifications/{id}` `200` both ways; button state toggled |

### Error contract

| Check | Result | Evidence |
|---|---|---|
| `403 CSRF_INVALID` | **PASS** | `PATCH /me/notifications/{id}` with a wrong `X-CSRF-Token` → real `403 code=CSRF_INVALID` |
| `409 VERSION_CONFLICT` | **NOT RUN** (then; **PASS** in the closure section) | in the current OpenAPI it exists only on admin products (`POST`/`PATCH`/`DELETE /admin/products…`); needs the admin session |

### Admin

| Feature | Result |
|---|---|
| MFA login, settings, customers, categories/materials/colours, product list/detail/edit, product create/update/delete, image upload/alt/cover/order/delete, admin CSRF, `409 VERSION_CONFLICT` (API and edit UI) | **NOT RUN: blocked on credentials.** The dev seed credentials are treated as compromised and must not enter source, tests, docs, `.env.local` or logs. A ready script reads them from a local file outside any repo (`%USERPROFILE%\.bekaa3d\dev-admin.json`: `admin_email`, `admin_password`, `admin_totp_secret`), types them only into the real login form, and never prints them. The file was not present when the run was attempted. **Resolved and run in the closure section above** |

### Integration defects found

1. **Captcha missing on three mounted auth flows** (register, resend, reset request): every real submit was `422`. **Fixed**; real runtime now `202`.
2. **`PublicSettingsRead` type drift** (removed `free_shipping_threshold`; missing `cash_payment_enabled`, `cash_max_order_total`). **Fixed.**
3. **`NotificationType` lacked `custom_request`**: generic fallback label only. **Fixed**; real notification renders "Custom request".
4. **No `/media` in local dev.** **Fixed** with the dev-only `MEDIA_PROXY_TARGET` rewrite.
5. **Mocked E2E race:** two login tests asserted `/account$` while `/account` server-redirects to `/account/profile`. They failed on the pre-change baseline too. **Fixed** (test-only).
6. **Hydration mismatch on `/reset-password`** (**fixed in `838e160`**, see the closure section; was open, frontend): the server renders the invalid-link alert because the token exists only in the URL fragment, and the client renders the form. React recovers on the client and the flow works, but it logs a hydration error. Not contract drift, so not changed in this phase.
7. **No logout control in the mounted UI** (**fixed in `80b8db6`**, see the closure section; was open, frontend): `AuthProvider.logout()` exists but nothing calls it. Not contract drift, so not changed in this phase.
8. Observation (backend): `/health/ready` reports `commit: "unknown"`.
9. Observation (backend): login succeeded for an account before its email was verified. Confirm with the backend team that this is intended.

### Environment notes

1. Partway through, Claude Code stopped the dev and media servers because the machine was critically low on memory. They were restarted after the user said to continue.
2. After that reclaim, the surviving orphan dev server's render workers were gone (`Jest worker encountered 2 child process exceptions`), so dynamic `/shop/[slug]` returned 500. A fresh dev server fixed it, and product detail passed on that server. This was not a code defect.
3. Acceptance scripts were kept outside the repo, in the session scratchpad. Script bugs found during the run (outbox template names; a cookie re-add that dropped the `/api/v1/auth`-scoped refresh cookie; an early URL-sanitization assertion) were fixed and the affected items re-run. The results above are from the fixed runs.

---

## Earlier attempt: 2026-10-19 (blocked)

Frontend `53b1ef3`, no backend checkout and no Docker on the machine, so the real-runtime portion was not attempted. That blocker is gone (see above).
