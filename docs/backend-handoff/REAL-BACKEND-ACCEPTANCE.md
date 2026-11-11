# Real Backend Acceptance

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
- **Unverified account (`403 EMAIL_VERIFICATION_REQUIRED`):** registration was rate-limited for the rest of the run. Deferred to the Phase 5H run (recorded there). Covered meanwhile by unit tests (`orderActionErrors`, `OrderCustomerActions`).

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
