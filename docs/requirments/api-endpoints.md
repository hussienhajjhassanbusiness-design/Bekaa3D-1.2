# Bekaa3D — API Endpoint Contract

**Document:** `api-endpoints.md`  
**Step:** 13 — API / Interface Design  
**Status:** V1 endpoint structure complete; ready for schema/OpenAPI implementation review  
**Source of truth:** `Bekaa3D_SRS_Complete.md` + frozen V1 `database-design.md`  
**Base API:** `/api/v1`

> **Important source rule:** The approved SRS names the required endpoint groups, features, security boundaries, state machines, and API conventions, but it does not prescribe every individual URL or Pydantic schema name. Exact paths, schema names, and a small number of low-level interaction details in this document are **V1 API design decisions**. They do not change the business requirements.

---

# 1. Contract Principles

1. Public and customer APIs live under `/api/v1`.
2. Admin APIs live under the separate `/api/v1/admin` router.
3. Payment-provider callbacks live under `/api/v1/webhooks`.
4. Operational health endpoints live outside the versioned business API.
5. The client never supplies trusted prices, totals, shipping rates, verified-purchase flags, STL ownership or delivery state, order status projections, or payment-confirmed state.
6. Every authenticated resource fetch by ID performs object-level authorization.
7. A caller who is authenticated but not allowed to know that a resource exists receives `404 NOT_FOUND`, not an existence-revealing `403`.
8. Every write by a normal account requires a verified email, except identity flows and explicitly public guest forms.
9. Every unsafe cookie-authenticated request uses CSRF protection.
10. Every collection endpoint is bounded either by cursor pagination or an explicit hard limit.
11. All externally visible errors use stable machine-readable codes.
12. State-machine mutations use explicit action/transition endpoints rather than unrestricted status-field PATCHes.
13. Side effects such as email delivery are committed via the transactional outbox and executed after commit.
14. Whish callbacks are notifications only; they never directly prove payment.
15. STL bytes are never streamed through FastAPI; the API authorizes and nginx serves via internal redirect.

---

# 2. Global API Conventions

| Concern | V1 Contract |
|---|---|
| Base path | `/api/v1` |
| Authentication | httpOnly, Secure, SameSite cookies |
| Access token | Short lived |
| Refresh token | Rotating; stored hashed server-side |
| CSRF | Double-submit token on unsafe cookie-authenticated methods |
| CSRF header | `X-CSRF-Token` |
| Dates | ISO-8601 UTC |
| Money | `{"amount_cents": 1999, "currency": "USD"}` |
| Enums | lowercase snake-case strings |
| Errors | RFC 9457 `application/problem+json` |
| Pagination | cursor-based |
| Page parameters | `cursor`, `limit` |
| Default page size | 20 — V1 API design decision |
| Maximum page size | 100 — V1 API design decision |
| Sorting | comma-separated fields; `-` prefix means descending |
| Filtering | allowlisted query parameters only |
| Idempotency | `Idempotency-Key` required on normal checkout, offer checkout, and refund creation |
| Rate limits | `RateLimit-*` response headers |
| Request correlation | response/problem includes stable `request_id` |
| Empty collection | `"items": []` |
| Unknown JSON fields | rejected on input schemas (`extra="forbid"`) |

## 2.1 Standard Cursor Page

```json
{
  "items": [],
  "next_cursor": null
}
```

`next_cursor = null` means there is no next page.

## 2.2 Stable Sorting

Every cursor-paginated query appends a deterministic unique tie-breaker internally, normally `id`, even when the caller sorts by another field.

Example:

```text
sort=-created_at
```

is internally equivalent to a stable ordering such as:

```text
created_at DESC, id DESC
```

The client does not construct or interpret cursors.

---

# 3. Authentication Levels

| Label | Meaning |
|---|---|
| **Public** | No login required |
| **Authenticated** | Valid session; email verification not required for read-only account operations |
| **Verified Customer** | Authenticated + verified email |
| **Admin + MFA** | Administrator session with MFA completed |
| **Provider** | External payment-provider request; no cookie auth |
| **System** | Internal worker/scheduler; not exposed as a public HTTP endpoint |

### Admin Information-Hiding Rule

- no authentication → `401 AUTH_REQUIRED`;
- authenticated non-admin calling an admin route → `404 NOT_FOUND`;
- admin without completed MFA → `401 MFA_REQUIRED`.

The last case arises only for an administrator whose MFA enrollment is not yet
confirmed. Login is MFA-gated (§8.1, §8.2 and
[ADR-017](../adr/ADR-017-login-gated-admin-mfa.md)): an administrator with an
enabled credential receives `202 MfaChallengeRead` and no session at all, so
they cannot reach an admin route to be challenged. No challenge is issued by
the admin boundary — the only source of one is `POST /auth/login`.

---

# 4. CSRF and Cookie Behaviour

1. Login/refresh sets or rotates the readable CSRF cookie used by the double-submit pattern.
2. Authenticated unsafe methods send the matching value in `X-CSRF-Token`.
3. Webhook endpoints do **not** use browser CSRF; they use provider/IP/signature controls.
4. Public guest forms do not rely on auth cookies and use captcha + rate limiting.
5. Logout clears auth cookies and revokes the current server-side session.

---

# 5. Error Contract

All API errors return `application/problem+json`.

Recommended shape:

```json
{
  "type": "https://bekaa3d.example/problems/PRODUCT_NOT_PURCHASABLE",
  "title": "Request cannot be completed",
  "status": 422,
  "detail": "Human-readable diagnostic text.",
  "instance": "/api/v1/checkout",
  "code": "PRODUCT_NOT_PURCHASABLE",
  "request_id": "req_...",
  "errors": []
}
```

The frontend renders its own message from `code`; `detail` is a diagnostic string, not user-facing copy.

## 5.1 SRS-Defined Stable Errors

| Status | Code | Meaning |
|---:|---|---|
| 400 | `MALFORMED_REQUEST` | Body cannot be parsed |
| 401 | `AUTH_REQUIRED` | No valid authentication |
| 403 | `EMAIL_VERIFICATION_REQUIRED` | Write attempted by unverified account |
| 404 | `NOT_FOUND` | Missing resource or intentionally hidden unauthorized resource |
| 409 | `PRODUCT_ALREADY_OWNED` | Customer already owns this STL (paid, unrefunded line) |
| 409 | `OFFER_ALREADY_ACTIVE` | Live offer already exists |
| 409 | `IDEMPOTENCY_KEY_CONFLICT` | Same key reused with a different request body |
| 410 | `OFFER_CHECKOUT_EXPIRED` | Accepted-offer checkout window elapsed |
| 422 | `QUANTITY_EXCEEDS_LIMIT` | Quantity exceeds product cap |
| 422 | `OFFER_BELOW_MINIMUM` | Offer below configured floor |
| 422 | `PRODUCT_NOT_PURCHASABLE` | Product cannot currently be bought online |
| 422 | `OFFER_COOLDOWN_ACTIVE` | Rejection cooldown active |
| 429 | `RATE_LIMITED` | Rate limit exceeded |
| 503 | `ORDERS_PAUSED` | Global checkout kill switch enabled |

## 5.2 Additional V1 Contract Errors

These codes are implementation additions needed to give the frontend deterministic handling for required SRS behaviours.

