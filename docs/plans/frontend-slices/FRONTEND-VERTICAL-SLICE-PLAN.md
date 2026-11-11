# Bekaa3D — Frontend Vertical Slice Implementation Plan

**Step:** Frontend companion to Step 18 (backend vertical slices)
**Date:** 2026-09-26
**Status:** Draft for review — analysis only, no implementation started
**Source of truth (backend):** `docs/plans/backend/vertical-slice-plan.md` (VS-001 → VS-040, approved)

> This plan follows the same philosophy as the backend plan: no "build all components / all pages / all services" phases. Each Frontend Vertical Slice (FVS) is a complete, mergeable, user-facing capability wired to real backend endpoints that already exist (or are being built in a parallel/prior slice on the agreed dependency order).

---

## 1. Purpose

Bekaa3D's backend team has frozen a 40-slice vertical implementation plan (VS-001–VS-040) covering auth, catalogue, uploads, commerce, negotiation, engagement and release hardening. This document is the frontend counterpart: it decomposes the same product into **Frontend Vertical Slices (FVS-001–FVS-046)**, each one a shippable UI capability that consumes specific, named backend endpoints from the source-of-truth plan.

This document does **not** redesign backend behavior, invent endpoints, or assume request/response shapes beyond what VS-001–VS-040 states. Anywhere the backend plan is silent on a contract detail the frontend needs, it is flagged explicitly in §17 as `NEEDS BACKEND CONFIRMATION` rather than guessed.

## 2. Source of Truth

- **Backend capabilities, endpoints, state machines, and business rules:** `docs/plans/backend/vertical-slice-plan.md`, VS-001–VS-040, is authoritative. If this document and the backend plan ever disagree, the backend plan wins and this document must be corrected.
- **SRS feature IDs (F-xxx):** referenced only as they appear in the backend plan; this document does not introduce new F-IDs.
- **Frontend-only features** (no backend slice): F-001 Home, F-002 Floating WhatsApp, F-003 About Us, F-011 WhatsApp click-to-chat, F-013 SEO rendering/sitemaps — called out in the backend plan §5 and covered in this plan under FM-B and §6/§13.

## 3. Frontend Architecture Assumptions

The backend plan does not mandate a frontend stack. The following are **assumptions made for this plan** and should be confirmed with the team before FVS-001 starts (see §17):

- **Framework:** React 18+ with TypeScript, using a meta-framework that supports server-side/static rendering for public pages (Next.js app router is assumed). Rationale: VS-013 explicitly hands SEO fields to "the frontend/rendering layer" (backend plan §5, F-013), and product/category pages need crawlable HTML rather than a client-only SPA shell — CSR-only React cannot satisfy the sitemap/SEO requirement in §16 without a rendering layer that can produce real HTML per URL.
- **Server state:** TanStack Query. Rationale: nearly every slice is a thin UI over a REST resource with cache invalidation needs (cart after checkout, orders after cancellation, offers after counter/accept) — a dedicated server-cache library avoids hand-rolled `useEffect` fetch/loading/error triplication across 46 slices. Introduced in FVS-001 because the very first slice (health check, then registration) needs request/loading/error handling.
- **Forms:** React Hook Form + Zod. Rationale: every write-heavy slice (register, checkout, product admin, offers) needs client-side schema validation that mirrors server Pydantic validation messages; Zod schemas double as TypeScript types for request payloads.
- **Styling:** Tailwind CSS + a small internal component layer (see §7), not a third-party component library, so admin tables/dialogs/timelines that don't exist off-the-shelf (order line timelines, offer negotiation threads) aren't fought.
- **State that is not server state** (auth session flag, cart badge count mirrored from query cache, UI-only toggles): React context + component state — no global client-state library (Redux/Zustand) is introduced unless a real slice proves the need. This matches the backend's own "don't scaffold ahead of need" rule (backend plan §7).
- **No library is added in this plan "for later."** Every dependency listed above is justified by the first slice that needs it, per the backend team's merge-strategy philosophy (§7 of the backend plan, mirrored in §20 here).
- **These are assumptions, not decisions.** Flagged as `NEEDS BACKEND/TEAM CONFIRMATION` in §17 — the frontend team should sign off on the framework/rendering choice before FVS-001 is scoped as a ticket.

## 4. Frontend Milestones

Frontend milestones mirror the backend's five milestones, but slice counts are **not** 1:1 — some backend slices need zero, one, or several frontend slices, explained per-slice in §5 and summarized here.

| Milestone | Backend milestone | FVS range | Exit condition |
|---|---|---|---|
| FM-A — Foundation & Auth | A (VS-001–009) | FVS-001–009 | A visitor can register, verify, log in, recover a password; an admin can log in with MFA; a customer can see their profile and notifications; an admin can manage business settings and customer accounts. |
| FM-B — Catalogue, Uploads & Storefront | B (VS-010–018) | FVS-010–022 | Admin can build a full catalogue (categories/products/images/STL versions); a visitor can discover, search, and view products; STL ownership/download works end-to-end; Home/About/WhatsApp/BYI/Contact are live. |
| FM-C — Commerce | C (VS-019–027) | FVS-023–032 | A customer can hold a mixed cart, check out, pay (mock provider), see verified (not merely redirected) payment status, view order history, and admin can fulfill, cancel, and refund orders. |
| FM-D — Negotiation & Engagement | D (VS-028–035) | FVS-033–040 | STL offer negotiation (submit → counter → accept/reject → checkout) works for both sides; reviews, wishlist, and BYI admin pipeline are live. |
| FM-E — Reporting, Data Rights & Release | E (VS-036–040) | FVS-041–046 | Admin analytics/audit are visible; customers can export/delete their data; the frontend passes its own release gate (SEO, error pages, accessibility, performance). |

Rationale for non-1:1 mapping is documented per-slice in §5; a full accounting of every VS-001–VS-040 against frontend work is in the traceability matrix, §18.

## 5. Frontend Vertical Slices

### Milestone FM-A — Foundation & Auth

#### FVS-001 — Frontend App Shell, Routing & API Client Foundation

**Priority:** P0 · **Risk:** High technical foundation · **Value:** Enables every later slice
**Depends on (frontend):** None
**Backend dependencies:** VS-001 (bootable API, health/readiness, correlation ID, RFC 9457 problem model)
**Backend endpoints used:**
```
GET /health/live
GET /health/ready
```
**Frontend capability:** Nothing user-facing yet beyond a bootable app shell — this is the one allowed foundation slice (see §3, §20). It stands up the app skeleton, the centralized API client, the base layout, and a route-not-found page, and proves the app can talk to the real backend.
**Routes:** `/` (placeholder shell), catch-all 404.
**Components:** `AppLayout` (header/footer skeleton), `ErrorBoundary`, `NotFoundPage`, `LoadingSpinner`, `Toast` (introduced here because the API client needs somewhere to report failures).
**State:** TanStack Query client instance (global); no auth/cart state yet.
**API integration:** Centralized `apiClient` wrapping `fetch`: base URL config, JSON parsing, RFC 9457 problem-response parsing into a typed `ApiError`, request-ID propagation for support/debugging, network-failure normalization. A dev-only banner calls `GET /health/ready` on load and shows a red banner if the API is unreachable — this is the only direct consumer of the health endpoints.
**API integration — error handling:** Every non-2xx response is parsed as a `Problem` object (`type/title/status/detail`, plus `errors[]` if present — exact validation-error shape is `NEEDS BACKEND CONFIRMATION`, see §17). Unparseable bodies fall back to a generic network-error `ApiError`.
**UX states:** App boot loading state; global error boundary fallback; 404 page; offline/network-unreachable banner.
**Responsive behavior:** Base layout grid works at 320px–1920px; header collapses to a hamburger below 768px (menu itself is empty until FVS-003/006 add auth-aware nav items).
**Accessibility:** Skip-to-content link; landmark regions (`header`, `main`, `footer`); focus-visible outline reset done once here so every later slice inherits it.
**Testing:** Unit tests for the `apiClient` (success parse, problem parse, network failure, timeout); component test for `ErrorBoundary` catching a thrown render error; smoke E2E that the app boots and hits `/health/ready`.
**Documentation:** README section on running the frontend against the local backend; API client usage doc for future slice authors.
**Mergeable outcome:** A clean checkout of the frontend repo boots, renders a shell, and proves connectivity to the real API — the same guarantee VS-001 gives the backend.

---

#### FVS-002 — Registration & Email Verification

**Priority:** P0 · **Risk:** High — first customer-facing flow · **Value:** First real customer capability
**Depends on (frontend):** FVS-001
**Backend dependencies:** VS-002 (registration, email verification, resend, outbox)
**Backend endpoints used:**
```
POST /api/v1/auth/register
POST /api/v1/auth/verify-email
POST /api/v1/auth/resend-verification
```
**Frontend capability:** A visitor can create an account, is told to check email (enumeration-safe wording — never "email already exists"), can click a verification link that lands on a confirmation page, and can request the verification email again if it didn't arrive.
**Routes:** `/register`, `/verify-email` (reads the token from the URL fragment, `#token=...` — **confirmed at FVS-002 BATCH 2 contract sync; not a query param**, see `docs/plans/frontend-slices/FVS-002-IMPLEMENTATION-PLAN.md` §1 row 8), `/verify-email/resend`.
**Components:** `Form`, `TextField`, `PasswordField` (with strength hint), `Button`, `Alert` — this is the slice that introduces the base form component set per §3/§18, because it's the first write flow in the app.
**State:** Form state (React Hook Form + Zod schema mirroring server field rules); no auth/session state — **confirmed at FVS-002 BATCH 2 contract sync (no longer just an assumption): registration does not log the user in, creates no frontend auth state, and sets no auth cookies** (they land on a "check your email" success state, then verify, then log in separately via FVS-003).
**API integration:** `POST /register` always returns the same "check your email" success shape regardless of whether the email existed, per the backend's enumeration-safe design — the UI must never branch copy on a "this email is taken" case. `POST /verify-email` with an invalid/expired/used token shows a distinct error with a resend CTA. `POST /resend-verification` is itself enumeration-safe and rate-limited; UI shows a generic "if that account exists, an email was sent" message either way.
**UX states:** Submitting; success (check-your-email); token invalid/expired/used; token already-verified (idempotent re-click); resend cooldown (rate-limited) with a visible countdown; network failure.
**Responsive behavior:** Single-column form, full-width inputs and CTA on mobile; centered card max-width 420px on desktop.
**Accessibility:** Labeled inputs with `aria-describedby` error text; error summary announced via `aria-live="polite"` on submit failure; password field has a visible show/hide toggle with correct `aria-pressed`; the resend-cooldown countdown is announced via `aria-live="polite"` at its start and completion (not on every tick) and is always paired with static "resend available at HH:MM:SS" text for screen-reader users, matching the treatment given to the deadline countdown in FVS-034.
**Testing:** Component tests for validation rules; integration tests mocking the three endpoints for success/enumeration/expired-token cases; E2E: register → (simulate email link) → verify → land on login prompt.
**Documentation:** Note in the account-flow doc that registration intentionally never confirms/denies existing accounts, so future contributors don't "fix" it.
**Mergeable outcome:** A visitor can complete the full registration-and-verification loop against the real backend outbox-driven email flow.

---

#### FVS-003 — Login, Logout & Session Management

**Priority:** P0 · **Risk:** High security · **Value:** Unlocks every authenticated slice
**Depends on (frontend):** FVS-001, FVS-002
**Backend dependencies:** VS-003 (login/logout/refresh, cookie-based session, CSRF, reuse detection)
**Backend endpoints used:**
```
POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/refresh
```
**Frontend capability:** A verified customer logs in, stays logged in across page loads via httpOnly cookies, is silently refreshed, and is logged out (locally and cross-tab). Protected routes redirect anonymous users to `/login` with a return-to path.
**Routes:** `/login`; no dedicated logout route (action, not a page).
**Components:** `LoginForm`, `ProtectedRoute` wrapper, `AuthProvider` (context exposing `user`/`isAuthenticated`/`isLoading`).
**State:** **Authentication state** — since the session lives in httpOnly cookies (per VS-003), the frontend cannot read the cookie directly; auth state is derived from calling `GET /api/v1/me` on boot (confirmed at FVS-003 BATCH 3A as an explicit, approved cross-slice dependency pulled forward from VS-006 — see `docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md` §1 — not a circular FVS-006-depends-on-FVS-003-depends-on-FVS-006 reference as an earlier draft of this line implied) and caching the result in TanStack Query, invalidated on login/logout. **CSRF state** — confirmed at BATCH 3A: a JS-readable `csrf_token` cookie, echoed in an `X-CSRF-Token` header on every CSRF-required mutating request (see the implementation plan §5) — no longer `NEEDS BACKEND CONFIRMATION`.
**API integration:** Login failures are enumeration-safe (generic "invalid email or password", no "user not found" vs "wrong password" distinction) and reflect the backend's progressive-delay/lockout behavior without the UI inventing its own lockout copy — it just surfaces whatever the server returns. On any `401` from any endpoint, the API client attempts one silent `POST /refresh`; if that also fails, it clears cached auth state and redirects to `/login?returnTo=...`. Reuse-detected sessions (old refresh token replayed) come back as a revoked session — treated identically to expired-session UX.
**UX states:** Submitting; invalid credentials; account locked/rate-limited (generic copy, no specifics that aid an attacker); session-expired mid-app (silent refresh, or forced re-login if refresh also fails); logged out confirmation.
**Responsive behavior:** Same single-column form pattern as FVS-002.
**Accessibility:** Same form a11y baseline as FVS-002; focus moves to the first invalid field on submit failure.
**Testing:** `ProtectedRoute` redirect behavior (unauthenticated → `/login`, authenticated → renders children); silent-refresh unit test (401 → refresh → retry original request); E2E: register → verify → login → visit a protected route → logout → protected route redirects again.
**Documentation:** Auth architecture note (see §8) linked from this slice.
**Mergeable outcome:** Session-aware routing works end-to-end against real cookie-based auth, including the refresh-on-401 path.

---

#### FVS-004 — Password Reset Flow

**Priority:** P0 · **Risk:** High security · **Value:** Account recovery
**Depends on (frontend):** FVS-003
**Backend dependencies:** VS-004 (password reset with global session revocation)
**Backend endpoints used:**
```
POST /api/v1/auth/password-reset/request
POST /api/v1/auth/password-reset/confirm
```
**Frontend capability:** A customer requests a reset link (enumeration-safe), follows the emailed link to a "set new password" page, and is told that all other sessions/devices were logged out.
**Routes:** `/forgot-password`, `/reset-password` (token query param).
**Components:** Reuses `Form`/`TextField`/`PasswordField`/`Alert` from FVS-002; no new primitives.
**State:** Form state only; on successful confirm, any cached auth state is cleared client-side since the backend revoked all sessions.
**API integration:** Request step always shows the same "if that account exists…" success message. Confirm step distinguishes expired/used token from password-policy validation failure (mirrors server rules — no separate client-invented policy).
**UX states:** Request submitted (generic success); confirm submitting; token invalid/expired/used; password fails policy; success → explicit "you've been logged out everywhere, please log in again" messaging, then redirect to `/login`.
**Responsive behavior:** Same as FVS-002/003 form pattern.
**Accessibility:** Same baseline; success message uses `role="status"`.
**Testing:** Integration tests for both enumeration-safe and token-invalid paths; E2E: request → confirm with token → forced re-login.
**Documentation:** Cross-reference in the auth architecture doc that reset always invalidates all sessions, so support/QA don't treat it as a bug.
**Mergeable outcome:** A customer can recover a lost password without the UI leaking account existence, and understands why they were logged out everywhere.

---

#### FVS-005 — Admin Login & MFA

