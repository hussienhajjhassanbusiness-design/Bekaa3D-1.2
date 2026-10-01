# FVS-003 — Login, Logout & Session Management — Implementation Plan

> **For agentic workers:** One task at a time, RED/GREEN where marked, full verification before every commit, one local commit per task, STOP and report after each batch — never auto-continue. Mirrors the exact workflow FVS-001/FVS-002 used successfully.

**Goal:** A verified customer can log in, stay logged in across page loads via backend-managed httpOnly cookies, be silently refreshed, be forced back to `/login` when refresh fails, log out, be logged out consistently across tabs, and have a safe `returnTo` preserved through the redirect — with no new auth-token persistence in the browser and no speculative authorization/role system.

**Architecture:** Reuse every FVS-001/FVS-002 foundation as-is (`apiClient`, `ApiError`, `QueryProvider`, `AppLayout`, `Toast`, `LoadingSpinner`, `Form`/`TextField`/`PasswordField`/`Button`/`Alert`, global error boundaries, Playwright infrastructure). Add exactly what this slice needs: a login mutation/page, a `returnTo` validator, an `AuthProvider` + auth-session TanStack Query, a `ProtectedRoute` wrapper, a single-flight refresh coordinator, a logout mutation, and a cross-tab logout broadcast. No new runtime dependency is currently justified (see §19).

**Tech Stack:** Next.js App Router, TanStack Query v5 (existing), React Hook Form + Zod (existing, FVS-002). Native `BroadcastChannel` for cross-tab logout (browser API, no package).

