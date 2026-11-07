# 05 — Fulfillment

The administrator's order queue, line-by-line fulfillment, the cash handover, admin
cancellation and the STL delivery queue. Fulfillment owns no tables: it writes order lines
through `ordering.public`. Requirements: FR-08, FR-09, FR-12, FR-20; BR-035 to BR-038, BR-042,
BR-057, BR-064 to BR-068, BR-075, BR-077, BR-142 to BR-149; ADR-019, ADR-039, ADR-040, ADR-043.

Every route is admin-only (customer `404`, anonymous `401`); every write needs CSRF.

Code: routers in `src/app/fulfillment/api/` (`admin_orders.py`, `item_transition.py`,
`stl_deliveries.py`, `admin_order_schemas.py`), use cases in `src/app/fulfillment/application/`
(`transition_line.py`, `record_cash_handover.py`, `cancel_lines.py`, `mark_stl_delivered.py`,
`admin_order_detail.py`), limits in `fulfillment/domain/limits.py`, the legal moves in
`src/app/ordering/domain/line_transitions.py`, the status projection in
`ordering/domain/order_status.py`, the handover rule in `ordering/domain/handover.py`.

**Line states and legal moves**

| Path | Moves |
| --- | --- |
| Delivery | `pending → in_production → ready_to_ship → shipped → delivered`; `shipped → returned`; `returned → shipped` (re-ship) or `→ in_production` (reprint) |
| Pickup | `pending → in_production → ready_for_pickup → picked_up` |
| STL | `awaiting_delivery → delivered` |
| Cancel | from `pending`, `in_production` (no reason); `ready_to_ship` (`refused`, `other`); `ready_for_pickup` (`refused`, `no_show`, `other`); `returned` (unpaid cash only: `refused`, `other`); `shipped` (unpaid cash with total 0 only: `other`) |

On a cash order, `delivered` and `picked_up` are reached **only** by the cash handover. No
physical step on an unpaid online order (BR-148). `in_production` ("start printing") is silent
for the customer: no email, and their view shows `pending`.

Customer emails per order and visible step (sent when the last live physical line reaches it):
`order_ready` (`ready_to_ship`), `order_shipped`, `order_ready_for_pickup`, `order_delivered`,
`order_picked_up`, and `order_stl_delivered` for an STL line.

---

## Order queue

### `GET /api/v1/admin/orders`

Admin. Newest first. **Never lists an unpaid online order** (BR-148): `status=pending_payment` is
`422`. Query: `status`, `fulfillment_method`, `payment_method`, `payment_due` (`true` = the cash
due view), `customer_id`, `order_number` (1-40), `placed_after`, `placed_before` (UTC offset
required), `limit` (1-100, 25), `cursor`.

Item: `{id, order_number, customer_id, customer_email, status, fulfillment_method,
payment_method, payment_due, amount_due, total, estimated_dispatch_at, placed_at}`.

Errors: `401`, `404` (customer), `422` (bad filter, `pending_payment`, bad cursor).

### `GET /api/v1/admin/orders/{order_id}`

Admin. `AdminOrderDetail`: any order (unpaid online included), with `customer_id`,
`customer_email`, `contact_phone`, `delivery_address`, `payment_reached_paid`, `admin_note`, the
real line states, each line's `available_actions` (`[{target_status, cancel_reasons}]`: exactly
what the transition endpoint accepts now), every payment, the full history with actors,
`refunds[]`, `chargebacks[]` and `refund_balance`. `404` for an unknown id.

### `PATCH /api/v1/admin/orders/{order_id}`

Admin; CSRF; 120 per hour per admin. Body `{"admin_note": "Call before delivery." | null}`
(≤ 5000; blank or null clears). Audited `order.admin_note_updated` with `has_note` only. Never
shown to the customer. **Do not put customer contact details in the note**: account deletion
keeps it. `200 AdminOrderDetail`. Errors: `404`, `422` (another field, too long), `429`.

| ID | Test | Expected |
| --- | --- | --- |
| FUL-01 | Admin `GET /admin/orders` | ORD-15 listed with `payment_due: true`; ORD-21 listed only after it is paid |
| FUL-02 | `GET /admin/orders?status=pending_payment` | `422 VALIDATION_ERROR` |
| FUL-03 | `GET /admin/orders?payment_due=true` | only unpaid cash orders |
| FUL-04 | `GET /admin/orders/{ORD-21 id}` before payment | `200`; `payment_reached_paid: false`; the line's `available_actions` is `[]` |
| FUL-05 | `GET /admin/orders/{ORD-15 id}` | the line's `available_actions` include `in_production` and `cancelled` |
| FUL-06 | `PATCH` `{"admin_note": "Fragile, pack twice."}` | `200`; `admin_note` set; the customer's `GET /me/orders/{id}` has no `admin_note` |
| FUL-07 | `PATCH` `{"admin_note": "x", "status": "completed"}` | `422 VALIDATION_ERROR` |
| FUL-08 | Customer: `GET /admin/orders` | `404 NOT_FOUND` |

