# FVS-002 — Registration & Email Verification — Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans`-style discipline: one task at a time, RED/GREEN where marked, full verification before every commit, one local commit per task, STOP and report after each task — never auto-continue. This mirrors the exact workflow FVS-001 used successfully.

**Goal:** A visitor can register, receive enumeration-safe "check your email" messaging, verify via emailed link, see success/failure, and resend the verification email with correct cooldown handling — with no auto-login and no new auth/session architecture.

**Architecture:** Reuse every FVS-001 foundation as-is (apiClient, ApiError, QueryProvider, AppLayout, Toast, LoadingSpinner, routing/error conventions). Add exactly what this slice needs and nothing else: `apiClient.post`, React Hook Form + Zod, five base form primitives (`Form`, `TextField`, `PasswordField`, `Button`, `Alert`), three routes, three mutations.

**Tech Stack:** Next.js App Router (existing), TanStack Query v5 (existing), React Hook Form + Zod + `@hookform/resolvers` (new — versions current at planning time: `react-hook-form@^7.89.0`, `zod@^4.6.5`, `@hookform/resolvers@^5.9.1`; not pinned exactly, resolve current compatible versions at implementation time per FVS-001's own convention).

**Spec:** `FRONTEND-VERTICAL-SLICE-PLAN.md` §5 "FVS-002 — Registration & Email Verification" (lines 79–100) and `vertical-slice-plan.md` §"VS-002" (lines 63–78) are the governing specs. This plan argues from both; task executors should read this plan first, falling back to those sources only for wording this plan quotes.

## 0. Repository / FVS-001 Foundation State (read before starting any task)

Verified directly against the repository, not assumed:

- FVS-001 is implemented through **FVS001-T17 plus the T15 focus-ring closure fix** (commit `54862f8` at planning time). `docs/frontend-setup.md` is the canonical setup/architecture doc.
- **FVS-001's own real-backend verification is still PENDING** (`npm run test:e2e` with a real backend up, and `npm run test:e2e:backend`, both recorded PENDING — no real VS-001 backend has been reachable in this environment at any point in this engagement). **FVS-002 planning is not blocked by this** (per this task's own instruction), but no FVS-002 task may claim FVS-001's frontend dependency is "fully proven against a real backend" — only that its code/tests/local-proxy-wiring are complete. The real-backend gap carries forward into FVS-002's own real-backend acceptance task (§25 below), which needs the same currently-unavailable backend.
- `src/lib/api/apiClient.ts` exposes **`get()` only** — no `post()`. Confirmed by direct read. FVS-002 is the first write flow; extending apiClient is mandatory, in its own task (§10below), not bypassed.
- `package.json` has **no** `react-hook-form`, `zod`, or `@hookform/resolvers`. Confirmed by direct read.
- No `src/components/forms/` (or similar) directory exists yet. No `/register`, `/verify-email`, `/verify-email/resend` routes exist yet.
- `bekaa3d-commerce-ux` (project skill) does **not** apply to this slice — it governs cart/checkout/STL/offers/order-state UX, none of which exists in a registration/email-verification flow. Not included in this plan's skill map.

## 1. Contract Confidence Table

**Updated at FVS-002 BATCH 2 (Contract Sync)** — the backend has confirmed the majority of rows below. Evidence source for every newly-confirmed row is the backend's own `docs/frontend-contract-vs002.md` as relayed in the BATCH 2 contract-sync instruction; that document is not itself present in this frontend execution context, so this table records the confirmed facts, not a copy of that file. **Two items remain genuinely unresolved and must not be guessed: the RFC 9457 `errors[]` field-level validation shape (row 7) and the Turnstile captcha contract (row 18).**

| # | Contract item | Status | Evidence / source | Frontend consequence |
|---|---|---|---|---|
| 1 | Endpoint paths (`register`, `verify-email`, `resend-verification`) | **CONFIRMED** | `vertical-slice-plan.md` VS-002 line 75; backend contract sync | Mutations/routes can be built against exact paths now. **Also confirmed: the backend's own path already includes `/api`** — `/api/v1/auth/register` etc. — unlike the health endpoints, whose backend path has no `/api` prefix. This is a proxy-configuration fact, not a mutation-code change (§5, and FVS-002 BATCH 2 Part B) |
| 2 | Registration request field names | **CONFIRMED** | Backend contract sync | Request body is exactly `{ "email": string, "password": string }` — no other fields (§9, §21) |
| 3 | Password validation rules (length/complexity) | **CONFIRMED** | Backend contract sync | Minimum 8, maximum 256 **Unicode code points** (counted via `[...password].length`, never `.length`, which counts UTF-16 code units); **no complexity rule** (no uppercase/lowercase/digit/symbol requirement); values are **not trimmed** before submission; control characters are rejected client-side (§8, §9, §21) |
| 4 | Email format check | **ASSUMED — safe, non-authoritative** | Standard web input hygiene, not a backend business rule; `bekaa3d-api-contract`'s own principle ("frontend validation is UX only, never authoritative") | A generic "looks like an email" client check is permitted — it cannot be stricter than any real backend rule and never blocks a request the server would accept. Email is **not trimmed/normalized** before submission (unchanged assumption) |
| 5 | Registration success HTTP status | **CONFIRMED** | Backend contract sync | Success is **HTTP 202** specifically (not just "any 2xx") |
| 6 | Registration success response shape (`RegistrationAccepted`) | **CONFIRMED** | Backend contract sync | Body is `{ "message": string }`. Frontend still reads **no** field from it — success is the HTTP 202 outcome alone, matching `useReadiness`'s existing pattern; the backend's own message text is never rendered (enumeration-safety and safe-message rules both forbid it) |
| 7 | RFC 9457 validation-error (`errors[]`) extension shape | **NEEDS BACKEND CONFIRMATION — still open** | `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 ("RFC 9457 problem-response validation-error shape"); the backend's own `docs/frontend-contract-vs002.md` reportedly has a concrete example, but it is **not available in this frontend execution context** | No per-field server-error mapping is built; server validation failures surface only via the existing generic `ApiError.message`/`Alert` path until this is actually confirmed in a context this frontend work can read |
| 8 | Verify-email token transport | **CONFIRMED** | Backend contract sync | The email link format is `{FRONTEND_BASE_URL}/verify-email#token=...` — the token travels in the **URL fragment**, not a query string, and must be read from `location.hash` (never `useSearchParams`, which cannot see a fragment). POST body field is `token` (string). Token length is exactly 43 characters. This corrects the prior "query param" assumption everywhere it appeared (§9, §13, §21 task definition) |
| 9 | Invalid / expired / used token distinction | **CONFIRMED** | Backend contract sync | Invalid token → HTTP 400, code `INVALID_TOKEN`. Used token → HTTP 400, code `INVALID_TOKEN` (same code as invalid — no distinct signal). Expired token → HTTP 410, code `RESOURCE_EXPIRED` (genuinely distinct from the other two). UI implements exactly two failure states, not three: a generic "invalid" state (400) and an "expired" state (410) with different copy (§13, §21) |
| 10 | Already-verified idempotent re-click behavior | **CONFIRMED** | Backend contract sync | Backend returns HTTP 400 `INVALID_TOKEN` for this case too — **explicitly not** a separate already-verified success state. The existing generic-failure (400) state already handles it correctly with no special-casing (§13, §22) |
| 11 | Resend request field name(s) | **CONFIRMED** | Backend contract sync | Request body is exactly `{ "email": string }` (§9, §24) |
| 12 | Resend enumeration-safe behavior | **CONFIRMED** (behavior and outcome) | `vertical-slice-plan.md` VS-002 line 74; backend contract sync | Success is HTTP 202, identical regardless of whether the account exists. During an active cooldown the backend **still returns 202** — it simply doesn't send another email — so the frontend must never infer "no cooldown is active" from a 202 alone; cooldown state is tracked client-side from the timestamp of the frontend's own last successful resend (§6, §24) |
| 13 | Rate-limit HTTP status (429 or otherwise) | **CONFIRMED** | Backend contract sync | HTTP 429, with a `Retry-After` header in whole seconds. Fixed one-hour per-IP windows: register = 5, resend = 5, verify = 20. Failed backend validation **also counts** toward these limits, so client-side validation must catch every confirmed rule before sending, to avoid wasting rate-limit budget (§9, §21, §24) |
| 14 | Cooldown duration source (`Retry-After` header / response field / fixed value) | **CONFIRMED** | Backend contract sync | Fixed value: **120 seconds** per account after a successful resend 202 — not derived from a header or response field. Countdown task (§10, §11, §24) is no longer contract-gated on the duration itself; it is gated only on the resend field name (row 11, now confirmed) and can proceed |
| 15 | Auto-login after registration | **CONFIRMED — no** | `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 ("Does registration (VS-002) log the user in?"); backend contract sync | Registration does **not** log the user in, creates no frontend auth state, and sets no auth cookies — explicitly confirmed, not merely an assumption anymore (§3, §7) |
| 16 | Correlation/request-ID header | **NEEDS BACKEND CONFIRMATION** — already logged, inherited from FVS-001, unaffected by this sync | `src/lib/api/ApiError.ts` inline comment | Unchanged from FVS-001; never populated |
| 17 | Local dev email-adapter test mechanism (for real-backend acceptance) | **PARTIALLY CONFIRMED** | Backend contract sync | A manual mechanism exists **now**: stop the worker and inspect `email_outbox` directly via SQL. A file-based dev/test email provider is being built but is **not ready yet**. This resolves enough of row 17 to describe Task T14's manual procedure, but **T14 itself remains explicitly deferred** — not attempted in this batch or until a real backend is reachable (§0, §16, §25) |
| 18 | Captcha (Cloudflare Turnstile) contract | **NEEDS BACKEND CONFIRMATION — still open, new row** | Backend contract sync: Turnstile will be added later to registration and resend; exact field name/contract not yet confirmed | Do **not** install Turnstile, render a fake captcha widget, add a captcha request field, or create a dummy token anywhere in this slice. Registration/resend code must stay composable enough that a future field/widget can be added without a rewrite — no extra abstraction beyond that (§8 note, §21) |

**Gap-list disposition:** rows 7 and 18 remain genuinely open and must stay listed in `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 (row 18 is a new gap not previously logged there — see the §17 update below). Rows 2, 3, 8, 9, 10, 11, 13, 14 — previously flagged as gaps this plan surfaced beyond §17 — are now resolved by this sync and require no further gap-list entry.

