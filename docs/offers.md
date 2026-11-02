# Offers (VS-039, VS-040, VS-041)

The contract for offer submission, negotiation, offer reads and expiry. Decisions and their reasons: [ADR-034](adr/ADR-034-offer-submission-and-expiry.md) (submission, expiry) and [ADR-035](adr/ADR-035-offer-negotiation.md) (negotiation). Offer checkout and auto-close: [ADR-037](adr/ADR-037-accepted-offer-checkout.md). Shapes: [`api-endpoints.md`](requirments/api-endpoints.md) §13, §21 and `OfferDetail`, and the OpenAPI file in [`frontend-handoff/`](frontend-handoff/openapi.json).

## `POST /api/v1/offers`

Verified email, CSRF header, 20 per user per hour.

```json
{"product_id": "…", "amount_cents": 800, "currency": "USD", "message": "optional"}
```

`201` returns `OfferDetail`:
- the status is `awaiting_admin` and the turn is `admin`;
- `responds_by` is now + `offer_response_window`, 48 h by default;
- round 1 is `customer` / `submitted`.

Every active administrator gets an in-app `offer` notification.

| Refusal | Status and code |
|---|---|
| Shop paused (`accepting_orders` off) | `503 ORDERS_PAUSED` |
| Physical product | `422 PRODUCT_NOT_PURCHASABLE`, `reason: not_negotiable` |
| Unknown, hidden or deleted product | `422 PRODUCT_NOT_PURCHASABLE`, `reason: not_listed` |
| Unavailable STL | `422 PRODUCT_NOT_PURCHASABLE`, `reason: unavailable` |
| STL already owned (paid, not refunded) | `409 PRODUCT_ALREADY_OWNED` |
| Below `minimum_offer_percentage` of the list price | `422 OFFER_BELOW_MINIMUM`, with `minimum: {amount_cents, currency}` |
| Above the list price | `422 VALIDATION_ERROR` on `amount_cents` |
| A live offer (`awaiting_admin`, `awaiting_customer`, `accepted`) on this product | `409 OFFER_ALREADY_ACTIVE` |
| A rejection's cooldown has not ended | `422 OFFER_COOLDOWN_ACTIVE`, with `cooldown_until` |
| Bad body: amount ≤ 0 or not an integer, currency not `USD`, message over 1 000 characters after trimming or containing control characters, unknown field | `422 VALIDATION_ERROR` |
| Anonymous / unverified / no CSRF / over the limit | `401` / `403 EMAIL_VERIFICATION_REQUIRED` / `403 CSRF_INVALID` / `429 RATE_LIMITED` |

A refused submission writes nothing.

## `GET /api/v1/me/offers` and `GET /api/v1/me/offers/{offer_id}`

A session is enough; an unverified customer can read. The list is newest first. It filters by `status` and `product_id`, and pages with `cursor` and `limit` (1-100, default 20). A malformed cursor is `422`. Another customer's offer is the same `404` as an unknown id.

The list rows are `OfferSummary`:
- `id`, `product {id, name, slug, cover_image}`, `status`, `turn`;
- `current_amount`, `agreed_amount`, `responds_by`, `checkout_expires_at`, `created_at`.

The detail adds:
- `initial_amount`, `cooldown_until`, `updated_at`;
- `rounds[]`, each `{sequence, actor, action, amount, message, created_at}`;
- `allowed_actions`: what the caller may do now (see below).

## `GET /api/v1/admin/offers` and `GET /api/v1/admin/offers/{offer_id}`

These sit behind the admin boundary: anonymous gets `401`, a customer `404`, an administrator without MFA `401`. Each row and the detail add `customer {id, email}`.

The queue order:
1. `awaiting_admin`, soonest `responds_by` first;
2. `awaiting_customer`, soonest `responds_by` first;
3. `accepted`;
4. closed offers, oldest first.

Filters: `status`, `product_id`, `user_id`, and `responds_before`. `responds_before` matches only pending offers (`awaiting_*`) whose deadline is before it. It is exclusive and needs a UTC offset. A naive timestamp or a tampered cursor is `422`.

## Answering an offer (VS-040)

| Route | Who | Allowed from | Body |
|---|---|---|---|
| `POST /api/v1/me/offers/{id}/counter` | the customer | `awaiting_customer` | `{amount_cents, currency, message?}` |
| `POST /api/v1/me/offers/{id}/accept` | the customer | `awaiting_customer` | `{expected_amount_cents}` |
| `POST /api/v1/me/offers/{id}/withdraw` | the customer | either awaiting state, whoever's turn | `{reason?}` or none |
| `POST /api/v1/admin/offers/{id}/counter` | an administrator | `awaiting_admin` | `{amount_cents, currency, message?}` |
| `POST /api/v1/admin/offers/{id}/accept` | an administrator | `awaiting_admin` | `{expected_amount_cents}` |
| `POST /api/v1/admin/offers/{id}/reject` | an administrator | `awaiting_admin` | `{reason?}` or none |

