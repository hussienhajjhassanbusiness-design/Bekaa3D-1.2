# ADR-032: Checkout, idempotency and payment verification (VS-023)

**Status:** Accepted. Schema in VS-023 PR A (migration `03a4730dd046`); checkout, idempotency and verification in VS-023 PR B.
**Date:** 2026-10-17
**Source basis:** Owner decisions of 2026-10-17 on the [VS-023 plan](../plans/VS-023-digital-checkout-plan.md) (Revisions 1-5 and Checkpoints 1-4); SRS §7.3, §7.5, §9.2, §20.1, §20.2, §23; database-design.md §8.3-§8.5, §9.1, §9.2, §13.4 and §14; [ADR-009](ADR-009-soft-delete-anonymisation-retention.md); [ADR-019](ADR-019-manual-stl-delivery.md); [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md), including its appendix; [ADR-029](ADR-029-cart-decisions.md)
**Applies first to:** migration `03a4730dd046`; `POST /api/v1/checkout`, `POST /api/v1/webhooks/payments/{provider}`, `GET /api/v1/me/stl-ownership`; the `verify_payments` and `purge_expired_idempotency_records` jobs.

## Context

VS-023 creates the order and payment tables with every frozen column, so VS-023b, VS-024, VS-028 and VS-029 need no destructive change. It then builds the first money path: a digital-only order paid online. Three properties drive every decision below:

- a customer is charged at most once, at the live price, and only after the provider itself confirms the exact amount;
- no network call happens inside a transaction or under a lock;
- a crash or a lost callback at any point leaves a state that a retry, the cron or VS-024's reconciliation can finish.

## Decision

### Schema (PR A)

1. **Foreign keys to `users` on financial rows are `RESTRICT`, as database-design §14 mandates.** These are `orders.user_id` (`:1879`), `order_items.user_id` (`:1890`), `order_items.delivered_by` (`:1891`) and `payments.recorded_by` (`:1892`).
   - A customer or administrator who owns money records is anonymised, never deleted (ADR-009).
   - The daily purge cannot reach these rows: it deletes only accounts with `email_verified_at IS NULL`, and checkout requires a verified account (BR-030).
   - `test_no_foreign_key_to_users_can_block_the_purge` allows `RESTRICT` only for these exact four (table, column) pairs.
2. **`order_status_history.actor_user_id` is `ON DELETE SET NULL`.** NULL already means "the system".
3. **`orders.digital_terms_version`** (TEXT, nullable) is set exactly when `digital_terms_accepted_at` is (`ck_orders_digital_terms_version`). Checkout writes a code constant until a settings value exists.
4. **`uq_payments_one_cash` is created before `uq_payments_one_live`,** so a second cash payment is reported under the INV-22 name.
5. **Schema additions from the ADR-024 appendix and the plan:** `webhook_events.provider_payment_id` and `payment_id` (FK `RESTRICT`), resolved at receipt; `idempotency_records.state` (`in_progress` / `done`) and `resource_id`; the three cash CHECKs from database-design §9.1; `paid` only with `verified_at`; `UNIQUE(provider, provider_payment_id)`.

### Ownership

6. **Ordering owns orders, lines, history, checkout, `derive_order_status` and STL ownership; Payments owns payments, webhook events, the provider port, the mock and verification; Platform owns idempotency.** Fulfillment owns nothing yet. Payments calls `app.ordering.public`; Ordering reaches Payments only through its own `PaymentAttempts` port, wired in the checkout route, so there is no import cycle.

### Checkout

7. **Two transactions, with the provider call between them.**
   - Tx1: claim the `Idempotency-Key`, lock the cart, revalidate every line against Catalog, insert the order, lines, pending payment, history and audit row, attach the order to the claim, clear the cart, commit.
   - The provider call runs with no transaction open, bounded at 10 s.
   - Tx2: store the provider reference, or fail the attempt (`502 PAYMENT_PROVIDER_UNAVAILABLE`), and store the response.
   - Only the `201` and the post-commit `502` are stored and replayed (`Idempotent-Replayed: true`). Every other refusal rolls back Tx1, the claim included, so a corrected retry with the same key runs fresh.
8. **No transaction is open while checkout waits on the provider** (owner, Checkpoint 3). The route reads the customer through `verified_user_short_read`, which checks the session, verification and CSRF in its own transaction and ends it before the handler runs. The request-scoped `get_session` behind `current_verified_user` would otherwise hold a read-only transaction and a pooled connection for the whole call. `test_checkout_no_open_transaction.py` holds a slow fake provider and finds no `idle in transaction` backend in `pg_stat_activity`.
9. **The live price is charged; the cart snapshot is display-only.** A price that differs from the snapshot is refused with `409 CART_PRICE_CHANGED` naming the new amount, unless the request accepts exactly that amount. Lines that cannot be bought are refused all together, each named; an STL bought since it was added is dropped and named (SRS §7.3 step 5).
10. **The STL ownership index is raced, not pre-checked.** A violation of `uq_order_items_stl_ownership` inside a SAVEPOINT becomes `409 PRODUCT_ALREADY_OWNED`, never a 500.
11. **Order numbers are `B3D-` and 8 Crockford base32 characters,** regenerated inside a SAVEPOINT on a collision, at most 5 attempts; the fifth collision is a 500 and nothing is written.
12. **`PAYMENT_PROVIDER=none` means no online payment:** an online checkout answers `503 ONLINE_PAYMENT_UNAVAILABLE` and every webhook path is 404. *Amended by [ADR-038](ADR-038-physical-checkout-and-cash-eligibility.md) decision 8 (VS-028):* a cash checkout needs no provider, so it still works.