| Status | Code | Meaning |
|---:|---|---|
| 422 | `VALIDATION_ERROR` | Parsed body violates schema |
| 400 | `INVALID_TOKEN` | Verification/reset token invalid |
| 401 | `INVALID_CREDENTIALS` | Login failed; response remains enumeration-safe |
| 401 | `MFA_REQUIRED` | Admin login requires second factor |
| 401 | `MFA_INVALID` | MFA code/recovery code invalid |
| 403 | `ACCOUNT_DISABLED` | Account cannot authenticate/write |
| 403 | `CSRF_INVALID` | CSRF token missing/mismatch |
| 409 | `ACCOUNT_DELETION_BLOCKED` | Open order or unsettled refund prevents anonymisation |
| 409 | `CART_EMPTY` | Checkout attempted with no valid lines |
| 409 | `CART_PRICE_CHANGED` | Current product price differs from unconfirmed cart snapshot |
| 409 | `INVALID_STATE_TRANSITION` | Requested state-machine transition is illegal |
| 409 | `ORDER_NOT_CANCELLABLE` | Customer/admin cancellation cannot legally occur |
| 409 | `PAYMENT_ALREADY_ACTIVE` | Live payment already exists |
| 409 | `CATEGORY_IN_USE` | Category, material or colour cannot be archived while a live product uses it (VS-013) |
| 409 | `SLUG_CONFLICT` | Live slug already exists |
| 409 | `VERSION_CONFLICT` | The `version` sent is not the stored one; nothing was written. Body carries `current_version` (ADR-020) |
| 409 | `REVIEW_ALREADY_EXISTS` | Active user/product review already exists |
| 409 | `OFFER_NOT_YOUR_TURN` | Offer action attempted by wrong actor |
| 410 | `OFFER_EXPIRED` | Offer inactivity lifetime elapsed |
| 410 | `RESOURCE_EXPIRED` | Single-use/time-limited resource expired |
| 416 | `RANGE_NOT_SATISFIABLE` | Invalid byte range on an admin attachment download |
| 422 | `REFUND_EXCEEDS_AVAILABLE` | Requested refund exceeds refundable amount |
| 422 | `INVALID_FULFILLMENT` | Address/zone/method does not match cart contents |
| 422 | `UPLOAD_REJECTED` | Type/size/count/content validation failed |
| 422 | `MALWARE_DETECTED` | Uploaded content failed malware scan |
| 422 | `SETTING_INVALID` | Setting value does not match its declared type/range |
| 502 | `PAYMENT_PROVIDER_ERROR` | Provider call failed |
| 503 | `PAYMENT_VERIFICATION_UNAVAILABLE` | Automated verification unavailable and manual verification is required |
| 405 | `METHOD_NOT_ALLOWED` | Route exists but not for this method; response carries `Allow`. Under `/api/v1/admin` only an MFA-complete administrator ever sees it (VS-011); everyone else gets 401/404 per SEC-10 |
| 500 | `INTERNAL_ERROR` | Unexpected server fault; details are logged, never returned |
| 503 | `SERVICE_UNAVAILABLE` | A required dependency (database, Redis) is unreachable or timed out; retrying later is safe |

**Security note:** authentication, resend-verification, and password-reset flows must preserve the SRS anti-enumeration requirement. Do not leak account existence through response body, timing, or status differences.

---

# 6. Operational Endpoints

These are intentionally outside `/api/v1`.

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /health/live` | Public | — | `200 LivenessRead` | 503 | — | Process liveness only; no deep dependency probing |
| `GET /health/ready` | Public/infra | — | `200 ReadinessRead` | 503 | — | Checks required dependencies; includes app version/commit, never secrets |

---

# 7. Public Storefront Endpoints

## 7.1 Catalogue and Search

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/products` | Public | query params | `200 ProductPage` | 400, 429 | Cursor; filters: `type`, `category_id`, `material_id`, `colour_id`, `price_min_cents`, `price_max_cents`, `min_rating`, `featured`, `q`; sorts: `price`, `-price`, `-average_rating`, `-created_at` | Only non-deleted, visible products in active categories; unavailable products remain visible |
| `GET /api/v1/products/{slug}` | Public | — | `200 ProductDetail` | 404, 429 | — | Response includes relevant commerce capabilities and SEO fields |
| `GET /api/v1/products/{slug}/reviews` | Public | query params | `200 ReviewPage` | 404, 429 | Cursor; optional `rating`, `verified_purchase`; sort `-created_at` default | Hidden/deleted reviews excluded |
| `GET /api/v1/search/suggestions` | Public | `q`, `limit` | `200 SearchSuggestionList` | 400, 429 | Hard limit; V1 max 10 | Trigram typo tolerance |
| `GET /api/v1/categories` | Public | — | `200 CategoryList` | 429 | Hard-limited reference list | Active categories only |
| `GET /api/v1/materials` | Public | — | `200 MaterialList` | 429 | Hard-limited reference list | Active material values |
| `GET /api/v1/colours` | Public | — | `200 ColourList` | 429 | Hard-limited reference list | Active colour values |
| `GET /api/v1/settings/public` | Public | — | `200 PublicSettingsRead` | 429 | — | Strict allowlist only; e.g. WhatsApp number, pickup address/hours, accepting-orders state, free-shipping threshold |

### Public Product List Rules

- facets combine with logical AND;
- `q` searches translated product name/description;
- `material_id` and `colour_id` apply only where meaningful;
- server may reject nonsensical sort/filter combinations with `400 VALIDATION_ERROR`;
- `limit` is bounded by the global maximum.

---

## 7.2 Guest Lead / Contact Forms

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `POST /api/v1/custom-requests` | Public; captcha + rate limit | `multipart/form-data CustomRequestCreate` | `201 CustomRequestReceipt` | 400, 422 `UPLOAD_REJECTED` / `MALWARE_DETECTED`, 429 | — | Validates/re-encodes/scans private attachments; creates lead; admin-only attachments; no transaction/payment |
| `POST /api/v1/contact-messages` | Public; captcha + rate limit | `ContactMessageCreate` + captcha token | `201 ContactMessageReceipt` | 400, 422, 429 | — | Adds message to admin queue |

---

# 8. Authentication and MFA Endpoints

## 8.1 Core Authentication

| Method + Path | Auth / Authorization | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/auth/register` | Public | `RegisterRequest` | `202 RegistrationAccepted` | 400, 422, 429 | **Enumeration-safe:** same response whether address is new or already registered; if eligible, creates unverified account and enqueues verification email |
| `POST /api/v1/auth/login` | Public | `LoginRequest` | Customer: `200 SessionRead`; Admin needing MFA: `202 MfaChallengeRead` | 400, 401, 403, 429 | Progressive delay/lockout; successful customer login sets auth + CSRF cookies |
| `POST /api/v1/auth/logout` | Authenticated | — | `204` | 401, 403 CSRF | Revokes current session; clears cookies |
| `POST /api/v1/auth/refresh` | Authenticated refresh cookie | — | `204` | 401, 403 CSRF, 429 | Rotates refresh token/hash/version and CSRF cookie; detects token reuse |
| `POST /api/v1/auth/verify-email` | Public | `VerifyEmailRequest` | `204` | 400 `INVALID_TOKEN`, 410 `RESOURCE_EXPIRED`, 429 | Single-use token; audits account event |
| `POST /api/v1/auth/resend-verification` | Public or authenticated | `ResendVerificationRequest` | `202` | 429 | Uniform response regardless of account existence/state; outbox email if eligible |
| `POST /api/v1/auth/password-reset/request` | Public | `PasswordResetRequest` | `202` | 429 | Uniform response; enqueue reset email only when appropriate |
| `POST /api/v1/auth/password-reset/confirm` | Public | `PasswordResetConfirm` | `204` | 400, 410, 429 | Replaces password hash; revokes all sessions; audits security event |

## 8.2 Admin MFA

**V1 API design assumption:** TOTP is used for the administrator because the SRS requires admin MFA but does not name a mechanism.

Persistence is defined in Step 12 by `mfa_credentials` and one-time hashed `mfa_recovery_codes`.

| Method + Path | Auth / Authorization | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/auth/mfa/setup` | Authenticated admin enrollment session | `MfaSetupRequest` | `200 MfaSetupRead` | 401, 404, 429 | Returns TOTP setup material once; secret remains protected |
| `POST /api/v1/auth/mfa/setup/confirm` | Authenticated admin enrollment session | `MfaSetupConfirmRequest` | `200 MfaRecoveryCodesRead` | 401, 422, 429 | Enables MFA only after valid code; returns one-time recovery codes |
| `POST /api/v1/auth/mfa/verify` | MFA challenge | `MfaVerifyRequest` | `204` | 401 `MFA_INVALID`, 410, 429 | Completes admin login; sets full auth + CSRF cookies |
| `POST /api/v1/auth/mfa/recovery-codes/regenerate` | Admin + MFA | `MfaRecoveryRegenerateRequest` | `200 MfaRecoveryCodesRead` | 401, 404, 429 | Invalidates previous recovery codes; audit event |

### Registration Anti-Enumeration Behaviour

Registration never returns a distinguishable `EMAIL_ALREADY_REGISTERED` error.

- new email → create unverified account + queue verification email;
- existing unverified email → may queue/resend verification subject to rate limits;
- existing verified email → no account mutation; optional security notification;
- all cases return the same public `202 RegistrationAccepted` shape.

This follows SEC-06 and prevents registration from becoming an account-existence oracle.

There is no normal “disable MFA” endpoint in V1 because the SRS treats admin MFA as required.

---

# 9. Customer Account Endpoints

