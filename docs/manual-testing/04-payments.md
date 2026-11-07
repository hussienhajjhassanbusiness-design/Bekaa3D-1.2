# 04 — Payments

Provider webhooks and verification, the admin payment tools (list, detail, reconcile, manual
confirm, record a late capture), refunds and chargebacks. Requirements: FR-07, FR-10;
BR-052 to BR-064, BR-150; ADR-032, ADR-036, ADR-042, ADR-049.

**The rules that matter most:** a webhook is only a hint (BR-053); `paid` needs independent
verification with the exact amount (BR-054, BR-055); the platform never moves money: every
refund is recorded, paid outside the platform, then settled (BR-063).

Code: routers in `src/app/payments/api/`, services in `src/app/payments/application/services/`
(`apply.py`, `payments.py`, `refunds.py`, `chargebacks.py`, `webhooks.py`), rules in
`src/app/payments/domain/` (`payments.py`, `outcome.py`, `manual.py`, `refunds.py`,
`chargebacks.py`, `release.py`, `alerts.py`, `limits.py`), adapters in
`src/app/payments/infrastructure/providers/` (`mock`, `manual`).

Who-can-call labels: see [01-identity.md](01-identity.md). Payment states: `pending`,
`processing`, `paid`, `partially_refunded`, `refunded`, `failed`, `expired`. Refund states:
`pending`, `settled`, `failed` (still owed), `voided`. Refund kinds: `admin`, `cancellation`,
`late_capture`.

---

## Webhook

### `POST /api/v1/webhooks/payments/{provider}`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| The provider (HMAC signature; no cookies) | no | no (idempotent by `(provider, event_id)`) | bad signatures 30 per minute per IP; good ones 600 per minute per provider |

Stores the event once and answers `200 {"received": true}`; **after** the response the server
asks the provider for the payment's real status. Only an exact capture on a live attempt of an
uncancelled order pays it; anything else is a **late capture** (audit `payment.late_capture`,
a `late_capture` alert, and one pending `late_capture` refund). The `verify_payments` job retries
lost verifications every minute. Paying moves STL lines to `awaiting_delivery`, the order to
`in_progress`, closes the customer's live offers on that STL, and queues `order_payment_confirmed`.

The mock signs with `X-Mock-Signature`. Body:
`{"event_id": "ev_…", "type": "payment.updated", "payment_reference": "<payment id>"}`.

| Status | Code | When |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | body over 64 KiB, or a signed body that cannot be read |
| 401 | `WEBHOOK_SIGNATURE_INVALID` | bad or missing signature; nothing stored |
| 404 | `NOT_FOUND` | provider not configured, or one that takes no webhooks (`manual`, `cash`) |
| 429 | `RATE_LIMITED` | over either limit |

Code: `payments/api/webhooks.py`, `application/services/webhooks.py`,
`application/services/apply.py`, `infrastructure/verification.py`, `jobs/verify_payments.py`.

| ID | Test | Expected |
| --- | --- | --- |
| PAY-01 | (`mock`) An online order from ORD-21: `mock_pay.py <payment id> paid --send-to http://api:8000` | script prints `webhook answered 200`; order `in_progress`; payment `paid`; `order_payment_confirmed` in the outbox |
| PAY-02 | Run the script again with `paid` for the same payment | `200` again; nothing paid twice; still one `paid` payment |
| PAY-03 | `curl -X POST http://localhost:8000/api/v1/webhooks/payments/mock -H "Content-Type: application/json" -d '{"event_id":"x","type":"payment.updated","payment_reference":"<id>"}'` (no signature) | `401 WEBHOOK_SIGNATURE_INVALID`; nothing stored |
| PAY-04 | `POST /webhooks/payments/whish` (or `manual`) with any body | `404 NOT_FOUND` |
| PAY-05 | Online checkout of `test-stl-b` (CAT-52); `mock_pay.py <id> paid --captured-amount-cents 1 --send-to …` | late capture: order stays `pending_payment`; `GET /admin/payments?late_captured=true` lists it; a `late_capture` refund appears in `GET /admin/refunds` |
| PAY-06 | Online checkout of `test-stl-a` (CAT-52), pay it with `mock_pay.py … paid`, then `GET /me/stl-ownership?product_id=<test-stl-a>` | `owned: true`; the line is `awaiting_delivery` |

