# 99 — Test checklist

Every manual test from the per-context files, in an order where each step's prerequisites come
first. Tick each box as you go. The full steps, request bodies and error tables are in the file
named after each test.

Before starting: [00-overview.md](00-overview.md) §4 (stack, seed, Swagger login, emails, rate
limits). Clear the Redis counters whenever a `429` blocks you (overview §4.7).

## 1. Stack, health and the admin boundary

Overview §4.1-4.5 done: stack up, migrations applied, seed run, credentials in `C:\Users\user\bekaa3d-seed-credentials.txt`, Swagger open.

- [ ] **ADM-30** [08](08-platform-admin.md) — `GET /health/live` and `/health/ready` → both `200`
- [ ] **ADM-31** [08](08-platform-admin.md) — `docker compose stop redis`, then `/health/ready` and `/health/live` → ready `503 SERVICE_UNAVAILABLE`; live still `200`. `docker compose start redis` afterwards
- [ ] **ADM-32** [08](08-platform-admin.md) — Any request with an `X-Request-ID: my-test-1` header → the response echoes `X-Request-ID: my-test-1`
- [ ] **ADM-01** [08](08-platform-admin.md) — Anonymous: `GET /api/v1/admin/settings` and `GET /api/v1/admin/does-not-exist` → both `401 AUTH_REQUIRED`
- [ ] **ADM-02** [08](08-platform-admin.md) — Customer: the same two → both `404 NOT_FOUND` with the same `title` and `detail`
- [ ] **ADM-03** [08](08-platform-admin.md) — Customer: `POST /api/v1/admin/categories` with an invalid JSON body → `404 NOT_FOUND` (not `400`: the body is never read)
- [ ] **ADM-04** [08](08-platform-admin.md) — Admin (MFA): `GET /api/v1/admin/does-not-exist` → `404 NOT_FOUND`
- [ ] **ADM-05** [08](08-platform-admin.md) — Admin: `DELETE /api/v1/admin/settings` → `405` with an `Allow: GET, HEAD` header
- [ ] **ADM-06** [08](08-platform-admin.md) — Admin: `GET /api/v1/admin/settings/` (trailing slash) → not a redirect: the same answer an unknown path gets

## 2. Registration, verification and sessions

Stop the worker before reading tokens from `email_outbox` (overview §4.6).

- [ ] **ID-01** [01](01-identity.md) — Register a new address with the dummy captcha token → `202`; one `verification_email` row in `email_outbox` for that address
- [ ] **ID-02** [01](01-identity.md) — Register the same address again at once → `202`, same body; no second outbox row (2 min cooldown)
- [ ] **ID-03** [01](01-identity.md) — Register `seed-customer@example.com` (already verified) → `202`, same body; no outbox row
- [ ] **ID-04** [01](01-identity.md) — Register with `captcha_token: "wrong"` → `400 CAPTCHA_INVALID`; no user created
- [ ] **ID-05** [01](01-identity.md) — Password `short1` (7 characters) → `422 VALIDATION_ERROR`, `loc` `["body","password"]`
- [ ] **ID-06** [01](01-identity.md) — Add an extra field `"role": "admin"` → `422 VALIDATION_ERROR` (unknown fields forbidden)
- [ ] **ID-07** [01](01-identity.md) — Stop the worker, read the token for ID-01's address (overview §4.6), verify → `204`; `GET /me` after login shows `email_verified: true`
- [ ] **ID-08** [01](01-identity.md) — Send the same token again → `400 INVALID_TOKEN`
- [ ] **ID-09** [01](01-identity.md) — Send `{"token": "abc"}` → `400 INVALID_TOKEN`
- [ ] **ID-10** [01](01-identity.md) — Register an address, wait 2 minutes, resend → `202`; a second `verification_email` row; the older token still works until used
- [ ] **ID-11** [01](01-identity.md) — Resend for an unknown address → `202`, same body; no outbox row
- [ ] **ID-12** [01](01-identity.md) — Log in as the seed customer → `200`; cookies `access_token`, `refresh_token`, `csrf_token` in DevTools; no token in the body
- [ ] **ID-13** [01](01-identity.md) — Log in as the seed admin → `202` with `challenge_id`; no cookies set
- [ ] **ID-14** [01](01-identity.md) — Wrong password for the customer → `401 INVALID_CREDENTIALS`; an audit row `user.login_failed`
- [ ] **ID-15** [01](01-identity.md) — Unknown email → `401 INVALID_CREDENTIALS`, the same body as ID-14
- [ ] **ID-16** [01](01-identity.md) — Wrong password 4 times in a row → the 4th answer takes about 1 s longer; then reset the throttle (overview §4.7)
- [ ] **ID-18** [01](01-identity.md) — Log out with the CSRF header → `204`; the cookies disappear from DevTools; `POST /auth/refresh` now answers `401`
- [ ] **ID-19** [01](01-identity.md) — Log out without the CSRF header (clear Authorize first) → `403 CSRF_INVALID`; still logged in
- [ ] **ID-20** [01](01-identity.md) — Logged in, call refresh with CSRF → `204`; `access_token` cookie value changes; `csrf_token` stays the same
- [ ] **ID-21** [01](01-identity.md) — Copy the `refresh_token` value, refresh once, then put the old value back in DevTools and refresh again → `401 AUTH_REQUIRED`; the session is revoked (the next refresh with the new token also fails)
- [ ] **ID-37** [01](01-identity.md) — Logged in as the customer → `200`, own email, `role: customer`
- [ ] **ID-38** [01](01-identity.md) — Logged out → `401 AUTH_REQUIRED`

## 3. Password reset

Use a throwaway account, not the seed customer.

- [ ] **ID-22** [01](01-identity.md) — Window A: log in as a test customer. Window B: request a reset, read `reset_url` (worker stopped), confirm with a new password → `204`; in window A the next authenticated call answers `401 AUTH_REQUIRED` at once (not after 15 min)
- [ ] **ID-23** [01](01-identity.md) — Log in with the old password → `401 INVALID_CREDENTIALS`; the new one works
- [ ] **ID-24** [01](01-identity.md) — Confirm again with the same token → `400 INVALID_TOKEN`
- [ ] **ID-25** [01](01-identity.md) — Request a reset for an unknown address → `202`, same body; no outbox row
- [ ] **ID-26** [01](01-identity.md) — Request twice within 2 minutes for the same account → both `202`; only one `password_reset_email` row

## 4. Administrator MFA

Wait for a fresh 30 s TOTP step between admin logins.

- [ ] **ID-27** [01](01-identity.md) — ID-13's challenge + the current TOTP code → `204`; cookies set; `GET /api/v1/admin/settings` answers `200`
- [ ] **ID-28** [01](01-identity.md) — Log in again, verify with a wrong code → `401 MFA_INVALID`; verifying again with the right code on the same challenge gives `410 RESOURCE_EXPIRED`
- [ ] **ID-29** [01](01-identity.md) — Log in twice inside one 30 s step, verify both with the same code → the first `204`, the second `401 MFA_INVALID`
- [ ] **ID-30** [01](01-identity.md) — Send both `code` and `recovery_code` → `422 VALIDATION_ERROR`
- [ ] **ID-32** [01](01-identity.md) — Seed admin (MFA on): `POST /auth/mfa/setup` with the right password → `409 INVALID_STATE_TRANSITION`
- [ ] **ID-33** [01](01-identity.md) — Seed customer: `POST /auth/mfa/setup` → `404 NOT_FOUND`
- [ ] **ID-34** [01](01-identity.md) — Seed admin: `POST /auth/mfa/setup/confirm` with any code → `409 INVALID_STATE_TRANSITION`

## 5. Settings

Set `pickup_address` now; checkout tests need it.

