# ADR-038: Physical checkout and cash eligibility - a hash-only cash block table that can only reference a cash order, canonical phone spellings in the database, and a never-rotated phone-hash key (VS-028)

**Status:** Accepted in full. Decisions 1-7 (schema) are built in VS-028 PR A (migration `fcd589e89e59`); decisions 8-18 (checkout, plan D3-D13) in PR B (#31); decisions 19-22 by the review follow-up of 2026-10-22.
**Date:** 2026-10-20
**Source basis:** Owner decisions of 2026-10-20 on the [VS-028 plan](../plans/VS-028-physical-checkout-plan.md) (Q1-Q17, Revisions 1-3); SRS §7.3, §7.4, §9.8; BR-141, BR-144, BR-145; database-design.md §8.3, §8.6, §14; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md); [ADR-027](ADR-027-address-book-decisions.md); [ADR-028](ADR-028-keyed-monthly-rotated-ip-hashes.md); [ADR-032](ADR-032-checkout-idempotency-and-payment-verification.md)
**Applies first to:** `cash_payment_blocks`; `orders.contact_phone_snapshot` and `orders.contact_phone_hash`; the `cash_*` settings; `PHONE_HASH_SALT`; `GET /api/v1/settings/public`; `POST /api/v1/checkout`; `amount_due` on the order reads.
**Amends:** [ADR-032](ADR-032-checkout-idempotency-and-payment-verification.md) d12 (decision 8); SRS §22.3's cash rows (decision 19).

## Context

ADR-024 lets a physical-only order be paid in cash, limited per customer **or** per contact phone, and blocked after a whole-order refusal. Both the limit and the block match on a keyed hash of the normalised phone, so the hash must be computed one way, from one spelling, with one key that never changes. VS-023 created the order columns; VS-028 PR A adds the block table, the settings and the key, before any checkout code reads them.

## Decision

1. **`cash_payment_blocks` holds only the phone's hash**, `^[0-9a-f]{64}$` (`ck_cash_payment_blocks_hash_format`), never the number. A block is `refused` or `no_show` only (`ck_cash_payment_blocks_reason`), one per order (`uq_cash_payment_blocks_order`), and cleared with both `cleared_at` and `cleared_by` (`ck_cash_payment_blocks_cleared_pair`); it is never deleted.
2. **A block can only reference a cash order** (plan Q4). The table carries `order_payment_method`, defaulting to and CHECKed as `'cash'` (`ck_cash_payment_blocks_cash_only`), under a composite foreign key to `orders(id, payment_method)` (`fk_cash_payment_blocks_order_payment_method`), the INV-21 pattern payments already use. Either guard alone refuses a block on an online order.
3. **Both foreign keys to `users` are `RESTRICT`**, as database-design §14 lists them:
   - `cash_payment_blocks.user_id` (`database-design.md:1953`, `fk_cash_payment_blocks_user`);
   - `cash_payment_blocks.cleared_by` (`database-design.md:1955`, `fk_cash_payment_blocks_cleared_by`).

   They join the allowlist in `tests/integration/test_deep_db_constraints_and_migrations.py` (`RESTRICT_TO_USERS_ALLOWED`), as ADR-032's Consequences require for any new `RESTRICT` key to `users`. The daily purge of never-verified accounts cannot reach either:
   - a block needs a cash order, and a cash order needs a verified customer (already held by `orders.user_id`, `RESTRICT`);
   - `cleared_by` is always an administrator.