## 9.1 Profile and Data Rights

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/me` | Authenticated | — | `200 UserProfileRead` | 401 | — | Read allowed while unverified; no V1 mutable profile field exists, so there is no corresponding write endpoint |
| `GET /api/v1/me/export` | Verified Customer | — | `200 DataExportRead` | 401, 403, 429 | — | JSON export includes profile, addresses, orders (with STL delivery records), reviews, offers |
| `DELETE /api/v1/me` | Verified Customer; fresh-auth requirement | `AccountDeletionRequest` | `204` | 401, 403, 409 `ACCOUNT_DELETION_BLOCKED`, 429 | — | Anonymises; blocked by open orders/unsettled refunds; disables login |

`ACCOUNT_DELETION_BLOCKED` is an additional stable V1 code.

## 9.2 Address Book

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/me/addresses` | Authenticated | — | `200 AddressList` | 401 | Hard-limited | Own addresses only |
| `POST /api/v1/me/addresses` | Verified Customer | `AddressCreate` | `201 AddressRead` | 401, 403, 422 | — | Setting default clears prior default atomically |
| `GET /api/v1/me/addresses/{address_id}` | Authenticated; owner | — | `200 AddressRead` | 401, 404 | — | Object ownership |
| `PATCH /api/v1/me/addresses/{address_id}` | Verified Customer; owner | `AddressUpdate` | `200 AddressRead` | 401, 403, 404, 422 | — | Historical orders unaffected because they use snapshots |
| `DELETE /api/v1/me/addresses/{address_id}` | Verified Customer; owner | — | `204` | 401, 403, 404, 409 | — | Soft delete; reject deletion when needed by an in-progress checkout/order workflow |
| `PUT /api/v1/me/addresses/{address_id}/default` | Verified Customer; owner | — | `200 AddressRead` | 401, 403, 404 | — | Atomically switches default |

---

# 10. Cart, Shipping and Checkout

## 10.1 Cart

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/cart` | Authenticated | — | `200 CartRead` | 401 | — | Shows snapshot price + current price + `price_changed`; may include fulfillment-relevant summary |
| `POST /api/v1/cart/items` | Verified Customer | `CartItemAdd` | `200 CartRead` | 401, 403, 409 `PRODUCT_ALREADY_OWNED`, 422 `PRODUCT_NOT_PURCHASABLE` / `QUANTITY_EXCEEDS_LIMIT`, 429 | — | Existing product merges quantity; STL quantity forced to 1 |
| `PATCH /api/v1/cart/items/{product_id}` | Verified Customer | `CartItemQuantityUpdate` | `200 CartRead` | 401, 403, 404, 422, 429 | — | Sets absolute physical quantity; STL remains exactly 1 |
| `DELETE /api/v1/cart/items/{product_id}` | Verified Customer | — | `204` | 401, 403, 404 | — | Removes current cart line |

## 10.2 Shipping Zones

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/shipping-zones` | Verified Customer | — | `200 ShippingZoneList` | 401, 403 | Hard-limited | Active Lebanese zones/rates only; server remains rate authority |

V1 uses explicit zone selection. No automatic governorate→zone mapping endpoint exists.

## 10.3 Checkout

| Method + Path | Auth / Authorization | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/checkout` | Verified Customer | `CheckoutRequest` + required `Idempotency-Key` | `201 CheckoutRead` | 401, 403, 409 `CART_EMPTY` / `CART_PRICE_CHANGED` / `IDEMPOTENCY_KEY_CONFLICT` / `PAYMENT_ALREADY_ACTIVE`, 422 `INVALID_FULFILLMENT` / `PRODUCT_NOT_PURCHASABLE` / `QUANTITY_EXCEEDS_LIMIT`, 429, 503 `ORDERS_PAUSED`, 502 | Single transaction validates cart, recomputes amounts, snapshots order/lines/address/shipping/terms, creates pending payment, clears cart; returns provider redirect information |

### Price-Change Confirmation Contract

`CartRead` exposes old snapshot and current price.

When checkout detects a change not explicitly accepted:

```text
409 CART_PRICE_CHANGED
```

with a problem extension:

```json
{
  "price_changes": [
    {
      "product_id": "...",
      "old_amount_cents": 1000,
      "new_amount_cents": 1200,
      "currency": "USD"
    }
  ]
}
```

The retry includes exact accepted values in `CheckoutRequest.accepted_price_changes`.

If a price changes again after the user confirms, the request fails again rather than silently charging a new amount.

A materially changed retry uses a **new** idempotency key.

---

# 11. Customer Orders

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/me/orders` | Authenticated | query params | `200 OrderPage` | 401 | Cursor; optional `status`, `placed_after`, `placed_before`; default `-placed_at` | Own orders only |
| `GET /api/v1/me/orders/{order_id}` | Authenticated; owner | — | `200 OrderDetail` | 401, 404 | — | Includes lines, payment projection, refund summary and status history needed by customer |
| `POST /api/v1/me/orders/{order_id}/cancel` | Verified Customer; owner | `CustomerOrderCancelRequest` | `200 OrderDetail` | 401, 403, 404, 409 `ORDER_NOT_CANCELLABLE` / `INVALID_STATE_TRANSITION` | — | V1 decision: cancels all still-self-cancellable physical lines atomically; digital lines are never cancelled; if cancellation is no longer legally possible, no partial silent cancellation occurs |

---

# 12. Customer STL Purchases

Removed by ADR-019: there is no STL library, entitlement or download endpoint, because the platform stores no STL files. A customer sees each STL purchase and whether it has been sent as a line in `GET /api/v1/me/orders/{order_id}` (`fulfillment_status`: `awaiting_delivery` or `delivered`, with `delivered_at`). The file itself arrives by email from the administrator.

---

# 13. Customer Offer / Negotiation Endpoints

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `POST /api/v1/offers` | Verified Customer | `OfferCreate` | `201 OfferDetail` | 401, 403, 409 `PRODUCT_ALREADY_OWNED` / `OFFER_ALREADY_ACTIVE`, 422 `OFFER_BELOW_MINIMUM` / `OFFER_COOLDOWN_ACTIVE` / `PRODUCT_NOT_PURCHASABLE`, 429 | — | STL only; first round appended; admin notification/email |
| `GET /api/v1/me/offers` | Authenticated | query params | `200 OfferPage` | 401 | Cursor; optional `status`, `product_id`; default `-created_at` | Own offer history |
| `GET /api/v1/me/offers/{offer_id}` | Authenticated; owner | — | `200 OfferDetail` | 401, 404 | — | Includes append-only rounds and current deadline |
| `POST /api/v1/me/offers/{offer_id}/counter` | Verified Customer; owner; customer turn | `OfferCounterRequest` | `200 OfferDetail` | 401, 403, 404, 409 `OFFER_NOT_YOUR_TURN` / `INVALID_STATE_TRANSITION`, 410, 422, 429 | — | Adds round; switches turn; resets `responds_by`; notification/outbox |
| `POST /api/v1/me/offers/{offer_id}/accept` | Verified Customer; owner; customer turn | — | `200 OfferDetail` | 401, 403, 404, 409, 410, 429 | — | Freezes agreed price; creates checkout window; notification/outbox |
| `POST /api/v1/me/offers/{offer_id}/withdraw` | Verified Customer; owner | `OfferWithdrawRequest` | `200 OfferDetail` | 401, 403, 404, 409, 410 | — | Legal only in pending negotiation states; append history |
| `POST /api/v1/me/offers/{offer_id}/checkout` | Verified Customer; owner; accepted offer | `OfferCheckoutRequest` + `Idempotency-Key` | `201 CheckoutRead` | 401, 403, 404, 409 `IDEMPOTENCY_KEY_CONFLICT` / `PAYMENT_ALREADY_ACTIVE`, 410 `OFFER_CHECKOUT_EXPIRED`, 429, 502 | — | One-time agreed-price checkout; creates order/payment; price comes from immutable accepted offer |

---

# 14. Customer Reviews, Wishlist and Notifications

## 14.1 Reviews

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/me/reviews` | Authenticated | `cursor`, `limit` | `200 ReviewPage` | 401 | Cursor | Own reviews including moderation state |
| `POST /api/v1/reviews` | Verified Customer | `ReviewCreate` | `201 ReviewRead` | 401, 403, 409 `REVIEW_ALREADY_EXISTS`, 422, 429 | — | Purchase not required; server computes Verified Purchase; updates product rating aggregate |
| `PATCH /api/v1/reviews/{review_id}` | Verified Customer; owner | `ReviewUpdate` | `200 ReviewRead` | 401, 403, 404, 422, 429 | — | Revalidates content; recalculates rating aggregate |
| `DELETE /api/v1/reviews/{review_id}` | Verified Customer; owner | — | `204` | 401, 403, 404 | — | Soft delete; recalculates aggregates |

## 14.2 Wishlist

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/me/wishlist` | Authenticated | query params | `200 WishlistPage` | 401 | Cursor; default `-created_at` | Active wishlist items only |
| `PUT /api/v1/me/wishlist/{product_id}` | Verified Customer | — | `204` | 401, 403, 404, 429 | — | Idempotently adds/restores active wishlist row; updates product aggregate |
| `DELETE /api/v1/me/wishlist/{product_id}` | Verified Customer | — | `204` | 401, 403, 404 | — | Soft delete; updates aggregate |

