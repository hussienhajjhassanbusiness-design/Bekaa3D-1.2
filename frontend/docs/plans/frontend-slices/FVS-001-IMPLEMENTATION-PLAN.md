# FVS-001 Implementation Plan — Frontend App Shell, Routing & API Client Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task once it is approved. Steps use checkbox syntax for tracking. Every task also carries `bekaa3d-frontend-slice-dod` obligations — see §28.

**Status:** **READY.** Planning complete, independently reviewed, and the frontend stack formally approved by the project owner (see §29A) — no blocker remains before `FVS001-T01`. No application code has been written yet; this document remains planning-only until implementation is explicitly started.
**Spec:** `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §5 (FVS-001 entry) and `docs/plans/backend/vertical-slice-plan.md` (VS-001) — this plan argues from both; implementers should read both alongside this document.

## 1. Title / Status

FVS-001 — Frontend App Shell, Routing & API Client Foundation. Planning artifact only. Implementation has not started. This document is what gets reviewed before `FVS001-T01` may begin.

## 2. Objective

Stand up the one sanctioned foundation slice (per `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §20, mirroring the backend's own VS-001 exception to "no scaffolding-only work") so that every later frontend slice has a bootable app, a base layout, routing, and a centralized, contract-honest API client to build on — without pulling forward any business logic, auth, or commerce concern that belongs to a later slice.

## 3. Source of Truth

- **Backend contract:** `docs/plans/backend/vertical-slice-plan.md`, VS-001 only. Confirmed endpoints: `GET /health/live`, `GET /health/ready`. No other endpoint is used or assumed.
- **Frontend slice definition:** `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §5, FVS-001 entry (quoted in full in §7 below), plus its cross-cutting sections §3 (architecture assumptions), §7 (shared architecture), §8 (auth architecture — not yet relevant, noted for context only), §9 (API integration architecture), §10 (error handling), §14 (responsive), §15 (accessibility), §17 (contract gaps), §19 (frontend DoD), §20 (merge strategy).
- **Project skills:** `.claude/skills/bekaa3d-brand-ui/` (design tokens), `.claude/skills/bekaa3d-api-contract/` (contract discipline — mandatory for the API client design), `.claude/skills/bekaa3d-frontend-slice-dod/` (completion checklist). `bekaa3d-commerce-ux` was checked and correctly excluded — FVS-001 has no cart/STL/offer/order content for it to apply to.
- **This document does not modify `docs/plans/backend/vertical-slice-plan.md` or `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`.** Any contradiction discovered against either is reported in §8/§29 below, not silently fixed upstream.

## 4. Current Repository State (verified this session)

```
C:/My projects/bekaa3D/
├── .claude/skills/                        (bekaa3d-brand-ui, bekaa3d-api-contract,
│                                            bekaa3d-commerce-ux, bekaa3d-frontend-slice-dod)
├── ChatGPT Image Sep 26, 2026, ...jpg      (brand logo reference)
├── docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md
└── vertical-slice-plan.md
```

Confirmed by direct inspection immediately before writing this plan:
- **No `package.json`** anywhere in the tree.
- **No `src/`, no `.ts`/`.tsx`/`.js`/`.jsx` files**, no `next.config.*`.
- **Not a Git repository** (`git status` fails with "not a git repository").
- No existing frontend application, no established application architecture, no lockfiles, no `.env` files.

This matches the prior environment review exactly — nothing has changed. FVS-001 starts from a genuinely empty slate.

## 5. Scope

Exactly the 25 outcomes listed in the task brief, each mapped to a task in §24:

1. Bootable frontend application · 2. Base application shell · 3. Routing foundation · 4. Root route `/` · 5. Catch-all 404 handling · 6. Base `AppLayout` · 7. Header skeleton · 8. Main content region · 9. Footer skeleton · 10. `ErrorBoundary` (render-error path) · 11. `NotFoundPage` · 12. `LoadingSpinner` · 13. Toast infrastructure (primitive only) · 14. TanStack Query client · 15. Centralized `apiClient` · 16. Health/readiness connectivity check · 17. Development-only backend-unreachable banner · 18. RFC 9457-compatible base problem handling · 19. Network-failure normalization · 20. Request/correlation-ID support where the confirmed contract allows (currently: reserved, not wired — see §8) · 21. Base accessibility foundation · 22. Responsive shell foundation · 23. Unit/component tests · 24. Smoke E2E test · 25. Developer documentation.

## 6. Explicit Non-Scope

FVS-001 will **not** implement, and no task in this plan touches: registration, login, logout, authentication state, customer profile, admin authentication, MFA, cart, wishlist, products, categories, STL store, checkout, payments, offers, reviews, orders, notifications, addresses, admin dashboard, analytics, BYI, contact forms — and no placeholder architecture (empty auth context, stub cart reducer, unused admin route folder, etc.) is created for any of them either. Where a future need is foreseeable (e.g., the API client will eventually carry auth headers), the design leaves room for it without building it now — see §13's "extension points, not speculative features" principle.

## 7. Confirmed Backend Contract

Quoted directly from `docs/plans/backend/vertical-slice-plan.md`, VS-001 (no paraphrase, no invention):

> **Request/response schema:** `LivenessRead`, `ReadinessRead`, RFC 9457 base problem model.
> **Logic / side effects:** Application startup/shutdown, DB connectivity/readiness, request IDs, structured PII-safe logging, global error translation.
> **Endpoint / entrypoint:** `GET /health/live`, `GET /health/ready`.
> **Tests:** App boots; liveness works without DB probe; readiness fails when DB is unavailable; correlation ID present; malformed/error response contract.

What this tells us, precisely:
- `GET /health/live` reflects process liveness only (no DB check) — expected to be fast and almost always successful if the process is up.
- `GET /health/ready` additionally reflects DB connectivity — this is the meaningful signal for "can the app actually do anything," and is the one `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-001 entry already designates as the dev banner's data source.
- Response bodies are named types (`LivenessRead`, `ReadinessRead`) but **no field-by-field shape is given anywhere in the backend plan** — so the frontend must not assume any specific JSON body content. It may key its ready/not-ready decision off **HTTP status code alone** and treat the body as optional, best-effort diagnostic text.
- The backend's own test suite includes "correlation ID present" — so a correlation-ID mechanism exists server-side, but **no header name is given anywhere in `docs/plans/backend/vertical-slice-plan.md`**. The frontend must not guess `X-Request-ID`, `X-Correlation-ID`, or any other name.
- A "malformed/error response contract" test exists on the backend side — the frontend's parser must not assume every response is well-formed JSON.

## 8. Open Contract Questions

Per `bekaa3d-api-contract`, nothing below is resolved by guessing — each is designed around, not assumed:

| # | Question | Blocking? | How this plan handles it in the meantime |
|---|---|---|---|
| 1 | Exact field shape of `LivenessRead`/`ReadinessRead` response bodies | No | `apiClient`/readiness hook key off HTTP status only; body is parsed best-effort and never required |
| 2 | Correlation/request-ID header name (request-side and/or response-side) | No | `ApiError` reserves an optional `correlationId?: string` field, left `undefined`; no header name is read or sent anywhere in FVS-001 code; a `// NEEDS BACKEND CONFIRMATION` comment marks the exact spot to wire it once known |
| 3 | RFC 9457 `errors[]`/validation-extension shape (already logged in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17) | No | `ApiError` carries the five confirmed RFC 9457 fields (`type`/`title`/`status`/`detail`/`instance`) plus a typed `raw: unknown` escape hatch holding the full parsed body — adding a typed accessor for the confirmed extension later does not require touching the parser |
| 4 | CORS for cross-origin requests (frontend dev server vs. backend dev server, different ports) | **Corrected during independent review — this was wrongly marked "No" (non-blocking) in an earlier draft.** CORS applies to *any* cross-origin browser fetch regardless of credentials — dismissing it as "no cookies involved, so not blocking" conflated the credentials question with the separate CORS question. An uncorrected version of this plan would have shipped a dev-only banner that reports "unreachable" even when a healthy backend is running, because the browser's CORS preflight would fail with no `Access-Control-Allow-Origin` header confirmed anywhere in `docs/plans/backend/vertical-slice-plan.md`. **Resolved by design, not deferred** — see §9/§12/§13: FVS-001 routes all backend calls through a same-origin Next.js dev rewrite, so the browser never makes a cross-origin request at all in local development. No backend CORS configuration is required for FVS-001 to work. | `next.config.ts` `rewrites()` proxies `/api/:path*` → the real backend origin (server-side, not browser-side); `apiClient` calls only relative `/api/...` paths |
| 4b | Production cross-origin strategy (once a deployment target exists) | No — genuinely out of scope for FVS-001, since no deployment target has been chosen anywhere in the project documents (§12) | Left open; whichever slice first deploys the app must either configure a production-equivalent proxy/rewrite or get real backend CORS headers confirmed — noted in §29B as a later, non-blocking item |
| 5 | **Frontend stack formal approval** — is Next.js + React + TypeScript + Tailwind + TanStack Query + Vitest + RTL + Playwright + npm actually approved, or still `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §3's self-described "assumptions, not decisions"? | **RESOLVED — approved by the project owner.** See §29A. | No longer a working assumption — this is now the confirmed stack. React Hook Form and Zod were explicitly named as approved *future* technologies, not approved for use *in* FVS-001 — §9/§26's YAGNI deferral of both stands unchanged. |

**Disclosed deviations from `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-001 entry** (per this document's own §3 promise to report, not silently resolve, any contradiction with the master plan — both flagged during independent review, neither found by the original draft):

- **`ErrorBoundary` → `error.tsx`/`global-error.tsx`.** The source entry names a component called `ErrorBoundary`; this plan implements the same responsibility using Next.js App Router's native file-based error-boundary convention instead of a hand-rolled component (§17/T07). Functionally equivalent (App Router's `error.tsx` *is* a React error boundary under the hood), but the naming/architecture substitution is logged here explicitly rather than left implicit.
- **`Toast`'s stated rationale vs. its actual FVS-001 wiring.** The source entry justifies introducing `Toast` in this slice "because the API client needs somewhere to report failures." This plan instead routes all `apiClient`/health-check failures through the dedicated `BackendUnreachableBanner` (§17), leaving `Toast` with no wired trigger in FVS-001 beyond its own component test (T12) — infrastructure for a future slice's mutations, not a consumer of this slice's own failures. The component still gets built (outcome 13 requires it), but the *reason* given in the source document for building it now doesn't match how it's actually used here. Not treated as blocking (Toast's existence is still correct per outcome 13), but disclosed rather than silently diverged from.

## 9. Architecture Decisions Used

Decisions made *for this plan*, each with a reason, each cheaply reversible unless noted:

