# Checkout and verified payment (VS-023)

A verified customer checks out a cart of STL products and pays online; the order is paid only once the provider itself confirms the exact amount. Decisions and rationale: [ADR-032](adr/ADR-032-checkout-idempotency-and-payment-verification.md). Requirements: SRS §7.3, §7.5, §9.2, §20.1, §20.2, BR-030, BR-031, BR-056, BR-058 to BR-060. Plan: [`plans/VS-023-digital-checkout-plan.md`](plans/VS-023-digital-checkout-plan.md). Physical lines, delivery, pickup and cash arrive with VS-028; payment retry and reconciliation with VS-024; STL delivery with VS-023b. An accepted offer is checked out at its agreed price through `POST /api/v1/me/offers/{offer_id}/checkout`, which shares this route's transactions, replay and rate limit ([`offers.md`](offers.md), VS-041). Paying an STL also settles the customer's offers on it: the one bought through becomes `paid`, any other live one `auto_closed`.

## Routes

| Method + path | Auth | Success | Errors |
|---|---|---|---|
| `POST /api/v1/checkout` | Verified + `X-CSRF-Token` + `Idempotency-Key` | `201 CheckoutRead` | below |
| `GET /api/v1/me/stl-ownership?product_id=` | Signed in (unverified allowed) | `200 {product_id, owned}` | 401, 422 |
| `POST /api/v1/webhooks/payments/{provider}` | The provider: HMAC signature, no cookies | `200 {received: true}` | 400, 401, 404, 429 |

## `POST /api/v1/checkout`

**Request** (`extra="forbid"`: no amount, total or price is ever accepted):

```text
payment_method: "online" | "cash"          # cash -> 422 PAYMENT_METHOD_NOT_ALLOWED until VS-028
payment_provider?: str                     # default: the one configured provider
fulfillment_method? / address_id? / contact_phone?   # any of them -> 422 INVALID_FULFILLMENT
customer_note?: str (<= 1000)
accept_terms: true
accept_digital_final_sale?: true           # required when an STL line remains
accept_cash_terms?: true                   # accepted and ignored for online orders
accepted_price_changes?: [{product_id, amount_cents, currency}]   # <= 50
```

Header `Idempotency-Key`: 8-255 characters of `[A-Za-z0-9._:-]`. One key per "Place order" press and all its automatic retries; a new key after any change.

