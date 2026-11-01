# Refunds, voids and chargebacks (VS-030)

As built. Decisions: [ADR-042](adr/ADR-042-refunds-voids-and-chargebacks.md) (amends SRS §20.2 and ADR-024 d12, d16). Plan: [VS-030](plans/VS-030-refunds-settlement-plan.md). Schemas: [`frontend-handoff/openapi.json`](frontend-handoff/openapi.json); every route is admin-only, with MFA, and every write needs CSRF and is limited to 60 an hour per administrator (reads 300).

**The one rule:** the platform never moves money. Every V1 refund is manual: the administrator records it, pays it in the provider's dashboard or in cash, then settles it here. Nothing is ever paid out twice and payout never exceeds what was paid, because every balance is derived under the order's row lock.

## Routes

| Route | Answers | Notes |
|---|---|---|
| `POST /api/v1/admin/orders/{order_id}/refunds` | `201 RefundDetail` | `Idempotency-Key` required; always `kind = admin` |
| `GET /api/v1/admin/refunds` | `200 RefundPage` | `queue=true` (default): pending and owed, oldest first; `queue=false`: history, newest first; filters `status`, `kind`, `order_id`, `customer_id`, `created_from`, `created_to` |
| `GET /api/v1/admin/refunds/{refund_id}` | `200 RefundDetail` | with reissue links |
| `POST /api/v1/admin/refunds/{refund_id}/settle` | `200 RefundDetail` | `pending → settled`; a repeat is 200 unchanged |
| `POST /api/v1/admin/refunds/{refund_id}/fail` | `200 RefundDetail` | `pending → failed`: still owed |
| `POST /api/v1/admin/refunds/{refund_id}/reissue` | `201 RefundDetail` | `Idempotency-Key` required; a new pending twin |
| `POST /api/v1/admin/refunds/{refund_id}/void` | `200 RefundDetail` | closes a mistake unpaid; a repeat keeps the first reason |
| `POST /api/v1/admin/orders/{order_id}/chargebacks` | `201 ChargebackDetail` | `Idempotency-Key` required |
| `GET /api/v1/admin/orders/{order_id}/chargebacks`, `GET /api/v1/admin/chargebacks/{id}` | `200` | never in the queue |
| `POST /api/v1/admin/payments/{payment_id}/record-capture` | `201 RecordCaptureRead` | `Idempotency-Key` required; see below |

`AdminOrderDetail` carries `refunds[]`, `chargebacks[]` and `refund_balance` (per line and for the payment). The customer's `OrderDetail.refunds[]` shows admin, cancellation and late-capture refunds as `processing` or `refunded`, never a voided one or a chargeback ([`order-history.md`](order-history.md)).

## Balances

- A line's balance is its total minus its items in pending, settled and owed (failed, not reissued) refunds and in chargebacks. A `refunded` line, and a `cancelled` one without any items, have 0.
- The payment's balance is its amount minus those refunds and the chargebacks' applied amounts. A cash payment is refunded up to the cash recorded.
- A refund over either balance is 422 `REFUND_EXCEEDS_AVAILABLE`, with `available`.
- A refund that empties an unfinished physical line (`pending`, `in_production`, `ready_to_ship`, `shipped`, `ready_for_pickup`) is 422 `REFUND_REQUIRES_CANCELLATION`: cancel it (VS-031).
- A line covered in full becomes `refunded` at creation if it is delivered, picked up, returned or an STL line; an STL line still awaiting delivery then leaves the queue and frees ownership. A partial refund leaves the line as it is.
- Before any balance, the order's total must equal its lines, an online payment must equal the total, and the payment's currency the order's (Q-2): otherwise 409 `ORDER_TOTAL_MISMATCH`, nothing written, a `refund_integrity_error` log and a `refund_integrity` alert. Settle skips this check: it records a payout already made. Create, fail, void, reissue and a paid chargeback do not (late-capture refunds skip it entirely, ADR-042 d19), so on such an order those stay refused until the data is repaired (runbook step 8; ADR-042 d24).

## Status

The order and payment statuses are recomputed on create, fail, reissue, void and every chargeback, never on settle. Once paid: an owed refund → `partially_refunded`; all lines cancelled → `cancelled`; refunds and chargebacks cover the paid money → `refunded`; any refund or chargeback → `partially_refunded`; all lines terminal → `completed`. The payment may move back: `refunded → partially_refunded → paid`. Late-capture refunds never count.

