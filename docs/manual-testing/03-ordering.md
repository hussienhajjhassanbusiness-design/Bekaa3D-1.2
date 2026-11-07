# 03 — Ordering

Cart, checkout, the customer's orders, payment retry, cancellation, "I got it" / "Report a
problem", STL ownership, offer checkout, and two admin tools (order release, cash blocks).
Requirements: FR-05, FR-06, FR-09, FR-20, FR-21; BR-020 to BR-042, BR-140 to BR-150;
ADR-024, ADR-029, ADR-032, ADR-033, ADR-037, ADR-038, ADR-041, ADR-043, ADR-048, ADR-049.

Code: routers in `src/app/ordering/api/`, services in `src/app/ordering/application/services/`,
rules in `src/app/ordering/domain/` (`cart_rules.py`, `checkout_rules.py`, `cash.py`,
`payment_methods.py`, `manual_orders.py`, `order_status.py`, `cancellation.py`, `receipt.py`),
persistence in `src/app/ordering/infrastructure/`.

Who-can-call labels: see [01-identity.md](01-identity.md).

**Before you start:** log in as the seed customer, create an address (ID-44) and, for pickup
tests, set `pickup_address` as the admin (`PATCH /api/v1/admin/settings/pickup_address`,
[08-platform-admin.md](08-platform-admin.md)). Relevant settings and defaults:
`accepting_orders` (seed: true), `cash_payment_enabled` (true), `cash_max_open_orders` (1),
`cash_max_order_total` (10 000 cents), `manual_max_open_orders` (3), `checkout_hold_period`
(30 min), `manual_payment_hold_period` (7 days).

---

## Cart

One cart per customer, persisting across sessions (BR-020). Mixed STL and physical (BR-021).
One line per product; adding again merges (BR-022). STL quantity is always 1 (BR-023). A
physical line is capped by the product's **current** `max_quantity_per_line` (BR-024), never
clamped. At most 50 lines. The price is snapshotted for display only; checkout charges the live
price (BR-026). There is no total in the cart.

Code: `ordering/api/cart.py`, `api/cart_schemas.py`, `application/services/cart.py`,
`domain/cart_rules.py`, `infrastructure/carts.py`.

### `GET /api/v1/cart`

Customer; no CSRF. Never creates a cart: before the first write the answer is `id: null`.

Response `200`:

```json
{
  "id": "4b7e…",
  "items": [
    {
      "product_id": "…",
      "product_type": "physical",
      "name": "Moon Lamp",
      "slug": "moon-lamp",
      "cover_image": {"id": "…", "url": "/media/products/….png", "alt_text": null, "is_cover": true},
      "quantity": 2,
      "snapshot_price": {"amount_cents": 2400, "currency": "USD"},
      "current_price": {"amount_cents": 2400, "currency": "USD"},
      "price_changed": false,
      "max_quantity": 5,
      "over_cap": false,
      "purchasable": true,
      "unpurchasable_reason": null
    }
  ],
  "contains_physical": true,
  "contains_digital": false,
  "payment_methods": ["online", "cash"],
  "updated_at": "2026-11-07T10:00:00Z"
}
```

`payment_methods` lists what every line's product accepts (STL: online only); `[]` means the
lines share none.

### `POST /api/v1/cart/items`

Verified; CSRF; 300 cart writes per hour per user. Body `{"product_id": "…", "quantity": 1}`.
Response `200 CartRead`.

### `PATCH /api/v1/cart/items/{product_id}`

Verified; CSRF; same limit. Body `{"quantity": 3}` (absolute). Response `200 CartRead`.

### `DELETE /api/v1/cart/items/{product_id}`