---

## Admin payments

Under the admin boundary. Code: `payments/api/admin_payments.py`,
`infrastructure/admin_reads.py`, `infrastructure/manual.py`, `infrastructure/reconcile.py`.

### `GET /api/v1/admin/payments`

Admin. Oldest first, keyset cursor. Query: `status` (repeatable), `provider`, `order_id`,
`late_captured`, `awaiting_confirmation` (`true`: the `manual` payments to arrange and confirm,
with each order's `hold_expires_at`), `initiated_after`, `initiated_before` (UTC offset
required), `cursor`, `limit` (1-100, 20).

Item: `{id, order_id, order_number, provider, status, amount_cents, currency,
captured_amount_cents, captured_currency, provider_payment_id, initiated_at, verified_at,
failed_at, expired_at, late_captured_at, needs_manual_confirmation, unprocessed_event_count,
hold_expires_at}`. Never a redirect URL or customer contact. Errors: `401`, `404`, `422`.

### `GET /api/v1/admin/payments/{payment_id}`

Admin. `{payment, order, events[] (no payloads), history[], available_actions}` where
`available_actions` ⊆ `reconcile`, `confirm`, `release_order`. `404` for an unknown id.

### `POST /api/v1/admin/payments/{payment_id}/reconcile`

Admin; CSRF; 60 per hour per admin. Answers **`202`**
`{"payment": {…}, "reconcile": "queued"}` once the audit row `payment.reconcile_requested` is
committed; the provider is asked afterwards in the background.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown payment |
| 409 | `INVALID_STATE_TRANSITION` | `reason: cash_payment` |
| 503 | `PAYMENT_VERIFICATION_UNAVAILABLE` | the provider has no status API (`manual`): confirm by hand |

### `POST /api/v1/admin/payments/{payment_id}/confirm`

Admin; CSRF; 30 per hour per admin. Confirms a payment by hand, for a provider **without** a
status API (`manual`, BR-054). Goes through the webhook's own apply path.

Request:

```json
{
  "provider_reference": "WISH-778812",
  "verified_amount_cents": 350,
  "verified_currency": "USD",
  "reason": "Paid by Whish transfer, checked in the app."
}
```

`provider_reference` is optional for `manual` only (unique per provider when given); `reason`
10-1000 characters. Response `200`: `{"outcome": "apply_paid", "payment": {…}}`. `outcome` is one
of `apply_paid`, `late_capture`, `late_capture_and_fail`, `noop`, ….

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown payment |
| 409 | `INVALID_STATE_TRANSITION` | `reason: cash_payment` |
| 409 | `MANUAL_CONFIRMATION_NOT_ALLOWED` | the provider has a status API (`mock`): reconcile instead |
| 409 | `PAYMENT_REFERENCE_MISMATCH` | the reference belongs to another payment, or this one stores another |
| 409 | `PAYMENT_ALREADY_PAID_OTHER_REFERENCE` | a `manual` attempt already holding money, a new reference (maybe a second transfer); nothing written |
| 422 | `PAYMENT_AMOUNT_MISMATCH` | amount or currency differs from the attempt; `expected_amount_cents`; nothing written |
| 422 | `PAYMENT_REFERENCE_REQUIRED` | no reference on a non-`manual` provider |
| 422 | `VALIDATION_ERROR` | reason under 10 characters, negative amount |

### `POST /api/v1/admin/payments/{payment_id}/record-capture`

Admin; CSRF; **`Idempotency-Key` required**; 30 per hour per admin. Records a capture the
provider's dashboard shows with an amount or currency **different** from an attempt that never
reached paid. It becomes a late capture with its pending `late_capture` refund; the attempt
fails so the customer may retry.

