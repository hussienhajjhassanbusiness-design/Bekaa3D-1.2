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
5. The client never supplies trusted prices, totals, cash amounts due, verified-purchase flags, STL ownership or delivery state, order status projections, or payment-confirmed state.
6. Every authenticated resource fetch by ID performs object-level authorization.
7. A caller who is authenticated but not allowed to know that a resource exists receives `404 NOT_FOUND`, not an existence-revealing `403`.
8. Every write by a normal account requires a verified email, except identity flows and explicitly public guest forms.
9. Every unsafe cookie-authenticated request uses CSRF protection.
10. Every collection endpoint is bounded either by cursor pagination or an explicit hard limit.
11. All externally visible errors use stable machine-readable codes.
12. State-machine mutations use explicit action/transition endpoints rather than unrestricted status-field PATCHes.
13. Side effects such as email delivery are committed via the transactional outbox and executed after commit.
14. Payment-provider callbacks are notifications only; they never directly prove payment. A cash payment is created only by the administrator's cash handover (ADR-024).
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
| Idempotency | `Idempotency-Key` required on normal checkout, offer checkout, refund creation and reissue, chargeback recording and record-capture (VS-030) |
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
| 400 | `CAPTCHA_INVALID` | Captcha token empty, invalid, expired or already used; a missing field is `422 VALIDATION_ERROR`. A Turnstile outage is `503 SERVICE_UNAVAILABLE` with `Retry-After` (fail closed, ADR-026) |
| 401 | `INVALID_CREDENTIALS` | Login failed; response remains enumeration-safe |
| 401 | `MFA_REQUIRED` | Admin login requires second factor |
| 401 | `MFA_INVALID` | MFA code/recovery code invalid |
| 401 | `WEBHOOK_SIGNATURE_INVALID` | Payment webhook signature did not verify; nothing stored, counted per IP (VS-023, ADR-032) |
| 403 | `ACCOUNT_DISABLED` | Account cannot authenticate/write |
| 403 | `CSRF_INVALID` | CSRF token missing/mismatch |
| 409 | `ACCOUNT_DELETION_BLOCKED` | Open order or unsettled refund prevents anonymisation |
| 409 | `CART_EMPTY` | Checkout attempted with no valid lines |
| 409 | `CART_PRICE_CHANGED` | Current product price differs from unconfirmed cart snapshot |
| 409 | `INVALID_STATE_TRANSITION` | Requested state-machine transition is illegal |
| 409 | `ORDER_NOT_CANCELLABLE` | Customer/admin cancellation cannot legally occur |
| 409 | `PAYMENT_ALREADY_ACTIVE` | Live payment already exists (VS-024 retry; cannot occur on a fresh checkout); body carries `payment_id`, `payment_status` and `redirect_url` (null while `processing`) |
| 409 | `PAYMENT_REFERENCE_MISMATCH` | Manual confirm: the typed provider reference differs from the stored one, or belongs to another payment (VS-024) |
| 409 | `MANUAL_CONFIRMATION_NOT_ALLOWED` | Manual confirm on a provider that has a status API; reconcile it instead (VS-024, ADR-036) |
| 409 | `ORDER_NOT_PAID` | Refund or chargeback on an order (or attempt) whose money was never taken, an unpaid cash order included (VS-030) |
| 409 | `ORDER_TOTAL_MISMATCH` | The order's total differs from its lines, or an online payment from the total, or the payment's currency from the order's; nothing written, an error log and a `refund_integrity` alert (VS-030 Q-2) |
| 409 | `CHARGEBACK_DUPLICATE` | This provider dispute reference is already recorded (VS-030) |
| 409 | `IDEMPOTENCY_REQUEST_IN_PROGRESS` | Same `Idempotency-Key` and body while the first request is still running, or crashed between placing the order and starting the payment; body carries `order_id`, `order_number`; `Retry-After: 2` (VS-023, ADR-032) |
| 409 | `CATEGORY_IN_USE` | Category, material or colour cannot be archived while a live product uses it (VS-013) |
| 409 | `SLUG_CONFLICT` | Live slug already exists |
| 409 | `VERSION_CONFLICT` | The `version` sent is not the stored one; nothing was written. Body carries `current_version` (ADR-020) |
| 409 | `REVIEW_ALREADY_EXISTS` | Active user/product review already exists |
| 409 | `OFFER_NOT_YOUR_TURN` | Offer action attempted by wrong actor |
| 409 | `OFFER_AMOUNT_CHANGED` | Accept named an `expected_amount_cents` that is not the offer's `current_amount`; nothing was written. Body carries `current_amount` (ADR-035 d9) |
| 410 | `OFFER_EXPIRED` | Offer inactivity lifetime elapsed |
| 410 | `RESOURCE_EXPIRED` | Single-use/time-limited resource expired |
| 416 | `RANGE_NOT_SATISFIABLE` | Invalid byte range on an admin attachment download |
| 422 | `REFUND_EXCEEDS_AVAILABLE` | Requested refund exceeds refundable amount |
| 422 | `REFUND_REQUIRES_CANCELLATION` | The refund would empty an unfinished physical line; cancel the line instead (ADR-024) |
| 422 | `CHARGEBACK_NOT_ONLINE` | A cash payment cannot be charged back (VS-030) |
| 422 | `CHARGEBACK_ITEMS_FORBIDDEN` | A late-captured attempt paid no line, so its chargeback names none (VS-030) |
| 422 | `CHARGEBACK_ALLOCATION_INVALID` | An item exceeds its line's balance, or the items exceed the payment's balance or the charge left after the absorbed refunds; body carries `available` (VS-030) |
| 422 | `INVALID_FULFILLMENT` | Address, contact phone or method does not match cart contents |
| 422 | `PAYMENT_METHOD_NOT_ALLOWED` | Cash chosen for an order with an STL line or a zero total, or while cash is switched off; or an unconfigured online provider chosen (ADR-024) |
| 422 | `CASH_PAYMENT_LIMIT_REACHED` | The recomputed total exceeds the cash maximum (`reason: order_total`, ADR-024) |
| 422 | `CASH_NOT_AVAILABLE` | The customer or the contact phone is blocked from cash, or already has the maximum open unpaid cash orders; one body for every case, with no `reason` (ADR-038) |
| 422 | `CASH_AMOUNT_MISMATCH` | Cash entered at handover differs from the amount due (ADR-024) |
| 422 | `UPLOAD_REJECTED` | Type/size/count/content validation failed |
| 422 | `ADDRESS_LIMIT_REACHED` | The customer already has the maximum of 20 live saved addresses (VS-026, ADR-027) |
| 422 | `CART_LINE_LIMIT_REACHED` | A new product would exceed the cart's 50 lines; body carries `limit` (VS-022, ADR-029) |
| 422 | `MALWARE_DETECTED` | Uploaded content failed malware scan |
| 422 | `SETTING_INVALID` | Setting value does not match its declared type/range |
| 502 | `PAYMENT_PROVIDER_ERROR` | Provider call failed (reserved; checkout uses `PAYMENT_PROVIDER_UNAVAILABLE`) |
| 502 | `PAYMENT_PROVIDER_UNAVAILABLE` | The order was placed but its online payment could not be started (provider down or timed out after the order committed); body carries `order_id`, `order_number`; replayed for the same key (VS-023, ADR-032) |
| 503 | `ONLINE_PAYMENT_UNAVAILABLE` | No online payment provider is configured (`PAYMENT_PROVIDER=none`); nothing written (VS-023) |
| 503 | `PAYMENT_VERIFICATION_UNAVAILABLE` | Automated verification unavailable and manual verification is required |
| 422 | `PAYMENT_AMOUNT_MISMATCH` | Manual confirm: the typed amount or currency differs from the attempt's; body carries `expected_amount_cents`, `currency`; nothing is written and nothing becomes a late capture (VS-024, ADR-036) |
| 405 | `METHOD_NOT_ALLOWED` | Route exists but not for this method; response carries `Allow`. Under `/api/v1/admin` only an MFA-complete administrator ever sees it (VS-011); everyone else gets 401/404 per SEC-10 |
| 500 | `INTERNAL_ERROR` | Unexpected server fault; details are logged, never returned |
| 503 | `SERVICE_UNAVAILABLE` | A required dependency (database, Redis, the captcha provider) is unreachable or timed out; retrying later is safe. A captcha outage carries `Retry-After` (ADR-026) |

## 5.3 Payment Webhook Processing Errors (stored, never returned)

A webhook that passes its signature is always answered `200 {received: true}`. When its event cannot be applied it is stored already processed, with one of these values in `webhook_events.processing_error`, and logged as an error (`payment_webhook_ignored`). A provider that does not answer verification leaves the event unprocessed with the provider's error text, and the `verify_payments` job retries it.