## Late captures

- A late capture (VS-024: money for a failed or expired attempt, a cancelled order, or a wrong amount) creates one pending `late_capture` refund in the same transaction: no items, no requester, the captured amount (an overpayment is owed in full), the reported currency, never converted.
- With no reported amount (or a negative or absurd one) it uses the attempt's amount in the attempt's currency, and an unreadable currency falls back to the attempt's; both are flagged in the reason ("check the dashboard"). A zero capture creates nothing.
- `uq_refunds_one_live_late_capture` keeps one live obligation per payment against a second event or the backfill.
- Its settle, fail, reissue and void work although the order was never paid. The customer's "refund issued" notice goes out when it is settled.
- Migration `80e56abf0969` backfilled every older late capture, marked `late capture (backfill 80e56abf0969)`. It never adds one beside an existing late-capture refund of any status, and it skipped payments whose audit row was malformed: they are listed in the `refund.backfill_skipped` audit row, to be recorded by hand.
- **Record-capture** is for a provider with no status API: when the dashboard shows a capture whose amount or currency differs from an attempt that never reached paid, record it there. A matching amount is refused (`use_confirm`: use manual confirm instead). It goes through the normal late-capture path, so the alert and the obligation follow.

## Chargebacks

- **Open refunds are absorbed.** Recording one voids every pending and owed refund on its payment (`void_reason = absorbed by chargeback <id>`). Their items become the chargeback's first items, so no line's coverage changes. If the bank took less than those refunds, the rest stays owed as a new pending refund (`remainder after chargeback <id>`), of the same kind.
- **The form's `items`** add coverage on top, within each line's balance, and must total exactly the charge left after the absorbed refunds or, if that is larger, everything still refundable (otherwise 422 `CHARGEBACK_ALLOCATION_INVALID`, whose `chargeable_cents` says the total to name). A line they empty becomes `refunded` (delivered, picked up, returned, STL) or `cancelled` with no refund (unfinished physical). Anything else the bank took is `excess_cents`: it exists only once nothing is left to refund.
- **One alert per chargeback,** of kind `chargeback`, or `chargeback_excess` when there is excess. An audit row `chargeback.recorded` lists the voided and remainder refund ids.
- **On a late-captured attempt:** no items; its open `late_capture` refund is absorbed the same way. If that refund is not in USD, nothing is absorbed and the charge is all excess. No status changes.
- **Refusals:** online payments only (422 `CHARGEBACK_NOT_ONLINE`); one record per provider dispute reference (409 `CHARGEBACK_DUPLICATE`); 409 `ORDER_NOT_PAID` for an attempt that never took money.
- **Production** stays on `PAYMENT_PROVIDER=none` until VS-032, so there is nothing to charge back there yet.

## Lock order

Claim, then `orders`, every line by id, the order's payments by id, the refund(s) (`FOR UPDATE` or INSERT), then the chargeback INSERT. No path takes a lower rank after a higher one (plan §8.1); `tests/unit/payments/test_refund_writers.py` and `tests/concurrency/test_refund_lock_order.py` check it.

## Runbook

1. **A customer is owed money.** Open the order, check `refund_balance`, then record the refund with the lines and amounts. The customer is emailed now.
2. **Pay it** in the provider's dashboard, or in cash.
3. **Settle it** with the dashboard reference. The queue no longer shows it.
4. **It bounced:** mark it failed. It stays in the queue as owed; reissue it when you pay again, then settle the reissue.
5. **It was a mistake:** void it with the reason, unless it is settled or its line is already `refunded` or `cancelled` (settle or fail it instead).
6. **The queue shows a `late_capture` refund:** the provider took money that paid nothing. Check the dashboard (the reason says if the amount or currency was a guess), refund it there, then settle it here. A wrong one is voided.
7. **The bank charged back:** record the chargeback with the dispute reference and the lines it covers beyond the open refunds; a 422 tells you the exact total to name (`chargeable_cents`). Read any excess alert.
8. **A `refund_integrity` alert, or 409 `ORDER_TOTAL_MISMATCH`** (logged as `refund_integrity_error`): stop. Do not retry, and do not record that order's refunds, failures, voids or chargebacks another way. Contact the developer. The order's data is repaired only by a reviewed fix (a pull request), never by hand in the database, and there is no repair tool. You can still settle a payout you already made.