---

## Line transitions

### `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Admin | yes | no (a repeat is a 409) | 300 per hour per admin, shared with admin cancel |

Moves one line one step (physical) or marks an STL `delivered`. In one transaction: the line and
its history, the order status (recomputed, never set: BR-035), an audit row
(`order_item.transitioned`, or `stl.delivered`), and the customer's notice for a visible step.

Request: `{"target_status": "in_production", "reason": "optional note, ≤ 500", "cancel_reason": null}`.
Response `200 AdminOrderDetail`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown order, unknown item, or an item of another order |
| 409 | `INVALID_STATE_TRANSITION` | `reason` (with the line's `fulfillment_status`): `payment_required` (unpaid online), `cash_handover_required` (`delivered`/`picked_up` on cash), `not_a_legal_edge`, `line_closed` (cancelled/refunded), `already_delivered` (STL, with `fulfilled_at`), `not_awaiting_delivery` (STL), `cancel_reason_required`, `cancel_reason_not_allowed`, `refund_exceeds_available` |
| 409 | `ORDER_TOTAL_MISMATCH` | a paid cancel whose order data does not add up (alerted) |
| 422 | `VALIDATION_ERROR` | unknown `target_status`, note over 500, unknown field |
| 429 | `RATE_LIMITED` | over 300 per hour |

| ID | Test | Expected |
| --- | --- | --- |
| FUL-09 | ORD-15 (cash, delivery) line: `in_production` | `200`; no customer email; order `in_progress` |
| FUL-10 | Same line: `ready_to_ship` | `200`; `order_ready` email queued |
| FUL-11 | Same line: `shipped` | `200`; `order_shipped` email |
| FUL-12 | Same line: `delivered` | `409 INVALID_STATE_TRANSITION`, `reason: cash_handover_required` |
| FUL-13 | A fresh `pending` line: `shipped` (skipping steps) | `409`, `reason: not_a_legal_edge`, `fulfillment_status: pending` |
| FUL-14 | Unpaid online order line: `in_production` | `409`, `reason: payment_required` |
| FUL-15 | A `ready_to_ship` line: `cancelled` without `cancel_reason` | `409`, `reason: cancel_reason_required` |
| FUL-16 | A `ready_to_ship` line: `cancelled` with `cancel_reason: no_show` | `409`, `reason: cancel_reason_not_allowed` |
| FUL-17 | Paid (mock) delivery order line through `shipped` → `delivered` | `200`; `order_delivered` email; order `completed` when every line is terminal |
| FUL-18 | A paid `shipped` line: `returned`, then `shipped` again | both `200`; `order_shipped` announced again |

---

## Cash handover

### `POST /api/v1/admin/orders/{order_id}/cash-handover`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Admin | yes | no | 60 per hour per admin |

Records the cash collected, once per order (BR-143), and in the same transaction marks every live
line `delivered` (delivery) or `picked_up` (pickup) and creates one `cash` payment, `paid`, for
exactly the live total. Every live line must be `shipped` (delivery) or `ready_for_pickup`
(pickup).

Request: `{"amount_cents": 4800, "currency": "USD", "note": "Paid in full to the courier."}`.
Response `200 AdminOrderDetail` (status `completed`; one cash payment with `recorded_by`).

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown order |
| 409 | `INVALID_STATE_TRANSITION` | `reason`: `not_a_cash_order`, `no_live_line`, `already_recorded`, `lines_not_ready` |
| 422 | `CASH_AMOUNT_MISMATCH` | not exactly the live total, or zero; `amount_due` |
| 422 | `VALIDATION_ERROR` | `currency` not USD, negative or non-integer amount, unknown field |
| 429 | `RATE_LIMITED` | over 60 per hour |

| ID | Test | Expected |
| --- | --- | --- |
| FUL-19 | ORD-15 after FUL-11 (line `shipped`): handover with 4799 | `422 CASH_AMOUNT_MISMATCH`, `amount_due` 4800; nothing written |
| FUL-20 | Handover with exactly 4800 | `200`; line `delivered`; order `completed`; one `cash` payment `paid`; `order_delivered` email with a `cash_receipt` |
| FUL-21 | Handover again | `409`, `reason: already_recorded` |
| FUL-22 | Handover on a cash order still `in_production` | `409`, `reason: lines_not_ready` |
| FUL-23 | Handover on an online order | `409`, `reason: not_a_cash_order` |

---

## Admin cancellation

### `POST /api/v1/admin/orders/{order_id}/cancel`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Admin | yes | no | shares the 300 per hour transition limit |

Cancels every physical line in `pending`, `in_production`, `ready_to_ship` or
`ready_for_pickup`; shipped, returned and finished lines stay. A paid line gets one pending
`cancellation` refund for its remaining balance; an unpaid cash line none. A cash order left
with no live line, where every recorded `cancel_reason` is `refused` or `no_show`, gets a **cash
block** (BR-144). To cancel one line only, use the transition endpoint with
`target_status: cancelled`.

Request: `{"reason": "Customer refused the delivery at the door.", "cancel_reason": "refused"}`
(`reason` 1-500; `cancel_reason` required when a line is `ready_to_ship` or `ready_for_pickup`).
Response `200 AdminOrderDetail`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown order |
| 409 | `INVALID_STATE_TRANSITION` | `reason`: `payment_required`, `no_cancellable_line`, `cancel_reason_required`, `cancel_reason_not_allowed`, `not_a_legal_edge`, `line_closed`, `refund_exceeds_available` |
| 409 | `ORDER_TOTAL_MISMATCH` | integrity failure (alerted) |
| 422 | `VALIDATION_ERROR` | blank reason, unknown `cancel_reason` |

| ID | Test | Expected |
| --- | --- | --- |
| FUL-24 | A new cash delivery order (use a second customer if the seed customer already holds an open or recently self-cancelled cash order); line to `in_production`, then `ready_to_ship`; cancel with `cancel_reason: refused` | `200`; order `cancelled`; no refund; a cash block appears (ORD-63) |
| FUL-25 | Paid (mock) order, line `in_production`: cancel with no `cancel_reason` | `200`; a pending `cancellation` refund for the line total; `order_refund_issued` email |
| FUL-26 | An unpaid online order | `409`, `reason: payment_required` |
| FUL-27 | An order whose lines are all `delivered` | `409`, `reason: no_cancellable_line` |
| FUL-28 | A `ready_to_ship` order without `cancel_reason` | `409`, `reason: cancel_reason_required` |

---

## STL delivery queue

The platform never stores STL files (ADR-019). The administrator emails them from their own
drive, then marks the line delivered (BR-042, BR-057, BR-065).

### `GET /api/v1/admin/stl-deliveries`

Admin. Every STL line in `awaiting_delivery`, oldest first. Query: `limit` (1-100, 25), `cursor`,
`product_id`, `customer_id`.

Response `200`:

```json
{
  "items": [
    {
      "item_id": "…", "order_id": "…", "order_number": "B3D-…",
      "product_id": "…", "product_name": "Phone Stand STL",
      "customer_id": "…", "customer_email": "seed-customer@example.com",
      "line_total_cents": 350, "currency": "USD",
      "queued_at": "2026-11-07T10:00:00Z"
    }
  ],
  "next_cursor": null
}
```

A refunded or cancelled line is not listed; a partly refunded one is. Errors: `401`, `404`,
`422` (bad cursor). Code: `fulfillment/api/stl_deliveries.py`.

Marking an STL sent uses the transition endpoint above with `{"target_status": "delivered"}`:
the line gets `fulfilled_at` and `delivered_by`, the customer an `order_stl_delivered` email and
an in-app notification, and an audit row `stl.delivered`. Code:
`fulfillment/application/mark_stl_delivered.py`.

| ID | Test | Expected |
| --- | --- | --- |
| FUL-29 | After PAY-08 (or PAY-01 for an STL): `GET /admin/stl-deliveries` | the paid STL line is listed with the customer's email |
| FUL-30 | Transition it to `delivered` with `reason: "Sent from Drive"` | `200`; line `delivered` with `fulfilled_at`; order `completed` (if no other live line); `order_stl_delivered` in the outbox; gone from the queue |
| FUL-31 | Transition it to `delivered` again | `409`, `reason: already_delivered`, `fulfilled_at` |
| FUL-32 | Transition an STL line to `cancelled` | `409`, `reason: not_a_legal_edge` |
| FUL-33 | Refund an awaiting STL line in full (PAY tests), then read the queue | the line is `refunded` and no longer listed; `GET /me/stl-ownership` answers `owned: false` |