- **Repository layout:** the Next.js application is scaffolded at the **repository root**, alongside the existing plan documents and `.claude/`, not in a subdirectory like `apps/web`. Reason: this repository is the frontend-only workspace (backend lives elsewhere, per project context established earlier in this engagement); a single-app repo doesn't need a monorepo layout. Reversible (a later move is mechanical) — not treated as blocking.
- **Source layout:** `src/app`, `src/components`, `src/lib` (App Router with a `src/` directory) rather than a rootless `app/` — keeps application code visibly separated from the growing set of root-level planning documents and config files. Standard, supported Next.js option.
- **Same-origin dev proxy instead of a direct cross-origin `fetch` to the backend.** `next.config.ts` uses Next.js's built-in `rewrites()` to forward `/api/:path*` (relative, same-origin from the browser's perspective) to the real backend origin server-side. **Added during independent review** to fix a Critical finding: an earlier draft had the browser call the backend's absolute URL directly and dismissed the resulting CORS requirement as "not blocking for FVS-001" — but CORS applies to any cross-origin fetch regardless of credentials, and no CORS configuration is confirmed anywhere in `docs/plans/backend/vertical-slice-plan.md`. Routing through a same-origin proxy removes the need for backend CORS configuration entirely for local development, and as a side benefit never exposes the real backend origin in client-shipped code (§22). See §12/§13 for the resulting environment/client design.
  **Explicit scope guardrail (per the user's post-approval clarification):** this proxy is a single passthrough `rewrite()` rule and nothing more. It must stay limited to exactly what FVS-001 needs — it does **not** transform requests/responses, inject headers, attach auth/CSRF, branch on path beyond the one `/api/:path*` → backend forwarding rule, or accumulate additional routes/logic as later slices are built. It is not a BFF (backend-for-frontend) and not an API gateway, and no later slice should treat it as one without a fresh, explicit architecture decision — it exists solely to make the browser's request same-origin; the backend remains the sole authority on every business rule, exactly as `bekaa3d-api-contract` requires. If a future slice needs request/response transformation, that is a new, separately-justified decision, not an organic extension of this one.
- **RFC 9457 parsing uses manual type guards, not a schema-validation library.** Only five known fields exist to check; introducing Zod for this would be exactly the kind of forward-provisioning `bekaa3d-api-contract`'s YAGNI framing and this task's own instructions warn against. Zod is deferred to whichever slice first has a real form/complex-payload validation need (expected FVS-002).
- **No toast library.** A single in-house `Toast`/`ToastProvider` primitive is built (a handful of components, no dependency) because FVS-001 has no real toast-triggering event yet (no mutations exist) — evaluating a richer library (stacking, swipe-to-dismiss, promise-based toasts) is deferred to the slice that first needs those features.
- **No `clsx`/`tailwind-merge` or similar class-composition utility.** FVS-001's components (`LoadingSpinner`, `Toast`, banner, layout) have at most two or three boolean states each — plain conditional expressions are sufficient. Deferred until a component's conditional class logic genuinely earns a dependency (a strong future candidate: an admin `StatusBadge` with many variants in a much later slice).
- **Unit/component test mocking uses Vitest's native `fetch` stubbing (`vi.stubGlobal`), not MSW.** The entire mockable surface in FVS-001 is one endpoint family (health). Mock Service Worker's request-interception machinery is justified once request matching gets non-trivial (multiple endpoints, method/body matching) — not yet.
- **Health/readiness decision is HTTP-status-driven, not body-driven** (see §8, item 1) — the single biggest lever for not inventing an unconfirmed response contract.

## 10. Proposed Minimal FVS-001 Structure

Paths below are **proposed**, consistent with the repository-layout decision in §9; if the stack approval in §29 changes the framework choice, this structure is void and must be re-planned, not silently reinterpreted.

```
/
├── package.json
├── tsconfig.json
├── next.config.ts
├── .env.local.example
├── .gitignore
├── eslint.config.mjs
├── vitest.config.ts
├── playwright.config.ts
├── src/
│   ├── app/
│   │   ├── layout.tsx            (root layout — composes providers + AppLayout)
│   │   ├── page.tsx               (root route `/`)
│   │   ├── not-found.tsx          (catch-all 404 — NotFoundPage)
│   │   ├── error.tsx              (segment error boundary)
│   │   ├── global-error.tsx       (root-level safety net)
│   │   └── globals.css            (Tailwind entry + brand CSS variables)
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppLayout.tsx
│   │   │   ├── Header.tsx
│   │   │   ├── Footer.tsx
│   │   │   └── SkipLink.tsx
│   │   └── feedback/
│   │       ├── LoadingSpinner.tsx
│   │       ├── Toast.tsx
│   │       ├── ToastProvider.tsx
│   │       └── BackendUnreachableBanner.tsx
│   └── lib/
│       ├── api/
│       │   ├── ApiError.ts
│       │   ├── problem.ts          (RFC 9457 parsing)
│       │   └── apiClient.ts
│       ├── query/
│       │   ├── queryClient.ts
│       │   └── QueryProvider.tsx
│       └── health/
│           └── useReadiness.ts
├── e2e/
│   └── smoke.spec.ts
└── docs/
    └── frontend-setup.md
```

No folder is created for a feature that doesn't exist yet (no `auth/`, `cart/`, `products/`, etc. — matching §6).

## 11. Dependency Strategy

Full table in §26. Governing rule restated: **a package is introduced by the task that has a genuine, present need for it — never because a later slice will probably want it.** Every dependency below is traceable to a specific FVS-001 outcome; RHF, Zod, a toast library, and class-utility helpers are named explicitly as deferred, with the reasoning in §9.

## 12. Environment Strategy

**Redesigned during independent review** around the same-origin dev proxy (§9) to close the CORS gap in §8, item 4.

- **`API_PROXY_TARGET`** — the only environment variable FVS-001 needs, read **server-side only**, by `next.config.ts`'s `rewrites()` function (which runs in Node during `next dev`/`next build`, never shipped to the browser). **Deliberately not `NEXT_PUBLIC_`-prefixed** — the browser never needs to know the backend's real origin, since it only ever calls the same-origin `/api/...` path. This is a strict security improvement over an earlier draft that planned to expose the backend origin via `NEXT_PUBLIC_API_BASE_URL`: the real backend URL now never appears in client-shipped JavaScript at all.
- **`apiClient` itself takes no base-URL configuration** — it calls relative paths (e.g., `/api/health/ready`), which Next.js's dev server resolves same-origin and the rewrite forwards server-side. No `NEXT_PUBLIC_*` variable exists in FVS-001 at all.
- **Local development:** `.env.local` (git-ignored, developer-created from `.env.local.example`) sets `API_PROXY_TARGET=http://localhost:8000` (or wherever the developer runs the FastAPI backend) — exact value is a local dev convenience, not a contract detail.
- **Production:** out of scope for FVS-001 (no deployment target has been decided anywhere in the project documents, §29B item 4b) — whichever slice first deploys the app must either configure an equivalent production rewrite/proxy or get real backend CORS headers confirmed and switch `apiClient` to an absolute, `NEXT_PUBLIC_`-exposed URL at that time.
- **What may be exposed client-side:** nothing, in this slice — there is no `NEXT_PUBLIC_*` variable at all for FVS-001, which is the strongest possible answer to "what must never be exposed."
- **What must never be exposed:** no secret, token, or credential exists in FVS-001 at all (no auth yet); the rule (never prefix a future secret with `NEXT_PUBLIC_`) is stated here so later slices inherit the right instinct even though nothing in this slice tests it yet.
- No real secret value is created anywhere in this plan or its tasks.

## 13. API Client Design

The centralized `apiClient` is the highest-leverage, highest-risk piece of this slice — every later slice depends on it, so its contract is designed to be extended, not rewritten.

**Core shape (types, not yet implementation):**

```ts
// src/lib/api/ApiError.ts
export type ApiErrorKind = "http" | "network" | "timeout" | "parse";

export interface ApiError {
  kind: ApiErrorKind;
  status?: number;              // present for kind: "http"
  type?: string;                // RFC 9457 `type` — confirmed field
  title?: string;                // RFC 9457 `title` — confirmed field
  detail?: string;               // RFC 9457 `detail` — confirmed field
  instance?: string;             // RFC 9457 `instance` — confirmed field
  correlationId?: string;        // reserved — NEEDS BACKEND CONFIRMATION, never populated in FVS-001
  message: string;               // safe, user-facing fallback text — never the raw `detail` verbatim in production
  raw: unknown;                  // full parsed body (or raw text) for dev diagnostics only — never rendered to end users
}
```

**`apiClient` responsibilities (implemented in `FVS001-T09`, building on `FVS001-T08`'s parser and `FVS001-T10`'s env config):**

1. **Calls only relative paths** (e.g., `apiClient.get("/api/health/ready")`), never an absolute cross-origin URL — **corrected during independent review**: an earlier draft read an absolute base URL from `NEXT_PUBLIC_API_BASE_URL` and called the backend directly, which would have failed CORS preflight with no backend CORS configuration confirmed anywhere in the backend plan. The relative path resolves same-origin against whatever host serves the Next.js app; `next.config.ts`'s `rewrites()` (§9/§12) forwards it server-side to the real backend. There is no base-URL configuration inside `apiClient` itself to get wrong.
2. Issue the request via native `fetch`, with an `AbortController`-driven timeout (a frontend-only operational default, not a backend contract — proposed 10s for the health check specifically, overridable per call).
3. `credentials` mode defaults to `'same-origin'` (fetch's own default) — **not** explicitly set to `'include'` anywhere in this slice. Now doubly appropriate: the request is same-origin by construction (point 1), so there is no cross-origin credentials question to answer for FVS-001 at all.
4. On a thrown network error (fetch rejecting before any response — offline, DNS failure, connection refused, **or the dev server's rewrite target itself being unreachable**, which surfaces to the browser as an ordinary failed same-origin response, not a CORS error): normalize to `ApiError` with `kind: "network"`.
5. On an aborted request (timeout): normalize to `ApiError` with `kind: "timeout"`.
6. On a **2xx response specifically**, attempt `response.json()`; if the body is empty or genuinely unparseable (a bare `200` with no body is an entirely plausible shape for a liveness/readiness check, and `response.json()` throws on an empty body) — **clarified during independent review, an earlier draft left this ambiguous** — this is still treated as **success**, with the resolved value being `undefined`, not an `ApiError`. A 2xx response is never turned into an error solely because its body didn't parse.
7. On any **non-2xx response**, attempt `response.json()`:
   - If it parses and looks like an RFC 9457 problem body (has at least one of `type`/`title`/`status`/`detail`), populate the confirmed fields and set `raw` to the full parsed object.
   - If it parses but doesn't look like a problem body, still capture it in `raw`, leave the RFC 9457 fields undefined.
   - If it doesn't parse (non-JSON or empty body), set `kind: "parse"`, capture the raw text (bounded length) in `raw`.
   - In every non-2xx case, always return/throw an `ApiError` with `kind: "http"` and the real HTTP `status`, regardless of whether the body parsed.
8. For a 2xx response with a parseable body, return the parsed JSON body directly (no `ApiError` wrapper) — callers only ever deal with `ApiError` on the failure path.
9. `message` (the safe user-facing string) is derived from a small status-code-keyed fallback table (e.g., "Something went wrong. Please try again." for 5xx, "We couldn't reach the server." for network/timeout) — **never** the raw backend `detail` text verbatim, since that field's safety for end-user display is unconfirmed (§22 Security Review).
10. Request-ID/correlation-ID: **not read or sent in FVS-001.** The `correlationId` field exists on the type for forward compatibility; wiring it is a one-line change once the header name is confirmed, not a redesign.
11. **Redirects:** relies on `fetch`'s default `redirect: "follow"` behavior; no task in FVS-001 needs to distinguish a redirected response from a direct one, and no redirect is expected from a health-check endpoint — noted here so a future slice that *does* care about redirect behavior knows this wasn't a deliberate design decision, just the platform default.

**What the `apiClient` explicitly does NOT do in FVS-001:** attach auth headers, attach a CSRF header, retry non-idempotent requests automatically, cache responses itself (TanStack Query owns caching), configure or expose any absolute backend URL (point 1), or assume any endpoint beyond the two confirmed health paths.

## 14. RFC 9457 Handling

Implemented in `src/lib/api/problem.ts` (`FVS001-T08`), consumed by `apiClient` (`FVS001-T09`). Handles exactly the five confirmed fields — `type`, `title`, `status`, `detail`, `instance` — via manual TypeScript type guards (`typeof body === "object" && body !== null && ...`), not a schema library (§9). The parser's return type always includes the `raw: unknown` escape hatch so that when the `errors[]`/field-validation extension shape is eventually confirmed (`docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17), a later slice adds a typed accessor over `raw` — the parser itself does not need to change. This is deliberately the smallest amount of structure that both (a) uses the fields we're actually sure of and (b) doesn't lose any data the backend actually sent.

## 15. Query Client Design

- **Library:** `@tanstack/react-query` v5 (current major as of this plan; confirmed via current TanStack docs during this planning session — `gcTime` is the current name, `cacheTime` was renamed in v5; default `staleTime` is `0` and default `retry` is `3` with exponential backoff unless overridden).
- **`QueryClient` instantiation (`FVS001-T11`):** one singleton created in `src/lib/query/queryClient.ts`, **no speculative global `defaultOptions`** beyond what FVS-001 itself needs. The health/readiness query configures its *own* `staleTime: 0` (a liveness signal should never be considered "fresh" from cache) and a bounded `retry` (proposed: 2 retries with short backoff — not the default 3, since a dev-only diagnostic banner shouldn't hang for long before telling the developer something's wrong) at the query-hook level, not globally.
- **Provider placement:** `QueryProvider` (thin wrapper around `QueryClientProvider`) is composed into `src/app/layout.tsx`, wrapping `AppLayout`. It is a Client Component (`'use client'`) since `QueryClientProvider` requires client-side React context.
- **No React Query Devtools dependency added** — genuinely optional for a slice this small; noted as a reasonable *if the implementer wants it*, not required (kept out of the dependency table in §26 as a judgment call for the implementer, not a plan requirement).

## 16. Health/Readiness Design

Two endpoints, two distinct roles (§7):

| Endpoint | Meaning | FVS-001 usage |
|---|---|---|
| `GET /health/live` | Process is up (no DB check) | **Not used by FVS-001.** No UI need for a liveness-only signal exists yet — using `/health/ready` alone is sufficient for the dev banner's purpose (§10 of the task brief scopes this to "development-only readiness check"). Documented here so a future slice doesn't have to rediscover why only one of the two confirmed endpoints is wired up. |
| `GET /health/ready` | Process up **and** DB reachable | Polled by `useReadiness` (`FVS001-T13a`) to drive the dev-only banner (`FVS001-T13b`) |

**State matrix for `useReadiness` / `BackendUnreachableBanner`:**

| Backend condition | HTTP result the client sees | UI state |
|---|---|---|
| Healthy | 2xx | No banner (silent success) |
| Not ready (DB down, backend up) | Non-2xx from a reachable server (exact status code not confirmed by VS-001 — `NEEDS BACKEND CONFIRMATION`; handling is status-class-driven, not tied to a specific code) | Banner: "Backend is up but not ready" (distinct copy from unreachable) |
| Unreachable (backend process not running) | `fetch` throws (`ApiError.kind: "network"`) | Banner: "Cannot reach the backend at `<base URL>`" |
| Timeout | `AbortController` fires (`ApiError.kind: "timeout"`) | Banner: "Backend did not respond in time" |
| Malformed response body | 2xx or non-2xx with unparseable body | Treated by HTTP status alone (§8, item 1) — a malformed body never blocks determining ready vs not-ready, only affects whether extra diagnostic text is available |

- **Loading state:** `LoadingSpinner` shown only during the *first* check; subsequent background refetches do not flash the spinner (TanStack Query's `isLoading` vs `isFetching` distinction — the banner logic uses `isLoading` for the initial mount only).
- **The banner is excluded from production builds entirely** — gated on `process.env.NODE_ENV === "development"` at the component level, not just visually hidden, so it never ships in the client bundle shipped to real users (§16 Security Review).
- **No polling storm:** the readiness query uses a bounded refetch interval appropriate for a dev diagnostic (proposed: refetch every 15s while the tab has focus, via TanStack Query's `refetchInterval` + `refetchIntervalInBackground: false`), not an aggressive tight loop.

## 17. Error-Handling Design

Four categories, four distinct mechanisms — never funneled through one generic handler (per the task brief's explicit instruction):

| Category | Mechanism | Owner component/file | Why separate |
|---|---|---|---|
| A. React/render failures (a component throws during render) | Next.js App Router's native error boundary convention | `src/app/error.tsx` (segment-level), `src/app/global-error.tsx` (root-level safety net, production-only per Next.js's own behavior — dev uses Next's built-in overlay) | This is a genuine crash — the tree is broken and needs a fallback UI + `reset()` affordance, not a toast |
| B. API Problem responses (a `GET /health/ready` call returns a well-formed non-2xx) | `ApiError` object returned to the caller (TanStack Query's `error` state) | `apiClient` / `useReadiness` → consumed by `BackendUnreachableBanner` | This is expected, recoverable application state, not a crash — must never trip the React error boundary |
| C. Network failures (unreachable, timeout) | Same `ApiError` path as B, discriminated by `kind` | Same as B | Distinguished from B only by `kind`, not by mechanism — both are "the query failed," rendered by the same banner with different copy |
| D. Route-not-found | Next.js App Router's `notFound()` / `not-found.tsx` convention | `src/app/not-found.tsx` | An expected outcome (bad URL), not a crash and not an API failure — gets a real page and a real HTTP 404 status, not a boundary fallback |

`Toast` is **not** a fifth error mechanism in this slice — per the task brief, the backend-unreachable condition uses the dedicated banner, not repeated toast firing. The `Toast` primitive exists in FVS-001 purely as infrastructure (§13 of the brief) for slices that will have real transient-success/failure events (form submissions, mutations) — it has no wired trigger in FVS-001 beyond what its own component test exercises directly.

## 18. App Shell / Routing Design

- **`AppLayout`** (`FVS001-T05a` for landmarks/`SkipLink`, `FVS001-T05b` for `Header`/`Footer` content): composes `SkipLink` → `Header` (skeleton — no nav items, since none exist yet per §6) → `<main>` (content region, the route's actual page renders here) → `Footer` (skeleton). This is the one layout every route in the app will eventually pass through.
- **Root layout (`src/app/layout.tsx`, `FVS001-T14`):** the composition root — wraps `AppLayout` with `QueryProvider` and `ToastProvider`, mounts `BackendUnreachableBanner` (dev-only) and the readiness check. This is intentionally the *only* file that knows about all of these pieces at once; individual components don't reach into each other.
- **Root route (`src/app/page.tsx`, `FVS001-T06`):** renders inside `AppLayout`'s main region. Content is a minimal placeholder (e.g., "Bekaa3D — Engineered Grade 3D Solutions" from the brand tagline, plus a note that this is the foundation slice) — **not** a home page; F-001 (the real Home page) is FVS-022's job, not this slice's.
- **Catch-all 404 (`src/app/not-found.tsx`, `FVS001-T06`):** renders `NotFoundPage` content inside the same `AppLayout` shell (consistent chrome even on an error page), with a link back to `/`.
- **No other routes exist.** No `/shop`, `/login`, `/account`, etc. — creating empty route folders for future slices is exactly the "placeholder business architecture" §4/§6 forbids.

## 19. Brand/UI Foundation

Built directly from `bekaa3d-brand-ui`'s `tokens.md` — no new design system, no deviation:

- **Color tokens** (`FVS001-T03`) become CSS custom properties in `src/app/globals.css` (`--brand-dark-green: #195B2D`, `--brand-lime: #8AC143`, `--brand-green: #3D793A`, `--ink: #21201F`, plus the neutral scale and semantic colors), then exposed to Tailwind via `tailwind.config` theme extension — so every later slice's component styles reference the same token names the skill defines, not ad hoc hexes.
- **Typography, spacing, radius:** Tailwind theme extended with the skill's type scale, 4px spacing scale, and radius tokens — used by `AppLayout`/`Header`/`Footer`/`LoadingSpinner`/`Toast`/banner, the only components that exist yet.
- **Focus ring:** the skill's `focus-ring` token (`0 0 0 2px white, 0 0 0 4px #8AC143`) implemented once, globally, in `globals.css` as the default `:focus-visible` treatment — every later slice inherits it instead of reinventing focus styles (this is explicitly called out as this slice's responsibility in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-001 entry).
- **No admin-density tokens, no product/STL card styles, no button-hierarchy components beyond what `AppLayout`'s own skeleton needs** — those are real needs of later slices (FVS-011 admin, FVS-013 catalogue), not this one.

## 20. Responsive Requirements

Per `bekaa3d-brand-ui`/`docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §14 breakpoints (mobile ≤767px, tablet 768–1023px, desktop ≥1024px), verified 320px through large desktop:

- `AppLayout` grid/flex structure works at all widths without horizontal scroll or overflow.
- **Header below 768px:** the task brief explicitly warns against building "meaningless complex mobile-navigation behavior" for zero nav items. **Revised during independent review:** an earlier draft reserved an inert, unused hamburger-toggle `<button>` "for later" — itself exactly the kind of speculative scaffolding this document argues against everywhere else (§9). FVS-001's header skeleton (`FVS001-T05b`) contains no nav-toggle element of any kind; a future slice adding the first real navigation item adds the toggle then, at negligible cost, once it has something real to toggle. This is a stricter, more consistent reading of "minimum structural support required so later navigation can be added cleanly" than the earlier draft's placeholder button.
- Footer skeleton stacks cleanly at narrow widths (no fixed-width content that would overflow).
- `BackendUnreachableBanner` and `Toast` render legibly and don't obscure the skip link or main content at 320px.

## 21. Accessibility Requirements

Explicit, verified in `FVS001-T15`:

- **Skip-to-content link** (`SkipLink`, part of `FVS001-T05a`): first focusable element in the DOM, visually hidden until focused, jumps to `<main id="main-content">`.
- **Landmarks:** `<header>`, `<main>`, `<footer>` are real semantic elements (not `<div>`s with ARIA roles bolted on), each present exactly once per page.
- **Semantic HTML** throughout — no `<div onClick>` standing in for a `<button>`.
- **Keyboard navigation:** every interactive element in this slice (skip link, toast dismiss control, banner if dismissible — no header button/toggle exists in FVS-001 at all, per §9/T05b's review-driven removal of the earlier speculative placeholder) is reachable and operable via keyboard alone — verified manually in `FVS001-T15` and by component tests where behavior exists (`FVS001-T04`/`T05a`/`T05b`/`T12`).
- **Visible focus indicators:** the brand focus-ring token (§19), applied globally — **no global CSS ever sets `outline: none` without an equivalent visible replacement**, checked explicitly in `FVS001-T15` and part of `FVS001-T18`'s final review.
- **Logical focus order:** DOM order matches visual order (skip link → header → main → footer); no `tabindex` values above 0 anywhere.
- **Minimum contrast:** brand token pairs (e.g., `ink` on `white`, `white` on `brand-dark-green`) checked against WCAG AA (4.5:1 body text / 3:1 large text) during `FVS001-T03`; the tokens as sampled are expected to pass but this is verified, not assumed.
- **Reduced motion:** `LoadingSpinner`'s animation and `Toast`'s enter/exit transition respect `prefers-reduced-motion` (reduced to a simple opacity change or no animation) — small, cheap to do correctly from the start.
- **Accessible error/banner semantics:** `BackendUnreachableBanner` uses `role="status"` or `role="alert"` as appropriate (status for "not ready," alert for "unreachable" — a genuine failure the developer needs to notice immediately) with `aria-live`; `Toast` uses `role="status"`/`aria-live="polite"`; the render-error fallback (`error.tsx`) has a clear heading structure so it's announced properly.

## 22. Security Review

Reviewed against Security Guidance's areas of concern, scoped to what actually exists in FVS-001 (no auth/payment/upload features exist yet to review):

| Area | Finding | Action taken in this plan |
|---|---|---|
| Environment-variable exposure | **Improved during independent review's CORS fix (§8/§9/§12):** the earlier draft's `NEXT_PUBLIC_API_BASE_URL` would have exposed the real backend origin in client-shipped JavaScript. The corrected design has **zero** `NEXT_PUBLIC_*` variables in FVS-001 — `API_PROXY_TARGET` is server-only | Documented in §12; T10 explicitly forbids `NEXT_PUBLIC_` prefixing it |
| API base URL handling | Must not be hardcoded; the browser must never construct or receive an absolute backend URL | `apiClient` calls only relative `/api/...` paths (§13, point 1); the real origin lives only in `next.config.ts`'s server-side rewrite (T10) |
| CORS | An earlier draft dismissed this as non-blocking, which was itself the Critical finding that drove the proxy redesign (§8, item 4) | Resolved by design — same-origin proxy means no cross-origin request, and therefore no CORS exposure, exists in FVS-001 at all |
| Server/client boundary | `apiClient`, `QueryProvider`, `Toast`, `error.tsx` all need `'use client'` (hooks/browser APIs); no server-only secret exists yet to leak across the boundary | Explicit `'use client'` requirement called out per-component in §10/§13/§17; documented as a standing rule in `FVS001-T17` for when server-only data *does* eventually exist |
| Dangerous HTML rendering | Nothing in FVS-001 renders backend-supplied or user-supplied content via `dangerouslySetInnerHTML` | `ApiError.detail`/`raw` are rendered as plain text (React's default escaping) wherever they appear (dev banner only) — never injected as raw HTML; stated as a standing rule, not just a current-state observation |
| Error-message leakage | RFC 9457 `detail` safety for end-user display is unconfirmed; `raw` may contain backend internals | `ApiError.message` (safe, status-keyed fallback text) is the only field ever shown to a production end user; `detail`/`raw` are dev-diagnostic-only and the banner that shows them is compiled out of production entirely (§16, mount-point gating per T13b/T14's corrected design) |
| Backend Problem Details leakage | Same as above — no PII is plausible in a health-check context, but the *pattern* matters for every later slice that reuses this client | The safe-message/raw-diagnostic split (§13) is designed once here so later slices don't have to invent it under time pressure |
| Request headers | No auth/CSRF headers sent in FVS-001 (nothing to leak) | Explicitly listed as **not** implemented in §13's "what the apiClient does NOT do" |
| Credentials | No session exists yet, and the request is same-origin by construction | `credentials` mode defaults to `'same-origin'`, never `'include'` (§13, point 3) — not a CORS-driven concern anymore, just standing practice ahead of FVS-003 |
| Secrets | None exist | `.gitignore` excludes `.env.local` from the first commit (`FVS001-T01`) as standing practice, even though no secret exists yet |
| Production vs development diagnostics | The unreachable banner and any verbose `ApiError.raw` logging must never ship to production users; naively gating *inside* the banner component would still run its polling hook in production (React hooks can't be conditionally called) | **Corrected during independent review:** the `NODE_ENV === "development"` gate lives at the mount point in `FVS001-T14`'s root layout, not inside `BackendUnreachableBanner` itself (§16, T13b, T14) — the component and its polling hook are simply never mounted in production, not hidden-but-running |
| Dependency selection | All proposed packages (§26) are from their respective official/maintaining organizations (Vercel/Next.js, TanStack, Testing Library, Vitest/Vite team, Microsoft/Playwright) — no obscure or unmaintained packages | No further action needed; noted for the record |

**No finding in this review blocks or changes any task below.** No authentication, CSRF, or security feature belonging to a later slice was introduced to "get ahead" of a risk — the mitigations above are all things FVS-001 itself must do correctly, not early auth work.

*(Note on "Security Guidance" as referenced throughout this document: this refers to the `security-guidance` Claude Code plugin installed and verified connected during this project's environment-setup task — an Anthropic first-party plugin providing pattern-based security warnings and diff review, not a project-specific skill among the four `bekaa3d-*` skills. Listed here for disambiguation since, unlike Context7's non-availability, its availability was never separately re-verified within this planning session.)*

## 23. Testing Strategy

Mechanism decisions (§9): Vitest + React Testing Library for unit/component tests, native `fetch` stubbing (`vi.stubGlobal`) for mocking — no MSW. Playwright for E2E. The default, deterministic E2E suite (`npm run test:e2e`) requires no real running backend to pass (§27, risk #11) — designed to tolerate the backend being absent (see below). A second, separately-scripted E2E spec (`npm run test:e2e:backend`, `FVS001-T16` action 4, added per post-approval clarification) *does* require a real backend, deliberately and only there, to prove genuine connectivity to VS-001 before the slice is considered done (`FVS001-T18`).

**TDD applicability policy** (referenced throughout §24 as "§23"): a task follows full RED-GREEN-REFACTOR when it implements real logic or rendered behavior with checkable output (component primitives, the RFC 9457 parser, the `apiClient`, the readiness hook/banner, the error boundary). A task is **configuration validation, not TDD**, when its output is "does this tool/setting behave as configured" rather than "does this logic produce the right result" — bootstrap (T01), lint/type/test-runner setup (T02), token/style wiring (T03), env config (T10), the QueryClient singleton itself (T11, though its one consumer, the readiness hook, is fully TDD'd), and integration/composition (T16) all fall here: they're verified by running the relevant command and observing the result, not by a red-then-green unit test. Routing (T07) is a hybrid — the *page content* is TDD'd as a component, but *the URL routing itself* is Next.js file-based configuration, verified by the dev server and the E2E smoke test (T18), not a unit test.

**API client (`FVS001-T08`/`T09`):**
- Successful 2xx response → parsed JSON returned directly.
- RFC 9457 problem response (well-formed, matching fields) → `ApiError` with correct `type`/`title`/`status`/`detail`/`instance`.
- Malformed/non-JSON problem-shaped response → `ApiError` with `kind: "parse"`, raw text captured, no thrown exception escapes the client.
- Non-JSON error body generally (e.g., an HTML error page from a misconfigured proxy) → same `kind: "parse"` path, doesn't crash the caller.
- Network failure (`fetch` rejects) → `ApiError` with `kind: "network"`.
- Timeout/abort → `ApiError` with `kind: "timeout"`, fired at the configured duration, not late/never.

**Error boundary (`FVS001-T07`):**
- A child component that throws during render → `error.tsx` fallback renders, with a working `reset()` control.
- Fallback UI itself renders inside the brand shell (not a bare unstyled crash page).

**Health check (`FVS001-T13a`/`T13b`):**
- Ready (mocked 2xx) → no banner.
- Not ready (mocked non-2xx from a reachable stub) → banner, "not ready" copy.
- Unreachable (mocked network-error) → banner, "unreachable" copy.
- Timeout (mocked hang past the configured duration) → banner, "timed out" copy.

**Routing (`FVS001-T06`, verified further in `FVS001-T16`):**
- `/` renders `AppLayout` + root page content.
- An unknown path renders `NotFoundPage` content inside the same shell.
- (Note: file-based routing itself has little logic to unit-test — this is primarily configuration validated by the dev server booting and the E2E smoke test, not a RED/GREEN unit cycle; see §27.)

**Accessibility (`FVS001-T15`):**
- Landmark presence (`header`/`main`/`footer`) — component test asserting on rendered roles.
- Skip link is the first focusable element and moves focus to `<main>` on activation — component test.
- Critical keyboard/focus behavior (tab order, visible focus ring class applied) — manual verification pass, documented in `FVS001-T15`'s own notes, supplemented by an automated `@axe-core/playwright` assertion on `/` and the 404 page if that dependency is accepted (§26 — recommended, not mandatory).

**E2E smoke (`FVS001-T16`):**
- Application boots and `/` renders the shell (title, landmarks present).
- Navigating to an unknown path renders 404 content with a working link back to `/`.
- The readiness/banner path is exercised **tolerantly**: the test asserts the app renders a coherent state either way (banner present *or* absent) rather than requiring a specific backend state — because the smoke test must pass in CI/local runs where the FastAPI backend may not be running (§27, risk #11). A separate, explicitly backend-dependent spec (`e2e/backend-connectivity.spec.ts`, its own script, `FVS001-T16` action 4) **is** added, deliberately kept out of the default deterministic run, to prove real connectivity to VS-001 before the slice is complete.

No test in this plan asserts against an assumed `LivenessRead`/`ReadinessRead` body shape (§8) — all readiness-state tests key off HTTP status/network outcome, matching the `apiClient` design.

## 24. Detailed Task Breakdown

### FVS001-T01 — Repository & Next.js Bootstrap

**Purpose:** Create the actual application skeleton so every later task has something to modify. This is the one task in the whole slice that is pure scaffolding, matching the backend's own VS-001 exception to "no scaffolding-only work."
**Depends on:** None.
**Files expected to be created/modified:** `package.json`, `next.config.ts`, `tsconfig.json` (initial, generic — tightened in T02), `.gitignore`, `src/app/layout.tsx` and `src/app/page.tsx` (framework defaults, rewritten by later tasks), local Git repository (`.git/`) if not already initialized.
**Implementation actions:**
1. Confirm §29's blocking stack-approval question has been answered before starting.
2. If the directory is not already a Git repository, run `git init` (local only — no remote is added, per §7 of the task's "operating mode").
3. Scaffold Next.js with TypeScript, Tailwind, ESLint, App Router, and `src/` directory enabled (via the framework's own official scaffolding tool, using current stable versions — do not pin exact versions in this plan per §26).
4. Confirm the dev server starts and serves the framework's default page at `/`.
5. Add a repository-root `.gitignore` covering `node_modules/`, `.next/`, `.env*.local`, build artifacts, and editor/OS cruft.
6. Make the first local commit (scaffold only) so later tasks have a clean diff baseline — no remote push (forbidden by the task's operating mode).
**Do NOT:** add any dependency beyond what the scaffolding tool itself installs; write any application-specific component; configure Vitest/Playwright yet (T02/T16); touch `docs/plans/backend/vertical-slice-plan.md` or `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`.
**Tests:** None yet — this task is verified by observation, not by a test suite that doesn't exist yet.
**Acceptance criteria:** `npm run dev` starts without error; the default page loads in a browser; `git log` shows one commit; `git status` is clean.
**Verification:** `npm run dev` (manual check), `git status`, `git log --oneline`.
**Skills/tools:** Superpowers (`using-git-worktrees` is relevant only if implementation happens in an isolated worktree — a per-implementation choice, not fixed by this plan). No Context7/Security Guidance/project skills genuinely apply to raw scaffolding.

---

### FVS001-T02 — TypeScript, Lint, Test-Runner & Script Configuration

**Purpose:** Tighten the framework's default TypeScript/ESLint configuration, install and configure the unit/component test runner, and establish every `package.json` script later tasks' "Verification" steps rely on (`lint`, `typecheck`, `test`, `test:e2e`, `build`). **Corrected during independent review:** an earlier draft of this plan deferred test-runner setup to an undefined "T-suite" and left `test` as a placeholder script, while `FVS001-T04` (the first task to write real component tests) silently assumed a working runner already existed. That gap is closed here — no later task may assume Vitest/RTL exist until this task actually installs and configures them.
**Depends on:** `FVS001-T01`.
**Files expected to be created/modified:** `tsconfig.json`, `eslint.config.mjs` (or the framework's current default lint config file), `package.json` (`scripts`/`devDependencies`), `vitest.config.ts`, `vitest.setup.ts` (or equivalent RTL/jsdom setup file).
**Implementation actions:**
1. Enable TypeScript `strict: true` (and `noUncheckedIndexedAccess` if not already default) in `tsconfig.json`.
2. Set up path aliases consistent with §10's structure (e.g., `@/*` → `src/*`) if not already provided by the scaffold.
3. Install Vitest, its React plugin, `jsdom` (or `happy-dom`), and the Testing Library stack (`@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`) per §26's dependency table.
4. Create `vitest.config.ts` (jsdom/happy-dom environment, React plugin) and a setup file that extends `expect` with `@testing-library/jest-dom`'s matchers.
5. Add `package.json` scripts: `dev`, `build`, `start` (scaffold defaults, confirm present), `lint`, `typecheck` (`tsc --noEmit`), `test` (real Vitest invocation — no longer a placeholder), `test:e2e` (placeholder until `FVS001-T16`, since Playwright isn't installed until then).
6. Write and run one throwaway test (e.g., `expect(true).toBe(true)` inside a minimal RTL render) to prove the runner, jsdom environment, and RTL matchers are actually wired together — then delete the throwaway test once proven.
7. Confirm `npm run lint`, `npm run typecheck`, and `npm run test` all exit 0 against the scaffold's own default files/the (now-deleted) throwaway test's absence.
**Do NOT:** add Prettier or any formatting tool not already bundled with the scaffold's default ESLint config — not required by any DoD item, deferred as a team-preference decision outside this plan's scope; add any business-logic file; install Playwright here (that's `FVS001-T16`'s job, since nothing before it needs E2E).
**Tests:** Configuration validation, not TDD (§23) — verified by running the scripts, including the throwaway prove-it-works test described in action 6, not by a red/green cycle of real application behavior.
**Acceptance criteria:** `npm run lint` exits 0; `npm run typecheck` exits 0; `npm run test` runs Vitest successfully (0 tests, since the throwaway was deleted, but a non-error exit) against a real Vitest invocation, not a placeholder script; introducing a deliberate type error locally causes `typecheck` to fail (sanity-checked once, not left in the codebase).
**Verification:** `npm run lint`, `npm run typecheck`, `npm run test`.
**Skills/tools:** None of the five project/Superpowers/Context7/Security-Guidance tools materially apply to config tightening beyond general care.

---

### FVS001-T03 — Brand Design Tokens & Global Styles

**Purpose:** Make `bekaa3d-brand-ui`'s tokens the actual source of visual truth in code, not just documentation, before any component is styled.
**Depends on:** `FVS001-T01`. (Parallel-safe with `FVS001-T02` — different files, no shared state.)
**Files expected to be created/modified:** `src/app/globals.css`, `tailwind.config.ts` (or the current Tailwind config mechanism for the installed major version — confirm via current docs at implementation time, since Tailwind's setup differs between v3 and v4).
**Implementation actions:**
1. Re-read `.claude/skills/bekaa3d-brand-ui/tokens.md` §§1–9 (colors through elevation) in full before starting.
2. Define brand/semantic/neutral colors as CSS custom properties in `globals.css`.
3. Extend Tailwind's theme with those tokens (color names, spacing scale, radius scale, type scale) so components reference `bg-brand-dark-green` etc., not raw hex utilities.
4. Implement the global `:focus-visible` treatment using the skill's `focus-ring` token — verify it is not overridden or removed by any scaffold default.
5. Verify the brand token color pairs actually used in this slice (`ink` on `white`, `white` on `brand-dark-green`) meet WCAG AA contrast (manual check with a contrast checker, recorded as a one-line note in this task's completion evidence).
**Do NOT:** invent new colors not in `tokens.md`; build the admin-density token set (no admin UI exists); build product/STL card styles.
**Tests:** Not TDD — configuration/visual validation. A lightweight smoke test may assert the CSS custom properties exist in the compiled stylesheet, but this is optional.
**Acceptance criteria:** Tailwind utilities using brand token names compile and render the correct colors in a browser; a focused interactive element shows the brand focus ring; contrast check recorded as passing.
**Verification:** Visual check in a browser at `/` once `FVS001-T06` exists (this task's own output is only verifiable in isolation via a temporary test element, then re-verified once real components consume it).
**Skills/tools:** `bekaa3d-brand-ui` (mandatory — this task *is* that skill's tokens becoming code).

---

### FVS001-T04 — Shared Primitive: `LoadingSpinner`

**Purpose:** Provide the one small, reusable loading indicator that `useReadiness`'s initial-load state (`FVS001-T13a`) needs, built once rather than inline.
**Depends on:** `FVS001-T02` (needs a working test runner — see that task's corrected scope), `FVS001-T03`. (Parallel-safe with `FVS001-T12`.)
**Files expected to be created/modified:** `src/components/feedback/LoadingSpinner.tsx`, `src/components/feedback/LoadingSpinner.test.tsx`.
**Implementation actions:**
1. Write a failing component test: renders with `role="status"`, includes visually-hidden accessible text (e.g., "Loading…"), respects `prefers-reduced-motion` (asserted via a class/style check, not real media-query simulation if that's impractical in jsdom — document the limitation).
2. Implement the minimal component to pass.
3. Confirm the spin animation uses a CSS transform/opacity approach that degrades cleanly under reduced motion.
**Do NOT:** add size/color variant props speculatively — a single default size/style is sufficient until a real second use case exists.
**Tests:** TDD-appropriate (§23) — RED/GREEN as described above.
**Acceptance criteria:** Component renders with correct role and accessible text; reduced-motion handling present; test passes.
**Verification:** `npm run test -- LoadingSpinner`.
**Skills/tools:** `bekaa3d-brand-ui` (token-driven styling), Superpowers `test-driven-development`.

---

### FVS001-T05a — `AppLayout` Landmarks & `SkipLink`

**Purpose:** The structural/accessibility core of the app shell — split out from the original single "AppLayout shell" task during independent review, since a reviewer could legitimately accept the skip-link/landmark behavior here while rejecting the header/footer content of the old combined task, and vice versa.
**Depends on:** `FVS001-T02` (test runner), `FVS001-T03` (tokens).
**Files expected to be created/modified:** `src/components/layout/AppLayout.tsx`, `src/components/layout/SkipLink.tsx`, plus a `.test.tsx` file per component.
**Implementation actions:**
1. Write failing tests first: `SkipLink` is the first focusable element in the DOM and moves focus to `#main-content` on activation/click; `AppLayout` renders exactly one `<header>` slot, one `<main id="main-content">`, one `<footer>` slot (accepting `header`/`footer` content as children/props so `FVS001-T05b` can fill them in independently).
2. Implement each component minimally to pass.
3. Verify keyboard tab order: skip link → (header content, once T05b exists) → main → footer.
**Do NOT:** implement any header/footer visual content (that's `FVS001-T05b`); add any navigation link (no auth-aware links exist yet).
**Tests:** TDD-appropriate (§23).
**Acceptance criteria:** Landmark test passes; skip-link focus-move test passes.
**Verification:** `npm run test -- AppLayout SkipLink`.
**Skills/tools:** `bekaa3d-brand-ui`, Superpowers `test-driven-development`.

---

### FVS001-T05b — Header & Footer Skeleton

**Purpose:** The visual/content half of the app shell, independently reviewable from the landmark/skip-link structure it renders inside.
**Depends on:** `FVS001-T02`, `FVS001-T03`, `FVS001-T05a`.
**Files expected to be created/modified:** `src/components/layout/Header.tsx`, `src/components/layout/Footer.tsx`, plus a `.test.tsx` file per component.
**Implementation actions:**
1. Write failing tests first: `Header`/`Footer` render their skeleton content (brand mark reference — not the logo file itself, see Do NOT below — and placeholder text) without any nav items; content is responsive at the breakpoints in §20 (this task implements the responsive CSS, not just defers it to `FVS001-T15`'s later verification pass — an earlier draft of this plan scheduled only *verification* of responsive behavior without ever scheduling its *implementation*, corrected here).
2. Implement each component minimally to pass, styled from `FVS001-T03`'s tokens.
3. Mount `Header`/`Footer` into `FVS001-T05a`'s `AppLayout` slots.
**Do NOT:** add any navigation link; implement a mobile-nav hamburger toggle or reserve an unused placeholder `<button>` for one — **removed during independent review**: an earlier draft reserved an inert, non-functional toggle button "for later," which is exactly the kind of speculative scaffolding §9's "extension points, not speculative features" principle argues against elsewhere in this same document. Zero nav items exist in FVS-001; the CSS space for a future toggle can be added by whichever slice adds the first real nav item, cheaply, without needing anything reserved here. Do not embed the actual brand logo image file as a component asset either — that's a content decision for whichever slice defines final header branding (this task uses text/token-based brand treatment only, consistent with "no placeholder business architecture").
**Tests:** TDD-appropriate (§23).
**Acceptance criteria:** Header/Footer render correctly and responsively at 320px–1920px (implemented here, formally re-verified in `FVS001-T17`).
**Verification:** `npm run test -- Header Footer`.
**Skills/tools:** `bekaa3d-brand-ui`, Superpowers `test-driven-development`.

---

### FVS001-T06 — Routing: Root Route `/` + Catch-All Not-Found

**Purpose:** Deliver outcomes 3–5 and 11 (routing foundation, root route, 404 handling, `NotFoundPage`).
**Depends on:** `FVS001-T05a`, `FVS001-T05b`. (Parallel-safe with `FVS001-T07`.)
**Files expected to be created/modified:** `src/app/page.tsx`, `src/app/not-found.tsx`, `src/components/pages/NotFoundPage.tsx` (or colocated directly in `not-found.tsx` if no reuse need exists — implementer's call, no reuse case exists yet so colocation is acceptable).
**Implementation actions:**
1. Write a component test for the root page's content rendering inside `AppLayout`.
2. Write a component test for `NotFoundPage` content (heading, explanatory text, link back to `/`).
3. Implement `src/app/page.tsx` using `AppLayout` and placeholder foundation-slice content (§18).
4. Implement `src/app/not-found.tsx` using the same shell.
**Do NOT:** implement the real F-001 Home page content (FVS-022's job); implement any product/catalogue link.
**Tests:** Component-level TDD for content; the URL-to-page *routing* behavior itself is configuration, verified by the dev server + `FVS001-T18`'s E2E smoke test, not a unit test (§23).
**Acceptance criteria:** `/` renders expected content in a browser; an arbitrary unknown path (e.g., `/does-not-exist`) renders `NotFoundPage` content with a real HTTP 404 status (verified via browser devtools network tab or `curl -I`).
**Verification:** `npm run test -- page NotFoundPage`; manual `curl -I http://localhost:3000/does-not-exist` showing `404`.
**Skills/tools:** `bekaa3d-brand-ui` (content styling), Superpowers `test-driven-development`.

---

### FVS001-T07 — Render-Error Boundary (`error.tsx` / `global-error.tsx`)

**Purpose:** Deliver outcome 10 and error category A (§17) — a real, working boundary for unexpected render/runtime failures, using Next.js's native App Router convention (confirmed current via this session's documentation check: `error.tsx` must be a Client Component, receives `error`/`reset` props, catches render errors in its segment and below but not its own layout or event-handler errors; `global-error.tsx` replaces the entire root layout and is active in production only, since dev uses Next's own overlay).
**Depends on:** `FVS001-T05a`, `FVS001-T05b`. (Parallel-safe with `FVS001-T06`.)
**Files expected to be created/modified:** `src/app/error.tsx`, `src/app/global-error.tsx`, a component test exercising the fallback (via a test-only component that throws).
**Implementation actions:**
1. Write a failing test: render a subtree containing a component that throws, assert the fallback UI (heading, "try again" via `reset()`, styled inside the brand shell) renders instead of the app crashing.
2. Implement `error.tsx` (`'use client'`) with the fallback UI and a working `reset()` button.
3. Implement `global-error.tsx` as a minimal root-level safety net (must include its own `<html>`/`<body>` per Next.js's requirement for this file) — kept intentionally sparse since it's a last-resort path.
4. Document (inline comment + `FVS001-T17`) that `error.tsx` does **not** catch `ApiError`/network failures — those are handled per §17 category B/C, not here.
**Do NOT:** funnel `ApiError` handling through this boundary; make this boundary aware of TanStack Query at all.
**Tests:** TDD-appropriate.
**Acceptance criteria:** A deliberately-thrown error in a descendant component renders the fallback, not a blank page or an unhandled crash; `reset()` re-attempts rendering.
**Verification:** `npm run test -- error`.
**Skills/tools:** `bekaa3d-brand-ui` (fallback styling), Superpowers `test-driven-development`. Context7/current Next.js docs already consulted during planning (§ "Source of Truth"); re-confirm at implementation time only if the installed Next.js version differs materially from what was checked.

---

### FVS001-T08 — `ApiError` Type & RFC 9457 Problem Parser

**Purpose:** The pure-logic core of the API layer — deliver outcome 18 (RFC 9457 handling) and the foundation of outcome 19 (network-failure normalization), fully unit-testable without any UI or network dependency.
**Depends on:** `FVS001-T02`. (Parallel-safe with the entire `T03`–`T07` UI branch and with `FVS001-T10`/`T11`.)
**Files expected to be created/modified:** `src/lib/api/ApiError.ts`, `src/lib/api/problem.ts`, `src/lib/api/problem.test.ts`.
**Implementation actions:**
1. Write failing tests first, covering exactly the matrix in §23: valid RFC 9457 body → correct typed fields; body missing some confirmed fields → the present ones populated, absent ones `undefined`; non-problem JSON body → captured in `raw`, RFC fields `undefined`; non-JSON/malformed body → `kind: "parse"`, raw text captured, no thrown exception.
2. Implement `ApiError` per the shape in §13.
3. Implement `problem.ts`'s parsing function using manual type guards only (§9, §14 — no Zod).
4. Add the `correlationId?: string` field to `ApiError` with an inline `// NEEDS BACKEND CONFIRMATION: correlation/request-ID header name — see docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md §17` comment at its declaration, per `bekaa3d-api-contract`'s inline-marking rule — left `undefined` everywhere it's constructed in this task.
**Do NOT:** add a schema-validation dependency; invent or guess the `errors[]` extension shape; invent a correlation-ID header name.
**Tests:** Strongly TDD-appropriate — this is the highest-value RED/GREEN candidate in the whole slice.
**Acceptance criteria:** All matrix cases in §23 pass; `ApiError`'s type is exported and usable by `FVS001-T09`.
**Verification:** `npm run test -- problem`.
**Skills/tools:** `bekaa3d-api-contract` (mandatory — this task is the literal implementation of that skill's RFC 9457/no-invention rules), Superpowers `test-driven-development`.

---

### FVS001-T09 — Centralized `apiClient`

**Purpose:** Deliver outcome 15/16/19/20 — the one fetch wrapper every later slice will import, built exactly to the design in §13.
**Depends on:** `FVS001-T08`. (No longer depends on `FVS001-T10` — the proxy redesign, §12/§13, means `apiClient` doesn't consume any environment variable directly; `FVS001-T10`/`next.config.ts`'s rewrite is a separate, parallel concern that `apiClient` doesn't need to know about.)
**Files expected to be created/modified:** `src/lib/api/apiClient.ts`, `src/lib/api/apiClient.test.ts`.
**Implementation actions:**
1. Write failing tests first, covering the full matrix in §23 (success, RFC 9457 error, malformed error, empty/unparseable 2xx body treated as success, non-JSON error body, network failure, timeout/abort), using `vi.stubGlobal("fetch", ...)` to control every case deterministically — no real network call in any unit test.
2. Implement `apiClient` per §13's eleven numbered responsibilities, consuming `FVS001-T08`'s `ApiError`/`problem.ts`. Calls only relative `/api/...` paths (§13 point 1) — this task does **not** read any base-URL environment variable, since none exists in the corrected design (§12).
3. Implement the safe-message fallback table (status-code-keyed, small — 4xx generic, 5xx generic, network, timeout).
4. Confirm `credentials` is never set to `'include'` anywhere in this file (§13 point 3, §22).
**Do NOT:** attach any auth/CSRF header; retry automatically; assume any endpoint beyond `/health/live`/`/health/ready` (which this task doesn't even call directly — that's `FVS001-T13a`'s job; this task only builds the general-purpose client); read or construct an absolute backend URL anywhere in this file.
**Tests:** Strongly TDD-appropriate.
**Acceptance criteria:** All matrix cases pass; calling the client against a mocked 2xx returns parsed JSON directly (no `ApiError` wrapper); calling it against every failure case returns/throws a correctly-shaped `ApiError`.
**Verification:** `npm run test -- apiClient`.
**Skills/tools:** `bekaa3d-api-contract` (mandatory), Security Guidance (review this file specifically for credentials/header handling once written — the single most security-relevant file in this slice), Superpowers `test-driven-development`.

---

### FVS001-T10 — Environment Configuration & Dev Proxy

**Purpose:** Establish `API_PROXY_TARGET` and the same-origin dev-proxy rewrite (§9/§12) that closes the CORS gap identified during independent review — this task's scope expanded from plain env-var setup to include the `next.config.ts` rewrite, since the two are one design decision.
**Depends on:** `FVS001-T02`. (Parallel-safe with `FVS001-T08`, `FVS001-T09` — `apiClient` no longer consumes this task's output directly, per T09's corrected dependency line.)
**Files expected to be created/modified:** `.env.local.example`, `.gitignore` (confirm `.env*.local` is excluded — likely already present from `FVS001-T01`, verify rather than assume), `next.config.ts` (`rewrites()` function), a short section in `FVS001-T17`'s documentation.
**Implementation actions:**
1. Create `.env.local.example` containing `API_PROXY_TARGET=http://localhost:8000` (an example/placeholder value, not a real secret — there is no secret in this variable at all).
2. Confirm `.env.local` itself (the developer's real, git-ignored copy) is excluded by `.gitignore`.
3. Add an `async rewrites()` function to `next.config.ts` forwarding `/api/:path*` to `${process.env.API_PROXY_TARGET}/:path*`.
4. Write the one-paragraph rule (§12's "what may be exposed" / "what must never be exposed," now "nothing is exposed at all in FVS-001") into the docs draft that `FVS001-T17` will finalize.
**Do NOT:** create a real `.env.local` file with a committed value beyond the example; introduce any variable not needed by this slice; prefix `API_PROXY_TARGET` with `NEXT_PUBLIC_` (it must stay server-only, per §12); write more than the single `/api/:path*` passthrough rewrite rule — no request/response transformation, no header injection, no auth logic, no additional routes (§9's explicit BFF/gateway guardrail). This is a one-line proxy rule, not the start of a gateway layer.
**Tests:** Not TDD — configuration. Verified by inspection and by `FVS001-T13a`/`T16` actually succeeding in reaching the backend through the proxy.
**Acceptance criteria:** `.env.local.example` exists and is committed; `.env.local` is git-ignored; a request to `/api/health/ready` from the running dev server reaches the real backend and returns its actual response (manually verified once a local backend is available); the rule is documented.
**Verification:** `git check-ignore -v .env.local` confirms it's ignored; `git status` never shows a real `.env.local`; manual `curl http://localhost:3000/api/health/ready` (with a local backend running) returns the backend's real response, not a 404 from Next.js itself.
**Skills/tools:** Security Guidance (confirm `API_PROXY_TARGET` is never accidentally exposed client-side — this is now the single most important thing this task gets right).

---

### FVS001-T11 — TanStack Query Client & Provider

**Purpose:** Deliver outcome 14, per the design in §15.
**Depends on:** `FVS001-T02`. (Parallel-safe with the entire `T03`–`T10` set — this task doesn't need `AppLayout` to exist, only to be mountable later in `FVS001-T14`.)
**Files expected to be created/modified:** `src/lib/query/queryClient.ts`, `src/lib/query/QueryProvider.tsx`, a smoke test for the provider.
**Implementation actions:**
1. Instantiate a singleton `QueryClient` with **no global `defaultOptions` beyond what's justified** (§15) — document the decision to leave defaults alone inline as a comment, so a future contributor doesn't "helpfully" add speculative global retry/staleTime settings for business queries that don't exist yet.
2. Implement `QueryProvider` (`'use client'`) wrapping `QueryClientProvider`.
3. Write a minimal smoke test: `QueryProvider` renders its children.
**Do NOT:** add React Query Devtools as a required dependency (optional, implementer's call, not in §26's required table); set global `staleTime`/`retry` defaults intended for future commerce/auth queries.
**Tests:** Mostly configuration validation with one thin smoke test — not a full TDD cycle (§23).
**Acceptance criteria:** `QueryProvider` renders children without error; `queryClient` singleton is importable by `FVS001-T13a`.
**Verification:** `npm run test -- QueryProvider`.
**Skills/tools:** Context7 (recommended, to confirm the installed TanStack Query major version's exact API — this session's WebSearch-based check already confirmed v5's `gcTime` naming and defaults; re-verify only if the installed version differs).

---

### FVS001-T12 — Toast Primitive

**Purpose:** Deliver outcome 13, per the design in §17's closing paragraph — the minimum reusable primitive, not a notification framework.
**Depends on:** `FVS001-T02`, `FVS001-T03`. (Parallel-safe with `FVS001-T04`–`T07`.)
**Files expected to be created/modified:** `src/components/feedback/Toast.tsx`, `src/components/feedback/ToastProvider.tsx`, `.test.tsx` files for both.
**Implementation actions:**
1. Write failing tests: `ToastProvider`/`useToast()` can show a toast with a message and a variant (success/error/info — reusing `bekaa3d-brand-ui`'s semantic colors); a shown toast is dismissible (manually and/or via a timeout); `Toast` uses `role="status"`/`aria-live="polite"`.
2. Implement the context/provider and the visual component minimally.
3. Respect `prefers-reduced-motion` for enter/exit transitions (§21).
**Do NOT:** add a toast library dependency (§9); wire this to any real event — no mutation exists in this slice to trigger one; build stacking/queueing logic beyond showing more than one toast without crashing (a real queueing/ordering policy is deferred until a slice has enough simultaneous events to need one).
**Tests:** TDD-appropriate.
**Acceptance criteria:** A toast triggered via `useToast()` in a test renders and is dismissible; accessibility roles present.
**Verification:** `npm run test -- Toast`.
**Skills/tools:** `bekaa3d-brand-ui` (semantic color variants), Superpowers `test-driven-development`.

---

### FVS001-T13a — Readiness Query Hook

**Purpose:** Deliver the data half of outcome 16 — the one direct consumer of the confirmed health endpoint, per the state matrix in §16. Split from a combined hook+banner task during independent review, since the pure-logic hook and the UI/ARIA-bearing banner are separately reviewable and the original combined task's own implementation actions never actually included the banner's accessibility semantics (corrected in `FVS001-T13b`).
**Depends on:** `FVS001-T09`, `FVS001-T11`.
**Files expected to be created/modified:** `src/lib/health/useReadiness.ts`, `useReadiness.test.ts`.
**Implementation actions:**
1. Write failing tests first, covering every row of §16's state matrix (ready/not-ready/unreachable/timeout/malformed-body-doesn't-block-status-determination), mocking `apiClient`/`fetch` — not hitting a real backend.
2. Implement `useReadiness` as a TanStack Query hook calling `GET /health/ready` via `apiClient`, with `staleTime: 0`, a bounded `retry` (proposed 2), and a bounded `refetchInterval` (proposed 15s, foreground-only) per §16.
**Do NOT:** call `GET /health/live` (§16 — not used in this slice, documented why); assume any response body field; retry indefinitely; render anything — this task is data-only, `FVS001-T13b` owns rendering.
**Tests:** Strongly TDD-appropriate — this is the second-highest-value RED/GREEN candidate after `FVS001-T08`.
**Acceptance criteria:** Every §16 matrix row has a passing test against the hook's returned state (not yet rendered UI).
**Verification:** `npm run test -- useReadiness`.
**Skills/tools:** `bekaa3d-api-contract` (this hook is the direct, careful consumer of the two confirmed endpoints — no scope creep to other endpoints), Superpowers `test-driven-development`.

---

### FVS001-T13b — Backend-Unreachable Banner

**Purpose:** Deliver outcome 17 and the UI/accessibility half of the readiness feature, consuming `FVS001-T13a`'s hook.
**Depends on:** `FVS001-T13a`, `FVS001-T04`.
**Files expected to be created/modified:** `src/components/feedback/BackendUnreachableBanner.tsx`, `BackendUnreachableBanner.test.tsx`.
**Implementation actions:**
1. Write failing tests first: renders nothing when `useReadiness` reports ready; renders "not ready" copy with `role="status"`/`aria-live="polite"` when the backend is up but not ready; renders "unreachable"/"timed out" copy with `role="alert"`/`aria-live="assertive"` when the backend can't be reached at all (a genuine failure the developer needs to notice immediately) — **this explicit role/aria-live split was missing from the original combined task's implementation actions**, added here during independent review since §21 already promised it but no task step actually implemented it.
2. Implement `BackendUnreachableBanner` using `LoadingSpinner` (`FVS001-T04`) for the initial-load state only (`isLoading`, not `isFetching`).
3. **Dev-only gating, done correctly at the composition boundary, not inside this component:** this component itself does not read `process.env.NODE_ENV` and early-return — because React hooks cannot be conditionally called, an internal early-return after calling `useReadiness()` would still execute the hook's polling in production, contradicting the "dev-only" requirement (§16, §22 — flagged as a real risk during independent review: a naive implementation would poll `/health/ready` from every production visitor's browser every 15 seconds). Instead, `FVS001-T16` (root layout composition) is responsible for conditionally *mounting* `<BackendUnreachableBanner />` at all, only when `process.env.NODE_ENV === "development"` — this task's job is only to render correctly whenever it *is* mounted.
**Do NOT:** gate rendering internally via an early-return after calling the hook (see action 3); show the banner in production (enforced by `FVS001-T16` not mounting it, verified in `FVS001-T18`).
**Tests:** Strongly TDD-appropriate.
**Acceptance criteria:** Every §16 matrix row has a passing test; "not ready" vs "unreachable"/"timeout" are visually and semantically (`role`/`aria-live`) distinct; the component contains no `NODE_ENV` check of its own (verified by code review, since a passing test can't prove an absence).
**Verification:** `npm run test -- BackendUnreachableBanner`; `npm run build && npm run start` then manual confirmation the banner never appears regardless of backend state (this final production check is completed once `FVS001-T16` has actually wired the conditional mount).
**Skills/tools:** `bekaa3d-brand-ui` (banner styling/semantic colors), Superpowers `test-driven-development`.

---

### FVS001-T14 — Root Layout Composition

**Purpose:** Wire every previously-independent piece into `src/app/layout.tsx` — the integration point where the slice becomes one coherent application.
**Depends on:** `FVS001-T05a`, `FVS001-T05b`, `FVS001-T06`, `FVS001-T07`, `FVS001-T09`, `FVS001-T11`, `FVS001-T12`, `FVS001-T13a`, `FVS001-T13b`.
**Files expected to be created/modified:** `src/app/layout.tsx`.
**Implementation actions:**
1. Compose `QueryProvider` → `ToastProvider` → `AppLayout` (containing `SkipLink`/`Header`/`{children}`/`Footer`) → `BackendUnreachableBanner` in `src/app/layout.tsx`, with the banner wrapped in an explicit `process.env.NODE_ENV === "development"` conditional **at this mount point** — per `FVS001-T13b`'s design, the banner component itself contains no such check, so this is the one and only place in the whole slice that decides whether the readiness poll/banner exist at all in a given build.
2. Confirm `error.tsx`/`global-error.tsx`/`not-found.tsx` (all sibling files in `src/app/`) continue to work correctly with the now-composed root layout (Next.js's own convention handles this automatically, but verify by triggering each path manually).
3. Run the *existing* test suite from every prior task to confirm nothing regressed from composition.
4. Add one integration test rendering the fully composed root layout in isolation (mocked `apiClient`/`fetch`), asserting it renders without throwing and that all three landmarks (`header`/`main`/`footer`) are present — composition-only bugs (e.g., provider-nesting/context mistakes) are not caught by any component's own isolated unit tests, so this task needs at least one test of its own, not just a regression check.
**Do NOT:** add any new component or behavior not already built by a prior task; add auth/cart/business logic "while I'm in here."
**Tests:** One new integration test (composition-level, per action 4 above) plus a full regression check of the existing suite — configuration validation for the wiring itself, TDD for the new composition test (§23).
**Acceptance criteria:** `npm run dev` boots; `/` renders the fully composed shell (header, main content, footer, skip link, no banner if backend is reachable or a banner if not); a deliberately-triggered render error still shows the `error.tsx` fallback; an unknown route still shows 404; the full existing test suite still passes.
**Verification:** `npm run test` (full suite), manual boot + click-through in a browser.
**Skills/tools:** None of the five tools apply uniquely to composition beyond general care; `bekaa3d-frontend-slice-dod` items 5–7 (desktop/tablet/mobile) become checkable for the first time against the *real*, fully composed app starting here.

---

### FVS001-T15 — Accessibility & Responsive Verification Pass

**Purpose:** Formal verification of §20/§21 against the now-composed application — a dedicated task, not an afterthought, per the task brief's explicit staging.
**Depends on:** `FVS001-T14`.
**Files expected to be created/modified:** Possibly small fixes to files from `T03`–`T14` if a defect is found (not new files) — this task is a verification pass, and any fix it produces belongs to whichever component owns the defect.
**Implementation actions:**
1. Manual keyboard-only walkthrough of `/` and the 404 page: tab order, skip-link activation, visible focus at every stop, no keyboard trap.
2. Manual viewport check at 320px, 375px, 768px, 1024px, 1440px, 1920px — no horizontal overflow, no illegible/overlapping content, banner/toast don't obscure the skip link.
3. Contrast re-check of any color pairing introduced since `FVS001-T03`'s initial check (should be none new, but verify).
4. If `@axe-core/playwright` was accepted into the dependency table (§26), add its assertions to the `FVS001-T16` smoke spec now (this task and `T16` are tightly coupled on that specific point — sequence them together if the dependency is accepted).
5. Record findings (pass/fail per checklist item, with fixes applied) as this task's own completion evidence — becomes part of `FVS001-T17`'s documentation.
**Do NOT:** treat this as optional or skippable because "it probably looks fine" — per `bekaa3d-frontend-slice-dod` items 5–7/17–19, each must be independently verified, not assumed.
**Tests:** Primarily manual verification; automated `@axe-core` assertions if accepted (§26) supplement but do not replace the manual pass, since automated tools don't catch everything (e.g., logical tab order, genuine keyboard-trap absence).
**Acceptance criteria:** Every item in §20/§21 has a recorded pass; any defect found is fixed and re-verified before this task is marked complete.
**Verification:** The manual walkthrough itself, recorded; `npm run test:e2e` if axe assertions were added.
**Skills/tools:** `bekaa3d-brand-ui` (the authority for what "correct" looks like here), Superpowers `verification-before-completion`.

---

### FVS001-T16 — E2E Smoke Test Infrastructure & Test

**Purpose:** Deliver outcome 24, per the design in §23's closing E2E paragraph.
**Depends on:** `FVS001-T14`. (Parallel-safe with `FVS001-T15` and `FVS001-T17` — independent verification activities.)
**Files expected to be created/modified:** `playwright.config.ts`, `e2e/smoke.spec.ts`, `e2e/backend-connectivity.spec.ts` (added per the user's post-approval clarification — see action 4).
**Implementation actions:**
1. Configure Playwright against the local dev server (`webServer` config starting `npm run dev` automatically for the test run, or documented manual-start instructions — implementer's choice, document whichever is chosen).
2. Write the smoke spec per §23: app boots and `/` renders shell landmarks; unknown route renders 404 with working back-link; readiness/banner path asserted tolerantly (either valid state accepted, per §27 risk #11 — never a hard dependency on the backend being up). This spec — and only this spec — is what `npm run test:e2e` runs by default, and it must remain deterministic and backend-independent.
3. If `@axe-core/playwright` was accepted (§26), add its scan assertions here per `FVS001-T15`'s note.
4. **Add a second, separately-invoked spec, `e2e/backend-connectivity.spec.ts`, excluded from the default `test:e2e` run** (via a distinct Playwright project/`testMatch` and a separate `npm run test:e2e:backend` script) that makes one real request to `/api/health/ready` (through the dev proxy, §10/§13) against an actually-running local backend and asserts a genuine 2xx response — this is the one place in the entire test suite that is *allowed* to require a real backend, precisely because it exists to prove real connectivity to VS-001, not to run unattended in every environment. **This satisfies the clarification that FVS-001 must genuinely prove backend connectivity before completion, without compromising the deterministic smoke test's backend-independence** — the two specs have different jobs and different scripts, and neither is run by the other's command.
**Do NOT:** assert a specific backend health state as a hard requirement in `smoke.spec.ts`; fold the backend-connectivity check into the default `test:e2e` run (it must stay opt-in/separately-scripted, not silently make CI or a backend-less local run start failing); add any additional E2E scenario belonging to a later slice (no login flow, no product browsing — nothing to test yet).
**Tests:** This *is* the test — written test-first in the sense of defining expected behavior before considering the slice complete, though it's an E2E spec, not a unit RED/GREEN cycle (§23).
**Acceptance criteria:** `npm run test:e2e` passes with the backend running; `npm run test:e2e` **also** passes with the backend not running (both runs performed and observed, not assumed); `npm run test:e2e:backend` passes when run against a real local backend, with its output recorded as evidence (required by `FVS001-T18`, not optional).
**Verification:** `npm run test:e2e` run twice — once with a local backend reachable, once without; `npm run test:e2e:backend` run once with a real local backend and its output captured.
**Skills/tools:** Superpowers `verification-before-completion` (all three run conditions must actually be observed, not assumed).

---

### FVS001-T17 — Developer Documentation

**Purpose:** Deliver outcome 25 — so a developer (or agent) picking up FVS-002 doesn't have to reverse-engineer this slice's decisions.
**Depends on:** `FVS001-T14` (needs the real, composed app to document accurately); can start drafting earlier and finalize last, in parallel with `T15`/`T16`.
**Files expected to be created/modified:** `docs/setup/frontend-setup.md` (or a root `README.md` section — implementer's choice; §10's proposed structure suggests `docs/setup/frontend-setup.md`), inline code comments already added by prior tasks (not duplicated here, referenced).
**Implementation actions:**
1. Document local setup: prerequisites, `npm install`, `.env.local` creation from the example, `npm run dev`.
2. Document the `apiClient`/`ApiError` contract for future slice authors: how to call it, what `ApiError.kind` values mean, the safe-message/raw-diagnostic split (§13, §22), and explicitly the open contract questions from §8 with a pointer to `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 as the living list.
3. Document the four-category error-handling split (§17) so a future contributor doesn't try to route an `ApiError` through `error.tsx` or vice versa.
4. Document the test commands (`lint`, `typecheck`, `test`, `test:e2e`, `build`) and the mocking approach (native fetch stubbing, no MSW, and why).
5. Fold in `FVS001-T15`'s recorded accessibility/responsive verification notes.
**Do NOT:** document features that don't exist yet (no "how to add a product page" speculative guide).
**Tests:** Not applicable — documentation, verified by completeness review against this task's own action list.
**Acceptance criteria:** A developer with no prior context on this session could follow the doc and get the app running locally, understand the `apiClient` contract, and know where the open contract questions live.
**Verification:** Self-review against the action-list above, **required**, plus a fresh read-through by whoever picks up `FVS001-T18` or the next slice — not optional, since a documentation task's author is the worst-positioned person to judge whether it's actually clear to someone with no prior context.
**Skills/tools:** `bekaa3d-api-contract` (the contract documentation must match the skill's own rules, not restate them incorrectly).

---

### FVS001-T18 — Final FVS-001 Slice Verification

**Purpose:** The explicit VERIFY + REVIEW phase for the whole slice — not a new feature task, the closing gate.
**Depends on:** All prior tasks (`FVS001-T01`–`T17`).
**Files expected to be created/modified:** None expected (this task may produce small fix commits if the DoD walk-through surfaces a defect, attributed back to the owning task/file).
**Implementation actions:**
1. Run `superpowers:verification-before-completion`'s discipline: gather real evidence (command output, not recollection) for every claim below.
2. Run `npm run lint`, `npm run typecheck`, `npm run test`, `npm run test:e2e` (both backend-up and backend-down), `npm run build` — record actual output/exit codes.
3. **Run `npm run test:e2e:backend` against a real, locally-running VS-001 backend and record its output** — this is a required gate, not optional, added per the user's post-approval clarification: FVS-001 is not complete until it has genuinely proven connectivity to the real backend through the dev proxy, distinct from the deterministic backend-tolerant suite in step 2.
4. Walk the entire `bekaa3d-frontend-slice-dod` 35-item checklist against the real, composed application (not from memory) — using this plan's own §28 mapping as the starting point, but independently re-verifying each item's evidence, not just copying the mapping's claim.
5. Request an independent review per `superpowers:requesting-code-review` (a fresh reviewer, not self-review) covering the whole slice's diff against this plan.
6. Confirm §5's 25 outcomes are all genuinely present and §6's non-scope list is genuinely empty of any leaked implementation.
**Do NOT:** mark any DoD item complete without evidence gathered in *this* session; skip the independent review step because "it's just a foundation slice"; treat step 2's backend-tolerant E2E pass as a substitute for step 3's real-backend proof — they verify different things.
**Tests:** This task runs tests, it does not write new ones.
**Acceptance criteria:** All commands in steps 2–3 exit successfully with recorded output, **including a real, observed 2xx response from the actual VS-001 backend via `test:e2e:backend`**; all applicable DoD items (§28) verified with evidence; independent review completed with no unresolved Critical/Important findings; §5/§6 scope check passes.
**Verification:** The commands themselves (including the real-backend run), plus the completed DoD walk-through and review as artifacts.
**Skills/tools:** `bekaa3d-frontend-slice-dod` (mandatory — this task *is* that skill), Superpowers `verification-before-completion` and `requesting-code-review` (both mandatory).

## 25. Task Dependency Graph / Execution Order

**Corrected during independent review:** an earlier draft of this section used a hand-drawn ASCII arrow diagram whose edges (spurious `T06`/`T07`/`T12` → `T13` arrows) did not actually match each task's own stated `Depends on` line in §24. Rather than risk the same drift recurring, this section is now derived mechanically: each task's level below is `1 + max(level of its own dependencies)`, computed directly from §24's `Depends on` lines (T05a/T05b/T13a/T13b reflect the review-driven splits). Tasks at the same level have no dependency relationship between them and may run in parallel once every lower level is complete.

| Wave | Tasks | Depends on (from §24, verbatim) |
|---|---|---|
| 0 | `T01` | None |
| 1 | `T02`, `T03` | `T01` |
| 2 | `T04`, `T05a`, `T08`, `T10`, `T11`, `T12` | `T02` and/or `T03` (see each task's own line) |
| 3 | `T05b`, `T09` | `T05b`: `T02`,`T03`,`T05a` — `T09`: `T08`,`T10` |
| 4 | `T06`, `T07`, `T13a` | `T06`/`T07`: `T05a`,`T05b` — `T13a`: `T09`,`T11` |
| 5 | `T13b` | `T13a`, `T04` |
| 6 | `T14` | `T05a`,`T05b`,`T06`,`T07`,`T09`,`T11`,`T12`,`T13a`,`T13b` |
| 7 | `T15`, `T16`, `T17` | `T14` |
| 8 | `T18` | All prior tasks |

No cycle exists — every task's level is strictly greater than every one of its dependencies' levels, which is only possible in an acyclic graph (if a cycle existed, this level computation would not terminate).

**Explicitly parallel-safe waves:** within Wave 2, all six tasks touch disjoint files and may proceed simultaneously. Within Wave 4, `T06`/`T07` are UI-only and `T13a` is data-only — no file overlap. Within Wave 7, `T15`/`T16`/`T17` are independent verification/documentation activities, none of which modifies the others' files.

**Genuinely sequential, with reasons:** `T09` needs `T08`'s `ApiError`/parser types to exist first (it consumes them directly) — it no longer needs `T10` (§13's corrected design removed that dependency, since `apiClient` doesn't read `T10`'s proxy env config directly). `T13b` needs `T13a` (renders its data) and `T04` (uses `LoadingSpinner`) — a genuine join point. `T14` needs every component it composes to exist (`T05a`, `T05b`, `T06`, `T07`, `T09`, `T11`, `T12`, `T13a`, `T13b`) — the integration task cannot start before its parts do. `T18` needs everything — it is the closing gate by definition.

## 26. Dependency Table

| Package | Why FVS-001 needs it | Runtime/Dev | Introduced by | Required now / defer |
|---|---|---|---|---|
| `next` | The application framework itself | Runtime | T01 | **Required now** — pending §29 stack approval |
| `react`, `react-dom` | Required by Next.js | Runtime | T01 | **Required now** |
| `@tanstack/react-query` | Outcome 14 — QueryClient foundation; also the vehicle for the readiness check (T13a) | Runtime | T11 | **Required now** |
| `typescript`, `@types/node`, `@types/react`, `@types/react-dom` | TypeScript support (scaffold + strict config) | Dev | T01/T02 | **Required now** |
| `tailwindcss` (+ its current-version peer/plugin requirements — resolve at implementation time per official current docs, version-sensitive) | Outcome 22 responsive foundation + brand token system (T03) | Dev | T01/T03 | **Required now** |
| `eslint`, `eslint-config-next` (or current framework-recommended lint config) | Lint script (T02) | Dev | T01/T02 | **Required now** |
| `vitest`, `@vitejs/plugin-react` (or the framework-appropriate equivalent), `jsdom` (or `happy-dom`) | Unit/component test runner (outcome 23) | Dev | T02 | **Required now** |
| `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event` | Component testing (T04–T09, T12, T13b) | Dev | T02 (installed/configured here — see T02's corrected scope) | **Required now** |
| `@playwright/test` | E2E smoke test (outcome 24) | Dev | T16 | **Required now**, but not installed until T16 — no earlier task needs it |
| `@axe-core/playwright` | Automated accessibility assertions folded into the smoke test (§21/§23) | Dev | T15/T16 if accepted | **Recommended, not mandatory** — genuinely optional; the manual a11y pass in T15 is the required verification, this would supplement it cheaply. Flagged for the plan reviewer's judgment, not decided unilaterally here. |
| **`react-hook-form`** | *(from the original stack proposal)* | — | — | **Deferred.** No form exists anywhere in FVS-001. First real need: FVS-002 (registration). |
| **`zod`** | *(from the original stack proposal)* | — | — | **Deferred.** The RFC 9457 parser needs only manual type guards for five known fields (§9, §14). First real need: whichever slice has a genuine complex-payload validation requirement, expected FVS-002. |
| **A toast library** (e.g., `sonner`) | *(implied by "Toast infrastructure" if read as "add a library")* | — | — | **Deferred.** An in-house primitive (T12) covers FVS-001's actual need; a library is justified once a slice needs stacking/queueing/promise-based toasts. |
| **`clsx` / `tailwind-merge`** | *(common early Tailwind-project addition)* | — | — | **Deferred.** FVS-001's components have at most 2–3 boolean states, expressible without a utility. Revisit when a component's conditional class logic genuinely earns it. |

No package version is pinned in this table by design (§21 of the task brief) — implementation resolves current compatible versions at `FVS001-T01` time, consulting Context7/current official docs where an API surface is version-sensitive (Tailwind's config mechanism and TanStack Query's option names, both already spot-checked during this planning session).

## 27. Risk Register

| # | Risk | Impact | Likelihood | Mitigation | Blocks implementation? |
|---|---|---|---|---|---|
| 1 | Frontend stack not formally approved anywhere in project documents | High (wrong foundation → rework) | Confirmed present (not hypothetical — verified in §29) | Explicit blocking question; resolved before `T01` | **Yes** — see §29 |
| 2 | Backend unavailable during local dev/E2E (separate team's repo, may not always run locally) | Medium | Medium–High | `BackendUnreachableBanner` is designed for exactly this case; `T16`'s smoke test is explicitly designed to pass with or without the backend running (§23) | No |
| 3 | Unknown RFC 9457 `errors[]` validation extension | Low for FVS-001 itself (no forms yet) | N/A now | `raw` escape hatch in `ApiError` (§13/§14) | No |
| 4 | Unknown correlation/request-ID header name | Low (dev-diagnostic nice-to-have, not core function) | Confirmed missing | Reserved, unwired field (§8) | No |
| 5 | Environment configuration mistakes (e.g., a future secret accidentally prefixed `NEXT_PUBLIC_`) | High if it ever happens | Low now (no secret exists yet) | Rule documented explicitly now (§12/T10) so the habit exists before the risk is real | No |
| 6 | Excessive foundation abstraction (over-engineering `apiClient`/`QueryClient` for hypothetical future needs) | Medium (wasted effort, harder review) | Medium (natural temptation on "the" foundation slice) | Explicit non-scope (§6), per-task "Do NOT" sections, §9's "extension points, not speculative features" principle | No |
| 7 | Dependency bloat | Medium | Low–Medium | §26's explicit deferred-dependency list with reasons | No |
| 8 | Client/server boundary mistakes (missing `'use client'`, accidental server-only import in a client bundle) | Medium | Medium | Next.js build fails loudly on most such mistakes; TypeScript LSP catches import errors; convention documented in T17 | No |
| 9 | Next.js App Router rendering-model mistakes (e.g., Pages Router patterns leaking in) | Medium | Low–Medium | This plan's App Router conventions (`error.tsx`/`not-found.tsx`/`global-error.tsx`) verified against current official documentation during this planning session | No |
| 10 | Flaky health-check behavior (retry storms against a possibly-restarting dev backend) | Low–Medium | Medium | Bounded retry (2) + bounded refetch interval (15s, foreground-only), not aggressive polling (§15/§16) | No |
| 11 | Tests accidentally depending on an always-running backend | Medium (breaks CI/local runs for developers without the backend up) | Medium–High if not deliberately designed against | All unit/component tests mock `fetch` natively (§9/§23); the one E2E test is explicitly designed to tolerate backend absence (§23/T16) | No |
| 12 | Tailwind's setup mechanism is version-sensitive (v3 vs v4 differ substantially) | Low–Medium | Medium | Deferred to implementation time (`T01`/`T03`), to be checked against current official docs then, not guessed now | No |

## 28. DoD Traceability Matrix

Mapped from `.claude/skills/bekaa3d-frontend-slice-dod`'s 35-item checklist to the task that satisfies each and the verification that proves it. Items marked **NOT APPLICABLE** carry a specific reason, not a silent skip (per that skill's own rule).

| # | DoD item | Status | Satisfying task | Verification |
|---|---|---|---|---|
| 1 | Backend VS dependency identified | APPLICABLE | This document, §7 | VS-001 cited with direct quotes |
| 2 | Frontend FVS identified | APPLICABLE | This document, throughout | FVS-001 cited |
| 3 | Real API contract used, never invented | APPLICABLE | T08, T09 | Only `/health/live`/`/health/ready` used; §8 tracks every open question explicitly rather than guessing |
| 4 | Route created matches the plan's routing table | APPLICABLE | T06 | `/` and catch-all 404 match `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-001 Routes line exactly |
| 5 | Desktop UI complete | APPLICABLE | T14, T15 | Manual verification at ≥1024px |
| 6 | Tablet UI checked (768–1023px) | APPLICABLE | T15 | Manual verification |
| 7 | Mobile UI checked (≤767px) | APPLICABLE | T15 | Manual verification, including 320px |
| 8 | Loading state | APPLICABLE | T13b | Readiness-check initial-load spinner, tested |
| 9 | Empty state | **NOT APPLICABLE** | — | No list/collection data exists anywhere in FVS-001 — nothing can be "empty" |
| 10 | Error state | APPLICABLE | T07, T09, T13b | Render-error fallback, `ApiError` handling, unreachable/not-ready banner, all tested |
| 11 | Unauthorized state (401) | **NOT APPLICABLE** | — | No authenticated endpoint exists in FVS-001; auth doesn't exist until FVS-003 |
| 12 | Forbidden state (403/hidden-404) | **NOT APPLICABLE** | — | No authorization boundary exists yet — same reason as #11 |
| 13 | Not-found state | APPLICABLE | T06 | `NotFoundPage`, tested, real HTTP 404 verified |
| 14 | Expired/stale state | **NOT APPLICABLE** | — | No tokens, payment windows, or offer deadlines exist in this slice |
| 15 | Client-side form validation | **NOT APPLICABLE** | — | No form exists anywhere in FVS-001 |
| 16 | Server validation errors displayed correctly | **NOT APPLICABLE** | — | No form/mutation UI exists to display them against; the RFC 9457 *parser* is built (T08) but has nothing to render into yet — that begins in FVS-002 |
| 17 | Accessibility checked against `bekaa3d-brand-ui` | APPLICABLE | T15 | Full checklist walk-through, recorded |
| 18 | Keyboard operation checked | APPLICABLE | T15 | Manual keyboard-only walkthrough |
| 19 | Focus state checked | APPLICABLE | T03 (implementation), T15 (verification) | Focus-ring token applied globally, verified visible at every interactive element |
| 20 | Security assumptions checked | APPLICABLE | §22 of this document, T18 | Full review recorded; no invented auth/CSRF mechanism anywhere |
| 21 | Sensitive information not exposed | APPLICABLE | T09, T10, T13b, T14 | No secret in `NEXT_PUBLIC_*`; dev banner excluded from production build (conditional mount at T14, per the review-driven correction), verified via production build check |
| 22 | Unit/component tests added | APPLICABLE | T04–T09, T12, T13a, T13b | Full suite, run and observed |
| 23 | Integration tests where appropriate | APPLICABLE | T09, T13a, T14 | Mocked-fetch tests covering the full contract matrix, plus T14's composition-level integration test |
| 24 | E2E happy path | APPLICABLE | T16 | Smoke test, run twice (backend up/down) |
| 25 | Important failure path tested | APPLICABLE | T08, T09, T13a, T13b | Malformed/network/timeout/unreachable all explicitly tested |
| 26 | No invented API behavior | APPLICABLE | T08, T09, §8 | Only confirmed endpoints/fields used; every gap explicitly marked |
| 27 | No unresolved contract assumption silently implemented | APPLICABLE | §8, inline code comments (T08) | Every open question logged in this document and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17, not guessed |
| 28 | Tests passing | APPLICABLE | T18 | `npm run test`, `npm run test:e2e` (both backend states), `npm run test:e2e:backend` (real backend), output recorded |
| 29 | Build passing | APPLICABLE | T18 | `npm run build`, exit code recorded |
| 30 | Lint/type checks passing | APPLICABLE | T02 (setup), T18 (final check) | `npm run lint`, `npm run typecheck` |
| 31 | `verification-before-completion` performed | APPLICABLE | T18 | Evidence-gathering discipline applied, not assumed |
| 32 | Code review performed | APPLICABLE | T18 (whole-slice review); each task's own implementation should also get per-task review per `superpowers:requesting-code-review` during actual execution | Independent reviewer's findings recorded |
| 33 | Documentation updated | APPLICABLE | T17 | `docs/setup/frontend-setup.md` complete per its action list |
| 34 | Slice independently mergeable | APPLICABLE | By design (§6 non-scope) | No dependency on any unfinished future-slice code |
| 35 | Main branch remains deployable after merge | APPLICABLE | T18 | Build passes on the final composed state before merge |

## 29. Blocking Questions

### A. MUST ANSWER BEFORE FVS-001 IMPLEMENTATION — **NONE REMAIN**

~~1. Formal frontend stack approval.~~ **RESOLVED.** The project owner formally approved Next.js (App Router) + React + TypeScript + Tailwind CSS + TanStack Query v5 + Vitest + React Testing Library + Playwright + npm for FVS-001 and beyond. Two conditions attached, both already consistent with this plan and reconfirmed rather than newly imposed: (a) React Hook Form and Zod are approved as *future* technologies only — they remain deferred per §9/§26's YAGNI reasoning and must not be installed in FVS-001 without an actual FVS-001 requirement, which does not currently exist; (b) local development only — local Git is used for version control, no GitHub authentication, no remote repository, no push, no pull requests. This matches the plan's existing "operating mode" constraints (this document never planned any GitHub interaction) and required no change to any task.

This was the only genuine blocker in this plan. **The planning status is now READY — `FVS001-T01` may begin.**

### B. CAN SAFELY REMAIN OPEN UNTIL A LATER FVS

2. Exact `LivenessRead`/`ReadinessRead` response body shape — not needed; design keys off HTTP status only (§8, §16).
3. Correlation/request-ID header name — reserved field, unwired, no functional loss in FVS-001 (§8).
4. RFC 9457 `errors[]` validation-extension shape — already tracked in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17; the `raw` escape hatch means FVS-001's parser doesn't need to guess it (§14).
5. CORS/credentials contract for authenticated requests — irrelevant to FVS-001's unauthenticated health check; becomes relevant (and should be re-raised) before FVS-003 begins (§8).
6. Exact repository layout (root vs. subdirectory) — a reasoned default is stated (§9) and cheaply reversible; not worth blocking on.
7. Whether `@axe-core/playwright` is accepted — a judgment call for whoever reviews this plan or executes `T15`/`T16`, not a contract question at all.

## 30. Final Acceptance Criteria

FVS-001 is done when **all** of the following are true, each traceable to a task above:

- [ ] A fresh local checkout (`git clone` equivalent) followed by `npm install` and `npm run dev` boots the app with no manual fix-up (T01, T18).
- [ ] `/` renders the Bekaa3D-branded shell: header skeleton, main content, footer skeleton, skip link (T05a, T05b, T06, T14).
- [ ] An unknown route renders the expected `NotFoundPage` content with a genuine HTTP 404 status (T06).
- [ ] The base layout is verified responsive from 320px through large desktop (T05b implementation, T15 verification, §20/§21 design) — with no unused/inert mobile-nav placeholder element, per the review-driven removal in §9/T05b.
- [ ] The accessibility foundation (skip link, landmarks, focus ring, keyboard operability, reduced-motion handling) exists and is verified, not assumed (T15).
- [ ] `QueryClient` is correctly configured with no speculative global defaults (T11).
- [ ] The centralized `apiClient` exists, is fully unit-tested against the matrix in §23, and is the only place `fetch` is called for backend communication (T08, T09).
- [ ] `GET /health/ready` connectivity can be checked, and the result drives a dev-only banner distinguishing ready / not-ready / unreachable / timeout (T13a, T13b).
- [ ] Backend failure is handled visibly during development and is **provably absent** from a production build (T13b, T14, T18).
- [ ] RFC 9457 base errors (`type`/`title`/`status`/`detail`/`instance`) become typed `ApiError` objects; unknown/malformed bodies never crash the parser (T08).
- [ ] Malformed and network failures are normalized into the same `ApiError` shape via a distinct `kind` discriminator (T08, T09).
- [ ] No auth, cart, product, or any other later-slice business logic exists anywhere in the diff (T18, §6 scope check).
- [ ] All tests pass: `npm run test`, `npm run test:e2e` (both backend-up and backend-down), and `npm run test:e2e:backend` (a real, observed connection to the actual VS-001 backend — required, not optional, per the user's post-approval clarification) (T18).
- [ ] `npm run lint` and `npm run typecheck` pass (T18).
- [ ] `npm run build` passes (T18).
- [ ] `docs/setup/frontend-setup.md` explains local startup, the `apiClient` contract, and points to the open contract questions (T17).
- [ ] No contract assumption was silently invented anywhere — every gap is logged in this document's §8/§29 and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17 (T18, ongoing per-task discipline).

## 31. Implementation Readiness Checklist

- [x] FVS-001's full spec (`docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §5 entry) read and quoted directly (§7).
- [x] VS-001 read and quoted directly, no field invented beyond what it states (§7).
- [x] Current repository state verified firsthand this session, not assumed from memory (§4).
- [x] All three relevant project skills re-read in full before designing the API client / task breakdown (`bekaa3d-brand-ui`, `bekaa3d-api-contract`, `bekaa3d-frontend-slice-dod`); `bekaa3d-commerce-ux` correctly excluded as not applicable.
- [x] Current official documentation checked for the two most version-sensitive APIs (TanStack Query v5, Next.js App Router error/not-found conventions) — via WebSearch, since Context7's MCP tools were not exposed in this session (installed and connected per the prior environment-setup task, but newly-attached MCP servers typically need a session restart to surface their tools — noted, not silently worked around).
- [x] Security Guidance's concern areas reviewed against the planned foundation (§22) — no finding blocks or changes a task.
- [x] Task decomposition complete: 20 tasks (18 in the initial draft, `T05`/`T13` each split into two during independent review), each independently implementable/testable/reviewable, dependency graph verified acyclic via explicit level computation (§24, §25).
- [x] **Stack approval obtained** — formally approved by the project owner (§29A): Next.js App Router, React, TypeScript, Tailwind CSS, TanStack Query v5, Vitest, React Testing Library, Playwright, npm; React Hook Form/Zod confirmed approved-for-future-use only, not for FVS-001; local-Git-only development confirmed. **The one true blocker is resolved — planning status is READY.**
- [x] Independent plan review completed by a fresh, non-authoring reviewer against 18 named failure categories; 2 Critical, 7 Important, and 7 Minor findings were surfaced and every one applied to this document (test-runner setup that no task actually performed, CORS wrongly dismissed as non-blocking, oversized tasks split, a speculative UI placeholder removed, a dev-only gate redesigned to avoid running in production, several broken cross-references and undisclosed deviations from the source plan corrected). No finding was dismissed without a documented reason.
- [x] Post-approval clarifications applied: a separate, explicitly backend-dependent E2E spec (`test:e2e:backend`) added and required at `FVS001-T18` to prove real VS-001 connectivity, without compromising the default deterministic suite's backend-independence; the same-origin dev proxy explicitly scoped to a single passthrough rule with a standing guardrail against growing into a BFF/gateway (§9, `FVS001-T10`).

## 32. Recommended First Implementation Task

**`FVS001-T01` — Repository & Next.js Bootstrap.** The stack-approval blocker is resolved (§29A) — this task may begin now. It has no dependencies, is the only task that unblocks all others, and is low-risk (pure scaffolding, no business logic, verified by observation rather than a test suite that doesn't exist yet).
