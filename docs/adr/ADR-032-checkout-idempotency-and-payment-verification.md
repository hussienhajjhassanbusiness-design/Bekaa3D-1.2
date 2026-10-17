# ADR-032: Checkout, idempotency and payment verification - schema decisions (VS-023)

**Status:** Accepted for the schema (VS-023 PR A). The checkout, idempotency and verification decisions are added by VS-023 PR B, per [the VS-023 plan](../plans/VS-023-digital-checkout-plan.md).
**Date:** 2026-10-17
**Source basis:** Owner decisions of 2026-10-17 on the VS-023 plan (Revision 2, Q18, the purge conflict); database-design.md §8.3-§8.5, §9.1, §9.2, §13.4 and §14; [ADR-009](ADR-009-soft-delete-anonymisation-retention.md); [ADR-019](ADR-019-manual-stl-delivery.md); [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md), including its appendix
**Applies first to:** migration `03a4730dd046` (orders, order_items, order_status_history, payments, webhook_events, idempotency_records).

## Context

VS-023 creates the order and payment tables with every frozen column, so VS-023b, VS-024, VS-028 and VS-029 need no destructive change. Building them surfaced four schema questions the spec does not settle by itself:

- §14 gives the first `RESTRICT` foreign keys to `users`, while an existing test required every such key to be `CASCADE` or `SET NULL` so the never-verified purge can never fail.
- The owner wants evidence of which digital-terms text a customer accepted.
- A cash payment is always live, which hides the one-cash-payment index behind the one-live-payment index.
- The ADR-024 appendix left `webhook_events` without a payment link and the idempotency record without states.

## Decision

1. **Foreign keys to `users` on financial rows are `RESTRICT`, as database-design §14 mandates.** These are `orders.user_id` (`:1879`), `order_items.user_id` (`:1890`), `order_items.delivered_by` (`:1891`) and `payments.recorded_by` (`:1892`).
   - A customer or administrator who owns money records is anonymised, never deleted (ADR-009).
   - The daily purge cannot reach these rows: it deletes only accounts with `email_verified_at IS NULL`, and checkout requires a verified account (BR-030).
   - `test_no_foreign_key_to_users_can_block_the_purge` allows `RESTRICT` only for these exact four (table, column) pairs. Any other `RESTRICT` key to `users` fails it.
2. **`order_status_history.actor_user_id` is `ON DELETE SET NULL`.** NULL already means "the system". No CHECK or NOT NULL prevents it, and the history row survives.
3. **`orders.digital_terms_version`** (TEXT, nullable) is a plan addition.
   - It is set exactly when `digital_terms_accepted_at` is (`ck_orders_digital_terms_version`).
   - Checkout writes a code constant until a settings value exists.
   - There is no general `terms_version` column.
4. **`uq_payments_one_cash` is created before `uq_payments_one_live`.** PostgreSQL then reports a second cash payment under the INV-22 name. Otherwise the live-payment index always fires first, because a cash payment is never `failed` or `expired`.
5. **Schema additions from the ADR-024 appendix and the plan:**
   - `webhook_events.provider_payment_id` and `payment_id` (FK `RESTRICT`), resolved at receipt, with `(payment_id) WHERE processed_at IS NULL`;
   - `idempotency_records.state` (`in_progress` / `done`) and `resource_id`;
   - the three cash CHECKs from database-design §9.1;
   - `paid` only with `verified_at`;
   - `UNIQUE(provider, provider_payment_id)`.
6. **Go-live gate (owner):** no real online provider is configured in production before VS-024 and VS-030 are merged, unless an operational alert on late captures and stuck payments exists.
7. **No transaction is open while checkout waits on the provider** (owner, Checkpoint 3). The checkout route reads the customer through `verified_user_short_read`, which checks the session, verification and CSRF in its own transaction and ends it before the handler runs. The request-scoped `get_session` behind `current_verified_user` would otherwise hold a read-only transaction and a pooled connection for the whole provider call, up to its 10 s timeout. `test_checkout_no_open_transaction.py` holds a slow fake provider and finds no `idle in transaction` backend in `pg_stat_activity` meanwhile.
8. **Verification runs after the webhook's 200, with a cron fallback.** The webhook only caps the body (64 KiB, before the signature), checks the signature, spends the matching bucket (per IP for invalid or unsigned traffic, per provider for signed traffic) and stores the event deduplicated on `(provider, provider_event_id)`. A `BackgroundTasks` callback then asks the provider itself (never the webhook body) and applies the answer in one transaction that locks `orders`, then `order_items` by id, then `payments`, and marks the event processed last. `verify_payments` runs every minute over up to 50 unprocessed events. Delay from receipt to `paid`: typically one provider query after the 200 (0.16 s against the mock, measured in `test_webhook_api.py`); at worst about 60 s (the next tick) when the background task is lost, and up to about 560 s with a degraded provider (50 events at the 10 s timeout each); a provider that stays down keeps the event unprocessed until it answers.
9. **Paid only on an exact match.** Captured amount equals both the attempt and the order total, in USD, on a live attempt of an uncancelled order, and `verified_at` is set. Any other capture is a late capture, recorded once: `late_captured_at`, an audit row `payment.late_capture` with its reason, and an error log. The listing query is `SELECT ... FROM payments WHERE late_captured_at IS NOT NULL` (`ix_payments_late_captured`).

## Consequences

- Deleting a user who owns an order fails with `23503` on `orders_user_id_fkey`. A schema test asserts it, alongside a test that a never-verified user without orders is deleted normally.
- A later slice that adds a `RESTRICT` key to `users` must cite §14 and extend the allowlist deliberately.
- Every constraint is tested at the database level by name, and each test was shown to fail once its constraint is removed.

## Alternatives rejected

- **`CASCADE` on `orders.user_id`:** deleting a user would delete their orders and payments.
- **`SET NULL` on the owner columns:** they are NOT NULL by design, and `SET NULL` on `delivered_by` would break the STL delivery-record CHECK.
- **Keeping the blanket "CASCADE or SET NULL" test:** it contradicts §14 and would force one of the two options above.