Request: `{"captured_amount_cents": 300, "captured_currency": "USD", "dashboard_reference": "WISH-1", "reason": "Customer sent 3 USD instead of 3.50."}`.
Response `201`: `{"outcome": "late_capture_and_fail", "payment": {…}, "refund_id": "…"}`.

| Status | Code | When |
| --- | --- | --- |
| 409 | `INVALID_STATE_TRANSITION` | `reason`: `cash_payment`, `already_paid`, `already_late_captured`, `use_confirm` (the amount matches: confirm instead) |
| 409 | `MANUAL_CONFIRMATION_NOT_ALLOWED` | provider with a status API |
| 409 | `PAYMENT_REFERENCE_MISMATCH` | reference owned by another payment |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS` | key reuse |
| 422 | `PAYMENT_REFERENCE_REQUIRED` / `VALIDATION_ERROR` | no reference off `manual`; zero amount, lower-case currency |

| ID | Test | Expected |
| --- | --- | --- |
| PAY-07 | (`manual`) Admin: `GET /admin/payments?awaiting_confirmation=true` | ORD-34's payment, with `hold_expires_at` |
| PAY-08 | Confirm it with the exact total and a 10+ character reason | `200`, `outcome: apply_paid`; order `in_progress`; STL line `awaiting_delivery`; customer `order_payment_confirmed` email |
| PAY-09 | Confirm it again with the same reference | `200`, `outcome: noop` |
| PAY-10 | Confirm it again with another reference | `409 PAYMENT_ALREADY_PAID_OTHER_REFERENCE` |
| PAY-11 | One of ORD-35's unpaid manual orders: confirm with 1 cent less | `422 PAYMENT_AMOUNT_MISMATCH`, `expected_amount_cents`; nothing written |
| PAY-12 | Same order: record-capture with the smaller amount (new key) | `201`, a `refund_id`; payment `failed`, `late_captured_at` set; the refund is in the queue |
| PAY-13 | ORD-35's other unpaid manual order: record-capture with its exact amount | `409 INVALID_STATE_TRANSITION`, `reason: use_confirm` |
| PAY-14 | (`manual`) Reconcile a manual payment | `503 PAYMENT_VERIFICATION_UNAVAILABLE` |
| PAY-15 | (`mock`) Confirm a mock payment | `409 MANUAL_CONFIRMATION_NOT_ALLOWED` |
| PAY-16 | (`mock`) Reconcile a mock payment | `202`, `reconcile: queued`; detail `history` shows `payment.reconcile_requested` |
| PAY-17 | Reason `"ok"` on confirm | `422 VALIDATION_ERROR` |
| PAY-18 | `GET /admin/payments?initiated_after=2026-11-01` | `422` (needs a time and offset) |

---

## Refunds

Every route is admin-only. Writes need CSRF and share 60 per hour per admin; reads 300 per hour.
A line's **balance** is its total minus its pending, settled and owed refunds and chargebacks;
the payment's balance likewise. Code: `payments/api/admin_refunds.py`,
`application/services/refunds.py`, `domain/refunds.py`, `infrastructure/refunds.py`,
`infrastructure/refund_views.py`.

### `POST /api/v1/admin/orders/{order_id}/refunds`

Admin; CSRF; **`Idempotency-Key` required**. Records a pending `admin` refund on a paid order
(BR-061, BR-062). Partial and per line; a line covered in full becomes `refunded` if it is
delivered, picked up, returned or an STL (an STL awaiting delivery leaves the queue and frees
ownership, BR-064). The customer is emailed `order_refund_issued`.

Request:

```json
{
  "items": [{"order_item_id": "<line id>", "amount_cents": 1200}],
  "reason": "Lamp arrived cracked; partial refund agreed."
}
```

Response `201` `RefundDetail`:

```json
{
  "id": "…", "order_id": "…", "order_number": "B3D-…", "customer_id": "…",
  "payment_id": "…", "payment_provider": "mock", "kind": "admin", "status": "pending",
  "owed": false, "amount_cents": 1200, "currency": "USD",
  "reason": "Lamp arrived cracked; partial refund agreed.",
  "requested_by": "<admin id>", "approved_by": "<admin id>",
  "items": [{"order_item_id": "…", "product_name": "Moon Lamp", "amount_cents": 1200}],
  "reissue_of_refund_id": null, "reissued_by_refund_id": null, "reissued_at": null,
  "settled_at": null, "settled_by": null, "settlement_reference": null, "settlement_note": null,
  "failed_at": null, "failed_by": null, "failure_reason": null,
  "voided_at": null, "voided_by": null, "void_reason": null,
  "created_at": "2026-11-07T10:00:00Z"
}
```

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown order, or a line not on it |
| 409 | `ORDER_NOT_PAID` | nothing was paid (unpaid online, unpaid cash) |
| 409 | `ORDER_TOTAL_MISMATCH` | the order's data does not add up; nothing written; a `refund_integrity` alert. Stop and call the developer |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS` | key reuse |
| 422 | `REFUND_EXCEEDS_AVAILABLE` | an item over its line's balance, or the total over the payment's; `available` |
| 422 | `REFUND_REQUIRES_CANCELLATION` | it would empty an unfinished physical line (`pending` … `ready_for_pickup`): cancel it instead; `order_item_ids` |
| 422 | `VALIDATION_ERROR` | no items, amount 0, blank reason |