Verified; CSRF; same limit. Response `204`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | `PATCH`/`DELETE` of a product not in the cart |
| 409 | `PRODUCT_ALREADY_OWNED` | adding an STL the customer owns (paid, not refunded); `product_ids` |
| 422 | `PRODUCT_NOT_PURCHASABLE` | `reason`: `not_listed` (unknown, deleted, hidden, category off), `unavailable`, `whatsapp_only` |
| 422 | `QUANTITY_EXCEEDS_LIMIT` | over the cap (STL above 1); `max_quantity`, `requested`, `current_quantity` |
| 422 | `CART_LINE_LIMIT_REACHED` | a 51st different product; `limit: 50` |
| 422 | `VALIDATION_ERROR` | quantity 0, negative, `"2"`, `1.0`; unknown field |
| 429 | `RATE_LIMITED` | over 300 writes per hour |

| ID | Test | Expected |
| --- | --- | --- |
| ORD-01 | Seed customer: `GET /cart` before any write (or after emptying) | `200`; `items: []` |
| ORD-02 | Add `moon-lamp` quantity 2 | `200`; one line, quantity 2, `max_quantity` set, `payment_methods: ["online","cash"]` |
| ORD-03 | Add `moon-lamp` quantity 1 again | quantity 3 (merged) |
| ORD-04 | Add `moon-lamp` quantity 3 (3 + 3 > the seeded cap of 5) | `422 QUANTITY_EXCEEDS_LIMIT`, `max_quantity: 5`; cart unchanged |
| ORD-05 | Add `dragon-stl` quantity 2 | `422 QUANTITY_EXCEEDS_LIMIT`, `max_quantity: 1` |
| ORD-06 | Add `dragon-stl` twice with quantity 1 | both `200`; one line, quantity 1 |
| ORD-07 | Add `name-sign` | `422 PRODUCT_NOT_PURCHASABLE`, `reason: whatsapp_only` |
| ORD-08 | Add `knight` | `422`, `reason: unavailable` |
| ORD-09 | Add `prototype-gear`'s id (admin `GET /admin/products` to find it) | `422`, `reason: not_listed` |
| ORD-10 | `PATCH` `moon-lamp` to `0` | `422 VALIDATION_ERROR` |
| ORD-11 | `DELETE` a product not in the cart | `404 NOT_FOUND` |
| ORD-12 | With `moon-lamp` and `dragon-stl` in the cart, `GET /cart` | `contains_physical` and `contains_digital` true; `payment_methods: ["online"]` |
| ORD-13 | Admin raises `moon-lamp`'s price, then customer `GET /cart` | `price_changed: true`, `current_price` new, `snapshot_price` old |
| ORD-14 | Unverified account adds to the cart | `403 EMAIL_VERIFICATION_REQUIRED`; `GET /cart` still `200` |

---

## Checkout

### `POST /api/v1/checkout`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Verified | yes | **required**: 8-255 chars of `[A-Za-z0-9._:-]` | 30 per hour per user (replays count) |

Turns the cart into an order. Prices and totals are recomputed server-side; the body never
carries an amount (BR-031). STLs the customer bought since adding them are dropped and named in
`dropped_lines`. The cart is cleared in the same transaction as the order.

- **Online** (BR-052 to BR-058): order `pending_payment`, a `pending` payment attempt with a hold.
  On `mock`, `next_step: redirect` and a `redirect_url`; on `manual`, `redirect_url: null` and
  `next_step: await_admin_contact`, a `order_awaiting_payment` email, and a `manual_payment_due`
  alert to the administrators.
- **Cash** (BR-140 to BR-145): every line physical and every product accepts cash. Order
  `in_progress`, `payment: null`, `payment_due: true`, `amount_due` = total, an
  `order_cash_placed` email. No payment row and no hold.
- The same key with the same body replays the stored `201` (or `502`) with
  `Idempotent-Replayed: true`. The same key with another body is `409 IDEMPOTENCY_KEY_CONFLICT`.

Request fields:

| Field | Rule |
| --- | --- |
| `payment_method` | `online` or `cash` |
| `payment_provider` | online only; defaults to the configured one |
| `fulfillment_method` | `delivery` or `pickup` when a kept line is physical; absent for STL-only |
| `address_id` | delivery only, required there |
| `contact_phone` | pickup (required); STL-only on `manual` (required); Lebanese, stored E.164 |
| `customer_note` | optional, ≤ 1000 |
| `accept_terms` | must be `true` |
| `accept_digital_final_sale` | `true`, required when an STL line remains (BR-060) |
| `accept_cash_terms` | `true`, required for cash |
| `accepted_price_changes` | `[{product_id, amount_cents, currency}]` to accept a changed price at exactly that amount |

Request (cash, delivery):

```json
{
  "payment_method": "cash",
  "fulfillment_method": "delivery",
  "address_id": "<your address id>",
  "accept_terms": true,
  "accept_cash_terms": true
}
```

Response `201` (cash):

```json
{
  "order": {
    "id": "9e3d…",
    "order_number": "B3D-…",
    "source": "cart",
    "status": "in_progress",
    "payment_method": "cash",
    "fulfillment_method": "delivery",
    "subtotal": {"amount_cents": 4800, "currency": "USD"},
    "tax": {"amount_cents": 0, "currency": "USD"},
    "total": {"amount_cents": 4800, "currency": "USD"},
    "placed_at": "2026-11-07T10:00:00Z",
    "estimated_dispatch_at": "2026-11-10T10:00:00Z",
    "delivery_fee_note": "The delivery fee is paid to the courier on delivery.",
    "delivery_address": {"recipient_name": "Rami Haddad", "governorate": "beqaa", "city": "Zahle", "area": "Hoch el Oumara", "street": "Main street", "landmark_notes": "Blue gate next to the bakery"},
    "payment_due": true,
    "amount_due": {"amount_cents": 4800, "currency": "USD"},
    "lines": [
      {"id": "…", "product_id": "…", "product_type": "physical", "name": "Moon Lamp", "unit_price": {"amount_cents": 2400, "currency": "USD"}, "quantity": 2, "line_total": {"amount_cents": 4800, "currency": "USD"}, "fulfillment_status": "pending"}
    ]
  },
  "payment": null,
  "dropped_lines": []
}
```

Online responses carry `"payment": {"id": "…", "status": "pending", "provider": "mock", "redirect_url": "http://localhost:3000/…", "next_step": "redirect", "hold_expires_at": "…"}`.

| Status | Code | When |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` | no session, or the account closed meanwhile |
| 403 | `CSRF_INVALID` / `EMAIL_VERIFICATION_REQUIRED` | no CSRF; unverified |
| 409 | `CART_EMPTY` | no cart, no lines, or every line already owned (`dropped_lines`) |
| 409 | `CART_PRICE_CHANGED` | a live price differs from the snapshot and is not in `accepted_price_changes`; `price_changes[{product_id, old_amount_cents, new_amount_cents, currency}]` |
| 409 | `PRODUCT_ALREADY_OWNED` | an STL is held by another of this customer's live orders; `product_ids` |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` | same key, different body |
| 409 | `IDEMPOTENCY_REQUEST_IN_PROGRESS` | same key still running; `order_id`, `order_number`, `Retry-After: 2` |
| 422 | `PRODUCT_NOT_PURCHASABLE` | a line hidden, unavailable or WhatsApp-only; `lines[{product_id, reason, max_quantity?}]` |
| 422 | `QUANTITY_EXCEEDS_LIMIT` | only over-cap lines; `lines` |
| 422 | `NO_COMMON_PAYMENT_METHOD` | kept lines share no accepted method; `lines[{product_id, accepted_payment_methods}]` |
| 422 | `PAYMENT_METHOD_NOT_ALLOWED` | `reason`: `cash_requires_physical`, `cash_not_accepted`, `online_not_accepted` (+`product_ids`), `cash_disabled`, `zero_total`, `provider_not_configured`, `provider_required`, `provider_not_applicable` |
| 422 | `INVALID_FULFILLMENT` | fulfillment fields do not fit the kept lines; unknown/foreign/deleted `address_id`; pickup with no `pickup_address` setting |
| 422 | `CONTACT_PHONE_REQUIRED` | STL-only on `manual` without `contact_phone` |
| 422 | `MANUAL_ORDER_LIMIT_REACHED` | already `manual_max_open_orders` unpaid `manual` orders; `max_open_orders` |
| 422 | `CASH_PAYMENT_LIMIT_REACHED` | `reason: order_total`: above `cash_max_order_total` |
| 422 | `CASH_NOT_AVAILABLE` | a cash block, or `cash_max_open_orders` open cash orders, for this account **or** phone; a physical line priced 0. One body for all |
| 422 | `VALIDATION_ERROR` | schema; missing `Idempotency-Key`; an amount in the body; missing `accept_digital_final_sale`/`accept_cash_terms`; bad `contact_phone` |
| 429 | `RATE_LIMITED` | over 30 per hour |
| 502 | `PAYMENT_PROVIDER_UNAVAILABLE` | order placed unpaid, the provider could not start; `order_id`, `order_number` |
| 503 | `ORDERS_PAUSED` | `accepting_orders` is off |
| 503 | `ONLINE_PAYMENT_UNAVAILABLE` | online with `PAYMENT_PROVIDER=none` |

