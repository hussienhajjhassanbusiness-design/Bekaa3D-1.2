# VS-023 — Checkout and Verified Payment for Digital Orders: Implementation Plan

**Status:** DONE: PR A (schema) merged in `62586d1`; PR B (code) complete on branch `vs-023-checkout`, all five suite chunks green (Checkpoint 5)
**Date:** 2026-10-16 (Revision 2: 2026-10-17)
**Planned against alembic head:** `26d5d039d72c` (custom_requests, VS-034, merged in
`ae93c2a` after Revision 1).
- Derived statically from `revision` / `down_revision` in `migrations/versions/`: 20
  files, one linear chain, one head (`26d5d039d72c`, which revises `bde6135b2538`), no
  merge revisions.
- This slice's migration therefore has `down_revision = "26d5d039d72c"`.
- Re-derive the head immediately before `alembic revision`, because VS-023b or another
  slice may merge first.

## Revision 5 (2026-10-17): PR B requirements (owner)

PR B starts from `main` at `62586d1` (PR A merged; head `03a4730dd046`). These bind PR B in
addition to Revisions 1-4:

1. **Provider succeeded, Tx2 failed:** the payment is matched by **lookup of the payment
   row**, not by order metadata.
   - `create_payment` passes our `payments.id` as the merchant reference. The mock echoes
     it as `payment_reference` in every event.
   - `receive_webhook` resolves the payment by `(provider, provider_payment_id)` first,
     then by `payment_reference` → `payments.id` with the same `provider`.
   - Verification stores a missing `provider_payment_id` under the ADR-024 lock order
     when it applies the result.
   - Test: the Tx2 crash after the provider call, then a webhook carrying only the
     reference resolves, verifies and marks the order paid.
2. **Client IP and body cap:**
   - The invalid-signature bucket keys on `client_ip(request)`
     (`src/app/api/dependencies.py:39`), the same source as every other per-IP limiter.
     VS-020 makes it the real client by running uvicorn with `--proxy-headers` and
     `--forwarded-allow-ips` limited to nginx (`docs/vertical-slice-plan.md:436`).
   - The app never parses `X-Forwarded-For` itself.
   - The body is read through a 64 KiB bounded stream **before** `parse_webhook`. A
     larger body is refused unread past the cap (`400 VALIDATION_ERROR`) and spends no
     bucket.
3. **Go-live gate:** no real online provider may be configured in production before
   VS-024 and VS-030 are merged, unless an operational alert on late captures and stuck
   payments exists.
   - PR B enforces what it can: production accepts only `none` (no real adapter exists
     until VS-032).
   - ADR-032 records the gate, and VS-032's entry in the slice plan must cite it.
4. **A stuck `in_progress` claim** (crash between Tx1 and Tx2):
   - The order stays `pending_payment`, so order history (VS-025) shows it unpaid with
     its pending attempt.
   - For 24 h the key answers `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` naming the order.
   - After the daily purge removes the expired claim, the same key is a new request; the
     cart is already empty, so it gets `409 CART_EMPTY`.
   - Recovery is VS-024's reconciliation and retry. Documented in `docs/checkout.md`.
5. **Delay from webhook receipt to `paid`** (§2.4):
   - typical: one provider status query after the 200 (background task);
   - worst case: about 60 s (the next `verify_payments` tick), up to about 560 s with a
     slow provider (a 50-event batch at a 10 s timeout each). Documented in
     `docs/checkout.md`.

## Revision 4 (2026-10-17): merged `origin/main` (VS-035)

- VS-035 (`902cde2`) took ADR-031, so VS-023's ADR is now **ADR-032**: the file,
  `docs/adr/README.md`, this plan, the migration comment and database-design.
- VS-035 adds no migration. The head stays `03a4730dd046` (parent `26d5d039d72c`).
- The only conflict was the ADR index in `docs/adr/README.md`; both lines are kept.

## Revision 3 (2026-10-17): RESTRICT foreign keys to users (owner, option 1)

The PR A suite run found `test_no_foreign_key_to_users_can_block_the_purge` requiring every
FK to `users` to be CASCADE or SET NULL. That contradicts database-design §14. The owner
chose to keep the spec. Recorded in ADR-032 decisions 1-2.

- **RESTRICT is intentional** on `orders.user_id` (DD `:1879`), `order_items.user_id`
  (`:1890`), `order_items.delivered_by` (`:1891`) and `payments.recorded_by` (`:1892`).
  - Users who own money records are anonymised, never deleted (ADR-009).
  - The purge cannot reach these rows: it deletes only `email_verified_at IS NULL`
    accounts (`src/app/identity/infrastructure/repositories.py:368-390`), and checkout
    requires a verified account (BR-030).
- **The test now allowlists exactly those four (table, column) pairs.** Any other
  RESTRICT key to `users` fails it, and so does a stale allowlist entry.
- **`order_status_history.actor_user_id` is ON DELETE SET NULL** (was RESTRICT). It is
  nullable, no CHECK reads it, and NULL already means "the system".
- **New database tests:**
  - a never-verified user without orders is deleted (its idempotency claim cascades);
  - deleting an order owner is refused with `23503` / `orders_user_id_fkey`;
  - deleting an acting user leaves the history row with a NULL actor.

## Revision 2 (2026-10-17): main moved; owner decisions before PR A

1. **`main` moved to `ae93c2a` (VS-034).** The head is now `26d5d039d72c`, and
   `ADR-030-bring-your-idea-submission.md` took ADR-030.
   - VS-023's ADR was renamed ADR-031 here, then **ADR-032** in Revision 4 once VS-035
     merged its own ADR-031; it is renamed everywhere in this plan.
   - VS-034 also added one line at database-design `:346` (and further lines in
     §12.4/§12.5), so every citation below that line moved. The old → new references
     are in the commit message of this revision.
2. **Q18 decided (owner):** PR A adds nullable **`orders.digital_terms_version` TEXT**,
   a plan addition to be recorded in ADR-032.
   - PR B writes a constant (`DIGITAL_TERMS_VERSION`) until a settings value exists.
   - It is NULL for orders without STL lines, and set whenever
     `digital_terms_accepted_at` is set (`ck_orders_digital_terms_version`).
   - No general `terms_version` column is added.
3. **PR B must handle** (owner, recorded here for the PR B session):
   - **Provider succeeded but Tx2 failed:**
     - a webhook can arrive for a payment whose `provider_payment_id` was never stored.
       `receive_webhook` must also match on the merchant reference (our `payment_id`,
       which the mock sends as `payment_reference`) before treating the event as
       unknown;
     - verification must then store the reference under the ADR-024 lock order;
     - test: crash after the provider call, then the webhook resolves and applies.
   - **Real client IP for the invalid-signature bucket**, plus a body cap before the
     signature check:
     - behind nginx (VS-020), `request.client.host` is the proxy. PR B must define the
       trusted source (the proxy-set header, or uvicorn `--proxy-headers` with
       `--forwarded-allow-ips` limited to the proxy) and never trust a client-supplied
       `X-Forwarded-For`;
     - the 64 KiB cap is enforced on the streamed body **before** `parse_webhook`
       runs.
   - **Go-live gate:** no real online provider may be configured in production before
     VS-024 (retry, reconciliation, hold release) **and** VS-030 (late-capture refund
     obligations) are merged, unless an operational alert on late captures and stuck
     payments exists. ADR-032 records it, and the VS-032 entry in the slice plan
     references it.

**Preflight (2026-10-16, `main` at `d727793`, tree clean):**
- Remote branches: `main`, `feat/vs-038-wishlist`, `vs-022-mixed-cart`,
  `vs-046-security-retention`; none is ahead of `main` and none touches VS-023.
- Commits naming VS-023 are VS-022's prepared interface (`dd76d2c`, "incl. the VS-023
  lock interface") and ADR-025 (`8b16928`); both are merged and are inputs, not VS-023
  work. No VS-023 plan exists in `docs/plans/` or on any branch.
