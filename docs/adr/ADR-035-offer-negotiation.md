# ADR-035: Offer negotiation - the agreed price capped at today's list price, a floor on customer counters, a stored reminder time, and one error order

**Status:** Accepted
**Date:** 2026-10-20; amended 2026-10-20 (decision 9, VS-040 follow-up)
**Source basis:** Owner decisions of 2026-10-20 on the VS-040 plan (the open item of [ADR-034](ADR-034-offer-submission-and-expiry.md), and Q1 to Q8); SRS §11, §16.1, §20.6; BR-040, BR-082 to BR-092; FR-13; api-endpoints.md §13, §21, §29.7; database-design.md §11, §17.6

## Context

VS-040 adds counter, accept and withdraw for the customer, and counter, accept and reject for the administrator. `expire_offers` also closes accepted offers whose checkout window has passed. ADR-034 left one question open: the offer does not snapshot the list price, so a price lowered mid-negotiation could leave the customer agreeing to pay more than the shop now asks. The specification also leaves these open:

- whether counters are bounded;
- how the "expiring soon" email is sent exactly once;
- what is rechecked when an offer is answered;
- who is told about each event;
- which refusal wins when several apply.

## Decision

1. **The agreed price never exceeds today's list price** (owner decision).
   - On accept by either party, `agreed_amount_cents = min(current_amount_cents, current list price)`.
   - The `accepted` round records the agreed amount. `current_amount_cents` keeps the last proposal.
   - A counter above the current list price is `422 VALIDATION_ERROR` on `amount_cents`, for either party, the same as submission. A counter is refused rather than silently lowered, because the person typed that number.
   - "Today's" price is the committed price the answer reads. A price edit that commits after that read is a later change, which SRS §11.3 says the agreed price ignores. So the product row is not locked.
   - `ck_offers_agreed_within_current` (`agreed_amount_cents <= current_amount_cents`) makes the database refuse any later write that raises the agreed price. `current_amount_cents` never changes after acceptance.
2. **The floor applies to customer counters.** BR-090 names submission. Without a floor on counters, a customer could submit at 70 % and then counter at 1 %.
   - A customer counter below `minimum_offer_percentage` of the current list price is `422 OFFER_BELOW_MINIMUM`.
   - Administrator counters have no floor: the shop may discount as it likes.
3. **The reminder time is stored** (`offers.remind_at`, migration `8d2f6a1c3e57`).
   - An administrator counter sets it to 75 % of the way through the customer's turn: `responds_by - window / 4`.
   - `expire_offers` locks each due offer with `SKIP LOCKED` and clears the field. While the turn is still open, it also queues the `offer_expiring_soon` email and an in-app notification. Clearing the field is the receipt, so a rerun, or two runs at once, send once.
   - A reminder found past the deadline is dropped unsent; the expiry pass takes over.
   - `ck_offers_remind_at_awaiting_customer` allows the field only on the customer's turn, because SRS §16.1 reminds only the customer.
   - Every transition out of that turn clears it.
4. **What an answer rechecks.**
   - Accept rechecks ownership. An STL bought meanwhile gives `409 PRODUCT_ALREADY_OWNED` and nothing is written; closing the offer is VS-041's auto-close (BR-088).
   - Counter and accept recheck the product. If it is unlisted, unavailable or priced at 0, the answer is `422 PRODUCT_NOT_PURCHASABLE` with the usual `reason`.
   - Reject and withdraw always work, so the customer is never stuck with an offer on a hidden product.
   - The kill switch blocks none of them (BR-040).
5. **One error order, under the row lock.** Every action locks the offer `FOR UPDATE`, the row `expire_offers` locks with `SKIP LOCKED`, and then checks in this order:
   1. `404`: unknown, or another customer's;
   2. `410 OFFER_EXPIRED`: the status is `expired`, or the offer is awaiting and `now >= responds_by`. So an answer at the deadline gets 410 whether or not the job has run;
   3. `409 INVALID_STATE_TRANSITION`, with `offer_status`: any other closed or accepted offer;
   4. `409 OFFER_NOT_YOUR_TURN`.

   Withdrawal ignores the turn (ADR-034 d8). A refused action writes nothing. `offer_status` is named so because RFC 9457's `status` is the HTTP status.

   The time used for every check and timestamp is read **after** the lock is taken (an injected clock). An answer that waited on the lock past the deadline is therefore `410`, not a late success.