Code: `ordering/api/checkout.py`, `api/checkout_schemas.py`, `api/idempotent.py`,
`application/services/checkout.py`, `domain/checkout_rules.py`, `domain/cash.py`,
`domain/payment_methods.py`, `domain/manual_orders.py`, `platform/infrastructure/idempotency.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ORD-15 | Cart `moon-lamp` ×2; cash delivery checkout (body above), key `ord15-cash-0001` | `201`; `status: in_progress`, `payment: null`, `amount_due` 4800; cart now empty; `order_cash_placed` in `email_outbox` |
| ORD-16 | Send ORD-15 again with the same key and body | `201` with `Idempotent-Replayed: true`; same order; no second order |
| ORD-17 | Same key, change `customer_note` | `409 IDEMPOTENCY_KEY_CONFLICT` |
| ORD-18 | Checkout without `Idempotency-Key` | `422 VALIDATION_ERROR` |
| ORD-19 | Checkout with an empty cart (new key) | `409 CART_EMPTY` |
| ORD-20 | Cart `geometric-planter`; cash checkout (new key) while ORD-15 is open | `422 CASH_NOT_AVAILABLE` (`cash_max_open_orders` = 1) |
| ORD-21 | Same cart, online delivery checkout (mock) | `201`; `pending_payment`, `payment.next_step: redirect`, `hold_expires_at` ≈ now + 30 min |
| ORD-22 | Cart `dragon-stl` + `moon-lamp`; cash | `422 PAYMENT_METHOD_NOT_ALLOWED`, `reason: cash_requires_physical` |
| ORD-23 | Cart `cable-organizer` (online only); cash | `422 PAYMENT_METHOD_NOT_ALLOWED`, `reason: cash_not_accepted`, `product_ids` |
| ORD-24 | Cart `dragon-stl`; online without `accept_digital_final_sale` | `422 VALIDATION_ERROR` on `accept_digital_final_sale` |
| ORD-25 | Cart `moon-lamp`; online with `"fulfillment_method": "delivery"` and no `address_id` | `422 INVALID_FULFILLMENT` |
| ORD-26 | Cart `moon-lamp`; pickup without `contact_phone`; and separately pickup before `pickup_address` is set | both `422 INVALID_FULFILLMENT` |
| ORD-27 | Admin raises `moon-lamp` price; checkout | `409 CART_PRICE_CHANGED` with `price_changes`; nothing charged |
| ORD-28 | Repeat with `accepted_price_changes: [{product_id, amount_cents: <new>, currency: "USD"}]` | `201` at the new price |
| ORD-29 | Add `"total_cents": 1` to the body | `422 VALIDATION_ERROR` (unknown field) |
| ORD-30 | After cancelling ORD-15 (ORD-48 style), cash order `moon-lamp` ×5 = 12 000 cents | `422 CASH_PAYMENT_LIMIT_REACHED`, `reason: order_total` |
| ORD-31 | Admin sets `accepting_orders` to false; checkout | `503 ORDERS_PAUSED`; set it back to true |
| ORD-32 | Cart `name-sign` cannot be added; instead add `moon-lamp`, then admin switches it to `whatsapp_only`; checkout | `422 PRODUCT_NOT_PURCHASABLE`, `reason: whatsapp_only` |

**Paying a mock attempt** (ORD-21): run `scripts/mock_pay.py <payment id> paid --send-to http://api:8000`
(overview §4.4). The webhook answers `200`, the order becomes `in_progress`, an
`order_payment_confirmed` email is queued. See [04-payments.md](04-payments.md).

