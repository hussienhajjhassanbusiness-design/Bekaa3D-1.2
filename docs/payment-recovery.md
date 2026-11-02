# Payment recovery (VS-024)

Retry, reconciliation, the checkout hold release and manual confirmation, as built. Decisions: [ADR-036](adr/ADR-036-payment-recovery.md). Plan: [VS-024](plans/VS-024-payment-recovery-plan.md). Checkout and verification themselves: [`checkout.md`](checkout.md).

**The one rule:** an unpaid order is released automatically **only** when the provider explicitly answers `failed` or `expired` for its latest attempt. Nothing else (no answer, a timeout, `unknown`, `pending`, `processing`, an unprocessed webhook event, a provider without a status API) ever cancels an order. Those wait for the provider, for reconciliation, or for an administrator. **The `manual` provider** (VS-050, [ADR-049](adr/ADR-049-manual-payment.md)) has no one to ask: at its own deadline the job answers `expired` itself and releases the order (see [Manual payment](#manual-payment-vs-050)).

## Routes

| Route | Who | Answers |
|---|---|---|
| `POST /api/v1/me/orders/{order_id}/payments` | the order's owner, verified, CSRF, `Idempotency-Key` | `201 PaymentRetryRead` |
| `GET /api/v1/admin/payments` | admin with MFA | `200 AdminPaymentPage` (oldest first, keyset cursor) |
| `GET /api/v1/admin/payments/{payment_id}` | admin with MFA | `200 AdminPaymentDetail` |
| `POST /api/v1/admin/payments/{payment_id}/reconcile` | admin with MFA, CSRF | `202 ReconcileQueued` |
| `POST /api/v1/admin/payments/{payment_id}/confirm` | admin with MFA, CSRF | `200 ManualConfirmRead` |
| `POST /api/v1/admin/payments/{payment_id}/record-capture` | admin with MFA, CSRF, `Idempotency-Key` | `201 RecordCaptureRead`: a mismatched dashboard capture as a late capture plus its refund obligation (VS-030, [`refunds.md`](refunds.md)) |
| `POST /api/v1/admin/orders/{order_id}/release` | admin with MFA, CSRF | `200 OrderReleaseRead` |

Schemas are in [`frontend-handoff/openapi.json`](frontend-handoff/openapi.json). No admin response carries provider metadata (so no redirect URL), a webhook payload or the customer's email.

## Retry

- Allowed only before `placed_at` plus the previous attempt's hold (`checkout_hold_period`, 30 min by default, or `manual_payment_hold_period` for `manual`), on an unpaid online order whose lines are all `pending`; `409 INVALID_STATE_TRANSITION` with `reason` `cash_order`, `order_cancelled`, `order_not_payable` or `checkout_hold_expired` otherwise. An offer order (VS-041) also needs its offer still `accepted` and inside its checkout window, else `reason: offer_checkout_expired` ([ADR-037](adr/ADR-037-accepted-offer-checkout.md)).
- The new attempt charges the order's own total; the body cannot name an amount. `payment_provider` defaults to the previous attempt's, while still configured.
- A live attempt is `409 PAYMENT_ALREADY_ACTIVE` with `payment_id`, `payment_status` and `redirect_url` (null while `processing`). `payment_status`, not `status`: a problem body's `status` is the HTTP status.
- One `Idempotency-Key` is one retry of one order by one user (scope `payment_retry:{order_id}`). The `201` and the `502 PAYMENT_PROVIDER_UNAVAILABLE` are replayed for the same key.
- 10 retries per user per hour; a Redis outage refuses (503), as every limiter does.
- The provider is called after the first transaction commits, with no transaction open. The redirect URL is never logged or written to an audit row.

## The hold deadline

`hold_deadline = max(placed_at, latest attempt's initiated_at) + hold`, where `hold` is `manual_payment_hold_period` (7 days by default) when the latest attempt is `manual`, else `checkout_hold_period`. A retry restarts it, so a retry made a second before the hold ends gets a full hold of its own (at most just under two holds after placement).

## Jobs

| Job | Cadence | What it does |
|---|---|---|
| `reconcile_payments` | minutes 0, 15, 30, 45 (second 30), and at worker start | Asks the provider about each live online attempt older than 5 minutes and applies the answer. Raises `stuck` for one older than an hour (once a day), `reference_unknown`, `manual_confirmation_due` and `provider_not_configured`. |
| `release_stale_checkouts` | every 5 minutes from :02 (second 45), and at worker start | For each unpaid online order past its hold deadline: skips it if any attempt has an unprocessed event or its provider has no status API; otherwise asks about the latest attempt and releases only on `failed` / `expired`. A `paid` answer is applied (paid, or a late capture), never released. |

Both page by keyset (50 a page), never lock what they select, ask one provider at a time with a 10 s bound, stop asking a provider after 3 consecutive failures in a run (`provider_unreachable`, once an hour), and stop at 240 s (`truncated`; the next run continues). Overlapping runs are safe: every write re-checks under `orders`, the lines and the order's payments.

**A release** expires nothing by itself: it applies the provider's own answer, then sets `orders.cancelled_at`, cancels the order's `pending` lines (which frees the STL for the same customer), records history and the `order.checkout_released` audit row, and sends the customer an in-app `order.checkout_expired` notification and an `order_checkout_expired` email.

## Manual confirm

For a provider **without** a status API (or one no longer configured) only; a status provider answers `409 MANUAL_CONFIRMATION_NOT_ALLOWED` (use reconcile).

- Body: `provider_reference`, `verified_amount_cents`, `verified_currency` (`USD`), `reason` (10-1000 characters). `provider_reference` is optional for `manual` only (`422 PAYMENT_REFERENCE_REQUIRED` otherwise); it is trimmed and keeps its case. Put notes in `reason`: a given reference is unique per provider.
- An amount or currency that differs from the attempt is `422 PAYMENT_AMOUNT_MISMATCH` with `expected_amount_cents`. **Nothing is written and nothing becomes a late capture.** A customer who paid a different amount is refunded in the provider's dashboard, and the order released by hand.
- Otherwise it goes through the webhook's own apply path: a live attempt on an uncancelled order is paid; an attempt no longer live, or a cancelled order, records a late capture. A stored reference that differs, or a reference another payment owns, is `409 PAYMENT_REFERENCE_MISMATCH`. On an attempt that already holds money (paid or late-captured), the same reference or none is a `noop`, and any other reference, also where none is stored, is `409 PAYMENT_ALREADY_PAID_OTHER_REFERENCE` unless another payment has it (then `PAYMENT_REFERENCE_MISMATCH`): nothing is written (VS-050 audit A-01).
- The payment's unprocessed events are closed; the audit row `payment.manual_confirmation` keeps the typed amount, reference and reason. A double submit is `NOOP`.

## Manual release

`POST /api/v1/admin/orders/{order_id}/release`, body `reason` (10-1000 characters) and `events_reviewed`.

- For `manual`, available **at any time** (VS-050 Q3). For every other provider, from the hold deadline **plus 24 hours**; `409 INVALID_STATE_TRANSITION` with `reason: grace_not_elapsed` and `release_available_at` before that. Early only when the latest attempt has no provider reference and the provider answered `unknown` (the checkout crash window).
- With unprocessed events it needs `events_reviewed: true` (`409 … unprocessed_events` with `count` otherwise); the events are then dismissed (`processing_error = dismissed_by_admin`) and listed in the audit row.
- It expires the live attempt, then releases as the job does, with the administrator as the actor on every row. It never calls the provider.

## Reconcile (admin)

`POST /api/v1/admin/payments/{payment_id}/reconcile` answers `202` once its audit row (`payment.reconcile_requested`) has committed; the provider is asked afterwards, in a background task with no transaction open. No answer or `unknown` is recorded as `payment.reconcile_deferred` with its reason. If the task is lost, a live attempt is picked up by the next `reconcile_payments` run; for a dead attempt, ask again. A cash payment is `409`; a provider without a status API is `503 PAYMENT_VERIFICATION_UNAVAILABLE` (confirm it by hand).

## Alerts

Every active, verified administrator receives each alert as an in-app `payment.alert.<kind>` notification and an `admin_payment_alert` email (sent once VS-021 delivers email), and an error log `payment_alert` carries the kind, ids and counts. Alerts carry only the order number, reason, attempt status, provider and the amounts an admin needs: never a redirect URL, provider reference or customer contact.

| Kind | Repeats |
|---|---|
| `late_capture`, `manual_confirmation_due`, `manual_payment_due`, `release_due`, `reference_unknown` | once per payment |
| `stuck`, `event_unverified`, `provider_unavailable`, `provider_not_configured` | once a day per payment |
| `provider_unreachable` | once an hour per provider |

## Operator runbook

**A late capture** (`late_capture` alert, or `GET /api/v1/admin/payments?late_captured=true`): money arrived that cannot pay the order (the attempt was no longer live, the order was cancelled, or the amount differed). The order and its lines are untouched. Refund the captured amount (`captured_amount_cents`, `captured_currency`) in the provider's dashboard. VS-030 will make these refund obligations. The SQL listing in [`checkout.md`](checkout.md) still works.

**A stuck payment** (`stuck`): the provider keeps answering `pending` or `processing`. Check its dashboard. If it shows a capture on a no-status provider, confirm it; on a status provider, reconcile. If it shows nothing after the hold and the 24 h grace, release the order with a reason saying what you checked.

**Manual confirmation due** (`manual_confirmation_due`): a provider without a status API has an event or a live attempt. Confirm it against the dashboard (the exact amount), or release the order after the grace.

**Provider unreachable** (`provider_unreachable`): nothing is written or released while it is down; reconciliation and the release resume on their own.

## Manual payment (VS-050)

`PAYMENT_PROVIDER=manual` is V1's production provider ([ADR-049](adr/ADR-049-manual-payment.md)). The website shows no payment details; the administrator arranges each payment with the customer by WhatsApp or phone.

1. **Checkout** (cart, offer or retry) creates the order `pending_payment` with a `pending` attempt and no reference. The response's payment has `next_step: await_admin_contact` and `hold_expires_at`. An STL-only or offer order must give `contact_phone` (`422 CONTACT_PHONE_REQUIRED`); delivery and pickup already carry one. The customer gets `order.awaiting_payment` and an `order_awaiting_payment` email; every administrator gets one `manual_payment_due` alert, in the same transaction as the order. A retry onto `manual` of an order without a phone is `422 CONTACT_PHONE_REQUIRED`. A cart or offer checkout is `422 MANUAL_ORDER_LIMIT_REACHED` (with `max_open_orders`) while the customer already holds `manual_max_open_orders` (default 3) unpaid `manual` orders; a retry is not limited (BR-150, ADR-049 d14).
2. **Work list:** `GET /api/v1/admin/payments?awaiting_confirmation=true`, oldest first, with each order's `hold_expires_at`. The customer's phone and email are on `GET /api/v1/admin/orders/{order_id}`.
3. **Paid as arranged:** confirm with the exact total, the transfer's reference if there is one, and a `reason`. STL lines enter `awaiting_delivery`; physical lines may start production.
4. **A different amount** (short, over, or not USD): confirm refuses it; record-capture records it as a late capture with its refund obligation (a given reference is stored and unique, as on confirm), the attempt fails, and the customer may retry within the hold.
5. **Never paid:** the job releases the order at `hold_expires_at`; the administrator may release it earlier, with a reason. Money that arrives after a release is confirmed against the expired attempt: a late capture and its refund.

Reconciliation skips `manual`, and its webhook route answers 404. A second transfer on an attempt already paid has no record in the platform (an accepted V1 limitation, ADR-049): the administrator returns the extra money to the customer outside the system. Typing its reference on the paid attempt is refused with `409 PAYMENT_ALREADY_PAID_OTHER_REFERENCE`, which flags it without changing the attempt.

## Go-live

Production runs `PAYMENT_PROVIDER=manual` once a server exists (VS-020); alert and customer emails need VS-021. VS-032 (an API provider) is deferred. ADR-032 decision 24's main clause (VS-024 and VS-030 merged) is met; its alert clause holds only if someone reads the alerts.
