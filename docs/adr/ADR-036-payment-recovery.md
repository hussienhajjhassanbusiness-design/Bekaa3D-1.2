# ADR-036: Payment recovery - retry, reconciliation, hold release and manual confirmation (VS-024)

**Status:** Accepted. Schema in VS-024 PR A (migration `00ce1ce252a6`, merged as #20); code in VS-024 PR B.
**Date:** 2026-10-20
**Source basis:** Owner decisions of 2026-10-18 to 2026-10-20 on the [VS-024 plan](../plans/VS-024-payment-recovery-plan.md) (Revisions 1-2 and Checkpoints 1-5); SRS §9.2, §9.4, §20.1, §23; database-design.md §8.3, §9.1, §9.2; [ADR-012](ADR-012-payment-provider-abstraction.md); [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md), including its appendix; [ADR-032](ADR-032-checkout-idempotency-and-payment-verification.md)
**Applies first to:** `POST /api/v1/me/orders/{order_id}/payments`; `GET /api/v1/admin/payments`, `GET /api/v1/admin/payments/{payment_id}`, `POST /api/v1/admin/payments/{payment_id}/reconcile`, `POST /api/v1/admin/payments/{payment_id}/confirm`, `POST /api/v1/admin/orders/{order_id}/release`; the `reconcile_payments` and `release_stale_checkouts` jobs.

**Numbering:** the VS-024 plan names this ADR-033. ADR-033 (VS-025), ADR-034 (VS-039) and ADR-035 (VS-040, unmerged) were taken on `origin` while VS-024 was built, so it is ADR-036.

## Context

VS-023 can charge a customer once, at the live price, and only on the provider's own exact answer. It cannot recover: a failed attempt leaves an order the customer cannot pay again, a lost callback waits for a webhook that never comes, and an abandoned checkout holds its STL until someone deletes it. VS-024 adds the exits without weakening VS-023's three properties: charged at most once; no network call inside a transaction or under a lock; every crash leaves a state a retry, a job or an admin can finish.

## Decision

### Release and reconciliation

1. **An order is released automatically only on an explicit provider `failed` or `expired` for its latest attempt** (table T2). No answer, a timeout, `unknown`, `pending`, `processing`, an unprocessed event, an open breaker, or a provider without a status API never releases anything. The release re-checks under `orders`, the lines by id and the order's payments by id: still `pending_payment`, the same latest attempt, no new unprocessed event, the deadline still passed, every attempt dead. The latest attempt is asked even when our own Tx2 already marked it `failed`.
2. **The hold deadline is `max(placed_at, latest attempt's initiated_at) + checkout_hold_period`** (D4). Retry is refused from `placed_at + checkout_hold_period`, so the deadline stays under twice the hold.
3. **`unknown` ("no record of this merchant reference") is "no answer" everywhere.** It never pays, fails or releases, and opens no Tx B.
4. **Reconciliation** asks the provider about live online attempts older than 5 minutes every 15 minutes, keyset-paged and unlocked, one query in flight, a 10 s bound per query, a 3-failure breaker per provider and a 240 s run deadline. Every provider call runs with no transaction open (`pg_stat_activity` probes).
5. **A status query is bounded at `PROVIDER_TIMEOUT_SECONDS`, and an adapter that does not declare `supports_status_query` is treated as having no status API:** it is never asked, and its orders need manual confirmation and manual release.

### Manual actions

6. **Manual confirm** (`POST /admin/payments/{id}/confirm`) is allowed only for a provider without a status API, or one no longer configured; a status provider is `409 MANUAL_CONFIRMATION_NOT_ALLOWED`. It goes through `apply_result`, the same function, decision table and lock order as the webhook.
7. **A typed amount or currency that differs from the attempt is `422 PAYMENT_AMOUNT_MISMATCH`, refused before any lock or write. There is no late-capture path from manual confirm:** nothing is written, no alert is raised. This amends ADR-024 d15 in part. A customer who paid a different amount on a no-status provider is refunded in the provider's dashboard (VS-030 owner question 2).
8. **Manual release** (`POST /admin/orders/{id}/release`) is available from the hold deadline plus a **24 h grace** (`MANUAL_RELEASE_GRACE`, a code constant), for every provider. A reason is mandatory and audited with the request id and IP hash; unprocessed events need `events_reviewed`, and are then dismissed and listed. The provider is never called. **The one early exception (Revision 2, Q7):** no stored provider reference and an `unknown` answer recorded; then it is available from the deadline itself.
9. **Admin reconcile answers `202` after its transaction commits and before any provider call**; the query runs in a background task with no transaction open (a raw ASGI ordering test). A lost task is picked up by the 15-minute job for a live attempt.

### Alerts

10. **Alerts go to every active, verified administrator** as an in-app notification and an outbox email, plus an error log carrying only ids and counts. Each delivery runs in its own SAVEPOINT, so a failed alert never rolls back a money write. Payloads carry only an allow-listed set of details: never a redirect URL, a provider reference or a customer contact.
11. **De-duplication is by `payment.alert_raised` audit rows, under a transaction-level advisory lock on `(kind, entity)`** (the payment, or the provider). The lock is the last lock any transaction takes, after `orders`, the lines and `payments` when the alert is raised inside Tx B; nothing locks after it but the `KEY SHARE` foreign-key checks on `users`, so it adds no cycle. Two job runs raising the same alert produce one per administrator (a real-Postgres race that fails without the lock).
12. **Late captures** store `captured_amount_cents` and `captured_currency` from the provider's verified answer, under the three locks, in the same UPDATE as the status, and raise one `late_capture` alert per payment. `GET /admin/payments?late_captured=true` now lists them alongside ADR-032 d21's SQL listing, which still works. VS-030 turns them into refund obligations through the `LateCaptureSink` hook.

### Retry

13. **Retry** is `POST /api/v1/me/orders/{order_id}/payments`, owner-only by the lock's own predicate (`… WHERE id AND user_id FOR UPDATE`), with checkout's two transactions around `create_payment`, an `Idempotency-Key` scoped `payment_retry:{order_id}` per user, and 10 per user per hour. `uq_payments_one_live` is the backstop: its violation is caught inside a SAVEPOINT and answered `409 PAYMENT_ALREADY_ACTIVE` with `payment_id`, `payment_status` and `redirect_url`. The field is `payment_status` because RFC 9457 reserves `status` for the HTTP status. The redirect URL is never logged or audited.

### Locks and limits

14. **Global lock order:** `idempotency_records → carts → orders → order_items (by id) → payments (by id) → webhook_events`, then INSERTs, and the alert advisory lock last. No separate hold-release lock.
15. **Every VS-024 timing and limit lives in `app.payments.domain.limits`** (D14), checked by a value test and a source scan.

### The go-live gate

16. **ADR-032 d24 stands, and this ADR does not open it.** Alerts close the gate's alert clause only if someone reads them: the email channel needs VS-021's sender, and an operator has to watch the in-app list. **Production stays on `PAYMENT_PROVIDER=none` until VS-032** delivers a real adapter, and VS-032 depends on VS-030 (refunds), so the main clause (VS-024 and VS-030 merged) also still applies.

## Consequences

- VS-030 replaces the `LateCaptureSink` binding to add the refund obligation in the same Tx B, after `payments`; it caps a late-capture refund by `captured_amount_cents`.
- **VS-032 notes:** an adapter must set `supports_status_query`; captured currencies must be upper-case ISO 4217 (`test_a_capture_names_its_currency_in_upper_case_iso_4217`; anything else breaks `ck_payments_captured_shape` and rolls Tx B back); an abandoned session must eventually answer `expired`, or its orders wait for manual release; `previous_provider`'s latest-attempt ordering becomes testable with a second online provider.
- Every guard, refusal and race has a test shown to fail once the guard is removed, except the equivalent mutants listed in the plan's checkpoint reports.

### Recorded deviations from the plan

- **Race #3** (a lock-free live INSERT committing while a retry is held) cannot happen: the INSERT takes `FOR KEY SHARE` on the `orders` row the retry holds `FOR UPDATE`, so it waits. The race test proves the wait; the index-to-409 mapping is tested with an in-transaction rival.
- **The detail's history length reuses `ADMIN_PAGE_MAX`** (100) rather than a new limit.
- **`GET /admin/payments` and its detail omit `needs_attention` and `last_provider_answer`** (plan §2.2); they are left for VS-029's admin queue.
- `OrderSide` did not gain `release`; the release calls `ordering.public.release_unpaid_order` directly. The job bodies live in `app.payments.infrastructure`, beside verification, because the application layer may not import infrastructure.
- A Redis outage on the retry limiter is 503 (fail closed), as every limiter, not 429.

## Alternatives rejected

- **Releasing on a timeout or `pending` after the hold:** a payment that is still being made would be cancelled, and its money would arrive for an order that no longer exists.
- **Recording a differing manual-confirm amount as a late capture:** a typo would create a refund obligation for money that never moved.
- **Redis for alert de-duplication:** an outage would drop alerts or repeat them every run, and the audit row is the operator's record anyway.
- **A separate hold-release lock:** it would add a lock the apply path does not take, and a second order in which locks could be taken.
