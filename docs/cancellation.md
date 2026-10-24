# Cancellation and returns (VS-031)

As built in VS-031. The decisions and their reasons are in [ADR-043](adr/ADR-043-cancellation-and-returns.md) and [ADR-038](adr/ADR-038-physical-checkout-and-cash-eligibility.md) d23. Refund rules are in [`refunds.md`](refunds.md).

## Routes

| Route | Who | Body | Success | Refusals |
|---|---|---|---|---|
| `POST /api/v1/me/orders/{id}/cancel` | Verified customer, owner; CSRF; 10/hour | `{reason?: str ≤ 500}` | `200 OrderDetail` | 401, 403 (`CSRF_INVALID`, `EMAIL_VERIFICATION_REQUIRED`), 404 (unknown or another customer's), 409 `ORDER_NOT_CANCELLABLE`, 422, 429 |
| `POST /api/v1/admin/orders/{id}/cancel` | Administrator (MFA); CSRF; the transition limit | `{reason: str 1-500, cancel_reason?: refused \| no_show \| other}` | `200 AdminOrderDetail` | 401/404, 409 `INVALID_STATE_TRANSITION` (`payment_required`, `no_cancellable_line`, `cancel_reason_required`, `cancel_reason_not_allowed`, `refund_exceeds_available`) or `ORDER_TOTAL_MISMATCH`, 422, 429 |
| `POST /api/v1/admin/orders/{id}/items/{item_id}/transition` | as before | adds `cancel_reason?` | `200 AdminOrderDetail` | adds `cancel_reason_required`, `cancel_reason_not_allowed`, `refund_exceeds_available` |

No route takes an `Idempotency-Key`. A repeated cancel is a 409, never a second refund.

## What a cancel takes

- **Customer:** every live physical line, all `pending` (`can_cancel`), or nothing. An unpaid online order, an STL-only order and an order whose printing started are refused.
- **Administrator's order cancel:** every physical line in `pending`, `in_production`, `ready_to_ship` or `ready_for_pickup`. Shipped, returned and finished lines stay as they are.
- **One line (transition endpoint):** any legal `-> cancelled` edge. The edges and the reasons they take:

| From | Delivery | Pickup | Reasons |
|---|---|---|---|
| `pending`, `in_production` | yes | yes | none |
| `ready_to_ship` | yes | - | `refused`, `other` |
| `ready_for_pickup` | - | yes | `refused`, `no_show`, `other` |
| `returned` | unpaid cash only | - | `refused`, `other` |
| `shipped` | unpaid cash, total 0 only | - | `other` |

Return edges: `shipped -> returned`, then `returned -> shipped` (re-ship) or `-> in_production` (reprint). `returned -> refunded` is a refund of the line's remaining balance through `POST /admin/orders/{id}/refunds`.

## Money

- A paid line's cancel creates one pending `cancellation` refund for each cancelled line's **whole remaining balance**: its total less earlier refunds and chargebacks. None is created when that is 0. If the refund cannot be created, nothing is cancelled. A paid line is never left cancelled with part of its balance uncovered, so a chargeback for the whole payment always allocates.
- An unpaid cash line is never refunded.
- A customer's refund has `requested_by` = the customer and `approved_by` NULL.

## Cash block (BR-144)

A block is written after a cancel that leaves an unpaid cash order with no live line, when every recorded `cancel_reason` on the order is `refused` or `no_show` (at least one). It is keyed on the customer and the order's phone hash, under the cart lock and then the phone lock. A partial refusal, any `other` cancel and an online order never block. A cancel with no reason (the customer's, or from `pending` / `in_production`) is neutral: a customer cancelling the last live line after an administrator refused the others completes the block.

A cart with any physical line priced 0 cannot be paid in cash (ADR-043 d12), so a free item cannot turn a refusal into an `other` cancel that escapes the block.

## Cash limit (ADR-038 d23)

A cash order the customer cancelled themselves (`orders.customer_cancelled_at`) counts toward `cash_max_open_orders` for 24 hours, for that customer and that phone. At exactly 24 hours it stops counting.

## Notices and audit

- `order_cancelled` email and `order.cancelled` notification. Payload: `order_id`, `order_number`, `items[{item_id, product_name}]`, `order_cancelled`, `amount_due_cents` (unpaid cash still live, else null), `refund_cents`, `currency`.
- A paid cancel also sends `order_refund_issued` / `refund.issued`.
- A step newly reached by the lines that remain is announced once. A re-ship announces `shipped` again.
- One `order.cancelled` audit row per request. It never holds a phone or a hash.
