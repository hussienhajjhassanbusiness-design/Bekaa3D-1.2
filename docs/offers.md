# Offers (VS-039)

The contract for offer submission, offer reads and inactivity expiry. Decisions and their reasons: [ADR-034](adr/ADR-034-offer-submission-and-expiry.md). Shapes: [`api-endpoints.md`](requirments/api-endpoints.md) §13, §21 and `OfferDetail`, and the OpenAPI file in [`frontend-handoff/`](frontend-handoff/openapi.json). VS-040 adds counter, accept, reject and withdraw; VS-041 adds offer checkout.

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
- `allowed_actions`, which is always `[]` until VS-040.

## `GET /api/v1/admin/offers` and `GET /api/v1/admin/offers/{offer_id}`

These sit behind the admin boundary: anonymous gets `401`, a customer `404`, an administrator without MFA `401`. Each row and the detail add `customer {id, email}`.

The queue order:
1. `awaiting_admin`, soonest `responds_by` first;
2. `awaiting_customer`, soonest `responds_by` first;
3. `accepted`;
4. closed offers, oldest first.

Filters: `status`, `product_id`, `user_id`, and `responds_before`. `responds_before` matches only pending offers (`awaiting_*`) whose deadline is before it. It is exclusive and needs a UTC offset. A naive timestamp or a tampered cursor is `422`.

## `expire_offers` (every 5 minutes)

An `awaiting_admin` or `awaiting_customer` offer expires once `now >= responds_by`. Expiry:
- sets `expired` with no turn, and keeps the missed deadline;
- appends a `system` / `expired` round;
- writes an audit row;
- sends the customer an in-app `offer.expired` notification.

An accepted offer never expires from inactivity. Rerunning the job, or running it twice at once, expires each offer once. The kill switch does not stop it.

## Rounds

Rounds are append-only and kept forever (BR-091). `sequence` is unique per offer. A round has an amount and currency together, or neither.
