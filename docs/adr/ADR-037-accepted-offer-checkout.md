# ADR-037: Accepted-offer checkout - the agreed price, the order inserted before the offer is locked, paid and auto-close inside the payment, and no stretch over a pause

**Status:** Accepted
**Date:** 2026-10-20
**Source basis:** Owner decisions of 2026-10-20 on the VS-041 plan (Q1 to Q13, and the pause question ADR-035 left open); SRS §5.4, §11.3, §11.4, §20.6, §20.8; BR-085 to BR-089; F-094, F-095, F-098; FR-13; api-endpoints.md §13, §29.5; database-design.md §8.4, §17.6; [ADR-032](ADR-032-checkout-idempotency-and-payment-verification.md), [ADR-034](ADR-034-offer-submission-and-expiry.md), [ADR-035](ADR-035-offer-negotiation.md), [ADR-036](ADR-036-payment-recovery.md)

## Context

VS-041 lets a customer pay for an accepted offer once, at the agreed price. It must also close any live offer once the STL is bought another way (BR-088). Earlier slices left it these problems:

- **Payment in flight (ADR-035).** `expire_offers` would expire an accepted offer whose payment is still in flight.
- **Known race (ADR-034).** A submission can commit beside a payment and leave a live offer on an owned STL.
- **Retry (VS-024).** Retry would let an offer order take a new attempt after its window has closed.
- **Pause.** Nothing yet says whether the checkout window stretches over an `accepting_orders` pause.

## Decision

1. **The route.** `POST /api/v1/me/offers/{offer_id}/checkout` belongs to Ordering, which owns orders and checkout.
   - It reads the offer through Ordering's `OfferCheckouts` port, implemented by `app.negotiation.public.SqlOfferCheckouts`.
   - It reuses cart checkout's two transactions around the provider call (ADR-032 d7), its replay rules and its 30-per-hour bucket.
   - The idempotency scope is `offer_checkout:{offer_id}`.
   - The body is `{accept_terms: true, accept_digital_final_sale: true, payment_provider?}`. It names no amount.
   - The order has `source = offer`. Its one STL line carries `offer_id`, and `unit_price_cents` and the total are the offer's `agreed_amount_cents`. The list price is never read, so a later price change is ignored (SRS §11.3).
2. **Refusal order** (owner, Q8). Each refusal writes nothing:
   1. body `422`;
   2. `404` for an unknown offer or another customer's;
   3. `410 OFFER_CHECKOUT_EXPIRED`, if the offer is `checkout_expired`, or accepted with `now >= checkout_expires_at`;
   4. `409 INVALID_STATE_TRANSITION` with `offer_status`;
   5. `503 ORDERS_PAUSED`;
   6. `503 ONLINE_PAYMENT_UNAVAILABLE`;
   7. `422 PRODUCT_NOT_PURCHASABLE`, if the product is hidden or unavailable (as accept refuses, ADR-035 d4);
   8. `409 PAYMENT_ALREADY_ACTIVE`, if the offer's unpaid order has a live attempt;
   9. `409 PRODUCT_ALREADY_OWNED`, from `uq_order_items_stl_ownership`, if the order exists but has no live attempt (the customer retries that order instead);
   10. `422 PAYMENT_METHOD_NOT_ALLOWED`.

   The offer's own state comes before the pause, so a lapsed offer says so rather than "paused".
3. **The order first, then the offer lock** (owner, Q4).
   - Checkout reads the offer without a lock for the refusals above. It then inserts the order, the line and the attempt, locks the offer `FOR UPDATE`, and checks it again with a clock read after the lock.
   - The locked offer must equal the one that was priced; otherwise the transaction fails and nothing is charged. This holds today because an accepted offer never changes (BR-085), and the check keeps it holding if that ever changes.
   - Locking the offer first could deadlock against a cart payment of the same STL. That payment holds the line it moved and wants the offer, while checkout's line INSERT would wait on that line.
   - The line's composite foreign key to `offers` takes `FOR KEY SHARE` on the offer. So `expire_offers` (`SKIP LOCKED`) passes over an offer whose checkout has inserted its line.
4. **At most once, in the database** (owner, Q1). Migration `d5507ee63176` adds `uq_order_items_offer_once`, a unique index on `order_items (offer_id) WHERE offer_id IS NOT NULL AND fulfillment_status <> 'cancelled'`.
   - An offer pays for one line, ever. Only a line cancelled unpaid by the hold release frees it.
   - A refunded line leaves the ownership index, but not this one.
