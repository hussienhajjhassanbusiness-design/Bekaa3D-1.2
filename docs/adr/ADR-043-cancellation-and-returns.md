# ADR-043: Cancellation and returns - every cancel of a paid line refunds its whole remaining balance, one use case serves the customer, the administrator and the transition endpoint (VS-031)

**Status:** Accepted (2026-10-24, owner approval of the VS-031 plan, items 1-13 and both must-resolve answers)
**Date:** 2026-10-24
**Source basis:** [VS-031 slice](../vertical-slice-plan.md#vs-031--cancellation-and-returns) and its two "Must resolve before build" items; SRS §8.9, §20.4-20.5, BR-144, BR-148, BR-149; FR-08, FR-09, FR-20; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d8, d9; [ADR-033](ADR-033-customer-order-read-model.md) d4; [ADR-040](ADR-040-admin-order-queue-fulfillment-and-cash-handover.md) d1, d2; [ADR-042](ADR-042-refunds-voids-and-chargebacks.md) d5, d16, d17; VS-030 plan §3.7.
**Amends:** database-design §3.4b (`shipped -> cancelled` records `other`); api-endpoints §21 (the admin cancel's 409 reasons); SRS BR-145, §9 step 9 and §9.8.1 (d12: no cash for a cart with a line priced 0). Must-resolve 1 is [ADR-038](ADR-038-physical-checkout-and-cash-eligibility.md) d23.
**Applies first to:** migration `595b7e6e2792` (`orders.customer_cancelled_at`).

## Context

VS-030 built refunds and chargebacks but left cancellation to VS-031. Two items had to be resolved before building:

1. A customer's self-cancel of an unpaid cash order reopened ADR-038 d22's cash probe (resolved by ADR-038 d23).
2. A chargeback's items must total exactly `min(charged - absorbed, the payment's balance)` (ADR-042 d16). If any writer left a paid line `cancelled` with less than its total covered, the payment's balance would exceed the sum of the line balances, and every chargeback on that order would get a 422 it could not satisfy.

## Decision

1. **Every cancel of a paid line refunds its whole remaining balance, in the same transaction** (must-resolve 2). `payments.domain.refunds.cancellation_items` derives one item per cancelled line, equal to its balance (none when that is 0, e.g. a $0 line). It refuses a line that is not unfinished physical. If the refund cannot be created (the payment's balance is smaller, or the Q-2 totals check fails), the whole cancel is refused with a 409 and nothing changes. So after any cancel the line balances still sum to the payment's balance, and a chargeback for the whole payment can always be allocated. The cap alternative (cap the required chargeback total by the sum of line balances) was rejected: it would hide the inconsistency rather than prevent it.
2. **One use case, three entry points** (`fulfillment/application/cancel_lines.py`):
   - the customer's `POST /me/orders/{id}/cancel`;
   - the administrator's `POST /admin/orders/{id}/cancel`;
   - the transition endpoint's `-> cancelled`.

   All three run in the ADR-024 d9 order:
   1. `orders`, then every line by id;
   2. payments, then the refund (`payments.public.create_cancellation_refund`, under the caller's lock, leaving the order recompute to the caller);
   3. Ordering's `cancel_lines` writer;
   4. if a block is due, the customer's cart (created if missing), then the phone advisory lock, then the block;
   5. the order status, recomputed from fresh refund facts.

   Fulfillment owns it because it already combines Ordering and Payments. `app.fulfillment.public` serves Ordering's customer route, which builds its own `OrderDetail` (plan Q13).
3. **The edges** (`ordering/domain/line_transitions.py`): `shipped -> returned`, `returned -> shipped | in_production`, and the cancels.
   - `pending` and `in_production` take no reason.
   - `ready_to_ship` takes `refused` or `other`; `ready_for_pickup` takes `refused`, `no_show` or `other`.
   - `returned` takes `refused` or `other`, on an unpaid cash line only.
   - `shipped` takes only `other`, on an unpaid cash line of total 0. This amends §3.4b, which listed only three states.

   A missing reason is `409 cancel_reason_required`; a reason the state does not take is `cancel_reason_not_allowed`. `available_actions` lists each target with its reasons, from the same table. `returned -> refunded` goes through the refund endpoint only (Q2). STL lines are never cancelled.
4. **The customer's cancel** reuses `can_cancel` under the locks (ADR-033 d4): every live physical line, all `pending`, or nothing (`409 ORDER_NOT_CANCELLABLE`). It sets `orders.customer_cancelled_at` (ADR-038 d23). Its refund is requested by the customer and approved by no administrator (`approved_by` NULL).
5. **The administrator's order cancel** takes every physical line in `pending`, `in_production`, `ready_to_ship` or `ready_for_pickup`. One `cancel_reason` per request is recorded on the lines that take one. Lines that are shipped, returned or done are left alone. The 409 reasons are:
   - `payment_required` on an unpaid online order (BR-148);
   - `no_cancellable_line`;
   - `cancel_reason_required` and `cancel_reason_not_allowed`.

   A `returned` line is cancelled through the transition endpoint (Q6).
6. **The cash block (BR-144)** reads all the order's lines after the cancel. It applies to an unpaid cash order with no live line, where every recorded reason is `refused` or `no_show` (at least one). The block's reason is `refused` if any line was refused, else `no_show` (Q7). An online order never blocks.
7. **`orders.cancelled_at` stays the hold release's mark** (Q5): no cancel sets it, so `ADMIN_QUEUE_PREDICATE` is unchanged and a cancelled paid order stays in the queue.
8. **Notices (Q3).**
   - Every cancel sends one `order_cancelled` email and an `order.cancelled` notification. They name the cancelled lines, say whether the order is now cancelled, give the new `amount_due_cents` when an unpaid cash order still has live lines, and give the refund amount when there is one.
   - A paid cancel also sends VS-030's "refund issued" notice (Q7), so the customer gets two messages.
   - A cancel that leaves every live line at a visible step not reached before announces that step once (`step_newly_reached`). A re-ship announces `shipped` again.
9. **No `Idempotency-Key`** on a cancel (Q4): under the lock a repeat finds the lines already cancelled, so it is a 409 and never a second refund.
10. **One `order.cancelled` audit row per request** (Q10). It records the lines with their previous state and reason, the refund id and amount, whether a block was written, the note, and the actor (customer or administrator). It holds no phone or hash.
11. **Rate limits** (Q12): the customer has 10 cancels per hour; the administrator's cancels share the transition endpoint's per-administrator limit. The customer's optional `reason` (at most 500 characters) is kept in the status history.
12. **Cash refuses a cart with any physical line priced 0** (owner decision 2026-10-24, closing ADR-024's appendix item for VS-031). Otherwise a customer who adds a free item to every cash order and refuses only the paid lines at the door ends with the free line cancelled `other`, and `other` prevents the BR-144 block every time. The refusal is the one generic `422 CASH_NOT_AVAILABLE` of ADR-038 d19, raised in `cash_precheck` before the phone lock, so it says nothing about the account or the phone (ADR-038 d20). A cart whose whole total is 0 keeps its earlier `PAYMENT_METHOD_NOT_ALLOWED` (`zero_total`). The same cart can still be paid online. The `$0` cancel edges (`shipped -> cancelled` with `other`) stay for cash orders placed before this rule.

## Consequences

- `orders.status` can read `cancelled` while `orders.cancelled_at` is NULL. That is a cancelled paid order or a cancelled cash order; each line carries its own `cancelled_at`.
- A cancellation refund is never voided (ADR-042's `line_already_cancelled`). One created by mistake is settled or failed.
- `tests/unit/ordering/test_cash_lock_order.py` allowlists the fulfillment adapter `insert_cash_block` as the third caller of the phone lock, and proves it takes the cart lock first.
- `KNOWN_LINE_STATUS_CALLERS` is unchanged. The cancel writes through `SqlOrderStore.cancel_order_lines`, listed in `KNOWN_WRITERS`, called only from `ordering.public.cancel_lines`.
