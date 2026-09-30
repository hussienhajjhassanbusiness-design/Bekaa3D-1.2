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

The browser never learns the backend's real origin. It only ever calls same-origin `/api/...` paths; `next.config.ts`'s `rewrites()` forwards those to the real backend, server-side:

```
frontend request:  /api/:path*
                    ↓ (next.config.ts rewrite, strips the /api prefix)
backend request:    ${API_PROXY_TARGET}/:path*
```

Example: a frontend call to `/api/health/ready` reaches the backend's `GET /health/ready`. `apiClient` itself never constructs or receives an absolute backend URL.

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

Runs **only** `e2e/smoke.spec.ts` (Playwright's `smoke` project in `playwright.config.ts`). Deliberately backend-independent — verified to pass whether or not a real backend is running.

Current coverage: `/` boots (shell landmarks, SkipLink, foundation content); `/does-not-exist` renders 404 content with a working "Back to home" link and the shell still exactly-once afterward; the readiness/banner state is asserted **tolerantly** — whichever valid state is currently showing is accepted, never a hard-coded expectation.

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
