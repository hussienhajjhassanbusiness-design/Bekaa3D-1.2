# 07 — Engagement

Notifications, wishlist, reviews and moderation, Bring Your Idea (custom requests), the contact
form, and engagement analytics. Requirements: FR-14 to FR-17, FR-21; BR-100 to BR-116;
ADR-030, ADR-031, ADR-044, ADR-046; [`docs/notification-contract.md`](../notification-contract.md).

Code: routers in `src/app/engagement/api/`, use cases in
`src/app/engagement/application/commands/` and `application/services/`, rules in
`src/app/engagement/domain/` (`reviews.py`, `profanity.py`, `custom_request.py`,
`contact_message.py`), persistence in `src/app/engagement/infrastructure/`.

Who-can-call labels: see [01-identity.md](01-identity.md).

---

## Notifications

Types: `account`, `order`, `payment`, `refund`, `offer`, `download`, `custom_request`. The
payload's `event` names what happened (`order.placed`, `payment.confirmed`, `offer.countered`,
`stl.delivered`, `payment.alert.<kind>` for administrators, …).
Code: `engagement/api/notifications.py`, `application/services/notification_writer.py`.

### `GET /api/v1/me/notifications`

Customer (or admin). Newest first; `cursor`, `limit` (1-100, 20), `read` (true/false).

Response `200`:

```json
{
  "items": [
    {"id": "…", "type": "order", "payload": {"event": "order.placed", "order_id": "…", "order_number": "B3D-…"}, "read": false, "created_at": "2026-11-07T10:00:00Z"}
  ],
  "next_cursor": null
}
```

Errors: `401`, `422` (bad cursor or `limit`).

### `PATCH /api/v1/me/notifications/{notification_id}`