**STL with manual payment** (`PAYMENT_PROVIDER=manual`, overview §3.3):

| ID | Test | Expected |
| --- | --- | --- |
| ORD-33 | Cart `phone-stand-stl`; online checkout with `accept_terms`, `accept_digital_final_sale`, no `contact_phone` | `422 CONTACT_PHONE_REQUIRED` |
| ORD-34 | Same with `"contact_phone": "71 123 456"` | `201`; `pending_payment`, `payment.provider: manual`, `redirect_url: null`, `next_step: await_admin_contact`, `hold_expires_at` ≈ now + 7 days; admin gets a `payment.alert.manual_payment_due` notification |
| ORD-35 | Place two more unpaid manual orders (online physical orders work: `moon-lamp`, delivery), so three are unpaid, then try a fourth | the fourth answers `422 MANUAL_ORDER_LIMIT_REACHED`, `max_open_orders: 3` |

---

## The customer's orders

### `GET /api/v1/me/orders`

Customer. Newest first. Query: `status`, `placed_after` (inclusive), `placed_before`
(exclusive) — both need a UTC offset — `cursor`, `limit` (1-100, 20). Items:
`{id, order_number, status, payment_method, fulfillment_method, payment_due, amount_due, total, placed_at}`.
Errors: `401`, `422` (bad cursor, a timestamp without offset).

### `GET /api/v1/me/orders/{order_id}`

