# ADR-033: Customer order read model - fixed schemas, `in_production` masked, flags from Payments, one payment shown

**Status:** Accepted
**Date:** 2026-10-19
**Source basis:** Owner decisions of 2026-10-19 on the VS-025 plan (Q1 to Q9); SRS §8.9, §20.2, BR-033, F-026, F-027; FR-08, FR-09; [ADR-019](ADR-019-manual-stl-delivery.md); [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) decision 8; [ADR-025](ADR-025-frontend-contract-decisions.md)

## Context

VS-025 gives customers `GET /api/v1/me/orders` and `GET /api/v1/me/orders/{order_id}`. The specification names the flags and sections of `OrderDetail` but leaves open:

- exactly when `payment_due` is true;
- where "a payment that reached paid" comes from, since Ordering does not own payments;
- which payment a customer sees when an order has several attempts;
- what a customer-visible history row carries;
- what the line's delivery timestamp is called.

## Decision

1. **Fixed customer schemas.** The repository selects named columns and never reads `admin_note`, `contact_phone_hash`, `customer_email_snapshot` or `delivered_by`. The response models have no field for them, for a provider reference or for provider metadata. Ownership is an `orders.user_id = :caller` term in every query (lines and history join `orders`), so another customer's order is the same 404 as an unknown id.
2. **`in_production` is internal** (ADR-024 d8). A line in it reads `pending`. A history row *into* it is dropped. The next row *out of* it, for the same line, reads as from the state before it: `pending` normally, `returned` on a reprint (FR-08). A row that masking turns into a no-op (`pending -> pending`) is dropped too. `can_cancel` is computed on the **unmasked** states, so a line being printed still blocks self-cancel.
3. **History rows carry `{order_item_id, from_status, to_status, at}` only.** No actor and no `reason`, because a reason can be text an administrator wrote.
4. **Flags.**
   - `payment_due` = cash, no payment has reached paid, and status `in_progress`. A refused or cancelled cash order is not due.
   - `can_cancel` follows SRS §8.9, with "reached paid" (`paid`, `partially_refunded`, `refunded`) read from Payments, not inferred from the order status.
   - **Owner decision 2026-10-19:** only *live* physical lines count, live meaning not cancelled (as in SRS §9.8 step 3). A line an administrator already cancelled neither blocks self-cancel nor counts as the physical line it needs. A refunded physical line still counts, because only a finished line is refunded in full. This amends the literal "every physical line" of SRS §8.9, BR-066 and ADR-024 d8; the SRS text was updated to match.
   - **Owner decision 2026-10-19:** unpaid cash orders get `amount_due_cents`, the sum of live line totals (BR-055), built in VS-028.
5. **Payments through a port.** Ordering declares `OrderPaymentReader`; Payments implements it (`app.payments.public.order_payment_reader`) as one batched query per page. For each order it answers `reached_paid`, and the attempt shown: the live or paid one (at most one, `uq_payments_one_live`), else the newest by `(initiated_at, id)`. Only its status, provider and amount are returned. Late-capture data is not shown.
6. **The line's timestamp is `fulfilled_at`**, the column's own name, for every line type.
7. **Deferred.** The refund summary arrives with VS-030, when `refunds` exists. `can_retry_payment` and `hold_expires_at` arrive with VS-024's functions; whichever of VS-024 and VS-025 merges second wires them in.

## Consequences

- An administrator field added to `orders` later cannot leak by accident: it would have to be added to the repository's column list and to a response model.
- VS-029, which first moves physical lines, inherits the masking without change.
- The flags are advisory: the detail is several READ COMMITTED reads, not one snapshot. VS-031's self-cancel must re-check the same `can_cancel` predicate under the ADR-024 d9 locks, and must use exactly this predicate, or the flag lies.
- `total` is the order total at checkout. On a cash order with a cancelled line, the amount due at handover is the sum of the live lines, not `total`; VS-028's `amount_due` says so explicitly.
- A late-captured attempt reads as `failed`. Whether its `late_capture` refund appears in the customer's refund summary is VS-030's decision.
- `status_history` shows line rows and order rows together, oldest first. The frontend tells them apart by `order_item_id`.
- `fulfillment_status` in the OpenAPI enum still lists `in_production`, because the shared enum type is used. The contract doc says it never appears.
