# Backend response to the frontend unlock request

Answers every item in [`../frontend-requests/BACKEND-UNLOCK-HANDOFF.md`](../frontend-requests/BACKEND-UNLOCK-HANDOFF.md)
by its ID, in the field order of [`../frontend-requests/BACKEND-RESPONSE-TEMPLATE.md`](../frontend-requests/BACKEND-RESPONSE-TEMPLATE.md).

- **Backend state:** slices VS-001 to VS-016, VS-022 (cart), VS-026 (address book), VS-033 (contact form and captcha), VS-034 (Bring Your Idea submission), VS-035 (the admin Bring Your Idea pipeline, attachment download and funnel; [`../custom-requests.md`](../custom-requests.md#admin-pipeline-vs-035)), VS-038 (wishlist) and VS-046 (security retention) are built. Nothing else exists yet: no checkout, order, payment or refund route.
- **Schemas are not retyped here.** Field lists live in [`openapi.json`](openapi.json), generated from the code and checked by a test. A block names the schema; open it at `components.schemas.<Name>`.
- **Decisions since the first version:** three open questions were decided on 2026-10-14 and recorded in [ADR-025](../adr/ADR-025-frontend-contract-decisions.md): admin `available_actions` (C8, P1-11), the STL ownership check (C11) and Turnstile captcha on five forms (P2-1, P2-6, P2-7). Captcha is now built (VS-033, [ADR-026](../adr/ADR-026-captcha-refusal-and-outage.md)); the other two are provisional until their slices are built.
- **Every example below is real**, captured from the application running against a database filled by [`scripts/dev_seed.py`](../../scripts/dev_seed.py). IDs and timestamps will differ on your machine.

## Contents

1. [Shared conventions](#1-shared-conventions) — errors, cookies, CSRF, the admin boundary, rate limits
2. [Built and confirmed](#2-built-and-confirmed) — A1, A2, A3, B1, B2, B3, B4, B5, C1, C2, P1-1 to P1-7, P2-5, P2-6, P2-8, VS-036 (reviews)
3. [Removed by ADR-019 and ADR-024](#3-removed-by-adr-019-and-adr-024) — C4, C9, C10, P1-8, P1-9
4. [Not built yet (provisional)](#4-not-built-yet-provisional) — C5, C6, C7, C8, C11, C12, P1-10 to P1-13, P2-2; also P2-1, P2-3, P2-4 and P2-7, which VS-033 has since built, C3, which VS-026 has since built, and C5, which VS-022 has since built
5. [Test accounts and fixtures](#5-test-accounts-and-fixtures) — items 1 to 9
6. [Corrections to "confirmed" items in the request](#6-corrections-to-confirmed-items-in-the-request)
7. [Open questions](#7-open-questions) — three decided by ADR-025, ten still open

---

## 1. Shared conventions

These hold for every built route. Blocks below refer to them instead of repeating them.

### 1.1 Error body

Every non-2xx response is `application/problem+json` with exactly these members (schema `Problem`):

```json
{
  "type": "http://localhost:8000/problems/AUTH_REQUIRED",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid session is required for this request.",
  "instance": "/api/v1/me",
  "code": "AUTH_REQUIRED",
  "request_id": "req_daddf4f0bcb74ad79fb878febab0c0dd",
  "errors": []
}
```

- Branch on `code`. `title` and `detail` are diagnostic English text and may change.
- `type` is `<BASE_URL>/problems/<code>`. It is an identifier, not a page you can open.
- `errors` is always present. It is `[]` unless the error is about specific fields; see [C1](#domain--item-c1--rfc-9457-field-level-validation-error-shape).
- A few errors add one extra top-level member. Today the only one is `current_version` on `409 VERSION_CONFLICT`.
- `X-Request-ID` is on every response and equals `request_id`.

Errors any route can return: `400 MALFORMED_REQUEST` (body is not JSON), `422 VALIDATION_ERROR`, `429 RATE_LIMITED` (rate-limited routes), `500 INTERNAL_ERROR`, `503 SERVICE_UNAVAILABLE` (database or Redis down; safe to retry). `405 METHOD_NOT_ALLOWED` carries an `Allow` header.

### 1.2 Session cookies and CSRF

`POST /api/v1/auth/login` (or `POST /api/v1/auth/mfa/verify` for an administrator) sets three cookies. Captured:

```
Set-Cookie: access_token=<redacted>; HttpOnly; Max-Age=900; Path=/; SameSite=lax
Set-Cookie: refresh_token=<redacted>; HttpOnly; Max-Age=2592000; Path=/api/v1/auth; SameSite=lax
Set-Cookie: csrf_token=<redacted>; Max-Age=2592000; Path=/; SameSite=lax
```

- `access_token` and `refresh_token` are `HttpOnly`. `csrf_token` is readable by JavaScript on purpose.
- Every cookie-authenticated `POST`, `PUT`, `PATCH` or `DELETE` must send header **`X-CSRF-Token`** with the current `csrf_token` cookie value. `GET` never needs it. Missing or wrong: `403 CSRF_INVALID`.
- `POST /api/v1/auth/refresh` rotates all three cookies, so re-read `csrf_token` after a refresh.
- Cookies are `Secure` in every environment except `ENVIRONMENT=development`. Over plain `http` outside development the browser drops them.
- The API has **no CORS support**. The browser must call it same-origin through your proxy.

### 1.3 The admin boundary

Every path under `/api/v1/admin`, real or not, answers:

| Caller | Response |
|---|---|
| No session | `401 AUTH_REQUIRED` |
| Signed-in customer | `404 NOT_FOUND`, identical to a path that does not exist |
| Administrator whose MFA enrolment is not confirmed | `401 MFA_REQUIRED` |
| Administrator with MFA complete | the route's own answer |

All admin routes share one rate limit: 300 requests per 60 seconds per administrator.

### 1.4 Rate-limit headers

Rate-limited routes send `RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset` (whole seconds) on 2xx and 429 responses. A 429 also sends `Retry-After` in whole seconds, never an HTTP date. See [P2-8](#domain--item-p2-8--rate-limit-429-universality).

---

## 2. Built and confirmed

### Domain / item: A1 — OpenAPI / schema source

**Status:** built.

**Confirmed endpoint:**
`GET /openapi.json` on the running backend (`http://localhost:8000/openapi.json`; it is not under `/api`). Swagger UI is at `GET /docs`.

**Request schema:** none.

**Response schema:** an OpenAPI 3.1 document. A snapshot is committed at [`openapi.json`](openapi.json): 57 operations, 80 schemas.

**Enums/statuses/actions:** every enum is in the document as `components.schemas.<Name>.enum`: `ProductType`, `PurchaseMode`, `UserRole`, `NotificationType`, `SettingType`. No response has an "available actions" list today.

**Errors:** none specific.

**Auth/CSRF/MFA:** public.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** the file itself.

**Example error JSON:** not applicable.

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json). `tests/unit/test_openapi_snapshot.py` fails when the file and the code disagree, so the file is never stale on `main`. Regenerate with `python scripts/export_openapi.py`.

**Notes:**
- The document covers only what is built. Anything in section 3 or 4 of this file is not in it.
- Each operation carries `security`: `sessionCookie` for an authenticated read, `sessionCookie` plus `csrfToken` for an authenticated write, nothing for a public route.
- Every 4xx and 5xx response points at schema `Problem`. The `HTTPValidationError` and `ValidationError` schemas are FastAPI leftovers and are never returned.
- `Problem.errors` is typed loosely as an array of objects. Its real shape is in [C1](#domain--item-c1--rfc-9457-field-level-validation-error-shape).
- A generated client is safe to build from this file: request schemas reject unknown fields.

### Domain / item: A2 — Local backend startup

**Status:** built.

**Confirmed endpoint:**
`GET /health/live` and `GET /health/ready` (outside `/api/v1`).

**Request schema:** none.

**Response schema:** see `openapi.json`: `LivenessRead`, `ReadinessRead`.

**Enums/statuses/actions:** `status` is always `"ok"`; a failing readiness check is a `503` problem, not a different status value.

**Errors:**
- `503 SERVICE_UNAVAILABLE` — Postgres or Redis unreachable — the shared problem body.

**Auth/CSRF/MFA:** public.

**Concurrency/idempotency:** not applicable.

**Example success JSON:**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "commit": "unknown"
}
```

**Example error JSON:** the shared problem body with `"status": 503, "code": "SERVICE_UNAVAILABLE"`.

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** [`../../README.md`](../../README.md) "Getting Started", [`../../docker-compose.yml`](../../docker-compose.yml).

**Notes:** how to start everything, from the repository root:

```sh
cp .env.example .env            # then replace every placeholder secret; see below
docker compose up -d --build    # postgres, redis, clamav, api, worker
docker compose exec api alembic upgrade head
docker compose run --rm -T -e PYTHONPATH=src api python - < scripts/dev_seed.py
curl http://localhost:8000/health/ready
```

- **Secrets.** `.env` is git-ignored. Every `generate_with__...` and `change_me...` value in `.env.example` must be replaced with a value you generate locally, for example `python -c "import secrets; print(secrets.token_hex(32))"`. If you change `POSTGRES_PASSWORD`, change it inside `DATABASE_URL` too. Never commit `.env` or paste its values anywhere.
- **Ports on the host:** API `8000`, Postgres `5442` (not 5432), Redis `6379`, ClamAV `3310`.
- **Migrations** are the `alembic upgrade head` line. Run it again after every `git pull`.
- **Seed** is the `dev_seed.py` line; details in [A3](#domain--item-a3--test-account-and-fixture-provisioning).
  The script is piped into the container because the image does not contain `scripts/`. In PowerShell, which has no `<`, use `Get-Content scripts/dev_seed.py | docker compose run --rm -T -e PYTHONPATH=src api python -`. Options go after the dash: `python - --rotate-credentials`.
- **ClamAV** downloads virus definitions on first start and can take a few minutes. Until it is healthy, image upload answers `503`. Nothing else depends on it.
- **CORS:** none, and none is needed while the browser only calls your own origin. Your two proxy rewrites are right: `/api/health/*` to `/health/*`, and `/api/v1/*` unchanged. Add a third for images, see [B4](#domain--item-b4--imageasset-url-format).
- **Postman or curl straight at `:8000`** works without CORS, because CORS is a browser rule. You must keep the cookies from login and send `X-CSRF-Token` yourself on writes.
- **Trailing slashes:** never send one. `/api/v1/products/` answers `307`.
- `ENVIRONMENT` must stay `development` locally, or the cookies become `Secure` and are dropped over `http`.

### Domain / item: A3 — Test account and fixture provisioning

**Status:** built (seed script and SQL workaround). The file-based email adapter is not built.

**Confirmed endpoint:** none; this is tooling.

**Request schema:** not applicable.

**Response schema:** not applicable.

**Enums/statuses/actions:** not applicable.

**Errors:** the seed script exits with `dev_seed refuses to run with ENVIRONMENT=...` unless `ENVIRONMENT` is `development` or `test`.

**Auth/CSRF/MFA:** not applicable.

**Concurrency/idempotency:** the seed is safe to run again. It adds only what is missing and never changes an existing account, product or reference value.

**Example success JSON:** not applicable. The script prints, once:

```
Accounts: seed-admin@example.com (administrator, MFA enrolled) and seed-customer@example.com
  admin password        <generated>
  admin TOTP secret     <generated>
  admin otpauth URI     <generated>
  admin recovery codes  <ten generated codes>
  customer password     <generated>
Shown once: keep these in a password manager, never in a tracked file.
Created 11 products and 12 images.
```

**Example error JSON:** not applicable.

**Fixture/test account:** this block is the fixture.

**Authoritative source/OpenAPI file:** [`../../scripts/dev_seed.py`](../../scripts/dev_seed.py), tested by `tests/integration/test_dev_seed.py`.

**Notes:**

*(a) Reading emails locally.* The file-based email adapter is **not built**; it is still only a proposal ([`../frontend-contract-vs002.md`](../frontend-contract-vs002.md) section 7.4). The `email_outbox` SQL read stays the accepted workaround:

```sh
docker compose stop worker      # the worker redacts the token once it "sends"
docker compose exec -T postgres psql -U bekaa3d -d bekaa3d -Atc \
  "select payload->>'verification_url' from email_outbox
   where recipient_email = 'you@example.com' and template = 'verification_email'
   order by created_at desc limit 1"
```

- For a password reset use `template = 'password_reset_email'` and `payload->>'reset_url'`.
- Links are `<FRONTEND_BASE_URL>/verify-email#token=...` and `<FRONTEND_BASE_URL>/reset-password#token=...`. The token is in the URL **fragment**, so it never reaches a server; read it with `location.hash`.
- The console email adapter logs only the names of the payload fields, never the token. The repository README still says the log contains the token; that sentence is out of date.
- For most testing you can skip email entirely: the seeded customer is already verified.

*(b) Administrator with MFA.* The seed creates `seed-admin@example.com` with TOTP already enabled, the same state `/auth/mfa/setup/confirm` produces.

- Add the printed TOTP secret (or the `otpauth://` URI) to an authenticator app. In an automated test, compute the code from the secret with any TOTP library (30-second step, 6 digits, SHA-1).
- **Each TOTP code works once.** Two admin logins inside the same 30-second step need two different codes; the second login with the same code gets `401 MFA_INVALID`. Wait for the next step, or use a recovery code.
- Each recovery code also works once.
- Lost the credentials? Run the seed with `--rotate-credentials` (`... api python - --rotate-credentials < scripts/dev_seed.py`). It issues new passwords, a new TOTP secret and new recovery codes for both seed accounts and ends their sessions.
- Put the credentials in your own git-ignored file (for example the frontend's `.env.local`) or a password manager. Never in a tracked file.

*(c) What the seed creates.*

| What | Detail |
|---|---|
| Administrator | `seed-admin@example.com`, verified, MFA enabled |
| Customer | `seed-customer@example.com`, verified, with two unread notifications |
| Categories | `home-decor`, `toys-figures`, `tools-gadgets`, and `seasonal` (disabled, so it is hidden) |
| Materials, colours | PLA, PETG, Resin; Black, White, Red |
| Physical products | `moon-lamp` (featured), `geometric-planter`, `dragon` (two images), `cable-organizer` (online only), `name-sign` (WhatsApp only), `knight` (unavailable) |
| STL products | `dragon-stl`, `phone-stand-stl` (featured), `low-poly-vase-stl` (unavailable) |
| Never on the storefront | `prototype-gear` (hidden), `holiday-ornament` (disabled category); both answer `404` publicly |
| Settings | `accepting_orders` set to `true`; `whatsapp_number` only when you pass `--whatsapp-number +961...` |

*(d) Rate limits in automated tests.* Registration allows 5 per hour per IP. Clear the counters between tests:

```sh
docker compose exec -T redis sh -c "redis-cli --scan --pattern 'ratelimit:*' | xargs -r redis-cli DEL"
```

Never `FLUSHALL`: the same Redis holds MFA challenges and the job queue.

### Domain / item: B1 — Public settings response shape

**Status:** built. One field is about to be removed, see Notes.

**Confirmed endpoint:**
`GET /api/v1/settings/public`

**Request schema:** none.

**Response schema:** see `openapi.json`: `PublicSettingsRead`. It is a **flat object** with a fixed set of keys, not a `{key, value}[]` list. Every key is always present; a value that is not configured is `null`.

**Enums/statuses/actions:** none.

**Errors:**
- `429 RATE_LIMITED` — more than 600 requests per hour from one IP.

**Auth/CSRF/MFA:** public.

**Concurrency/idempotency:** not applicable (read-only).

**Example success JSON:**

```json
{
  "accepting_orders": true,
  "cash_payment_enabled": true,
  "cash_max_order_total": { "amount_cents": 10000, "currency": "USD" },
  "pickup_address": null,
  "pickup_hours": null,
  "whatsapp_number": "+96170000000"
}
```

**Example error JSON:** the shared problem body with `"status": 429, "code": "RATE_LIMITED"`.

**Fixture/test account:** the seed sets `accepting_orders`; pass `--whatsapp-number` to set the number, or `PATCH /api/v1/admin/settings/whatsapp_number` as the seed administrator.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); rules in [`../settings-registry.md`](../settings-registry.md).

**Notes:** the three names you asked for:

| You asked for | Field | Type |
|---|---|---|
| WhatsApp business number | `whatsapp_number` | E.164 string such as `"+96170000000"`, or `null` |
| Kill switch | `accepting_orders` | boolean; `false` means checkout will answer `503 ORDERS_PAUSED` |
| Free-shipping threshold | — | **removed on 2026-10-20**, see below |

- There is no "message" setting for WhatsApp. The frontend builds the `wa.me` link and any prefilled text itself.
- **2026-10-20 (VS-028 PR A): `free_shipping_threshold` removed** from `GET /api/v1/settings/public` and from the admin settings (its `GET`/`PATCH /api/v1/admin/settings/free_shipping_threshold` now answer `404`). `cash_payment_enabled` (bool) and `cash_max_order_total` (`{amount_cents, currency}`, never `null`) added. Remove any read of the old field. ADR-024 removed all shipping charges, so there is no threshold.
- `cash_payment_enabled` and `cash_max_order_total` are live in the response, and checkout honours them since VS-028 PR B (2026-10-22, [C6](#domain--item-c6--checkout-contract)): hide or disable cash when the switch is off or the cart total is above the maximum.
- `pickup_address` and `pickup_hours` are strings or `null`. Hide the element when `null`.
- The home page can read this on every load today; cache headers arrive with VS-020.

### Domain / item: B2 — Catalogue public list contract

**Status:** built.

**Confirmed endpoint:**
`GET /api/v1/products`

**Request schema:** query parameters, all optional; exact types in `openapi.json` under `paths./api/v1/products.get.parameters`.

| Parameter | Meaning |
|---|---|
| `type` | `physical` or `stl` |
| `category_id`, `material_id`, `colour_id` | a UUID each, from `GET /api/v1/categories`, `/materials`, `/colours` |
| `price_min_cents`, `price_max_cents` | integer cents, inclusive |
| `min_rating` | 0 to 5, at most two decimals |
| `featured` | `true` or `false` |
| `q` | search text, at most 200 characters; blank means no search |
| `sort` | `-created_at` (default), `price`, `-price`, `-average_rating`; with `q` also `-relevance` (the default then) |
| `cursor`, `limit` | see [C2](#domain--item-c2--cursor-pagination-response-shape) |

**Response schema:** see `openapi.json`: `ProductPage`, whose `items` are `ProductListItem`.

**Enums/statuses/actions:** `type`: `"physical" | "stl"`. `purchase_mode`: `"online_only" | "whatsapp_only" | "both"`, and `null` for every STL product. No "available actions" list on a list item; the detail response has `capabilities` ([B3](#domain--item-b3--product-detail-contract)).

**Errors:**
- `422 VALIDATION_ERROR` — a bad value for any parameter, including a tampered cursor — `errors[].loc` is `["query", "<parameter>"]`.
- `429 RATE_LIMITED` — more than 600 requests per hour from one IP.

**Auth/CSRF/MFA:** public.

**Concurrency/idempotency:** not applicable (read-only).

**Example success JSON:** `GET /api/v1/products?type=physical&category_id=<toys-figures id>&limit=1`

```json
{
  "items": [
    {
      "id": "bfe73498-21a9-4bc2-bda6-44fdd8a90962",
      "type": "physical",
      "name": "Articulated Dragon",
      "slug": "dragon",
      "cover_image": {
        "id": "e8fbdad8-af60-4a33-8772-77b1d96360aa",
        "url": "/media/products/b7b56621-1fc1-4bed-ba3e-ff9f8ca089d4.png",
        "alt_text": "Articulated Dragon, view 1",
        "is_cover": true
      },
      "price": {
        "amount_cents": 1800,
        "currency": "USD"
      },
      "category": {
        "id": "b0440ac7-ff53-432b-84a5-4e31cbcb8cd3",
        "name": "Toys and Figures",
        "slug": "toys-figures"
      },
      "material": {
        "id": "86f2d315-41be-491d-8a3e-09a599237ffe",
        "name": "PLA"
      },
      "colour": {
        "id": "7aeecf3f-50a6-488b-b0e1-3739df5b2ae3",
        "name": "Red"
      },
      "is_available": true,
      "purchase_mode": "both",
      "average_rating": 0.0,
      "review_count": 0,
      "is_featured": false
    }
  ],
  "next_cursor": "eyJzIjoiLWNyZWF0ZWRfYXQiLCJrIjoiMjAyNi0xMC0xMlQxODowNDoyNy42NjU5NzgrMDA6MDAiLCJpIjoiYmZlNzM0OTgtMjFhOS00YmMyLWJkYTYtNDRmZGQ4YTkwOTYyIn0"
}
```

**Example error JSON:** `GET /api/v1/products?sort=bogus`

```json
{
  "type": "http://localhost:8000/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/products",
  "code": "VALIDATION_ERROR",
  "request_id": "req_ee2e023e677241ed879f6f0ad3d1db19",
  "errors": [
    {
      "loc": [
        "query",
        "sort"
      ],
      "msg": "Input should be 'price', '-price', '-average_rating', '-created_at' or '-relevance'",
      "type": "literal_error"
    }
  ]
}
```

**Fixture/test account:** the seeded catalogue: 9 visible products across 3 categories, 3 materials, 3 colours and both types.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); behaviour in [`../storefront-catalogue.md`](../storefront-catalogue.md).

**Notes:**
- **Wire names differ from your URL keys.** Your URL uses `category`, `material`, `colour`; the API takes `category_id`, `material_id`, `colour_id`, and they are UUIDs, not names or slugs. Map your URL value to an id through the three reference lists. Unknown parameters are ignored silently, so `?category=...` returns the unfiltered list rather than an error.
- **One value per facet.** There is no multi-value filter. `category_id=a,b` is a `422`. A repeated parameter (`category_id=a&category_id=b`) is not an error but only the last value is used. Facets combine with AND.
- STL products have no material or colour, so filtering by either returns physical products only.
- A product is listed only when it is visible, not deleted, and its category is active. Unavailable products stay listed with `is_available: false`.
- `average_rating` and `review_count` are live since VS-036: exact over visible reviews (hidden and deleted ones excluded), updated on every review create, edit and delete. See [Reviews](#domain--item-vs-036--reviews-and-the-verified-purchase-badge).
- Reference lists for the filter panel: `GET /api/v1/categories` (`{items: [{id, name, slug}]}`), `GET /api/v1/materials` and `GET /api/v1/colours` (`{items: [{id, name}]}`). At most 100 rows each, no pagination.

### Domain / item: B3 — Product detail contract

**Status:** built.

**Confirmed endpoint:**
`GET /api/v1/products/{slug}`

**Request schema:** `slug` path parameter: the product's current lowercase slug, exactly as returned by the list.

**Response schema:** see `openapi.json`: `ProductDetail` (every `ProductListItem` field plus `description`, `images`, the SEO fields, `dimensions`, `production_lead_time_days`, `batch_size`, `max_quantity_per_line`, `capabilities`).

**Enums/statuses/actions:** same enums as B2. **Machine-readable actions: yes**, field `capabilities`:

| Flag | True when |
|---|---|
| `can_add_to_cart` | the product is available, and is STL or has `purchase_mode` `online_only` or `both` |
| `can_offer` | STL and available |
| `whatsapp_available` | physical with `purchase_mode` `whatsapp_only` or `both` |

**Errors:**
- `404 NOT_FOUND` — no visible product has this slug (hidden, deleted, disabled category, old slug after a rename, or wrong case).
- `429 RATE_LIMITED` — more than 600 requests per hour from one IP.

**Auth/CSRF/MFA:** public. A session cookie changes nothing.

**Concurrency/idempotency:** not applicable (read-only).

**Example success JSON:** a physical product, `GET /api/v1/products/dragon`

```json
{
  "id": "bfe73498-21a9-4bc2-bda6-44fdd8a90962",
  "type": "physical",
  "name": "Articulated Dragon",
  "slug": "dragon",
  "cover_image": {
    "id": "e8fbdad8-af60-4a33-8772-77b1d96360aa",
    "url": "/media/products/b7b56621-1fc1-4bed-ba3e-ff9f8ca089d4.png",
    "alt_text": "Articulated Dragon, view 1",
    "is_cover": true
  },
  "price": {
    "amount_cents": 1800,
    "currency": "USD"
  },
  "category": {
    "id": "b0440ac7-ff53-432b-84a5-4e31cbcb8cd3",
    "name": "Toys and Figures",
    "slug": "toys-figures"
  },
  "material": {
    "id": "86f2d315-41be-491d-8a3e-09a599237ffe",
    "name": "PLA"
  },
  "colour": {
    "id": "7aeecf3f-50a6-488b-b0e1-3739df5b2ae3",
    "name": "Red"
  },
  "is_available": true,
  "purchase_mode": "both",
  "average_rating": 0.0,
  "review_count": 0,
  "is_featured": false,
  "description": "Articulated Dragon: seeded by scripts/dev_seed.py for local testing.",
  "images": [
    {
      "id": "e8fbdad8-af60-4a33-8772-77b1d96360aa",
      "url": "/media/products/b7b56621-1fc1-4bed-ba3e-ff9f8ca089d4.png",
      "alt_text": "Articulated Dragon, view 1",
      "is_cover": true
    },
    {
      "id": "93c25d4d-eae7-4c8b-9cc0-07dfcb9d1a1c",
      "url": "/media/products/65cac7df-4e3b-4e8e-ac66-4453af11e561.png",
      "alt_text": "Articulated Dragon, view 2",
      "is_cover": false
    }
  ],
  "seo_title": null,
  "seo_description": null,
  "og_image_url": null,
  "dimensions": {
    "length_mm": 120,
    "width_mm": 80,
    "height_mm": 60
  },
  "production_lead_time_days": 2,
  "batch_size": 2,
  "max_quantity_per_line": 5,
  "capabilities": {
    "can_add_to_cart": true,
    "can_offer": false,
    "whatsapp_available": true
  }
}
```

An STL product, `GET /api/v1/products/dragon-stl`

```json
{
  "id": "d2350ee4-c868-4fbe-a85e-ca3bb3109b42",
  "type": "stl",
  "name": "Articulated Dragon STL",
  "slug": "dragon-stl",
  "cover_image": {
    "id": "151c3b59-75ae-4034-bd15-c5924a318bb5",
    "url": "/media/products/ee1ed304-51a3-43d1-a57a-a0660b3c74a4.png",
    "alt_text": "Articulated Dragon STL, view 1",
    "is_cover": true
  },
  "price": {
    "amount_cents": 700,
    "currency": "USD"
  },
  "category": {
    "id": "b0440ac7-ff53-432b-84a5-4e31cbcb8cd3",
    "name": "Toys and Figures",
    "slug": "toys-figures"
  },
  "material": null,
  "colour": null,
  "is_available": true,
  "purchase_mode": null,
  "average_rating": 0.0,
  "review_count": 0,
  "is_featured": false,
  "description": "Articulated Dragon STL: seeded by scripts/dev_seed.py for local testing.",
  "images": [
    {
      "id": "151c3b59-75ae-4034-bd15-c5924a318bb5",
      "url": "/media/products/ee1ed304-51a3-43d1-a57a-a0660b3c74a4.png",
      "alt_text": "Articulated Dragon STL, view 1",
      "is_cover": true
    }
  ],
  "seo_title": null,
  "seo_description": null,
  "og_image_url": null,
  "dimensions": null,
  "production_lead_time_days": null,
  "batch_size": null,
  "max_quantity_per_line": null,
  "capabilities": {
    "can_add_to_cart": true,
    "can_offer": true,
    "whatsapp_available": false
  }
}
```

**Example error JSON:** `GET /api/v1/products/prototype-gear` (a hidden product)

```json
{
  "type": "http://localhost:8000/problems/NOT_FOUND",
  "title": "Request cannot be completed",
  "status": 404,
  "detail": "Not Found",
  "instance": "/api/v1/products/prototype-gear",
  "code": "NOT_FOUND",
  "request_id": "req_efb83907c6154688a343b5cedc33d8e5",
  "errors": []
}
```

**Fixture/test account:** seeded slugs: `dragon` (two images), `name-sign` (WhatsApp only), `knight` and `low-poly-vase-stl` (unavailable), `dragon-stl`.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../storefront-catalogue.md`](../storefront-catalogue.md); ADR-022.

**Notes:**
- **No stock.** Products are made to order; there is no quantity in stock anywhere. Availability is the single boolean `is_available`.
- **No "owned" indicator here.** This endpoint is anonymous and cacheable, so it cannot know who is asking. A signed-in customer's ownership comes from a separate endpoint, decided in [ADR-025](../adr/ADR-025-frontend-contract-decisions.md) and built in VS-023; see [C11](#domain--item-c11--per-product-ownership-check).
- `material`, `colour`, `dimensions`, `production_lead_time_days`, `batch_size`, `max_quantity_per_line` and `purchase_mode` are `null` on every STL product.
- `max_quantity_per_line` is the cart quantity cap for a physical product. An STL is always quantity 1.
- STL pages have no delivery-time field. The file is emailed by the administrator after payment (ADR-019); the promise text is an open business decision.
- Never exposed: `is_visible`, `version`, `wishlist_count`, `weight_grams`, timestamps.

### Domain / item: B4 — Image/asset URL format

**Status:** built, with one gap in local development (Notes).

**Confirmed endpoint:** none of its own. Image URLs arrive inside `cover_image` and `images` of B2 and B3, and inside `images` of the admin product reads.

**Request schema:** not applicable.

**Response schema:** see `openapi.json`: `PublicImage` (`id`, `url`, `alt_text`, `is_cover`) and `ProductImageRead` (admin).

**Enums/statuses/actions:** none.

**Errors:** none.

**Auth/CSRF/MFA:** images are public.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** from `GET /api/v1/products/dragon`:

```json
{
  "id": "e8fbdad8-af60-4a33-8772-77b1d96360aa",
  "url": "/media/products/b7b56621-1fc1-4bed-ba3e-ff9f8ca089d4.png",
  "alt_text": "Articulated Dragon, view 1",
  "is_cover": true
}
```

**Example error JSON:** not applicable.

**Fixture/test account:** every seeded visible product has a cover image; `dragon` has two.

**Authoritative source/OpenAPI file:** [`../product-images.md`](../product-images.md), ADR-021.

**Notes:**
- `url` is **ready to use**: a root-relative path such as `/media/products/<uuid>.png`. Put it straight into `src`. Do not build it from parts and do not parse it.
- The same shape holds in development, staging and production. The `/media` prefix is a deployment setting, so treat the whole string as opaque.
- Extensions are `.jpg`, `.png` or `.webp`. Uploads are re-encoded, so the file never changes after upload and can be cached hard.
- The API returns one size per image. There are no thumbnails or `srcset` variants.
- **Gap today:** nothing serves `/media` in local development. In production nginx will, and nginx arrives with VS-020. The API process itself does not serve files, so `http://localhost:8000/media/...` is a `404`. The files are on disk in the backend checkout under `storage/media_public/`. Until VS-020, serve that folder yourself and proxy `/media/*` to it, for example `npx serve storage/media_public -l 8001` plus a rewrite from `/media/:path*` to `http://localhost:8001/:path*`.
- `alt_text` can be `null`. Fall back to the product name.

### Domain / item: B5 — Search-suggestions endpoint

**Status:** built.

**Confirmed endpoint:**
`GET /api/v1/search/suggestions`

**Request schema:**
- `q`: string, required, 3 to 200 characters after trimming, containing a word of at least 3 letters or digits.
- `limit`: integer, optional, 1 to 10, default 10.

**Response schema:** see `openapi.json`: `SearchSuggestionList` (`items` of `SearchSuggestionRead`: `id`, `name`, `slug`, `type`).

**Enums/statuses/actions:** `type`: `"physical" | "stl"`.

**Errors:**
- `422 VALIDATION_ERROR` — `q` missing or too short, or `limit` out of range.
- `429 RATE_LIMITED` — more than 3,000 requests per hour from one IP.

**Auth/CSRF/MFA:** public.

**Concurrency/idempotency:** not applicable (read-only).

**Example success JSON:** `GET /api/v1/search/suggestions?q=drag`

```json
{
  "items": [
    {
      "id": "bfe73498-21a9-4bc2-bda6-44fdd8a90962",
      "name": "Articulated Dragon",
      "slug": "dragon",
      "type": "physical"
    },
    {
      "id": "d2350ee4-c868-4fbe-a85e-ca3bb3109b42",
      "name": "Articulated Dragon STL",
      "slug": "dragon-stl",
      "type": "stl"
    }
  ]
}
```

**Example error JSON:** `GET /api/v1/search/suggestions?q=dr`

```json
{
  "type": "http://localhost:8000/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/search/suggestions",
  "code": "VALIDATION_ERROR",
  "request_id": "req_4854ebbbd78b46fdbf5c40c704491e2a",
  "errors": [
    {
      "loc": [
        "query",
        "q"
      ],
      "msg": "must be 3 to 200 characters",
      "type": "value_error"
    }
  ]
}
```

**Fixture/test account:** the seeded catalogue.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../storefront-catalogue.md`](../storefront-catalogue.md); ADR-023.

**Notes:**
- **Debounce about 300 ms** after the last keystroke, and drop a response that arrives after a newer request was sent.
- **Send nothing until the term has 3 characters.** Shorter terms are a `422` and still count against the rate limit.
- Suggestions tolerate one typo (`dragn` finds "Articulated Dragon"). Link a suggestion to `/products/{slug}`.
- Full search is not a separate endpoint: it is `GET /api/v1/products?q=...` (B2).

### Domain / item: C1 — RFC 9457 field-level validation-error shape

**Status:** built.

**Confirmed endpoint:** every route. Shown here on `POST /api/v1/auth/register`.

**Request schema:** not applicable.

**Response schema:** schema `Problem` (section 1.1). For a `422 VALIDATION_ERROR`, `errors` is an array with one entry per failed field, each with exactly three keys:

- `loc`: array. The first element is where the value came from, `"body"`, `"query"` or `"path"`; the rest is the path to the field, for example `["body", "price", "amount_cents"]`.
- `msg`: English diagnostic text. Do not show it to users and do not match on it.
- `type`: a machine-readable reason such as `missing`, `string_too_short`, `extra_forbidden`, `uuid_parsing`, `literal_error`, `value_error`.

This is Pydantic's `loc`/`msg`/`type` passed through. Pydantic's `input`, `ctx` and `url` are removed. It is **not** a `field`/`message` pair.

**Enums/statuses/actions:** `type` is an open set (Pydantic's error types plus `value_error` for the API's own rules). Map the few you care about and fall back to a generic message.

**Errors:**
- `422 VALIDATION_ERROR` — a field is missing, wrong, or not allowed.
- `400 MALFORMED_REQUEST` — the body is not JSON at all; `errors` has one entry of `type: "json_invalid"`.

**Auth/CSRF/MFA:** not applicable.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** not applicable.

**Example error JSON:** two bad fields:

```json
{
  "type": "http://localhost:8000/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_6fcfc5145d89430897a9995f3bfaa74d",
  "errors": [
    {
      "loc": [
        "body",
        "email"
      ],
      "msg": "value is not a valid email address: An email address must have an @-sign.",
      "type": "value_error"
    },
    {
      "loc": [
        "body",
        "password"
      ],
      "msg": "String should have at least 8 characters",
      "type": "string_too_short"
    }
  ]
}
```

An unknown field (every request schema forbids them):

```json
{
  "type": "http://localhost:8000/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_bbf6da9d9fb0477e9415c68b715f798f",
  "errors": [
    {
      "loc": [
        "body",
        "captcha_token"
      ],
      "msg": "Extra inputs are not permitted",
      "type": "extra_forbidden"
    }
  ]
}
```

A body that is not JSON:

```json
{
  "type": "http://localhost:8000/problems/MALFORMED_REQUEST",
  "title": "Request body could not be parsed",
  "status": 400,
  "detail": "The request body is not valid JSON.",
  "instance": "/api/v1/auth/register",
  "code": "MALFORMED_REQUEST",
  "request_id": "req_e6ff49ff23f447ed899af933851f35d4",
  "errors": [
    {
      "loc": [
        "body",
        1
      ],
      "msg": "JSON decode error",
      "type": "json_invalid"
    }
  ]
}
```

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** `src/app/api/errors.py`; pinned by `tests/unit/test_error_contract.py`.

**Notes:**
- To attach an error to a form field, drop `loc[0]` and join the rest.
- `title` reads "Request body failed validation" even when the bad value was a query parameter. Trust `loc`, not `title`.
- Business-rule errors use their own `code` and usually have `errors: []`, with the explanation in `detail`. `422 SETTING_INVALID` is one of these. Some name the field anyway, in the same `loc`/`msg`/`type` shape: product type rules (`VALIDATION_ERROR`) and `UPLOAD_REJECTED` (`["body", "file"]`).
- Validation failures on rate-limited routes still consume the rate limit. Validate on the client first.

### Domain / item: C2 — Cursor pagination response shape

**Status:** built, and the same on every paginated route.

**Confirmed endpoint:** `GET /api/v1/products`, `GET /api/v1/me/notifications`, and the admin lists (`/admin/products`, `/admin/users`, `/admin/categories`, `/admin/materials`, `/admin/colours`, `/admin/settings`, `/admin/audit-logs`).

**Request schema:**
- `cursor`: string, optional. Omit it for the first page.
- `limit`: integer, optional, 1 to 100, default 20.

**Response schema:** always `{ "items": [...], "next_cursor": string | null }`. Both keys are always present. See any `*Page` schema in `openapi.json`.

**Enums/statuses/actions:** none.

**Errors:**
- `422 VALIDATION_ERROR` with `loc: ["query", "cursor"]` — the cursor is malformed, altered, or was issued for a different `sort` (or for a search when you are not searching, and the reverse).
- `422 VALIDATION_ERROR` with `loc: ["query", "limit"]` — `limit` outside 1 to 100.

**Auth/CSRF/MFA:** as the route.

**Concurrency/idempotency:** rows added, removed or hidden between two page fetches never make an existing row repeat or disappear. A row whose own sort value changes mid-walk (a price edit while sorting by price) can be seen twice or missed.

**Example success JSON:** `GET /api/v1/me/notifications?limit=1`

```json
{
  "items": [
    {
      "id": "f37a4558-0ef1-44bc-adb4-ff99d0c3584a",
      "type": "account",
      "payload": {
        "event": "account.seed_welcome",
        "message": "Created by scripts/dev_seed.py."
      },
      "read": false,
      "created_at": "2026-10-12T18:04:27.665978Z"
    }
  ],
  "next_cursor": "MjAyNi0xMC0xMlQxODowNDoyNy42NjU5NzgrMDA6MDB8ZjM3YTQ1NTgtMGVmMS00NGJjLWFkYjQtZmY5OWQwYzM1ODRh"
}
```

**Example error JSON:** `GET /api/v1/products?cursor=abc`

```json
{
  "type": "http://localhost:8000/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/products",
  "code": "VALIDATION_ERROR",
  "request_id": "req_a4eaa688f84b4991b671bc699cdb0bf0",
  "errors": [
    {
      "loc": [
        "query",
        "cursor"
      ],
      "msg": "cursor is not a valid pagination cursor",
      "type": "value_error"
    }
  ]
}
```

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../requirments/api-endpoints.md`](../requirments/api-endpoints.md) section 2.1.

**Notes:**
- **There is no `has_more` field.** `next_cursor: null` means this was the last page.
- **The cursor is opaque.** It happens to be base64, but its contents are not a contract. Send it back unchanged and never build one.
- Keep `sort`, `q` and the filters identical while paging; start again from the first page when any of them changes.
- There is no total count and no page number, so "Load more" works and "Page 3 of 9" cannot.
- The public reference lists (`/categories`, `/materials`, `/colours`) are not paginated: `{items}` only, at most 100 rows.

### Domain / item: P1-1 — Admin authorization source

**Status:** built.

**Confirmed endpoint:**
`GET /api/v1/me` (and the body of `POST /api/v1/auth/login`)

**Request schema:** none.

**Response schema:** see `openapi.json`: `UserProfileRead` for `/me`, `SessionRead` for a `200` login. Both have `role`.

**Enums/statuses/actions:** `role`: `"customer" | "admin"`. There is no "available actions" list and no MFA field.

**Errors:**
- `401 AUTH_REQUIRED` — no valid session.

**Auth/CSRF/MFA:** session cookie; no CSRF (GET).

**Concurrency/idempotency:** not applicable (read-only).

**Example success JSON:** `GET /api/v1/me` as the seeded administrator

```json
{
  "id": "f6393058-1d2f-4856-a859-cd143016d77d",
  "email": "seed-admin@example.com",
  "role": "admin",
  "email_verified": true,
  "email_verified_at": "2026-10-12T18:04:27.678647Z",
  "created_at": "2026-10-12T18:04:27.665978Z"
}
```

**Example error JSON:**

```json
{
  "type": "http://localhost:8000/problems/AUTH_REQUIRED",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid session is required for this request.",
  "instance": "/api/v1/me",
  "code": "AUTH_REQUIRED",
  "request_id": "req_daddf4f0bcb74ad79fb878febab0c0dd",
  "errors": []
}
```

**Fixture/test account:** `seed-admin@example.com` and `seed-customer@example.com`.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../admin-mfa.md`](../admin-mfa.md); ADR-017.

**Notes:** this is how `AdminProtectedRoute` should decide.

1. **Is the user an administrator?** `role === "admin"` from `GET /api/v1/me`. That is the only source. The tokens are `HttpOnly`, so there is no claim to read.
2. **Is MFA complete for this session?** No response field says so. You do not need one, because login is gated: an administrator with MFA enabled never receives a session from `/auth/login`, only a `202` challenge, and the session created by `/auth/mfa/verify` is already MFA-complete. So for an enrolled administrator, *having a session at all* means MFA is complete.
3. **The one exception** is an administrator who has not finished enrolling. They get an ordinary `200` session, `/me` says `admin`, and every `/api/v1/admin/*` call answers `401` with `code: "MFA_REQUIRED"`. Treat that code, from any admin call, as "send this user to MFA setup" ([P1-2](#domain--item-p1-2--admin-mfa-contract)).

Suggested guard: fetch `/me`; if not signed in, go to login; if `role !== "admin"`, show your normal not-found page; otherwise render, and handle `401 MFA_REQUIRED` globally in the API client. A cheap call to test the boundary is `GET /api/v1/admin/settings?limit=1`.

- The frontend guard is only for user experience. The backend enforces the boundary on every request (section 1.3), and a customer gets `404` from every admin path.
- If the frontend would rather have an explicit `mfa_completed` boolean on `/me`, ask for it. It is a small backend change that has not been requested or built.

### Domain / item: P1-2 — Admin MFA contract

**Status:** built.

**Confirmed endpoint:**
- `POST /api/v1/auth/mfa/verify` — finish an administrator login
- `POST /api/v1/auth/mfa/setup` — begin enrolment
- `POST /api/v1/auth/mfa/setup/confirm` — finish enrolment
- `POST /api/v1/auth/mfa/recovery-codes/regenerate`

**Request schema:** see `openapi.json`: `MfaVerifyRequest` (send `challenge_id` and **exactly one** of `code` or `recovery_code`), `MfaSetupRequest`, `MfaSetupConfirmRequest`, `MfaRecoveryRegenerateRequest`.

**Response schema:** see `openapi.json`: `verify` is `204` with the three cookies and no body; `MfaSetupRead`; `MfaRecoveryCodesRead` for both `confirm` and `regenerate`. The login challenge is `MfaChallengeRead`.

**Enums/statuses/actions:** none.

**Errors:**
- `401 MFA_INVALID` — `verify`: wrong code, unknown recovery code, or a recovery code already used (all identical on purpose).
- `410 RESOURCE_EXPIRED` — `verify`: the challenge is unknown, already used, or older than 5 minutes.
- `403 ACCOUNT_DISABLED` — `verify`: the account was deactivated since the password step.
- `401 INVALID_CREDENTIALS` — `setup`, `regenerate`: wrong `current_password`.
- `409 INVALID_STATE_TRANSITION` — `setup`, `confirm`: MFA is already enabled.
- `422 MFA_INVALID` — `confirm`: the code does not match the new secret (422 here, 401 on `verify`).
- `404 NOT_FOUND` — `setup`, `confirm`, `regenerate` called by a non-administrator.
- `429 RATE_LIMITED` — `verify` 10 per 15 minutes; `setup` and `regenerate` 5 per hour; `confirm` 10 per hour; all per IP.

**Auth/CSRF/MFA:**
- `verify`: **no cookie and no CSRF header**. Neither exists yet. The `challenge_id` is the credential.
- `setup`, `confirm`, `regenerate`: session cookie plus `X-CSRF-Token`; administrator only.

**Concurrency/idempotency:** a challenge is single-use and is spent by the first attempt, right or wrong. A TOTP code and a recovery code each work once.

**Example success JSON:** `POST /api/v1/auth/login` as an enrolled administrator answers `202` and sets no cookie:

```json
{
  "challenge_id": "<redacted>",
  "expires_in_seconds": 300
}
```

`POST /api/v1/auth/mfa/verify` then answers `204` with no body and sets:

```
Set-Cookie: access_token=<redacted>; HttpOnly; Max-Age=900; Path=/; SameSite=lax
Set-Cookie: refresh_token=<redacted>; HttpOnly; Max-Age=2592000; Path=/api/v1/auth; SameSite=lax
Set-Cookie: csrf_token=<redacted>; Max-Age=2592000; Path=/; SameSite=lax
```

**Example error JSON:** `verify` with an unknown challenge

```json
{
  "type": "http://localhost:8000/problems/RESOURCE_EXPIRED",
  "title": "Challenge expired",
  "status": 410,
  "detail": "This MFA challenge is no longer valid. Sign in again to obtain a new one.",
  "instance": "/api/v1/auth/mfa/verify",
  "code": "RESOURCE_EXPIRED",
  "request_id": "req_fd303105879549cd93212852ceb8fb44",
  "errors": []
}
```

**Fixture/test account:** the seeded administrator is already enrolled, so `setup` and `confirm` answer `409` for it. To test the enrolment screens you need an administrator without MFA; there is no API to create one (administrators are created in the database), so ask the backend owner for one when you reach FVS-005.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../admin-mfa.md`](../admin-mfa.md); ADR-017.

**Notes:**
- **Is `challenge_id` safe to hold in frontend state? Yes, in memory only.** It is a random single-use value that is useless without the second factor and dies after 5 minutes or one attempt. Do not put it in a URL, `localStorage` or `sessionStorage`. Losing it on a page reload is fine: the user signs in again.
- **A wrong code burns the challenge.** After `401 MFA_INVALID` you must send the user back through `/auth/login` for a new one. There is no "try again" on the same challenge.
- `expires_in_seconds` is 300. You may show a countdown.
- `MfaSetupRead.secret` and `otpauth_uri` are the raw TOTP secret, returned this once. Render the QR code from `otpauth_uri` in memory; never log or store either.
- The ten `recovery_codes` are returned once, by `confirm` and by `regenerate`. Make the user confirm they saved them.
- `confirm` upgrades the current session to MFA-complete, so no second login follows enrolment.
- There is no "disable MFA" endpoint.
- A recovery code is accepted in any case and with or without dashes.

### Domain / item: P1-3 — Admin settings

**Status:** built.

**Confirmed endpoint:**
- `GET /api/v1/admin/settings` — the list you were missing
- `GET /api/v1/admin/settings/{key}`
- `PATCH /api/v1/admin/settings/{key}`

**Request schema:** list: `cursor`, `limit`, `prefix` (key prefix), `type`. Update: see `openapi.json`: `SettingUpdate` (`{"value": <JSON>}`).

**Response schema:** see `openapi.json`: `SettingPage`, `SettingRead`. Each setting describes itself: `type`, `unit`, `minimum`, `maximum`, `nullable`, `is_public`, `description`.

**Enums/statuses/actions:** `type`: `"boolean" | "integer" | "string" | "money" | "duration" | "json"`. No "available actions" list.

**Errors:**
- `422 SETTING_INVALID` — the value does not fit the setting's type or range; the reasons are in `detail`, and `errors` is `[]`.
- `404 NOT_FOUND` — unknown key.
- `422 VALIDATION_ERROR` — the body has no `value` or has another field.

**Auth/CSRF/MFA:** administrator with MFA; `PATCH` also needs `X-CSRF-Token`.

**Concurrency/idempotency:** no version field. Two administrators saving the same setting: the last save wins, and both are audited. A `PATCH` with the value already stored is a `200` that changes nothing.

**Example success JSON:** `GET /api/v1/admin/settings?limit=3`

```json
{
  "items": [
    {
      "key": "accepting_orders",
      "type": "boolean",
      "value": true,
      "description": "Global kill switch. False blocks new checkout with 503 ORDERS_PAUSED; payments already in flight are unaffected.",
      "unit": null,
      "minimum": null,
      "maximum": null,
      "nullable": false,
      "is_public": true,
      "updated_at": "2026-10-12T18:04:28.624411Z",
      "updated_by": "f6393058-1d2f-4856-a859-cd143016d77d"
    },
    {
      "key": "checkout_hold_period",
      "type": "duration",
      "value": 1800,
      "description": "Seconds an unpaid checkout is held before automatic cancellation.",
      "unit": "seconds",
      "minimum": 300,
      "maximum": 7200,
      "nullable": false,
      "is_public": false,
      "updated_at": "2026-10-12T18:04:26.835160Z",
      "updated_by": null
    }
  ],
  "next_cursor": "Y2hlY2tvdXRfaG9sZF9wZXJpb2Q"
}
```

**Example error JSON:** `PATCH /api/v1/admin/settings/whatsapp_number` with `{"value": "070-000"}`

```json
{
  "type": "http://localhost:8000/problems/SETTING_INVALID",
  "title": "Setting value is not valid",
  "status": 422,
  "detail": "value must be a canonical E.164 number: a leading '+', then up to 15 digits, with no spaces or separators",
  "instance": "/api/v1/admin/settings/whatsapp_number",
  "code": "SETTING_INVALID",
  "request_id": "req_863a8abb20d14297b90d91d3c056a147",
  "errors": []
}
```

**Fixture/test account:** the seeded administrator. A fresh database has seventeen settings (since VS-028, 2026-10-20).

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json). **The authoritative key registry is [`../settings-registry.md`](../settings-registry.md)** (code: `src/app/platform/domain/settings_registry.py`).

**Notes:**
- Build the editor from the list response. Each row tells you its control: `boolean` is a switch, `integer` and `duration` are numbers within `minimum`/`maximum` (`duration` is in seconds), `string` is text, `money` is `{"amount_cents": int, "currency": "USD"}`. Where `nullable` is true, `null` means "not set".
- **Which keys need a confirmation step?** The backend has none: every `PATCH` applies at once. Confirmation is a frontend decision. `accepting_orders` deserves one, because it stops or opens checkout for everybody.
- Keys cannot be created or deleted through the API.
- `daily_download_cap` (ADR-019) was deleted by VS-023b; it no longer appears in the settings list. `free_shipping_threshold` (ADR-024) was deleted on 2026-10-20 (VS-028); `cash_payment_enabled`, `cash_max_open_orders` (integer 1 – 10) and `cash_max_order_total` (money, 1 – 1 000 000 cents, never `null`) were added the same day.

### Domain / item: P1-4 — Admin customer management

**Status:** built.

**Confirmed endpoint:**
- `GET /api/v1/admin/users`
- `GET /api/v1/admin/users/{user_id}`
- `PATCH /api/v1/admin/users/{user_id}`

**Request schema:** list: `cursor`, `limit`, `verified` (boolean), `active` (boolean), `search` (part of an email address, any case). Update: see `openapi.json`: `AdminUserUpdate` (`{"is_active": boolean}`, nothing else).

**Response schema:** see `openapi.json`: `AdminUserPage`, `AdminUserDetail`.

**Enums/statuses/actions:** `role`: `"customer" | "admin"`. No "available actions" list.

**Errors:**
- `409 INVALID_STATE_TRANSITION` — the account is anonymised or deleted, or deactivating it would leave no active administrator.
- `404 NOT_FOUND` — no such user.

**Auth/CSRF/MFA:** administrator with MFA; `PATCH` also needs `X-CSRF-Token`.

**Concurrency/idempotency:** `PATCH` with the state the account is already in is a `200` that changes nothing.

**Example success JSON:** `GET /api/v1/admin/users?search=seed-customer&limit=1`

```json
{
  "items": [
    {
      "id": "b2c4fe90-cb7b-40ad-bb1d-1d9e49877ee1",
      "email": "seed-customer@example.com",
      "role": "customer",
      "is_active": true,
      "email_verified_at": "2026-10-12T18:04:27.813928Z",
      "created_at": "2026-10-12T18:04:27.665978Z"
    }
  ],
  "next_cursor": null
}
```

**Example error JSON:** what the deactivated customer gets when they try to sign in again:

```json
{
  "type": "http://localhost:8000/problems/ACCOUNT_DISABLED",
  "title": "Account unavailable",
  "status": 403,
  "detail": "This account can no longer be used to sign in.",
  "instance": "/api/v1/auth/login",
  "code": "ACCOUNT_DISABLED",
  "request_id": "req_0a138f8d7dbd406c8dd6e50b5817a6b0",
  "errors": []
}
```

**Fixture/test account:** the seeded administrator and customer.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json).

**Notes:** your two questions.

- **Does deactivation revoke existing sessions immediately? Yes.** In the same transaction every session of that account is revoked and every access token already issued stops working.
- **What does an already-signed-in session receive on its next request?** `401 AUTH_REQUIRED`, the same answer as any expired session. It is not told why. `POST /auth/refresh` also answers `401`. A new login attempt answers `403 ACCOUNT_DISABLED`.
- Reactivation does not restore old sessions; the user signs in again.
- The list and the detail return the same fields today. There is no order history, address or note on a user yet.
- The only editable field is `is_active`. An administrator cannot change an email, a password or a role.
- Every read of this data is audit-logged, including list views.

### Domain / item: P1-5 — Admin reference data (categories/materials/colours)

**Status:** built.

**Confirmed endpoint:** for each of `categories`, `materials`, `colours`:
- `GET /api/v1/admin/{resource}`
- `POST /api/v1/admin/{resource}`
- `GET /api/v1/admin/{resource}/{id}`
- `PATCH /api/v1/admin/{resource}/{id}`
- `DELETE /api/v1/admin/{resource}/{id}`

**Request schema:** see `openapi.json`: `CategoryCreate`, `CategoryUpdate`, `MaterialCreate`, `MaterialUpdate`, `ColourCreate`, `ColourUpdate`. List: `cursor`, `limit`, `include_deleted` (boolean, default false).

**Response schema:** see `openapi.json`: `AdminCategoryPage` and `CategoryDetail`, and the same pair for materials and colours. Only categories have a `slug`.

**Enums/statuses/actions:** no status enum. A value is in one of three states: live (`is_active: true`, `deleted_at: null`), disabled (`is_active: false`, `deleted_at: null`), archived (`deleted_at` set).

**Errors:**
- `409 SLUG_CONFLICT` — a live category already has that slug, or a live material or colour already has that name (any case).
- `409 CATEGORY_IN_USE` — `DELETE` of a value that a live product uses. The same code for all three resources.
- `409 INVALID_STATE_TRANSITION` — `PATCH` or `DELETE` on an archived value.
- `422 VALIDATION_ERROR` — bad slug format, blank name, or an empty `PATCH`.
- `404 NOT_FOUND`.

**Auth/CSRF/MFA:** administrator with MFA; writes also need `X-CSRF-Token`.

**Concurrency/idempotency:** no version field; the last save wins.

**Example success JSON:** `GET /api/v1/admin/categories?limit=2`

```json
{
  "items": [
    {
      "id": "180555c0-0d30-434e-a70b-ccbc063a673e",
      "name": "Home Decor",
      "slug": "home-decor",
      "is_active": true,
      "deleted_at": null,
      "created_at": "2026-10-12T18:04:27.665978Z",
      "updated_at": "2026-10-12T18:04:27.665978Z"
    },
    {
      "id": "190bc079-dec3-4434-b137-052e65b0d0fd",
      "name": "Seasonal",
      "slug": "seasonal",
      "is_active": false,
      "deleted_at": null,
      "created_at": "2026-10-12T18:04:27.665978Z",
      "updated_at": "2026-10-12T18:04:27.665978Z"
    }
  ],
  "next_cursor": "eyJuIjoiU2Vhc29uYWwiLCJpIjoiMTkwYmMwNzktZGVjMy00NDM0LWIxMzctMDUyZTY1YjBkMGZkIn0"
}
```

**Example error JSON:** `DELETE` of a category in use

```json
{
  "type": "http://localhost:8000/problems/CATEGORY_IN_USE",
  "title": "Value is in use",
  "status": 409,
  "detail": "Category 180555c0-0d30-434e-a70b-ccbc063a673e is used by a live product; reassign it first.",
  "instance": "/api/v1/admin/categories/180555c0-0d30-434e-a70b-ccbc063a673e",
  "code": "CATEGORY_IN_USE",
  "request_id": "req_492d65fa9d224286bbe1abb8c9d36f82",
  "errors": []
}
```

**Fixture/test account:** the seeded reference data; `seasonal` is seeded disabled.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../reference-data.md`](../reference-data.md).

**Notes:** your two questions.

- **Archive mechanism: `DELETE`.** There is no separate archive endpoint. `DELETE` is a soft archive and answers `204`. It is permanent: there is no restore, and an archived value cannot be edited.
- **To hide a value temporarily, `PATCH {"is_active": false}`** instead. That is reversible.
- **Can a product keep a value that is later archived? No.** A value used by a live product cannot be archived (`409 CATEGORY_IN_USE`); reassign the products first. A value used only by deleted products can be archived.
- **A product can keep a value that is later disabled.** A product in a disabled category disappears from the storefront. A disabled material or colour still shows on its products but leaves the public filter lists.
- Archiving a category frees its slug for reuse.
- Lists are ordered by name.

### Domain / item: P1-6 — Admin product CRUD

**Status:** built.

**Confirmed endpoint:**
- `GET /api/v1/admin/products`
- `POST /api/v1/admin/products`
- `GET /api/v1/admin/products/{product_id}`
- `PATCH /api/v1/admin/products/{product_id}`
- `DELETE /api/v1/admin/products/{product_id}?version=N`

**Request schema:** see `openapi.json`: `AdminProductCreate`, `AdminProductUpdate`. List parameters: `type`, `category_id`, `is_visible`, `is_featured`, `is_available`, `deleted`, `q`, `sort` (`-created_at`, `price`, `-price`), `cursor`, `limit`.

**Response schema:** see `openapi.json`: `AdminProductPage`, `AdminProductDetail`.

**Enums/statuses/actions:** `type`: `"physical" | "stl"`, fixed at creation. `purchase_mode`: `"online_only" | "whatsapp_only" | "both"`. No "available actions" list.

**Errors:**
- `409 VERSION_CONFLICT` — the `version` sent is not the stored one. Nothing was written. The body has an extra member `current_version`.
- `409 SLUG_CONFLICT` — another live product has the slug.
- `409 INVALID_STATE_TRANSITION` — the product is deleted.
- `422 VALIDATION_ERROR` — a bad field, a field not allowed for the product's type, or an archived or unknown category, material or colour. `errors[].loc` names the field.
- `404 NOT_FOUND`.

**Auth/CSRF/MFA:** administrator with MFA; writes also need `X-CSRF-Token`.

**Concurrency/idempotency:** **optimistic locking, field `version`.** Every read returns it. `PATCH` must send it in the body and `DELETE` in the query string. On `409 VERSION_CONFLICT`, re-read the product, show the user the newer state, and let them retry.

**Example success JSON:** `GET /api/v1/admin/products?q=Moon+Lamp&limit=1`

```json
{
  "items": [
    {
      "id": "149e7387-f8cb-432f-b6bb-8f27f3c5649a",
      "type": "physical",
      "category_id": "180555c0-0d30-434e-a70b-ccbc063a673e",
      "name": "Moon Lamp",
      "description": "Moon Lamp: seeded by scripts/dev_seed.py for local testing.",
      "slug": "moon-lamp",
      "seo_title": null,
      "seo_description": null,
      "og_image_url": null,
      "price": {
        "amount_cents": 2400,
        "currency": "USD"
      },
      "is_visible": true,
      "is_featured": true,
      "is_available": true,
      "purchase_mode": "both",
      "material_id": "86f2d315-41be-491d-8a3e-09a599237ffe",
      "colour_id": "efe3e28c-4e0f-451c-9a53-cee916ecac8d",
      "dimensions": {
        "length_mm": 120,
        "width_mm": 80,
        "height_mm": 60
      },
      "production_lead_time_days": 2,
      "batch_size": 2,
      "max_quantity_per_line": 5,
      "weight_grams": null,
      "average_rating": 0.0,
      "review_count": 0,
      "wishlist_count": 0,
      "version": 1,
      "deleted_at": null,
      "created_at": "2026-10-12T18:04:27.665978Z",
      "updated_at": "2026-10-12T18:04:27.665978Z",
      "images": [
        {
          "id": "319c6f4f-da64-4ce8-8a85-c58a18ad5084",
          "product_id": "149e7387-f8cb-432f-b6bb-8f27f3c5649a",
          "url": "/media/products/248eb877-bafa-4001-9072-9523d0876f9a.png",
          "alt_text": "Moon Lamp, view 1",
          "sort_order": 0,
          "is_cover": true,
          "created_at": "2026-10-12T18:04:27.665978Z",
          "updated_at": "2026-10-12T18:04:27.665978Z"
        }
      ]
    }
  ],
  "next_cursor": null
}
```

**Example error JSON:** a `PATCH` with a stale `version`

```json
{
  "current_version": 1,
  "type": "http://localhost:8000/problems/VERSION_CONFLICT",
  "title": "Product was changed by someone else",
  "status": 409,
  "detail": "The product is at version 1; re-read it and retry.",
  "instance": "/api/v1/admin/products/149e7387-f8cb-432f-b6bb-8f27f3c5649a",
  "code": "VERSION_CONFLICT",
  "request_id": "req_64f665903c4b47cc85b7457d44c8f7cd",
  "errors": []
}
```

`POST` of an STL product with a physical-only field

```json
{
  "type": "http://localhost:8000/problems/VALIDATION_ERROR",
  "title": "Product is not valid",
  "status": 422,
  "detail": "batch_size: is not allowed on an STL product",
  "instance": "/api/v1/admin/products",
  "code": "VALIDATION_ERROR",
  "request_id": "req_f3ed09367ffc4337a70369df71d7f201",
  "errors": [
    {
      "loc": [
        "body",
        "batch_size"
      ],
      "msg": "is not allowed on an STL product",
      "type": "value_error"
    }
  ]
}
```

**Fixture/test account:** the seeded catalogue (11 products, including one hidden and one in a disabled category).

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../products.md`](../products.md); ADR-020.

**Notes:** the field matrix you asked for.

| Group | Fields |
|---|---|
| Both types, required on create | `type`, `category_id`, `name`, `slug`, `price` |
| Both types, optional | `description`, `seo_title`, `seo_description`, `og_image_url`, `is_visible` (default `false`), `is_featured` (default `false`), `is_available` (default `true`) |
| Physical only, **required** | `purchase_mode`, `production_lead_time_days` (0 or more), `batch_size`, `max_quantity_per_line` |
| Physical only, optional | `material_id`, `colour_id`, `dimensions` (`length_mm`, `width_mm`, `height_mm`, all three), `weight_grams` |
| STL | none of the eight physical-only fields; sending one is a `422` |
| Read-only | `id`, `version`, `average_rating`, `review_count`, `wishlist_count`, `images`, `created_at`, `updated_at`, `deleted_at` |

- `price` is `{"amount_cents": <integer>, "currency": "USD"}`. Integer cents only, `USD` only. Your `MoneyInput` fits.
- An STL product has **no file field**. No STL file is ever uploaded (ADR-019).
- `PATCH` semantics: a field left out is unchanged; a field sent as `null` is cleared. `name`, `slug`, `price`, `category_id` and the three flags cannot be `null`. `type` cannot be sent.
- A new product is hidden (`is_visible: false`) until you set it visible.
- `slug` is letters, digits and single hyphens. The server trims and lowercases it, and does **not** generate it from the name: "Moon Lamp" is a `422`, `moon-lamp` is accepted.
- `DELETE` is a permanent soft delete and frees the slug. There is no restore.
- Length limits: name, slug and SEO title 200; SEO description 500; description 10,000.
- `GET .../{product_id}` also returns deleted products; the list shows them only with `deleted=true`.

### Domain / item: P1-7 — Admin product image upload

**Status:** built.

**Confirmed endpoint:**
- `POST /api/v1/admin/products/{product_id}/images` — upload
- `PATCH /api/v1/admin/products/{product_id}/images/{image_id}` — alt text
- `PUT /api/v1/admin/products/{product_id}/images/{image_id}/cover` — make cover
- `PUT /api/v1/admin/products/{product_id}/images/order` — reorder
- `DELETE /api/v1/admin/products/{product_id}/images/{image_id}`

**Request schema:** upload is `multipart/form-data` with two parts: **`file`** (required, one image) and **`alt_text`** (optional text, at most 300 characters). Others: see `openapi.json`: `ProductImageUpdate`, `ProductImageOrderUpdate`.

**Response schema:** see `openapi.json`: `ProductImageRead` (upload answers `201`), `ProductImageList` (reorder).

**Enums/statuses/actions:** none. **There is no scan state**: see Concurrency.

**Errors:**
- `422 UPLOAD_REJECTED` — not a JPEG, PNG or WebP by content; empty; over 10 MB; over 40 megapixels; no `Content-Length`; or the product already has 20 images.
- `422 MALWARE_DETECTED` — the scan found malware.
- `503 SERVICE_UNAVAILABLE` — the scanner is down. The upload is refused, never accepted unscanned.
- `409 INVALID_STATE_TRANSITION` — the product is deleted, or you tried to delete the cover while other images remain.
- `422 VALIDATION_ERROR` — reorder list does not name every live image exactly once.
- `404 NOT_FOUND` — the product, or an image that is not a live image of this product.

**Auth/CSRF/MFA:** administrator with MFA plus `X-CSRF-Token` on all five.

**Concurrency/idempotency:** **the upload is synchronous.** The response arrives after the file has been scanned, re-encoded and stored: `201` means the image is live and usable; anything else means nothing was kept. There is no pending state and nothing to poll. Image changes do not change the product's `version`.

**Example success JSON:**

```json
{
  "id": "8a55009c-3d0d-4c6e-98c4-6559047a072f",
  "product_id": "149e7387-f8cb-432f-b6bb-8f27f3c5649a",
  "url": "/media/products/c258ce0e-3fc5-494d-9d1b-f850a550bdc8.jpg",
  "alt_text": "Side view",
  "sort_order": 1,
  "is_cover": false,
  "created_at": "2026-10-12T18:04:31.710576Z",
  "updated_at": "2026-10-12T18:04:31.710576Z"
}
```

**Example error JSON:** a file that is not an image

```json
{
  "type": "http://localhost:8000/problems/UPLOAD_REJECTED",
  "title": "Upload rejected",
  "status": 422,
  "detail": "not a JPEG, PNG or WebP image",
  "instance": "/api/v1/admin/products/149e7387-f8cb-432f-b6bb-8f27f3c5649a/images",
  "code": "UPLOAD_REJECTED",
  "request_id": "req_3f0eab2017bf4089a833d4d5f0aa92aa",
  "errors": [
    {
      "loc": [
        "body",
        "file"
      ],
      "msg": "not a JPEG, PNG or WebP image",
      "type": "value_error"
    }
  ]
}
```

**Fixture/test account:** the seeded products and administrator.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../product-images.md`](../product-images.md); ADR-021.

**Notes:**
- One file per request. Upload several by sending several requests, one after another (they lock the product).
- The type is decided from the file's content, not its name or the part's content type.
- The first image of a product becomes its cover automatically. Later uploads go to the end.
- The stored file is re-encoded: EXIF and GPS data are stripped and the orientation is applied.
- To replace a cover: make another image the cover, then delete the old one.
- A scan can take a few seconds; allow a generous timeout and show progress.
- `url` follows [B4](#domain--item-b4--imageasset-url-format).

### Domain / item: P2-5 — Notifications

**Status:** built (the channel). One business event writes to it so far: `custom_request.submitted` (VS-034), sent to administrators.

**Confirmed endpoint:**
- `GET /api/v1/me/notifications`
- `PATCH /api/v1/me/notifications/{notification_id}`

**Request schema:** list: `cursor`, `limit`, `read` (boolean, optional filter). Update: see `openapi.json`: `NotificationUpdate` (`{"read": boolean}`).

**Response schema:** see `openapi.json`: `NotificationPage`, `NotificationRead` (`id`, `type`, `payload`, `read`, `created_at`).

**Enums/statuses/actions:** `type`: `"account" | "order" | "payment" | "refund" | "offer" | "download" | "custom_request"`. This is a category. The specific event is the string `payload.event`.

**Errors:**
- `401 AUTH_REQUIRED`.
- `403 EMAIL_VERIFICATION_REQUIRED` — `PATCH` by an account whose email is not verified.
- `403 CSRF_INVALID` — `PATCH` without the header.
- `404 NOT_FOUND` — not your notification, or no such id.

**Auth/CSRF/MFA:** session cookie. `GET` works for an unverified account. `PATCH` needs a verified account and `X-CSRF-Token`.

**Concurrency/idempotency:** marking read or unread is idempotent. Two simultaneous changes: the last one wins.

**Example success JSON:** `PATCH` with `{"read": true}`

```json
{
  "id": "f37a4558-0ef1-44bc-adb4-ff99d0c3584a",
  "type": "account",
  "payload": {
    "event": "account.seed_welcome",
    "message": "Created by scripts/dev_seed.py."
  },
  "read": true,
  "created_at": "2026-10-12T18:04:27.665978Z"
}
```

**Example error JSON:** the same `PATCH` without `X-CSRF-Token`

```json
{
  "type": "http://localhost:8000/problems/CSRF_INVALID",
  "title": "CSRF token missing or invalid",
  "status": 403,
  "detail": "Send this session's CSRF cookie value in the X-CSRF-Token header.",
  "instance": "/api/v1/me/notifications/f37a4558-0ef1-44bc-adb4-ff99d0c3584a",
  "code": "CSRF_INVALID",
  "request_id": "req_f97a9837527445f49c860af27f352d99",
  "errors": []
}
```

**Fixture/test account:** the seeded customer has two unread notifications.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../notification-contract.md`](../notification-contract.md).

**Notes:**
- Pagination is [C2](#domain--item-c2--cursor-pagination-response-shape); newest first.
- **There is no unread-count endpoint.** To show a badge, request `?read=false&limit=N` and count; show "N+" when `next_cursor` is not `null`.
- **The registry of `payload.event` values lives in [`../notification-contract.md`](../notification-contract.md).** Today it holds `custom_request.submitted` under type `custom_request` (VS-034, administrators only; payload `custom_request_id`, `project_title`, `title`) and one planned value: `stl.delivered` under type `download` (VS-023b). Each slice that adds an event records it there.
- `payload` is an object that always has `event`. Its other keys depend on the event. Render an unknown `event` with a generic fallback and never fail on one.
- The `download` category name is historical. It now means "your STL file was sent".
- There is no "mark all read" and no delete.

### Domain / item: VS-036 — Reviews and the Verified Purchase badge

**Status:** built (VS-036, [ADR-044](../adr/ADR-044-reviews-and-verified-purchase-badge.md)). Moderation (hide/restore, VS-037) is not built yet.

**Confirmed endpoint:**
- `GET /api/v1/products/{slug}/reviews` (public). The path takes the product **slug**, not its id.
- `GET /api/v1/me/reviews`
- `POST /api/v1/reviews`
- `PATCH /api/v1/reviews/{review_id}`
- `DELETE /api/v1/reviews/{review_id}`

**Request schema:** see `openapi.json`: `ReviewCreate` (`product_id`, `rating` 1-5, optional `body`) and `ReviewUpdate` (`rating?`, `body?`; at least one; `body: null` clears the text). `body` is trimmed, at most 2000 characters; whitespace-only becomes `null`, so a rating-only review is fine. Unknown fields (`is_verified_purchase`, `is_hidden`, ...) are a 422. Public list query: `cursor`, `limit` (1-50, default 20), `rating` (1-5), `verified_purchase` (boolean). `/me/reviews`: `cursor`, `limit`.

**Response schema:** `ReviewPage` of `PublicReviewRead` (`id`, `rating`, `body`, `is_verified_purchase`, `created_at`, `edited`). `MyReviewPage` / `MyReviewRead` add `product_id`, `product_slug` (`null` if the product was deleted) and `is_hidden`. There is **no author field**: render "Customer" or "Verified buyer"; an email is never exposed.

**Errors:**
- `404 NOT_FOUND`: public list or create for an unknown, deleted or non-public product; edit or delete of a review that is not yours, missing or already deleted (one body for all three).
- `409 REVIEW_ALREADY_EXISTS`: you already have a live review of this product, hidden or not. Delete it to write a new one.
- `422 REVIEW_CONTENT_REJECTED` with `reason` `"link"` or `"profanity"`; plain `422` for a bad rating, length or control character.
- `401`, `403 EMAIL_VERIFICATION_REQUIRED`, `403 CSRF_INVALID`, `429 RATE_LIMITED`.

**Auth/CSRF/MFA:** the public list needs nothing. `/me/reviews` needs a session (an unverified account may read). Writes need a verified account and `X-CSRF-Token`.

**Rate limits:** public list 600/hour per IP. Writes 10/hour per user, one budget shared by POST, PATCH and DELETE.

**Notes:**
- **The badge is computed by the server and can change at any time.** It turns on when a purchase is owned (STL paid) or received (physical `delivered` / `picked_up`, cash after the handover), and off after a full refund, a return or a cancellation. A partial refund keeps it. Never cache it client-side.
- **WhatsApp-only products never show the badge:** `is_verified_purchase` is always `false` there, and `verified_purchase=true` returns an empty page. If the product goes back to online sale, the badge reappears by itself.
- **Hidden and soft-deleted rows:** the public list never shows them, and they do not count in `average_rating` / `review_count`. `/me/reviews` shows your hidden reviews with `is_hidden: true` (edit them as usual; they stay hidden), and never your deleted ones.
- Sorting is fixed, newest first. Pagination is [C2](#domain--item-c2--cursor-pagination-response-shape).
- `edited` is `true` once the author changed the review.
- The profanity list is a first draft pending the product owner's review before go-live; expect it to change.

### Domain / item: P2-6 — Password reset

**Status:** built.

**Confirmed endpoint:**
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`

**Request schema:** see `openapi.json`: `PasswordResetRequest` (`email`), `PasswordResetConfirm` (`token`, `new_password`).

**Response schema:** `request` answers `202` with `PasswordResetAccepted`; `confirm` answers `204` with no body.

**Enums/statuses/actions:** none.

**Errors:**
- `400 INVALID_TOKEN` — `confirm`: the token is unknown, already used, or belongs to a deactivated account.
- `410 RESOURCE_EXPIRED` — `confirm`: the token is more than one hour old. Once the token is purged (VS-046: 7 days past expiry by default), the same link answers `400 INVALID_TOKEN`.
- `422 VALIDATION_ERROR` — bad email format, or a password that breaks the policy.
- `429 RATE_LIMITED` — `request` 5 per hour, `confirm` 20 per hour, per IP.

**Auth/CSRF/MFA:** public. No cookie and no CSRF header on either.

**Concurrency/idempotency:** a token works once. A successful `confirm` also cancels every other reset link the account holds.

**Example success JSON:** `request`, identical whether or not the address has an account

```json
{
  "message": "If an account exists for that address, a reset email has been sent."
}
```

**Example error JSON:** `confirm` with a bad token

```json
{
  "type": "http://localhost:8000/problems/INVALID_TOKEN",
  "title": "Reset link invalid",
  "status": 400,
  "detail": "This password reset link is invalid or has already been used.",
  "instance": "/api/v1/auth/password-reset/confirm",
  "code": "INVALID_TOKEN",
  "request_id": "req_8003d3fbb4af41b3b55dc29a4aa9ced7",
  "errors": []
}
```

**Fixture/test account:** the seeded customer; read the link from `email_outbox` ([A3](#domain--item-a3--test-account-and-fixture-provisioning)).

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../../README.md`](../../README.md) "Password reset (VS-004)".

**Notes:**
- **Password policy is the same as registration:** 8 to 256 characters counted as Unicode code points, no composition rules, no control characters, not trimmed. Details in [`../frontend-contract-vs002.md`](../frontend-contract-vs002.md) section 3.2.
- **The email link** is `<FRONTEND_BASE_URL>/reset-password#token=<token>`. Your route must be `/reset-password`, and the token is in the fragment. Remove it from the address bar after reading it.
- `request` always answers `202` with the same body and takes at least about 300 ms. Never tell the user whether the address exists.
- A second `request` within 2 minutes for the same account sends no second email, silently.
- **A successful reset signs the user out everywhere.** It does not sign them in: send them to the login page.
- A reset does not remove an administrator's MFA.
- From VS-033 the reset **request** needs a Turnstile `captcha_token` ([ADR-025](../adr/ADR-025-frontend-contract-decisions.md)); see [P2-7](#domain--item-p2-7--turnstile-field-contract). The confirm step does not.

### Domain / item: P2-8 — Rate-limit (429) universality

**Status:** built for every existing route; provisional for routes not built.

**Confirmed endpoint:** every rate-limited route.

**Request schema:** not applicable.

**Response schema:** headers, section 1.4.

**Enums/statuses/actions:** none.

**Errors:**
- `429 RATE_LIMITED` — body is the shared problem; headers `RateLimit-Limit`, `RateLimit-Remaining: 0`, `RateLimit-Reset`, and `Retry-After` equal to `RateLimit-Reset`.

**Auth/CSRF/MFA:** not applicable.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** not applicable.

**Example error JSON:**

```json
{
  "type": "http://localhost:8000/problems/RATE_LIMITED",
  "title": "Too many requests",
  "status": 429,
  "detail": "Rate limit exceeded. Try again later.",
  "instance": "/api/v1/auth/register",
  "code": "RATE_LIMITED",
  "request_id": "req_...",
  "errors": []
}
```

**Fixture/test account:** none. Reset counters with the Redis command in [A3](#domain--item-a3--test-account-and-fixture-provisioning).

**Authoritative source/OpenAPI file:** `src/app/core/rate_limit.py` (one limiter for the whole API); limits per route in [`../frontend-contract-vs002.md`](../frontend-contract-vs002.md) section 6 and [`../admin-mfa.md`](../admin-mfa.md).

**Notes:**
- **Yes, the shape is universal today.** Every limit in the API goes through one function, so `Retry-After` is whole seconds everywhere, never an HTTP date. `ApiError.retryAfterSeconds` needs no per-route case.
- The login lockout (10th failed attempt for one email and IP) is also `429 RATE_LIMITED` with `Retry-After: 900`.
- Current limits per IP: register 5/hour, resend 5/hour, verify-email 20/hour, login 20/hour, refresh 60/hour, reset request 5/hour, reset confirm 20/hour, public reads 600/hour per route (the public review list included), suggestions 3,000/hour. Review writes: 10/hour per user. Admin: 300/minute per administrator.
- Contact form: 60 attempts/hour, then 5/hour per IP and per email. Bring Your Idea: 20 attempts/hour, then 5/hour per IP and per email ([P2-2](#domain--item-p2-2--bring-your-idea-submission)). Both use the same limiter and headers.
- **Provisional:** offer routes are not built. They are planned to use the same limiter.
- Until VS-020, a server-rendering frontend sends every visitor's request from one IP and all visitors share one budget. VS-020 adds a trusted forwarded-IP header.

---

## 3. Removed by ADR-019 and ADR-024

These items will never be built. Remove the frontend work that depends on them.

- **ADR-019** ([`../adr/ADR-019-manual-stl-delivery.md`](../adr/ADR-019-manual-stl-delivery.md)): the platform stores and serves **no STL files**. After a verified payment the administrator emails the file by hand and marks the order line as sent. There are no asset versions, entitlements, library, downloads, download cap or download history.
- **ADR-024** ([`../adr/ADR-024-cash-on-delivery-and-courier-priced-shipping.md`](../adr/ADR-024-cash-on-delivery-and-courier-priced-shipping.md)): the platform **charges no shipping**. The courier sets and collects the delivery fee. There are no shipping zones, no shipping line in a total, no free-shipping threshold and no shipping refund. The same ADR adds cash on delivery for physical-only orders.

| Removed | By | Frontend slices to retire or change |
|---|---|---|
| C4 Shipping zones | ADR-024 | FVS-024 (both halves); the zone step of FVS-026 |
| C9 Entitlements and library | ADR-019 | FVS-020; route `/account/library` |
| C10 STL download | ADR-019 | FVS-021; route `/account/downloads` |
| P1-8 STL asset-version upload | ADR-019 | FVS-018 |
| P1-9 Entitlement grant | ADR-019 | FVS-019 |
| Free-shipping threshold (part of B1, C6) | ADR-024 | the threshold display in FVS-022 and FVS-026 |
| Shipping refund (part of P1-13) | ADR-024 | the "shipping" row of `RefundCreateForm` |
| "Digital refund revokes entitlement" (part of P1-13) | ADR-019 | the revocation confirmation gate in `RefundCreateForm` |
| Fixtures 4, 5, 6 (as written) | both | see [section 5](#5-test-accounts-and-fixtures) |

### Domain / item: C4 — Shipping zones (public read)

**Status:** removed by ADR-024.

**Confirmed endpoint:** none. `GET /api/v1/shipping-zones` does not exist and never will.

**Request schema:** not applicable.

**Response schema:** not applicable. There is no `ShippingZoneRead`.

**Enums/statuses/actions:** not applicable.

**Errors:** the path answers `404 NOT_FOUND`.

**Auth/CSRF/MFA:** not applicable.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** none.

**Example error JSON:** the shared problem body with `"status": 404, "code": "NOT_FOUND"`.

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** ADR-024 decision 1; [`../requirments/api-endpoints.md`](../requirments/api-endpoints.md) section 10.2.

**Notes:**
- Checkout has no zone picker and no zone id. An order total is `subtotal + tax`, and tax is 0 in V1.
- Delivery orders show the fixed text "delivery fee paid to the courier on delivery". The API will return it on the order (`delivery_fee_note`, provisional).
- The address book stays ([C3](#domain--item-c3--address-book-contract)); the address's phone is the courier's contact.
- The admin shipping-zone CRUD is removed too.

### Domain / item: C9 — Entitlements / customer library contract

**Status:** removed by ADR-019.

**Confirmed endpoint:** none. `GET /api/v1/me/entitlements` does not exist and never will.

**Request schema:** not applicable.

**Response schema:** not applicable.

**Enums/statuses/actions:** not applicable.

**Errors:** the path answers `404 NOT_FOUND` (or `401` when signed out).

**Auth/CSRF/MFA:** not applicable.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** none.

**Example error JSON:** none.

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** ADR-019 decisions 1 and 5; [`../requirments/api-endpoints.md`](../requirments/api-endpoints.md) section 12.

**Notes:**
- There is no entitlement entity. **Ownership is a paid, unrefunded STL order line.**
- The customer's list of purchased STLs is their order history: each STL line shows `fulfillment_status` `awaiting_delivery` or `delivered`, with `fulfilled_at` ([C8](#domain--item-c8--orderorder-line-status-enum-and-available-actions), provisional).
- A "My STL purchases" page, if you want one, is a filtered view over `GET /api/v1/me/orders`. It has no download button.
- `EntitlementModel` has no backend counterpart; delete it.

### Domain / item: C10 — STL download delivery

**Status:** removed by ADR-019.

**Confirmed endpoint:** none. There is no file-download endpoint and no `GET /api/v1/me/downloads` history endpoint. Neither will be built.

**Request schema:** not applicable.

**Response schema:** not applicable.

**Enums/statuses/actions:** not applicable.

**Errors:** not applicable. The daily-cap and revoked-access errors you asked about do not exist.

**Auth/CSRF/MFA:** not applicable.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** none.

**Example error JSON:** none.

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** ADR-019.

**Notes:**
- The customer receives the STL **as an email attachment from the administrator**, sent by hand to the email address they bought with. Delivery is not instant.
- What the frontend shows instead of a download button: on the order page, "We will email your file" while the line is `awaiting_delivery`, and "Sent on <date>" once it is `delivered`.
- When the administrator marks a line as sent, the customer gets an email and an in-app notification (type `download`, `payload.event: "stl.delivered"`, provisional until VS-023b).
- A customer who lost the file asks through the contact form or WhatsApp. There is no re-download.
- The promised delivery time ("within N hours") is an open business decision; do not hard-code one.
- `DownloadButton`, `downloadHistoryModel`, `DownloadHistoryTable` and `DownloadNotice` have no backend counterpart.

### Domain / item: P1-8 — Admin STL asset-version upload

**Status:** removed by ADR-019.

**Confirmed endpoint:** none. No asset-version list, create, detail or publish endpoint exists or will.

**Request schema:** not applicable.

**Response schema:** not applicable.

**Enums/statuses/actions:** not applicable. There are no scan states for STL files.

**Errors:** not applicable.

**Auth/CSRF/MFA:** not applicable.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** none.

**Example error JSON:** none.

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** ADR-019 decision 1.

**Notes:**
- The administrator keeps STL files on their own drive. Nothing is uploaded to the platform.
- An STL product is created like any other product ([P1-6](#domain--item-p1-6--admin-product-crud)) with `type: "stl"`. It has images but no file.
- `assetVersionWorkflow`, `AssetVersionList`, `AssetVersionUploader` and `useScanStatusPolling` have no backend counterpart. `FileUploader` is still used by product images and, later, Bring Your Idea.
- What replaces it for the administrator is the **STL delivery queue** ([P1-11](#domain--item-p1-11--admin-order-fulfillment), provisional): a list of paid STL lines still to be emailed, each with a "mark as sent" action.

### Domain / item: P1-9 — Admin entitlement grant

**Status:** removed by ADR-019.

**Confirmed endpoint:** none. `POST /api/v1/admin/users/{user_id}/entitlements` does not exist and never will. The request listed it as confirmed; it was removed.

**Request schema:** not applicable. There is no `AdminEntitlementGrant`.

**Response schema:** not applicable.

**Enums/statuses/actions:** not applicable.

**Errors:** not applicable.

**Auth/CSRF/MFA:** not applicable.

**Concurrency/idempotency:** not applicable.

**Example success JSON:** none.

**Example error JSON:** none.

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** ADR-019; [`../requirments/api-endpoints.md`](../requirments/api-endpoints.md) section 17.

**Notes:**
- To give an STL away, the administrator simply emails it. The platform records nothing.
- `GrantEntitlementDialog` and `entitlementGrantModels` have no backend counterpart. `DialogShell` and `SearchableCombobox` are generic and stay useful.

---

## 4. Not built yet (provisional)

> **Everything in this section is PROVISIONAL.** No code exists for it. The answers come from the specification ([`../requirments/api-endpoints.md`](../requirments/api-endpoints.md), [`../SRS.md`](../SRS.md), the ADRs and [`../vertical-slice-plan.md`](../vertical-slice-plan.md)) and can change when the slice is built. Build models and screens against them if you want a head start, but do not treat a field name as final until the slice is merged and the route appears in `openapi.json`. Each block names the slice to watch.

> **Built since this section was written:** C3 (VS-026), C5 (VS-022), and from VS-023 C6 (STL-only checkout), C11 (ownership check), C12 (idempotency) and the server side of C7. Each block's status line says so; their contracts are in `openapi.json`.

Build order on the backend: VS-020 (staging) or VS-022 (cart) next, then VS-023 (digital checkout), VS-023b, VS-024, VS-025, VS-026, VS-028 (physical checkout and cash), VS-029, VS-030, VS-031, VS-033, VS-034.

### Domain / item: C3 — Address book contract

**Status:** **built** (VS-026). Decisions: [ADR-027](../adr/ADR-027-address-book-decisions.md). Full contract: [`docs/address-book.md`](../address-book.md).

**Confirmed endpoint:**
- `GET /api/v1/me/addresses`, `POST /api/v1/me/addresses`
- `GET`, `PATCH`, `DELETE /api/v1/me/addresses/{address_id}`
- `PUT /api/v1/me/addresses/{address_id}/default`

**Request schema:** `AddressCreate`, `AddressUpdate` in `openapi.json`.
- Required: `label`, `recipient_name`, `phone`, `governorate`, `city`, `landmark_notes`.
- Optional: `area`, `street`, `is_default`.
- `landmark_notes` is **required**, which changes the provisional answer.
- `PATCH` takes any subset. An empty body is `422`; `null` clears `area` or `street`.

**Response schema:** `AddressRead` is the fields above (phone in E.164), plus `id`, `is_default`, `created_at`, `updated_at`. `AddressList` is `{"items": AddressRead[]}`.

**Enums/statuses/actions:** `governorate` is one of `akkar`, `baalbek_hermel`, `beirut`, `beqaa`, `keserwan_jbeil`, `mount_lebanon`, `nabatieh`, `north`, `south`. Labels are yours to translate.

**Errors:**
- `401 AUTH_REQUIRED`.
- `403 CSRF_INVALID` or `EMAIL_VERIFICATION_REQUIRED` on writes.
- `404 NOT_FOUND` for another user's, a deleted or an unknown id; all three are the same body.
- `422 VALIDATION_ERROR`, with `errors[].loc` naming the field.
- `422 ADDRESS_LIMIT_REACHED` at 20 saved addresses.
- There is no `409`.

**Auth/CSRF/MFA:** reads: any signed-in user, verified or not. Writes: verified customer plus `X-CSRF-Token`.

**Concurrency/idempotency:** the default switch is atomic. The database allows one default per user, and parallel switches end with exactly one. `PUT …/default` is idempotent.

**Example success JSON:**

```json
{
  "id": "6f1c2a8e-5d0b-4e7a-9c3f-1b2d3e4f5a6b",
  "label": "Home",
  "recipient_name": "Rima Haddad",
  "phone": "+9613123456",
  "governorate": "beqaa",
  "city": "Zahle",
  "area": "Hoch el Oumara",
  "street": null,
  "landmark_notes": "Blue gate opposite the bakery",
  "is_default": true,
  "created_at": "2026-10-15T09:30:00Z",
  "updated_at": "2026-10-15T09:30:00Z"
}
```

**Example error JSON:** see [C1](#domain--item-c1--rfc-9457-field-level-validation-error-shape).

**Fixture/test account:** any verified seed customer; the seed adds no addresses.

**Authoritative source/OpenAPI file:** `openapi.json`; `docs/address-book.md`.

**Notes:**
- **No postal code and no country.** Addresses are Lebanese only.
- `phone` accepts any common Lebanese spelling (`03 123 456`, `71 123 456`, `+961 3 123 456`, `00961…`) and comes back as E.164. Show it as you like; send it back as it is.
- **Default address:**
  - A user's **first** address becomes the default automatically.
  - Later ones become default only through `PUT …/default`, or `is_default: true` on create or update; the previous default is cleared in the same transaction.
  - `PATCH {"is_default": false}` on the default clears it.
- **Delete is a soft delete.** Deleting the default leaves **no** default; nothing is promoted (open question 10, now answered). Past orders keep their own copy of the address.
- The list is not paginated: at most 20 addresses, the default first, then newest.

### Domain / item: C5 — Cart contract

**Status:** built (VS-022). Full contract: [`../cart.md`](../cart.md); decisions: [ADR-029](../adr/ADR-029-cart-decisions.md).

**Confirmed endpoint:**
- `GET /api/v1/cart`
- `POST /api/v1/cart/items`
- `PATCH /api/v1/cart/items/{product_id}`
- `DELETE /api/v1/cart/items/{product_id}`

**Request schema:** `CartItemAdd` (`product_id`, `quantity` default 1), `CartItemQuantityUpdate` (`quantity`). `quantity` is a JSON integer of at least 1.

**Response schema:** `CartRead` and `CartLineRead` in `openapi.json`. Per line, besides the product summary and the two prices:
- `price_changed` — the current price differs from the snapshot taken when the line was first added.
- **`over_cap`** — the line's quantity is above the product's *current* `max_quantity_per_line` (an administrator lowered it). Show it as an error on the line; `PATCH` can lower the quantity, and checkout will refuse the line until then.
- `purchasable` / `unpurchasable_reason` — `not_listed`, `unavailable` or `whatsapp_only` when the product can no longer be bought. The line stays; it can be deleted but not edited, and checkout refuses it.
- `max_quantity` — the current physical cap (null for STL and for a line that is not listed).

There is no total: compute one for display if you need it; checkout recomputes it from live prices.

**Enums/statuses/actions:** `unpurchasable_reason`: `not_listed`, `unavailable`, `whatsapp_only`.

**Errors:**
- `422 PRODUCT_NOT_PURCHASABLE` with `reason` — the same three values. An unknown, deleted, hidden or inactive-category product answers identically (`not_listed`).
- `422 QUANTITY_EXCEEDS_LIMIT` with `max_quantity`, `requested`, `current_quantity` — over the cap after merging, or an STL quantity other than 1. Nothing is clamped and the cart is unchanged.
- `422 CART_LINE_LIMIT_REACHED` with `limit` (50) — a new product in a full cart.
- `403 EMAIL_VERIFICATION_REQUIRED`, `403 CSRF_INVALID`, `429 RATE_LIMITED` (300 writes per hour per user).
- `404 NOT_FOUND` — `PATCH` or `DELETE` of a product not in the cart.
- `409 PRODUCT_ALREADY_OWNED` arrives with VS-023, not VS-022.

**Auth/CSRF/MFA:** `GET`: any signed-in user (an unverified one gets an empty cart, `id: null`). Writes: verified customer plus `X-CSRF-Token`. There is no anonymous or guest cart on the server.

**Concurrency/idempotency:** no version field. Every write locks the cart first, so two simultaneous adds of one product produce one line within the cap. Re-adding an STL already in the cart is a `200` no-op.

**Example success JSON** (`GET /api/v1/cart` after the administrator raised the physical product's price from 25.00 to 28.00 and lowered its cap from 5 to 3; captured from the application against a test database, so ids differ):

```json
{
  "id": "23fc133e-3b12-4bc9-aab7-e582a76d9f36",
  "items": [
    {
      "product_id": "31914788-f904-4529-92c8-025a05f96d46",
      "product_type": "physical",
      "name": "Dragon",
      "slug": "p-e082a5c2276f",
      "cover_image": null,
      "quantity": 4,
      "snapshot_price": {"amount_cents": 2500, "currency": "USD"},
      "current_price": {"amount_cents": 2800, "currency": "USD"},
      "price_changed": true,
      "max_quantity": 3,
      "over_cap": true,
      "purchasable": true,
      "unpurchasable_reason": null
    },
    {
      "product_id": "a3b29c43-a479-492a-b360-57ae389602e6",
      "product_type": "stl",
      "name": "Dragon (STL)",
      "slug": "p-1cfd8f64c04d",
      "cover_image": null,
      "quantity": 1,
      "snapshot_price": {"amount_cents": 900, "currency": "USD"},
      "current_price": {"amount_cents": 900, "currency": "USD"},
      "price_changed": false,
      "max_quantity": null,
      "over_cap": false,
      "purchasable": true,
      "unpurchasable_reason": null
    }
  ],
  "contains_physical": true,
  "contains_digital": true,
  "updated_at": "2026-10-16T20:10:32.118211Z"
}
```

**Example error JSON** (`POST /api/v1/cart/items` with `quantity: 2` for an STL):

```json
{
  "type": "http://localhost:8000/problems/QUANTITY_EXCEEDS_LIMIT",
  "title": "Quantity exceeds the limit",
  "status": 422,
  "detail": "At most 1 of this product fit in one cart line.",
  "instance": "/api/v1/cart/items",
  "code": "QUANTITY_EXCEEDS_LIMIT",
  "request_id": "req_04240eb351aa41dbb8a3bde69f9cca4e",
  "errors": [],
  "max_quantity": 1,
  "requested": 2,
  "current_quantity": 1
}
```

**Fixture/test account:** the seeded verified customer can fill a mixed cart with `dragon` and `dragon-stl`.

**Authoritative source/OpenAPI file:** `openapi.json` (`/api/v1/cart*`, `CartRead`, `CartLineRead`); [`../cart.md`](../cart.md).

**Notes:**
- **Lines are addressed by `product_id`, not by an item id.** A cart holds at most one line per product.
- **Adding a product already in the cart merges the quantities** and re-checks the current cap.
- `PATCH` sets the absolute quantity; it is not an increment. An STL line accepts only 1.
- Mutations return the whole `CartRead` (`DELETE` returns `204`).
- The snapshot price is display-only: checkout charges the live price and refuses a changed one until the customer accepts it ([C6](#domain--item-c6--checkout-contract)).
- Your wiring gap about `EntitlementModel.productId` disappears with the entitlement model. See [C11](#domain--item-c11--per-product-ownership-check).

### Domain / item: C6 — Checkout contract

**Status:** **built** for every cart type: STL-only online (VS-023); physical and mixed, delivery and pickup, online and cash (VS-028, 2026-10-22).

> **2026-10-22 (VS-028 review follow-up): two breaking changes to PR B's contract below.**
> - **`amount_due_cents` is now `amount_due`**, a `PriceRead` (`{amount_cents, currency}`) or `null`, on `CheckoutRead.order`, every `GET /api/v1/me/orders` item and `GET /api/v1/me/orders/{id}`. Read the currency from it, not from `total`.
> - **New error `422 CASH_NOT_AVAILABLE`, with no `reason`,** replaces `PAYMENT_METHOD_NOT_ALLOWED` (`cash_blocked`) and `CASH_PAYMENT_LIMIT_REACHED` (`open_orders`). It covers a cash block and the open-cash-order limit alike, for the account or the phone, in one identical body; show its `detail` ("Cash on delivery isn't available for this order; please pay online.") and offer online payment. `CASH_PAYMENT_LIMIT_REACHED` now only ever has `reason: order_total`.
>
> **2026-10-22 (VS-028 PR B): checkout changes.** Additive, except that `payment` may now be `null`.
> - **Request:** `fulfillment_method`, `address_id`, `contact_phone` and `accept_cash_terms` now take effect (rules below). `"cash"` is accepted for physical-only carts.
> - **Response:** `payment` is **nullable** (`null` for a cash order). `order` gains `estimated_dispatch_at`, `delivery_fee_note`, `delivery_address`, `payment_due` and `amount_due` (a `PriceRead` or `null`; cash only).
> - **Order history:** `amount_due` (a `PriceRead` or `null`) is added to every `GET /api/v1/me/orders` item and to `GET /api/v1/me/orders/{id}`: what is still due on an unpaid cash order after any cancelled line; `null` otherwise. Show it instead of `total` while `payment_due`.
> - **New errors:** `422 CASH_PAYMENT_LIMIT_REACHED` with `reason: order_total`, and `422 CASH_NOT_AVAILABLE` (no `reason`). New `PAYMENT_METHOD_NOT_ALLOWED` reasons: `cash_disabled`, `provider_not_applicable`.
> - **Reminder:** `free_shipping_threshold` is gone since 2026-10-20 (PR A, [B1](#domain--item-b1--public-settings-response-shape)); there is no shipping charge anywhere.

**Confirmed endpoint:** `POST /api/v1/checkout`. Full contract: [`../checkout.md`](../checkout.md).

**Request schema:** `CheckoutRequest` in `openapi.json`: `payment_method` (`"online"`, or `"cash"` when every line is physical), `payment_provider` (online only; defaults to the one configured), `fulfillment_method` (`"delivery"` or `"pickup"`; required with a physical line, absent for STL-only), `address_id` (delivery only, required there), `contact_phone` (pickup only, required there; any Lebanese spelling), `customer_note` (≤ 1000), `accept_terms: true`, `accept_digital_final_sale: true` (required with an STL), `accept_cash_terms: true` (required for cash), `accepted_price_changes[]` (≤ 50). Any other field, including a total or a price, is `422 VALIDATION_ERROR`. The rules apply to the lines left after already-owned STLs are dropped ([`../checkout.md`](../checkout.md) has the matrix).

**Response schema:** `201 CheckoutRead`: `order` (live prices, lines `pending`, plus `estimated_dispatch_at`, `delivery_fee_note`, `delivery_address`, `payment_due`, `amount_due`), `payment` and `dropped_lines` (`[{product_id, reason: "already_owned"}]`: STLs bought since they were added, not charged). **Online:** the order is `pending_payment` and `payment` is `{id, status: "pending", provider, redirect_url}`; send the customer to `payment.redirect_url`. **Cash:** the order is `in_progress`, `payment` is `null`, `payment_due` is `true` and `amount_due` is what the courier or the workshop collects. The contact phone is never in this response.

**Enums/statuses/actions:** `payment_method`: `"online" | "cash"`; `fulfillment_method`: `"delivery" | "pickup"` (VS-028).

**Errors:**
- `409 CART_EMPTY` (with `dropped_lines`), `409 CART_PRICE_CHANGED` (with `price_changes: [{product_id, old_amount_cents, new_amount_cents, currency}]`; nothing is charged), `409 PRODUCT_ALREADY_OWNED` (with `product_ids`), `409 IDEMPOTENCY_KEY_CONFLICT`, `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` (with `order_id`, `order_number`, `Retry-After: 2`).
- `422 PRODUCT_NOT_PURCHASABLE` / `QUANTITY_EXCEEDS_LIMIT` (with `lines: [{product_id, reason, max_quantity?}]`, every offending line), `422 INVALID_FULFILLMENT` (fields that do not fit the cart, an address that is not the customer's live one, or pickup while no pickup address is set), `422 PAYMENT_METHOD_NOT_ALLOWED` (with `reason`: `cash_requires_physical`, `cash_disabled`, `zero_total`, `provider_not_configured`, `provider_required`, `provider_not_applicable`), `422 CASH_PAYMENT_LIMIT_REACHED` (with `reason: order_total`), `422 CASH_NOT_AVAILABLE` (no `reason`: a cash block or an open cash order, for the account or the phone), `422 VALIDATION_ERROR` (a missing `accept_digital_final_sale` or `accept_cash_terms`, or an invalid `contact_phone`, points at that field).
- `429 RATE_LIMITED` (30 per user per hour; a replay counts).
- `502 PAYMENT_PROVIDER_UNAVAILABLE`: **the order exists**, unpaid (`order_id`, `order_number`); retry its payment with `POST /api/v1/me/orders/{order_id}/payments` ([C7](#domain--item-c7--payment-verification)).
- `503 ORDERS_PAUSED`, `503 ONLINE_PAYMENT_UNAVAILABLE` (an online checkout with no provider configured; cash still works).

**Auth/CSRF/MFA:** verified customer, `X-CSRF-Token`, and the `Idempotency-Key` header ([C12](#domain--item-c12--idempotency-key-mechanism)).

**Concurrency/idempotency:** see C12. The server recomputes every price and total; the client never sends an amount, except to confirm a price change it has shown the user.

**Example success JSON:** see `CheckoutRead` in `openapi.json`; the price-change body is shown under Errors.

**Example error JSON:** the RFC 9457 problem shape, with the extension members listed under Errors.

**Fixture/test account:** `scripts/dev_seed.py` (a verified customer and STL products), then `scripts/mock_pay.py` to pay ([`../checkout.md`](../checkout.md)).

**Authoritative source/OpenAPI file:** `openapi.json` (`POST /api/v1/checkout`); [ADR-032](../adr/ADR-032-checkout-idempotency-and-payment-verification.md).

**Notes:**
- **No cart id and no cart version in the body.** The server checks out the signed-in user's own cart.
- **Price changed:** show the new prices and resend with `accepted_price_changes: [{product_id, amount_cents, currency}]` and a **new** idempotency key. If the price moves again, it fails again.
- **Kill switch:** `accepting_orders` in public settings ([B1](#domain--item-b1--public-settings-response-shape)).
- **Consent wording does not exist.** The terms and digital final-sale texts are business decisions still open (SRS section 30.2). The backend stores when consent was given (and the digital-terms version), not the wording. Do not ship invented copy.
- **Cash refusals do not say why.** `CASH_NOT_AVAILABLE` is one body for a block and for an open cash order, whether the account or only the phone matched. Show its `detail` and offer online payment; never guess a reason.
- **Delivery fee:** paid to the courier on delivery; show `delivery_fee_note` as given. There is no shipping amount.

### Domain / item: C7 — Payment verification

**Status:** server-side verification **built** in VS-023 (webhook, verification after the 200, the `verify_payments` job). Payment retry **built** in VS-024 (below). The customer-facing read is VS-025: PROVISIONAL.

**Built in VS-023:** the order becomes paid only when the provider itself confirms the exact amount. Typical delay after the provider's webhook: under a second against the mock; at worst about a minute when a background task is lost. With the mock, the return page is `{frontend}/checkout/return?order=<order_number>`; a real provider's return parameters are still undecided (VS-032).

**Confirmed endpoint:** none yet. **No dedicated payment-status endpoint is planned.** The planned read is `GET /api/v1/me/orders/{order_id}` (VS-025), which will carry the order status and a payment summary. Planned retry: `POST /api/v1/me/orders/{order_id}/payments` (VS-024).

**Request schema:** provisional: none for the read. The retry needs `Idempotency-Key`.

**Response schema:** provisional: `OrderDetail` (api-endpoints.md section 30), including `payment_due`, the derived order `status` and a payment summary. The summary's field names are not written yet.

**Enums/statuses/actions:** provisional.
- Payment status: `"pending" | "processing" | "paid" | "partially_refunded" | "refunded" | "failed" | "expired"`. **There is no `cancelled` payment status.**
- Order status: `"pending_payment" | "in_progress" | "completed" | "partially_refunded" | "refunded" | "cancelled"`.

**Retry (built, VS-024):** `POST /api/v1/me/orders/{order_id}/payments`, body `PaymentRetryRequest` (`payment_provider` optional; no amount is accepted, the order's total is charged), header `Idempotency-Key` (one key per retry of one order). `201 PaymentRetryRead`: `order` (with `hold_expires_at`) and `payment` (with `redirect_url`; send the customer there). Allowed only before the checkout hold ends (30 minutes after placement by default).

**Errors:**
- `404 NOT_FOUND`: no such order, or another user's (identical bodies).
- `409 PAYMENT_ALREADY_ACTIVE`: the order already has a live attempt. **The body carries `payment_id`, `payment_status` (`"pending"` or `"processing"`) and `redirect_url`** (the live attempt's page while `pending`; `null` while `processing`, when there is nothing to resume). The field is `payment_status`, not `status`: every problem body's `status` member is the HTTP status (409), per RFC 9457. Resume with `redirect_url`, or poll the order while `processing`.
- `409 INVALID_STATE_TRANSITION` with `reason`: `cash_order`, `order_cancelled`, `order_not_payable` (already paid, or a line is no longer pending), `checkout_hold_expired`.
- **Resume or retry:** `order.hold_expires_at` in the 201 is when the job may release the order if the provider says `failed` or `expired`; show the retry action only before the hold (30 minutes after placement by default). After a release the order is `cancelled` and the customer gets an `order.checkout_expired` notification.
- **Admin payments (built, VS-024):** `GET /api/v1/admin/payments` (keyset `cursor`, `late_captured=true` for refunds to make), `GET /api/v1/admin/payments/{id}` (with `available_actions`: `reconcile`, `confirm`, `release_order`), `POST …/{id}/reconcile` (**`202`**: the result arrives later; re-read the detail), `POST …/{id}/confirm` (422 `PAYMENT_AMOUNT_MISMATCH` with `expected_amount_cents`), `POST /api/v1/admin/orders/{id}/release` (409 `grace_not_elapsed` with `release_available_at`). Full contract: [`../payment-recovery.md`](../payment-recovery.md).
- `409 IDEMPOTENCY_KEY_CONFLICT`, `409 IDEMPOTENCY_REQUEST_IN_PROGRESS`, `422 PAYMENT_METHOD_NOT_ALLOWED` (with `reason`), `422 VALIDATION_ERROR`, `429 RATE_LIMITED` (10 per user per hour; a replay counts), `502 PAYMENT_PROVIDER_UNAVAILABLE` (the new attempt failed; the order is still payable; replayed for the same key), `503 ONLINE_PAYMENT_UNAVAILABLE`.

**Auth/CSRF/MFA:** signed-in owner.

**Concurrency/idempotency:** not applicable to the read.

**Example success JSON:** none; not built.

**Example error JSON:** none; not built.

**Fixture/test account:** none possible yet. The mock provider is planned to cover every verification outcome; how a tester triggers each one is not designed.

**Authoritative source/OpenAPI file:** none yet. Plan: VS-023, VS-024, VS-025; SRS sections 9 and 20; ADR-012, ADR-024.

**Notes:**
- **The rule the frontend already follows is the right one:** the return from the provider proves nothing. Only the server's own verification makes an order paid, and the frontend learns it by reading the order.
- A customer sees success when the order status leaves `pending_payment` (to `in_progress` or `completed`). A failed or expired attempt leaves the order `pending_payment` and it can be retried, until the checkout hold ends (30 minutes by default) and the order becomes `cancelled`.
- **Undecided, so no answer exists:** the return URL and its query parameters (order id or payment id, provider parameters to strip), and the recommended polling interval, backoff, maximum duration and request timeout. They depend on the online provider, which is not chosen (SRS section 30.4). Keep `usePaymentStatusPoller` parameterised. See section 7.
- Whether a `cancelled` variant is needed in `PaymentVerificationState`: map it from the **order** status `cancelled`, not from a payment status.
- A cash order has nothing to verify: it is placed unpaid with `payment_due`.

### Domain / item: C8 — Order/order-line status enum and "available actions"

**Status:** not built. PROVISIONAL. Slices: VS-023 (enums), VS-025 (customer reads), VS-029 (admin).

**Confirmed endpoint:** none yet. Planned: `GET /api/v1/me/orders`, `GET /api/v1/me/orders/{order_id}`.

**Request schema:** provisional: list filters `status`, `placed_after`, `placed_before`; sort `-placed_at`; `cursor`, `limit`.

**Response schema:** provisional: `OrderPage`, `OrderDetail` (api-endpoints.md section 30).

**Enums/statuses/actions:** provisional; source [`../requirments/database-design.md`](../requirments/database-design.md) sections 3.6 and 3.7.
- **One shared line-status enum** for both product types, field `fulfillment_status`: `"pending" | "awaiting_delivery" | "in_production" | "ready_to_ship" | "shipped" | "delivered" | "returned" | "ready_for_pickup" | "picked_up" | "cancelled" | "refunded"`.
- Which values a line can take depends on its type and method:
  - STL: `pending`, `awaiting_delivery`, `delivered`, `refunded`, `cancelled`.
  - Physical, delivery: `pending`, `in_production`, `ready_to_ship`, `shipped`, `delivered`, `returned`, `cancelled`, `refunded`.
  - Physical, pickup: `pending`, `in_production`, `ready_for_pickup`, `picked_up`, `cancelled`, `refunded`.
- **Customers never see `in_production`.** Customer responses show it as `pending` and leave it out of the status history.
- Order status: `"pending_payment" | "in_progress" | "completed" | "partially_refunded" | "refunded" | "cancelled"`. It is derived by the server and never set directly.
- **Available actions, customer side: yes, as booleans on `OrderDetail`:** `can_cancel` and `payment_due`. Use them; do not re-derive them.
- **Available actions, admin side: decided** ([ADR-025](../adr/ADR-025-frontend-contract-decisions.md), VS-029). Every line of `AdminOrderDetail` carries `available_actions`: a list of `{target_status, cancel_reasons}` the transition endpoint would accept at read time. `cancel_reasons` is empty when no reason is taken; otherwise one of the listed reasons is required. See [P1-11](#domain--item-p1-11--admin-order-fulfillment).

**Errors:** provisional: `401`, `404 NOT_FOUND`.

**Auth/CSRF/MFA:** signed-in owner.

**Concurrency/idempotency:** not applicable (read-only).

**Example success JSON:** none; not built.

**Example error JSON:** none; not built.

**Fixture/test account:** none possible yet.

**Authoritative source/OpenAPI file:** none yet. Plan: VS-025; ADR-024 decision 8; SRS section 20.

**Notes:**
- A cash order is `in_progress` from the moment it is placed, with `payment_due: true`.
- `can_cancel` is true only while the order has a live (not cancelled) physical line, is paid or is cash, and every live physical line is still `pending`; lines the administrator already cancelled are ignored (ADR-033). STL lines are never cancelled.
- Your request for a machine-readable list of legal admin transitions is **decided: yes** ([ADR-025](../adr/ADR-025-frontend-contract-decisions.md)). The admin screens should render only the listed actions and never re-encode the state machine. Customer responses do not carry the list; customers use `can_cancel`.

### Domain / item: C11 — Per-product ownership check

**Status:** **built** (VS-023).

**Confirmed endpoint:**
- `capabilities` on `GET /api/v1/products/{slug}` ([B3](#domain--item-b3--product-detail-contract));
- `GET /api/v1/me/stl-ownership?product_id=<uuid>` (VS-023), `StlOwnershipRead` in `openapi.json`.

**Request schema:** ownership check: `product_id` query parameter, UUID, required.

**Response schema:** built: `Capabilities` in `openapi.json`, the same for every visitor. Ownership check, provisional: `200 {"product_id": "<uuid>", "owned": <bool>}` (`StlOwnershipRead` in api-endpoints.md section 30).

**Enums/statuses/actions:** not applicable.

**Errors:** provisional:
- ownership check: `401 AUTH_REQUIRED` when signed out; `422 VALIDATION_ERROR` for a missing or malformed `product_id`;
- `409 PRODUCT_ALREADY_OWNED` from `POST /api/v1/cart/items` and from checkout.

**Auth/CSRF/MFA:** ownership check: any signed-in user, verified or not; `GET`, so no CSRF header.

**Concurrency/idempotency:** the database will allow one live STL line per customer and product, so two parallel checkouts cannot both buy the same STL.

**Example success JSON:** see `capabilities` in the B3 example.

**Example error JSON:** none; not built.

**Fixture/test account:** buy an STL with the dev seed's customer and `scripts/mock_pay.py`.

**Authoritative source/OpenAPI file:** ADR-019 decision 5; ADR-022; VS-023.

**Notes:**
- **Decided** ([ADR-025](../adr/ADR-025-frontend-contract-decisions.md)): a signed-in customer asks `GET /api/v1/me/stl-ownership?product_id=` for the product on screen. Call it only when the visitor is signed in and the product is an STL; the public product response stays the same for everyone.
- `owned` is true when the customer has a paid, unrefunded STL line for the product (`awaiting_delivery` or `delivered`, not fully refunded). An unknown, hidden or physical product answers `owned: false`.
- **It is a hint, not a guarantee.** The cart still refuses a second purchase with `409 PRODUCT_ALREADY_OWNED`, and checkout refuses it too. That includes an STL held by the customer's own unpaid order, for which the check answers `owned: false`; handle the `409` as well.
- **Do not diff an entitlement list**: there is none ([C9](#domain--item-c9--entitlements--customer-library-contract)).

### Domain / item: C12 — Idempotency-Key mechanism

**Status:** built for checkout in VS-023. VS-024 (payment retry) and VS-030 (refunds) reuse it.

**Confirmed endpoint:** `POST /api/v1/checkout`. Planned on `POST /api/v1/me/orders/{order_id}/payments` and `POST /api/v1/admin/orders/{order_id}/refunds`.

**Request schema:** header **`Idempotency-Key`**, required, **generated by the client**: 8–255 characters of `[A-Za-z0-9._:-]` (a UUID v4 fits).

**Response schema:** the stored response. A replay carries the header `Idempotent-Replayed: true`.

**Enums/statuses/actions:** not applicable.

**Errors:**
- missing or malformed header: `422 VALIDATION_ERROR`;
- same key, different body: `409 IDEMPOTENCY_KEY_CONFLICT`;
- same key and body while the first request is still running (or crashed between placing the order and starting the payment): `409 IDEMPOTENCY_REQUEST_IN_PROGRESS` with `order_id`, `order_number` and `Retry-After: 2`.

**Auth/CSRF/MFA:** as the route.

**Concurrency/idempotency:**
- Same key and same body: the stored response (same status, same body), nothing new created. Only a `201` and the post-commit `502 PAYMENT_PROVIDER_UNAVAILABLE` are stored; any other refusal stores nothing, so a corrected retry with the same key runs fresh.
- Keys are scoped per user and per operation, and live 24 hours (purged daily).
- **A replay counts against the checkout rate limit** (30 per user per hour), like any other checkout request. Retry a timed-out request a few times with backoff, not in a tight loop.

**Example success JSON:** see `CheckoutRead` in `openapi.json`.

**Example error JSON:** `{"code": "IDEMPOTENCY_KEY_CONFLICT", "status": 409, ...}` (the RFC 9457 problem shape).

**Fixture/test account:** none.

**Authoritative source/OpenAPI file:** `openapi.json` (`POST /api/v1/checkout`); [ADR-032](../adr/ADR-032-checkout-idempotency-and-payment-verification.md).

**Notes:**
- **Who generates it:** the client, once per user intent (one "Place order" press and all its automatic retries).
- **Reuse after a timeout or network error:** resend with the **same** key.
- **Reuse after a `409` or after the user changes anything** (accepted prices, payment method): use a **new** key.
- `useCheckoutAttempt` and `useIdempotencyAttempt` already match this.

### Domain / item: P1-10 — Admin payments

**Status:** not built. PROVISIONAL. Slice: VS-024. Two rules in this slice are still marked "must resolve before build".

**Confirmed endpoint:** none yet. Planned:
- `GET /api/v1/admin/payments`
- `GET /api/v1/admin/payments/{payment_id}`
- `POST /api/v1/admin/payments/{payment_id}/reconcile`
- `POST /api/v1/admin/payments/{payment_id}/confirm`

**Request schema:** provisional; see api-endpoints.md section 29.14 (`ManualPaymentConfirmRequest`): `provider_reference`, `verified_amount_cents`, `evidence_note`. Reconcile has no body.

**Response schema:** provisional: `PaymentPage`, `PaymentDetail`. Field lists are not written yet.

**Enums/statuses/actions:** provisional: payment status as in [C7](#domain--item-c7--payment-verification). Provider: `mock`, `cash`, and real providers once chosen. No "available actions" list is specified.

**Errors:** provisional: `409` (wrong state), `422` (amount does not match), `502 PAYMENT_PROVIDER_ERROR`, `503 PAYMENT_VERIFICATION_UNAVAILABLE`.

**Auth/CSRF/MFA:** administrator with MFA plus `X-CSRF-Token`.

**Concurrency/idempotency:** no idempotency key on these. A duplicate success for a payment already `paid` is planned to do nothing.

**Example success JSON:** none; not built.

**Example error JSON:** none; not built.

**Fixture/test account:** none possible yet.

**Authoritative source/OpenAPI file:** none yet. Plan: VS-024; api-endpoints.md section 20; ADR-024 decision 15.

**Notes:** your questions, provisionally.
- **Reconcile blocks.** It asks the provider and returns `200 PaymentDetail` with the result. It is not queued.
- **Manual confirm's reason field** is `evidence_note`, with `provider_reference` and `verified_amount_cents`. There is **no acknowledgment field** in the body; a "yes, I checked" tick box is a frontend gate only.
- **Allowed source states for manual confirm are not final.** The plan says a live attempt (`pending` or `processing`) on an order that is not cancelled is applied, and an attempt that is no longer live records a "late capture" (an automatic refund obligation) instead of being refused. How a wrong amount is handled is one of the two unresolved rules. Do not hard-code a matrix.
- Cash payments appear in the list but are never confirmed here; they are recorded by the cash handover ([P1-11](#domain--item-p1-11--admin-order-fulfillment)).

### Domain / item: P1-11 — Admin order fulfillment

**Status:** **built** (VS-023b STL delivery, 2026-10-21; VS-029 physical lines, cash handover and cash blocks, 2026-10-23). Cancel and return actions come with VS-031 ([P1-12](#domain--item-p1-12--cancellation-and-returns)).

**Confirmed endpoints** (full reference: [`docs/fulfillment.md`](../fulfillment.md), [`docs/stl-delivery.md`](../stl-delivery.md)):
- `GET /api/v1/admin/orders` — the queue, newest first; filters `status`, `fulfillment_method`, `payment_method`, `payment_due`, `customer_id`, `order_number`, `placed_after`, `placed_before`, `limit`, `cursor`
- `GET /api/v1/admin/orders/{order_id}` — `AdminOrderDetail`
- `PATCH /api/v1/admin/orders/{order_id}` — `{ "admin_note": "..." | null }` only
- `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition` — `{ "target_status", "reason"? }`; answers `AdminOrderDetail`
- `POST /api/v1/admin/orders/{order_id}/cash-handover` — `{ "amount_cents", "currency": "USD", "note"? }`; answers `AdminOrderDetail`
- `GET /api/v1/admin/stl-deliveries` — the STL delivery queue
- `GET /api/v1/admin/cash-blocks`, `POST /api/v1/admin/cash-blocks/search` (`{ "phone", "active"?, "limit"?, "cursor"? }`), `POST /api/v1/admin/cash-blocks/{block_id}/clear`

**Schemas:** `AdminOrderPage`, `AdminOrderSummaryRead`, `AdminOrderDetail`, `AdminOrderLineRead`, `AvailableActionRead`, `AdminOrderPaymentRead`, `AdminHistoryRead`, `AdminOrderUpdate`, `CashHandoverRequest`, `CashPaymentBlockPage`, `CashPaymentBlockRead` in [`openapi.json`](openapi.json). Money is `PriceRead`. `OrderItemTransitionRequest` has no `cancel_reason` until VS-031.

**Enums/statuses/actions:** line status as in [C8](#domain--item-c8--orderorder-line-status-enum-and-available-actions). **Machine-readable actions: yes** ([ADR-025](../adr/ADR-025-frontend-contract-decisions.md)): every line carries `available_actions`, a list of `{target_status, cancel_reasons}`; `cancel_reasons` is always `[]` until VS-031.

**Errors:** `409 INVALID_STATE_TRANSITION` with `reason` (transition: `payment_required`, `cash_handover_required`, `not_a_legal_edge`, `line_closed`, `already_delivered`, `not_awaiting_delivery`, plus the line's `fulfillment_status`; handover: `not_a_cash_order`, `no_live_line`, `already_recorded`, `lines_not_ready`), `422 CASH_AMOUNT_MISMATCH` (with `amount_due`), `422 VALIDATION_ERROR`, `429 RATE_LIMITED`.

**Auth/CSRF/MFA:** administrator with MFA; writes also need `X-CSRF-Token`. A customer gets `404` on every route.

**Concurrency/idempotency:** no version field and no `Idempotency-Key`. Each transition and the handover lock the order; when two administrators act on the same state, one succeeds and the other gets `409 INVALID_STATE_TRANSITION` (a second handover: `already_recorded`). Re-read the order and render its new state.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [ADR-040](../adr/ADR-040-admin-order-queue-fulfillment-and-cash-handover.md), [ADR-039](../adr/ADR-039-stl-delivery-workflow.md), ADR-024 decisions 4, 5, 8.

**Notes:**
- Steps. Delivery: `pending → in_production → ready_to_ship → shipped → delivered`. Pickup: `pending → in_production → ready_for_pickup → picked_up`. STL: `awaiting_delivery → delivered` ("mark as sent").
- Nothing physical moves on an online order that is not paid. Unpaid online orders never appear in the queue (`status=pending_payment` is a `422`), though their detail still opens.
- A cash order's lines never reach `delivered` or `picked_up` through the transition endpoint. The **cash handover** does it for the whole order at once and records the payment; the amount entered must equal `amount_due` exactly.
- Order status cannot be patched. It is always derived.
- `TransitionAffordance` reads `available_actions`: one button per entry. A line with `[]` has no action. After a `409`, re-read the order and render the new list.
- The cash handover is an order-level action and is not in `available_actions`. Offer it when `payment_due` is true and every live line is `shipped` (delivery) or `ready_for_pickup` (pickup).
- Cash blocks never carry the phone or its hash; search by phone in the body.

### Domain / item: P1-12 — Cancellation and returns

**Status:** not built. PROVISIONAL. Slice: VS-031.

**Confirmed endpoint:** none yet. Planned, and these are the two paths you had no placeholder for:
- `POST /api/v1/me/orders/{order_id}/cancel` — customer
- `POST /api/v1/admin/orders/{order_id}/cancel` — administrator
- returns use the line-transition endpoint of [P1-11](#domain--item-p1-11--admin-order-fulfillment)

**Request schema:** provisional; see api-endpoints.md section 29.6: `CustomerOrderCancelRequest` (`reason`, optional), `AdminOrderCancelRequest` (`reason`, and `cancel_reason` when a line is `ready_to_ship` or `ready_for_pickup`).

**Response schema:** provisional: `200 OrderDetail` / `200 AdminOrderDetail`.

**Enums/statuses/actions:** provisional: `cancel_reason`: `"refused" | "no_show" | "other"`. Customer side: `can_cancel` on `OrderDetail`.

**Errors:** provisional:
- `409 ORDER_NOT_CANCELLABLE` — customer cancel when it is no longer allowed. Nothing is changed.
- `409 INVALID_STATE_TRANSITION` — admin cancel on an unpaid online order, or an illegal step.

**Auth/CSRF/MFA:** customer: verified owner plus `X-CSRF-Token`. Admin: administrator with MFA plus `X-CSRF-Token`.

**Concurrency/idempotency:** no idempotency key. The order is locked, so a cancel racing "start printing" has exactly one winner.

**Example success JSON:** none; not built.

**Example error JSON:** none; not built.

**Fixture/test account:** none possible yet.

**Authoritative source/OpenAPI file:** none yet. Plan: VS-031; api-endpoints.md sections 11 and 18; ADR-024 decisions 6 and 8.

**Notes:** your questions, provisionally.
- **Cutoff:** a customer can cancel only while **every** live (not cancelled) physical line is still `pending`, meaning printing has not started on any of them. The moment the administrator marks one line `in_production`, self-cancel closes. The customer never sees `in_production`; they see `can_cancel` turn false.
- **Customer cancel is all or nothing:** it cancels every live physical line of the order, never some. STL lines are never cancelled.
- **Race lost:** `409 ORDER_NOT_CANCELLABLE`, shared problem body, nothing changed. Re-read the order.
- **Refund after an admin cancel:** cancelling a paid line creates a pending refund of kind `cancellation` for the line's remaining balance, in the same transaction. It then sits in the refund queue ([P1-13](#domain--item-p1-13--refunds)) until the administrator pays it by hand and settles it. Cancelling an unpaid cash line creates no refund.
- A cash order refused at the door can block that customer and phone from paying cash again. The administrator can clear the block.
- Returns: `shipped → returned`, then re-ship, reprint, refund, or (unpaid cash line) cancel, all through the transition endpoint.

### Domain / item: P1-13 — Refunds

**Status:** **built** (VS-030). Decisions: [ADR-042](../adr/ADR-042-refunds-voids-and-chargebacks.md); as-built reference: [`../refunds.md`](../refunds.md).

**Confirmed endpoints** (all administrator, MFA; every POST needs `X-CSRF-Token`):
- `POST /api/v1/admin/orders/{order_id}/refunds` (`Idempotency-Key` required)
- `GET /api/v1/admin/refunds` (the obligations queue by default; `queue=false` for the history), `GET /api/v1/admin/refunds/{refund_id}`
- `POST /api/v1/admin/refunds/{refund_id}/settle`, `…/fail`, `…/void`
- `POST /api/v1/admin/refunds/{refund_id}/reissue` (`Idempotency-Key` required)
- `POST /api/v1/admin/orders/{order_id}/chargebacks` (`Idempotency-Key` required), `GET /api/v1/admin/orders/{order_id}/chargebacks`, `GET /api/v1/admin/chargebacks/{chargeback_id}`
- `POST /api/v1/admin/payments/{payment_id}/record-capture` (`Idempotency-Key` required): a dashboard capture whose amount differs, on a provider with no status API

**Request and response schemas:** `openapi.json` (`RefundCreate`, `RefundSettlementRequest`, `RefundFailureRequest`, `RefundVoidRequest`, `RefundDetail`, `RefundPage`, `ChargebackCreate`, `ChargebackDetail`, `RecordCaptureRequest`, `RecordCaptureRead`); api-endpoints.md sections 19 and 29.13.

**Enums:** refund status `"pending" | "settled" | "failed" | "voided"`; refund kind `"admin" | "cancellation" | "late_capture"`. A chargeback is its own record, not a refund kind. `RefundDetail.owed` is true for a failed refund not yet reissued.

**Errors:** `422 REFUND_EXCEEDS_AVAILABLE` (with `available.lines[]` and `available.payment_cents`), `422 REFUND_REQUIRES_CANCELLATION` (with `order_item_ids`), `409 ORDER_NOT_PAID`, `409 ORDER_TOTAL_MISMATCH`, `409 INVALID_STATE_TRANSITION` (with `reason`: `not_pending`, `not_failed`, `already_settled`, `already_reissued` plus `reissued_by_refund_id`, `line_already_refunded`, `line_already_cancelled`), and for chargebacks `409 CHARGEBACK_DUPLICATE`, `422 CHARGEBACK_NOT_ONLINE`, `422 CHARGEBACK_ITEMS_FORBIDDEN`, `422 CHARGEBACK_ALLOCATION_INVALID` (with `available`, including `chargeable_cents`). Idempotency answers as in [C12](#domain--item-c12--idempotency-key-mechanism).

**Refundable balance:** `AdminOrderDetail.refund_balance` (`lines[]` of `{order_item_id, balance_cents}`, and `payment_cents`), null until a payment reached paid. The server computes it; the form must not. `AdminOrderDetail.refunds[]` and `.chargebacks[]` list the order's records.

**Customer view:** `OrderDetail.refunds[]` (`{kind, status, amount, created_at}`, status `processing` or `refunded`); voided refunds and chargebacks are never shown.

**Notes:**
- **Every refund is manual:** record it, pay it in the provider's dashboard or in cash, then settle it. Settling changes no order or payment status.
- A refund's lines become `refunded` when the refund is created and covers them in full; a partial refund leaves a line as it is. An unfinished physical line cannot be refunded to 0: cancel it (VS-031).
- **Void** closes a mistaken pending or owed refund unpaid, with a reason. It is refused once settled, or when one of its lines is already `refunded` or `cancelled`.
- **Chargebacks** absorb the payment's open refunds (they are voided, and anything the bank did not cover stays owed as a new pending refund); the form's items add coverage on top and must total exactly what the 422's `chargeable_cents` says (the charge left, capped by what is still refundable). Production stays on `PAYMENT_PROVIDER=none` until VS-032, so chargebacks happen only in dev and staging until then.

### Domain / item: P2-1 — Captcha provider (BYI/contact)

**Status:** **built** (VS-033) for register, resend verification, the password-reset request and the contact form, and (VS-034) Bring Your Idea. Decisions: [ADR-025](../adr/ADR-025-frontend-contract-decisions.md), [ADR-026](../adr/ADR-026-captcha-refusal-and-outage.md).

**Confirmed endpoint:** `POST /api/v1/auth/register`, `/auth/resend-verification`, `/auth/password-reset/request`, `POST /api/v1/contact-messages`, `POST /api/v1/custom-requests`.

**Request schema:** a required `captcha_token` string (at most 2048 characters) in each body; see `openapi.json`.

**Response schema:** not applicable.

**Enums/statuses/actions:** not applicable.

**Errors:**
- `400 CAPTCHA_INVALID`: the token is empty, invalid, expired or already used. Reset the widget and let the user try again. On the three auth routes the answer is the same whatever the email address.
- `422 VALIDATION_ERROR`: the `captcha_token` field is missing, like any other required field.
- `503 SERVICE_UNAVAILABLE` with `Retry-After: 30`: Turnstile could not be reached. Nothing was stored or sent; try again later. The backend never lets a request through without a verdict.

**Auth/CSRF/MFA:** public; no cookie, no CSRF.

**Concurrency/idempotency:** a token is single-use. Get a new one for every submission, including a retry after an error.

**Example success JSON:** not applicable.

**Example error JSON:** `POST /api/v1/auth/register` with a refused token

```json
{
  "type": "http://localhost:8000/problems/CAPTCHA_INVALID",
  "title": "Captcha refused",
  "status": 400,
  "detail": "The captcha token is empty, invalid, expired or already used.",
  "instance": "/api/v1/auth/register",
  "code": "CAPTCHA_INVALID",
  "request_id": "req_44889cea7ca64f9590306a4c1e1658bc",
  "errors": []
}
```

Turnstile unreachable (`POST /api/v1/contact-messages`; header `Retry-After: 30`):

```json
{
  "type": "http://localhost:8000/problems/SERVICE_UNAVAILABLE",
  "title": "Service temporarily unavailable",
  "status": 503,
  "detail": "Captcha verification is temporarily unavailable. Retry later.",
  "instance": "/api/v1/contact-messages",
  "code": "SERVICE_UNAVAILABLE",
  "request_id": "req_aab135d768354fedb08b45b349346507",
  "errors": []
}
```

**Fixture/test account:** a local backend with `CAPTCHA_PROVIDER=fake` accepts exactly one token, `XXXX.DUMMY.TOKEN.XXXX`. That is the token Cloudflare's public test site key (`1x00000000000000000000AA`) issues, so a development frontend using that key works unchanged. The fake refuses every other token.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [ADR-026](../adr/ADR-026-captcha-refusal-and-outage.md).

**Notes:**
- **Vendor: Cloudflare Turnstile.** The backend's secret is `TURNSTILE_SECRET`. Site keys are public and belong in the frontend's configuration; none exist yet for staging or production.
- **Release together.** On the three auth routes this is a breaking change: a request without `captcha_token` is now refused. Ship the widget in the same release.
- The backend does not check Turnstile's `action` or `hostname`, so the widget needs no `action` value.

### Domain / item: P2-2 — Bring-Your-Idea submission

**Status:** **built** (VS-034). Decisions: [ADR-030](../adr/ADR-030-bring-your-idea-submission.md); behaviour: [`../custom-requests.md`](../custom-requests.md).

**Confirmed endpoint:** `POST /api/v1/custom-requests`

**Request schema:** one `multipart/form-data` request (`openapi.json`, the request body of `POST /api/v1/custom-requests`):
- `name`: 1-100 characters after trimming.
- `email`.
- `phone` (required): up to 32 characters of digits, spaces and `+ ( ) . -`, with at least 6 digits.
- `project_title`: 1-200 characters after trimming.
- `description`: 1-5000 characters after trimming; line breaks allowed.
- `preferred_material`, `preferred_colour` (optional): up to 100 characters, free text.
- `dimensions` (optional): up to 200 characters, free text.
- `captcha_token` (required).
- `attachments`: the file part name, **without brackets**, repeated once per image. Parts under any other name (`attachments[]` included) are ignored, so the images would be silently lost. 0 to 5 images, each a JPEG, PNG or WebP of at most 10 MB (40 MP). The type is read from the content; the filename and `Content-Type` are ignored. **Leave the part out when there are no images**: a blank file part is `422`.

An empty text part counts as absent: an empty optional field is stored as none, an empty required field is `422 VALIDATION_ERROR`. That includes an empty `captcha_token`, which here is `422`, not `400` as on the JSON forms.

**Response schema:** `201 CustomRequestReceipt`: `id` and `created_at`. No attachment URL is ever returned: attachments are administrator-only.

**Enums/statuses/actions:** none on the public side.

**Errors**, in the order they are checked:
1. `429 RATE_LIMITED` with `Retry-After`: 20 attempts per hour per IP, counted before the body is read.
2. `422 UPLOAD_REJECTED`: the request is over 5 × 10 MB + 64 KiB or has no `Content-Length`.
3. `422 VALIDATION_ERROR` for a field; `422 UPLOAD_REJECTED` for more than 5 files or a file over 10 MB. Nothing is verified or counted yet, so the captcha token is not spent.
4. `400 CAPTCHA_INVALID` and `503 SERVICE_UNAVAILABLE` ([P2-1](#domain--item-p2-1--captcha-provider-byicontact)).
5. `429 RATE_LIMITED`: 5 accepted requests per hour per IP and 5 per hour per email address.
6. Per file: `422 MALWARE_DETECTED`, then `422 UPLOAD_REJECTED` (not a real image). A scanner outage is `503 SERVICE_UNAVAILABLE`.

`UPLOAD_REJECTED` and `MALWARE_DETECTED` from a file name it in `errors[0].loc` as `["body", "attachments", <index>]`, counting from 0. Any refusal keeps nothing: no request, no file.

**Auth/CSRF/MFA:** public; no cookie, no CSRF. A signed-in user may use it too; the request is not linked to their account.

**Concurrency/idempotency:** none. Sending the same form twice stores two requests.

**Example success JSON:**

```json
{
  "id": "0b6f3c1e-5e2a-4f4e-9a57-3f8d2c1b7a90",
  "created_at": "2026-10-17T09:12:44.018231Z"
}
```

**Example error JSON:** a PDF sent as the second file:

```json
{
  "type": "http://localhost:8000/problems/UPLOAD_REJECTED",
  "title": "Upload rejected",
  "status": 422,
  "detail": "not a JPEG, PNG or WebP image",
  "instance": "/api/v1/custom-requests",
  "code": "UPLOAD_REJECTED",
  "request_id": "req_6c5da7aa03be4e2d889c824b709aa50d",
  "errors": [
    {"loc": ["body", "attachments", 1], "msg": "not a JPEG, PNG or WebP image", "type": "value_error"}
  ]
}
```

**Fixture/test account:** use the fake captcha token from P2-1. Locally `SCANNER=fake` accepts anything but the EICAR test string.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [`../custom-requests.md`](../custom-requests.md); api-endpoints.md sections 7.2 and 29.9.

**Notes:**
- **Scanning is synchronous.** The `201` arrives after every file is scanned, re-encoded and stored.
- Each active administrator gets an in-app notification of type `custom_request` ([P2-5](#domain--item-p2-5--notifications)).
- Reference images are deleted 90 days after submission (the `custom_request_attachment_retention` setting).

### Domain / item: P2-3 — Contact form

**Status:** **built** (VS-033).

**Confirmed endpoint:** `POST /api/v1/contact-messages`

**Request schema:** `ContactMessageCreate` in `openapi.json`:
- `name`: 1-100 characters after trimming.
- `email`.
- `phone` (optional): up to 32 characters of digits, spaces and `+ ( ) . -`, with at least 6 digits.
- `subject` (optional): up to 200 characters; a blank one counts as none.
- `message`: 1-5000 characters after trimming; line breaks allowed.
- `captcha_token` (required).

Unknown fields are refused.

**Response schema:** `201 ContactMessageReceipt`: `id` and `created_at`.

**Enums/statuses/actions:** none on the public side.

**Errors:**
- `400 CAPTCHA_INVALID` and `503 SERVICE_UNAVAILABLE` ([P2-1](#domain--item-p2-1--captcha-provider-byicontact)).
- `422 VALIDATION_ERROR`: a field is invalid. Fields are checked before the captcha, so the token is not spent.
- `429 RATE_LIMITED` with `Retry-After`: 60 attempts per hour per IP (checked first), then 5 accepted messages per hour per IP and 5 per hour per email address. A refused captcha does not count against the 5.

**Auth/CSRF/MFA:** public; no cookie, no CSRF. A signed-in user may use it too; the message is not linked to their account.

**Concurrency/idempotency:** none. Sending the same form twice stores two messages.

**Example success JSON:**

```json
{
  "id": "62efe9ca-af5a-40d8-82c9-88461b333e42",
  "created_at": "2026-10-14T22:06:50.371388Z"
}
```

**Example error JSON:** see [P2-1](#domain--item-p2-1--captcha-provider-byicontact) and [C1](#domain--item-c1--rfc-9457-field-level-validation-error-shape).

**Fixture/test account:** use the fake captcha token from P2-1.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); api-endpoints.md sections 7.2 and 29.9.

**Notes:** validation errors use the shape in [C1](#domain--item-c1--rfc-9457-field-level-validation-error-shape).

### Domain / item: P2-4 — Admin contact queue

**Status:** **built** (VS-033).

**Confirmed endpoint:**
- `GET /api/v1/admin/contact-messages`
- `GET /api/v1/admin/contact-messages/{message_id}`
- `PATCH /api/v1/admin/contact-messages/{message_id}`

**Request schema:** list query parameters are `status`, `created_after` (inclusive), `created_before` (exclusive; both need a UTC offset), `email` (exact, case-insensitive), `cursor` and `limit` (1-100, default 20). `ContactMessageAdminUpdate` is `{"status": ...}`, and nothing else is accepted.

**Response schema:** `ContactMessagePage` (`items`, `next_cursor`); `ContactMessageDetail`. List rows carry every field, including name, email and message.

**Enums/statuses/actions:** `"new" | "read" | "replied" | "archived"`. The status only moves forward, and steps may be skipped: `new` can go straight to `archived`. Sending the current status changes nothing and answers `200`.

**Errors:** `404 NOT_FOUND`, `403 CSRF_INVALID` (PATCH), `409 INVALID_STATE_TRANSITION` (a backward move), `422 VALIDATION_ERROR` (bad query, cursor or body).

**Auth/CSRF/MFA:** administrator with MFA; `PATCH` also needs `X-CSRF-Token`.

**Concurrency/idempotency:** a status change locks the row and is checked against the current status. If another administrator has moved it further, you get `409`; re-read the message.

**Example success JSON:** `GET /api/v1/admin/contact-messages?status=new&limit=1`

```json
{
  "items": [
    {
      "id": "62efe9ca-af5a-40d8-82c9-88461b333e42",
      "name": "Rima Haddad",
      "email": "rima@example.com",
      "phone": "+961 3 123 456",
      "subject": "Bulk keychains",
      "message": "Can you print 40 keychains?",
      "status": "new",
      "created_at": "2026-10-14T22:06:50.371388Z",
      "updated_at": "2026-10-14T22:06:50.371388Z"
    }
  ],
  "next_cursor": null
}
```

**Example error JSON:** moving a `replied` message back to `read`

```json
{
  "type": "http://localhost:8000/problems/INVALID_STATE_TRANSITION",
  "title": "Contact message status cannot move backwards",
  "status": 409,
  "detail": "A replied message cannot become read.",
  "instance": "/api/v1/admin/contact-messages/62efe9ca-af5a-40d8-82c9-88461b333e42",
  "code": "INVALID_STATE_TRANSITION",
  "request_id": "req_b5489b90fe104a59a3e88ae749a8f9b8",
  "errors": []
}
```

**Fixture/test account:** the seeded administrator; submit a message through the public form first.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); api-endpoints.md section 24.

**Notes:**
- There is no create and no delete on the admin side. Archive a message to clear it from the working queue.
- The default order is `new` first, then `read`, `replied`, `archived`, and oldest first within each status. Use `status=new` for an inbox view.
- Opening a message does not mark it read; send the `PATCH`.
- The administrator replies outside the system (email or phone) and then sets the status to `replied`.

### Domain / item: P2-7 — Turnstile field contract

**Status:** **built** (VS-033); see [P2-1](#domain--item-p2-1--captcha-provider-byicontact) for errors, the outage answer and the development token.

**Confirmed endpoint:** `POST /api/v1/auth/register`, `/auth/resend-verification`, `/auth/password-reset/request`.

**Request schema:** see `openapi.json`: `RegisterRequest` (`email`, `password`, `captcha_token`), `ResendVerificationRequest` and `PasswordResetRequest` (`email`, `captcha_token`).

**Response schema:** unchanged: `202 RegistrationAccepted` / `202 PasswordResetAccepted`.

**Enums/statuses/actions:** none.

**Errors:** `400 CAPTCHA_INVALID`, `422 VALIDATION_ERROR` (field missing), `503 SERVICE_UNAVAILABLE`, `429 RATE_LIMITED`.

**Auth/CSRF/MFA:** public.

**Concurrency/idempotency:** a token is single-use.

**Example success JSON:** not applicable.

**Example error JSON:** see [P2-1](#domain--item-p2-1--captcha-provider-byicontact).

**Fixture/test account:** the fake token from P2-1.

**Authoritative source/OpenAPI file:** [`openapi.json`](openapi.json); [ADR-026](../adr/ADR-026-captcha-refusal-and-outage.md).

**Notes:**
- The captcha is checked before any account lookup and refuses the same way whatever the email, so these routes stay enumeration-safe.
- **Breaking change:** a request without `captcha_token` is now refused. Ship the widget in the same release.
- Login, email verification and password-reset confirmation take no captcha.

---

## 5. Test accounts and fixtures

Your nine items, in order. "Seed" means [`scripts/dev_seed.py`](../../scripts/dev_seed.py); how to run it is in [A2](#domain--item-a2--local-backend-startup).

| # | You asked for | Answer |
|---|---|---|
| 1 | Working local email delivery | **Workaround confirmed.** The file-based adapter is not built. Read links from `email_outbox` with the worker stopped ([A3](#domain--item-a3--test-account-and-fixture-provisioning)). The seeded customer is already verified, so most flows need no email. |
| 2 | One disposable administrator with MFA enrolled | **Provided by the seed.** `seed-admin@example.com`; the password, TOTP secret and recovery codes are printed once when you run it. |
| 3 | One physical product, priced | **Provided by the seed**: six physical products. There is no stock quantity anywhere; "in stock" is `is_available: true`. `knight` is seeded unavailable. |
| 4 | One STL product with a clean, published asset version | **Changed by ADR-019.** Asset versions do not exist. The seed provides three STL products (`dragon-stl`, `phone-stand-stl`, `low-poly-vase-stl`); that is everything an STL product is. |
| 5 | One STL entitlement granted to the test customer | **Removed by ADR-019.** Entitlements do not exist. Ownership will be a paid STL order line, which cannot exist before VS-023. No fixture is possible today. |
| 6 | One seeded shipping zone | **Removed by ADR-024.** There are no shipping zones and no free-shipping threshold. |
| 7 | A way to trigger each mock-payment outcome | **Not possible yet.** No payment code exists. A mock provider covering every verification outcome is part of VS-023; how a tester selects an outcome has not been designed. Provisional. |
| 8 | A mixed cart (one physical, one STL) | **Possible (VS-022).** Sign in as the seeded verified customer and add `dragon` and `dragon-stl`. Checking it out waits for VS-028. |
| 9 | Seeded orders in several fulfillment states | **Not possible yet.** There are no order tables until VS-023, so nothing can be seeded even directly in the database. The seed will grow with each slice. |

What you can test end to end today, against a real backend: registration, email verification, resend, login, the administrator MFA login, refresh, logout, `/me`, password reset, notifications, the whole public storefront (settings, lists, filters, search, suggestions, product pages), and the admin screens for settings, users, categories, materials, colours, products and product images.

Against [`MINIMUM-MANUAL-TEST-UNLOCK.md`](../frontend-requests/MINIMUM-MANUAL-TEST-UNLOCK.md):

| Level | Status |
|---|---|
| 1 — Real public storefront | **Unlocked now.** B1 to B4 are answered and the seed provides the catalogue. One gap: images need the `/media` workaround in B4. |
| 2 — Real customer account | **Unlocked now.** Password reset (FVS-004) is unlocked too: P2-6 is built. |
| 3 — Real purchase flow | **Blocked on the backend.** C1 and C2 are answered. C3 is built (VS-026). C5, C6, C7, C8 and C12 are not built. C4 is removed. |
| 4 — Real admin operations | **Partly unlocked.** P1-1 to P1-7 are built: admin login with MFA, settings, customers, reference data, products, images. P1-10 to P1-13 are not built. P1-8 and P1-9 are removed. |

---

## 6. Corrections to "confirmed" items in the request

The request lists some things as already confirmed that are not true of the backend. Each is explained in its block; this is the list in one place.

| The request says | Actually |
|---|---|
| `GET /api/v1/shipping-zones` is confirmed (C4, C6) | Removed by ADR-024. It does not exist. |
| `GET /api/v1/me/entitlements` is confirmed (C9) | Removed by ADR-019. It does not exist. |
| `GET /api/v1/me/downloads` is confirmed (C10) | Removed by ADR-019. It does not exist. |
| `POST /api/v1/admin/users/{user_id}/entitlements` is confirmed (P1-9) | Removed by ADR-019. It does not exist. |
| `GET /api/v1/cart`, `POST /api/v1/checkout`, `/api/v1/me/addresses*`, `GET /me/orders/{id}` are confirmed (C3, C5, C6, C7) | The paths are planned and unchanged. `/me/addresses*` is built (VS-026); the others are not, and answer `404` today. |
| Cart lines are addressed by `{item_id}` (C5) | Planned as `{product_id}`. |
| URL filter keys `category`, `material`, `colour` are the wire names (B2) | The API takes `category_id`, `material_id`, `colour_id`, as UUIDs, one value each. |
| Turnstile is confirmed for register and resend (P2-6, P2-7) | **Built** (VS-033): register, resend and the reset request require `captcha_token` ([P2-7](#domain--item-p2-7--turnstile-field-contract)). |
| Password reset fields are unconfirmed (P2-6) | Built since VS-004 and fully specified. |
| The admin settings list endpoint is unconfirmed (P1-3) | Built: `GET /api/v1/admin/settings`. |
| Admin user detail and update paths are unconfirmed (P1-4) | Built. |
| Admin product and image paths are placeholders (P1-6, P1-7) | Built; the real paths are in the blocks and in `openapi.json`. |
| A free-shipping threshold exists (B1, C6, fixtures) | Removed by ADR-024. The field is still returned, always `null`, until VS-028 deletes it. |
| "Digital refund revokes entitlement" is confirmed policy (P1-13) | There is no entitlement. A fully refunded STL line becomes `refunded`; a file already emailed cannot be recalled. |
| Refunds have a manual-versus-provider distinction and a shipping part (P1-13) | Every refund is manual, and there is no shipping to refund (ADR-024). |
| Routes `/account/library` and `/account/downloads` | Have nothing to show. Remove them. |
| Products have stock (B3, fixtures) | No stock exists. Products are made to order; use `is_available`. |

---

## 7. Open questions

These are not backend gaps to be filled by reading code. Each needed a decision, most of them from the product owner. Three were decided on 2026-10-14 and are recorded in [ADR-025](../adr/ADR-025-frontend-contract-decisions.md); the rest are still open, so nobody should build on a guess.

| # | Question | Blocks | Status |
|---|---|---|---|
| 1 | Should admin order responses list the legal next actions for each line? (C8, P1-11) | FVS-030, FVS-031 | **Decided:** yes. Every line of `AdminOrderDetail` carries `available_actions` (`{target_status, cancel_reasons}`), built in VS-029. |
| 2 | Should a signed-in customer be able to see "you own this STL" before pressing "add to cart"? (C11) | FVS-014, FVS-025 | **Decided:** yes, through `GET /api/v1/me/stl-ownership?product_id=` (`{product_id, owned}`), built in VS-023. The cart still refuses a second purchase. |
| 3 | Payment return URL, its query parameters, and the polling interval, backoff, maximum duration and timeout (C7). | FVS-027 | Partly answered (VS-023): with the mock, `{frontend}/checkout/return?order=<order_number>`; verification typically completes within a second of the provider's webhook, at worst about a minute. A real provider's parameters stay open (SRS section 30.4) |
| 4 | Which online payment provider: Whish, a card gateway, or both (SRS section 30.4). | FVS-026, FVS-027 | Open. Product owner, before VS-032 |
| 5 | Idempotency key lifetime and required format (C12). | FVS-026, FVS-032 | **Answered (VS-023):** 24 hours; 8–255 characters of `[A-Za-z0-9._:-]`; a replay counts against the 30/hour checkout limit |
| 6 | Where the refundable balance per line is returned (P1-13). | FVS-032 | Answered (VS-030): `AdminOrderDetail.refund_balance` |
| 7 | Captcha vendor, and whether captcha also covers registration, resend and password reset (P2-1, P2-7; SRS SEC-12). | FVS-002, FVS-004, FVS-015, FVS-016 | **Decided:** Cloudflare Turnstile on register, resend verification, the password-reset request, contact and Bring Your Idea; VS-033 builds the captcha port and applies it to all five. Built in VS-033: a refused token is `400 CAPTCHA_INVALID`, an outage `503 SERVICE_UNAVAILABLE` ([ADR-026](../adr/ADR-026-captcha-refusal-and-outage.md)). |
| 8 | Consent wording: terms, digital final sale, cash terms (C6; SRS section 30.2). | FVS-026 | Open. Product owner; legal text |
| 9 | STL delivery-time promise shown on product pages and at checkout (C10; SRS section 30.2). | FVS-014, FVS-026 | Open. Product owner |
| 10 | Can the default address be deleted, and what becomes default afterwards (C3). | FVS-023 | **Answered (VS-026, ADR-027):** yes; no address becomes default afterwards |
| 11 | Bring Your Idea attachment limits and the wire name of the file field (P2-2). | FVS-015 | Open. Backend, in VS-034 |
| 12 | Should `/me` return an explicit `mfa_completed` flag (P1-1)? Not needed, but the frontend may prefer it. | FVS-005 | Open. Frontend to request if wanted |
| 13 | An administrator account without MFA, to test the enrolment screens (P1-2). There is no API to create one. | FVS-005 | Open. Backend owner, on request |