4. **The order's contact phone is stored in one spelling** (plan Q6): `ck_orders_contact_phone_e164` (`^\+961[0-9]{7,8}$`, the form `app.core.phone` produces) and `ck_orders_phone_hash_format`. Two spellings of one number in the database would let a second account escape the limit.
5. **The open-cash-order count by phone has its index now** (plan Q3): `ix_orders_open_cash_phone (contact_phone_hash) WHERE payment_method = 'cash' AND status = 'in_progress'`. `EXPLAIN` on an empty table cannot show the need, and creating it later would mean a migration on a live table. The count by user is served by `ix_orders_user_placed`.
6. **`PHONE_HASH_SALT` is a required secret, never rotated** (ADR-024 d6, plan Q5). `hash_phone` is `HMAC-SHA256(key = PHONE_HASH_SALT, msg = E.164)`, lowercase hex, and refuses any input that is not already E.164. Outside development and test, `main.py` and `worker.py` refuse to start with a value shorter than 32 characters or still starting with `generate_with__`; the error names the setting, never its value. Logs redact it by key, and redact the phone, its hash and E.164 numbers inside text.
7. **Settings** (BR-145): `cash_payment_enabled` (public, `true`), `cash_max_open_orders` (private, `1`, 1-10) and `cash_max_order_total` (public, 10 000 cents, 1-1 000 000, never null). `free_shipping_threshold` is deleted from the table, the registry and the public allowlist; a downgrade restores it as JSON null.

## Checkout decisions (VS-028 PR B; plan D3-D13)

8. **`ONLINE_PAYMENT_UNAVAILABLE` (503) is for online checkouts only** (D3). A cash checkout needs no provider and works with `PAYMENT_PROVIDER=none`. This amends ADR-032 d12; webhooks are still 404.
9. **A cash checkout is one transaction** (D4): claim the key, place the order, complete the claim, COMMIT. No payment row, no provider call, no Tx2. A failure anywhere before the COMMIT leaves no order, no claim and the cart as it was.
10. **Lock order** (D5): `idempotency_records → carts → addresses FOR SHARE (delivery) → the phone advisory lock (cash)`, then reads and INSERTs only. Checkout never locks an existing `orders` row; VS-031's `orders → cart → phone` cancel depends on that ([ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d9).
11. **The phone lock is `pg_advisory_xact_lock(CASH_PHONE_LOCK_NS, hashtext(phone_hash))`** (D6), the two-int form, whose key space is not the one-bigint locks'. VS-031's block insert takes it through the same function, `ordering.public.lock_cash_phone`.
12. **The phone hash is computed in one place** (D7): `app.core.security.hash_phone`, as decision 6 defines it.
13. **Open cash orders are `payment_method = 'cash' AND status = 'in_progress'`** (D8), matched by `user_id` or `contact_phone_hash`. That equals "unpaid and not cancelled" only because an unpaid cash order derives `in_progress` until every line is cancelled, and a cash order that reached `paid` never derives `in_progress`. VS-030 changes the projection and must keep both true (slice plan, VS-030 "Must resolve" item 6).
14. **The SRS 7.4 matrix is one pure function over the kept lines** (D9), after owned STLs are dropped.
15. **Contact phones are normalised in `CheckoutRequest`** (D10), so the idempotency hash covers the E.164 form and two spellings of one number are one body.
16. **Dispatch** (D11): `estimated_dispatch_at = placed_at + max(lead × ceil(qty ÷ batch))` calendar days over the physical lines; none for an STL-only order. Lead time and batch size are snapshotted on each physical line.
17. **The amount due is one pure function** (D12), `amount_due_cents(lines)`: the line totals not cancelled. VS-029's handover reuses it. The API shows it as `amount_due` (decision 21).
18. **Snapshots are immutable by construction** (D13): no `UPDATE orders` writes a snapshot column, enforced by a static writer test. No database trigger.

## PR B as built (2026-10-22): deviations from the plan

PR B (branch `vs-028-checkout`) follows the plan's D3-D13 as written; only these differ.