| `processing_error` | Meaning |
|---|---|
| `unknown_payment` | Neither the provider's reference nor our `payment_reference` names a payment |
| `reference_mismatch` | Our `payment_reference` names a payment whose stored provider reference differs from the event's |
| `provider_mismatch` | Our `payment_reference` names a payment of another provider |

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
| `GET /api/v1/products` | Public | query params | `200 ProductPage` | 422, 429 | Cursor; filters: `type`, `category_id`, `material_id`, `colour_id`, `price_min_cents`, `price_max_cents`, `min_rating`, `featured`, `q`; sorts: `price`, `-price`, `-average_rating`, `-created_at`, and `-relevance` with `q` (its default; ADR-023) | Only non-deleted, visible products in active categories; unavailable products remain visible |
| `GET /api/v1/products/{slug}` | Public | — | `200 ProductDetail` | 404, 429 | — | Response includes relevant commerce capabilities (ADR-022) and SEO fields |
| `GET /api/v1/products/{slug}/reviews` | Public | query params | `200 ReviewPage` | 404, 429 | Cursor; optional `rating`, `verified_purchase`; sort `-created_at` default | Hidden/deleted reviews excluded |
| `GET /api/v1/search/suggestions` | Public | `q`, `limit` | `200 SearchSuggestionList` | 422, 429 | Hard limit; V1 max 10 | Trigram typo tolerance (VS-016, see `docs/storefront-catalogue.md`) |
| `GET /api/v1/categories` | Public | — | `200 CategoryList` | 429 | Hard-limited reference list | Active categories only |
| `GET /api/v1/materials` | Public | — | `200 MaterialList` | 429 | Hard-limited reference list | Active material values |
| `GET /api/v1/colours` | Public | — | `200 ColourList` | 429 | Hard-limited reference list | Active colour values |
| `GET /api/v1/settings/public` | Public | — | `200 PublicSettingsRead` | 429 | — | Strict allowlist only; e.g. WhatsApp number, pickup address/hours, accepting-orders state, cash payment switch and maximum cash total |

### Public Product List Rules

- facets combine with logical AND;
- `q` searches product name/description in English (plain columns per ADR-016; VS-016 corrected "translated");
- `material_id` and `colour_id` apply only where meaningful;
- server may reject nonsensical sort/filter combinations with `422 VALIDATION_ERROR` (the §5.2 status; VS-015, see `docs/storefront-catalogue.md`);
- `limit` is bounded by the global maximum.

---

## 7.2 Guest Lead / Contact Forms

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `POST /api/v1/custom-requests` | Public; no auth cookies or CSRF; Turnstile captcha (ADR-025) + rate limit | `multipart/form-data CustomRequestCreate` | `201 CustomRequestReceipt` (`id`, `created_at`) | 400 `CAPTCHA_INVALID`, 422 `VALIDATION_ERROR` / `UPLOAD_REJECTED` / `MALWARE_DETECTED`, 429, 503 | — | Order (ADR-030): 20/hour attempts per IP and a `Content-Length` cap before parsing, fields, count and sizes, captcha, then 5/hour per IP and per email, then scan, re-encode, private store and insert. 0-5 images, 10 MB each. Notifies every active administrator in-app. No transaction or payment (VS-034, `docs/custom-requests.md`) |
| `POST /api/v1/contact-messages` | Public; no auth cookies or CSRF; Turnstile captcha (ADR-025) + rate limit | `ContactMessageCreate` | `201 ContactMessageReceipt` | 400 `CAPTCHA_INVALID`, 422, 429, 503 | — | Order (ADR-026): 60/hour attempts per IP, body, captcha, then 5/hour per IP and 5/hour per email, then insert as `new`. Repeated submissions are separate messages. The body and sender are never logged (VS-033) |

---

# 8. Authentication and MFA Endpoints

## 8.1 Core Authentication

| Method + Path | Auth / Authorization | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/auth/register` | Public; Turnstile captcha from VS-033 (ADR-025) | `RegisterRequest` | `202 RegistrationAccepted` | 400, 422, 429 | **Enumeration-safe:** same response whether address is new or already registered; if eligible, creates unverified account and enqueues verification email |
| `POST /api/v1/auth/login` | Public | `LoginRequest` | Customer: `200 SessionRead`; Admin needing MFA: `202 MfaChallengeRead` | 400, 401, 403, 429 | Progressive delay/lockout; successful customer login sets auth + CSRF cookies |
| `POST /api/v1/auth/logout` | Authenticated | — | `204` | 401, 403 CSRF | Revokes current session; clears cookies |
| `POST /api/v1/auth/refresh` | Authenticated refresh cookie | — | `204` | 401, 403 CSRF, 429 | Rotates refresh token/hash/version and CSRF cookie; detects token reuse |
| `POST /api/v1/auth/verify-email` | Public | `VerifyEmailRequest` | `204` | 400 `INVALID_TOKEN`, 410 `RESOURCE_EXPIRED`, 429 | Single-use token; audits account event. An expired token answers 410 until VS-046 purges it (7 d past expiry by default), then 400 |
| `POST /api/v1/auth/resend-verification` | Public or authenticated; Turnstile captcha from VS-033 (ADR-025) | `ResendVerificationRequest` | `202` | 429 | Uniform response regardless of account existence/state; outbox email if eligible |
| `POST /api/v1/auth/password-reset/request` | Public; Turnstile captcha from VS-033 (ADR-025) | `PasswordResetRequest` | `202` | 429 | Uniform response; enqueue reset email only when appropriate |
| `POST /api/v1/auth/password-reset/confirm` | Public | `PasswordResetConfirm` | `204` | 400, 410, 429 | Replaces password hash; revokes all sessions; audits security event. 410 becomes 400 once VS-046 purges the token |

## 8.2 Admin MFA

**V1 API design assumption:** TOTP is used for the administrator because the SRS requires admin MFA but does not name a mechanism.

Persistence is defined in Step 12 by `mfa_credentials` and one-time hashed `mfa_recovery_codes`.

| Method + Path | Auth / Authorization | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/auth/mfa/setup` | Authenticated admin enrollment session | `MfaSetupRequest` | `200 MfaSetupRead` | 401, 404, 429 | Returns TOTP setup material once; secret remains protected |
| `POST /api/v1/auth/mfa/setup/confirm` | Authenticated admin enrollment session | `MfaSetupConfirmRequest` | `200 MfaRecoveryCodesRead` | 401, 422, 429 | Enables MFA only after valid code; returns one-time recovery codes |
| `POST /api/v1/auth/mfa/verify` | MFA challenge | `MfaVerifyRequest` | `204` | 401 `MFA_INVALID`, 410, 429 | Completes admin login; sets full auth + CSRF cookies |
| `POST /api/v1/auth/mfa/recovery-codes/regenerate` | Admin + MFA | `MfaRecoveryRegenerateRequest` | `200 MfaRecoveryCodesRead` | 401, 404, 429 | Invalidates previous recovery codes; audit event |

### Captcha on Authentication Forms

From VS-033, register, resend verification and the password-reset request require a Turnstile `captcha_token` (ADR-025, SEC-12). The captcha is verified before any account lookup, and a refused captcha gives the same answer whatever the email address, so it is not an account-existence oracle. A refused token is `400 CAPTCHA_INVALID` and an outage `503 SERVICE_UNAVAILABLE` (ADR-026). Login, email verification and reset confirmation take no captcha.

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
| `GET /api/v1/me/addresses` | Authenticated | — | `200 AddressList` | 401 | Hard-limited: at most 20 live addresses (ADR-027) | Own addresses only; default first, then newest |
| `POST /api/v1/me/addresses` | Verified Customer | `AddressCreate` | `201 AddressRead` | 401, 403, 422 `ADDRESS_LIMIT_REACHED` | — | Setting default clears prior default atomically; a user's first live address is always the default (ADR-027) |
| `GET /api/v1/me/addresses/{address_id}` | Authenticated; owner | — | `200 AddressRead` | 401, 404 | — | Object ownership |
| `PATCH /api/v1/me/addresses/{address_id}` | Verified Customer; owner | `AddressUpdate` | `200 AddressRead` | 401, 403, 404, 422 | — | Historical orders unaffected because they use snapshots |
| `DELETE /api/v1/me/addresses/{address_id}` | Verified Customer; owner | — | `204` | 401, 403, 404 | — | Soft delete; deleting the default leaves none. No `409`: checkout locks the address it snapshots and refuses a deleted one (ADR-027) |
| `PUT /api/v1/me/addresses/{address_id}/default` | Verified Customer; owner | — | `200 AddressRead` | 401, 403, 404 | — | Atomically switches default |