**Response `201`:** the order (`pending_payment`, live prices, lines `pending`), the payment (`pending`, provider, `redirect_url` to the provider's page) and `dropped_lines` (STLs bought since they were added, not charged). A replay of the same key and body returns the stored response with `Idempotent-Replayed: true`.

**Errors:**

| Status | Code | When |
|---|---|---|
| 409 | `CART_EMPTY` | no cart, no lines, or every line already owned (`dropped_lines` names them) |
| 409 | `CART_PRICE_CHANGED` | a live price differs from the cart snapshot and was not accepted at exactly that amount; `price_changes[{product_id, old_amount_cents, new_amount_cents, currency}]`; nothing is charged |
| 409 | `PRODUCT_ALREADY_OWNED` | an STL is held by another live order of this customer; `product_ids` |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` | same key, different body |
| 409 | `IDEMPOTENCY_REQUEST_IN_PROGRESS` | same key and body still running, or crashed between placing the order and starting the payment; `order_id`, `order_number`, `Retry-After: 2` |
| 422 | `PRODUCT_NOT_PURCHASABLE` | any line hidden, unavailable or WhatsApp-only (over-cap lines are listed too); `lines[{product_id, reason, max_quantity?}]` |
| 422 | `QUANTITY_EXCEEDS_LIMIT` | only over-cap lines; same `lines` |
| 422 | `INVALID_FULFILLMENT` | a physical line, or any fulfillment field |
| 422 | `PAYMENT_METHOD_NOT_ALLOWED` | `reason`: `cash_requires_physical`, `provider_not_configured`, `provider_required`, `zero_total` |
| 422 | `VALIDATION_ERROR` | schema, a client-sent total, or a missing `accept_digital_final_sale` |
| 429 | `RATE_LIMITED` | 30 checkouts per user per hour (a replay counts) |
| 502 | `PAYMENT_PROVIDER_UNAVAILABLE` | the order exists unpaid; the provider could not start the payment; `order_id`, `order_number`; replayed for the same key |
| 503 | `ORDERS_PAUSED` | `accepting_orders` is off |
| 503 | `ONLINE_PAYMENT_UNAVAILABLE` | `PAYMENT_PROVIDER=none`; nothing written |

Every refusal before the order commits leaves the cart, the order tables and the idempotency key untouched.

**Two transactions.** The first claims the key, locks the cart, revalidates every line, inserts the order, lines, pending payment, history and audit row, and clears the cart. The provider is then called with no transaction open (10 s timeout). The second stores the provider reference, or fails the attempt.

**A stuck claim** (a crash between the two): the order stays `pending_payment` with its pending attempt; for 24 h the key answers `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` naming the order; after the daily purge the same key is a new request, and the cart is already empty, so it gets `409 CART_EMPTY`. Recovery is VS-024's reconciliation and payment retry ([`payment-recovery.md`](payment-recovery.md)).

## Webhook and verification

1. A provider that is not configured here is `404`; nothing is stored and no bucket is spent.
2. A body over 64 KiB is `400`, refused before the signature is checked.
3. A bad signature is `401 WEBHOOK_SIGNATURE_INVALID`, not stored, and counted against 30 per minute per IP.
4. A good signature counts against 600 per minute per provider; the event is stored once per `(provider, event_id)` and answered `200`.
5. After the response, the backend asks the provider for the payment's status itself; the webhook body is never trusted. The `verify_payments` job retries every minute.
6. **Paid** needs the captured amount to equal the order total in USD on a live attempt of an uncancelled order. Then the STL lines move to `awaiting_delivery`, the order to `in_progress`, and the customer gets an email and a `payment.confirmed` notification.
7. Any other capture is a **late capture**: the attempt is marked, an audit row `payment.late_capture` and an error log record why, and the lines are untouched.

**Delay from webhook to paid:** typically one provider query after the `200` (0.16 s against the mock); at worst about 60 s when the background task is lost, and up to about 560 s with a degraded provider.

**Late captures until VS-030.** Each one raises a `late_capture` alert to every administrator and is listed by `GET /api/v1/admin/payments?late_captured=true` (VS-024, [`payment-recovery.md`](payment-recovery.md)). This SQL listing still works, run by an operator:

```sql
SELECT id, order_id, provider, amount_cents, status, late_captured_at
FROM payments WHERE late_captured_at IS NOT NULL ORDER BY late_captured_at;
```

Each late capture also has an audit row (`payment.late_capture`, with its reason). VS-030 turns late captures into refund obligations.

**Go-live gate:** no real online provider is configured in production before VS-024 and VS-030 are merged, unless an operational alert on late captures and stuck payments exists (ADR-032). VS-024's alerts meet that clause only if someone reads them ([ADR-036](adr/ADR-036-payment-recovery.md)). Production accepts only `PAYMENT_PROVIDER=none` until VS-032 adds a real adapter.

## The mock provider (development)

- `PAYMENT_PROVIDER=mock` boots only in development and test, or in staging with its own `MOCK_WEBHOOK_SECRET`; boot refuses it anywhere else, in the API and the worker alike.
- Checkout redirects to `{FRONTEND_BASE_URL}/checkout/return?order=<order_number>`.
- Nothing reachable over HTTP pays a mock payment. To pay one locally:

```text
docker compose run --rm -T -e PYTHONPATH=src api python - <payment_id> paid --send-to http://api:8000 < scripts/mock_pay.py
```

States: `paid` (add `--captured-amount-cents N` for an under- or overpayment), `processing`, `failed`, `expired`. The script refuses production and the default secret outside development and test.

## Concurrency

Lock order (ADR-024 d9, ADR-029 d4): checkout locks the idempotency key, then the cart, and only inserts new order rows; payment apply locks the order, its lines by id, then the payment. There is no cycle (`tests/concurrency/test_checkout_races.py`, `test_payment_races.py`).

## Database

`orders`, `order_items`, `order_status_history`, `payments`, `webhook_events`, `idempotency_records` (migration `03a4730dd046`, database-design §8.3-§8.5, §9.1, §9.2, §13.4). Jobs: `verify_payments` (every minute) and `purge_expired_idempotency_records` (daily 03:53).