Each returns `200` with the offer detail (`AdminOfferDetail` on admin routes).

**Guards.**
- Customer routes need a verified email and CSRF, with 60 actions per user per hour.
- Admin routes sit behind the admin boundary and need CSRF.

**What each action does.** Every action locks the offer and appends a round.
- **Counter:**
  - switches the turn and sets `responds_by` to now + `offer_response_window` (48 h by default);
  - must be at most today's list price;
  - a customer's counter must also meet `minimum_offer_percentage`; an administrator's needn't.
- **Accept:**
  - names `expected_amount_cents`, the `current_amount` the caller's page showed. Any other value is refused, so a stale page never binds either party to an amount other than the one it showed, apart from the list-price cap below (ADR-035 d9);
  - freezes `agreed_amount = min(amount on the table, today's list price)`;
  - sets `checkout_expires_at` to now + `offer_checkout_window` (24 h by default);
  - clears `responds_by`, since the inactivity timer no longer applies.
- **Reject:** sets `cooldown_until` to now + `offer_rejection_cooldown` (7 days by default; 0 means none).
- **Withdraw:** closes the offer.

`allowed_actions` is:

| Status | The customer sees | An administrator sees |
|---|---|---|
| `awaiting_admin` | `["withdraw"]` | `["counter", "accept", "reject"]` |
| `awaiting_customer` | `["counter", "accept", "withdraw"]` | `[]` |
| Any other status, or the deadline reached | `[]` | `[]` |

| Refusal (checked in this order) | Status and code |
|---|---|
| Unknown, or another customer's | `404` |
| `expired`, or awaiting with `now >= responds_by` | `410 OFFER_EXPIRED` |
| Any other closed status, or `accepted` | `409 INVALID_STATE_TRANSITION`, with `offer_status` |
| The other party's turn | `409 OFFER_NOT_YOUR_TURN` |
| Accept whose `expected_amount_cents` is not `current_amount` | `409 OFFER_AMOUNT_CHANGED`, with `current_amount: {amount_cents, currency}` |
| Counter or accept on an unlisted, unavailable or zero-priced product | `422 PRODUCT_NOT_PURCHASABLE`, with `reason` |
| Accept when the customer already owns the STL | `409 PRODUCT_ALREADY_OWNED` |
| Customer counter below the floor | `422 OFFER_BELOW_MINIMUM`, with `minimum` |
| Counter above today's list price; bad body, including an accept without `expected_amount_cents` | `422 VALIDATION_ERROR` |

A refused action writes nothing. The kill switch never blocks an answer.

**Who is told.**

| Event | Customer | Administrators |
|---|---|---|
| Administrator counters | email `offer_countered` + in-app `offer.countered` | none |
| Customer counters | none | in-app `offer.countered` |
| Accepted (either side) | email `offer_accepted` + in-app `offer.accepted` | in-app `offer.accepted` if the customer accepted |
| Rejected | email `offer_rejected` + in-app `offer.rejected` | none |
| Withdrawn | none | in-app `offer.withdrawn` |

## Offer checkout (VS-041)

`POST /api/v1/me/offers/{offer_id}/checkout`. Verified email, CSRF header, an `Idempotency-Key` (8-255 characters of `[A-Za-z0-9._:-]`), and cart checkout's 30 per user per hour.

```json
{"accept_terms": true, "accept_digital_final_sale": true, "payment_provider": "optional", "contact_phone": "+96171123456"}
```

`contact_phone` is required on the `manual` provider (production, VS-050): it is the number the administrator calls to arrange payment, normalised to E.164 and stored on the order. Any other provider refuses it.

`201` returns `CheckoutRead`, the same shape as `POST /checkout` ([`checkout.md`](checkout.md)):
- the order is `pending_payment` with `source: "offer"`;
- its one STL line is priced at the offer's `agreed_amount`. The list price is never read, so a later price change, up or down, is ignored;
- the payment is `pending`, with the provider's `redirect_url`, `next_step` and `hold_expires_at`; on `manual`, `redirect_url` is null and `next_step` is `await_admin_contact` ([`payment-recovery.md`](payment-recovery.md#manual-payment-vs-050));
- `dropped_lines` is `[]`.

The offer stays `accepted` until the payment is verified. A replay of the same key and body returns the stored `201` (or `502`) with `Idempotent-Replayed: true`.

