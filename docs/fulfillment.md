# Admin order queue, fulfillment and cash handover (VS-029)

The administrator finds an order in the queue, moves each physical line from received to delivered or picked up, and records the cash for a cash order at handover. Decisions: [ADR-024](adr/ADR-024-cash-on-delivery-and-courier-priced-shipping.md), [ADR-040](adr/ADR-040-admin-order-queue-fulfillment-and-cash-handover.md). STL lines: [`stl-delivery.md`](stl-delivery.md).

Every route is administrator-only (MFA): a customer gets `404`, an anonymous caller `401`. Every write also needs `X-CSRF-Token`. Money is `PriceRead` (`{amount_cents, currency}`).

## Routes

### `GET /api/v1/admin/orders`

Newest first by `(placed_at, id)`. **Never lists an unpaid online order**, open or released (BR-148); `status=pending_payment` is a `422`.

| Query | Meaning |
|---|---|
| `status`, `fulfillment_method`, `payment_method` | exact match |
| `payment_due` | `true`: the "cash due" view (unpaid cash orders); `false`: everything else |
| `customer_id`, `order_number` | exact match |
| `placed_after` (inclusive), `placed_before` (exclusive) | aware ISO 8601 |
| `limit` (1-100, default 25), `cursor` | keyset paging; a bad cursor is `422` |

Each item: `id`, `order_number`, `customer_id`, `customer_email`, `status`, `fulfillment_method`, `payment_method`, `payment_due`, `amount_due` (the live line total while `payment_due`, else `null`), `total`, `estimated_dispatch_at`, `placed_at`.

### `GET /api/v1/admin/orders/{order_id}` → `AdminOrderDetail`

Any order, unpaid online ones included. Beyond the customer's view it carries `customer_id`, `customer_email`, `payment_reached_paid`, `admin_note`, the real line states (never masked), `delivered_by`, every payment (newest first; `recorded_by` for cash) and the full status history with actors (oldest first). Each line has `available_actions`: `[{target_status, cancel_reasons}]`, exactly what the transition endpoint would accept now; `cancel_reasons` stays empty until VS-031.

### `PATCH /api/v1/admin/orders/{order_id}`

Body `{ "admin_note": "..." | null }` (≤ 5000 chars); blank or `null` clears it, any other field is `422`. Answers `AdminOrderDetail`. Audited as `order.admin_note_updated` with `has_note` only, never the text. No customer response ever has the note. 120 per administrator per hour. **Do not put customer contact details (name, phone, address, email) in the note:** account deletion strips them from the order but keeps the note as written (ADR-047 d2).

### `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition`

Body `{ "target_status": "...", "reason": "..." }` (`reason` optional, ≤ 500, kept in the history). Answers `AdminOrderDetail`. Shared limit with STL delivery: 300 per administrator per hour.

| Path | Edges |
|---|---|
| delivery | `pending → in_production → ready_to_ship → shipped → delivered` |
| pickup | `pending → in_production → ready_for_pickup → picked_up` |
| STL | `awaiting_delivery → delivered` ([`stl-delivery.md`](stl-delivery.md)) |

`409 INVALID_STATE_TRANSITION` with `reason` and the line's `fulfillment_status`:

| `reason` | When |
|---|---|
| `payment_required` | an online order whose payment never reached `paid` (BR-148) |
| `cash_handover_required` | `→ delivered` / `→ picked_up` on a cash order: only the handover reaches them |
| `not_a_legal_edge` | any other step, a skipped step or the other method's step |
| `line_closed` | the line is `cancelled` or `refunded` |
| `already_delivered`, `not_awaiting_delivery` | STL lines only |

### `POST /api/v1/admin/orders/{order_id}/cash-handover`

Body `{ "amount_cents": 3600, "currency": "USD", "note": "..." }`: the cash actually collected. Answers `AdminOrderDetail`. 60 per administrator per hour.

| Status | When |
|---|---|
| `409 INVALID_STATE_TRANSITION` | `reason`: `not_a_cash_order`, `no_live_line`, `already_recorded`, `lines_not_ready` (every live line must be `shipped` for delivery, `ready_for_pickup` for pickup) |
| `422 CASH_AMOUNT_MISMATCH` | not exactly the live line total in the order's currency, or zero; carries `amount_due` |
| `422 VALIDATION_ERROR` | another currency, a non-integer or negative amount, an unknown field |

Nothing is written on any refusal.

### `/api/v1/admin/cash-blocks`

| Route | Notes |
|---|---|
| `GET /api/v1/admin/cash-blocks` | `customer_id`, `active`, `limit`, `cursor`; newest first |
| `POST /api/v1/admin/cash-blocks/search` | body `{ phone, active?, limit?, cursor? }`: the phone stays out of URLs and logs; any spelling of one number matches; a non-Lebanese number is `422` |
| `POST /api/v1/admin/cash-blocks/{block_id}/clear` | sets `cleared_at`, `cleared_by`, audited `cash_block.cleared`; clearing a cleared block is a `200` that changes nothing |

Each block: `id`, `customer_id`, `order_id`, `order_number`, `reason`, `created_at`, `active`, `cleared_at`, `cleared_by`. Never the phone or its hash. Search and clear share 60 per administrator per hour. VS-031 creates blocks.

## What one transition or handover writes

In one transaction, locking `orders` and then every line by id (ADR-024 d9):

1. the line(s) and their history rows (actor = the administrator);
2. the order status through `derive_order_status`, with a history row when it changes; `completed_at` the first time it is `completed`;
3. for a handover, one `cash` payment, `paid`, for the live total, with `recorded_by` and `verified_at` (`uq_payments_one_cash` is the final guard);
4. an audit row: `order_item.transitioned` on the line, or `order.cash_handover` on the order;
5. the customer's notice, if a visible step was reached (below).

## What the customer hears and sees

- **One email and one notification per order per visible step**, on the transition that brings the last live physical line to that step. Cancelled and refunded lines are not waited for.

  | Step | Template | `payload.event` |
  |---|---|---|
  | `ready_to_ship` ("finished") | `order_ready` | `order.ready_to_ship` |
  | `shipped` | `order_shipped` | `order.shipped` |
  | `ready_for_pickup` | `order_ready_for_pickup` (with `pickup_address`, `pickup_hours`) | `order.ready_for_pickup` |
  | `delivered` | `order_delivered` | `order.delivered` |
  | `picked_up` | `order_picked_up` | `order.picked_up` |

  Delivery emails carry `delivery_fee_note` ("delivery fee paid to the courier on delivery"). The `delivered` / `picked_up` emails set `receipt_actions`: their "I got it" and "Report a problem" buttons open the order page (VS-029b adds the actions). The handover's email adds `cash_receipt` (`payment_id`, `amount_cents`, `currency`, `recorded_at`). No payload carries the phone, its hash or the address.
- **`in_production` ("start printing") is silent**: no email, no notification; the customer sees the line as `pending` and the step is left out of their history. `can_cancel` turns false once printing starts.
- Emails are outbox rows sent after commit by `dispatch_outbox`; a provider outage never blocks a transition.

## For VS-030 and VS-031

- VS-031 adds the cancel and return edges (with `cancel_reasons`) to `ordering/domain/line_transitions.py`, and must decide whether a cancel that leaves every remaining line at a step sends that step's notice (ADR-040 consequences).
- If VS-031 sets `orders.cancelled_at` on a paid online order, `ADMIN_QUEUE_PREDICATE` must still list it.
- VS-030 still has to replace the `refund_present` stop-gap in `ordering.public.status_inputs_for` (ADR-039 d7).
