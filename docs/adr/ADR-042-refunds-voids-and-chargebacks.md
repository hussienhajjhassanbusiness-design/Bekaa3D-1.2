# ADR-042: Refunds, voids and chargebacks - an owed refund is checked first, a voided status closes an obligation unpaid, chargebacks are their own record that absorbs open refunds (VS-030)

**Status:** Proposed. PR A (schema, migration `c01e53ab3e0f`) is built on it. PR B and PR C complete it and set it to Accepted.
**Date:** 2026-10-23
**Source basis:** [VS-030 plan](../plans/VS-030-refunds-settlement-plan.md) (Revisions 1 and 2, owner answers Q1-Q12); [VS-030 slice](../vertical-slice-plan.md#vs-030--refunds-and-settlement) and its six "Must resolve before build" items; SRS §9.5-9.7, §20.1-20.2; database-design.md §9.3-9.6; [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d9, d11, d12, d15, d16 and its appendix; [ADR-036](ADR-036-payment-recovery.md) d7, d12, d16; [ADR-038](ADR-038-physical-checkout-and-cash-eligibility.md) d13; VS-041 audit Q-1 and Q-2.
**Amends:** SRS §20.2 and database-design §17.2 (the order-status order); ADR-024 d16 and SRS §9.7 (a chargeback is not a refund kind).
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

## Consequences

- PR B rewrites the `derive_order_status` tests for cases A and B (VS-023's note asked for this ADR), and replaces the `refund_present` stop-gap.
- SRS §9.7, §20.1 (the payment back edges) and §20.2, database-design §17.2, api-endpoints §19 and the entities documents are aligned in PR C.
- VS-032 depends on VS-031 (a chargeback test cancels a line), and only wires provider disputes into `record_chargeback`.