**Spec:** `FRONTEND-VERTICAL-SLICE-PLAN.md` §5 "FVS-003 — Login, Logout & Session Management" and `vertical-slice-plan.md` §"VS-003" are the governing specs. **This plan documents and resolves a real conflict between those two documents and the backend's actual VS-003/VS-006 scope — see §0 and §4.** Where this plan and either source document disagree, this plan's own Contract Confidence Table (§5 below, mirroring FVS-002's own §1) governs; executors read this plan first.

> **CORRECTED after initial review:** T02 (login mutation) and T09 (logout) were originally marked "CAN IMPLEMENT NOW" despite this same plan's own Contract Confidence Table listing their real request/response semantics as unconfirmed — an internal inconsistency, now fixed. Both are reclassified **BLOCKED ON BACKEND CONTRACT**. T04 (AuthProvider) is reclassified fully **BLOCKED ON ARCHITECTURE DECISION** (its "interface half" is no longer treated as buildable in isolation, to avoid shipping a `user` field that implies metadata not yet known to exist). T06 (refresh coordinator) and T10 (cross-tab logout) are redesigned as fully generic, contract-independent primitives — decoupled from the real refresh/logout HTTP calls they'll eventually wire into — and remain **CAN IMPLEMENT NOW**. T07 (401 wrapper) is newly reclassified **BLOCKED ON BACKEND CONTRACT**, since its entire purpose is encoding exactly the replay-safety/refreshability decisions that must not be guessed. See the "Task Status Classification (corrected)" section below for the full table and reasoning, and the implementation session's own "FVS-003 SAFE BATCH 1" report for what was actually built under this correction.

---

## 0. Repository / FVS-001 / FVS-002 Foundation State (read before starting any task)

Verified directly against the repository, not assumed:

- FVS-002 is implemented through its Batch 4 (T01–T13 complete; T14 real-backend acceptance still **PENDING** — no real backend has been reachable in this environment at any point in this engagement). FVS-001's own real-backend verification is likewise still **PENDING**. Planning FVS-003 is not blocked by either PENDING item, but no FVS-003 task may claim FVS-001/FVS-002's real-backend acceptance is complete.
- `src/lib/api/apiClient.ts` exposes `get()`/`post()` only, both built on a shared `request()` helper. Confirmed by direct read: **no `credentials` option is set anywhere** — every `fetch()` call relies on the platform default, which is `"same-origin"` (not `"omit"`, not `"include"`). See §7 for why this is already sufficient and should not be changed to `"include"`.
- `src/lib/api/ApiError.ts` has `kind: "http" | "network" | "timeout" | "parse"`, `status` (only for `kind: "http"`), `retryAfterSeconds` (added FVS-002 Batch 3, parsed `Retry-After` header), `correlationId` (reserved, never populated — header name still unconfirmed), and `raw`/`message`. No auth-specific field exists yet.
- `src/lib/query/queryClient.ts`/`QueryProvider.tsx` set **no global `defaultOptions`** — each slice's own hooks configure their own `retry`/`staleTime`. FVS-003 follows the same "no speculative global defaults" rule (§23).
- `src/components/layout/Header.tsx` has **no nav items at all** — confirmed by direct read ("No nav items exist in FVS-001... nothing interactive here yet"). FVS-003 does **not** add a nav-based logout button to `Header` — see §19's non-scope note and Task T09.
- `package.json` has **no** cookie library, auth library, Redux/Zustand, or Axios. React Hook Form/Zod/`@hookform/resolvers` exist from FVS-002 and are reused for the login form; no new runtime dependency is currently justified (§19).
- FVS-002's `Form`/`TextField`/`PasswordField`/`Button`/`Alert` primitives (`src/components/forms/`, `src/components/feedback/Alert.tsx`) already support `ref`-forwarding (added FVS-002 Batch 4 for focus management) and are reused unchanged for the login form.
- `bekaa3d-commerce-ux` does **not** apply to this slice (same reasoning as FVS-002: no cart/checkout/STL/offers/order-state UX here). Not included in the skill map.

---

## 1. The /me / FVS-006 Conflict (read before anything else — this blocks real auth-bootstrap correctness)

**Confirmed by direct repository evidence, not guessed:**

- `vertical-slice-plan.md` VS-003's own "Endpoint / entrypoint" line lists **only** `POST /api/v1/auth/login`, `/logout`, `/refresh`. VS-003 does **not** expose any current-user/current-session read endpoint.
- `GET /api/v1/me` is `vertical-slice-plan.md` VS-006's endpoint ("Current customer profile," **depends on VS-003**, not the other way around).
- `FRONTEND-VERTICAL-SLICE-PLAN.md` §5's FVS-003 entry currently states: *"auth state is derived from calling `GET /api/v1/me` (FVS-006) on boot."* Its FVS-006 entry currently states: *"`GET /me` result is the canonical 'who am I' query, cached and shared by `AuthProvider` (FVS-003)."*
- **This is a genuine, confirmed circular planning defect**, not a misreading: FVS-003 (`depends on (frontend): FVS-001, FVS-002` — not FVS-006) is specified to need an endpoint that belongs to FVS-006, which itself depends on FVS-003 already existing and working. Backend-side, VS-006 depends on VS-003, so the backend endpoint for "who am I" literally cannot exist before VS-003 ships — yet VS-003's own frontend counterpart is specified to need it on boot.

**This plan does NOT resolve this itself.** Per instruction, it is marked:

> **AUTH BOOTSTRAP ENDPOINT — NEEDS BACKEND / ARCHITECTURE CONFIRMATION**

Four options, presented without a silent choice (Task T04 below is sequenced to start only once one of these is approved):

| Option | Description | What it would require |
|---|---|---|
| **A** | VS-003 actually exposes some current-session/current-user endpoint not yet named in `vertical-slice-plan.md`'s prose line (e.g., login/refresh responses could carry a minimal session/user body). | Backend confirmation: does `POST /login` or `POST /refresh`'s success body carry any user/session field? (Already a contract-table row, §5 below — currently unconfirmed either way.) |
| **B** | `GET /api/v1/me` is explicitly pulled forward into FVS-003's own scope as an approved cross-slice dependency (FVS-003 would then depend on VS-006 too, and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s dependency graph needs correcting). | Product/architecture sign-off to officially widen FVS-003's backend dependency from VS-003-only to VS-003+VS-006, plus the same for the backend side if VS-006 must ship before/with VS-003. |
| **C** | FVS-003 determines **boolean** session state without `/me`, by using `POST /api/v1/auth/refresh` itself as a boot-time probe: a 2xx response means a valid session exists (and rotates it); a 401/403 means anonymous. No rich `user` object (email, etc.) would be available until `/me` lands later. | No new backend dependency — uses only VS-003's own confirmed endpoints. Requires confirming `refresh` is safe/intended to be called speculatively on every page load (not just reactively after a 401) and does not itself count toward a rate limit in a way that breaks normal use. **Recommended as the architecturally cleanest option that needs no cross-slice pull-forward**, but this is a recommendation for approval, not a decision made here. |
| **D** | True authenticated bootstrap remains genuinely blocked until FVS-006 ships; FVS-003 only implements login/logout/refresh-on-401/cross-tab-logout, with no page-load "am I already logged in" capability (every page load would require a fresh login unless the user is mid-session with a request already in flight). | Accepting a materially degraded capability ("stays logged in across page loads" — one of this slice's own stated core-capability bullets, §… above — would not actually work) until FVS-006 ships. |

**Until one of these is approved, Task T04 (AuthProvider + bootstrap query) is split into an unblocked interface-design half and a blocked bootstrap-mechanism half — see T04's own task definition.**

---

## 2. Contract Confidence Table

| # | Contract item | Status | Evidence / source | Frontend consequence |
|---|---|---|---|---|
| 1 | Endpoint paths (`login`, `logout`, `refresh`) | **CONFIRMED** | `vertical-slice-plan.md` VS-003 line 92; `FRONTEND-VERTICAL-SLICE-PLAN.md` §5 | Mutations can be built against exact paths now |
| 2 | Login request field names | **ASSUMED** | `vertical-slice-plan.md` names only the type `LoginRequest`, no fields — same gap shape FVS-002's registration row 2 had before its own BATCH 2 confirmation | Assumed `{ email, password }`, mirroring registration's confirmed shape (§5 row — FVS-002). Flagged, not silently treated as confirmed; T02 must not be described as using a backend-confirmed body until this is explicitly confirmed |
| 3 | Login password rules | **ASSUMED — none beyond "required"** | Not stated; no login-specific complexity/length rule anywhere | The login form does **not** invent a different password rule than registration's; it does not re-validate length/complexity at all beyond non-empty, since a wrong rule here would reject a legitimate existing password the backend already accepts |
| 4 | Email format check | **ASSUMED — safe, non-authoritative** | Same `bekaa3d-api-contract` principle already applied in FVS-002 | A generic "looks like an email" check only; never stricter than any real backend rule |
| 5 | Login success HTTP status | **NEEDS BACKEND CONFIRMATION** | Not stated | Treat any 2xx as success; do not assert a specific status code |
| 6 | Login success response body | **NEEDS BACKEND CONFIRMATION** | Not stated whether `SessionRead` (named in VS-003's schema line) is returned to the frontend at all, or only written as a cookie | Directly affects the §1 Option A bootstrap question above — if confirmed to carry user/session data, Option A becomes viable without a new endpoint |
| 7 | Login failure HTTP status | **NEEDS BACKEND CONFIRMATION** | Not stated | Generic `kind:"http"` 4xx handling applies until confirmed; UI copy is enumeration-safe regardless of the exact status |
| 8 | Invalid-credential error signal | **NEEDS BACKEND CONFIRMATION** | VS-003 states credential verification exists; no distinct machine-readable code is named | No specific error-code branching invented; one generic "Invalid email or password." copy for any credential-rejection signal |
| 9 | Locked/rate-limited signal | **NEEDS BACKEND CONFIRMATION** | VS-003 states "progressive failure delay/lockout" exists; no status/code/field named | No lockout countdown or duration is invented; a 429 (if that's how it surfaces) reuses the same `ApiError.retryAfterSeconds` pattern already built in FVS-002 Batch 3, shown as a safe generic "too many attempts" message only if `retryAfterSeconds` is actually present |
| 10 | Cookies set by login | **NEEDS BACKEND CONFIRMATION** | VS-003 states "short-lived access cookie; rotating refresh cookie" exist, httpOnly implied by the whole slice's own design premise | Frontend must never attempt to read either cookie's value (§6) |
| 11 | Cookie names | **NEEDS BACKEND CONFIRMATION** — already logged | `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 "Auth cookie names and CSRF header contract" | Irrelevant to the frontend either way, since cookies are httpOnly and never read by JS — recorded for completeness, not because the frontend needs the name |
| 12 | Cookie `SameSite`/`Secure`/`Path` | **NEEDS BACKEND CONFIRMATION** | Not stated | Pure backend concern; no frontend code depends on these values, but a wrong `SameSite` setting could silently break the proxy-based dev flow — worth a backend-handoff question (§ Backend Questions) so a dev-environment surprise isn't mistaken for a frontend bug later |
| 13 | Are both access + refresh cookies httpOnly | **ASSUMED — yes, both** | The slice's own design premise ("the frontend cannot read the cookie directly," `FRONTEND-VERTICAL-SLICE-PLAN.md` §5) | §6's absolute rule applies to both; if either were JS-readable this plan's entire "never read/store a token" posture would need revisiting — treated as confirmed-enough to build against, but flagged as an assumption, not a literal confirmation |
| 14 | Does the frontend ever receive a token body (vs. cookie-only) | **NEEDS BACKEND CONFIRMATION** | Same gap as row 6 | If a token body is ever returned, it must **never** be written to `localStorage`/`sessionStorage`/React state/any persistence — read §6 again; a returned body may only ever be used to extract safe, non-secret user/session metadata, never the credential material itself |
| 15 | Refresh request body | **NEEDS BACKEND CONFIRMATION** | Not stated | Assume no body is required (the refresh token travels in the cookie); T06/T07 do not invent a body |
| 16 | Refresh cookies used automatically | **ASSUMED — yes** | Standard cookie-based session design; VS-003's own "rotating refresh cookie" line | Relies on the browser's automatic cookie attachment via same-origin `fetch` defaults (§7) — no manual cookie handling |
| 17 | Refresh CSRF requirement | **NEEDS BACKEND CONFIRMATION** | VS-003 states double-submit CSRF exists generally; not stated per-endpoint | T08 (CSRF) remains blocked until this and the general CSRF mechanism (row 20) are both confirmed |
| 18 | Refresh success status/body | **NEEDS BACKEND CONFIRMATION** | Not stated | Treat 2xx as success; body contents (if any) not relied upon unless row 6/14 resolve favorably |
| 19 | Refresh cookie rotation | **ASSUMED — yes** | VS-003's own "rotating refresh cookie" line | No frontend action needed either way — rotation is entirely a Set-Cookie-header backend behavior the browser applies transparently |
| 20 | Refresh failure statuses | **NEEDS BACKEND CONFIRMATION** | Not stated | T06/T07 treat any non-2xx from `/refresh` as "refresh failed → expire session," without branching on the exact status unless a specific one is later confirmed to need different UX |
| 21 | Reuse-detected response | **NEEDS BACKEND CONFIRMATION** | VS-003 states "old-token reuse revokes session" as a backend behavior; the exact HTTP signal back to the frontend is not stated | Per §21 of this plan: treated identically to a normal expired-session UX unless the backend confirms a distinct signal and product explicitly wants different copy |
| 22 | Can refresh itself return 401/403 | **ASSUMED — yes, that's the failure case** | Logical necessity of the whole design — refresh must be able to fail | T06 treats any refresh failure (regardless of exact status) as "could not refresh" — no recursive refresh-of-refresh is ever attempted (§9) |
| 23 | Does refresh response include user/session state | **NEEDS BACKEND CONFIRMATION** | Same gap as row 6/14 | Same consequence as row 6 for the §1 bootstrap-Option-A question |
| 24 | Logout request shape | **NEEDS BACKEND CONFIRMATION** | Not stated whether a body is required | Assume no body; T09 does not invent one |
| 25 | Logout CSRF requirement | **NEEDS BACKEND CONFIRMATION** | Same gap as row 17/20 (CSRF) | Same T08 blocking rule applies |
| 26 | Logout success status/body | **NEEDS BACKEND CONFIRMATION** | Not stated | Treat 2xx as success; no body field relied upon |
| 27 | Logout cookie-clearing semantics | **ASSUMED — backend clears via Set-Cookie on response** | Standard pattern for httpOnly cookie logout; not explicitly stated otherwise | No frontend cookie-clearing code is written (frontend cannot read/clear an httpOnly cookie anyway) |
| 28 | Logout idempotency | **NEEDS BACKEND CONFIRMATION** | Not stated | T09 does not assume calling logout twice is either safe or unsafe; it simply never calls it twice in its own code (no auto-retry, `retry:false`) |
| 29 | CSRF token delivery mechanism | **NEEDS BACKEND CONFIRMATION** — already logged | `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 | T08 fully blocked — see §8 below, nothing is invented |
| 30 | CSRF header name | **NEEDS BACKEND CONFIRMATION** — already logged | Same §17 entry | Same as row 29 |
| 31 | Which methods require CSRF | **NEEDS BACKEND CONFIRMATION** | "Double-submit CSRF" named generally in VS-003; no method/endpoint matrix given | T08 blocked; §8 below lists the exact open questions to resolve before any CSRF code is written |
| 32 | Does login require CSRF | **NEEDS BACKEND CONFIRMATION** | Same gap | Commonly exempted in double-submit designs (no session yet to protect), but not assumed here — explicit backend question |
| 33 | Does refresh require CSRF | **NEEDS BACKEND CONFIRMATION** | Same gap | Explicit backend question — if yes, T06/T07 cannot be fully wired until T08 unblocks |
| 34 | Does logout require CSRF | **NEEDS BACKEND CONFIRMATION** | Same gap | Explicit backend question |
| 35 | 401 refreshability — are auth endpoints themselves excluded | **ARCHITECTURE DECISION — yes, by this plan's own design** | §9 below | `login`/`logout`/`refresh` are called directly through `apiClient`, never through the refresh-aware wrapper (T07) — this is a frontend architecture choice, not a backend contract item, and is treated as settled by this plan |
| 36 | One-refresh-maximum / concurrent 401 behavior | **ARCHITECTURE DECISION — single-flight, this plan's own design** | §10 below | T06 implements exactly one in-flight refresh promise shared by every concurrent 401; not contract-dependent |
| 37 | Request-replay safety for writes after refresh | **NEEDS BACKEND / SECURITY CONFIRMATION** | §11 below — no backend statement proves a 401 always precedes any write side-effect | T07's wrapper auto-retries **GET requests only** after a successful refresh; POST/PATCH/DELETE are never auto-replayed by default (opt-in only, and no current FVS-003 call opts in) until the backend confirms replay safety |
| 38 | Cross-tab logout propagation contract | **ARCHITECTURE DECISION — frontend-owned, `BroadcastChannel`** | §20 below | No backend contribution exists or is expected; purely a frontend same-browser mechanism |
| 39 | Return-to query parameter name | **ARCHITECTURE DECISION — `returnTo`, this plan's own design** | §15 below; matches `FRONTEND-VERTICAL-SLICE-PLAN.md`'s own prose ("`/login?returnTo=...`") | Settled; T01/T05 build against this exact name |
| 40 | Correlation/request-ID header | **NEEDS BACKEND CONFIRMATION** — already logged, inherited from FVS-001/002, unaffected by this slice | `src/lib/api/ApiError.ts` inline comment | Unchanged; never populated |

---

## 3. Security Rule — No Token Access If httpOnly (non-negotiable)

If the backend's access/refresh cookies are httpOnly (assumed, row 13 — and treated as the only safe assumption to build against), **no frontend code may ever attempt to read them.** Specifically forbidden anywhere in this slice's code:

- Reading `document.cookie` for an auth/session/refresh token.
- Writing an access token, refresh token, or raw session identifier to `localStorage`, `sessionStorage`, React state, a module-level variable, IndexedDB, or any other browser-side persistence.
- Any token-persistence "convenience" layer invented because a contract gap made it feel easier than waiting for confirmation.

Authentication state (`AuthProvider`'s `user`/`isAuthenticated`) may hold **safe, non-secret metadata only** (e.g., an email address or a boolean), never credential material. If row 14's "does a token body ever come back" resolves to yes, the token value itself is still never persisted — only non-secret fields from that body may be projected into `user`.

---

## 4. Cookie / Fetch Credentials Contract

Verified directly: `src/lib/api/apiClient.ts`'s `request()` calls `fetch(path, { ...init, signal })` with **no `credentials` option set**. Per the Fetch specification, the default `credentials` mode is `"same-origin"` — cookies are sent automatically for any same-origin request, and the browser's own address bar origin is the only thing that matters (not whether a dev proxy sits in front of the real backend).

**Both in development and production, every `apiClient` call is same-origin to the page that makes it** — the browser always calls a relative `/api/...` path, never the backend's real origin directly (Next.js's `rewrites()` forwards server-side, invisibly to the browser, both for the health-strip rule and the versioned-preserve rule already established in FVS-002 Batch 2/3). This means:

- **No code change to `apiClient` is needed or planned for FVS-003.** `credentials: "include"` must **not** be added — it is unnecessary (the default already covers the only case that exists: same-origin) and would be the wrong signal to a future reader that cross-origin credentialed requests are expected, which they are not.
- **No CORS workaround is needed or planned.** CORS only applies to cross-origin requests; this architecture never makes one.

This is a settled architectural fact from Fetch/cookie spec semantics plus the already-proven same-origin proxy design — not a guess, and not contract-dependent.

---

## 5. CSRF — Blocked Contract Gate (no infrastructure built yet)

Per rows 29–34 of §2, **nothing about the CSRF mechanism is confirmed**: not the cookie name, not the header name, not the delivery mechanism, not which of login/refresh/logout require it. This plan does **not** invent any of:

- A cookie name.
- A header name.
- A DOM `<meta>` tag convention.
- A response-body field.
- A `localStorage`-based token mirror.
- A rotation strategy.

**Task T08 exists only as a placeholder** recording exactly what must be confirmed before any code is written (the bulleted list above, plus: where does `apiClient` attach the header once known; is login exempt; is refresh exempt; does logout require it; how does rotation interact with the single-flight refresh coordinator). T08 is marked **BLOCKED ON CSRF CONTRACT** throughout the task list and is not scheduled into any batch until the backend answers the questions in the Backend Questions section.

---

## 6. apiClient 401 / Refresh Architecture

**Ownership split (per this plan's own architecture decision, §2 row 35):**

| Layer | Owns | Does NOT own |
|---|---|---|
| **Transport** (`apiClient`, unchanged) | Detecting and normalizing a 401 into `ApiError { kind:"http", status:401 }` — already does this today | Refresh, retry, redirect, any auth business logic |
| **Auth/session coordinator** (new: `src/lib/auth/authenticatedRequest.ts` + `src/lib/auth/refreshCoordinator.ts`) | The refresh-on-401-then-retry-once dance; the single-flight guarantee (§10); deciding which requests are safe to retry (§11) | Routing/navigation; it never imports `next/navigation` |
| **Routing / `AuthProvider`/`ProtectedRoute`** | Reacting to "session is now anonymous" by navigating to `/login?returnTo=...` | Any HTTP call of its own beyond what `AuthProvider`'s own session query performs |

**Exclusions (non-negotiable, prevents every form of recursion named in the brief):**

- `login`, `logout`, and `refresh` themselves are **always** called directly through `apiClient.post(...)` — **never** through the refresh-aware wrapper (`authenticatedRequest`). This is enforced by construction (the wrapper is simply never imported into `useLogin`/`useLogout`/the refresh coordinator's own call), not by a runtime check, so there is no code path by which refresh can trigger refresh, login can trigger refresh, or logout can trigger refresh.
- The refresh coordinator never auto-retries a request to `/api/v1/auth/*` itself.
- Only ONE retry is ever attempted per original request, win or lose — if the retried request also 401s, that is surfaced as a final failure (triggering the expired-session transition), not a second refresh attempt.

---

## 7. Single-Flight Refresh

**Corrected design (generic, genuinely contract-independent — the original version below this line hardcoded the real refresh call directly inside the coordinator, which smuggled in an assumption about its shape; Task T06 now builds only the generic primitive):**

```ts
function createSingleFlight<T>(fn: () => Promise<T>): () => Promise<T> {
  let inFlight: Promise<T> | null = null;
  return () => {
    if (inFlight) return inFlight;
    inFlight = fn().finally(() => { inFlight = null; });
    return inFlight;
  };
}
```

This primitive has **no knowledge of refresh, `apiClient`, cookies, CSRF, or status codes** — it deduplicates concurrent calls to *any* injected async function, preserving its real resolve value and rejection reason unchanged (never collapsed to a boolean). Wiring it to the real `POST /api/v1/auth/refresh` call — i.e., `const refreshOnce = createSingleFlight(() => apiClient.post("/api/v1/auth/refresh"))` — is Task T07's job, and T07 remains **BLOCKED ON BACKEND CONTRACT** until the backend confirms refresh's real success/failure semantics (§2 rows 15/18/20/22).

Every concurrent 401 across any number of simultaneous requests would call the wired `refreshOnce()`; the first caller starts it, every other caller observes the same in-flight promise and awaits that exact reference. Once settled (success or failure), the slot clears, so a **later, independent** 401 can start a fresh refresh — this is not a one-time lockout, just a per-attempt dedupe. No queue library, no event emitter framework — one closure variable and one promise.

---

## 8. Request Replay Safety

Per §2 row 37: no backend statement proves a 401 is always returned **before** a write's side effect executes. A blanket "retry any POST/PATCH/DELETE after a successful refresh" policy is therefore **not safe to build** and is explicitly **not built** in this slice.

**Scoped, implementable-now rule:**

- **GET requests** are retried automatically after a successful refresh — reads have no side-effect-duplication risk.
- **POST/PATCH/DELETE requests are never auto-retried by default.** A caller may explicitly opt in per-call (e.g., `authenticatedRequest(() => apiClient.post(...), { retryAfterRefresh: true })`), but **no call in FVS-003 itself opts in**, since FVS-003 has no authenticated write endpoint of its own to protect (login/logout/refresh are explicitly excluded from this wrapper entirely, per §6).
- The general "is it safe to replay an authenticated write after a refresh" question is logged as an explicit open item for **every future authenticated slice**, not resolved here — see Backend Questions, "401/REPLAY."

This lets FVS-003 ship a real, useful 401→refresh→retry mechanism today without betting on an unconfirmed backend guarantee.

---

## 9. Auth Context (`AuthProvider`)

**Public interface (deliberately minimal — nothing added "because it might be useful"):**

```ts
interface AuthContextValue {
  user: SafeUser | null;       // non-secret metadata only, or null if anonymous/unknown
  isAuthenticated: boolean;
  isLoading: boolean;          // true only during the very first bootstrap check
  logout: () => void;          // wraps useLogout's mutate; fire-and-forget from the caller's perspective
}
```

No `refreshSession()` exposed publicly — refresh is reactive (driven by 401s via T07's wrapper) and the single-flight coordinator already prevents any need for a caller to manually trigger it. If a genuine future need for a manual "refresh now" button appears, it is added then, not spec'd speculatively now.

**Ownership split (per this plan's own rule, avoiding two sources of truth):**

- **TanStack Query** owns the actual server-derived session data — one query, key `["auth", "session"]`, `staleTime: Infinity` (session validity isn't something that goes stale on a timer; it's invalidated by explicit events — login success, logout, refresh failure — never by a background poll), `retry: false` (an auth check that fails should not silently retry against a real anonymous state).
- **`AuthProvider`** is a thin context wrapper around that one query plus the `logout` action — it derives `isAuthenticated`/`isLoading`/`user` from the query's own `status`/`data`, and never maintains a second, independently-settable piece of state that could drift from the query.

**The bootstrap query function itself is the part blocked by §1.** The query's shape (key, `staleTime`, `retry`, and the `AuthContextValue` it projects) is decidable now and is Task T04's first, unblocked half. Its `queryFn` body — "how do we actually determine whether a returning browser has a valid session" — is Task T04's second half, sequenced after one of §1's four options is approved.

---

## 10. Auth Bootstrap (page-load behavior)

Three states only, matching `isLoading`/`isAuthenticated`:

| State | `isLoading` | `isAuthenticated` | UI |
|---|---|---|---|
| Unknown (bootstrap in flight) | `true` | — (ignored) | `LoadingSpinner`, nothing else rendered yet |
| Authenticated | `false` | `true` | Real content |
| Anonymous | `false` | `false` | `ProtectedRoute` redirects; public pages render normally |

**No protected content is ever rendered before the bootstrap check resolves** — `ProtectedRoute` (T05) checks `isLoading` first, unconditionally, before even looking at `isAuthenticated`. No `localStorage`-based "optimistic" authenticated flash is used to fake instant persistence; that would be exactly the token-persistence anti-pattern §3 forbids (there is no non-secret way to know "probably still logged in" without asking the server).

---

## 11. Protected Route

```tsx
<ProtectedRoute>
  <SomeFutureAuthenticatedPage />
</ProtectedRoute>
```

- `isLoading` → render `LoadingSpinner` only.
- `isAuthenticated` → render `children`.
- anonymous → `router.replace(`/login?returnTo=${encodeURIComponent(safeReturnTo)}`)`, rendering nothing (not even a flash of `children`) while the redirect is in flight.
- **No authorization/role checking.** `ProtectedRoute` answers exactly one question — authenticated vs. not — and nothing about *which* authenticated user may see *what*. That is explicitly out of scope (§ Non-Scope) unless a later slice states otherwise.

**Open scope note (not silently decided):** no real protected application page exists yet in this repository (FVS-006, which would be the first real consumer, is not built). `ProtectedRoute`'s own unit tests use a trivial fake child (same pattern as `Form.test.tsx`'s `FakeField`), which needs no real page. The **E2E** flow's "visit a protected route" step, however, needs *something* to visit — see Task T12's own open question.

---

## 12. Safe `returnTo`

```ts
export function isSafeReturnTo(value: string): boolean {
  if (!value.startsWith("/") || value.startsWith("//")) return false;
  try {
    const resolved = new URL(value, window.location.origin);
    return resolved.origin === window.location.origin;
  } catch {
    return false;
  }
}
```

- Must start with exactly one `/` (rejects `https://evil.com`, `javascript:...`, `data:...` outright — none start with `/`).
- Rejects `//evil.com` (protocol-relative) via the explicit `startsWith("//")` check **and** the `URL`-origin re-check as defense in depth (resolving `//evil.com` against the app's own origin still yields a different origin).
- Falls back to `/` when the candidate is missing, empty, or fails the check.
- Query parameter name: **`returnTo`** (settled, §2 row 39 — matches the spec's own prose).

Tested explicitly against encoded/open-redirect attempts (`%2F%2Fevil.com`, `/\evil.com`, `/..%2f..`, etc. — the exact list lives in Task T01's test matrix, not invented twice).

---

## 13. Cache Security (logout / session expiry)

On logout success **and** on a refresh-failure-triggered session expiry, `AuthProvider`:

1. Calls `queryClient.setQueryData(["auth","session"], anonymousShape)` (or `removeQueries` — T09 decides the precise call during implementation; either is safe here since there is exactly one auth query right now) so `isAuthenticated` flips to `false` immediately, without waiting for a refetch.
2. **Establishes the convention, does not build a taxonomy:** this slice has no other authenticated-user-scoped query to worry about yet (no `/me`, no orders, no profile). The convention for **future** authenticated slices is recorded here so they don't each invent their own: *any query whose data would differ between two different logged-in users, or between a logged-in and an anonymous user, should nest its query key under a shared, exported prefix constant from this slice's auth module (e.g. `AUTH_SCOPED_QUERY_KEY_PREFIX`), so a single future `queryClient.removeQueries({ queryKey: [AUTH_SCOPED_QUERY_KEY_PREFIX], exact: false })` call on logout generalizes without re-deriving the rule.* No elaborate cache taxonomy is built now, since no second authenticated query exists to prove the pattern against yet.

---

## 14. Accessibility

Reuses FVS-002's established baseline exactly (visible labels, `aria-describedby`, `aria-invalid`, polite error summary, focus-first-invalid-field, password show/hide with correct `aria-pressed`, visible focus ring via the existing `brand-dark-green` double-ring token — no new focus styling needed).

**New to this slice:**
- Login success → redirect: focus must land somewhere meaningful post-navigation, not silently at `<body>` — same `tabIndex={-1}` + programmatic-focus pattern FVS-002 Batch 4 already established for its own success states, applied to whatever the destination page is (the protected route the user was headed to, or `/` if none).
- A session-expired message (when refresh fails mid-session) must be discoverable by assistive technology — reuses `Alert`'s existing `role="status"`/`aria-live="polite"` pattern (not `role="alert"` — an expired session is informational, not a mid-task error, consistent with `BackendUnreachableBanner`'s own not-ready/unreachable precedent from FVS-001).

---

## 15. Responsive Design

Identical card pattern to FVS-002: mobile single-column, full-width inputs/CTA (explicitly including the `w-full` class FVS-002 Batch 4 added after finding its own register/resend buttons weren't full-width — T03 must not repeat that defect); desktop centered card, `max-width: 420px`. No new breakpoint. No raw hex colors anywhere in this slice's components — only existing semantic tokens.

---

## 16. Testing Strategy

**Unit/component:** `returnTo` validator (pure function, exhaustive attack-string matrix), the refresh coordinator (single-flight, mocked `apiClient`, fake timers where relevant), `authenticatedRequest`'s GET-retry/no-write-retry rule, `ProtectedRoute` (against a mocked `AuthProvider` context, three states), the login Zod schema, the cross-tab `BroadcastChannel` helper (a thin wrapper, mockable in jsdom).

**Integration:** Login (success, invalid credentials with enumeration-safe generic copy, rate-limit-with-`retryAfterSeconds`, rate-limit-without-duration, no double submission, safe `returnTo` round-trip); refresh (401 → one refresh → retry original once; refresh failure → expired-session transition; no recursion against login/logout/refresh themselves; concurrent 401s share one refresh); logout (backend call, cache clear, cross-tab broadcast fires); `ProtectedRoute` (loading/authenticated/anonymous-redirect, malicious `returnTo` never honored).

**E2E (deterministic, backend-independent, route-interception only):** register → verify → login → (protected-route step — see T12's open scope note) → logout → protected route redirects to `/login` again.

**Real backend (separate, final gate, mirrors FVS-001/002's own T14 pattern):** real cookies set/sent/persisted-across-reload, real refresh, real logout, and — once T08 unblocks — real CSRF accept/reject behavior. Never faked with `page.route` interception; never folded into the default `npm run test:e2e` run.

---

## 17. Dependency Policy

Checked against native/already-installed capability before proposing anything (per instruction):

- **Cross-tab logout:** native `BroadcastChannel` (Chrome 54+, Firefox 38+, Safari 15.4+, Edge 79+) — no package. Chosen over a `localStorage` `storage`-event fallback because it is purpose-built for exactly this (cross-tab, same-origin messaging) and needs no write-then-clean-up of a persisted key; the broader historical browser support `storage` events offer is not a stated requirement anywhere in this repository (**ASSUMED** project browser-support floor — flagged, not a confirmed requirement; override if the team needs pre-2022 Safari).
- **Cookie access:** none needed — httpOnly cookies are never read by design (§3); no `js-cookie` or similar.
- **Auth state:** React Context + the existing TanStack Query instance — no Redux/Zustand.
- **Router helpers:** Next.js's own `useRouter`/`redirect` — no third-party router-helper package.

**No new runtime dependency is added by this plan.**

---

## 18. Skill Map

| Skill | Applies to |
|---|---|
| `bekaa3d-brand-ui` | T03 (login form, once unblocked), T11 (responsive/accessibility pass) |
| `bekaa3d-api-contract` | T02 (login mutation — blocked), T04 (bootstrap — blocked), T07 (401 wiring — blocked), T08 (CSRF — blocked), T09 (logout — blocked), planning itself (this document). **Not** T06 or T10 — both are now generic primitives with zero contract knowledge by design. |
| `bekaa3d-frontend-slice-dod` | T11 (integration pass), T13–T14 (final verification) |
| `bekaa3d-commerce-ux` | **Not used anywhere in this slice** (§0) |
| `superpowers:test-driven-development` | Every task marked TDD REQUIRED below — currently buildable: T01, T05 (vs. mock), T06, T10; blocked until their gates clear: T02, T03, T04, T07, T09 |
| `superpowers:verification-before-completion` | Every task |
| `superpowers:requesting-code-review` | T11 (whole-slice gate) and T14 (final real-backend gate) |

---

## Global Constraints

- Local Git only: no remote, no push, no PR, no GitHub MCP.
- One task at a time within a batch; STOP after each batch; wait for explicit instruction before the next.
- Full verification (`lint`, `typecheck`, `test`, `build`, plus `test:e2e` where the task touches routes/pages) before every commit.
- One local commit per task (mirrors FVS-002's own discipline, not "one commit per batch").
- Never invent a backend contract item marked `NEEDS BACKEND CONFIRMATION` in §2 — implement only what that row's "Frontend consequence" column actually allows.
- Reuse FVS-001/FVS-002 primitives/conventions; do not redesign `apiClient`, `ApiError`, `QueryProvider`, `AppLayout`, routing, `Form`/`TextField`/`PasswordField`/`Button`/`Alert`, or error-boundary conventions.
- No `data-testid` sprinkled everywhere — prefer role/label/text queries exactly as FVS-001/FVS-002's own tests do.

## Review Focus

(The five input classes/conditions most likely to bite a real user that no single task's own tests might otherwise catch — verified across the slice, primarily in T11.)

1. **Concurrent 401 storm** — five simultaneous authenticated requests all failing with 401 at once must trigger exactly one refresh, not five — tested explicitly in T06/T07.
2. **Refresh-failure navigation loop** — a failed refresh must redirect to `/login` exactly once, not repeatedly re-trigger itself if the login page's own boot sequence somehow re-checks auth state — tested in T04/T05's integration.
3. **StrictMode double-invoke of the bootstrap effect** — React 19 Strict Mode's dev-only double-invoke must not fire the bootstrap check (or, once resolved, the refresh probe) twice — same guard pattern FVS-002 Batch 3's `useVerifyEmail` already proved works (a ref not reset in cleanup), reapplied here — tested in T04.
4. **Open-redirect via `returnTo` surviving encoding** — percent-encoded and backslash-based open-redirect attempts must all resolve to the safe fallback — tested exhaustively in T01.
5. **Cross-tab logout racing a concurrent login** — logging out in tab A while tab B is mid-login must not leave tab B in a confused half-authenticated state — tested in T10.

---

## Task Status Classification (corrected — see changelog below)

> **CORRECTED at the first post-planning review.** The original version of this plan marked T02 (login mutation) and T09 (logout) as "CAN IMPLEMENT NOW" merely because their fields were *likely* (`{email,password}`, no body) — inconsistent with this same plan's own Contract Confidence Table, which lists their exact request/response semantics as unconfirmed. Corrected below. T06 and T10 were also re-examined and found to contain real, extractable, genuinely contract-independent sub-pieces once their HTTP/business-wiring halves are separated out — both are now split the same way T04 already was in the original version.

Four honest categories, used consistently from here on:

- **CAN IMPLEMENT NOW** — no backend contract gap and no pending architecture decision blocks real, final code.
- **IMPLEMENTABLE NOW / REAL BACKEND ACCEPTANCE LATER** — the code can be written and unit/integration-tested for real today (against a mock or a generic injected dependency), but its *real-world* correctness cannot be proven until a backend-contract or architecture gap closes.
- **BLOCKED ON BACKEND CONTRACT** — writing the real implementation would require inventing an unconfirmed backend detail (a field name, a status code, a body shape, a CSRF requirement, etc.). No code is written until the backend confirms.
- **BLOCKED ON ARCHITECTURE DECISION** — the backend contract isn't actually the blocker; a *project-side* decision (the §1 bootstrap-mechanism choice, or an explicit policy sign-off) is.

| Task | Corrected classification | Why |
|---|---|---|
| T01 `returnTo` validator | **CAN IMPLEMENT NOW** | Pure frontend logic; no backend involvement at all (unchanged from the original plan). |
| T02 Login mutation | **BLOCKED ON BACKEND CONTRACT** | Was incorrectly "CAN IMPLEMENT NOW" — calling the real endpoint requires committing to assumed field names (`{email,password}`), an assumed success/failure shape, and an assumed CSRF-exemption, none of which is confirmed (§2 rows 2/3/5/6/7/8/9/32). |
| T03 Login page | **BLOCKED ON BACKEND CONTRACT** | Depends on T02's assumed schema; as scoped (the real business form wired to the real mutation), it inherits T02's blocker. A presentational-only `LoginForm` shell *could* theoretically be isolated from the real mutation (no business schema, just markup/a11y structure) — not split out as its own task ID in this correction to avoid inflating the task count for a sub-slice no one has asked to prioritize; flagged here as a legitimate future split if a team wants visual-only login UI work scheduled before the contract lands. |
| T04 AuthProvider | **BLOCKED ON ARCHITECTURE DECISION** | Was "SPLIT" in the original version with an "interface half" marked CAN IMPLEMENT NOW. Corrected: even the interface half must not ship a `user` field that implies real metadata exists while §1 is unresolved — so the *entire* task, including its shell, waits for one of §1's four options to be approved. (The shell's *design* — §9's four-field `AuthContextValue` shape — remains valid design work and needs no further planning once unblocked; it just isn't built yet.) |
| T05 ProtectedRoute | **IMPLEMENTABLE NOW / REAL BACKEND ACCEPTANCE LATER** | Its loading/authenticated/anonymous-redirect logic can be fully built and unit-tested today against a *mocked* `AuthProvider` context value (three literal states fed in directly) — this requires no real contract, since it never calls an endpoint itself. Its real-world correctness (does "authenticated" ever actually become true against a real session) is gated on T04. |
| T06 Single-flight coordinator | **CAN IMPLEMENT NOW, but redesigned to be fully generic** | The original design hardcoded `apiClient.post("/api/v1/auth/refresh")` and collapsed success/failure to a boolean — that encodes assumed refresh semantics. Corrected: T06 now builds `createSingleFlight<T>(fn: () => Promise<T>): () => Promise<T>` — a generic async-deduplication primitive with **zero knowledge** of refresh, cookies, CSRF, endpoints, or status codes. It would behave identically if used to deduplicate any other concurrent async call. Wiring an actual refresh call into it is a separate, later, contract-blocked step (absorbed into T07, not a task of its own). |
| T07 401 integration wrapper | **BLOCKED ON BACKEND CONTRACT** | Was incorrectly "CAN IMPLEMENT NOW." Unlike T06's pure dedup primitive, T07's entire reason for existing is deciding *which* 401s are refreshable and *which* requests are safe to replay — exactly the two decisions §2 rows 35/37 and this correction's own instruction say must not be encoded into production code before the backend confirms enough to make them safely. No "pure utility" version is planned either, since a generic version of this specific wrapper would still have to take a stance on retry-after-refresh semantics to be useful, and that stance is the blocked part. |
| T08 CSRF plumbing | **BLOCKED ON BACKEND CONTRACT** | Unchanged in substance from the original "BLOCKED ON CSRF CONTRACT" — relabeled to fit the four-category scheme used consistently now. |
| T09 Logout | **BLOCKED ON BACKEND CONTRACT** | Was incorrectly "CAN IMPLEMENT NOW." Calling the real endpoint requires an assumed body shape, an assumed CSRF-exemption, and — explicitly flagged in the original plan itself as a non-silent decision point — the unresolved local-clear-on-network-failure policy (§2 rows 24/25/26/27/28). |
| T10 Cross-tab logout | **CAN IMPLEMENT NOW, but redesigned to separate the signal from the wiring** | The original design wired `announceLogout()` directly into `useLogout`'s success handler, inheriting T09's blocker by association. Corrected: the `BroadcastChannel` wrapper itself (`announceLogout()`/`onLogoutAnnounced()`, posting/receiving an opaque `{type:"logout"}` message) has **no knowledge of logout's HTTP semantics at all** — it doesn't know what triggered the broadcast, only that something did. That primitive is genuinely contract-independent and buildable today. *Wiring* it into `useLogout`'s success handler remains deferred until T09 unblocks (a one-line call once it does). |
| T11 Integration/security pass | **Pending — transitively blocked** | Depends on T02/T03/T04/T07/T09 all being real, all of which are now contract/architecture-blocked. Not schedulable until enough of those clear. |
| T12 E2E | **Pending — transitively blocked** | Depends on T11. |
| T13 Docs | **Pending — transitively blocked** | Depends on T12 (can draft early, per the original plan). |
| T14 Real-backend/CSRF acceptance | **BLOCKED ON BACKEND CONTRACT + backend availability** | Unchanged — already explicitly blocked in the original plan. |

---

## Task Dependency Graph (corrected)

```
T01 (returnTo validator) — CAN IMPLEMENT NOW, no edges in
T06 (generic single-flight primitive) — CAN IMPLEMENT NOW, no edges in
T10 (generic cross-tab signal primitive) — CAN IMPLEMENT NOW, no edges in

T02 (login mutation, BLOCKED ON BACKEND CONTRACT) ── T03 (login page, BLOCKED ON BACKEND CONTRACT)

T04 (AuthProvider, BLOCKED ON ARCHITECTURE DECISION §1) ── T05 (ProtectedRoute, IMPLEMENTABLE NOW vs. mock / REAL ACCEPTANCE LATER)
                                                        └── T09 (logout, BLOCKED ON BACKEND CONTRACT) ── [wires T10's primitive in]

T06 ── T07 (401 wrapper, BLOCKED ON BACKEND CONTRACT — needs T06's primitive once unblocked)

T08 (CSRF, BLOCKED ON BACKEND CONTRACT, no edges in or out yet)

{T01..T10 all real} ── T11 (integration/a11y/security pass) ── T12 (E2E) ── T13 (docs) ── T14 (real-backend + CSRF acceptance)
```

- **Fully unblocked today, zero dependencies:** T01, T06 (generic primitive), T10 (generic primitive).
- **T05** is unit-testable today against a mocked context (no edge into a *blocked* task for that purpose) but its real integration edge into T04 remains until §1 resolves.
- **T02→T03**, **T04→T09**, **T06→T07** are the contract/architecture-blocked chains — none of them can start until their respective gate clears.
- **T08** still has no outgoing edges — unblocking it later adds edges into T02/T06-via-T07/T09 as a follow-up, not predicted further here.
- **T11** depends on T01–T10 all being real (not just T01/T06/T10's primitives) — it cannot start meaningfully until the backend contract and the §1 decision both land. **T12** depends on T11. **T13** can draft early. **T14** depends on T12, real backend availability, and T08.

**Critical path (corrected):** the backend answering the Backend Questions (login/refresh/logout fields+semantics, CSRF) **and** the §1 bootstrap-mechanism decision — both now gate almost the entire slice, not just T04 as the original version implied. Only T01, T06's primitive, and T10's primitive are free of that critical path entirely.

---

## Optimized Implementation Batches (corrected)

| Batch | Contents | Gate to start |
|---|---|---|
| **Batch 1 — Safe, contract-independent infrastructure** | T01 (`returnTo` validator), T06 (generic single-flight primitive), T10 (generic cross-tab signal primitive) | None — startable immediately |
| **Batch 2 — Login** | T02 (login mutation), T03 (login page) | Backend confirms login's request/response contract (Backend Questions "LOGIN") |
| **Batch 3 — Bootstrap, protection, refresh wiring, logout, CSRF** | T04 (AuthProvider), T05 (ProtectedRoute real integration), T07 (401 wrapper wired to T06), T09 (logout, wires T10's primitive in), T08 (CSRF, if its own contract has also landed by then) | The §1 bootstrap decision **and** the backend confirming refresh/logout/CSRF contracts |
| **Batch 4 — Integration/security/E2E/docs** | T11, T12, T13 | Batches 2 and 3 both landed |
| **Real backend acceptance (separate, final gate)** | T14 | Real backend reachable, CSRF contract confirmed |

This replaces the original plan's four-batch shape (which bundled T02/T03 into "Batch 1" and T04/T05 into "Batch 2" without registering that both were contract/architecture-blocked). **Batch 1 above is the only batch currently startable without any external unblock** — see Part B of this correction for its actual execution.

---

## TDD Map

| Task | TDD status |
|---|---|
| T01 | TDD REQUIRED (pure function, exhaustive attack-string matrix) |
| T02 | TDD REQUIRED once unblocked |
| T03 | TDD REQUIRED once unblocked |
| T04 | TDD REQUIRED once unblocked |
| T05 | TDD REQUIRED (buildable now against a mocked context) |
| T06 | TDD REQUIRED (buildable now — generic primitive, highest-value isolated security module) |
| T07 | TDD REQUIRED once unblocked |
| T08 | VERIFICATION ONLY — no implementation exists to test yet; task is a tracked placeholder |
| T09 | TDD REQUIRED once unblocked |
| T10 | TDD REQUIRED (buildable now — generic primitive) |
| T11 | Verification pass — not new-feature TDD; DoD-checklist-driven |
| T12 | E2E — behavior-defined-before-done, not unit RED/GREEN |
| T13 | CONFIG/DOCS — TDD not required |
| T14 | Verification/acceptance — TDD not applicable |

---

## Task List

### FVS003-T01 — Safe `returnTo` Validator

**Status:** CAN IMPLEMENT NOW.
**Purpose:** The one security-critical pure function every redirect-to-login call site depends on.
**Depends on:** None.
**Contract gates:** None — pure frontend logic (§12).
**Files expected:** `src/lib/auth/returnTo.ts`, `returnTo.test.ts`.
**Implementation actions:**
1. RED: tests for the exact matrix in §12 — valid relative paths accepted; `//evil.com`, `https://evil.com`, `javascript:...`, `data:...`, `\\evil.com`, percent-encoded variants (`%2F%2Fevil.com`), and a missing/empty value all rejected (fall back to `/`).
2. GREEN: implement `isSafeReturnTo` and a small `resolveReturnTo(value: string | null): string` wrapper that returns the validated value or `/`.
**Do NOT:** allow any absolute URL, any protocol-relative URL, any non-`/`-leading value; invent a allow-list of "trusted" external domains.
**Tests:** TDD required.
**Acceptance criteria:** Every attack string in Review Focus item 4 is rejected; every legitimate relative path is accepted.
**Verification:** `npm run test -- returnTo`, then full suite.
**Skills/tools:** `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add safe returnTo validator`

---

### FVS003-T02 — Login Schema & Mutation

**Status:** **BLOCKED ON BACKEND CONTRACT** (corrected — see the Task Status Classification section above). **Do NOT implement until the backend confirms:** login request field names, success status/body, failure status/signal, cookie/session behavior relevant to the frontend, and whether CSRF applies to login (§2 rows 2/3/5/6/7/8/9/10/32). The `{email,password}` shape below is this plan's working *expectation*, not a confirmed contract — it must not be coded against until confirmed, even though it is likely correct.
**Purpose:** The real login mutation, enumeration-safe by construction.
**Depends on:** None (architecturally), but **execution is blocked** until the Backend Questions "LOGIN" group is answered.
**Contract gates:** Rows 2, 3, 5, 6, 7, 8, 9, 10, 32 of §2 are unconfirmed — every one of them would need to be invented to write real code today, which this task does not do.
**Files expected (once unblocked):** `src/lib/auth/useLogin.ts`, `useLogin.test.ts`.
**Implementation actions (once unblocked):**
1. RED: mutation tests mirroring `useRegister.test.ts`'s own rigor — exact confirmed path/body, no trailing slash, `retry:false`, network/timeout/http-error pass-through unchanged, a `429` with `retryAfterSeconds` surfaces unchanged (no invented countdown at this layer — that's T03's UI concern).
2. GREEN: implement `useLogin()` using `apiClient.post`, called **directly** (never through T07's `authenticatedRequest` wrapper — §6's exclusion rule).
**Do NOT:** add a field beyond whatever the backend actually confirms; invent a distinct "account locked" `ApiError` shape; auto-retry; begin this task before the contract is confirmed merely because the shape seems obvious.
**Tests:** TDD required once unblocked.
**Acceptance criteria:** Matches `useRegister`'s own proven pattern exactly; `retry:false` proven with the fake-timer technique FVS-002 Batch 4's independent review required (not a bare immediate call-count check).
**Verification:** `npm run test -- useLogin`, full suite.
**Skills/tools:** `bekaa3d-api-contract`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add login mutation`

---

### FVS003-T03 — Login Page (`/login`)

**Status:** **BLOCKED ON BACKEND CONTRACT** (corrected — inherits T02's blocker, since this page is the real business form wired to the real mutation and schema). A presentational-only `LoginForm` shell with no business schema is a legitimate future split (see the Task Status Classification table above) but is not carved out as its own task ID here; nothing in this task proceeds until T02 unblocks.
**Purpose:** The real login form and enumeration-safe failure UX.
**Depends on:** T02 (and T01, since a successful login redirects through the `returnTo` validator).
**Contract gates:** Same unconfirmed rows as T02; additionally row 9 (lockout signal) — no lockout duration/countdown is rendered unless `retryAfterSeconds` is actually present on a `429`.
**Files expected (once unblocked):** `src/app/login/page.tsx`, `page.test.tsx`.
**Implementation actions (once unblocked):**
1. RED: page tests — renders labeled email/password fields + submit (reusing `Form`/`TextField`/`PasswordField`/`Button`); client-validation blocks an empty submit without calling the mutation; a credential-rejection failure (any `ApiError.kind:"http"` 4xx) shows exactly "Invalid email or password." — never a distinct "no such user" vs. "wrong password" copy, and never for two different mocked failure reasons does the copy differ (enumeration-safety test, same pattern as FVS-002's register/resend); a `429` with `retryAfterSeconds` shows a safe "too many attempts, wait about Ns" message, a `429` without it shows a safe generic message with no invented duration; network/timeout get their own safe messages; double-submit prevented via `Form`'s existing `fieldset disabled={isSubmitting}` guard; on success, navigates to the validated `returnTo` (or `/` if absent/unsafe) via T01's resolver.
2. GREEN: implement the page, `type="text"`+`inputMode="email"` for the email field (same auto-trim-avoidance reasoning as FVS-002), `w-full` on the submit button from the start (do not repeat FVS-002's own found-and-fixed mobile-CTA defect).
**Do NOT:** invent a password-strength hint (login isn't registration — there's nothing to hint at); invent a lockout countdown without `retryAfterSeconds`; trim/normalize either field unless a confirmed rule says to.
**Tests:** TDD required, including the explicit enumeration-safety test.
**Acceptance criteria:** Enumeration-safety test passes; double-submit test passes; full-width CTA present from the start.
**Verification:** `npm run test -- login`, full suite, `npm run build`.
**Skills/tools:** `bekaa3d-api-contract`, `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add login page`

---

### FVS003-T04 — Auth Session Query & `AuthProvider`

**Status:** **BLOCKED ON ARCHITECTURE DECISION** (corrected — the original version split this into an "interface half" marked CAN IMPLEMENT NOW; that was wrong). **Do not implement any part of this task, including the context shell, until one of §1's four options (A–D) is approved.** The concern raised at correction time: even a deliberately-placeholder `AuthContextValue.user` field, shipped before §1 resolves, risks implying real user metadata exists or will shortly — safer to not write the shell at all than to write one with a field whose future shape is still genuinely unknown. The four-field shape in §9 remains the *design* (no further design work needed once unblocked); it is simply not coded yet.
**Purpose:** The single source of truth for "is anyone logged in," and the thin context wrapper the rest of the app consumes.
**Depends on:** The §1 architecture decision — nothing in this task starts before then.
**Contract gates:** §1 (AUTH BOOTSTRAP ENDPOINT) blocks the entire task. Rows 6/14/23 of §2 (does login/refresh ever return user/session data) directly affect which option gets chosen and therefore what the eventual `user` field can actually contain.
**Files expected (once unblocked):** `src/lib/auth/AuthProvider.tsx`, `AuthProvider.test.tsx`, `src/lib/auth/authQueryKey.ts` (the shared `["auth","session"]` key + the `AUTH_SCOPED_QUERY_KEY_PREFIX` convention from §13).
**Implementation actions (once §1 is resolved):**
1. RED/GREEN: `AuthProvider` context shape (`user`/`isAuthenticated`/`isLoading`/`logout`), wired to a TanStack `useQuery(["auth","session"], queryFn, { staleTime: Infinity, retry: false })`, where `queryFn` implements whichever of options A–D was approved, including the React Strict Mode double-invoke guard named in Review Focus item 3 if the chosen option performs a side-effecting call (e.g. Option C's speculative refresh).
**Do NOT:** persist any part of the session to browser storage; add fields to `AuthContextValue` beyond the four listed in §9; write any version of this file — including a "placeholder" — before §1 resolves.
**Tests:** TDD required once unblocked.
**Acceptance criteria:** `AuthProvider` correctly projects the real query state (loading/error/success) into the four public fields; a real returning session resolves `isAuthenticated: true` without ever reading a cookie value or `localStorage`.
**Verification:** `npm run test -- AuthProvider`, full suite.
**Skills/tools:** `bekaa3d-api-contract`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add auth session query and AuthProvider` (once unblocked).

---

### FVS003-T05 — `ProtectedRoute`

**Status:** **IMPLEMENTABLE NOW / REAL BACKEND ACCEPTANCE LATER** (corrected — clarified from the original "CAN IMPLEMENT NOW"). Its own logic can be fully built and unit-tested today against a **mocked** `AuthProvider` context value (three literal states fed in directly — this test technique requires no real `AuthProvider` to exist yet, only an agreed-upon shape for the context value, which §9's design already settles). Its real-world correctness — does "authenticated" ever actually become `true` against a genuine session — is gated on T04, which is now fully blocked (see T04's corrected status above). **Do not claim this task is "done" in any sense beyond "unit-tested against a mock" until T04 unblocks and a real integration pass (T11) confirms it.**
**Purpose:** The reusable gate every future authenticated page/slice wraps itself in.
**Depends on:** T04's eventual interface (design-only dependency, not an execution-order one — T05 can be built before T04 exists, as long as it imports/mocks the *agreed* context shape from §9), T01 (`returnTo` resolver).
**Contract gates:** None of its own; its real-world acceptance inherits T04's §1 blocker.
**Files expected:** `src/components/auth/ProtectedRoute.tsx`, `ProtectedRoute.test.tsx`.
**Implementation actions:**
1. RED: tests mocking `AuthProvider`'s context value directly (three states) — loading renders `LoadingSpinner` and nothing else; authenticated renders `children`; anonymous renders nothing and calls `router.replace` with `/login?returnTo=<encoded current path>`; a malicious current path (per T01's matrix) never appears unescaped/unsafe in the generated redirect.
2. GREEN: implement using `useRouter`/`usePathname` from `next/navigation` and T01's validator.
**Do NOT:** add any role/permission check; render `children` even briefly before the loading check resolves.
**Tests:** TDD required, including the malicious-`returnTo`-prevention test from Review Focus item 4.
**Acceptance criteria:** All three states render correctly against a mocked context; no authorization logic present.
**Verification:** `npm run test -- ProtectedRoute`, full suite.
**Skills/tools:** `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add ProtectedRoute component`

---

### FVS003-T06 — Single-Flight Refresh Coordinator

**Status:** **CAN IMPLEMENT NOW — redesigned to be generic** (corrected). The original design hardcoded `apiClient.post("/api/v1/auth/refresh")` directly inside the coordinator, which smuggled in an assumption about the refresh call's shape/semantics. Corrected: this task now builds a fully generic async single-flight primitive with **zero knowledge of refresh, cookies, CSRF, endpoints, or status codes** — it would behave identically deduplicating any other concurrent async call. Wiring an actual refresh call into it is T07's job, and T07 remains blocked.
**Purpose:** The highest-value isolated, genuinely contract-independent security primitive in this slice.
**Depends on:** None.
**Contract gates:** None at all — by design, this module never imports `apiClient` or references any endpoint/path/status code.
**Files expected:** `src/lib/auth/singleFlight.ts`, `singleFlight.test.ts`.
**Implementation actions:**
1. RED: tests against a **generic injected async function** (a `vi.fn()` resolving/rejecting on demand, not `apiClient`) — a single call to the wrapped function starts exactly one underlying call; five concurrent calls while one is in flight all resolve/reject from the exact same promise (spy call-count stays at 1); after the in-flight promise settles (success **or** rejection — both must clear the in-flight slot, not just success), a new call starts a genuinely new underlying call (call count becomes 2); the wrapper preserves the original function's resolve value and rejection reason unchanged (no boolean-collapsing, no swallowed errors) — callers decide what a rejection means.
2. GREEN: implement `createSingleFlight<T>(fn: () => Promise<T>): () => Promise<T>` exactly per §7's corrected generic design.
**Do NOT:** import `apiClient`, reference `/api/v1/auth/refresh` or any other path, add retry/backoff, convert the result to a boolean, or build a generic request-queue library — this is a single, minimal, reusable dedup primitive and nothing more.
**Tests:** TDD required — this is Review Focus item 1's owning primitive (its actual wiring into a real refresh call happens in T07, blocked).
**Acceptance criteria:** The concurrent-call dedup property holds against an arbitrary injected async function, proving the primitive itself needs no contract knowledge to be correct.
**Verification:** `npm run test -- singleFlight`, full suite.
**Skills/tools:** `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add generic single-flight async coordinator`

---

### FVS003-T07 — `authenticatedRequest` 401 Integration Wrapper

**Status:** **BLOCKED ON BACKEND CONTRACT** (corrected — the original version marked this "CAN IMPLEMENT NOW," which was wrong). Unlike T06's now-generic primitive, this task's entire purpose is deciding *which* 401s are refreshable and *which* requests are safe to replay — exactly the two decisions §2 rows 35/37 (and this correction's own instruction) say must not be encoded into production code before the backend confirms enough to make them safely. No "pure utility" fallback version is planned either: a generic version of this specific wrapper would still have to take a real stance on retry-after-refresh semantics to be useful for anything, and that stance is precisely the blocked part. **Do not implement any version of this module until the backend confirms refresh's real success/failure contract (§2 rows 15/18/20/22) and the Backend Questions "401/REPLAY" item is answered.**
**Purpose:** Wires T06's generic primitive into actual request retry behavior, once the policy it would encode is safe to encode.
**Depends on:** T06 (available today), and the backend contract items above (not available today).
**Contract gates:** Row 37 of §2 (write-replay safety) and row 35 (which 401s are refreshable) both block real implementation; §11's GET-only-by-default scoping remains this plan's own recommended policy for whenever this task unblocks, not something built speculatively now.
**Files expected (once unblocked):** `src/lib/auth/authenticatedRequest.ts`, `authenticatedRequest.test.ts`.
**Implementation actions (once unblocked):**
1. RED: tests — a wrapped GET that 401s triggers exactly one refresh (via T06's primitive, mocked) then retries the original GET exactly once, succeeding if the retry succeeds; a wrapped GET whose retry also 401s surfaces the final error without a second refresh attempt; a wrapped POST that 401s does **not** auto-retry (resolves with the refresh outcome recorded but the original mutation is never re-sent) unless the caller passed `{ retryAfterRefresh: true }`, in which case it behaves like the GET case; a non-401 error passes through completely unchanged (no refresh attempted for a 500, a network error, a timeout, or any other status).
2. GREEN: implement `authenticatedRequest<T>(call: () => Promise<T>, options?: { retryAfterRefresh?: boolean; isRead?: boolean }): Promise<T>`, calling T06's primitive (wired to a real refresh call, once confirmed) only on an `ApiError` with `kind:"http"` and `status:401`.
**Do NOT:** import this module into `useLogin`/`useLogout`/the refresh call's own invocation (§6's exclusion rule — enforced by simply never doing it, verified by code review in T11); attempt a second refresh if the retried call also 401s; begin any part of this task before the contract confirms enough to make its central decisions safely.
**Tests:** TDD required once unblocked.
**Acceptance criteria:** Review Focus item 1 (concurrent storm) and the no-recursion rule both provably hold through this wrapper, not just through T06's primitive in isolation.
**Verification:** `npm run test -- authenticatedRequest`, full suite.
**Skills/tools:** `bekaa3d-api-contract`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add authenticated-request 401 retry wrapper` (once unblocked).

---

### FVS003-T08 — CSRF Plumbing (placeholder — tracked, not built)

**Status:** **BLOCKED ON CSRF CONTRACT.** No implementation action exists yet.
**Purpose:** Record exactly what must be confirmed before any CSRF code is written, so this isn't re-discovered from scratch later.
**Depends on:** The backend answering §2 rows 29–34 (and the Backend Questions "CSRF" group below).
**Contract gates:** All of rows 29–34.
**Files expected:** None yet.
**Implementation actions:** None yet — this task is a tracked gap, not a build step. Once unblocked, it will need: where the token is read from (cookie value — if JS-readable by design, unlike the session cookies — or a response field), which header name `apiClient` attaches it under, whether login/refresh/logout are exempt, and how rotation interacts with T06's single-flight coordinator (a token refreshed mid-flight must not race a concurrent mutation).
**Do NOT:** invent any of the bulleted unknowns in §5 to "unblock" this task early.
**Tests:** None yet.
**Acceptance criteria:** N/A until unblocked.
**Verification:** N/A until unblocked.
**Skills/tools:** `bekaa3d-api-contract`.
**Suggested commit message:** N/A — no commit for a task with no implementation.

---

### FVS003-T09 — Logout

**Status:** **BLOCKED ON BACKEND CONTRACT** (corrected — the original version marked this "CAN IMPLEMENT NOW," which was wrong). Calling the real endpoint requires an assumed body shape, an assumed CSRF-exemption, and this task's own explicitly-flagged, currently-unresolved local-clear-on-network-failure policy (§2 rows 24/25/26/27/28). **Do not implement until these are confirmed/decided.**
**Purpose:** The logout mutation, cache clearing, and `AuthProvider.logout()` wiring.
**Depends on:** T04 (now fully blocked — see T04's corrected status) for the `["auth","session"]` key convention; the Backend Questions "LOGOUT" group.
**Contract gates:** Rows 24/25/26/27/28 of §2 all block real implementation.
**Files expected (once unblocked):** `src/lib/auth/useLogout.ts`, `useLogout.test.ts`, plus the `logout` wiring inside `AuthProvider.tsx`.
**Implementation actions (once unblocked):**
1. RED: mutation test — exact confirmed path/body, `retry:false`; a successful logout clears the auth query cache (per §13) so `isAuthenticated` flips to `false` synchronously, without waiting for a refetch.
2. **Explicit, non-silent decision point (must be resolved before step 3, not invented):** if the backend logout call itself fails (network/timeout/5xx), should the frontend still clear local auth state? This plan does **not** decide this silently — implementers must get explicit sign-off at this task's execution time, since it's a genuine security/product tradeoff (clearing anyway = user-perceived instant logout but a session that's still technically valid server-side if the network call never arrived; not clearing = a confusing "logout didn't work" UX that may itself be exploitable if the user walks away assuming they're logged out). Record whichever answer is approved in `docs/` (T13) once decided.
3. GREEN: implement `useLogout()` + `AuthProvider.logout()`, calling `apiClient.post` **directly** (never through T07 — §6), and wiring in T10's already-built cross-tab signal primitive (one line: call its `announceLogout()`-equivalent inside the success handler).
**Do NOT:** auto-retry logout; call this through the `authenticatedRequest` wrapper; silently pick the network-failure behavior from step 2 without recording that a decision was made and by whom; begin this task before the contract/decision items above are resolved.
**Tests:** TDD required once unblocked.
**Acceptance criteria:** Cache clears on success; the network-failure decision from step 2 is explicitly recorded, not defaulted into silently.
**Verification:** `npm run test -- useLogout`, full suite.
**Skills/tools:** `bekaa3d-api-contract`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add logout mutation and cache clearing` (once unblocked).

---

### FVS003-T10 — Cross-Tab Logout Signal

**Status:** **CAN IMPLEMENT NOW — redesigned to separate the signal primitive from the logout wiring** (corrected). The original design wired `announceLogout()` directly into `useLogout`'s success handler as part of this same task, which inherited T09's blocker by association even though the broadcast mechanism itself knows nothing about logout's HTTP semantics. Corrected: this task now builds **only** the generic, opaque signal primitive. Wiring it into `useLogout`'s success handler is a one-line addition that happens as part of T09, once T09 unblocks — not duplicated or pre-empted here.
**Purpose:** The reusable, content-free, same-browser cross-tab signaling mechanism that logout (once unblocked) and any future cross-tab-relevant event can build on.
**Depends on:** None.
**Contract gates:** None — this module never calls `apiClient`, never references `/logout`, and has no opinion about what triggers a broadcast.
**Files expected:** `src/lib/auth/crossTabSignal.ts`, `crossTabSignal.test.ts`.
**Implementation actions:**
1. RED: tests — a thin wrapper around `BroadcastChannel("bekaa3d-auth")` exposing `announce(eventType: string)` and `onAnnounced(callback: (eventType: string) => void)`; posting from one instance is observed by a second instance (jsdom supports `BroadcastChannel` — confirm at implementation time; if the test environment genuinely lacks it, mock it explicitly and say so, never silently skip the test); the message payload is always an opaque string tag (e.g. `"logout"`) — never a token, user data, or anything identifying; posting and receiving on the *same* channel instance does not echo back to its own sender (standard `BroadcastChannel` behavior — assert it explicitly rather than assuming).
2. GREEN: implement the wrapper as a small, generic, reusable primitive — not logout-specific in its own type signature, even though logout is its first real caller.
**Do NOT:** give this module any knowledge of auth state, `AuthProvider`, or the query client; wire it into `useLogout` here (that happens in T09, once unblocked); broadcast any token/user data; fall back to a `localStorage` `storage`-event mechanism without an explicit decision to do so (§17 — not planned by default).
**Tests:** TDD required — this is Review Focus item 5's owning primitive (its actual logout-triggered usage is proven once T09 unblocks).
**Acceptance criteria:** A simulated second-tab broadcast is observed by a receiver registered via `onAnnounced`, proving the primitive itself needs no auth/logout contract knowledge to be correct.
**Verification:** `npm run test -- crossTabSignal`, full suite.
**Skills/tools:** `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add cross-tab signal primitive`

---

### FVS003-T11 — Integration, Accessibility & Security Pass

**Purpose:** The whole-slice-so-far verification gate, mirroring FVS-002 Batch 4's T11 discipline exactly (including dispatching a fresh independent code review).
**Depends on:** T01–T03, T04 (interface half minimum — note in the report if the bootstrap half is still blocked at this point, since that materially limits what "integration" can mean), T05–T07, T09, T10.
**Files expected:** Likely none beyond fixes; any defect fix goes in the smallest owning file, same discipline as FVS-002 Batch 4.
**Implementation actions:**
1. Walk `bekaa3d-frontend-slice-dod`'s full checklist against the real composed app.
2. Real keyboard/viewport/focus walkthrough (Playwright + system Edge, route interception, same six-breakpoint matrix as FVS-001/002) of `/login` and whatever minimal protected-route demonstration exists (see T12's open question — T11 can reuse whatever T12 settles on, or verify `ProtectedRoute` purely via its own unit tests if no demo page exists yet).
3. Security review per §3/§6/§7/§8/§11 — explicitly grep for `document.cookie`, `localStorage`, `sessionStorage` writes of anything token-shaped, confirm `authenticatedRequest` is never imported by `useLogin`/`useLogout`/`refreshCoordinator`.
4. Dispatch a fresh independent code-review subagent (per `superpowers:requesting-code-review`), scoped to T01–T10's diff against this plan, with particular focus on: no-token-persistence, single-flight correctness, no-refresh-recursion, replay-safety scoping, `returnTo` validator completeness, enumeration safety, accessibility.
5. Resolve every Critical/Important finding before this task is considered complete; fix-or-record Minor findings per the same rule FVS-002 Batch 4 used.
**Do NOT:** silently mark a browser-dependent check PASS without a real browser; expand scope into T12/T13/T14.
**Tests:** Verification-only; any defect fix gets a regression test in its owning file.
**Acceptance criteria:** DoD checklist walked with evidence; review findings resolved or explicitly recorded.
**Verification:** Full `lint`/`typecheck`/`test`/`build`, plus real-browser checks the environment supports.
**Skills/tools:** `bekaa3d-brand-ui`, `bekaa3d-api-contract`, `bekaa3d-frontend-slice-dod`, `superpowers:verification-before-completion`, `superpowers:requesting-code-review`.
**Suggested commit message:** `fix: address FVS-003 integration findings` (only if a fix was needed).

---

### FVS003-T12 — Deterministic E2E

**Purpose:** One deterministic, backend-independent E2E spec proving the conceptual flow.
**Depends on:** T11.
**Files expected:** `e2e/login-and-logout.spec.ts` (or extends `register-and-verify.spec.ts` — decide at implementation time which reads more clearly), added to the existing `smoke` project's `testMatch`.
**Implementation actions:**
1. **Open scope decision (flagged, not silently resolved):** the conceptual flow needs "a protected route" to visit between login and logout. Two honest options: (a) build one deliberately trivial, clearly-temporary demo route wrapped in `ProtectedRoute` purely to exercise this E2E (documented as temporary, removed or replaced once FVS-006 supplies a real one), or (b) scope this E2E to register→verify→login→logout→re-redirect-to-login, proving `ProtectedRoute`'s redirect behavior through its own unit/integration tests (T05) instead of an E2E visit to a page that doesn't exist yet. Recommend (b) to avoid shipping throwaway UI, but this is this task's own call to make explicitly at execution time, not pre-decided here.
2. Route-intercept `POST /api/v1/auth/login` (202/200 success, invalid-credential failure) and `POST /api/v1/auth/logout` (success); reuse the existing register/verify interception pattern from FVS-002's own `register-and-verify.spec.ts` if chaining the full conceptual flow in one spec.
3. Run `npm run test:e2e` twice to prove determinism (same discipline as every prior slice).
**Do NOT:** hit a real backend; build a second Playwright project; fold this into `backend-connectivity.spec.ts`.
**Tests:** This is the test.
**Acceptance criteria:** Two consecutive clean runs.
**Verification:** `npm run test:e2e` ×2, `npm run lint`, `npm run typecheck`, `npm run build`.
**Skills/tools:** `superpowers:verification-before-completion`.
**Suggested commit message:** `test: add login/logout E2E flow`

---

### FVS003-T13 — Documentation

**Purpose:** The auth architecture section, describing only what's actually committed.
**Depends on:** T12.
**Files expected:** `docs/frontend-setup.md` (new section, same file FVS-001/002 already extend — no new standalone doc).
**Implementation actions:**
1. Add a section covering: cookie-based auth and the httpOnly boundary (§3); why `credentials:"include"` is deliberately NOT used (§4); auth-state ownership split between TanStack Query and `AuthProvider` (§9); the refresh/single-flight/replay-safety design (§6–§8) including the explicit GET-only auto-retry scoping; the CSRF section stating plainly that it is unimplemented pending contract confirmation (§5) — not documented as if it exists; `ProtectedRoute`/`returnTo` validation (§11–§12); logout/cross-tab semantics (§13, §20) including whichever answer T09 recorded for the network-failure-during-logout question; the still-open `/me`/FVS-006 bootstrap question (§1), written as an open question, not as settled fact.
**Do NOT:** document CSRF as if a mechanism exists; document the bootstrap mechanism as settled if §1 is still unresolved at this point; write any FVS-006 profile-UI documentation.
**Tests:** None — docs task.
**Acceptance criteria:** Every path/command referenced actually exists; no speculative feature documented as real.
**Verification:** `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`.
**Skills/tools:** `bekaa3d-api-contract`.
**Suggested commit message:** `docs: document login and session management architecture`

---

### FVS003-T14 — Real Backend / Cookie / CSRF Acceptance

**BLOCKED** on real backend availability (unconfirmed throughout this engagement) **and** on T08/CSRF contract confirmation for its CSRF-specific proof. **Do not attempt until both are true.**
**Purpose:** Prove the real cookie-based session loop end-to-end, mirroring FVS-001/002's own real-backend acceptance gate.
**Depends on:** T12, real backend reachable, T08 unblocked (for the CSRF half only — the cookie/login/refresh/logout half can proceed once a real backend is reachable even if CSRF is still pending, with that specific sub-proof marked pending separately).
**Files expected:** A new real-backend E2E spec (exact name decided at implementation time, mirroring `backend-connectivity.spec.ts`'s own separate-script convention) plus a corresponding `test:e2e:backend:*`-style script.
**Implementation actions:**
1. Log in against the real backend through the real proxy; confirm real cookies are set and sent automatically on the next request.
2. Reload the page; confirm the session persists (real bootstrap mechanism, whichever §1 option was approved, actually works against a real cookie).
3. Force/observe a real refresh; confirm rotation and continued access.
4. Log out; confirm the real session is invalidated and a subsequent protected request genuinely 401s.
5. Once T08 is unblocked, confirm the real CSRF header/token round-trips correctly and that a missing/invalid CSRF value is genuinely rejected where the backend promises it will be.
**Do NOT:** fake any of this with `page.route`; skip and claim FVS-003 is done without it.
**Tests:** Real-backend acceptance evidence, not a unit test.
**Acceptance criteria:** A genuine, observed login→persist→refresh→logout loop against the real backend, output recorded; CSRF proof recorded once T08 unblocks.
**Verification:** The real run itself, output captured verbatim.
**Skills/tools:** `superpowers:verification-before-completion`.
**Suggested commit message:** `test: add real-backend session acceptance verification`

---

## Backend Questions (for later consolidated handoff — do not send yet)

**SESSION BOOTSTRAP**
1. Does VS-003 expose any current-session/current-user read endpoint, or is `/me` genuinely VS-006-only? (Resolves §1 Option A vs. B/C/D.)
2. Do `POST /login` or `POST /refresh` success responses carry any user/session body field at all, even a minimal one? (§2 rows 6/14/23.)

**LOGIN**
3. Exact request field names (confirm `email`/`password`)? Any login-specific password rule?
4. Success HTTP status and body shape?
5. Failure HTTP status for invalid credentials — and is there a distinct machine-readable code, or must the frontend treat all 4xx login failures identically?
6. Exact lockout/rate-limit signal — status code, and does it carry `Retry-After`?

**REFRESH**
7. Request body required, or cookie-only?
8. Success status/body — any rotation signal the frontend needs to react to?
9. Failure statuses — is reuse-detection distinguishable from a plain expired session, and should the frontend treat them differently?
10. Can refresh itself be rate-limited, and if so does it carry `Retry-After` too?

**LOGOUT**
11. Request body required?
12. Success status/body?
13. Idempotency — is calling logout twice safe?

**CSRF**
14. Where is the CSRF token delivered — a JS-readable cookie, or only in a login/bootstrap response body?
15. Exact header name the frontend must echo it in?
16. Which of login/refresh/logout require it?
17. Rotation strategy — does the token change on every request, only on login, only on refresh?

**401/REPLAY**
18. For any authenticated write endpoint, is a 401 guaranteed to occur strictly before the request's side effect executes (i.e., is it safe to blindly retry a write after a successful refresh), or must the frontend never assume this?

**COOKIES**
19. Cookie names, `SameSite`/`Secure`/`Path` values — not needed by frontend code, but useful to rule out a dev-environment proxy surprise being mistaken for a frontend bug.

**CROSS-TAB / SESSION INVALIDATION**
20. Does the backend ever need to proactively notify the frontend of a server-initiated session invalidation (e.g., an admin force-logout), or is cross-tab sync purely a frontend-owned, same-browser concern as this plan assumes?

**REAL TESTING**
21. Is there a backend-side way to create a disposable test session/account for real-backend E2E acceptance without going through the full register→verify email loop every time?

---

## Risk Register

| Risk | Impact | Mitigation | Owning task |
|---|---|---|---|
| Reading an httpOnly cookie from JS accidentally | Critical — defeats the entire security premise | §3's absolute rule; T11's explicit grep-based check | T11 |
| Auth source-of-truth duplication (AuthProvider vs. TanStack Query drifting) | High — inconsistent UI, hard-to-debug auth bugs | §9's explicit ownership split; `AuthProvider` derives, never duplicates | T04 |
| `/me`/FVS-006 cross-slice dependency | High — blocks real bootstrap correctness entirely | §1's four options, explicitly not silently resolved; T04 split into unblocked/blocked halves | T04 |
| Infinite refresh loop / refresh recursion | Critical — could hammer the backend or lock a user out | §6's exclusion-by-construction rule (login/logout/refresh never go through the wrapper); T06/T07's own recursion tests | T06, T07 |
| Concurrent refresh storm | High — redundant backend load, possible race conditions server-side | T06's single-flight design | T06 |
| Unsafe replay of write requests | High — potential duplicate side effects (double charges, double orders in later slices) | §11's GET-only-by-default scoping; explicit backend question #18 | T07 |
| CSRF contract mismatch | High — either broken mutations (missing token) or a false sense of security (wrong token) | §5/§8's total non-invention rule; T08 fully blocked | T08 |
| Open redirect via `returnTo` | High — classic phishing vector | §12's validator + exhaustive attack-string test matrix | T01 |
| Stale authenticated cache after logout | Medium — a logged-out user could still see cached personal data | §13's cache-clear convention | T09 |
| Protected-content flash before redirect | Medium — a split-second leak of UI structure (not data) to an anonymous user | §10/§11's loading-first rule | T05 |
| Cross-tab logout drift | Medium — one tab thinks it's logged in after another logs out | T10's `BroadcastChannel` mechanism | T10 |
| Token storage leakage (any form) | Critical | §3; no persistence code is ever written | All tasks touching `AuthProvider`/mutations |
| Login enumeration leakage (copy or timing) | High | §17 of FVS-002's own established pattern, reapplied; one generic failure copy regardless of cause | T03 |
| Attacker-useful lockout copy (exact remaining attempts, exact unlock time beyond `retryAfterSeconds`) | Medium | §18's rule — no countdown invented beyond confirmed `retryAfterSeconds` | T03 |
| Cookie/CORS misunderstanding (e.g., someone later adding `credentials:"include"` "just in case") | Medium — could introduce an unneeded cross-origin credentialed-request posture | §4's explicit documented reasoning, cited in T13's docs | T13 (documentation prevents recurrence) |
| Logout network-failure semantics decided silently | Medium — a real security/product tradeoff shipped without sign-off | T09's explicit non-silent decision point | T09 |
| Session-expired navigation loop | Medium — a failed refresh repeatedly re-triggering itself | Review Focus item 2; T04/T05 integration test | T04, T05 |
| React Strict Mode duplicate auth effects | Medium — a duplicate bootstrap/refresh call in dev | Same ref-guard pattern already proven in FVS-002 Batch 3 | T04 |
| Real-cookie E2E unavailable | Medium — blocks final sign-off, not implementation | T14 isolated, clearly marked pending | T14 |

## Definition of Done (FVS-003-specific)

**Functional:** login works against the assumed-then-confirmed contract; a returning session is recognized on page load once §1 resolves; protected routing gates correctly; silent refresh-on-401 works with retry-once semantics; a failed refresh forces re-login with a safe `returnTo`; logout works and propagates cross-tab; `returnTo` is validated against open redirects.

**Security:** httpOnly cookies never read or stored by JS (§3, verified by T11's grep); CSRF contract followed exactly once confirmed, never invented before then (§5/§8); no refresh recursion (T06/T07's tests); single-flight refresh proven under concurrency (T06); no unsafe write replay (§11); no open redirect (T01); enumeration-safe login (T03); sensitive cache cleared on logout (T09/§13).

**Accessibility:** FVS-002's form baseline reused; focus never silently lost on login-success redirect; session-expired messaging discoverable by assistive technology — all walked with real evidence in T11.

**Quality:** `lint`, `typecheck`, unit/integration tests, `test:e2e` (run twice), `build` all green at every task boundary, final full suite green at T12.

**Backend:** T14's real-cookie-session acceptance evidence (login/persist/refresh/logout) obtained, plus CSRF acceptance once T08 unblocks, before this slice is called fully done — matching FVS-001/002's own standing rule that real-backend verification is a genuine gate, not a formality.

## Non-Scope

Registration implementation (FVS-002, already done); email verification implementation (FVS-002, already done); password reset (FVS-004/VS-004); MFA (FVS-005); profile editing/any FVS-006 UI (explicitly — this plan does not build `/account` or any profile page, even though it discusses the `/me` endpoint's planning conflict); admin RBAC; authorization/permissions beyond authenticated-vs-anonymous; social login; remember-me (unless a future backend contract explicitly defines it); any browser-storage-based token persistence; a real identity-provider integration; cart; checkout; products; admin features. A logout *trigger button* placed in real site navigation is also out of scope here — `Header` has no nav items at all yet (confirmed, §0), and adding one is a later slice's job (likely FVS-006's `AccountLayout`) unless explicitly requested; this slice delivers the `logout()` mechanism and its effects, not a navigation UI for it.