1. **Refusal precedence.** The SRS 7.4 matrix now runs after owned STLs are dropped, so `INVALID_FULFILLMENT` and `cash_requires_physical` come after `CART_EMPTY` (with `dropped_lines`) and before `CART_PRICE_CHANGED`. Before PR B a physical line was refused before the owned-STL drop.
2. **`resolve_fulfillment` takes the kept lines' product types**, not the lines, plus the command's fields; the matrix needs nothing else.
3. **The courier note keeps the existing VS-025 wording**, "The delivery fee is paid to the courier on delivery.", as one constant in `ordering/domain/fulfillment.py` used by every response and email.
4. **`Order` (the internal read of a placed order) gains `estimated_dispatch_at` and the address snapshot**, never the phone or its hash, so the checkout response and emails need no second read. `OnlinePlacedOrder` keeps the provider call and offer checkout typed with a non-null payment.
5. **`get_live_for_share` is on `SqlAddressRepository` only**, not on the `AddressStore` protocol: only `identity.public.lock_checkout_address` calls it.
6. **The release query keeps its `payment_method = 'online'` filter as defence in depth.** It is redundant today, because an unpaid cash order derives `in_progress`, never `pending_payment`, but no CHECK enforces that. The reconcile query's `order_payment_method = 'online'` filter is redundant for the same kind of reason: a cash order has no payment row until VS-029 records one as `paid`.
7. **R1's delivery variant uses one E.164 number on both addresses.** `ck_addresses_phone_e164` stores no other spelling; the pickup variant sends two spellings of one number.
8. **The leak scan searches three more strings than the plan lists**: the two spaced spellings the customer sends and the invalid input. Without them an echoed invalid number went unnoticed (mutation L2).
9. **R5 proves the D5 invariant directly.** A cash checkout completes while a release or a payment retry holds the customer's other order. Taking any `orders` lock before the phone lock makes it wait, and the test fails.

## Review follow-up (2026-10-22, after PR #31)

19. **One refusal for a block and for an open cash order.** Both are `422 CASH_NOT_AVAILABLE` with the detail "Cash on delivery isn't available for this order; please pay online." and no `reason`. The body never says which rule matched, nor whether the account or the phone did. This replaces the plan's Q8 answer (distinct `cash_blocked` and `open_orders` reasons) and amends SRS §22.3. `CASH_PAYMENT_LIMIT_REACHED` now means only `reason: order_total`.
20. **Every cash check that needs no phone runs before the phone lock**, the total cap included: all lines physical, `cash_payment_enabled`, a total above zero, then `cash_max_order_total`. Checked after the phone, an over-cap cart would read `order_total` for a clean phone and `CASH_NOT_AVAILABLE` for a blocked one: a probe that creates nothing.
21. **`amount_due` is a `PriceRead`** (`{amount_cents, currency}`, or null) on the checkout response, the order list and the order detail, like every other amount in the API. It replaces the plan's Q12 answer (a bare `amount_due_cents`). The `order_cash_placed` email payload keeps `amount_due_cents` with `currency`, as `order_payment_confirmed` keeps `total_cents`.
22. **The remaining probe is accepted.** A verified customer with a physical cart can still learn that a phone is blocked or has an open cash order: try cash with it and get `CASH_NOT_AVAILABLE` instead of an order. It is bounded by the 30-per-hour checkout limit, and the first probe that does not match places a real cash order on the prober's own account. From then on every cash checkout from that account is refused whatever the phone, until that order is handed over or cancelled (with the default `cash_max_open_orders = 1`). The answer never names the rule or the account.

## Consequences

- The plaintext phone exists only in `orders.contact_phone_snapshot`. Leaking `PHONE_HASH_SALT` lets the about 10^8 Lebanese numbers be brute-forced from block hashes; losing it makes every block stop matching by phone (they still match by `user_id`), and order hashes would have to be recomputed from the snapshots.
- A user who has a block row, or who cleared one, cannot be hard-deleted. VS-045's anonymisation must keep the row (it holds no readable personal data) rather than delete the user.
- The public settings response changed shape (2026-10-20): the frontend handoff records the removal.
- The checkout and order responses changed shape (2026-10-22): `amount_due_cents` became `amount_due`, and `cash_blocked` / `open_orders` became `CASH_NOT_AVAILABLE`. The frontend handoff records both; the frontend shows one message for `CASH_NOT_AVAILABLE`.

## Alternatives rejected

- **A `users` column for the block** - it cannot match a phone used by a second account (ADR-024 Consequences).
- **`ON DELETE SET NULL` on `cleared_by`** - contradicts database-design §14 and would erase who cleared a block; the purge cannot reach an administrator anyway.
- **Rotating the phone key like the IP salt (ADR-028)** - every existing block and open-order match would silently stop matching.