---

# 10. Cart and Checkout

## 10.1 Cart

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/cart` | Authenticated | — | `200 CartRead` | 401 | Hard-limited: at most 50 lines (ADR-029) | Shows snapshot price + current price + `price_changed`, `over_cap` and `purchasable`; never creates a cart (`id: null` until the first write) |
| `POST /api/v1/cart/items` | Verified Customer | `CartItemAdd` | `200 CartRead` | 401, 403, 409 `PRODUCT_ALREADY_OWNED` (VS-023), 422 `PRODUCT_NOT_PURCHASABLE` (`reason`) / `QUANTITY_EXCEEDS_LIMIT` (`max_quantity`) / `CART_LINE_LIMIT_REACHED`, 429 | — | Existing product merges quantity, refused (never clamped) above the current cap; STL accepts only quantity 1, and re-adding an STL already in the cart is a no-op (VS-022) |
| `PATCH /api/v1/cart/items/{product_id}` | Verified Customer | `CartItemQuantityUpdate` | `200 CartRead` | 401, 403, 404, 422, 429 | — | Sets absolute quantity; STL accepts only 1; refused on a line no longer purchasable |
| `DELETE /api/v1/cart/items/{product_id}` | Verified Customer | — | `204` | 401, 403, 404, 429 | — | Removes (hard-deletes) the cart line; 404 when absent (ADR-029). One 300/hour per-user bucket covers `POST`, `PATCH` and `DELETE` |

## 10.2 Shipping Zones

Removed by ADR-024. The courier prices and collects the delivery fee; there is no shipping-zone endpoint, and no order carries a shipping amount.

## 10.3 Checkout

| Method + Path | Auth / Authorization | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/checkout` | Verified Customer | `CheckoutRequest` + required `Idempotency-Key` | `201 CheckoutRead` | 401, 403, 409 `CART_EMPTY` / `CART_PRICE_CHANGED` / `PRODUCT_ALREADY_OWNED` / `IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS`, 422 `INVALID_FULFILLMENT` / `PRODUCT_NOT_PURCHASABLE` / `QUANTITY_EXCEEDS_LIMIT` / `PAYMENT_METHOD_NOT_ALLOWED` / `CASH_PAYMENT_LIMIT_REACHED` / `CASH_NOT_AVAILABLE` / `VALIDATION_ERROR`, 429, 502 `PAYMENT_PROVIDER_UNAVAILABLE`, 503 `ORDERS_PAUSED` / `ONLINE_PAYMENT_UNAVAILABLE` | **As built (VS-023 online; VS-028 physical and cash, ADR-032, ADR-038):** online is two transactions around the provider call; cash is one transaction with no payment row and no provider call (`payment: null`), and works with `PAYMENT_PROVIDER=none`; the live price is charged; `dropped_lines` names STLs bought since they were added, on both paths; a replay carries `Idempotent-Replayed: true`, is a pure read and counts against the 30/hour limit; `PAYMENT_ALREADY_ACTIVE` is VS-024's retry code and cannot occur here. Full contract: [`docs/checkout.md`](../checkout.md). Target behaviour: single transaction validates cart, recomputes amounts, then validates the payment method against the recomputed total, snapshots order/lines/address/contact phone/payment method/terms, clears cart. Online: creates a pending payment with the chosen provider and returns provider redirect information. Cash: creates no payment and returns the order with `payment_due` |

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
| `GET /api/v1/me/orders` | Authenticated | query params | `200 OrderPage` | 401, 422 | Cursor; optional `status`, `placed_after` (inclusive), `placed_before` (exclusive), both with a timezone; fixed `-placed_at, -id` | Own orders only. **As built (VS-025):** items are `OrderSummary`; see [`docs/order-history.md`](../order-history.md) |
| `POST /api/v1/me/orders/{order_id}/payments` | Verified Customer; owner; CSRF | `PaymentRetryRequest` + required `Idempotency-Key` | `201 PaymentRetryRead` | 401, 403, 404, 409 `PAYMENT_ALREADY_ACTIVE` / `INVALID_STATE_TRANSITION` / `IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS`, 422 `PAYMENT_METHOD_NOT_ALLOWED` / `VALIDATION_ERROR`, 429, 502 `PAYMENT_PROVIDER_UNAVAILABLE`, 503 `ONLINE_PAYMENT_UNAVAILABLE` | — | **As built (VS-024, ADR-036):** retry on the same order before `placed_at + checkout_hold_period`; the order's own total is charged; key scoped `payment_retry:{order_id}` per user; two transactions around the provider call; 10/hour. Full contract: [`docs/payment-recovery.md`](../payment-recovery.md) |
| `GET /api/v1/me/orders/{order_id}` | Authenticated; owner | — | `200 OrderDetail` | 401, 404 | — | Includes lines, payment method, `payment_due`, `can_cancel`, payment projection, refund summary and status history needed by customer; `in_production` is shown as `pending` and omitted from the history. **As built (VS-025, ADR-033; VS-030):** `refunds[]` lists admin, cancellation and late-capture refunds as `processing` or `refunded`, never voided ones or chargebacks; another customer's order is the same 404 as an unknown id |
| `POST /api/v1/me/orders/{order_id}/cancel` | Verified Customer; owner | `CustomerOrderCancelRequest` | `200 OrderDetail` | 401, 403, 404, 409 `ORDER_NOT_CANCELLABLE` / `INVALID_STATE_TRANSITION` | — | V1 decision: cancels all still-self-cancellable physical lines atomically; digital lines are never cancelled; allowed only when `can_cancel` is true (a live physical line, a cash order or a payment that reached `paid`, every live (not cancelled) physical line `pending`; already-cancelled lines are ignored, ADR-033); if cancellation is no longer legally possible, no partial silent cancellation occurs |
| `POST /api/v1/me/orders/{order_id}/confirm-receipt` | Verified Customer; owner; CSRF | — | `200 OrderDetail` | 401, 403, 404, 409 `INVALID_STATE_TRANSITION` | — | Sets `receipt_confirmed_at` on delivered / picked-up lines; idempotent; no state change (ADR-024, VS-029b). **As built (ADR-041):** physical lines only; `409` carries `reason: no_delivered_line`; only unset timestamps are written; audited when a line was stamped; no rate limit. Contract: [`docs/order-history.md`](../order-history.md) |
| `POST /api/v1/me/orders/{order_id}/report-problem` | Verified Customer; owner; CSRF | `ProblemReportCreate` | `201 OrderDetail` | 401, 403, 404, 409 `INVALID_STATE_TRANSITION`, 422, 429 | — | Sets `problem_reported_at` and creates a contact message linked to the order; no state change (ADR-024, VS-029b). **As built (ADR-041):** physical lines only; the first report's time is kept and every report is a new message; one in-app notification (`order.problem_reported`) per active administrator in the same transaction; 5/hour per user; audited without the body |

The delivered / picked-up email links only to the order page; it never carries a link that changes state, because email scanners follow links.

---

# 12. Customer STL Purchases