## 14.3 Notifications

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/me/notifications` | Authenticated | query params | `200 NotificationPage` | 401 | Cursor; optional `read`; default `-created_at` | Own notifications |
| `PATCH /api/v1/me/notifications/{notification_id}` | Verified Customer; owner | `NotificationUpdate` | `200 NotificationRead` | 401, 403, 404, 422 | — | Sets read/unread state |

---

# 15. Admin Catalogue Endpoints

All routes in this section require **Admin + MFA**. All mutations are audit-logged.

## 15.1 Products

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/products` | query params | `200 AdminProductPage` | 401/404, 400 | Cursor; filters `type`, `category_id`, `is_visible`, `is_featured`, `is_available`, `deleted`, `q`; sorts `-created_at`, `price`, `-price` | Includes drafts/archived according to filters |
| `POST /api/v1/admin/products` | `AdminProductCreate` | `201 AdminProductDetail` | 401/404, 409 `SLUG_CONFLICT`, 422 | — | Creates common + type-specific fields; name is required |
| `GET /api/v1/admin/products/{product_id}` | — | `200 AdminProductDetail` | 401/404 | — | Includes images/type-specific metadata |
| `PATCH /api/v1/admin/products/{product_id}` | `AdminProductUpdate` | `200 AdminProductDetail` | 401/404, 409 `SLUG_CONFLICT` / `VERSION_CONFLICT` / `INVALID_STATE_TRANSITION`, 422 | — | Cannot violate physical/STL type integrity; server-controlled aggregates rejected; name/description/SEO/slug fields update in place; requires `version` (ADR-020) |
| `DELETE /api/v1/admin/products/{product_id}?version=N` | — | `204` | 401/404, 409 `VERSION_CONFLICT` / `INVALID_STATE_TRANSITION`, 422 | — | Soft delete; slug released in the same transaction; `version` query parameter required (ADR-020) |

## 15.2 Product Images

| Method + Path | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|
| `POST /api/v1/admin/products/{product_id}/images` | multipart `ProductImageUpload` | `201 ProductImageRead` | 401/404, 409 (product deleted), 422 `UPLOAD_REJECTED` / `MALWARE_DETECTED`, 503 `SERVICE_UNAVAILABLE` (scanner down; fail closed) | Size check, scan the raw upload, content inspect, re-encode, store, insert (ADR-021); never trust extension; first image becomes the cover; ≤ 10 MB, ≤ 20 live images |
| `PATCH /api/v1/admin/products/{product_id}/images/{image_id}` | `ProductImageUpdate` | `200 ProductImageRead` | 401/404, 409 (product deleted), 422 | Updates allowed image metadata |
| `PUT /api/v1/admin/products/{product_id}/images/{image_id}/cover` | — | `200 ProductImageRead` | 401/404, 409 (product deleted) | Atomically clears previous cover |
| `PUT /api/v1/admin/products/{product_id}/images/order` | `ProductImageOrderUpdate` | `200 ProductImageList` | 401/404, 409 (product deleted), 422 | Bulk reorder validated as exact owned image set |
| `DELETE /api/v1/admin/products/{product_id}/images/{image_id}` | — | `204` | 401/404, 409 `INVALID_STATE_TRANSITION` (the cover while others remain, or product deleted) | Soft-deletes image metadata; the file is kept (BR-033) and garbage-collected only when no row references it; cannot leave invalid cover state silently |

## 15.3 STL Asset Versions

Removed by ADR-019: STL files are never uploaded.

---

# 16. Admin Reference-Data Endpoints

All use Admin + MFA and audit logging.

## 16.1 Categories

| Method + Path | Request | Success | Errors | Pagination / Notes |
|---|---|---|---|---|
| `GET /api/v1/admin/categories` | query params | `200 AdminCategoryPage` | 401/404 | Cursor; include active/deleted |
| `POST /api/v1/admin/categories` | `CategoryCreate` | `201 CategoryDetail` | 401/404, 409 `SLUG_CONFLICT`, 422 | — |
| `GET /api/v1/admin/categories/{category_id}` | — | `200 CategoryDetail` | 401/404 | — |
| `PATCH /api/v1/admin/categories/{category_id}` | `CategoryUpdate` | `200 CategoryDetail` | 401/404, 409, 422 | Can update name/slug/active state |
| `DELETE /api/v1/admin/categories/{category_id}` | — | `204` | 401/404, 409 `CATEGORY_IN_USE` | Soft delete only after products reassigned |

## 16.2 Materials

| Method + Path | Request | Success | Errors | Pagination / Notes |
|---|---|---|---|---|
| `GET /api/v1/admin/materials` | query params | `200 AdminMaterialPage` | 401/404 | Cursor |
| `POST /api/v1/admin/materials` | `MaterialCreate` | `201 MaterialDetail` | 401/404, 422 | — |
| `GET /api/v1/admin/materials/{material_id}` | — | `200 MaterialDetail` | 401/404 | — |
| `PATCH /api/v1/admin/materials/{material_id}` | `MaterialUpdate` | `200 MaterialDetail` | 401/404, 422 | — |
| `DELETE /api/v1/admin/materials/{material_id}` | — | `204` | 401/404, 409 `CATEGORY_IN_USE` while a live product uses it | Soft/archive behavior; existing historical/product references preserved |

## 16.3 Colours

| Method + Path | Request | Success | Errors | Pagination / Notes |
|---|---|---|---|---|
| `GET /api/v1/admin/colours` | query params | `200 AdminColourPage` | 401/404 | Cursor |
| `POST /api/v1/admin/colours` | `ColourCreate` | `201 ColourDetail` | 401/404, 422 | — |
| `GET /api/v1/admin/colours/{colour_id}` | — | `200 ColourDetail` | 401/404 | — |
| `PATCH /api/v1/admin/colours/{colour_id}` | `ColourUpdate` | `200 ColourDetail` | 401/404, 422 | — |
| `DELETE /api/v1/admin/colours/{colour_id}` | — | `204` | 401/404, 409 `CATEGORY_IN_USE` while a live product uses it | Soft/archive |

## 16.4 Shipping Zones

| Method + Path | Request | Success | Errors | Pagination / Notes |
|---|---|---|---|---|
| `GET /api/v1/admin/shipping-zones` | query params | `200 AdminShippingZonePage` | 401/404 | Cursor; active/deleted |
| `POST /api/v1/admin/shipping-zones` | `ShippingZoneCreate` | `201 ShippingZoneRead` | 401/404, 409, 422 | V1 Lebanese flat-rate zone |
| `GET /api/v1/admin/shipping-zones/{zone_id}` | — | `200 ShippingZoneRead` | 401/404 | — |
| `PATCH /api/v1/admin/shipping-zones/{zone_id}` | `ShippingZoneUpdate` | `200 ShippingZoneRead` | 401/404, 422 | Old orders keep snapshots |
| `DELETE /api/v1/admin/shipping-zones/{zone_id}` | — | `204` | 401/404 | Soft delete/archive; new checkouts cannot choose it |

---

# 17. Admin User Endpoints