- [ ] **ADM-07** [08](08-platform-admin.md) — Anonymous `GET /settings/public` → `200`, six keys
- [ ] **ADM-08** [08](08-platform-admin.md) — Admin `PATCH /admin/settings/pickup_address` `{"value": "Bekaa3D workshop, Zahle main road"}` → `200`; the public endpoint shows it; pickup checkout now works
- [ ] **ADM-09** [08](08-platform-admin.md) — `PATCH /admin/settings/minimum_offer_percentage` `{"value": 150}` → `422 SETTING_INVALID`
- [ ] **ADM-10** [08](08-platform-admin.md) — `PATCH /admin/settings/accepting_orders` `{"value": "yes"}` → `422 SETTING_INVALID`
- [ ] **ADM-11** [08](08-platform-admin.md) — `PATCH /admin/settings/cash_max_order_total` `{"value": {"amount_cents": 20000, "currency": "USD"}}` → `200`; the public endpoint shows 20000. **Set it back to 10000**: ORD-30 relies on the default cap
- [ ] **ADM-12** [08](08-platform-admin.md) — `PATCH /admin/settings/no_such_key` → `404 NOT_FOUND`
- [ ] **ADM-13** [08](08-platform-admin.md) — `GET /admin/settings?prefix=offer_` → only `offer_checkout_window`, `offer_rejection_cooldown`, `offer_response_window`
- [ ] **ADM-14** [08](08-platform-admin.md) — After ADM-08, `GET /admin/audit-logs?action=setting.updated` → an audit row with before and after values

## 6. Public catalogue

- [ ] **CAT-01** [02](02-catalog.md) — Anonymous `GET /products` → `200`; 9 items; no `prototype-gear` or `holiday-ornament`; `knight` and `low-poly-vase-stl` present with `is_available: false`
- [ ] **CAT-02** [02](02-catalog.md) — `GET /products?type=stl` → only `dragon-stl`, `phone-stand-stl`, `low-poly-vase-stl`
- [ ] **CAT-03** [02](02-catalog.md) — `GET /products?featured=true` → `moon-lamp`, `phone-stand-stl`
- [ ] **CAT-04** [02](02-catalog.md) — `GET /products?sort=price&limit=2`, then the same with `cursor=<next_cursor>` → pages in ascending price; no product repeats
- [ ] **CAT-05** [02](02-catalog.md) — Use page 1's cursor with `sort=-price` → `422 VALIDATION_ERROR`, `loc` `["query","cursor"]`
- [ ] **CAT-06** [02](02-catalog.md) — `GET /products?price_min_cents=2000&price_max_cents=1000` → `422 VALIDATION_ERROR`
- [ ] **CAT-07** [02](02-catalog.md) — `GET /products?sort=-relevance` (no `q`) → `422 VALIDATION_ERROR` on `sort`
- [ ] **CAT-08** [02](02-catalog.md) — `GET /products?q=dragons` → both dragon products (stemming)
- [ ] **CAT-09** [02](02-catalog.md) — `GET /products?q=dragn` → the dragon products (fuzzy fallback)
- [ ] **CAT-10** [02](02-catalog.md) — `GET /products/dragon` → `200`; two images; `capabilities.can_add_to_cart: true`, `whatsapp_available: true`
- [ ] **CAT-11** [02](02-catalog.md) — `GET /products/name-sign` → `can_add_to_cart: false`, `whatsapp_available: true` (WhatsApp only)
- [ ] **CAT-12** [02](02-catalog.md) — `GET /products/dragon-stl` → `can_offer: true`, `whatsapp_available: false`
- [ ] **CAT-13** [02](02-catalog.md) — `GET /products/prototype-gear` and `/products/holiday-ornament` → both `404 NOT_FOUND`
- [ ] **CAT-14** [02](02-catalog.md) — `GET /products/Dragon` → `404 NOT_FOUND`
- [ ] **CAT-15** [02](02-catalog.md) — `GET /search/suggestions?q=drag` → dragon products
- [ ] **CAT-16** [02](02-catalog.md) — `GET /search/suggestions?q=dr` → `422 VALIDATION_ERROR` on `q`
- [ ] **CAT-17** [02](02-catalog.md) — `GET /categories` → three categories; no `seasonal`
- [ ] **CAT-18** [02](02-catalog.md) — `GET /products/` (trailing slash) → `307` redirect

## 7. Admin catalogue and images

ClamAV must be healthy for uploads.

- [ ] **CAT-19** [02](02-catalog.md) — Create category `{"name": "Lamps", "slug": "lamps"}` → `201`; audit row; appears in public `GET /categories`
- [ ] **CAT-20** [02](02-catalog.md) — Create another with slug `lamps` → `409 SLUG_CONFLICT`
- [ ] **CAT-21** [02](02-catalog.md) — Create with slug `Desk Lamps` → `422 VALIDATION_ERROR` on `slug`
- [ ] **CAT-22** [02](02-catalog.md) — `PATCH` it `{"is_active": false}` → `200`; gone from public `/categories`
- [ ] **CAT-23** [02](02-catalog.md) — `DELETE` it (no products) → `204`; then `PATCH` it → `409 INVALID_STATE_TRANSITION`; creating a new `lamps` now works
- [ ] **CAT-24** [02](02-catalog.md) — `DELETE` the `toys-figures` category → `409 CATEGORY_IN_USE`
- [ ] **CAT-25** [02](02-catalog.md) — Create material `pla` → `409 SLUG_CONFLICT` (PLA exists, case-insensitive)
- [ ] **CAT-26** [02](02-catalog.md) — `GET /admin/categories?include_deleted=true` → archived categories listed with `deleted_at` set
- [ ] **CAT-27** [02](02-catalog.md) — As the customer, `POST /admin/categories` → `404 NOT_FOUND`
- [ ] **CAT-28** [02](02-catalog.md) — As the admin, `POST /admin/colours` without the CSRF header → `403 CSRF_INVALID`
- [ ] **CAT-29** [02](02-catalog.md) — Create the physical product above → `201`, `version: 1`; visible at `GET /products/desk-lamp`; audit `product.created`
- [ ] **CAT-30** [02](02-catalog.md) — Create an STL with `"batch_size": 1` → `422 VALIDATION_ERROR` naming `batch_size`
- [ ] **CAT-31** [02](02-catalog.md) — Create a physical product without `purchase_mode` → `422 VALIDATION_ERROR`
- [ ] **CAT-32** [02](02-catalog.md) — Create with `"price": {"amount_cents": 100, "currency": "EUR"}` → `422 VALIDATION_ERROR`
- [ ] **CAT-33** [02](02-catalog.md) — `PATCH` with `version: 1` and a new price → `200`, `version: 2`
- [ ] **CAT-34** [02](02-catalog.md) — `PATCH` again with `version: 1` → `409 VERSION_CONFLICT`, `current_version: 2`; nothing written
- [ ] **CAT-35** [02](02-catalog.md) — `PATCH` `{"version": 2, "type": "stl"}` → `422 VALIDATION_ERROR`
- [ ] **CAT-36** [02](02-catalog.md) — `PATCH` `{"version": 2, "is_available": false}` → storefront shows `is_available: false`, `can_add_to_cart: false`
- [ ] **CAT-37** [02](02-catalog.md) — `PATCH` `{"version": 3, "purchase_mode": "whatsapp_only"}` → storefront `can_add_to_cart: false`; a cart holding it is refused at checkout (see ORD tests)
- [ ] **CAT-38** [02](02-catalog.md) — `DELETE ?version=1` (stale) → `409 VERSION_CONFLICT`
- [ ] **CAT-39** [02](02-catalog.md) — `DELETE` with the current version → `204`; `GET /products/desk-lamp` → `404`; admin `GET` still shows it with `deleted_at`
- [ ] **CAT-40** [02](02-catalog.md) — Create another product with slug `desk-lamp` → `201` (the deleted one freed the slug)
- [ ] **CAT-41** [02](02-catalog.md) — `GET /admin/products?deleted=true` → only deleted products
- [ ] **CAT-42** [02](02-catalog.md) — Upload a small PNG to the CAT-40 product → `201`, `is_cover: true`, `sort_order: 0`; it shows as `cover_image` on the storefront
- [ ] **CAT-43** [02](02-catalog.md) — Upload a second image → `201`, `is_cover: false`, `sort_order: 1`
- [ ] **CAT-44** [02](02-catalog.md) — `PUT …/{second}/cover` → `200`; the first is no longer cover
- [ ] **CAT-45** [02](02-catalog.md) — `PUT …/order` with the two ids reversed → `200`, `sort_order` 0 and 1 swapped
- [ ] **CAT-46** [02](02-catalog.md) — `PUT …/order` with only one id → `422 VALIDATION_ERROR`
- [ ] **CAT-47** [02](02-catalog.md) — `DELETE` the cover while the other image is live → `409 INVALID_STATE_TRANSITION`
- [ ] **CAT-48** [02](02-catalog.md) — Upload a `.txt` file renamed to `.png` → `422 UPLOAD_REJECTED`
- [ ] **CAT-49** [02](02-catalog.md) — Upload the EICAR test string saved as a file → `422 MALWARE_DETECTED` (needs ClamAV healthy)
- [ ] **CAT-50** [02](02-catalog.md) — `PATCH …/{id}` with `{"alt_text": null}` → `200`, `alt_text: null`
- [ ] **CAT-51** [02](02-catalog.md) — Upload with `docker compose stop clamav` → `503 SERVICE_UNAVAILABLE`; restart ClamAV afterwards
- [ ] **CAT-52** [02](02-catalog.md) — Create two STL products for the payment tests: `{"type": "stl", "category_id": "<tools-gadgets id>", "name": "Test STL A", "slug": "test-stl-a", "price": {"amount_cents": 500, "currency": "USD"}, "is_visible": true}`, and the same with `test-stl-b` → both `201`; both on the storefront with `can_offer: true`

