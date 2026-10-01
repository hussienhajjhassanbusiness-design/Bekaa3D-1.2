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

`.env.local.example` (committed) contains:

```
API_PROXY_TARGET=http://localhost:8000
```

Edit `.env.local` to point at wherever you actually run the backend.

- `API_PROXY_TARGET` is read **server-side only**, by `next.config.ts`'s `rewrites()`. It must **never** be renamed with a `NEXT_PUBLIC_` prefix — that would ship the backend's real origin into client-side JavaScript, which this design specifically avoids. There is no `NEXT_PUBLIC_*` variable anywhere in FVS-001.
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

A visitor can register, receive enumeration-safe "check your email" messaging, verify via an emailed link, and resend the verification email with cooldown handling. No auto-login, no new auth/session architecture — that remains FVS-003's scope. See `FVS-002-IMPLEMENTATION-PLAN.md` for the full task-by-task plan and contract-confidence table; this section documents only what is actually committed.

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
- State mapping: **204** → success (with a `/login` link). **400** `INVALID_TOKEN` → one generic "invalid link" state — this deliberately covers an invalid token, a used token, and an already-verified re-click alike, since the backend returns the same code for all three; there is no separate "already verified" success state. **410** `RESOURCE_EXPIRED` → a distinct "expired" state, whose copy always communicates both halves of: "if you already verified your email, log in — otherwise request a new link." Separately, a **429** gets its own safe rate-limit message (using `retryAfterSeconds` when available), and a network/timeout/other failure each get their own safe generic message — these four are the standard transport-failure layer every mutation-consuming page in this slice has, orthogonal to the two token-validity states above (see `FVS-002-IMPLEMENTATION-PLAN.md` §13's BATCH 4 clarification).
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

Runs **only** `e2e/smoke.spec.ts` and `e2e/register-and-verify.spec.ts` (both matched by Playwright's `smoke` project in `playwright.config.ts`). Deliberately backend-independent — verified to pass whether or not a real backend is running.

Current coverage: `/` boots (shell landmarks, SkipLink, foundation content); `/does-not-exist` renders 404 content with a working "Back to home" link and the shell still exactly-once afterward; the readiness/banner state is asserted **tolerantly** — whichever valid state is currently showing is accepted, never a hard-coded expectation. `register-and-verify.spec.ts` (FVS002-T12) proves the full register → check-email → verify → `/login`-prompt flow and a short resend smoke check, both via route interception, never a real backend.

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

`@axe-core/playwright` is **not installed**. `FVS-001-IMPLEMENTATION-PLAN.md` §26 classifies it as "recommended, not mandatory... flagged for the plan reviewer's judgment, not decided unilaterally" — it was never formally accepted. There is currently no automated accessibility scanning in this repository; the verification above is the only accessibility evidence that exists.

## Open Contract Questions

The living list of unconfirmed backend contract items is `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 — this document does not maintain a second, competing copy. Relevant to FVS-001 specifically:

- The RFC 9457 validation-error extension shape (an `errors[]`-style field or similar) is logged there as unconfirmed — `ApiError.raw` is the escape hatch until it's confirmed.
- The correlation/request-ID header name is unconfirmed — `ApiError.correlationId` exists on the type but is never populated by any current code (see its inline comment in `src/lib/api/ApiError.ts`).
- No endpoint or response-body contract beyond the two confirmed health paths (`GET /health/ready`; `GET /health/live`, unused by this slice) exists yet for this frontend to consume.

Do not guess at any of these — confirm with the backend team and update `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 first.

## Current FVS-001 Verification Status

Implementation through FVS001-T16 exists and is committed, but **FVS-001 should not yet be treated as fully signed off**. The following remain open, expected to be closed before/during FVS001-T18's final Definition-of-Done pass:

1. FVS001-T15's real browser/manual accessibility verification (see above).
2. The open focus-ring contrast finding — needs a design/accessibility decision.
3. `npm run test:e2e` run with a real backend **up**.
4. `npm run test:e2e:backend` run with a genuine 2xx from a real backend.
