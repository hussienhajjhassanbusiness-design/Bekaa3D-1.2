# ADR-042: Refunds, voids and chargebacks - an owed refund is checked first, a voided status closes an obligation unpaid, chargebacks are their own record that absorbs open refunds (VS-030)

**Status:** Accepted (2026-10-24, VS-030 PR C). PR A (schema, migration `c01e53ab3e0f`), PR B (refund core) and PR C (late capture, backfill `80e56abf0969`, chargebacks, record-capture) are built on it.
**Date:** 2026-10-23
**Source basis:** [VS-030 plan](../plans/VS-030-refunds-settlement-plan.md) (Revisions 1 and 2, owner answers Q1-Q12); [VS-030 slice](../vertical-slice-plan.md#vs-030--refunds-and-settlement) and its six "Must resolve before build" items; SRS §9.5-9.7, §20.1-20.2; database-design.md §9.3-9.6; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d9, d11, d12, d15, d16 and its appendix; [ADR-036](ADR-036-payment-recovery.md) d7, d12, d16; [ADR-038](ADR-038-physical-checkout-and-cash-eligibility.md) d13; VS-041 audit Q-1 and Q-2.
**Amends:** SRS §20.1 (the payment's back edges), §20.2 and database-design §17.2 (the order-status order); ADR-024 d12 (settle is recorded after paying, in the dashboard); ADR-024 d16 and SRS §9.7 (a chargeback is not a refund kind, and absorbs open refunds); ADR-036 d7 (a mismatched capture can be recorded, d21 below).
**Applies first to:** migration `c01e53ab3e0f` (VS-030 PR A).

## Context

The final PR #8 review left six open items in VS-030:
- **Status after a failed refund.** A failed full refund reads `refunded` while money is still owed.
- **Pending and owed refunds after a chargeback.** They stay payable, so payout can exceed what was paid.
- **A chargeback after a full refund.** It cannot be recorded under `amount_cents > 0`.
- **A fully charged-back unfinished line.** It can still be shipped.
- **Chargeback recording.** It has no endpoint and no idempotency.
- **The open-cash count.** It depends on the order status.

The VS-041 audit added two more:
- **Q-1:** `order_items.user_id` is not tied to its order's customer in the database.
- **Q-2:** an order total is not tied to its lines.

## Decision

1. **The order status checks an owed refund first** (amends SRS §20.2). Once a payment reached paid, the checks run in this order:
   1. an owed refund (failed, not reissued) → `partially_refunded`;
   2. every line cancelled → `cancelled`;
   3. refunds cover the paid money → `refunded`;
   4. any refund → `partially_refunded`;
   5. every line terminal → `completed`;
   6. otherwise → `in_progress`.

   "All lines refunded" is dropped: it is unreachable unless refunds already cover the paid money. Over every input combination, only two outputs change, both intended (PR #8 cases A and B, plan §3.1a):
   - every line cancelled with a refund owed;
   - every line refunded with a refund owed.

   Both read `partially_refunded`. The owner confirmed this, working alone (plan Revision 2).
2. **`voided` is a terminal refund status.** It closes a pending or owed obligation without paying it: a mistake, or one absorbed by a chargeback. A settled refund is never voided (`ck_refunds_void_never_settled`). A voided refund is never reissued (`ck_refunds_reissued_failed`). Voiding is admin-only, needs a reason, and is audited.
3. **Chargebacks are their own tables** (`chargebacks`, `chargeback_items`), not `refunds.kind = chargeback`.
   - `charged_cents = applied_cents + excess_cents`, with `applied_cents >= 0`, so a chargeback after a full refund records its whole amount as excess.
   - Online only (`ck_chargebacks_online_only`, plus a FK naming the payment's real provider).
   - One record per provider dispute reference (`uq_chargebacks_dispute`).
   - `refund_kind` is `admin`, `cancellation` and `late_capture`.
4. **Recording a chargeback voids every pending and owed refund on its payment**, in the same transaction, so total payout never exceeds the money paid.
   - It cancels, in that transaction, an unfinished physical line whose balance reaches 0.
   - It is recorded through `POST /api/v1/admin/orders/{id}/chargebacks` with a required `Idempotency-Key` (PR C).
   - Production stays on `PAYMENT_PROVIDER=none` until VS-032.
5. **The open-cash count stays status-based** (owner answer Q12). The plan (§3.1) proves that an unpaid, uncancelled cash order always derives `in_progress`, and that a paid one never does. Tests pin both proofs.
6. **Integrity in the database** (VS-041 Q-1):
   - `fk_order_items_order_owner (order_id, user_id) → orders (id, user_id)`, added `NOT VALID` and then validated, after a precheck that refuses mismatched data;
   - composite FKs so that a refund's or chargeback's payment is the order's own, and an item names a line of its parent's own order.

   Q-2 (the total equals its lines) is asserted inside each refund transaction, not by a trigger.
7. **A late-capture refund may carry the currency the provider reported**, never converted (owner answer Q6). Every other refund is USD.

### Decided in PR B (refund core, branch `vs-030-refund-core`)

8. **One lock order for every refund path:** the idempotency claim, then `orders`, every line by id, the order's payments by id, then the refund (`FOR UPDATE` or INSERT). Rank 5 (`chargebacks`) is reserved for PR C; the cart and phone lock come last (VS-031). LO1 checks it statically and LO2 at runtime.
9. **Refund facts are read only under the order's row lock.** The reader refuses a transaction that does not hold that order's lock (`OrderLockRequiredError`, a check on the row's `xmax`/`xmin`). Every refund writer takes the lock first (U12), so the rows cannot change under a reader.
10. **Two guards back the state machine.** The use case decides on the locked row (`refund_step`), and each UPDATE matches only a row still in a legal source state. The CHECKs added in PR A are the last backstop.
11. **Create and reissue run in one transaction with their `Idempotency-Key` claim.** Any 4xx rolls the claim back, so the same key may be retried. Only the 201 is stored and replayed. Scopes: `admin_refund_create` and `admin_refund_reissue`, per administrator.
12. **A Q-2 mismatch (owner answer Q11)** answers 409 `ORDER_TOTAL_MISMATCH` and writes nothing. It logs `refund_integrity_error` and raises a `refund_integrity` payment alert in its own transaction, repeated at most daily per payment. Unpaid orders are refused first (409 `ORDER_NOT_PAID`).
13. **Settle changes no order or payment status.** Create, fail, reissue and void recompute both. The payment may move back (`refunded → partially_refunded → paid`).
14. **Display reads are unlocked and never decide money.** The customer's `OrderDetail.refunds` shows admin, cancellation and late-capture refunds as `processing` or `refunded`, hiding voided ones and a reissued failure (Q9). `AdminOrderDetail` gains `refunds` and `refund_balance`.
15. **The cash-block phone search is audited** as `cash_block.searched`, with its filters, result count and block ids only: never the phone or its hash (Q8).

### Decided in PR C (branch `vs-030-pr-c`; owner answers C1-C4, plan Revision 3)

16. **A chargeback absorbs the payment's open refunds (C1).** It voids every pending and owed refund on its payment (d4), and their items become its first items, so no line's coverage drops and no `refunded` or `cancelled` line reopens. If the bank charged less than those refunds, absorption runs in (refund id, line id) order and the unabsorbed part becomes one new pending refund per voided refund, of the same kind (`remainder after chargeback <id>`). The administrator's items add coverage on top, within each line's balance, and must total exactly the charge left after absorption or, if that is larger, everything still refundable on the payment (422 `CHARGEBACK_ALLOCATION_INVALID` otherwise; revised after the PR C review, owner 2026-10-24). Excess is the rest, so it exists only once the payment's balance is 0 and can never be refunded again: payout (refunds still owed or paid plus what chargebacks applied) never exceeds the money paid, and the bank's excess is never paid twice.
17. **D4 as built.** A line the administrator's items bring to 0 becomes `refunded` if it is delivered, picked up, returned or an STL line, or `cancelled` (no refund, no `cancel_reason`, history reason `chargeback`) if it is an unfinished physical line. `shipped` is cancelled and `returned` refunded here, so VS-031 needs no `returned → refunded` override.
18. **A late-captured attempt's chargeback** names no items, absorbs its open `late_capture` refund the same way (with a remainder when partial) and moves no status. One whose open refund is not in USD is not compared: nothing is absorbed and the whole charge is excess (C4). Q-2 runs only where balances are derived, so not here.
19. **Late-capture refunds** are created in VS-024's Tx B by `SqlLateCaptureRefunds` (`INSERT ... ON CONFLICT DO NOTHING` on `uq_refunds_one_live_late_capture`, then the alert). Their settle, fail, reissue and void lock the order, its lines and its payments with no paid payment required, skip Q-2 and recompute nothing; settling one sends the "refund issued" notice (Q7). The payment row stores only what `ck_payments_captured_shape` holds (no currency without an amount, an unreadable one unknown, an amount above 10^12 unknown), so a malformed provider report never rolls back the late capture. With no reported amount the obligation is the attempt's amount in the attempt's currency; the refund flags such a guess in its reason. The refund is inserted before the alert, whose advisory lock comes last.
20. **The backfill** (`80e56abf0969`) creates the obligation for every older late capture, from the stored capture, else the oldest `payment.late_capture` audit row, else the attempt's amount (flagged). A malformed audit row skips the payment, listed in a `refund.backfill_skipped` audit row; an audit row that records "no amount" follows Q6 like the live sink. A payment that already has any `late_capture` refund, whatever its status, gets none, so a rerun never adds a second obligation beside a failed or voided one. Its downgrade deletes only its still-pending rows.
21. **Record-capture** (`POST /admin/payments/{id}/record-capture`, Q5) records a dashboard capture whose amount or currency differs from an attempt that never reached paid, on a provider with no status API, through `apply_result` as a late capture. A matching amount is refused (`use_confirm`).
22. **One alert per chargeback** (`chargeback`, or `chargeback_excess` with excess), never folded into an earlier one (a zero window skips the dedupe lookup); the dispute reference stays on the chargeback record and out of audit rows and logs. Every refund a chargeback voids or creates gets its own `refund.voided` or `refund.created` audit row.
23. **PR B review fixes.** A void is refused when one of its lines is `cancelled` as well as `refunded` (the 0-balance rule would strand the money); a line named twice in one request is refused; Q-2 also compares the payment's currency to the order's; settle skips Q-2 (C3); the order-status facts count only the paid payment's refunds and chargebacks.

## Consequences

- PR B rewrites the `derive_order_status` tests for cases A and B (VS-023's note asked for this ADR), and replaces the `refund_present` stop-gap.
- SRS §9.6, §9.7, §10.4, BR-064, §20.1, §20.2 and §21.3, FR-10, database-design §9.3, §9.5, §17.1 and §17.2, api-endpoints §19 and §29.13, the entities documents and the glossary were aligned in PR C. The as-built reference is [`docs/refunds.md`](../refunds.md).
- Under d16 the administrator must name the chargeback's items knowing the open refunds it absorbs; the 422 returns `chargeable_cents`, the total they must make. A refund racing a chargeback makes whichever commits second refuse (plan R13).
- VS-032 depends on VS-031 (a chargeback test cancels a line), and only wires provider disputes into `record_chargeback`.
