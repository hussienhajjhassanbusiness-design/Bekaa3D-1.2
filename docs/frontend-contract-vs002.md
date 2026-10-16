# Frontend contract — VS-002 (registration, email verification, resend)

**Audience:** the frontend team. **Status:** authoritative for the code at commit
`05e2b08` (`main`, 2026-10-01). Where this document and older docs disagree, this
one describes what the server actually does; the disagreements worth knowing are
listed in [§9](#9-inconsistencies-and-surprises). The SRS still wins on what the
server *should* do — anything in §9 that is a real defect is flagged for the
backend, not for you to work around silently.

## How this was produced

- Every rule below was read from the code (file references in [§10](#10-source-references)),
  then confirmed by real HTTP requests.
- Every "Request / Response" block is a **real captured exchange**, not a
  hand-written example. They were captured against an isolated instance: a
  Docker image built from commit `05e2b08`, its own PostgreSQL 16 and Redis 7,
  `ENVIRONMENT=development`, `BASE_URL=http://localhost:8100` (the dev stack
  uses port `8000`), `FRONTEND_BASE_URL=http://localhost:3000`,
  `EMAIL_PROVIDER=console`. Libraries: FastAPI 0.141.1, Pydantic 2.13.5,
  email-validator 2.3.0, uvicorn 0.54.0.
- Presentation only: the `date` and `server` response headers are omitted,
  JSON bodies are pretty-printed, and string values over 160 characters are
  shortened with `…(+N chars)`. Nothing else is edited. `x-request-id` and
  `ratelimit-*` values are exactly what the server sent.
- Two things were done to the test instance that a real client cannot do, and
  are called out where they apply: rate-limit counters in Redis were cleared
  between scenarios (otherwise the 5/hour budget runs out after five
  requests), and for the *expired token* case the token's `expires_at` was
  moved into the past in the database (the alternative is waiting 24 hours).
  The 2-minute resend cooldown was **not** simulated — the capture really
  waited it out.

---

## 1. Quick reference

| | Register | Verify email | Resend verification |
|---|---|---|---|
| Method + path | `POST /api/v1/auth/register` | `POST /api/v1/auth/verify-email` | `POST /api/v1/auth/resend-verification` |
| Body | `{"email", "password"}` | `{"token"}` | `{"email"}` |
| Success | `202` + `{"message": …}` | `204`, empty body | `202` + `{"message": …}` |
| Auth / cookies | none needed, none set | none needed, none set | none needed, none set |
| CSRF header | not required | not required | not required |
| Errors | `400`, `422`, `429` | `400 INVALID_TOKEN`, `410 RESOURCE_EXPIRED`, `422`, `429` | `400`, `422`, `429` |
| Rate limit | 5 / hour / IP | 20 / hour / IP | 5 / hour / IP |
| Min response time | ~300 ms (deliberate) | none (~25–100 ms) | ~300 ms (deliberate) |

---

## 2. Global conventions

### 2.1 Paths

- The backend exposes these routes at exactly `/api/v1/auth/register`,
  `/api/v1/auth/verify-email` and `/api/v1/auth/resend-verification`. There is
  no other prefix: no `root_path`, no `servers` entry in the OpenAPI document,
  no gateway rewriting. `GET /openapi.json` lists them under the same paths.
- `/auth/register` and `/api/auth/register` are `404`. A trailing slash is
  answered with a `307` redirect (see [§9](#9-inconsistencies-and-surprises) —
  never send one).
- All three are `POST`-only. Any other method is `405` with `Allow: POST`.

Request:

```http
POST /auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-np-c67cbb@example.com",
  "password": "correct horse"
}
```

Response (took 24 ms):

```http
HTTP/1.1 404 Not Found
x-request-id: req_a312bc032f194e08af11da7b04173cad
content-length: 234
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/NOT_FOUND",
  "title": "Request cannot be completed",
  "status": 404,
  "detail": "Not Found",
  "instance": "/auth/register",
  "code": "NOT_FOUND",
  "request_id": "req_a312bc032f194e08af11da7b04173cad",
  "errors": []
}
```

Request:

```http
POST /api/v1/auth/register/ HTTP/1.1
Content-Type: application/json

{
  "email": "fe-slash-c67cbb@example.com",
  "password": "correct horse"
}
```

Response (took 5 ms):

```http
HTTP/1.1 307 Temporary Redirect
content-length: 0
location: http://localhost:8100/api/v1/auth/register
x-request-id: req_dc35986b700a4377b4b5910e14684c35
```

### 2.2 Request format

- Send `Content-Type: application/json` and a JSON object body. **This is not
  optional.** A body sent as `text/plain` — which is what `fetch` does by
  default when `body` is a string and you set no header — or with no
  `Content-Type` at all is **not parsed** and is rejected with a confusing
  `422` at `loc: ["body"]`:

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: text/plain;charset=UTF-8

{
  "email": "fe-tp-c67cbb@example.com",
  "password": "correct horse"
}
```

Response (took 310 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_e72777cfbd10458390372da846b60672
content-length: 409
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_e72777cfbd10458390372da846b60672",
  "errors": [
    {
      "loc": [
        "body"
      ],
      "msg": "Input should be a valid dictionary or object to extract fields from",
      "type": "model_attributes_type"
    }
  ]
}
```

- Unknown fields are rejected (`extra="forbid"`), so do not send extra keys
  such as `password_confirmation` or `name`.
- Body that is not valid JSON at all → `400 MALFORMED_REQUEST`; valid JSON
  with bad fields → `422 VALIDATION_ERROR`.

### 2.3 Error format (RFC 9457)

Every error from every endpoint is `Content-Type: application/problem+json`
with exactly these keys:

| Key | Type | Meaning |
|---|---|---|
| `type` | string (URI) | `{BASE_URL}/problems/{code}`. **Does not resolve** (it is a `404`); treat it as an identifier. |
| `title` | string | Short human summary. English, may change. |
| `status` | integer | Same as the HTTP status. |
| `detail` | string | Longer human text. English, may change. |
| `instance` | string | The request path. |
| `code` | string | **Stable machine code. Branch on this.** |
| `request_id` | string | Same value as the `X-Request-ID` response header. |
| `errors` | array | Field-level errors; `[]` when not a validation error. |

Each item of `errors` is `{"loc": [...], "msg": string, "type": string}`:

- `loc` is a path starting with `"body"`, then the field name — e.g.
  `["body", "password"]`. Map `loc[1]` to your form field. (For a JSON syntax
  error the second element is the character offset, an integer.)
- `type` is Pydantic's error type (`missing`, `string_too_short`,
  `string_too_long`, `string_type`, `value_error`, `extra_forbidden`,
  `model_attributes_type`, `json_invalid`). Stable enough to branch on.
- `msg` is library-generated English, sometimes prefixed `"Value error, "`.
  Show your own copy; do not display or parse `msg`.
- One response carries **all** field errors at once (see the combined
  bad-email-and-password example in §3.4).

One complete real example (a `422` from register):

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-short-c67cbb@example.com",
  "password": "1234567"
}
```

Response (took 307 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_7827f80ba3464410bb9ebab87557bdf6
content-length: 388
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_7827f80ba3464410bb9ebab87557bdf6",
  "errors": [
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

Codes these three endpoints can return: `VALIDATION_ERROR` (422),
`MALFORMED_REQUEST` (400), `INVALID_TOKEN` (400, verify only),
`RESOURCE_EXPIRED` (410, verify only), `RATE_LIMITED` (429),
`METHOD_NOT_ALLOWED` (405), `NOT_FOUND` (404), and — for infrastructure
failures on any route — `SERVICE_UNAVAILABLE` (503, safe to retry later) and
`INTERNAL_ERROR` (500).

### 2.4 Request ID

- Response header **`X-Request-ID`** is on every response, success or error,
  and equals `request_id` in problem bodies.
- You may send your own `X-Request-ID`. It is echoed back if it matches
  `^[A-Za-z0-9._-]{1,128}$`; anything else is silently replaced with a
  server-generated `req_<32 hex>`. Useful for correlating E2E test failures
  with API logs.

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json
X-Request-ID: fe-test.123

{
  "email": "fe-rid-c67cbb@example.com"
}
```

Response (took 319 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 4
ratelimit-reset: 3600
x-request-id: fe-test.123

{
  "message": "If eligible, a verification email has been sent."
}
```

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json
X-Request-ID: has space

{
  "email": "fe-rid2-c67cbb@example.com"
}
```

Response (took 326 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 3
ratelimit-reset: 3600
x-request-id: req_ca100b77cfd5440e8329abc8e86c439e

{
  "message": "If eligible, a verification email has been sent."
}
```

### 2.5 CORS — there is none

**The API has no CORS middleware.** A browser preflight is answered `405`
with no `Access-Control-*` headers, and a simple cross-origin request gets a
normal response with no `Access-Control-Allow-Origin`, which the browser then
hides from your code. In practice: **a page on `http://localhost:3000` cannot
call `http://localhost:8000` directly.**

Request:

```http
OPTIONS /api/v1/auth/register HTTP/1.1
Origin: http://localhost:3000
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

Response (took 327 ms):

```http
HTTP/1.1 405 Method Not Allowed
allow: POST
x-request-id: req_42f8c6773aea4cf486f2cc13be7ca927
content-length: 268
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/METHOD_NOT_ALLOWED",
  "title": "Request cannot be completed",
  "status": 405,
  "detail": "Method Not Allowed",
  "instance": "/api/v1/auth/register",
  "code": "METHOD_NOT_ALLOWED",
  "request_id": "req_42f8c6773aea4cf486f2cc13be7ca927",
  "errors": []
}
```

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json
Origin: http://localhost:3000

{
  "email": "fe-cors-c67cbb@example.com"
}
```

Response (took 315 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 2
ratelimit-reset: 3599
x-request-id: req_6ce65fd7b1694958bb67d075007fba14

{
  "message": "If eligible, a verification email has been sent."
}
```

What to do today: serve the frontend and the API from **one origin**. In
development, proxy `/api/*` from the frontend dev server to
`http://localhost:8000` (Vite `server.proxy`, Next.js `rewrites`, etc.) and
call relative URLs (`/api/v1/auth/register`). This is also what the cookie
design assumes (SameSite=Lax, refresh cookie scoped to `/api/v1/auth`), so it
is the arrangement least likely to break in later slices. If the team needs
true cross-origin calls, that is a backend change (allowed origins,
`allow_credentials`) and should be requested, not worked around. See
[§9](#9-inconsistencies-and-surprises).

### 2.6 Cookies and CSRF (for later slices; VS-002 uses neither)

VS-002's three endpoints need no cookies, set no cookies, and require no CSRF
header. For the slices that follow (captured from `POST /api/v1/auth/login`):

| Cookie | `HttpOnly` | `Path` | `Max-Age` | `SameSite` | Purpose |
|---|---|---|---|---|---|
| `access_token` | yes | `/` | 900 (15 min) | Lax | Session JWT |
| `refresh_token` | yes | `/api/v1/auth` | 2592000 (30 d) | Lax | Rotated by `POST /api/v1/auth/refresh` |
| `csrf_token` | **no** (JS-readable) | `/` | 2592000 (30 d) | Lax | Double-submit value |

- `Secure` is off only when `ENVIRONMENT=development`; in **any** other
  environment the cookies are `Secure` and are dropped by browsers over plain
  `http`. A staging site on `http://` will look like "login succeeds but
  nothing is logged in".
- Unsafe cookie-authenticated requests (logout, refresh, `PATCH`/`POST` on
  `/me/...`, admin writes) must send header **`X-CSRF-Token`** with the current
  value of the `csrf_token` cookie. Missing/wrong → `403 CSRF_INVALID`.
- Use `credentials: "same-origin"` (the `fetch` default) with the same-origin
  proxy above; `"include"` only matters if you ever go cross-origin.

### 2.7 Rate-limit headers

Rate-limited routes return, on **2xx and 429 responses only**:

| Header | Value |
|---|---|
| `RateLimit-Limit` | requests allowed per window |
| `RateLimit-Remaining` | requests left in this window |
| `RateLimit-Reset` | **seconds** until the window resets (integer) |
| `Retry-After` | **429 only**; integer **seconds** (delta-seconds form, never an HTTP date); always equal to `RateLimit-Reset` |

`400`/`422` responses carry **no** `RateLimit-*` headers even though they
consume budget (§6).

### 2.8 Deliberately slow responses

Register and resend (and password-reset request) never answer faster than
~300 ms, on every branch, including validation errors. This is an
anti-enumeration control (SEC-06): it stops response time revealing whether
an address has an account. It is not a performance bug; do not "fix" it with
optimistic UI that assumes an instant answer, and do not set client timeouts
below a second or two. Measured on the capture run (ms):

- register, new address: 317, 306, 325, 307 — existing unverified address: 326, 328, 304, 318
- resend, unknown: 322, 322, 307 — verified: 305, 323, 305 — unverified in cooldown: 322, 320, 321

---

## 3. `POST /api/v1/auth/register`

### 3.1 Request

| Field | Type | Required | Rules |
|---|---|---|---|
| `email` | string | yes | Valid address per `email-validator` (no DNS check). Total ≤ **254** characters; part before `@` ≤ **64 octets** (UTF-8). Special-use domains are rejected — email-validator's list is `arpa`, `invalid`, `local`, `localhost`, `onion`, `test` (`.test` captured below); `example.com` is accepted. No control characters. Leading/trailing whitespace is stripped. The domain is lowercased on storage; the local part keeps its case, but lookups are case-insensitive, so `Ann@x.com` and `ann@x.com` are the same account. |
| `password` | string | yes | See §3.2. |

No other fields are accepted.

### 3.2 Password rules — exact

- **Length 8 to 256, counted in Unicode code points** of the string as sent
  (Python `len`), *before* any normalisation.
  - JavaScript's `password.length` counts UTF-16 code units, so it disagrees
    for characters outside the BMP (most emoji): `"🔒".length === 2` but the
    server counts 1. Validate client-side with **`[...password].length`** (or
    `Array.from(password).length`).
  - A combining sequence counts as its parts: `"é"` typed as `e` + U+0301
    is 2 code points, precomposed `é` (U+00E9) is 1. Captured below: seven
    precomposed `é` is rejected; four decomposed `é` (8 code points) is
    accepted.
- **No composition rules.** No required digits, cases or symbols (a deliberate
  V1 decision, BR-120). No breached-password or common-password check.
  8 spaces is a valid password.
- **Whitespace is significant and not trimmed.** Leading/trailing spaces are
  part of the password.
- **Control characters are rejected** (U+0000–U+001F and U+007F), including
  tab and newline → `422`, `type: "value_error"`.
- Must be a JSON string (a number is `422 string_type`).
- **Unicode normalisation:** the server applies **NFKC** before hashing (and
  before comparing at login). So precomposed and decomposed `é` are the same
  password, and so are compatibility forms (e.g. full-width `Ａ` and `A`, the
  ligature `ﬁ` and `fi`). The client should send exactly what was typed and
  must not normalise or trim.

### 3.3 Success

`202 Accepted`, body always exactly
`{"message": "If eligible, a verification email has been sent."}`.

It **never logs the user in and never sets a cookie**: no `Set-Cookie` header
appears in any captured register response, and `GET /api/v1/me` right after
registering is `401 AUTH_REQUIRED`. After registering, send the user to a
"check your email" screen; they log in separately (an unverified account
*can* log in — see §9).

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-new-c67cbb@example.com",
  "password": "correct horse"
}
```

Response (took 322 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 4
ratelimit-reset: 3600
x-request-id: req_f69c8046f8a945149bde45c527021aa5

{
  "message": "If eligible, a verification email has been sent."
}
```

Request:

```http
GET /api/v1/me HTTP/1.1
```

Response (took 6 ms):

```http
HTTP/1.1 401 Unauthorized
x-request-id: req_9cfe8d45eca54ae4b309f2cea902bff1
content-length: 270
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/AUTH_REQUIRED",
  "title": "Authentication required",
  "status": 401,
  "detail": "A valid session is required for this request.",
  "instance": "/api/v1/me",
  "code": "AUTH_REQUIRED",
  "request_id": "req_9cfe8d45eca54ae4b309f2cea902bff1",
  "errors": []
}
```

**Same response for new and existing addresses.** Registering an address that
already exists — unverified or verified — returns the identical `202` body,
status and header set; only `x-request-id` and `RateLimit-*` counters differ,
and those depend on how many requests you have made, not on the account.
Timing is equalised (§2.8). What happens server-side (invisible to you):

| Address state | Effect |
|---|---|
| new | account created (unverified); verification email queued |
| exists, unverified, last email ≥ 2 min ago | new verification email queued (password in the request is **ignored**) |
| exists, unverified, last email < 2 min ago | nothing |
| exists, verified | nothing |

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-new-c67cbb@example.com",
  "password": "different pass"
}
```

Response (took 315 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 3
ratelimit-reset: 3599
x-request-id: req_92045c8b2b6448d9914289a36935a4c7

{
  "message": "If eligible, a verification email has been sent."
}
```

(The capture confirmed the repeat created no second outbox row, and that an
upper-cased copy of the address resolved to the same single account.)

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "FE-NEW-C67CBB@EXAMPLE.COM",
  "password": "correct horse"
}
```

Response (took 321 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 2
ratelimit-reset: 3599
x-request-id: req_4702d1698a8e4b2d843d9fc56a739acc

{
  "message": "If eligible, a verification email has been sent."
}
```

### 3.4 Validation errors

Bad email:

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "not-an-email",
  "password": "correct horse"
}
```

Response (took 326 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_8c65e6523a3b47988841cbaa7ee435ee
content-length: 413
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_8c65e6523a3b47988841cbaa7ee435ee",
  "errors": [
    {
      "loc": [
        "body",
        "email"
      ],
      "msg": "value is not a valid email address: An email address must have an @-sign.",
      "type": "value_error"
    }
  ]
}
```

Bad password (too short, shown in §2.3), too long:

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-long-c67cbb@example.com",
  "password": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx…(+217 chars)"
}
```

Response (took 305 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_a9db0f09d82841a180c34da9c990d2c3
content-length: 388
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_a9db0f09d82841a180c34da9c990d2c3",
  "errors": [
    {
      "loc": [
        "body",
        "password"
      ],
      "msg": "String should have at most 256 characters",
      "type": "string_too_long"
    }
  ]
}
```

Both at once — one response, one entry per field:

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "nope",
  "password": "short"
}
```

Response (took 327 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_047dde9528f2460fb95a7534c68b9929
content-length: 516
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_047dde9528f2460fb95a7534c68b9929",
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

Other captured variants:

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-miss-c67cbb@example.com"
}
```

Response (took 321 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_d405785802fb4173b9292c03b6f0a6e7
content-length: 353
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_d405785802fb4173b9292c03b6f0a6e7",
  "errors": [
    {
      "loc": [
        "body",
        "password"
      ],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-extra-c67cbb@example.com",
  "password": "correct horse",
  "name": "Ann"
}
```

Response (took 305 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_94e1b2d46c144dadb91ce3c516a663bc
content-length: 373
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_94e1b2d46c144dadb91ce3c516a663bc",
  "errors": [
    {
      "loc": [
        "body",
        "name"
      ],
      "msg": "Extra inputs are not permitted",
      "type": "extra_forbidden"
    }
  ]
}
```

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-ctl-c67cbb@example.com",
  "password": "correct\thorse"
}
```

Response (took 317 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_48c4db7462d444df9f07d3a12b9c57d8
content-length: 391
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_48c4db7462d444df9f07d3a12b9c57d8",
  "errors": [
    {
      "loc": [
        "body",
        "password"
      ],
      "msg": "Value error, must not contain control characters",
      "type": "value_error"
    }
  ]
}
```

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-dt-c67cbb@foo.test",
  "password": "correct horse"
}
```

Response (took 327 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_53b3e1960ad645fcb240665f2e707c06
content-length: 467
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_53b3e1960ad645fcb240665f2e707c06",
  "errors": [
    {
      "loc": [
        "body",
        "email"
      ],
      "msg": "value is not a valid email address: The part after the @-sign is a special-use or reserved name that cannot be used with email.",
      "type": "value_error"
    }
  ]
}
```

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa@example.com",
  "password": "correct horse"
}
```

Response (took 328 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_cd7b39cd76c24f89b5df43930e4a35fe
content-length: 409
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_cd7b39cd76c24f89b5df43930e4a35fe",
  "errors": [
    {
      "loc": [
        "body",
        "email"
      ],
      "msg": "Value error, the part before '@' must be at most 64 octets (RFC 5321)",
      "type": "value_error"
    }
  ]
}
```

Also captured (outputs shortened here): a 255-character address →
`422`, `msg: "value is not a valid email address: The email address is too
long (1 character too many)."`; a 254-character address → `202`; a
256-character password → `202`; eight `🔒` → `202`; four decomposed `é` →
`202`; seven precomposed `é` → `422 string_too_short`; eight spaces → `202`;
`" pad@example.com "` → `202`, stored as `pad@example.com`;
`Mixed.Case@EXAMPLE.COM` → stored as `Mixed.Case@example.com`.

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-uni7-c67cbb@example.com",
  "password": "ééééééé"
}
```

Response (took 317 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_b3a5f11cf7ea49d88887e530c017f08e
content-length: 388
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_b3a5f11cf7ea49d88887e530c017f08e",
  "errors": [
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

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-uni4-c67cbb@example.com",
  "password": "éééé"
}
```

Response (took 323 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 3
ratelimit-reset: 3600
x-request-id: req_4f61f7c873b444c3b7f18d33340c2076

{
  "message": "If eligible, a verification email has been sent."
}
```

Malformed JSON:

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{"email": 
```

Response (took 305 ms):

```http
HTTP/1.1 400 Bad Request
x-request-id: req_554c64d3b9ef41589aa694f44aa38337
content-length: 355
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/MALFORMED_REQUEST",
  "title": "Request body could not be parsed",
  "status": 400,
  "detail": "The request body is not valid JSON.",
  "instance": "/api/v1/auth/register",
  "code": "MALFORMED_REQUEST",
  "request_id": "req_554c64d3b9ef41589aa694f44aa38337",
  "errors": [
    {
      "loc": [
        "body",
        10
      ],
      "msg": "JSON decode error",
      "type": "json_invalid"
    }
  ]
}
```

### 3.5 Rate limited (429)

5 requests per hour per client IP, **counting every request that reaches
validation — including `422`s**. Below: five requests with invalid bodies,
then a valid sixth is refused. Once the limit is hit, even a request with
invalid fields gets `429` (the limit is checked before field validation — captured separately with curl: `{"email":"bad","password":"x"}` after the limit → `429`, `retry-after: 3598`);
only a body that is not JSON at all still gets `400`.

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "bad",
  "password": "x"
}
```

Response (took 311 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_7913a76355934291856f5eaf15c920d1
content-length: 516
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/register",
  "code": "VALIDATION_ERROR",
  "request_id": "req_7913a76355934291856f5eaf15c920d1",
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

Request:

```http
POST /api/v1/auth/register HTTP/1.1
Content-Type: application/json

{
  "email": "fe-rl-c67cbb@example.com",
  "password": "correct horse"
}
```

Response (took 305 ms):

```http
HTTP/1.1 429 Too Many Requests
ratelimit-limit: 5
ratelimit-remaining: 0
ratelimit-reset: 3598
retry-after: 3598
x-request-id: req_4df829a507fa48f988ad2c1f6628abd2
content-length: 265
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/RATE_LIMITED",
  "title": "Too many requests",
  "status": 429,
  "detail": "Rate limit exceeded. Try again later.",
  "instance": "/api/v1/auth/register",
  "code": "RATE_LIMITED",
  "request_id": "req_4df829a507fa48f988ad2c1f6628abd2",
  "errors": []
}
```

---

## 4. `POST /api/v1/auth/verify-email`

### 4.1 The link in the email

The verification email links to the **frontend**, never the API, with the
token in the URL **fragment**:

```text
{FRONTEND_BASE_URL}/verify-email#token={token}
```

Shape of the capture's outbox row, token redacted (a real one is 43 URL-safe base64 characters) (`FRONTEND_BASE_URL=http://localhost:3000`):

```text
http://localhost:3000/verify-email#token=<TOKEN>
```

- Route: `/verify-email` on the frontend. Parameter: `token`, in the
  **fragment** (`#`), not the query (`?`). Browsers never send a fragment to
  any server, so the token stays out of access logs and `Referer` headers.
- The token is `secrets.token_urlsafe(32)`: **43 characters** of
  `[A-Za-z0-9_-]`, no padding, no URL-encoding needed.
- Read it with `new URLSearchParams(location.hash.slice(1)).get("token")`.
  Recommended: then remove it from the address bar
  (`history.replaceState(null, "", location.pathname)`) so it does not linger
  in history or get shared by copy-paste.
- Do **not** verify automatically on page load without guarding against
  double execution (React StrictMode, remounts): the second `POST` of the same
  token returns `400`, and if it wins the race your UI shows an error for a
  successful verification. Send it once.
- Valid for **24 hours** from issue. The full email payload the backend queues
  (template `verification_email`) is
  `{"token": "<TOKEN>", "expires_at": "2026-10-01T21:56:55.053992+00:00", "verification_url": "http://localhost:3000/verify-email#token=<TOKEN>"}`.

### 4.2 Request

| Field | Type | Required | Rules |
|---|---|---|---|
| `token` | string | yes | ≤ 128 characters (longer → `422`). Empty string is allowed by the schema and answered `400 INVALID_TOKEN`. Send the token only — not the whole URL. |

### 4.3 Responses

| Situation | Status | `code` |
|---|---|---|
| valid, unused, unexpired token for an unverified account | `204` | — |
| unknown token (typo, truncated, whole URL pasted, empty) | `400` | `INVALID_TOKEN` |
| token already used | `400` | `INVALID_TOKEN` |
| unused, unexpired token, but the account is **already verified** (e.g. an older link from before a resend) | `400` | `INVALID_TOKEN` |
| token past its 24 h window | `410` | `RESOURCE_EXPIRED` |
| token purged by retention (VS-046: 7 days past expiry by default) | `400` | `INVALID_TOKEN` |
| missing / too-long / non-string `token` | `422` | `VALIDATION_ERROR` |
| over 20 requests/hour from this IP | `429` | `RATE_LIMITED` |

The `400` cases are **indistinguishable** by design — same status, code,
title and detail. Verification does **not** log the user in and sets no
cookies. If the user already has a session, the change is visible
immediately through `GET /api/v1/me` (`email_verified: true`); no refresh or
re-login is needed, but any `email_verified` you cached from the login
response is now stale.

Suggested UI mapping: `204` → "Email verified — log in"; `400` → "This link is
invalid or has already been used. If you already verified, just log in;
otherwise request a new link"; `410` → "This link has expired" + resend form.

Success (`204`, empty body — note the misleading `content-type` header, §9):

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{
  "token": "<TOKEN>"
}
```

Response (took 52 ms):

```http
HTTP/1.1 204 No Content
content-type: application/json
ratelimit-limit: 20
ratelimit-remaining: 19
ratelimit-reset: 3600
x-request-id: req_f905ef8d535a4aaebf697ded33ceb91b
```

Invalid (unknown) token:

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{
  "token": "LGb8jK2QfVXAv38ypilK1Y65tMkvNVleDFawk97HvEw"
}
```

Response (took 25 ms):

```http
HTTP/1.1 400 Bad Request
x-request-id: req_a30368a150bc4e839d697e9c51d3a303
content-length: 301
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/INVALID_TOKEN",
  "title": "Verification link invalid",
  "status": 400,
  "detail": "This verification link is invalid or has already been used.",
  "instance": "/api/v1/auth/verify-email",
  "code": "INVALID_TOKEN",
  "request_id": "req_a30368a150bc4e839d697e9c51d3a303",
  "errors": []
}
```

Already-used token (the same token as the success above, sent again):

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{
  "token": "<TOKEN>"
}
```

Response (took 42 ms):

```http
HTTP/1.1 400 Bad Request
x-request-id: req_66863573c1f3422e879390e718a017f2
content-length: 301
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/INVALID_TOKEN",
  "title": "Verification link invalid",
  "status": 400,
  "detail": "This verification link is invalid or has already been used.",
  "instance": "/api/v1/auth/verify-email",
  "code": "INVALID_TOKEN",
  "request_id": "req_66863573c1f3422e879390e718a017f2",
  "errors": []
}
```

Expired token — *the token's `expires_at` was moved 1 second into the past in
the test database before this request*; a real expired token behaves the same
because the check is `now >= expires_at`. The account stayed unverified, and
repeating the request gives the same `410`:

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{
  "token": "fSG69BYDY1tsrhv165HkGtez5bIPlGO5eC_gjXpTMgk"
}
```

Response (took 28 ms):

```http
HTTP/1.1 410 Gone
x-request-id: req_9f3351a0f6e0456db1396a24c64f236a
content-length: 302
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/RESOURCE_EXPIRED",
  "title": "Verification link expired",
  "status": 410,
  "detail": "This verification link has expired. Request a new one.",
  "instance": "/api/v1/auth/verify-email",
  "code": "RESOURCE_EXPIRED",
  "request_id": "req_9f3351a0f6e0456db1396a24c64f236a",
  "errors": []
}
```

Already-verified user using a fresh link. The account was registered (link
1), a resend after the real 2-minute cooldown issued link 2, link 1 was then
used successfully, and link 2 — unused and unexpired — was submitted:

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{
  "token": "yt7FE91jdJMah95uC74Wdl_JBayl4oqFTH216rqGY10"
}
```

Response (took 103 ms):

```http
HTTP/1.1 204 No Content
content-type: application/json
ratelimit-limit: 20
ratelimit-remaining: 19
ratelimit-reset: 3600
x-request-id: req_d11ec21085844138a6f1a8feaa9736f2
```

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{
  "token": "hG1skrI5CMARYzTBUdol6WPnHzUEdU25SJ4NvSgnFZY"
}
```

Response (took 33 ms):

```http
HTTP/1.1 400 Bad Request
x-request-id: req_ce15e28538254f2491ba83748d74e8ff
content-length: 301
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/INVALID_TOKEN",
  "title": "Verification link invalid",
  "status": 400,
  "detail": "This verification link is invalid or has already been used.",
  "instance": "/api/v1/auth/verify-email",
  "code": "INVALID_TOKEN",
  "request_id": "req_ce15e28538254f2491ba83748d74e8ff",
  "errors": []
}
```

(Afterwards link 2 is still recorded as unused; the request was refused and
rolled back. Note also that link 1 kept working after link 2 was issued — a
resend does not invalidate earlier links; see §9.)

Validation errors:

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{
  "token": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

Response (took 26 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_5ab71a018e9646a8b424537bfd639b40
content-length: 389
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/verify-email",
  "code": "VALIDATION_ERROR",
  "request_id": "req_5ab71a018e9646a8b424537bfd639b40",
  "errors": [
    {
      "loc": [
        "body",
        "token"
      ],
      "msg": "String should have at most 128 characters",
      "type": "string_too_long"
    }
  ]
}
```

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{}
```

Response (took 28 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_17d891758fde4ae081acacb357ce2d9d
content-length: 354
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/verify-email",
  "code": "VALIDATION_ERROR",
  "request_id": "req_17d891758fde4ae081acacb357ce2d9d",
  "errors": [
    {
      "loc": [
        "body",
        "token"
      ],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

Rate limited (21st request in the hour; the previous 20 were `400`s, which
count):

Request:

```http
POST /api/v1/auth/verify-email HTTP/1.1
Content-Type: application/json

{
  "token": "nope"
}
```

Response (took 28 ms):

```http
HTTP/1.1 429 Too Many Requests
ratelimit-limit: 20
ratelimit-remaining: 0
ratelimit-reset: 3599
retry-after: 3599
x-request-id: req_3db00350ffc445078b3ef08abdfa8dcf
content-length: 269
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/RATE_LIMITED",
  "title": "Too many requests",
  "status": 429,
  "detail": "Rate limit exceeded. Try again later.",
  "instance": "/api/v1/auth/verify-email",
  "code": "RATE_LIMITED",
  "request_id": "req_3db00350ffc445078b3ef08abdfa8dcf",
  "errors": []
}
```

---

## 5. `POST /api/v1/auth/resend-verification`

### 5.1 Request

| Field | Type | Required | Rules |
|---|---|---|---|
| `email` | string | yes | Same rules as register's `email` (§3.1). |

No other fields. No cookie or CSRF header needed (a logged-in user may call it
too; the session is ignored — the address in the body decides).

### 5.2 Success — always the same

`202 Accepted` with the identical body register uses:
`{"message": "If eligible, a verification email has been sent."}`.

A new email is queued **only** when the address belongs to an unverified
account whose most recent verification email was issued **≥ 2 minutes** ago.
In every other case — unknown address, verified account, inside the cooldown —
nothing happens and the response is the same.

**Enumeration-safety evidence** (all from the capture run):

- Unknown, verified, and unverified-in-cooldown addresses all returned `202`,
  the same body, and the same header set (`content-type`, `ratelimit-limit`,
  `ratelimit-remaining`, `ratelimit-reset`, `x-request-id`).
- Timing was flat across the three (§2.8): 305–323 ms.
- Outbox row counts confirmed the server-side difference is real but hidden:
  the unverified account had 1 row after the in-cooldown resend and 2 rows
  after the resend at ~122 s; the verified account stayed at 1.

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json

{
  "email": "fe-nobody-c67cbb@example.com"
}
```

Response (took 306 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 3
ratelimit-reset: 3599
x-request-id: req_b869f14081894aa0969a41eec202ea3f

{
  "message": "If eligible, a verification email has been sent."
}
```

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json

{
  "email": "fe-new-c67cbb@example.com"
}
```

Response (took 317 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 2
ratelimit-reset: 3599
x-request-id: req_01287feb2f8c472ebe4c8a3078ba2a2f

{
  "message": "If eligible, a verification email has been sent."
}
```

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json

{
  "email": "fe-resend-c67cbb@example.com"
}
```

Response (took 323 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 4
ratelimit-reset: 3600
x-request-id: req_684c568768904fb68d7f63dc071e1b62

{
  "message": "If eligible, a verification email has been sent."
}
```

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json

{
  "email": "fe-resend-c67cbb@example.com"
}
```

Response (took 321 ms):

```http
HTTP/1.1 202 Accepted
content-length: 62
content-type: application/json
ratelimit-limit: 5
ratelimit-remaining: 3
ratelimit-reset: 3596
x-request-id: req_56b77126c7f14cf39a818b344fad545c

{
  "message": "If eligible, a verification email has been sent."
}
```

### 5.3 Cooldown

- **Exactly 2 minutes** (`RESEND_COOLDOWN = timedelta(minutes=2)`), per
  account, measured from the creation time of that account's most recent
  verification token (issued by register *or* resend). Captured: a resend at
  ~118 s created no email; one at ~122 s did.
- Configured as a **code constant** in
  `src/app/identity/application/services/verification.py` — not an
  environment variable and not an admin setting. The 24 h token lifetime
  (`VERIFICATION_TOKEN_TTL`) is in the same file.
- The cooldown is **silent**: the API never tells you it is active. Disable
  the "resend" button client-side for 2 minutes after a register or resend,
  and word the confirmation as "If your account needs verifying, we've sent a
  new link".

### 5.4 Rate limited (429)

5 requests per hour per IP, all outcomes counted. `Retry-After` is in
**seconds** and counts down to the end of the fixed window — up to 3600 s.
Captured: the 6th request got `Retry-After: 3598`, a 7th three seconds later
got `3595`.

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json

{
  "email": "fe-nx-c67cbb@example.com"
}
```

Response (took 307 ms):

```http
HTTP/1.1 429 Too Many Requests
ratelimit-limit: 5
ratelimit-remaining: 0
ratelimit-reset: 3598
retry-after: 3598
x-request-id: req_c610847ead6543009ac5f98280a24bb7
content-length: 276
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/RATE_LIMITED",
  "title": "Too many requests",
  "status": 429,
  "detail": "Rate limit exceeded. Try again later.",
  "instance": "/api/v1/auth/resend-verification",
  "code": "RATE_LIMITED",
  "request_id": "req_c610847ead6543009ac5f98280a24bb7",
  "errors": []
}
```

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json

{
  "email": "fe-nx-c67cbb@example.com"
}
```

Response (took 307 ms):

```http
HTTP/1.1 429 Too Many Requests
ratelimit-limit: 5
ratelimit-remaining: 0
ratelimit-reset: 3595
retry-after: 3595
x-request-id: req_7d363db8afd049f99c14e09e6751d54d
content-length: 276
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/RATE_LIMITED",
  "title": "Too many requests",
  "status": 429,
  "detail": "Rate limit exceeded. Try again later.",
  "instance": "/api/v1/auth/resend-verification",
  "code": "RATE_LIMITED",
  "request_id": "req_7d363db8afd049f99c14e09e6751d54d",
  "errors": []
}
```

Validation error:

Request:

```http
POST /api/v1/auth/resend-verification HTTP/1.1
Content-Type: application/json

{
  "email": "x@"
}
```

Response (took 308 ms):

```http
HTTP/1.1 422 Unprocessable Content
x-request-id: req_c004db439eb44fa1b7fcce651d2e9f2c
content-length: 428
content-type: application/problem+json

{
  "type": "http://localhost:8100/problems/VALIDATION_ERROR",
  "title": "Request body failed validation",
  "status": 422,
  "detail": "One or more fields failed validation.",
  "instance": "/api/v1/auth/resend-verification",
  "code": "VALIDATION_ERROR",
  "request_id": "req_c004db439eb44fa1b7fcce651d2e9f2c",
  "errors": [
    {
      "loc": [
        "body",
        "email"
      ],
      "msg": "value is not a valid email address: There must be something after the @-sign.",
      "type": "value_error"
    }
  ]
}
```

---

## 6. Rate-limit rules per endpoint

All limits are **fixed windows keyed by client IP only** (not by email),
stored in Redis. The window starts at the first request from that IP and lasts
the full period; `Retry-After`/`RateLimit-Reset` report the time left in it.
Every request that reaches the limiter counts, **including ones answered 400
`INVALID_TOKEN` or 422** — only a body that is not valid JSON is rejected
before the limiter runs. Configured as constants at the top of
`src/app/identity/api/auth.py`.

| Endpoint | Limit | Notes |
|---|---|---|
| `POST /api/v1/auth/register` | 5 / 3600 s | plus the silent 2-min per-account email cooldown |
| `POST /api/v1/auth/verify-email` | 20 / 3600 s | |
| `POST /api/v1/auth/resend-verification` | 5 / 3600 s | plus the silent 2-min per-account email cooldown |
| `POST /api/v1/auth/login` (VS-003) | 20 / 3600 s | plus per-(email, IP) throttle: 3 free failures, then growing delay up to 8 s, lockout for 15 min at the 10th → `429 RATE_LIMITED`, `Retry-After: 900` |
| `POST /api/v1/auth/refresh` (VS-003) | 60 / 3600 s | |
| `POST /api/v1/auth/password-reset/request` (VS-004) | 5 / 3600 s | |
| `POST /api/v1/auth/password-reset/confirm` (VS-004) | 20 / 3600 s | |

Implications:

- Five register attempts that fail client-visible validation lock that IP out
  of registering for up to an hour. **Mirror the §3 rules client-side** so
  invalid forms are never submitted.
- Everyone behind one public IP (office, campus, carrier-grade NAT on mobile)
  shares one budget.
- Automated tests will hit these limits almost immediately; see §7.3.

---

## 7. Getting the verification email in local development and automated tests

### 7.1 What exists today

- **Email adapter:** the only implemented provider is `console`
  (`EMAIL_PROVIDER=console`). It does **not** print the email: by design it
  logs only the payload's *keys*, and the log pipeline also redacts the
  recipient. A real line from the worker:

  ```text
  info  console_email_send  payload_keys=['expires_at', 'token', 'verification_url'] template=verification_email to=[redacted-email]
  ```

  So the console output cannot give you a token or link.
- **Outbox table:** register/resend insert a row in `email_outbox`
  (`template = 'verification_email'`) whose JSONB `payload` holds `token`,
  `verification_url` and `expires_at` **in plaintext while the row is
  `pending`**. The worker's `dispatch_outbox` job runs every minute at
  second `:00` (batch of 20), "sends" through the console adapter, marks the
  row `sent`, and **redacts** the payload to
  `{"token": "[redacted]", "expires_at": "[redacted]", "verification_url": "[redacted]"}`.
  With the normal dev stack running, a test therefore has between 0 and 60
  seconds to read the token — a race it will lose intermittently.

**Conclusion: there is no clean way today.** There is a workable one, below;
nothing was built for this document.

### 7.2 Workable today, zero backend changes

In the stack used for automated frontend tests, **stop the worker** so nothing
redacts, then read the link straight from PostgreSQL:

```sh
docker compose stop worker

# latest verification link for an address (domain is stored lower-cased;
# the column is case-insensitive CITEXT, so any case matches)
docker compose exec -T postgres psql -U bekaa3d -d bekaa3d -Atc \
  "select payload->>'verification_url' from email_outbox
   where recipient_email = 'e2e-123@example.com' and template = 'verification_email'
   order by created_at desc limit 1"
```

Or from a Node test with `pg`, connecting to `localhost:5442` (the dev
stack's host port) with the `.env` database credentials. The query is
available the moment the `202` arrives: the outbox row commits before the
response is sent.

Costs and caveats: tests need database credentials and depend on the
`email_outbox` table layout (a backend-internal detail that may change without
notice); the worker must stay stopped for the run (nothing else in VS-002
needs it); use addresses on a non-reserved domain such as `example.com`
(`.test` is rejected, §3.1); and clear rate limits between tests (§7.3).

### 7.3 Rate limits in automated tests

With only five registrations per hour per IP, an E2E suite must reset the
counters, e.g. before each test:

```sh
docker compose exec -T redis sh -c \
  "redis-cli --scan --pattern 'ratelimit:*' | xargs -r redis-cli DEL"
```

This clears every `ratelimit:*` key (all endpoints) and nothing else — never
`FLUSHALL` a Redis that also holds sessions, MFA challenges and the job
queue.

### 7.4 Proposal (not built): file-based mail capture

**Recommended smallest safe option: a `file` email provider.**

- New adapter `FileEmailProvider` behind the existing `EmailProviderPort`:
  each "sent" message is written as one JSON file
  (`{to, template, payload, sent_at}`) into `EMAIL_CAPTURE_DIR`, via write-to-
  temp-then-rename so a reader never sees half a file. Tests poll that
  directory (bind-mounted, e.g. `./storage/mail_capture`, git-ignored) for the
  newest file addressed to their recipient.
- **Impossible to enable in production:** a Pydantic validator on `Settings`
  refuses to construct settings when `EMAIL_PROVIDER=file` and `ENVIRONMENT`
  is not in an **allowlist** of `{"development", "test"}` — so both the API
  and the worker fail to boot. An allowlist, not `!= "production"`, because
  `ENVIRONMENT` is a free string and `prod` or `staging` would slip past a
  denylist. The worker already resolves the provider at startup
  (`app/worker.py`), so a misconfiguration is loud, not silent.
- Exercises the real path (register → outbox → worker → provider), so tests
  also catch outbox regressions, and the token-redaction behaviour stays
  exactly as in production.
- Downside: delivery waits for the worker's next minute tick, so a test waits
  up to ~60 s per email. Acceptable for a handful of E2E flows; if not, a
  follow-up can let dev/test run the dispatch cron more often.
- **Cost:** roughly half a day including review — about 40 lines of
  production code (adapter, factory branch, settings validator), about 80 lines
  of tests (writer, factory, and "refuses to boot outside the allowlist" for
  both `production` and an arbitrary value), plus `.env.example`,
  `docker-compose.yml` volume, `.gitignore` and README lines. No migration, no
  new dependency, no new HTTP surface.

**Not recommended: a dev-only HTTP endpoint** (e.g.
`GET /api/v1/dev/outbox?email=`). It would be faster for tests, but
password-reset emails go through the same outbox, so an endpoint that is
accidentally mounted in production is not a leak of verification links — it
is **account takeover of any user**. Its guard would be one conditional
`include_router`, and it would still race the worker's redaction unless the
worker is stopped, which is what §7.2 already does without the risk. Similar
cost (~half a day) for more danger.

---

## 8. Frontend checklist

- Call `/api/v1/auth/...` on the **same origin** (dev proxy); no CORS exists.
- Always send `Content-Type: application/json`; never send extra fields; no
  trailing slashes.
- Validate client-side before submit: email shape and ≤ 254 chars; password
  `[...pw].length` between 8 and 256, no control characters. Every rejected
  submit burns rate-limit budget.
- Branch on `status` + `code`; map `errors[].loc[1]` to fields; ignore `msg`,
  `title`, `detail` for logic.
- Treat register/resend `202` as "maybe sent"; never claim an email was sent
  or that an account exists.
- Throttle the resend button for 2 minutes in the UI.
- Read the token from the fragment, POST it once, strip it from the URL.
- Do not call `.json()` on a `204`.
- On `429`, read `Retry-After` (seconds) and show a wait, not a retry loop.
- Expect ~300 ms minimum on register and resend.

---

## 9. Inconsistencies and surprises

Things likely to confuse a frontend developer, or that look like backend
issues. Items marked **(backend)** are worth a ticket; none were changed here.

1. **No CORS at all (backend decision needed).** Preflight → `405`. Only a
   same-origin setup works. Nothing in the SRS or `api-endpoints.md` states
   the intended deployment topology or allowed origins, so whether the
   frontend will be same-origin in production is an open question to settle
   now, before later slices bake in an assumption.
2. **`fetch` without `Content-Type` fails with an unhelpful error.**
   `422`, `loc: ["body"]`, `type: model_attributes_type`, "Input should be a
   valid dictionary…" — not "wrong content type".
3. **Validation failures consume the rate limit, and the limit is checked
   before validation.** Five bad register submits → locked out for up to an
   hour; after that even the error messages stop and every submit is `429`.
   `400`/`422` responses also omit `RateLimit-*` headers, so the client cannot
   see the budget draining.
4. **Fixed one-hour window.** `Retry-After` can be close to `3600`; it is not a
   short back-off. Keyed by IP only, while `api-endpoints.md` (Public Forms)
   says "rate limits by IP/email".
5. **(backend, before deployment) Per-IP limits behind a proxy.** The limiter
   keys on the TCP peer address. uvicorn only trusts `X-Forwarded-For` from
   `127.0.0.1` by default, and the planned nginx will be a separate container,
   so once it is in front of the API **every user will share one bucket**
   (5 registrations per hour for the whole site) unless
   `--forwarded-allow-ips`/`FORWARDED_ALLOW_IPS` is configured. Not visible in
   local dev.
6. **Password length is counted in code points, before NFKC.** JS
   `.length` disagrees for emoji; and because normalisation happens after the
   length check, a password that is 8 code points as typed can be shorter
   after normalisation (four decomposed `é` → four characters) — the effective
   minimum is slightly below 8 for such input. Harmless in practice, but the
   rule is "8 code points as sent", not "8 characters".
7. **All-whitespace passwords are accepted; nothing is trimmed** in passwords
   (emails are trimmed). The UI should not trim either, or login will fail
   for users who typed a trailing space at registration.
8. **Resend does not invalidate earlier links.** After a resend, *both* the
   old and the new link verify the account (each valid 24 h). Whichever is
   used second returns `400 "invalid or has already been used"` even though
   that link was never used — the account is simply already verified.
9. **An expired link for an already-verified account returns `410` "expired —
   request a new one"**, not `400`, because expiry is checked before the
   account state. Following that advice sends a resend that silently does
   nothing (verified accounts get no email). The `410` screen should also say
   "already verified? log in".
10. **Already-verified and bogus links are indistinguishable** (`400
    INVALID_TOKEN` for both). The frontend cannot tell a user "you're already
    verified" from a verify response.
11. **Unverified accounts can log in** (VS-003): `POST /api/v1/auth/login`
    returns `200`, sets cookies, and `email_verified: false`. The "verified
    boundary" is enforced per action (cart, checkout, …), not at login. Plan
    the post-login UI for unverified users. The `email_verified` in the login
    response is a snapshot — re-read `GET /api/v1/me` after verification.
12. **The `204` from verify carries `content-type: application/json`** with an
    empty body. Clients that parse JSON based on the content type will throw;
    check the status first.
13. **Problem `type` URIs do not resolve** (`{BASE_URL}/problems/{code}` is a
    `404`) and point at the API host (`BASE_URL`), not the frontend.
14. **Trailing slash → `307` to an absolute URL** built from the request's
    host (`http://localhost:8100/...` in the capture). Behind a proxy that can
    point at an internal host or the wrong scheme.
15. **Captcha:** SEC-12 says "captcha on all public unauthenticated forms",
    while SRS §2.2 and `api-endpoints.md` list captcha only for Bring Your
    Idea and the contact form. Registration and resend have no captcha today
    and accept no captcha field (extra fields are `422`). Do not add one to the
    form until the SRS is clarified.
16. **Validation messages leak library wording**, e.g. `"Value error, must not
    contain control characters"` and `"value is not a valid email address: The
    part after the @-sign is a special-use or reserved name…"`. Fine for
    logs, not for users.
17. **Reserved domains are rejected** (`@foo.test`, `@x.local`), which trips up
    test fixtures that use the RFC 2606 `.test` TLD. Use `example.com`.
18. **Registering an existing unverified address with a different password
    ignores the new password** (it only re-sends the link, after the
    cooldown). A user who forgot what they typed first must use password
    reset once verified — registering again does not fix it.
19. **Unverified accounts are deleted after 30 days** (setting
    `unverified_account_purge_period` = 2592000 s, admin-editable). A link
    whose account was purged returns `400`, and register then creates a fresh
    account.
20. Minor doc drift: `api-endpoints.md` lists the resend success as a bare
    `202`; the code returns the same `{"message": …}` body as register.
    The OpenAPI schema has no `maxLength` on `email` (the 254/64 limits are
    enforced but not advertised).

---

## 10. Source references

| Concern | Where |
|---|---|
| Routes, status codes, per-route rate limits | `src/app/identity/api/auth.py` |
| `/api/v1` prefix | `src/app/api/v1/router.py`, `src/app/main.py` |
| Request schemas, password/token lengths | `src/app/identity/api/schemas.py` |
| Email type (64-octet local part), control-character rule | `src/app/api/text.py`, `src/app/core/text.py` |
| NFKC normalisation | `src/app/identity/infrastructure/password_hasher.py` |
| Register / verify / resend logic | `src/app/identity/application/commands/{register_user,verify_email,resend_verification}.py` |
| Link format, 24 h TTL, 2 min cooldown | `src/app/identity/application/services/verification.py` |
| Token check order (used → expired → already verified) | `src/app/identity/domain/entities.py` (`VerificationToken.mark_used`, `User.mark_verified`) |
| Rate limiter and headers | `src/app/core/rate_limit.py` |
| 300 ms response floor | `src/app/api/enumeration.py` |
| Problem details, 400 vs 422 split | `src/app/api/errors.py` |
| `X-Request-ID` | `src/app/api/middleware.py` |
| Cookies | `src/app/api/cookies.py`; CSRF header name in `src/app/identity/api/dependencies.py` |
| Console email adapter | `src/app/integrations/email/console.py` |
| Outbox dispatch and payload redaction | `src/app/jobs/outbox.py`, `src/app/jobs/registry.py`, `src/app/platform/domain/entities.py` |