| Method + Path | Auth | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/admin/users` | Admin + MFA | query params | `200 AdminUserPage` | 401/404 | Cursor; filters verified/active; search email; `-created_at` | PII access audited/redacted from logs |
| `GET /api/v1/admin/users/{user_id}` | Admin + MFA | — | `200 AdminUserDetail` | 401/404 | — | Shows account status and admin-safe customer summary |
| `PATCH /api/v1/admin/users/{user_id}` | Admin + MFA | `AdminUserUpdate` | `200 AdminUserDetail` | 401/404, 409, 422 | — | V1 allows account activation/deactivation controls; no arbitrary password editing |

The admin entitlement-grant endpoint is removed by ADR-019. To give an STL away, the administrator simply emails it; the platform records nothing.

---

# 18. Admin Order / Fulfillment Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/orders` | query params | `200 AdminOrderPage` | 401/404, 400 | Cursor; filters `status`, `fulfillment_method`, customer, order number, dates; default `-placed_at` | Admin fulfillment queue |
| `GET /api/v1/admin/orders/{order_id}` | — | `200 AdminOrderDetail` | 401/404 | — | Customer/order data, lines, status history, payments/refunds, internal note |
| `PATCH /api/v1/admin/orders/{order_id}` | `AdminOrderUpdate` | `200 AdminOrderDetail` | 401/404, 422 | — | V1 restricted to mutable admin fields such as internal note; order status is not directly patchable |
| `GET /api/v1/admin/stl-deliveries` | query params | `200 StlDeliveryPage` | 401/404, 400 | Cursor; optional `product_id`, customer; default oldest first (`placed_at`) | STL delivery queue (ADR-019): every STL line in `awaiting_delivery`, with order number, product, customer and `customer_email_snapshot` to send to |
| `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition` | `OrderItemTransitionRequest` | `200 AdminOrderDetail` | 401/404, 409 `INVALID_STATE_TRANSITION`, 422 | — | Locks line; validates the delivery/pickup/STL state machine; recomputes order projection; history + audit + notifications. For an STL line, `awaiting_delivery → delivered` records `delivered_at` and `delivered_by` and notifies the customer that the file was emailed |
| `POST /api/v1/admin/orders/{order_id}/cancel` | `AdminOrderCancelRequest` | `200 AdminOrderDetail` | 401/404, 409 `INVALID_STATE_TRANSITION` | — | Cancels eligible lines according to state; creates refund obligation when required; digital rules preserved |

The line-transition endpoint is the only normal API path for fulfillment status changes.

---

# 19. Admin Refund Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/admin/orders/{order_id}/refunds` | `RefundCreate` + required `Idempotency-Key` | `201 RefundDetail` | 401/404, 409 `IDEMPOTENCY_KEY_CONFLICT`, 422 `REFUND_EXCEEDS_AVAILABLE`, 429, 502 | — | Supports selected line amounts + shipping; validates against refundable amount; a refunded STL line leaves the delivery queue; records obligation; audit/outbox |
| `GET /api/v1/admin/refunds` | query params | `200 RefundPage` | 401/404 | Cursor; `status`, order/customer/date; default oldest pending first when queueing | Pending-refund obligations queue |
| `GET /api/v1/admin/refunds/{refund_id}` | — | `200 RefundDetail` | 401/404 | — | Full settlement/audit view |
| `POST /api/v1/admin/refunds/{refund_id}/settle` | `RefundSettlementRequest` | `200 RefundDetail` | 401/404, 409 `INVALID_STATE_TRANSITION`, 422 | — | Used for manual-transfer settlement or provider-confirmed completion; append audit; notification/outbox |

Refund settlement is explicit because the SRS requires obligations to remain tracked until actually settled.

---

# 20. Admin Payment / Reconciliation Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/payments` | query params | `200 PaymentPage` | 401/404 | Cursor; filters status/provider/order/date; processing oldest first | Includes payments needing manual confirmation |
| `GET /api/v1/admin/payments/{payment_id}` | — | `200 PaymentDetail` | 401/404 | — | Provider references/verification history; sensitive provider secrets never returned |
| `POST /api/v1/admin/payments/{payment_id}/reconcile` | — | `200 PaymentDetail` | 401/404, 409, 502, 503 `PAYMENT_VERIFICATION_UNAVAILABLE` | — | Queries provider outside DB lock, then applies verified result transactionally |
| `POST /api/v1/admin/payments/{payment_id}/confirm` | `ManualPaymentConfirmRequest` | `200 PaymentDetail` | 401/404, 409, 422 | — | Only manual fallback when automatic provider status verification is unavailable; verified amount must equal order total; STL delivery queue/production/status/audit/outbox side effects |

A callback alone never authorizes these state changes.

---

# 21. Admin Offer Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/offers` | query params | `200 AdminOfferPage` | 401/404 | Cursor; `status`, `product_id`, customer, deadlines; pending deadline first | Pending offers queue |
| `GET /api/v1/admin/offers/{offer_id}` | — | `200 AdminOfferDetail` | 401/404 | — | Complete negotiation rounds |
| `POST /api/v1/admin/offers/{offer_id}/counter` | `OfferCounterRequest` | `200 AdminOfferDetail` | 401/404, 409 `OFFER_NOT_YOUR_TURN`, 410, 422 | — | Append round; switch turn; reset deadline; notification/outbox |
| `POST /api/v1/admin/offers/{offer_id}/accept` | — | `200 AdminOfferDetail` | 401/404, 409, 410 | — | Freeze current amount; start checkout window; notification/outbox |
| `POST /api/v1/admin/offers/{offer_id}/reject` | `OfferRejectRequest` | `200 AdminOfferDetail` | 401/404, 409, 410 | — | Append rejection; arm cooldown; notification/outbox |

---

# 22. Admin Review Moderation

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/reviews` | query params | `200 AdminReviewPage` | 401/404 | Cursor; filters hidden/rating/product/user/verified; `-created_at` | Moderation queue/view |
| `GET /api/v1/admin/reviews/{review_id}` | — | `200 AdminReviewDetail` | 401/404 | — | Includes moderation state |
| `POST /api/v1/admin/reviews/{review_id}/hide` | `ReviewModerationRequest` | `200 AdminReviewDetail` | 401/404, 409 | — | Hides review; recalculates product aggregates; audit |
| `POST /api/v1/admin/reviews/{review_id}/restore` | `ReviewModerationRequest` | `200 AdminReviewDetail` | 401/404, 409 | — | Restores review; recalculates aggregates; audit |

---

# 23. Admin Bring Your Idea Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/custom-requests` | query params | `200 CustomRequestPage` | 401/404 | Cursor; status/date/email; oldest actionable first | Lead pipeline |
| `GET /api/v1/admin/custom-requests/{request_id}` | — | `200 CustomRequestDetail` | 401/404 | — | Includes private attachment metadata and admin fields |
| `POST /api/v1/admin/custom-requests/{request_id}/transition` | `CustomRequestTransition` | `200 CustomRequestDetail` | 401/404, 409 `INVALID_STATE_TRANSITION`, 422 | — | Enforces state machine; quoted transition may record amount; lost/closed records outcome; audit |
| `PATCH /api/v1/admin/custom-requests/{request_id}` | `CustomRequestAdminUpdate` | `200 CustomRequestDetail` | 401/404, 422 | — | Updates non-state admin data such as notes; status changes forbidden here |
| `GET /api/v1/admin/custom-requests/{request_id}/attachments/{attachment_id}/download` | Admin + MFA | optional Range | Binary `200/206` | 401/404, 416 | — | Private internal redirect; attachment must not be expired/purged |

---

# 24. Admin Contact Message Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/contact-messages` | query params | `200 ContactMessagePage` | 401/404 | Cursor; status/date/email; default oldest new first | Admin queue |
| `GET /api/v1/admin/contact-messages/{message_id}` | — | `200 ContactMessageDetail` | 401/404 | — | Access audited |
| `PATCH /api/v1/admin/contact-messages/{message_id}` | `ContactMessageAdminUpdate` | `200 ContactMessageDetail` | 401/404, 422 | — | Allowed status values: new/read/replied/archived; actual human reply can happen outside system |

---

# 25. Admin Settings Endpoints

| Method + Path | Request | Success | Errors | Pagination | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/settings` | query params | `200 SettingPage` | 401/404 | Cursor/hard limit; optional key prefix/type | All typed settings |
| `GET /api/v1/admin/settings/{key}` | — | `200 SettingRead` | 401/404 | — | — |
| `PATCH /api/v1/admin/settings/{key}` | `SettingUpdate` | `200 SettingRead` | 401/404, 422 `SETTING_INVALID` | — | Type/range validated; audit trail; operational changes require no deploy |

Clients cannot create arbitrary setting keys in V1; keys are schema/configuration-defined.

---

# 26. Admin Audit Log Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/audit-logs` | query params | `200 AuditLogPage` | 401/404 | Cursor; actor/action/entity_type/entity_id/request_id/date; default `-created_at` | Read-only |
| `GET /api/v1/admin/audit-logs/{audit_id}` | — | `200 AuditLogRead` | 401/404 | — | Read-only; sensitive fields already redacted at write time |

No create/update/delete audit-log endpoint exists.

---

# 27. Admin Analytics Endpoints

All analytics are read-only, Admin + MFA, bounded by explicit date ranges/limits. Revenue is attributed **per order line**, not per order.

