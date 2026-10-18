# VS-024 — Payment Recovery: Retry, Reconciliation, Hold Release, Manual Confirm: Implementation Plan

**Status:** IN PROGRESS (code): CP1 merged (PR #20, `8d15284`, migration `00ce1ce252a6`).
CP2-CP6 are on branch `vs-024-recovery` from 2026-10-18. Revisions 1 and 2 hold the owner's decisions.
**Date:** 2026-10-18
**Planned against alembic head:** `03a4730dd046` (orders_payments_webhooks_idempotency,
VS-023 PR A, merged before `42c3f63`).
- Derived statically from `revision` / `down_revision` in `migrations/versions/`: 21
  files, one linear chain, one head. `03a4730dd046` revises `26d5d039d72c`, and no file
  names `03a4730dd046` as its `down_revision`. No merge revisions.
- This slice's migration (PR A, §4) therefore has `down_revision = "03a4730dd046"`.
- Re-derive the head immediately before `alembic revision`: VS-023b and VS-028 also
  plan migrations (`docs/vertical-slice-plan.md:575-578`, `:693-699`).

**Pre-flight (2026-10-18):** `git fetch`, `git checkout main`, `git pull --ff-only`
(already up to date at `42c3f63`). Remote branches: `feat/vs-038-wishlist`,
`vs-022-mixed-cart`, `vs-023-checkout`, `vs-023-schema`, `vs-046-security-retention`. None
has a commit that is not on `main` (`git log main..origin/<branch>` is empty for all five),
and no commit on any ref mentions VS-024. Highest ADR on `origin/main`: **ADR-032**, so
this slice's ADR is **ADR-033** (re-check before writing it).

**Format:** follows [`VS-023-digital-checkout-plan.md`](VS-023-digital-checkout-plan.md).
Every `file:line` below is on `main` at `42c3f63`.

---

## Revision 2 (2026-10-18): owner answers before CP1

These are recorded as decided. They bind PR B.

- **Q1 (captured amount now):** decided by the owner's CP1 instruction. PR A adds
  `captured_amount_cents` and `captured_currency`.
- **Q2:** VS-030 must handle a late capture that has **no matching payment record**, such
  as a mismatched amount that manual confirm refused (§2.3, R3). VS-030's plan must say
  how it is recorded and refunded.
- **Q6:** `MANUAL_RELEASE_GRACE` is **24 h, a code constant** in
  `app.payments.domain.limits` (§3.8), not a setting.
- **Q7:** **no early release when a provider reference is stored.** Manual release
  without the grace is allowed only for an attempt that has no `provider_payment_id` and
  whose latest provider answer is `unknown` (the checkout crash window). Every other case
  waits for the 24 h grace (§2.5).
- **Q9:** **keep the `redirect_url` log test** (§6.2). No framework on this stack logs
  local variables:
  - `format_exc_info` turns tracebacks into plain text before **both** the JSON and the
    console renderer (`core/logging.py:171-174`, `:186-189`). So the `ConsoleRenderer`
    receives a string and has no frames to print locals from.
  - `rich` and `better_exceptions` are not installed and are not in
    `requirements*.txt` / `pyproject.toml`. Without them, `structlog.dev.ConsoleRenderer`
    has no locals-printing formatter.
  - FastAPI runs with `debug=False` (`main.py:50`, the default), so Starlette serves no
    debug traceback page.
  - uvicorn's error log uses the stdlib traceback, which has no locals.
  - The first draft's claim that the development console "may show locals" was wrong,
    and is corrected in §2.1. No logging change is needed.
- **Q12:** "an abandoned session eventually answers `expired`" is a **VS-032 provider
  selection criterion and a contract fixture** (§6.4, R1).
- **Still open:** Q3, Q4, Q5, Q8, Q10, Q11.

## Revision 1 (2026-10-18): owner review

These points bind the plan. The body below already reflects them.

1. **Automatic release happens only on an explicit provider `failed` or `expired`** (§3.1 T2).
   - Never on: no answer, a timeout, `unknown`, `pending`, `processing`, or any
     unprocessed webhook event.
   - This replaces the grace auto-release of the first draft's D5.
2. **Manual admin release** (§2.5) becomes possible once the hold plus
   `MANUAL_RELEASE_GRACE` (24 h) has passed. A reason is mandatory and the action is
   audited.
   - It is the only exit for providers without a status API, and for attempts the
     provider never settles.
   - §2.5 lists the money risks and the test for each case.
3. **Admin reconcile answers `202` before any provider call** (§2.2).
   - The provider call runs in a background task after the response is sent, outside
     every transaction.
   - The 15-minute job is the fallback for live attempts.
4. **Manual confirm:** a typed amount or currency that differs from the attempt is always
   `422 PAYMENT_AMOUNT_MISMATCH` (§2.3).
   - It is never recorded as a late capture.
   - `record_mismatch` is removed. This replaces D6 and the first draft's owner question 3.
5. **Retry** (§2.1):
   - the idempotency scope is `payment_retry:{order_id}`, per user;
   - `redirect_url` reaches only the owner and is never logged;
   - the race tests are listed in §6.3.
6. **`unknown` never changes anything:** no attempt is failed, paid or released on it
   (§3.2a). This replaces D10's "fail an unreferenced attempt after 5 min".
7. **Every timing and limit lives in one module, `app.payments.domain.limits`** (§3.8).
8. **§8.1 shows the lock order with the SQL for each path**, and where the hold release
   sits in it. **§8 lists the checkpoints with what each reports, and PR A's exact file
   list.**

**Earlier decisions that changed:**
- D3: the idempotency scope;
- D5: the release rule;
- D6: confirm on a mismatch;
- D10: what `unknown` does;
- the first draft's owner questions 2, 3 and 8 are now decided, and §10 is renumbered.

**New decisions:** D13 (manual release) and D14 (the constants module).

---

## 0. Decisions this plan takes (summary)

| # | Decision | Where |
|---|---|---|
| D1 | One small additive migration: `payments.captured_amount_cents` and `captured_currency` (ADR-024 appendix `:98`). Everything else needs no schema change: every query is served by an index VS-023 already built. | §4 |
| D2 | The schema PR (PR A) merges first, per CONTRIBUTING.md's migration lock (`CONTRIBUTING.md:42-47`). It contains no application code (§8). | §8 |
| D3 | Retry is `POST /api/v1/me/orders/{order_id}/payments`, owner-only, with the checkout pattern: `Idempotency-Key` scoped `payment_retry:{order_id}` per user, two transactions around the provider call, and the `RETRY_RATE_LIMIT`. It is refused once `placed_at + checkout_hold_period` has passed. | §2.1 |
| D4 | The hold deadline is `max(placed_at, latest attempt's initiated_at) + checkout_hold_period`. The retry cut-off in D3 caps it at under 2 × hold. | §3.1 |
| D5 | The `release_stale_checkouts` job releases an order **only** when the provider explicitly answers `failed` or `expired` for its latest attempt. Nothing else ever releases automatically. | §3.1 T2 |
| D6 | Manual confirm goes through `apply_result`, the same path and lock order as the webhook. A typed amount or currency that differs from the attempt is `422 PAYMENT_AMOUNT_MISMATCH`: nothing is written and nothing is recorded as a late capture. | §2.3 |
| D7 | Manual confirm is allowed only for providers without a status API, or that are no longer configured. A status-capable provider answers `409 MANUAL_CONFIRMATION_NOT_ALLOWED`. | §2.3 |
| D8 | Admin reconcile answers `202` before any provider call. The query runs in a background task after the response, with no transaction open. The 15-minute job is the fallback for live attempts. | §2.2 |
| D9 | Alerts go to every active administrator as an in-app notification and an email, plus an error log. They are de-duplicated through `payment.alert_raised` audit rows. | §3.5 |
| D10 | The provider port gains `unknown` ("no record of this merchant reference"). It is treated as "no answer" everywhere: nothing is failed, paid or released. | §3.2a |
| D11 | `verify_payments` skips events awaiting manual confirmation. Every status query is bounded at `PROVIDER_TIMEOUT_SECONDS`. | §3.3 |
| D12 | Global lock order: `idempotency_records → carts → orders → order_items (by id) → payments (by id) → webhook_events`, then INSERTs only. No path takes a separate "hold-release" lock. | §8.1 |
| D13 | Manual admin release: `POST /api/v1/admin/orders/{order_id}/release`, available after the hold deadline + `MANUAL_RELEASE_GRACE` (24 h). A reason is mandatory, it is audited, and it never calls the provider. | §2.5 |
| D14 | Every VS-024 timing and limit, and the VS-023 payment ones it depends on, live in `app.payments.domain.limits`. | §3.8 |

## 1. Scope and non-goals

### In scope (VS-024 only)

- **Retry (BR-058, F-047):** a new `pending` attempt on the same order, for the order's
  snapshot total (`docs/vertical-slice-plan.md:612-619`).
- **`reconcile_payments` job (every 15 min, SRS §23 `SRS.md:1399`):** live online attempts
  with no answer, including the checkout Tx2-crash attempt with no provider reference
  (`docs/vertical-slice-plan.md:602`, ADR-032 Consequences `:71`).
- **`release_stale_checkouts` job (every 5 min, `SRS.md:1398`):** cancels unpaid online
  orders whose hold ended, **only** on an explicit provider `failed` / `expired` (T2, §3.1).
  This frees the STL ownership index (`ordering/infrastructure/models.py:316`).
- **Manual admin release** `POST /api/v1/admin/orders/{order_id}/release` after the grace,
  with a mandatory reason (§2.5).
- **Admin payments:** `GET /api/v1/admin/payments`, `GET …/{payment_id}`,
  `POST …/{payment_id}/reconcile`, `POST …/{payment_id}/confirm`
  (`api-endpoints.md:589-592`).
- **Late captures:** the captured amount is stored, and administrators are alerted
  (ADR-024 d15 `:51`, appendix `:98`). VS-024 creates **no** refund row.
- **Alerts** for stuck payments, skipped releases, unreachable providers, manual
  confirmations due and late captures (SRS §24.6 `SRS.md:1445`; Done-when "No payment
  stays stuck without an alert", `docs/vertical-slice-plan.md:646`).
- **Fixes to VS-023 code this slice depends on:**
  - the 10 s bound on status queries (D11);
  - the manual-confirmation starvation in `verify_payments` (D11);
  - the admin actor on apply's audit rows (`apply.py:81`, `:118`, `:160` write
    `actor_user_id=None`, although `apply_result` takes `actor_user_id`, `apply.py:33`).

### Non-goals, and exactly who owns them

| Not here | Owner | Why |
|---|---|---|
| The `late_capture` refund obligation, `refunds` / `refund_items`, the backfill for rows already late-captured | **VS-030** (`docs/vertical-slice-plan.md:782`, `:794`) | VS-024 only records the capture, its amount and the alert, and exposes the hook VS-030 extends (§3.6). |
| Payment status `paid → partially_refunded → refunded` | VS-030 | No refund exists before VS-030. |
| BR-148 enforcement on physical transitions, the cash handover, the admin order queue | **VS-029** (`:747`, `:751-756`) | VS-024 provides the read VS-029 gates on (§3.6) and the one BR-148 exception, the hold release (`SRS.md:343`). |
| Cash orders | VS-028 / VS-029 | They have no payment row while unpaid, so no VS-024 query can select one (ADR-024 d3 `:20`). VS-024 still filters `payment_method = 'online'` explicitly, and tests it with seeded rows. |
| A real provider adapter, the provider list setting, the IP allowlist, sandbox fixtures, chargebacks | **VS-032** (`:896-906`) | VS-024 keeps the port provider-neutral (§3.6). |
| Customer order history and detail (`can_retry_payment`, `hold_expires_at` on `OrderDetail`) | **VS-025** | VS-024 exports the pure function VS-025 calls (§3.6). |
| Self-cancel and admin cancel | **VS-031** | Both give 409 on `pending_payment` (`docs/vertical-slice-plan.md:851`). Only the hold release cancels such orders. |
| Cron liveness and external paging (Sentry, uptime) | **VS-047** | VS-024's alerts are in-app, email and log records VS-047 can route. |
| Offer checkout | VS-041 | It reuses retry and release unchanged (`source = 'offer'` is just another order). |

---

## 2. API and jobs

All routes return RFC 9457 problems with stable codes. New codes, added to
api-endpoints §5.2: `PAYMENT_AMOUNT_MISMATCH` (422), `PAYMENT_REFERENCE_MISMATCH` (409),
`MANUAL_CONFIRMATION_NOT_ALLOWED` (409). Existing codes reused: `PAYMENT_ALREADY_ACTIVE`
(`api-endpoints.md:186`), `INVALID_STATE_TRANSITION` (`:184`),
`PAYMENT_VERIFICATION_UNAVAILABLE` (`:210`), `PAYMENT_METHOD_NOT_ALLOWED`,
`PAYMENT_PROVIDER_UNAVAILABLE`, `ONLINE_PAYMENT_UNAVAILABLE`, `IDEMPOTENCY_*`.

### 2.1 `POST /api/v1/me/orders/{order_id}/payments` — retry (resolves item 1)

**Who may call:** the order's owner, verified, with `X-CSRF-Token`, through
`verified_user_short_read` (`identity/api/dependencies.py:173-186`).
- That dependency ends its own transaction before the handler runs, as checkout's does
  (ADR-032 d8).
- The owner check is in the lock SQL itself (`… WHERE id = :order_id AND user_id = :me
  FOR UPDATE`). An unknown order and another user's order give the same `404`.
- Administrators cannot retry for a customer.

**Request** (`extra="forbid"`; no amount is accepted, the snapshot total is charged):

```text
payment_provider?: str      # default: the previous attempt's provider if still configured,
                            # else the single configured provider
```

**Idempotency, scoped per order and per user:**
- Scope `payment_retry:{order_id}`.
- The claim's unique key is `UNIQUE NULLS NOT DISTINCT (scope, user_id, key)`
  (`uq_idempotency_records_scope_user_key`, `platform/infrastructure/models.py:215-219`;
  `scope` is unbounded `TEXT`, `:202`).
- So one key is one retry of one order by one user:
  - the same key on another order is a new, independent claim;
  - the same key from another user is a new claim, and never replays this user's
    response;
  - the same key and order with a different `payment_provider` is
    `409 IDEMPOTENCY_KEY_CONFLICT`.
- The request hash covers `{payment_provider}`; the order is already in the scope.
- Claims live 24 h and are purged by the existing daily job, whatever their scope
  (`jobs/purge_idempotency.py`).

**Two transactions, as checkout** (`ordering/api/checkout.py:288-352`):
- **Tx1:**
  1. Claim the key.
  2. `SELECT … FROM orders WHERE id AND user_id FOR UPDATE`.
  3. Run T1 (§3.1) on the locked row and on its lines, read without a lock.
  4. Read the order's payments without a lock.
  5. INSERT the pending attempt inside `begin_nested()` (a SAVEPOINT).
  6. INSERT audit `payment.retry_started` `{order_id, payment_id, provider}`. There is no
     URL in it.
  7. Attach the order to the claim, then COMMIT.
- **Provider call:** `create_payment` with no transaction open, bounded at
  `PROVIDER_TIMEOUT_SECONDS`.
- **Tx2:** `record_provider_reference`, or `fail_attempt` (`payments/application/services/payments.py:32-58`),
  then store the response.

**The one-live-payment index → a clean 409:**
- The INSERT in step 5 can violate `uq_payments_one_live`
  (`payments/infrastructure/models.py:111-116`). That happens when a live attempt exists,
  or appeared since step 4.
- The `IntegrityError` is caught **inside the SAVEPOINT**. Its constraint name is read
  the same way `SqlOrderStore` reads it (`ordering/infrastructure/orders.py:61-64`) and
  mapped to `PaymentAlreadyActiveError` → `409 PAYMENT_ALREADY_ACTIVE`.
  - Any other `IntegrityError` is re-raised (a 500, never disguised).
- Raising the 409 rolls back Tx1, and the claim with it (ADR-032 d7). The same key works
  again once the live attempt fails or expires.
- `uq_payments_one_cash` cannot fire: a retry is online-only (T1 refuses a cash order).

**Response `201 PaymentRetryRead`:**

```text
order:   {id, order_number, status: "pending_payment", total_cents, currency, hold_expires_at}
payment: {id, status: "pending", provider, amount_cents, currency, redirect_url}
```

**`redirect_url`: only to the owner, never logged:**
- It appears only in the `201` and in the `409 PAYMENT_ALREADY_ACTIVE` body. Both are
  built **after** the owner-predicate lock, so another user only ever gets the identical
  404.
- The URL comes from `payments.provider_metadata` (`payments/infrastructure/payments.py:98`).
- It is stored only in two places:
  - `payments.provider_metadata`, which no admin response returns (§2.2);
  - the claim's `response_body`, which replays only to the same user, key and order.
- It is never in an audit row, a log field or a problem `detail`.
- The error handler logs only the path and the exception type
  (`api/errors.py:150`, `:161`). Production logs render tracebacks without locals
  (`core/logging.py:189`).
- No framework logs locals: `format_exc_info` runs before both renderers
  (`core/logging.py:186-189`), `rich` and `better_exceptions` are not installed, and
  FastAPI runs with `debug=False` (`main.py:50`). This is Revision 2, Q9.
- A test captures every log record during a 201, a 409 and a 502 retry, and asserts the
  URL string appears in none (§6.2).

**Errors:**

| Status | Code | When |
|---|---|---|
| 401 / 403 | `AUTH_REQUIRED` / CSRF / `EMAIL_VERIFICATION_REQUIRED` | as checkout |
| 404 | `NOT_FOUND` | unknown order, or not the caller's |
| 409 | `PAYMENT_ALREADY_ACTIVE` | a `pending` or `processing` attempt exists. The body has `payment_id`, `status` and `redirect_url` (null while `processing`), so the client can resume the live attempt. |
| 409 | `INVALID_STATE_TRANSITION` | `reason` is one of `cash_order`, `order_not_payable`, `order_cancelled`, `checkout_hold_expired` |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS` | as checkout (ADR-032 d13) |
| 422 | `PAYMENT_METHOD_NOT_ALLOWED` | `provider_not_configured` or `provider_required` |
| 422 | `VALIDATION_ERROR` | schema |
| 429 | `RATE_LIMITED` | `RETRY_RATE_LIMIT` per user per `RETRY_RATE_WINDOW`; fail closed; a replay counts |
| 502 | `PAYMENT_PROVIDER_UNAVAILABLE` | the attempt was failed in Tx2 and the order is still payable; replayed for the same key |
| 503 | `ONLINE_PAYMENT_UNAVAILABLE` | `PAYMENT_PROVIDER=none`; nothing written |

**Not checked, on purpose:**
- `accepting_orders` (BR-040, `SRS.md:217`; `docs/vertical-slice-plan.md:618`).
- Live price or availability (the order is an immutable snapshot).
- STL ownership. The order's own `pending` lines hold `uq_order_items_stl_ownership`
  (`ordering/infrastructure/models.py:316-323`). T1 instead requires every line to be
  `pending` (owner question 3).

### 2.2 Admin payments (`/api/v1/admin/payments…`)

Mounted on the admin router, so every route inherits `require_admin` (an administrator
with MFA complete) and `admin_rate_limit` (`api/v1/admin.py:62-86`).
- A customer gets the byte-identical 404 (SEC-10).
- Writes also take `require_csrf`.
- No response includes `provider_metadata` (so no `redirect_url`), webhook payloads or
  the customer's email.

**`GET /api/v1/admin/payments` → `200 PaymentPage`**
- Cursor `(initiated_at, id)`, oldest first.
- Filters: `status` (repeatable), `provider`, `order_id`, `initiated_after` and
  `initiated_before` (each with a UTC offset), `late_captured`, `needs_attention`.
- `needs_attention` is true for:
  - a live attempt older than `STUCK_AFTER`;
  - an attempt awaiting manual confirmation;
  - a late capture;
  - an order whose manual release is due.
- `limit` defaults to `ADMIN_PAGE_DEFAULT` and is at most `ADMIN_PAGE_MAX`.
- Not audited: the page carries no personal data beyond the order number.

`PaymentSummary`:

```text
id, order_id, order_number, provider, status, amount_cents, currency,
captured_amount_cents, captured_currency, provider_payment_id,
initiated_at, verified_at, failed_at, expired_at, late_captured_at,
needs_manual_confirmation: bool, unprocessed_event_count: int,
last_provider_answer: {state, at, source} | null      # from the latest verification audit row
```

**`GET /api/v1/admin/payments/{payment_id}` → `200 PaymentDetail`**
- The summary, plus `order {status, total_cents, placed_at, cancelled_at,
  hold_expires_at, manual_release_available_at}`.
- `events[]` without payload, and `history[]`, the audit rows via `ix_audit_logs_entity`
  (`platform/infrastructure/models.py:109`).
- `available_actions ⊆ {"reconcile", "confirm", "release_order"}`, computed by the same
  pure rules the POSTs use.

**`POST /api/v1/admin/payments/{payment_id}/reconcile` → `202` (D8)**

Sequence; nothing in steps 1-4 calls the provider:

1. **The boundary.** `require_admin` → `current_claims` reads `users.auth_epoch` through
   `get_session` (`identity/api/dependencies.py:63-88`). That opens the request's unit of
   work, `async with session_factory() as session, session.begin()`
   (`api/dependencies.py:20-22`).
2. **The handler:**
   - an unlocked `SELECT … FROM payments WHERE id`;
   - `404` for an unknown id;
   - `409 INVALID_STATE_TRANSITION` for a `cash` payment;
   - `503 PAYMENT_VERIFICATION_UNAVAILABLE` for a provider without a status query;
   - a reconcile limit of `RECONCILE_RATE_LIMIT` per admin.
   Then it INSERTs audit `payment.reconcile_requested` (actor, request id, IP hash), calls
   `background.add_task(reconcile_in_background, factory, providers, payment_id,
   admin_id)` and returns `202 {payment: PaymentDetail, reconcile: "queued"}`.
3. **FastAPI leaves the function scope:** the unit of work COMMITs and closes its session
   **before** the response is sent (`api/dependencies.py:12-19`).
4. **Starlette sends `http.response.start` and `http.response.body`, and only then awaits
   the background task** (`.venv/Lib/site-packages/starlette/responses.py:168-172`,
   Starlette 1.7.0). The webhook already relies on exactly this
   (`payments/api/webhooks.py:134-136`, ADR-032 d16).
5. **The background task is `verify_payment(…, source="manual_reconcile",
   actor_user_id=admin)`:**
   - Tx A: `async with factory() as session, session.begin()`, a read that is closed
     before `_ask` runs;
   - the provider query with no session, bounded at `PROVIDER_TIMEOUT_SECONDS`;
   - Tx B in a fresh session (`payments/infrastructure/verification.py:95-110`).
   **So no transaction is open during the provider call.**
6. **Failure handling:**
   - `ProviderUnavailableError` or an `unknown` answer → audit `payment.reconcile_deferred
     {reason}` in its own short transaction;
   - any other exception → `logger.aexception("payment_reconcile_background_failed")`,
     as `verify_in_background` does (`verification.py:126-131`).
7. **If the task dies** (worker restart, crash, an exception before Tx B):
   - **A live attempt** (`pending` / `processing`) is picked up by the next
     `reconcile_payments` run. That is at most 15 min later, and the attempt is already
     older than `RECONCILE_MIN_AGE` if an admin is reconciling it.
   - **A dead attempt** (`failed` / `expired`, a late-capture hunt) is not a job
     candidate. The detail then shows `reconcile_requested` with no result after it, and
     the admin asks again.

### 2.3 `POST /api/v1/admin/payments/{payment_id}/confirm` — manual confirm (resolves item 3, Must-resolve item 2)

**Authorization:**
- The admin router's `require_admin`: role `admin`, MFA complete. A customer gets 404 and
  an admin without MFA gets 401 (`api/v1/admin.py:17-20`, `:84`).
- `admin_rate_limit` (300/min per admin, `:56-78`) and `require_csrf`.
- `CONFIRM_RATE_LIMIT` per admin per hour.
- The provider is never called, so the request's own unit of work is the transaction.

**Request `ManualPaymentConfirmRequest`** (`extra="forbid"`):

```text
provider_reference: str (1..255)    # the transaction id on the provider dashboard
verified_amount_cents: int (>= 0)   # the captured amount the dashboard shows
verified_currency: str(3) = "USD"
reason: str (REASON_MIN..REASON_MAX) # mandatory: what the admin checked and why
```

`api-endpoints.md:1166-1171` names the field `evidence_note`; it becomes `reason`, the same
word the manual release uses.

**Order of checks:**

1. Unlocked read of the payment.
   - Unknown → `404`.
   - `provider = 'cash'` → `409 INVALID_STATE_TRANSITION` (ADR-024 appendix `:130`).
2. A configured adapter with `supports_status_query = True` → `409
   MANUAL_CONFIRMATION_NOT_ALLOWED` (D7; ADR-012 `:13`).
3. **The amount guard.** `verified_amount_cents != payment.amount_cents`, or
   `verified_currency != "USD"`, gives `422 PAYMENT_AMOUNT_MISMATCH` with
   `expected_amount_cents` and `currency`.
   - The transaction is rolled back, so **no payment, event, line, order, audit or alert
     row is written, and no late capture is recorded**.
   - One structured warning `payment_manual_confirm_refused {payment_id, admin_id}` is
     logged, without the amount or the reason text.
   - The attempt amount equals the order total for every attempt that checkout or retry
     opens, so the guard enforces "exactly the order total".
   - **Consequence:** `decide` never receives a mismatched amount from this path, so a
     manual confirm can never produce `LATE_CAPTURE_AND_FAIL`.
4. **`apply_result`** (`payments/application/services/apply.py:24-64`) is called with
   `ProviderResult("paid", verified_amount_cents, "USD")`, `source="manual"`,
   `actor_user_id=admin` and `provider_payment_id=provider_reference`. This is the same
   function, decision table (`domain/outcome.py:37-68`) and locks as webhook
   verification:
   - an unlocked `SELECT payments WHERE id` to learn the order (`apply.py:39`);
   - `SELECT … FROM orders WHERE id FOR UPDATE`, then `SELECT … FROM order_items WHERE
     order_id ORDER BY id FOR UPDATE` (`ordering/public.py:49-55`,
     `ordering/infrastructure/orders.py:158-173`);
   - `SELECT … FROM payments WHERE id FOR UPDATE` (`apply.py:43`);
   - the outcomes:
     - **live attempt on an uncancelled order** → `APPLY_PAID` (STL lines
       `awaiting_delivery`, history, the customer email and notification);
     - **attempt `failed` / `expired`, or the order cancelled** → `LATE_CAPTURE`
       (exact amount, SRS §9.2 `SRS.md:757`);
     - **already paid** → `NOOP`.
5. **The reference check, under the payment lock.**
   - A stored `provider_payment_id` that differs from the given one → `409
     PAYMENT_REFERENCE_MISMATCH`, rolled back.
   - A reference already used by another payment raises `uq_payments_provider_reference`
     (`payments/infrastructure/models.py:82`) and gives the same 409.
6. `UPDATE webhook_events SET processed_at = :now WHERE payment_id = :id AND processed_at
   IS NULL`, last (`ix_webhook_events_payment_unprocessed`, `models.py:171-175`).
7. **Audit row `payment.manual_confirmation`:** `actor_user_id = admin`, `entity_type =
   'payment'`, `entity_id`, `request_id`, `ip_hash`, and `after_data`:

   ```text
   {order_id, order_number, typed_amount_cents, typed_currency, provider_reference,
    reason, outcome, attempt_status_before, events_marked_processed}
   ```

   `apply_result` also writes its own `payment.verified` or `payment.late_capture` row,
   now with the admin as actor (§3.4).
8. **Response:** `200 PaymentDetail` with `outcome`. A double submit gets `NOOP`, so
   confirm needs no `Idempotency-Key`.

**Consequence of 3:** on a provider without a status API, a customer who paid a different
amount has no row in the platform. The admin refunds it in the provider dashboard and
releases the order (§2.5), stating that in the reason. The money risk is case R-f (§2.5);
whether VS-030 adds a "record mismatched capture" action is owner question 2.

### 2.4 Jobs (`src/app/jobs/registry.py`)

| Job | Cadence (`app.payments.domain.limits`) | Body | Bounds |
|---|---|---|---|
| `reconcile_payments` | `RECONCILE_CRON_MINUTES = {0,15,30,45}`, `second=30`, `run_at_startup=True` | §3.2 | pages of `RECONCILE_PAGE_SIZE`, keyset `(initiated_at, id)`; sequential queries; `JOB_RUN_DEADLINE_SECONDS`; breaker after `PROVIDER_BREAKER_FAILURES` |
| `release_stale_checkouts` | `RELEASE_CRON_MINUTES = {2,7,…,57}`, `second=45`, `run_at_startup=True` | §3.1 T2 | pages of `RELEASE_PAGE_SIZE`, keyset `(placed_at, id)`; same deadline and breaker |
| `verify_payments` (VS-023) | unchanged (`registry.py:46`) | skips events awaiting manual confirmation (D11) | `VERIFY_BATCH_SIZE` |

- `JOB_RUN_DEADLINE_SECONDS` (240) is under arq's default 300 s `job_timeout`, which
  `worker.py:55-64` does not override.
- Overlapping runs are safe: each one re-checks under the orders lock (§8.1).

### 2.5 `POST /api/v1/admin/orders/{order_id}/release` — manual admin release (D13)

**Why it exists:** the job never releases without an explicit `failed` / `expired` (T2).
Without a manual exit, the following would stay `pending_payment` for ever, keeping the
attempt live (retry gets `PAYMENT_ALREADY_ACTIVE`) and the STL reserved:
- an order on a provider with no status API;
- an attempt the provider keeps calling `pending`, `processing` or `unknown`;
- an attempt whose only capture was a mismatched late capture.

This is the dead end of Must-resolve item 1 (`docs/vertical-slice-plan.md:648`).

**Where it lives:** `app.ordering.api.admin_release`, mounted on the admin router. VS-029
adds the rest of `/admin/orders` beside it.

**Authorization:** the same as confirm: admin, MFA, `require_csrf`, `admin_rate_limit`,
and `RELEASE_RATE_LIMIT` per admin per hour. The provider is never called.

**Request** (`extra="forbid"`):

```text
reason: str (REASON_MIN..REASON_MAX)   # mandatory, e.g. "dashboard shows no payment; customer
                                       # confirmed abandonment by phone"
events_reviewed: bool = false          # required true when unprocessed events exist
```

**The grace:**
- The release is available from `hold_deadline + MANUAL_RELEASE_GRACE` (24 h, §3.8).
- That holds for every provider. For one without a status API it is the only way an
  unpaid order ends.
- The job raises `release_due` (once per order) when the grace passes for an order it
  cannot release. `PaymentDetail.order.manual_release_available_at` shows the time.
- **The one early exception (Revision 2, Q7):** if the latest attempt has **no**
  `provider_payment_id` and its latest provider answer is `unknown`, the release is
  available from `hold_deadline` itself.
  - Any stored provider reference rules this out; that attempt waits for the full grace.
  - `manual_release_refusal` and its unit tests cover both branches.

**Transaction (the request's unit of work; the same locks as the job's Tx B, §8.1):**

1. `SELECT … FROM orders WHERE id FOR UPDATE` (unknown → `404`).
2. `SELECT … FROM order_items WHERE order_id ORDER BY id FOR UPDATE`.
3. `SELECT … FROM payments WHERE order_id ORDER BY id FOR UPDATE`.
4. `SELECT count(*) FROM webhook_events WHERE payment_id = ANY(:ids) AND processed_at IS
   NULL`, unlocked.
5. **Checks, each `409 INVALID_STATE_TRANSITION` with a `reason`:**
   - `cash_order`;
   - `order_cancelled`;
   - `order_not_payable` (not `pending_payment`, i.e. a payment reached paid);
   - `grace_not_elapsed` (with `release_available_at`);
   - `unprocessed_events` (with `count`), when events exist and `events_reviewed` is
     false.
6. **Writes:**
   - each live attempt → `expired` (`expired_at`), audit `payment.expired {source:
     "admin_release"}` with the admin as actor;
   - if `events_reviewed`, the unprocessed events → `processed_at`, `processing_error =
     'dismissed_by_admin'`;
   - `release_unpaid_order(..., actor_user_id=admin, reason="released_by_admin")`
     (§3.6);
   - **audit row `order.checkout_released`**, `actor_user_id = admin`, `request_id`,
     `ip_hash`, with `after_data`:

     ```text
     {source: "admin", reason, hold_deadline, attempts_expired[], events_dismissed[]}
     ```

   - the customer notification and email, as for the automatic release.
7. **Response:** `200 {order_id, status: "cancelled", cancelled_at}`. A repeat gets
   `409 order_cancelled`.

**Money risk of releasing an order whose payment later arrives, and the test for each
case:**

| # | Case | What happens to the money | Until VS-030 | Test (§6.2 / §6.3) |
|---|---|---|---|---|
| R-a | The provider said `expired` (auto release), and the customer pays anyway | The webhook verification records a late capture (`attempt_not_live`, `apply.py:140-145`) with `captured_*`. It is never applied to the order. | Alert to every admin, plus `?late_captured=true`. The admin refunds in the dashboard. | `test_late_success_after_automatic_release_is_a_late_capture` |
| R-b | Manual release on a no-status provider; the customer had paid and the webhook was lost | The platform never learns of it. The refund depends on the admin's dashboard check, recorded in `reason`. | `reason` in `order.checkout_released`. A later confirm (exact amount) on the expired attempt is a late capture. | `test_confirm_after_manual_release_records_late_capture_not_payment` |
| R-c | Manual release with `events_reviewed` dismisses an event that was a real payment | The events are marked `dismissed_by_admin`. A later event for the same payment is stored and verified (status providers) as a late capture. | Audit lists `events_dismissed`. | `test_release_with_reviewed_events_dismisses_them_and_a_later_event_is_a_late_capture` |
| R-d | The customer re-buys the freed STL, then the old capture arrives | Two captures; the old one is a late capture and the new order is untouched. | Alert; refund one. | `test_rebuy_after_release_then_old_capture_leaves_new_order_paid` |
| R-e | Manual release during a provider outage on a status provider | After recovery, reconcile or the webhook finds the capture → late capture. | Alert. | `test_capture_found_after_outage_on_released_order` |
| R-f | A mismatched amount captured (before or after release) | Through verification: `LATE_CAPTURE_AND_FAIL` or `LATE_CAPTURE` with the captured amount stored. Through manual confirm: 422, nothing recorded (§2.3). | Admin refunds in the dashboard; reason on the release. | `test_mismatch_via_verification_is_late_capture`, `test_mismatch_via_confirm_is_422_and_writes_nothing` |
| R-g | Fees on the capture and the refund; a chargeback if the refund is slow | A business loss outside the platform. | Alert latency is minutes (the next job run), not days. | risk only (§9) |

## 3. Layers, function by function

### 3.0 Package ownership (unchanged from ADR-032 d6)

- **Ordering** owns:
  - the retry route and service;
  - the hold-release row changes (`orders.cancelled_at`, lines → `cancelled`, history,
    status recompute);
  - the pure retry and hold rules.
- **Payments** owns:
  - the two jobs' bodies, the admin payment routes and manual confirm;
  - the alerts, the `unknown` answer and the store additions.
- Payments calls `app.ordering.public`. Ordering reaches Payments only through its
  `PaymentAttempts` port (`ordering/application/ports.py:73-80`), extended in §3.4.

### 3.1 Pure rules (no I/O)

**`app.ordering.domain.payment_recovery`** (new):

- `hold_deadline(placed_at, latest_attempt_initiated_at | None, hold) -> datetime` returns
  `max(placed_at, initiated_at) + hold` (D4).
- `manual_release_available_at(deadline) -> datetime` returns
  `deadline + MANUAL_RELEASE_GRACE`.
- `retry_refusal(order, lines, now, hold) -> RetryRefusal | None` implements **table T1**.
  The first matching row wins.

  | Condition (read under the orders lock) | Refusal |
  |---|---|
  | `payment_method = cash` | `cash_order` |
  | `cancelled_at IS NOT NULL` | `order_cancelled` |
  | `status <> pending_payment`, or any line not `pending` | `order_not_payable` |
  | `now >= placed_at + hold` | `checkout_hold_expired` |
  | otherwise | None; a live attempt is caught by the index (§2.1) |

- `can_retry_payment(...) -> bool` applies the same table without the lock, for VS-025.
- `manual_release_refusal(order, live_events, now, deadline, events_reviewed)` covers the
  §2.5 checks.

**`app.payments.domain.release.release_action(...)` — table T2: what the job does** (D5).
- Inputs:
  - the order's latest attempt (by `initiated_at, id`), with its stored status;
  - the adapter capability: `status_query`, `no_status_query` or `not_configured`;
  - the count of unprocessed events on any of the order's attempts;
  - the provider answer for the latest attempt: a `ProviderResult`, `unavailable`
    (error or timeout), or not asked.
- Outputs: `RELEASE`, `APPLY_ONLY` or `SKIP(alert_kind | None)`.
- Candidates are orders past `hold_deadline` (§3.4).

| Precondition / answer | Job action | Why |
|---|---|---|
| Any unprocessed event on any attempt of the order | `SKIP(event_unverified` or `manual_confirmation_due)`; **not asked** | An event may be a payment (ADR-024 d15 `:53`) |
| Capability `no_status_query` or `not_configured` | `SKIP(release_due` once the grace has passed, else None) | Nothing can confirm "unpaid": manual release only |
| Answer `failed` | Tx B: `apply_result` (marks the attempt `failed`, or NOOP if it already is), then **`RELEASE`** | Explicit |
| Answer `expired` | Tx B: `apply_result` (marks it `expired`), then **`RELEASE`** | Explicit |
| Answer `paid`, exact, attempt live | `APPLY_ONLY` → `APPLY_PAID`; never released | The payment wins |
| Answer `paid`, mismatch or attempt dead | `APPLY_ONLY` → late capture; **not released** | Money arrived, so a human decides: the alert, then manual release after the grace |
| Answer `pending` or `processing` | `SKIP(stuck` if older than `STUCK_AFTER`; `release_due` once the grace has passed`)` | Not explicit |
| Answer `unknown` | `SKIP(reference_unknown)`; nothing written | D10 |
| `unavailable`: error, timeout, breaker open | `SKIP(provider_unavailable)`; nothing written | Never cancel what cannot be checked |

**Notes on T2:**
- **The latest attempt is asked even when it is already `failed` / `expired` in the
  database.**
  - A `failed` written by checkout's or retry's Tx2 after a `create_payment` error
    (`payments/application/services/payments.py:41-58`) is our own conclusion, not the
    provider's answer.
  - Asking again also catches a late success before the order is cancelled.
- **Older attempts are not asked.** A late success on one of them reaches us through its
  webhook or an admin reconcile, and is a late capture either way.
- **`RELEASE` re-checks under the locks:** still `pending_payment`, the same latest
  attempt, no new unprocessed event, and the deadline still passed. Otherwise it skips
  this run.

**`app.payments.domain.outcome.decide`:** one explicit branch, placed first:
`result.state == "unknown"` → `Outcome.NOOP` (§3.2a). Every existing row is unchanged
(`outcome.py:48-68`).

**`app.payments.domain.manual.confirm_refusal(payment, capability, typed_amount,
typed_currency)`** is the pure form of §2.3 steps 1-3.

### 3.2 `app.payments.application.services.reconcile` (new)

```python
async def reconcile_stuck(factory, providers, *, now) -> dict[str, int]:
    """The `reconcile_payments` body: pages of stale live attempts; Tx A / query / Tx B each."""
```

**Candidates** (unlocked, keyset-paged, `RECONCILE_PAGE_SIZE`):

```sql
SELECT id FROM payments
WHERE status IN ('pending','processing') AND order_payment_method = 'online'
  AND initiated_at <= :now - :reconcile_min_age
  AND (initiated_at, id) > (:after_at, :after_id)
ORDER BY initiated_at, id LIMIT :page
```

- Served by `ix_payments_unsettled` (`payments/infrastructure/models.py:124-129`).
- No row is locked (ADR-024 d9 `:26`).

**Each candidate** goes through `verify_payment(…, source="reconcile")`
(`verification.py:92-110`): Tx A, the query bounded at `PROVIDER_TIMEOUT_SECONDS`, then
Tx B (`orders → lines → payment`).
- A missing reference is stored under those locks (`apply.py:46-47`). This recovers the
  checkout Tx2-crash attempt that the provider knows.
- An `unknown` answer writes nothing (§3.2a).

**Skipped without a query:**
- no status API → `manual_confirmation_due`, once per payment;
- provider not configured → `provider_not_configured`.

**Provider down:** `ProviderUnavailableError` counts as deferred and writes nothing.
After `PROVIDER_BREAKER_FAILURES` consecutive failures for a provider, the rest of the run
skips it, with one `provider_unreachable` alert per `ALERT_REPEAT_PER_PROVIDER`.

**Stuck:** a candidate still live and older than `STUCK_AFTER` raises `stuck`, once per
`ALERT_REPEAT_PER_PAYMENT`.

**Returns** `{seen, applied, deferred, unknown, skipped_manual, skipped_unconfigured,
breaker_open, truncated}`.

### 3.2a `unknown`: every place that matches on `ProviderState`, and what it does

From `grep -rn "ProviderState|result.state|_STATES|choices=" src scripts tests`:

| Place | Today | With `unknown` |
|---|---|---|
| `payments/domain/outcome.py:10`, the `ProviderState` Literal | five values | gains `"unknown"` |
| `outcome.py:22`, `ProviderResult.state` | typed by the Literal | unchanged |
| `outcome.py:48`, `== "paid"` | the paid branch | new first branch `if result.state == "unknown": return Outcome.NOOP`. It would already fall through `:60` / `:68` to NOOP; the explicit line pins the intent. |
| `outcome.py:60-68`: `not in LIVE`, `processing`, `failed`, `expired` | — | never reached for `unknown` |
| `payments/application/services/apply.py:58-63`, outcome dispatch | writes per outcome | `NOOP` writes nothing |
| `payments/infrastructure/verification.py:70-89`, `verify_event` | applies, then marks the event processed (`:88`) | `unknown` **does not call apply** and **does not mark processed**. It calls `record_error(event, "provider_unknown_reference")`, keeping the event unprocessed so T2 keeps skipping the order, plus a `reference_unknown` alert. The next `verify_payments` run asks again. |
| `verification.py:92-110`, `verify_payment` | Tx A, query, Tx B | `unknown` returns `Outcome.NOOP` **without opening Tx B**, and raises the alert |
| `reconcile_stuck` (§3.2) | — | counted as `unknown`; nothing written |
| `release_action` (T2) | — | `SKIP(reference_unknown)` |
| admin reconcile background (§2.2) | — | audit `payment.reconcile_deferred {reason: "unknown"}` |
| `payments/infrastructure/providers/mock.py:94-95` | an absent state answers `pending` | answers `unknown` |
| `mock.py:32` `_STATES`, `:152` `_state()` (stored states) | five values | unchanged: `unknown` is never stored |
| `mock.py:126`, `simulate(state: ProviderState)` | — | raises `ValueError` for `"unknown"`; tests cannot store it |
| `scripts/mock_pay.py:17`, `:81` (`choices=STATES`) | paid / processing / failed / expired | unchanged |
| `tests/integration/payments/test_mock_provider.py:76-79` | never-created → `pending` | expects `unknown`; renamed `…_is_unknown_…` |
| `tests/unit/payments/test_outcome.py:88` parametrize | four states | gains `unknown` |
| `tests/contract/payments/test_provider_contract.py:67`, `tests/integration/ordering/test_checkout_crash_window.py:141`, `tests/security/test_payment_security.py:177` | a **created** payment → `pending` | unchanged (the mock knows them) |

**The consequence for the checkout crash window**, where Tx1 committed and the provider
was never called:
- the provider answers `unknown`;
- the attempt stays `pending`;
- retry gets `409 PAYMENT_ALREADY_ACTIVE` with `redirect_url: null`;
- the order ends only by manual release after the grace. That is risk R10, and owner
  question 7.

**Tests that `unknown` never moves anything** (§6.1, §6.2):
- **Unit:** `decide(unknown)` is `NOOP` for every `PaymentStatus` × `order_cancelled` ×
  `already_late_captured`, and `release_action(unknown)` is never `RELEASE`.
- **Integration**, one test per entry point: `verify_event`, `verify_payment` /
  reconcile, the release job, and the admin reconcile background, each with the mock
  answering `unknown`. Each asserts that these are unchanged:
  - payment `status`, `failed_at`, `expired_at`, `verified_at`, `late_captured_at`;
  - order `status`, `cancelled_at`;
  - every line's `fulfillment_status`;
  - no history row;
  - the event still unprocessed;
  - exactly one `reference_unknown` alert.

### 3.3 `app.payments.infrastructure.verification` (change)

- `_ask` wraps `adapter.query_status` in `asyncio.timeout(PROVIDER_TIMEOUT_SECONDS)`
  (today it is unbounded, `verification.py:53-57`) and maps `TimeoutError` to
  `ProviderUnavailableError`.
- `verify_event` with `supports_status_query = False` does not query. It records
  `processing_error = 'manual_confirmation_required'`, leaving the event unprocessed, and
  raises `manual_confirmation_due` once.
- `unknown` is handled as described in §3.2a.
- `SqlWebhookEventStore.unprocessed_ids` excludes `processing_error =
  'manual_confirmation_required'`, which removes the head-of-line block
  (`webhook_events.py:46-54`).
- `verify_payment` gains `source` (`reconcile | release | manual_reconcile`) and
  `actor_user_id`.

### 3.4 Ports and stores (extend)

**`app.payments.application.ports`:**

- `PaymentProviderPort`:
  - `supports_status_query` is now honoured by every caller (today it is declared,
    `ports.py:58`, and never read; `grep` finds only the mock and a contract assertion);
  - `query_status` documents the `unknown` answer.
- `PaymentStore` additions:
  - `lock_for_order(order_id) -> list[Payment]`: `FOR UPDATE ORDER BY id`. Called only
    after `lock_order_for_change`.
  - `live_for_order(order_id) -> Payment | None`: unlocked.
  - `previous_provider(order_id) -> PaymentProvider | None`: unlocked.
  - `stale_live_ids(now, min_age, after, limit)`: unlocked.
  - `page(filters, cursor, limit)` and `detail(payment_id)`: admin reads.
  - `mark_late_capture(..., captured_amount_cents, captured_currency)`: extended.
  - `mark_paid(..., captured_amount_cents, captured_currency)`: extended, records the
    exact amount.
- `Payment` gains `initiated_at`, `captured_amount_cents`, `captured_currency` and
  `redirect_url`.
- `OrderSide` gains `release(locked, *, at, reason, actor_user_id) -> tuple[UUID, ...]` (the lines
  cancelled).
- **`PaymentAlerts`** (new):
  `async def raise_alert(kind, *, payment_id, order_id, details, dedupe_window) -> bool`.
- **`LateCaptureSink`** (new, the VS-030 hook):
  `async def late_capture_recorded(locked, payment, *, captured_amount_cents,
  captured_currency, reason, at) -> None`.
- `WebhookEventStore`:
  - `mark_processed_for_payment(payment_id, at)`;
  - `count_unprocessed_for_payment(payment_id)` (served by
    `ix_webhook_events_payment_unprocessed`);
  - `record_error` is reused for `manual_confirmation_required`.

**`app.payments.application.services.apply`** (change):

- `Source` gains `"release"`, `"admin_release"` and `"manual_reconcile"`.
- `_paid`, `_status` and `_late_capture` record `actor_user_id` (today `None`,
  `apply.py:81`, `:118`, `:160`).
- `_paid` stores the captured amount.
- `_late_capture` stores `captured_amount_cents` / `captured_currency`, then calls
  `LateCaptureSink.late_capture_recorded` (VS-024: the alert; VS-030: plus the refund).
- No change to the decision or the lock sequence (`apply.py:39-57`).

**`app.ordering.application.ports.PaymentAttempts`** (extend, `ports.py:73-80`):

- `live_attempt(order_id) -> PaymentAttemptRef | None`, with its `redirect_url`;
- `previous_provider(order_id) -> str | None`;
- `open_attempt(...)`, unchanged, reused by retry.

**`app.ordering.infrastructure.orders.SqlOrderStore`** (extend):

- `set_cancelled(order_id, at)`: the first writer of `orders.cancelled_at`.
- `set_line_status(..., cancelled_at=at)`: also sets `order_items.cancelled_at` for the
  cancelled transition.
- `lock_owned_order(order_id, user_id)`: `FOR UPDATE` with the ownership predicate.
- `release_candidates(now, hold, after, limit)`, unlocked:

  ```sql
  SELECT id FROM orders
  WHERE status = 'pending_payment' AND payment_method = 'online'
    AND placed_at <= :now - :hold
    AND (placed_at, id) > (:after_at, :after_id)
  ORDER BY placed_at, id LIMIT 50
  ```

  - Served by `ix_orders_status_placed (status, placed_at DESC)`
    (`ordering/infrastructure/models.py:203`).
  - `pending_payment` already implies online and uncancelled
    (`ordering/domain/order_status.py:39-42`); the explicit `payment_method` filter is a
    belt for VS-028's seeded cash rows.

### 3.5 Alerts (`app.payments.infrastructure.alerts.SqlPaymentAlerts`, new)

- **Kinds:**
  - `late_capture`: once per payment, inside Tx B;
  - `stuck`: 24 h;
  - `manual_confirmation_due`: once per payment;
  - `event_unverified`, `provider_unavailable`: 24 h per payment;
  - `release_due`: once per order, when the grace passes (§2.5);
  - `provider_unreachable`: per provider, 1 h;
  - `provider_not_configured`: 24 h;
  - `reference_unknown`: once per payment.
- **De-duplication through the audit log:**
  - Before raising, read `audit_logs WHERE entity_type = 'payment' AND entity_id = :id
    AND action = 'payment.alert_raised' AND after_data->>'kind' = :kind AND created_at >
    :now - :window` (`ix_audit_logs_entity`; the monthly partitions prune on
    `created_at`).
  - Then write that audit row.
  - `provider_unreachable` uses `ix_audit_logs_action_created_at` with
    `entity_id IS NULL`.
  - Why not Redis: a Redis outage would either drop alerts or repeat them every 5 min,
    and the audit row is itself the operator's record.
- **Delivery, each in its own SAVEPOINT** (the FR-15 precedent,
  `engagement/application/commands/submit_custom_request.py:106-119`), so a failed alert
  never rolls back a money write:
  - an in-app notification per active administrator: category `payment` (already in the
    enum, `engagement/domain/enums.py:10`, so no DDL), `payload.event =
    "payment.alert.<kind>"`, with `payment_id`, `order_number`, amounts and reason;
  - an outbox email per active administrator: template `admin_payment_alert`. This needs
    `identity.public.active_administrator_contacts(session) -> list[(id, email)]`, a new
    read beside `active_administrator_ids` (`identity/public.py:41-43`);
  - `logger.aerror("payment_alert", kind=…, payment_id=…)` for VS-047 to route.

### 3.6 Published interfaces (resolves item 7)

**`app.payments.public`** (additions, frozen at Checkpoint 2):

```python
async def payment_reached_paid(session, order_id) -> bool        # VS-029 BR-148 gate, under the caller's orders lock
async def order_payment_state(session, order_id) -> OrderPaymentState  # VS-025 / VS-029 detail
#   OrderPaymentState(reached_paid: bool, live: PaymentAttemptRef | None,
#                     attempts: int, late_captured: int, hold_expires_at: datetime | None)
LateCaptureSink, PaymentAlerts                                   # ports VS-030 / VS-032 extend
apply_provider_result(session, payment_id, result, *, source, actor_user_id, provider_payment_id)
verify_payment(factory, providers, payment_id, *, source, actor_user_id) -> Outcome
reconcile_stuck(factory, providers, *, now) -> dict[str, int]
release_stale(factory, providers, *, now) -> dict[str, int]
```

**`app.ordering.public`** (additions):

```python
async def release_unpaid_order(session, locked: LockedOrder, *, at, reason, actor_user_id=None) -> tuple[UUID, ...]
#   orders.cancelled_at, pending lines -> cancelled (+ cancelled_at), history, recompute -> cancelled.
#   Caller holds orders + lines + payments; actor None = the job, else the releasing admin.
def can_retry_payment(order, lines, *, now, hold) -> bool        # VS-025 OrderDetail
def hold_deadline(placed_at, live_initiated_at, hold) -> datetime # VS-025 hold_expires_at
```

**What each later slice consumes:**

- **VS-029 (admin order queue, handover, BR-148):**
  - `payment_reached_paid` inside its transition transaction, after
    `lock_order_for_change`;
  - `release_unpaid_order` as the only BR-148 exception (VS-029's endpoint never calls
    it);
  - `order_payment_state` for `AdminOrderDetail`;
  - its race test "reconcile vs handover" (`docs/vertical-slice-plan.md:766`) relies on
    §8.1. `reconcile_stuck` never selects a cash order (status `pending` / `processing`
    is impossible for cash, `ck_payments_cash_shape`, `payments/infrastructure/models.py:90-94`).
- **VS-030 (refunds):**
  - replaces the `LateCaptureSink` binding with one that also INSERTs the `late_capture`
    refund (no items, no requester, `captured_amount_cents`, `captured_currency`). This
    happens in the same Tx B, after `payments`, so `refunds` comes last in the lock
    order (ADR-024 d9);
  - backfills from `payments WHERE late_captured_at IS NOT NULL`
    (`ix_payments_late_captured`), reading `captured_amount_cents`. VS-024 rows have it,
    and pre-VS-024 dev rows fall back to the `payment.late_capture` audit row's
    `captured_amount_cents` (`apply.py:152`);
  - an overpayment's refund may exceed `payments.amount_cents` (ADR-024 appendix `:98`),
    so VS-030 caps a late-capture refund by `captured_amount_cents`, not `amount_cents`.
- **VS-032 (live provider):**
  - `PaymentProviderPort` unchanged except the `unknown` answer;
  - an adapter sets `supports_status_query`, which alone switches its orders to manual
    confirmation and to manual release after the grace (T2, §2.5);
  - a shared `choose_provider(requested, configured, previous) -> str` (moved out of
    `ordering/application/services/checkout.py:58-66`) serves checkout and retry when the
    setting becomes a list;
  - contract fixtures add "unknown reference", "status timeout" and "no status API";
  - `PaymentAlerts` is the alert the go-live gate refers to.
- **VS-025:** `can_retry_payment`, `hold_deadline`, `order_payment_state`.
- **VS-028:** nothing new. Its test "a cash order is never selected by release,
  reconciliation or retry" (`docs/vertical-slice-plan.md:723`) runs against VS-024's
  queries.

### 3.7 Routes

- `app.ordering.api.payment_retry` (new) is mounted in `api/v1/me.py`. It shares
  checkout's `_replay`, `_in_progress`, `_conflict` and `_stored`, moved to
  `app.ordering.api.idempotent`.
- `app.ordering.api.admin_release` (new, §2.5) and `app.payments.api.admin_payments`
  (new, §2.2-§2.3) are mounted in `api/v1/admin.py`, after the existing routers and
  before the catch-alls.
- `app.jobs.reconcile_payments` and `app.jobs.release_stale_checkouts` are thin job
  wrappers, like `jobs/verify_payments.py`, with entries in `registry.py`.
- Docstrings and comments stay within 3 lines.

### 3.8 Every timing and limit: `app.payments.domain.limits` (D14)

**File:** `src/app/payments/domain/limits.py`.
- Pure: it imports only `datetime.timedelta`.
- Re-exported through `app.payments.public`, so Ordering's API layer, `jobs/registry.py`
  and the mock read it the way checkout already imports Payments
  (`ordering/api/checkout.py:44`).
- Ordering's domain rules take these values as parameters and import nothing from
  Payments.

| Name | Value | Used by | Moved from |
|---|---|---|---|
| `PROVIDER_TIMEOUT_SECONDS` | 10.0 | `create_payment` and `query_status` | `payments/application/services/payments.py:17` |
| `MOCK_REDIS_TIMEOUT_SECONDS` | `= PROVIDER_TIMEOUT_SECONDS` | mock adapter socket timeouts | `payments/infrastructure/providers/mock.py:31` |
| `VERIFY_BATCH_SIZE` | 50 | `verify_payments` | `payments/infrastructure/verification.py:24` |
| `RECONCILE_MIN_AGE` | 5 min | reconcile candidates | new |
| `RECONCILE_PAGE_SIZE` / `RELEASE_PAGE_SIZE` | 50 / 50 | job paging | new |
| `RECONCILE_CRON_MINUTES` | `{0, 15, 30, 45}`, second 30 | registry | new |
| `RELEASE_CRON_MINUTES` | `{2, 7, …, 57}`, second 45 | registry | new |
| `JOB_RUN_DEADLINE_SECONDS` | 240 | both jobs | new |
| `PROVIDER_BREAKER_FAILURES` | 3 | both jobs | new |
| `STUCK_AFTER` | 1 h | `stuck` alert, `needs_attention` | new |
| `MANUAL_RELEASE_GRACE` | 24 h | §2.5, T2 `release_due` | new |
| `ALERT_REPEAT_PER_PAYMENT` / `ALERT_REPEAT_PER_PROVIDER` | 24 h / 1 h | alert de-duplication | new |
| `WEBHOOK_MAX_BODY_BYTES` | 64 KiB | webhook | `payments/api/webhooks.py:28` |
| `WEBHOOK_UNVERIFIED_LIMIT` / `WEBHOOK_VERIFIED_LIMIT` / `WEBHOOK_WINDOW_SECONDS` | 30 / 600 / 60 | webhook | `payments/api/webhooks.py:29` |
| `MOCK_STATE_TTL_SECONDS` | 7 d | mock adapter | `payments/infrastructure/providers/mock.py:30` |
| `CHECKOUT_RATE_LIMIT`, `CHECKOUT_RATE_WINDOW_SECONDS` | 30, 3600 | checkout | `ordering/api/checkout.py:68-69` |
| `RETRY_RATE_LIMIT`, `RETRY_RATE_WINDOW_SECONDS` | 10, 3600 | retry | new |
| `CONFIRM_RATE_LIMIT` / `RECONCILE_RATE_LIMIT` / `RELEASE_RATE_LIMIT` | 30 / 60 / 30 per admin per 3600 s | admin routes | new |
| `ADMIN_PAGE_DEFAULT` / `ADMIN_PAGE_MAX` | 20 / 100 | `GET /admin/payments` | new |
| `REASON_MIN` / `REASON_MAX` | 10 / 1000 characters | confirm, release | new |

**Not in this module, on purpose:**
- `checkout_hold_period`: an admin-editable setting (1 800 s, range 300-7 200,
  `platform/domain/settings_registry.py:132-140`), read through `SettingsReader`.
- The admin boundary's 300/min (`api/v1/admin.py:56-57`): it covers every admin route,
  not payments.
- The idempotency TTL (24 h, `platform/domain/idempotency.py:12`): Platform's, shared
  with every scope.

A unit test asserts every name exists and holds its value. A source scan asserts that no
payment-path module defines a numeric literal timeout or limit outside `limits.py`.

## 4. Database

### 4.1 Is a migration needed?

**Yes, one small additive migration** (D1). Nothing else in VS-024 needs schema:

| Need | Served by (already on `main`) |
|---|---|
| One live attempt per order | `uq_payments_one_live` (`payments/infrastructure/models.py:111-116`) |
| Reconcile candidates | `ix_payments_unsettled` (`:124-129`) |
| Release candidates | `ix_orders_status_placed` (`ordering/infrastructure/models.py:203`) |
| "Has an unprocessed event" per payment | `ix_webhook_events_payment_unprocessed` (`payments/infrastructure/models.py:171-175`) |
| Late-capture listing | `ix_payments_late_captured` (`:130-134`) |
| Alert de-duplication, payment history | `ix_audit_logs_entity`, `ix_audit_logs_action_created_at` (`platform/infrastructure/models.py:109`, `:112`) |
| `orders.cancelled_at`, `order_items.cancelled_at` | columns exist (`ordering/infrastructure/models.py:158`, `:235`) |
| Notification category `payment` | enum value exists (`engagement/domain/enums.py:10`) |
| Hold length | setting `checkout_hold_period`, 1 800 s, range 300-7 200 (`platform/domain/settings_registry.py:132-140`) |

**Why the two columns:**
- ADR-024's appendix assigns them to VS-024 (`ADR-024:98`): "Store the captured amount of
  a late capture… An overpayment's `late_capture` refund exceeds `payments.amount_cents`".
- Today the amount survives only in the audit row (`apply.py:152`).
- The admin list (§2.2) must show it before VS-030, and VS-030's refund must not depend
  on parsing audit JSON.
- Deferring them to VS-030 is owner question 1.

### 4.2 Migration `<new>_payments_captured_amount.py` (`down_revision = "03a4730dd046"`)

```text
upgrade:
  ALTER TABLE payments ADD COLUMN captured_amount_cents BIGINT NULL;
  ALTER TABLE payments ADD COLUMN captured_currency CHAR(3) NULL;
  ck_payments_captured_shape:
    (captured_amount_cents IS NULL OR captured_amount_cents >= 0)
    AND (captured_currency IS NULL OR captured_currency ~ '^[A-Z]{3}$')
    AND (captured_currency IS NULL OR captured_amount_cents IS NOT NULL)
  ck_payments_captured_when:
    captured_amount_cents IS NULL
    OR (provider <> 'cash'
        AND (late_captured_at IS NOT NULL
             OR status IN ('paid','partially_refunded','refunded')))
downgrade:
  drop both CHECKs, then both columns.
```

- **Backward compatible:**
  - nullable, no default, so `ADD COLUMN` is metadata-only;
  - VS-023 code never names the columns (`_COLUMNS`, `payments/infrastructure/payments.py:19-28`);
  - the CHECKs hold for every existing row (all NULL).
- **Reversible:** the downgrade drops only what upgrade added. Late-capture rows written
  meanwhile keep their audit copy of the amount.
- `captured_currency` is not pinned to USD on purpose: a capture in another currency is
  exactly the mismatch it records.
- **Models:** `PaymentModel` gains both columns and both CHECKs. The parity test
  (`tests/integration/test_model_migration_parity.py`) covers them.
- **database-design §9.1:** two column rows and the two CHECKs under "Added by VS-024".

### 4.3 Rows VS-024 writes (no new tables)

| Table | Write | Path |
|---|---|---|
| `payments` | INSERT pending (retry); `status` → `expired` / `failed` / `processing` / `paid`; `captured_*`; `late_captured_at`; `provider_payment_id` fill | retry, apply, job release, manual release |
| `orders` | `cancelled_at`; `status` only via `recompute_order_status` | job release, manual release |
| `order_items` | `pending → cancelled`, `cancelled_at` | `release_unpaid_order` only (`KNOWN_LINE_STATUS_CALLERS` gains it, `tests/unit/ordering/test_order_item_writers.py:18`) |
| `order_status_history` | line rows and the projection row. Actor NULL with reason `checkout_hold_expired` (job), or the admin's id with reason `released_by_admin` | releases |
| `webhook_events` | `processed_at` (confirm); `processing_error` set to `manual_confirmation_required` or `provider_unknown_reference` (event stays unprocessed); `dismissed_by_admin` with `processed_at` (manual release) | verify, confirm, release |
| `idempotency_records` | scope `payment_retry:{order_id}` | retry |
| `audit_logs` | `payment.retry_started`, `payment.reconcile_requested`, `payment.reconcile_deferred`, `payment.manual_confirmation`, `payment.expired` (`source` `release` / `admin_release`), `order.checkout_released` (`source` `job` / `admin`, with `reason`), `payment.alert_raised`; plus `payment.verified` / `failed` / `late_capture` with the real actor | all |
| `notifications`, `outbox` | admin alerts; customer `order.checkout_expired` (owner question 5) | alerts, releases |

## 5. Performance and abuse

- **No network call inside a transaction or under a lock**, on every new path:
  - retry: as checkout;
  - reconcile: route 202 plus background; job Tx A / query / Tx B;
  - release job: Tx A / query / Tx B;
  - confirm and manual release: never call the provider.
  - Tested by `pg_stat_activity` probes (§6.2), as `test_checkout_no_open_transaction.py`
    does.
- **Query cost:** both job selections are keyset index range scans with `LIMIT`
  `RECONCILE_PAGE_SIZE` / `RELEASE_PAGE_SIZE`. Per
  candidate, there are at most 2 primary-key reads in Tx A, plus 1 partial-index count
  (unprocessed events) for the release. Tx B locks 1 order, its lines and its payments.
- **Provider load:**
  - reconcile and release query sequentially, at most one call in flight per job;
  - `PROVIDER_TIMEOUT_SECONDS` bound;
  - breaker after `PROVIDER_BREAKER_FAILURES` consecutive failures per provider per run;
  - `JOB_RUN_DEADLINE_SECONDS` run deadline;
  - attempts younger than `RECONCILE_MIN_AGE` are never reconciled, because the webhook
    path handles them.
  - All values are in §3.8.
- **When the provider is down:** nothing is written; attempts stay live; the breaker
  stops the run's queries; one `provider_unreachable` alert per hour.
  - The release skips those orders (never cancels what it cannot check).
  - Retry answers 502 with the attempt failed and the order still payable.
- **Rate limits:**
  - `RETRY_RATE_LIMIT` per user (fail closed);
  - `RECONCILE_RATE_LIMIT`, `CONFIRM_RATE_LIMIT` and `RELEASE_RATE_LIMIT` per admin, on top
    of the 300/min admin limit;
  - the webhook limits are unchanged (ADR-032 d15).
- **Abuse:**
  - a retry is bounded by the hold window (≤ 2 h by the setting's maximum) and the rate
    limit, so a customer cannot farm provider sessions indefinitely;
  - the retry body cannot name an amount;
  - the confirm amount must equal the attempt amount; a mismatch is a 422 and writes
    nothing;
  - manual release needs the grace, a reason, and `events_reviewed` when events exist;
  - confirm cannot be used on a status-query provider at all (D7);
  - every admin action is audited with request id and IP hash.
- **Starvation:**
  - keyset paging inside each run means skipped rows never block later ones;
  - `verify_payments` excludes events awaiting manual confirmation (D11).
- **STL ownership:** a release frees the index at commit. A concurrent checkout of the
  same STL by that customer waits on the unique index for the release to commit, then
  succeeds. It never deadlocks (§8.1).

---

## 6. Tests (per category; `tests/<category>/…`)

Rows that later slices create (physical lines from VS-028, a `refunded` payment from
VS-030, a cash order) are **seeded directly**, as VS-029 does (ADR-024 appendix `:100`).
A no-status-API provider is a **test-only stub adapter**
(`tests/integration/payments/support.py`) with `supports_status_query = False`, never a
production code path. Every guard's test is shown to fail once the guard is removed (the
VS-023 rule, ADR-032 Consequences).

### 6.1 Unit (`tests/unit/payments`, `tests/unit/ordering`)

- **`decide`:** `unknown` → `NOOP` for every `PaymentStatus` × `order_cancelled` ×
  `already_late_captured`. `test_outcome.py:88` gains `unknown`, and every existing row is
  unchanged.
- **T1 `retry_refusal`:** every row and the first-match order. Boundaries:
  `now == placed_at + hold` is refused; one second before is allowed.
- **T2 `release_action`:** one test per row. Also:
  - **only** `failed` and `expired` ever return `RELEASE`. This is a property test over
    every answer × capability × event count × stored status;
  - an unprocessed event beats every answer;
  - `no_status_query` / `not_configured` never return `RELEASE`;
  - `release_due` appears only once `now >= deadline + MANUAL_RELEASE_GRACE`.
- **`hold_deadline`:** the max of the two inputs; `None` latest attempt; UTC only.
  **`manual_release_available_at`:** deadline + 24 h.
- **`manual_release_refusal`:** each 409 reason, and the boundary at exactly the grace.
- **`confirm_refusal`:**
  - cash → `INVALID_STATE_TRANSITION`;
  - a status provider → `MANUAL_CONFIRMATION_NOT_ALLOWED`;
  - an unconfigured provider is allowed;
  - amount −1 cent, +1 cent, 0, or EUR → `PAYMENT_AMOUNT_MISMATCH`;
  - exact USD → allowed.
- **`choose_provider`:** requested, previous, single, and several with none named.
- **`limits`:** every name and value; the source scan for stray numeric limits (§3.8).
- **Writer allowlists:** `test_order_item_writers.py` lists `release_unpaid_order`.
  `test_apply_decides_under_lock.py` covers `source` `manual` and `release`.

### 6.2 Integration (real Postgres; `tests/integration/payments`, `…/ordering`)

**Retry API:**
- A failed attempt, then a retry → a second attempt on the same order and order number,
  paid through the mock; the line becomes `awaiting_delivery` (`:625`).
- A retry while `pending` → 409 `PAYMENT_ALREADY_ACTIVE` with the live attempt's
  `redirect_url`. While `processing` → 409 with `redirect_url` null.
- Paid order, seeded `refunded` order, released order, past `placed_at + hold`, seeded
  cash order → 409 with `order_not_payable`, `order_cancelled`, `checkout_hold_expired` or
  `cash_order` respectively (`:628`, `:635`).
- **Owner only:**
  - another user's order, and an unknown id → byte-identical 404 bodies, and neither
    contains a URL;
  - unverified → 403; missing CSRF → 403; anonymous → 401.
- **`redirect_url` never logged:** structlog is captured with the production JSON
  processors. Over a 201, a 409 `PAYMENT_ALREADY_ACTIVE` and a 502 retry, the mock's
  redirect URL string appears in no log record and no `audit_logs.after_data`.
- **The idempotency scope:**
  - key K on order A, then K on order B (same user) → two independent 201s and two
    attempts;
  - K by user 1, then K by user 2 on user 2's own order → independent; user 2 never
    receives user 1's body;
  - K replayed on A → `Idempotent-Replayed: true` and no second attempt;
  - K on A with another `payment_provider` → 409 `IDEMPOTENCY_KEY_CONFLICT`;
  - the stored claim row has scope `payment_retry:{A}`.
- **The index violation → a clean 409:** a live attempt is inserted directly between the
  unlocked read and the INSERT (a hook in the test store). The result is:
  - 409 `PAYMENT_ALREADY_ACTIVE`, not a 500;
  - no claim row is left;
  - after the live attempt is marked `failed`, the same key succeeds.
- **Other cases:**
  - an unconfigured provider → 422 (`:633`);
  - `PAYMENT_PROVIDER=none` → 503, nothing written;
  - the kill switch on → the retry still succeeds (BR-040);
  - the 11th retry in an hour → 429; Redis down → 429;
  - no `idle in transaction` backend during a slow `create_payment`;
  - the amount is the order's `total_cents` even after a price change.
- **A retry just before the hold deadline is not cancelled:** with a fake clock, retry at
  `placed_at + hold − 1 s`, while the mock answers `pending` for the new attempt. Then run
  the release job at `placed_at + hold + 1 s`, at `+ 2·hold − 1 s`, and at `+ 2·hold + 1 h`.
  - Each run leaves the order `pending_payment`, the attempt `pending` and the lines
    `pending`.
  - Then `mock_pay paid` → the order is paid.
  - A second variant has the mock answer `expired` at `+ 2·hold + 1 s`: the release
    happens only then.

**Reconcile job:**
- A missed callback is applied in one run (`:629`).
- The Tx2-crash attempt the mock knows → the reference is stored and the result applied.
- `failed` / `expired` answers mark the attempt, and the order stays `pending_payment`.
- An attempt younger than `RECONCILE_MIN_AGE` is not queried (spy adapter).
- The breaker opens after 3 failures; one `provider_unreachable` alert per hour; nothing
  is written.
- A hanging `query_status` is cut at `PROVIDER_TIMEOUT_SECONDS` (overridden short in the
  test), for `verify_event` too.
- A no-status stub is never queried and raises `manual_confirmation_due` once over 3 runs.
- The deadline sets `truncated = 1`, and the next run continues.
- `stuck` is raised once per 24 h.
- `EXPLAIN` uses `ix_payments_unsettled`.

**Release job, one test per T2 row:**
- **Explicit `failed` → released:**
  - `orders.cancelled_at` set; status `cancelled`;
  - lines `cancelled` with `cancelled_at`;
  - history with a NULL actor; audit `order.checkout_released {source: job}`;
  - the customer notified;
  - the same customer can then check out the same STL.
- **Explicit `expired`** → released.
- **An attempt already `failed` in the database by Tx2:**
  - the mock answers `pending` → **not** released;
  - the mock answers `expired` → released.
- **`paid` exact** → paid, not released (`:630`).
- **`paid` mismatch** → late capture with `captured_*`, **not** released.
- **`pending`, `processing`, `unknown`, provider error, timeout, breaker open** → not
  released, nothing written, and the expected alert raised. One test per answer.
- **An unprocessed event** → not asked, not released (`:639`, first half).
- **No-status stub:** never released by the job at any age. `release_due` is raised once,
  after the grace.
- **A seeded order with physical lines and an explicit `expired`** → all its `pending`
  lines are cancelled (`:634`).
- **A seeded cash order** → never selected (VS-028 `:723`).
- **Paging:** 120 skipped orders ahead of one releasable order → it is released in the
  same run.
- `EXPLAIN` uses `ix_orders_status_placed`.

**Manual release (§2.5):**
- **Before the grace** → 409 `grace_not_elapsed` with `release_available_at`; nothing
  written.
- **After the grace, on a no-status order with no events** → `cancelled`:
  - the live attempt `expired` with source `admin_release`;
  - history actor = admin, reason `released_by_admin`;
  - audit `order.checkout_released` with `reason`, `attempts_expired` and the admin
    actor, `request_id`, `ip_hash`;
  - the customer notified.
- **Unprocessed events:**
  - without `events_reviewed` → 409 `unprocessed_events`;
  - with it → the events are `dismissed_by_admin` and listed in the audit row.
- **A missing or short `reason`** → 422.
- **Refusals:** a cash order, a paid order, an already-released order → 409 with the right
  reason. Unknown id → 404.
- **Boundary:** a customer → 404 (byte-identical); an admin without MFA → 401; no CSRF →
  403; the 31st release in an hour → 429.
- **No provider call** (a spy adapter records zero calls).

**Money-risk cases (§2.5 table), one test each:**
- `test_late_success_after_automatic_release_is_a_late_capture` (R-a);
- `test_confirm_after_manual_release_records_late_capture_not_payment` (R-b);
- `test_release_with_reviewed_events_dismisses_them_and_a_later_event_is_a_late_capture`
  (R-c);
- `test_rebuy_after_release_then_old_capture_leaves_new_order_paid` (R-d);
- `test_capture_found_after_outage_on_released_order` (R-e);
- `test_mismatch_via_verification_is_late_capture` and
  `test_mismatch_via_confirm_is_422_and_writes_nothing` (R-f).

Each asserts:
- the order and its lines are unchanged by the capture;
- `late_captured_at` and `captured_*` are set (where a capture is recorded);
- exactly one `late_capture` alert per admin.

**Admin reconcile (§2.2):**
- **202 before any provider call:** the app is driven through a raw ASGI harness that
  appends each `send` message to a list shared with a spy adapter. The
  `http.response.body` message comes **before** the adapter's `query_status` entry.
  - TestClient waits for background tasks, so it cannot show this ordering.
- **No open transaction:** the spy blocks `query_status` on an `asyncio.Event`. While it
  is blocked, `pg_stat_activity` has no `idle in transaction` backend for the app role
  (the probe from `tests/integration/ordering/test_checkout_no_open_transaction.py:31-35`).
  The event is then released, and the payment ends verified.
- **The background task dies:** `reconcile_in_background` is made to raise, or `add_task`
  is patched to drop the task.
  - The `payment.reconcile_requested` audit row exists, and the attempt is still live.
  - Running `reconcile_payments` once then applies the provider's `paid`.
  - The same for a `failed` answer.
- **Refusals:** a cash id → 409; a no-status provider → 503 and **no** background task
  added; unknown → 404.
- **Results:** a provider error → `payment.reconcile_deferred {reason: provider_unavailable}`;
  an `unknown` answer → `{reason: unknown}` and nothing changed.
- **On an `expired` attempt with a capture** → a late capture is found.
- **The limit:** the 61st request in an hour → 429.

**Manual confirm (§2.3):**
- **Live attempt, exact amount and USD:**
  - paid, STL `awaiting_delivery`, one email, one notification;
  - events marked processed;
  - audit `payment.manual_confirmation` with `typed_amount_cents`, `typed_currency`,
    `provider_reference`, `reason`, `outcome = apply_paid` and the admin actor;
  - `payment.verified` with the admin actor.
- **The amount differs by −1, +1, or equals 0; or the currency is EUR** → 422
  `PAYMENT_AMOUNT_MISMATCH` with `expected_amount_cents`. For each, assert:
  - the payment row is byte-for-byte unchanged (`status`, `late_captured_at`,
    `captured_*`, `provider_payment_id`);
  - no audit, alert, notification or outbox row;
  - the events are still unprocessed;
  - the same request with the right amount then succeeds.
- **A mismatch on an `expired` attempt** → also 422, and not a late capture.
- **The exact amount on an `expired` attempt, or on a cancelled order** → a late capture
  (`:638`), never applied.
- **Other outcomes:**
  - a status provider → 409 `MANUAL_CONFIRMATION_NOT_ALLOWED`;
  - a cash id → 409;
  - a differing stored reference → 409 `PAYMENT_REFERENCE_MISMATCH`;
  - a reference owned by another payment → 409;
  - a double submit → `NOOP`, one email;
  - a missing `reason` → 422;
  - no CSRF → 403;
  - the 31st confirm in an hour → 429.
- **The same lock order as the webhook:** the SQL captured for a confirm, and for
  `apply_provider_result(source="webhook")` on an identical seeded payment, have the same
  `FOR UPDATE` sequence: `payments` (unlocked) → `orders` → `order_items` → `payments`.

**`unknown` (§3.2a):** the four entry-point tests, each asserting that nothing moved.

**Late captures** (`:637`, `:641`, `:642`) are as in the first draft: expired attempt on
a released order; a failed attempt while a retry is live; a second capture after the
retry paid; an under- or overpayment on a live attempt through verification. Each sets
`captured_*` and raises one alert.

**Lock order from captured SQL** (as `test_payment_lock_order.py`): every path in §8.1
has the exact statement order asserted. No batch selection contains `FOR UPDATE`.

**Schema (PR A):** the refused and accepted pairs for both CHECKs; parity and
reversibility; `alembic heads` = 1.

### 6.3 Concurrency (`tests/concurrency/test_payment_recovery_races.py`; real Postgres, `meet_or_fail`)

1. **Retry vs retry, different keys:** one 201 and one 409 `PAYMENT_ALREADY_ACTIVE`.
   - The loser waits on the orders lock, then sees the winner's attempt. Its 409 is
     clean, not a 500.
   - One provider `create_payment` call.
   - Repeated 50× (`:626`).
2. **Retry vs retry, same key and order:** one 201; the other 409
   `IDEMPOTENCY_REQUEST_IN_PROGRESS`, or a replay. One attempt.
3. **Retry vs a lock-free live INSERT (the index path, real Postgres).**
   - Because every retry locks the order first, two retries can never both pass the read.
     The index is the backstop for a writer that skips the lock.
   - The test runs a raw `INSERT INTO payments … 'pending'` for the same order, without
     the orders lock, in a second connection. It commits while the retry is held, by a
     barrier, between its read and its INSERT.
   - The retry's SAVEPOINT INSERT then violates `uq_payments_one_live`. The result is 409
     `PAYMENT_ALREADY_ACTIVE`, the claim is rolled back, and the response is not a 500.
4. **Retry vs webhook verification of the current live attempt answering `failed`:**
   - either the verification commits first and the retry gets 201 (a new attempt);
   - or the retry runs first and gets 409 `PAYMENT_ALREADY_ACTIVE`;
   - never two live attempts. Each run ends with ≤ 1 live attempt.
5. **Retry vs webhook verification of an old `failed` attempt answering `paid`** (a late
   success):
   - the retry gets 201, and the old attempt becomes a late capture;
   - the order stays `pending_payment` with one live attempt;
   - no deadlock.
6. **Retry vs release** (`:636`):
   - either the retry commits first and the release then finds a young `pending` attempt
     (not explicit, so it skips);
   - or the release commits first (the mock answered `expired` for the old attempt) and
     the retry gets 409 `order_cancelled`;
   - never a pending payment on a cancelled order. 50×.
7. **Reconcile vs webhook verification** of one payment → applied once (`:630`).
8. **Manual confirm vs webhook verification** → one apply, the other `NOOP` (ADR-024
   appendix `:130`).
9. **Release vs a paid verification:** either paid (the release re-checks and skips) or
   released then a late capture; never both paid and cancelled.
10. **Manual release vs a paid verification:** either the order is paid (the release gets
    409 `order_not_payable`) or it is released (the verification records an
    `order_cancelled` late capture).
11. **Two overlapping release runs** → one release, one set of history rows.
12. **Release vs a checkout of the same STL** by the same customer → 409 before the
    commit, 201 after; no deadlock.
13. **Two admins confirming one payment** → one apply, one email.
14. **Reconcile vs release** on one order; **retry Tx2 vs reconcile Tx B** → one outcome,
    no `DeadlockDetectedError`.

### 6.4 Contract (`tests/contract/payments/test_provider_contract.py`)

- The mock answers `unknown` for a never-created reference. `simulate(…, "unknown")`
  raises.
- `query_status` works with no `provider_payment_id`.
- A timeout maps to `ProviderUnavailableError`.
- The no-status stub declares `supports_status_query = False`, and nothing calls its
  `query_status`.
- **For VS-032:** an abandoned session must eventually answer `expired` (owner question
  12).

### 6.5 Security (`tests/security/test_payment_recovery_security.py`)

- Every new admin path: anonymous 401, customer 404 byte-identical to an imaginary path,
  admin without MFA 401 (SEC-10, `api/v1/admin.py:17-20`).
- Retry: IDOR (another customer's order id) 404 with no timing or body difference; no
  amount field accepted (422 `extra="forbid"`); `redirect_url` only in the owner's 201 / 409.
- Manual release and confirm: customer 404, admin without MFA 401, no CSRF 403.
- No HTTP route marks a mock payment paid (extends `test_payment_security.py`'s scan to
  the new routes).
- Responses never contain `provider_metadata`, `payload`, webhook secret or customer
  email. The confirm and release `reason` text and `redirect_url` are never logged.

### 6.6 Smoke and e2e

- `tests/e2e/test_vs024_payment_recovery.py`:
  - register → checkout → `mock_pay failed` → retry → `mock_pay paid` → line
    `awaiting_delivery`;
  - checkout → `mock_pay expired` → release job (fake clock) → order `cancelled` → the same
    STL bought again;
  - checkout (no-status stub) → hold + grace → admin release with a reason → `cancelled`.
- `tests/smoke`: both jobs registered in `CRON_JOBS` and `FUNCTIONS`; the retry and admin
  routes in the OpenAPI snapshot.

### 6.7 Running the suite (sequential chunks, never all at once)

1. `pytest tests/unit`
2. `pytest tests/integration/ordering tests/integration/payments tests/integration/platform`
3. `pytest tests/integration --ignore=tests/integration/ordering --ignore=tests/integration/payments --ignore=tests/integration/platform`
4. `pytest tests/concurrency`
5. `pytest tests/contract tests/security tests/smoke tests/e2e`

Plus `ruff check .`, `ruff format --check .` and `mypy src tests`. Integration needs
Docker (testcontainers). Inside compose, `api` and `worker` share the mock's Redis
(VS-023 R9).

---

## 7. Docs and ADRs

- **ADR-033 (new): "Payment recovery: retry, reconciliation, hold release and manual
  confirmation"** (D1-D14).
  - It amends ADR-024 d15 in part: a manual confirm with a differing amount is refused
    (422), never a late capture; automatic release only on an explicit `failed` /
    `expired` (T2); the manual admin release (§2.5).
  - It amends ADR-032 d17 (`verify_payments` skips manual-confirmation events) and d21
    (the late-capture view now includes the admin list).
  - It does not rewrite either; README governance forbids that (`docs/adr/README.md`,
    Governance).
  - It records that the ADR-032 d24 alert condition is met by §3.5 once VS-021 delivers
    email. The gate's main clause (VS-024 **and** VS-030 merged) still stands, because
    VS-032 depends on VS-030 (`docs/vertical-slice-plan.md:55`).
- **`docs/payment-recovery.md` (new),** the contract in the style of `docs/checkout.md`:
  routes, errors, T1, T2, the jobs, alerts, the operator runbook for late captures and
  stuck payments.
- **`docs/checkout.md`:**
  - `:55` stuck claim → links retry;
  - `:69-76`: the late-capture view adds `GET /admin/payments?late_captured=true` and
    alerts (the SQL listing stays);
  - `:78` gate wording.
- **`docs/requirments/api-endpoints.md`:**
  - §5.2: the three new codes;
  - a retry row in the `/me/orders` table (`:404-408`);
  - §20 rows `:589-592`: reconcile becomes `202`, confirm gets the new errors and `reason`;
    a new row for `POST /admin/orders/{id}/release`;
  - §29.14 `ManualPaymentConfirmRequest` (`:1166-1171`): the new fields, and replace
    "Server requires exact order-total match" with the 422 amount-guard rule.
- **`docs/requirments/database-design.md`:**
  - §9.1: the two columns and CHECKs;
  - §9.2: `manual_confirmation_required`;
  - §8.3 Rules: the hold deadline.
- **SRS** (owner approval needed, SRS wins over the plan):
  - §9.4 `SRS.md:767`: "which is what the checkout-release job provides" becomes
    "reconciliation and verification free it" (ADR-024 appendix `:99`);
  - §23 `:1398`: the release row says "only on an explicit failed or expired", plus the manual release;
  - §9.2 `:757`: a manual confirm with a differing amount is refused (422), never a late capture.
- **`docs/vertical-slice-plan.md` VS-024:**
  - status, "Model / migration" (one migration, D1), the as-built notes;
  - the two "Must resolve before build" items marked resolved with links;
  - the test "a hold expiring while a payment verifies: the payment wins" (`:630`)
    restated as race 6, because it cannot hold if the release commits first (ADR-024
    appendix `:99`);
  - the "manual confirm with the wrong amount gives 422" test (`:632`) restated.
  - Add the VS-030 note "cap late-capture refunds by `captured_amount_cents`".
- **Frontend handoff** (`docs/frontend-handoff/BACKEND-RESPONSE.md`): the retry and
  resume contract, `hold_expires_at`, and the `202` reconcile.
  `docs/frontend-handoff/openapi.json` is regenerated.
- **`docs/settings-registry.md:38`:** `checkout_hold_period` now also bounds retry, and
  the deadline is measured from the later of placement and the live attempt.
- **`docs/adr/README.md`:** the ADR-033 line.

---

## 8. Implementation steps, in order, with checkpoints

### PR A: schema only (merge first, under the migration lock)

Take the migration lock first (`CONTRIBUTING.md:42-47`).

1. Announce the lock and re-derive the head (`03a4730dd046` expected).
2. Add the two columns and two CHECKs to `PaymentModel`.
3. Hand-write the migration (§4.2). Check `alembic heads` = 1, then upgrade → downgrade
   -1 → upgrade.
4. Add the schema, parity and reversibility tests, and update database-design §9.1.
5. Run chunks 1-3, then open PR A.

**PR A contains exactly these files, and no application code:**

| File | Change |
|---|---|
| `migrations/versions/<rev>_payments_captured_amount.py` | new; `down_revision = "03a4730dd046"` |
| `src/app/payments/infrastructure/models.py` | two `mapped_column` and two `CheckConstraint` **declarations** on `PaymentModel` |
| `tests/integration/ordering/test_order_payment_schema.py` | refused/accepted pairs for both CHECKs |
| `tests/integration/test_model_migration_parity.py` | unchanged file; it already compares `payments` (`:17-21`) and so covers the new columns |
| `tests/integration/test_migration_reversibility.py` | a block for the new revision |
| `docs/requirments/database-design.md` | §9.1 rows |

The one `src/` change is the declarative ORM mapping. It is needed because the parity test
compares the model with the migrated schema, and it is not behaviour:
- no repository, service, route, job, domain type or `_COLUMNS` tuple
  (`payments/infrastructure/payments.py:19-28`) changes;
- the `Payment` dataclass does not change;
- nothing reads or writes the columns until PR B.

A reviewer check: `git diff --stat main…vs-024-schema -- src` must list only
`payments/infrastructure/models.py`, and every added line must be a column or a
constraint declaration.

### PR B: code (branch `vs-024-payment-recovery`, from `main` after PR A)

6. Pure rules (§3.1: T1, T2, `decide` `unknown`, `confirm_refusal`,
   `manual_release_refusal`, `choose_provider`) and `limits.py` (§3.8), with unit tests.
7. Ports and stores (§3.4); apply changes (actor, captured amount, `LateCaptureSink`);
   verification fixes and `unknown` (§3.2a, §3.3); the mock's `unknown`. Integration,
   contract and lock-order tests.
8. Alerts (§3.5), `active_administrator_contacts`.
9. `release_unpaid_order`, the `SqlOrderStore` additions, the writers test.
10. Jobs and registry.
11. The retry route.
12. Admin payments routes, then manual release.
13. The concurrency suite and e2e.
14. Docs and ADR-033.

### Checkpoints and what each reports

| # | When | Reports |
|---|---|---|
| **CP1** | PR A ready / merged | the new revision id; `alembic heads` output (1 head); the upgrade → downgrade -1 → upgrade log; chunk 1-3 pass counts; the `git diff --stat -- src` above; "migration lock released" |
| **CP2** (owner sign-off) | after step 6 | T1, T2, `confirm_refusal` and `manual_release_refusal` as tables with their unit-test counts; the property test proving only `failed` / `expired` release; the `limits.py` table; the frozen §3.6 interface listing for VS-029, VS-030 and VS-032 |
| **CP3** | after step 10 | chunks 1-2 pass counts; both `EXPLAIN` plans (`ix_payments_unsettled`, `ix_orders_status_placed`); the captured SQL of release Tx B and reconcile Tx B against §8.1; one job run's counters against a seeded set |
| **CP4** | after step 12 | chunks 1-3 and 5 pass counts; the OpenAPI diff (retry, five admin routes, three new error codes); the ASGI-ordering and `pg_stat_activity` results for admin reconcile and retry; the no-URL-in-logs result; the 422-writes-nothing result |
| **CP5** | after step 13 | chunk 4 with the repeat counts per race (50× for 1 and 6); every chunk run alone and green; `ruff check`, `ruff format --check`, `mypy src tests` clean |
| **CP6** | after step 14 | ADR-033; the doc diffs; the SRS edits listed and held for owner approval; the plan status set to DONE |

### 8.1 Lock order per path, with the SQL order (resolves item 6)

Statements are listed in the order each transaction sends them. **L** marks a lock on an
existing row.

**Checkout Tx1** (VS-023, unchanged):
1. `INSERT INTO idempotency_records … ON CONFLICT DO NOTHING`, then a `SELECT` of the
   claim (**L**: unique-key wait on its own key only).
2. `SELECT … FROM carts WHERE user_id FOR UPDATE` (**L**).
3. Catalog `SELECT`s, no lock.
4. `INSERT orders` (SAVEPOINT), `INSERT order_items` (SAVEPOINT), `INSERT payments`,
   `INSERT order_status_history`, `INSERT audit_logs`.
5. `DELETE FROM cart_items`, `UPDATE carts`.
6. `UPDATE idempotency_records SET resource_id`.

**Checkout / retry Tx2:**
1. Either `UPDATE payments SET provider_payment_id … WHERE id AND provider_payment_id IS
   NULL`, or `UPDATE payments SET status='failed' … WHERE id AND status='pending'` plus
   `INSERT audit_logs`.
2. `UPDATE idempotency_records SET state='done'`.

**Retry Tx1:**
1. `INSERT INTO idempotency_records` (scope `payment_retry:{order_id}`) `… ON CONFLICT DO
   NOTHING`, then `SELECT` (**L**: own key).
2. `SELECT … FROM orders WHERE id = :id AND user_id = :me FOR UPDATE` (**L**).
3. `SELECT … FROM order_items WHERE order_id`, no lock.
4. `SELECT … FROM payments WHERE order_id`, no lock.
5. `SAVEPOINT`; `INSERT INTO payments`; `RELEASE SAVEPOINT`, or `ROLLBACK TO` on
   `uq_payments_one_live`.
6. `INSERT audit_logs`.
7. `UPDATE idempotency_records SET resource_id`.

**Webhook receipt:** a `SELECT payments` (by reference, then id), no lock;
`INSERT webhook_events … ON CONFLICT DO NOTHING`.

**Verification, reconcile and admin-reconcile Tx B** (`apply_result`):
1. `SELECT payments WHERE id`, no lock.
2. `SELECT orders WHERE id FOR UPDATE` (**L**).
3. `SELECT order_items WHERE order_id ORDER BY id FOR UPDATE` (**L**).
4. `SELECT payments WHERE id FOR UPDATE` (**L**).
5. `UPDATE payments`, `UPDATE order_items`, `INSERT order_status_history`,
   `UPDATE orders` (status), `INSERT audit_logs`, `INSERT outbox`,
   `INSERT notifications`.
6. `UPDATE webhook_events WHERE id` (verification only).

**Release job:**
- **Selection:** `SELECT id FROM orders WHERE status='pending_payment' … ORDER BY
  placed_at, id LIMIT` (no lock).
- **Tx A:** `SELECT payments WHERE order_id`; `SELECT count(*) FROM webhook_events WHERE
  payment_id = ANY …` (no lock).
- **The provider call**, with no transaction open.
- **Tx B:**
  1. `SELECT orders WHERE id FOR UPDATE` (**L**).
  2. `SELECT order_items WHERE order_id ORDER BY id FOR UPDATE` (**L**).
  3. `SELECT payments WHERE order_id ORDER BY id FOR UPDATE` (**L**).
  4. The re-check: `SELECT count(*) FROM webhook_events …`, no lock.
  5. `apply_result`. Its locks repeat rows already held.
  6. `UPDATE payments` (the explicit `failed` / `expired`).
  7. `UPDATE orders SET cancelled_at`; `UPDATE order_items SET
     fulfillment_status='cancelled', cancelled_at`.
  8. `INSERT order_status_history`; `UPDATE orders` (status); `INSERT audit_logs`.
  9. `INSERT notifications` / `outbox` (customer, and alerts in SAVEPOINTs).

**Manual release** (request unit of work):
1. The boundary `SELECT users.auth_epoch`, no lock.
2. `SELECT orders FOR UPDATE` (**L**).
3. `SELECT order_items ORDER BY id FOR UPDATE` (**L**).
4. `SELECT payments WHERE order_id ORDER BY id FOR UPDATE` (**L**).
5. `SELECT count(*) FROM webhook_events`, no lock.
6. `UPDATE payments` (expired); `UPDATE webhook_events` (dismissed).
7. `UPDATE orders`, `UPDATE order_items`.
8. `INSERT history`, `INSERT audit`, `INSERT notifications`, `INSERT outbox`.

**Manual confirm** (request unit of work):
1. The boundary `SELECT users.auth_epoch`.
2. `SELECT payments WHERE id`, no lock.
3. `SELECT orders FOR UPDATE` (**L**).
4. `SELECT order_items ORDER BY id FOR UPDATE` (**L**).
5. `SELECT payments WHERE id FOR UPDATE` (**L**).
6. `UPDATE payments`, the order and line writes, `INSERT`s.
7. `UPDATE webhook_events WHERE payment_id AND processed_at IS NULL`.
8. `INSERT audit_logs` (`payment.manual_confirmation`).

**Admin reconcile request:** the boundary read; `SELECT payments WHERE id`;
`INSERT audit_logs`; COMMIT; then the response; then the background task (Tx A / query /
Tx B, as verification).

**Job selections** (both jobs): plain `SELECT … LIMIT`. Never `FOR UPDATE`.

**The global order:** `idempotency_records → carts → orders → order_items (id) → payments
(id) → webhook_events`, then only INSERTs of new rows. No path takes two of these in the
opposite order.

**The hold-release lock, against checkout and apply:**
- **There is no separate hold-release lock:** no advisory lock and no table lock. The
  release job's Tx B and the manual release take the ordinary row locks, in the same
  prefix as apply: `orders` FOR UPDATE first, then `order_items` by id, then the order's
  `payments` by id.
- **Against apply** (webhook, reconcile, confirm): both start with the same `orders` row
  lock, so they serialise there. Whoever is second re-reads under the lock:
  - a release after an apply sees the order paid and skips;
  - an apply after a release sees `cancelled_at` and records a late capture
    (`apply.py:140-145`).
- **Against checkout:** checkout locks no existing `orders`, `order_items` or `payments`
  row. It locks only its idempotency claim and the cart, then inserts new rows. The
  release never touches `carts` or `idempotency_records`. So neither waits on the other.
  - The single point of contact is `uq_order_items_stl_ownership`: checkout's INSERT of
    the same `(user, STL)` waits for the release's uncommitted `pending → cancelled`
    UPDATE. That wait is one-way, because the release never waits on anything checkout
    holds.
- **Against retry:** both take `orders` first; retry then only INSERTs.
- **Against itself:** two overlapping runs serialise on `orders` and re-check, so only one
  releases.
- **KEY SHARE on `users`:** the notification and outbox INSERTs take it after `orders`.
  VS-045 must not lock `users` FOR UPDATE before `orders` (R7).

---

## 9. Risks

- **R1 — Automatic cancellation now depends on the provider saying `expired`.**
  - An abandoned session that a provider never expires (or the mock's state, which lives
    7 d, `mock.py:30`, then answers `unknown`) stays `pending_payment`.
  - The order is then released only by an admin after the grace. BR-039's "cancelled
    automatically" holds only for providers that expire sessions (owner question 12).
- **R2 — Manual release is a human decision about money.**
  - Cases R-a to R-g are in §2.5.
  - Mitigations: the mandatory reason, the 24 h grace, the `events_reviewed` flag, and an
    audit row with request id and IP hash.
- **R3 — A mismatched capture confirmed by hand leaves no platform record** (§2.3). The
  admin's refund in the dashboard is tracked only by the release reason, until VS-030
  (owner question 2).
- **R4 — `202` reconcile is less immediate** for the admin. The detail shows the result
  after one provider round trip.
- **R5 — Alert volume during an outage.** De-duplicated; revisit with VS-047.
- **R6 — Hold extension by retry** to under 2 × hold.
- **R7 — `users` KEY SHARE after `orders`.** VS-045 must respect it.
- **R8 — Later-slice state is seeded in tests.** VS-028 and VS-030 re-run these tests on
  real rows.
- **R9 — Stale SRS sentences** until the owner approves the edits (§7).
- **R10 — A checkout crash-window attempt that the provider answers `unknown`** blocks
  retry until a manual release after the grace. That is rare (a crash between Tx1 and
  the provider call). Owner question 7.
- **R11 — Admin email depends on VS-021.** Until then, the alert is in-app plus the log.

---

## 10. Owner questions (each with a recommendation)

Settled since the first draft, and no longer asked:
- the release rule (Revision 1 item 1);
- confirm on a mismatch (item 4);
- `unknown` (item 6);
- `202` reconcile (item 3).

1. **DECIDED (Revision 2, by the CP1 instruction):** the captured amount is stored now,
   in PR A.
2. **DECIDED (Revision 2):** VS-030 must handle a late capture with no matching payment
   record.
3. **Drop `409 PRODUCT_ALREADY_OWNED` from retry** (`docs/vertical-slice-plan.md:616`)?
   *Recommendation:* yes. The order's own `pending` lines hold the ownership index
   (`ordering/infrastructure/models.py:316-323`), and T1's "every line `pending`" check
   replaces it.
4. **Manual confirm only for providers without a status API (D7)?**
   *Recommendation:* yes (ADR-012 `:13`). During an outage nothing is cancelled, and
   reconcile retries.
5. **Tell the customer when their order is released** (job or admin)?
   *Recommendation:* yes: an in-app `order.checkout_expired` notification and the email
   `order_checkout_expired`, saying that any payment that still arrives is refunded.
6. **DECIDED (Revision 2):** 24 h, a code constant (§3.8).
7. **DECIDED (Revision 2):** no early release when a provider reference is stored. An
   early release (from the hold deadline) is allowed only with no stored reference and a
   latest answer of `unknown`.
8. **Is the alert channel for ADR-032 d24 an in-app notification plus an email to every
   active admin?**
   *Recommendation:* yes. The gate itself is unchanged.
9. **DECIDED (Revision 2):** keep the `redirect_url` log test. No framework logs locals,
   so no logging change is needed.
10. **Keep the §3.8 values as code constants rather than settings?**
    *Recommendation:* yes, as VS-023 did. Promote one only when an operator needs to tune
    it.
11. **May the SRS edits** (§9.2 `:757`, §9.4 `:767`, §23 `:1398`) land in PR B's docs
    commit after CP2?
    *Recommendation:* yes.
12. **DECIDED (Revision 2):** an `expired` answer for an abandoned session is a VS-032
    selection criterion and contract fixture.