### `POST /api/v1/admin/refunds/{refund_id}/settle`

Admin; CSRF. `pending → settled` after paying outside the platform. Body
`{"reference": "dashboard ref", "note": "optional"}` (both optional). A repeat answers `200`
unchanged. Order and payment statuses do not move. `200 RefundDetail`.

### `POST /api/v1/admin/refunds/{refund_id}/fail`

Admin; CSRF. `pending → failed`: it stays **owed** (`owed: true`) in the queue. Body
`{"reason": "Transfer bounced."}`. `200 RefundDetail`.

### `POST /api/v1/admin/refunds/{refund_id}/reissue`

Admin; CSRF; **`Idempotency-Key` required**. A failed refund gets a new pending twin (same kind,
items, amount). `201 RefundDetail` (the twin; the original shows `reissued_by_refund_id`).

### `POST /api/v1/admin/refunds/{refund_id}/void`

Admin; CSRF. Closes a refund created by mistake, unpaid. Body `{"reason": "Entered twice."}`.
The customer gets `order_refund_cancelled` (without the reason). A second void answers `200`
with the first reason and tells no one. `200 RefundDetail`.

Transition errors (settle, fail, reissue, void):

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown refund |
| 409 | `INVALID_STATE_TRANSITION` | `reason`: `not_pending`, `not_failed`, `already_settled`, `already_reissued` (+ `reissued_by_refund_id`), `line_already_refunded`, `line_already_cancelled` |
| 409 | `ORDER_TOTAL_MISMATCH` | as above (not on settle) |

### `GET /api/v1/admin/refunds`

Admin. `queue=true` (default): pending and owed, oldest first; `queue=false`: history, newest
first. Filters: `status` (repeatable), `kind` (repeatable), `order_id`, `customer_id`,
`created_from`, `created_to`, `cursor`, `limit`. `200 {items: [RefundDetail], next_cursor}`.

### `GET /api/v1/admin/refunds/{refund_id}`

Admin. `200 RefundDetail`; `404`.

