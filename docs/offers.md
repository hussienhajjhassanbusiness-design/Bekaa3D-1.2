# Offers (VS-039, VS-040)

The contract for offer submission, negotiation, offer reads and expiry. Decisions and their reasons: [ADR-034](adr/ADR-034-offer-submission-and-expiry.md) (submission, expiry) and [ADR-035](adr/ADR-035-offer-negotiation.md) (negotiation). Shapes: [`api-endpoints.md`](requirments/api-endpoints.md) §13, §21 and `OfferDetail`, and the OpenAPI file in [`frontend-handoff/`](frontend-handoff/openapi.json). VS-041 adds offer checkout.

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
| `POST /api/v1/me/offers/{id}/accept` | the customer | `awaiting_customer` | none |
| `POST /api/v1/me/offers/{id}/withdraw` | the customer | either awaiting state, whoever's turn | `{reason?}` or none |
| `POST /api/v1/admin/offers/{id}/counter` | an administrator | `awaiting_admin` | `{amount_cents, currency, message?}` |
| `POST /api/v1/admin/offers/{id}/accept` | an administrator | `awaiting_admin` | none |
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
| Counter or accept on an unlisted, unavailable or zero-priced product | `422 PRODUCT_NOT_PURCHASABLE`, with `reason` |
| Accept when the customer already owns the STL | `409 PRODUCT_ALREADY_OWNED` |
| Customer counter below the floor | `422 OFFER_BELOW_MINIMUM`, with `minimum` |
| Counter above today's list price; bad body | `422 VALIDATION_ERROR` |

A refused action writes nothing. The kill switch never blocks an answer.

**Who is told.**

| Event | Customer | Administrators |
|---|---|---|
| Administrator counters | email `offer_countered` + in-app `offer.countered` | none |
| Customer counters | none | in-app `offer.countered` |
| Accepted (either side) | email `offer_accepted` + in-app `offer.accepted` | in-app `offer.accepted` if the customer accepted |
| Rejected | email `offer_rejected` + in-app `offer.rejected` | none |
| Withdrawn | none | in-app `offer.withdrawn` |

## `expire_offers` (every 5 minutes)

An `awaiting_admin` or `awaiting_customer` offer expires once `now >= responds_by`. Expiry:
- sets `expired` with no turn, and keeps the missed deadline;
- appends a `system` / `expired` round;
- writes an audit row;
- sends the customer an in-app `offer.expired` notification.

An accepted offer never expires from inactivity. Rerunning the job, or running it twice at once, expires each offer once. The kill switch does not stop it.

Since VS-040, each run makes two more passes, each one locking, re-checking and writing per offer:
- **Checkout window.** An `accepted` offer becomes `checkout_expired` once `now >= checkout_expires_at`. It gets a `system` round, an audit row and an in-app `offer.checkout_expired`. The agreed amount and the deadline stay.
- **Expiring soon.** An administrator's counter sets `remind_at` to 75 % of the customer's turn. Once `now >= remind_at`, the customer gets the `offer_expiring_soon` email and an in-app `offer.expiring_soon`, once, and `remind_at` is cleared. A reminder found past the deadline is dropped unsent.

## Rounds

Rounds are append-only and kept forever (BR-091). `sequence` is unique per offer. A round has an amount and currency together, or neither.
