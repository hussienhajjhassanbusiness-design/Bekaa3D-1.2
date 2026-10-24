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
- **`receipt_confirmed_at`** and **`problem_reported_at`** (VS-029b, [ADR-041](adr/ADR-041-receipt-confirmation-and-problem-report.md)): on a physical line, the first "I got it" and the first problem report. Always null on STL lines.
- **`payment`**: `{status, provider, amount}` of the live or paid attempt, else of the most recent one. `null` while a cash order is unpaid. No provider reference.
- **`payment_due`**: an unpaid cash order (`in_progress`). Pay the courier, or pay at pickup. `total` is the total at checkout: if a line was cancelled, the amount due is the sum of the lines still live, not `total`. That sum is `amount_due` (VS-028; a `PriceRead`, ADR-038 d21), on the list items and the detail: the line totals not cancelled while `payment_due`, else null.
- **`can_cancel`**: true only when the order has a live (not cancelled) physical line, is cash or has a payment that reached paid, is `in_progress` or `partially_refunded`, and every live physical line is still `pending`. Lines an administrator already cancelled are ignored. It is false for STL-only orders and unpaid online orders. Self-cancel itself is VS-031. The flag is advisory: the cancel route re-checks under its locks.
- **`can_retry_payment`** (VS-041): a new payment attempt may be started now with `POST /api/v1/me/orders/{order_id}/payments`. It means an unpaid online order, every line `pending`, inside `placed_at + checkout_hold_period`, and no attempt `pending` or `processing`. On an offer order (`source: "offer"`) the offer must also still be inside its checkout window. The flag is advisory; the POST re-checks under its locks.
- **`hold_expires_at`** (VS-041): for an unpaid online order, when it may be released if still unpaid. That is the later of placement and the latest attempt, plus `checkout_hold_period` ([`payment-recovery.md`](payment-recovery.md)). It is null for every other order. It can be later than the last moment `can_retry_payment` allows, because retry is bounded from placement.
- **`delivery_address`** and `delivery_fee_note` are set for delivery orders only. `contact_phone` is set for physical orders.
- **`status_history`**: oldest first, `{order_item_id, from_status, to_status, at}`. `order_item_id` is null for the order's own status. Entries into `in_production` are left out, and the next one out of it reads as from the state before it (`pending`, or `returned` when a returned item is reprinted). No actor and no reason.
- **Never returned:** `admin_note`, the checkout email, the phone hash, the delivering administrator, provider references or metadata.

## "I got it" and "Report a problem" (VS-029b)

`POST /api/v1/me/orders/{order_id}/confirm-receipt` (no body, `200 OrderDetail`) and `POST /api/v1/me/orders/{order_id}/report-problem` (`{"message": "..."}`, `201 OrderDetail`). Decisions: [ADR-041](adr/ADR-041-receipt-confirmation-and-problem-report.md).

- A verified email and `X-CSRF-Token` are required: unverified `403 EMAIL_VERIFICATION_REQUIRED`, missing token `403 CSRF_INVALID`, anonymous `401`. Another customer's order gives the same `404` as an unknown id.
- Both cover the physical lines that are `delivered` or `picked_up`. With none, both give `409 INVALID_STATE_TRANSITION` with `reason: no_delivered_line`. A delivered STL line does not count.
- Neither changes a line's status, the order status or the history; the order completes without them. The email buttons only open the order page.
- Confirming again changes nothing; a line delivered since is stamped then.
- A report is 1-5000 characters after trimming (`422` otherwise), 5 an hour per user (`429`). Each report becomes a contact message in the administrator's queue and an in-app alert for every administrator; `problem_reported_at` keeps the first report's time.

## Refund summary (VS-030)

`OrderDetail.refunds[]`, oldest first: `{kind, status, amount, created_at}` for each `admin`, `cancellation` and `late_capture` refund (ADR-033 d7, ADR-042 d14). `status` is `processing` while it is pending or owed and `refunded` once settled. A voided refund, a failed one already reissued (its reissue is listed instead) and chargebacks are never shown. It is a display read: the balances live on the admin order detail only.