## 8. Address book

- [ ] **ID-44** [01](01-identity.md) — As the seed customer, create the address above → `201`; `phone` is `+9613123456`; `is_default: true` (first address)
- [ ] **ID-45** [01](01-identity.md) — Create a second address with `is_default: false`, then `PUT …/{second}/default` → `200`; the list shows the second first with `is_default: true`, the first `false`
- [ ] **ID-46** [01](01-identity.md) — `PATCH` the first with `{"street": null}` → `200`, `street: null`
- [ ] **ID-47** [01](01-identity.md) — `PATCH` with `{}` → `422 VALIDATION_ERROR`
- [ ] **ID-48** [01](01-identity.md) — Create with `"phone": "+33 1 23 45 67 89"` → `422 VALIDATION_ERROR` on `phone`
- [ ] **ID-49** [01](01-identity.md) — Create without `landmark_notes` → `422 VALIDATION_ERROR`
- [ ] **ID-50** [01](01-identity.md) — As a second customer, `GET` the seed customer's address id → `404 NOT_FOUND`
- [ ] **ID-51** [01](01-identity.md) — Delete the default address → `204`; the list has no default
- [ ] **ID-52** [01](01-identity.md) — As an unverified account, create an address → `403 EMAIL_VERIFICATION_REQUIRED`; `GET` the list still `200`
- [ ] **ID-53** [01](01-identity.md) — Create without the CSRF header → `403 CSRF_INVALID`

## 9. Offers (before anyone buys `dragon-stl`)

- [ ] **NEG-01** [06](06-negotiation.md) — Offer 100 on `dragon-stl` → `422 OFFER_BELOW_MINIMUM`, `minimum.amount_cents: 490`
- [ ] **NEG-02** [06](06-negotiation.md) — Offer 800 → `422 VALIDATION_ERROR` on `amount_cents` (above the list price)
- [ ] **NEG-03** [06](06-negotiation.md) — Offer on `moon-lamp` → `422 PRODUCT_NOT_PURCHASABLE`, `reason: not_negotiable`
- [ ] **NEG-04** [06](06-negotiation.md) — Offer on `low-poly-vase-stl` → `422`, `reason: unavailable`
- [ ] **NEG-05** [06](06-negotiation.md) — Offer 600 on `dragon-stl` → `201`, `awaiting_admin`, `allowed_actions: ["withdraw"]`; admin has an `offer` notification
- [ ] **NEG-06** [06](06-negotiation.md) — Offer again on `dragon-stl` → `409 OFFER_ALREADY_ACTIVE`
- [ ] **NEG-07** [06](06-negotiation.md) — Customer tries `counter` on NEG-05 → `409 OFFER_NOT_YOUR_TURN`
- [ ] **NEG-08** [06](06-negotiation.md) — Admin: `GET /admin/offers` → NEG-05 first, with `customer.email`
- [ ] **NEG-09** [06](06-negotiation.md) — Admin counters 680 → `200`, `awaiting_customer`, new `responds_by`; customer gets `offer_countered` email
- [ ] **NEG-10** [06](06-negotiation.md) — Admin counters again → `409 OFFER_NOT_YOUR_TURN`
- [ ] **NEG-11** [06](06-negotiation.md) — Customer accepts with `expected_amount_cents: 600` → `409 OFFER_AMOUNT_CHANGED`, `current_amount.amount_cents: 680`
- [ ] **NEG-12** [06](06-negotiation.md) — Customer counters 400 → `422 OFFER_BELOW_MINIMUM`
- [ ] **NEG-13** [06](06-negotiation.md) — Customer counters 650 → `200`, `awaiting_admin`
- [ ] **NEG-14** [06](06-negotiation.md) — Admin accepts with `expected_amount_cents: 650` → `200`, `accepted`, `agreed_amount` 650, `checkout_expires_at` ≈ now + 24 h, `responds_by: null`; customer `offer_accepted` email
- [ ] **NEG-15** [06](06-negotiation.md) — Customer withdraws the accepted offer → `409 INVALID_STATE_TRANSITION`, `offer_status: accepted`
- [ ] **NEG-16** [06](06-negotiation.md) — Second customer offers 600 on `dragon-stl`; admin rejects with a reason → `200`, `rejected`, `cooldown_until` ≈ now + 7 days; `offer_rejected` email
- [ ] **NEG-17** [06](06-negotiation.md) — Second customer offers again → `422 OFFER_COOLDOWN_ACTIVE`, `cooldown_until`
- [ ] **NEG-18** [06](06-negotiation.md) — Second customer offers on `phone-stand-stl`, then withdraws → `200`, `withdrawn`; admins get an in-app `offer.withdrawn`
- [ ] **NEG-19** [06](06-negotiation.md) — Admin sets `accepting_orders` false; customer submits an offer; admin counters an existing one → submit `503 ORDERS_PAUSED`; the counter still works (BR-040). Set it back
- [ ] **NEG-27** [06](06-negotiation.md) — Second customer: `GET /me/offers/{NEG-05 id}` → `404 NOT_FOUND`
- [ ] **NEG-28** [06](06-negotiation.md) — `GET /admin/offers?responds_before=2026-12-01` → `422` (needs a time and offset)

## 10. Cart