## 2. Enumeration Safety (non-negotiable, applies to every task touching register/resend copy)

The frontend must never branch wording on whether an account exists. Approved conceptual copy (exact strings are this task's own responsibility to finalize with product, not this plan's job to invent further than the plan documents already state):

- Registration success: a "check your email" message — never "email already registered" or equivalent.
- Resend: "If an account exists for that email, a verification email was sent." — identical wording regardless of the real outcome.

**Every task that renders register/resend success copy must include a test asserting the UI cannot distinguish the two cases** (e.g., a test that mocks both a "new account" and a "duplicate email" server response behind the *same* 2xx/enumeration-safe contract and asserts identical rendered copy). This is called out explicitly in §21 (Task T08) and §24 (Task T10).

## 3. Auth State / No Auto-Login

This slice introduces **no** auth context, session store, access/refresh token handling, logged-in header state, or automatic login. `AuthProvider` is explicitly FVS-003's component (`FRONTEND-VERTICAL-SLICE-PLAN.md` §5 FVS-003 entry), not FVS-002's. Registration ends in a "check your email" state; verification ends in a success state with a link/prompt to `/login` (a route FVS-003 owns — this slice does not build `/login` itself, only links to it). If backend confirmation later reveals registration *does* establish a session, that is a follow-up change to Task T08 only, not a rebuild of this plan.

## 4. Form Architecture

Five primitives, minimal, presentational-first (RHF-agnostic where possible so component tests don't need a real form context):

- **`Form`** — semantic `<form>`, submit handling via a passed `onSubmit`, an error-summary slot (`role="alert"` or `aria-live="polite"` region — finalized in Task T05 against §17's accessibility notes), no internal validation logic of its own.
- **`TextField`** — label, input, `aria-describedby` wiring to help/error text, invalid state styling from existing semantic tokens. Accepts plain props (`value`/`onChange`/`error`/`label`/`hint`); does not import `react-hook-form` itself.
- **`PasswordField`** — wraps `TextField`'s pattern; adds a real `<button type="button">` show/hide toggle with correct `aria-pressed`, preserves the typed value across the type change, and a **static** (not computed) strength-hint text slot (§8 below — no scoring algorithm).
- **`Button`** — only the variants this slice actually uses (primary submit, secondary/tertiary if a page needs one) plus `disabled`/loading-submitting states. Not the full `bekaa3d-brand-ui` button-hierarchy table — add a variant only when a page in this slice needs it.
- **`Alert`** — accessible message region, variant driven by the existing semantic tokens (`success`/`warning`/`danger`/`info`), left-border + 8%-tint pattern matching `Toast`/`BackendUnreachableBanner`'s already-established visual treatment from FVS-001 (reuse that pattern, don't reinvent it).

No `select`/`checkbox`/`radio`/date-picker/file-upload/combobox/phone-field component — nothing in this slice needs one.

## 5. API Layering

Unchanged from FVS-001: `UI → mutation hook → apiClient → relative /api/... path → Next.js proxy → backend`. No feature component calls `fetch` directly. No new HTTP wrapper. `API_PROXY_TARGET` stays server-only, untouched by this slice.

**Corrected at FVS-002 BATCH 2 (Contract Sync) — the backend's real path for these endpoints already includes `/api`.** The frontend calls are still:

```
apiClient.post("/api/v1/auth/register", ...)
apiClient.post("/api/v1/auth/verify-email", ...)
apiClient.post("/api/v1/auth/resend-verification", ...)
```

but these now forward to the backend's `/api/v1/auth/register`, `/api/v1/auth/verify-email`, `/api/v1/auth/resend-verification` — **the proxy must preserve the `/api` prefix for these paths**, which is the opposite of the health-endpoint behavior (`/api/health/ready` → `/health/ready`, which still strips it, since the backend's own health paths have no `/api` prefix). This is a genuine dev-proxy configuration change, not mechanical inheritance of the old single-rule assumption — see FVS-002 BATCH 2 Part B, which corrects `next.config.ts` to route health paths one way and versioned API paths the other, with the resulting paths proven rather than assumed.

## 6. apiClient POST Support (scope for Task T06)

Extend, do not redesign. `apiClient.post<T>(path, body, options?)`:

- Enforces the same `/api/` path rule as `get()` (reuse `assertApiPath`).
- Serializes `body` as JSON; sets `Content-Type: application/json` only when a body is actually sent.
- Reuses the exact same success contract as `get()` (2xx + valid JSON → parsed value; 2xx + empty/unparseable → `undefined`), the exact same failure contract (delegates to `parseProblemBody`, same `ApiError.kind` rules), and the exact same timeout mechanism (`AbortController`, same default, same `timeoutMs` override).
- **No retry** — writes never auto-retry (already true of `get()`; stays true here, and is the reason Task T08/T10's mutations must explicitly set `retry: false`, since TanStack Query's own default is `3`).
- No auth/CSRF header invention (§12 of the plan-prompt's own instruction — matches FVS-001's existing stance, unchanged until VS-003).
- Not a generic Axios-like framework — no interceptors, no request/response transform pipeline, no config object beyond `timeoutMs`.