Removed by ADR-019: there is no STL library, entitlement or download endpoint, because the platform stores no STL files. A customer sees each STL purchase and whether it has been sent as a line in `GET /api/v1/me/orders/{order_id}` (`fulfillment_status`: `awaiting_delivery` or `delivered`, with `fulfilled_at`). The file itself arrives by email from the administrator.

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/me/stl-ownership` | Authenticated | `product_id` query parameter (UUID, required) | `200 StlOwnershipRead` | 401, 422 | — | ADR-025, VS-023. `owned` is true when the caller has a paid, unrefunded STL line for the product (`awaiting_delivery` or `delivered`, not fully refunded). An unknown, hidden or physical product answers `owned: false`. A hint for the product page only: the cart and checkout still refuse a second purchase with 409 `PRODUCT_ALREADY_OWNED` |

---

# 13. Customer Offer / Negotiation Endpoints

| Method + Path | Auth / Authorization | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `POST /api/v1/offers` | Verified Customer | `OfferCreate` | `201 OfferDetail` | 401, 403, 409 `PRODUCT_ALREADY_OWNED` / `OFFER_ALREADY_ACTIVE`, 422 `OFFER_BELOW_MINIMUM` / `OFFER_COOLDOWN_ACTIVE` / `PRODUCT_NOT_PURCHASABLE`, 429, 503 `ORDERS_PAUSED` | — | STL only; first round appended; admin in-app notification (no email, SRS §16.1; ADR-034) |
| `GET /api/v1/me/offers` | Authenticated | query params | `200 OfferPage` | 401 | Cursor; optional `status`, `product_id`; default `-created_at` | Own offer history |
| `GET /api/v1/me/offers/{offer_id}` | Authenticated; owner | — | `200 OfferDetail` | 401, 404 | — | Includes append-only rounds and current deadline |
| `POST /api/v1/me/offers/{offer_id}/counter` | Verified Customer; owner; customer turn | `OfferCounterRequest` | `200 OfferDetail` | 401, 403, 404, 409 `OFFER_NOT_YOUR_TURN` / `INVALID_STATE_TRANSITION`, 410, 422, 429 | — | Adds round; switches turn; resets `responds_by`; notification/outbox |
| `POST /api/v1/me/offers/{offer_id}/accept` | Verified Customer; owner; customer turn | `OfferAcceptRequest` | `200 OfferDetail` | 401, 403, 404, 409 (incl. `OFFER_AMOUNT_CHANGED`), 410, 422, 429 | — | Freezes agreed price; creates checkout window; notification/outbox; `expected_amount_cents` must equal `current_amount` (ADR-035 d9) |
| `POST /api/v1/me/offers/{offer_id}/withdraw` | Verified Customer; owner | `OfferWithdrawRequest` (optional) | `200 OfferDetail` | 401, 403, 404, 409, 410, 429 | — | Legal in both awaiting states, whoever's turn (ADR-034, ADR-035); append history |
| `POST /api/v1/me/offers/{offer_id}/checkout` | Verified Customer; owner; accepted offer | `OfferCheckoutRequest` + `Idempotency-Key` | `201 CheckoutRead` | 401, 403, 404, 409 `INVALID_STATE_TRANSITION` / `PAYMENT_ALREADY_ACTIVE` / `PRODUCT_ALREADY_OWNED` / `IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS`, 410 `OFFER_CHECKOUT_EXPIRED`, 422 `PRODUCT_NOT_PURCHASABLE` / `PAYMENT_METHOD_NOT_ALLOWED` / `VALIDATION_ERROR`, 429, 502, 503 `ORDERS_PAUSED` / `ONLINE_PAYMENT_UNAVAILABLE` | — | One-time agreed-price checkout; creates order/payment; price comes from immutable accepted offer. **As built (VS-041, ADR-037):** cart checkout's two transactions, replay and 30/hour bucket; the order is inserted before the offer is locked and re-checked; the window does not stretch over a pause. Contract: [`docs/offers.md`](../offers.md) |

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

Removed by ADR-024: there are no shipping zones to manage.

---

# 17. Admin User Endpoints

| Method + Path | Auth | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|---|
| `GET /api/v1/admin/users` | Admin + MFA | query params | `200 AdminUserPage` | 401/404 | Cursor; filters verified/active; search email; `-created_at` | PII access audited/redacted from logs |
| `GET /api/v1/admin/users/{user_id}` | Admin + MFA | — | `200 AdminUserDetail` | 401/404 | — | Shows account status and admin-safe customer summary |
| `PATCH /api/v1/admin/users/{user_id}` | Admin + MFA | `AdminUserUpdate` | `200 AdminUserDetail` | 401/404, 409, 422 | — | V1 allows account activation/deactivation controls; no arbitrary password editing; detail shows any uncleared cash payment blocks |

The admin entitlement-grant endpoint is removed by ADR-019. To give an STL away, the administrator simply emails it; the platform records nothing.

---

# 18. Admin Order / Fulfillment Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/orders` | query params | `200 AdminOrderPage` | 401/404, 400 | Cursor; filters `status`, `fulfillment_method`, `payment_method`, `payment_due`, customer, order number, dates; default `-placed_at` | Admin fulfillment queue; never lists `pending_payment` orders (BR-148); `payment_due=true` is the "cash due" view |
| `GET /api/v1/admin/orders/{order_id}` | — | `200 AdminOrderDetail` | 401/404 | — | Customer/order data, contact phone, payment method and amount due, lines with `available_actions` (ADR-025), status history, payments/refunds, internal note |
| `PATCH /api/v1/admin/orders/{order_id}` | `AdminOrderUpdate` | `200 AdminOrderDetail` | 401/404, 422 | — | V1 restricted to mutable admin fields such as internal note; order status is not directly patchable |
| `GET /api/v1/admin/stl-deliveries` | query params | `200 StlDeliveryPage` | 401/404, 422 | Cursor; optional `product_id`, `customer_id`; oldest first by `(order_items.created_at, id)`, the placement time (VS-023b, [`stl-delivery.md`](../stl-delivery.md)) | STL delivery queue (ADR-019): every STL line in `awaiting_delivery`, with order number, product, customer and `customer_email_snapshot` to send to |
| `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition` | `OrderItemTransitionRequest` | `200 AdminOrderDetail` | 401/404, 409 `INVALID_STATE_TRANSITION`, 422 | — | Locks the order, then the line (ADR-024 lock order); a physical edge requires a cash order or an online payment that reached `paid` — `paid`, `partially_refunded` or `refunded` (BR-148); validates the delivery/pickup/STL state machine; `→ cancelled` from `ready_to_ship`, `returned` or `ready_for_pickup` requires `cancel_reason` and may insert a cash payment block (BR-144; it then also locks the customer's cart and takes the phone advisory lock); an unpaid cash line totalling 0 may go `shipped → cancelled` (`other`); recomputes order projection; history + audit + notifications (one per order per visible step, ADR-040 d2). The cancel and return edges, `cancel_reason` and the BR-144 block arrive with VS-031 (ADR-040 d1). For an STL line, `awaiting_delivery → delivered` records `fulfilled_at` and `delivered_by` and notifies the customer that the file was emailed. `→ in_production` sends no customer notification. On a cash order, `→ delivered` and `→ picked_up` are refused; use the cash handover |
| `POST /api/v1/admin/orders/{order_id}/cash-handover` | `CashHandoverRequest` | `200 AdminOrderDetail` | 401/404, 409 `INVALID_STATE_TRANSITION`, 422 `CASH_AMOUNT_MISMATCH` | — | Cash orders only. Locks the order, then all lines by `id`; at least one live line, and every live line `shipped` / `ready_for_pickup`; amount must equal the sum of live line totals and be above zero (the full amount the customer paid); marks them delivered / picked up, creates the single `cash` payment (`paid`, `recorded_by`), recomputes status; history + audit + notification + email with the cash receipt (ADR-024) |
| `POST /api/v1/admin/orders/{order_id}/cancel` | `AdminOrderCancelRequest` | `200 AdminOrderDetail` | 401/404, 409 `INVALID_STATE_TRANSITION` | — | Locks the order, then all physical lines by `id`. 409 on an unpaid online (`pending_payment`) order (BR-148; only the hold release cancels those). Cancels eligible lines according to state (`pending`, `in_production`, `ready_to_ship`, `ready_for_pickup`); `cancel_reason` required for `ready_to_ship` and `ready_for_pickup` lines; a paid line's `cancellation` refund is its remaining balance (none when 0); on a cash order the BR-144 block rule applies (then also the customer's cart lock and the phone advisory lock); digital rules preserved |

| `GET /api/v1/admin/cash-blocks` | query params | `200 CashPaymentBlockPage` | 401/404 | Cursor; filters customer, `active`; default `-created_at` | Cash payment blocks (ADR-024) |
| `POST /api/v1/admin/cash-blocks/search` | `CashBlockSearchRequest` (`phone`) | `200 CashPaymentBlockPage` | 401/404, 422 | Cursor | Finds blocks by phone; the number travels in the body, so it never reaches request logs, and is hashed before matching |
| `POST /api/v1/admin/cash-blocks/{block_id}/clear` | — | `200 CashPaymentBlockRead` | 401/404 | — | Sets `cleared_at`/`cleared_by`; audited; idempotent |

The line-transition endpoint and, for cash orders, the cash-handover endpoint are the only normal API paths for fulfillment status changes.

Every line of every `AdminOrderDetail` (including the one returned by a transition, handover or cancel) carries `available_actions`: the transitions the line-transition endpoint would accept for it at read time (ADR-025). It is a hint; the endpoint remains the authority and answers 409 `INVALID_STATE_TRANSITION` after a concurrent change.

---