- [ ] **ORD-01** [03](03-ordering.md) — Seed customer: `GET /cart` before any write (or after emptying) → `200`; `items: []`
- [ ] **ORD-02** [03](03-ordering.md) — Add `moon-lamp` quantity 2 → `200`; one line, quantity 2, `max_quantity` set, `payment_methods: ["online","cash"]`
- [ ] **ORD-03** [03](03-ordering.md) — Add `moon-lamp` quantity 1 again → quantity 3 (merged)
- [ ] **ORD-04** [03](03-ordering.md) — Add `moon-lamp` quantity 3 (3 + 3 > the seeded cap of 5) → `422 QUANTITY_EXCEEDS_LIMIT`, `max_quantity: 5`; cart unchanged
- [ ] **ORD-05** [03](03-ordering.md) — Add `dragon-stl` quantity 2 → `422 QUANTITY_EXCEEDS_LIMIT`, `max_quantity: 1`
- [ ] **ORD-06** [03](03-ordering.md) — Add `dragon-stl` twice with quantity 1 → both `200`; one line, quantity 1
- [ ] **ORD-07** [03](03-ordering.md) — Add `name-sign` → `422 PRODUCT_NOT_PURCHASABLE`, `reason: whatsapp_only`
- [ ] **ORD-08** [03](03-ordering.md) — Add `knight` → `422`, `reason: unavailable`
- [ ] **ORD-09** [03](03-ordering.md) — Add `prototype-gear`'s id (admin `GET /admin/products` to find it) → `422`, `reason: not_listed`
- [ ] **ORD-10** [03](03-ordering.md) — `PATCH` `moon-lamp` to `0` → `422 VALIDATION_ERROR`
- [ ] **ORD-11** [03](03-ordering.md) — `DELETE` a product not in the cart → `404 NOT_FOUND`
- [ ] **ORD-12** [03](03-ordering.md) — With `moon-lamp` and `dragon-stl` in the cart, `GET /cart` → `contains_physical` and `contains_digital` true; `payment_methods: ["online"]`
- [ ] **ORD-13** [03](03-ordering.md) — Admin raises `moon-lamp`'s price, then customer `GET /cart`; then the admin sets it back to 2400 → `price_changed: true`, `current_price` new, `snapshot_price` old; back to `price_changed: false` after the reset
- [ ] **ORD-14** [03](03-ordering.md) — Unverified account adds to the cart → `403 EMAIL_VERIFICATION_REQUIRED`; `GET /cart` still `200`

## 11. Checkout and payment (mock)

`PAYMENT_PROVIDER=mock`.

- [ ] **ORD-15** [03](03-ordering.md) — Set the cart to exactly `moon-lamp` ×2 (`PATCH` the quantity, `DELETE` any other line); cash delivery checkout (body above), key `ord15-cash-0001` → `201`; `status: in_progress`, `payment: null`, `amount_due` 4800; cart now empty; `order_cash_placed` in `email_outbox`
- [ ] **ORD-16** [03](03-ordering.md) — Send ORD-15 again with the same key and body → `201` with `Idempotent-Replayed: true`; same order; no second order
- [ ] **ORD-17** [03](03-ordering.md) — Same key, change `customer_note` → `409 IDEMPOTENCY_KEY_CONFLICT`
- [ ] **ORD-18** [03](03-ordering.md) — Checkout without `Idempotency-Key` → `422 VALIDATION_ERROR`
- [ ] **ORD-19** [03](03-ordering.md) — Checkout with an empty cart (new key) → `409 CART_EMPTY`
- [ ] **ORD-20** [03](03-ordering.md) — Cart `geometric-planter`; cash checkout (new key) while ORD-15 is open → `422 CASH_NOT_AVAILABLE` (`cash_max_open_orders` = 1)
- [ ] **ORD-21** [03](03-ordering.md) — Same cart, online delivery checkout (mock) → `201`; `pending_payment`, `payment.next_step: redirect`, `hold_expires_at` ≈ now + 30 min
- [ ] **ORD-22** [03](03-ordering.md) — Cart `dragon-stl` + `moon-lamp`; cash → `422 PAYMENT_METHOD_NOT_ALLOWED`, `reason: cash_requires_physical`
- [ ] **ORD-23** [03](03-ordering.md) — Cart `cable-organizer` (online only); cash → `422 PAYMENT_METHOD_NOT_ALLOWED`, `reason: cash_not_accepted`, `product_ids`
- [ ] **ORD-24** [03](03-ordering.md) — Cart `dragon-stl`; online without `accept_digital_final_sale` → `422 VALIDATION_ERROR` on `accept_digital_final_sale`
- [ ] **ORD-25** [03](03-ordering.md) — Cart `moon-lamp`; online with `"fulfillment_method": "delivery"` and no `address_id` → `422 INVALID_FULFILLMENT`
- [ ] **ORD-26** [03](03-ordering.md) — Cart `moon-lamp`; pickup without `contact_phone`; and separately pickup before `pickup_address` is set → both `422 INVALID_FULFILLMENT`
- [ ] **ORD-27** [03](03-ordering.md) — Admin raises `moon-lamp` price; checkout → `409 CART_PRICE_CHANGED` with `price_changes`; nothing charged
- [ ] **ORD-28** [03](03-ordering.md) — Repeat with `accepted_price_changes: [{product_id, amount_cents: <new>, currency: "USD"}]` → `201` at the new price
- [ ] **ORD-29** [03](03-ordering.md) — Add `"total_cents": 1` to the body → `422 VALIDATION_ERROR` (unknown field)
- [ ] **ORD-30** [03](03-ordering.md) — Cart `moon-lamp` ×5 (12 000 cents, over the 10 000 cap); cash checkout. The total cap is checked before the open-order limit, so ORD-15 being open does not matter → `422 CASH_PAYMENT_LIMIT_REACHED`, `reason: order_total`
- [ ] **ORD-31** [03](03-ordering.md) — Admin sets `accepting_orders` to false; checkout → `503 ORDERS_PAUSED`; set it back to true
- [ ] **ORD-32** [03](03-ordering.md) — Cart `moon-lamp`; admin switches it to `purchase_mode: whatsapp_only`; checkout; then the admin switches it back to `both` → `422 PRODUCT_NOT_PURCHASABLE`, `reason: whatsapp_only`
- [ ] **PAY-01** [04](04-payments.md) — (`mock`) An online order from ORD-21: `mock_pay.py <payment id> paid --send-to http://api:8000` → script prints `webhook answered 200`; order `in_progress`; payment `paid`; `order_payment_confirmed` in the outbox
- [ ] **PAY-02** [04](04-payments.md) — Run the script again with `paid` for the same payment → `200` again; nothing paid twice; still one `paid` payment
- [ ] **PAY-03** [04](04-payments.md) — `curl -X POST http://localhost:8000/api/v1/webhooks/payments/mock -H "Content-Type: application/json" -d '{"event_id":"x","type":"payment.updated","payment_reference":"<id>"}'` (no signature) → `401 WEBHOOK_SIGNATURE_INVALID`; nothing stored
- [ ] **PAY-04** [04](04-payments.md) — `POST /webhooks/payments/whish` (or `manual`) with any body → `404 NOT_FOUND`
- [ ] **PAY-05** [04](04-payments.md) — Online checkout of `test-stl-b` (CAT-52); `mock_pay.py <id> paid --captured-amount-cents 1 --send-to …` → late capture: order stays `pending_payment`; `GET /admin/payments?late_captured=true` lists it; a `late_capture` refund appears in `GET /admin/refunds`
- [ ] **PAY-06** [04](04-payments.md) — Online checkout of `test-stl-a` (CAT-52), pay it with `mock_pay.py … paid`, then `GET /me/stl-ownership?product_id=<test-stl-a>` → `owned: true`; the line is `awaiting_delivery`
- [ ] **PAY-15** [04](04-payments.md) — (`mock`) Confirm a mock payment → `409 MANUAL_CONFIRMATION_NOT_ALLOWED`
- [ ] **PAY-16** [04](04-payments.md) — (`mock`) Reconcile a mock payment → `202`, `reconcile: queued`; detail `history` shows `payment.reconcile_requested`
- [ ] **PAY-17** [04](04-payments.md) — Reason `"ok"` on confirm → `422 VALIDATION_ERROR`
- [ ] **PAY-18** [04](04-payments.md) — `GET /admin/payments?initiated_after=2026-11-01` → `422` (needs a time and offset)

## 12. Customer orders, ownership and retry

