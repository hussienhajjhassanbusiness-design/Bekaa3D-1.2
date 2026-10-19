# Customer order history (VS-025)

The contract for `GET /api/v1/me/orders` and `GET /api/v1/me/orders/{order_id}`. Decisions and their reasons: [ADR-033](adr/ADR-033-customer-order-read-model.md). Shapes: [`api-endpoints.md`](requirments/api-endpoints.md) `OrderDetail` and `OrderSummary`, and the OpenAPI file in [`frontend-handoff/`](frontend-handoff/openapi.json).

## Access

- A session is enough. A customer with an unverified email can read their orders. There is no rate limit, like `GET /cart`.
- Anonymous: `401`.
- Another customer's order gives the same `404` as an unknown id. Ownership is part of every SQL query.
- An administrator sees only their own orders here; the admin order queue is VS-029.

## `GET /api/v1/me/orders`

| Parameter | Meaning |
|---|---|
| `status` | One `OrderStatus`: `pending_payment`, `in_progress`, `completed`, `partially_refunded`, `refunded`, `cancelled`. |
| `placed_after` | Inclusive. ISO-8601 **with a timezone**. Without one: `422`. |
| `placed_before` | Exclusive. Same rules. |
| `cursor` | Opaque. Pass back `next_cursor`. A malformed one: `422 VALIDATION_ERROR` naming `cursor`. |
| `limit` | 1-100, default 20. |

- Sort is fixed: newest `placed_at` first, then `id` descending, so orders placed at the same instant still page exactly once.
- An order placed while you page appears on a fresh first page; it never repeats or displaces a row in the pages you are reading.
- Each item: `{id, order_number, status, payment_method, fulfillment_method, payment_due, total, placed_at}`.

## `GET /api/v1/me/orders/{order_id}`

- **What was bought.** Every line shows its name, image, unit price and line total as they were at checkout (BR-033). Editing, repricing or deleting the product never changes them. `image_url` is built from the image captured at checkout.
- **`fulfillment_status`** is never `in_production`: a line being printed reads `pending` ("Received"), even though the OpenAPI enum lists the value.
- **`fulfilled_at`**: for an STL line, when the administrator emailed the file (`delivered`). This is the customer's STL purchase list (F-027): `awaiting_delivery` means paid and not yet sent.
- **`payment`**: `{status, provider, amount}` of the live or paid attempt, else of the most recent one. `null` while a cash order is unpaid. No provider reference.
- **`payment_due`**: an unpaid cash order (`in_progress`). Pay the courier, or pay at pickup. `total` is the total at checkout: if a line was cancelled, the amount due is the sum of the lines still live, not `total`.
- **`can_cancel`**: true only when the order has a physical line, is cash or has a payment that reached paid, is `in_progress` or `partially_refunded`, and every physical line is still `pending`. It is false for STL-only orders and unpaid online orders. Self-cancel itself is VS-031. The flag is advisory: the cancel route re-checks under its locks.
- **`delivery_address`** and `delivery_fee_note` are set for delivery orders only. `contact_phone` is set for physical orders.
- **`status_history`**: oldest first, `{order_item_id, from_status, to_status, at}`. `order_item_id` is null for the order's own status. Entries into `in_production` are left out, and the next one out of it reads as from the state before it (`pending`, or `returned` when a returned item is reprinted). No actor and no reason.
- **Never returned:** `admin_note`, the checkout email, the phone hash, the delivering administrator, provider references or metadata.

## Not yet

- Refund summary: VS-030.
- `can_retry_payment`, `hold_expires_at`: VS-024 (see the slice plan's "Wire in when VS-024 merges").
- Receipt confirmation and problem report fields: VS-029b.