# 19. Admin Refund Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/admin/orders/{order_id}/refunds` | `RefundCreate` + required `Idempotency-Key` | `201 RefundDetail` | 401/404, 409 `ORDER_NOT_PAID` / `ORDER_TOTAL_MISMATCH` / `IDEMPOTENCY_KEY_CONFLICT` / `IDEMPOTENCY_REQUEST_IN_PROGRESS`, 422 `REFUND_EXCEEDS_AVAILABLE` (with `available`) / `REFUND_REQUIRES_CANCELLATION` / `VALIDATION_ERROR`, 429 | — | Records a `kind = admin` refund; the administrator then pays it by hand (provider dashboard or cash) and settles it. The platform calls no provider. One transaction with the key's claim: a 4xx stores nothing. Locks the order, every line, the order's payments, then the refund (ADR-042 d8). Supports selected paid-line amounts (BR-149; no shipping, ADR-024); validates each line against `line_total` minus its items in pending, settled and owed refunds and in chargebacks (0 for a cancelled line without any), and the sum against the payment's balance; refuses to empty an unfinished physical line; a cash payment is refunded up to the cash recorded; a line becomes `refunded` only when fully covered, and a fully refunded STL line leaves the delivery queue; recomputes payment and order status; audit; the customer's "refund issued" email and notification (Q7) |
| `GET /api/v1/admin/refunds` | query params | `200 RefundPage` | 401/404 | Cursor; `status`, `kind`, order/customer/date; default oldest first when queueing | Obligations queue: pending refunds and owed refunds (failed, not reissued); chargebacks never appear as obligations |
| `GET /api/v1/admin/refunds/{refund_id}` | — | `200 RefundDetail` | 401/404 | — | Full settlement/audit view |
| `POST /api/v1/admin/refunds/{refund_id}/settle` | `RefundSettlementRequest` | `200 RefundDetail` | 401/404, 409 `INVALID_STATE_TRANSITION` (`not_pending`), 422 | — | Records that the administrator paid it: `pending → settled`; settling a settled refund answers 200 unchanged. Locks order, lines, payments, refund. No order or payment status changes, and no Q-2 check (it moves no money). A `late_capture` refund's "refund issued" notice goes out here (Q7); audited |
| `POST /api/v1/admin/refunds/{refund_id}/fail` | `RefundFailureRequest` | `200 RefundDetail` | 401/404, 409 `INVALID_STATE_TRANSITION` / `ORDER_TOTAL_MISMATCH` | — | Marks a pending refund `failed` when the money did not reach the customer (ADR-024): no line state changes; the refund stays owed in the obligations queue; recomputes payment and order status (owed → `partially_refunded`); audited |
| `POST /api/v1/admin/refunds/{refund_id}/void` | `RefundVoidRequest` | `200 RefundDetail` | 401/404, 409 `INVALID_STATE_TRANSITION` (`already_settled`, `already_reissued`, `line_already_refunded`, `line_already_cancelled`) / `ORDER_TOTAL_MISMATCH`, 422 | — | Closes a pending or owed refund created by mistake, unpaid (ADR-042 d2): frees its balance, recomputes payment and order status, one `refund.voided` audit row with the reason. A second void answers 200 with the first reason. Never a settled refund, never one whose line is already `refunded` or `cancelled`; a voided refund is never reissued |
| `POST /api/v1/admin/refunds/{refund_id}/reissue` | — + required `Idempotency-Key` | `201 RefundDetail` | 401/404, 409 `INVALID_STATE_TRANSITION` (`not_failed`, `already_reissued` with `reissued_by_refund_id`) / `ORDER_TOTAL_MISMATCH` / `IDEMPOTENCY_KEY_CONFLICT` | — | Only for a `failed` refund not yet reissued: creates a new pending refund of the same kind, items and amount (`reason = reissue of <id>`), sets `reissued_at` on the failed one; recomputes status; audited, no customer notice |
| `POST /api/v1/admin/orders/{order_id}/chargebacks` | `ChargebackCreate` + required `Idempotency-Key` | `201 ChargebackDetail` | 401/404, 409 `ORDER_NOT_PAID` / `CHARGEBACK_DUPLICATE` / `ORDER_TOTAL_MISMATCH` / `IDEMPOTENCY_KEY_CONFLICT`, 422 `CHARGEBACK_NOT_ONLINE` / `CHARGEBACK_ITEMS_FORBIDDEN` / `CHARGEBACK_ALLOCATION_INVALID` / `VALIDATION_ERROR`, 429 | — | ADR-042 d3-d5, d16: voids every pending and owed refund on the payment and absorbs their items; a remainder the bank did not cover stays owed as a new pending refund; the administrator's items add coverage, a line they empty becomes `refunded` (delivered, picked up, returned, STL) or `cancelled` (unfinished physical, no refund); the rest is excess. Recomputes payment and order status (none on a late-captured attempt); audit `chargeback.recorded`; one alert per chargeback (`chargeback_excess` when there is excess). Never in the obligations queue |
| `GET /api/v1/admin/orders/{order_id}/chargebacks` | — | `200 list[ChargebackDetail]` | 401/404 | Oldest first | An order's chargebacks |
| `GET /api/v1/admin/chargebacks/{chargeback_id}` | — | `200 ChargebackDetail` | 401/404 | — | One chargeback with its items |

Refund settlement is explicit because the SRS requires obligations to remain tracked until actually settled.

---

# 20. Admin Payment / Reconciliation Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/payments` | query params | `200 AdminPaymentPage` | 401/404, 422 | Cursor `(initiated_at, id)`, oldest first; filters `status` (repeatable), `provider`, `order_id`, `late_captured`, `initiated_after`, `initiated_before` | **As built (VS-024):** `late_captured=true` lists late captures; no provider metadata, payload or customer email; `needs_attention` and `last_provider_answer` are not built (ADR-036) |
| `GET /api/v1/admin/payments/{payment_id}` | — | `200 AdminPaymentDetail` | 401/404 | — | **As built (VS-024):** the order with `hold_expires_at` and `manual_release_available_at`, events without payloads, the audit history (newest first, at most 100) and `available_actions` |
| `POST /api/v1/admin/payments/{payment_id}/reconcile` | — | `202 ReconcileQueued` | 401/404, 409 `INVALID_STATE_TRANSITION` (cash), 429, 503 `PAYMENT_VERIFICATION_UNAVAILABLE` | — | **As built (VS-024):** answers 202 after its audit row commits; the provider is queried afterwards in a background task with no transaction open; no answer or `unknown` is audited as `payment.reconcile_deferred`; 60/hour per admin |
| `POST /api/v1/admin/payments/{payment_id}/confirm` | `ManualPaymentConfirmRequest` | `200 ManualConfirmRead` | 401/404, 409 `MANUAL_CONFIRMATION_NOT_ALLOWED` / `PAYMENT_REFERENCE_MISMATCH` / `INVALID_STATE_TRANSITION`, 422 `PAYMENT_AMOUNT_MISMATCH` / `VALIDATION_ERROR`, 429 | — | Online payments on a provider without a status API only (VS-024, ADR-036). A typed amount or currency that differs from the attempt is 422 and writes nothing. Otherwise, on a live attempt of an uncancelled order it applies the payment; on an attempt no longer live, or on a cancelled order, it records a late capture (alert) instead. STL delivery queue/status/audit/outbox side effects; 30/hour per admin. Cash is recorded by the cash handover instead |
| `POST /api/v1/admin/payments/{payment_id}/record-capture` | `RecordCaptureRequest` + required `Idempotency-Key` | `201 RecordCaptureRead` | 401/404, 409 `MANUAL_CONFIRMATION_NOT_ALLOWED` / `INVALID_STATE_TRANSITION` (`cash_payment`, `already_paid`, `already_late_captured`, `use_confirm`) / `IDEMPOTENCY_KEY_CONFLICT`, 422, 429 | — | VS-030 Q5 (VS-024 Q2): a capture the dashboard shows on a provider without a status API, whose amount or currency differs from an attempt that never reached paid. Recorded as a late capture through the normal path (a live attempt is failed), so the alert and the `late_capture` refund obligation follow; a matching amount is refused (`use_confirm`). Audit `payment.capture_recorded` keeps the typed values; 30/hour per admin |
| `POST /api/v1/admin/orders/{order_id}/release` | `OrderReleaseRequest` | `200 OrderReleaseRead` | 401/404, 409 `INVALID_STATE_TRANSITION` (`cash_order`, `order_cancelled`, `order_not_payable`, `grace_not_elapsed` with `release_available_at`, `unprocessed_events` with `count`), 422, 429 | — | **As built (VS-024, ADR-036):** the manual hold release, from the hold deadline plus 24 h; mandatory `reason`; `events_reviewed` dismisses unprocessed events; expires the live attempt; never calls the provider; 30/hour per admin |

A callback alone never authorizes these state changes.

---