- [ ] **ORD-36** [03](03-ordering.md) — `GET /me/orders` → ORD-15 and ORD-21 orders, newest first
- [ ] **ORD-37** [03](03-ordering.md) — `GET /me/orders?status=pending_payment` → only unpaid online orders
- [ ] **ORD-38** [03](03-ordering.md) — `GET /me/orders?placed_after=2026-11-01` → `422 VALIDATION_ERROR` (no time and offset); `2026-11-01T00:00:00Z` works
- [ ] **ORD-39** [03](03-ordering.md) — `GET /me/orders/{ORD-15 id}` → `can_cancel: true`, `payment_due: true`, `payment: null`, line `pending`
- [ ] **ORD-41** [03](03-ordering.md) — A second customer reads ORD-15's id → `404 NOT_FOUND`
- [ ] **ORD-42** [03](03-ordering.md) — `phone-stand-stl`, not bought yet → `owned: false`
- [ ] **ORD-43** [03](03-ordering.md) — `test-stl-a` after PAY-06 paid it → `owned: true`; adding it to the cart now gives `409 PRODUCT_ALREADY_OWNED`
- [ ] **ORD-44** [03](03-ordering.md) — ORD-21's order while its attempt is `pending` → `409 PAYMENT_ALREADY_ACTIVE` with `payment_id`
- [ ] **ORD-45** [03](03-ordering.md) — `mock_pay.py <id> failed`, then retry with a new key → `201`, a new pending attempt
- [ ] **ORD-46** [03](03-ordering.md) — Retry ORD-15 (cash) → `409 INVALID_STATE_TRANSITION`, `reason: cash_order`
- [ ] **ORD-47** [03](03-ordering.md) — Retry an order whose 30 min hold has passed → `409`, `reason: checkout_hold_expired`

## 13. Fulfillment and cash handover

- [ ] **FUL-01** [05](05-fulfillment.md) — Admin `GET /admin/orders` → ORD-15 listed with `payment_due: true`; ORD-21 listed only after it is paid
- [ ] **FUL-02** [05](05-fulfillment.md) — `GET /admin/orders?status=pending_payment` → `422 VALIDATION_ERROR`
- [ ] **FUL-03** [05](05-fulfillment.md) — `GET /admin/orders?payment_due=true` → only unpaid cash orders
- [ ] **FUL-04** [05](05-fulfillment.md) — `GET /admin/orders/{ORD-21 id}` before payment → `200`; `payment_reached_paid: false`; the line's `available_actions` is `[]`
- [ ] **FUL-05** [05](05-fulfillment.md) — `GET /admin/orders/{ORD-15 id}` → the line's `available_actions` include `in_production` and `cancelled`
- [ ] **FUL-06** [05](05-fulfillment.md) — `PATCH` `{"admin_note": "Fragile, pack twice."}` → `200`; `admin_note` set; the customer's `GET /me/orders/{id}` has no `admin_note`
- [ ] **FUL-07** [05](05-fulfillment.md) — `PATCH` `{"admin_note": "x", "status": "completed"}` → `422 VALIDATION_ERROR`
- [ ] **FUL-08** [05](05-fulfillment.md) — Customer: `GET /admin/orders` → `404 NOT_FOUND`
- [ ] **FUL-09** [05](05-fulfillment.md) — ORD-15 (cash, delivery) line: `in_production` → `200`; no customer email; order `in_progress`
- [ ] **ORD-40** [03](03-ordering.md) — After FUL-09 moved ORD-15's line to `in_production`, the customer reads the order → the line still reads `pending`; `can_cancel: false`; no history entry for `in_production`
- [ ] **FUL-10** [05](05-fulfillment.md) — Same line: `ready_to_ship` → `200`; `order_ready` email queued
- [ ] **FUL-11** [05](05-fulfillment.md) — Same line: `shipped` → `200`; `order_shipped` email
- [ ] **FUL-12** [05](05-fulfillment.md) — Same line: `delivered` → `409 INVALID_STATE_TRANSITION`, `reason: cash_handover_required`
- [ ] **FUL-13** [05](05-fulfillment.md) — A fresh `pending` line: `shipped` (skipping steps) → `409`, `reason: not_a_legal_edge`, `fulfillment_status: pending`
- [ ] **FUL-14** [05](05-fulfillment.md) — Unpaid online order line: `in_production` → `409`, `reason: payment_required`
- [ ] **FUL-15** [05](05-fulfillment.md) — A `ready_to_ship` line: `cancelled` without `cancel_reason` → `409`, `reason: cancel_reason_required`
- [ ] **FUL-16** [05](05-fulfillment.md) — A `ready_to_ship` line: `cancelled` with `cancel_reason: no_show` → `409`, `reason: cancel_reason_not_allowed`
- [ ] **FUL-17** [05](05-fulfillment.md) — ORD-21's line (paid by PAY-01, delivery) through `in_production`, `ready_to_ship`, `shipped`, `delivered` → `200`; `order_delivered` email; order `completed` when every line is terminal
- [ ] **FUL-18** [05](05-fulfillment.md) — A paid `shipped` line: `returned`, then `shipped` again → both `200`; `order_shipped` announced again
- [ ] **FUL-19** [05](05-fulfillment.md) — ORD-15 after FUL-11 (line `shipped`): handover with 4799 → `422 CASH_AMOUNT_MISMATCH`, `amount_due` 4800; nothing written
- [ ] **FUL-20** [05](05-fulfillment.md) — Handover with exactly 4800 → `200`; line `delivered`; order `completed`; one `cash` payment `paid`; `order_delivered` email with a `cash_receipt`
- [ ] **FUL-21** [05](05-fulfillment.md) — Handover again → `409`, `reason: already_recorded`
- [ ] **FUL-22** [05](05-fulfillment.md) — Handover on a cash order still `in_production` → `409`, `reason: lines_not_ready`
- [ ] **FUL-23** [05](05-fulfillment.md) — Handover on an online order → `409`, `reason: not_a_cash_order`

## 14. Receipt and problem report

- [ ] **ORD-55** [03](03-ordering.md) — ORD-15 before handover: confirm receipt → `409 INVALID_STATE_TRANSITION`, `reason: no_delivered_line`
- [ ] **ORD-56** [03](03-ordering.md) — After the cash handover (FUL tests): confirm receipt → `200`; lines have `receipt_confirmed_at`; status unchanged
- [ ] **ORD-57** [03](03-ordering.md) — Report a problem → `201`; `problem_reported_at` set; a new item in `GET /admin/contact-messages`
- [ ] **ORD-58** [03](03-ordering.md) — Report with `"message": "   "` → `422 VALIDATION_ERROR`

## 15. Reviews that depend on a delivery

- [ ] **ENG-16** [07](07-engagement.md) — After FUL-20 hands `moon-lamp` over to the seed customer, read ENG-11's review in `GET /me/reviews` → `is_verified_purchase: true` (recomputed when the line changed, BR-104)

## 16. Cancellation, refusals and cash blocks