6. **The timer is void once accepted.**
   - Accept sets `responds_by = NULL` (BR-087) and `checkout_expires_at = now + offer_checkout_window`.
   - `expire_offers` moves an accepted offer to `checkout_expired` once `now >= checkout_expires_at`, appending a `system` round, an audit row and an in-app `offer.checkout_expired`. It sends no email, because §16.1 lists none.
   - The agreed price and the deadline stay on the row.
   - Each offer runs in its own transaction. A failing one is rolled back, logged and skipped, so one bad row cannot stall the other passes. A lost database connection still fails the run.
7. **Who is told.**
   - The customer gets an email and an in-app notification on an administrator's counter, on any accept (the email carries the checkout deadline), on a rejection (with `cooldown_until`) and on the reminder.
   - Administrators get only in-app notifications for a customer counter, accept or withdrawal (§16.1 lists no administrator email).
   - All of them are written in the action's transaction.
8. **Limits and bodies.**
   - Customer actions share a bucket of 60 per user per hour, separate from submission's 20 (SEC-11). Administrator actions need CSRF and sit behind the admin boundary.
   - Reject and withdraw take an optional `reason`, and a counter an optional `message`. Each is kept as the round's message under the 1 000-character rule.
   - `allowed_actions` lists what the viewer may do now.
9. **Accept names the amount it accepts** (owner decision, VS-040 follow-up).
   - Both accept routes require `{"expected_amount_cents": …}`: the `current_amount` the caller's page showed. A missing or malformed value is `422 VALIDATION_ERROR`.
   - If it is not the offer's `current_amount_cents`, the answer is `409 OFFER_AMOUNT_CHANGED` with `current_amount`, and nothing is written. Without it, an administrator accepting from a stale page after the customer countered lower would bind the shop to the lower amount, and a customer's stale tab could do the same to them.
   - It is compared with the amount on the table, not the capped agreed amount of decision 1, so a price cut never makes a correct page look stale.
   - It is checked under the row lock, after the refusals of decision 5 and before the product and ownership rechecks of decision 4.
   - Withdraw-and-resubmit stays as it is: a resubmission is a new offer with a new id, so a page showing the old one gets `409 INVALID_STATE_TRANSITION`.

## Consequences

- VS-041 reads only `agreed_amount_cents`, which is now never above the list price at the moment of acceptance. A later price change is ignored (SRS §11.3).
- **For VS-041:**
  - `expire_offers` will expire an accepted offer whose payment is in flight. VS-041 must exempt an offer with a live payment from the checkout-expiry pass, as its slice says ("a payment already in flight completes").
  - VS-041 also owns the auto-close that decision 4's ownership refusal leaves to it.
  - The `accepting_orders` kill switch blocks offer checkout like any new checkout (`503 ORDERS_PAUSED`). Decision 4 keeps answers open while paused, so an offer may be accepted then and its checkout refused until the shop reopens. Whether the checkout window should stretch over a pause is VS-041's question, not decided here.
- **SRS conflict, resolved.** SRS §20.6 and database-design.md §17.6 drew `accepted` only from `awaiting_admin`, while FR-13, F-092 and api-endpoints.md §13 let the customer accept on their own turn. Both diagrams now carry the `awaiting_customer → accepted` arrow.
- The customer's turn has a reminder and the administrator's does not. If the shop later wants admin reminders, that needs a second column or a wider CHECK, not a reinterpretation of this one.
- Each two-party integration test opens one test client at a time. A client's lifespan rebinds the app's engine to its own event loop, so two clients used alternately mix loops and hang.