**Priority:** P0 · **Risk:** High privileged security · **Value:** Safely unlocks all admin frontend work
**Depends on (frontend):** FVS-003
**Backend dependencies:** VS-005 (admin MFA, isolated admin security boundary)
**Backend endpoints used:**
```
POST /api/v1/auth/mfa/setup
POST /api/v1/auth/mfa/setup/confirm
POST /api/v1/auth/mfa/verify
POST /api/v1/auth/mfa/recovery-codes/regenerate
```
**Frontend capability:** An admin logs in (reusing FVS-003's login), is challenged for a TOTP code, can enroll MFA the first time (QR/secret + confirm), can use a one-time recovery code if locked out of their authenticator, and can regenerate recovery codes. All `/admin/*` routes are inaccessible (rendered as a genuine 404, not a 403 — matching the backend's non-admin-sees-404 rule) to non-admin users.
**Routes:** `/admin/login`, `/admin/mfa/setup`, `/admin/mfa/verify`, `/admin/mfa/recovery-codes`; `/admin/*` layout guard.
**Components:** `AdminProtectedRoute` (separate from customer `ProtectedRoute` — checks admin role, not just auth), `MfaChallengeForm`, `MfaSetupWizard` (QR code + confirmation code), `RecoveryCodeList` (one-time reveal, copy-to-clipboard, printable).
**State:** Admin auth state layered on top of FVS-003's `AuthProvider` (`isAdmin`, `mfaVerified` for the session); recovery codes are shown exactly once client-side and never re-fetchable — the component must not cache them beyond the reveal screen.
**API integration:** MFA verify failures are generic ("invalid code") without revealing whether the account itself is valid — same enumeration-safety principle as customer auth. A non-admin hitting any `/admin` frontend route renders the app's standard 404 page, not a "forbidden" page, to match the backend's route-hiding behavior.
**UX states:** Setup (QR + confirm code) vs already-enrolled (challenge only); invalid TOTP; recovery-code accepted (forces re-enrollment prompt afterward per typical MFA UX — confirm backend supports this, else just log in); non-admin → 404; admin session without MFA yet completed this session → forced to `/admin/mfa/verify` before any admin route renders.
**Responsive behavior:** Admin login/MFA screens are still mobile-usable (an admin may approve something from a phone) even though the rest of `/admin` is desktop-first (see FM-C/D admin slices).
**Accessibility:** QR code has a text-equivalent secret key for screen-reader/non-camera setup; recovery codes are presented as a selectable, screen-reader-readable list, not an image.
**Testing:** `AdminProtectedRoute` unit tests (non-admin → 404, admin-without-MFA → redirect to challenge, admin-with-MFA → renders); E2E: admin login → MFA setup → confirm → land on admin dashboard placeholder; E2E: non-admin visits `/admin/products` → sees 404.
**Documentation:** Admin enrollment runbook (linked to backend's own MFA runbook from VS-005).
**Mergeable outcome:** Every subsequent admin slice can assume `AdminProtectedRoute` already enforces MFA — no per-page security reimplementation.

---

#### FVS-006 — Customer Account Shell & Profile

**Priority:** P1 · **Risk:** Low · **Value:** Foundation for every `/account/*` slice
**Depends on (frontend):** FVS-003
**Backend dependencies:** VS-006 (read-only customer profile)
**Backend endpoints used:**
```
GET /api/v1/me
```
**Frontend capability:** A logged-in customer sees an account layout with a left-nav (Profile, Orders, Downloads, Offers, Wishlist, Reviews, Addresses, Notifications — links populated as their slices land) and a read-only profile page (email, verification status, account state). No editable fields exist in V1 because the backend defines none (VS-006 is explicitly read-only) — the frontend must not invent an edit form.
**Routes:** `/account` (redirects to `/account/profile`), `/account/profile`.
**Components:** `AccountLayout` (nav + content region), `ProfileCard`.
**State:** `GET /me` result is the canonical "who am I" query, cached and shared by `AuthProvider` (FVS-003) so login-state and profile-view share one source of truth instead of two separate fetches.
**API integration:** Straightforward cached read; 401 bounces to login via the FVS-003 mechanism; no mutation path exists this slice.
**UX states:** Loading skeleton for the profile card; error state (retry button) if `/me` fails after a session is otherwise considered valid; unverified-account banner if `email_verified` is false, linking to resend-verification (FVS-002).
**Responsive behavior:** Account nav becomes a horizontal scrollable tab bar or a collapsible drawer below 768px instead of a fixed sidebar.
**Accessibility:** Account nav is a proper `<nav>` with `aria-current="page"` on the active section; content region is a landmark so screen-reader users can jump past the nav.
**Testing:** Component test for unverified banner visibility logic; integration test for `/me` loading/error/success; E2E: log in → land on profile → see own email.
**Documentation:** Note explaining why there's no "edit profile" form (matches backend DoD — no invented mutable fields).
**Mergeable outcome:** Every later `/account/*` slice (orders, downloads, offers, wishlist, reviews, addresses, notifications) plugs into this shell's nav instead of building its own layout.

---

#### FVS-007 — Admin Business Settings Editor

**Priority:** P0 · **Risk:** Medium — feeds many later slices' business rules · **Value:** Operational control
**Depends on (frontend):** FVS-005
**Backend dependencies:** VS-007 (typed settings editor, safe public settings)
**Backend endpoints used:**
```
GET /api/v1/admin/settings/{key}
PATCH /api/v1/admin/settings/{key}
GET /api/v1/admin/settings
GET /api/v1/settings/public
```
*(The settings-list path is backend prose only ("list settings") — placeholder, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** An admin views and edits every business-tunable setting (accepting-orders toggle, offer windows/cooldown/floor, checkout hold, unverified-purge window, daily download cap, free-shipping threshold, pickup address/hours, WhatsApp number) through typed controls (boolean toggle, number input with range, string) rather than a raw JSON editor — the UI renders a control per setting's declared type, it does not assume a fixed hand-built form per key so new settings the backend adds later don't require a frontend redeploy to appear (a generic typed-field renderer keyed by the settings list response).
**Routes:** `/admin/settings`.
**Components:** `SettingsTable`/`SettingRow` (renders `BooleanField`/`NumberField`/`TextField` based on the setting's declared type), `ConfirmDialog` for changes that affect live commerce (e.g., "accepting orders" off).
**State:** Settings list is server state (TanStack Query), invalidated on every successful `PATCH`; no local draft persistence beyond the open edit row.
**API integration:** `PATCH` validation errors (wrong type/out-of-range) render inline under the specific field using the server's error message, not a client-invented one. Every change is expected to be audited server-side — no separate frontend audit UI needed here (that's FVS-042).
**UX states:** Loading list; per-row save/saving/saved/error; optimistic toggle for booleans with rollback on server rejection; confirmation dialog before saving a setting flagged as high-impact (client-side list of "confirm before save" keys, e.g., accepting-orders).
**Responsive behavior:** Table becomes a stacked card list per setting below 768px (label, control, and inline error stacked instead of columns).
**Accessibility:** Each control has a programmatically associated label and description (the setting's help text); toggle switches expose `role="switch"` and `aria-checked`.
**Testing:** Component tests per field-type renderer; integration test for validation-error display; E2E: admin changes free-shipping threshold → value persists on reload.
**Documentation:** Mirrors the backend's setting-key registry doc so frontend field labels/help text stay in sync with what each key actually controls.
**Mergeable outcome:** Every later slice that depends on a business setting (checkout free-shipping, offer floor/cooldown, download cap, WhatsApp button) already has an admin surface to configure it before that slice ships.

**Also implicitly delivered:** `GET /api/v1/settings/public` has no dedicated admin UI — it's a cross-cutting read consumed directly by FVS-014 (product WhatsApp), FVS-022 (floating WhatsApp/home), and FVS-025/026 (free-shipping threshold display). It is not a separate FVS; see §6.

---

#### FVS-008 — Notification Center

**Priority:** P1 · **Risk:** Low · **Value:** Reusable channel every later slice's events land in
**Depends on (frontend):** FVS-006
**Backend dependencies:** VS-008 (in-app notifications)
**Backend endpoints used:**
```
GET /api/v1/me/notifications
PATCH /api/v1/me/notifications/{id}
```
**Frontend capability:** A logged-in customer sees an unread-count badge (header bell icon) and a notification list (`/account/notifications`) they can mark read/unread. This slice ships with **zero concrete notification types rendered specially** — VS-008 itself defines only the transport; concrete event copy/icons are added by the slice that introduces each event (order paid, offer countered, etc.), exactly mirroring the backend's own incremental approach.
**Routes:** `/account/notifications` (added to the FVS-006 account nav).
**Components:** `NotificationBell` (header), `NotificationList`, `NotificationItem` (generic renderer keyed by a `type` field, falling back to a plain title/body render for types the frontend doesn't yet have custom copy for — so new backend event types never crash the UI).
**State:** Paginated server state; unread count is a lightweight derived/polling query (poll interval, not push — nothing in VS-008 or anywhere else in `docs/plans/backend/vertical-slice-plan.md` mentions a WebSocket/push mechanism, so none is assumed, per §7/§9's shared-architecture rule against inventing realtime transport).
**API integration:** Bounded pagination (exact shape `NEEDS BACKEND CONFIRMATION`, §17); `PATCH` to toggle read/unread is optimistic with rollback on failure.
**UX states:** Empty inbox; loading; error/retry; unread vs read visual distinction; pagination/"load more".
**Responsive behavior:** Bell dropdown on desktop; full-screen sheet on mobile instead of a small anchored popover.
**Accessibility:** Bell button has `aria-label="Notifications, N unread"`; list items are a proper list (`<ul>/<li>`) with read-state conveyed by text, not color alone.
**Testing:** Generic-renderer fallback test (unknown `type` still renders safely); mark-read optimistic-update/rollback test; E2E: notification appears after a later slice's action (deferred until such a slice exists) — for this slice alone, E2E covers list/read/unread only.
**Documentation:** Contract doc listing known `type` values as they're added by later slices (payment paid, offer countered, order shipped, etc.) — a living table this slice starts and later slices append to.
**Mergeable outcome:** Every later commerce/negotiation slice can emit a real in-app notification without the frontend needing a redesign — it already has a generic renderer and an inbox.

---

#### FVS-009 — Admin Customer Management

**Priority:** P1 · **Risk:** Medium security/PII · **Value:** Core admin operations
**Depends on (frontend):** FVS-005
**Backend dependencies:** VS-009 (admin user management)
**Backend endpoints used:**
```
GET /api/v1/admin/users
GET /api/v1/admin/users/{id}
PATCH /api/v1/admin/users/{id}
```
**Frontend capability:** An admin searches/paginates the customer list, opens a customer detail view (account state, verification status), and activates/deactivates an account — no other field is editable, matching the backend's "only approved fields" rule.
**Routes:** `/admin/customers`, `/admin/customers/:id`.
**Components:** `AdminTable` (introduced here — first admin list-with-search-and-pagination; reused by every later admin list slice: orders, offers, reviews, BYI, audit log), `StatusBadge` (active/deactivated), `ConfirmDialog` (deactivation confirmation, since it blocks the customer's login).
**State:** Server state via TanStack Query with URL-synced search/pagination params (`?q=&page=`) so a filtered view is shareable/bookmarkable and back-button-safe.
**API integration:** Deactivation is treated as a state-changing action requiring confirmation, not a plain checkbox toggle, since it immediately blocks the customer; PII fields displayed are limited to what the backend's `AdminUserDetail` schema returns — the frontend does not fetch or display anything beyond that (e.g., no raw password hash, no internal notes not modeled by this endpoint).
**UX states:** Empty search results; loading table skeleton; deactivate confirm/success/error; pagination boundaries.
**Responsive behavior:** `AdminTable` establishes the pattern used everywhere in admin: horizontal scroll container on narrow viewports rather than column-dropping, since admin is desktop-first but must not be unusable on a tablet.
**Accessibility:** Table has proper `<th scope="col">` headers; row actions are reachable by keyboard (not hover-only); confirm dialog traps focus and returns focus to the triggering button on close.
**Testing:** `AdminTable` component tests (sorting/pagination/search wiring) since it's reused everywhere; integration test for deactivate flow; E2E: admin searches a customer → deactivates → customer can no longer log in (cross-checked against FVS-003's login test).
**Documentation:** Note on which fields are editable and why (mirrors backend's PII-handling doc).
**Mergeable outcome:** Admin can manage customer accounts without database access, and the `AdminTable`/`StatusBadge`/`ConfirmDialog` primitives it introduces are ready for every later admin list slice.

### Milestone FM-B — Catalogue, Uploads & Storefront

#### FVS-010 — Admin Reference Data (Categories, Materials, Colours)

**Priority:** P1 · **Risk:** Low · **Value:** Prerequisite for product creation
**Depends on (frontend):** FVS-005, FVS-009 (reuses `AdminTable`)
**Backend dependencies:** VS-010
**Backend endpoints used:**
```
GET/POST/PATCH/DELETE /api/v1/admin/categories
GET/POST/PATCH/DELETE /api/v1/admin/materials
GET/POST/PATCH/DELETE /api/v1/admin/colours
GET /api/v1/categories
GET /api/v1/materials
GET /api/v1/colours
```
(exact admin path shapes per the backend's "admin CRUD groups" — confirm final paths against OpenAPI when available, §17)
**Frontend capability:** Admin creates/edits/archives categories, materials, and colours — three near-identical CRUD screens sharing one generic component rather than three bespoke ones, since the backend also treats them as "plain reference-data tables" (VS-010).
**Routes:** `/admin/categories`, `/admin/materials`, `/admin/colours`.
**Components:** `ReferenceDataManager` (generic list+create+edit+archive, configured per entity: label, slug-or-not, extra fields like colour hex swatch).
**State:** Server state per entity; archived items remain visible in the admin list (struck-through/badge) but excluded from public consumption (FVS-013 facets).
**API integration:** Slug-collision errors surface inline on the name/slug field; archive is a soft action (not delete) reflected as a status badge, not row removal.
**UX states:** Empty state ("no categories yet — create one"); slug-collision validation error; archive confirm; archived-item visual state.
**Responsive behavior:** Same stacked-card pattern as FVS-007 below 768px.
**Accessibility:** Colour swatches include a text label, never color-only identification (WCAG 1.4.1).
**Testing:** `ReferenceDataManager` tests parameterized across all three entities; E2E: create category → appears in product-creation dropdown (cross-checked in FVS-011).
**Documentation:** Admin reference-data workflow, mirroring backend doc.
**Mergeable outcome:** Admin can populate controlled facet values before any product references them.

---

#### FVS-011 — Admin Product Management

**Priority:** P0 · **Risk:** High — central catalogue authoring · **Value:** Core sellable catalogue
**Depends on (frontend):** FVS-010
**Backend dependencies:** VS-011
**Backend endpoints used:**
```
GET /api/v1/admin/products
POST /api/v1/admin/products
GET /api/v1/admin/products/{id}
PATCH /api/v1/admin/products/{id}
DELETE /api/v1/admin/products/{id}
```
*(VS-011's endpoint line is prose only ("Admin product list/create/detail/update/delete") — every path above is a frontend-constructed placeholder, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin creates and edits both physical and STL products through **one product form that adapts its fields to the immutable product-type choice** made at creation (physical-only fields like purchase mode/availability are hidden/disabled for STL and vice versa) — the type cannot be changed after creation, and the UI must disable/hide the type selector on edit rather than pretend it's editable.
**Routes:** `/admin/products`, `/admin/products/new`, `/admin/products/:id/edit`.
**Components:** `ProductForm` (type-aware field groups), `ProductTypeSelector` (create-only, locked on edit), `MoneyInput` (cents-safe input, introduced here since VS-011 requires integer-cents money — this component is reused by every later price-entering UI: offers, refunds), `AdminTable` (product list, reused from FVS-009).
**State:** Draft form state via React Hook Form/Zod, schema branching on product type; server state for the product list/detail.
**API integration:** Server validation errors for type-mismatched fields (e.g., "purchase mode not allowed for STL") render on the specific field, not as a generic toast, so the admin understands the type constraint. Slug-reuse-after-soft-delete is a server rule the UI doesn't need to special-case beyond showing whatever error/success the server returns.
**UX states:** Create vs edit mode; type-locked-after-creation notice; validation errors per invalid type/field combination; soft-delete confirm; publish/unpublish state (visibility toggle) if modeled by the product's fields.
**Responsive behavior:** Long form uses a sticky section-nav (General / Pricing / Category-Material-Colour / Publication) on desktop, collapses to a linear scroll with in-page anchors on mobile — admin is still expected to sometimes triage from a tablet.
**Accessibility:** `MoneyInput` announces the currency unit via `aria-label`, not placeholder text alone; type-locked selector communicates why it's disabled via `aria-describedby`, not just a grayed-out look.
**Testing:** `MoneyInput` unit tests (cents rounding, negative rejection); `ProductForm` tests per type branch; integration test for slug-collision and type-mismatch server errors; E2E: create a physical product → appears in admin list → edit → type selector is locked.
**Documentation:** Product type field matrix mirrored from the backend doc, so admins/support know which fields apply to which type.
**Mergeable outcome:** Admin can build a valid, type-correct catalogue entry end-to-end without touching the database — `MoneyInput` and `AdminTable` are now proven for every later money-entry/list slice.

---

#### FVS-012 — Admin Product Image Management

**Priority:** P0 · **Risk:** High upload/security integration · **Value:** Required product presentation; proves the reusable upload pattern
**Depends on (frontend):** FVS-011
**Backend dependencies:** VS-012 (shared storage/scanning ports proven here first)
**Backend endpoints used:**
```
POST /api/v1/admin/products/{id}/images
PATCH /api/v1/admin/products/{id}/images/{image_id}
DELETE /api/v1/admin/products/{id}/images/{image_id}
```
(VS-012's endpoint line is entirely prose — the upload/update/delete paths above and the cover-select/reorder endpoints alike are frontend-constructed placeholders, `NEEDS BACKEND CONFIRMATION`, §17)
**Frontend capability:** Admin uploads multiple product images (drag-and-drop or file picker), sees per-file upload progress, marks one as cover, and drag-reorders the gallery. This is **the slice that introduces the reusable `FileUploader` component** (§11) — every later upload slice (STL assets, BYI attachments) configures the same component rather than rebuilding upload UX.
**Routes:** Embedded in `/admin/products/:id/edit` (an "Images" section/tab), not a standalone route.
**Components:** `FileUploader` (progress bar per file, client-side type/size pre-check mirroring server limits, retry-on-failure, cancel-in-flight), `ImageGallery` (drag-reorder grid, cover badge/star toggle).
**State:** Upload queue is local component state (per-file progress/status); once uploaded, the image list is server state, invalidated after upload/reorder/delete.
**API integration:** The backend inspects file content (not extension) and runs malware scanning — the frontend must not claim "upload complete" until the server confirms acceptance; a file that fails server-side scanning/validation shows a specific rejection reason returned by the API, not a generic "upload failed." Reorder sends the new order to the server rather than trusting client-side order as final (server remains authority on persisted order).
**UX states:** Idle drop-zone; uploading (per-file progress); server rejected (bad type/oversized/failed scan) with reason; cover-selection race (server rejects a second concurrent cover-set — UI refetches and shows the actual current cover); reorder saving/error (revert on failure); delete confirm.
**Responsive behavior:** Grid becomes a single-column reorderable list with up/down buttons on touch devices where drag-and-drop reordering is unreliable, rather than disabling reorder entirely.
**Accessibility:** Drag-reorder has a keyboard-operable alternative (move up/down buttons) — drag-only reordering is not acceptable a11y; upload progress is announced via `aria-live="polite"`.
**Testing:** `FileUploader` unit tests (progress, cancel, client-side pre-check rejecting an obviously-wrong type before hitting the network); integration test for server-rejection-reason display; E2E: upload two images → set cover → reorder → reload shows persisted order.
**Documentation:** Upload limits (size/count/type) surfaced in the UI copy, sourced from the same limits the backend documents — not independently invented numbers.
**Mergeable outcome:** One real upload path (`FileUploader`) is proven end-to-end against the backend's storage/scanning integration before STL and BYI uploads reuse it.

---

#### FVS-013 — Public Catalogue & Product Discovery

**Priority:** P0 · **Risk:** Medium — first storefront experience · **Value:** Core discovery funnel
**Depends on (frontend):** FVS-001; consumes FVS-010's public reference-data endpoints
**Backend dependencies:** VS-013, VS-010 (public facet lists)
**Backend endpoints used:**
```
GET /api/v1/products
GET /api/v1/search/suggestions
GET /api/v1/categories
GET /api/v1/materials
GET /api/v1/colours
```
**Frontend capability:** A visitor browses the product grid, searches (with typo-tolerant suggestions), filters by category/material/colour, sorts (including "most downloaded" only where the backend allows it), and pages through results — all reflected in the URL so the view is shareable and back-button-safe.
**Routes:** `/shop`, `/shop?category=&material=&colour=&sort=&q=&cursor=`.
**Components:** `ProductGrid`, `ProductCard`, `FilterPanel` (facet checkboxes sourced from live category/material/colour lists, not hardcoded), `SortSelect` (allowlisted options only — never renders a sort option the backend doesn't support), `SearchBar` (debounced, wired to suggestions), `Pagination`/`LoadMore` (cursor-based — see §17 for exact cursor contract confirmation), `EmptyState`.
**State:** **URL state** is the source of truth for filters/sort/search/cursor (not component state) so the browser back button and shared links work; **server state** is the product page itself (TanStack Query keyed by the full query-string).
**API integration:** Filters are combined with AND semantics per the backend; the UI must not imply OR-across-facets in its copy/checkboxes. Cursor pagination means "page numbers" are not truly random-access — UI presents "load more" or "next" rather than a numbered page picker unless the exact cursor contract (§17) turns out to support jump-to-page.
**UX states:** Loading grid skeleton; empty results (no products match filters, with a "clear filters" CTA); search-typo tolerance (still shows results for a near-miss query); network error with retry; end-of-results.
**Responsive behavior:** Desktop: filter panel as a persistent left sidebar, 3–4 column grid. Tablet: 2-column grid, filters in a collapsible panel. Mobile: 1–2 column grid, filters open as a full-screen sheet/modal triggered by a "Filters" button, sort as a bottom-sheet select.
**Accessibility:** Filter checkboxes are a real fieldset/legend group per facet; applied-filter chips are individually removable and keyboard-reachable; grid is a list semantically (`role="list"`/`listitem` if not native `<ul>`), each card's primary link wraps the whole clickable card without nesting interactive elements incorrectly; `SortSelect` is a native `<select>` (or a custom listbox with full `role="listbox"`/`aria-activedescendant`/arrow-key support if a native select can't carry the visual design) — never a div-based dropdown with mouse-only interaction.
**Testing:** URL-state sync unit tests (filters round-trip through the URL); `FilterPanel`/`SortSelect` component tests (never renders disallowed sort values); integration tests mocking empty/paginated/error responses; E2E: search → filter → sort → open a product → back button restores the exact prior filtered view.
**Documentation:** SEO metadata for list/category pages is specified in §13, not duplicated here.
**Mergeable outcome:** A visitor can fully discover the catalogue end-to-end against the real search/filter/sort backend, with shareable, resumable URLs.

---

#### FVS-014 — Public Product Detail Page

**Priority:** P0 · **Risk:** Medium · **Value:** Where discovery converts to intent to buy/negotiate
**Depends on (frontend):** FVS-013
**Backend dependencies:** VS-013 (product detail + SEO fields), VS-007 (public settings for WhatsApp number)
**Backend endpoints used:**
```
GET /api/v1/products/{slug}
GET /api/v1/settings/public
```
**Frontend capability:** A visitor views full product detail — image gallery, description, price, category/material/colour, and type-specific panels: physical shows purchase mode/availability/shipping-eligibility hints; STL shows license/ownership-relevant copy and, for authenticated owners, points toward their library (FVS-020) rather than duplicating purchase UI. Includes the WhatsApp click-to-chat action (F-011) built from this product's data plus the public WhatsApp number setting — no order/API write happens on click, it only opens a `wa.me` link with a prefilled message.
**Routes:** `/shop/:slug`.
**Components:** `ImageGallery` (uses the ordered/cover images from FVS-012's data), `ProductTypeBadge`, `PriceDisplay` (introduced here — cents-safe, currency-aware; reused by cart/checkout/offers), `WhatsAppChatButton`, `AddToCartButton` (wired to FVS-025 once that slice lands — this slice ships the button disabled/hidden if cart doesn't exist yet, per dependency order; for an anonymous visitor the button is always enabled and, on click, redirects to `/login?returnTo=<product-url>` per FVS-003's `ProtectedRoute` pattern rather than silently failing or attempting a guest cart — VS-020's cart model is user-scoped only, no guest-cart concept exists), `UnavailableNotice` (WhatsApp-only or out-of-availability physical products).
**State:** Server state for product detail (keyed by slug); no client-only state beyond gallery selection (which image is active).
**API integration:** A slug for a hidden/deleted/archived-category product returns 404 from the backend — rendered as the app's real not-found page, not a soft "unavailable" banner, matching VS-013's exclusion rule. Unavailable-but-still-listed physical products remain visible (per VS-013) with a clear "currently unavailable" state instead of a purchase action.
**UX states:** Loading; 404 (removed/hidden product); unavailable physical product (no purchase CTA, WhatsApp CTA still present if applicable); WhatsApp-only product (no cart CTA at all, WhatsApp is the only path); STL already-owned-by-viewer (CTA points to library/download instead of purchase); loading gallery images.
**Responsive behavior:** Desktop: two-column (gallery left, info/actions right, sticky on scroll). Mobile: stacked, gallery as a swipeable carousel, sticky bottom action bar for the primary CTA (buy/add-to-cart/WhatsApp).
**Accessibility:** Gallery thumbnails are keyboard-navigable with visible focus; the active/main image has descriptive `alt` text sourced from product data; sticky mobile action bar doesn't obscure focusable content underneath (tested with keyboard nav + zoom).
**Testing:** Type-specific panel rendering tests (physical vs STL vs WhatsApp-only vs owned-STL); 404 routing test; E2E: browse → open product → click WhatsApp → correct `wa.me` link with product name in the prefilled text.
**Documentation:** Per-page SEO/OG/canonical/structured-data implementation lives in §13; this slice implements what §13 specifies for product pages.
**Mergeable outcome:** A visitor can fully evaluate any product type and reach the correct next action (buy, WhatsApp, or "already owned") before cart/checkout exist.

---

#### FVS-015 — Bring Your Idea (BYI) Public Submission

**Priority:** P0 · **Risk:** High guest-upload security · **Value:** High-value lead channel
**Depends on (frontend):** FVS-012 (reuses `FileUploader`)
**Backend dependencies:** VS-014 (captcha, rate limiting, private attachments)
**Backend endpoints used:**
```
POST /api/v1/custom-requests
```
**Frontend capability:** A guest (no login required) submits a custom-print idea with description and attachments, protected by a captcha widget, and receives a safe receipt (no sensitive detail echoed back beyond confirmation).
**Routes:** `/bring-your-idea`.
**Components:** `BringYourIdeaForm`, `CaptchaWidget` (provider TBD — `NEEDS BACKEND CONFIRMATION`, §17), reuses `FileUploader` from FVS-012 configured for this endpoint's stricter count/size limits.
**State:** Form state only; no auth/session involvement (guest flow).
**API integration:** Rate-limit (429) and captcha-failure responses render distinct, non-technical guidance ("please try again in a few minutes" vs "please complete the verification"); oversized/too-many/invalid-type attachments are pre-checked client-side (mirroring server limits) before upload attempt, then re-validated server-side with the server's rejection reason shown if it disagrees.
**UX states:** Submitting; captcha failed; rate-limited (429) with retry guidance; attachment rejected (type/size/count); success receipt; network/disk failure on the server surfaced generically (no internal error detail leaked).
**Responsive behavior:** Full-width single-column form on mobile; attachment thumbnails wrap into a grid on wider screens.
**Accessibility:** Captcha widget's accessible/audio-challenge fallback is preserved (don't wrap it in something that breaks its own a11y affordances); file list announces added/removed files via `aria-live`.
**Testing:** Client-side pre-check unit tests (size/count/type); integration tests for captcha-failure and rate-limit response handling; E2E: submit with one valid attachment → receive receipt.
**Documentation:** Public form limits and retention-window copy sourced from the backend's setting, not hardcoded independently (cross-reference FVS-007).
**Mergeable outcome:** The riskiest unauthenticated upload path in the product is proven in the UI, reusing the same hardened uploader component as admin image upload.

---

#### FVS-016 — Public Contact Form

**Priority:** P1 · **Risk:** Medium abuse surface · **Value:** Direct lead/support channel
**Depends on (frontend):** FVS-015 (reuses captcha pattern)
**Backend dependencies:** VS-015 (guest submission half)
**Backend endpoints used:**
```
POST /api/v1/contact-messages
```
**Frontend capability:** A visitor sends a contact message (name/email/message) protected by the same captcha/rate-limit pattern as BYI, with a safe receipt confirmation.
**Routes:** `/contact`.
**Components:** `ContactForm`, reuses `CaptchaWidget` from FVS-015.
**State:** Form state only.
**API integration:** Same captcha/rate-limit UX pattern as FVS-015 — deliberately consistent so users only learn this interaction once.
**UX states:** Submitting; captcha failed; rate-limited; success receipt; network failure.
**Responsive behavior:** Simple single-column form at all widths; no special breakpoints needed.
**Accessibility:** Same baseline as FVS-015's form.
**Testing:** Integration tests for captcha/rate-limit paths; E2E happy path.
**Documentation:** None beyond inline form copy.
**Mergeable outcome:** Visitors have a working, abuse-resistant contact channel independent of BYI.

---

#### FVS-017 — Admin Contact Message Queue

**Priority:** P1 · **Risk:** Low · **Value:** Operationalizes the contact channel
**Depends on (frontend):** FVS-009 (reuses `AdminTable`), FVS-016
**Backend dependencies:** VS-015 (admin half)
**Backend endpoints used:**
```
GET /api/v1/admin/contact-messages
GET /api/v1/admin/contact-messages/{id}
PATCH /api/v1/admin/contact-messages/{id}
```
*(VS-015's admin half is prose only — placeholders above, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin lists, reads, and transitions contact messages through new → read → replied → archived.
**Routes:** `/admin/contact-messages`, `/admin/contact-messages/:id`.
**Components:** `AdminTable` (reused), `StatusBadge` (reused, new status set), `MessageDetail`.
**State:** Server state with URL-synced status filter.
**API integration:** Status transition is an explicit action (button per legal next state), not a free-text/dropdown status field, mirroring the backend's controlled state model.
**UX states:** Empty queue; loading; status-transition success/error; filter-by-status.
**Responsive behavior:** `AdminTable` pattern (horizontal scroll on narrow viewports).
**Accessibility:** Status transition buttons have clear accessible names ("Mark replied", not just an icon).
**Testing:** Integration test for legal-transition-only action set; E2E: message arrives → admin marks read → replied → archived.
**Documentation:** Queue-state reference for support staff.
**Mergeable outcome:** Admin operates the contact channel without database access.

---

#### FVS-018 — Admin STL Asset Upload & Version Management

**Priority:** P0 · **Risk:** High digital-asset security · **Value:** Prerequisite for all STL revenue
**Depends on (frontend):** FVS-011, FVS-012 (reuses `FileUploader`)
**Backend dependencies:** VS-016
**Backend endpoints used:**
```
GET /api/v1/admin/products/{id}/asset-versions
POST /api/v1/admin/products/{id}/asset-versions
GET /api/v1/admin/products/{id}/asset-versions/{version_id}
POST /api/v1/admin/products/{id}/asset-versions/{version_id}/publish
```
*(VS-016's endpoint line is prose only — placeholders above, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin uploads one-or-more files as a new asset version bundle for an STL product, watches per-file scan status (pending/clean/infected), and — only once every file in the bundle is clean — publishes the version atomically as "current." Previous versions remain visible (read-only, superseded) rather than disappearing.
**Routes:** `/admin/products/:id/assets` (STL products only — the product form from FVS-011 shows this tab only when type is STL).
**Components:** `AssetVersionUploader` (configures `FileUploader` for multi-file bundles with per-file scan-status polling), `AssetVersionList` (current vs superseded, publish action gated on all-clean), `ScanStatusBadge`.
**State:** Server state for version list/detail; scan status is polled (no push mechanism exists per current backend contract) until all files in a pending version resolve to clean/infected.
**API integration:** The Publish action is disabled (not just discouraged) while any file in the version is pending/infected — the button's disabled state is server-truth-driven, not a client guess, refetching status rather than assuming a fixed scan duration. A race where another admin publishes a different version concurrently is surfaced by refetching "current version" after any publish attempt fails.
**UX states:** Upload-in-progress; scanning (polling, spinner per file); infected-file rejection (bundle cannot publish, specific file flagged); all-clean → publish enabled; publish success (version now marked current, previous marked superseded in the UI); publish race/conflict; direct-URL visit to this route for a non-STL product (VS-016's own test requires "product must be STL" — render the app's standard not-found/wrong-type message rather than an empty or broken asset list).
**Responsive behavior:** Admin desktop-first; still usable in a pinch on tablet with a stacked file list instead of a table.
**Accessibility:** Scan-status polling updates are announced via `aria-live="polite"` so screen-reader admins aren't left guessing; disabled publish button has a visible/announced reason ("waiting for scan to complete").
**Testing:** Publish-button gating unit tests (disabled while any file non-clean); polling logic tests (stops once resolved); E2E: upload bundle → wait for clean → publish → previous version shows as superseded.
**Documentation:** Bundle/version lifecycle mirrored from backend doc; scan-status polling interval documented for future maintainers.
**Mergeable outcome:** Admin can safely get a "current" STL bundle live without ever exposing an unscanned or partially-clean bundle as purchasable.

---

#### FVS-019 — Admin Entitlement Management

**Priority:** P0 · **Risk:** High authorization model · **Value:** Proves digital ownership before payments exist
**Depends on (frontend):** FVS-018
**Backend dependencies:** VS-017 (admin-grant path)
**Backend endpoints used:**
```
POST /api/v1/admin/users/{user_id}/entitlements
```
**Frontend capability:** Admin manually grants an STL entitlement to a specific customer (support/goodwill/manual-sale path), from either the customer detail page (FVS-009) or the product detail page (FVS-011).
**Routes:** Embedded action in `/admin/customers/:id` and `/admin/products/:id/edit`, not a standalone route.
**Components:** `GrantEntitlementDialog` (customer/product picker + confirm).
**State:** Local dialog state; on success, invalidates the customer's entitlement list query (feeds FVS-020's data for that user, viewed from admin side if such a view exists) and shows a success toast.
**API integration:** Only STL products are selectable (client-side filters product picker to STL type, though the server is the actual authority and will reject a physical product regardless); active-uniqueness conflict (already entitled) surfaces the server's specific error.
**UX states:** Product/user not selected (disabled confirm); already-entitled conflict; success; error.
**Responsive behavior:** Dialog is usable at mobile widths (admin may act from a support conversation on a phone).
**Accessibility:** Dialog traps focus, labeled combobox/search for product and user pickers.
**Testing:** Integration test for already-entitled conflict message; E2E: grant → customer's library (FVS-020) reflects the new entitlement.
**Documentation:** Grant-source note (manual admin grant vs future payment-driven grant in FVS-027/036).
**Mergeable outcome:** Digital ownership can be demonstrated end-to-end in the UI before any payment code exists.

---

#### FVS-020 — Customer STL Library

**Priority:** P0 · **Risk:** Low (read) · **Value:** Where ownership becomes visible to the customer
**Depends on (frontend):** FVS-006, FVS-019
**Backend dependencies:** VS-017 (customer-facing read)
**Backend endpoints used:**
```
GET /api/v1/me/entitlements
GET /api/v1/me/entitlements/{id}
```
**Frontend capability:** A logged-in customer sees every STL product they own, its current version info, and a path to download (FVS-021) — never a raw storage path or private URL.
**Routes:** `/account/library` (added to FVS-006's account nav).
**Components:** `EntitlementList`, `EntitlementCard` (product name/thumbnail, current version label, download CTA).
**State:** Server state; empty-state when the customer owns nothing yet.
**API integration:** Revoked entitlements are excluded from the list entirely (per VS-017's "revoked hidden" rule) — the UI does not show a "revoked" badge for something the API never returns; if a specific entitlement detail 404s (e.g., navigated via stale link after revocation), that's a distinct not-found state, not a crash.
**UX states:** Empty library ("you don't own any STL products yet" + link to shop); loading; revoked-and-thus-absent (no special UI, just absent); detail 404 on stale link.
**Responsive behavior:** Card grid → single column list on mobile.
**Accessibility:** Cards are list items with a single clear primary action link/button, not multiple overlapping click targets.
**Testing:** Integration test that revoked entitlements never render; E2E: after FVS-019 grants an entitlement, it appears here.
**Documentation:** None beyond inline empty-state copy guidance.
**Mergeable outcome:** Customers can see what they own before the download mechanism (FVS-021) or payment path (FVS-036) exists.

---

#### FVS-021 — Customer STL Download Experience

**Priority:** P0 · **Risk:** Critical digital security/performance · **Value:** Completes STL delivery
**Depends on (frontend):** FVS-020
**Backend dependencies:** VS-018
**Backend endpoints used:**
```
GET /api/v1/me/downloads
[entitlement-file download endpoint — exact path NEEDS BACKEND CONFIRMATION, §17]
```
**Frontend capability:** From the library (FVS-020), a customer downloads their current STL file (a direct navigation/link to the authorized download endpoint — not a fetch-and-blob, since the backend streams via nginx `X-Accel-Redirect` and supports HTTP Range for large files, which the browser's native download handling manages better than a JS-mediated blob download) and views download history with dates.
**Routes:** `/account/downloads` (added to account nav); download action lives on `/account/library`.
**Components:** `DownloadButton` (renders as a real anchor to the authorized endpoint, not a JS click-handler that fetches — preserves native browser resume/range support), `DownloadHistoryTable`.
**State:** Server state for history list; the download action itself has no client-tracked "state" beyond a disabled/cooldown UI if the daily cap is hit.
**API integration:** A cap-exceeded response (daily download limit) is shown as a clear, specific message with the reset time if the backend provides one, not a generic error; a revoked/no-longer-entitled attempt (stale link) is a distinct 403/404 state.
**UX states:** Normal download (native browser handling takes over); daily cap reached; entitlement revoked since page load (stale link); history empty vs populated.
**Responsive behavior:** History table becomes a stacked list on mobile (date + filename, no horizontal scroll needed since it's few columns).
**Accessibility:** Download link has a clear accessible name including the file/product name, not just "Download."
**Testing:** Integration tests for cap-reached and revoked-access error displays; E2E: grant entitlement → download → appears in history.
**Documentation:** Note that this is a plain anchor `href` by design (for Range/resume support), so future contributors don't "improve" it into a blob-fetch that breaks large-file resume.
**Mergeable outcome:** An entitled customer can securely download through the exact production delivery path, and see their history.

---

#### FVS-022 — Home Page, About Us & Floating WhatsApp

**Priority:** P1 · **Risk:** Low · **Value:** First impression / brand surface
**Depends on (frontend):** FVS-007 (public settings), FVS-013 (featured products)
**Backend dependencies:** None directly — frontend-only per backend plan §5 (F-001, F-002, F-003), composed from VS-007 and VS-013 data
**Backend endpoints used:**
```
GET /api/v1/settings/public
GET /api/v1/products   (e.g., featured/recent subset)
```
**Frontend capability:** Home page composes a hero, featured/recent products (reusing `ProductCard`/`ProductGrid` from FVS-013), and links into shop/BYI/contact. About Us is static content (approved V1 scope — no CMS). A floating WhatsApp button appears on every public page, driven by the public WhatsApp number setting.
**Routes:** `/`, `/about`.
**Components:** `FloatingWhatsAppButton` (global, mounted in the app shell from FVS-001, reads the same public-settings query as FVS-014's chat button so there's one cached source), `HeroSection`, `FeaturedProductsSection` (reuses `ProductGrid`/`ProductCard`).
**State:** Server state (public settings, cached/shared app-wide; featured product list).
**API integration:** If the public-settings fetch fails, the floating WhatsApp button simply doesn't render rather than showing a broken link — never hardcode a fallback phone number in the frontend.
**UX states:** Loading featured products (skeleton grid); settings fetch failure (button silently absent); About content is static, no loading state needed.
**Responsive behavior:** Floating button repositions to avoid overlapping the mobile sticky action bar introduced in FVS-014 (z-index/position coordination between the two slices' components).
**Accessibility:** Floating button has an accessible name ("Chat with us on WhatsApp") and is reachable in keyboard tab order without being a tab-order trap that appears before main content on every page.
**Testing:** Component test that the button doesn't render without a phone number; E2E: home page loads featured products and links to shop.
**Documentation:** None beyond content-ownership note (About Us copy is static content, not backend-driven).
**Mergeable outcome:** The storefront has a real front door and the site-wide WhatsApp affordance required by F-002/F-011.

### Milestone FM-C — Commerce

#### FVS-023 — Customer Address Book

**Priority:** P1 · **Risk:** Low · **Value:** Enables physical checkout inputs
**Depends on (frontend):** FVS-006
**Backend dependencies:** VS-019 (address half)
**Backend endpoints used:**
```
GET /api/v1/me/addresses
POST /api/v1/me/addresses
PATCH /api/v1/me/addresses/{id}
DELETE /api/v1/me/addresses/{id}
```
**Frontend capability:** Customer manages saved addresses and sets a default; explicit shipping-zone selection happens at checkout (FVS-026), not here — V1 has no automatic governorate mapping, so the address form does not attempt to infer a zone from the address.
**Routes:** `/account/addresses` (added to account nav).
**Components:** `AddressList`, `AddressForm`, `SetDefaultToggle`.
**State:** Server state; default-switch is optimistic with rollback.
**API integration:** Only one address can be default — setting a new default is server-authoritative; the UI reflects whatever the server returns rather than locally flipping two toggles and hoping.
**UX states:** Empty address book; create/edit/delete confirm; default-switch pending/error.
**Responsive behavior:** Card list at all widths; form is a modal on desktop, full-screen on mobile.
**Accessibility:** Radio-button semantics for "default" selection (not a set of independent checkboxes, since only one can be true).
**Testing:** Integration test for default-switch server-truth reconciliation; E2E: add two addresses → set default → reflected on reload.
**Documentation:** Explicit note that zone selection is a checkout-time action, not derived here (avoids a future contributor "helpfully" adding auto-detection that the backend doesn't support).
**Mergeable outcome:** Checkout (FVS-026) has real address input to build on.

---

#### FVS-024 — Admin Shipping Zone Management

**Priority:** P1 · **Risk:** Medium commerce prerequisite · **Value:** Enables physical checkout pricing
**Depends on (frontend):** FVS-007
**Backend dependencies:** VS-019 (shipping-zone half)
**Backend endpoints used:**
```
GET /api/v1/admin/shipping-zones
POST /api/v1/admin/shipping-zones
PATCH /api/v1/admin/shipping-zones/{id}
GET /api/v1/shipping-zones
```
*(VS-019's admin half is prose only ("admin shipping-zone CRUD") — placeholders above, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin creates/edits shipping zones and rates (server-owned rate authority — the frontend never computes shipping cost itself). Archived zones become unavailable at checkout.
**Routes:** `/admin/shipping-zones`.
**Components:** `ReferenceDataManager`-style form (extends the FVS-010 pattern with a rate/`MoneyInput` field from FVS-011).
**State:** Server state.
**API integration:** Rate fields use `MoneyInput` (reused from FVS-011) for cents-safety; archiving a zone in use by an active order does not retroactively change that order's snapshot (checkout/order snapshots are immutable — this slice only affects future checkouts).
**UX states:** Create/edit/archive; empty list.
**Responsive behavior:** Stacked-card pattern below 768px.
**Accessibility:** Same `MoneyInput` a11y baseline as FVS-011.
**Testing:** Integration test that archived zones disappear from the public `/shipping-zones` list consumed by checkout; E2E: create zone → visible at checkout (cross-checked in FVS-026).
**Documentation:** Note on the V1 explicit-zone-selection rule (no auto-detection), consistent with backend doc.
**Mergeable outcome:** Physical checkout has real, admin-controlled shipping options before checkout itself is built.

---

#### FVS-025 — Shopping Cart (Mixed Physical + STL)

**Priority:** P0 · **Risk:** High mixed-commerce rules · **Value:** Core purchase funnel
**Depends on (frontend):** FVS-014, FVS-020
**Backend dependencies:** VS-020
**Backend endpoints used:**
```
GET /api/v1/cart
POST /api/v1/cart/items
PATCH /api/v1/cart/items/{item_id}
DELETE /api/v1/cart/items/{item_id}
```
*(VS-020's endpoint line only gives a literal path for `GET /api/v1/cart`; the add/update/delete item paths above follow this app's REST convention but are **not** backend-confirmed — `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** A verified customer adds physical and STL products to one persistent cart, with STL quantity locked to 1, already-owned STL rejected client-side before the request is even sent (with server as final authority), unavailable/WhatsApp-only products never offered an add-to-cart action (per FVS-014), and quantity capped at the server's current max. Mini-cart (header) and full cart page share the same server-state query.
**Routes:** `/cart`, wrapped in `ProtectedRoute` (VS-020's cart is user-scoped only — there is no guest-cart concept in the backend plan); header `MiniCartDrawer` accessible from any page but renders a "log in to start a cart" prompt instead of cart contents for anonymous visitors.
**Components:** `MiniCartDrawer`, `CartPage`, `CartLineItem` (renders differently for physical — quantity stepper — vs STL — fixed qty=1, no stepper), `PriceDisplay` (reused), `EmptyCartState`, `LoggedOutCartPrompt` (anonymous-visitor state — see UX states below).
**State:** **Server state** is the cart itself (single source of truth, no separate client-side cart mirror to avoid drift); **optimistic UI** for quantity changes/removal with rollback if the server rejects (e.g., a cap was lowered, or the item became unavailable between page load and the request).
**API integration:** Every mutation re-fetches the authoritative cart (price snapshot vs current price) rather than trusting the optimistic local delta as final — the backend, not the frontend, is the source of truth for price/availability/quantity, per §12 below. A merge-on-duplicate-add is a normal success case (quantity increases), not an error.
**UX states:** Anonymous visitor (redirected to login on Add to Cart from a product page; `/cart` itself shows `LoggedOutCartPrompt` rather than a 404/blank page if reached directly); empty cart; adding (optimistic + confirm); quantity-cap rejected; STL-already-owned rejected pre-request; item became unavailable server-side (removed with an explanatory line, not a silent disappearance); price changed since it was added (shown as a "price updated" note on the line, not hidden); loading; error/retry.
**Responsive behavior:** Desktop: mini-cart as a slide-over drawer from the header; full cart page as a two-column layout (line items + sticky summary). Mobile: mini-cart as a bottom sheet; full cart page stacks the summary below line items but keeps a sticky "Checkout" bar at the bottom.
**Accessibility:** Quantity stepper has accessible increment/decrement buttons with the current value announced; removing an item announces via `aria-live` so screen-reader users get confirmation without focus loss.
**Testing:** Optimistic-update rollback unit tests; STL qty-lock and already-owned pre-check tests; integration tests for price-change and unavailable-removal server responses; E2E: add a physical + an STL item → adjust physical quantity → attempt to add owned STL (rejected) → proceed to checkout.
**Documentation:** Cart invariants doc mirroring backend's (one cart/user, STL qty=1, price snapshot semantics) so support/QA understand why totals can differ from "current" catalogue prices.
**Mergeable outcome:** A verified customer can hold and manage a valid mixed cart end-to-end against real backend invariants.

---

#### FVS-026 — Checkout Flow

**Priority:** P0 · **Risk:** Critical transaction/concurrency · **Value:** Core revenue path
**Depends on (frontend):** FVS-023, FVS-024, FVS-025
**Backend dependencies:** VS-021
**Backend endpoints used:**
```
POST /api/v1/checkout
GET /api/v1/shipping-zones
```
**Frontend capability:** Customer reviews the cart, chooses delivery (saved address + zone) or pickup per applicable line, confirms if the server detected a price change since items were added, accepts terms and, for any digital item, an explicit digital-final-sale consent, and submits — the server computes trusted totals/shipping/free-threshold; the frontend never computes or displays a final total it invented locally, only what the server returns (or, pre-submit, a clearly-labeled "estimated" figure it recomputes identically to the server's known public rules, if any are safe to mirror — otherwise it waits for the server response before showing a final number).
**Routes:** `/checkout`.
**Components:** `CheckoutStepper` (recommend a single-page layout with Delivery/Review/Confirm as in-page sections rather than a multi-step wizard, given V1's scope and the need to show the price-change conflict banner in context without a step transition hiding it), `DeliveryMethodSelector` (address+zone vs pickup, per line if the cart mix requires it), `PriceChangeConflictBanner`, `ConsentCheckboxGroup` (terms + digital-final-sale, itemized per digital product per §12 below), `OrderSummary`.
**State:** Form state (delivery choice, consent checkboxes) plus **idempotency key** generated client-side once per checkout attempt and reused across retries of the *same* submission so a double-click or network retry cannot create two orders (exact idempotency header contract `NEEDS BACKEND CONFIRMATION`, §17).
**API integration:** A `409`-shaped price-change-conflict response re-renders the affected line(s) with the new price and requires explicit re-confirmation before resubmitting — the frontend never silently resubmits with server-corrected values. A cart mutated concurrently (e.g., item removed by a stock rule) surfaces per-line, not as a generic failure. Kill-switch ("not accepting orders" setting from FVS-007) disables the submit CTA with an explanatory banner rather than letting the user submit into a guaranteed rejection.
**UX states:** Loading checkout data (cart + addresses + zones); price-change conflict (re-confirm); cart-changed-concurrently (per-line); missing required consent (digital final-sale); kill-switch active (checkout disabled); submitting (idempotent — safe to show a spinner and disable the button, since retry reuses the same key); success (redirect to payment, FVS-027); failure (server error, retry safe due to idempotency).
**Responsive behavior:** Desktop: two-column (form left, sticky order summary right). Mobile: linear single column, order summary collapsible/expandable above the form, sticky submit bar.
**Accessibility:** Consent checkboxes are individually labeled with the exact obligation they represent (not one blanket "I agree to everything"); price-change banner is announced via `aria-live="assertive"` since it blocks progress and needs immediate attention.
**Testing:** Idempotency-key reuse unit test (same key across a resubmission of the identical attempt); price-conflict re-render integration test; consent-required validation test; kill-switch-disabled-submit integration test (accepting-orders setting off → submit is disabled with the explanatory banner, not silently rejected after a round-trip); concurrent-cart-mutation integration test (a line becomes unavailable/changes between page load and submit → per-line, not generic, failure); E2E: cart → checkout → (mock) price unchanged → submit → redirected to payment result flow (FVS-027).
**Documentation:** Checkout sequence doc cross-referencing the backend's transaction sequence so frontend and backend engineers share the same mental model of what happens in the one DB transaction.
**Mergeable outcome:** A customer can convert a valid mixed cart into a pending order through the real checkout transaction, including its concurrency/price-conflict edge cases.

---

#### FVS-027 — Payment Result & Verification UX

**Priority:** P0 · **Risk:** Critical — must not assume success from redirect params · **Value:** Trustworthy purchase completion
**Depends on (frontend):** FVS-026
**Backend dependencies:** VS-022 (independent verification/reconciliation), VS-021 (mock payment redirect), VS-027 (live provider — same UI, different provider underneath)
**Backend endpoints used:**
```
[order/payment status read endpoint — exact path NEEDS BACKEND CONFIRMATION, §17]
GET /api/v1/me/orders/{id}   (available once FVS-029 lands; used here for the same purpose if no dedicated status endpoint exists)
```
**Frontend capability:** After checkout redirects to the (mock, then real Whish) payment provider and the customer returns to the site, the frontend treats the return as **"payment attempt finished, status unknown"** — never as success — and polls the backend's own verified status until it resolves to paid/failed/expired, exactly per §12 below. Query parameters on the return URL are used only to identify *which* order to check, never to decide success/failure.
**Routes:** `/checkout/payment-result?order_id=...` (or provider-specific return path — confirm exact contract in §17).
**Components:** `PaymentStatusPoller` (polls order/payment status at a backoff interval, stops on terminal state or timeout), `PaymentPendingState`, `PaymentSuccessState`, `PaymentFailedState`, `PaymentExpiredState`.
**State:** Server state (polled order/payment status) is the only source of truth; no state is derived from URL query params beyond the order identifier.
**API integration:** While status is `pending`/`processing`, the poller keeps checking (interval and max-duration are frontend-configurable but must eventually stop and show a "we're still confirming — check your order history" fallback rather than polling forever); a `failed` status shows retry-to-checkout guidance; an `expired`/interrupted payment (customer abandoned the provider page) is a distinct state from `failed` if the backend distinguishes them.
**UX states:** Verifying (spinner, "confirming your payment — do not close this page" copy that is honest about polling, not a fake progress bar); success (order confirmation, entitlements/next-steps link); failed (retry CTA back to checkout/cart); expired; network failure while polling (retry-polling CTA); polling-timeout fallback (link to order history instead of infinite spinner).
**Responsive behavior:** Centered single-column status card at all widths — no layout complexity needed here, clarity matters more than density.
**Accessibility:** Status changes are announced via `aria-live="polite"` (verifying → success/failed) since a screen-reader user staring at a spinner otherwise gets no feedback when it resolves.
**Testing:** Poller unit tests (backoff, terminal-state stop, timeout fallback); integration tests for each terminal status rendering; **explicit test that a manipulated success-looking query string with a backend status still stuck at `pending` renders the pending state, not success** (this is the single most important test in this slice, guarding against the anti-pattern described in §12 below).
**Documentation:** Payment UX sequence diagram (checkout → provider → return → poll → terminal state) cross-referenced with the backend's verification/reconciliation runbook.
**Mergeable outcome:** The frontend never displays "Payment Successful" on the strength of a redirect alone — success is always backend-verified.

---

#### FVS-028 — Admin Payment Management

**Priority:** P0 · **Risk:** Critical payment security (read/ops surface) · **Value:** Operational payment visibility
**Depends on (frontend):** FVS-005, FVS-027
**Backend dependencies:** VS-022 (admin half)
**Backend endpoints used:**
```
GET /api/v1/admin/payments
GET /api/v1/admin/payments/{id}
POST /api/v1/admin/payments/{id}/reconcile
POST /api/v1/admin/payments/{id}/confirm
```
*(VS-022's admin half is prose only — placeholders above, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin lists payments, opens detail (status, provider reference, amount, linked order), triggers a manual reconciliation check, and — for the documented manual-fallback path — manually confirms a payment when the provider callback was lost.
**Routes:** `/admin/payments`, `/admin/payments/:id`.
**Components:** `AdminTable` (reused), `StatusBadge` (payment states), `ManualConfirmDialog` (requires explicit confirmation + reason, since this bypasses normal verification).
**State:** Server state.
**API integration:** Manual confirm is treated as a high-risk action — dialog requires the admin to acknowledge they've independently verified the payment (mirrors the backend's manual-fallback design intent), and the action is audited server-side (visible later in FVS-042).
**UX states:** Loading; reconcile-in-progress/result; manual-confirm confirm/success/error; already-paid (manual confirm is a no-op/blocked if already resolved, per idempotency at the backend).
**Responsive behavior:** `AdminTable` pattern.
**Accessibility:** Manual-confirm dialog focus-trapped, requires an explicit checkbox/typed confirmation rather than a single accidental-clickable button, given the financial risk.
**Testing:** Integration test for already-paid manual-confirm rejection; E2E: admin views a payment → reconciles → sees updated status.
**Documentation:** Manual-fallback operational runbook cross-referenced from the backend's reconciliation runbook.
**Mergeable outcome:** Admin has real operational control over the payment lifecycle without database access, for the exact cases VS-022 designs for.

---

#### FVS-029 — Customer Order History & Detail

**Priority:** P1 · **Risk:** Medium ownership · **Value:** Customer trust / support reduction
**Depends on (frontend):** FVS-006, FVS-027
**Backend dependencies:** VS-023
**Backend endpoints used:**
```
GET /api/v1/me/orders
GET /api/v1/me/orders/{id}
```
**Frontend capability:** A customer views paginated order history (status/date filters) and full order detail, including a **per-line-item view** for mixed orders (each physical/STL line shown with its own status, not one blended order-level status), payment summary, and refund status if any — all as immutable snapshots (address/price/zone at time of purchase), never re-computed from current catalogue data.
**Routes:** `/account/orders`, `/account/orders/:id`.
**Components:** `OrderList`, `OrderDetail`, `OrderLineItem` (introduced here — reused by admin's order console in FVS-030 for the customer-visible parts), `StatusBadge`/`StatusTimeline` (per-line state visualization, see §14 below).
**State:** Server state with URL-synced status/date filters and cursor pagination (consistent with FVS-013's URL-state pattern).
**API integration:** A request for another customer's order ID returns 404 (IDOR-hidden, not 403) — the frontend renders the app's standard not-found page, matching the backend's hiding behavior rather than a distinct "forbidden" message that would confirm the order's existence.
**UX states:** Empty order history; loading; 404 (not own order / doesn't exist — same UI either way); mixed-order per-line status display; filter/pagination boundaries.
**Responsive behavior:** Desktop: order list as a table; order detail as a two-column (line items + summary sidebar). Mobile: order list as stacked cards; detail as a single stacked column with the summary above line items for quick scanning.
**Accessibility:** Status timeline uses text labels alongside any icon/color (never color-only); order line list is a real list structure.
**Testing:** IDOR-hiding integration test (foreign order ID → 404, indistinguishable from a nonexistent ID); snapshot-immutability display test (order shows purchase-time price even if current catalogue price differs); E2E: complete a purchase (FVS-026/027) → appears in history with correct line-item detail.
**Documentation:** Customer-visible order projection doc (which fields are shown vs admin-only, e.g., internal notes are never present here).
**Mergeable outcome:** A customer can self-serve their entire purchase history without contacting support, and without any IDOR leak.

---

#### FVS-030 — Admin Order Fulfillment Console

**Priority:** P0 · **Risk:** High state machine · **Value:** Enables actual fulfillment operations
**Depends on (frontend):** FVS-009, FVS-029 (reuses `OrderLineItem`/`StatusBadge`)
**Backend dependencies:** VS-024
**Backend endpoints used:**
```
GET /api/v1/admin/orders
GET /api/v1/admin/orders/{id}
PATCH /api/v1/admin/orders/{id}
[per-line transition endpoint — exact path NEEDS BACKEND CONFIRMATION, §17]
```
*(VS-024's endpoint line is prose only — the list/detail/update paths above are frontend-constructed placeholders too, not just the bracketed transition endpoint. All `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin sees a searchable/filterable order queue, opens order detail with an editable **internal note** (never customer-visible — visually distinguished so no admin ever confuses it with customer-facing content), and transitions each physical order line through its legal next states (e.g., into production, out for delivery, delivered) via explicit per-line action buttons — never a free-text or generic-dropdown status field, mirroring the backend's controlled state machine.
**Routes:** `/admin/orders`, `/admin/orders/:id`.
**Components:** `AdminTable` (reused), `OrderLineItem` (reused, extended with admin transition actions), `InternalNoteEditor` (visually distinct "internal — not visible to customer" styling), `LineTransitionButton` (renders only the legal next actions for that line's current state — the button set itself is derived from the line's status, not a static list), `ConfirmDialog` (for irreversible transitions).
**State:** Server state for the queue/detail; internal note has its own save state independent of line transitions.
**API integration:** The frontend does not attempt to enumerate the full state machine independently — it renders whatever "available actions" the order/line detail response indicates are legal from the current state (if the backend doesn't return an explicit affordance list, the frontend maintains a client-side transition table mirrored exactly from the backend's documented state diagram, flagged in §17 if no server-provided affordance list exists). A row-lock conflict (another admin transitioned the same line concurrently) surfaces as a refetch-and-explain, not a silent overwrite.
**UX states:** Loading queue; search/filter/empty results; note save pending/success/error; transition confirm/success/illegal-transition-rejected/concurrency-conflict; mixed-order per-line independent status.
**Responsive behavior:** `AdminTable` pattern for the queue; detail view's per-line action buttons wrap onto multiple rows on narrow viewports rather than causing horizontal scroll.
**Accessibility:** Internal note field has an explicit "not visible to customers" label read by screen readers, not conveyed by color alone; transition buttons have accessible names describing the destination state, not just "Next."
**Testing:** Transition-button-set-derivation tests (only legal actions rendered per state); concurrency-conflict integration test; internal-note visibility boundary test (never rendered in any customer-facing component — cross-checked against FVS-029); E2E: admin transitions a physical line from paid → production → delivered.
**Documentation:** State-machine transition table mirrored from the backend doc — kept in one place so frontend and backend state diagrams cannot drift silently.
**Mergeable outcome:** Admin can run real fulfillment operations without ever being able to set an illegal status or leak internal notes to customers.

---

#### FVS-031 — Order Cancellation & Returns UX

**Priority:** P0 · **Risk:** High concurrency/refund boundary · **Value:** Essential exception handling
**Depends on (frontend):** FVS-029, FVS-030
**Backend dependencies:** VS-025
**Backend endpoints used:**
```
[customer order cancel endpoint — NEEDS BACKEND CONFIRMATION, §17]
[admin order cancel endpoint — NEEDS BACKEND CONFIRMATION, §17]
[existing per-line transition endpoint from VS-024, extended for returned/re-ship/reprint]
```
**Frontend capability:** A customer can cancel a paid physical line **only** while it's pre-production (the cancel button is present/enabled purely based on the line's current status, disappearing once production starts — a race the backend resolves authoritatively, with the frontend showing "this item has already entered production and can no longer be cancelled" if the request loses the race); STL lines never show a cancel action. Admin can cancel post-production (triggering the refund-obligation path handled in FVS-032) and move a shipped line to returned, then to re-ship/reprint/refund from the returned state.
**Routes:** Actions embedded in `/account/orders/:id` (customer) and `/admin/orders/:id` (admin) — no standalone routes.
**Components:** `CancelOrderLineButton` (customer, status-gated), `AdminCancelDialog` (admin, requires reason, may trigger refund obligation messaging), `ReturnedItemActions` (admin: re-ship / reprint / refund, rendered only on lines in `returned` state).
**State:** Action-local pending/error state; on success, invalidates the order detail query so the line's new status/available-actions reflect immediately.
**API integration:** The customer-cancel race (production starts concurrently with the cancel click) is handled by trusting the server's response, not a client-side "it looked cancellable a second ago" assumption — a losing race shows the specific "too late, already in production" message the server returns.
**UX states:** Cancel available; cancel race-lost (already in production); cancel success; STL line has no cancel affordance at all (not disabled — absent, since it's never legal); admin cancel triggers refund-obligation notice; returned-state action picker (re-ship/reprint/refund).
**Responsive behavior:** Consistent with FVS-029/030's order-detail responsive layout — actions stack below line info on mobile.
**Accessibility:** Destructive actions (cancel, admin cancel) use `ConfirmDialog` (reused) with a clear description of consequence (e.g., "this will initiate a refund") before the irreversible action fires.
**Testing:** Status-gated-button-visibility tests (present/absent per line status, especially STL-never-cancellable); race-lost integration test; admin-cancel-triggers-refund-obligation-notice integration test; returned-state action-picker test (re-ship/reprint/refund options render correctly and only in the `returned` state); partial-mixed-cancellation E2E (mirroring VS-025's own mandatory "partial mixed cancellation" test); E2E: customer cancels a pre-production line successfully; E2E: customer attempts to cancel a line the admin has just moved to production (race-lost path).
**Documentation:** Cancellation cutoff rule and returned-state flow, mirrored from backend doc, so support scripts match actual UI behavior.
**Mergeable outcome:** The highest-risk physical fulfillment exceptions are handled deterministically in the UI, matching the backend's authoritative state machine exactly.

---

#### FVS-032 — Admin Refund Management

**Priority:** P0 · **Risk:** Critical financial correctness · **Value:** Required commerce safety net
**Depends on (frontend):** FVS-030, FVS-031
**Backend dependencies:** VS-026
**Backend endpoints used:**
```
POST /api/v1/admin/orders/{id}/refunds
GET /api/v1/admin/refunds
GET /api/v1/admin/refunds/{id}
POST /api/v1/admin/refunds/{id}/settle
```
*(VS-026's endpoint line is prose only — placeholders above, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin creates a refund against specific order lines (and optionally shipping) with server-derived refundable balances shown as the ceiling — the UI never lets an admin type an arbitrary amount that exceeds what the server will allow, it presents the server's computed maximum per line and validates against it before submission (final authority still server-side). Admin can also view a refund queue and mark a refund settled once money has actually moved (provider or manual). The **mandatory mixed-order partial-refund** scenario is explicitly covered: refunding only the physical failure and its shipping while a digital line's entitlement remains untouched.
**Routes:** `/admin/refunds`, `/admin/refunds/:id`; refund creation embedded in `/admin/orders/:id`.
**Components:** `RefundCreateForm` (per-line amount inputs bounded by server-reported refundable balance, `MoneyInput` reused), `AdminTable` (reused, refund queue), `RefundDetail`, `SettleRefundDialog`.
**State:** Server state; refund creation is idempotent client-side too (disable submit after first click, rely on the same idempotency-key pattern as checkout if the endpoint requires one — confirm in §17).
**API integration:** Over-refund attempts are rejected server-side with a specific error shown inline on the offending line's amount field; a digital-line refund is shown with an explicit "this will revoke the customer's entitlement" warning before submission (destructive, confirmed via `ConfirmDialog`); a refund remains "pending settlement" in the UI until the settle action succeeds — the UI never implies money has moved just because a refund record was created.
**UX states:** Refund form validation (per-line ceiling); over-refund rejected; digital-revocation confirm; pending-settlement badge; settle success/failure (manual method vs provider method shown distinctly); duplicate-submission guard.
**Responsive behavior:** Refund form fields stack per line on mobile; `AdminTable` pattern for the queue.
**Accessibility:** Per-line amount inputs are labeled with the product name, not just "Amount 1/2/3"; the entitlement-revocation warning is presented as an explicit confirmation step, not fine print.
**Testing:** **Mandatory E2E for the mixed-order partial refund** (refund physical line + shipping, verify digital entitlement in FVS-020 is unaffected); over-refund rejection integration test; duplicate-submission guard unit test; settle-flow integration test for both provider and manual methods.
**Documentation:** Refund accounting rules mirrored from backend doc, including the "already-downloaded file remains evidence only" clarification so admin UI copy doesn't imply a refund undoes a download.
**Mergeable outcome:** A mixed order can be correctly, safely refunded in part while preserving valid digital ownership — the single highest-stakes commerce UI in the plan.

**Note on VS-027 (live Whish adapter):** no dedicated FVS. It changes the payment *provider* behind FVS-026/027/028's existing UI, not the UI contract itself — see traceability matrix §18 ("Shared frontend work"). The frontend should verify FVS-027's real redirect/return handling against the live provider's actual redirect shape once credentials exist, as a hardening pass on FVS-027, not a new slice.

### Milestone FM-D — Negotiation & Engagement

#### FVS-033 — Customer Offer Submission & History

**Priority:** P1 · **Risk:** High state/deadline rules · **Value:** STL negotiation revenue
**Depends on (frontend):** FVS-014, FVS-020
**Backend dependencies:** VS-028
**Backend endpoints used:**
```
POST /api/v1/offers
GET /api/v1/me/offers
GET /api/v1/me/offers/{id}
```
**Frontend capability:** From an STL product's detail page (FVS-014), a customer who doesn't already own it and has no other live offer on it can submit a price offer at or above the configured minimum floor (the floor itself is not necessarily known client-side unless the product/settings response exposes it — if not, the client relies entirely on the server's rejection message; do not hardcode a floor value). A rejection-cooldown (from a prior rejected offer) is surfaced clearly if the customer tries again too soon. `/account/offers` lists all of the customer's offers with status.
**Routes:** `/account/offers`, `/account/offers/:id` (detail — this is also where FVS-034's negotiation UI lives); "Make an offer" action embedded on `/shop/:slug` for eligible STL products.
**Components:** `MakeOfferDialog` (amount input using `PriceDisplay`/`MoneyInput` conventions), `OfferList`, `OfferStatusBadge`.
**State:** Server state; dialog form state for the offer amount.
**API integration:** Duplicate-live-offer and cooldown-active rejections render the server's specific reason (with a countdown to cooldown expiry if the response includes a timestamp — timezone/format confirmed in §17); already-owned products never show the "Make an offer" action at all (client-side gate backed by the entitlement check from FVS-020's data), matching the backend's "not already owned" rule.
**UX states:** Eligible → dialog available; already-owned → no action shown; duplicate-live-offer rejected; cooldown-active rejected (with countdown if timestamp available); below-floor rejected (server message); submitted → appears in `/account/offers` as pending.
**Responsive behavior:** `MakeOfferDialog` full-screen on mobile, centered modal on desktop.
**Accessibility:** Dialog focus-trapped; amount input announces currency unit; cooldown countdown is both visually and textually presented (not a bare number ticking with no label).
**Testing:** Already-owned gating unit test; cooldown-countdown display test; integration tests for duplicate/floor/cooldown rejections; E2E: submit a valid offer → appears in offer history as pending.
**Documentation:** Offer eligibility rules mirrored from backend doc.
**Mergeable outcome:** A customer can open one valid negotiation and see its status, before counter/accept/reject UI exists.

---

#### FVS-034 — Customer Offer Negotiation (Counter/Accept/Withdraw)

**Priority:** P1 · **Risk:** High state machine, deadline-sensitive · **Value:** Completes the customer side of negotiation
**Depends on (frontend):** FVS-033
**Backend dependencies:** VS-029
**Backend endpoints used:**
```
POST /api/v1/me/offers/{id}/counter
POST /api/v1/me/offers/{id}/accept
POST /api/v1/me/offers/{id}/withdraw
```
*(VS-029 describes these customer actions in prose only, no literal paths — placeholders above, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** On `/account/offers/:id`, the customer sees a **conversation/timeline UI** of every round (who acted, amount, timestamp), the current turn (whose move it is), a live-updating deadline countdown for their own turn, and only the actions that are legal right now (counter/accept when it's their turn and an admin round is pending response; withdraw while a customer round is pending). This is explicitly **not** built on WebSockets — status is refreshed via polling/refetch-on-focus (TanStack Query's window-focus refetch plus a bounded interval while the offer is non-terminal), since nothing in `docs/plans/backend/vertical-slice-plan.md` describes a push/realtime mechanism (§7/§9's no-invented-realtime rule).
**Routes:** `/account/offers/:id`.
**Components:** `OfferTimeline` (round-by-round history, immutable/append-only rendering — never edits a past round), `OfferActionPanel` (renders only legal actions for the current turn/state), `DeadlineCountdown`, `AcceptedCheckoutWindowBanner` (post-acceptance, links to FVS-036).
**State:** Server state, polled while the offer is in any non-terminal condition (the exact status-string enum is not given in `docs/plans/backend/vertical-slice-plan.md` — VS-028/029 describe states only in prose; treat any specific status token as a placeholder pending confirmation, `NEEDS BACKEND CONFIRMATION`, §17); countdown itself is a local `setInterval` ticking display only — the authoritative expiry check still happens server-side on action submission.
**API integration:** A wrong-turn or expired-deadline action attempt (lost a race against the deadline or an admin action) is met with the server's specific rejection, followed by an immediate refetch to show the now-current state rather than leaving a stale UI. Accept transitions into a checkout-window countdown (handled by FVS-036) rather than immediate purchase.
**UX states:** My-turn (actions enabled); their-turn (read-only, "waiting for admin" with their deadline shown); countered (new round appended, my deadline reset); accepted (frozen price + checkout-window banner); rejected (cooldown notice, matches FVS-033); withdrawn (terminal, no further action); expired (terminal, "this offer expired" — no action); action-race-lost (refetch-and-explain).
**Responsive behavior:** Timeline is a vertical list at all widths; action panel becomes a sticky bottom bar on mobile so the primary action (counter/accept/withdraw) is always reachable without scrolling back up.
**Accessibility:** Timeline entries are a real ordered list; countdown is announced at reasonable intervals via `aria-live="polite"` (not every second — that would be disruptive) and always paired with a static "expires at HH:MM" text for screen-reader users who can't track a ticking number.
**Testing:** Legal-action-set-per-turn unit tests; countdown display tests; polling-while-nonterminal / stop-on-terminal tests; integration test for wrong-turn/expired rejection-then-refetch; E2E: submit offer → (simulate admin counter) → customer counters back → (simulate admin accept) → checkout-window banner appears.
**Documentation:** Offer state diagram mirrored from backend doc — this is the single most state-heavy customer UI in the plan and needs one authoritative diagram shared with backend.
**Mergeable outcome:** Negotiation reaches accepted/rejected/withdrawn outcomes in the UI through explicit actions, never a generic status field, matching the backend exactly.

---

#### FVS-035 — Admin Offer Management

**Priority:** P1 · **Risk:** High state machine · **Value:** Completes the business side of negotiation
**Depends on (frontend):** FVS-009, FVS-034 (reuses `OfferTimeline`)
**Backend dependencies:** VS-028 (admin list/detail), VS-029 (admin counter/accept/reject)
**Backend endpoints used:**
```
GET /api/v1/admin/offers
GET /api/v1/admin/offers/{id}
POST /api/v1/admin/offers/{id}/counter
POST /api/v1/admin/offers/{id}/accept
POST /api/v1/admin/offers/{id}/reject
```
*(VS-028's admin list/detail and VS-029's admin actions are prose-only in the backend plan — every path above is a frontend-constructed placeholder, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin sees a queue of live/pending offers (filterable by status/deadline urgency), opens an offer to see the same `OfferTimeline` component the customer sees (reused verbatim — one negotiation view, two personas), and counters/accepts/rejects when it's the admin's turn.
**Routes:** `/admin/offers`, `/admin/offers/:id`.
**Components:** `AdminTable` (reused), `OfferTimeline` (reused from FVS-034), `OfferActionPanel` (reused, admin action set).
**State:** Server state; same polling pattern as FVS-034 for admins actively viewing an open negotiation.
**API integration:** Same wrong-turn/expired handling pattern as FVS-034, shared logic rather than reimplemented.
**UX states:** Queue empty/loading; deadline-urgency sort/filter (e.g., "expiring soon"); same per-turn action-set gating as the customer view.
**Responsive behavior:** `AdminTable` pattern for the queue; detail view identical layout to FVS-034 since it's the same component.
**Accessibility:** Same baseline as FVS-034 (shared component).
**Testing:** Reuses FVS-034's `OfferTimeline`/`OfferActionPanel` test suite parameterized for the admin action set; E2E: admin counters a live offer → customer side (FVS-034) reflects the new round.
**Documentation:** Shared with FVS-034's state diagram — one document, not two.
**Mergeable outcome:** Both sides of every negotiation can be operated without a generic status PATCH anywhere in the codebase.

---

#### FVS-036 — Accepted-Offer Checkout

**Priority:** P1 · **Risk:** High commerce integration · **Value:** Converts negotiation into revenue
**Depends on (frontend):** FVS-026, FVS-027, FVS-034
**Backend dependencies:** VS-030
**Backend endpoints used:**
```
POST /api/v1/me/offers/{id}/checkout
```
**Frontend capability:** From the accepted-offer banner (FVS-034), the customer checks out at the **frozen agreed price** within the checkout window — reusing FVS-026's consent/idempotency patterns and FVS-027's payment-verification flow, but entered from a different trigger and with the price already fixed (no cart, no price-change conflict UI needed here, since the agreed price cannot drift). An expired window is a distinct, clear terminal state (maps to a 410 from the backend) — not a generic error.
**Routes:** `/account/offers/:id/checkout` (or reuses `/checkout` with an offer context param — recommend a distinct route so the offer-checkout UI doesn't have to conditionally strip cart-specific elements from FVS-026's page).
**Components:** `OfferCheckoutSummary` (frozen price display, no editable line items), reuses `ConsentCheckboxGroup` (digital-final-sale) and the payment redirect/verification flow from FVS-027.
**State:** Minimal — mostly a read of the accepted offer plus the same idempotency-key pattern as FVS-026.
**API integration:** A second checkout attempt on an already-converted offer is rejected (idempotent/one-time) and shown as "already purchased" rather than retried; a normal-cart purchase of the same product elsewhere auto-closes the live offer server-side — if the customer navigates back to this offer after that happens, the UI reflects the now-closed state via refetch, not a stale cached "still accepted" view.
**UX states:** Window active (checkout available with live countdown reused from `DeadlineCountdown`); window expired (410 — clear terminal message, no retry path since the negotiation is over); already-converted (redirect to the resulting order in FVS-029); payment flow states identical to FVS-027.
**Responsive behavior:** Same as FVS-026.
**Accessibility:** Same as FVS-026; frozen-price display explicitly labeled "agreed price" so it's not confused with a live catalogue price.
**Testing:** Expired-window (410) integration test; already-converted-redirect test; E2E: accept offer → checkout within window → payment verified (reusing FVS-027's poller) → order appears in FVS-029's history at the agreed price, not list price.
**Documentation:** Offer-checkout sequence doc.
**Mergeable outcome:** An accepted negotiation converts into the same safe, verified payment pipeline as normal checkout, at the frozen price.

---

#### FVS-037 — Product Reviews (Public + Customer)

**Priority:** P1 · **Risk:** Medium abuse/aggregate correctness · **Value:** Storefront trust
**Depends on (frontend):** FVS-014, FVS-029 (verified-purchase badge context)
**Backend dependencies:** VS-031
**Backend endpoints used:**
```
GET /api/v1/products/{slug}/reviews
GET /api/v1/me/reviews
POST /api/v1/me/reviews
PATCH /api/v1/me/reviews/{id}
DELETE /api/v1/me/reviews/{id}
```
*(VS-031's endpoint line gives a literal path only for `GET /me/reviews`; the public-list and create/update/delete paths above are frontend-constructed, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Public product pages show a review list with average rating and a **Verified Purchase** badge computed and returned entirely server-side (the frontend never infers or displays this badge from its own purchase-history data — it renders exactly what the review record says, since the server recomputes it from entitlement/purchase state). Any verified (email-verified) customer — purchaser or not, per the approved open-review model — can leave one review per product, editable/deletable from `/account/reviews`.
**Routes:** Review section embedded in `/shop/:slug` (FVS-014); `/account/reviews` (added to account nav).
**Components:** `ReviewList`, `ReviewCard` (star rating display, `VerifiedPurchaseBadge`), `ReviewForm` (create/edit, rating 1–5 + text), `MyReviewsList`.
**State:** Server state; product's own review list and the customer's own review are separate queries (a customer's own pending edit shouldn't wait on the full public list to refetch).
**API integration:** Duplicate-review-per-product attempts are rejected server-side (UI instead offers "edit your existing review" once one exists — the create form becomes an edit form for that product if the customer already has one); content-filter rejections show the specific server message.
**UX states:** No reviews yet (empty state on product page); own-review exists → form becomes edit mode; duplicate-attempt (shouldn't normally be reachable given the above, but handled defensively); rating validation (1–5 only); delete confirm.
**Responsive behavior:** Review list paginates/loads-more on all widths; form fields stack on mobile.
**Accessibility:** Star rating input is keyboard-operable (arrow keys / number keys), not mouse-hover-only, with the numeric value announced; verified-purchase badge has real text, not an icon-only tooltip.
**Testing:** Badge-render-from-server-value-only test (frontend never computes it); duplicate-review UI-becomes-edit-mode test; E2E: verified customer (non-purchaser) leaves a review → appears publicly without a verified badge; E2E: purchaser leaves a review → badge appears.
**Documentation:** Explicit "no purchase required" rule documented in the review-form copy/help text so customers aren't confused why a non-purchaser can review.
**Mergeable outcome:** Reviews work end-to-end per the approved open-review model without the frontend ever inventing badge logic.

---

#### FVS-038 — Admin Review Moderation

**Priority:** P1 · **Risk:** Medium content moderation · **Value:** Protects catalogue quality
**Depends on (frontend):** FVS-009, FVS-037
**Backend dependencies:** VS-032
**Backend endpoints used:**
```
GET /api/v1/admin/reviews
GET /api/v1/admin/reviews/{id}
POST /api/v1/admin/reviews/{id}/hide
POST /api/v1/admin/reviews/{id}/restore
```
*(VS-032's endpoint line is prose only — placeholders above, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin lists reviews, hides abusive ones (removed from public view, not deleted — history preserved), and restores them.
**Routes:** `/admin/reviews`, `/admin/reviews/:id`.
**Components:** `AdminTable` (reused), `ReviewCard` (reused, admin context adds hide/restore actions), `StatusBadge` (visible/hidden).
**State:** Server state.
**API integration:** Hide/restore immediately affects the public `ReviewList` query (FVS-037) via cache invalidation if both are open in the same session context; otherwise a normal refetch on the public page picks it up.
**UX states:** Hide confirm; restore; hidden-state badge; non-admin 404 (consistent with the rest of admin).
**Responsive behavior:** `AdminTable` pattern.
**Accessibility:** Hide/restore buttons have clear accessible names, not icon-only.
**Testing:** Integration test that a hidden review disappears from `GET /products/{slug}/reviews` results (cross-checked against FVS-037); E2E: admin hides a review → public page no longer shows it → admin restores → it reappears.
**Documentation:** Moderation-behavior note (hide, not delete).
**Mergeable outcome:** Admin can protect catalogue quality without destroying review history.

---

#### FVS-039 — Customer Wishlist

**Priority:** P2 · **Risk:** Low · **Value:** Engagement + merchandising signal
**Depends on (frontend):** FVS-014
**Backend dependencies:** VS-033
**Backend endpoints used:**
```
GET /api/v1/me/wishlist
PUT /api/v1/me/wishlist/{product_id}
DELETE /api/v1/me/wishlist/{product_id}
```
**Frontend capability:** A verified customer adds/removes products to a wishlist from the product card (FVS-013) or detail page (FVS-014), and views the full list at `/account/wishlist`. Add/remove is idempotent — clicking "add" on an already-wishlisted item is a harmless no-op, matching the backend's idempotent PUT.
**Routes:** `/account/wishlist` (added to account nav); toggle embedded in `ProductCard`/product detail.
**Components:** `WishlistToggleButton` (heart icon, filled/outline state), `WishlistPage` (reuses `ProductGrid`).
**State:** Server state; the toggle button's filled/outline state is derived from the wishlist query, with optimistic toggling and rollback on failure.
**API integration:** Removing a product that was later deleted from the catalogue is handled gracefully (the wishlist entry disappears or shows a "no longer available" placeholder rather than crashing the grid render).
**UX states:** Toggle optimistic/confirmed/rolled-back; empty wishlist; deleted-product-in-wishlist placeholder.
**Responsive behavior:** Same `ProductGrid` responsive behavior as FVS-013.
**Accessibility:** Heart toggle has `aria-pressed` and an accessible name that changes with state ("Add to wishlist" / "Remove from wishlist").
**Testing:** Idempotent-toggle unit test; optimistic-rollback test; E2E: wishlist a product from the grid → appears on `/account/wishlist` → remove → gone.
**Documentation:** None beyond inline behavior notes.
**Mergeable outcome:** Customers can maintain a wishlist end-to-end; admin's aggregate wishlist counts (used later in FVS-041) are fed by real customer activity.

---

#### FVS-040 — Admin BYI Pipeline & Funnel Analytics

**Priority:** P1 · **Risk:** Medium state machine · **Value:** Measures the highest-value lead channel
**Depends on (frontend):** FVS-009, FVS-015
**Backend dependencies:** VS-035
**Backend endpoints used:**
```
GET /api/v1/admin/custom-requests
GET /api/v1/admin/custom-requests/{id}
PATCH /api/v1/admin/custom-requests/{id}
POST /api/v1/admin/custom-requests/{id}/transition
GET /api/v1/admin/custom-requests/{id}/attachments/{attachment_id}
GET /api/v1/admin/analytics/custom-requests/funnel
```
*(VS-035's endpoint line gives a literal path only for the funnel endpoint — the list/detail/update/transition/attachment paths above are frontend-constructed, `NEEDS BACKEND CONFIRMATION`, §17.)*
**Frontend capability:** Admin manages the BYI lead pipeline through its explicit states (New → Contacted → Quoted → In Progress → Completed, or Closed/Lost as an exit at any point), enters a quote amount when transitioning to Quoted, downloads private attachments (admin-only — the frontend never constructs or guesses the attachment URL, it always follows the server-provided admin download link), and views a funnel chart of conversion by stage.
**Routes:** `/admin/custom-requests`, `/admin/custom-requests/:id`, `/admin/custom-requests/funnel`.
**Components:** `AdminTable` (reused), `RequestPipelineStageBadge`, `TransitionActionPanel` (legal-next-state-only actions, same pattern as FVS-030's line transitions), `QuoteAmountInput` (`MoneyInput` reused), `AttachmentDownloadLink`, `FunnelChart` (see the `dataviz` design guidance for chart styling).
**State:** Server state; funnel analytics is a separate read query from the pipeline list.
**API integration:** An expired attachment (per the lead's retention window) is a distinct "no longer available" state, not a broken-link error; Quoted transition requires the amount field, validated before submission to avoid a round-trip failure for a known-required field.
**UX states:** Pipeline stage transitions (legal-only, same pattern as FVS-030); Lost-outcome capture; expired-attachment state; funnel loading/empty/populated.
**Responsive behavior:** `AdminTable` pattern for the list; funnel chart reflows to a simpler bar/stacked view on narrow viewports rather than a dense multi-series layout.
**Accessibility:** Funnel chart includes a text/table equivalent of the data (not chart-only), per standard chart accessibility practice.
**Testing:** Legal-transition-only test (reuses the FVS-030 pattern); quote-required-field validation test; expired-attachment display test; E2E: new request → contacted → quoted (amount entered) → completed; funnel reflects the counts.
**Documentation:** Lead pipeline state diagram mirrored from backend doc.
**Mergeable outcome:** Admin can operate and measure the custom-print lead lifecycle end-to-end.

**Note on VS-034 (download analytics rollup):** no dedicated FVS — it's a backend data-retention job, but its one read endpoint (`GET /admin/analytics/downloads`) *is* directly consumed by FVS-041 (Admin Analytics Dashboard) as a first-class widget, not merely "fed into" it. This is direct frontend work embedded in FVS-041, not a "no UI" case — see the corrected §18 matrix row.

### Milestone FM-E — Reporting, Data Rights & Release

#### FVS-041 — Admin Analytics Dashboard

**Priority:** P2 · **Risk:** Medium reporting correctness · **Value:** Admin decision support
**Depends on (frontend):** FVS-005; reuses data produced by FVS-030 (orders), FVS-033/034 (offers), FVS-037 (reviews), FVS-039 (wishlist), FVS-021 (downloads)
**Backend dependencies:** VS-036 (core), VS-034 (download analytics), VS-033 (wishlist counts, reused)
**Backend endpoints used:**
```
GET /api/v1/admin/analytics/overview
GET /api/v1/admin/analytics/revenue
GET /api/v1/admin/analytics/recent-purchases
GET /api/v1/admin/analytics/customers
GET /api/v1/admin/analytics/top-rated
GET /api/v1/admin/analytics/downloads
```
*(VS-036's endpoint line is prose only ("Admin analytics overview/revenue/recent-purchases/customers/top-rated") — every path above is a frontend-constructed placeholder, `NEEDS BACKEND CONFIRMATION`, §17. `GET /admin/analytics/downloads` is VS-034's endpoint, quoted directly.)*
**Frontend capability:** A single dashboard surfaces overview KPIs, revenue (split physical vs STL per order line, matching the backend's attribution model — the frontend never re-derives this split itself, it renders exactly what the revenue endpoint returns), recent purchases, customer stats, top-rated products, download analytics, and pending-offers count, all within admin-selectable, bounded date ranges.
**Routes:** `/admin/analytics` (the bare `/admin` path is reserved for a future admin landing page, not this dashboard).
**Components:** `DashboardKpiGrid`, `RevenueChart`, `RecentPurchasesList`, `TopRatedList`, `DateRangePicker` (bounded — cannot select an unbounded/all-time range if the backend requires a bound; confirm the exact bound in §17). Follows the `dataviz` skill's chart/color guidance for any chart component introduced here.
**State:** Server state per widget, all keyed by the shared selected date range (URL-synced so a dashboard view is shareable/bookmarkable, consistent with FVS-013's URL-state pattern).
**API integration:** An empty date range (no activity) renders an explicit "no data in this period" state per widget, not a misleading zeroed chart that looks like an error; refunded-revenue treatment follows exactly whatever the backend's agreed reporting contract returns — the frontend does not apply its own opinion about whether refunds should net against revenue.
**UX states:** Loading per widget (independent skeletons, not one blocking spinner for the whole page); empty-range; error-per-widget (one failing widget doesn't blank the whole dashboard); date-range validation (out-of-bounds selection rejected client-side before request).
**Responsive behavior:** Desktop: multi-column KPI grid + full-width charts below. Tablet: 2-column KPI grid. Mobile: single-column stacked KPIs and charts, each chart simplified per the `dataviz` responsive guidance.
**Accessibility:** Every chart has a text/table data-equivalent; KPI tiles are readable by screen readers as label+value pairs, not just large decorative numbers; `DateRangePicker` is keyboard-operable (arrow keys between dates, `Enter` to select) with the current range announced on change, not just visually indicated.
**Testing:** Per-widget independent-error unit tests; date-range bound validation test; empty-range display test; E2E: admin selects a date range → all widgets update consistently.
**Documentation:** Metric definitions mirrored verbatim from the backend's metric-definition doc so dashboard copy and backend definitions cannot disagree (e.g., what counts as "revenue" for a refunded line).
**Mergeable outcome:** Admin gets real business visibility without any metric being independently invented on the frontend.

---

#### FVS-042 — Admin Audit Log Viewer

**Priority:** P2 · **Risk:** Medium security/history · **Value:** Operational traceability
**Depends on (frontend):** FVS-005
**Backend dependencies:** VS-037
**Backend endpoints used:**
```
GET /api/v1/admin/audit-logs
GET /api/v1/admin/audit-logs/{id}
```
**Frontend capability:** Admin filters and reads audit log entries (by actor/action/entity/request/date) — strictly read-only, no mutation UI exists because none exists on the backend.
**Routes:** `/admin/audit-logs`, `/admin/audit-logs/:id`.
**Components:** `AdminTable` (reused), `AuditFilterBar`, `AuditLogDetail`.
**State:** Server state with URL-synced filters (consistent pattern).
**API integration:** No write actions anywhere in this slice — the UI must not add one (e.g., no "delete log" button, even for admins), matching the backend's explicit no-mutation-routes rule.
**UX states:** Empty filtered results; loading; filter-across-date-partition boundary (large ranges may be slower — a loading state that doesn't look broken); detail view for a single entry.
**Responsive behavior:** `AdminTable` pattern; filter bar collapses into a filter-sheet on mobile.
**Accessibility:** Filter controls are properly labeled form fields, not icon-only toggles.
**Testing:** Read-only-surface test (no interactive element anywhere issues a write request); integration test for filter combinations; E2E: admin filters by actor and date range → sees matching entries.
**Documentation:** Audit event taxonomy reference mirrored from backend doc, so admins can interpret entries without guessing.
**Mergeable outcome:** Admin can investigate material actions without database access, with a UI that cannot accidentally mutate history.

---

#### FVS-043 — Customer Data Export

**Priority:** P2 · **Risk:** Medium privacy/ownership · **Value:** Data rights
**Depends on (frontend):** FVS-006
**Backend dependencies:** VS-038
**Backend endpoints used:**
```
GET /api/v1/me/export
```
**Frontend capability:** From account settings/profile, a customer requests and downloads their own JSON data export (profile, addresses, orders, downloads, reviews, offers) — a plain-link download of whatever the backend generates, with no client-side reshaping of the export content, since the backend defines exactly what belongs in it (and explicitly excludes secrets/internal notes/provider secrets).
**Routes:** Action embedded in `/account/profile` (FVS-006) — a "Download my data" button; no standalone results page beyond a triggered download/success state.
**Components:** `DataExportButton`.
**State:** Local pending/success/error state for the export request only.
**API integration:** Rate-limited exports show a clear retry-after message if the customer requests too frequently; the export itself downloads as a file (native browser download of the JSON response) rather than being rendered inline, since it's meant to be a portable artifact, not a UI view.
**UX states:** Requesting; rate-limited; success (download triggered); error/retry.
**Responsive behavior:** Single button at all widths — no layout complexity.
**Accessibility:** Button communicates loading state via `aria-busy`, and success/failure via `aria-live` region since the "result" is a file download, not a page change a screen reader would otherwise notice.
**Testing:** Rate-limit-message integration test; E2E: request export → file download triggered.
**Documentation:** Export-contents summary mirrored from backend doc so customer-facing help copy is accurate.
**Mergeable outcome:** A customer can exercise a real data-portability right without support intervention.

---

#### FVS-044 — Customer Account Deletion

**Priority:** P1 · **Risk:** High privacy/referential integrity · **Value:** Data rights + compliance
**Depends on (frontend):** FVS-029 (needs order-state awareness), FVS-006
**Backend dependencies:** VS-039
**Backend endpoints used:**
```
DELETE /api/v1/me
```
**Frontend capability:** A customer requests account deletion (anonymisation) from account settings, with a **fresh-auth requirement** (re-enter password / re-authenticate immediately before the destructive action, not relying on an old session) and a clear explanation beforehand of what is retained (anonymized financial/download history) versus removed (PII, login capability, addresses/reviews/wishlist). A blocked deletion (open orders or unsettled refunds) shows the specific blocking reason and links to the relevant order(s) rather than a generic failure.
**Routes:** `/account/settings` (or a `/account/delete` confirmation sub-route) — a multi-step confirmation flow, not a single accidental-click button, given irreversibility.
**Components:** `AccountDeletionFlow` (re-auth step → consequences summary → final confirm), `ReAuthPrompt`, `BlockedDeletionNotice` (links to open orders via FVS-029's order detail route).
**State:** Local flow-step state; on success, immediately clears all cached auth/session state and redirects to a logged-out landing page — no lingering client cache of the now-anonymised account.
**API integration:** A blocked-by-open-order response is rendered with the actual order reference(s) so the customer knows exactly what to resolve first; the fresh-auth step re-uses the login mechanism from FVS-003 rather than inventing a separate credential check.
**UX states:** Consequence summary (retained vs removed, explicit and specific — not vague "some data will be kept"); re-auth required/failed; blocked (open order/unsettled refund, with links); confirmed → success → logged out; repeated-deletion-attempt (idempotent/safe per backend, shown as already-deleted rather than an error if somehow re-triggered).
**Responsive behavior:** Single-column flow at all widths — this is a deliberately slow, careful, non-dense UI regardless of viewport.
**Accessibility:** Each step requires an explicit, unambiguous confirmation action (e.g., typing "DELETE" or a clearly labeled final button) — never a pre-checked checkbox; blocked-reason text is programmatically associated with the disabled confirm action.
**Testing:** Blocked-deletion integration test (open order → specific reason shown, action disabled); re-auth-required test; E2E: customer with no open orders completes deletion → cannot log in afterward (cross-checked against FVS-003).
**Documentation:** Anonymisation consequence summary mirrored precisely from the backend's field-map doc — this copy must not overstate or understate what's retained, for legal accuracy.
**Mergeable outcome:** Account deletion satisfies the frozen retention model in the UI, with no dark patterns and no vague copy about what happens to the customer's data.

---

#### FVS-045 — Frontend Production Readiness & Release Hardening

**Priority:** P0 release gate · **Risk:** Critical operations · **Value:** Makes completed features safe to launch
**Depends on (frontend):** All preceding slices
**Backend dependencies:** VS-040 (mirrors its release-gate philosophy on the frontend side; consumes nothing new)
**Backend endpoints used:** None new — this slice hardens existing integrations, it does not add features.
**Frontend capability:** Not a user-facing feature — a release-gate slice, exactly mirroring the backend's VS-040. Covers: real 404/500/offline pages (not framework defaults), production error-boundary reporting (no unhandled blank screens), removal of any dev-only banners/mocks (e.g., FVS-001's health-check banner is dev-only and must not ship to production), CSP/security headers appropriate to the chosen framework's deployment, verified Lighthouse/Core Web Vitals budget on the top public pages (home, catalogue, product detail — the highest-traffic, most SEO-sensitive pages), a full accessibility sweep (axe or equivalent) across every route, and a check that no secret/API key is embedded in client-shipped bundles.
**Routes:** `/404`, `/500` (or equivalent error boundary), offline fallback.
**Components:** `NotFoundPage` (real content, not a framework placeholder — links back to shop/home), `ErrorPage`, `OfflineBanner`.
**State:** N/A — this slice is cross-cutting hardening, not a new state domain.
**API integration:** Verifies every slice's error-handling paths (§10) are actually exercised against the real backend's error shapes in a staging environment, not just mocked in tests.
**UX states:** N/A beyond the error/offline pages themselves.
**Responsive behavior:** Verifies the responsive requirements stated in every prior slice actually hold at 320px/768px/1024px/1440px breakpoints, not just at whatever viewport each slice happened to be developed in.
**Accessibility:** Full axe-core sweep across every route with zero critical/serious violations; manual keyboard-only pass through the five most critical journeys (§16).
**Testing:** Lighthouse/Web Vitals budget check in CI for public pages; full accessibility audit; bundle-analysis check for accidental secret leakage; smoke E2E across every route confirming no route 500s on a cold load.
**Documentation:** Frontend deployment/runbook doc (build, environment variables, CDN/cache headers for static assets, rollback procedure).
**Mergeable outcome:** Release is blocked until the frontend's own security, performance, and accessibility gates pass — matching the backend's philosophy that "feature tests are green" is not sufficient for launch.

---

#### FVS-046 — SEO Rendering, Sitemap & Robots

**Priority:** P1 · **Risk:** Medium — organic-discovery dependent · **Value:** Long-term acquisition channel
**Depends on (frontend):** FVS-013, FVS-014
**Backend dependencies:** VS-013 (SEO fields on product/category data) — backend plan explicitly assigns rendering/sitemap generation to the frontend/web layer (§5, F-013)
**Backend endpoints used:**
```
GET /api/v1/products   (for sitemap generation — slugs/updated-at)
GET /api/v1/products/{slug}   (SEO fields per product)
GET /api/v1/categories
```
**Frontend capability:** Dedicated implementation of: per-page `<title>`/meta description sourced from each product/category's SEO fields (never hardcoded per-product copy), canonical URLs (especially important given filter/sort query-string variants of `/shop` from FVS-013 — canonical should point at the unfiltered or canonical-filtered URL per an agreed strategy), Open Graph/Twitter card tags for product pages (image = cover image from FVS-012), structured data (Product schema.org JSON-LD) on product detail pages, a generated `sitemap.xml` (static pages + all live product/category slugs, regenerated on a build/revalidation cadence appropriate to the chosen framework), `robots.txt`, and a genuine (crawlable, correctly-status-coded) 404 for removed/hidden products rather than a client-side-only "not found" render that still returns HTTP 200 to a crawler.
**Routes:** `/sitemap.xml`, `/robots.txt`; meta/structured-data applied across `/`, `/shop`, `/shop/:slug`, `/about`.
**Components:** `SeoHead` (shared meta/OG/canonical/JSON-LD component consumed by every public page), sitemap-generation build step/route handler.
**State:** N/A — build-time/request-time data composition, not client state.
**API integration:** Sitemap generation must page through the full product list (respecting VS-013's live/visible-only exclusion rules) rather than assuming a small fixed count; a product that becomes hidden/deleted is dropped from the next sitemap regeneration.
**UX states:** N/A (crawler-facing, not a rendered UI state) — but the 404 case must return an actual HTTP 404 status, verified in FVS-045's testing, not just a friendly-looking page served with a 200.
**Responsive behavior:** N/A.
**Accessibility:** Structured data and meta tags don't affect on-page accessibility directly, but the `SeoHead` component must not introduce duplicate/conflicting `<title>` elements that break assistive-tech page-title announcements on client-side navigation.
**Testing:** Snapshot tests verifying correct meta/OG/JSON-LD output per product's SEO fields; sitemap-generation test against a paginated product list (including an exclusion case for a hidden product); HTTP-status test that a removed product's URL returns real 404, not 200.
**Documentation:** SEO field-to-tag mapping doc (which backend field feeds which meta tag) so content/marketing knows what to fill in on the admin side (FVS-011) to control SEO output.
**Mergeable outcome:** Product/category pages are genuinely crawlable and indexable, satisfying F-013 entirely on the frontend/rendering side as the backend plan specifies.

## 6. Frontend-Only Features

These map to the backend plan's own §5 list ("Public/front-end features that do not need their own backend slice") and are folded into the FVS slices above rather than treated as orphaned work:

| Backend ID | Feature | Where it lives in this plan |
|---|---|---|
| F-001 | Home page | FVS-022 |
| F-002 | Floating WhatsApp button | FVS-022 (global component), consumes VS-007 public settings |
| F-003 | About Us | FVS-022 (static content) |
| F-011 | Product WhatsApp click-to-chat | FVS-014, consumes VS-013 product data + VS-007 public settings |
| F-013 | SEO rendering/sitemaps | FVS-046 (dedicated), plus per-page meta baked into FVS-013/014 |

No backend slice is invented for any of these. Each consumes only endpoints that already exist in VS-007/VS-013.

## 7. Shared Frontend Architecture

Per the backend's own merge-strategy rule ("shared abstractions are introduced by the first real feature that needs them"), the following shared pieces are **not** built as a standalone slice — each is introduced by the FVS listed and reused after:

| Shared piece | Introduced by | Reused by |
|---|---|---|
| API client (`apiClient`, RFC 9457 parsing) | FVS-001 | Every slice |
| `AuthProvider` / session state | FVS-003 | Every authenticated slice |
| `AdminProtectedRoute` | FVS-005 | Every admin slice |
| Base form primitives (`Form`, `TextField`, `PasswordField`, `Button`, `Alert`) | FVS-002 | Every write-flow slice |
| `AdminTable` | FVS-009 | FVS-010, 017, 019, 028, 030, 032, 035, 038, 040, 042 |
| `ConfirmDialog` | FVS-009 | Every destructive-action slice |
| `FileUploader` | FVS-012 | FVS-015, FVS-018 |
| `MoneyInput` / `PriceDisplay` | FVS-011, FVS-014 | FVS-024, 025, 026, 032, 033 |
| `CaptchaWidget` | FVS-015 | FVS-016 |
| `StatusBadge` | FVS-009 | FVS-017, 028, 029, 030, 032, 035, 038, 040 |
| `OrderLineItem` | FVS-029 | FVS-030, 031 |
| `OfferTimeline` / `OfferActionPanel` / `DeadlineCountdown` | FVS-034 | FVS-035, 036 |
| `PaymentStatusPoller` | FVS-027 | FVS-036 |
| `SeoHead` | FVS-046 | FVS-013, 014, 022 |

This table exists so slice authors know **where to look before building something that already exists**, not as a mandate to pre-build any of it early.

## 8. Authentication Architecture

- **Session model:** the backend issues a short-lived access cookie and a rotating, httpOnly refresh cookie (VS-003). The frontend cannot read either directly — auth state is always derived by calling `GET /api/v1/me` and caching the result (FVS-003/006), never by decoding a cookie client-side.
- **Protected routes:** two guard components — `ProtectedRoute` (any authenticated customer — VS-006's own test explicitly allows unverified-but-authenticated reads, e.g. FVS-006's profile page, so this guard checks login state only, not email-verification state) and `AdminProtectedRoute` (admin + MFA-verified-this-session). Both redirect rather than render a forbidden page for the customer case; the admin case renders the app's real 404 for non-admins, matching the backend's route-hiding behavior exactly (VS-005). Where a specific mutation requires the verified-email boundary (per the backend DoD, "verified-email boundary... applied" per mutating slice), that check is additional and per-endpoint — it is the server's rejection that's authoritative, not a separate frontend "verified" route guard.
- **Session expiration / refresh:** any `401` triggers exactly one silent `POST /auth/refresh` attempt via the API client (FVS-001); a second failure clears cached state and redirects to `/login?returnTo=<path>`. This is centralized in the API client, not reimplemented per slice.
- **CSRF:** the backend uses a double-submit cookie pattern (VS-003). The exact cookie name and expected request-header name are `NEEDS BACKEND CONFIRMATION` (§17) — the API client attaches it to every mutating request once confirmed.
- **MFA:** admin sessions carry an additional `mfaVerified` flag scoped to the current browser session (FVS-005); `AdminProtectedRoute` checks both `isAdmin` and `mfaVerified` before rendering any `/admin` route.
- **Hiding is not authorization.** Every route guard and conditionally-hidden element in this document (`AdminProtectedRoute`, hidden admin buttons, hidden privileged actions) is a UX convenience, never the actual security boundary. The backend must independently refuse any privileged request regardless of what the frontend shows or hides — no FVS slice should ship on the assumption that "the button isn't visible so the action is safe." This applies to every admin-only mutation in FM-B through FM-E, not just the auth slices.
- **Logout:** clears all cached TanStack Query state for the current user (not just the auth query) to avoid any stale-data leak into a subsequently logged-in different user on a shared device.

## 9. API Integration Architecture

- **Centralized client (FVS-001):** one `apiClient` module wraps `fetch`, handling base URL, JSON parsing, credential inclusion (cookies), CSRF header attachment, and RFC 9457 problem-response parsing into a typed `ApiError { status, type, title, detail, errors? }`.
- **Server state:** TanStack Query for every read/write that touches the backend. Query keys are structured hierarchically (`['products', 'list', filters]`, `['orders', 'detail', orderId]`) so invalidation can target precisely (e.g., checkout success invalidates `['cart']` and `['orders', 'list']` without over-invalidating unrelated queries).
- **Mutations:** every mutation that changes something another open view depends on explicitly lists its invalidation targets (documented per-slice above) rather than a blanket `invalidateQueries()` on every mutation, which would cause needless refetch storms on data-heavy admin screens.
- **Optimistic updates:** used only where a wrong optimistic guess is cheap to roll back and low-consequence (cart quantity, notification read-state, wishlist toggle, settings boolean toggle) — never for money-moving actions (checkout, refund creation, payment confirmation), which always wait for the server response before showing any success state.
- **Retry policy:** TanStack Query's default retry (with backoff) is used for transient network failures on **reads**; **mutations are never auto-retried** by the client because a naive retry of a non-idempotent write could double-submit — idempotency keys (checkout, offer-checkout, refund creation) are the mechanism that makes a *user-initiated* retry (e.g., clicking submit again after a timeout) safe, not silent client-side auto-retry.
- **Pagination:** the backend uses cursor pagination on list endpoints (VS-013, VS-023, VS-008, etc.). The exact cursor field name/shape is `NEEDS BACKEND CONFIRMATION` (§17); the frontend's `Pagination`/`LoadMore` components are built against whatever that shape turns out to be, abstracted behind one `usePaginatedQuery` hook so a later contract change touches one place.

## 10. Error Handling

The backend returns RFC 9457 problem responses (VS-001). The frontend does **not** treat every non-2xx the same way — each status class has a distinct UI pattern:

| Status | Frontend treatment |
|---|---|
| 400 / 422 (validation) | Inline field-level errors from the response's error detail, using the server's message text, not a client-invented one. |
| 401 | Silent refresh attempt (§8); on second failure, redirect to login with return path. |
| 403 | Rendered as the real 404 page when the backend itself hides existence (admin routes, foreign resource ownership — VS-005, VS-023 IDOR-hiding rule); rendered as an explicit "you don't have permission" only where the backend's own design intentionally reveals existence but denies action (confirm per-endpoint in §17 where ambiguous). |
| 404 | App's standard not-found page/component. |
| 409 | Conflict-specific UI per slice (price-change conflict in FVS-026, already-entitled in FVS-019, already-converted offer in FVS-036) — never a generic "conflict occurred" toast. |
| 410 | Expired-resource UI (offer checkout window in FVS-036) — distinct copy from a plain 404. |
| 429 | Rate-limit message with retry guidance, using a `Retry-After` value if the backend provides one (`NEEDS BACKEND CONFIRMATION`, §17). |
| 500 / unhandled | Generic "something went wrong, please try again" — never leaks stack traces or internal detail, logged to the error-boundary reporting set up in FVS-045. |
| Network failure (no response) | Distinct "you appear to be offline" state, never conflated with a 500. |

## 11. Upload Architecture

One reusable `FileUploader` component (introduced FVS-012, reused FVS-015/FVS-018) covers every upload surface: product images, BYI attachments, STL asset bundles. It provides:

- **Client-side pre-check** (type/size/count) mirroring the server's documented limits, purely to give fast feedback — the server's check is always the actual authority, and the component always surfaces the server's specific rejection reason if it disagrees with the client's pre-check.
- **Progress:** per-file upload progress via `XMLHttpRequest`/`fetch` upload-progress events (multipart POST, not chunked/resumable — nothing in the backend plan describes a resumable/chunked upload protocol, so none is assumed; confirm in §17 if large STL files need it).
- **Scanning state:** for surfaces where the backend performs async malware scanning (product images, BYI attachments, STL assets), the component supports a post-upload "scanning" polling phase before an item is usable (STL publish-gating in FVS-018), rather than treating "upload finished" as "ready."
- **Failure/retry:** a failed individual file can be retried without re-uploading the whole batch; a cancel-in-flight control aborts the underlying request.
- **Never assumes chunked/resumable upload, drag-reorder-only interaction, or a specific captcha/virus-scan vendor** — those are explicit gaps, §17.

## 12. Payment UX

Fully specified per-slice in FVS-026/027/028/036; the governing principle (from the brief and enforced by FVS-027's explicit anti-pattern test) is:

```
Cart → Checkout → Create checkout (FVS-026) → Payment initiation
  → Provider/payment page (external, mock in dev / Whish in prod)
  → Return to website → Payment verification/status (FVS-027, polled)
  → Success / Pending / Failed / Expired → Order (FVS-029)
```

The frontend **never** renders a success state from URL query parameters alone — every terminal state shown to the customer is the result of a backend-verified status read, polled until resolved or timed out. This applies identically to the mock provider (VS-021/022) and the live Whish provider (VS-027) — the UI does not change when the provider swap happens, only the destination the redirect points to.

## 13. SEO

Covered in full by FVS-046 (dedicated sitemap/robots/structured-data slice) plus per-page implementation inside FVS-013 (list/category meta) and FVS-014 (product meta, Open Graph, JSON-LD). Summary of what's owned where:

- **Title/description/canonical:** `SeoHead` component (FVS-046), fed by VS-013's SEO fields — sourced from the backend, never independently authored per-product in the frontend.
- **Open Graph/Twitter cards:** product detail (FVS-014), image = cover image from FVS-012.
- **Structured data:** `Product` schema.org JSON-LD on product detail pages only (FVS-046).
- **Sitemap/robots:** generated artifacts (FVS-046), regenerated on a cadence tied to the chosen rendering framework's build/revalidation model.
- **404 handling:** must return a genuine HTTP 404 status for removed/hidden product slugs, verified as part of the FVS-045 release gate — a client-side-only "not found" render that still returns 200 to a crawler is treated as a bug, not a style choice.
- **Dynamic routes:** `/shop/:slug` and `/shop?filters` must not each generate a separately-indexed low-value page — canonical strategy for filtered list views is decided in FVS-046 and is a `NEEDS BACKEND/TEAM CONFIRMATION` item only in the sense of confirming whether filter combinations should be indexable at all (a product/marketing decision, not a backend contract gap).

## 14. Responsive Strategy

General breakpoints used throughout: mobile ≤ 767px, tablet 768–1023px, desktop ≥ 1024px. Per-slice specifics are documented inline in §5; the patterns that recur across many slices:

- **Product grids** (FVS-013, FVS-022, FVS-039): 3–4 columns desktop → 2 columns tablet → 1–2 columns mobile.
- **Filters** (FVS-013): persistent sidebar desktop → collapsible panel tablet → full-screen sheet mobile.
- **Cart/checkout** (FVS-025, FVS-026): two-column with sticky summary desktop → stacked with sticky action bar mobile.
- **Admin tables** (every admin list slice via `AdminTable`): horizontal-scroll container rather than column-dropping, so no data silently disappears; stacked-card fallback specifically for simpler reference-data/settings tables (FVS-007, FVS-010) where column-per-card makes more sense than a scrolling table.
- **Order/offer detail with timelines** (FVS-029, FVS-030, FVS-034): two-column desktop (content + summary sidebar) → single stacked column mobile with summary surfaced first for quick scanning.
- **File uploaders** (FVS-012, FVS-015, FVS-018): drag-and-drop drop-zone desktop → tap-to-pick file input mobile (drag-and-drop is unreliable on touch), with a keyboard/button-based reorder fallback (§5, FVS-012) since drag-reorder alone fails both touch and accessibility needs.
- **Dashboards** (FVS-041): multi-column KPI grid + side-by-side charts desktop → single-column stacked, simplified charts mobile.

## 15. Accessibility

Cross-cutting commitments applied to every slice (specific applications noted per-slice in §5):

- **Keyboard navigation:** every interactive element (including drag-reorder, star ratings, countdown-adjacent actions) has a keyboard-operable equivalent — never a mouse/touch-only interaction.
- **Labels:** every form field has a programmatically associated label; every icon-only button has an accessible name via `aria-label`.
- **Focus management:** modals/dialogs (`ConfirmDialog`, `MakeOfferDialog`, admin dialogs) trap focus while open and return focus to the triggering element on close; route changes move focus to the new page's main heading so screen-reader users aren't left on a stale focus target.
- **Semantic HTML:** lists are real lists, tables are real tables with header scope, landmark regions (`header`/`nav`/`main`/`footer`) are present on every page (established in FVS-001).
- **Dialogs/modals:** `aria-modal="true"`, labeled by their heading, dismissible via `Escape`.
- **Form errors:** announced via `aria-live` regions on submit failure, associated to their field via `aria-describedby`, and focus moves to the first invalid field.
- **Color:** status/state is never conveyed by color alone anywhere in the plan (status badges, timelines, verified-purchase badges, colour swatches all pair color with text).
- **Charts** (FVS-041, FVS-040): every chart ships a text/table equivalent, per the `dataviz` skill's accessibility guidance.

## 16. Testing Strategy

- **Unit:** pure logic — `apiClient` parsing, `MoneyInput` cents handling, idempotency-key generation/reuse, status-derived button/action-set gating, URL-state serialization.
- **Component:** individual components in isolation with mocked data — forms, `AdminTable`, `FileUploader`, `OfferTimeline`, dialogs — including their UX-state variants (loading/empty/error/etc.) enumerated per-slice in §5.
- **Integration:** component + mocked API contract behavior — verifying a slice's UI reacts correctly to each documented backend response shape (success, each documented error, IDOR-hiding, conflict states) without hitting a real backend.
- **E2E:** full user journeys against a real (or realistic staging) backend. Minimum required E2E flows, each tied to the FVS(s) that deliver it:

1. Registration → verification → login — FVS-002, FVS-003
2. Login → browse → product detail → cart — FVS-003, FVS-013, FVS-014, FVS-025
3. Mixed physical + STL checkout — FVS-025, FVS-026
4. Payment success (verified, not redirect-assumed) — FVS-027
5. Payment failure/recovery — FVS-027
6. STL entitlement → download — FVS-019, FVS-020, FVS-021
7. Offer → counter → accept → checkout — FVS-033, FVS-034, FVS-036
8. Physical order → cancellation — FVS-029, FVS-031
9. Admin login → MFA — FVS-005
10. Admin product creation (with image upload) — FVS-011, FVS-012
11. Admin STL upload/version publishing — FVS-018
12. Admin order fulfillment (queue → transitions) — FVS-030
13. Refund (mandatory mixed-order partial refund) — FVS-032
14. BYI submission → admin processing — FVS-015, FVS-040
15. Account export/deletion — FVS-043, FVS-044

## 17. Backend Contract Questions / Gaps

Each item below is `NEEDS BACKEND CONFIRMATION` — this plan does not guess an answer and proceeds on the safest assumption stated, to be corrected once confirmed.

---
**Issue:** Cursor pagination response shape
**Backend slice:** VS-013, VS-023, VS-008, and every other cursor-paginated list
**Why frontend needs clarification:** `usePaginatedQuery` (§9) and every list UI (FVS-013, FVS-029, FVS-008, FVS-041) needs to know the exact field names for the cursor token, page size, and "more results" indicator.
**What is currently defined:** "Cursor pagination" is named as the mechanism; no field-level shape is given.
**What is missing:** Request param name(s) for the cursor and page size; response field name(s) for the next cursor and a has-more flag.
**Recommended question:** What are the exact request/response field names for cursor pagination, and is the cursor opaque (base64 token) or a raw sortable value the frontend could theoretically construct itself (it should not, but confirms whether to type it as opaque)?

---
**Issue:** RFC 9457 problem-response validation-error shape
**Backend slice:** VS-001 (base contract), every write endpoint
**Why frontend needs clarification:** FVS-002/011/026/etc. need to map field-level validation errors to specific form fields.
**What is currently defined:** "RFC 9457 base problem model" exists.
**What is missing:** Whether/how per-field validation errors are represented within the problem body (e.g., an `errors` array with `field`/`message`, or Pydantic's raw `loc`/`msg` shape passed through).
**Recommended question:** What is the exact JSON shape of a 422 validation-error problem response, field-by-field?

---
**Issue:** Auth cookie names and CSRF header contract — **RESOLVED at FVS-003 BATCH 3A**
**Backend slice:** VS-003
**What is currently defined:** Cookie names: `access_token` (httpOnly, Path `/`, 15m), `refresh_token` (httpOnly, Path `/api/v1/auth`, 30d), `csrf_token` (JS-readable, `SameSite=Lax`, Path `/`, 30d, does not rotate on refresh). CSRF header: `X-CSRF-Token`. Required for refresh/logout/every authenticated write; exempt for login and anonymous POSTs (register/verify/resend/password-reset).
**What is missing:** Nothing further — resolved. See `docs/plans/frontend-slices/FVS-003-IMPLEMENTATION-PLAN.md` §2 rows 10–13, 29–34 and §5.

---
**Issue:** Idempotency-Key mechanism for checkout/offer-checkout/refund creation
**Backend slice:** VS-021, VS-030, VS-026
**Why frontend needs clarification:** FVS-026/032/036 need to know the exact header name and whether the frontend generates the key or the backend does.
**What is currently defined:** "Idempotency, kill switch" are part of the checkout transaction; `idempotency_records` table exists.
**What is missing:** Header name (e.g., `Idempotency-Key`), key generation responsibility (client UUID vs server-issued), and key lifetime/reuse window.
**Recommended question:** What header carries the idempotency key, does the client generate it, and how long is a key considered valid for retry/replay?

---
**Issue:** Payment return/redirect contract and status-check endpoint
**Backend slice:** VS-021 (mock), VS-022, VS-027 (live)
**Why frontend needs clarification:** FVS-027 is the single most safety-critical slice in the plan and needs the exact return URL shape and a dedicated status-read endpoint (or confirmation that order detail is the correct read).
**What is currently defined:** Checkout creates a pending payment; webhook independently verifies; admin can reconcile/manually confirm.
**What is missing:** The exact return-URL query parameters the provider/mock redirects back with, whether a dedicated `GET` status endpoint exists distinct from order detail, and the recommended polling interval/timeout.
**Recommended question:** What does the payment-provider return redirect look like exactly, and is there a lightweight status-only endpoint the frontend should poll instead of the full order detail?
**Status (phase 5F, 2026-11-11, backend `2dfb27b`): PARTLY RESOLVED.** Confirmed from code and runtime: there is no customer payment route; `GET /api/v1/me/orders/{id}` (`status`, `payment.status`, `can_retry_payment`, `hold_expires_at`) is the read, and the frontend polls it (bounded, see `REAL-BACKEND-ACCEPTANCE.md` Phase 5F). The checkout and retry return URL is `{FRONTEND_BASE_URL}/checkout/return?order=<order_number>` (mock; the live provider's parameters wait on VS-032). **Still open:** the return URL carries an order *number*, and there is no customer lookup by number (`GET /me/orders` filters only by status/dates/cursor), so `/checkout/return` cannot open the order and stays a neutral handoff to the orders list. **Recommended question:** can the return URL carry the order `id` (UUID), or can a customer `GET /me/orders?order_number=` be added?

---
**Issue:** Resuming a live payment attempt from the order page
**Backend slice:** VS-024 (backend repo numbering; payment recovery)
**Why frontend needs clarification:** While an attempt is `pending`, `can_retry_payment` is `false`, and the order detail carries no `redirect_url`. The only route that returns the live attempt's URL is `POST /me/orders/{id}/payments`, as `409 PAYMENT_ALREADY_ACTIVE` with `redirect_url`. A customer who left the provider page without paying cannot get back to it from the order page; the frontend does not send a POST it is told is not allowed just to read that refusal.
**What is currently defined:** `PAYMENT_ALREADY_ACTIVE` carries `payment_id`, `payment_status`, `redirect_url` (null while `processing`). The frontend offers "Continue to payment" when it receives one.
**What is missing:** A customer-readable resume URL for a `pending` attempt (e.g. `payment.redirect_url` on `OrderDetailRead`, owner only), or a documented "resume" action.
**Recommended question:** Should `OrderDetailRead.payment` expose the live attempt's `redirect_url` to its owner, or should `can_retry_payment` be true for a `pending` attempt so the POST's `PAYMENT_ALREADY_ACTIVE` is the intended resume path?

---
**Issue:** Captcha provider
**Backend slice:** VS-014, VS-015
**Why frontend needs clarification:** `CaptchaWidget` (FVS-015/016) needs to know which provider's SDK/script to integrate (reCAPTCHA, hCaptcha, Turnstile all have different integration shapes and accessibility fallbacks).
**What is currently defined:** "Shared CaptchaPort" (backend abstraction).
**What is missing:** Which concrete captcha vendor is configured behind the port.
**Recommended question:** Which captcha provider is configured, and what site key should the frontend use per environment?

---
**Issue:** Order/order-line status enum values
**Backend slice:** VS-021, VS-024, VS-025
**Why frontend needs clarification:** `StatusBadge`/`OrderLineItem`/`TransitionActionPanel` (FVS-029, FVS-030, FVS-031) render status-specific copy/color and derive legal next actions — this requires the exhaustive, authoritative list of status string values per line type.
**What is currently defined:** Named states in prose (pending, paid, production, delivery, pickup, delivered, cancelled, returned, refunded) but no single enumerated contract.
**What is missing:** The exact enum values (and whether physical vs STL lines share one status enum or have separate ones) plus the legal-transition table if the frontend is expected to encode it itself rather than receive an "available actions" list per response.
**Recommended question:** Please provide the authoritative order-line status enum and transition table, and confirm whether API responses include an "available next actions" list or whether the frontend must encode the state machine itself.

---
**Issue:** Rate-limit response detail (429)
**Backend slice:** VS-040 (coverage), applied throughout
**Why frontend needs clarification:** FVS-003/015/016/033 all need to show an accurate retry-after message.
**What is currently defined:** Rate limiting is applied to every sensitive endpoint.
**What is missing:** Whether a `Retry-After` header or body field is included.
**Recommended question:** Do 429 responses include a `Retry-After` header or equivalent field the frontend can render as a countdown?

---
**Issue:** Image/asset URL format
**Backend slice:** VS-012
**Why frontend needs clarification:** `ImageGallery`/`ProductCard` (FVS-012, FVS-013, FVS-014) need to know how to construct or receive displayable image URLs, since raw storage keys must never be exposed per VS-018's precedent for STL files.
**What is currently defined:** Storage is behind a `StoragePort`; product images are re-encoded and stored with a generated key.
**What is missing:** Whether product-image API responses include a ready-to-use public URL, or a key the frontend must combine with a base path.
**Recommended question:** Does the product/image API response include a direct, public, ready-to-render URL per image, and is it stable across environments (dev/staging/prod)?

---
**Issue:** STL download endpoint path and invocation mechanism
**Backend slice:** VS-018
**Why frontend needs clarification:** FVS-021's `DownloadButton` must render a real anchor `href`, not a JS fetch, to preserve Range/resume support — it needs the exact path shape.
**What is currently defined:** "Entitlement-file download endpoint," nginx `X-Accel-Redirect` internally, never exposes storage key.
**What is missing:** The exact public path/verb the frontend links to (e.g., `GET /api/v1/me/entitlements/{id}/download`).
**Recommended question:** What is the exact download endpoint path the frontend should use as a plain anchor `href`?

---
**Issue:** Notification pagination and event `type` taxonomy
**Backend slice:** VS-008
**Why frontend needs clarification:** FVS-008's generic `NotificationItem` renderer needs the full list of `type` values as later slices add them, to avoid perpetual "add a case" churn without a shared registry.
**What is currently defined:** "Later slices add concrete event types."
**What is missing:** A living registry of `type` values as each slice (payment paid, offer countered, order shipped, etc.) introduces one.
**Recommended question:** Can the backend team maintain (or let frontend maintain, backend-reviewed) a single shared table of notification `type` values as each slice adds one, so the two teams don't drift?

---
**Issue:** Shipping-zone response shape
**Backend slice:** VS-019
**Why frontend needs clarification:** FVS-024/026 need the exact fields (name, rate in cents, active flag, and whether a zone has a human-readable region list) to render a zone picker.
**What is currently defined:** "Rates server-owned," "no automatic governorate mapping."
**What is missing:** Exact field names/shape of a shipping-zone object.
**Recommended question:** What is the exact shape of a shipping-zone object returned by `GET /shipping-zones`?

---
**Issue:** Admin "available actions" affordances for state-machine UIs
**Backend slice:** VS-024, VS-029, VS-035
**Why frontend needs clarification:** FVS-030/034/040 render only legal next actions per current state — cleanest if the API response itself lists them, otherwise the frontend must independently encode and maintain three separate state machines that could drift from backend reality.
**What is currently defined:** Legal/illegal transitions are enforced server-side; prose describes the states.
**What is missing:** Whether responses include a machine-readable "available actions" list.
**Recommended question:** Can order/offer/custom-request detail responses include an `available_actions` (or equivalent) field so the frontend never has to independently re-encode the state machine?

---
**Issue:** Timezone display convention
**Backend slice:** Global (DoD states "timestamps use UTC")
**Why frontend needs clarification:** Countdown/deadline UIs (FVS-034's `DeadlineCountdown`, FVS-036's checkout window) need to know what local timezone to *display* to a Lebanon-based customer base, even though storage/transport is UTC.
**What is currently defined:** Timestamps use UTC (storage/transport only).
**What is missing:** Confirmed display timezone (assume Asia/Beirut, browser-local, or configurable) — not a backend contract gap so much as a product decision the frontend needs before FVS-034 ships.
**Recommended question:** Should countdowns/timestamps display in the customer's browser-local time or a fixed Asia/Beirut business timezone?

---
**Issue:** Offer / offer-round status enum values
**Backend slice:** VS-028, VS-029
**Why frontend needs clarification:** FVS-034/FVS-035's `OfferTimeline`/`OfferActionPanel`/polling logic need to know the exhaustive status-string enum for an offer and each round, parallel to the order-status gap already listed above — this was missed in the original gap list even though the same "prose states, no literal enum" problem applies (VS-028/029 describe states only as "first append-only round," "turn/deadline," "accept freezes agreed price," "reject arms cooldown," never as a literal set of enum values).
**What is currently defined:** Prose descriptions of offer lifecycle events and transitions; no enumerated `status` field values for an offer or a round.
**What is missing:** The exhaustive enum (e.g., is it `pending`/`countered`/`accepted`/`rejected`/`withdrawn`/`expired`, or different literal values?) for both offer-level and round-level status, and whether responses include an `available_actions` list (see the related item above).
**Recommended question:** Please provide the authoritative offer and offer-round status enum, parallel to the order-line status enum requested above.

---
**Issue:** Does registration (VS-002) log the user in? — **RESOLVED at FVS-002 BATCH 2 contract sync**
**Backend slice:** VS-002
**Why frontend needs clarification:** FVS-002 needs to know whether to redirect a freshly-registered (but not yet verified) user into an authenticated state or to a plain "check your email" page with no session established.
**What is currently defined:** Confirmed: registration does **not** establish a session — no auth state, no cookies. The customer logs in separately (via VS-003) after verifying their email.
**What is missing:** Nothing further — resolved. See `docs/plans/frontend-slices/FVS-002-IMPLEMENTATION-PLAN.md` §1 row 15.

---
**Issue:** Turnstile captcha contract for registration/resend (VS-002) — distinct from the BYI captcha item above
**Backend slice:** VS-002
**Why frontend needs clarification:** Cloudflare Turnstile will be added later to the registration and resend-verification forms; FVS-002's form/schema needs to stay composable for it without a rewrite once it lands.
**What is currently defined:** Turnstile is the confirmed provider (unlike the BYI captcha item above, whose provider is still open); exact field name and request/response contract are not yet confirmed.
**What is missing:** The request field name Turnstile's token should be sent under, and whether it gates registration, resend, or both.
**Recommended question:** What field name and validation contract does the backend expect for the Turnstile token on `POST /auth/register` and `POST /auth/resend-verification`, and when is it being turned on?

---
**Issue:** Frontend-constructed REST paths for backend slices whose "Endpoint / entrypoint" line is prose-only
**Backend slice:** VS-007 (settings list), VS-010 (admin CRUD paths), VS-011, VS-012, VS-015 (admin half), VS-016, VS-018 (download path), VS-019 (admin shipping-zone CRUD), VS-020 (cart item add/update/delete), VS-022 (admin payment paths), VS-024 (admin order list/detail/update — line-transition path separately flagged), VS-025, VS-026, VS-027 (payment status read), VS-028 (admin offer list/detail), VS-029 (both customer and admin actions), VS-031 (all review paths except `GET /me/reviews`), VS-032, VS-035 (admin BYI CRUD/attachment-download paths), VS-036
**Why frontend needs clarification:** This document's "Backend endpoints used" blocks quote a literal path wherever `docs/plans/backend/vertical-slice-plan.md` gives one, but for the slices listed above the backend document only describes the capability in prose (e.g., VS-011: "Admin product list/create/detail/update/delete" — no literal path anywhere), and this document had, in an earlier draft, nonetheless stated specific concrete REST paths (e.g., `POST /api/v1/admin/products`) with no visible caveat. An independent review (see revision note below) caught three slices (VS-020, VS-028, VS-031) that weren't even in this list's first draft, plus roughly a dozen more that were listed here but not flagged inline in §5 where a reader would actually see the risk.
**What is currently defined:** Every affected endpoint block in §5 now carries an inline `NEEDS BACKEND CONFIRMATION` note directly beneath it (not just this one paragraph) — those paths follow this app's evident REST convention (mirroring the slices that *do* have literal paths) but remain **frontend-constructed inferences, not backend-confirmed contracts**, exactly the failure mode `bekaa3d-api-contract` (project skill) exists to prevent.
**What is missing:** An OpenAPI spec, or direct backend confirmation, for the exact path/verb of every endpoint under the affected slices above.
**Recommended question:** Please publish (or confirm) the literal REST path and HTTP verb for every endpoint under VS-007, VS-011, VS-012, VS-015 (admin), VS-016, VS-019 (admin), VS-020 (item mutations), VS-022 (admin), VS-024 (base list/detail/update), VS-026, VS-028 (admin), VS-029, VS-031 (all but `GET /me/reviews`), VS-032, VS-035 (admin), and VS-036 before any FVS slice in those areas is implemented against the paths shown in §5 of this document — treat every path in this document for those slices as a placeholder, not a contract, until then.

## 18. Frontend ↔ Backend Traceability Matrix

| Frontend Slice | Backend Slice(s) | Main Routes | Main API Endpoints | Customer/Admin | Status |
|---|---|---|---|---|---|
| FVS-001 | VS-001 | `/` (shell) | `GET /health/live`, `GET /health/ready` | N/A (foundation) | Direct frontend work |
| FVS-002 | VS-002 | `/register`, `/verify-email` | `POST /auth/register`, `/verify-email`, `/resend-verification` | Customer | Direct frontend work |
| FVS-003 | VS-003 | `/login` | `POST /auth/login`, `/logout`, `/refresh` | Customer | Direct frontend work |
| FVS-004 | VS-004 | `/forgot-password`, `/reset-password` | `POST /auth/password-reset/request`, `/confirm` | Customer | Direct frontend work |
| FVS-005 | VS-005 | `/admin/login`, `/admin/mfa/*` | `POST /auth/mfa/*` | Admin | Direct frontend work |
| FVS-006 | VS-006 | `/account/profile` | `GET /me` | Customer | Direct frontend work |
| FVS-007 | VS-007 | `/admin/settings` | `GET/PATCH /admin/settings/{key}`, `GET /settings/public` | Admin (+ public read shared) | Direct frontend work |
| FVS-008 | VS-008 | `/account/notifications` | `GET/PATCH /me/notifications*` | Customer | Direct frontend work |
| FVS-009 | VS-009 | `/admin/customers*` | `GET/PATCH /admin/users*` | Admin | Direct frontend work |
| FVS-010 | VS-010 | `/admin/categories`, `/materials`, `/colours` | Admin CRUD + public lists | Admin (+ public read shared) | Direct frontend work |
| FVS-011 | VS-011 | `/admin/products*` | Admin product CRUD | Admin | Direct frontend work |
| FVS-012 | VS-012 | `/admin/products/:id/edit` (images tab) | Admin image upload/order/cover | Admin | Direct frontend work |
| FVS-013 | VS-013, VS-010 | `/shop` | `GET /products`, `/search/suggestions` | Customer (public) | Direct frontend work |
| FVS-014 | VS-013, VS-007 | `/shop/:slug` | `GET /products/{slug}`, `/settings/public` | Customer (public) | Direct frontend work |
| FVS-015 | VS-014 | `/bring-your-idea` | `POST /custom-requests` | Customer (guest) | Direct frontend work |
| FVS-016 | VS-015 | `/contact` | `POST /contact-messages` | Customer (guest) | Direct frontend work |
| FVS-017 | VS-015 | `/admin/contact-messages*` | Admin contact CRUD | Admin | Direct frontend work |
| FVS-018 | VS-016 | `/admin/products/:id/assets` | Admin asset-version upload/publish | Admin | Direct frontend work |
| FVS-019 | VS-017 | Embedded (customer/product detail) | `POST /admin/users/{id}/entitlements` | Admin | Direct frontend work |
| FVS-020 | VS-017 | `/account/library` | `GET /me/entitlements*` | Customer | Direct frontend work |
| FVS-021 | VS-018 | `/account/downloads` | `GET /me/downloads`, download endpoint | Customer | Direct frontend work |
| FVS-022 | — (F-001/002/003) | `/`, `/about` | `GET /settings/public`, `GET /products` | Customer (public) | Frontend-only |
| FVS-023 | VS-019 | `/account/addresses` | `GET/POST/PATCH/DELETE /me/addresses*` | Customer | Direct frontend work |
| FVS-024 | VS-019 | `/admin/shipping-zones` | Admin shipping-zone CRUD, `GET /shipping-zones` | Admin (+ public read shared) | Direct frontend work |
| FVS-025 | VS-020 | `/cart` | `GET/POST/PATCH/DELETE /cart*` | Customer | Direct frontend work |
| FVS-026 | VS-021 | `/checkout` | `POST /checkout`, `GET /shipping-zones` | Customer | Direct frontend work |
| FVS-027 | VS-022, VS-021, VS-027 | `/checkout/payment-result` | Order/payment status read | Customer | Direct frontend work — needs backend confirmation (§17) |
| FVS-028 | VS-022 | `/admin/payments*` | Admin payment list/detail/reconcile/confirm | Admin | Direct frontend work |
| FVS-029 | VS-023 | `/account/orders*` | `GET /me/orders*` | Customer | Direct frontend work |
| FVS-030 | VS-024 | `/admin/orders*` | Admin order list/detail/update/transition | Admin | Direct frontend work — needs backend confirmation (§17) |
| FVS-031 | VS-025 | Embedded (order detail, both personas) | Customer/admin cancel, line transition | Customer + Admin | Direct frontend work — needs backend confirmation (§17) |
| FVS-032 | VS-026 | `/admin/refunds*` | Admin refund create/list/detail/settle | Admin | Direct frontend work |
| — | VS-027 | (none — provider swap under FVS-026/027/028) | Existing checkout/webhook/payment routes | N/A | Shared frontend work (no new UI) |
| FVS-033 | VS-028 | `/account/offers*` | `POST /offers`, `GET /me/offers*` | Customer | Direct frontend work |
| FVS-034 | VS-029 | `/account/offers/:id` | Customer counter/accept/withdraw | Customer | Direct frontend work |
| FVS-035 | VS-028, VS-029 | `/admin/offers*` | Admin offer list/detail/counter/accept/reject | Admin | Direct frontend work |
| FVS-036 | VS-030 | `/account/offers/:id/checkout` | `POST /me/offers/{id}/checkout` | Customer | Direct frontend work |
| FVS-037 | VS-031 | Embedded (product detail), `/account/reviews` | Public + own review CRUD | Customer (+ public read shared) | Direct frontend work |
| FVS-038 | VS-032 | `/admin/reviews*` | Admin review hide/restore | Admin | Direct frontend work |
| FVS-039 | VS-033 | `/account/wishlist` | `GET/PUT/DELETE /me/wishlist*` | Customer | Direct frontend work |
| FVS-040 | VS-035 | `/admin/custom-requests*` | Admin BYI pipeline + funnel | Admin | Direct frontend work |
| FVS-041 | VS-036, VS-034 (embedded widget), VS-033 (reused) | `/admin/analytics` | Admin analytics endpoints | Admin | Direct frontend work |
| FVS-042 | VS-037 | `/admin/audit-logs*` | `GET /admin/audit-logs*` | Admin | Direct frontend work |
| FVS-043 | VS-038 | Embedded (`/account/profile`) | `GET /me/export` | Customer | Direct frontend work |
| FVS-044 | VS-039 | `/account/settings` (deletion flow) | `DELETE /me` | Customer | Direct frontend work |
| FVS-045 | VS-040 | `/404`, `/500` | None new | N/A (release gate) | Frontend-only |
| FVS-046 | VS-013 (F-013) | `/sitemap.xml`, `/robots.txt` | `GET /products*`, `/categories` | Customer (public) | Frontend-only |

**Coverage check:** every backend slice VS-001–VS-040 appears at least once in this matrix, either as a direct frontend mapping or explicitly marked "No direct UI required" (VS-034) / "Shared frontend work" (VS-027).

## 19. Frontend Definition of Done

A frontend slice is not complete because a page renders locally. It is complete only when all applicable items below are true:

- [ ] User-facing capability works end-to-end against the real (or staging) backend, not just mocked responses.
- [ ] Only the documented backend endpoints from the source-of-truth plan are integrated — no invented endpoint or assumed field.
- [ ] Loading state implemented.
- [ ] Empty state implemented.
- [ ] Error state implemented (mapped per §10, not a single generic catch-all).
- [ ] Unauthorized/forbidden/not-found behavior matches the backend's own hiding rules (404 vs 403 as appropriate — §10).
- [ ] Client-side validation implemented where it improves UX, but server validation remains authoritative.
- [ ] Server validation errors are displayed on the correct field/context, using the server's message.
- [ ] Responsive behavior implemented per §14 at 320px/768px/1024px/1440px.
- [ ] Accessibility checked per §15 (keyboard, labels, focus, semantics, live regions).
- [ ] Authentication/authorization/ownership behavior verified (including IDOR-hiding where applicable).
- [ ] CSRF behavior correct on every mutating request.
- [ ] Upload security UX implemented where applicable (client pre-check + server-truth acceptance, never assumed).
- [ ] Money is never computed as a final/authoritative value on the frontend — only displayed from server-returned integer cents.
- [ ] Optimistic updates (where used) have a tested rollback path; money-moving actions are never optimistic.
- [ ] Unit/component tests added.
- [ ] Integration tests added covering success + the slice's documented error/edge cases.
- [ ] E2E test added or extended for any critical journey this slice completes (§16).
- [ ] SEO implemented where applicable (§13).
- [ ] No analytics/telemetry added beyond what's explicitly approved.
- [ ] No backend assumption exists outside this document's cited endpoints — any gap is flagged in §17, not silently guessed.
- [ ] Documentation updated (contract notes, state diagrams shared with backend where applicable).
- [ ] No placeholder functionality, disabled-forever buttons, or "coming soon" states shipped as if complete.
- [ ] The slice can be merged independently and leaves `main` deployable.

## 20. Merge Strategy

Mirrors the backend plan's own rules (its §7) exactly:

1. Prefer one pull request per FVS slice.
2. Do not scaffold every route/page/component up front — a slice adds only the routes/components it actually needs.
3. Shared abstractions (§7 of this document) are introduced by the **first real slice that needs them**, then reused — never pre-built "for later."
4. Do not create placeholder pages, empty admin sections, or disabled nav links pointing at unbuilt routes — a nav item appears only when its slice ships.
5. Design-system components are born inside the feature that first needs them (FVS-002 for forms, FVS-009 for tables/dialogs, FVS-012 for uploads), never as a standalone "design system" PR.
6. Keep `main` deployable after every merged slice — a slice that half-implements a flow (e.g., checkout without payment verification) is not merged until it reaches its own stated "mergeable outcome."
7. The live-Whish provider swap (VS-027) can merge as soon as backend credentials/adapter are ready, reusing FVS-026/027/028 without waiting on unrelated engagement/analytics slices — same principle the backend plan states for its own VS-027.

Explicitly do **not** create backlog items such as "build the design system," "build all admin pages," "build all forms," "connect all pages to the API," or "add tests for everything later" — these are implementation layers inside a slice, not deliverables by themselves, exactly as the backend plan states in its own §8.

## 21. Recommended Implementation Order

Follow FM-A → FM-B → FM-C → FM-D → FM-E, respecting each slice's stated frontend and backend dependencies (§5). Within a milestone, the numeric FVS order above already reflects a valid dependency-respecting sequence, with these notes:

- **FVS-001 must land before anything else** — every other slice depends on the API client/app shell.
- **FVS-002 through FVS-009 (FM-A) should be finished, in order, before FM-B begins** — later slices assume a working `AuthProvider`, `AdminProtectedRoute`, and account shell.
- **Within FM-B, admin authoring slices (FVS-010–012, FVS-018–019) can run in parallel with public storefront slices (FVS-013–014, FVS-022) once their shared dependencies (FVS-001, FVS-005/007) exist** — they don't block each other, mirroring the backend's own catalogue/upload parallelism.
- **FVS-020/021 (STL library/download) cannot start before FVS-018/019** — no version to download, no entitlement to hold.
- **FM-C's commerce spine is strictly sequential:** FVS-025 (cart) → FVS-026 (checkout) → FVS-027 (payment result) → FVS-029 (order history) → FVS-030 (fulfillment) → FVS-031 (cancellation) → FVS-032 (refunds) — each depends on the previous slice's data existing.
- **FVS-023/024 (addresses/shipping zones) can be built in parallel with FVS-025 (cart)**, both only need to be ready before FVS-026 (checkout).
- **FM-D's offer thread is strictly sequential:** FVS-033 → FVS-034 → FVS-035 (parallel with 034 once 033 lands) → FVS-036 (needs FVS-026/027 from FM-C already merged).
- **FVS-037/038 (reviews) and FVS-039 (wishlist) have no dependency on the offer thread** and can run in parallel with FVS-033–036.
- **FM-E is mostly parallel** once its individual backend/frontend dependencies exist — FVS-041 (analytics) needs the most prior data-producing slices merged first (orders, offers, reviews, wishlist, downloads) so it has real data to report on; FVS-045 (release hardening) is last by definition, since it hardens everything preceding it; FVS-046 (SEO) should land before FVS-045's release-gate check, since FVS-045 verifies the 404/status-code behavior FVS-046 establishes.

This plan is now ready for review. No implementation should begin until each FVS is approved and — per §17 — the `NEEDS BACKEND CONFIRMATION` items are resolved with the backend team, since several (payment return contract, order-status enum, idempotency header) block the highest-risk slices (FVS-026, FVS-027, FVS-030, FVS-032) from being scoped accurately.