- [ ] **ORD-48** [03](03-ordering.md) — A fresh cash order, all lines `pending`: cancel → `200`; status `cancelled`; `order_cancelled` email; no refund
- [ ] **ORD-49** [03](03-ordering.md) — Cancel it again → `409 ORDER_NOT_CANCELLABLE`
- [ ] **ORD-50** [03](03-ordering.md) — A paid (mock) physical order, all `pending`: cancel → `200`; a `refunds[]` entry `kind: cancellation`, `status: processing`; `order_refund_issued` email
- [ ] **ORD-51** [03](03-ordering.md) — An order after the admin moved a line to `in_production` → `409 ORDER_NOT_CANCELLABLE`
- [ ] **ORD-52** [03](03-ordering.md) — An unpaid online order → `409 ORDER_NOT_CANCELLABLE`
- [ ] **ORD-53** [03](03-ordering.md) — An STL-only paid order → `409 ORDER_NOT_CANCELLABLE`
- [ ] **ORD-54** [03](03-ordering.md) — Right after ORD-48, a new cash checkout → `422 CASH_NOT_AVAILABLE` (the cancelled cash order counts for 24 h)
- [ ] **FUL-24** [05](05-fulfillment.md) — A new cash delivery order (use a second customer if the seed customer already holds an open or recently self-cancelled cash order); line to `in_production`, then `ready_to_ship`; cancel with `cancel_reason: refused` → `200`; order `cancelled`; no refund; a cash block appears (ORD-63)
- [ ] **FUL-25** [05](05-fulfillment.md) — Paid (mock) order, line `in_production`: cancel with no `cancel_reason` → `200`; a pending `cancellation` refund for the line total; `order_refund_issued` email
- [ ] **FUL-26** [05](05-fulfillment.md) — An unpaid online order → `409`, `reason: payment_required`
- [ ] **FUL-27** [05](05-fulfillment.md) — An order whose lines are all `delivered` → `409`, `reason: no_cancellable_line`
- [ ] **FUL-28** [05](05-fulfillment.md) — A `ready_to_ship` order without `cancel_reason` → `409`, `reason: cancel_reason_required`
- [ ] **ORD-63** [03](03-ordering.md) — After FUL-24 (a refused cash order): `GET /admin/cash-blocks?active=true` → one block, `reason: refused`
- [ ] **ORD-64** [03](03-ordering.md) — Search by the order's phone written differently (`+961 71 123 456`) → the same block
- [ ] **ORD-65** [03](03-ordering.md) — Search with `"phone": "+33612345678"` → `422 VALIDATION_ERROR`
- [ ] **ORD-66** [03](03-ordering.md) — The blocked customer tries a cash checkout → `422 CASH_NOT_AVAILABLE`
- [ ] **ORD-67** [03](03-ordering.md) — Clear the block, then clear it again → `200` with `active: false`; second `200` unchanged; cash checkout works again (if no open cash order)

## 17. Manual payment provider

Switch to `PAYMENT_PROVIDER=manual` and recreate `api` and `worker` (overview §4.4).

- [ ] **ORD-33** [03](03-ordering.md) — Cart `phone-stand-stl`; online checkout with `accept_terms`, `accept_digital_final_sale`, no `contact_phone` → `422 CONTACT_PHONE_REQUIRED`
- [ ] **ORD-34** [03](03-ordering.md) — Same with `"contact_phone": "71 123 456"` → `201`; `pending_payment`, `payment.provider: manual`, `redirect_url: null`, `next_step: await_admin_contact`, `hold_expires_at` ≈ now + 7 days; admin gets a `payment.alert.manual_payment_due` notification
- [ ] **ORD-35** [03](03-ordering.md) — Place two more unpaid manual orders (online physical orders work: `moon-lamp`, delivery), so three are unpaid, then try a fourth → the fourth answers `422 MANUAL_ORDER_LIMIT_REACHED`, `max_open_orders: 3`
- [ ] **PAY-07** [04](04-payments.md) — (`manual`) Admin: `GET /admin/payments?awaiting_confirmation=true` → ORD-34's payment, with `hold_expires_at`
- [ ] **PAY-08** [04](04-payments.md) — Confirm it with the exact total and a 10+ character reason → `200`, `outcome: apply_paid`; order `in_progress`; STL line `awaiting_delivery`; customer `order_payment_confirmed` email
- [ ] **PAY-09** [04](04-payments.md) — Confirm it again with the same reference → `200`, `outcome: noop`
- [ ] **PAY-10** [04](04-payments.md) — Confirm it again with another reference → `409 PAYMENT_ALREADY_PAID_OTHER_REFERENCE`
- [ ] **PAY-11** [04](04-payments.md) — One of ORD-35's unpaid manual orders: confirm with 1 cent less → `422 PAYMENT_AMOUNT_MISMATCH`, `expected_amount_cents`; nothing written
- [ ] **PAY-12** [04](04-payments.md) — Same order: record-capture with the smaller amount (new key) → `201`, a `refund_id`; payment `failed`, `late_captured_at` set; the refund is in the queue
- [ ] **PAY-13** [04](04-payments.md) — ORD-35's other unpaid manual order: record-capture with its exact amount → `409 INVALID_STATE_TRANSITION`, `reason: use_confirm`
- [ ] **PAY-14** [04](04-payments.md) — (`manual`) Reconcile a manual payment → `503 PAYMENT_VERIFICATION_UNAVAILABLE`
- [ ] **ORD-59** [03](03-ordering.md) — The PAY-13 order (still unpaid, `manual`): release with a 10+ character reason → `200`; order `cancelled`; customer gets `order_checkout_expired`
- [ ] **ORD-60** [03](03-ordering.md) — Release PAY-05's order (unpaid, `mock`) within a day of placing it → `409`, `reason: grace_not_elapsed`, `release_available_at`
- [ ] **ORD-61** [03](03-ordering.md) — Release a cash order → `409`, `reason: cash_order`
- [ ] **ORD-62** [03](03-ordering.md) — Reason `"too short"` → `422 VALIDATION_ERROR`

## 18. STL delivery

- [ ] **FUL-29** [05](05-fulfillment.md) — After PAY-06 and PAY-08: `GET /admin/stl-deliveries` → the paid `test-stl-a` and `phone-stand-stl` lines are listed, oldest first, with the customer's email
- [ ] **FUL-30** [05](05-fulfillment.md) — Transition it to `delivered` with `reason: "Sent from Drive"` → `200`; line `delivered` with `fulfilled_at`; order `completed` (if no other live line); `order_stl_delivered` in the outbox; gone from the queue
- [ ] **FUL-31** [05](05-fulfillment.md) — Transition it to `delivered` again → `409`, `reason: already_delivered`, `fulfilled_at`
- [ ] **FUL-32** [05](05-fulfillment.md) — Transition an STL line to `cancelled` → `409`, `reason: not_a_legal_edge`

## 19. Offer checkout and expiry

Switch back to `PAYMENT_PROVIDER=mock` and recreate `api` and `worker`.

- [ ] **NEG-20** [06](06-negotiation.md) — NEG-14 offer: `POST /me/offers/{id}/checkout` without `Idempotency-Key` → `422 VALIDATION_ERROR`
- [ ] **NEG-21** [06](06-negotiation.md) — Same with a key, `accept_terms` and `accept_digital_final_sale` (on `manual` add `contact_phone`) → `201`, `order.source: offer`, one line at 650
- [ ] **NEG-22** [06](06-negotiation.md) — Checkout the same offer again with a new key → `409 PAYMENT_ALREADY_ACTIVE` (its attempt is live)
- [ ] **NEG-23** [06](06-negotiation.md) — Pay the order (mock_pay or manual confirm) → offer `paid` with a `system/paid` round; the STL is owned
- [ ] **NEG-24** [06](06-negotiation.md) — A second customer's offer whose checkout window passed (set `offer_checkout_window` to 3600, accept, wait over an hour) → checkout answers `410 OFFER_CHECKOUT_EXPIRED`; after the next job run the offer is `checkout_expired`
- [ ] **NEG-25** [06](06-negotiation.md) — (Long) Set `offer_response_window` to 3600; submit; wait over an hour → within 5 minutes after the deadline the offer is `expired`; any answer gives `410 OFFER_EXPIRED`
- [ ] **NEG-26** [06](06-negotiation.md) — A customer holds a live offer on an STL, then buys it through the cart and pays → the offer becomes `auto_closed`; answering it gives `409 INVALID_STATE_TRANSITION`, `offer_status: auto_closed`

## 20. Refunds and chargebacks

Still on `mock`.

