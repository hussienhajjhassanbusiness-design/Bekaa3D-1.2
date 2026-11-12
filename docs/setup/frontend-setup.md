# Bekaa3D Frontend Setup

Developer setup and architecture reference for the Bekaa3D frontend (FVS-001, the foundation slice). This document describes what is **actually implemented and committed** — not intended or future behavior.

## Prerequisites

- **Node.js** and **npm**. No exact Node version is enforced anywhere in this repository (no `engines` field in `package.json`); implementation and verification were done with Node v24.11.1, noted here as "verified with," not a requirement.
- A local clone of this repository.
- Optional for most work, **required** for the real-backend E2E test and for the dev-only readiness banner to ever show a "ready" state: a locally-running VS-001 backend. Everything else (install, dev server, unit tests, the default E2E smoke suite, production build) works with no backend running at all.

## Installation

```bash
npm install
```

## Environment Configuration

Copy the committed example file to your own local, git-ignored copy:

```bash
cp .env.local.example .env.local
```

`.env.local.example` (committed) is the canonical list of **every** frontend variable (`API_PROXY_TARGET`, `MEDIA_PROXY_TARGET`, `NEXT_PUBLIC_TURNSTILE_SITE_KEY`, `NEXT_PUBLIC_ALLOW_MOCK_PAYMENTS`), each marked server-only, development-only or public, with its production rule. For local development the only required line is:

```
API_PROXY_TARGET=http://localhost:8000
```

Edit `.env.local` to point at wherever you actually run the backend. **Production** (topology, reverse proxy, the 52,494,336-byte upload limit, security headers, cookies, the mock-payment limitation and the deployment checklist): see [`production-readiness.md`](production-readiness.md).