## 7. Mutation Architecture

TanStack Query `useMutation`, one hook per endpoint, colocated with its owning route under `src/lib/auth/` (mirrors `src/lib/health/useReadiness.ts`'s existing placement convention — a `lib/<domain>/` folder, not a generic `hooks/` or `features/` tree):

- `src/lib/auth/useRegister.ts`
- `src/lib/auth/useVerifyEmail.ts`
- `src/lib/auth/useResendVerification.ts`

No global mutation defaults are added to `queryClient.ts` (unchanged from FVS-001's "no speculative defaultOptions" stance). Each mutation sets `retry: false` explicitly. No feature component contains raw HTTP logic — only these hooks call `apiClient.post`.

## 8. Password Strength Hint

**Static rule hint, not a scored strength meter.** No `zxcvbn` or similar dependency (not approved, not needed). **Confirmed at FVS-002 BATCH 2 (table row 3):** the real rule is 8–256 Unicode code points, no complexity requirement — the hint copy states exactly that (e.g., "Use 8–256 characters.") and nothing more; it must not claim a complexity rule that doesn't exist, and must not be described as a "strength score" since the frontend still computes no score. The hint remains a plain describedby-linked text node, not a live-scored indicator.

**Captcha note (table row 18):** Cloudflare Turnstile will be added to registration (and resend) later; its field name/contract is not yet confirmed. This task does **not** install Turnstile, render a placeholder widget, or add a dummy captcha field — the form/schema is simply written so a future field can be added without restructuring it.

## 9. Validation & Accessibility (governs T03–T05, T08–T10)

- Visible labels (not placeholder-only), unique `id`s, `aria-describedby` linking each field to its help/error text, `aria-invalid` on invalid fields.
- Error summary region after a failed submit, `aria-live="polite"`.
- Focus moves to the **first invalid field** on submit failure (matches `FRONTEND-VERTICAL-SLICE-PLAN.md` §5's FVS-003 accessibility note, "focus moves to the first invalid field on submit failure" — applied consistently here since FVS-002 establishes the pattern FVS-003 explicitly says it reuses). Do not build a more elaborate focus-management scheme than this.
- All of this inherits the now-corrected global focus-ring token from FVS-001's T15 closure pass automatically — no new focus styling is needed in this slice's primitives.
- **Confirmed at FVS-002 BATCH 2 (table row 3):** password length is validated by **Unicode code point count**, via `[...password].length` (spreading the string into an array of code points) or an equivalent code-point-aware method — never `password.length`, which counts UTF-16 code units and over-counts characters outside the Basic Multilingual Plane (e.g., some emoji). Minimum 8, maximum 256 code points; no complexity rule; no trimming of email or password before validation/submission; control characters are rejected client-side.

## 10. Resend Cooldown — Confirmed at FVS-002 BATCH 2

**Duration is confirmed: 120 seconds (2 minutes) after a successful resend 202, per account** (table row 14) — no longer a contract gate; the countdown can be built directly against this fixed value. Required UX: visible countdown, `aria-live="polite"` announcement at countdown **start** and **completion** only (never per-tick), paired with a static "resend available at HH:MM:SS" text node for screen readers. This exact treatment is already specified in `FRONTEND-VERTICAL-SLICE-PLAN.md` §5 (FVS-002 entry) as the pattern FVS-034 will later reuse — FVS-002 is establishing it, not copying an existing implementation (none exists yet).

Since the backend still returns 202 during an active cooldown (it just silently skips sending another email — table row 12), the frontend derives cooldown state from the timestamp of its **own** last successful resend call, not from any backend field — there is no cooldown-remaining value in the response to read.

## 11. Countdown Architecture (once duration source is confirmed)

- Derive remaining time from an **absolute deadline timestamp**, never a bare decrementing integer (avoids drift).
- Clean up the interval/timeout on unmount.
- Disable the resend button for the cooldown's duration.
- `aria-live` announces only at start and at zero — not every tick.
- Deterministic tests use fake timers (`vi.useFakeTimers()` + `vi.advanceTimersByTimeAsync`), matching the pattern already established in `useReadiness.test.ts`.
- No general-purpose countdown framework/package — one small hook, local to this feature, reusable later by copy-paste-and-adapt if FVS-034 needs it (per the "born inside the feature that first needs it" rule), not pre-abstracted now.

## 12. Error-Handling Model (reuse FVS-001's four layers exactly)

| Layer | Source | Owner |
|---|---|---|
| A. Render/component exceptions | A component throws | `error.tsx`/`global-error.tsx` — unchanged, not touched by this slice |
| B. API/business result | A mutation resolves to a normalized `ApiError` | Page-local state → `Alert`, never thrown into `error.tsx` |
| C. Transient feedback | A one-off notification for a completed action | `Toast`, only if a specific task below genuinely justifies it (current expectation: none — registration/verify/resend results are page-local `Alert` states, not toasts, since they're the primary content of the page, not a transient aside) |
| D. Persistent readiness state | N/A to this slice | `BackendUnreachableBanner` — unchanged, not touched |

`ApiError.raw`, `.detail`, `.type`, `.title`, `.instance` are never rendered directly — only `ApiError.message` (or a page's own safe, hardcoded copy) reaches the user, exactly matching FVS-001's established rule (`docs/frontend-setup.md`, "Safe message vs. raw diagnostic").

## 13. Invalid / Expired / Used Token — Decision Table (confirmed at FVS-002 BATCH 2)

| Condition | Backend signal | Frontend state/copy |
|---|---|---|
| Valid, unused token | HTTP 204 | Success state |
| Invalid token | HTTP 400, code `INVALID_TOKEN` | Generic "invalid" failure state: "This verification link isn't valid. Request a new one." + resend CTA |
| Used token | HTTP 400, code `INVALID_TOKEN` (same code as invalid — no distinct signal) | Same generic "invalid" failure state as above — do not invent a separate "already used" sub-state |
| Already-verified re-click | HTTP 400, code `INVALID_TOKEN` (same code again) | Same generic "invalid" failure state as above — **explicitly not** a separate already-verified success state, per the confirmed contract |
| Expired token | HTTP 410, code `RESOURCE_EXPIRED` | Distinct "expired" failure state, copy communicating: "If you already verified your email, you can log in; otherwise request a new link." (exact wording may follow Bekaa3D's tone, but must preserve both halves of that meaning) + resend CTA and a link to `/login` |

This collapses to exactly **two** failure states (generic-invalid, expired) plus success — not three/four, and not the single generic-failure design originally planned before this row was confirmed. No further sub-states (e.g. distinguishing "used" from "invalid") are invented, since the backend's own signal does not distinguish them either.

## 14. Responsive & Brand Reuse

Mobile: single-column, full-width fields, full-width primary CTA. Desktop: centered card, `max-width: 420px`. Uses the existing `mobile`/`tablet`/`desktop` breakpoint tokens from FVS-001 (`tablet:`/`desktop:` Tailwind variants) — no new breakpoint. All colors come from existing semantic tokens (`success`/`danger`/`warning`/`info`/`text-*`/`surface-*`/the corrected focus-ring) — no raw hex anywhere in this slice's components.

## 15. Testing Strategy

**Unit/component** (Vitest + RTL, native `fetch`/module mocking, no MSW — same as FVS-001): `TextField`, `PasswordField` (including the show/hide toggle and `aria-pressed`), `Button`, `Alert`, the Zod schemas once real field names are confirmed, the countdown hook (pure logic, fake timers).

**Feature/integration** (mock `apiClient` at the module boundary, not `fetch` directly, for these — matches how `BackendUnreachableBanner.test.tsx` mocked `useReadiness`): registration (valid submit, client validation, enumeration-safe success shown identically for "new" and "duplicate" mocked responses, API validation failure, network failure, double-submit prevention); verify-email (valid token, malformed/missing token, generic failure state, network failure); resend (enumeration-safe response identical regardless of mocked outcome, cooldown display once unblocked, countdown accessibility, rate-limit path falls through to the generic failure `Alert`).

**E2E** (Playwright, extends FVS-001's `e2e/` infrastructure): a new deterministic spec added to the existing `smoke` project's test directory *only once the contract-gated pages are real* (register → check-email state → simulated verification link with a locally-controlled fake token → verify → a visible prompt/link to `/login`). Stays backend-independent, matching `e2e/smoke.spec.ts`'s existing discipline — determine the exact interception mechanism (likely `page.route` to stub the three endpoints, since this is testing frontend behavior, not backend connectivity) at Task T12 implementation time.

**Real-backend acceptance** (separate, deliberately not part of default E2E — mirrors FVS-001's `e2e/backend-connectivity.spec.ts` split): a new spec proving the real outbox-driven loop, gated on the local dev email-adapter mechanism being confirmed (table row 17). Never folded into the default `test:e2e` run.

## 16. Real Backend / Outbox Acceptance

Required by VS-002's own stated "mergeable outcome" ("A visitor can complete the full registration-and-verification loop against the real backend outbox-driven email flow") and this slice's DoD (§23). The exact mechanism for a test to obtain a real verification token from the backend's "local dev email adapter" (`vertical-slice-plan.md` line 77) is **not invented here** — Task T14 is written to the interface ("however the backend documents extracting a token locally") and is genuinely blocked until that's confirmed **and** a real backend is reachable (currently: it is not, per §0 above).

## 17. Documentation

One update to the existing `docs/frontend-setup.md` (not a new file — one canonical doc, per FVS-001's established convention), adding a new section covering: the enumeration-safety rule and why it must never be "fixed" by a future contributor; where the `/api/v1/auth/*` endpoint contracts and their open questions live (pointing at this plan's §1 table and `FRONTEND-VERTICAL-SLICE-PLAN.md` §17, not duplicating them); the resend-cooldown announcement contract. No standalone "auth manual."

## 18. Security / Privacy Review Points (checked explicitly in Task T11)

Enumeration safety (§2); passwords never logged (no `console.log`/analytics on form values, no password value in any error object); verification tokens never logged, and never persisted beyond the single request that consumes them (read from the URL, used once, not written to any storage); no auth/session assumption introduced (§3); no secret in the client bundle (nothing changes here vs. FVS-001 — still zero `NEXT_PUBLIC_*`); `ApiError.raw`/`detail`/backend HTML never rendered (§12); mutations never auto-retry (§6/§7 — prevents duplicate-write risk); rate-limit responses are handled as a generic failure, not specially trusted/parsed beyond status; the verification token appears in the URL **fragment** (`#token=...`, confirmed at FVS-002 BATCH 2 — not a query string) by necessity (backend-driven design, not a frontend choice) — note this plainly in T13's docs rather than attempting to "fix" an architecture this slice doesn't own. The fragment is never sent to the server by the browser on navigation, which is a small privacy positive over a query string, but is not itself a reason this design was chosen and not a guarantee this plan invents further meaning from.

## 19. Dependency Policy

Add only: `react-hook-form`, `zod`, `@hookform/resolvers` (Task T01). Do **not** add Formik, Yup, Axios, a password-strength library, a toast library, a state-management library, or MSW — none is justified by this slice.

## 20. Skill Map

| Skill | Applies to |
|---|---|
| `bekaa3d-brand-ui` | T02–T05 (primitives), T08–T10 (pages), T11 (responsive/accessibility pass) |
| `bekaa3d-api-contract` | T01 (schema-field gating), T06 (apiClient extension), T08–T10 (mutations/error handling), planning itself (this document) |
| `bekaa3d-frontend-slice-dod` | T11 (integration pass), T13–T14 (final verification) |
| `bekaa3d-commerce-ux` | **Not used anywhere in this slice** (§0) |
| `superpowers:test-driven-development` | Every task marked TDD REQUIRED/USEFUL below |
| `superpowers:verification-before-completion` | Every task, all real run conditions actually observed |
| `superpowers:requesting-code-review` | T11 (whole-slice-so-far gate) and T14 (final) |

---

## Global Constraints

(Every task below implicitly includes these — stated once here, not repeated per task.)

- Local Git only: no remote, no push, no PR, no GitHub MCP.
- One task at a time; STOP after each; wait for explicit instruction before the next.
- Full verification (`lint`, `typecheck`, `test`, `build`, plus `test:e2e` where the task touches routes/pages) before every commit.
- One local commit per task.
- Never invent a backend contract item marked `NEEDS BACKEND CONFIRMATION` in §1 — implement only what that row's "Frontend consequence" column actually allows.
- Reuse FVS-001 primitives/conventions; do not redesign `apiClient`, `ApiError`, `QueryProvider`, `AppLayout`, routing, or error-boundary conventions.
- No `data-testid` sprinkled everywhere — prefer role/label/text queries exactly as FVS-001's own tests do; add a test-only attribute only if a specific task genuinely cannot query any other way.

## Review Focus

(The five input classes/conditions most likely to bite a real user, per the spec, that no single task's own tests might otherwise catch — verified across the slice, primarily in T11.)

1. **Enumeration leakage under partial failure** — e.g., a network error during registration must show the *network* failure state, not silently fall through to the enumeration-safe success copy (and vice versa) — tested explicitly in T08.
2. **Double submission** — a slow network + impatient double-click/double-Enter on the register or resend form must not fire two mutations — tested in T08/T10.
3. **Countdown surviving a backgrounded/inactive tab** — the absolute-deadline design (§11) must still compute correctly if timers were throttled while the tab was hidden — tested in T10 once unblocked.
4. **Token query-string edge cases** — missing token, empty token, and a token containing characters requiring URL-decoding must all reach the generic failure state cleanly, not crash the page — tested in T09.
5. **Focus loss on route transition** — after a successful verify or a successful register, focus must land somewhere sensible (not silently reset to `<body>` with no indication anything happened) — tested in T11's accessibility pass.

---

## Task Dependency Graph

```
T01 (deps)
├─ T02 (Button+Alert) ──────────────┐
├─ T03 (TextField) ─── T04 (PasswordField) ─┤
├─ T05 (Form) ← needs T02,T03,T04            ├─ T08 (Register flow) ──┐
T06 (apiClient.post) ───────────────────────┤                        │
T07 (route skeletons) ──────────────────────┘                        │
                                              T09 (Verify-email flow) ┼─ T11 (integration/a11y/security) ─ T12 (E2E) ─ T13 (docs) ─ T14 (real-backend acceptance)
                                              T10 (Resend + cooldown) ┘
```

- **T01, T06, T07** have no dependency on each other or on T02–T05 — fully parallel-safe (though still executed one at a time per workflow).
- **T02 → T03 → T04 → T05** is a soft sequence (each reuses the prior's established pattern) but T02/T03 could run in either order; T04 genuinely needs T03's pattern; T05 genuinely needs T02–T04 to exist.
- **T08, T09, T10** each depend on T05 (Form), T06 (apiClient.post), and T07 (their own route skeleton) — parallel-safe with each other, but each is individually contract-gated (§1).
- **T11** depends on T08, T09, T10 all being real (not skeletons).
- **T12** depends on T11. **T13** can start drafting once T08–T10 land but is finalized after T12. **T14** depends on T12 and on real backend availability.

**Critical path:** T01/T05-chain → T08/T09/T10 (whichever clears its contract gate last) → T11 → T12 → T13/T14.

**Parallel-safe now:** T01, T02, T03, T06, T07 (and T04/T05 once their own deps land) — none require backend confirmation.

**Contract-blocked (as of BATCH 2 contract sync):** None of T08/T09/T10 remain blocked on the rows that used to gate them (2,3,5,6,15 for T08; 8,9,10 for T09; 11,12,13,14 for T10 — all now confirmed). Row 7 (`errors[]` shape) and row 18 (captcha) remain open but do not block T08–T10 from proceeding, per each task's own updated contract-status note.

**Backend-availability-blocked (separate from contract-blocked):** T14 only.

---

## TDD Map

| Task | TDD status |
|---|---|
| T01 | CONFIG — TDD not required (dependency install) |
| T02 | TDD REQUIRED (Button, Alert — real rendered behavior) |
| T03 | TDD REQUIRED |
| T04 | TDD REQUIRED (toggle behavior, `aria-pressed`) |
| T05 | TDD REQUIRED (submit/error-summary/focus wiring) |
| T06 | TDD REQUIRED (mirrors T09's own apiClient test rigor) |
| T07 | CONFIG/INTEGRATION — TDD not required (route skeletons, verified by build+manual render, matching T06's own precedent in FVS-001) |
| T08 | TDD REQUIRED |
| T09 | TDD REQUIRED |
| T10 | TDD REQUIRED |
| T11 | Verification pass — not new-feature TDD; DoD-checklist-driven |
| T12 | E2E — behavior-defined-before-considered-done, not unit RED/GREEN (matches FVS-001 T16's own classification) |
| T13 | CONFIG/DOCS — TDD not required |
| T14 | Verification/acceptance — TDD not applicable |

---

## Task List

### FVS002-T01 — Form Dependencies

**Purpose:** Install the only new dependencies this slice needs, establishing them for every later task.
**Depends on:** None.
**Files expected:** `package.json`, `package-lock.json`.
**Implementation actions:**
1. `npm install react-hook-form zod @hookform/resolvers` (runtime dependencies — these ship in the client bundle, not dev-only).
2. Confirm current compatible versions via npm at implementation time (do not pin to this plan's planning-time versions if newer compatible ones exist).
**Do NOT:** install Formik, Yup, or any other form/validation library; add any other package "while I'm in here."
**Tests:** None — config task.
**Acceptance criteria:** `npm install` succeeds; `npm run build` still succeeds with the new deps present but unused.
**Verification:** `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`.
**Skills/tools:** None beyond `superpowers:verification-before-completion`.
**Suggested commit message:** `chore: add React Hook Form and Zod dependencies`

---

### FVS002-T02 — Button & Alert Primitives

**Purpose:** The two simplest reusable primitives, needed by every later form/page task.
**Depends on:** None.
**Files expected:** `src/components/forms/Button.tsx`, `Button.test.tsx`, `src/components/feedback/Alert.tsx` (feedback, not forms — matches `Toast`'s existing placement, since `Alert` is a feedback primitive, not form-specific), `Alert.test.tsx`.
**Implementation actions:**
1. RED: write failing tests for `Button` (renders children, `disabled` state, a loading/submitting state that disables the button and exposes it accessibly — e.g., `aria-busy` — without inventing a spinner-in-button pattern beyond what's needed) and `Alert` (renders message, variant-driven semantic token classes reusing the exact `bg-*-bg border-l-*` pattern already established by `Toast`/`BackendUnreachableBanner`, correct `role`/`aria-live` per variant — status/polite for info/success, alert/assertive for danger — mirroring `BackendUnreachableBanner`'s existing not-ready/unreachable split).
2. GREEN: implement both minimally.
3. Verify compiled CSS for the token classes actually used (same technique as FVS001-T12/T13b).
**Do NOT:** build every button variant from `bekaa3d-brand-ui`'s table — only what a page in this slice needs (primary submit at minimum; add secondary/tertiary only if a task below actually uses one); give `Alert` a dismiss control (it's not `Toast` — it's a persistent page-level message, not a transient notification).
**Tests:** TDD required.
**Acceptance criteria:** Both components pass their tests; `Alert`'s variant→token mapping is reused, not reinvented; compiled CSS confirmed.
**Verification:** `npm run test -- Button`, `npm run test -- Alert`, then full suite.
**Skills/tools:** `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add Button and Alert form primitives`

---

### FVS002-T03 — TextField Primitive

**Purpose:** The base labeled-input primitive every text-entry field in this slice builds on.
**Depends on:** None (parallel-safe with T02).
**Files expected:** `src/components/forms/TextField.tsx`, `TextField.test.tsx`.
**Implementation actions:**
1. RED: tests for visible label, unique `id` generation (`useId`, matching `LoadingSpinner`'s existing pattern), `aria-describedby` linking to help/error text, `aria-invalid` when an `error` prop is present, error text actually rendered and associated.
2. GREEN: implement minimally — plain controlled props (`label`, `value`, `onChange`, `error?`, `hint?`, plus native input passthrough props), no RHF import.
**Do NOT:** import `react-hook-form` here (keep it RHF-agnostic; RHF wiring happens where it's consumed); build a floating-label or multi-line variant not needed by this slice.
**Tests:** TDD required.
**Acceptance criteria:** Component passes accessibility-focused tests; no RHF dependency in this file.
**Verification:** `npm run test -- TextField`, then full suite.
**Skills/tools:** `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add TextField form primitive`

---

### FVS002-T04 — PasswordField Primitive

**Purpose:** Extends `TextField`'s pattern with the show/hide toggle and strength-hint slot this slice's spec requires.
**Depends on:** T03.
**Files expected:** `src/components/forms/PasswordField.tsx`, `PasswordField.test.tsx`.
**Implementation actions:**
1. RED: tests for — input `type` starts as `password`; a real `<button type="button">` toggle with an accessible name (e.g., "Show password"/"Hide password", changing with state) and correct `aria-pressed`; activating it flips `type` to `text` and back, **preserving the typed value** across the toggle; toggle is keyboard-operable; a static strength-hint text node is rendered and `aria-describedby`-linked alongside the error text (both can coexist — confirm no `aria-describedby` collision, e.g. space-separated ID list).
2. GREEN: implement, reusing `TextField`'s internal structure where sensible (composition, not duplication).
**Do NOT:** install `zxcvbn` or compute a real strength score; invent specific password rules in the hint copy beyond a generic, honestly-worded helper string (§8) — the backend's real rules are unconfirmed (table row 3).
**Tests:** TDD required.
**Acceptance criteria:** Toggle behavior and `aria-pressed` verified; value preserved across type changes; keyboard-operable.
**Verification:** `npm run test -- PasswordField`, then full suite.
**Skills/tools:** `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add PasswordField primitive with show/hide toggle`

---

### FVS002-T05 — Form Wrapper Primitive

**Purpose:** The submit/error-summary/focus-management shell every page-level form composes.
**Depends on:** T02, T03, T04.
**Files expected:** `src/components/forms/Form.tsx`, `Form.test.tsx`.
**Implementation actions:**
1. RED: tests using a small **fake** local schema (e.g., one required text field — not a real registration/resend schema) proving: semantic `<form>` renders; `onSubmit` fires with parsed values on valid submit; on invalid submit, an error-summary region renders with `aria-live="polite"` and focus moves to the first invalid field (§9); submit is prevented while already submitting (the double-submit-prevention seam T08/T10 will rely on).
2. GREEN: implement using React Hook Form's `FormProvider`/`useForm` plus `@hookform/resolvers/zod`, accepting a caller-supplied Zod schema as a prop — this file itself defines no business schema.
**Do NOT:** hardcode any registration/resend/verify-specific field or schema here; build a multi-step/wizard form capability not needed by this slice.
**Tests:** TDD required.
**Acceptance criteria:** Generic form contract (submit/validate/error-summary/focus/double-submit-guard) proven against a fake schema, reusable by every later page task.
**Verification:** `npm run test -- Form`, then full suite.
**Skills/tools:** `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add Form primitive with validation and focus management`

---

### FVS002-T06 — apiClient POST/JSON Support

**Purpose:** The one transport-layer extension this slice needs (§6). Mirrors FVS001-T09's own rigor since this is the second-most-reused piece of infrastructure in the app after `get()`.
**Depends on:** None (parallel-safe with T01–T05, T07).
**Files expected:** `src/lib/api/apiClient.ts` (modified), `apiClient.test.ts` (modified/extended).
**Implementation actions:**
1. RED: extend the existing test matrix (mirror `apiClient.test.ts`'s existing structure exactly) with `post()` cases: successful 2xx + JSON body → parsed value; 2xx + empty/unparseable body → `undefined` (same as `get`); non-2xx → same `ApiError` construction path as `get` (reuse, do not duplicate `parseProblemBody` wiring); network failure → `kind:"network"`; timeout → `kind:"timeout"`; path-prefix enforcement (`/api/` required) reused from `assertApiPath`; body is actually serialized as JSON and `Content-Type: application/json` is set only when a body is sent.
2. GREEN: implement `post<T>(path, body, options?)`, reusing internal helpers (`assertApiPath`, `fallbackHttpMessage`, `networkError`, `timeoutError`, `parseProblemBody`) rather than copy-pasting `get()`'s body.
3. Export it alongside `get` on the existing `apiClient` object (`export const apiClient = { get, post };`).
**Do NOT:** add retry logic; add auth/CSRF headers; build a generic request-options/interceptor system; change `get()`'s existing behavior.
**Tests:** TDD required — full matrix mirrored from `get()`'s own test file.
**Acceptance criteria:** All matrix cases pass; `get()`'s existing 11 tests still pass unchanged (regression).
**Verification:** `npm run test -- apiClient`, then full suite, then `npm run build`.
**Skills/tools:** `bekaa3d-api-contract`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add apiClient.post for JSON write requests`

---

### FVS002-T07 — Route Skeletons

**Purpose:** Prove the three routes exist and render inside the existing shell, before any real form logic lands — separates "does routing/layout work" from "is the contract-gated behavior correct," matching FVS-001's own T06-before-T08 sequencing philosophy.
**Depends on:** None (parallel-safe with T01–T06).
**Files expected:** `src/app/register/page.tsx`, `src/app/verify-email/page.tsx`, `src/app/verify-email/resend/page.tsx` (+ a `page.test.tsx` for each, following the existing `page.test.tsx` pattern from FVS-001's root/404 pages).
**Implementation actions:**
1. Each page renders a heading and a short placeholder paragraph only (no form yet) — proves the route exists and renders through the root layout's shell (inherited automatically, nothing to compose manually, exactly like `src/app/page.tsx`/`not-found.tsx` today).
2. Component tests assert the heading renders (matching the existing `page.test.tsx` style) — configuration validation, not RED/GREEN business logic.
**Do NOT:** add any form, mutation, or real content here — that's T08/T09/T10's job; add navigation links to these routes from the existing `Header` (no nav exists yet in FVS-001 and adding one is out of this slice's scope unless a later task explicitly calls for it).
**Tests:** Config/integration — not TDD in the RED/GREEN sense (matches FVS-001 T06's own classification in §23 of that plan).
**Acceptance criteria:** All three routes return 200 and render their heading; `npm run build` includes them in the route table.
**Verification:** `npm run test`, `npm run build`, `npm run dev` manual spot-check of all three URLs.
**Skills/tools:** None beyond `bekaa3d-brand-ui` for placeholder copy tone.
**Suggested commit message:** `feat: add register, verify-email, and resend route skeletons`

---

### FVS002-T08 — Registration Flow

**CONTRACT STATUS (updated at FVS-002 BATCH 2):** Rows 2 (field names), 3 (password rules), 5 (success status), 6 (success body), 15 (auto-login) are now **CONFIRMED** — this task is no longer blocked on them. **Row 7 (validation-error `errors[]` shape) and row 18 (Turnstile captcha) remain genuinely open** and must not be guessed: server field errors surface only via the generic `Alert` path per §12 until row 7 is confirmed, and no captcha field/widget/token is added until row 18 is confirmed.

**Purpose:** The real registration mutation and page, enumeration-safe by construction.
**Depends on:** T05, T06, T07.
**Files expected:** `src/lib/auth/useRegister.ts` (+ test), `src/app/register/page.tsx` (rewritten from skeleton), `page.test.tsx` (rewritten).
**Implementation actions:**
1. RED: mutation tests (mock `apiClient.post`, not `fetch`) for — successful submit resolves regardless of a mocked "new" vs. "duplicate" server response (enumeration-safety proof, §2); request body is exactly `{ email, password }` sent to `/api/v1/auth/register` with no trailing slash; `retry: false` is actually configured; network failure surfaces `ApiError.kind:"network"` through to the page; double-submit is prevented (rapid double-click fires exactly one mutation).
2. RED: page tests — client-side validation blocks submit with empty/malformed email, and password outside the confirmed 8–256 Unicode-code-point range (counted via `[...password].length`, not `.length`) or containing control characters, without ever sending the request; no password complexity rule is enforced; email/password are not trimmed; successful submit shows the enumeration-safe "check your email" `Alert`, identical copy whether the mocked backend implies a new or existing account; a server validation failure (mocked `ApiError.kind:"http"`) and a 429 rate-limit failure both show a safe generic message via `Alert`, never `.raw`/`.detail`.
3. GREEN: implement `useRegister` and wire `/register`'s real form (`Form` + `TextField` + `PasswordField` + `Button` + `Alert`), using a Zod schema built from the confirmed fields and password rule (row 2, row 3) only.
**Do NOT:** add any field, limit, or rule not confirmed by the backend (email/password only — no captcha field); introduce auth/session/cookie state (row 15 confirms none is created); retry the mutation automatically; invent the `errors[]` per-field mapping (row 7); render `ApiError.raw`.
**Tests:** TDD required, including the explicit enumeration-safety test from §2 and the full 21-item test matrix from the BATCH 2 Part C instruction.
**Acceptance criteria:** Enumeration-safety test passes; double-submit test passes; Unicode-code-point password counting proven (not UTF-16 length); no invented field/rule is present anywhere in the schema or copy.
**Verification:** `npm run test -- useRegister`, `npm run test -- register`, full suite, `npm run build`.
**Skills/tools:** `bekaa3d-api-contract` (mandatory — this is the highest contract-risk task in the slice), `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add registration mutation and page`

---

### FVS002-T09 — Verify-Email Flow

**CONTRACT STATUS (updated at FVS-002 BATCH 2):** Rows 8 (token transport), 9 (invalid/expired/used distinction), 10 (idempotent re-click) are now **CONFIRMED** — this task is no longer contract-gated. **Build the two-state design from the updated §13 table** (generic-invalid on 400 `INVALID_TOKEN`, expired on 410 `RESOURCE_EXPIRED`), not the single-generic-failure design originally planned before this sync, and not a further-split three/four-state design either — the backend's own signal supports exactly two failure states.

**Purpose:** The real verify-email mutation and page.
**Depends on:** T05, T06, T07.
**Files expected:** `src/lib/auth/useVerifyEmail.ts` (+ test), `src/app/verify-email/page.tsx` (rewritten), `page.test.tsx` (rewritten).
**Implementation actions:**
1. RED: mutation tests — valid token → HTTP 204 success; 400 `INVALID_TOKEN` → generic-invalid failure state; 410 `RESOURCE_EXPIRED` → distinct expired failure state; any other error (mocked `ApiError` of any other `kind`) → the generic-invalid failure state as the safe fallback; missing/empty/malformed token (read from `location.hash`, **not** `useSearchParams` — the token is in the URL fragment, which Next.js's server-rendered search params cannot see) → generic-invalid failure state without ever calling the mutation with a garbage value.
2. RED: page tests — loading state while the mutation is in flight; success state with a link/prompt toward `/login` (a route this slice does not build, just links to — per §3); generic-invalid failure state with a resend CTA linking to `/verify-email/resend`; expired failure state with copy communicating both "log in if already verified" and "otherwise request a new link," plus the same resend CTA and a `/login` link.
3. GREEN: implement, reading the 43-character token from `location.hash` (confirmed format `#token=...`) client-side (this requires a Client Component / `"use client"` boundary, since `location.hash` is never sent to or renderable by the server) and POSTing `{ token }` to `/api/v1/auth/verify-email`.
**Do NOT:** build more than two distinct failure UI states; read the token from `useSearchParams`/a query string; persist the token anywhere beyond the single request that consumes it (§18); auto-retry the verify mutation; invent a separate already-verified success state (row 10 confirms the backend does not distinguish it).
**Tests:** TDD required, including the URL-edge-case tests from Review Focus item 4 (now exercising `location.hash`, not search params).
**Acceptance criteria:** Generic-invalid and expired failure states correctly map to 400/410 respectively; token is read once, used once, never stored.
**Verification:** `npm run test -- useVerifyEmail`, `npm run test -- verify-email`, full suite, `npm run build`.
**Skills/tools:** `bekaa3d-api-contract`, `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add email verification mutation and page`

---

### FVS002-T10 — Resend Flow + Cooldown

**CONTRACT STATUS (updated at FVS-002 BATCH 2):** Rows 11 (field name), 12 (body shape/behavior), 13 (rate-limit status), and 14 (cooldown duration = 120 seconds fixed) are now **CONFIRMED** — both the submission half and the countdown-display half can be built together; this task is no longer split into a gated and an ungated half.

**Purpose:** The real resend mutation, page, and cooldown countdown.
**Depends on:** T05, T06, T07.
**Files expected:** `src/lib/auth/useResendVerification.ts` (+ test), `src/lib/auth/useCooldown.ts` (+ test — pure logic, split out from the page per §11's "one small hook" guidance), `src/app/verify-email/resend/page.tsx` (rewritten), `page.test.tsx` (rewritten).
**Implementation actions:**
1. RED: mutation tests — identical enumeration-safe result rendered whether the mocked backend response implies the account existed or not (§2's explicit test requirement); request body is exactly `{ email }` sent to `/api/v1/auth/resend-verification`; `retry: false`; a 429 response (with `Retry-After`) surfaces as a safe generic rate-limit `Alert`, not a fabricated cooldown value.
2. RED: `useCooldown` tests with fake timers — derives remaining time from an absolute deadline computed as "now + 120 seconds" at the moment of a successful 202 (not from any response field, since none carries the duration — table row 14); announces once at start, once at completion, never per-tick; cleans up on unmount; survives a simulated throttled-timer gap without drifting past the real deadline (Review Focus item 3).
3. GREEN: implement submission and cooldown together.
**Do NOT:** derive the cooldown duration from a `Retry-After` header or any response field — it is a fixed 120-second client-side value starting at the successful resend, per row 14; special-case the 429 rate-limit path into anything other than the generic `Alert`.
**Tests:** TDD required for both halves.
**Acceptance criteria:** Enumeration-safety test passes for resend; the countdown's accessibility-announcement test (start/completion only) passes.
**Verification:** `npm run test -- useResendVerification`, `npm run test -- useCooldown` (once built), `npm run test -- resend`, full suite, `npm run build`.
**Skills/tools:** `bekaa3d-api-contract`, `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add resend verification mutation and cooldown`

---

### FVS002-T11 — Integration, Accessibility, Responsive & Security Pass

**Purpose:** The whole-slice-so-far verification gate, mirroring FVS001-T15's discipline (and its constraint: **honestly mark anything requiring a real browser as pending if no browser tool is available in the executing environment** — do not fabricate keyboard/viewport/contrast results, per FVS001-T15's own precedent).
**Depends on:** T08, T09, T10.
**Files expected:** Likely none (verification-only); any fix goes in the smallest owning file from T02–T10, same discipline as FVS001-T15's defect-handling rule.
**Implementation actions:**
1. Walk `bekaa3d-frontend-slice-dod`'s full checklist against the three real pages.
2. Real (or honestly-marked-pending) keyboard walkthrough of all three routes; viewport matrix at the same six widths FVS-001 used (320/375/768/1024/1440/1920); contrast check of any new text/background pairing this slice introduced (reusing FVS-001's precise-calculation method, not estimation) — though if every color is reused verbatim from FVS-001's tokens with no new pairing, state that explicitly rather than re-deriving numbers already proven.
3. Security/privacy review against §18 of this plan, point by point.
4. Request an independent review (`superpowers:requesting-code-review`) of the T08–T10 diff together.
**Do NOT:** silently mark a browser-dependent check PASS without a real browser; expand scope into T12/T13/T14's work.
**Tests:** Verification-only; any defect fix gets a regression test in its owning component's existing test file.
**Acceptance criteria:** DoD checklist walked with evidence; any genuine defect found is fixed (smallest possible change) and re-verified; unresolved findings (if any) are reported, not hidden.
**Verification:** Full `lint`/`typecheck`/`test`/`build`, plus whatever manual/Playwright checks the executing environment genuinely supports.
**Skills/tools:** `bekaa3d-brand-ui`, `bekaa3d-api-contract`, `bekaa3d-frontend-slice-dod`, `superpowers:verification-before-completion`, `superpowers:requesting-code-review`.
**Suggested commit message:** `fix: address FVS-002 integration/accessibility findings` (only if a fix was needed — otherwise no commit, matching FVS001-T15's own "no empty commit" rule)

---

### FVS002-T12 — E2E Flow

**Purpose:** One deterministic, backend-independent E2E spec proving the full click-through flow, added to the existing `smoke` Playwright project.
**Depends on:** T11.
**Files expected:** `e2e/register-and-verify.spec.ts` (new file; whether it joins the existing `smoke` project's `testMatch` or needs its own project entry in `playwright.config.ts` is this task's own small decision — prefer extending the existing `smoke` project's `testMatch` array over adding a third project, unless a concrete reason emerges).
**Implementation actions:**
1. Determine the interception mechanism (`page.route` stubbing the three `/api/v1/auth/*` endpoints is the likely approach, matching this spec's need to stay backend-independent — confirm against current Playwright docs at implementation time, same discipline FVS001-T16 used for its own Playwright setup).
2. Write the flow: navigate to `/register` → submit → see check-email state → navigate to `/verify-email#token=<fake-43-char-token>` (URL fragment, confirmed at FVS-002 BATCH 2 — not a query string) → see success state → see a link/prompt toward `/login`.
3. Run `npm run test:e2e` twice conceptually (this flow doesn't depend on a real backend at all, unlike FVS-001's readiness-banner tolerance test) and confirm determinism.
**Do NOT:** hit a real backend in this spec; fold this into `e2e/backend-connectivity.spec.ts` or vice versa; add unrelated business-flow coverage.
**Tests:** This is the test — behavior-defined-before-done, not unit RED/GREEN.
**Acceptance criteria:** `npm run test:e2e` passes, including this new spec, with evidence captured (matches FVS001-T16's own evidentiary standard).
**Verification:** `npm run test:e2e` (full project run), `npm run lint`, `npm run typecheck`, `npm run build`.
**Skills/tools:** `superpowers:verification-before-completion`.
**Suggested commit message:** `test: add register-to-verify E2E flow`

---

### FVS002-T13 — Documentation

**Purpose:** The one small doc update (§17).
**Depends on:** T08, T09, T10 (needs real behavior to describe accurately — `docs/frontend-setup.md`'s own established rule is "describes the ACTUAL committed implementation").
**Files expected:** `docs/frontend-setup.md` (modified — new section, not a new file).
**Implementation actions:**
1. Add a section covering: the enumeration-safety rule and why (so a future contributor doesn't "fix" it); a pointer to this plan's §1 contract table and `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 for open questions (not a duplicate copy); the resend-cooldown announcement contract (start/completion only); the current-generic verify-email failure state and that it's deliberately not split into invalid/expired/used until confirmed (§13).
**Do NOT:** write a full auth architecture manual; duplicate FVS-001's existing sections; document FVS-003's login flow (not built yet).
**Tests:** None — docs task, same as FVS001-T17's own classification.
**Acceptance criteria:** Same self-review/fresh-reader-review discipline as FVS001-T17 — every path/command referenced actually exists, no speculative feature documented.
**Verification:** `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` (doc has no behavioral tests, run these only to confirm nothing regressed).
**Skills/tools:** `bekaa3d-api-contract`.
**Suggested commit message:** `docs: document registration and email verification contracts`

---

### FVS002-T14 — Real Backend / Outbox Acceptance

**BLOCKED** on table row 17 (local dev email-adapter mechanism unconfirmed) **and** on real backend availability (unconfirmed throughout this engagement to date, §0). **Do not attempt this task until both are true.**

**Purpose:** Prove VS-002's own stated mergeable outcome against the real backend, mirroring FVS001-T16's `test:e2e:backend` split.
**Depends on:** T12, real backend reachable, row 17 confirmed.
**Files expected:** `e2e/backend-connectivity.spec.ts` extended, or a new sibling spec (`e2e/register-and-verify-backend.spec.ts`) plus a `test:e2e:backend:register` -style script — exact shape is this task's own decision once the mechanism is known.
**Implementation actions:**
1. Register a real account against the real backend through the real proxy.
2. Obtain the real verification token via whatever mechanism the backend documents for its local dev email adapter (row 17) — **do not invent one**.
3. Submit it to `/verify-email` and confirm a genuine success.
**Do NOT:** mock the email/outbox mechanism; fake a token; skip this and claim FVS-002 is done without it (mirrors FVS001-T16/T18's own standing rule).
**Tests:** Real-backend acceptance evidence, not a unit test.
**Acceptance criteria:** A genuine, observed successful register→verify loop against the real backend, output recorded.
**Verification:** The real run itself, output captured verbatim.
**Skills/tools:** `superpowers:verification-before-completion`.
**Suggested commit message:** `test: add real-backend registration acceptance verification`

---

## Risk Register

| Risk | Impact | Mitigation | Owning task |
|---|---|---|---|
| Enumeration leakage (copy or timing side-channel) | High — defeats the entire security purpose of the slice | Explicit enumeration-safety tests in T08/T10; DoD check in T11 | T08, T10, T11 |
| Invented backend validation (field names/limits) | High — wasted work, possible shipped-wrong contract | Contract confidence table (§1); every schema task explicitly gated | T08, T09, T10 |
| Verification-token contract mismatch (wrong param name) | High — verify-email silently broken | T09 explicitly refuses to guess; STOPs if unconfirmed at start | T09 |
| Resend cooldown duration mismatch | Medium — wrong UX, possible premature/late resend allowance | Countdown split from submission (§10); duration never invented | T10 |
| Duplicate registration/resend submission | Medium — possible duplicate side effects server-side | `retry:false` + double-submit-prevention tests | T06, T08, T10 |
| Automatic mutation retry | Medium — same class of risk as above | T06 never implements retry; T08/T10 explicitly set `retry:false` | T06, T08, T10 |
| Password exposure (logged, rendered, or persisted) | High — credential leak | §18 review point; no `console.log` of form values anywhere | T08, T11 |
| Token exposure (logged or persisted beyond one use) | Medium — replay/leak risk | §18 review point; token read-once design in T09 | T09, T11 |
| Stale/drifting countdown | Low–Medium — confusing UX, possible premature resend attempt | Absolute-deadline architecture (§11), not a decrementing counter | T10 |
| Accessibility announcement spam (per-tick `aria-live`) | Medium — genuinely hostile to screen-reader users if wrong | Explicit start/completion-only test requirement | T10 |
| Query-parameter token handling edge cases | Medium — crash or confusing failure on a malformed link | Explicit edge-case tests (Review Focus item 4) | T09 |
| Backend availability / outbox testability | Medium — blocks final DoD sign-off, not implementation | T14 isolated, clearly marked pending, not silently skipped | T14 |
| Accidental auto-login assumption baked in too deeply | Medium — rework if backend confirms otherwise | §3/§7 explicit design; no auth context introduced at all, so a later correction is additive, not a rewrite | T08 |

## Definition of Done (FVS-002-specific)

**Functional:** registration flow works against confirmed contract fields; enumeration-safe success (tested, §2); email verification flow works for the confirmed success case and the generic failure case; resend flow works enumeration-safely; cooldown behaves correctly once its contract gate clears; a working link/prompt to `/login` appears after verification success (login itself is FVS-003).

**Accessibility:** labels, field errors/descriptions, error summary, full keyboard operability, show/hide `aria-pressed` correctness, cooldown announced only at start/completion, sensible focus behavior on submit failure and on success, responsive at mobile/desktop per §14 — all walked with real evidence in T11, same discipline as FVS001-T15.

**Security:** no account enumeration anywhere (copy or behavior); no password/token logging; no unsafe `ApiError.raw`/`detail`/HTML rendering; no speculative auth/session state introduced.

**Quality:** `lint`, `typecheck`, unit/integration tests, `test:e2e`, `build` all green at every task boundary, final full suite green at T12.

**Backend:** T14's real VS-002 outbox acceptance evidence obtained before this slice is called fully done — matching FVS-001's own standing rule that real-backend verification is a genuine gate, not a formality.

## Non-Scope

Login implementation (FVS-003); session/auth persistence; logout; forgot/reset password (FVS-004); social login; MFA (FVS-005); account profile (FVS-006); addresses; products; cart; STL; checkout; admin; wishlist; offers; production email-infrastructure implementation (the backend's concern, VS-002). "Registration" does not grow into the whole auth system in this slice.