| Refusal (checked in this order) | Status and code |
|---|---|
| Bad body: a missing or false consent, any amount, an unknown field | `422 VALIDATION_ERROR` |
| Unknown, or another customer's | `404` |
| `checkout_expired`, or accepted with `now >= checkout_expires_at` | `410 OFFER_CHECKOUT_EXPIRED` |
| Any other status | `409 INVALID_STATE_TRANSITION`, with `offer_status` |
| Shop paused (`accepting_orders` off) | `503 ORDERS_PAUSED` |
| `PAYMENT_PROVIDER=none` | `503 ONLINE_PAYMENT_UNAVAILABLE` |
| The STL is hidden or unavailable | `422 PRODUCT_NOT_PURCHASABLE`, with `lines[{product_id, reason}]` |
| The offer's unpaid order has a live attempt | `409 PAYMENT_ALREADY_ACTIVE`, with `payment_id`, `payment_status`, `redirect_url` |
| The offer's unpaid order has no live attempt, or the STL is already owned | `409 PRODUCT_ALREADY_OWNED`, with `product_ids`. Retry that order with `POST /api/v1/me/orders/{order_id}/payments` |
| An unknown `payment_provider` | `422 PAYMENT_METHOD_NOT_ALLOWED`, with `reason` |
| `manual` without `contact_phone` / another provider with one | `422 CONTACT_PHONE_REQUIRED` / `422 INVALID_FULFILLMENT` (VS-050; checked right after the provider is known to be configured) |
| `manual`, and the customer already holds `manual_max_open_orders` unpaid `manual` orders | `422 MANUAL_ORDER_LIMIT_REACHED`, with `max_open_orders` (VS-050 audit Q-1; checked under the customer's advisory lock, before the order is inserted, so at the cap it comes before `409 PRODUCT_ALREADY_OWNED` for an unpaid order of the same offer: pay or retry that order first) |
| Same key, different body / still running | `409 IDEMPOTENCY_KEY_CONFLICT` / `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` |
| The provider could not start the payment | `502 PAYMENT_PROVIDER_UNAVAILABLE`; the order exists unpaid |
| Anonymous / unverified / no CSRF / over the limit | `401` / `403 EMAIL_VERIFICATION_REQUIRED` / `403 CSRF_INVALID` / `429 RATE_LIMITED` |

A refused checkout writes nothing.

**The window does not stretch over a pause.** If the shop is paused, checkout answers `503` while the window keeps running. An offer that lapses meanwhile becomes `checkout_expired`, and the customer may submit a new offer at once: there is no cooldown, which follows a rejection only.

**A retry of an offer order** works as for any order ([`payment-recovery.md`](payment-recovery.md)), but only while the offer is still `accepted` and inside its window. Otherwise it answers `409 INVALID_STATE_TRANSITION` with `reason: offer_checkout_expired`. An attempt still in flight answers `409 PAYMENT_ALREADY_ACTIVE` first, with its `redirect_url`, even past the window, because that payment is honoured. Retry is bounded by the hold from placement (30 min by default). After that, a second checkout answers `409 PRODUCT_ALREADY_OWNED` until the hold release cancels the unpaid order, about one hold after its last attempt.

**At most once.** An offer pays for one order line, ever (`uq_order_items_offer_once`). Only a line cancelled unpaid, by the hold release, frees it for another checkout inside the window.

## When the STL is paid (VS-041)

Inside the verified payment's own transaction, for every STL line it moves to `awaiting_delivery`:
- the offer the line was bought through becomes `paid`, with a `system` / `paid` round carrying the agreed amount;
- any other live offer (`awaiting_admin`, `awaiting_customer` or `accepted`) for that customer and product becomes `auto_closed`, with a `system` / `auto_closed` round (BR-088).

Each writes an audit row (`offer.paid` or `offer.auto_closed`, naming the order). Neither sends a notification: the payment's own receipt tells the customer.

A submission and a payment's auto-close serialise on one (customer, product) lock, so a live offer never survives on an owned STL.

## `expire_offers` (every 5 minutes)

An `awaiting_admin` or `awaiting_customer` offer expires once `now >= responds_by`. Expiry:
- sets `expired` with no turn, and keeps the missed deadline;
- appends a `system` / `expired` round;
- writes an audit row;
- sends the customer an in-app `offer.expired` notification.

An accepted offer never expires from inactivity. Rerunning the job, or running it twice at once, expires each offer once. The kill switch does not stop it.

Since VS-040, each run makes two more passes, each one locking, re-checking and writing per offer:
- **Checkout window.** An `accepted` offer becomes `checkout_expired` once `now >= checkout_expires_at`. It gets a `system` round, an audit row and an in-app `offer.checkout_expired`. The agreed amount and the deadline stay. An offer whose order has a `pending` or `processing` attempt is left alone, so that payment completes (VS-041). The first run after the attempt ends unpaid expires it.
- **Expiring soon.** An administrator's counter sets `remind_at` to 75 % of the customer's turn. Once `now >= remind_at`, the customer gets the `offer_expiring_soon` email and an in-app `offer.expiring_soon`, once, and `remind_at` is cleared. A reminder found past the deadline is dropped unsent.

## Rounds

Rounds are append-only and kept forever (BR-091). `sequence` is unique per offer. A round has an amount and currency together, or neither.
