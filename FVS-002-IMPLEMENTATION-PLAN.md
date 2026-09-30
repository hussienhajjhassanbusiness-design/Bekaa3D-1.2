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

Every row's "Frontend consequence" governs the corresponding task's scope below. **No row below was resolved by guessing — every `NEEDS BACKEND CONFIRMATION` stays unresolved in this plan and in the code it produces.**

| # | Contract item | Status | Evidence / source | Frontend consequence |
|---|---|---|---|---|
| 1 | Endpoint paths (`register`, `verify-email`, `resend-verification`) | **CONFIRMED** | `vertical-slice-plan.md` VS-002 line 75; `FRONTEND-VERTICAL-SLICE-PLAN.md` §5 lines 86–88 | Mutations/routes can be built against exact paths now |
| 2 | Registration request field names | **NEEDS BACKEND CONFIRMATION** | `vertical-slice-plan.md` names only the type `RegisterRequest`, no fields | Zod schema for register cannot name real fields yet (§9, §21) |
| 3 | Password validation rules (length/complexity) | **NEEDS BACKEND CONFIRMATION** | Not stated anywhere in either plan document | Client schema applies **no** length/complexity rule; relies entirely on server-returned validation errors until confirmed (§9, §21) |
| 4 | Email format check | **ASSUMED — safe, non-authoritative** | Standard web input hygiene, not a backend business rule; `bekaa3d-api-contract`'s own principle ("frontend validation is UX only, never authoritative") | A generic "looks like an email" client check is permitted — it cannot be stricter than any real backend rule and never blocks a request the server would accept |
| 5 | Registration success HTTP status | **NEEDS BACKEND CONFIRMATION** | Not stated | Treat any 2xx as success via existing `apiClient` contract; do not assert a specific status code |
| 6 | Registration success response shape (`RegistrationAccepted`) | **NEEDS BACKEND CONFIRMATION** | Type named only, no fields, in `vertical-slice-plan.md` | Frontend reads **no** field from the success body — success is the HTTP outcome alone, exactly like `useReadiness`'s existing pattern |
| 7 | RFC 9457 validation-error (`errors[]`) extension shape | **NEEDS BACKEND CONFIRMATION** — already logged | `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 ("RFC 9457 problem-response validation-error shape") | No per-field server-error mapping is built; server validation failures surface only via the existing generic `ApiError.message`/`Alert` path until confirmed |
| 8 | Verify-email token transport (query param name vs. POST body field name) | **NEEDS BACKEND CONFIRMATION** | `FRONTEND-VERTICAL-SLICE-PLAN.md` §5 line 91 says the frontend *route* "reads a token query param" (a frontend routing assumption, not a backend-confirmed contract); backend names only `VerifyEmailRequest`, no field | The verify-email mutation task is contract-gated (§22) |
| 9 | Invalid / expired / used token distinction | **NEEDS BACKEND CONFIRMATION** | Not stated; only "single-use verification token" is mentioned | UI implements **one generic failure state**, not three, until the backend proves distinct signals (§21) |
| 10 | Already-verified idempotent re-click behavior | **NEEDS BACKEND CONFIRMATION** | Not stated | No special-casing; whatever HTTP outcome the backend returns is what the existing success/generic-failure states already handle (§22) |
| 11 | Resend request field name(s) | **NEEDS BACKEND CONFIRMATION** | Type named only (`ResendVerificationRequest`) | Resend schema cannot name a real field yet (§9, §24) |
| 12 | Resend enumeration-safe behavior | **CONFIRMED (behavior)** / body shape unconfirmed | `vertical-slice-plan.md` VS-002 line 74: "enumeration-safe registration/resend" (explicit) | UI copy rule is settled now (§6); exact response body still unconfirmed |
| 13 | Rate-limit HTTP status (429 or otherwise) | **NEEDS BACKEND CONFIRMATION** | Not stated | No special-cased rate-limit UI branch; generic `kind:"http"` 4xx handling applies until confirmed |
| 14 | Cooldown duration source (`Retry-After` header / response field / fixed value) | **NEEDS BACKEND CONFIRMATION** | Not stated anywhere | Countdown task is fully contract-gated (§24) — no duration is invented |
| 15 | Auto-login after registration | **NEEDS BACKEND CONFIRMATION** — already logged | `FRONTEND-VERTICAL-SLICE-PLAN.md` §17 ("Does registration (VS-002) log the user in?"), and §5's FVS-002 entry states its own working assumption of "no" | This plan builds against the documented "no auto-login" assumption (§7); flagged, not silently decided |
| 16 | Correlation/request-ID header | **NEEDS BACKEND CONFIRMATION** — already logged, inherited from FVS-001 | `src/lib/api/ApiError.ts` inline comment | Unchanged from FVS-001; never populated |
| 17 | Local dev email-adapter test mechanism (for real-backend acceptance) | **NEEDS BACKEND CONFIRMATION** | `vertical-slice-plan.md` VS-002 line 77 confirms a "local dev email adapter" is planned/documented on the backend side, but not *how* to extract a token from it | Real-backend acceptance task (§25) cannot be written to a concrete mechanism yet |

**New gaps this plan surfaces that are not yet in `FRONTEND-VERTICAL-SLICE-PLAN.md` §17** (rows 2, 3, 8, 9, 10, 11, 13, 14, 17 above, excluding the two already-logged rows 7 and 15): this plan does **not** edit that file (out of this planning task's scope), but whoever executes the contract-gated tasks below should append them to §17 before or as part of that task, per `bekaa3d-api-contract`'s "Maintaining the Contract-Gap List" rule.

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

Backend paths are `/api/v1/auth/register`, `/api/v1/auth/verify-email`, `/api/v1/auth/resend-verification` — since T09/T10 already established that `apiClient` paths must start with `/api/` and Next's rewrite strips only the literal `/api` prefix (not `/api/v1`), the frontend calls are:

```
apiClient.post("/api/v1/auth/register", ...)
apiClient.post("/api/v1/auth/verify-email", ...)
apiClient.post("/api/v1/auth/resend-verification", ...)
```

which the existing rewrite forwards to the backend's `/v1/auth/register` etc. **This mapping is mechanical, not a new design decision** — it follows T09/T10's already-approved rule applied to a `/v1`-prefixed backend path, the same way `/api/health/ready` → `/health/ready` already works. No new proxy configuration is needed.

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

**Static rule hint, not a scored strength meter.** No `zxcvbn` or similar dependency (not approved, not needed). Since real password rules are `NEEDS BACKEND CONFIRMATION` (table row 3), the hint text itself must be clearly generic/non-committal until confirmed (e.g., a static, honestly-worded helper string — exact copy is Task T08's own small decision, not invented as a "rule" the backend will actually enforce). The hint is a plain describedby-linked text node, not a live-scored indicator, keeping it cheap and avoiding a fabricated confidence signal about password strength the frontend cannot actually verify.

## 9. Validation & Accessibility (governs T03–T05, T08–T10)

- Visible labels (not placeholder-only), unique `id`s, `aria-describedby` linking each field to its help/error text, `aria-invalid` on invalid fields.
- Error summary region after a failed submit, `aria-live="polite"`.
- Focus moves to the **first invalid field** on submit failure (matches `FRONTEND-VERTICAL-SLICE-PLAN.md` §5's FVS-003 accessibility note, "focus moves to the first invalid field on submit failure" — applied consistently here since FVS-002 establishes the pattern FVS-003 explicitly says it reuses). Do not build a more elaborate focus-management scheme than this.
- All of this inherits the now-corrected global focus-ring token from FVS-001's T15 closure pass automatically — no new focus styling is needed in this slice's primitives.

## 10. Resend Cooldown — Contract Gate

**This is the single highest-risk contract area in the slice.** Required UX: visible countdown, rate-limited resend, `aria-live="polite"` announcement at countdown **start** and **completion** only (never per-tick), paired with a static "resend available at HH:MM:SS" text node for screen readers. This exact treatment is already specified in `FRONTEND-VERTICAL-SLICE-PLAN.md` §5 (FVS-002 entry) as the pattern FVS-034 will later reuse — FVS-002 is establishing it, not copying an existing implementation (none exists yet).

**Duration source is `NEEDS BACKEND CONFIRMATION`** (table row 14) — no value is invented. Task T10 is split internally so that the enumeration-safe resend *submission* (no cooldown display) can be built now, while the countdown *display* is gated behind duration-source confirmation (see Task T10's own Do-NOT list).

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

## 13. Invalid / Expired / Used Token — Decision Table

| Condition | Backend signal | Frontend state/copy |
|---|---|---|
| Valid, unused token | Confirmed: some 2xx (exact status/body unconfirmed, table row 5) | Success state |
| Invalid / expired / used / any other failure | **NEEDS BACKEND CONFIRMATION** — no distinct signal known (table row 9) | **One generic failure state**: "This verification link isn't valid. Request a new one." + resend CTA. Do not guess which sub-case occurred. |
| Already-verified re-click | **NEEDS BACKEND CONFIRMATION** (table row 10) | Whatever the backend's real HTTP outcome is — if 2xx, the existing success state naturally handles it with no special-casing; if an error, the existing generic failure state handles it. No invented idempotency branch. |

Revisit this table (and split the generic failure state into real sub-states) only once the backend confirms distinct signals — tracked as a documented follow-up in Task T13's docs update, not built speculatively now.

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

Enumeration safety (§2); passwords never logged (no `console.log`/analytics on form values, no password value in any error object); verification tokens never logged, and never persisted beyond the single request that consumes them (read from the URL, used once, not written to any storage); no auth/session assumption introduced (§3); no secret in the client bundle (nothing changes here vs. FVS-001 — still zero `NEXT_PUBLIC_*`); `ApiError.raw`/`detail`/backend HTML never rendered (§12); mutations never auto-retry (§6/§7 — prevents duplicate-write risk); rate-limit responses are handled as a generic failure, not specially trusted/parsed beyond status; the verification token appears in the URL query string by necessity (backend-driven design, not a frontend choice) — note this plainly in T13's docs rather than attempting to "fix" an architecture this slice doesn't own.

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

**Contract-blocked:** T08 (row 2,3,5,6,7,15), T09 (row 8,9,10), T10 (row 11,12,13,14) — each task definition below states exactly which rows gate it.

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

**CONTRACT GATE:** Blocked on table rows 2 (field names), 3 (password rules), 5 (success status), 6 (success body), 7 (validation-error shape), 15 (auto-login). **Can proceed only once at least rows 2 and 6 are confirmed** (password rules can remain unconfirmed per §8's static-hint design; auto-login proceeds on the documented "no" assumption per §3 with a flagged caveat; validation-error shape can remain unconfirmed — server field errors simply surface via the generic `Alert` path per §12 until row 7 is confirmed).

**Purpose:** The real registration mutation and page, enumeration-safe by construction.
**Depends on:** T05, T06, T07.
**Files expected:** `src/lib/auth/useRegister.ts` (+ test), `src/app/register/page.tsx` (rewritten from skeleton), `page.test.tsx` (rewritten).
**Implementation actions:**
1. RED: mutation tests (mock `apiClient.post`, not `fetch`) for — successful submit resolves regardless of a mocked "new" vs. "duplicate" server response (enumeration-safety proof, §2); `retry: false` is actually configured (mirror T13a's own `getReadinessQueryOptions`-style exported-options testability pattern if useful); network failure surfaces `ApiError.kind:"network"` through to the page; double-submit is prevented (rapid double-click fires exactly one mutation).
2. RED: page tests — client-side validation blocks submit with empty/malformed fields using only the confirmed email-shape check (§1 row 4) and whatever server-confirmed fields exist at implementation time; successful submit shows the enumeration-safe "check your email" `Alert`, never branching copy; a server validation failure (mocked `ApiError.kind:"http"`) shows the generic message via `Alert`, never `.raw`/`.detail`.
3. GREEN: implement `useRegister` and wire `/register`'s real form (`Form` + `TextField` + `PasswordField` + `Button` + `Alert`), using a Zod schema built **only** from confirmed field names (row 2) — if a field's server-side rule is unconfirmed (row 3), the schema imposes no rule beyond "required"/the generic email-shape check.
**Do NOT:** add any field, limit, or rule not confirmed by the backend at implementation time; introduce auth/session state even though "no auto-login" is only an assumption — if that assumption is later proven wrong, that's a follow-up task, not something to hedge for here now; retry the mutation automatically.
**Tests:** TDD required, including the explicit enumeration-safety test from §2.
**Acceptance criteria:** Enumeration-safety test passes; double-submit test passes; no invented field/rule is present anywhere in the schema or copy.
**Verification:** `npm run test -- useRegister`, `npm run test -- register`, full suite, `npm run build`.
**Skills/tools:** `bekaa3d-api-contract` (mandatory — this is the highest contract-risk task in the slice), `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add registration mutation and page`

---

### FVS002-T09 — Verify-Email Flow

**CONTRACT GATE:** Blocked on table rows 8 (token transport), 9 (invalid/expired/used distinction), 10 (idempotent re-click). **Implementable now only as the single-generic-failure-state design (§13)** — do not wait for rows 9/10 to build a richer version; build the safe generic version once row 8 (token transport) is confirmed, and treat 9/10 as documented future refinements (§13, §17 doc note).

**Purpose:** The real verify-email mutation and page.
**Depends on:** T05, T06, T07.
**Files expected:** `src/lib/auth/useVerifyEmail.ts` (+ test), `src/app/verify-email/page.tsx` (rewritten), `page.test.tsx` (rewritten).
**Implementation actions:**
1. RED: mutation tests — valid token → success; any error (mocked `ApiError` of any `kind`) → the single generic failure state, never a guessed sub-state; missing/empty/malformed token (read from the URL search params per Next.js's App Router convention, e.g. `useSearchParams`) → generic failure state without ever calling the mutation with a garbage value.
2. RED: page tests — loading state while the mutation is in flight; success state with a link/prompt toward `/login` (a route this slice does not build, just links to — per §3); generic failure state with a resend CTA linking to `/verify-email/resend`.
3. GREEN: implement, using the exact token parameter name confirmed at implementation time (row 8) — **if still unconfirmed when this task starts, STOP and report rather than guessing a name.**
**Do NOT:** build three/four distinct failure UI states; persist the token anywhere beyond the single request that consumes it (§18); auto-retry the verify mutation.
**Tests:** TDD required, including the URL-edge-case tests from Review Focus item 4.
**Acceptance criteria:** Generic failure state correctly covers every non-success `ApiError.kind`; token is read once, used once, never stored.
**Verification:** `npm run test -- useVerifyEmail`, `npm run test -- verify-email`, full suite, `npm run build`.
**Skills/tools:** `bekaa3d-api-contract`, `bekaa3d-brand-ui`, `superpowers:test-driven-development`.
**Suggested commit message:** `feat: add email verification mutation and page`

---

### FVS002-T10 — Resend Flow + Cooldown

**CONTRACT GATE:** Submission half blocked on table rows 11 (field name), 12 (body shape only — enumeration-safe *behavior* is already confirmed). Countdown-display half additionally blocked on rows 13 (rate-limit status) and 14 (cooldown duration source) — **do not build the live countdown until row 14 is confirmed**; the enumeration-safe submission itself can land once row 11 is confirmed, independent of the countdown.

**Purpose:** The real resend mutation, page, and (once unblocked) cooldown countdown.
**Depends on:** T05, T06, T07.
**Files expected:** `src/lib/auth/useResendVerification.ts` (+ test), `src/lib/auth/useCooldown.ts` (+ test — pure logic, split out from the page per §11's "one small hook" guidance), `src/app/verify-email/resend/page.tsx` (rewritten), `page.test.tsx` (rewritten).
**Implementation actions:**
1. RED: mutation tests — identical enumeration-safe result rendered whether the mocked backend response implies the account existed or not (§2's explicit test requirement); `retry: false`.
2. RED (once row 14 is confirmed): `useCooldown` tests with fake timers — derives remaining time from an absolute deadline; announces once at start, once at completion, never per-tick; cleans up on unmount; survives a simulated throttled-timer gap without drifting past the real deadline (Review Focus item 3).
3. GREEN: implement submission first; implement cooldown only once its gate clears.
**Do NOT:** invent a cooldown duration (30s/60s/5min or otherwise) if row 14 is still unconfirmed when this task starts — land the submission-only version and leave the countdown for a follow-up continuation of this same task ID; special-case a guessed rate-limit status code.
**Tests:** TDD required for both halves, each gated as above.
**Acceptance criteria:** Enumeration-safety test passes for resend; if the countdown half lands, its accessibility-announcement test (start/completion only) passes.
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
2. Write the flow: navigate to `/register` → submit → see check-email state → navigate to `/verify-email?<confirmed-token-param>=<fake-token>` → see success state → see a link/prompt toward `/login`.
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