- [ ] **PAY-19** [04](04-payments.md) — ORD-15 after its cash handover (FUL-20; line `delivered`, 4800): refund 1200 of the line, new key → `201`, `pending`; order `partially_refunded`; the customer's `GET /me/orders/{id}` shows `refunds[]` `processing`
- [ ] **PAY-20** [04](04-payments.md) — Same body, same key → `201` replayed (`Idempotent-Replayed: true`); still one refund
- [ ] **PAY-21** [04](04-payments.md) — Refund 5000 on that line → `422 REFUND_EXCEEDS_AVAILABLE`, `available`
- [ ] **PAY-22** [04](04-payments.md) — A paid order whose line is still `pending`: refund the whole line → `422 REFUND_REQUIRES_CANCELLATION`
- [ ] **PAY-23** [04](04-payments.md) — Refund on an unpaid cash order → `409 ORDER_NOT_PAID`
- [ ] **PAY-24** [04](04-payments.md) — Settle PAY-19's refund with a reference → `200`, `settled`; gone from `GET /admin/refunds`; listed with `queue=false`; customer sees `refunded`
- [ ] **PAY-25** [04](04-payments.md) — Settle it again → `200`, unchanged
- [ ] **PAY-26** [04](04-payments.md) — Another refund: fail it → `200`, `failed`, `owed: true`; still in the queue
- [ ] **PAY-27** [04](04-payments.md) — Reissue it (new key) → `201`, a new `pending` refund; the old one has `reissued_by_refund_id`
- [ ] **PAY-28** [04](04-payments.md) — Reissue the old one again (another key) → `409 INVALID_STATE_TRANSITION`, `reason: already_reissued`
- [ ] **PAY-29** [04](04-payments.md) — Void the new pending refund → `200`, `voided`; customer gets `order_refund_cancelled`
- [ ] **PAY-30** [04](04-payments.md) — Void a settled refund → `409 INVALID_STATE_TRANSITION`, `reason: already_settled`
- [ ] **PAY-31** [04](04-payments.md) — Refund the full balance of a delivered line → the line becomes `refunded`; when every line is covered the order becomes `refunded`
- [ ] **PAY-32** [04](04-payments.md) — Settle the PAY-05 `late_capture` refund → `200`; the order (never paid) is unchanged
- [ ] **PAY-33** [04](04-payments.md) — ORD-21's paid (mock) order, its line delivered in FUL-17: record a refund for part of the line (leave it pending), then a chargeback for the payment's full amount with items covering the rest → `201`; the pending refund is now `voided` with `void_reason` "absorbed by chargeback …"; order `refunded`
- [ ] **PAY-34** [04](04-payments.md) — Same dispute reference again (new key) → `409 CHARGEBACK_DUPLICATE`
- [ ] **PAY-35** [04](04-payments.md) — Items totalling less than the chargeable amount → `422 CHARGEBACK_ALLOCATION_INVALID` with `chargeable_cents`
- [ ] **PAY-36** [04](04-payments.md) — Chargeback on a cash payment → `422 CHARGEBACK_NOT_ONLINE`
- [ ] **PAY-37** [04](04-payments.md) — `GET /admin/orders/{id}/chargebacks` → the PAY-33 chargeback; it never appears in `GET /admin/refunds`
- [ ] **FUL-33** [05](05-fulfillment.md) — Refund an awaiting STL line in full (PAY tests), then read the queue → the line is `refunded` and no longer listed; `GET /me/stl-ownership` answers `owned: false`

## 21. Notifications and wishlist

- [ ] **ENG-01** [07](07-engagement.md) — Seed customer: `GET /me/notifications?read=false` → at least the two seeded `account` notifications
- [ ] **ENG-02** [07](07-engagement.md) — `PATCH` one with `{"read": true}` → `200`, `read: true`; it no longer appears with `read=false`
- [ ] **ENG-03** [07](07-engagement.md) — `PATCH` it with `{"read": "yes"}` → `422 VALIDATION_ERROR`
- [ ] **ENG-04** [07](07-engagement.md) — Second customer `PATCH`es the seed customer's notification id → `404 NOT_FOUND`
- [ ] **ENG-05** [07](07-engagement.md) — After a checkout → a new `order` notification; after a manual-payment checkout the admin has a `payment` notification with `event: payment.alert.manual_payment_due`
- [ ] **ENG-06** [07](07-engagement.md) — `PUT /me/wishlist/{moon-lamp id}` twice → both `204`; the list has it once
- [ ] **ENG-07** [07](07-engagement.md) — `PUT` the `prototype-gear` id → `404 NOT_FOUND`
- [ ] **ENG-08** [07](07-engagement.md) — `DELETE` a product not on the list → `204`
- [ ] **ENG-09** [07](07-engagement.md) — Admin hides `moon-lamp` (`is_visible: false`); customer reads the list → the item shows `available: false`. Restore visibility afterwards
- [ ] **ENG-10** [07](07-engagement.md) — Admin: `GET /admin/analytics/wishlist` → `total_active` counts the row; `most_wishlisted` lists `moon-lamp` with its `wishlist_count`

## 22. Reviews and moderation

- [ ] **ENG-11** [07](07-engagement.md) — Review `moon-lamp` with rating 5 → `201`, `is_verified_purchase: false`; `GET /products/moon-lamp` shows `review_count: 1`, `average_rating: 5.0`
- [ ] **ENG-12** [07](07-engagement.md) — Review `moon-lamp` again → `409 REVIEW_ALREADY_EXISTS`
- [ ] **ENG-13** [07](07-engagement.md) — Body `"see https://example.com"` → `422 REVIEW_CONTENT_REJECTED`, `reason: link`
- [ ] **ENG-14** [07](07-engagement.md) — Rating 6 → `422 VALIDATION_ERROR`
- [ ] **ENG-15** [07](07-engagement.md) — `PATCH` rating to 3 → `200`, `edited: true`; product `average_rating: 3.0`
- [ ] **ENG-17** [07](07-engagement.md) — Review `name-sign` (WhatsApp only) → `201`; the public list never shows a badge for it
- [ ] **ENG-18** [07](07-engagement.md) — `GET /products/moon-lamp/reviews?verified_purchase=true` → only badged reviews
- [ ] **ENG-19** [07](07-engagement.md) — Second customer `PATCH`es the seed customer's review → `404 NOT_FOUND`
- [ ] **ENG-20** [07](07-engagement.md) — `DELETE` own review, then post a new one → `204`, then `201`
- [ ] **ENG-21** [07](07-engagement.md) — Admin hides ENG-11's review with a reason → `200`, `is_hidden: true`; the public list no longer shows it; product rating recomputed; the author still sees it with `is_hidden: true`
- [ ] **ENG-22** [07](07-engagement.md) — Hide it again → `409 INVALID_STATE_TRANSITION`, `is_hidden: true`
- [ ] **ENG-23** [07](07-engagement.md) — Restore it → `200`, visible again
- [ ] **ENG-24** [07](07-engagement.md) — Hide a review its author deleted → `404 NOT_FOUND`

## 23. Bring Your Idea

Clear the rate-limit counters after ENG-28.

- [ ] **ENG-25** [07](07-engagement.md) — Logged out: submit with the dummy captcha, one PNG → `201` `{id, created_at}`; admins get a `custom_request` notification
- [ ] **ENG-26** [07](07-engagement.md) — Submit with a `.txt` file as `attachments` → `422 UPLOAD_REJECTED`, `loc` `["body","attachments",0]`
- [ ] **ENG-27** [07](07-engagement.md) — Submit with captcha `wrong` → `400 CAPTCHA_INVALID`
- [ ] **ENG-28** [07](07-engagement.md) — Keep submitting valid requests with the same email → `429 RATE_LIMITED` once 5 have passed the captcha in the hour from this IP or email; ENG-25 to ENG-27 may already count (clear the counters afterwards)
- [ ] **ENG-29** [07](07-engagement.md) — Admin lists requests → ENG-25 first with `status: new`, `attachment_count: 1`
- [ ] **ENG-30** [07](07-engagement.md) — Transition `new → quoted` → `409 INVALID_STATE_TRANSITION`
- [ ] **ENG-31** [07](07-engagement.md) — `new → contacted`, then `contacted → quoted` without an amount → `200`; then `422 VALIDATION_ERROR`
- [ ] **ENG-32** [07](07-engagement.md) — `contacted → quoted` with `quoted_amount_cents: 4500`, then `in_progress`, `completed`, `closed` → each `200`; outcome `won` after `in_progress`
- [ ] **ENG-33** [07](07-engagement.md) — Download the attachment → `200` with the image; headers `Content-Disposition: attachment`, `Cache-Control: no-store`
- [ ] **ENG-34** [07](07-engagement.md) — Customer downloads it → `404 NOT_FOUND`
- [ ] **ENG-35** [07](07-engagement.md) — Funnel: `GET /admin/analytics/custom-requests/funnel?from=2026-11-01T00:00:00Z&to=2026-12-01T00:00:00Z` → `200`; `submitted`, `contacted`, `quoted`, `won`, `lost`, `open`, `quoted_total_cents`, `won_total_cents`, `currency: USD`
- [ ] **ENG-36** [07](07-engagement.md) — Funnel with `from=2026-11-01` (date only) → `422 VALIDATION_ERROR` on `from`
- [ ] **ENG-37** [07](07-engagement.md) — Funnel with a range over 366 days, or `to` before `from` → `422 VALIDATION_ERROR` on `to`