- Next free ADR number on `origin/main` and every remote branch: **ADR-032**
  (Revision 4: `docs/adr/` now ends at ADR-031, VS-035's; no branch adds ADR-032).
- Code evidence: no `orders`, `order_items`, `payments`, `webhook_events` or
  `idempotency_records` model, table or migration exists. `src/app/payments/` and
  `src/app/fulfillment/` are empty layer packages. No payment port or adapter exists;
  `src/app/core/config.py:51-56` holds only `payment_provider = "mock"` and `whish_*`.

## Revision 1 (2026-10-17): answers to the plan review

Every answer below was checked against `main` at `d727793`. Each is reflected in the
section named. Earlier decisions that changed are marked **CHANGED**.

1. **`derive_order_status` follows SRS §20.2 as written** (§3.1, Q10). **CHANGED**: the
   reorder is dropped from VS-023.
   - SRS §20.2 (`docs/SRS.md:1179-1186`), the paid branch, verbatim:
     ```
     payment reached paid (online or cash):
         all lines cancelled              → cancelled
         refunds cover all paid money     → refunded
         all lines refunded               → refunded
         any non-failed or owed refund    → partially_refunded
         all lines terminal               → completed
         otherwise                        → in_progress
     ```
     and `:1188`: "a failed refund never counts toward `refunded`, but an owed (not
     reissued) one counts as a refund present".
   - The VS-030 bug (`docs/vertical-slice-plan.md:820`): "on a single-line order (or one
     where every line is fully refunded) a full refund that later fails leaves the line
     `refunded`. The order then reads `refunded` while money is still owed, which breaks
     ADR-024 decision 11 … Separately, 'all lines cancelled → cancelled' is checked
     first, so an all-cancelled order whose cancellation refund failed reads
     `cancelled`, not `partially_refunded`."
   - Worked cases:

     | Case | Inputs | SRS §20.2 order | Reordered (owed first, drop "all lines refunded") |
     |---|---|---|---|
     | A: one STL line, $10 paid; full $10 refund created (line → `refunded`), then marked `failed`, not reissued | paid; lines `[refunded]`; non-failed refunds $0 < $10; owed = yes | rule 2 no; **rule 3 "all lines refunded" → `refunded`** | **`partially_refunded`** |
     | B: paid order; every line cancelled; the cancellation refund failed and is owed | paid; lines all `cancelled`; owed = yes | **rule 1 → `cancelled`** | **`partially_refunded`** |
     | Control: no refunds, line `awaiting_delivery` | paid; no refund | `in_progress` | `in_progress` (identical) |

   - **Does the SRS provably contradict itself?** No.
     - Case A's `refunded` comes from the line-state rule, not from counting the failed
       refund. The `:1188` clause "never counts toward `refunded`" can be read as
       governing the coverage rule only, so the text is consistent on its own.
     - The conflict is with ADR-024 d11 ("an owed one keeps the order
       `partially_refunded`", `ADR-024…md:43`) and with BR-063's intent, not inside the
       SRS.
     - So VS-023 implements §20.2 verbatim. The reorder becomes a VS-030 note: VS-030
       must decide it with an ADR and the co-developer's confirmation, and change
       `derive_order_status`, SRS §20.2 and database-design §17.2 together.
     - In VS-023 the refund inputs are always "none", so cases A and B are reachable
       only in the unit tests, which pin the SRS result.
2. **Idempotency claim states** (§3.7, §3.8, §4.7, Q7). **CHANGED**.
   - Claims now have `state` (`in_progress` | `done`) and `resource_id` (the order id),
     both set in Tx1.
   - A retry that finds `in_progress` with the same hash gets
     `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` with `order_id`/`order_number`. It never
     re-runs checkout and never calls the provider.
   - The crash window (Tx1 committed, Tx2 never ran) therefore yields exactly one order
     and at most one provider call. The pending attempt is recovered by VS-024's
     reconciliation, which queries by merchant reference (`payment_id`, R3).
   - New crash-simulation tests (§6.2): crash before and after the provider call.
   - The race 2 expectation changes from "both 201" to "one 201, one 201 replay or 409
     in progress".
3. **Webhook rate limiting** (§2.2). **CHANGED**.
   - Order of checks: configured provider → body cap → signature check → bucket.
   - Invalid-signature or unsigned traffic: per-IP bucket `webhook-unverified:{ip}`,
     30/min.
   - Correctly signed traffic: per-provider bucket `webhook:{provider}`, 600/min.
   - Garbage from one IP cannot drain the legitimate bucket. Test added (§6.2).
4. **The mock provider has no HTTP route that marks a payment paid** (§3.6, Q15).
   - Routes reachable with `PAYMENT_PROVIDER=mock`:
     - `POST /api/v1/checkout` (creates a `pending` mock payment);
     - `POST /api/v1/webhooks/payments/mock` (stores an event only, after the
       `MOCK_WEBHOOK_SECRET` signature check).
   - Both exist only in `development`, `test` and `staging`. In `production` mock
     refuses to boot (§3.9), and the webhook path would 404 anyway.
   - Mock state changes only through `MockPaymentProvider.simulate()`, called by tests
     and by `scripts/mock_pay.py`. The script refuses `ENVIRONMENT=production` and needs
     direct Redis access.
   - Outside `development`/`test`, mock also refuses to boot with the default secret.
5. **Ownership-index violation → domain 409** (§3.2, §3.3).
   - `insert_lines` runs in a SAVEPOINT (the `begin_nested` pattern at
     `src/app/identity/infrastructure/repositories.py:329`) and matches the asyncpg
     `constraint_name` (the helper pattern at
     `src/app/catalog/infrastructure/repositories.py:116-121`).
   - Only `uq_order_items_stl_ownership` maps to `409 PRODUCT_ALREADY_OWNED`. Any other
     violation re-raises (500). Test added (§6.2).
6. **Order number collision** (§3.3). The order INSERT runs in a SAVEPOINT. A violation
   of `uq_orders_order_number` regenerates the number, up to 5 attempts, then raises.
   The outer transaction is never poisoned. Forced-collision tests added (§6.2).
7. **Verification latency** (§2.2, §2.4, Q12). **CHANGED**.
   - Cron-only worst case: one tick (60 s) plus the backlog ahead in a 50-event batch.
     With a degraded provider (10 s timeout per query) that reaches about 60 + 500 s.
   - Verifying inline before answering would break SRS §9.2 step 2 ("Return 200
     quickly", `SRS.md:751`).
   - Recommended: a FastAPI `BackgroundTasks` verification that runs **after** the 200
     is sent, with the minute cron as fallback. Typical delay becomes one provider
     round trip. Worst case stays at the cron bound if the API process dies or the
     provider is down.
8. **Late captures before VS-030** (§3.6, §4.5).
   - Each one writes audit `payment.late_capture` (entity `payment`; `after_data`
     carries order id, captured amount, reason).
   - It also writes an error-level structured log `payment_late_capture`.
   - Visible via `GET /api/v1/admin/audit-logs?action=payment.late_capture`
     (`src/app/platform/api/audit_logs.py:131`, `:144`) and the SQL in §3.6 on the new
     partial index `ix_payments_late_captured`.
   - No notification: there is no admin notification channel, and telling the customer
     before a refund exists would mislead.
   - Sentry is not wired (`sentry_dsn` exists only in `config.py:66`), so the log is not
     yet an external alert (R7).
9. **`PAYMENT_PROVIDER=none`** (§2.1, §3.3, Q5). **CHANGED** from 422.
   - Checkout answers `503 ONLINE_PAYMENT_UNAVAILABLE`, checked right after the kill
     switch, with nothing written and the cart intact.
   - A named but unconfigured provider while others are configured stays
     `422 PAYMENT_METHOD_NOT_ALLOWED` (`SRS.md:1369`).
   - Tests: `none` boots in production for both the API lifespan (`main.py:28`) and the
     worker `on_startup` (`worker.py:39`), checkout gives 503, every webhook path 404.
     Production + mock fails in both.
10. **Consent** (§3.3, Q4, new Q18).
    - Stored: `orders.terms_accepted_at` and `digital_terms_accepted_at` (and
      `cash_terms_accepted_at`, NULL online). database-design `:985-988`.
    - All three are set to one `now` in the `orders` INSERT inside Tx1, the same
      statement as the order (functional-requirements.md:344 requires one transaction).
    - **No terms version is stored.** The spec defines none (`SRS.md:666` "with
      timestamp"; api-endpoints.md:1594 "immutable order timestamps"). Q18 asks whether
      to add one.
11. **PR A** (§8). The exact file list, the main-stays-green argument and the five
    checkpoints with their reports are in §8.
    - The reversibility test already asserts one head without pinning it
      (`tests/integration/test_migration_reversibility.py:53`). PR A adds an
      orders-revision block in the same style.
    - A new model/migration parity test compares the six new tables.
12. **Citations for every column and CHECK built ahead of its slice** (§4.10): each has
    a database-design line, or is marked as a plan addition. Every CHECK for unbuilt
    behaviour is listed with its database-level test.

---

## 1. Scope and non-goals

### In scope (VS-023 only)

1. One migration: the enums, `orders`, `order_items`, `order_status_history`,
   `payments`, `webhook_events`, `idempotency_records`, with their **full frozen
   columns and CHECKs** (§4), so VS-023b, VS-024, VS-028, VS-029 and VS-030 need no
   destructive change.
2. `POST /api/v1/checkout` for **STL-only carts, paid online** (mock provider).
3. `POST /api/v1/webhooks/payments/{provider}` (provider-neutral, ADR-024 d13).
4. `GET /api/v1/me/stl-ownership?product_id=` (ADR-025 d2).
5. The STL ownership refusal in the cart (`409 PRODUCT_ALREADY_OWNED`, filling the
   placeholder at `src/app/ordering/application/services/cart.py:43`).
6. The payment-provider port, a **mock adapter** covering every verification branch,
   and a provider contract test suite VS-032 reuses.
7. The shared **verify-and-apply** path (query the provider outside locks, apply under
   the ADR-024 lock order), used by the webhook-triggered job now and by VS-024's
   reconciliation and manual confirmation later.
8. `derive_order_status()`: the full SRS §20.2 projection, cash branch included, pure
   and unit-tested on every branch.
9. A generic Platform idempotency service (VS-030 reuses it for refunds).
10. Jobs: `verify_payments` (every minute) and `purge_expired_idempotency_records`
    (daily).
11. Startup refusal of `ENVIRONMENT=production` with the `mock` provider (API and
    worker).
12. Docs: ADR-032, `docs/checkout.md`, spec updates (§7).

### Non-goals, and exactly who owns them

| Left to | What | Why it is not here |
|---|---|---|
| **VS-023b** (co-developer) | `GET /admin/stl-deliveries`; `POST /admin/orders/{id}/items/{item_id}/transition` (`awaiting_delivery → delivered`); the queue index `order_items(created_at) WHERE product_type='stl' AND fulfillment_status='awaiting_delivery'`; deleting `daily_download_cap`; removing `src/app/digital_assets`; the "your STL file has been sent" email/notification. | Separate slice. VS-023 **does** create `order_items.delivered_by`, `fulfilled_at` and both delivery CHECKs (§4.2), so VS-023b's migration is index + setting delete only (`docs/vertical-slice-plan.md:567` "unless VS-023 already created them"). |
| **VS-024** | Retry (`POST /me/orders/{id}/payments`), `reconcile_payments`, `release_stale_checkouts` (which sets `orders.cancelled_at` and cancels lines), manual confirm, the admin payments views, and its two "Must resolve before build" items (`docs/vertical-slice-plan.md:637+`). | VS-023 leaves a failed/expired attempt `pending_payment` (BR-058); nothing in VS-023 cancels an order. VS-024 reuses `verify_payment()` / `apply_provider_result()` (§3.6). |
| **VS-028** | Physical and mixed carts, delivery/pickup, address `FOR SHARE`, phone normalisation + `contact_phone_hash` (`PHONE_HASH_SALT`), cash eligibility and limits, the phone advisory lock, dispatch estimate, the three cash settings, deleting `free_shipping_threshold`. | VS-023 answers `422 INVALID_FULFILLMENT` for any physical line and `422 PAYMENT_METHOD_NOT_ALLOWED` for `cash` (`docs/vertical-slice-plan.md:538`). All order columns VS-028 needs already exist (`:684` "No order columns (they come from VS-023)"). |
| VS-025 | `GET /me/orders*`, `OrderDetail`, `payment_due`/`can_cancel`. | VS-023 returns only a minimal `CheckoutRead`. |
| VS-030 | `refunds`, `refund_items`, the automatic `late_capture` refund obligation. | VS-023 records `late_captured_at` + an alert only; VS-030 must also create obligations for rows already late-captured (§9 R7). |
| VS-032 | Real provider value(s), adapter, list-of-providers setting, `whish_*` rename. | ADR-024 d13; SRS §30.4 open. |
| VS-039/041 | Offers, `order_items.offer_id` FK, offer checkout. | `offers` does not exist; `offer_id` is created nullable **without** FK (§4.2). |

---

## 2. API and jobs

### 2.1 `POST /api/v1/checkout`

- **Auth:** `current_verified_user` + `require_csrf` + per-user rate limit (Q17:
  30/hour, key `checkout:{user_id}`, fail closed, as the cart).
- **Header:** `Idempotency-Key` required: 8–255 chars of `[A-Za-z0-9._:-]`. Missing or
  malformed → `422 VALIDATION_ERROR` (FastAPI header validation; same envelope as
  every other 422).
- **Body `CheckoutRequest`** (`extra="forbid"`, api-endpoints §29.5):

  ```text
  payment_method: "online" | "cash"          # cash → 422 PAYMENT_METHOD_NOT_ALLOWED (VS-028)
  payment_provider?: str                     # must be configured; default = the one configured
  fulfillment_method?: "delivery" | "pickup" # any value → 422 INVALID_FULFILLMENT (VS-028)
  address_id?: UUID                          # present → 422 INVALID_FULFILLMENT
  contact_phone?: str                        # present → 422 INVALID_FULFILLMENT
  customer_note?: str                        # ≤ 1000 chars, control chars refused
  accept_terms: Literal[True]
  accept_digital_final_sale?: Literal[True]  # required when any STL line remains
  accept_cash_terms?: Literal[True]          # accepted and ignored for online (VS-028 uses it)
  accepted_price_changes?: list[{product_id, amount_cents, currency}]  # ≤ 50 entries
  ```

  No client amount, total or price is accepted (BR-031; `extra="forbid"` refuses one).

- **Success `201 CheckoutRead`:**

  ```text
  order: { id, order_number, source: "cart", status: "pending_payment",
           payment_method: "online", fulfillment_method: null,
           subtotal{amount_cents,currency}, tax{…=0}, total{…}, placed_at,
           lines[{ id, product_id, product_type: "stl", name, unit_price{…},
                   quantity: 1, line_total{…}, fulfillment_status: "pending" }] }
  payment: { id, status: "pending", provider, redirect_url? }
  dropped_lines: [{ product_id, reason: "already_owned" }]   # SRS §7.3 step 5
  ```

  A replay returns the stored status and body with header `Idempotent-Replayed: true`.

- **Errors** (RFC 9457 `ApiError`, codes from `docs/requirments/api-endpoints.md:155-196`):

  | Status | Code | When | Extension |
  |---|---|---|---|
  | 401 | `AUTH_REQUIRED` | no session | — |
  | 403 | CSRF / `EMAIL_VERIFICATION_REQUIRED` | — | — |
  | 409 | `IDEMPOTENCY_KEY_CONFLICT` | same key, different request hash | — |
  | 409 | `IDEMPOTENCY_REQUEST_IN_PROGRESS` | same key and hash, claim still `in_progress` (concurrent request, or a crash between Tx1 and Tx2) | `order_id`, `order_number`; `Retry-After: 2` |
  | 409 | `CART_EMPTY` | no cart, no lines, or every line dropped as owned | `dropped_lines` |
  | 409 | `CART_PRICE_CHANGED` | live price ≠ snapshot and not exactly accepted | `price_changes[{product_id, old_amount_cents, new_amount_cents, currency}]` |
  | 409 | `PRODUCT_ALREADY_OWNED` | ownership-index violation on insert (STL held by another live order of this user) | `product_id` |
  | 422 | `PRODUCT_NOT_PURCHASABLE` | any line `not_listed`/`unavailable`/`whatsapp_only` (over-cap lines listed too) | `lines[{product_id, reason, max_quantity?}]` |
  | 422 | `QUANTITY_EXCEEDS_LIMIT` | only cap failures | `lines[…reason: "over_cap", max_quantity]` |
  | 422 | `INVALID_FULFILLMENT` | a physical line, or any fulfillment/address/phone field | — |
  | 422 | `PAYMENT_METHOD_NOT_ALLOWED` | `cash`; a named `payment_provider` that is not configured; $0 total (Q8) | `reason` |
  | 422 | `VALIDATION_ERROR` | schema; STL remains without `accept_digital_final_sale` | field errors |
  | 429 | `RATE_LIMITED` | — | — |
  | 502 | `PAYMENT_PROVIDER_UNAVAILABLE` | provider create failed **after** commit (Q14) | `order_id`, `order_number` |
  | 503 | `ORDERS_PAUSED` | `accepting_orders = false` | — |
  | 503 | `ONLINE_PAYMENT_UNAVAILABLE` | `PAYMENT_PROVIDER=none` (no online provider configured), checked after the kill switch; nothing written (Q5) | — |

  `PAYMENT_ALREADY_ACTIVE` (listed on the api row) cannot occur on a fresh order; it is
  VS-024's retry code. Doc note added (§7).

### 2.2 `POST /api/v1/webhooks/payments/{provider}`

- No cookies, no CSRF (api-endpoints.md:120). IP allowlisting is VS-020's nginx.
- **Order of checks** (Revision 1 item 3). Each check runs only if the previous one
  passed:
  1. `{provider}` must be in the configured online set (`cash` never, `mock` never in
     production). Otherwise **`404`, nothing stored, no bucket touched** (SRS:1386).
  2. The body must be ≤ 64 KiB, else `400 VALIDATION_ERROR`, read with a bounded
     stream.
  3. The adapter checks the signature (`parse_webhook`), a constant-time HMAC.
  4. **Invalid signature, or a provider without signature support:** counted against
     `enforce_rate_limit(key_prefix="webhook-unverified", subject=client_ip, limit=30,
     window_seconds=60)` (`src/app/core/rate_limit.py:19`).
     - An invalid signature then gets `401`, nothing stored, and an error log (SRS §9.2
       step 3).
     - An unsigned provider's event proceeds to storage.
     - Not storing forged events stops them squatting a real `provider_event_id` (R4).
  5. **Valid signature:** counted against `key_prefix="webhook"`, `subject=provider`,
     `limit=600`, `window_seconds=60`. Over the limit gives `429` and the provider
     retries.
  6. `INSERT … ON CONFLICT (provider, provider_event_id) DO NOTHING`; respond `200
     {received: true}` either way (BR-056). The payment link is resolved at receipt
     (§4.6, Q2).
- Invalid traffic only ever spends the per-IP unverified bucket, so a flood of forged
  bodies cannot exhaust the legitimate per-provider bucket. Verifying the HMAC before
  any bucket costs one hash over at most 64 KiB, which the body cap bounds.
- No provider query, lock or payment change happens before the response (SRS §9.2
  step 2). After the 200 has been sent, a `BackgroundTasks` callback runs
  `verify_event(event_id)` (§2.4, Q12).

### 2.3 `GET /api/v1/me/stl-ownership?product_id=<uuid>`

- `current_user` (verification not required, ADR-025 d2). Missing/malformed id →
  `422 VALIDATION_ERROR`; anonymous → `401 AUTH_REQUIRED`.
- `200 {product_id, owned}`. `owned` = the product is **listed and STL** (Catalog
  `CartProductReader`) **and** the caller has a line with `fulfillment_status IN
  ('awaiting_delivery','delivered')`. Unknown, hidden or physical → `false`. The
  caller's own unpaid (`pending`) line → `false` (ADR-025 `:38`). No rate limit (a
  read, like `GET /cart`).
- Mounted through `app/api/v1/me.py` (as the wishlist), router in
  `app/ordering/api/ownership.py`.

### 2.4 Jobs (`src/app/jobs/registry.py`)

| Job | Cadence | What |
|---|---|---|
| `verify_payments` | `cron(second=0, run_at_startup=True)` every minute | **Fallback** for the post-response background verification (§2.2). Processes up to 50 unprocessed `webhook_events`, oldest first, through `verify_event()` (§3.6). Idempotent; overlapping runs are safe. |
| `purge_expired_idempotency_records` | daily `03:53` | `DELETE … WHERE expires_at < now()` in batches of 1000 with `SKIP LOCKED`, capped at 50 batches, like `purge_security_records.py`. |

Both are thin entrypoints calling application use cases (ADR-011 `:13`).

**Delay from webhook receipt to `paid`** (Revision 1 item 7):
- **Typical, with background verification:** the time to send the 200, plus one
  provider status query, plus Tx B. Well under a second against the mock.
- **Worst case:** the background task is lost (API process restarts after the 200) or
  the provider is down. The cron then takes over:
  - up to 60 s to the next tick;
  - plus the backlog ahead of the event in its 50-event batch (≤ 50 × the 10 s provider
    timeout ≈ 500 s when the provider is degraded);
  - a provider that stays down keeps the event unprocessed until it answers.
- **Rejected: inline verification before the 200.** It violates SRS §9.2 step 2 ("Return
  200 quickly", `SRS.md:751`), ties the provider's webhook timeout to our provider
  query, and multiplies retries.
- **Rejected: cron only.** It is simpler, but a 60 s floor is visible to a customer
  returning from the payment page.

---

## 3. Layers, function by function

### 3.0 Package ownership (resolves Q1)

| Package | Owns in VS-023 | Evidence |
|---|---|---|
| `app.ordering` | `orders`, `order_items`, `order_status_history`; checkout; `derive_order_status`; STL ownership query + `/me/stl-ownership`; the order-side half of payment apply | database-design §4 "Ordering" lists 18–22 (`database-design.md:415-422`); the cart and its lock already live here |
| `app.payments` | `payments`, `webhook_events`; provider port + mock adapter; webhook route; verify-and-apply orchestration | ADR-005 `:13` (Payments is a context); ADR-012 `:13` "Payments-owned provider port"; ADR-013 `:13` "Payment remains Payments-owned"; database-design §4 "Payments" (`:424`) |
| `app.platform` | `idempotency_records` + `IdempotencyStore` + purge use case | database-design §4 "Platform" item 39 (`:454`) |
| `app.fulfillment` | **nothing in VS-023** | ADR-019 d8 (`ADR-019…md:23`) puts STL *delivery state transitions* in Fulfillment → VS-023b. Fulfillment "owns no tables of its own: line state lives on `order_items`" (`database-design.md:433`, `:1407`). The `pending → awaiting_delivery` move is part of payment apply "in the same transaction" (ADR-019 d2 `:17`), so it runs through `ordering.public` inside the Payments apply transaction. |

**Dependency direction (no import cycle):**
- `app.payments.application` → `app.ordering.public` (lock order, mark lines paid,
  recompute status).
- `app.ordering.application` depends only on its own ports. Checkout writes the
  pending payment through an **Ordering port** `PaymentAttempts`, whose adapter
  `SqlPaymentAttempts` is exported by `app.payments.public` and wired in
  `app.ordering.api.checkout` (the API layer, like `cart.py` wiring
  `app.catalog.public`).
- `ordering.public` never imports `ordering.api`, so `ordering.api → payments.public →
  payments.application → ordering.public` has no cycle.
- New architecture test: `app.ordering.{domain,application,infrastructure,public}`
  never import `app.payments`; `app.payments.domain` never imports `app.ordering`.

### 3.1 `app.ordering.domain` (pure)

**`enums.py`** (new): `OrderSource`, `OrderStatus`, `OrderItemStatus`,
`FulfillmentMethod`, `PaymentMethod`, `CancelReason` (`StrEnum`, values exactly as
database-design §3.4–3.7).

**`orders.py`** (new): frozen dataclasses `Order`, `OrderLine`, `NewOrder`,
`NewOrderLine`, `StatusChange`.

**`order_status.py`** (new):

```python
@dataclass(frozen=True)
class LineState:
    status: OrderItemStatus


@dataclass(frozen=True)
class OrderStatusInputs:
    payment_method: PaymentMethod
    cancelled_at_set: bool  # orders.cancelled_at IS NOT NULL
    payment_reached_paid: bool  # a payment in paid / partially_refunded / refunded
    lines: tuple[LineState, ...]
    refunds_cover_paid: bool = False  # non-failed, non-late_capture refunds ≥ paid amount
    refund_present: bool = False  # a non-failed or owed (failed, not reissued) refund


def derive_order_status(i: OrderStatusInputs) -> OrderStatus:
    """SRS §20.2 exactly as written (SRS.md:1172-1186). The only writer of orders.status."""
```

Rule order: **SRS §20.2 verbatim** (Revision 1 item 1; `docs/SRS.md:1172-1186`):
1. online, no payment reached paid: `cancelled_at_set` → `cancelled`, else
   `pending_payment`;
2. cash, no payment yet: all lines `cancelled` → `cancelled`, else `in_progress`;
3. paid: all lines `cancelled` → `cancelled`;
4. paid: `refunds_cover_paid` → `refunded`;
5. paid: all lines `refunded` → `refunded`;
6. paid: `refund_present` → `partially_refunded`;
7. paid: all lines terminal (`delivered`, `picked_up`, `refunded`, `cancelled`) →
   `completed`;
8. otherwise `in_progress`.

- The refund inputs default to "none" until VS-030 supplies them.
- **Note for VS-030** (not decided here): the PR #8 review case
  (`vertical-slice-plan.md:820`) gives `refunded` for case A and `cancelled` for case B
  (Revision 1 item 1 table), while ADR-024 d11 wants `partially_refunded`.
- Changing the rule order needs an ADR and the co-developer's confirmation, and must
  change this function, SRS §20.2, database-design §17.2 and the pinned unit tests
  together.

**`checkout_rules.py`** (new, pure; uses `app.catalog.application.ports` types as
`cart_rules.py` does):
- `collect_refusals(lines, products) -> list[LineRefusal]`: every line whose product is
  missing or has `purchase_refusal(product)`, or is physical over `cap_for(product)`.
  Raises `CheckoutLinesRefusedError(refusals, only_caps: bool)`.
- `require_digital_only(lines, request)`: a physical line or any fulfillment field →
  `InvalidFulfillmentError`.
- `split_owned(lines, owned_ids) -> (kept, dropped)`: SRS §7.3 step 5.
- `price_changes(kept, products, accepted) -> list[PriceChange]`: a change counts as
  accepted only if `accepted` holds exactly `(product_id, live amount, currency)`; a
  second change fails again (api-endpoints.md:380).
- `price_lines(kept, products) -> tuple[NewOrderLine, ...]`: the **live**
  `price_cents`, `line_total = unit × quantity`, name and cover snapshot (ADR-029 d3).
- `totals(lines) -> Totals(subtotal, tax=0, total)` (ADR-024 d1).
- `require_consent(request, has_stl)`.

**`order_number.py`** (new): `new_order_number(rand) -> str`, `B3D-` + 8 Crockford
base32 characters (Q11).

**`exceptions.py`** (extend): `CartEmptyError(dropped)`, `CartPriceChangedError(changes)`,
`CheckoutLinesRefusedError`, `InvalidFulfillmentError`, `PaymentMethodNotAllowedError(reason)`,
`ProductAlreadyOwnedError(product_ids)`, `OrdersPausedError`, `ConsentRequiredError`,
`OnlinePaymentUnavailableError`, `OrderNumberExhaustedError`.

### 3.2 `app.ordering.application.ports` (extend)

```python
class OrderStore(Protocol):
    async def insert_order(self, order: NewOrder) -> Order: ...
    async def insert_lines(self, order_id: UUID, lines: Sequence[NewOrderLine]) -> list[OrderLine]: ...
    async def add_history(self, changes: Sequence[StatusChange]) -> None: ...
    async def lock_order(self, order_id: UUID) -> Order | None:            # FOR UPDATE
    async def lock_lines(self, order_id: UUID) -> list[OrderLine]: ...      # FOR UPDATE ORDER BY id
    async def set_line_status(self, line_ids: Sequence[UUID], status: OrderItemStatus) -> None: ...
    async def set_order_status(self, order_id: UUID, status: OrderStatus) -> None: ...
    async def owned_stl_product_ids(self, user_id: UUID, product_ids: Sequence[UUID]) -> set[UUID]: ...

class PaymentAttempts(Protocol):          # implemented by Payments (§3.0)
    async def open_attempt(self, *, order_id: UUID, amount_cents: int, currency: str,
                           provider: str) -> PaymentAttemptRef: ...
    def configured_providers(self) -> frozenset[str]: ...
```

**SAVEPOINTs** (Revision 1 items 5 and 6) follow the existing patterns: the identity
repository's `begin_nested()` around a racing INSERT
(`src/app/identity/infrastructure/repositories.py:329`), and the catalogue's
structural constraint match on `error.orig.__cause__.constraint_name`
(`src/app/catalog/infrastructure/repositories.py:116-121`).

- `SqlOrderStore.insert_order(order, number_factory)` runs
  `async with session.begin_nested(): INSERT; flush`.
  - A `UniqueViolationError` on **`uq_orders_order_number` only** rolls back the
    savepoint and retries with a fresh number, up to 5 attempts.
  - After the fifth it raises `OrderNumberExhaustedError`, which is a 500 and logged.
  - Any other violation re-raises.
  - The outer transaction is never poisoned, so the cart lock and the idempotency claim
    stay valid.
- `SqlOrderStore.insert_lines` runs in its own savepoint.
  - A violation of **`uq_order_items_stl_ownership` only** rolls back the savepoint.
  - It then reads which of the order's STL product ids are held by another live line of
    this user, and raises `ProductAlreadyOwnedError(product_ids)`.
  - Any other `IntegrityError` re-raises (500).
  - The route rolls back Tx1 entirely and maps the error to `409 PRODUCT_ALREADY_OWNED`
    (§3.8): nothing is written, the cart is intact, and no claim remains.

### 3.3 `app.ordering.application.services.checkout` (new)

```python
@dataclass(frozen=True)
class PlacedOrder:
    order: Order
    lines: tuple[OrderLine, ...]
    payment: PaymentAttemptRef
    dropped: tuple[UUID, ...]

async def place_order(
    *, carts: CartStore, products: CartProductReader, orders: OrderStore,
    attempts: PaymentAttempts, settings: SettingsReader, audit: AuditWriter,
    user: CheckoutCustomer, request: CheckoutCommand, now: datetime,
) -> PlacedOrder:
```

It runs inside the caller's transaction, does not commit, and runs **after** the
idempotency claim (§3.7). Steps, mapped to SRS §7.3 (`SRS.md:650-666`):

| # | Step | SRS §7.3 | Locks / statements |
|---|---|---|---|
| 1 | *(caller)* idempotency claim | 1 | INSERT `idempotency_records` (unique-index wait only) |
| 2 | `settings.get_bool("accepting_orders")` false → `OrdersPausedError` | 2 | read |
| 2b | `attempts.configured_providers()` empty (`PAYMENT_PROVIDER=none`) → `OnlinePaymentUnavailableError` (503) | 9 | — |
| 3 | `lock_cart_for_checkout(carts, user_id=…)`; None or no lines → `CartEmptyError(())` | 3 | `carts FOR UPDATE`; lines read |
| 4 | `products.get_many(ids)`; `collect_refusals` | 4, 6 | one read, **no** product locks (ADR-029 d4) |
| 5 | `require_digital_only` (VS-028 removes it) | 7 | — |
| 6 | `request.payment_method == cash` → `PaymentMethodNotAllowedError("cash_requires_physical")` | 9 | — |
| 7 | `orders.owned_stl_product_ids`; `split_owned`; nothing kept → `CartEmptyError(dropped)` | 5 | one read |
| 8 | `price_changes` → `CartPriceChangedError` | §7.2 | — |
| 9 | `require_consent(request, has_stl=True)` | 13 (validated) | — |
| 10 | `price_lines`, `totals`; total 0 → `PaymentMethodNotAllowedError("zero_total")` (Q8) | 8 | — |
| 11 | provider = request's or the single configured one; not configured → `PaymentMethodNotAllowedError("provider_not_configured")` | 9 | — |
| 12 | `insert_order` in a savepoint with number retry (status from `derive_order_status` = `pending_payment`; consent below; `customer_email_snapshot = user.email`), `insert_lines` in a savepoint (all `pending`; ownership violation → 409), `attempts.open_attempt` (`pending`, amount = total), `add_history` (order `None → pending_payment`), `audit.record("order.placed")` | 10, 13 (written) | INSERTs only; implicit FK `KEY SHARE` on `users`, `products`, the new `orders` row |
| 12b | *(caller)* `idempotency.attach(record_id, resource_id=order.id)` | 1 | UPDATE own claim row |
| 13 | `clear_cart(carts, locked)` | 12 | under the same cart lock |

The service never calls the provider.

**Consent stored** (Revision 1 item 10):
- `orders.terms_accepted_at = now` and `orders.digital_terms_accepted_at = now` (STL
  present); `cash_terms_accepted_at` is NULL for online orders (database-design
  `:984-986`).
- All three are columns of the **same `orders` INSERT** in Tx1, so the consent record and
  the order commit or roll back together (functional-requirements.md:344).
- The request flags are validated before any write.
- No terms version is stored: none is specified (Q18).

### 3.4 `app.ordering.application.services.cart` (change)

- `add_item(carts, products, orders: OrderStore, …)`: after `quantity_after_add`, for an
  STL, `orders.owned_stl_product_ids(user_id, [product_id])` non-empty →
  `ProductAlreadyOwnedError` → `409 PRODUCT_ALREADY_OWNED`. It is the same query as
  checkout and the ownership endpoint, so the three agree. Only `awaiting_delivery` and
  `delivered` count; the user's own `pending` line does not (ADR-025 `:38`).
- `lock_cart_for_checkout` and `clear_cart` are unchanged.

### 3.5 `app.ordering.public` (new) — the interface VS-023b, VS-024, VS-028 and VS-029/030 consume

```python
# Re-exports
OrderStatus, OrderItemStatus, PaymentMethod, FulfillmentMethod, CancelReason
derive_order_status, OrderStatusInputs, LineState


@dataclass(frozen=True)
class LockedOrder:
    order: Order
    lines: tuple[OrderLine, ...]  # locked FOR UPDATE, ascending id


async def lock_order_for_change(session: AsyncSession, order_id: UUID) -> LockedOrder | None:
    """ADR-024 d9 steps 1-2: orders FOR UPDATE, then every line FOR UPDATE by id."""


async def mark_order_paid(session: AsyncSession, locked: LockedOrder, *, at: datetime) -> PaidOrder:
    """STL lines pending → awaiting_delivery; physical stay pending; history rows;
    recomputes status. The caller holds the payment lock (step 3) already."""


async def recompute_order_status(
    session: AsyncSession, locked: LockedOrder, inputs: OrderStatusInputs
) -> OrderStatus:
    """Writes orders.status and a history row only on change."""


async def stl_owned(session: AsyncSession, *, user_id: UUID, product_id: UUID) -> bool: ...
```

- VS-023b calls `lock_order_for_change`, then its own transition, then
  `recompute_order_status`.
- VS-024 calls the Payments functions in §3.6, which call these.
- VS-039 calls `stl_owned`.

### 3.6 `app.payments`

**`domain/enums.py`:** `PaymentStatus` (7 values), `PaymentProvider` (`mock`, `cash`).

**`domain/outcome.py`** (pure, the heart of verification):

```python
@dataclass(frozen=True)
class ProviderResult:
    state: Literal["pending", "processing", "paid", "failed", "expired"]
    captured_amount_cents: int | None
    currency: str | None

class Outcome(StrEnum):
    APPLY_PAID = "apply_paid"; MARK_PROCESSING = "mark_processing"
    MARK_FAILED = "mark_failed"; MARK_EXPIRED = "mark_expired"
    LATE_CAPTURE = "late_capture"; LATE_CAPTURE_AND_FAIL = "late_capture_and_fail"
    NOOP = "noop"

def decide(*, payment_status: PaymentStatus, payment_amount_cents: int,
           order_total_cents: int, order_cancelled: bool, result: ProviderResult) -> Outcome:
```

Decision table (SRS §9.2, §20.1; ADR-024 d15):

| Payment status | Order cancelled | Provider says | Amount | → Outcome |
|---|---|---|---|---|
| `paid`/`partially_refunded`/`refunded` | any | paid | any | `NOOP` (duplicate success) |
| `pending`/`processing` | no | paid | captured = amount = order total, USD | `APPLY_PAID` |
| `pending`/`processing` | no | paid | mismatch (under or over) or not USD | `LATE_CAPTURE_AND_FAIL` |
| `pending`/`processing` | yes | paid | any | `LATE_CAPTURE_AND_FAIL` |
| `failed`/`expired` | any | paid | any | `LATE_CAPTURE` (idempotent: only if `late_captured_at` is null) |
| `pending` | — | processing | — | `MARK_PROCESSING` |
| `pending`/`processing` | — | failed / expired | — | `MARK_FAILED` / `MARK_EXPIRED` |
| any other combination | | | | `NOOP` |

**`application/ports.py`:**

```python
class PaymentProviderPort(Protocol):
    name: str
    supports_status_query: bool
    async def create_payment(self, req: CreatePayment) -> CreatedPayment: ...
        # req: payment_id (merchant reference), order_number, amount_cents, currency, return_url
        # → provider_payment_id, redirect_url | None
    async def query_status(self, ref: PaymentRef) -> ProviderResult: ...
        # ref: payment_id + provider_payment_id | None; raises ProviderUnavailableError
    def parse_webhook(self, headers: Mapping[str, str], body: bytes) -> ParsedEvent: ...
        # raises InvalidSignatureError / MalformedEventError

class PaymentStore(Protocol):
    async def insert_pending(...) -> PaymentAttemptRef: ...
    async def get(self, payment_id) -> Payment | None: ...             # no lock
    async def lock(self, payment_id) -> Payment | None: ...            # FOR UPDATE, after orders
    async def find_by_reference(self, provider_payment_id) -> Payment | None: ...
    async def set_provider_reference(...); async def mark(...) ...
class WebhookEventStore(Protocol):
    async def insert_if_new(self, event: NewWebhookEvent) -> bool: ...
    async def unprocessed_ids(self, limit: int) -> list[UUID]: ...     # no lock
    async def mark_processed(self, event_id, *, error: str | None) -> None: ...
    async def record_error(self, event_id, error: str) -> None: ...    # stays unprocessed
```

**`application/services/payments.py`:**

```python
async def start_online_payment(
    session_factory, providers, *, payment_id, return_url
) -> StartResult:
    """Called by the checkout route after COMMIT. Holds no transaction during the
    provider call; then one short tx stores the reference or marks the attempt failed."""


async def receive_webhook(session, providers, *, provider: str, headers, body) -> None:
    """Parse (signature) → resolve payment by reference → INSERT ON CONFLICT DO NOTHING.
    A provider mismatch is stored already processed with error and alerted."""


async def verify_event(session_factory, providers, event_id: UUID) -> Outcome | None:
    """Tx A read → provider query outside any tx → apply_provider_result + mark processed."""


async def verify_payment(session_factory, providers, payment_id: UUID) -> Outcome:
    """Same without an event: VS-024's reconciliation entrypoint."""


async def apply_provider_result(
    session,
    payment_id: UUID,
    result: ProviderResult,
    *,
    source: Literal["webhook", "reconcile", "manual"],
    actor_user_id: UUID | None,
) -> Outcome:
    """Tx B, ADR-024 order: ordering.lock_order_for_change → payments.lock → decide →
    write. VS-024's manual confirm calls this with its own ProviderResult."""
```

`apply_provider_result` writes:
- **`APPLY_PAID`:** payment `paid` + `verified_at`; `ordering.public.mark_order_paid`;
  audit `payment.verified` (lines moved in `after_data`); outbox template
  `order_payment_confirmed` to `orders.customer_email_snapshot` ("the administrator will
  email your file to …", `docs/vertical-slice-plan.md:534`); `create_notification(type=
  PAYMENT, payload={"event": "payment.confirmed", "order_id", "order_number"})`.
- **`MARK_*`:** status + `failed_at`/`expired_at`; audit `payment.failed`/`payment.expired`;
  recompute (stays `pending_payment`).
- **`LATE_CAPTURE*`:** `late_captured_at` (+ `failed`/`failed_at` when live); lines
  untouched. Visible before VS-030 through (Revision 1 item 8):
  - **audit row** `payment.late_capture`: `actor_user_id=None`, `entity_type="payment"`,
    `entity_id=payment.id`, `after_data={order_id, order_number, captured_amount_cents,
    expected_amount_cents, attempt_status, reason: amount_mismatch | attempt_not_live |
    order_cancelled, source}`;
  - **error log** `logger.aerror("payment_late_capture", payment_id=…, order_id=…,
    reason=…)`. Sentry is not wired yet (`config.py:66` only), so this is a log line,
    not a page (R7);
  - **listing:** the admin audit viewer `GET
    /api/v1/admin/audit-logs?action=payment.late_capture`
    (`src/app/platform/api/audit_logs.py:131`, filter `:144`), and for operators and
    VS-030's backfill:
    ```sql
    SELECT id, order_id, provider, amount_cents, status, late_captured_at
    FROM payments WHERE late_captured_at IS NOT NULL ORDER BY late_captured_at;
    ```
    served by `ix_payments_late_captured` (§4.5);
  - **no notification:** no admin notification channel exists, and a customer message
    before a refund obligation exists would promise something nobody tracks.
- **`NOOP`:** nothing.

**`infrastructure/providers/mock.py`:** `MockPaymentProvider`, state in Redis hash
`mock_payment:{payment_id}` (status, amount, captured amount; TTL 7 days), shared by
the API and the worker (Q15).

**HTTP routes reachable with the mock provider** (Revision 1 item 4). There is no other
route, and no dev or test endpoint is added.

| Route | What it does with mock | development / test | staging | production |
|---|---|---|---|---|
| `POST /api/v1/checkout` | creates a `pending` mock payment (`create_payment`) | yes | yes | **unreachable**: mock refuses to boot (§3.9) |
| `POST /api/v1/webhooks/payments/mock` | stores an event after the `MOCK_WEBHOOK_SECRET` HMAC check; it **cannot change payment state**, because verification reads the mock's own Redis state | yes | yes, only with a non-default secret (boot refuses the default outside development/test) | **404** (not configurable; boot refuses mock) |
| `GET /api/v1/me/stl-ownership`, `POST /api/v1/cart/items` | read and refuse ownership; provider-independent | yes | yes | yes (with a real provider) |

- **Nothing reachable over HTTP marks a mock payment paid.** Only
  `MockPaymentProvider.simulate()` changes mock state. It is called by tests and by
  `scripts/mock_pay.py`.
- The script exits non-zero when `ENVIRONMENT=production`, and needs direct Redis access
  and the webhook secret.
- `redirect_url` points at the frontend, not at an API route.
- `create_payment` stores `pending` and returns `provider_payment_id = "mock_" + hex`,
  `redirect_url = {frontend_base_url}/checkout/return?order={order_number}`.
- `query_status` looks up by `payment_id` (works even without `provider_payment_id`,
  R3).
- `parse_webhook` requires `X-Mock-Signature: hex(HMAC-SHA256(mock_webhook_secret,
  body))` and JSON `{event_id, payment_reference, type}`.
- `simulate(payment_id, state, captured_amount_cents)` is for tests and
  `scripts/mock_pay.py` (dev only).
- Branches covered: paid, underpaid, overpaid, failed, expired, processing, timeout
  (`ProviderUnavailableError`), bad signature, duplicate event, late success after
  expiry.

**`infrastructure/providers/factory.py`:** `ADAPTERS: dict[str, Callable[[Settings],
PaymentProviderPort]]` (`{"mock": …}`), and

```python
def configured_payment_providers(settings: Settings) -> Mapping[str, PaymentProviderPort]:
    """Raise PaymentConfigurationError for an unknown name, 'cash', mock in production,
    or mock with the default secret outside development/test. 'none' gives {}."""
```

It is exported through `app.payments.public`. Tests register a stub adapter in `ADAPTERS`.

**`infrastructure/`:** `SqlPaymentStore`, `SqlWebhookEventStore`, `SqlPaymentAttempts`
(the Ordering port adapter), `models.py` (`PaymentModel`, `WebhookEventModel`).

**`api/webhooks.py`:** the router `prefix="/webhooks/payments"`, mounted in
`app/api/v1/router.py`.

### 3.7 `app.platform` — idempotency

**`application/ports/idempotency.py`:**

```python
class IdempotencyStore(Protocol):
    async def claim(
        self, *, scope: str, user_id: UUID | None, key: str, request_hash: str, expires_at: datetime
    ) -> Claim: ...
    async def attach(self, record_id: UUID, *, resource_id: UUID) -> None: ...
    async def complete(self, record_id: UUID, *, status_code: int, body: dict) -> None: ...
    async def purge_expired(self, *, now: datetime, limit: int) -> int: ...
```

`Claim` is one of `New(record_id)`, `Replay(status_code, body)`, `InProgress(resource_id)`
or `Conflict()`.

**Claim states** (Revision 1 item 2):

| `state` | Set by | Columns | Meaning |
|---|---|---|---|
| `in_progress` | Tx1: `claim` inserts it; `attach` sets `resource_id` = the new order id before COMMIT | `status_code`, `response_body` NULL; `resource_id` set at commit | the order and its pending payment exist; the provider call may or may not have happened |
| `done` | Tx2: `complete` | `status_code` (201 or 502), `response_body` set | the response is final and replayable |

`claim` runs `INSERT … ON CONFLICT ON CONSTRAINT uq_idempotency_records_scope_user_key DO
NOTHING RETURNING id`. If nothing comes back, the insert waited for the other holder to
commit, and `claim` reads the committed row:
- different hash → `Conflict` (409 `IDEMPOTENCY_KEY_CONFLICT`);
- same hash, `done` → `Replay`;
- same hash, `in_progress` → `InProgress(resource_id)` (409
  `IDEMPOTENCY_REQUEST_IN_PROGRESS`, with `order_id` and `order_number`).

It never re-runs checkout, never calls the provider, and never moves the row to `done`.

**After a crash between Tx1's COMMIT and `complete`** (process killed, Tx2 failed):
- The claim stays `in_progress` with the order id. Every retry with that key gets 409
  in progress naming the order, so there is never a second order or a second provider
  call.
- Until the claim expires (24 h), the payment is recovered without the key:
  - VS-024's reconciliation queries the provider by merchant reference `payment_id`
    (R3): it records the reference or marks the attempt failed;
  - the customer sees the order (VS-025) and retries payment (VS-024).
- VS-024 must treat an attempt with no `provider_payment_id` older than the provider
  timeout as a reconciliation candidate (R6).

`request_hash = sha256(scope + "\n" + canonical JSON of the validated body)`, where the
canonical form is `model_dump(mode="json")`, `sort_keys`, compact separators.
Exported by `app.platform.public` as `idempotency_store(session)`. TTL constant
`IDEMPOTENCY_TTL = timedelta(hours=24)` (Q7). `purge_expired_idempotency_records` calls
`purge_expired`.

### 3.8 `app.ordering.api.checkout` — the route and its two transactions

The route does **not** use `get_session` (which commits after the handler, before the
response): the provider call must come after COMMIT. It opens transactions itself from
`request.app.state.db_session_factory`:

```text
Tx1  (one transaction)
     claim                → Replay → stored response | InProgress → 409 | Conflict → 409
     place_order(...)     → domain errors → ROLLBACK → mapped 4xx/503 (claim gone too)
     attach(record, order.id)                      # claim stays in_progress
     COMMIT
No tx: start_online_payment → provider.create_payment (timeout 10 s)
Tx2  success: payments.provider_payment_id, provider_metadata.redirect_url;
              complete(record, 201, CheckoutRead with redirect_url) → return 201
     ProviderError/timeout: payment failed + failed_at; audit payment.failed;
              complete(record, 502 problem with order_id/order_number) → return 502 (Q14)
     any other exception: propagates (500); the claim stays in_progress (crash path)
```

- **Only 201 and the post-commit 502 become `done`.** Any 4xx/503 rolls back Tx1, the
  claim included, so a corrected retry with the same key runs fresh.
- An ownership violation rolls back Tx1 → `409 PRODUCT_ALREADY_OWNED`, cart intact
  (§3.2).
- A concurrent same-key request, or one arriving between Tx1's COMMIT and Tx2, gets `409
  IDEMPOTENCY_REQUEST_IN_PROGRESS` with the order id (`Retry-After: 2`). Once Tx2
  completes, retries replay the final 201 or 502.

### 3.9 Startup refusal (resolves Q5)

`configured_payment_providers(settings)` is called at boot, beside the existing fail-fast
checks:
- API: `src/app/main.py:28`, after `captcha_verifier(settings)` (ADR-026 pattern);
- worker: `src/app/worker.py:39`, after `get_email_provider(settings)`.

`Settings` gets no `model_validator`, because that would break Alembic, scripts and every
test that builds `Settings`. New `Settings` field: `mock_webhook_secret: str =
"mock-webhook-dev-secret"`. `.env.example` documents `PAYMENT_PROVIDER` (and `none`,
Q5) and `MOCK_WEBHOOK_SECRET`.

| `ENVIRONMENT` | `PAYMENT_PROVIDER` | API lifespan / worker `on_startup` | Checkout | Webhook paths |
|---|---|---|---|---|
| production | `mock` | **both raise `PaymentConfigurationError`** | — | — |
| production | `none` | both boot | `503 ONLINE_PAYMENT_UNAVAILABLE` | all 404 |
| staging | `mock` + default secret | both raise | — | — |
| staging | `mock` + own secret | both boot | normal | `/mock` only |
| development / test | `mock` | both boot | normal | `/mock` only |
| any | `cash` or unknown | both raise | — | — |

---

## 4. Database (one migration, `down_revision = "26d5d039d72c"`)

File: `migrations/versions/03a4730dd046_orders_payments_webhooks_idempotency.py`. Additive only:
new types, tables, constraints and indexes. Nothing existing is altered. It follows the
`bde6135b2538` (VS-022) style: `_PRODUCT_TYPE = postgresql.ENUM(..., create_type=False)`, a
`_timestamps()` helper, explicit constraint names, and a downgrade that drops tables then
enums with `checkfirst=True`.

### 4.1 Enums (new)

`fulfillment_method(delivery, pickup)`, `payment_method(online, cash)`,
`cancel_reason(refused, no_show, other)`, `order_source(cart, offer)`,
`order_status(pending_payment, cancelled, refunded, partially_refunded, completed,
in_progress)`, `order_item_status(pending, awaiting_delivery, in_production,
ready_to_ship, shipped, delivered, returned, ready_for_pickup, picked_up, cancelled,
refunded)`, `payment_status(pending, processing, paid, partially_refunded, refunded,
failed, expired)`, `payment_provider(mock, cash)`. `product_type` is reused.

### 4.2 `orders` (database-design §8.3, every column)

`id` UUID PK `gen_random_uuid()`; `order_number` TEXT; `user_id` UUID FK users
`RESTRICT`; `customer_email_snapshot` CITEXT NOT NULL; `source` order_source;
`status` order_status; `fulfillment_method` NULL; `payment_method` NOT NULL;
`subtotal_cents`, `tax_cents` (default 0), `total_cents` BIGINT; `currency` CHAR(3)
default `USD`; `recipient_name`, `contact_phone_snapshot`, `contact_phone_hash`,
`governorate`, `city`, `area`, `street`, `landmark_notes`, `customer_note`, `admin_note`
TEXT NULL; `estimated_dispatch_at` NULL; `terms_accepted_at` NOT NULL;
`digital_terms_accepted_at`, `cash_terms_accepted_at` NULL; **`digital_terms_version`
TEXT NULL** *(plan addition, Revision 2 / Q18)*; `placed_at` NOT NULL;
`completed_at`, `cancelled_at` NULL; `created_at`, `updated_at`.

| Name | Definition |
|---|---|
| `uq_orders_order_number` | UNIQUE(order_number) |
| `uq_orders_id_payment_method` | UNIQUE(id, payment_method), the composite-FK target |
| `ck_orders_money_non_negative` | subtotal ≥ 0 AND total ≥ 0 |
| `ck_orders_tax_zero` | tax_cents = 0 (V1) |
| `ck_orders_total_arithmetic` | total = subtotal + tax |
| `ck_orders_currency_usd` | currency = 'USD' |
| `ck_orders_physical_has_phone` | fulfillment_method IS NULL OR contact_phone_snapshot IS NOT NULL |
| `ck_orders_digital_only_online` | fulfillment_method IS NOT NULL OR payment_method = 'online' |
| `ck_orders_cash_terms` | payment_method <> 'cash' OR cash_terms_accepted_at IS NOT NULL |
| `ck_orders_delivery_address` | fulfillment_method IS DISTINCT FROM 'delivery' OR (recipient_name, governorate, city, landmark_notes all NOT NULL), matching `addresses`' NOT NULL columns (`2e89860f5274…:41-47`) |
| `ck_orders_phone_hash_pair` | (contact_phone_snapshot IS NULL) = (contact_phone_hash IS NULL) |
| `ck_orders_digital_terms_version` *(plan addition, Q18)* | (digital_terms_accepted_at IS NULL) = (digital_terms_version IS NULL) |
| `ix_orders_user_placed` | (user_id, placed_at DESC) |
| `ix_orders_status_placed` | (status, placed_at DESC) |

### 4.3 `order_items` (database-design §8.4, every column)

`id`; `order_id` UUID NOT NULL; `user_id` UUID FK users `RESTRICT`; `product_id`,
`product_type`; `offer_id` UUID NULL (**no FK**: VS-039 adds `fk_order_items_offer`
`NOT VALID` + `VALIDATE`, additive); `product_name_snapshot` TEXT; `image_snapshot` TEXT
NULL; `unit_price_cents`, `line_total_cents` BIGINT; `quantity` INT; `currency`;
`fulfillment_status`; `lead_time_days_snapshot`, `batch_size_snapshot` INT NULL;
`cancelled_at`, `fulfilled_at` NULL; `delivered_by` UUID FK users `RESTRICT` NULL;
`payment_method` NOT NULL; `cancel_reason` NULL; `receipt_confirmed_at`,
`problem_reported_at` NULL; timestamps.

| Name | Definition |
|---|---|
| `fk_order_items_order_payment_method` | (order_id, payment_method) → orders(id, payment_method) `ON UPDATE RESTRICT ON DELETE RESTRICT` (INV-21) |
| `fk_order_items_product_type` | (product_id, product_type) → products(id, type) `ON UPDATE RESTRICT`, proving the snapshot type, as `cart_items` does (ADR-029 d2) |
| `ck_order_items_money` | unit ≥ 0, line_total ≥ 0, quantity > 0, line_total = unit × quantity, currency = 'USD' |
| `ck_order_items_stl_quantity_one` | product_type <> 'stl' OR quantity = 1 |
| `ck_order_items_cash_is_physical` | payment_method <> 'cash' OR product_type = 'physical' |
| `ck_order_items_cancel_reason_state` | cancel_reason IS NULL OR fulfillment_status = 'cancelled' |
| `ck_order_items_snapshots_by_type` | physical → lead_time NOT NULL AND batch_size > 0; stl → both NULL |
| `ck_order_items_stl_delivery_record` | NOT (product_type='stl' AND fulfillment_status='delivered') OR (fulfilled_at, delivered_by NOT NULL) |
| `ck_order_items_physical_no_delivered_by` | product_type <> 'physical' OR delivered_by IS NULL |
| `ck_order_items_status_by_type` *(new guard; doc update)* | stl → status IN (pending, awaiting_delivery, delivered, refunded, cancelled); physical → status <> 'awaiting_delivery' |
| `uq_order_items_stl_ownership` | UNIQUE(user_id, product_id) WHERE product_type='stl' AND fulfillment_status IN ('pending','awaiting_delivery','delivered') (INV-18, ADR-019 d5) |
| `ix_order_items_order_id` | (order_id) |
| `ix_order_items_physical_status` | (fulfillment_status, order_id) WHERE product_type='physical' |

The STL delivery-queue index is **VS-023b's**. `receipt_confirmed_at` /
`problem_reported_at` get no CHECK now: whether they are physical-only is open (ADR-024
appendix, VS-029b).

### 4.4 `order_status_history` (§8.5)

`id`; `order_id` FK orders `RESTRICT`; `order_item_id` FK order_items `RESTRICT` NULL;
`from_status` TEXT NULL; `to_status` TEXT NOT NULL; `actor_user_id` FK users NULL;
`reason` TEXT NULL; `created_at`. `actor_user_id` is **ON DELETE SET NULL** (Revision 3).
Index `ix_order_status_history_order` (order_id,
created_at).

### 4.5 `payments` (§9.1, every column) — resolves Q3

`id`; `order_id` NOT NULL; `provider` payment_provider; `order_payment_method`;
`provider_payment_id` TEXT NULL; `status`; `amount_cents` BIGINT; `currency`;
`initiated_at` NOT NULL; `verified_at`, `late_captured_at`, `failed_at`, `expired_at`
NULL; `provider_metadata` JSONB NULL; `recorded_by` FK users NULL; timestamps.

| Name | Definition | Source |
|---|---|---|
| `fk_payments_order_payment_method` | (order_id, order_payment_method) → orders(id, payment_method) | INV-21 |
| `ck_payments_amount_currency` | amount ≥ 0, currency = 'USD' | §9.1 |
| `ck_payments_cash_iff_cash_order` | (provider = 'cash') = (order_payment_method = 'cash') | INV-21 |
| `ck_payments_cash_shape` | provider <> 'cash' OR (status IN ('paid','partially_refunded','refunded') AND recorded_by IS NOT NULL AND **verified_at IS NOT NULL** AND amount_cents > 0) | `database-design.md:1256` (**appendix item: verified_at**) |
| `ck_payments_late_capture` | late_captured_at IS NULL OR (status IN ('failed','expired') AND provider <> 'cash') | `:1257` (**appendix item**) |
| `ck_payments_online_not_recorded` | provider = 'cash' OR recorded_by IS NULL | `:1258` (**appendix item**) |
| `ck_payments_paid_verified` *(new guard)* | status NOT IN ('paid','partially_refunded','refunded') OR verified_at IS NOT NULL ("paid only through verification" in the database) | Done-when |
| `ck_payments_terminal_timestamps` *(new guard)* | status <> 'failed' OR failed_at IS NOT NULL; status <> 'expired' OR expired_at IS NOT NULL | — |
| `uq_payments_one_live` | UNIQUE(order_id) WHERE status NOT IN ('failed','expired') | §9.4 |
| `uq_payments_one_cash` | UNIQUE(order_id) WHERE provider = 'cash'; **created before `uq_payments_one_live`** so a second cash payment reports this name (PostgreSQL checks unique indexes in creation order; a cash payment is always live, so otherwise one-live always fired first) | INV-22 |
| `uq_payments_provider_reference` | UNIQUE(provider, provider_payment_id) (NULLs distinct) | Q13 (ADR-024 appendix, VS-032 item, brought forward) |
| `ix_payments_order` | (order_id) | lookups |
| `ix_payments_unsettled` | (status, initiated_at) WHERE status IN ('pending','processing') | §19.8 widened to cover VS-024's "pending or processing" (`vertical-slice-plan.md:610`); doc update |
| `ix_payments_late_captured` *(new)* | (late_captured_at) WHERE late_captured_at IS NOT NULL | the late-capture listing until VS-030 and its backfill (Revision 1 item 8); doc update |

### 4.6 `webhook_events` (§9.2 + link) — resolves Q2

`id`; `provider` payment_provider; `provider_event_id` TEXT; `event_type` TEXT NULL;
`payload` JSONB NOT NULL; `signature_valid` BOOLEAN NULL; **`provider_payment_id` TEXT
NULL**; **`payment_id` UUID FK payments `RESTRICT` NULL**; `received_at`;
`processed_at` NULL; `processing_error` TEXT NULL.

| Name | Definition |
|---|---|
| `uq_webhook_events_provider_event` | UNIQUE(provider, provider_event_id) |
| `ck_webhook_events_payload_size` | octet_length(payload::text) ≤ 65536 |
| `ix_webhook_events_unprocessed` | (received_at) WHERE processed_at IS NULL, for the `verify_payments` sweep |
| `ix_webhook_events_payment_unprocessed` | (payment_id) WHERE processed_at IS NULL, so VS-024's hold release asks "unprocessed event for this payment?" in one index probe (ADR-024 appendix `:94`) |

Rule (also VS-024 item 1's sub-point): an event that is ignored (unknown payment,
provider mismatch) or definitively verified gets `processed_at`. Only a provider outage
leaves it unprocessed (`processing_error` set) for the next run.

### 4.7 `idempotency_records` (§13.4)

Columns: `id`; `user_id` FK users `ON DELETE CASCADE` NULL (database-design.md:1912);
`scope` TEXT; `key` TEXT; `request_hash` CHAR(64); **`state` TEXT NOT NULL**
*(plan addition)*; **`resource_id` UUID NULL** *(plan addition: the order id, no FK,
because the record is scope-generic)*; `status_code` INT NULL; `response_body` JSONB
NULL; `expires_at`; `created_at`.

Constraints and indexes:
- `uq_idempotency_records_scope_user_key`: `UNIQUE NULLS NOT DISTINCT (scope, user_id,
  key)`, via `postgresql_nulls_not_distinct=True`, or `op.execute` if the pinned
  SQLAlchemy lacks it.
- `ck_idempotency_records_key_length` (1–255).
- `ck_idempotency_records_state`: state IN ('in_progress','done').
- `ck_idempotency_records_done_has_response`: (state = 'done') = (status_code IS NOT
  NULL AND response_body IS NOT NULL).
- `ck_idempotency_records_status_code` (100–599).
- `ix_idempotency_records_expires_at`.

`state` is TEXT with a CHECK rather than a new enum, so VS-030 can reuse the table with
no enum migration. database-design §13.4 (`:1803-1846`) gains both columns in PR A.

### 4.8 Models and registration

- `app/ordering/infrastructure/models.py` (+3 models).
- `app/payments/infrastructure/models.py` (new, 2 models).
- `app/platform/infrastructure/models.py` (+1).
- `app/core/models.py` imports the payments models (`src/app/core/models.py:7-11`).

### 4.9 Reversibility and compatibility

- `downgrade()` drops the six tables in reverse dependency order, then the eight enums
  (`checkfirst=True`), then nothing else (no existing object is touched).
- `tests/integration/test_migration_reversibility.py:23` gains the new revision, and the
  "one head" check stays.
- Backward compatible: running code before this slice never reads these tables.

### 4.10 What VS-023 builds ahead of VS-023b, VS-028 and VS-029: citation and database test

Every column or constraint below exists only so a later slice needs no destructive
change (Revision 1 item 12). "DD" means `docs/requirments/database-design.md`. Each
CHECK for behaviour VS-023 does not build is tested at the database level in
`tests/integration/ordering/test_order_payment_schema.py` with direct SQL: one
**refused** row (SQLSTATE 23514 / 23503 / 23505 and the constraint name asserted) and
one **accepted** row, so no constraint is too tight for its future slice.

**Columns** (all nullable or defaulted; no CHECK beyond those listed below):

| Column | For | DD line |
|---|---|---|
| `orders.fulfillment_method` | VS-028 | `:968` |
| `orders.payment_method` (cash value) | VS-028/029 | `:969` |
| `orders.recipient_name`, `governorate`, `city`, `area`, `street`, `landmark_notes` | VS-028 | `:974`, `:977-981` |
| `orders.contact_phone_snapshot`, `contact_phone_hash` | VS-028 | `:975-976` |
| `orders.admin_note` | VS-029 | `:983` |
| `orders.estimated_dispatch_at` | VS-028 | `:984` |
| `orders.cash_terms_accepted_at` | VS-028 | `:988` |
| `orders.digital_terms_version` | VS-023 (PR B writes it) | *plan addition* (Q18), beside `:986` |
| `orders.completed_at` | VS-023b/029 | `:990` |
| `orders.cancelled_at` | VS-024 | `:991` |
| `order_items.offer_id` (no FK yet) | VS-041 | `:1067` |
| `order_items.lead_time_days_snapshot`, `batch_size_snapshot` | VS-028 | `:1076-1077` |
| `order_items.cancelled_at` | VS-024/029 | `:1078` |
| `order_items.fulfilled_at`, `delivered_by` | **VS-023b** | `:1079-1080` |
| `order_items.payment_method` | VS-028 | `:1081` |
| `order_items.cancel_reason` | VS-029 | `:1082` |
| `order_items.receipt_confirmed_at`, `problem_reported_at` | VS-029b | `:1083-1084` |
| `payments.order_payment_method` | VS-028/029 | `:1225` |
| `payments.late_captured_at` | VS-024/030 (VS-023 also writes it) | `:1232` |
| `payments.recorded_by` | VS-029 | `:1236` |

**CHECKs, keys and indexes for unbuilt behaviour, with their database tests:**

| Constraint | For | DD line | Refused row in the test | Accepted row in the test |
|---|---|---|---|---|
| `uq_orders_id_payment_method` + `fk_order_items_order_payment_method` + `fk_payments_order_payment_method` | VS-028/029 | `:1022`, `:1081`, `:1225` | line with `payment_method='cash'` on an online order (23503); payment with `order_payment_method='cash'` on an online order (23503) | matching values |
| `ck_orders_physical_has_phone` | VS-028 | `:1019` | `fulfillment_method='pickup'`, phone NULL | pickup + phone + hash |
| `ck_orders_digital_only_online` | VS-028 | `:1020` | `fulfillment_method NULL`, `payment_method='cash'` | NULL + online |
| `ck_orders_cash_terms` | VS-028 | `:1021` | cash order, `cash_terms_accepted_at NULL` | cash + terms |
| `ck_orders_delivery_address` | VS-028 | `:1005` (fields from `addresses` NOT NULLs, `2e89860f5274…:41-47`) | delivery with `city NULL` | delivery with recipient, governorate, city, landmark, phone |
| `ck_orders_phone_hash_pair` | VS-028 | `:976` "set with `contact_phone_snapshot`" | phone without hash | both set |
| `ck_orders_digital_terms_version` | VS-023 PR B | *plan addition* (Q18) | version without `digital_terms_accepted_at`; timestamp without version | both set; both NULL |
| `ck_order_items_cash_is_physical` | VS-028 | `:1120` | STL line on a cash order (**plan test bullet**) | physical line on a cash order |
| `ck_order_items_cancel_reason_state` | VS-029 | `:1121` | `cancel_reason='refused'` on a `pending` line | on a `cancelled` line |
| `ck_order_items_snapshots_by_type` | VS-028 | `:1127-1128`, `:1134-1135` | physical line without lead time; physical `batch_size=0`; STL with a batch size | physical with both; STL with neither |
| `ck_order_items_stl_delivery_record` | **VS-023b** | `:1105` | STL `delivered` without `delivered_by` | STL `delivered` with `fulfilled_at` + `delivered_by` |
| `ck_order_items_physical_no_delivered_by` | **VS-023b**/029 | `:1106` | physical line with `delivered_by` | physical `delivered` without it |
| `ck_order_items_status_by_type` | VS-023b/029 | *plan addition* (DD §3.7 `:209-225` transition sets) | physical `awaiting_delivery`; STL `shipped` | STL `awaiting_delivery`; physical `in_production` |
| `ix_order_items_physical_status` | VS-029 | `:1156` | — (index; existence asserted) | — |
| `ck_payments_cash_iff_cash_order` | VS-029 | `:1255` | cash payment on an online order; online payment on a cash order (**plan test bullets**) | cash payment on a cash order (paid, verified, recorded, > 0) |
| `uq_payments_one_cash` | VS-029 | `:1254` | second cash payment on one order (**plan test bullet**), 23505 | first one |
| `ck_payments_cash_shape` | VS-029 | `:1256` | cash `pending`; cash without `recorded_by`; cash without `verified_at` (**appendix**); cash amount 0 | full cash row |
| `ck_payments_late_capture` | VS-024/030 | `:1257` | `late_captured_at` on a `paid` row; on a cash row (**appendix**) | on a `failed` online row |
| `ck_payments_online_not_recorded` | VS-029 | `:1258` | online payment with `recorded_by` (**appendix**) | online without |
| `ck_payments_paid_verified`, `ck_payments_terminal_timestamps` | all | *plan additions* | `paid` without `verified_at`; `failed` without `failed_at` | with them |

The only database objects VS-023 deliberately does **not** build for later slices:
- the STL queue index (VS-023b, DD `:1157`);
- `order_items.offer_id`'s FK (VS-039, DD `:1067`);
- the open-cash index `(contact_phone_hash) WHERE payment_method='cash'` (VS-028, DD
  `:1053`, "if `EXPLAIN` shows the need").

---

## 5. Performance and abuse

- **Checkout cost:** about 14 statements in Tx1 (claim, setting, cart lock, lines,
  product batch, owned query, order, lines as one executemany, payment, history, audit,
  clear, touch, store response), plus Tx2's two updates. Cart ≤ 50 lines (ADR-029 d5)
  bounds every loop and the product batch. The budget is NFR-03 "< 2 s excluding
  redirect" (`non-functional-requirements.md:10`). The integration suite asserts a
  statement-count ceiling on the happy path so an N+1 fails a test.
- **Provider call** outside any transaction or lock, with a 10 s timeout. A slow provider
  never holds the cart lock.
- **Lock hold time:** the cart lock is held only for Tx1 (no network inside).
- **Indexes:** every hot path has one (§4). The ownership probe uses
  `uq_order_items_stl_ownership`. The hold-release probe uses
  `ix_webhook_events_payment_unprocessed`.
- **Abuse:**
  - checkout 30/h/user, fail closed;
  - webhook: signature first, then 600/min per provider for signed traffic and 30/min per IP for invalid or unsigned traffic, body ≤ 64 KiB, unconfigured provider 404 before
    any read or write, bad signature never stored;
  - `accepted_price_changes` ≤ 50, `customer_note` ≤ 1000;
  - `Idempotency-Key` charset and length bounded;
  - idempotency keys scoped per user (no cross-user replay);
  - `/me/stl-ownership` reveals nothing for hidden or unknown products (ADR-025).
- **Retention:** idempotency rows live 24 h and are then purged daily. `webhook_events`
  retention is undecided in the spec, so nothing is purged now (R8).

---

## 6. Tests (per category; `tests/<category>/…`)

### 6.1 Unit (`tests/unit/ordering`, `tests/unit/payments`, `tests/unit/platform`)

- `test_order_status.py`: table-driven, **every branch** of `derive_order_status`:
  - online unpaid (no cancel / cancelled_at);
  - cash unpaid (all cancelled / some live);
  - paid with each SRS rule in order: all cancelled, refunds cover all paid money, all
    lines refunded, refund present, all terminal (each terminal state incl.
    `picked_up`), in progress;
  - **pinned SRS results for the PR #8 cases:** case A (one line `refunded`, refund
    failed and owed, coverage false) → `refunded`; case B (all cancelled, owed refund)
    → `cancelled`. Each test names the VS-030 note, so a later reorder changes it
    deliberately;
  - a property test (hypothesis, as `test_deep_properties.py`) that the output is always
    one of the six values and that `pending_payment` occurs only when online and not
    paid.
- `test_checkout_rules.py`:
  - refusals collected for every line (mixed reasons, caps only → `only_caps`);
  - physical line / any fulfillment field → invalid;
  - owned split (some, all);
  - price change detection (up, down, accepted exact, accepted stale amount, accepted
    wrong currency, change on a dropped line ignored);
  - totals use live prices, never the snapshot;
  - consent required with STL;
  - order number shape and alphabet.
- `test_cart_services.py` (extend): add of an owned STL → `ProductAlreadyOwnedError`;
  own `pending` line does not block; physical never queried.
- `tests/unit/payments/test_outcome.py`: every row of the §3.6 decision table, plus
  currency mismatch, overpayment, captured `None`.
- `test_provider_factory.py`:
  - unknown name, `cash`, mock in production → error;
  - mock in development/test → ok; mock in staging with the default secret → error,
    with its own secret → ok;
  - `none` → empty (Q5);
  - a stub registered in `ADAPTERS` passes in production.
- `tests/unit/platform/test_request_hash.py`: key order and whitespace insensitive;
  different scope → different hash.
- `test_deep_architecture.py` (extend):
  - the new no-cycle rule (§3.0);
  - `payments` and `ordering` appear in the published-surface assertion;
  - `app.fulfillment` stays empty.

### 6.2 Integration (`tests/integration/ordering`, `…/payments`, `…/platform`; real Postgres)

**Checkout API (`test_checkout_api.py`):**
- happy path: 201, order `pending_payment`, one `pending` STL line with live-price
  snapshot, pending payment = total, cart empty, one history row, one audit row,
  `customer_email_snapshot`, terms timestamps, `redirect_url` set;
- statement-count ceiling;
- same key + same body after completion → identical 201 + `Idempotent-Replayed`, still
  one order;
- **crash simulation, before the provider call** (`test_checkout_crash_window.py`):
  - patch `start_online_payment` to raise a non-provider `RuntimeError` before calling
    the spy provider; the request fails (500);
  - assert: one order, one `pending` payment with no reference, the claim
    `in_progress` with `resource_id` = that order, provider `create_payment` calls = 0;
  - retry with the same key and body → `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` with that
    `order_id`; still one order, still 0 provider calls, claim unchanged;
- **crash simulation, after the provider call:**
  - patch Tx2's `complete` to raise after the spy provider returned;
  - assert provider calls = 1, payment has no stored reference, claim `in_progress`;
  - retry → 409 in progress; provider calls still **1**, orders still 1;
  - `verify_payment(payment_id)` (the VS-024 entrypoint) then finds the mock payment by
    merchant reference;
- a 4xx after the claim (e.g. `CART_PRICE_CHANGED`) leaves **no** claim row; the same
  key with an accepted change then succeeds;
- `PAYMENT_PROVIDER=none` → `503 ONLINE_PAYMENT_UNAVAILABLE`, no order, no claim, cart
  intact;
- **ownership violation is a domain 409, not a 500:**
  - seed the customer's own unpaid order holding STL X (line `pending`), put X back in
    the cart, check out → `409 PRODUCT_ALREADY_OWNED` naming X, problem body (not 500),
    no new order, cart intact, no claim row;
  - the same STL held by **another** customer's pending order does not block (the index
    is per user) → 201;
  - an unrelated `IntegrityError` injected in `insert_lines` still surfaces as 500 (only
    the named index maps);
- **forced order-number collision:**
  - pre-insert an order numbered `B3D-AAAAAAAA`; patch the generator to yield it, then
    `B3D-BBBBBBBB` → 201 with `B3D-BBBBBBBB`, one new order, the same transaction still
    holding the cart lock (cart cleared, claim done);
  - patch it to collide 5 times → 500, nothing written, cart intact, no claim;
- same key + different body → 409 `IDEMPOTENCY_KEY_CONFLICT`;
- same key from another user → independent order;
- missing / malformed key → 422;
- kill switch off → 503, nothing written, cart intact, **no idempotency row**;
- a replay of an earlier success while the kill switch is off → 201 replay;
- no cart / empty cart → 409 `CART_EMPTY`;
- owned STL in cart (bought since) → dropped, named in `dropped_lines`, order has the
  rest;
- all lines owned → 409 `CART_EMPTY` with `dropped_lines`;
- price raised → 409 with `price_changes`; retry with exact acceptance → 201 at the
  **new** price; acceptance then a second change → 409 again;
- not-listed / unavailable / whatsapp-only line → 422 naming each, cart intact;
- over-cap only → 422 `QUANTITY_EXCEEDS_LIMIT`;
- physical line → 422 `INVALID_FULFILLMENT`; `fulfillment_method` given on STL-only
  → 422;
- `cash` → 422 `PAYMENT_METHOD_NOT_ALLOWED`; unconfigured `payment_provider` → 422;
  $0 total → 422 (Q8);
- missing `accept_digital_final_sale` → 422;
- client sends `total_cents` → 422 (extra forbidden);
- **a failure leaves the cart intact** (each 4xx above asserts cart rows unchanged);
- provider create fails → 502 with `order_id`, payment `failed`, order
  `pending_payment`, cart cleared, replay returns the same 502 (Q14);
- unverified → 403; no CSRF → 403; anonymous → 401; 31st checkout in an hour → 429.

**Cart (`test_cart_api.py`, extend):**
- owned STL add → 409 `PRODUCT_ALREADY_OWNED`;
- STL held only by own unpaid order → add allowed, checkout → 409
  `PRODUCT_ALREADY_OWNED` (ownership index), cart intact.

**Ownership endpoint (`test_stl_ownership_api.py`):**
- false before payment, false for another customer's purchase, true at
  `awaiting_delivery` and `delivered` (seeded), false for unknown / hidden / physical id;
- 401 anonymous; 422 missing / malformed `product_id`;
- unverified user allowed.

**Webhook (`test_webhook_api.py`):**
- valid mock event → 200, one row with `payment_id` resolved, and the background task
  verifies it before the test's next await (no cron run needed);
- **rate-limit isolation:**
  - 31 bad-signature posts from IP A → the 31st is 429 on `webhook-unverified:A`; none
    stored;
  - a correctly signed event from IP A and from IP B → 200 and stored (the
    `webhook:mock` bucket is untouched by the bad traffic);
  - 601 signed events in a window → the 601st is 429;
  - an unconfigured-provider post touches no bucket (Redis key absent);
- duplicate → 200, still one row;
- bad signature → 401, no row;
- `/payments/cash` → 404 no row; `/payments/unknown` → 404 no row;
- `/payments/mock` with `ENVIRONMENT=production` and a test-only stub configured → 404
  no row;
- oversize body → 400;
- unknown payment reference → stored, processed with error, alert logged;
- provider mismatch → stored, processed, nothing changed, alert.

**Verification (`test_verify_payments_job.py`):**
- paid → payment `paid` + `verified_at`, STL line `awaiting_delivery`, order
  `in_progress`, 2 line/order history rows, audit, one outbox row
  (`order_payment_confirmed`, to the snapshot email), one `payment` notification;
- **forged callback** (mock says pending) → nothing changes, event processed;
- **underpayment** and overpayment → attempt `failed` + `late_captured_at`, lines
  untouched, error log `payment_late_capture`, one audit row `payment.late_capture` with
  the reason;
- the row is returned by `GET /admin/audit-logs?action=payment.late_capture` and by the
  §3.6 SQL;
- failed → `failed`, order `pending_payment` (BR-058);
- expired → `expired`, order `pending_payment`;
- processing → `processing`;
- provider timeout → event unprocessed with `processing_error`, next run applies;
- **duplicate webhook applies once** (two events, one payment: one audit / outbox /
  notification);
- success for an `expired` attempt → late capture, lines untouched;
- **kill switch off does not block** an in-flight payment's verification;
- `verify_payment(payment_id)` without an event works (VS-024 entrypoint).

**Startup (`test_payment_startup.py`)**, every row of the §3.9 table, each through
**both** entrypoints:
- `app.main.lifespan` (entered with `LifespanManager` or the `make_app` fixture);
- `app.worker.on_startup(ctx)` with a dict ctx.

Production + `mock` raises in both; production + `none` boots in both; staging + mock +
default secret raises in both; development + mock boots in both; `cash` raises.

**DB constraints (`test_order_payment_schema.py`):**
- each CHECK and index in §4 refused or accepted by direct SQL, including **an STL line
  on a cash order, a cash payment on an online order, an online payment on a cash order,
  a second cash payment** (plan bullets);
- the three appendix CHECKs (`cash` without `verified_at`, `late_captured_at` on a
  `paid` row or on cash, `recorded_by` on an online payment);
- `paid` without `verified_at`;
- two live payments;
- duplicate `(provider, provider_payment_id)`;
- a second live STL line per user/product while a `cancelled` one may coexist;
- `UNIQUE NULLS NOT DISTINCT` with `user_id NULL`;
- composite FKs refuse a mismatched `payment_method`.

**Migrations:** `test_migration_reversibility.py`: upgrade → downgrade -1 → upgrade;
one head; the new revision follows `26d5d039d72c`.

**Idempotency purge (`test_purge_idempotency_job.py`):** expired rows deleted, live
kept, batches capped, `SKIP LOCKED` against a held row.

### 6.3 Concurrency (`tests/concurrency/test_checkout_races.py`, `test_payment_races.py`; `meet_or_fail`)

1. **Parallel double checkout**, same user, two keys: exactly one order; the other gets
   409 `CART_EMPTY` (the cart lock serialises; the second sees the cleared cart).
2. Same key, identical body, parallel: exactly one order and at most one provider call.
   The second waits on the unique index, then gets `409
   IDEMPOTENCY_REQUEST_IN_PROGRESS` (if Tx2 has not completed) or the replayed 201.
   **CHANGED** from "both 201".
3. Same key, different bodies, parallel: one 201, one 409 `IDEMPOTENCY_KEY_CONFLICT`.
4. **Two parallel checkouts of one STL by one customer → one order, one 409
   `PRODUCT_ALREADY_OWNED`.** One user has one cart, so a second checkout cannot hold the
   same STL in a cart concurrently. The race is checkout vs a second writer of a
   `pending` line for the same (user, product) that does not take the cart lock: a
   direct SQL insert that stands in for VS-041's offer checkout. Both pass the barrier;
   the ownership index lets exactly one commit (Q16).
5. Duplicate webhook delivered in parallel: one row, both 200.
6. Two `verify_event` runs on the same paid payment in parallel: `paid` once, one
   audit / outbox / notification, no deadlock.
7. Verification of order A racing checkout of a new order by the same user: no deadlock
   (lock-order proof, §8.1).

### 6.4 Contract (`tests/contract/payments/test_provider_contract.py`)

A parametrised suite over `ADAPTERS` (mock now; VS-032 adds its sandbox):
- create;
- query paid / underpaid / overpaid / failed / expired / processing;
- timeout raises `ProviderUnavailableError`;
- bad signature raises;
- duplicate event id parses identically;
- late success after expiry;
- query by merchant reference without `provider_payment_id`.

### 6.5 Security (`tests/security/test_checkout_security.py`)

- price tampering (`unit_price`, `total` in body);
- cash for an STL order;
- webhook to unconfigured / `cash` / production `mock`;
- mismatched provider;
- forged callback;
- idempotency key reuse across users;
- ownership endpoint for another user's product;
- `admin_note` / provider references never in `CheckoutRead`;
- the webhook body is never logged raw (redaction filter).

### 6.6 Smoke and e2e

- `tests/smoke/test_vs023_smoke.py` (`-m smoke`): checkout 201, webhook 200, job applies,
  ownership true.
- `tests/e2e/test_vs023_digital_purchase.py`: register → verify email (outbox token) →
  add STL → checkout → mock `simulate(paid)` + signed webhook → `verify_payments` →
  line `awaiting_delivery`, ownership `true`, email and notification present. This is
  the plan's full end-to-end bullet.

### 6.7 Running the suite (sequential chunks, never all at once)

1. `pytest tests/unit`
2. `pytest tests/integration/ordering tests/integration/payments tests/integration/platform`
3. `pytest tests/integration --ignore=tests/integration/ordering --ignore=tests/integration/payments --ignore=tests/integration/platform`
4. `pytest tests/concurrency`
5. `pytest tests/contract tests/security tests/smoke tests/e2e`

Plus `ruff check .`, `ruff format --check .`, `mypy src tests`. Integration needs Docker
(testcontainers). Inside compose, `DATABASE_URL` / `REDIS_URL` must use the in-network
hosts (`postgres`, `redis`) for `api` **and** `worker`, because the mock adapter's Redis
state must be the same instance for both (R9).

---

## 7. Docs and ADRs

- **ADR-032 "Checkout, idempotency and payment verification"** (next free number,
  verified on origin). It records:
  - package ownership (Q1);
  - the two-transaction checkout with provider-after-commit and which responses are
    stored (Q6, Q14);
  - `webhook_events.payment_id` + "ignored events are processed" (Q2);
  - idempotency claim states and the crash window (Q7);
  - background verification after the 200, with the cron as fallback (Q12);
  - webhook rate-limit buckets (Q17);
  - the order-number format and savepoint retry (Q11);
  - `PAYMENT_PROVIDER=none` (Q5);
  - `UNIQUE(provider, provider_payment_id)` (Q13);
  - the startup refusal location (Q4).
  `docs/adr/README.md` index updated.
- **ADR-024 appendix:** mark both VS-023 items resolved, with links.
- **`docs/vertical-slice-plan.md`:**
  - VS-023 Status/table row (In progress → Done at the end);
  - consent wording "validated before writing, recorded on the order insert; cart
    cleared last" (Q3);
  - the full cash CHECK list (Q2/Q3);
  - the `webhook_events` link;
  - "As built";
  - VS-030 note: create obligations for pre-existing `late_captured_at` rows (query in
    §3.6);
  - VS-030 note: the `derive_order_status` reorder question, cases A and B (Revision 1
    item 1; needs an ADR and the co-developer's confirmation);
  - VS-024 note: `processed_at` semantics, and reconciling attempts with no provider
    reference.
- **SRS:** VS-023 does not change §20.2.
  - §23: add `verify_payments` (1 min, webhook-loss fallback only; `reconcile_payments`
    stays VS-024's) and `purge_expired_idempotency_records` (daily), as VS-046 did
    (owner, Checkpoint 4); `api-endpoints.md` §34 and database-design §21.3 and §23 name them too;
  - §7.3 note that consent timestamps live on the order row;
  - §9.2 "bad signature: rejected, not stored".
- **`docs/requirments/database-design.md`:**
  - §8.4 `ck_order_items_status_by_type`;
  - §9.1 new guards, `uq_payments_provider_reference`, widened `ix_payments_unsettled`;
  - §9.2 `provider_payment_id`, `payment_id`, indexes, processed rule;
  - §13.4 `state`, `resource_id`, TTL;
  - §9.1 `ix_payments_late_captured`;
  - §19.8.
  These schema edits land in **PR A** with the migration, so docs and schema never
  disagree on `main`.
- **`docs/requirments/api-endpoints.md`:**
  - checkout row (`dropped_lines`, 422 shapes, 502 code, `Idempotent-Replayed`, remove
    `PAYMENT_ALREADY_ACTIVE` from fresh checkout);
  - webhook row (404 cases, 401 bad signature);
  - `CheckoutRead`;
  - error catalogue `PAYMENT_PROVIDER_UNAVAILABLE`, `ONLINE_PAYMENT_UNAVAILABLE`,
    `IDEMPOTENCY_REQUEST_IN_PROGRESS`.
- **New `docs/checkout.md`** (like `docs/cart.md`): contract, error table, idempotency,
  mock flow.
- `docs/cart.md`: owned refusal now built.
- `docs/notification-contract.md`: `payment.confirmed` event.
- `docs/settings-registry.md`: no change (no new setting).
- `README.md` "Merged so far".
- `docs/frontend-handoff/openapi.json` regenerated + `BACKEND-RESPONSE.md` note.
- `.env.example`: `PAYMENT_PROVIDER`, `MOCK_WEBHOOK_SECRET`.
- Docstrings and comments ≤ 3 lines, matching VS-022's density.

---

## 8. Implementation steps, in order, with checkpoints

**PR A — migration only (small; take the migration lock, CONTRIBUTING.md "The Alembic
migration lock")**

1. Announce the lock to the VS-023b co-developer. Re-derive the head (`26d5d039d72c`
   expected).
2. Enums + models (`ordering`, `payments`, `platform`) + `core/models.py` import.
3. Hand-write the migration (§4); `alembic heads` = 1; upgrade → downgrade -1 →
   upgrade.
4. Schema, parity and reversibility tests; database-design edits.
5. Chunks 1–3 green → open PR A.

**PR A contains exactly these files** (Revision 1 item 11):

| File | Change |
|---|---|
| `migrations/versions/03a4730dd046_orders_payments_webhooks_idempotency.py` | new; `down_revision = "26d5d039d72c"` |
| `src/app/ordering/domain/enums.py` | new: pure `StrEnum`s the models use (no logic) |
| `src/app/payments/domain/enums.py` | new: `PaymentStatus`, `PaymentProvider` |
| `src/app/ordering/infrastructure/models.py` | + `OrderModel`, `OrderItemModel`, `OrderStatusHistoryModel` |
| `src/app/payments/infrastructure/models.py` | new: `PaymentModel`, `WebhookEventModel` |
| `src/app/platform/infrastructure/models.py` | + `IdempotencyRecordModel` |
| `src/app/core/models.py` | + one import line for the payments models |
| `tests/integration/ordering/test_order_payment_schema.py` | new: every §4.10 refused/accepted pair + VS-023's own constraints |
| `tests/integration/test_model_migration_parity.py` | new: after `upgrade head`, Alembic `compare_metadata(MigrationContext, Base.metadata)` restricted to the six new tables must be empty (columns, types, nullability, indexes, uniques, FKs) |
| `tests/integration/test_migration_reversibility.py` | + an orders block: the new revision is in the chain with `down_revision == "26d5d039d72c"`, the six tables and eight enums exist after upgrade and are gone after `downgrade` to its own parent (`26d5d039d72c`), then `upgrade head` again. VS-034's `BYI_REVISION` block is left untouched. The existing **`assert len(scripts.get_heads()) == 1`** (`:53`) stays and still pins no head revision, so VS-023b's next migration needs no edit here |
| `tests/integration/test_deep_db_constraints_and_migrations.py` | Revision 3: the purge test allowlists the four §14 RESTRICT pairs |
| `docs/adr/ADR-032-checkout-idempotency-and-payment-verification.md`, `docs/adr/README.md` | Revision 3: ADR-032 with the schema decisions; PR B adds the rest |
| `docs/requirments/database-design.md` | the §7 schema edits (plan additions: `webhook_events` link, idempotency `state`/`resource_id`, new guards and indexes) |

**`main` stays green with PR A alone:**
- No application code imports the new models except `core/models.py`, which registers
  them on `Base.metadata`. No route, job or service reads or writes the tables.
- `tests/unit/test_deep_architecture.py` still passes: domain enums import nothing,
  models live in infrastructure, and there are no cross-context imports.
- Parity and reversibility run in chunk 3. The OpenAPI snapshot
  (`tests/unit/test_openapi_snapshot.py`) is unchanged because no route is added.
- Merging PR A releases the migration lock. VS-023b's queue-index migration then chains
  on PR A's revision.

> **Checkpoint 1 — PR A ready for review.** Reports:
> - `alembic heads` output (one revision) and its `down_revision`;
> - upgrade → `downgrade -1` → upgrade, and the full `base` round trip, both green;
> - parity diff empty;
> - the count of constraint tests (refused / accepted) mapped to §4.10;
> - chunks 1–3 green, ruff, mypy.
>
> The owner merges and the lock is released.

**PR B — the slice (branch `vs-023-digital-checkout`, rebased on PR A)**

6. Ordering domain: enums, `order_status.py`, `checkout_rules.py`, `order_number.py`,
   exceptions + unit tests.
7. Payments domain: `outcome.py` + unit tests.
8. Platform idempotency port, adapter, request hash + unit/integration tests.

> **Checkpoint 2 — pure logic.** Reports:
> - the `derive_order_status` test table with every SRS branch and the pinned case A/B
>   results;
> - the `decide()` table with each row's test;
> - the idempotency claim transitions (`New` / `Replay` / `InProgress` / `Conflict`)
>   with their integration tests against Postgres;
> - the frozen `ordering.public` / `payments.public` signatures, sent to the VS-023b
>   co-developer for confirmation;
> - unit chunk green.

9. Ordering infrastructure (`SqlOrderStore`), ports, `place_order`, `add_item` owned
   check.
10. Payments infrastructure: `SqlPaymentAttempts`, `SqlPaymentStore`, mock adapter,
    factory; startup checks in `main.py` and `worker.py`.
11. Checkout route (two transactions) + ownership route + error mapping + integration
    tests.

> **Checkpoint 3 — checkout up to `pending`.** Reports:
> - the checkout, cart and ownership integration suites green, including both crash
>   simulations, the ownership-409 tests, the forced order-number collisions, the `none`
>   → 503 test and the statement-count figure;
> - races 1–4 green;
> - a sample `CheckoutRead` and each error body, for the owner to check against the
>   frontend contract.

12. Webhook route, `receive_webhook`, `verify_event`/`verify_payment`,
    `apply_provider_result`, `mark_order_paid`, outbox + notification.
13. Jobs (`verify_payments`, `purge_expired_idempotency_records`) + registry.
14. Webhook / verification / startup integration tests, races 5–7, contract suite,
    security tests.

> **Checkpoint 4 — verification path.** Reports:
> - forged, under/overpaid (late-capture audit row visible in the audit viewer),
>   duplicate, timeout and mismatch cases green;
> - the background verification measured against the mock (receipt → `paid` time);
> - the cron fallback applies after a dropped background task;
> - webhook rate-limit isolation green;
> - the startup matrix through both `main.py` and `worker.py` green;
> - races 5–7 green, including the lock-order race;
> - the contract suite green.

15. Smoke + e2e; `scripts/mock_pay.py`.
16. Docs and ADR-032 (§7); OpenAPI regeneration.
17. Full suite in the five chunks + ruff + mypy; open PR B.

> **Checkpoint 5 — PR B ready.** Reports:
> - the five suite chunks (pass counts), ruff, `ruff format --check`, `mypy src tests`;
> - the e2e and smoke runs;
> - the docs list from §7 ticked;
> - the OpenAPI diff summary;
> - any open owner question.
>
> The owner merges, then Status → Done.

### 8.1 Lock order per path, and why there is no cycle (resolves Q6)

| Path | Locks, in order | Never |
|---|---|---|
| **Checkout Tx1** | ① `idempotency_records` unique-key wait (new row) → ② `carts` FOR UPDATE → ③ catalog reads, no locks → ④ INSERT `orders` / `order_items` / `payments` / history (new rows; implicit FK `KEY SHARE` on `users`, `products`) → ⑤ DELETE `cart_items`, UPDATE `carts` (already held) → ⑥ UPDATE own `idempotency_records` row | locks any **existing** `orders`, `order_items`, `payments` or `webhook_events` row |
| **Checkout Tx2** | UPDATE the new `payments` row (no `orders` lock: only `provider_payment_id`/metadata or `pending → failed`, which no other path can touch before the provider reference exists, R6) → UPDATE `idempotency_records` | touches `carts` or `orders` |
| **Webhook request** | INSERT `webhook_events` (unique-key wait on duplicate); unlocked SELECT of `payments` to resolve the reference | locks anything existing |
| **Verification Tx A** | unlocked reads (`webhook_events`, `payments`) | locks |
| **Provider query** | no transaction | — |
| **Verification Tx B** (`apply_provider_result`) | ① `orders` FOR UPDATE → ② `order_items` FOR UPDATE ORDER BY id → ③ `payments` FOR UPDATE → ④ INSERTs (history, audit, outbox, notification) → ⑤ UPDATE `webhook_events` by id | touches `carts` or `idempotency_records`; locks `payments` before `orders` |
| **Idempotency purge** | DELETE `idempotency_records` … `FOR UPDATE SKIP LOCKED` batches | touches any other table |
| *(VS-024 release / retry, VS-023b mark delivered — future)* | `orders` → lines by id → `payments` (ADR-024 d9) | — |

**No cycle:**
- **Checkout vs verification.** The only tables both touch are `orders`, `order_items`
  and `payments`. Checkout only INSERTs rows invisible to every other transaction until
  it commits, so verification can never wait on a checkout row. Checkout never waits on
  a row verification holds: it locks no existing order, line or payment, and a
  unique-index wait on `uq_order_items_stl_ownership` can only be against another
  *inserting* transaction for the same user and product, never against Tx B.
- **Checkout vs checkout.** The idempotency wait (same user + key) happens before the
  cart lock in both, so it is ordered. Two keys of one user serialise on the cart lock.
- **Checkout vs webhook / purge.** They share no table except `idempotency_records`
  (purge), which uses `SKIP LOCKED` and never waits.
- **Verification vs verification.** Same order of acquisition (`orders` → lines →
  `payments` → `webhook_events`), so they serialise on `orders`.
- **Verification vs future ADR-024 paths.** Identical prefix `orders → lines →
  payments`. `webhook_events` is always last and only Payments touches it.
- **Cart lock vs `orders` lock** (VS-029/031 cancel-with-block): `orders → … → cart`.
  Checkout holds a cart and never waits on an existing `orders` row (ADR-029 d4).

Every path acquires along one global order: `idempotency_records → carts → (new-row
inserts) | orders → order_items(by id) → payments → webhook_events`. Rows inserted by an
uncommitted transaction are unreachable to others, so the wait-for graph is acyclic.
Race 7 and races 1–6 exercise it.

---

## 9. Risks

- **R1 — The `derive_order_status` rule order differs from SRS §20.2 text** (Q10). If not
  accepted, VS-030 inherits the known failed-refund bug (`vertical-slice-plan.md:820`).
- **R2 — The provider call fails after commit.** The order exists, cart cleared, attempt
  `failed`, 502. Recovery is VS-024's retry. Until VS-024 merges there is no retry
  endpoint, so the customer cannot pay that order; they must re-add and check out again
  after the hold, and VS-024 must merge before go-live (`accepting_orders` defaults
  `false`, `settings_registry.py:75-88`).
- **R3 — Tx2 fails after the provider created a payment** (DB blip). The reference is
  lost locally. Mitigation: the merchant reference is our `payment_id`, and the port's
  `query_status` must work by merchant reference. VS-032 must verify the real provider
  supports it, else document manual confirmation.
- **R4 — Event-id squatting** on providers without signatures. A forged event processed
  as "still pending" marks the id processed, so a genuine later event with the same id
  is deduplicated. Mitigation: unguessable provider ids, IP allowlist (VS-020),
  reconciliation (VS-024). VS-032 re-assesses per provider.
- **R5 — A retry between Tx1 and Tx2** gets `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` with
  the order id. Documented in `docs/checkout.md`. The frontend waits `Retry-After` and
  retries, then shows the order.
- **R6 — Tx2 updates a payment without locking `orders`.** It is safe only because
  nothing else can act on an attempt with no provider reference before Tx2. VS-024's
  reconciliation must skip attempts younger than the provider timeout, or lock `orders`
  first when it marks them. Noted for VS-024.
- **R7 — Late captures have no refund obligation until VS-030.** The signals are the
  audit row and an error log line. With Sentry unwired (`config.py:66`) nobody is paged.
  Someone must check the audit viewer filter regularly until VS-030 (or VS-020 wires
  alerting). VS-030 must backfill obligations for existing `late_captured_at` rows.
- **R13 — A crashed checkout leaves its key `in_progress` for 24 h.** Retries get 409
  naming the order, never a duplicate. Until VS-024 merges, the customer cannot pay that
  order (same exposure as R2).
- **R14 — Background verification runs in the API process.** A provider query of up to
  10 s holds no lock or DB connection while waiting (Tx A and Tx B are short), but it
  does occupy the event loop task. The cron fallback covers a lost task.
- **R8 — `webhook_events` grows without retention.** Raise with VS-045 / retention
  policy.
- **R9 — Mock state in Redis.** A Redis flush loses mock payments (dev only). The compose
  `REDIS_URL` must be in-network for both `api` and `worker`.
- **R10 — Coordination with VS-023b.** It needs PR A merged and `ordering.public`
  (`lock_order_for_change`, `recompute_order_status`) frozen at Checkpoint 2. Agree the
  signatures with the co-developer before PR B.
- **R11 — Production cannot take online payments until VS-032.** `none` lets it boot
  (Q5).
- **R12 — `UNIQUE NULLS NOT DISTINCT` support** in the pinned SQLAlchemy is unverified.
  Fall back to `op.execute`.

---

## 10. Owner questions (each with a recommendation)

1. **Which package owns orders and payments code?** *Recommendation:*
   - Ordering owns `orders`, `order_items`, `order_status_history`, checkout,
     `derive_order_status` and ownership.
   - Payments owns `payments`, `webhook_events`, the provider port/mock, the webhook and
     verify-and-apply.
   - Platform owns `idempotency_records`.
   - Fulfillment gets nothing in VS-023 (it owns STL delivery *transitions*, VS-023b).
   - Payments → `ordering.public` only; Ordering reaches Payments only through its own
     `PaymentAttempts` port wired in the API layer.
   - Evidence: ADR-005 `:13`, ADR-012 `:13`, ADR-013 `:13`, ADR-019 d8 `:23`,
     database-design §4 `:415-454`, `:433`, `:1407`.
2. **`webhook_events` has no payment link (ADR-024 appendix `:94`).** *Recommendation:*
   add nullable `provider_payment_id` and `payment_id` (FK `RESTRICT`), resolved at
   receipt, plus the partial index `(payment_id) WHERE processed_at IS NULL`. Ignored
   and definitively verified events get `processed_at`; only a provider outage leaves
   one unprocessed.
3. **The three cash CHECKs missing from VS-023's list (ADR-024 appendix `:95`;
   database-design `:1256-1258`).** *Recommendation:* create all three:
   - `verified_at IS NOT NULL` inside the cash shape;
   - `late_captured_at → status IN (failed, expired) AND provider <> 'cash'`;
   - `provider <> 'cash' → recorded_by IS NULL`.
   Also add two guards: paid-family → `verified_at` (Done-when in the database) and the
   terminal timestamps. Test each.
4. **Consent ordering: SRS §7.3 step 13 (after clearing the cart) vs the plan's step 7
   (before).** *Recommendation:* there is no behavioural difference inside one
   transaction. Validate consent before any write, write the timestamps in the `orders`
   INSERT, clear the cart last. Reword the plan row to match SRS ("recorded on the order
   row; cart cleared last"). Evidence: `SRS.md:665-666`,
   `vertical-slice-plan.md:530-531`, database-design §25 steps 12–13.
5. **Where does startup refuse production + mock, and what does production run before
   VS-032?** *Recommendation:* `configured_payment_providers(settings)` called at
   `main.py:28` (beside `captcha_verifier`) and `worker.py:39` (beside
   `get_email_provider`), not a `Settings` validator. Also accept
   `PAYMENT_PROVIDER=none`: no online provider, checkout answers **`503
   ONLINE_PAYMENT_UNAVAILABLE`** (Revision 1; was 422), every webhook path 404.
   Production can then boot before VS-032 with `accepting_orders` still false. The full
   matrix is in §3.9 and is tested through both entrypoints.
6. **Lock order across checkout, webhook, verification and purge.** *Recommendation:*
   adopt §8.1: `idempotency → cart → new-row inserts` for checkout; `orders → lines by id
   → payments → webhook_events` for every apply; the webhook and purge lock nothing
   existing. The proof is in §8.1 and race 7 tests it. VS-024 must not touch an attempt
   lacking a provider reference without locking `orders` (R6).
7. **Idempotency semantics.** *Recommendation:*
   - scope `checkout`, unique per (scope, user, key);
   - hash = canonical validated body;
   - claim states `in_progress` (Tx1, with the order id) → `done` (Tx2, 201 or 502);
     4xx/503 roll back, so a corrected retry with the same key runs fresh;
   - a same-key retry while `in_progress` (concurrent, or after a crash between Tx1 and
     Tx2) gets `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` naming the order. Never a second
     order, never a second provider call;
   - TTL 24 h, purged daily in batches. A key reused after 24 h is a new request.
   Confirm 24 h.
8. **Money correctness edge cases.** *Recommendation:*
   - charge live `price_cents`; the snapshot only detects changes;
   - refuse non-purchasable and over-cap lines with 422 naming every one (VS-022
     contract);
   - drop owned STLs and name them in `dropped_lines`; empty after drop → 409
     `CART_EMPTY`;
   - paid only via verification with exact amount and currency match;
   - provider called after commit, outside locks;
   - webhook dedupe on (provider, event id), signature checked, bad signature not
     stored;
   - mismatches become late captures;
   - **refuse a $0 online total** with 422 `PAYMENT_METHOD_NOT_ALLOWED`
     (`reason: zero_total`) until free STLs are a decided feature (prices may be 0,
     `fc18b48a1780…:46`).
9. **Columns created now for VS-023b/028, and their interface.** *Recommendation:*
   - create every frozen column of `orders`, `order_items` and `payments` (§4), the
     delivery CHECKs and `delivered_by`;
   - `offer_id` without FK (VS-039 adds it `NOT VALID` + `VALIDATE`);
   - leave the STL queue index and the `daily_download_cap` delete to VS-023b;
   - no receipt/problem CHECK until VS-029b decides.
   Freeze `ordering.public` (`lock_order_for_change`, `mark_order_paid`,
   `recompute_order_status`, `derive_order_status`, `stl_owned`) and `payments.public`
   (`verify_payment`, `apply_provider_result`, `PaymentProviderPort`,
   `configured_payment_providers`, `idempotency_store` via Platform) at Checkpoint 2.
10. **`derive_order_status` rule order (VS-030 review, `vertical-slice-plan.md:820`).**
    *Recommendation (Revision 1, CHANGED):* VS-023 implements SRS §20.2 **as written**
    (`SRS.md:1172-1186`), because the SRS does not provably contradict itself (Revision
    1 item 1). The tests pin case A → `refunded` and case B → `cancelled`. The
    owed-first reorder (A, B → `partially_refunded`, matching ADR-024 d11) is a VS-030
    note, to be decided there with an ADR and the co-developer's confirmation. No SRS
    edit in VS-023.
11. **Order number format** (unspecified; BR-032 "human-readable").
    *Recommendation:* `B3D-` + 8 Crockford base32 characters (random, unique index).
    A collision regenerates the number inside a SAVEPOINT, up to 5 attempts, so the
    transaction is never poisoned. Short, readable, unambiguous, and it does not reveal
    sales volume as a sequence would.
12. **What triggers verification?** *Recommendation (Revision 1, CHANGED):* a FastAPI
    `BackgroundTasks` call to `verify_event` **after** the webhook's 200 has been sent,
    plus the `verify_payments` cron every minute as fallback.
    - Typical delay is one provider query. Worst case is about 60 s plus the batch
      backlog (≈ 560 s with a degraded provider), as in §2.4.
    - Inline verification before the 200 is rejected (SRS §9.2 step 2).
    - Cron-only is rejected for its 60 s floor.
13. **Add `UNIQUE(provider, provider_payment_id)` now (ADR-024 appendix lists it under
    VS-032)?** *Recommendation:* yes. It is free on empty tables, makes reference lookup
    indexed, and prevents one capture applying to two attempts.
14. **The provider create call fails after commit.** *Recommendation:* mark the attempt
    `failed`, keep the order `pending_payment` with the cart cleared, answer 502
    `PAYMENT_PROVIDER_UNAVAILABLE` with `order_id`, and store that 502 for replays.
    Recovery is VS-024's retry. Read the plan bullet "a failure leaves the cart intact"
    as failures inside the checkout transaction.
15. **How does a developer complete a mock payment?** *Recommendation:* the mock keeps
    its state in Redis (shared by API and worker). `scripts/mock_pay.py <payment_id>
    paid|failed|underpaid` sets the outcome and posts a signed webhook. The script
    refuses production.
    - No dev HTTP endpoint in the API.
    - No HTTP route can mark a mock payment paid; the route table is in §3.6.
    - Mock refuses to boot in production, and with the default secret outside
      development/test.
16. **"Two parallel checkouts of one STL by one customer".** One user has one cart, so
    two cart checkouts serialise and the second sees `CART_EMPTY`.
    *Recommendation:* test the ownership index with checkout racing a direct
    pending-line insert (the stand-in for VS-041's offer checkout): one commit, one 409
    `PRODUCT_ALREADY_OWNED`. Also test the sequential re-add → checkout → 409 path.
17. **Rate limits.** *Recommendation (Revision 1, webhook CHANGED):*
    - checkout: 30/hour per user (fail closed, keyed by user id);
    - webhook: signature checked **first**; correctly signed traffic uses the
      per-provider bucket (600/min); invalid or unsigned traffic uses its own per-IP
      bucket (30/min), so it cannot exhaust the legitimate one;
    - `/me/stl-ownership`: unlimited, like other reads.
18. **DECIDED (owner, Revision 2):** add nullable `orders.digital_terms_version` in PR A;
    PR B writes a constant until a settings value exists; recorded in ADR-032. The
    original question follows. **Store a terms version with consent?** (new, Revision 1 item 10). The spec stores
    only timestamps (`SRS.md:666`; database-design `:985-988`; api-endpoints.md:1594),
    and no versioned terms document exists to point at.
    - *Recommendation:* store none in VS-023.
    - If the owner wants evidence of which text was accepted (useful against chargebacks,
      BR-065), add nullable `orders.terms_version` and `digital_terms_version` in a later
      additive migration once the terms pages carry versions. It would be a spec change
      with an ADR.
