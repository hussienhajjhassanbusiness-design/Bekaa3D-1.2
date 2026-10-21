# ADR-039: STL delivery workflow - Fulfillment owns the use case, Ordering keeps every `order_items` write, one transaction writes the delivery and its notices, the queue is keyset-paged by placement time (VS-023b)

**Status:** Accepted
**Date:** 2026-10-21
**Source basis:** Owner decisions of 2026-10-21 on the [VS-023b plan](../plans/VS-023b-stl-delivery-queue-plan.md) (Q1-Q10); SRS §10.2-§10.4, §20.1; [ADR-019](ADR-019-manual-stl-delivery.md); [ADR-024](ADR-024-cash-on-delivery-and-courier-priced-shipping.md) d9; [ADR-032](ADR-032-checkout-idempotency-and-payment-verification.md) d6, d19
**Applies first to:** `GET /api/v1/admin/stl-deliveries`; `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition`; migration `7a1c3e9b5d24`.

## Context

ADR-019 d4 has the administrator mark an STL line delivered from a queue, and d8 puts STL line delivery state in Fulfillment. ADR-032 d6 said Fulfillment owns nothing yet, and d19 keeps a lines lock "for VS-023b". The writers of `order_items` are listed in one test (`tests/unit/ordering/test_order_item_writers.py`) so that each is checked to take the orders lock first.

## Decision

1. **Fulfillment owns the use case, the routes and the notices; Ordering keeps every `order_items` write.** `fulfillment` calls `ordering.public` (`lock_order_for_change`, `mark_stl_line_delivered`, `stl_delivery_page`). The new writer `set_line_delivered` joins the writers allow-list, and `fulfilled_at`/`delivered_by` are written nowhere else.
2. **Lock order is the ADR-024 d9 order:** `orders` `FOR UPDATE`, then every line of the order `FOR UPDATE` by id. The line's state is decided from the rows read under those locks, so a racing refund or a second administrator is seen, never overwritten.
3. **One transaction, nothing external in it.** The line update, history row, recomputed order status, audit row, in-app notification and the email's outbox row commit together. `dispatch_outbox` sends the email later.
4. **A refusal is `409 INVALID_STATE_TRANSITION` with a stable `reason`:** `already_delivered` (with `fulfilled_at`), `line_closed` (`refunded` or `cancelled`), `not_awaiting_delivery`, `not_an_stl_line`. An unknown order, an unknown item and an item of another order are the same `404`.
5. **The queue is ordered by `(order_items.created_at, id)` with an opaque keyset cursor.** `created_at` is the placement time: no paid timestamp exists on a line or an order (`verified_at` is on `payments`), so payment time is not used. The query pages the lines first and joins `orders` after, so the partial index `ix_order_items_stl_awaiting` orders and limits.
6. **A fully refunded line leaves the queue because its status is `refunded`**; the queue filters on `awaiting_delivery` only (ADR-019 d7).
7. **Stop-gap for VS-030:** `status_inputs_for` sets `refund_present` when the order is already `partially_refunded`, so delivering a line never turns that status into `completed`. VS-030 must replace it with the real refund query.
8. **The legal line edges are a pure table** (`ordering/domain/line_transitions.py`). VS-029 adds the physical edges and builds `available_actions` from it.
9. **The transition response is provisional** (`OrderItemTransitionRead`); VS-029 replaces it with `AdminOrderDetail`.
10. **`daily_download_cap` is deleted** (ADR-019): registry entry and seeded row; the downgrade re-seeds it.

## Consequences

+ A delivery cannot be half recorded, and the second of two administrators changes nothing.
+ VS-029 and VS-030 extend one table and one helper instead of forking the endpoint.
- The queue shows the oldest placement first, not the oldest payment; a retry-paid old order sits near the front.
- The transition response changes in VS-029, before any frontend depends on it.
- The outbox is at-least-once, so the "sent" email can rarely arrive twice (the in-app notification cannot).

## Alternatives rejected

- **Move the `order_items` SQL into `fulfillment`** - two modules would write one table and the writers test would need a second registry.
- **Send the email inside the transaction** - a provider outage would block, or roll back, a delivery the administrator already made.
- **Order by payment time** - needs a new column; the placement time is already indexed and stable.
