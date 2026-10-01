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

## 1. The /me / FVS-006 Conflict — RESOLVED at BATCH 3A

> **RESOLVED.** The backend team has confirmed `GET /api/v1/me` is implemented and is the approved FVS-003 bootstrap endpoint. This is **Option B** from the four options originally listed below (preserved for the historical record) — `/me` is explicitly pulled forward into FVS-003 as an approved, confirmed cross-slice dependency on VS-006's endpoint. **`FRONTEND-VERTICAL-SLICE-PLAN.md`'s dependency text has been corrected accordingly (see that file's own FVS-003 entry).** `POST /api/v1/auth/refresh` must **NOT** be used as a page-load probe (Option C, originally recommended, is explicitly rejected by the backend — see below) — refresh rotates the refresh cookie on every call, is rate-limited to 60/hour/IP, has no old-token grace period, and simultaneous old-token reuse across tabs can revoke the entire session, none of which is acceptable for a routine, unconditional page-load check.

**Approved bootstrap algorithm (backend-specified):**

1. Check whether a readable `csrf_token` cookie exists (pure client-side check, no network call).
2. If it does **not** exist: treat the user as anonymous immediately — **no network request is made at all.** (A user with no session never had a reason to have this cookie set.)
3. If it **does** exist: `GET /api/v1/me`.
4. `200` → authenticated; the response body is the canonical user shape (§ below).
5. `401` with problem `code: "AUTH_REQUIRED"` → perform **one** coordinated refresh (§7), then retry `/me` **exactly once**.
6. If the refresh fails, or the retried `/me` call is still `401 AUTH_REQUIRED` → anonymous / session expired. **Never retry `/me` indefinitely** — this is a bounded, at-most-two-calls sequence per bootstrap.

This closes the circular dependency the original four options were weighing: `/me` is now a real, confirmed, VS-003-scoped-for-frontend-purposes endpoint, and the `csrf_token`-cookie pre-check means an anonymous visitor's first page load costs zero network requests, not an unconditional `/me` call.

<details>
<summary>Original four options (historical record, superseded by the resolution above)</summary>

| Option | Description |
|---|---|
| A | VS-003 exposes some other current-session endpoint. |
| **B** | `GET /api/v1/me` pulled forward as an approved cross-slice dependency. **← This is what was approved.** |
| C | Boot-time `refresh` probe, no `/me` needed. **Explicitly rejected** — see above. |
| D | Bootstrap blocked until FVS-006 ships. **Moot** — resolved via B instead. |

</details>

---

## 2. Contract Confidence Table

> **Updated at BATCH 3A — the backend has answered the FVS-003 contract directly from the current backend implementation.** Rows below marked **CONFIRMED (BATCH 3A)** supersede their prior ASSUMED/NEEDS-CONFIRMATION status. Rows without that marker are unchanged from the original plan.

| # | Contract item | Status | Evidence / source | Frontend consequence |
|---|---|---|---|---|
| 1 | Endpoint paths (`login`, `logout`, `refresh`, `me`) | **CONFIRMED** | `vertical-slice-plan.md` VS-003; backend contract sync adds `GET /api/v1/me` (§1) | Mutations/queries can be built against exact paths now |
| 2 | Login request field names | **ASSUMED — not independently re-stated at BATCH 3A** | Still only `{ email, password }` by convention (matching registration); the BATCH 3A contract message describes login's cookie/CSRF behavior in detail but does not restate its literal JSON field names | T02 proceeds against `{ email, password }` per explicit instruction to unblock T02 — if the real backend ever rejects this shape, that is a fast, cheap correction during T02's own implementation, not a reason to have blocked the task further |
| 3 | Login password rules | **ASSUMED — none beyond "required"** | Unchanged | No login-specific complexity/length rule invented |
| 4 | Email format check | **ASSUMED — safe, non-authoritative** | Unchanged | Generic, non-authoritative check only |
| 5 | Login success HTTP status | **NEEDS BACKEND CONFIRMATION — still open** | Not restated at BATCH 3A | Treat any 2xx as success |
| 6 | Login success response body | **CONFIRMED (BATCH 3A) — no token body, ever** | "No token body is ever returned" (Cookie Model section) | Login's success handling reads **no** field from its own response body — the canonical "who am I" read is always the separate `GET /api/v1/me` call (§1), never the login response itself |
| 7 | Login failure HTTP status | **NEEDS BACKEND CONFIRMATION — still open** | Not restated | Generic `kind:"http"` 4xx handling applies |
| 8 | Invalid-credential error signal | **NEEDS BACKEND CONFIRMATION — still open** | Not restated | One generic "Invalid email or password." copy regardless |
| 9 | Locked/rate-limited signal | **NEEDS BACKEND CONFIRMATION — still open for login specifically** (refresh's own 429 is confirmed, row 20) | Not restated for login | No lockout countdown invented for login; reuses `ApiError.retryAfterSeconds` if present |
| 10 | Cookies set by login | **CONFIRMED (BATCH 3A)** | Cookie Model section | `access_token` (httpOnly, Path `/`, 15m), `refresh_token` (httpOnly, Path `/api/v1/auth`, 30d), `csrf_token` (JS-readable, Path `/`, 30d) |
| 11 | Cookie names | **CONFIRMED (BATCH 3A)** | Cookie Model section | `access_token`, `refresh_token`, `csrf_token` — only `csrf_token` is ever read by frontend code (§3) |
| 12 | Cookie `SameSite`/`Secure`/`Path` | **CONFIRMED (BATCH 3A)** | Cookie Model section | `csrf_token`: `SameSite=Lax`, `Path=/`. `Secure=true` outside development; non-`Secure` in local dev over HTTP. No frontend code depends on these values directly (the browser enforces them), but documented so a dev-environment surprise isn't mistaken for a frontend bug |
| 13 | Are both access + refresh cookies httpOnly | **CONFIRMED (BATCH 3A) — yes, both; `csrf_token` is the one exception** | Cookie Model section: "NEVER read access_token or refresh_token in JS. Only csrf_token may be read." | §3's absolute rule applies to `access_token`/`refresh_token` only; `csrf_token` is the sole cookie this slice's code ever reads, via `src/lib/auth/csrf.ts` (Part C) |
| 14 | Does the frontend ever receive a token body | **CONFIRMED (BATCH 3A) — no, never** | "No token body is ever returned" | Settled — no defensive code for a token-bearing body is needed anywhere |
| 15 | Refresh request body | **CONFIRMED (BATCH 3A) — none** | Refresh section: "No request body" | T06/T07 send no body |
| 16 | Refresh cookies used automatically | **CONFIRMED (BATCH 3A)** | "refresh_token HttpOnly cookie automatically attached by same-origin fetch" | No manual cookie handling; relies on fetch's same-origin default (§4, unchanged) |
| 17 | Refresh CSRF requirement | **CONFIRMED (BATCH 3A) — required** | "Also requires: X-CSRF-Token" | Refresh calls (Part D) always send `X-CSRF-Token` |
| 18 | Refresh success status/body | **CONFIRMED (BATCH 3A) — 204, empty** | Refresh section | T06/T07/Part D treat 204 as success, require no body |
| 19 | Refresh cookie rotation | **CONFIRMED (BATCH 3A)** | "Rotates: access_token, refresh_token. csrf_token stays same." | `csrf_token` is read fresh at send time regardless (§ CSRF below, never cached across a rotation) — harmless either way since it doesn't change, but the code makes no assumption that it won't |
| 20 | Refresh failure statuses | **CONFIRMED (BATCH 3A)** | Refresh section | `401 AUTH_REQUIRED` (covers missing/invalid/expired/unknown/revoked/expired-session/deactivated-owner/token-replay — all treated identically: session expired); `403 CSRF_INVALID` (bad/missing CSRF); `429 RATE_LIMITED` with `Retry-After` (60/hour/IP). **No automatic retry of refresh itself on any of these.** |
| 21 | Reuse-detected response | **CONFIRMED (BATCH 3A)** | "refresh-token replay" is explicitly one of the conditions folded into `401 AUTH_REQUIRED` | No distinct UX — identical to any other expired-session case, exactly as this plan's own §21 already assumed |
| 22 | Can refresh itself return 401/403 | **CONFIRMED (BATCH 3A)** | Refresh section (`401 AUTH_REQUIRED`, `403 CSRF_INVALID`) | T06/Part D treat any refresh failure as "could not refresh" — no recursive refresh-of-refresh (§6/§9, unchanged) |
| 23 | Does refresh response include user/session state | **CONFIRMED (BATCH 3A) — no** | "204 empty"; "No token body is ever returned" | `/me` remains the sole source of user/session data (§1) |
| 24 | Logout request shape | **CONFIRMED (BATCH 3A) — no body, per the existing Cookie/Refresh pattern** | Not explicitly restated for logout's body, but logout's CSRF/status are confirmed (rows 25/26) and no body is mentioned anywhere for it | T09 (Batch 3B) sends no body |
| 25 | Logout CSRF requirement | **CONFIRMED (BATCH 3A) — required** | "Required for: POST /api/v1/auth/logout" | T09 always sends `X-CSRF-Token` |
| 26 | Logout success status/body | **NEEDS BACKEND CONFIRMATION — still open (exact status not restated, though CSRF/path are confirmed)** | Not restated | T09 (Batch 3B) treats any 2xx as success until the exact code is confirmed |
| 27 | Logout cookie-clearing semantics | **ASSUMED — backend clears via Set-Cookie on response** | Unchanged | No frontend cookie-clearing code |
| 28 | Logout idempotency | **NEEDS BACKEND CONFIRMATION — still open** | Not restated | T09 (Batch 3B) does not assume either way |
| 29 | CSRF token delivery mechanism | **CONFIRMED (BATCH 3A)** | "Cookie: csrf_token ... JS-readable, not HttpOnly" | Part C reads it directly from `document.cookie` |
| 30 | CSRF header name | **CONFIRMED (BATCH 3A) — `X-CSRF-Token`** | CSRF section | Part C/apiClient attach exactly this header name |
| 31 | Which methods require CSRF | **CONFIRMED (BATCH 3A)** | CSRF section | Required for refresh, logout, and every authenticated POST/PUT/PATCH/DELETE. **Not** required for login, or for anonymous POSTs (register/verify-email/resend-verification/password-reset) |
| 32 | Does login require CSRF | **CONFIRMED (BATCH 3A) — no** | "Not required for: POST /api/v1/auth/login" | T02/T03 (Batch 3B) call login without `{csrf:true}` |
| 33 | Does refresh require CSRF | **CONFIRMED (BATCH 3A) — yes** | Row 17 | Part D always sets `{csrf:true}` |
| 34 | Does logout require CSRF | **CONFIRMED (BATCH 3A) — yes** | Row 25 | T09 (Batch 3B) always sets `{csrf:true}` |
| 35 | 401 refreshability — are auth endpoints themselves excluded | **CONFIRMED (BATCH 3A), matching this plan's own prior architecture decision** | "These endpoints themselves NEVER trigger refresh: login, logout, refresh, MFA endpoints, password-reset endpoints" | `login`/`logout`/`refresh`/MFA/password-reset are called directly through `apiClient`, never through the refresh-aware wrapper (Part E) — now a backend-confirmed requirement, not just a frontend preference |
| 36 | One-refresh-maximum / concurrent 401 behavior (same-tab) | **CONFIRMED (BATCH 3A) as a backend requirement too, matching this plan's own single-flight design** | §7/§10 below; "No second refresh if the retried request also fails" | Part D/E implement exactly one same-tab in-flight refresh via the existing generic `createSingleFlight` |
| 36b | Cross-tab refresh mutual exclusion | **CONFIRMED (BATCH 3A) — new requirement, backend-mandated** | "Backend explicitly requires avoiding simultaneous refresh-token rotations across tabs... Use a named Web Lock for refresh" | `BroadcastChannel` alone is **not** sufficient for this; Part D adds a named `navigator.locks` Web Lock specifically for refresh mutual exclusion, layered on top of (not replacing) the same-tab single-flight primitive — see §7's rewritten design below |
| 37 | Request-replay safety for writes after refresh | **CONFIRMED (BATCH 3A) — approved** | "Backend confirms authenticated write endpoints perform authentication before business side effects. Therefore replaying an authenticated write after a successful refresh is approved." | §8 below is rewritten: Part E's `authenticatedRequest` wrapper may now retry **both reads and writes** once after a successful refresh — the prior GET-only-by-default conservative scoping is lifted, backed by this explicit confirmation, not assumed |
| 38 | Cross-tab logout propagation contract | **ARCHITECTURE DECISION — frontend-owned, `BroadcastChannel`** (unchanged; distinct from row 36b's refresh-specific Web Lock requirement) | §20; BATCH 3A confirms `BroadcastChannel` remains the right mechanism for the logout *signal* itself — only refresh *mutual exclusion* additionally needs Web Locks | No backend contribution for logout propagation; purely frontend, same-browser |
| 39 | Return-to query parameter name | **ARCHITECTURE DECISION — `returnTo`, this plan's own design** | Unchanged | Settled |
| 40 | Correlation/request-ID header | **NEEDS BACKEND CONFIRMATION — still open, genuinely unrelated to this contract sync** | `src/lib/api/ApiError.ts` inline comment | Unchanged; never populated |
| 41 | `/me` bootstrap endpoint and algorithm | **CONFIRMED (BATCH 3A) — new row** | §1 above | `GET /api/v1/me`; 200 body `{id,email,role,email_verified,email_verified_at,created_at}`; 401 `AUTH_REQUIRED` on anonymous/expired access token; no rate limit; account-active state rechecked server-side on every call |
| 42 | RFC 9457 problem `code` field | **CONFIRMED (BATCH 3A) — new row** | Every failure mode in this contract sync is identified by a top-level string `code` (`AUTH_REQUIRED`, `MFA_REQUIRED`, `CSRF_INVALID`, `RATE_LIMITED`) | `ApiError` gains a normalized `code?: string` field (Part B) — production auth logic branches on `status`+`code`, never on raw body inspection |

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

## 5. CSRF — CONFIRMED at BATCH 3A

Per rows 29–34 of §2, the CSRF mechanism is now fully confirmed:

- **Cookie:** `csrf_token` — JS-readable (not httpOnly), `SameSite=Lax`, `Path=/`, stable for the entire session (does **not** rotate on refresh).
- **Header:** `X-CSRF-Token`, set to the cookie's current value.
- **Required for:** `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, and every authenticated `POST`/`PUT`/`PATCH`/`DELETE`.
- **Not required for:** `POST /api/v1/auth/login`, and anonymous POSTs (register/verify-email/resend-verification/password-reset — all FVS-002 territory, unaffected).
- **Read the cookie value at send time, every time** — never cached in React/module state across requests, since (though it happens to stay stable across a refresh per the contract) nothing in this architecture should depend on that stability to be correct.

**Implementation (Part C of BATCH 3A):** `src/lib/auth/csrf.ts` exports a small, pure cookie-reading helper (`readCookie(cookieString, name)` for testability + `readCsrfToken()` wrapping it against the real `document.cookie`). `apiClient.post` gains an explicit opt-in `{ csrf: true }` option (not a blanket auto-attach — login/register/verify/resend never pass it) that reads the cookie at send time and sets `X-CSRF-Token`, failing locally with a safe normalized `ApiError` (never inventing a fake token) if the cookie is unexpectedly missing when required.

---

## 6. apiClient 401 / Refresh Architecture — CONFIRMED precision at BATCH 3A

**Ownership split (unchanged from the original plan, now backend-confirmed as the correct shape too — §2 row 35):**

| Layer | Owns | Does NOT own |
|---|---|---|
| **Transport** (`apiClient`, extended only with the `{csrf:true}` opt-in from §5 — otherwise unchanged) | Detecting and normalizing a 401 into `ApiError { kind:"http", status:401, code: "AUTH_REQUIRED" }` | Refresh, retry, redirect, any auth business logic |
| **Auth/session coordinator** (`src/lib/auth/refreshSession.ts` + `src/lib/auth/authenticatedRequest.ts`) | The refresh-on-401-then-retry-once dance; same-tab single-flight (§7) **and** cross-tab Web Lock mutual exclusion (§7); deciding which requests are safe to retry (§8 — now broader than originally scoped) | Routing/navigation; never imports `next/navigation` |
| **Routing / `AuthProvider`/`ProtectedRoute`** | Reacting to "session is now anonymous" by navigating to `/login?returnTo=...` | Any HTTP call of its own beyond `AuthProvider`'s own `/me` session query |

**The refreshability rule is now precise, not just "a 401":**

> Only `HTTP 401` **with problem `code: "AUTH_REQUIRED"`** is refreshable. `401 MFA_REQUIRED` is a different, non-refreshable signal (surfaced to the caller unchanged — MFA UI is out of scope for this slice entirely). Every other failure — `403`, `404`, network, timeout, `500`, any other code — never triggers a refresh attempt either.

**Exclusions (non-negotiable, now also a backend-confirmed requirement — §2 row 35 — not just this plan's own preference):**

- `login`, `logout`, `refresh`, MFA endpoints, and password-reset endpoints are **always** called directly through `apiClient`, **never** through the refresh-aware wrapper (`authenticatedRequest`). Enforced by construction (the wrapper is simply never imported into those call sites), not a runtime path blacklist.
- The refresh mechanism never auto-retries a request to `/api/v1/auth/*` itself.
- Only ONE retry is ever attempted per original request — if the retried request also comes back `401 AUTH_REQUIRED`, that is surfaced as a final failure (triggering the expired-session transition), **never** a second refresh attempt.

---

## 7. Refresh Coordination — Same-Tab Single-Flight + Cross-Tab Web Lock (CONFIRMED design at BATCH 3A)

**Same-tab (unchanged — Task T06's generic primitive, already built):**

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

This primitive is reused unmodified — its generic design (no knowledge of refresh/cookies/CSRF) is exactly why it didn't need to change when the real contract landed.

**Cross-tab (new, backend-mandated — §2 row 36b):** `BroadcastChannel` (used for the logout *signal*, §20) is explicitly **not sufficient** for refresh mutual exclusion — the backend requires that two tabs never rotate the refresh cookie simultaneously, since `refresh_token` reuse detection could revoke the whole session if two tabs raced each other. The approved mechanism is the native **Web Locks API** (`navigator.locks`), with one named lock reserved for refresh:

```ts
async function coordinatedRefresh(refreshOnce: () => Promise<void>): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.locks) {
    // Environments without Web Locks fall back to same-tab-only protection
    // (createSingleFlight still applies) — not a silent correctness gap,
    // just a graceful reduction to single-tab-strength guarantees, which
    // this plan accepts as a documented limitation rather than inventing a
    // second cross-tab mechanism (§17's "smallest standards-based
    // mechanism" rule) for a browser outside the assumed support floor.
    return refreshOnce().then(() => true, () => false);
  }

  return navigator.locks.request("bekaa3d-refresh", async () => {
    // Re-check session state INSIDE the lock before refreshing — if another
    // tab already refreshed while this tab was waiting for the lock, a
    // fresh /me probe may already show "authenticated" again, in which case
    // this tab must NOT also refresh (that would be the exact "sequential
    // duplicate refresh" the backend asked to avoid).
    const alreadyValid = await recheckSession();
    if (alreadyValid) {
      return true;
    }
    return refreshOnce().then(() => true, () => false);
  });
}
```

The exact shape of `recheckSession()` (likely a direct, unwrapped `GET /api/v1/me` call — never through `authenticatedRequest`, to avoid any risk of recursive lock acquisition) is Part D's own implementation decision, built and tested against the confirmed `/me` contract (§1). **No package is added** — `navigator.locks` is a native browser API already available in this project's target browser (system Edge, used throughout this engagement's own Playwright infrastructure, supports Web Locks).

**Combined algorithm (same-tab + cross-tab):** a same-tab 401 first goes through `createSingleFlight` (deduplicating concurrent requests *within* this tab, instant, no lock overhead for the common case); the single-flight's own wrapped function is what acquires the cross-tab Web Lock before actually calling `POST /refresh`. This layers the two mechanisms rather than replacing one with the other — same-tab dedup stays cheap and synchronous-feeling, cross-tab exclusion only engages at the point a real network call is about to happen.

---

## 8. Request Replay Safety — CONFIRMED SAFE at BATCH 3A (prior conservative scoping lifted)

The backend has explicitly confirmed (§2 row 37): *"authenticated write endpoints perform authentication before business side effects... replaying an authenticated write after a successful refresh is approved."* This resolves what was previously an open security question, not resolved by this plan's own guess.

**Current rule (replacing the original GET-only-by-default scoping):**

- A request wrapped by `authenticatedRequest` (Part E) — **read or write** — that fails with `401 AUTH_REQUIRED` triggers exactly one coordinated refresh (§7), then is retried **exactly once**, regardless of HTTP method.
- If the retried request also comes back `401 AUTH_REQUIRED`, it is surfaced as a final failure — **no second refresh is attempted.**
- Every other failure (`401 MFA_REQUIRED`, `403`, `404`, network, timeout, `500`, anything else) passes through `authenticatedRequest` completely unchanged — no refresh is ever attempted for these.
- Malformed JSON in a request body can fail before the backend even reaches its own auth check, but that failure path is not a `401 AUTH_REQUIRED` and therefore never engages the refresh/replay mechanism at all — it's an ordinary request failure.

This lets FVS-003 ship a real, useful 401→refresh→retry-once mechanism for both reads and writes, backed by an explicit backend guarantee rather than an assumption.

---

## 9. Auth Context (`AuthProvider`) — bootstrap half now CONFIRMED and implementable

**Public interface, BATCH 3A Part F scope (deliberately minimal — `logout` deferred to Batch 3B, since wiring it requires T09, which isn't built yet; fabricating a placeholder `logout` now was considered and rejected — see Part F's own task definition):**

```ts
interface AuthContextValue {
  user: SafeUser | null;       // non-secret metadata only, or null if anonymous/unknown
  isAuthenticated: boolean;
  isLoading: boolean;          // true only during the very first bootstrap check
}
```

`SafeUser` is now a real, confirmed shape (§1 row 41, §2 row 41): `{ id: string; email: string; role: string; emailVerified: boolean; emailVerifiedAt: string | null; createdAt: string }` (camelCased at the boundary; the raw `/me` response uses snake_case — this is this task's own, ordinary mapping, not a contract invention).

No `refreshSession()` exposed publicly — refresh is reactive (driven by `401 AUTH_REQUIRED` via Part E's wrapper, and by the bootstrap query's own internal retry-once) and the coordinated refresh mechanism (§7) already prevents any need for a caller to manually trigger it.

**Ownership split (unchanged rule, now backed by a real queryFn):**

- **TanStack Query** owns the actual server-derived session data — one query, key `["auth", "session"]`, `staleTime: Infinity`, `retry: false` (the query's own internal AUTH_REQUIRED→refresh→retry-once sequence, §1, is not TanStack's own retry mechanism — it's bounded application logic inside the `queryFn` itself, which then resolves or rejects exactly once).
- **`AuthProvider`** is a thin context wrapper around that one query — it derives `isAuthenticated`/`isLoading`/`user` from the query's own `status`/`data`, and never maintains a second, independently-settable piece of state that could drift from the query.

---

## 10. Auth Bootstrap (page-load behavior) — CONFIRMED algorithm at BATCH 3A

The backend-approved bootstrap algorithm (§1) is now the real `queryFn`:

1. Check for a readable `csrf_token` cookie (via `src/lib/auth/csrf.ts`, Part C). **Absent → resolve anonymous immediately, zero network requests.**
2. Present → `GET /api/v1/me` (direct `apiClient.get`, never through `authenticatedRequest` — this IS the bootstrap check, not a request that should itself trigger the generic 401-refresh wrapper's own logic a second time).
3. `200` → authenticated, map the body to `SafeUser`.
4. `401 AUTH_REQUIRED` → perform one coordinated refresh (§7's `coordinatedRefresh`, same mechanism Part E's wrapper uses, not a separate one), then retry `/me` **exactly once**.
5. Refresh fails, or the retried `/me` is still `401 AUTH_REQUIRED` → anonymous. **Never retry further** — this is a bounded, at-most-two-`/me`-calls sequence.
6. Any other unexpected failure (network, timeout, `500`, a `401` with a different/missing code) → resolve anonymous as the safe default, **never** a false "authenticated." (The query's error state is still distinguishable from its success state internally, so a future task could add a distinct "bootstrap failed, unknown" UI if ever needed — not built speculatively now.)

Three states only, matching `isLoading`/`isAuthenticated`:

| State | `isLoading` | `isAuthenticated` | UI |
|---|---|---|---|
| Unknown (bootstrap in flight) | `true` | — (ignored) | `LoadingSpinner`, nothing else rendered yet |
| Authenticated | `false` | `true` | Real content |
| Anonymous | `false` | `false` | `ProtectedRoute` (Batch 3B) redirects; public pages render normally |

**No protected content is ever rendered before the bootstrap check resolves.** No `localStorage`-based "optimistic" authenticated flash is used to fake instant persistence — there is no non-secret way to know "probably still logged in" without asking the server, and now there's a cheap, zero-network way to know "definitely anonymous" (the `csrf_token` pre-check) instead.

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

## Task Status Classification (re-corrected at BATCH 3A — backend contract now confirmed)

> **History:** first corrected after the initial planning review (T02/T09 had been wrongly marked buildable against assumed fields; T06/T10 were split into generic-primitive/wiring halves). **Now updated again at BATCH 3A**, where the backend answered essentially the entire remaining contract (session bootstrap, CSRF, refresh, cookies, 401 refreshability, replay safety) in one pass. Only three real gaps remain: login's exact success/failure HTTP status and its invalid-credential signal (§2 rows 5/7/8/9), and logout's exact success status/idempotency (§2 rows 26/28) — neither blocks starting the respective task, since both degrade gracefully to "treat any 2xx as success, any non-2xx as generic failure," which this plan already does elsewhere (e.g. registration, FVS-002).

| Task | Classification at BATCH 3A | Why |
|---|---|---|
| T01 `returnTo` validator | **DONE** (Safe Batch 1) | — |
| T02 Login mutation | **UNBLOCKED** | Cookies/CSRF-exemption/response-body-shape (no token body, ever) are all confirmed (§2 rows 6/10/32). Exact login field names remain ASSUMED `{email,password}` (row 2) — not independently re-stated at BATCH 3A, but this is explicitly accepted as a fast-to-correct-if-wrong risk, not a blocker, per direct instruction. **Deferred to Batch 3B**, not built in BATCH 3A. |
| T03 Login page | **UNBLOCKED** | Depends only on T02. **Deferred to Batch 3B.** |
| T04 AuthProvider | **UNBLOCKED** | The §1 bootstrap conflict is resolved (`/me` approved). **Built in BATCH 3A, Part F** (bootstrap query + provider shell; `logout` deferred to Batch 3B per Part F's own non-fabrication rule). |
| T05 ProtectedRoute | **UNBLOCKED** | T04 (its real dependency) is now unblocked. **Deferred to Batch 3B** — BATCH 3A explicitly excludes it. |
| T06 Single-flight coordinator | **DONE** (Safe Batch 2) | — |
| T07 401 integration wrapper | **UNBLOCKED** | Refreshability (`401 AUTH_REQUIRED` only), exclusions, and replay safety are all confirmed (§2 rows 35/37). **Built in BATCH 3A, Part E.** |
| T08 CSRF plumbing | **UNBLOCKED** | Fully confirmed (§2 rows 29–34). **Built in BATCH 3A, Part C**, as `src/lib/auth/csrf.ts` + an `apiClient.post` opt-in — the task survives under a more precise name but the same ID. |
| T09 Logout | **UNBLOCKED** | CSRF requirement confirmed (row 25); exact success status (row 26) and idempotency (row 28) remain open but non-blocking (treat any 2xx as success, never call it twice). **Deferred to Batch 3B** — BATCH 3A explicitly excludes it. |
| T10 Cross-tab logout | **DONE** (Safe Batch 2, signal primitive only) | Wiring into `useLogout`'s success handler remains deferred until T09 lands (Batch 3B). |
| T11 Integration/security pass | **Pending — transitively blocked on Batch 3B** | Depends on T02/T03/T05/T09 (all deferred to Batch 3B) being real. |
| T12 E2E | **Pending — transitively blocked** | Depends on T11. |
| T13 Docs | **Pending — transitively blocked** | Depends on T12 (can draft early). |
| T14 Real-backend/CSRF acceptance | **BLOCKED ON BACKEND AVAILABILITY** | Contract is now fully confirmed; the only remaining blocker is a real backend to run against. |

---

## Task Dependency Graph (re-corrected at BATCH 3A)

```
T01 (DONE) ── T06 (DONE) ── T10 signal (DONE)

T02 (UNBLOCKED, login mutation) ── T03 (UNBLOCKED, login page)        [Batch 3B]

T04 (UNBLOCKED, AuthProvider — BUILT at BATCH 3A Part F) ── T05 (UNBLOCKED, ProtectedRoute)   [T05: Batch 3B]
                                                          └── T09 (UNBLOCKED, logout) ── [wires T10's primitive in]   [T09: Batch 3B]

T06 ── T07 (UNBLOCKED, 401 wrapper — BUILT at BATCH 3A Part E, wired to T06 + the new Web-Lock-aware refresh coordinator)

T08 (UNBLOCKED, CSRF — BUILT at BATCH 3A Part C)

{T01..T10 all real} ── T11 (integration/a11y/security pass) ── T12 (E2E) ── T13 (docs) ── T14 (real-backend acceptance)
```

- **Built at BATCH 3A:** T04 (Part F, logout deferred), T07 (Part E), T08 (Part C), plus the new `refreshSession`/`coordinatedRefresh` module (Part D) and the `ApiError.code` normalization (Part B) that both T04 and T07 depend on.
- **Deferred to Batch 3B:** T02, T03, T05 (real integration — its own unit tests already exist against a mock), T09, T10's logout-wiring.
- **T11** still depends on T02/T03/T05/T09 landing — **not** schedulable yet. **T12** depends on T11. **T13** can draft early. **T14** depends on T12 and real backend availability only now (contract itself is no longer the blocker).

**Critical path (re-corrected):** Batch 3B (T02/T03/T05/T09) → T11 → T12 → T13/T14. The backend-contract gate that dominated the previous critical path is now closed.

---

## Optimized Implementation Batches (re-corrected at BATCH 3A)

| Batch | Contents | Status |
|---|---|---|
| Safe Batch 1 | T01 | **DONE** |
| Safe Batch 2 | T06, T10 (signal primitive) | **DONE** |
| **BATCH 3A** | Part A (this sync) · Part B (`ApiError.code`) · Part C (CSRF, T08) · Part D (`refreshSession`/Web-Lock coordinator) · Part E (`authenticatedRequest`, T07) · Part F (`AuthProvider`/bootstrap query, T04 minus `logout`) | **This batch** |
| **Batch 3B (next)** | T02 (login mutation), T03 (login page), T05 (ProtectedRoute real wiring), T09 (logout — also completes T04's `logout` field and T10's wiring) | Gate: none remaining beyond normal execution — fully unblocked |
| **Batch 4** | T11, T12, T13 | Gate: Batch 3B lands |
| **Real backend acceptance (separate, final gate)** | T14 | Gate: real backend reachable |

---

## TDD Map

| Task | TDD status |
|---|---|
| T01 | TDD REQUIRED — **DONE** (pure function, exhaustive attack-string matrix) |
| T02 | TDD REQUIRED — unblocked, deferred to Batch 3B |
| T03 | TDD REQUIRED — unblocked, deferred to Batch 3B |
| T04 | TDD REQUIRED — **DONE at BATCH 3A** (minus `logout`, deferred to Batch 3B) |
| T05 | TDD REQUIRED — unblocked, deferred to Batch 3B |
| T06 | TDD REQUIRED — **DONE** (generic primitive, highest-value isolated security module) |
| T07 | TDD REQUIRED — **DONE at BATCH 3A** |
| T08 | TDD REQUIRED — **DONE at BATCH 3A** (as `src/lib/auth/csrf.ts` + the `apiClient` opt-in) |
| T09 | TDD REQUIRED — unblocked, deferred to Batch 3B |
| T10 | TDD REQUIRED — **DONE** (signal primitive; logout-wiring deferred to Batch 3B) |
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

**Status:** **UNBLOCKED at BATCH 3A** (re-corrected — see the Task Status Classification table above). Cookies/CSRF-exemption/no-token-body are confirmed; only the literal `{email,password}` field spelling remains ASSUMED-by-convention (§2 row 2). **Deferred to Batch 3B** — not implemented in BATCH 3A, which built the surrounding infrastructure (CSRF, refresh, bootstrap) this task will plug into.
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

**Status:** **UNBLOCKED at BATCH 3A**, same as T02 (see the Task Status Classification table above). **Deferred to Batch 3B.**
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

**Status:** **UNBLOCKED and BUILT at BATCH 3A, Part F** — §1's bootstrap conflict is resolved (`/me` approved as the canonical source). `AuthProvider`/the `["auth","session"]` query are real, committed code (`src/lib/auth/AuthProvider.tsx`, `useAuthSession.ts`). **The `logout` field is deliberately NOT included yet** — wiring it requires T09 (deferred to Batch 3B); shipping a fabricated placeholder was considered and rejected (§9).
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

**Status:** **UNBLOCKED at BATCH 3A** — T04 (its real dependency) is now built. **Deferred to Batch 3B**, not implemented in BATCH 3A.
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

**Status:** **DONE** (Safe Batch 2 — `src/lib/auth/singleFlight.ts`). Wiring it to the real refresh call is Part D of BATCH 3A, via `src/lib/auth/refreshSession.ts` (see §7).
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

**Status:** **UNBLOCKED and BUILT at BATCH 3A, Part E** — refreshability (`401 AUTH_REQUIRED` only) and replay safety (reads and writes both approved for one retry) are confirmed (§2 rows 35/37). Real code: `src/lib/auth/authenticatedRequest.ts`.
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

**Status:** **UNBLOCKED and BUILT at BATCH 3A, Part C** — CSRF is now fully confirmed (§2 rows 29–34, §5). Real code: `src/lib/auth/csrf.ts` plus an `apiClient.post(..., { csrf: true })` opt-in (no interceptor framework added).
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

**Status:** **UNBLOCKED at BATCH 3A** — CSRF requirement confirmed (row 25); exact success status (row 26) and idempotency (row 28) remain open but non-blocking. **Deferred to Batch 3B**, not implemented in BATCH 3A.
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

**Status:** **DONE** (Safe Batch 2 — `src/lib/auth/crossTabSignal.ts`, signal primitive only). Wiring into `useLogout`'s success handler is deferred to Batch 3B's T09.
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
| `/me`/FVS-006 cross-slice dependency | High — blocked real bootstrap correctness | **RESOLVED at BATCH 3A** — `/me` approved, built in Part F | T04 |
| Infinite refresh loop / refresh recursion | Critical — could hammer the backend or lock a user out | §6's exclusion-by-construction rule (login/logout/refresh never go through the wrapper); Part D/E's own recursion tests | Part D, Part E |
| Same-tab concurrent refresh storm | High — redundant backend load, possible race conditions server-side | T06's single-flight design, reused unmodified in Part D | Part D |
| **Cross-tab refresh race (new at BATCH 3A)** | High — backend-confirmed risk: simultaneous refresh-token rotation across tabs can revoke the entire session via reuse detection | §7's Web Lock (`navigator.locks`) mutual exclusion, with an in-lock session re-check before rotating; tested with an explicit lock test-double | Part D |
| Unsafe replay of write requests | **RESOLVED at BATCH 3A** — backend confirmed authenticated writes authenticate before their side effect; replay-after-refresh approved | §8, rewritten; Part E retries both reads and writes once | Part E |
| CSRF contract mismatch | **RESOLVED at BATCH 3A** — cookie name, header name, and exemptions all confirmed | §5, rewritten; built in Part C | Part C |
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