Customer, owner only. The order as bought (snapshots, BR-033), with `can_cancel`,
`can_retry_payment`, `hold_expires_at`, `contact_phone`, `delivery_address`, `lines[]`
(`fulfillment_status` never shows `in_production`: it reads `pending`), `payment`
(`{status, provider, amount, next_step}`), `status_history[]` and `refunds[]`
(`{kind, status: processing|refunded, amount, created_at}`). Never the admin note or provider
references. Errors: `401`, `404` (unknown or another customer's).

Code: `ordering/api/orders.py`, `api/order_schemas.py`, `application/services/order_history.py`,
`domain/customer_view.py`, `infrastructure/order_history.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ORD-36 | `GET /me/orders` | ORD-15 and ORD-21 orders, newest first |
| ORD-37 | `GET /me/orders?status=pending_payment` | only unpaid online orders |
| ORD-38 | `GET /me/orders?placed_after=2026-11-01` | `422 VALIDATION_ERROR` (no time and offset); `2026-11-01T00:00:00Z` works |
| ORD-39 | `GET /me/orders/{ORD-15 id}` | `can_cancel: true`, `payment_due: true`, `payment: null`, line `pending` |
| ORD-40 | Admin moves an ORD-15 line to `in_production`; customer reads the order | the line still reads `pending`; `can_cancel: false`; no history entry for `in_production` |
| ORD-41 | A second customer reads ORD-15's id | `404 NOT_FOUND` |

### `GET /api/v1/me/stl-ownership?product_id=…`

Customer. `200 {"product_id": "…", "owned": true|false}`: a paid, unrefunded STL line of a
listed product (BR-025). Errors: `401`, `422` (missing or bad `product_id`).
Code: `ordering/api/ownership.py`, `application/services/ownership.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ORD-42 | Before paying for `dragon-stl` | `owned: false` |
| ORD-43 | After its payment is verified (mock or manual confirm) | `owned: true`; adding it to the cart now gives `409 PRODUCT_ALREADY_OWNED` |

---

## Payment retry

### `POST /api/v1/me/orders/{order_id}/payments`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Verified, owner | yes | required (scope: this order) | 10 per hour per user |

Starts a new attempt for an unpaid online order, after the previous one failed or expired
(BR-058). The amount is always the order's own total. Allowed only within
`placed_at + hold` of the previous attempt, while every line is `pending`. Body
`{"payment_provider": "mock"}` or `{}`.

Response `201`:

```json
{
  "order": {"id": "…", "order_number": "B3D-…", "status": "pending_payment", "total_cents": 1250, "currency": "USD", "hold_expires_at": "…"},
  "payment": {"id": "…", "status": "pending", "provider": "mock", "amount_cents": 1250, "currency": "USD", "redirect_url": "http://localhost:3000/…", "next_step": "redirect"}
}
```

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown or another customer's order |
| 409 | `PAYMENT_ALREADY_ACTIVE` | an attempt is `pending` or `processing`; `payment_id`, `payment_status`, `redirect_url` |
| 409 | `INVALID_STATE_TRANSITION` | `reason`: `cash_order`, `order_cancelled`, `order_not_payable`, `checkout_hold_expired`, `offer_checkout_expired` |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS` | as checkout |
| 422 | `PAYMENT_METHOD_NOT_ALLOWED` | unknown or unconfigured provider |
| 422 | `CONTACT_PHONE_REQUIRED` | retry onto `manual` of an order without a phone |
| 502 | `PAYMENT_PROVIDER_UNAVAILABLE` | the provider could not start it; the order stays unpaid |
| 503 | `ONLINE_PAYMENT_UNAVAILABLE` | `PAYMENT_PROVIDER=none` |

Code: `ordering/api/payment_retry.py`, `application/services/retry.py`,
`domain/payment_recovery.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ORD-44 | ORD-21's order while its attempt is `pending` | `409 PAYMENT_ALREADY_ACTIVE` with `payment_id` |
| ORD-45 | `mock_pay.py <id> failed`, then retry with a new key | `201`, a new pending attempt |
| ORD-46 | Retry ORD-15 (cash) | `409 INVALID_STATE_TRANSITION`, `reason: cash_order` |
| ORD-47 | Retry an order whose 30 min hold has passed | `409`, `reason: checkout_hold_expired` |

---

## Cancellation by the customer

### `POST /api/v1/me/orders/{order_id}/cancel`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Verified, owner | yes | no | 10 per hour per user |

Cancels every live physical line while **all of them are `pending`** (BR-066, BR-067), on a cash
order or one whose payment reached paid. STL lines are never self-cancellable (BR-068). A paid
order gets one pending `cancellation` refund per line for its remaining balance; an unpaid cash
order gets none. A self-cancelled cash order still counts toward `cash_max_open_orders` for
24 hours. Body optional: `{"reason": "…"}` (≤ 500). Response `200 OrderDetail`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown or another customer's order |
| 409 | `ORDER_NOT_CANCELLABLE` | printing started, an unpaid online order, an STL-only order, nothing left to cancel, or an integrity check failed (admins alerted) |
| 422 | `VALIDATION_ERROR` | reason over 500, unknown field |
| 429 | `RATE_LIMITED` | over 10 per hour |

Code: `ordering/api/cancel.py`, `fulfillment/public.py` (`cancel_order_by_customer`),
`fulfillment/application/cancel_lines.py`, `ordering/domain/cancellation.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ORD-48 | A fresh cash order, all lines `pending`: cancel | `200`; status `cancelled`; `order_cancelled` email; no refund |
| ORD-49 | Cancel it again | `409 ORDER_NOT_CANCELLABLE` |
| ORD-50 | A paid (mock) physical order, all `pending`: cancel | `200`; a `refunds[]` entry `kind: cancellation`, `status: processing`; `order_refund_issued` email |
| ORD-51 | An order after the admin moved a line to `in_production` | `409 ORDER_NOT_CANCELLABLE` |
| ORD-52 | An unpaid online order | `409 ORDER_NOT_CANCELLABLE` |
| ORD-53 | An STL-only paid order | `409 ORDER_NOT_CANCELLABLE` |
| ORD-54 | Right after ORD-48, a new cash checkout | `422 CASH_NOT_AVAILABLE` (the cancelled cash order counts for 24 h) |

---

## "I got it" and "Report a problem"

Both cover physical lines in `delivered` or `picked_up` (BR-147). Neither changes any status;
the order completes without them. Code: `ordering/api/receipt.py`,
`application/services/receipt.py`, `domain/receipt.py`.

### `POST /api/v1/me/orders/{order_id}/confirm-receipt`

Verified, owner; CSRF; no body. Stamps `receipt_confirmed_at` on received lines; a repeat changes
nothing. Response `200 OrderDetail`.

### `POST /api/v1/me/orders/{order_id}/report-problem`

Verified, owner; CSRF; 5 per hour per user. Body `{"message": "The lamp arrived cracked."}`
(1-5000 after trimming). Creates a contact message in the admin queue and an in-app alert for
every administrator; stamps `problem_reported_at` (first report). Response `201 OrderDetail`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown or another customer's order |
| 409 | `INVALID_STATE_TRANSITION` | `reason: no_delivered_line`: no physical line delivered or picked up (an STL does not count) |
| 422 | `VALIDATION_ERROR` | blank or over-long message |
| 429 | `RATE_LIMITED` | over 5 reports per hour |

| ID | Test | Expected |
| --- | --- | --- |
| ORD-55 | ORD-15 before handover: confirm receipt | `409 INVALID_STATE_TRANSITION`, `reason: no_delivered_line` |
| ORD-56 | After the cash handover (FUL tests): confirm receipt | `200`; lines have `receipt_confirmed_at`; status unchanged |
| ORD-57 | Report a problem | `201`; `problem_reported_at` set; a new item in `GET /admin/contact-messages` |
| ORD-58 | Report with `"message": "   "` | `422 VALIDATION_ERROR` |

---

## Offer checkout

### `POST /api/v1/me/offers/{offer_id}/checkout`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Verified, offer owner | yes | required (scope: this offer) | shares checkout's 30 per hour |

Places a one-line STL order at the offer's agreed price (BR-085, BR-086); the list price is
never read. Body:

```json
{"accept_terms": true, "accept_digital_final_sale": true, "payment_provider": null, "contact_phone": "+96171123456"}
```

`contact_phone` is required on `manual` and refused (`422 INVALID_FULFILLMENT`) on any other
provider. Response `201 CheckoutRead` with `order.source: "offer"`. The offer stays `accepted`
until the payment is verified, then becomes `paid`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown or another customer's offer |
| 410 | `OFFER_CHECKOUT_EXPIRED` | past `checkout_expires_at`, or already `checkout_expired` |
| 409 | `INVALID_STATE_TRANSITION` | offer not `accepted`; `offer_status` |
| 409 | `PAYMENT_ALREADY_ACTIVE` | the offer's unpaid order has a live attempt |
| 409 | `PRODUCT_ALREADY_OWNED` | the STL is owned, or the offer's unpaid order has no live attempt (retry that order instead) |
| 422 | `PRODUCT_NOT_PURCHASABLE` | the STL is hidden or unavailable |
| 422 | `CONTACT_PHONE_REQUIRED` / `INVALID_FULFILLMENT` | phone missing on `manual` / sent on another provider |
| 422 | `MANUAL_ORDER_LIMIT_REACHED` | `manual_max_open_orders` reached |
| 503 | `ORDERS_PAUSED` / `ONLINE_PAYMENT_UNAVAILABLE` | kill switch / no provider |

Code: `ordering/api/offer_checkout.py`, `application/services/offer_checkout.py`. Tests are in
[06-negotiation.md](06-negotiation.md) (NEG-20 to NEG-24).

---

## Admin: release an unpaid order

### `POST /api/v1/admin/orders/{order_id}/release`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Admin | yes | no | 30 per hour per admin |

Cancels an unpaid online order by hand: expires its live attempt, cancels its `pending` lines
(frees an STL), sends `order_checkout_expired`. On `manual` it is allowed at any time; on other
providers only from the hold deadline **plus 24 hours**. Never calls the provider. Body:

```json
{"reason": "Customer asked by phone to cancel the order.", "events_reviewed": false}
```

`reason` 10-1000 characters. Response `200`:
`{"order_id": "…", "status": "cancelled", "cancelled_at": "…", "attempts_expired": ["…"], "events_dismissed": []}`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown order |
| 409 | `INVALID_STATE_TRANSITION` | `reason`: `cash_order`, `order_cancelled`, `order_not_payable`, `grace_not_elapsed` (+ `release_available_at`), `unprocessed_events` (+ `count`; resend with `events_reviewed: true`) |
| 422 | `VALIDATION_ERROR` | reason under 10 characters |

Code: `ordering/api/admin_release.py`, `payments/infrastructure/release.py`
(`release_order_by_admin`), `payments/domain/release.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ORD-59 | `manual` order from ORD-34: release with a 10+ character reason | `200`; order `cancelled`; customer gets `order_checkout_expired`; `phone-stand-stl` can be checked out again |
| ORD-60 | Release a fresh `mock` order | `409`, `reason: grace_not_elapsed`, `release_available_at` |
| ORD-61 | Release a cash order | `409`, `reason: cash_order` |
| ORD-62 | Reason `"too short"` | `422 VALIDATION_ERROR` |

---

## Admin: cash blocks

A block is written when a cash order is cancelled with every recorded reason `refused` or
`no_show` (BR-144). It refuses cash checkout for that customer and that phone.
Code: `ordering/api/admin_cash_blocks.py`, `ordering/infrastructure/cash.py`, `domain/cash.py`.

| Method and path | Who | CSRF | Limit | Notes |
| --- | --- | --- | --- | --- |
| `GET /api/v1/admin/cash-blocks` | Admin | no | admin router | `customer_id`, `active`, `limit` (1-100, 25), `cursor`; newest first |
| `POST /api/v1/admin/cash-blocks/search` | Admin | yes | 60 per hour (shared) | body `{"phone": "71 123 456", "active": true, "limit": 25, "cursor": null}`; any spelling of a Lebanese number; audited `cash_payment_block.searched` |
| `POST /api/v1/admin/cash-blocks/{block_id}/clear` | Admin | yes | 60 per hour (shared) | sets `cleared_at`/`cleared_by`; a second clear is `200` with no change |

Each block: `{id, customer_id, order_id, order_number, reason, created_at, active, cleared_at, cleared_by}`
(never the phone). Errors: `404` (unknown block), `422` (non-Lebanese phone, bad cursor), `429`.

| ID | Test | Expected |
| --- | --- | --- |
| ORD-63 | After FUL-24 (a refused cash order): `GET /admin/cash-blocks?active=true` | one block, `reason: refused` |
| ORD-64 | Search by the order's phone written differently (`+961 71 123 456`) | the same block |
| ORD-65 | Search with `"phone": "+33612345678"` | `422 VALIDATION_ERROR` |
| ORD-66 | The blocked customer tries a cash checkout | `422 CASH_NOT_AVAILABLE` |
| ORD-67 | Clear the block, then clear it again | `200` with `active: false`; second `200` unchanged; cash checkout works again (if no open cash order) |