5. **Paid and auto-close, in the payment's transaction** (BR-088, SRS 5.4 step 6).
   - When verification moves STL lines to `awaiting_delivery`, `settle_offers_on_stl_purchase` runs in the same transaction. Every payment path goes through it: webhook, reconciliation and manual confirm.
   - For each product it takes a transaction-scoped advisory lock on (user, product), then locks that product's live offers `FOR UPDATE`. The offer the line was bought through becomes `paid`, with a `system`/`paid` round carrying the agreed amount. Any other live offer becomes `auto_closed`.
   - Auto-close covers all three live statuses (owner, Q2), as BR-088 and SRS §11.4 say. The §20.6 and database-design §17.6 diagrams were amended to match.
   - Each change writes an audit row with no actor. There is no notification (owner, Q11): the payment's receipt already tells the customer.
   - An offer that is not `accepted` when its own line is paid gets an `offer.paid_out_of_state` audit row and an error log, and is never raised. Money already captured is never refused because of an offer's state.
6. **The (user, product) advisory lock** (owner, Q3). Submission takes it before its ownership read, and a payment's auto-close takes it before its live-offer read.
   - Whichever comes second sees the first one's commit: the submission sees the ownership, or the auto-close sees the new offer.
   - This closes ADR-034's known race, so a live offer never outlives ownership.
   - **SRS §20.8's lock order is extended:** `orders` → lines by id → `payments` → (user, product) advisory lock → `offers` by id.
7. **A payment in flight completes** (owner, Q6). `expire_offers`' checkout pass locks the offer, then skips it if an uncancelled order holding its line has a `pending` or `processing` attempt.
   - The job reads the committed attempt. A payment being applied has the attempt locked but not yet committed, so the job still sees it as live, and that payment then marks the offer `paid`.
   - Once the attempt ends unpaid, the next run expires the offer.
   - The pass reads its candidates keyset-paged by `(checkout_expires_at, id)`. It keeps reading pages until it has closed `limit` offers or reaches a short page, so a full page of skipped offers can never stall the offers behind it.
8. **Retry follows the window** (owner, Q5). VS-024's retry of an offer order locks the offer after the `orders` row (the same order a payment takes them in). If the offer is not `accepted`, or its window has closed, retry refuses with `409 INVALID_STATE_TRANSITION` and `reason: offer_checkout_expired`.
   - A live attempt is checked first and answers `409 PAYMENT_ALREADY_ACTIVE` with its `redirect_url`. An attempt in flight past the window is honoured (decision 7), so the customer is sent back to finish it rather than told the checkout expired.
9. **No stretch over a pause** (owner). The window keeps running while `accepting_orders` is off. An offer that lapses then becomes `checkout_expired` through the job, as at any other time. The customer may submit a new offer at once: the cooldown follows a rejection only (BR-089), and `checkout_expired` is not one.
10. **OrderDetail's owed fields** (owner, Q12; ADR-033 d7).
    - `hold_expires_at` is set only on an unpaid online order. It is the later of placement and the latest attempt, plus `checkout_hold_period` (VS-024 D4), and matches the admin payment detail.
    - `can_retry_payment` is VS-024's T1 rule without the lock. It is also false while an attempt is live, and false on an offer order whose offer has closed. The POST still re-checks under its locks.

## Consequences

- An offer can charge at most once, at the agreed price. A live offer never outlives ownership, and a payment that was in flight when the window closed is honoured.
- Every payment that pays an STL now also takes the advisory lock and the offer row. Test `test_payment_lock_order.py` asserts the extended order. VS-030's refund and VS-031's cancellation take neither, because they never create ownership.
- Two submissions for the same (user, product) now queue on the advisory lock. `uq_offers_live` still refuses the second one, because no application check comes before the insert.
- `OrderLine` and `CustomerOrderLine` carry `offer_id`. `payment_recovery`'s rules take read-only protocols, so `CustomerOrder` qualifies alongside `Order`.

## Alternatives rejected

- **Lock the offer before inserting the order.** It deadlocks against a cart payment of the same STL (decision 3).
- **Close offers from an outbox job after payment.** A live offer would outlive ownership for a while, and `paid` would lag the payment.
- **Stretch the window over a pause.** The owner chose a fixed window. A pause long enough to matter can be met by re-accepting the customer's new offer.
- **Let retry ignore the offer.** An expired checkout could be paid up to one hold period late (FR-13: "An expired checkout cannot be paid").