### Idempotency

13. **A claim is `in_progress` from Tx1 and `done` once its response is stored.** Same key and body while `in_progress` is `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` naming the order (`Retry-After: 2`); a different body is `409 IDEMPOTENCY_KEY_CONFLICT`. Keys are per user and per scope, live 24 h and are purged daily. A replay counts against the 30-per-hour checkout limit.
14. **A crash between Tx1 and Tx2 leaves the claim `in_progress` naming the order,** so a retry can never place a second order or call the provider twice. The payment is recovered by our `payments.id`, which every provider event echoes as the merchant reference: the webhook resolves the payment by the provider's reference first, then by our id, and verification stores a missing provider reference under its locks.

### Webhooks and verification

15. **The webhook checks, in order:** a configured provider (else 404, nothing stored, no bucket); a body of at most 64 KiB, read as a bounded stream before the signature; the HMAC signature; then the bucket that matches it (per IP for an invalid signature, `client_ip`; per provider for a valid one); then storage, deduplicated on `(provider, provider_event_id)`. A body that would exceed 64 KiB once stored as `jsonb` is refused with 400. Every adapter must sign its webhooks: an unsigned-provider path is not built.
16. **The webhook never changes a payment.** It answers 200 and a `BackgroundTasks` callback runs verification after the response. Events for an unknown payment, or whose provider reference contradicts the payment, are stored already processed with `processing_error` (`unknown_payment`, `reference_mismatch`, `provider_mismatch`) and logged as errors.
17. **Verification asks the provider itself, never the webhook body.** Tx A reads without locks; the provider is queried with no transaction open; Tx B applies the answer. `verify_payments` runs every minute over up to 50 unprocessed events as the fallback. A provider that does not answer leaves the event unprocessed with its error.
18. **Delay from receipt to `paid`:** typically one provider query after the 200 (0.16 s against the mock, `test_webhook_api.py`); at worst about 60 s (the next tick) when the background task is lost, and up to about 560 s with a degraded provider (50 events at the 10 s timeout each).
19. **Tx B locks the order, then its lines by id, then the payment, and no other row** (ADR-024 d9). One unlocked read of the payment comes first, only to learn the order id; every decision is made from the rows read under the three locks. The event is marked processed last. Each lock has a race it alone decides, except the lines lock, which no current writer needs: every writer of an existing line already holds the order's lock (`test_order_item_writers.py`). It is kept for VS-023b, VS-024, VS-028 and VS-030.
20. **Paid only on an exact match:** the captured amount equals both the attempt and the order total, in USD, on a live attempt of an uncancelled order. Then the payment becomes `paid` with `verified_at`, STL lines move `pending -> awaiting_delivery` in the same transaction, the status is recomputed through `derive_order_status`, and the customer gets an email and a `payment.confirmed` notification.
21. **Any other capture is a late capture, recorded once:** `late_captured_at`, an audit row `payment.late_capture` with its reason (`amount_mismatch`, `attempt_not_live`, `order_cancelled`) and an error log. Lines are untouched. **Until VS-030, the only supported view of late captures is the SQL listing** `SELECT id, order_id, provider, amount_cents, status, late_captured_at FROM payments WHERE late_captured_at IS NOT NULL ORDER BY late_captured_at` (served by `ix_payments_late_captured`). VS-030 turns them into refund obligations.

### The mock and production

22. **The mock keeps its state in Redis, and only `simulate()` changes it,** called by tests and by `scripts/mock_pay.py`. No HTTP route can mark a mock payment paid (`test_payment_security.py` scans every route).
23. **Boot refuses a forbidden configuration in both `main.py` and `worker.py`:** the mock in any environment outside development, test and staging; the mock with the default secret outside development and test; `cash` or an unknown name. `scripts/mock_pay.py` uses the same allowlist.
24. **Go-live gate (owner):** no real online provider is configured in production before VS-024 and VS-030 are merged, unless an operational alert on late captures and stuck payments exists. VS-032's entry in the slice plan must cite this decision.

## Consequences

- Deleting a user who owns an order fails with `23503` on `orders_user_id_fkey`.
- A later slice that adds a `RESTRICT` key to `users` must cite §14 and extend the allowlist deliberately; a later writer of `order_items` must take the order's lock first and extend `test_order_item_writers.py`.
- VS-024 inherits `verify_payment()` and `apply_provider_result()`, and must treat an attempt with no provider reference older than the provider timeout as a reconciliation candidate.
- Every constraint, refusal and race in VS-023 has a test that was shown to fail once its guard is removed.

## Alternatives rejected

- **`CASCADE` on `orders.user_id`:** deleting a user would delete their orders and payments.
- **`SET NULL` on the owner columns:** they are NOT NULL by design, and `SET NULL` on `delivered_by` would break the STL delivery-record CHECK.
- **Calling the provider inside Tx1:** a slow provider would hold the cart lock, and a commit failure after a successful charge would lose the payment.
- **Verifying before the 200:** it ties the provider's webhook timeout to our provider query and multiplies its retries (SRS §9.2 step 2).
- **Cron-only verification:** a 60 s floor is visible to a customer returning from the payment page.
- **Trusting the webhook body:** anyone holding or guessing the secret could mark an order paid.