| ID | Test | Expected |
| --- | --- | --- |
| PAY-19 | ORD-15 after its cash handover (FUL-20; line `delivered`, 4800): refund 1200 of the line, new key | `201`, `pending`; order `partially_refunded`; the customer's `GET /me/orders/{id}` shows `refunds[]` `processing` |
| PAY-20 | Same body, same key | `201` replayed (`Idempotent-Replayed: true`); still one refund |
| PAY-21 | Refund 5000 on that line | `422 REFUND_EXCEEDS_AVAILABLE`, `available` |
| PAY-22 | A paid order whose line is still `pending`: refund the whole line | `422 REFUND_REQUIRES_CANCELLATION` |
| PAY-23 | Refund on an unpaid cash order | `409 ORDER_NOT_PAID` |
| PAY-24 | Settle PAY-19's refund with a reference | `200`, `settled`; gone from `GET /admin/refunds`; listed with `queue=false`; customer sees `refunded` |
| PAY-25 | Settle it again | `200`, unchanged |
| PAY-26 | Another refund: fail it | `200`, `failed`, `owed: true`; still in the queue |
| PAY-27 | Reissue it (new key) | `201`, a new `pending` refund; the old one has `reissued_by_refund_id` |
| PAY-28 | Reissue the old one again (another key) | `409 INVALID_STATE_TRANSITION`, `reason: already_reissued` |
| PAY-29 | Void the new pending refund | `200`, `voided`; customer gets `order_refund_cancelled` |
| PAY-30 | Void a settled refund | `409 INVALID_STATE_TRANSITION`, `reason: already_settled` |
| PAY-31 | Refund the full balance of a delivered line | the line becomes `refunded`; when every line is covered the order becomes `refunded` |
| PAY-32 | Settle the PAY-05 `late_capture` refund | `200`; the order (never paid) is unchanged |

---

## Chargebacks

A chargeback is its own record, never a refund (ADR-042). Recording one **voids every pending and
owed refund** on the payment and absorbs their items; `items` add coverage beyond that. Online
payments only. Code: `payments/api/admin_chargebacks.py`, `application/services/chargebacks.py`,
`domain/chargebacks.py`, `infrastructure/chargebacks.py`.

### `POST /api/v1/admin/orders/{order_id}/chargebacks`

Admin; CSRF; **`Idempotency-Key` required**; shares the refund write limit.

Request:

```json
{
  "payment_id": "<payment id>",
  "provider_dispute_reference": "DSP-2026-0012",
  "charged_cents": 2400,
  "items": [{"order_item_id": "<line id>", "amount_cents": 2400}],
  "reason": "Bank reversed the transfer.",
  "received_at": "2026-11-07T09:00:00Z"
}
```

Response `201`:
`{"id": "…", "order_id": "…", "order_number": "…", "payment_id": "…", "payment_provider": "mock", "provider_dispute_reference": "DSP-2026-0012", "charged_cents": 2400, "applied_cents": 2400, "excess_cents": 0, "currency": "USD", "reason": "…", "recorded_by": "…", "received_at": "…", "created_at": "…", "items": [...]}`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown order or payment |
| 409 | `ORDER_NOT_PAID` | the attempt never took money |
| 409 | `CHARGEBACK_DUPLICATE` | this dispute reference is already recorded |
| 409 | `ORDER_TOTAL_MISMATCH` | integrity failure |
| 422 | `CHARGEBACK_NOT_ONLINE` | a cash payment |
| 422 | `CHARGEBACK_ITEMS_FORBIDDEN` | items on a late-captured attempt |
| 422 | `CHARGEBACK_ALLOCATION_INVALID` | items exceed a line's balance or do not total the chargeable amount; `chargeable_cents` |
| 422 | `VALIDATION_ERROR` | duplicate `order_item_id`, `received_at` without offset |

### `GET /api/v1/admin/orders/{order_id}/chargebacks` and `GET /api/v1/admin/chargebacks/{chargeback_id}`

Admin. The order's chargebacks oldest first (a list), or one. `404` for unknown ids.

| ID | Test | Expected |
| --- | --- | --- |
| PAY-33 | ORD-21's paid (mock) order, its line delivered in FUL-17: record a refund for part of the line (leave it pending), then a chargeback for the payment's full amount with items covering the rest | `201`; the pending refund is now `voided` with `void_reason` "absorbed by chargeback …"; order `refunded` |
| PAY-34 | Same dispute reference again (new key) | `409 CHARGEBACK_DUPLICATE` |
| PAY-35 | Items totalling less than the chargeable amount | `422 CHARGEBACK_ALLOCATION_INVALID` with `chargeable_cents` |
| PAY-36 | Chargeback on a cash payment | `422 CHARGEBACK_NOT_ONLINE` |
| PAY-37 | `GET /admin/orders/{id}/chargebacks` | the PAY-33 chargeback; it never appears in `GET /admin/refunds` |