| Method + Path | Request / Query | Success | Errors | Notes |
|---|---|---|---|---|
| `GET /api/v1/admin/analytics/overview` | optional date range | `200 AnalyticsOverview` | 401/404, 400 | Pending offers count, high-level customer/order metrics |
| `GET /api/v1/admin/analytics/revenue` | `from`, `to`, optional `group_by` | `200 RevenueAnalytics` | 401/404, 400 | Physical vs STL revenue by line |
| `GET /api/v1/admin/analytics/recent-purchases` | cursor, limit | `200 RecentPurchasePage` | 401/404 | Bounded recent purchases |
| `GET /api/v1/admin/analytics/customers` | date range | `200 CustomerAnalytics` | 401/404, 400 | Customer statistics |
| `GET /api/v1/admin/analytics/wishlist` | date range/limit | `200 WishlistAnalytics` | 401/404, 400 | Wishlist totals + most-wishlisted |
| `GET /api/v1/admin/analytics/stl-sales` | date range/limit | `200 StlSalesAnalytics` | 401/404, 400 | Best-selling STLs from paid, unrefunded lines; count of lines awaiting delivery |
| `GET /api/v1/admin/analytics/top-rated-products` | limit | `200 TopRatedProductList` | 401/404 | Maintained rating aggregates |
| `GET /api/v1/admin/analytics/custom-requests/funnel` | date range | `200 CustomRequestFunnelAnalytics` | 401/404, 400 | New→contacted→quoted→won/lost funnel |

Exact analytics default ranges/export formats remain tunable design-time settings; the route shapes are stable.

---

# 28. Payment Webhook

| Method + Path | Auth / Authorization | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/webhooks/payments/whish` | Provider; IP allowlist + signature if supported | raw provider event | `200 WebhookReceipt` | 400, 401/403 signature/IP failure, 429 | Persist unique `(provider,event_id)` first and return quickly; duplicate event is safe; callback never marks order paid by itself; verification/reconciliation follows independently |

Whish signature mechanics and status-query capabilities remain provider-dependent external details. The endpoint contract does not trust them as proof.

---

# 29. Request Schema Catalogue

Only significant request fields are listed here. All schemas reject unknown fields unless explicitly documented.

## 29.1 Identity

### `RegisterRequest`

```text
email: Email
password: str
```

### `LoginRequest`

```text
email: Email
password: str
```

### `VerifyEmailRequest`

```text
token: str
```

### `ResendVerificationRequest`

```text
email: Email
```

### `PasswordResetRequest`

```text
email: Email
```

### `PasswordResetConfirm`

```text
token: str
new_password: str
```

### `AccountDeletionRequest`

```text
current_password: str
confirmation: literal confirmation value
```

Fresh authentication may also be enforced by session age.

---

## 29.2 MFA

### `MfaSetupRequest`

```text
current_password: str
```

### `MfaSetupConfirmRequest`

```text
code: str
```

### `MfaVerifyRequest`

```text
challenge_id: str
code?: str
recovery_code?: str
```

Exactly one second-factor credential is supplied.

---

## 29.3 Address

### `AddressCreate`

```text
label: str
recipient_name: str
phone: str
governorate: str
city: str
area?: str
street?: str
landmark_notes?: str
is_default?: bool
```

### `AddressUpdate`

Same fields optional; empty update rejected.

---

## 29.4 Cart

### `CartItemAdd`

```text
product_id: UUID
quantity: int = 1
```

Physical: 1..max cap.  
STL: server requires exactly 1.

### `CartItemQuantityUpdate`

```text
quantity: int
```

---

## 29.5 Checkout

### `CheckoutRequest`

```text
fulfillment_method?: "delivery" | "pickup"
address_id?: UUID
shipping_zone_id?: UUID
customer_note?: str
accept_terms: true
accept_digital_final_sale?: true
accepted_price_changes?: [
  {
    product_id: UUID,
    amount_cents: int,
    currency: "USD"
  }
]
```

Rules:

- digital-only → fulfillment/address/zone are null;
- physical delivery → fulfillment=`delivery`, address + zone required;
- physical pickup → fulfillment=`pickup`, no address/zone needed;
- mixed order follows physical fulfillment rules;
- `accept_digital_final_sale=true` is required when any digital line exists;
- client never submits subtotal/shipping/total.

### `OfferCheckoutRequest`

```text
accept_terms: true
accept_digital_final_sale: true
```

Price/product/customer derive from the accepted offer.

---

## 29.6 Orders

### `CustomerOrderCancelRequest`

```text
reason?: str
```

V1 customer cancellation targets the order's still-self-cancellable physical work only; digital lines never cancel.

### `AdminOrderUpdate`

```text
admin_note?: str
```

### `OrderItemTransitionRequest`

```text
target_status: order_item_status
reason?: str
```

The server validates legal transition and actor.

### `AdminOrderCancelRequest`

```text
reason: str
```

---

## 29.7 Offers

### `OfferCreate`

```text
product_id: UUID
amount_cents: int
currency: "USD"
message?: str
```

### `OfferCounterRequest`

```text
amount_cents: int
currency: "USD"
message?: str
```

### `OfferWithdrawRequest`

```text
reason?: str
```

### `OfferRejectRequest`

```text
reason?: str
```

---

## 29.8 Reviews / Notifications

### `ReviewCreate`

```text
product_id: UUID
rating: int  # 1..5
body?: str
```

### `ReviewUpdate`

```text
rating?: int
body?: str
```

### `NotificationUpdate`

```text
read: bool
```

### `ReviewModerationRequest`

```text
reason?: str
```

---

## 29.9 Public Forms

### `CustomRequestCreate` — multipart

```text
name
email
phone
project_title
description
preferred_material?
preferred_colour?
dimensions?
captcha_token
attachments[]  # bounded image count/size, private
```

### `ContactMessageCreate`

```text
name
email
phone?
subject?
message
captcha_token
```

---

## 29.10 Admin Product

### `AdminProductCreate`

```text
type: "physical" | "stl"
category_id: UUID
name: str
description?: str
slug: str
seo_title?: str
seo_description?: str
og_image_url?: str
price: {amount_cents, currency="USD"}
is_visible?: bool
is_featured?: bool
is_available?: bool

# physical only
purchase_mode?
material_id?
colour_id?
dimensions?
production_lead_time_days?
batch_size?
max_quantity_per_line?
weight_grams?
```

Name is required. Server regenerates the search vector from name/description on write. `dimensions` is `{length_mm, width_mm, height_mm}`, positive integers (VS-013, see `docs/products.md`).

### `AdminProductUpdate`

Requires `version: int` (the version last read, ADR-020). Same mutable fields are optional **except `type`**, which is refused. Product type is immutable after creation in V1; converting a physical product into an STL product (or vice versa) requires creating a new product rather than corrupting type-specific history.

---

## 29.11 Images

### `ProductImageUpload` — multipart

```text
file
alt_text?
```

### `ProductImageUpdate`

```text
alt_text: str | null   # required; null or blank clears; <= 300 chars
```

### `ProductImageOrderUpdate`

```text
image_ids: [UUID, ...]  # exact desired order
```

### `ProductImageRead`

```text
id
product_id
url            # MEDIA_PUBLIC_URL + "/" + storage_key
alt_text
sort_order
is_cover
created_at
updated_at
```

`ProductImageList` is `{items: [ProductImageRead]}`. See `docs/product-images.md` (VS-014).


---

## 29.12 Reference Data

`CategoryCreate`:

```text
name: str
slug: str
is_active?: bool
```

`MaterialCreate`, `ColourCreate`:

```text
name: str
is_active?: bool
```

### `ShippingZoneCreate`

```text
name: str
rate: {amount_cents, currency="USD"}
is_active?: bool
```

### `ShippingZoneUpdate`

Same fields optional.

---

## 29.13 Refund

### `RefundCreate`

```text
items: [
  {
    order_item_id: UUID,
    amount_cents: int
  }
]
shipping_refund_cents?: int
reason: str
method?: "provider" | "manual"
```

Rules:

- server derives currency;
- every amount is validated against remaining refundable value;
- overall refund total is derived server-side;
- a refunded STL line becomes `refunded` and leaves the delivery queue;
- provider capability may force manual method.

### `RefundSettlementRequest`

```text
reference?: str
note?: str
```

Used only when manual/provider workflow reaches confirmed settlement.

---

## 29.14 Payment Manual Confirmation

### `ManualPaymentConfirmRequest`

```text
provider_reference: str
verified_amount_cents: int
evidence_note: str
```

Server requires exact order-total match and records the admin actor/audit trail.

---

## 29.15 Custom Request Admin

### `CustomRequestTransition`

```text
target_status: custom_request_status
quoted_amount_cents?: int
outcome?: "won" | "lost"
note?: str
```

Fields are allowed only when meaningful for the transition.

### `CustomRequestAdminUpdate`

```text
admin_notes?: str
```

---

## 29.16 Settings

### `SettingUpdate`

```text
value: JSON value
```

Server validates against the existing key's declared setting type/range.

---

# 30. Core Response Schema Catalogue

## `ProductListItem`

Includes at least:

```text
id
type
localized name
slug
cover image
price {amount_cents,currency}
category summary
physical facet summaries when applicable
is_available
purchase_mode when physical
average_rating
review_count
is_featured
```

## `ProductDetail`

Extends list item with:

```text
localized description
other-language/fallback metadata as needed
all public images
SEO fields
physical specifications / lead-time / batch information
for STL: a description of what the customer receives and that it is emailed after payment (ADR-019)
review aggregates
derived capabilities:
  can_add_to_cart
  can_offer
  whatsapp_available