## 24. Contact messages

- [ ] **ENG-38** [07](07-engagement.md) — Logged out: send a message → `201`; admin list shows it `new` with `user_id: null`
- [ ] **ENG-39** [07](07-engagement.md) — Logged in as the customer **with** CSRF → `201`; `user_id` is the customer
- [ ] **ENG-40** [07](07-engagement.md) — Logged in **without** CSRF → `403 CSRF_INVALID`
- [ ] **ENG-41** [07](07-engagement.md) — Captcha `wrong` → `400 CAPTCHA_INVALID`
- [ ] **ENG-42** [07](07-engagement.md) — Admin `PATCH` `new → replied` → `200`
- [ ] **ENG-43** [07](07-engagement.md) — Admin `PATCH` `replied → read` → `409 INVALID_STATE_TRANSITION`
- [ ] **ENG-44** [07](07-engagement.md) — Admin `GET /admin/contact-messages?created_after=2026-11-01` → `422` (needs a time and offset)

## 25. Audit log, analytics and data export

- [ ] **ADM-15** [08](08-platform-admin.md) — `GET /admin/audit-logs?action=user.login_failed` → the failed logins from ID-14
- [ ] **ADM-16** [08](08-platform-admin.md) — Take the `X-Request-ID` of any admin write, then `GET /admin/audit-logs?request_id=<it>` → exactly that write's row(s)
- [ ] **ADM-17** [08](08-platform-admin.md) — `GET /admin/audit-logs?created_after=2026-11-01` → `422 VALIDATION_ERROR` naming `created_after`
- [ ] **ADM-18** [08](08-platform-admin.md) — `created_after` later than `created_before` (both full timestamps) → `422`, "must be later than created_after"
- [ ] **ADM-19** [08](08-platform-admin.md) — `GET /admin/analytics/overview` (no query) → `200`; `timezone: Asia/Beirut`; the range is the last 30 days; `net.total_cents` includes PAY-01 and FUL-20
- [ ] **ADM-20** [08](08-platform-admin.md) — `GET /admin/analytics/revenue?from=2026-11-01&to=2026-11-30&group_by=week` → `200`; weekly buckets
- [ ] **ADM-21** [08](08-platform-admin.md) — `GET /admin/analytics/revenue?from=2026-11-30&to=2026-11-01` → `400 INVALID_DATE_RANGE`
- [ ] **ADM-22** [08](08-platform-admin.md) — `GET /admin/analytics/revenue?from=2024-01-01&to=2026-01-01` (over 366 days) → `400 INVALID_DATE_RANGE`
- [ ] **ADM-23** [08](08-platform-admin.md) — `GET /admin/analytics/stl-sales` after paying an STL → the STL listed with `units` and `net_cents`
- [ ] **ADM-24** [08](08-platform-admin.md) — `GET /admin/analytics/top-rated-products?min_reviews=1` → products with at least one visible review
- [ ] **ADM-25** [08](08-platform-admin.md) — `GET /admin/analytics/recent-purchases` → the latest paid orders, newest first
- [ ] **ADM-26** [08](08-platform-admin.md) — Customer: `GET /admin/analytics/overview` → `404 NOT_FOUND`
- [ ] **ADM-27** [08](08-platform-admin.md) — Seed customer with CSRF set in Authorize: `GET /me/export` → `200`; JSON with the customer's addresses, orders, reviews and offers
- [ ] **ADM-28** [08](08-platform-admin.md) — Without the CSRF header → `403 CSRF_INVALID`
- [ ] **ADM-29** [08](08-platform-admin.md) — Keep exporting → refused with `429 RATE_LIMITED` once 3 exports are used within 24 hours (clear the counters afterwards)

## 26. Admin user management

- [ ] **ID-54** [01](01-identity.md) — Admin: `GET /admin/users?search=seed-customer&limit=1` → `200`, one item; an audit row `user.list_viewed`
- [ ] **ID-55** [01](01-identity.md) — Admin: `GET /admin/users?limit=101` → `422 VALIDATION_ERROR`
- [ ] **ID-56** [01](01-identity.md) — Admin: `GET /admin/users?cursor=abc` → `422 VALIDATION_ERROR` on `cursor`
- [ ] **ID-57** [01](01-identity.md) — Customer: `GET /admin/users` → `404 NOT_FOUND`, the same body as `GET /api/v1/admin/nothing-here`
- [ ] **ID-58** [01](01-identity.md) — Anonymous: `GET /admin/users` → `401 AUTH_REQUIRED`
- [ ] **ID-59** [01](01-identity.md) — Admin: `PATCH` the seed admin's own id with `{"is_active": false}` (only admin) → `409 INVALID_STATE_TRANSITION` (last active administrator)
- [ ] **ID-60** [01](01-identity.md) — Window A logged in as a test customer. Admin deactivates them → `200`, `is_active: false`; window A's next call answers `401`
- [ ] **ID-17** [01](01-identity.md) — Deactivate a test customer (ID-60), log in with the right password → `403 ACCOUNT_DISABLED`
- [ ] **ID-61** [01](01-identity.md) — Admin reactivates them with `{"is_active": true}` → `200`; they can log in again
- [ ] **ID-62** [01](01-identity.md) — `PATCH` with `{"is_active": true, "role": "admin"}` → `422 VALIDATION_ERROR`
- [ ] **ID-63** [01](01-identity.md) — `PATCH` ID-39's anonymised account → `409 INVALID_STATE_TRANSITION`

## 27. Account deletion

Use throwaway customers.

- [ ] **ID-39** [01](01-identity.md) — Fresh verified test customer with an address and a wishlist item, no orders: delete with the right password → `204`; login with the old email gives `401`; `select email from users where id = '<id>'` shows `deleted+…@invalid`
- [ ] **ID-40** [01](01-identity.md) — Wrong password → `401 INVALID_CREDENTIALS`; still logged in
- [ ] **ID-41** [01](01-identity.md) — Customer with an unpaid cash order (`in_progress`) → `409 ACCOUNT_DELETION_BLOCKED`, `reason: open_order`
- [ ] **ID-42** [01](01-identity.md) — Seed admin → `409`, `reason: administrator`
- [ ] **ID-43** [01](01-identity.md) — Register again with ID-39's old email → `202`; a new account

## 28. Last: spends seed credentials

Then save the new recovery codes, or run the seed with `--rotate-credentials`.

- [ ] **ID-31** [01](01-identity.md) — Verify with a recovery code from the credentials file → `204`; that code is now spent (do this last, or rotate the seed credentials afterwards)
- [ ] **ID-35** [01](01-identity.md) — As the MFA-complete admin, regenerate with the right password → `200`, ten new codes; an old code now gives `401 MFA_INVALID` at verify. **Save the new codes in the credentials file.**
- [ ] **ID-36** [01](01-identity.md) — Regenerate with a wrong password → `401 INVALID_CREDENTIALS`; old codes still valid

Total: 356 tests.