# 21. Admin Offer Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/offers` | query params | `200 AdminOfferPage` | 401/404 | Cursor; `status`, `product_id`, customer, deadlines; pending deadline first | Pending offers queue |
| `GET /api/v1/admin/offers/{offer_id}` | — | `200 AdminOfferDetail` | 401/404 | — | Complete negotiation rounds |
| `POST /api/v1/admin/offers/{offer_id}/counter` | `OfferCounterRequest` | `200 AdminOfferDetail` | 401/404, 409 `OFFER_NOT_YOUR_TURN`, 410, 422 | — | Append round; switch turn; reset deadline; notification/outbox |
| `POST /api/v1/admin/offers/{offer_id}/accept` | `OfferAcceptRequest` | `200 AdminOfferDetail` | 401/404, 409 (incl. `OFFER_AMOUNT_CHANGED`), 410, 422 | — | Freeze current amount; start checkout window; notification/outbox; `expected_amount_cents` must equal `current_amount` (ADR-035 d9) |
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
| `GET /api/v1/admin/custom-requests` | query params | `200 CustomRequestPage` | 401/404, 422 | Cursor; `status`, `created_after`/`created_before`, exact `email`; order (status, created_at, id): `new` first, `closed`/`lost` last, oldest first | Lead pipeline; audited `custom_request.list_viewed` (VS-035) |
| `GET /api/v1/admin/custom-requests/{request_id}` | — | `200 CustomRequestDetail` | 401/404 | — | Includes admin fields and the metadata of unexpired attachments (no storage key); audited `custom_request.viewed` |
| `POST /api/v1/admin/custom-requests/{request_id}/transition` | `CustomRequestTransition` | `200 CustomRequestDetail` | 401/404, 403 CSRF, 409 `INVALID_STATE_TRANSITION`, 422 | — | Enforces the state machine under a row lock (staying put is 409); `quoted` requires an amount; the server sets the outcome (`won` at `in_progress`, `lost` at `lost`) and USD; audit (ADR-031) |
| `PATCH /api/v1/admin/custom-requests/{request_id}` | `CustomRequestAdminUpdate` | `200 CustomRequestDetail` | 401/404, 403 CSRF, 422 | — | Notes only (blank clears); any other field, status included, is 422; audited without the text |
| `GET /api/v1/admin/custom-requests/{request_id}/attachments/{attachment_id}/download` | Admin + MFA | — | Binary `200` | 401/404 | — | Streamed by the API (`no-store`, `attachment`, `nosniff`, sandboxed CSP); no Range; expired (`expires_at <= now`), purged, missing or another request's attachment is 404; audited. VS-020 may switch to nginx `X-Accel-Redirect` (ADR-031) |

---

# 24. Admin Contact Message Endpoints

| Method + Path | Request | Success | Errors | Pagination / Filter / Sort | Side Effects / Notes |
|---|---|---|---|---|---|
| `GET /api/v1/admin/contact-messages` | query params | `200 ContactMessagePage` | 401/404, 422 | Cursor; `status`, `created_after` (inclusive), `created_before` (exclusive), exact `email`; sorted `status` (new, read, replied, archived), then oldest first | Admin queue; audited as `contact_message.list_viewed` (filters as flags, no address) |
| `GET /api/v1/admin/contact-messages/{message_id}` | — | `200 ContactMessageDetail` | 401/404 | — | Audited as `contact_message.viewed`; does not mark the message read. Carries `user_id` and `order_id`, set only for a customer's problem report (VS-029b, ADR-041) |
| `PATCH /api/v1/admin/contact-messages/{message_id}` | `ContactMessageAdminUpdate` | `200 ContactMessageDetail` | 401/404, 403 `CSRF_INVALID`, 409 `INVALID_STATE_TRANSITION`, 422 | — | Status moves forward only, skipping allowed (new, read, replied, archived); the same status is a no-op that is still audited. Checked under a row lock and audited as `contact_message.status_changed` (status only). The reply itself happens outside the system |

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
| `GET /api/v1/admin/analytics/custom-requests/funnel` | `from`, `to` (UTC offset; default the last 90 days; at most 366) | `200 CustomRequestFunnelAnalytics` | 401/404, 422 | Submission-date cohort `[from, to)`: submitted, contacted, quoted, won, lost, open and quoted/won totals in cents (VS-035, ADR-031) |

Exact analytics default ranges/export formats remain tunable design-time settings; the route shapes are stable.

---

# 28. Payment Webhook

| Method + Path | Auth / Authorization | Request | Success | Errors | Side Effects / Notes |
|---|---|---|---|---|---|
| `POST /api/v1/webhooks/payments/{provider}` | Provider; IP allowlist (VS-020 nginx) + HMAC signature | raw provider event, at most 64 KiB | `200 WebhookAck` (`{received: true}`) | 400 `VALIDATION_ERROR` (body over 64 KiB, checked before the signature, or a signed body unreadable), 401 `WEBHOOK_SIGNATURE_INVALID`, 404 (provider not configured; never `cash`), 429 (per IP for bad signatures, per provider otherwise) | Persist unique `(provider,event_id)` first and return quickly; duplicate event is safe; callback never marks order paid by itself; verification asks the provider after the 200, with the `verify_payments` job as fallback (VS-023, ADR-032). Ignored events: §5.3 |

The online provider is undecided (SRS §30.4); `{provider}` is its `payment_provider` value. Only configured online providers are routable: any other value, `cash` always, and `mock` in production give 404 and store nothing. Verification uses the adapter named on the payment row, never the URL; an event whose provider differs from its payment's provider is stored, ignored and alerted. Signature mechanics and status-query capabilities remain provider-dependent external details. The endpoint contract does not trust them as proof.

---

# 29. Request Schema Catalogue

Only significant request fields are listed here. All schemas reject unknown fields unless explicitly documented.

## 29.1 Identity

### `RegisterRequest`

```text
email: Email
password: str
captcha_token: str   # from VS-033 (ADR-025)
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
captcha_token: str   # from VS-033 (ADR-025)
```

### `PasswordResetRequest`

```text
email: Email
captcha_token: str   # from VS-033 (ADR-025)
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
landmark_notes: str   # required: SRS 14.4 (ADR-027)
is_default?: bool
```

`phone` is a Lebanese number in any common spelling, stored and returned as E.164 (`+9613123456`). `governorate` is one of `akkar`, `baalbek_hermel`, `beirut`, `beqaa`, `keserwan_jbeil`, `mount_lebanon`, `nabatieh`, `north`, `south`. Full contract: [`docs/address-book.md`](../address-book.md).

### `AddressUpdate`

Same fields optional; empty update rejected; `null` clears `area` or `street` only. `is_default: false` on the default clears it.

### `AddressRead`

The create fields (phone in E.164) plus `id`, `is_default`, `created_at`, `updated_at`. `AddressList` is `{items: AddressRead[]}`.

---

## 29.4 Cart

### `CartItemAdd`

```text
product_id: UUID
quantity: int = 1
```

Physical: 1..current max cap, after merging with an existing line.  
STL: server requires exactly 1 (`422 QUANTITY_EXCEEDS_LIMIT` otherwise).  
`quantity` is a JSON integer, 1..2 147 483 647; unknown fields are refused (VS-022).

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
contact_phone?: str
payment_method: "online" | "cash"
payment_provider?: payment_provider   # online only; required when more than one is configured
customer_note?: str
accept_terms: true
accept_digital_final_sale?: true
accept_cash_terms?: true
accepted_price_changes?: [
  {
    product_id: UUID,
    amount_cents: int,
    currency: "USD"
  }
]
```

Rules:

- digital-only → fulfillment/address/contact phone are null; `payment_method=online`;
- physical delivery → fulfillment=`delivery`, address required; the contact phone is the address's phone;
- physical pickup → fulfillment=`pickup`, no address; `contact_phone` (Lebanese number) required;
- mixed order follows physical fulfillment rules and must be `online`;
- `payment_method=cash` requires every line physical, cash enabled, no uncleared block for the customer or the normalised contact phone, fewer than `cash_max_open_orders` open unpaid cash orders for the customer or that phone, the **recomputed** total above 0 and ≤ `cash_max_order_total`, and `accept_cash_terms=true`;
- `payment_provider` must be a configured online provider; it is stored on the payment row;
- the contact phone is stored normalised to E.164;
- `accept_digital_final_sale=true` is required when any digital line exists;
- client never submits subtotal/total; there is no shipping amount (ADR-024).

As built in VS-028 ([ADR-038](../adr/ADR-038-physical-checkout-and-cash-eligibility.md), [`docs/checkout.md`](../checkout.md)):
- the rules apply to the **kept** lines, after owned STLs are dropped, so a mixed cart whose STL is owned may pay cash;
- `contact_phone` sent with delivery → `INVALID_FULFILLMENT`; an invalid number → `VALIDATION_ERROR` at `body.contact_phone`, never echoing the input;
- an unknown, another customer's or a deleted `address_id` → one `INVALID_FULFILLMENT`; pickup while `pickup_address` is unset → `INVALID_FULFILLMENT`;
- `payment_provider` sent with cash → `PAYMENT_METHOD_NOT_ALLOWED` (`provider_not_applicable`);
- a missing `accept_cash_terms` for cash → `VALIDATION_ERROR` at `body.accept_cash_terms`;
- a block or the open-order limit → one `CASH_NOT_AVAILABLE` with no `reason`, whether the account or the phone matched; the total cap (`CASH_PAYMENT_LIMIT_REACHED`, `order_total`) is checked first, before the phone (ADR-038 d19-d20).

### `OfferCheckoutRequest`

```text
accept_terms: true
accept_digital_final_sale: true
payment_provider?: str      # as built (VS-041): as checkout and retry take it
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
cancel_reason?: "refused" | "no_show" | "other"   # required for → cancelled from ready_to_ship, returned or ready_for_pickup
```

The server validates legal transition, actor, payment state (BR-148) and cancel reason (`refused` or `other` from `ready_to_ship`, `returned` or `ready_for_pickup`; `no_show` only from `ready_for_pickup`).

### `AdminOrderCancelRequest`

```text
reason: str
cancel_reason?: "refused" | "no_show" | "other"   # required when a ready_to_ship or ready_for_pickup line is cancelled; no_show only for ready_for_pickup
```

### `CashHandoverRequest`

```text
amount_cents: int
currency: "USD"
note?: str
```

The amount must equal the sum of live line totals; the server never derives it from this field.

### `ProblemReportCreate`

```text
message: str         # 1-5000 after trimming; line breaks allowed (VS-029b)
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

