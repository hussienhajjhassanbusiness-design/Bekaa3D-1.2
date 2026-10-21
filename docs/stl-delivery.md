# STL delivery (VS-023b)

The administrator emails each paid STL from their own drive, then marks the line sent. Decisions: [ADR-019](adr/ADR-019-manual-stl-delivery.md), [ADR-039](adr/ADR-039-stl-delivery-workflow.md). Plan: [`plans/VS-023b-stl-delivery-queue-plan.md`](plans/VS-023b-stl-delivery-queue-plan.md).

## Routes

Both are administrator-only (MFA); a customer gets `404`, an anonymous caller `401`. The POST also needs `X-CSRF-Token` and is limited to 300 per administrator per hour.

### `GET /api/v1/admin/stl-deliveries`

Every STL line in `awaiting_delivery`, oldest first (`order_items.created_at`, then `id`). Query: `limit` (1-100, default 25), `cursor` (opaque), `product_id`, `customer_id`. A bad cursor is `422`.

`{ items: [...], next_cursor }`, each item:

| Field | Meaning |
|---|---|
| `item_id`, `order_id`, `order_number` | the line and its order |
| `product_id`, `product_name` | the product (name as sold) |
| `customer_id`, `customer_email` | who to send to: the email captured at checkout |
| `line_total_cents`, `currency` | the line's total |
| `queued_at` | when the line was placed |

A refunded or cancelled line is not listed; a partly refunded line still is.

### `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition`

Body `{ "target_status": "delivered" }`. `200`, provisional until VS-029:
`{ order_id, item_id, fulfillment_status: "delivered", fulfilled_at, delivered_by, order_status }`.

| Status | When |
|---|---|
| `404` | no such order, no such item, or the item is on another order (one body for all three) |
| `409 INVALID_STATE_TRANSITION` | `reason`: `already_delivered` (with `fulfilled_at`), `line_closed`, `not_awaiting_delivery`, `not_an_stl_line` |
| `422` | any other `target_status` |

There is no `Idempotency-Key`: a second call gets `409 already_delivered`.

## What one successful call writes

In one transaction, locking `orders` and then its lines by id:

1. the line: `delivered`, `fulfilled_at`, `delivered_by` (`ck_order_items_stl_delivery_record`);
2. a line history row (actor = the administrator) and, if it changed, an order history row;
3. the order status through `derive_order_status` (`completed` when every line is terminal);
4. an audit row `stl.delivered` on the line;
5. an in-app notification for the buyer (`download`, `payload.event = "stl.delivered"`);
6. an outbox email, template `order_stl_delivered`, to `customer_email_snapshot`.

The email is sent after commit by `dispatch_outbox`; it is at-least-once, so it can rarely arrive twice.

## For VS-029 and VS-030

- Add physical edges to `ordering/domain/line_transitions.py` (`LEGAL_EDGES`) and widen `target_status`; replace `OrderItemTransitionRead` with `AdminOrderDetail`.
- VS-030 must replace the `refund_present` stop-gap in `ordering.public.status_inputs_for` with the real refund query, and take the `orders` lock before refunding a line.