Verified; CSRF. Body `{"read": true}` (or `false`). `200 NotificationRead`. Errors: `403`,
`404` (unknown or another user's), `422`.

| ID | Test | Expected |
| --- | --- | --- |
| ENG-01 | Seed customer: `GET /me/notifications?read=false` | at least the two seeded `account` notifications |
| ENG-02 | `PATCH` one with `{"read": true}` | `200`, `read: true`; it no longer appears with `read=false` |
| ENG-03 | `PATCH` it with `{"read": "yes"}` | `422 VALIDATION_ERROR` |
| ENG-04 | Second customer `PATCH`es the seed customer's notification id | `404 NOT_FOUND` |
| ENG-05 | After a checkout | a new `order` notification; after a manual-payment checkout the admin has a `payment` notification with `event: payment.alert.manual_payment_due` |

---

## Wishlist

Verified users (BR-108). Adding and removing are idempotent. Code: `engagement/api/wishlist.py`,
`application/services/wishlist.py`, `infrastructure/wishlist.py`.

| Method and path | Who | CSRF | Limit | Answer |
| --- | --- | --- | --- | --- |
| `GET /api/v1/me/wishlist` | Customer | no | none | `200 {items, next_cursor}`; newest first; `cursor`, `limit` (1-100, 20) |
| `PUT /api/v1/me/wishlist/{product_id}` | Verified | yes | 120 writes per hour per user | `204`; adding again is still `204` |
| `DELETE /api/v1/me/wishlist/{product_id}` | Verified | yes | same | `204`, even when absent |

Item: `{product_id, created_at, available, name, slug, price_cents, currency, type}`; a product
that is no longer public shows `available: false` and null `slug`/price.

Errors: `PUT` of an unknown or non-public product is `404 NOT_FOUND`; `403`; `429`.

| ID | Test | Expected |
| --- | --- | --- |
| ENG-06 | `PUT /me/wishlist/{moon-lamp id}` twice | both `204`; the list has it once |
| ENG-07 | `PUT` the `prototype-gear` id | `404 NOT_FOUND` |
| ENG-08 | `DELETE` a product not on the list | `204` |
| ENG-09 | Admin hides `moon-lamp` (`is_visible: false`); customer reads the list | the item shows `available: false`. Restore visibility afterwards |
| ENG-10 | Admin: `GET /admin/analytics/wishlist` | `total_active` counts the row; `most_wishlisted` lists `moon-lamp` with its `wishlist_count` |

---

## Reviews

Any verified user may review any product, once (BR-100, BR-101); ratings 1-5 (BR-105); body
optional, ≤ 2000, no links or listed words (BR-107). The **verified purchase** badge comes from
real order lines: an owned STL, or a physical line `delivered`/`picked_up` and not refunded,
returned or cancelled (BR-102); never on a WhatsApp-only product (BR-103). The product's
`average_rating` and `review_count` are recomputed in the same transaction. Code:
`engagement/api/reviews.py`, `api/review_schemas.py`, `application/services/reviews.py`,
`domain/reviews.py`, `domain/profanity.py`, `infrastructure/reviews.py`,
`ordering/domain/badge.py`.

### `GET /api/v1/products/{slug}/reviews`

Anonymous; 600 per hour per IP. Visible reviews of a visible product, newest first. Query:
`cursor`, `limit` (1-50, 20), `rating` (1-5), `verified_purchase`. Items:
`{id, rating, body, is_verified_purchase, created_at, edited}` (no author). `404` for an unknown
or non-public product.

### `GET /api/v1/me/reviews`

Customer. Own live reviews, hidden ones included with `is_hidden: true`. Items add `product_id`,
`product_slug`, `is_hidden`.

### `POST /api/v1/reviews`

Verified; CSRF; 10 review writes per hour per user (shared with edit and delete).
Request: `{"product_id": "<moon-lamp id>", "rating": 5, "body": "Lovely light, well printed."}`.
Response `201`:
`{"id": "…", "rating": 5, "body": "Lovely light, well printed.", "is_verified_purchase": false, "created_at": "…", "edited": false, "product_id": "…", "product_slug": "moon-lamp", "is_hidden": false}`.

### `PATCH /api/v1/reviews/{review_id}`

Verified, author; CSRF; same limit. Any of `rating`, `body` (`null` clears). A hidden review
stays hidden. `200 MyReviewRead` with `edited: true`.

### `DELETE /api/v1/reviews/{review_id}`

Verified, author; CSRF; same limit. Soft delete; the author may then write a new one. `204`.

| Status | Code | When |
| --- | --- | --- |
| 404 | `NOT_FOUND` | product unknown or not public; review not the caller's or deleted |
| 409 | `REVIEW_ALREADY_EXISTS` | the caller already has a live review of this product |
| 422 | `REVIEW_CONTENT_REJECTED` | `reason`: `link` or `profanity` |
| 422 | `VALIDATION_ERROR` | rating 0 or 6, body over 2000, empty `PATCH` |
| 429 | `RATE_LIMITED` | over 10 writes per hour |

| ID | Test | Expected |
| --- | --- | --- |
| ENG-11 | Review `moon-lamp` with rating 5 | `201`, `is_verified_purchase: false`; `GET /products/moon-lamp` shows `review_count: 1`, `average_rating: 5.0` |
| ENG-12 | Review `moon-lamp` again | `409 REVIEW_ALREADY_EXISTS` |
| ENG-13 | Body `"see https://example.com"` | `422 REVIEW_CONTENT_REJECTED`, `reason: link` |
| ENG-14 | Rating 6 | `422 VALIDATION_ERROR` |
| ENG-15 | `PATCH` rating to 3 | `200`, `edited: true`; product `average_rating: 3.0` |
| ENG-16 | After FUL-20 hands `moon-lamp` over to the seed customer, read ENG-11's review in `GET /me/reviews` | `is_verified_purchase: true` (recomputed when the line changed, BR-104) |
| ENG-17 | Review `name-sign` (WhatsApp only) | `201`; the public list never shows a badge for it |
| ENG-18 | `GET /products/moon-lamp/reviews?verified_purchase=true` | only badged reviews |
| ENG-19 | Second customer `PATCH`es the seed customer's review | `404 NOT_FOUND` |
| ENG-20 | `DELETE` own review, then post a new one | `204`, then `201` |

### Admin moderation

| Method and path | Who | CSRF | Body | Answer |
| --- | --- | --- | --- | --- |
| `GET /api/v1/admin/reviews` | Admin | no | `cursor`, `limit` (1-100), `hidden`, `rating`, `product_id`, `user_id`, `verified_purchase` | `200`; live reviews (hidden and visible), newest first |
| `GET /api/v1/admin/reviews/{review_id}` | Admin | no | | `200 AdminReviewDetail` (`user_id`, `badge_shown`, `is_hidden`, `hidden_at`, …) |
| `POST /api/v1/admin/reviews/{review_id}/hide` | Admin | yes | `{"reason": "…"}` optional, ≤ 500 | `200`; rating recomputed; audited |
| `POST /api/v1/admin/reviews/{review_id}/restore` | Admin | yes | same | `200` |

Errors: `404` (unknown, or deleted by its author: BR-106), `409 INVALID_STATE_TRANSITION`
(already in that state; `is_hidden`), `422` (reason too long). Code:
`engagement/api/review_admin.py`, `application/services/review_moderation.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ENG-21 | Admin hides ENG-11's review with a reason | `200`, `is_hidden: true`; the public list no longer shows it; product rating recomputed; the author still sees it with `is_hidden: true` |
| ENG-22 | Hide it again | `409 INVALID_STATE_TRANSITION`, `is_hidden: true` |
| ENG-23 | Restore it | `200`, visible again |
| ENG-24 | Hide a review its author deleted | `404 NOT_FOUND` |

---

## Bring Your Idea (custom requests)

A guest lead form, never an order (BR-110 to BR-115). Images are scanned, type-sniffed,
re-encoded and stored privately; only the administrator can download them, until they expire
(`custom_request_attachment_retention`, 90 days).

### `POST /api/v1/custom-requests`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous (cookies ignored) | no | no | 20 attempts per hour per IP before parsing; then 5 per hour per IP and 5 per hour per email; captcha |

`multipart/form-data` parts: `name` (1-100), `email`, `phone` (≤ 32, at least 6 digits),
`project_title` (1-200), `description` (1-5000), optional `preferred_material`,
`preferred_colour` (≤ 100), `dimensions` (≤ 200), `captcha_token`, and 0-5 `attachments`
(JPEG/PNG/WebP, ≤ 10 MB and 40 MP each; omit the part when there are none). Every administrator
gets an in-app `custom_request` notification.

Response `201`: `{"id": "…", "created_at": "2026-11-07T10:00:00Z"}`.

| Status | Code | When |
| --- | --- | --- |
| 400 | `CAPTCHA_INVALID` | captcha refused |
| 422 | `VALIDATION_ERROR` | a missing or too long field, more than 5 files, a blank file part |
| 422 | `UPLOAD_REJECTED` | a file not an image, too big, too many pixels, or a body over the declared limit; `errors[].loc` names the file |
| 422 | `MALWARE_DETECTED` | ClamAV flagged a file |
| 429 | `RATE_LIMITED` | over a limit |
| 503 | `SERVICE_UNAVAILABLE` | captcha or ClamAV unavailable |

Code: `engagement/api/custom_requests.py`, `api/custom_request_schemas.py`,
`application/commands/submit_custom_request.py`, `domain/custom_request.py`,
`infrastructure/custom_requests.py`.

### Admin pipeline

| Method and path | Who | CSRF | Body / query | Answer |
| --- | --- | --- | --- | --- |
| `GET /api/v1/admin/custom-requests` | Admin | no | `cursor`, `limit` (1-100, 20), `status`, `created_after`, `created_before` (UTC offset), `email` | `200`; ordered `new`, `contacted`, `quoted`, …, oldest first in each |
| `GET /api/v1/admin/custom-requests/{request_id}` | Admin | no | | `200` with every field and the metadata of unexpired attachments |
| `PATCH /api/v1/admin/custom-requests/{request_id}` | Admin | yes | `{"admin_notes": "…" \| null}` (≤ 5000) | `200` |
| `POST /api/v1/admin/custom-requests/{request_id}/transition` | Admin | yes | `{"target_status": "quoted", "quoted_amount_cents": 4500}` | `200` |
| `GET /api/v1/admin/custom-requests/{request_id}/attachments/{attachment_id}/download` | Admin | no | | `200` image bytes, `Content-Disposition: attachment`, `Cache-Control: no-store` |

Legal moves (BR-113): `new → contacted → quoted` (needs `quoted_amount_cents` 1-100 000 000) →
`in_progress` (outcome `won`) `→ completed → closed`; `contacted` or `quoted → lost`. Anything else
is `409 INVALID_STATE_TRANSITION`; `quoted_amount_cents` on another target is `422`. An expired,
foreign or missing attachment is `404`. Code: `engagement/api/custom_request_admin.py`,
`application/commands/custom_request_pipeline.py`, `domain/custom_request.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ENG-25 | Logged out: submit with the dummy captcha, one PNG | `201` `{id, created_at}`; admins get a `custom_request` notification |
| ENG-26 | Submit with a `.txt` file as `attachments` | `422 UPLOAD_REJECTED`, `loc` `["body","attachments",0]` |
| ENG-27 | Submit with captcha `wrong` | `400 CAPTCHA_INVALID` |
| ENG-28 | Keep submitting valid requests with the same email | `429 RATE_LIMITED` once 5 have passed the captcha in the hour from this IP or email; ENG-25 to ENG-27 may already count (clear the counters afterwards) |
| ENG-29 | Admin lists requests | ENG-25 first with `status: new`, `attachment_count: 1` |
| ENG-30 | Transition `new → quoted` | `409 INVALID_STATE_TRANSITION` |
| ENG-31 | `new → contacted`, then `contacted → quoted` without an amount | `200`; then `422 VALIDATION_ERROR` |
| ENG-32 | `contacted → quoted` with `quoted_amount_cents: 4500`, then `in_progress`, `completed`, `closed` | each `200`; outcome `won` after `in_progress` |
| ENG-33 | Download the attachment | `200` with the image; headers `Content-Disposition: attachment`, `Cache-Control: no-store` |
| ENG-34 | Customer downloads it | `404 NOT_FOUND` |
| ENG-35 | Funnel: `GET /admin/analytics/custom-requests/funnel?from=2026-11-01T00:00:00Z&to=2026-12-01T00:00:00Z` | `200`; `submitted`, `contacted`, `quoted`, `won`, `lost`, `open`, `quoted_total_cents`, `won_total_cents`, `currency: USD` |
| ENG-36 | Funnel with `from=2026-11-01` (date only) | `422 VALIDATION_ERROR` on `from` |
| ENG-37 | Funnel with a range over 366 days, or `to` before `from` | `422 VALIDATION_ERROR` on `to` |

### `GET /api/v1/admin/analytics/custom-requests/funnel`

Admin. `from` (inclusive, default 90 days before `to`) and `to` (exclusive, default now) **must
be full timestamps with a UTC offset**, e.g. `2026-11-01T00:00:00Z`; the span is at most 366
days. A stage counts every lead that ever reached it. Code:
`engagement/api/admin_analytics.py`, `engagement/api/queue_cursor.py` (`check_range`).

### `GET /api/v1/admin/analytics/wishlist`

Admin. `limit` (1-100, 20). `{"total_active": 3, "most_wishlisted": [{"product_id", "name", "slug", "wishlist_count"}]}`.

---

## Contact messages

BR-116, FR-16. A signed-in sender's message is linked to the account (`user_id`) and must carry
CSRF; a guest's needs none.

### `POST /api/v1/contact-messages`

| Who | CSRF | Idempotency-Key | Limit |
| --- | --- | --- | --- |
| Anonymous, or signed in (then CSRF required) | only when signed in | no | 60 attempts per hour per IP; then 5 per hour per IP and 5 per hour per email; captcha |

Request: `{"name": "Rami", "email": "rami@example.com", "phone": "71123456", "subject": "Bulk order", "message": "Can you print 50 keychains?", "captcha_token": "XXXX.DUMMY.TOKEN.XXXX"}`
(`name` ≤ 100, `phone` ≤ 32 optional, `subject` ≤ 200 optional, `message` ≤ 5000).
Response `201`: `{"id": "…", "created_at": "…"}`.

Errors: `400 CAPTCHA_INVALID`, `401 AUTH_REQUIRED` (account deleted mid-request),
`403 CSRF_INVALID` (signed in without the header), `422 VALIDATION_ERROR`, `429`, `503`.

### Admin queue

| Method and path | Who | CSRF | Answer |
| --- | --- | --- | --- |
| `GET /api/v1/admin/contact-messages` | Admin | no | `cursor`, `limit`, `status` (`new`, `read`, `replied`, `archived`), `created_after`, `created_before` (UTC offset), `email`; `new` first, then oldest first; audited |
| `GET /api/v1/admin/contact-messages/{message_id}` | Admin | no | full message incl. `user_id`, `order_id` (problem reports); audited `contact_message.viewed`; does not mark it read |
| `PATCH /api/v1/admin/contact-messages/{message_id}` | Admin | yes | `{"status": "read"}`; forward only, else `409 INVALID_STATE_TRANSITION` |

Code: `engagement/api/contact_messages.py`, `api/contact_message_schemas.py`,
`application/commands/submit_contact_message.py`,
`application/commands/change_contact_message_status.py`, `domain/contact_message.py`.

| ID | Test | Expected |
| --- | --- | --- |
| ENG-38 | Logged out: send a message | `201`; admin list shows it `new` with `user_id: null` |
| ENG-39 | Logged in as the customer **with** CSRF | `201`; `user_id` is the customer |
| ENG-40 | Logged in **without** CSRF | `403 CSRF_INVALID` |
| ENG-41 | Captcha `wrong` | `400 CAPTCHA_INVALID` |
| ENG-42 | Admin `PATCH` `new → replied` | `200` |
| ENG-43 | Admin `PATCH` `replied → read` | `409 INVALID_STATE_TRANSITION` |
| ENG-44 | Admin `GET /admin/contact-messages?created_after=2026-11-01` | `422` (needs a time and offset) |
