# 06 — Negotiation (offers)

A customer offers a price for an STL; customer and administrator take turns until one accepts,
the administrator rejects, the customer withdraws, or a turn runs out. Acceptance opens a
one-time checkout at the agreed price. Requirements: FR-13; BR-080 to BR-092; ADR-034, ADR-035,
ADR-037.

Code: routers `src/app/negotiation/api/offers.py`, `admin_offers.py`, `offer_schemas.py`,
`offer_errors.py`; services `src/app/negotiation/application/services/` (`submit_offer.py`,
`respond_to_offer.py`, `offer_queries.py`, `expire_offers.py`, `settle_offers.py`); rules
`src/app/negotiation/domain/offers.py`; the job `src/app/jobs/expire_offers.py`; checkout
`src/app/ordering/api/offer_checkout.py`.

Settings: `minimum_offer_percentage` (70), `offer_response_window` (48 h, min 1 h),
`offer_checkout_window` (24 h, min 1 h), `offer_rejection_cooldown` (7 days, 0 = none).

Statuses: `awaiting_admin`, `awaiting_customer`, `accepted` (these three are **live**), then
`rejected`, `expired`, `withdrawn`, `paid`, `checkout_expired`, `auto_closed`. See the state
diagram in [00-overview.md §3.4](00-overview.md#34-offers).

---

## Customer routes

### `POST /api/v1/offers`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Verified | yes | no | 20 per hour per user |

Opens an offer on an STL: status `awaiting_admin`, turn `admin`, `responds_by` = now +
`offer_response_window`, round 1 `customer/submitted`. Every active administrator gets an in-app
`offer` notification. One live offer per customer and product (BR-081, a database constraint).

Request: `{"product_id": "<dragon-stl id>", "amount_cents": 600, "currency": "USD", "message": "Would you take 6?"}`.

Response `201` `OfferDetail`:

```json
{
  "id": "…",
  "product": {"id": "…", "name": "Articulated Dragon STL", "slug": "dragon-stl", "cover_image": {…}},
  "status": "awaiting_admin",
  "turn": "admin",
  "current_amount": {"amount_cents": 600, "currency": "USD"},
  "agreed_amount": null,
  "responds_by": "2026-11-09T10:00:00Z",
  "checkout_expires_at": null,
  "created_at": "2026-11-07T10:00:00Z",
  "initial_amount": {"amount_cents": 600, "currency": "USD"},
  "cooldown_until": null,
  "updated_at": "2026-11-07T10:00:00Z",
  "rounds": [{"sequence": 1, "actor": "customer", "action": "submitted", "amount": {"amount_cents": 600, "currency": "USD"}, "message": "Would you take 6?", "created_at": "…"}],
  "allowed_actions": ["withdraw"]
}
```

| Status | Code | When |
| --- | --- | --- |
| 409 | `OFFER_ALREADY_ACTIVE` | a live offer on this product already exists |
| 409 | `PRODUCT_ALREADY_OWNED` | the STL is owned |
| 422 | `PRODUCT_NOT_PURCHASABLE` | `reason`: `not_negotiable` (physical), `not_listed` (unknown, hidden, deleted), `unavailable` |
| 422 | `OFFER_BELOW_MINIMUM` | below `minimum_offer_percentage` of the list price; `minimum` |
| 422 | `OFFER_COOLDOWN_ACTIVE` | a rejection's cooldown is running; `cooldown_until` |
| 422 | `VALIDATION_ERROR` | above the list price; amount ≤ 0; currency not USD; message over 1000 |
| 503 | `ORDERS_PAUSED` | `accepting_orders` off (BR-040) |

### `GET /api/v1/me/offers` and `GET /api/v1/me/offers/{offer_id}`

Customer (unverified may read). List newest first; filters `status`, `product_id`, `cursor`,
`limit` (1-100, 20); rows are `OfferSummary`. The detail is `OfferDetail`. Another customer's
offer is `404`.

### `POST /api/v1/me/offers/{offer_id}/counter` · `/accept` · `/withdraw`

Verified; CSRF; 60 actions per hour per user. Each returns `200 OfferDetail`.

| Route | Allowed from | Body |
| --- | --- | --- |
| `counter` | `awaiting_customer` | `{"amount_cents": 650, "currency": "USD", "message": "Meet at 6.50?"}` (≥ minimum, ≤ list price) |
| `accept` | `awaiting_customer` | `{"expected_amount_cents": <current_amount shown>}` |
| `withdraw` | either awaiting state | `{"reason": "Changed my mind"}` or no body |

Accept freezes `agreed_amount` = min(amount on the table, today's list price) (BR-085), sets
`checkout_expires_at` = now + `offer_checkout_window` and clears `responds_by` (BR-087).

---

## Admin routes

Under the admin boundary; writes need CSRF. Each row adds `customer {id, email}`.

| Route | Allowed from | Body |
| --- | --- | --- |
| `GET /api/v1/admin/offers` | | `status`, `product_id`, `user_id`, `responds_before` (UTC offset), `cursor`, `limit`. Queue order: `awaiting_admin` by deadline, `awaiting_customer` by deadline, `accepted`, then closed |
| `GET /api/v1/admin/offers/{offer_id}` | | `AdminOfferDetail` |
| `POST /api/v1/admin/offers/{offer_id}/counter` | `awaiting_admin` | `{"amount_cents", "currency", "message?"}` (≤ list price; no minimum) |
| `POST /api/v1/admin/offers/{offer_id}/accept` | `awaiting_admin` | `{"expected_amount_cents"}` |
| `POST /api/v1/admin/offers/{offer_id}/reject` | `awaiting_admin` | `{"reason?"}`; starts `cooldown_until` (BR-089) |

Errors for every answer (customer and admin), checked in this order:

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | unknown, or another customer's |
| 410 | `OFFER_EXPIRED` | `expired`, or awaiting with `now ≥ responds_by` |
| 409 | `INVALID_STATE_TRANSITION` | any other closed status, or `accepted`; `offer_status` (`auto_closed` after a purchase) |
| 409 | `OFFER_NOT_YOUR_TURN` | the other party's turn |
| 409 | `OFFER_AMOUNT_CHANGED` | accept with `expected_amount_cents` ≠ `current_amount`; `current_amount` |
| 422 | `PRODUCT_NOT_PURCHASABLE` | counter/accept on an unlisted, unavailable or zero-priced product |
| 409 | `PRODUCT_ALREADY_OWNED` | counter/accept when the STL is owned (a backstop) |
| 422 | `OFFER_BELOW_MINIMUM` | a customer counter below the floor |
| 422 | `VALIDATION_ERROR` | counter above the list price, a missing `expected_amount_cents` |

Notifications: an admin counter emails the customer `offer_countered`; acceptance emails
`offer_accepted`; rejection `offer_rejected`; a customer counter, acceptance or withdrawal
notifies administrators in-app.

---

## Expiry (job `expire_offers`, every 5 minutes)

- An awaiting offer past `responds_by` becomes `expired` with a `system/expired` round and an
  in-app `offer.expired` for the customer (BR-084).
- An `accepted` offer past `checkout_expires_at` becomes `checkout_expired` (unless its order has
  a live payment attempt).
- After an admin counter, at 75 % of the customer's turn, the customer gets one
  `offer_expiring_soon` email.
- Paying the STL by any route closes every other live offer on it as `auto_closed` (BR-088), and
  the offer bought through becomes `paid`.

---

## Manual tests

Use `dragon-stl` (list price 700, minimum 490) with the seed customer, and a second verified
customer for the reject flow. Do these before buying `dragon-stl` in other tests.

| ID | Test | Expected |
| --- | --- | --- |
| NEG-01 | Offer 100 on `dragon-stl` | `422 OFFER_BELOW_MINIMUM`, `minimum.amount_cents: 490` |
| NEG-02 | Offer 800 | `422 VALIDATION_ERROR` on `amount_cents` (above the list price) |
| NEG-03 | Offer on `moon-lamp` | `422 PRODUCT_NOT_PURCHASABLE`, `reason: not_negotiable` |
| NEG-04 | Offer on `low-poly-vase-stl` | `422`, `reason: unavailable` |
| NEG-05 | Offer 600 on `dragon-stl` | `201`, `awaiting_admin`, `allowed_actions: ["withdraw"]`; admin has an `offer` notification |
| NEG-06 | Offer again on `dragon-stl` | `409 OFFER_ALREADY_ACTIVE` |
| NEG-07 | Customer tries `counter` on NEG-05 | `409 OFFER_NOT_YOUR_TURN` |
| NEG-08 | Admin: `GET /admin/offers` | NEG-05 first, with `customer.email` |
| NEG-09 | Admin counters 680 | `200`, `awaiting_customer`, new `responds_by`; customer gets `offer_countered` email |
| NEG-10 | Admin counters again | `409 OFFER_NOT_YOUR_TURN` |
| NEG-11 | Customer accepts with `expected_amount_cents: 600` | `409 OFFER_AMOUNT_CHANGED`, `current_amount.amount_cents: 680` |
| NEG-12 | Customer counters 400 | `422 OFFER_BELOW_MINIMUM` |
| NEG-13 | Customer counters 650 | `200`, `awaiting_admin` |
| NEG-14 | Admin accepts with `expected_amount_cents: 650` | `200`, `accepted`, `agreed_amount` 650, `checkout_expires_at` ≈ now + 24 h, `responds_by: null`; customer `offer_accepted` email |
| NEG-15 | Customer withdraws the accepted offer | `409 INVALID_STATE_TRANSITION`, `offer_status: accepted` |
| NEG-16 | Second customer offers 600 on `dragon-stl`; admin rejects with a reason | `200`, `rejected`, `cooldown_until` ≈ now + 7 days; `offer_rejected` email |
| NEG-17 | Second customer offers again | `422 OFFER_COOLDOWN_ACTIVE`, `cooldown_until` |
| NEG-18 | Second customer offers on `phone-stand-stl`, then withdraws | `200`, `withdrawn`; admins get an in-app `offer.withdrawn` |
| NEG-19 | Admin sets `accepting_orders` false; customer submits an offer; admin counters an existing one | submit `503 ORDERS_PAUSED`; the counter still works (BR-040). Set it back |
| NEG-20 | NEG-14 offer: `POST /me/offers/{id}/checkout` without `Idempotency-Key` | `422 VALIDATION_ERROR` |
| NEG-21 | Same with a key, `accept_terms` and `accept_digital_final_sale` (on `manual` add `contact_phone`) | `201`, `order.source: offer`, one line at 650 |
| NEG-22 | Checkout the same offer again with a new key | `409 PAYMENT_ALREADY_ACTIVE` (its attempt is live) |
| NEG-23 | Pay the order (mock_pay or manual confirm) | offer `paid` with a `system/paid` round; the STL is owned |
| NEG-24 | A second customer's offer whose checkout window passed (set `offer_checkout_window` to 3600, accept, wait over an hour) | checkout answers `410 OFFER_CHECKOUT_EXPIRED`; after the next job run the offer is `checkout_expired` |
| NEG-25 | (Long) Set `offer_response_window` to 3600; submit; wait over an hour | within 5 minutes after the deadline the offer is `expired`; any answer gives `410 OFFER_EXPIRED` |
| NEG-26 | A customer holds a live offer on an STL, then buys it through the cart and pays | the offer becomes `auto_closed`; answering it gives `409 INVALID_STATE_TRANSITION`, `offer_status: auto_closed` |
| NEG-27 | Second customer: `GET /me/offers/{NEG-05 id}` | `404 NOT_FOUND` |
| NEG-28 | `GET /admin/offers?responds_before=2026-12-01` | `422` (needs a time and offset) |