### `OfferAcceptRequest`

```text
expected_amount_cents: int  # the current_amount the caller saw (ADR-035 d9)
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
name: str                 # 1-100 after trimming
email: Email
phone: str                # up to 32; digits, spaces, + ( ) . -; at least 6 digits
project_title: str        # 1-200 after trimming
description: str          # 1-5000 after trimming; line breaks allowed
preferred_material?: str  # up to 100; blank means none
preferred_colour?: str    # up to 100; blank means none
dimensions?: str          # up to 200; blank means none
captcha_token: str        # VS-033 (ADR-025, ADR-026); an empty part is 422 (ADR-030)
attachments[]: file       # 0-5 JPEG/PNG/WebP, 10 MB each; omit when none (VS-034)
```

### `ContactMessageCreate`

```text
name: str            # 1-100 after trimming
email: Email
phone?: str          # up to 32; digits, spaces, + ( ) . -; at least 6 digits
subject?: str        # up to 200; blank means none
message: str         # 1-5000 after trimming; line breaks allowed
captcha_token: str   # VS-033 (ADR-025, ADR-026)
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
reason: str
```

Rules:

- server derives currency;
- every amount is validated against remaining refundable value;
- overall refund total is derived server-side;
- a fully refunded STL line becomes `refunded` and leaves the delivery queue; a partial refund leaves the line in its state;
- every V1 refund is manual (ADR-024): the administrator records it, pays it outside the platform, then settles it here; the route always records `kind = admin`;
- a request that would empty an unfinished physical line gives 422 `REFUND_REQUIRES_CANCELLATION`;
- `items` 1-50, each `order_item_id` once, `amount_cents` 1 to 10^9; `reason` 1-1000.

### `RefundSettlementRequest`, `RefundFailureRequest`, `RefundVoidRequest`

```text
settle: reference: str ≤200 | null, note: str ≤1000 | null
fail:   reason: str 1..1000
void:   reason: str 1..1000
```

### `ChargebackCreate` (VS-030, ADR-042)

```text
payment_id: UUID
provider_dispute_reference: str 1..200   # unique per provider
charged_cents: int > 0
items: [{order_item_id: UUID, amount_cents: int > 0}]   # 0..50; coverage beyond the absorbed refunds
reason: str 1..1000
received_at: datetime with offset
```

`ChargebackDetail` adds `id`, `order_number`, `payment_provider`, `applied_cents`, `excess_cents`, `currency`, `recorded_by`, `created_at` and the items with their product names. It never carries a phone, hash, address or the payment's provider reference.

### `RecordCaptureRequest` (VS-030 Q5)

```text
captured_amount_cents: int > 0
captured_currency: str  # ^[A-Z]{3}$, stored as reported, never converted
dashboard_reference: str 1..255
reason: str
```

`RecordCaptureRead` is `{outcome, payment, refund_id}`.

### `CashBlockSearchRequest`

```text
phone: str   # normalised and hashed server-side; never logged
```

Each search writes one `cash_block.searched` audit row with the filters, the result count and the block ids: never the phone or its hash (VS-030 Q8, ADR-038).

### `RefundFailureRequest`

```text
reason: str
```

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
provider_reference: str (1..255)
verified_amount_cents: int (>= 0)
verified_currency: str(3) = "USD"
reason: str (10..1000)            # was `evidence_note`
```

A typed amount or currency that differs from the attempt is `422 PAYMENT_AMOUNT_MISMATCH` (with `expected_amount_cents`), refused before any write and never recorded as a late capture. The admin actor, request id, IP hash, typed amount, reference and reason are audited (VS-024, ADR-036).

---

## 29.15 Custom Request Admin

### `CustomRequestTransition`

```text
target_status: custom_request_status
quoted_amount_cents?: int   # required for quoted, 1-100,000,000; refused otherwise
```

The server derives `outcome` (`won` at `in_progress`, `lost` at `lost`) and `currency` (`USD`); `outcome` and `note` are not accepted (ADR-031). Notes go through `CustomRequestAdminUpdate`.

### `CustomRequestAdminUpdate`

```text
admin_notes: str | null   # required key, at most 5000; blank or null clears
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
id                      # null until the first write
items[]                 # in the order first added
each item:
  product_id, product_type, name
  slug, cover_image      # null when the product is no longer listed
  quantity
  snapshot_price         # display only; checkout charges the live price
  current_price          # null when the product is no longer listed
  price_changed
  max_quantity           # current physical cap; null for STL / not listed
  over_cap               # quantity above the current cap; checkout refuses it
  purchasable
  unpurchasable_reason   # not_listed | unavailable | whatsapp_only | null
derived:
  contains_physical
  contains_digital
updated_at
```

No client-authoritative total is trusted for checkout, so none is returned. Full contract: [`docs/cart.md`](../cart.md) (VS-022).

## `CheckoutRead`

```text
order: OrderDetail or OrderSummary
payment:
  id
  status
  provider
  redirect_url?