- `API_PROXY_TARGET` is read **server-side only**, by `next.config.ts`'s `rewrites()`. It must **never** be renamed with a `NEXT_PUBLIC_` prefix — that would ship the backend's real origin into client-side JavaScript, which this design specifically avoids. (FVS-001 had no `NEXT_PUBLIC_*` variable; the two that exist now are public by design and listed in `.env.local.example`.)
- `.env.local` is git-ignored (`.gitignore`'s `.env*.local` pattern); `.env.local.example` is committed.
- This is not a secret — it's a local-development convenience value, not a credential.

## Development Proxy

The browser never learns the backend's real origin. It only ever calls same-origin `/api/...` paths; `next.config.ts`'s `rewrites()` forwards those to the real backend, server-side. **Two different rules apply, because the backend's own path shape differs by endpoint family (corrected at FVS-002 BATCH 2 — the original single-rule version below was wrong for versioned API paths):**

```
Health endpoints (backend path has NO /api prefix):
frontend request:  /api/health/:path*
                    ↓ (strips the /api prefix)
backend request:    ${API_PROXY_TARGET}/health/:path*

Versioned API endpoints (backend path KEEPS its /api prefix):
frontend request:  /api/v1/:path*
                    ↓ (preserves the /api prefix)
backend request:    ${API_PROXY_TARGET}/api/v1/:path*
```

Examples: a frontend call to `/api/health/ready` reaches the backend's `GET /health/ready` (stripped). A frontend call to `/api/v1/auth/register` reaches the backend's `POST /api/v1/auth/register` (preserved, not `/v1/auth/register`). `apiClient` itself never constructs or receives an absolute backend URL; the two rules are ordered specific-before-general in `next.config.ts` (`/api/health/:path*` first), since a plain rewrites array is tried in source order and the first match wins.

**If `API_PROXY_TARGET` is unset:** `rewrites()` registers no rewrite rule at all — not a hardcoded fallback, not an invalid `undefined/...` destination. The app still builds and runs; any `/api/...` request just falls through to Next's normal routing (effectively unmatched) until you configure the variable.

## Local Media Proxy (`/media`)

**Gap, per `docs/backend-handoff/BACKEND-RESPONSE.md` B4:** the backend API
process does not serve `/media/*` locally (nginx does this in
production/staging; it arrives in local dev only once backend VS-020 is
built). Product image URLs returned by the catalogue (`cover_image.url`,
`images[].url`) are root-relative paths like
`/media/products/<uuid>.png` — ready to use as-is, never parsed or
rebuilt — but until something serves that prefix locally, every image
404s against a local backend.

The backend's own documented workaround: serve the backend checkout's
`storage/media_public/` folder yourself, then add a third Next.js rewrite
alongside the two in `next.config.ts` so `/media/*` forwards to that local
file server instead of the real backend (which doesn't serve it either).

**This frontend workspace does not have the backend checkout available**
(no sibling backend repo, no Docker on this machine — see "Real backend
acceptance" below), so the commands below are **documented, not executed**
in this engagement. From the backend repository root, once it's checked
out alongside this frontend:

```powershell
# PowerShell — run from the backend repository's root directory
npx serve storage/media_public -l 8001
```

```sh
# POSIX equivalent
npx serve storage/media_public -l 8001
```

Then add a third rewrite to `next.config.ts`'s `rewrites()` array (ordered
after the two existing rules — all three are still tried specific-first,
and `/media/:path*` never collides with `/api/:path*`):

```ts
{
  source: "/media/:path*",
  destination: "http://localhost:8001/:path*",
},
```

This is a **development-only** workaround. Production/staging URL
semantics are unchanged — the same root-relative `/media/...` path is
served by nginx there, per B4 — so nothing about this rewrite is ever
shipped as a production configuration change.

## Running the App

```bash
npm run dev     # http://localhost:3000, hot reload
npm run build   # production build
npm run start   # serve the production build
```

In development, `BackendUnreachableBanner` is mounted and will poll `/api/health/ready`. If no backend is configured or running, seeing an "unreachable" banner is expected and does not indicate a frontend problem — the rest of the app remains fully usable either way.

## API Client Contract

`src/lib/api/apiClient.ts` — the one HTTP client every slice uses.

```ts
const data = await apiClient.get("/api/health/ready");
```

**Path rule:** `path` must start with `/api/`. Anything else throws synchronously.

| Correct | Incorrect |
|---|---|
| `/api/health/ready` | `/health/ready` |
| | `http://localhost:8000/health/ready` |

Next's rewrite strips the `/api` prefix before forwarding — the frontend path and the backend path are deliberately different strings.

**Success contract (2xx response):**

| Body | Resolves to |
|---|---|
| Valid JSON | the parsed value, directly (never wrapped in `{ data: ... }`) |
| Empty | `undefined` |
| Unparseable/non-JSON | `undefined` |

A malformed 2xx body is **never** converted into an error.

**Failure contract:** any non-2xx response, a network failure, or the client's own timeout all `throw` an `ApiError` — never returned as a value. See the next section.

The only currently-confirmed endpoint is `GET /api/health/ready`. No product/order/auth endpoint exists yet in this codebase — do not invent one (`bekaa3d-api-contract`).

## ApiError Contract

`src/lib/api/ApiError.ts`.

**`kind` — exactly when each value occurs:**

| `kind` | When |
|---|---|
| `"http"` | Non-2xx response whose body parsed as JSON |
| `"parse"` | Non-2xx response whose body did **not** parse |
| `"network"` | `fetch` itself rejected (offline, DNS failure, connection refused, ...) |
| `"timeout"` | apiClient's own request timeout fired (default 10s, overridable per call via `{ timeoutMs }`) |

**Fields:**

- `type`, `title`, `detail`, `instance` — the four confirmed RFC 9457 Problem Details fields, populated only when the body was valid JSON and actually contained them. Assume nothing — any of these may be `undefined`.
- `status` — the real HTTP status code, but populated **only** for `kind: "http"` (stays `undefined` for `"parse"`/`"network"`/`"timeout"`).
- `correlationId` — reserved on the type, **never populated by any current code**. The backend's correlation/request-ID header name is not yet confirmed (see Open Contract Questions).
- `retryAfterSeconds` — added in FVS-002 BATCH 3. Populated only for a non-2xx response that carries a `Retry-After` header expressed as a valid, finite, non-negative whole number of seconds (the backend's confirmed rate-limit contract uses this form, not an HTTP-date). Missing or malformed values leave this `undefined` — never guessed. No raw `Headers`/`Response` object is ever exposed; this is the only header value `apiClient` surfaces.
- `raw` — the full parsed body, or the raw response text if it didn't parse. Diagnostic only.
- `message` — a safe, frontend-authored fallback string. See below.

### Safe message vs. raw diagnostic — read before rendering any error

- **`message`** is safe to show to a real user. It's always one of a small, fixed set of frontend-written strings (below) — never backend-sourced text.
- **`raw`, `detail`, `type`, `title`, `instance`** are diagnostic data only. Do not render them directly to end users — a backend `detail` string, an HTML error page, or exception text could leak implementation details. Showing backend-provided text to users is a real future design decision, not something to default into.

Current fallback `message` categories (verbatim from `apiClient.ts` — frontend copy, not backend wording):

| Case | `message` |
|---|---|
| `kind: "http"`, status ≥ 500 | "Something went wrong. Please try again." |
| `kind: "http"`, status < 500 | "There was a problem with your request. Please try again." |
| `kind: "network"` | "We couldn't reach the server." |
| `kind: "timeout"` | "The server took too long to respond. Please try again." |

### No auth / CSRF / correlation yet

FVS-001 does not add `Authorization`/Bearer headers, CSRF headers, refresh-token behavior, a forced `credentials` mode (it stays at fetch's default, `same-origin`), or correlation/request-ID headers. None of this is permanently forbidden — each is waiting on its own confirmed backend contract or slice (auth arrives in a later slice; the correlation header name is unconfirmed).

## Error-Handling Layers

Four categories, four different mechanisms — a failure must be routed to the right one. Not every error goes to `error.tsx`.

| Category | Example | Owner |
|---|---|---|
| A. Render/component exceptions | A component throws while rendering | `src/app/error.tsx` (segment boundary) / `src/app/global-error.tsx` (catastrophic root-layout failure only) |
| B. API/query/network failures | A request resolves to a normalized `ApiError` | Handled as query/local state (e.g. `useReadiness`'s normalized `state`) — **never** thrown into `error.tsx`; this is expected, recoverable application state, not a crash |
| C. Transient user feedback | A one-off success/failure notification for a real user action | `Toast`, once a future slice has a real event to trigger it — nothing does yet |
| D. Persistent readiness state | "Is the backend currently reachable/ready" | `BackendUnreachableBanner`, driven by `useReadiness`, mounted only in development |

### `error.tsx` vs. `global-error.tsx`

- **`error.tsx`** — segment-level render-error boundary. Renders **inside** the normal composed shell (the root layout's `AppLayout`/`Header`/`Footer` remain visible around it). Uses the current Next.js `retry()` prop.
- **`global-error.tsx`** — last resort for when the **root layout itself** fails. Fully self-contained: its own `<html>`/`<body>`, its own `globals.css` import. Cannot depend on `AppLayout`, `QueryProvider`, `ToastProvider`, or anything else in the normal shell, since those might be exactly what's broken.

## TanStack Query

`@tanstack/react-query` v5.

- `src/lib/query/queryClient.ts` sets **no speculative global `defaultOptions`** — nothing in FVS-001 needs one yet; each query configures its own options (see Readiness Monitoring).
- `getQueryClient()`: on the server, returns a **brand-new** `QueryClient` on every call, so one user's cached data can never leak into another user's request; in the browser, it reuses one stable singleton for the life of the tab.
- `QueryProvider` (`src/lib/query/QueryProvider.tsx`) wires this into React context, mounted once at the root layout.

## Readiness Monitoring

`useReadiness()` (`src/lib/health/useReadiness.ts`) returns:

```ts
{ state: "ready" | "not-ready" | "unreachable" | "timeout" | undefined; isLoading: boolean }
```

`state` is `undefined` only during the very first load — check `isLoading` first, don't infer loading from `state === undefined` alone.

It calls `apiClient.get("/api/health/ready")` — the backend endpoint remains `GET /health/ready`, reached through the proxy described above. No response-body field is ever assumed; readiness is derived purely from the HTTP-level outcome.

Query configuration: `staleTime: 0`; `retry: 2` (initial attempt + 2 retries = 3 total attempts); `refetchInterval: 15_000` (15s); `refetchIntervalInBackground: false` (polls only while the tab has focus).

**Implementation detail, if you touch this file:** TanStack Query rejects `undefined` as successful query data, but `apiClient` legitimately resolves `undefined` for a 2xx response with an empty/unparseable body. `useReadiness`'s own query function coerces that one case to `null` before TanStack ever sees it. This is internal plumbing — consumers of `useReadiness()` use the normalized `state`/`isLoading` fields only and should never depend on that `null`.

### Development-only banner

`BackendUnreachableBanner` is mounted only when `process.env.NODE_ENV === "development"`, and that check lives at the **root composition boundary**, in `src/app/layout.tsx` — not inside the banner component itself. Why: the component always calls `useReadiness()` unconditionally (React's Rules of Hooks forbid a conditional hook call); if the `NODE_ENV` check lived inside the component instead, the readiness-polling hook would still run for every production visitor even though the component rendered nothing. Gating at the mount point is the only way to stop the polling itself from existing in production.

## Toast Primitive

`src/components/feedback/Toast.tsx` / `ToastProvider.tsx`.

- Variants: `success`, `error`, `info`.
- `useToast().showToast({ message, variant })`.
- **Manual dismissal only** — no automatic timeout.
- Multiple toasts can be shown safely; there is no ordering/queueing/eviction policy yet (deferred until a slice actually needs one).
- **Not currently wired to any real event.** Nothing outside its own tests calls `showToast()` — a future slice with a real mutation/success/failure event is expected to be its first real caller.

## FVS-002 — Registration & Email Verification

A visitor can register, receive enumeration-safe "check your email" messaging, verify via an emailed link, and resend the verification email with cooldown handling. No auto-login, no new auth/session architecture — that remains FVS-003's scope. See `docs/plans/frontend-slices/FVS-002-IMPLEMENTATION-PLAN.md` for the full task-by-task plan and contract-confidence table; this section documents only what is actually committed.

### Register (`/register`)

`src/app/register/page.tsx`, mutation in `src/lib/auth/useRegister.ts`.

- Fields: exactly `email` and `password` — `POST /api/v1/auth/register`, body `{ email, password }`, no trailing slash.
- Password rule: **8–256 Unicode code points**, counted via `[...password].length` (never `.length`, which counts UTF-16 code units and would over-count characters outside the Basic Multilingual Plane). No complexity rule (no required uppercase/digit/symbol). Control characters are rejected client-side. Neither field is trimmed before submission — `type="text"` + `inputMode="email"` is used instead of `type="email"` specifically because an `<input type="email">` auto-trims its own value, which would silently violate this.
- **Enumeration-safe by construction:** success is HTTP 202 with body `{ message }` — that `message` is never read or rendered; the UI shows one fixed, frontend-authored "check your email" string regardless of whether the backend implies a new or an existing account.
- No auth/session state is created; no cookies are set. The success view links toward `/login` (FVS-003's route, not built here).
- Double-submission is prevented by `Form`'s existing `fieldset disabled={isSubmitting}` guard; the mutation also sets `retry: false`.

### Verify Email (`/verify-email`)

`src/app/verify-email/page.tsx`, mutation in `src/lib/auth/useVerifyEmail.ts`.

- The emailed link format is `{FRONTEND_BASE_URL}/verify-email#token=...` — **the token travels in the URL fragment, never a query string.** `useSearchParams()` cannot see a fragment and is never used for this; the token is read client-side from `window.location.hash` via a small `URLSearchParams`-based parser (`parseTokenFromHash`), which safely handles a missing/empty hash, a missing `token` key, an empty value, unrelated fragment fields, and percent-encoded content without throwing.
- **The token is removed from the visible URL immediately after capture** (`history.replaceState`, no navigation/reload) — so the secret does not linger in `window.location.hash` for the rest of the page's lifetime. This runs once, client-only, and never causes a second verification request.
- Locally, a token must be exactly 43 characters to even attempt verification; no alphabet/regex is invented beyond that length check (the backend has not confirmed one). A locally-invalid token is never sent to the backend.
- The token is captured into component state and used exactly once; it is never logged, never written to `localStorage`/`sessionStorage`/a cookie, and never rendered in any error text. A `useRef` single-consumption guard ensures at most one `POST` fires per page instance even under React Strict Mode's development-only double-invoke of effects.
- Request: `POST /api/v1/auth/verify-email`, body `{ token }`, no trailing slash, `retry: false`. A 204 (empty body) is treated as success — `apiClient` already resolves `undefined` for an empty/unparseable 2xx body, so no response content is required.
- State mapping: **204** → success (with a `/login` link). **400** `INVALID_TOKEN` → one generic "invalid link" state — this deliberately covers an invalid token, a used token, and an already-verified re-click alike, since the backend returns the same code for all three; there is no separate "already verified" success state. **410** `RESOURCE_EXPIRED` → a distinct "expired" state, whose copy always communicates both halves of: "if you already verified your email, log in — otherwise request a new link." Separately, a **429** gets its own safe rate-limit message (using `retryAfterSeconds` when available), and a network/timeout/other failure each get their own safe generic message — these four are the standard transport-failure layer every mutation-consuming page in this slice has, orthogonal to the two token-validity states above (see `docs/plans/frontend-slices/FVS-002-IMPLEMENTATION-PLAN.md` §13's BATCH 4 clarification).
- On success, focus moves to the page's heading (not silently to `<body>`) — same pattern used on the register success view.

### Resend Verification (`/verify-email/resend`)

`src/app/verify-email/resend/page.tsx`, mutation in `src/lib/auth/useResendVerification.ts`, countdown in `src/lib/auth/useCooldown.ts`.

- Field: exactly `email` — `POST /api/v1/auth/resend-verification`, body `{ email }`, no trailing slash. Same client email-shape rule as registration; not trimmed.
- **Enumeration-safe:** every successful 202 renders the identical fixed copy ("If an account exists for that email, a verification email was sent.") regardless of whether the account exists, doesn't exist, or the backend's own server-side cooldown silently suppressed the email — the frontend never tries to infer account existence.
- **120-second success cooldown:** every successful 202 starts a cooldown of exactly `Date.now() + 120_000` — an **absolute deadline**, never a decrementing counter, so a throttled/backgrounded timer gap self-corrects on the next tick instead of drifting. The resend button is disabled for the cooldown's duration.
- **429 rate-limit cooldown is a separate thing from the 120s success cooldown.** If the response carries a valid `Retry-After` (via `ApiError.retryAfterSeconds`), the frontend disables resend until `Date.now() + retryAfterSeconds * 1000` instead — which may be far longer than 120 seconds (confirmed per-IP limits: register=5/hr, resend=5/hr, verify=20/hr). A missing/malformed `Retry-After` shows a generic rate-limit failure without inventing a duration.
- Accessibility: one `aria-live="polite"` announcement when the cooldown starts ("Resend available at HH:MM:SS", local browser time, stable while the deadline doesn't change) and one more when it completes ("You can resend the verification email now.") — never once per tick. The visible ticking countdown text is a separate, plain (non-live) element so it never spams screen readers; this was a real, found-and-fixed defect during FVS-002's integration pass (the rate-limit warning `Alert` previously recomputed its message from the ticking seconds every render, which re-announced every second for any `Retry-After` under 60s — fixed by freezing that message once, at the moment the 429 is caught).
- On a successful resend, focus moves to the success message (the page stays on the same form, unlike register/verify-email's dedicated success views).
- No cooldown state, email, or token is persisted to `localStorage`/`sessionStorage`/a cookie anywhere in this slice.

### Errors

RFC 9457 base Problem Details handling (`type`/`title`/`status`/`detail`/`instance`) is shared with FVS-001 — see the ApiError Contract section above. The exact field-level `errors[]` validation-error extension shape is **still unconfirmed** by the backend; no code anywhere in this slice invents it. Server-side field validation failures surface only through the existing generic `ApiError`/`Alert` path. `ApiError.raw`/`.detail`/`.type`/`.title`/`.instance` are never rendered to the user in any FVS-002 page — only safe, frontend-authored copy.

### Captcha

Cloudflare Turnstile is planned for registration and resend but is **not implemented**. No Turnstile dependency is installed, no placeholder widget is rendered, and no captcha field/token exists anywhere in this slice's code. The exact field name and request contract are pending backend confirmation.

### Real Backend / Outbox Acceptance

A deterministic, backend-independent E2E spec exists (`e2e/register-and-verify.spec.ts`) proving the full register → check-email → (simulated email link) → verify → `/login`-prompt flow via Playwright route interception — it never contacts a real backend. **Real-backend acceptance (FVS002-T14) remains pending** and is a genuine, separate gate, not satisfied by the E2E spec above. The current manual workaround for inspecting a real verification token during development is to stop the backend's worker and inspect the `email_outbox` table directly via SQL; an automated, file-based dev/test email provider is being built on the backend side but is not ready yet.

## FVS-003 — Login, Logout & Session Management

A verified customer can log in, stay logged in across page loads via
backend-managed httpOnly cookies, be silently refreshed, be forced back to
`/login` when refresh fails, log out (locally and cross-tab), and have a
safe `returnTo` preserved through the redirect. See
`docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md` for the full task-by-task plan and
contract-confidence table; this section documents only what is actually
committed.

### Cookie model

Three cookies, confirmed by the backend contract:

| Cookie | Readable by JS | Path | Lifetime |
|---|---|---|---|
| `access_token` | **No** (httpOnly) | `/` | 15 minutes |
| `refresh_token` | **No** (httpOnly) | `/api/v1/auth` | 30 days |
| `csrf_token` | **Yes** | `/` | 30 days, stable across refresh |

`access_token`/`refresh_token` are never read anywhere in this codebase —
not via `document.cookie`, not via any other mechanism. `csrf_token` is the
*only* cookie any frontend code reads, and only through one approved
helper: `readCsrfToken()` in `src/lib/auth/csrf.ts`. No token, session
identifier, or credential material is ever written to `localStorage`,
`sessionStorage`, React state, or a module-level variable anywhere in this
slice.

### Same-origin API, no CORS, no `credentials` override

Every `apiClient` call is a same-origin relative `/api/...` request, exactly
like FVS-001/002 — `fetch`'s default `credentials: "same-origin"` already
sends cookies automatically; `apiClient.ts` sets no `credentials` option and
none is added for this slice. No `credentials: "include"` and no CORS
workaround are needed or planned, because the browser never calls the
backend's real origin directly (Next's `rewrites()` forwards server-side).

### Session bootstrap — `/me` is canonical, `csrf_token` is only a hint

`src/lib/auth/authSession.ts`'s `bootstrapAuthSession()` is the one
backend-approved algorithm:

1. Check for a readable `csrf_token` cookie. **Absent → resolve anonymous
   immediately, zero network requests.** Its absence is a fast, free,
   100%-reliable anonymous signal (a user with no session never had a
   reason to have this cookie set).
2. **Its presence is only a hint that a session might exist — never proof of
   authentication.** The cookie could be stale (session since expired or
   revoked server-side) or simply left over from a previous visit. The only
   way to actually know is to ask the server.
3. Present → `GET /api/v1/me` (direct `apiClient.get`, never through
   `authenticatedRequest` — this call *is* the bootstrap check, not a
   request that should itself re-enter the generic 401-refresh wrapper).
4. `200` → authenticated; body mapped to a non-secret `SafeUser` shape
   (`{id, email, role, emailVerified, emailVerifiedAt, createdAt}` — never a
   token field of any kind).
5. `401 AUTH_REQUIRED` → exactly one coordinated refresh (below), then retry
   `/me` exactly once.
6. Refresh failure, or the retried `/me` still `401 AUTH_REQUIRED`, or any
   other unexpected failure (network/timeout/500/a 401 with a different
   code such as `MFA_REQUIRED`) → **anonymous.** Never a false
   "authenticated" result; never retried a third time.

`POST /api/v1/auth/refresh` is explicitly **not** used as a page-load probe
— refresh rotates the refresh cookie on every call, is rate-limited
(60/hour/IP), and simultaneous old-token reuse across tabs can revoke the
entire session, none of which is acceptable for an unconditional page-load
check.

### Auth state ownership

- **TanStack Query** owns the actual data: one query, key `["auth",
  "session"]` (the `AUTH_SESSION_QUERY_KEY` constant exported from
  `authSession.ts`), `staleTime: Infinity`, `retry: false` — the bootstrap
  sequence's own bounded refresh-then-retry-once logic lives inside the
  `queryFn` itself, not TanStack's own retry mechanism.
- **`AuthProvider`** (`src/lib/auth/AuthProvider.tsx`) is a thin context
  wrapper that *derives* `{user, isAuthenticated, isLoading, logout}` from
  that one query — it never maintains a second, independently-settable
  piece of state that could drift from it. `logout` is the one action field
  added beyond projection (forwards to `useLogout()`'s mutation) —
  deliberately nothing else (no `refreshSession`, `login`, `setUser`,
  `setAuthenticated`, tokens, or roles).

### Refresh coordination

Two layered mechanisms, both in `src/lib/auth/refreshSession.ts`:

1. **Same-tab single-flight** (`src/lib/auth/singleFlight.ts`,
   `createSingleFlight`) — a fully generic async-dedup primitive with zero
   auth/HTTP knowledge. Concurrent same-tab callers all share one in-flight
   refresh; the slot clears on both success and failure.
2. **Cross-tab mutual exclusion** — a named Web Lock
   (`navigator.locks.request("bekaa3d-refresh", ...)`), backend-mandated:
   two tabs rotating the refresh cookie simultaneously can trigger reuse
   detection and revoke the whole session. **Inside the lock**, the session
   is re-checked (`GET /api/v1/me`, direct and unwrapped) before refreshing
   — a second tab that acquires the lock after a first tab already
   refreshed sees the session already valid and does **not** rotate the
   token a second time.

If `navigator.locks` is unavailable, this falls back to same-tab-only
protection (`refreshOnce()` called directly) — a documented, non-silent
reduction in guarantees, not a second invented cross-tab mechanism. This
project's supported/tested browser (Edge 79+, the same browser this
repository's own Playwright suite runs against) supports Web Locks, so this
fallback path is defensive-only, not a live gap for any currently-supported
browser.

`BroadcastChannel` is never used as a mutex anywhere in this codebase — it
is reserved exclusively for the logout *signal* (below), a separate concern
from refresh mutual exclusion.

### 401 handling — `authenticatedRequest`

`src/lib/auth/authenticatedRequest.ts` wraps a future authenticated call
with refresh-then-retry-once behavior:

- Only `401` **with problem `code: "AUTH_REQUIRED"`** is refreshable.
  `401 MFA_REQUIRED` is a different, non-refreshable signal, surfaced
  unchanged. Every other failure (`403`, `404`, network, timeout, `500`,
  any other code) never triggers a refresh.
- At most one refresh per call, at most one retry of the original request.
  If the retried call also comes back `401 AUTH_REQUIRED`, that surfaces as
  a final failure — never a second refresh.
- **Both reads and writes** may be retried once after a successful refresh
  — the backend has confirmed authenticated write endpoints authenticate
  before their business side effect, so replaying a write after refresh is
  safe, not merely assumed.
- `login`, `logout`, and `refresh` itself are always called directly
  through `apiClient`, **never** through this wrapper — enforced by
  construction (the wrapper is simply never imported into those call
  sites), not a runtime blacklist. As of this writing, `authenticatedRequest`
  has no production call site at all yet — it is prepared infrastructure
  for the first real authenticated write, which doesn't exist until a later
  slice ships one.

### CSRF

- **Cookie:** `csrf_token`, JS-readable, stable for the session (does not
  rotate on refresh).
- **Header:** `X-CSRF-Token`, attached only when a caller explicitly opts in
  via `apiClient.post(path, body, { csrf: true })` — never a blanket
  auto-attach. Required for `refresh`, `logout`, and every authenticated
  write; **not** required for `login` or any of FVS-002's anonymous POSTs.
- **Read fresh at send time, every call** — never cached across requests in
  React or module state.
- A missing `csrf_token` cookie when `{csrf: true}` was requested is a
  local precondition failure (`ApiError{kind:"csrf"}`) — no request is
  sent, and no token is ever fabricated.

### Login (`/login`)

`src/app/login/page.tsx`, mutation in `src/lib/auth/useLogin.ts`.

- `POST /api/v1/auth/login`, body exactly `{email, password}`, no CSRF, no
  trailing slash.
- Two disjoint success shapes, never collapsed into "any 2xx means
  authenticated": **`200`** (`{user_id, email, role, email_verified,
  session_expires_at}`) is a normal session; **`202`** (`{challenge_id,
  expires_in_seconds}`) is an MFA challenge that establishes **no session
  and sets no cookies**. The `200` body itself is never trusted as the
  ongoing auth source of truth — only `GET /me` is; the login response is
  read only far enough to discriminate the two shapes (`user_id` vs
  `challenge_id`).
- On `202`: shows a safe, generic "additional verification required, not
  yet available" message. Never builds MFA UI, never marks `AuthProvider`
  authenticated, never exposes or persists `challenge_id`, never navigates
  — MFA itself is FVS-005's scope entirely.
- On `200`: `await queryClient.invalidateQueries({queryKey:
  AUTH_SESSION_QUERY_KEY})` **before** navigating — since the auth-session
  query is always active (mounted by the root-level `AuthProvider`),
  TanStack's `invalidateQueries` genuinely awaits the real `/me` refetch
  before its promise resolves, so navigation never races ahead of the
  canonical authenticated state. Proven directly (not just asserted) by
  `src/app/login/page.race.test.tsx`, which exercises the real
  `useLogin -> AuthProvider -> bootstrapAuthSession` wiring with only
  `apiClient` mocked, deliberately stalls `/me`, and confirms navigation
  waits for it.
- Email is trimmed before submission (the one field-level transformation
  this slice applies); password is never trimmed and has no 8-character
  minimum (unlike registration) — only a non-empty requirement and a
  ≤256-character cap mirroring the confirmed backend maximum.
- Failure copy: `401 INVALID_CREDENTIALS` → "Invalid email or password."
  (identical regardless of unknown-email vs wrong-password — enumeration
  safety is a backend-confirmed design intent, not just a frontend
  convention); `403 ACCOUNT_DISABLED` → safe generic copy, never revealing
  the password was correct; `429 RATE_LIMITED` → safe copy, with a coarse
  wait time only when `retryAfterSeconds` is actually present; network/
  timeout get their own safe messages. Raw backend diagnostic text
  (`ApiError.raw`/`.detail`) is never rendered.
- `returnTo` is read from the login URL's query string and resolved through
  `src/lib/auth/returnTo.ts`'s `resolveReturnTo` before navigating — see
  below.

### Safe `returnTo`

`src/lib/auth/returnTo.ts`. `isSafeReturnTo` requires exactly one leading
`/`, rejects `//...` and any literal-or-percent-encoded backslash, and
re-validates by resolving against a fixed fake origin
(`new URL(value, FAKE_ORIGIN).origin === FAKE_ORIGIN`). Any rejected or
missing value falls back to `/`. `buildLoginRedirectPath` produces
`/login?returnTo=<encoded-safe-path>` for `ProtectedRoute`'s own redirect.
Tested against an exhaustive attack-string matrix (absolute URLs,
protocol-relative URLs, `javascript:`/`data:` pseudo-protocols, backslash
tricks, percent-encoded variants) in `returnTo.test.ts`, and against a real
browser in `e2e/login-session.spec.ts`.

### `ProtectedRoute`

`src/components/auth/ProtectedRoute.tsx`. Three states only, matching
`AuthProvider`'s own: `isLoading` → `LoadingSpinner` only; `isAuthenticated`
→ renders `children`; anonymous → renders nothing and `router.replace`s to
`/login?returnTo=<current path+query>` inside a `useEffect` (never during
render, so protected children are never rendered even momentarily before
the redirect). No role/permission checking of any kind. Callers must never
wrap `/login` itself with it (redirect-loop avoidance) — an invariant
documented in the component's own comment, not enforced internally.

**No real protected application route exists yet** in this repository
(FVS-006 will supply the first one) — `ProtectedRoute` is proven entirely
through its own component/integration tests
(`ProtectedRoute.test.tsx`) and through `AuthProvider.test.tsx`'s
cross-tab-race test, not through an E2E visit to a page that doesn't exist.
No throwaway production route was created purely to exercise it in E2E.

### Logout — local-first

`src/lib/auth/useLogout.ts`, wired into `AuthProvider.logout()`.

Backend-recommended "local-first" sequence, in order:

1. `queryClient.setQueryData(AUTH_SESSION_QUERY_KEY, null)` — local auth
   state flips to anonymous **synchronously, before any network response**.
2. Broadcast a `"logout"` cross-tab signal (below).
3. `POST /api/v1/auth/logout` (no body, `{csrf: true}`, direct `apiClient`
   call — never `authenticatedRequest`, so logout itself can never trigger
   a refresh).
4. **Both `204` and `401 AUTH_REQUIRED` count as confirmed server
   success** (an already-logged-out session completing "logout" again is,
   from the user's perspective, still a successful logout). `403
   CSRF_INVALID`, network/timeout failures, and a missing `csrf_token`
   cookie are explicitly **not** confirmed success.
5. On any non-confirmed outcome: the user remains locally logged out
   regardless (that already happened in step 1), and exactly **one**
   bounded background retry fires after a fixed delay — a bare `setTimeout`
   calling the same server-logout attempt once more, nothing scheduled
   again after that. Never a generic retry/job framework, never routed
   through `authenticatedRequest`, never triggers `refreshSession`.
6. `mutateAsync()`/`AuthProvider.logout()` always **resolve** (never
   reject) with `{serverConfirmed: boolean}` — the user's own logout action
   is never a failed action, since the frontend is already locally logged
   out by the time any server outcome is known.

**User feedback on a failed server-side logout:** `serverConfirmed: false`
is a genuinely caller-observable result, not an internally-swallowed
detail — `AuthProvider.logout()` forwards `useLogout`'s own result
Promise unchanged (proven by a dedicated test in `AuthProvider.test.tsx`).
There is currently no real logout trigger in the UI to display this to an
end user (no nav/account surface exists yet — see Non-Scope below), so
nothing renders it today; the seam a future logout button/page would need
already exists and is tested, without inventing one now.

### Cross-tab logout

`src/lib/auth/crossTabSignal.ts` (`createCrossTabSignal`, built on native
`BroadcastChannel`) plus `AuthProvider.tsx`'s subscription. Outgoing: a
local `logout()` call announces the literal string `"logout"` only — never
an email, token, or any other payload, even though the primitive's own type
signature accepts any string. Incoming: another tab receiving `"logout"`
immediately calls `queryClient.cancelQueries({queryKey:
AUTH_SESSION_QUERY_KEY})` then `setQueryData(..., null)` — never calls the
logout API again, never re-announces (so it can never loop), never
triggers a refresh.

**Login-vs-remote-logout race:** if a concurrent login's own
`invalidateQueries`-triggered `/me` refetch is still in flight when a
remote `"logout"` signal arrives, `cancelQueries()` (called before
`setQueryData`) causes that in-flight fetch's eventual resolution to be
discarded rather than applied — a stale "authenticated" result can never
land after the anonymous state has been set. Proven by a dedicated test in
`AuthProvider.test.tsx` that builds exactly this sequence with a
controllable, deliberately-delayed `/me` fetch.

Survives React Strict Mode's dev-only effect double-invoke correctly: the
discarded first mount's subscription is torn down (`unsubscribe()` +
`close()`) before the second, surviving mount registers its own — proven
with a test that genuinely exercises double-invoke (building the render
tree directly, rather than via React Testing Library's `wrapper` render
option, which was found during this slice's own integration pass not to
trigger genuine double-invoke in this test environment).

### Cache security

On logout (local or remote) and nowhere else, exactly one query is
cleared: `["auth","session"]`. No unrelated public data (e.g. a future
catalog/product query) is ever touched by this mechanism. There is
currently no second authenticated-user-scoped query in this codebase — the
convention any future one must follow (so logout generalizes without
re-deriving the rule) is recorded in `docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md` §13:
nest such a query's key under a shared, exported prefix constant from this
slice's auth module, so a single future `removeQueries` call on logout can
target the whole prefix. No such constant exists yet, since nothing
consumes it — it is not invented speculatively ahead of a real second
query.

### Deterministic E2E scope

`e2e/login-session.spec.ts` (FVS003-T12) covers, all via route
interception against the real browser (never a real backend): normal login
with a real browser cookie jar (the backend's `Set-Cookie` for
`csrf_token` is genuinely applied, never simulated in JS) through to
canonical `/me`-authenticated navigation; safe `returnTo` round-tripping
(including one with its own nested query string); unsafe external and
protocol-relative `returnTo` both falling back to `/`; the `202` MFA path
never authenticating, navigating, or exposing `challenge_id`; and a
real-browser accessibility/responsive pass (six-viewport overflow and
desktop-centering check, full-width mobile CTA, a full keyboard walkthrough
with visible focus and no trap, the password show/hide toggle's keyboard
operability and `aria-pressed` correctness, focus-first-invalid-field with
a polite validation summary, and confirmation that a credential failure
never leaks raw backend diagnostic text).

**Why logout and `ProtectedRoute` are not covered here:** there is
intentionally no real logout trigger in site navigation and no real
protected product route anywhere in this repository yet (both are later
slices' job — most likely FVS-006). Building either purely to round out
this E2E file was explicitly rejected. They remain proven through their
own component/integration tests instead (`useLogout.test.ts`,
`AuthProvider.test.tsx`'s cross-tab tests, `ProtectedRoute.test.tsx`). The
full login → protected-page → logout browser flow will be exercised once a
real protected route/logout trigger exists, or during T14 against the real
backend.

### Real backend acceptance — still pending

FVS003-T14 (real cookie/session/refresh/logout/CSRF acceptance against an
actual backend) has not been attempted — no real backend has been reachable
in this environment at any point in this engagement, matching FVS-001's and
FVS-002's own still-pending real-backend gates. This is a genuine, separate
gate, not satisfied by anything in this section.

## FVS-006 — Customer Account Shell & Profile

A logged-in customer sees an account shell (nav + content region) and a
read-only profile (email, verification status). `/account` redirects to
`/account/profile`. No edit form exists — VS-006 is deliberately
read-only; see `docs/plans/frontend-slices/FVS-006-IMPLEMENTATION-PLAN.md` for the full task-by-task
plan. This section documents only what is actually committed.

### One canonical query, no second `/me` fetch

`AccountLayout` and `ProfileCard` both read the same `useAuth()` context
FVS-003 already established — neither mounts a second `useQuery`, calls
`apiClient.get("/api/v1/me")` directly, or introduces a second query key.
`ProfileCard`'s Retry button targets the exact same canonical key
(`queryClient.refetchQueries({queryKey: AUTH_SESSION_QUERY_KEY})`,
`src/lib/auth/authSession.ts`'s own exported constant) — never a new
fetch path.

### A real cross-slice defect found and fixed here

Building this slice's own error state ("show a retry button if `/me`
fails after a session is otherwise valid") surfaced a genuine bug in
FVS-003's bootstrap logic: `bootstrapAuthSession()` previously caught
*every* `/me` failure — including a plain network error, our own
request timeout, an unparseable response, or a `5xx` — and resolved
anonymous (`null`), identically to a confirmed logged-out session. Since
the query never rejected, there was no way to tell "this session is
genuinely invalid" apart from "the server/network just broke for a
second." A customer with a perfectly valid session could have been
silently bounced to `/login` by a transient blip.

Fixed in `src/lib/auth/authSession.ts`: a definitive 401 (`AUTH_REQUIRED`
or any other code) still resolves anonymous, unchanged — a real 4xx is
still a real "not authenticated" signal. Only `network`/`timeout`/`parse`
failures and any `5xx` now re-throw, so the `["auth","session"]` query
genuinely errors. `AuthProvider` exposes exactly one new field,
`isError: boolean` (nothing else — no new store, no new hook).
`ProtectedRoute` no longer redirects when `isError` is true; it renders
`children` so the page itself can show a retryable error.

**This shifts the safety obligation onto each page that reads cached
auth data.** `ProtectedRoute` rendering children on `isError` does *not*
by itself make a page safe — it only means the page won't be wrongly
logged out. `ProfileCard` (and any future `/account/*` page built the
same way, reading only `useAuth()` with no API call of its own) must
check `useAuth().isError` itself, before trusting `isAuthenticated`/
`user`, and show its own retry UI instead of real content when it's
true. A future page that forgets this check would be relying on a
safety net that doesn't exist for this page family — see the comment in
`ProtectedRoute.tsx` itself for the exact invariant.

### Account shell owns `/account/*` protection

`src/components/account/AccountLayout.tsx` wraps `ProtectedRoute`
(reused, never duplicated into a `CustomerProtectedRoute`) and renders
the nav + content region only once `ProtectedRoute` actually lets
children through. No `/account/*` page wraps its own second
`ProtectedRoute` — `src/app/account/layout.tsx` mounts the shell once for
the whole route group.

The content region is a `<section aria-label="Account content">`, never
a second `<main>` — `AppLayout` already renders the one `<main
id="main-content">` landmark at the root layout for every route.

### Account navigation registry

`src/components/account/accountNavItems.ts` exports `ACCOUNT_NAV_ITEMS`
— today exactly one entry (`Profile`). This is the single place every
later `/account/*` slice (Orders, Downloads, Offers, Wishlist, Reviews,
Addresses, Notifications) adds itself to as its own route lands; no
disabled/dead placeholder link is rendered ahead of that. The nav is a
real `<nav aria-label="Account">` with real `Link` elements, and the
active route gets `aria-current="page"` via `usePathname()`.

Responsive behavior is pure CSS (this project's existing named
`tablet:`/768px breakpoint token, no JS viewport detection): a
horizontal, `overflow-x-auto` tab row on mobile; a vertical sidebar
beside the content region at `tablet:` and above.

### Profile — read-only, by design

`src/components/account/ProfileCard.tsx` displays the user's email, a
human-readable verification status, and nothing else fetched from the
response. **There is no edit-profile form, no Save/Edit/Cancel control,
and no input/textarea/select anywhere in this component** — VS-006
defines no mutable profile field for V1, so none is invented here. If a
mutable field is ever approved, it is a requirement change for a future
slice, not something this one guesses at.

**Unverified banner:** when `emailVerified` is `false`, a warning banner
appears, linking to the existing `/verify-email/resend` route (FVS-002)
— never a new route. When `emailVerified` is `true`, the banner is fully
absent (not merely hidden).

**Loading:** a simple skeleton (`role="status"`, motion-reduce-safe via
the same Tailwind variant pattern `LoadingSpinner`/`Toast` already use)
— no skeleton library installed.

**Account-state display decision (from this slice's own audit):** the
confirmed `/me` response has no literal `account_state`/`status`/
`enabled` field — `docs/plans/backend/vertical-slice-plan.md`'s "verification/account
state" and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s "account state" are both
prose that predates the real, field-level contract sync FVS-003
confirmed. `ProfileCard` shows a fixed "Account status: Active" line,
but this is explicitly a **derived display, never a fabricated API
field** — justified only because a successful `/me` response is, per
FVS-003's own confirmed contract, impossible for an inactive account
("account-active state rechecked server-side on every call"). The code
comment at this exact line makes the same point, so a future reader
doesn't mistake it for a real response field.

### Deterministic E2E coverage

`e2e/account-profile.spec.ts` (FVS006-T06) covers, via route
interception against a real browser (never a real backend): the
`/account` → `/account/profile` redirect with a real authenticated
session; the unverified-banner path and its exact resend link; an
anonymous visit redirecting to `/login` with the safe `returnTo`
preserved; absence of any edit UI; mobile nav visibility/keyboard-
reachability; a six-viewport overflow/layout check; and — the strongest
evidence for this slice's own bootstrap fix — a real `500` from `/me`
showing a retryable error (never a false redirect to `/login`), with
Retry genuinely re-fetching and rendering the real profile afterward.

### Real backend acceptance — still pending

FVS006-T07 (the real register→login→`/account/profile` loop against an
actual backend) has not been attempted — no real backend has been
reachable in this environment at any point in this engagement, matching
every prior slice's own still-pending real-backend gate.

## Testing

### Unit / Component Tests

```bash
npm run lint
npm run typecheck
npm run test
```

Vitest + React Testing Library. Network mocking uses native `fetch` stubbing (`vi.stubGlobal("fetch", ...)`), or module-mocking `apiClient`/`useReadiness` directly where that's the more appropriate seam (e.g. a component test that shouldn't know `fetch` exists). **No MSW** (Mock Service Worker).

Why no MSW: FVS-001's network surface is intentionally tiny — one client, one real endpoint — so native stubs are sufficient, and a service-worker/mock-server dependency would be unnecessary infrastructure for what exists today. This isn't a permanent rule; a future slice with a much larger network surface may reasonably justify MSW.

### Default E2E Smoke Tests

```bash
npm run test:e2e
```

Runs **only** `e2e/smoke.spec.ts`, `e2e/register-and-verify.spec.ts`, `e2e/login-session.spec.ts`, and `e2e/account-profile.spec.ts` (all four matched by Playwright's `smoke` project in `playwright.config.ts`). Deliberately backend-independent — verified to pass whether or not a real backend is running.

Current coverage: `/` boots (shell landmarks, SkipLink, foundation content); `/does-not-exist` renders 404 content with a working "Back to home" link and the shell still exactly-once afterward; the readiness/banner state is asserted **tolerantly** — whichever valid state is currently showing is accepted, never a hard-coded expectation. `register-and-verify.spec.ts` (FVS002-T12) proves the full register → check-email → verify → `/login`-prompt flow and a short resend smoke check, both via route interception, never a real backend. `login-session.spec.ts` (FVS003-T12) proves the login flow — see the FVS-003 section above for its exact scope. `account-profile.spec.ts` (FVS006-T06) proves the account shell/profile flow — see the FVS-006 section above for its exact scope.

No accessibility automation runs here — see below.

### Real Backend Connectivity E2E Test

```bash
npm run test:e2e:backend
```

Runs **only** `e2e/backend-connectivity.spec.ts`. Requires: the frontend dev server (started automatically by Playwright's `webServer` config), `API_PROXY_TARGET` configured, and an actual VS-001 backend running locally.

Makes one real request to `/api/health/ready` through the frontend origin (exercising the genuine proxy, not a mock) and asserts a genuine 2xx response — no response-body field is inspected. This command is intentionally separate and opt-in: it is never run by `npm test`, `npm run test:e2e`, or `npm run build`.

### Playwright browser note

Both projects in `playwright.config.ts` use `channel: "msedge"` — the system-installed Microsoft Edge — instead of Playwright's own bundled Chromium. During FVS001-T16's implementation, the environment had no outbound network access to `cdn.playwright.dev`, so Playwright's browser binary could not be downloaded; a channel-based browser launches an already-installed executable directly, with no download required. If your machine doesn't have Edge installed, either install it or change the config to `devices["Desktop Chrome"]` and run `npx playwright install chromium` (requires normal internet access).

Generated run artifacts — `test-results/`, `playwright-report/`, `blob-report/`, `playwright/.cache/` — are git-ignored; do not commit them.

### Current backend E2E status

| Run | Result |
|---|---|
| Default smoke (`test:e2e`), backend **down** | **PASS** (verified, run twice) |
| Default smoke (`test:e2e`), backend **up** | **PENDING** — no real backend available in this environment |
| Backend connectivity (`test:e2e:backend`) | **PENDING** — no real backend available; a real attempt genuinely failed for the correct reason (nothing to reach), which at least proves the spec is wired to real infrastructure and not a mock |

Both PENDING rows must be closed with a real backend before FVS-001 is considered fully done (FVS001-T18).

## Accessibility & Responsive Verification Status

As of FVS001-T15/T16.

**Verified** (source-level / calculated / compiled-output evidence):

- Exactly one `<header>`/`<main>`/`<footer>` landmark and one SkipLink per route — confirmed via live HTML inspection of `/` and `/does-not-exist`.
- Live-region structure: `LoadingSpinner` (`role="status"`), `Toast` (`role="status"`/`aria-live="polite"`), `BackendUnreachableBanner` not-ready (`role="status"`/`polite`) and unreachable/timeout (`role="alert"`/`assertive`) — no redundant/nested live regions.
- Text/status color contrast, calculated precisely from the real token hex values (WCAG relative-luminance formula, not estimated). Every checked text pairing passes its 4.5:1/3:1 target **except** the focus-ring finding below.
- Reduced-motion CSS genuinely compiled: `@media (prefers-reduced-motion:reduce)` is present in the real production CSS bundle, covering `LoadingSpinner` and `Toast`.
- Source-level focus-order checks: no `tabindex` above `0` anywhere in the codebase; the one `outline: none` that exists is always paired with a visible replacement ring on the same rule.

**PENDING manual/browser verification** (no interactive browser was available during T15's own pass; Playwright/Edge became available afterward in T16 but hasn't yet been used for this):

- A real keyboard-only walkthrough of `/` and `/does-not-exist` (Tab order, SkipLink first-focus, focus visibility, no keyboard trap).
- The full responsive viewport matrix — 320 / 375 / 768 / 1024 / 1440 / 1920px — for both `/` and `/does-not-exist`.
- Horizontal-overflow measurement in a real browser.
- Banner/SkipLink and Toast/SkipLink visual-overlap checks.
- Real `prefers-reduced-motion` browser emulation (only the compiled CSS rule has been confirmed, not actual browser behavior).

### Open focus-ring finding (unresolved)

FVS001-T15 calculated the global focus-ring's outer edge (`brand-lime`, `#8AC143`) against the app's dominant white background at **2.15:1** — below the WCAG 1.4.11 non-text-contrast target of 3:1. This is an **open accessibility/design finding requiring a decision** (widen the ring, change its outer color, or explicitly accept the risk with documented rationale). It has not been fixed, and this document does not fix it either — see `src/app/globals.css`'s `--shadow-focus-ring` token.

### Automated accessibility scanning

`@axe-core/playwright` is **not installed**. `docs/plans/frontend-slices/FVS-001-IMPLEMENTATION-PLAN.md` §26 classifies it as "recommended, not mandatory... flagged for the plan reviewer's judgment, not decided unilaterally" — it was never formally accepted. There is currently no automated accessibility scanning in this repository; the verification above is the only accessibility evidence that exists.

## Open Contract Questions

The living list of unconfirmed backend contract items is `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 — this document does not maintain a second, competing copy. Relevant to FVS-001 specifically:

- The RFC 9457 validation-error extension shape (an `errors[]`-style field or similar) is logged there as unconfirmed — `ApiError.raw` is the escape hatch until it's confirmed.
- The correlation/request-ID header name is unconfirmed — `ApiError.correlationId` exists on the type but is never populated by any current code (see its inline comment in `src/lib/api/ApiError.ts`).
- No endpoint or response-body contract beyond the two confirmed health paths (`GET /health/ready`; `GET /health/live`, unused by this slice) exists yet for this frontend to consume.

Do not guess at any of these — confirm with the backend team and update `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 first.

## FVS-013/FVS-014/FVS-022 — Real Public Storefront (Catalogue, Product Detail, Home, About)

REAL STOREFRONT INTEGRATION PHASE 1 wires the public storefront against
the BUILT backend contract (`docs/backend-handoff/openapi.json` + `BACKEND-RESPONSE.md`
B1–B5), superseding every earlier `NEEDS BACKEND CONFIRMATION` placeholder
those sections named. This section documents only what is actually
committed.

### Contract adapters (new)

- `src/lib/catalog/productTypes.ts` — raw wire types (`ProductListItem`,
  `ProductDetail`, `ProductPage`, etc.), transcribed field-for-field from
  `openapi.json`.
- `src/lib/catalog/productAdapters.ts` — `toProductCardModel` /
  `toProductDetailModel`, the only place the wire contract is converted to
  the camelCase UI model. Every `null` in the wire contract (STL's
  material/colour/dimensions/etc.) is preserved as `null`, never defaulted.
- `src/lib/catalog/referenceDataApi.ts` + `useReferenceData.ts` —
  categories/materials/colours.
- `src/lib/catalog/productsApi.ts` + `useProducts.ts`/`useProduct.ts` —
  list (cursor-paginated, `useInfiniteQuery`) and detail queries.
- `src/lib/catalog/shopQueryAdapter.ts` — maps `/shop`'s URL state
  (`shopUrlState.ts`, unchanged) to the real `category_id`/`material_id`/
  `colour_id` query parameters. The URL stores each facet's real `id`
  directly (materials/colours have no public slug, so this keeps one
  consistent encoding across all three facets rather than slug-for-
  category-only).
- `src/lib/search/searchSuggestionsApi.ts` + `useSearchSuggestions.ts` —
  300ms-debounced (`useDebouncedValue`, `src/lib/shared/`), 3-character
  minimum, keyed by the debounced term so a stale response can never
  overwrite a newer one (TanStack's own per-key cache, not a manual
  sequence counter).
- `src/lib/settings/publicSettingsModel.ts` — `PublicSettingsRead` (the
  real, confirmed flat shape) + `toPublicSettingsModel`, which also
  normalizes the E.164 `whatsapp_number` (`"+961..."`) to the digits-only
  form `buildWhatsAppHref` requires.

### Routes mounted

- `/shop` (`src/app/shop/page.tsx` + `ShopView`) — filters, search,
  sort, cursor "load more" pagination, loading/empty/error states.
- `/shop/[slug]` (`src/app/shop/[slug]/page.tsx` + `ProductDetailView`) —
  real product detail; a 404 renders `NotFoundContent` directly (this page
  is client-rendered, matching this app's established architecture where
  `apiClient` is a same-origin browser fetch never usable server-side —
  Next's own `notFound()` is documented as Server-Component/Server-
  Function/Route-Handler only, not Client Components, so it is not used
  here).
- `/about` — static brand content (FVS-022's own "approved V1 scope — no
  CMS" line).
- `/` — Hero (unchanged heading) + real featured products + real category
  showcase + static "Why Choose Bekaa3D" — each data-backed section omits
  itself entirely when the backend returns nothing, never a placeholder.
- Global: `Header`/`Footer` now carry real navigation to `/`, `/shop`,
  `/about` (previously intentionally link-free during FVS-001).
  `GlobalWhatsAppButton` is mounted once in the root layout, reading the
  one shared `usePublicSettings()` query also used by the product page.

### Real backend acceptance — not attempted

No backend checkout or Docker runtime is available in this frontend
workspace (no sibling backend repository; `docker` is not installed on
this machine) — matching FVS-001/002/003/006's own already-documented
"real backend acceptance — still pending" gate. The backend was not
started, no migrations/seed were run, and the local media proxy above was
documented but not executed. This phase is contract-correct against
`openapi.json` and covered by mocked-contract unit/component/E2E tests
only; it has not been exercised against a live backend.

## Current FVS-001 Verification Status

Implementation through FVS001-T16 exists and is committed, but **FVS-001 should not yet be treated as fully signed off**. The following remain open, expected to be closed before/during FVS001-T18's final Definition-of-Done pass:

1. FVS001-T15's real browser/manual accessibility verification (see above).
2. The open focus-ring contrast finding — needs a design/accessibility decision.
3. `npm run test:e2e` run with a real backend **up**.
4. `npm run test:e2e:backend` run with a genuine 2xx from a real backend.
