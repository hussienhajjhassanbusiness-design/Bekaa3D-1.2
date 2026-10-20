# ADR-034: Offer submission and expiry - a list-price ceiling, the kill switch on new offers, the cooldown read after the insert, and a lock-then-recheck expiry job

**Status:** Accepted
**Date:** 2026-10-20
**Source basis:** Owner decisions of 2026-10-20 on the VS-039 plan (Q1 to Q11); SRS §11, §20.6, §22.3, §23, BR-040, BR-080 to BR-092, SEC-11; FR-13; database-design.md §11; [ADR-019](ADR-019-manual-stl-delivery.md) d5; [ADR-022](ADR-022-storefront-commerce-capabilities.md)

## Context

VS-039 builds `POST /api/v1/offers`, the customer's and the administrator's offer reads, and the `expire_offers` job. The specification fixes the live-offer constraint, the floor, the cooldown and the turn-based deadline. It leaves open:

- the rate limit;
- whether an offer can exceed the list price;
- who is told about a new or expired offer, and how;
- the refusal codes for a physical, hidden or unavailable product;
- what "owned" means at submission;
- the admin queue order;
- the exact second an offer expires;
- whether the kill switch applies to offers.

It also has two races the specification does not spell out.

## Decision

1. **Refusals at submission, in this order:**
   1. the kill switch;
   2. the product (STL, listed, available);
   3. ownership;
   4. the amount (floor, then ceiling);
   5. the live-offer index;
   6. the cooldown.

   Every refusal writes nothing: no offer, round, audit row or notification.
2. **The kill switch blocks new offers** (owner decision on Q10). `accepting_orders = false` refuses `POST /offers` with `503 ORDERS_PAUSED`, the code checkout uses. It never blocks reading, expiring, countering, accepting, rejecting or withdrawing an existing offer. BR-040, INV-10 and the SRS glossary were updated to match.
3. **The amount.** All arithmetic is in integer cents.
   - **Floor:** the smallest whole-cent amount at or above `minimum_offer_percentage` of the current list price, rounded up. So 70 % of 999 gives 700, never 699.
   - **Ceiling:** the list price itself. At or above it the customer should just buy. Above it is `422 VALIDATION_ERROR` on `amount_cents`. A free STL therefore cannot be offered on.
4. **Refusal codes.**
   - A physical, unknown, hidden, deleted or unavailable product is `422 PRODUCT_NOT_PURCHASABLE`, with `reason` `not_negotiable`, `not_listed` or `unavailable`, the same shape as the cart. It is never stricter or looser than ADR-022's `can_offer`.
   - An owned STL is `409 PRODUCT_ALREADY_OWNED`. Owned means a paid, unrefunded line (ADR-019 d5).
   - An STL in an unpaid order does not block an offer. If that order is paid, VS-041's auto-close closes the offer.
5. **The cooldown is read after the insert.**
   - The race: a submission reads "no cooldown", then an administrator's rejection commits, then the insert succeeds, because the rejected offer no longer occupies `uq_offers_live`.
   - Under READ COMMITTED, while the old offer is still live, the insert either conflicts with it or waits for the rejecting transaction. It can only succeed once that rejection has committed. A cooldown check made after the insert therefore always sees the rejection, and its refusal rolls back the insert.
   - `tests/concurrency/test_offer_races.py` proves this by holding an uncommitted rejection open. The test fails if the check moves before the insert.
   - The latest `cooldown_until` wins. A cooldown that ends exactly now has ended.
6. **Expiry.**
   - An awaiting offer expires once `now >= responds_by`.
   - The job selects up to 200 candidate ids without a lock, soonest deadline first. Then, one short transaction per offer, it takes `FOR UPDATE SKIP LOCKED`, re-checks the offer, sets `expired` with `turn = NULL`, and appends a `system` / `expired` round, an audit row (no actor) and an in-app notification to the customer (`offer.expired`).
   - `responds_by` keeps the deadline that was missed.
   - Only the awaiting states are candidates, so an accepted offer never expires from inactivity (BR-087).
   - Overlapping runs, and a run racing a customer or administrator action (VS-040, which locks the same row), cannot expire one offer twice.
7. **Notifications, no email.** A new offer gives every active administrator one in-app `offer` notification (`offer.submitted`). SRS §16.1 lists no administrator email for offers; api-endpoints.md's "notification/email" yields to the SRS. Both notifications are written in the offer's own transaction.
8. **Reads.**
   - The customer's list is newest first by `(created_at, id)`.
   - The admin queue is ordered by `(rank, sort_at, id)`:

     | Rank | Status | Sorted by |
     |---|---|---|
     | 0 | `awaiting_admin` | `responds_by`, soonest first |
     | 1 | `awaiting_customer` | `responds_by`, soonest first |
     | 2 | `accepted` | `created_at`, oldest first |
     | 3 | every closed status | `created_at`, oldest first |

     It filters by `status`, `product_id`, `user_id` and `responds_before`, which matches pending offers only, because a closed offer keeps its old deadline. Each row names the customer's id and email; reading the queue is not audited, as with the VS-009 user list.
   - Both details carry every round.
   - `allowed_actions` is `[]` until VS-040 adds the actions. VS-040 then allows withdrawal from both awaiting states (BR-092 "pending offer"), where database-design.md §17.6 shows only `awaiting_customer`.
9. **Limits.**
   - Submission: 20 per user per hour (SEC-11), counted only for verified users.
   - Message: optional, trimmed, at most 1 000 characters after trimming; line breaks allowed, other control characters refused.
10. **NULL-safe CHECKs.** A CHECK that evaluates to NULL passes. So the status/turn check and the round-money check use `IS NOT DISTINCT FROM` and explicit `IS NOT NULL`. Without them, an awaiting offer with a NULL turn, or a round with an amount but no currency, was accepted.
11. **An order line's offer is its own.** `order_items (offer_id, user_id, product_id)` references `offers (id, user_id, product_id)`, and `ck_order_items_offer_is_stl` allows an `offer_id` only on an STL line. So VS-041 cannot price one customer's line from another customer's offer, or from an offer on another product. `ck_offers_accepted_shape` also covers `paid` and `checkout_expired`, which are reached only from `accepted`, so they keep the agreed price, `accepted_at` and the checkout deadline.

## Consequences

- VS-040's counter, accept, reject and withdraw lock the offer row, the same row the job locks, so expiry and a last-second answer serialise. VS-040 must check `now < responds_by` under that lock, so its `410 OFFER_EXPIRED` agrees with decision 6.
- VS-040's reject sets `rejected_at` and `cooldown_until` in the same statement as the status (`ck_offers_rejected_shape`), which is what decision 5 relies on.
- VS-041 reads the agreed price only from `agreed_amount_cents`. The ceiling here means no accepted offer can exceed the list price at submission time. A later counter is VS-040's to bound.
- The kill switch now also hides a path to new revenue. That is the intent: a paused shop takes on no new commitments.
- **Known race, for VS-041.** A submission can read "not owned" while a payment for the same STL commits. VS-041's auto-close, running in that payment, cannot see the uncommitted offer, so a live offer can survive on an owned STL. No double charge is possible: `uq_order_items_stl_ownership` refuses a second live line. VS-041's offer checkout must refuse an owned product and auto-close the offer then, or serialise the two with a shared advisory lock on (user, product).
- **Open for VS-040.** The offer does not snapshot the list price. If the administrator lowers the price below `current_amount_cents` before accepting, the customer would pay above the list price. VS-040 must decide whether accept and counter re-check the current price.