```

As built in VS-028: `payment` is null for a cash order. `order` adds `estimated_dispatch_at`, `delivery_fee_note` (delivery only), `delivery_address` (`{recipient_name, governorate, city, area, street, landmark_notes}` or null; never the contact phone or its hash), `payment_due` and `amount_due` (a `PriceRead`; cash only, else null).

As built in VS-023 (digital, online): `order` is `{id, order_number, source, status, payment_method, fulfillment_method, subtotal, tax, total, placed_at, lines[{id, product_id, product_type, name, unit_price, quantity, line_total, fulfillment_status}]}`, `payment` is `{id, status: "pending", provider, redirect_url}`, and `dropped_lines` is `[{product_id, reason: "already_owned"}]`. No provider reference, provider metadata or `admin_note` is ever returned.

## `OrderDetail`

Includes:

```text
id
order_number
source
derived status
fulfillment_method
payment_method
payment_due
can_cancel
monetary breakdown (subtotal, tax, total; no shipping)
address and contact-phone snapshots where applicable
delivery_fee_note ("delivery fee paid to the courier on delivery") for delivery orders
estimated_dispatch_at (shown as the estimated ready date)
placed/completed/cancelled timestamps
lines[]
customer-visible notes
payment summary
refund summary
customer-visible status history (omits in_production)
```

`admin_note` is never returned by customer endpoints.

As built in VS-025 ([ADR-033](../adr/ADR-033-customer-order-read-model.md), [`docs/order-history.md`](../order-history.md)): `{id, order_number, source, status, fulfillment_method, payment_method, payment_due, can_cancel, subtotal, tax, total, delivery_address, contact_phone, delivery_fee_note, estimated_dispatch_at, placed_at, completed_at, cancelled_at, customer_note, lines[], payment, status_history[]}`. Each line is `{id, product_id, product_type, name, image_url, unit_price, quantity, line_total, fulfillment_status, fulfilled_at, cancelled_at}`; `payment` is `{status, provider, amount}` or null; each history entry is `{order_item_id, from_status, to_status, at}`. VS-030 added `refunds[]`: `{kind, status, amount, created_at}`, `status` being `processing` (pending or owed) or `refunded` (settled); voided refunds, a reissued failure and chargebacks are never listed (Q9). VS-041 added `can_retry_payment` and `hold_expires_at` (ADR-037 d10). VS-028 added `amount_due` (a `PriceRead`): the total of the lines not cancelled while `payment_due`, else null.

## `OrderSummary`

As built in VS-025: `{id, order_number, status, payment_method, fulfillment_method, payment_due, total, placed_at}`, in an `OrderPage` (`items`, `next_cursor`). VS-028 added `amount_due` (as in `OrderDetail`).

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

As built in VS-039 ([ADR-034](../adr/ADR-034-offer-submission-and-expiry.md), [`docs/offers.md`](../offers.md)): `{id, product {id, name, slug, cover_image}, status, turn, initial_amount, current_amount, agreed_amount, responds_by, checkout_expires_at, cooldown_until, created_at, updated_at, rounds[], allowed_actions[]}`; each round is `{sequence, actor, action, amount, message, created_at}`. `allowed_actions` lists what the caller may do now (`counter`, `accept`, `reject`, `withdraw`; VS-040, [ADR-035](../adr/ADR-035-offer-negotiation.md)); `responds_by` is null once accepted. The admin shapes add `customer {id, email}`; list rows (`OfferSummary`) omit `initial_amount`, `cooldown_until`, `updated_at`, `rounds` and `allowed_actions`. An amount above the list price is `422 VALIDATION_ERROR`, and the kill switch refuses `POST /offers` with `503 ORDERS_PAUSED`.

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

Order lines in `OrderDetail` carry `fulfillment_status` (with `in_production` shown as `pending`) and `fulfilled_at` (for STL lines, when the file was emailed); physical lines carry `receipt_confirmed_at` and `problem_reported_at`.

## `AdminOrderDetail` line actions

Each line in `AdminOrderDetail` carries (ADR-025):

```text
available_actions[]:
  target_status: order_item_status
  cancel_reasons: ["refused" | "no_show" | "other"]   # empty: no reason taken; otherwise one is required
```

Computed from the same transition table the line-transition endpoint enforces, including the BR-148 payment gate and the cash-handover rule. `[]` when no transition is legal.

## `StlOwnershipRead`

```text
product_id: UUID
owned: bool
```

## `PublicSettingsRead`

Strict allowlist, e.g.:

```text
accepting_orders
cash_payment_enabled
cash_max_order_total
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
payment_method
payment_due
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
| Checkout | order + immutable line snapshots + payment (online only) + consent + cart clear + idempotency record |
| Payment verification | payment state + STL lines to `awaiting_delivery` + physical lines stay `pending` + close live offer + order projection + history + audit + outbox/notifications |
| Customer/admin cancellation | line transitions + order projection + refund obligation for paid lines + cash payment block on a whole-order cash refusal or no-show + history + audit + outbox |
| Cash handover | live lines to delivered / picked up + `cash` payment + order projection + badge recompute + history + audit + outbox/notification with cash receipt |
| Receipt confirmation / problem report | line timestamps (+ contact message for a report) |
| Refund | refund obligation + refund items + fully refunded lines to `refunded` (STL leaves delivery queue) + order projection + audit + outbox |
| Refund failure | refund `failed` (stays owed in the obligations queue; no line state change) + payment and order projection + audit |
| Refund reissue | new pending refund of the same kind, items and amount + `reissued_at` on the failed one + audit |
| Chargeback | open refunds on the payment voided and absorbed + remainder refund + chargeback and its items + emptied lines `refunded` or `cancelled` + payment and order projection + audit + alert |
| Refund void | refund `voided` (balance freed) + payment and order projection + audit |
| Late capture | `late_captured_at` on the attempt + automatic `late_capture` refund obligation + alert; order and lines untouched |
| Offer create/counter/accept/reject/withdraw | append offer round + state/deadline + audit + outbox/notification |
| Review create/update/delete/moderate | review mutation + rating/review-count aggregate |
| Wishlist add/remove | active wishlist state + wishlist-count aggregate |
| Setting change | typed setting mutation + audit |
| Fulfillment transition | line state + derived order status + history + audit + appropriate email/notification (none for `in_production`; STL `delivered`: "file sent" email + notification) |

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
| Shipping zones / shipping fees | Removed by ADR-024; the courier prices and collects delivery |
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
purge_expired_security_records
verify_payments
purge_expired_idempotency_records
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
| F-027 Purchased STLs with delivery status | `/me/orders*` line status; `GET /me/stl-ownership` for one product (ADR-025) |
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
| F-043 Removed (ADR-024) | — |
| F-044 Pickup | `CheckoutRequest.fulfillment_method=pickup` |
| F-045 Removed (ADR-024) | — |
| F-046 Idempotent checkout | `POST /checkout` + `Idempotency-Key` |
| F-047 Online payment redirect/return | checkout returns redirect; order detail used after return |
| F-048 Webhook | `POST /webhooks/payments/{provider}` |
| F-049 Server verification | internal provider adapter + admin reconcile route |
| F-050 Reconciliation | scheduled job + `POST /admin/payments/{id}/reconcile` |
| F-051 Manual confirmation | `POST /admin/payments/{id}/confirm` |
| F-052 Terms consent | checkout request + immutable order timestamps |
| F-053 Payment method choice | `CheckoutRequest.payment_method` + cash limits |
| F-054 Cash handover | `POST /admin/orders/{id}/cash-handover` |

## 35.4 Fulfillment

| Feature | Endpoint |
|---|---|
| F-060 Order queue | `GET /admin/orders` |
| F-061 Line transitions | `POST /admin/orders/{order}/items/{item}/transition` |
| F-062 Internal note | `PATCH /admin/orders/{id}` |
| F-063 Delivery workflow | line transition endpoint |
| F-064 Pickup workflow | line transition endpoint |
| F-065 Return handling | line transition + refund endpoint (cash refusal: line transition to `cancelled`) |
| F-066 Admin cancel | `POST /admin/orders/{id}/cancel` / line transition |
| F-067 Dispatch estimate | derived during checkout/order response |
| F-068 Kill switch | admin setting + checkout 503 |
| F-069 Receipt confirmation / problem report | `POST /me/orders/{id}/confirm-receipt`, `POST /me/orders/{id}/report-problem` |

## 35.5 Refunds

| Feature | Endpoint |
|---|---|
| F-070 Per-line refund | `POST /admin/orders/{id}/refunds` |
| F-071 Removed (ADR-024) | — |
| F-072 Obligation tracking | `/admin/refunds*` |
| F-073 STL line leaves delivery queue on refund | refund transaction side effect |
| F-074 Pending queue | `GET /admin/refunds` (default `queue=true`: pending or owed) |

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
| F-113 Removed (ADR-024) | — |
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
| F-132 Captcha | Turnstile on register, resend verification, password-reset request, contact and Bring Your Idea (ADR-025); no backend captcha-management endpoint |
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
- marking delivered and refunding lock the order row, then the same line (ADR-024 lock order), so exactly one wins.

## Admin

- separate router;
- MFA;
- non-admin existence hiding;
- audit every mutation;
- least PII in logs.

## Payment Webhook

- IP allowlist when possible;
- only configured online providers routable (`cash` never, `mock` never in production);
- verification through the payment row's provider, never the URL;
- signature verification when provider supports it;
- unique provider event ID;
- immediate persistence;
- independent server-side verification before an STL is sent or an online order's goods are produced; cash orders never pass through the webhook.

---

# 37. Open External Details That Do Not Change Route Structure

The approved SRS still waits on payment-provider/client/operations details. These do not block the endpoint structure:

- which online provider: Whish, a card gateway, or both (SRS §30.4);
- provider signature mechanism;
- provider status-query capability;
- sandbox availability;
- exact transaction settlement/fees;
- actual courier partner;
- cash terms wording;
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
- [x] Delivery/pickup and payment method, including cash on delivery (ADR-024).
- [x] Normal checkout.
- [x] Order history/detail/cancellation.
- [x] Provider-neutral webhook/verification/reconciliation/manual fallback.
- [x] Cash handover, receipt confirmation and problem report (ADR-024).
- [x] Full/partial refund + obligations (no shipping, ADR-024).
- [x] STL delivery queue and delivery status (ADR-019).
- [x] Offer negotiation + checkout.
- [x] Reviews + moderation + verified badge.
- [x] Wishlist.
- [x] Notifications.
- [x] Bring Your Idea + private attachments + admin pipeline.
- [x] Contact queue.
- [x] Product/image admin.
- [x] Category/material/colour admin.
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