```

## `CartRead`

```text
id
items[]
each item:
  product summary
  quantity
  snapshot_price
  current_price
  price_changed
derived:
  contains_physical
  contains_digital
```

No client-authoritative total is trusted for checkout.

## `CheckoutRead`

```text
order: OrderDetail or OrderSummary
payment:
  id
  status
  provider
  redirect_url?
```

## `OrderDetail`

Includes:

```text
id
order_number
source
derived status
fulfillment_method
monetary breakdown
address/shipping snapshots where applicable
estimated_dispatch_at
placed/completed/cancelled timestamps
lines[]
customer-visible notes
payment summary
refund summary
customer-visible status history
```

`admin_note` is never returned by customer endpoints.

## `OfferDetail`

```text
id
product summary
status
turn
current/agreed amount
responds_by
checkout_expires_at
rounds[]
allowed_actions[]
```

## `StlDeliveryItem` (admin queue row)

```text
order_id
order_number
order_item_id
product summary
customer summary
customer_email_snapshot
paid_at
```

Order lines in `OrderDetail` carry `fulfillment_status` and, for STL lines, `delivered_at`.

## `PublicSettingsRead`

Strict allowlist, e.g.:

```text
accepting_orders
free_shipping_threshold
pickup_address
pickup_hours
whatsapp_number
```

Internal security/payment settings are never returned.

---

# 31. Filter and Sort Allowlist

## Public Products

Filters:

```text
type
category_id
material_id
colour_id
featured
price_min_cents
price_max_cents
min_rating
q
```

Sorts:

```text
price
-price
-average_rating
-created_at
```

## Customer Orders

Filters:

```text
status
placed_after
placed_before
```

Sort:

```text
-placed_at
```

## Admin Orders

Filters:

```text
status
fulfillment_method
customer
order_number
placed_after
placed_before
```

Sorts:

```text
-placed_at
placed_at
```

## Offers

Filters:

```text
status
product_id
responds_before
```

## Reviews

Filters:

```text
rating
verified_purchase
hidden  # admin only
product_id  # admin/own views
user_id     # admin only
```

## Audit Logs

Filters:

```text
actor_user_id
action
entity_type
entity_id
request_id
created_after
created_before
```

Unknown filter/sort fields produce `400 VALIDATION_ERROR`; they are never interpolated directly into SQL.

---

# 32. Side-Effect Catalogue

| Operation | Transactional side effects |
|---|---|
| Registration | verification token + email outbox + audit |
| Password reset confirm | password change + revoke sessions + audit |
| Checkout | order + immutable line snapshots + payment + consent + cart clear + idempotency record |
| Payment verification | payment state + STL lines to `awaiting_delivery` + physical line transitions + close live offer + order projection + history + audit + outbox/notifications |
| Customer/admin cancellation | line transitions + order projection + possible refund obligation + history + audit + outbox |
| Refund | refund obligation + refund items + STL line refunded (leaves delivery queue) + order projection + audit + outbox |
| Offer create/counter/accept/reject/withdraw | append offer round + state/deadline + audit + outbox/notification |
| Review create/update/delete/moderate | review mutation + rating/review-count aggregate |
| Wishlist add/remove | active wishlist state + wishlist-count aggregate |
| Setting change | typed setting mutation + audit |
| Fulfillment transition | line state + derived order status + history + audit + appropriate email/notification (STL `delivered`: "file sent" email + notification) |

No external email send occurs before the database transaction commits.

---

# 33. Endpoints That Must **Not** Be Invented for V1

These SRS features do not require separate backend CRUD APIs:

| Feature | V1 Handling |
|---|---|
| Home hero / why-choose-us / footer | Frontend/static composition using public catalogue/settings data |
| About Us content/gallery | Frontend/static content unless a future CMS requirement is added |
| Floating WhatsApp button | Frontend uses allowlisted public WhatsApp setting |
| WhatsApp product contact | Frontend constructs link with product context; no order is created |
| Canonical markup | Frontend/server-rendering layer using product slugs |
| Product comments | Explicitly out of V1 |
| Product variants | Explicitly out of V1 |
| Courier tracking API | Explicitly out of V1 |
| Cash on delivery | Explicitly out of V1 |
| Guest checkout | Explicitly out of V1 |
| Tax/VAT engine | Explicitly out of V1 |
| STL licensing | Explicitly out of V1 |

## SEO Sitemap Note

The SRS requires per-language XML sitemaps but does not assign ownership to the backend API. This should be generated by the web/rendering layer from the product/category contract. Do **not** add mutable “sitemap CRUD” endpoints.

---

# 34. Internal Jobs — No Public Endpoint

These are scheduler/worker operations, not HTTP APIs:

```text
dispatch_outbox
expire_offers
release_stale_checkouts
reconcile_payments
purge_unverified_accounts
purge_expired_attachments
reap_orphan_files
backup_verify
ensure_partitions
rotate_ip_salt
```

Admin manual reconcile/confirm endpoints exist for operational intervention, but the scheduled jobs themselves are not exposed as public “run job” routes.

---

# 35. Feature-to-Endpoint Traceability

This section verifies that every V1 feature in the SRS has an API or an intentional non-API implementation path.

## 35.1 Public Storefront

| Feature | Endpoint / Implementation |
|---|---|
| F-001 Home | frontend composition + `GET /products`, `/categories`, `/settings/public`; no invented CMS |
| F-002 WhatsApp button | `GET /settings/public` + frontend |
| F-003 About Us | static/frontend; no CMS requirement |
| F-004 Physical catalogue | `GET /products?type=physical` |
| F-005 STL catalogue | `GET /products?type=stl` |
| F-006 Product detail | `GET /products/{slug}` + public reviews |
| F-007 Full-text search | `GET /products?q=...` |
| F-008 Faceted filters | `GET /products` filter allowlist |
| F-009 Sorting | `GET /products?sort=...` |
| F-010 Autocomplete | `GET /search/suggestions` |
| F-011 WhatsApp product contact | product detail + public WhatsApp setting + frontend link |
| F-013 SEO | product/category slugs + rendering/sitemap layer |

## 35.2 Customer Account

| Feature | Endpoint |
|---|---|
| F-020 Registration/verification | `/auth/register`, `/auth/verify-email` |
| F-021 Login/logout/refresh | `/auth/login`, `/auth/logout`, `/auth/refresh` |
| F-022 Password reset | reset request + confirm |
| F-023 Resend verification | `/auth/resend-verification` |
| F-024 View account profile | `GET /me` |
| F-025 Address book | `/me/addresses*` |
| F-026 Order history/detail | `/me/orders*` |
| F-027 Purchased STLs with delivery status | `/me/orders*` line status |
| F-028 Removed (ADR-019) | — |
| F-029 Offer history | `/me/offers*` |
| F-030 Wishlist | `/me/wishlist*` |
| F-031 Review management | `/me/reviews`, `/reviews/{id}` |
| F-032 Notification centre | `/me/notifications*` |
| F-033 Self-cancel | `POST /me/orders/{id}/cancel` |
| F-034 Data export | `GET /me/export` |
| F-035 Anonymisation | `DELETE /me` |

## 35.3 Commerce

| Feature | Endpoint |
|---|---|
| F-040 Mixed cart | `/cart*` |
| F-041 Quantity caps | cart add/update + checkout revalidation |
| F-042 Price change confirmation | `GET /cart` + `POST /checkout` conflict/retry contract |
| F-043 Shipping zone/rate | `GET /shipping-zones` + checkout |
| F-044 Pickup | `CheckoutRequest.fulfillment_method=pickup` |
| F-045 Free shipping | server-side checkout using setting |
| F-046 Idempotent checkout | `POST /checkout` + `Idempotency-Key` |
| F-047 Whish redirect/return | checkout returns redirect; order detail used after return |
| F-048 Webhook | `POST /webhooks/payments/whish` |
| F-049 Server verification | internal provider adapter + admin reconcile route |
| F-050 Reconciliation | scheduled job + `POST /admin/payments/{id}/reconcile` |
| F-051 Manual confirmation | `POST /admin/payments/{id}/confirm` |
| F-052 Terms consent | checkout request + immutable order timestamps |

## 35.4 Fulfillment

| Feature | Endpoint |
|---|---|
| F-060 Order queue | `GET /admin/orders` |
| F-061 Line transitions | `POST /admin/orders/{order}/items/{item}/transition` |
| F-062 Internal note | `PATCH /admin/orders/{id}` |
| F-063 Delivery workflow | line transition endpoint |
| F-064 Pickup workflow | line transition endpoint |
| F-065 Return handling | line transition + refund endpoint |
| F-066 Admin cancel | `POST /admin/orders/{id}/cancel` / line transition |
| F-067 Dispatch estimate | derived during checkout/order response |
| F-068 Kill switch | admin setting + checkout 503 |

## 35.5 Refunds

| Feature | Endpoint |
|---|---|
| F-070 Per-line refund | `POST /admin/orders/{id}/refunds` |
| F-071 Shipping refund | same refund request |
| F-072 Obligation tracking | `/admin/refunds*` |
| F-073 STL line leaves delivery queue on refund | refund transaction side effect |
| F-074 Pending queue | `GET /admin/refunds?status=pending` |

## 35.6 Digital Marketplace

| Feature | Endpoint / Mechanism |
|---|---|
| F-080–F-082, F-084–F-088 | Removed (ADR-019) |
| F-083 STL lines to `awaiting_delivery` | payment verification transaction |
| F-089 STL delivery queue / mark delivered | `GET /admin/stl-deliveries`; line transition to `delivered` |

## 35.7 Offers

| Feature | Endpoint |
|---|---|
| F-090 Submit/floor | `POST /offers` |
| F-091 Admin accept/reject/counter | `/admin/offers/{id}/*` |
| F-092 Customer accept/counter/withdraw | `/me/offers/{id}/*` |
| F-093 Inactivity expiry | scheduler + offer deadline fields |
| F-094 One-time checkout | `POST /me/offers/{id}/checkout` |
| F-095 Checkout expiry | offer checkout returns 410 after expiry |
| F-096 Rejection cooldown | offer create/reject contract |
| F-097 Negotiation history | offer detail rounds |
| F-098 Auto-close after acquisition | payment verification transaction side effect |

## 35.8 Engagement

| Feature | Endpoint |
|---|---|
| F-100 Reviews/badge | public reviews + customer review endpoints |
| F-101 Moderation | admin hide/restore |
| F-102 Rating aggregates | review side effects + product response |
| F-103 Wishlist | wishlist endpoints |
| F-104 Wishlist analytics | admin analytics/wishlist |
| F-105 Notifications | `/me/notifications*` |
| F-106 BYI submission | `POST /custom-requests` |
| F-107 BYI admin pipeline | admin custom-request endpoints |
| F-108 Contact | public contact + admin queue |

## 35.9 Administration

| Feature | Endpoint |
|---|---|
| F-110 Product CRUD | admin product endpoints |
| F-111 Images | admin image endpoints |
| F-112 Category/material/colour | admin reference-data endpoints |
| F-113 Shipping zones | admin shipping-zone endpoints |
| F-114 Settings editor | admin settings |
| F-116 User management | admin users |
| F-117 Audit viewer | admin audit logs |
| F-118 Admin MFA | auth MFA endpoints |

## 35.10 Analytics

| Feature | Endpoint |
|---|---|
| F-120 Revenue by stream | `/admin/analytics/revenue` |
| F-121 Recent purchases | `/admin/analytics/recent-purchases` |
| F-122 Pending offers count | `/admin/analytics/overview` |
| F-123 Wishlist stats | `/admin/analytics/wishlist` |
| F-124 Best-selling STL | `/admin/analytics/stl-sales` |
| F-125 Top rated | `/admin/analytics/top-rated-products` |
| F-126 Customer stats | `/admin/analytics/customers` |
| F-127 Removed (ADR-019) | — |
| F-128 BYI funnel | `/admin/analytics/custom-requests/funnel` |

## 35.11 Platform Services

| Feature | Endpoint / Mechanism |
|---|---|
| F-130 Email outbox | internal DB + worker; no public CRUD |
| F-132 Captcha | public form validation; no backend captcha-management endpoint |
| F-133 Rate limiting | middleware/nginx/Redis; response headers |
| F-134 Correlation logging | middleware |
| F-135 Audit logging | side effect + admin read-only viewer |
| F-136 Scheduled jobs | scheduler/worker; no public “run job” endpoint |
| F-137 Health/readiness | `/health/live`, `/health/ready` |
| F-138 Backup verification | internal ops job; no public endpoint |

**Traceability result:** every V1 feature has an explicit endpoint or an intentional non-API implementation owner.

---

# 36. Security Review by Route Class

## Public Reads

- rate-limit expensive search/autocomplete;
- parameterized FTS/trigram queries;
- no deleted/invisible product leakage.

## Public Forms

- captcha;
- rate limits by IP/email;
- upload type inspection;
- image re-encoding;
- malware scanning;
- private storage.

## Customer Writes

- authenticated cookie;
- verified email;
- CSRF;
- ownership;
- object IDs never substitute for authorization.

## STL Delivery

- no STL file is stored or served (ADR-019);
- only an administrator marks an STL line delivered, from `awaiting_delivery` only;
- marking delivered and refunding lock the same line.

## Admin

- separate router;
- MFA;
- non-admin existence hiding;
- audit every mutation;
- least PII in logs.

## Payment Webhook

- IP allowlist when possible;
- signature verification when provider supports it;
- unique provider event ID;
- immediate persistence;
- independent server-side verification before anything is delivered or produced.

---

# 37. Open External Details That Do Not Change Route Structure

The approved SRS still waits on Whish/client/operations details. These do not block the endpoint structure:

- Whish signature mechanism;
- Whish status-query capability;
- provider refund API vs manual transfer;
- sandbox availability;
- exact transaction settlement/fees;
- actual courier partner/rates;
- pickup identity policy;
- terms/privacy/refund wording;
- exact session/token lifetimes;
- BYI attachment retention period;
- analytics default date ranges/export formats.

When these values become known, update provider adapters, settings, validation, and possibly request/response detail—not the fundamental endpoint grouping.

---

# 38. Step 13 Completion Checklist

## Contract

- [x] Base path/versioning fixed.
- [x] Public/customer/admin/webhook route boundaries fixed.
- [x] Authentication levels fixed.
- [x] CSRF behavior documented.
- [x] Money/date/enum representation fixed.
- [x] RFC 9457 error shape fixed.
- [x] Stable SRS error codes preserved.
- [x] Additional required frontend-handling errors named.
- [x] Cursor pagination fixed.
- [x] Filter/sort allowlists documented.
- [x] Idempotency requirements documented.

## Features

- [x] Public catalogue/search/filter/sort.
- [x] Authentication/verification/reset.
- [x] Admin MFA.
- [x] Profile/addresses/data rights.
- [x] Mixed cart.
- [x] Price-change confirmation.
- [x] Shipping/pickup.
- [x] Normal checkout.
- [x] Order history/detail/cancellation.
- [x] Whish webhook/verification/reconciliation/manual fallback.
- [x] Full/partial refund + shipping refund + obligations.
- [x] STL delivery queue and delivery status (ADR-019).
- [x] Offer negotiation + checkout.
- [x] Reviews + moderation + verified badge.
- [x] Wishlist.
- [x] Notifications.
- [x] Bring Your Idea + private attachments + admin pipeline.
- [x] Contact queue.
- [x] Product/image admin.
- [x] Category/material/colour admin.
- [x] Shipping-zone admin.
- [x] User management.
- [x] Settings.
- [x] Audit viewer.
- [x] Analytics.
- [x] Health/readiness.
- [x] Platform-only jobs explicitly kept out of public API.
- [x] Every SRS feature traced to an endpoint or intentional non-API implementation.

## Security

- [x] Object ownership represented.
- [x] Admin 404 hiding rule represented.
- [x] Verified-email write boundary represented.
- [x] Rate-limit-sensitive endpoints identified.
- [x] Captcha guest forms represented.
- [x] Upload security represented.
- [x] No STL file endpoint exists (ADR-019).
- [x] Payment callback never trusted.
- [x] Server price authority preserved.

**Step 13 endpoint structure: COMPLETE for V1.**

The next implementation artifact should be the actual OpenAPI/Pydantic schema specification generated from this contract—not route code yet.
