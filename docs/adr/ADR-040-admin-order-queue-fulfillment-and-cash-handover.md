# ADR-040: Admin order queue, physical fulfillment and cash handover - forward edges only, one notice per order per visible step, the handover as the only cash writer, a queue that never lists an unpaid online order (VS-029)

**Status:** Accepted
**Date:** 2026-10-23
**Source basis:** [VS-029 slice plan](../vertical-slice-plan.md#vs-029--admin-order-queue-fulfillment-and-cash-handover); SRS §8.3-§8.5, §8.7, §9.8.3, §9.8.6, §15.2, §16.1, §20.2-§20.5; BR-054, BR-055, BR-143, BR-148; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d4, d6, d8, d9; [ADR-025](ADR-025-frontend-contract-decisions.md); [ADR-033](ADR-033-customer-order-read-model.md); [ADR-038](ADR-038-physical-checkout-and-cash-eligibility.md); [ADR-039](ADR-039-stl-delivery-workflow.md)
**Supersedes:** ADR-039 d4's `not_an_stl_line` reason (a physical line now takes the physical edges) and d9 (the transition answers `AdminOrderDetail`).
**Applies first to:** `GET /api/v1/admin/orders`, `GET/PATCH /api/v1/admin/orders/{order_id}`, `POST …/items/{item_id}/transition` (physical edges), `POST …/cash-handover`, `/api/v1/admin/cash-blocks` (list, search, clear); migration `b6e1d0c4a2f7`.

## Context

VS-023b (ADR-039) built the transition endpoint for STL lines and a pure edge table. VS-028 created cash orders that have no payment row until the administrator records the cash (SRS §9.8.3). Physical lines could not move yet, nothing created a cash payment, and the administrator had no order queue. VS-030 (refunds) and VS-031 (cancellations, returns, cash blocks) build on what this slice decides.

## Decision

1. **Forward edges only.** VS-029 adds `pending → in_production → ready_to_ship → shipped → delivered` (delivery) and `pending → in_production → ready_for_pickup → picked_up` (pickup) to `ordering/domain/line_transitions.py`. Cancel, return and refund edges are VS-031's and VS-030's, so `available_actions[].cancel_reasons` is always empty for now. The table is the single source for the endpoint's refusals and for `available_actions` (ADR-025), so the two cannot disagree.
2. **One email and one notification per order per visible step** (`ordering/domain/fulfillment_steps.py`). The visible steps are `ready_to_ship`, `shipped`, `delivered` (delivery) and `ready_for_pickup`, `picked_up` (pickup); `in_production` is silent and masked for the customer (ADR-033). A notice is sent only on the transition that brings the *last* live physical line to that step: a multi-line order hears once, not once per line. Cancelled and refunded lines are not waited for. Because VS-029 lines only move forward one edge at a time under the order lock, each step can be reached once. The handover sends the `delivered` / `picked_up` notice itself, with the cash receipt.
3. **BR-148 in the table.** Every physical edge needs a cash order or an online payment that reached `paid` (`paid`, `partially_refunded`, `refunded`), read after the order lock is taken; otherwise `409 payment_required`. The hold release's `pending → cancelled` (VS-024) does not use this endpoint.
4. **On a cash order only the handover reaches `delivered` / `picked_up`**: the endpoint refuses them with `409 cash_handover_required`, and `available_actions` never lists them.
5. **`completed_at` is written the first time the order becomes `completed`** (`coalesce`), so a later recompute never moves it.
6. **The cash handover is the only writer of a cash payment.** `record_cash_handover` locks the order, then every line by id (ADR-024 d9); refuses with `409` (`not_a_cash_order`, `no_live_line`, `already_recorded`, `lines_not_ready`, in that order); requires `amount_cents` to equal the live line total (ADR-033 `amount_due_cents`) and be above zero, in the order's currency, else `422 CASH_AMOUNT_MISMATCH` carrying `amount_due`; then inserts one `paid` cash payment with `recorded_by` and `verified_at`, moves every live line, recomputes the status, and writes history, audit, notification and email in the same transaction. The insert runs in a SAVEPOINT and `uq_payments_one_cash` is the final guard; a second cash row also breaks `uq_payments_one_live`, so either name maps to `CashAlreadyRecordedError` → `409 already_recorded`. `tests/unit/payments/test_cash_payment_writers.py` pins the call chain, and the chains that move lines as paid (`hand_over_cash_lines`) or pass BR-148's flag (`transition_physical_line`).
7. **Fulfillment writes through the other contexts' public modules.** Lines and status through `ordering.public`, the cash row through `payments.public.insert_cash_payment`, all on the route's session; Fulfillment owns no table.
8. **The queue never lists an unpaid online order, open or released** (`ADMIN_QUEUE_PREDICATE`: `status <> 'pending_payment' AND (payment_method = 'cash' OR cancelled_at IS NULL)`), and `status=pending_payment` is a `422`. Today only the hold release sets `orders.cancelled_at` on an online order. The detail route opens any order, so an administrator following a link still sees an unpaid one, with no actions. The queue is keyset-paged by `(placed_at, id)`, newest first, on the partial index `ix_orders_admin_queue`; the `payment_due=true` ("cash due") view uses `ix_orders_cash_due`. Both are checked with `EXPLAIN`.
9. **The internal note is the only `PATCH`able field.** Blank or null clears it. The audit row records `has_note` only, never the text, and no history row is written. No customer schema has the field.
10. **Limits** (`fulfillment/domain/limits.py`): all line transitions share the VS-023b limit of 300 an hour per administrator; the handover 60, the note 120, the cash-block search and clear 60. Queue pages default to 25, at most 100.
11. **Cash blocks.** The list filters by customer and active. The phone search takes the phone in the body, so it never reaches request logs, normalises it like checkout (any spelling matches) and matches on its keyed hash. No response carries the phone or its hash (ADR-038). Clearing locks the block, sets `cleared_at` and `cleared_by` and writes an audit row; clearing a cleared block is a `200` that changes and audits nothing.

## Consequences

+ A physical order of either payment method reaches `completed`, and a cash order's payment exists only for exactly the cash recorded at handover.
+ Two administrators on one transition or one handover produce one outcome and one set of side effects; a handover racing a transition on another line, or a `reconcile_payments` run, ends with one consistent result and no deadlock (`tests/concurrency/test_admin_order_races.py`).
- **VS-031 must keep d2 true when lines can be cancelled or returned.** A cancel can make the remaining lines "all at step X" without any of them moving, so the step's notice would be skipped; a `shipped → returned → shipped` edge would re-send `shipped`. VS-031 decides whether either sends a notice.
- **VS-031 must keep d8 true.** If cancelling a paid online order sets `orders.cancelled_at`, that order leaves the queue; the predicate must then tell a paid-then-cancelled order from a released one.
- The handover's `422` names the order's amount due in its currency; the request accepts USD only, as checkout does.
- Until VS-030 replaces the `refund_present` stop-gap, a transition on a `refunded` order derives `in_progress` (strict-xfail in `tests/unit/ordering/test_status_inputs.py`); no order can be `refunded` before VS-030.
- A partial shipment is not announced: on a two-line order, the parcel with line A arrives without a "shipped" or "delivered" email until line B reaches the same step (SRS §16.1's order-level triggers; SRS §8.3 does not settle partial shipments).

## Alternatives rejected

- **A notice on every line's step** - a three-line order would send three "shipped" emails.
- **Letting the transition endpoint reach `delivered` on a cash order and recording the cash separately** - the line could be delivered with no payment, or paid twice; SRS §9.8.3 makes them one act.
- **Deriving the handover amount from the request** - BR-143 has the administrator type what they collected; the server compares, never trusts.
- **Joining `payments` in the queue query to hide unpaid online orders** - crosses a context boundary in SQL, and `orders.status` already distinguishes them.
