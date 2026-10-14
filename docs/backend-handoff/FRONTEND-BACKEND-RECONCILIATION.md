# Frontend–Backend Reconciliation (FVS-001 → FVS-032)

**Scope:** every slice in `docs/frontend-requests/BACKEND-UNLOCK-HANDOFF.md`'s audit (FVS-001–FVS-032, milestones FM-A/B/C), reconciled against the backend's real, built-from-code answer in `docs/backend-handoff/BACKEND-RESPONSE.md` and `docs/backend-handoff/openapi.json`.

**Method:** `openapi.json` is authoritative for what is *built*. `BACKEND-RESPONSE.md`'s own Built / Removed / Not-built labels are taken as given, never re-derived. Nothing here changes `src/`; this is a planning document only.

**Current mounted reality** (confirmed against `src/app/`): only `/`, `/login`, `/register`, `/verify-email`, `/verify-email/resend`, `/account`, `/account/profile` are mounted routes. Every other page — `/shop`, product detail, `/cart`, `/checkout`, `/account/orders`, `/account/addresses`, `/account/library`, `/account/downloads`, `/about`, `/contact`, `/bring-your-idea`, and the entire `/admin/*` tree — exists only as built, unit-tested, unmounted components under `src/components/**` and `src/lib/**` (confirmed by directory listing and by `docs/frontend-requests/BACKEND-UNLOCK-HANDOFF.md` line 10).

---

## 1. Executive summary

The backend is built through the **public catalogue and the built-admin-operations surface** (VS-001–VS-016 per `BACKEND-RESPONSE.md` line 6): health, auth (register/verify/login/logout/refresh/password-reset), admin MFA, public settings, the public catalogue (list/detail/search), and the admin CRUD screens (settings, users, categories/materials/colours, products, product images). Nothing from cart onward exists: no cart, checkout, payment, order, refund, address, contact or Bring-Your-Idea route is built (`BACKEND-RESPONSE.md` line 6).

Two ADRs permanently deleted parts of the frontend's planned surface:
- **ADR-019** — the platform never stores or serves STL files. There is no entitlement/library model, no download endpoint, no admin asset-version upload, no admin entitlement grant. STL files are emailed by hand after a verified payment.
- **ADR-024** — the platform charges no shipping. There are no shipping zones, no shipping rate, no free-shipping threshold (the field survives in `PublicSettingsRead` only until VS-028 deletes it, and is always `null` — do not build UI on it). Cash-on-delivery for physical-only orders is new.

Of the 32 slices in scope: **9 are ready to integrate now (A)**, **4 are partially ready (B)**, **12 are blocked on backend work not yet started (C)**, **5 are superseded and should be retired (D)**, **2 require a product-owner decision before they can even be correctly designed (E)**. (One slice, FVS-014, is split between A/B territory and is counted once, under B, since part of it is genuinely blocked.)

The single biggest unlock since the frontend's last audit: **the admin authorization question (P1-1) that blocked every admin route is now answered** — `role` on `GET /api/v1/me` is the only source of truth, and for an MFA-enrolled administrator, *having a session at all* means MFA is complete (`401 MFA_REQUIRED` is the one exception to handle globally). This was previously the single largest structural blocker (`BACKEND-UNLOCK-HANDOFF.md` P1-1, line 12) and is now fully resolved, unblocking FVS-005, 007, 009, 010, 011, 012 for real integration.

The single biggest frontend liability to clean up: **STL-ownership/download/entitlement UI (FVS-018–FVS-021) and shipping-zone UI (FVS-024)** were built or scaffolded against concepts the backend has permanently removed. These should be retired, not merely left unmounted.

---

## 2. FVS-001 → FVS-032 status matrix

Legend: **A** ready now · **B** partially ready · **C** backend not built · **D** superseded/retire · **E** needs product decision.

| Slice | Title | Class | Backend status | Authoritative source |
|---|---|---|---|---|
| FVS-001 | App shell, routing, API client | **A** | VS-001 built | `BACKEND-RESPONSE.md` A2; `openapi.json` |
| FVS-002 | Registration & email verification | **A** | VS-002 built, no captcha | `BACKEND-RESPONSE.md` §2 A3, P2-7 |
| FVS-003 | Login, logout, session | **A** | VS-003 built | `BACKEND-RESPONSE.md` §1.2, P1-1 |
| FVS-004 | Password reset | **A** | P2-6 built | `BACKEND-RESPONSE.md` P2-6 |
| FVS-005 | Admin login & MFA | **A** | P1-1, P1-2 built | `BACKEND-RESPONSE.md` P1-1, P1-2 |
| FVS-006 | Customer account shell & profile | **A** | VS-006 built | `BACKEND-RESPONSE.md` P1-1 (`/me`) |
| FVS-007 | Admin business settings editor | **A** | P1-3 built; B1 built | `BACKEND-RESPONSE.md` P1-3, B1 |
| FVS-008 | Notification center | **A** | P2-5 built (channel only) | `BACKEND-RESPONSE.md` P2-5 |
| FVS-009 | Admin customer management | **A** | P1-4 built | `BACKEND-RESPONSE.md` P1-4 |
| FVS-010 | Admin reference data | **A** | P1-5 built | `BACKEND-RESPONSE.md` P1-5 |
| FVS-011 | Admin product management | **A** | P1-6 built | `BACKEND-RESPONSE.md` P1-6 |
| FVS-012 | Admin product image management | **A** (UX model wrong) | P1-7 built, synchronous | `BACKEND-RESPONSE.md` P1-7 |
| FVS-013 | Public catalogue & discovery | **A** (facet keys wrong) | B2 built | `BACKEND-RESPONSE.md` B2 |
| FVS-014 | Public product detail | **B** | B3 built; cart/owned-STL parts unbuilt/removed | `BACKEND-RESPONSE.md` B3, C9, C11 |
| FVS-015 | Bring Your Idea submission | **C** | P2-2 not built; P2-1 captcha not built | `BACKEND-RESPONSE.md` P2-2, P2-1 |
| FVS-016 | Public contact form | **C** | P2-3 not built | `BACKEND-RESPONSE.md` P2-3 |
| FVS-017 | Admin contact message queue | **C** | P2-4 not built | `BACKEND-RESPONSE.md` P2-4 |
| FVS-018 | Admin STL asset-version upload | **D** | Removed, ADR-019 | `BACKEND-RESPONSE.md` §3, P1-8 |
| FVS-019 | Admin entitlement grant | **D** | Removed, ADR-019 | `BACKEND-RESPONSE.md` §3, P1-9 |
| FVS-020 | Customer STL library | **D** | Removed, ADR-019 | `BACKEND-RESPONSE.md` §3, C9 |
| FVS-021 | Customer STL download experience | **D** | Removed, ADR-019 | `BACKEND-RESPONSE.md` §3, C10 |
| FVS-022 | Home, About, floating WhatsApp | **A** | B1, B2 built (composition only) | `BACKEND-RESPONSE.md` B1, B2 |
| FVS-023 | Customer address book | **C** | C3 not built | `BACKEND-RESPONSE.md` C3 |
| FVS-024 | Admin shipping-zone management | **D** | Removed, ADR-024 | `BACKEND-RESPONSE.md` §3, C4 |
| FVS-025 | Shopping cart | **C** | C5 not built | `BACKEND-RESPONSE.md` C5 |
| FVS-026 | Checkout flow | **C** | C6 not built; zone step must be deleted | `BACKEND-RESPONSE.md` C6, §3 |
| FVS-027 | Payment result & verification UX | **E** | C7 not built; provider/return-URL undecided | `BACKEND-RESPONSE.md` C7; §7 Q3, Q4 |
| FVS-028 | Admin payment management | **C** | P1-10 not built | `BACKEND-RESPONSE.md` P1-10 |
| FVS-029 | Customer order history & detail | **C** | C8 not built | `BACKEND-RESPONSE.md` C8 |
| FVS-030 | Admin order fulfillment console | **E** | P1-11 not built; no "legal actions" affordance decided | `BACKEND-RESPONSE.md` P1-11; §7 Q1 |
| FVS-031 | Order cancellation & returns UX | **C** | P1-12 not built | `BACKEND-RESPONSE.md` P1-12 |
| FVS-032 | Admin refund management | **C** | P1-13 not built; shipping/entitlement rows must be deleted now | `BACKEND-RESPONSE.md` P1-13, §3, §6 |

**Counts: A = 9, B = 1, C = 12, D = 5, E = 2.** (Totals to 29 distinct classes across 32 slices; FVS-014 is the one slice that is genuinely split, recorded once as B.)

---

## 3. Per-slice detail

### A — Ready to integrate now

#### FVS-001 — App shell, routing, API client
- **Current frontend state:** mounted at `/`; `apiClient`, RFC 9457 `Problem` parsing, `ErrorBoundary`, `NotFoundPage` built (`BACKEND-UNLOCK-HANDOFF.md` line 11).
- **Backend status:** `GET /health/live`, `GET /health/ready` built (`BACKEND-RESPONSE.md` A2).
- **Assumptions that were wrong:** none load-bearing; the plan's placeholder validation-error shape (§17/C1) is now confirmed as Pydantic `loc`/`msg`/`type`, not `field`/`message` — the `ApiError` parser should be checked against the real shape in `BACKEND-RESPONSE.md` §1.1/C1.
- **Frontend work remaining valid:** all of it.
- **Frontend work to change:** verify `ApiError`'s validation-error branch matches `loc`/`msg`/`type` exactly (not a guessed `field`/`message` pair).
- **Route to mount:** already mounted.
- **Can implement now:** yes — point at a real backend and verify.

#### FVS-002 — Registration & email verification
- **Current frontend state:** mounted (`/register`, `/verify-email`, `/verify-email/resend`); built end-to-end against the frontend's own contract (`BACKEND-UNLOCK-HANDOFF.md` line 11).
- **Backend status:** `POST /auth/register`, `/auth/verify-email`, `/auth/resend-verification` built, **no captcha field accepted** — sending one is a `422 extra_forbidden` (`BACKEND-RESPONSE.md` P2-7).
- **Assumptions that were wrong:** the original unlock request assumed Turnstile was "already confirmed" for register/resend — it is not, and is not planned. The frontend plan already correctly assumed no captcha at this slice (FVS-002 batch 2 note in the FVS plan), so no correction is needed here, only confirmation.
- **Frontend work remaining valid:** all of it.
- **Frontend work to change:** none.
- **Route to mount:** already mounted.
- **Can implement now:** yes, point at a real backend.

#### FVS-003 — Login, logout, session
- **Current frontend state:** mounted (`/login`); `AuthProvider`, `ProtectedRoute`, CSRF header wiring built (`BACKEND-UNLOCK-HANDOFF.md` line 11).
- **Backend status:** cookie/CSRF contract fully specified and built (`BACKEND-RESPONSE.md` §1.2, P1-1).
- **Assumptions that were wrong:** none — the frontend's existing design (derive auth from `GET /me`, CSRF token in a JS-readable cookie) matches the backend exactly.
- **Frontend work remaining valid:** all of it.
- **Frontend work to change:** none.
- **Route to mount:** already mounted.
- **Can implement now:** yes.

#### FVS-004 — Password reset
- **Current frontend state:** components built (reuses `Form`/`TextField`/`PasswordField`/`Alert` per the FVS plan), **not mounted** (`/forgot-password`, `/reset-password` absent from `src/app`).
- **Backend status:** built (`BACKEND-RESPONSE.md` P2-6); `README.md` line 76 confirms "Built". `BACKEND-RESPONSE.md` §5 table: "Unlocked now."
- **Assumptions that were wrong:** none of substance — field rules (8–256 Unicode code points, no composition rules) match what the plan assumed from registration.
- **Frontend work remaining valid:** all of it.
- **Frontend work to change:** none; this is purely a mounting task.
- **Route to mount:** `/forgot-password`, `/reset-password` (token in the URL fragment, not a query param).
- **Can implement now:** yes.

#### FVS-005 — Admin login & MFA
- **Current frontend state:** components built (`MfaChallengeForm`, `MfaSetupWizard`, `RecoveryCodeList` per the plan), **not mounted** (`/admin/*` entirely absent from `src/app`).
- **Backend status:** P1-1 and P1-2 both built (`BACKEND-RESPONSE.md` P1-1, P1-2).
- **Assumptions that were wrong — this is the big one:** the plan's `AuthProvider` design (FVS-005 line 168 of the FVS plan) assumed a per-session `mfaVerified` boolean the frontend would track itself. **There is no such field and none is planned.** The correct rule: `role === "admin"` from `/me` is the only authorization source; for an enrolled administrator, the mere existence of a session means MFA is complete, because `/auth/login` never issues a session to an MFA-enrolled admin — it issues a `202` challenge instead. The one exception is an administrator who has not finished *enrolling*, who gets an ordinary session and then a global `401 MFA_REQUIRED` on every `/admin/*` call (`BACKEND-RESPONSE.md` P1-1 notes, and the Special Attention item "established admin session implies completed MFA except MFA_REQUIRED handling").
- **Frontend work remaining valid:** `MfaChallengeForm`, `MfaSetupWizard`, `RecoveryCodeList`, the challenge-id-in-memory-only design.
- **Frontend work to change:** `AdminProtectedRoute`/`AuthProvider` must drop the invented `mfaVerified` session flag and instead (1) check `role === "admin"` from `/me`, (2) treat a global `401 MFA_REQUIRED` from any `/admin/*` call as "go enroll," not a generic auth failure.
- **Route to mount:** `/admin/login`, `/admin/mfa/setup`, `/admin/mfa/verify`, `/admin/mfa/recovery-codes`, and the `/admin/*` layout guard.
- **Can implement now:** yes — and doing so unblocks every other admin slice below.

#### FVS-006 — Customer account shell & profile
- **Current frontend state:** mounted (`/account`, `/account/profile`).
- **Backend status:** `GET /me` built (`BACKEND-RESPONSE.md` P1-1).
- **Assumptions that were wrong:** none; VS-006 is confirmed read-only, matching the plan's explicit "no edit form" decision.
- **Frontend work remaining valid:** all of it.
- **Can implement now:** yes, already done.

#### FVS-007 — Admin business settings editor
- **Current frontend state:** `SettingControl`, `SettingRow`, `settingTypes.ts` built under `src/components/admin/settings/`; **not mounted**.
- **Backend status:** P1-3 built: `GET /admin/settings` (list, cursor-paginated), `GET/PATCH /admin/settings/{key}`; public read `GET /settings/public` (B1) built too.
- **Assumptions that were wrong:** the plan flagged the settings-list path as prose-only/`NEEDS BACKEND CONFIRMATION` — it is now a literal, cursor-paginated `GET /admin/settings` returning each setting's own `type`/`unit`/`minimum`/`maximum`/`nullable` metadata, exactly matching the plan's "generic typed-field renderer" design. `free_shipping_threshold` and `daily_download_cap` are both obsolete keys scheduled for deletion (ADR-024, ADR-019) — do not build special UI for them (`BACKEND-RESPONSE.md` P1-3 notes).
- **Frontend work remaining valid:** `SettingRow`/`SettingControl`'s type-driven rendering design.
- **Frontend work to change:** exclude or gray out `free_shipping_threshold` and `daily_download_cap` rows rather than rendering them as live controls.
- **Route to mount:** `/admin/settings`.
- **Can implement now:** yes.

#### FVS-008 — Notification center
- **Current frontend state:** components under `src/components/notifications/` (per `PROJECT-STRUCTURE.md`'s grouping); **not mounted**.
- **Backend status:** P2-5 built as a channel; `GET /me/notifications`, `PATCH /me/notifications/{id}` work; **no business event writes to it yet** — the registry of `payload.event` values is empty except a planned `stl.delivered` (`BACKEND-RESPONSE.md` P2-5).
- **Assumptions that were wrong:** the plan's generic `NotificationItem` (renders unknown `type` safely) was exactly the right call given the empty event registry — no correction needed. Pagination is confirmed `{items, next_cursor}` (C2), not a `has_more`/page-number model.
- **Frontend work remaining valid:** `NotificationBell`, `NotificationList`, generic-fallback renderer.
- **Route to mount:** `/account/notifications`.
- **Can implement now:** yes, though the inbox will be empty until a later slice emits a real event.

#### FVS-009 — Admin customer management
- **Current frontend state:** `AdminTable` built; **not mounted**.
- **Backend status:** P1-4 built: `GET /admin/users`, `GET /admin/users/{id}`, `PATCH /admin/users/{id}` (`{is_active}` only).
- **Assumptions that were wrong:** none of substance; "only approved fields editable" matches exactly.
- **Frontend work remaining valid:** `AdminTable`, `StatusBadge`, `ConfirmDialog`.
- **Route to mount:** `/admin/customers`, `/admin/customers/:id`.
- **Can implement now:** yes.

#### FVS-010 — Admin reference data
- **Current frontend state:** `ReferenceDataManager` built; **not mounted**.
- **Backend status:** P1-5 built for categories/materials/colours; archive = `DELETE` (permanent, no restore); temporary hide = `PATCH {is_active: false}` (reversible).
- **Assumptions that were wrong:** the plan treated "archive" as a single soft action; the backend distinguishes a **permanent** archive (`DELETE`, frees the slug, cannot be undone) from a **reversible** disable (`PATCH is_active`). `ReferenceDataManager` must expose both as distinct actions, not one.
- **Frontend work remaining valid:** the generic three-entity CRUD design.
- **Frontend work to change:** split "archive" (irreversible) from "disable" (reversible) as two separate actions/confirmations.
- **Route to mount:** `/admin/categories`, `/admin/materials`, `/admin/colours`.
- **Can implement now:** yes.

#### FVS-011 — Admin product management
- **Current frontend state:** `ProductForm`/`MoneyInput`/`ProductTypeSelector` built; **not mounted**.
- **Backend status:** P1-6 built with **optimistic locking** on `version` (every `PATCH`/`DELETE` must send it; `409 VERSION_CONFLICT` on mismatch).
- **Assumptions that were wrong:** the plan did not previously confirm the field matrix; it is now exact (`BACKEND-RESPONSE.md` P1-6 notes): physical-only required fields are `purchase_mode`, `production_lead_time_days`, `batch_size`, `max_quantity_per_line`; STL rejects all eight physical-only fields with `422`.
- **Frontend work remaining valid:** `ProductForm` type-branching design, `MoneyInput`.
- **Frontend work to change:** add version-conflict handling (re-read, show newer state, let the admin retry) — this was not previously confirmed as optimistic-locking and needs explicit UI for it.
- **Route to mount:** `/admin/products`, `/admin/products/new`, `/admin/products/:id/edit`.
- **Can implement now:** yes.

#### FVS-012 — Admin product image management
- **Current frontend state:** `FileUploader`, `ImageGallery` built; **not mounted**.
- **Backend status:** P1-7 built — **upload is synchronous**: the `201` response only arrives after the file is scanned, re-encoded and stored; "there is no pending state and nothing to poll" (`BACKEND-RESPONSE.md` P1-7).
- **Assumptions that were wrong — significant:** the FVS plan's own asset-upload pattern assumed a pending/scanning/clean workflow with polling (explicitly built for FVS-018's STL assets, and `FileUploader` was designed to be reused that way). For **images**, that model is wrong: there is no scan-status to poll. A request either returns `201` (live, usable) or an error (`422 UPLOAD_REJECTED`/`MALWARE_DETECTED`, `503` if the scanner is down) — nothing is ever "pending."
- **Frontend work remaining valid:** the "one file per request, sequential uploads" model, client-side type/size pre-checks.
- **Frontend work to change:** remove any scan-status-polling affordance from the image-upload path specifically (it only applies to the now-removed STL asset-version flow, FVS-018); image upload is synchronous accept/reject.
- **Route to mount:** embedded in `/admin/products/:id/edit`.
- **Can implement now:** yes.

#### FVS-013 — Public catalogue & discovery
- **Current frontend state:** `shopUrlState`, `FilterPanel`, `SortSelect`, `SearchBar` built (`BACKEND-UNLOCK-HANDOFF.md` B2); **not mounted** (`/shop` absent).
- **Backend status:** B2 built fully, including `B5` search suggestions.
- **Assumptions that were wrong:** (1) the plan's URL keys `category`/`material`/`colour` are **not** the wire names — the API takes `category_id`/`material_id`/`colour_id`, UUIDs, obtained from `GET /categories`/`/materials`/`/colours`; the frontend's URL-to-filter mapping must resolve slugs/names to ids before calling the API. (2) **One value per facet only** — there is no multi-value filter; a comma-joined id list is a `422`. (3) The plan's `SortSelect` mentioned a "most downloaded" sort "only where the backend allows it" — it doesn't: the only sort values are `-created_at` (default), `price`, `-price`, `-average_rating`, and `-relevance` (only with `q`). Remove any download-count sort option.
- **Frontend work remaining valid:** `shopUrlState` as the source of truth, cursor-based `LoadMore` (there is no page-number pagination — no `has_more`/total-count field exists, C2).
- **Frontend work to change:** map URL slugs to backend UUIDs via the reference-list endpoints before querying; drop the "most downloaded" sort option; enforce single-value facets in `FilterPanel`.
- **Route to mount:** `/shop`.
- **Can implement now:** yes.

#### FVS-022 — Home, About, floating WhatsApp
- **Current frontend state:** `FloatingWhatsAppButton`, `HeroSection` built; `/` is currently only FVS-001's placeholder shell; `/about` absent.
- **Backend status:** composes already-built `GET /settings/public` (B1) and `GET /products` (B2); no dedicated backend slice (frontend-only per the FVS plan).
- **Assumptions that were wrong:** none beyond B1's correction below (same field, shared with FVS-007/014/026): `free_shipping_threshold` is always `null` and obsolete — never surface it, even as a banner. There is no "message" field for WhatsApp; the frontend builds the `wa.me` link and any prefilled text itself.
- **Frontend work remaining valid:** `FloatingWhatsAppButton`'s "render nothing if settings fetch fails" rule (correctly anticipates there being no hardcoded fallback number).
- **Route to mount:** `/` (replace the placeholder shell with real Home content), `/about`.
- **Can implement now:** yes.

### B — Partially ready

#### FVS-014 — Public product detail
- **Current frontend state:** `PriceDisplay`, `ProductTypeBadge`, `UnavailableNotice`, `ProductImageGallery`, WhatsApp CTA helpers built (`BACKEND-UNLOCK-HANDOFF.md` B3); `AddToCartButton` built but intentionally non-wired; **not mounted** (`/shop/:slug` absent).
- **Backend status:** B3 fully built, including a real, machine-readable `capabilities` object (`can_add_to_cart`, `can_offer`, `whatsapp_available`) that replaces the guesswork the frontend plan anticipated needing. C9 (STL library/ownership) is removed; C11 (per-product ownership for a signed-in viewer) is explicitly **not built and not planned** — "there is no 'is this product owned by me' field, and none is planned" (`BACKEND-RESPONSE.md` C11).
- **Assumptions that were wrong:** (1) the plan's "STL already-owned-by-viewer → points to library" state (FVS-014 UX states) depends on the now-removed library (FVS-020) and the never-planned ownership signal (C11) — this state cannot be built as designed. (2) `max_quantity_per_line` is real for physical products (cart quantity cap) but STL is always quantity 1 — already correctly assumed.
- **Frontend work that remains valid:** gallery, price, type badge, WhatsApp CTA, the `capabilities`-driven action gating (this maps cleanly onto the real response).
- **Frontend work that should be changed/retired:** delete the "already-owned STL → go to your library" UX state entirely; an STL product page has no behavior change for an owner versus a non-owner today (the 409 at cart/checkout time is the only signal, once cart exists — C11 note).
- **Route that can now be mounted:** `/shop/:slug` can be built and shown today for every field except purchase actions.
- **Whether implementation can happen now:** yes for display; `AddToCartButton` stays disabled until FVS-025 (cart) lands, exactly as the original plan anticipated for dependency-ordering reasons — that part was already correctly deferred, not wrong.

### C — Backend not built

For every slice below, the correct action is: **keep the already-built presentational components and client-side models** (they cost nothing and the plan explicitly built "everything that doesn't require a guessed contract"), but **do not wire any network call**, and do not invent response shapes beyond what `BACKEND-RESPONSE.md` §4 states as provisional.

#### FVS-015 — Bring Your Idea submission
- **Backend status:** P2-2 not built (slice VS-034); captcha itself (P2-1) not built, vendor undecided — only an unused `TURNSTILE_SECRET` env var hints at Cloudflare Turnstile, which `BACKEND-RESPONSE.md` explicitly calls "a hint, not a decision."
- **Frontend work that remains valid:** `BringYourIdeaForm`, reused `FileUploader` (configured for this endpoint's limits once they exist).
- **Frontend work to retire/change now:** none to retire; do not hardcode a captcha vendor integration — `CaptchaWidget` should stay provider-agnostic until P2-1 resolves.
- **Can implement now:** no network wiring; form/validation UI can be finished.

#### FVS-016 — Public contact form
- **Backend status:** P2-3 not built (slice VS-033), same captcha dependency as FVS-015.
- **Can implement now:** no.

#### FVS-017 — Admin contact message queue
- **Backend status:** P2-4 not built (slice VS-033); field names for list/detail not written yet.
- **Can implement now:** no.

#### FVS-023 — Customer address book
- **Backend status:** C3 not built (slice VS-026). Planned fields are Lebanon-only (`governorate`, `city` required; no postal code, no country) — matches the plan's existing no-auto-zone-detection design.
- **Frontend work that remains valid:** `AddressList`, `AddressForm`, `SetDefaultToggle`/`DefaultAddressSelector`.
- **Open item:** whether a default address can be deleted, and what becomes default afterward, is unspecified (`BACKEND-RESPONSE.md` §7 Q10) — backend's call, not yet made.
- **Can implement now:** no network wiring.

#### FVS-025 — Shopping cart
- **Backend status:** C5 not built (slice VS-022).
- **Assumptions that were wrong (for whenever it lands):** cart lines are addressed by **`product_id`**, not an `{item_id}` as the plan's placeholder endpoints assumed (`BACKEND-RESPONSE.md` §6 correction table). The already-owned-STL precheck the plan wanted to run client-side against `EntitlementModel.productId` has no backing data anymore — entitlements don't exist; the only signal will be the server's `409 PRODUCT_ALREADY_OWNED` once checkout exists.
- **Frontend work that remains valid:** `CartPage`, `CartLineItem`, `MiniCartDrawer`, `LoggedOutCartPrompt`.
- **Frontend work to change when built:** route item mutations by `product_id`; drop any client-side "already owned" precheck that depends on the entitlement model.
- **Can implement now:** no network wiring.

#### FVS-026 — Checkout flow
- **Backend status:** C6 not built (slices VS-023, VS-028).
- **Assumptions that were wrong:** the entire zone/shipping-cost portion of checkout is gone (ADR-024) — there is no zone id, no shipping line, and `OrderSummary`/`DeliveryMethodSelector` must never reference a shipping-zone selector. `Idempotency-Key` is confirmed as the header name, client-generated once per checkout intent (C12) — this part of the plan's `useCheckoutAttempt` design is already correct.
- **Frontend work that remains valid:** `CheckoutStepper`, `ConsentCheckboxGroup`, `PriceChangeConflictBanner`, `CheckoutDisabledBanner` (kill-switch), `useCheckoutAttempt`.
- **Frontend work to change/retire now:** remove any shipping-zone picker wiring from `DeliveryMethodSelector`; consent copy (terms, digital-final-sale, cash-terms text) does not exist anywhere and must not be invented (open question #8) — ship with placeholder copy clearly marked pending legal sign-off, not production text.
- **Can implement now:** no network wiring.

#### FVS-028 — Admin payment management
- **Backend status:** P1-10 not built (slice VS-024); two rules "must resolve before build" on the backend side (how a wrong manual-confirm amount is handled; which payment states are eligible for manual confirm) — these are backend design questions, not yet a product-owner item.
- **Frontend work that remains valid:** `AdminPaymentList`, `PaymentDetail`, `ManualConfirmDialog`.
- **Can implement now:** no network wiring.

#### FVS-029 — Customer order history & detail
- **Backend status:** C8 not built (slice VS-025). The customer-visible status enum and the `can_cancel`/`payment_due` booleans are specified provisionally; customers never see `in_production` (shown as `pending`).
- **Frontend work that remains valid:** `OrderList`, `OrderDetail`, `OrderLineItem`, `StatusTimeline`.
- **Can implement now:** no network wiring.

#### FVS-031 — Order cancellation & returns UX
- **Backend status:** P1-12 not built (slice VS-031). Cutoff rule is specified: customer cancel is **all-or-nothing** across every physical line, only while every physical line is still `pending`; STL lines are never cancellable.
- **Frontend work that remains valid:** `CancelOrderLineButton`, `CancellableOrderLine`, `AdminCancelDialog`, `OrderConcurrencyConflictNotice`.
- **Can implement now:** no network wiring.

#### FVS-032 — Admin refund management
- **Backend status:** P1-13 not built (slice VS-030); several rules "must resolve before build" (where the refundable-balance-per-line field lives — open question #6, backend's to answer).
- **Assumptions that must be corrected regardless of backend build status (already-built components contain these):** `RefundCreateForm` must **drop its shipping-refund row entirely** — nothing was ever charged for shipping (ADR-024), so there is nothing to refund. `RefundCreateForm`'s "revocation confirmation gate" for digital lines must become a **plain warning**, not a confirmation gate tied to an entitlement — there is no entitlement to revoke; an STL line simply becomes `refunded` once refunds cover its whole price, and a file already emailed cannot be un-sent (`BACKEND-RESPONSE.md` §3 table and §6 correction table).
- **Frontend work that remains valid:** `RefundQueue`, `RefundDetail`, `SettleRefundDialog`, per-line `MoneyInput`-bounded amount fields.
- **Can implement now:** no network wiring, but the shipping-row and entitlement-gate corrections to `RefundCreateForm` **can and should happen now**, independent of backend readiness, since they are corrections to already-committed frontend code, not new integration work.

### D — Superseded / retire

All four of these are permanent removals (ADR-019 or ADR-024), confirmed in `BACKEND-RESPONSE.md` §3's removal table. None will ever be built. The components listed have "no backend counterpart" verbatim per the backend's own notes.

#### FVS-018 — Admin STL asset-version upload & version management
- **Removed by:** ADR-019 (`BACKEND-RESPONSE.md` P1-8).
- **Components with no backend counterpart:** `AssetVersionWorkflow`, `AssetVersionList`, `AssetVersionUploader`, `useScanStatusPolling` (all under `src/components/admin/`).
- **What replaces it:** nothing for the admin's own storage — the admin keeps STL files on their own drive. The **STL delivery queue** (P1-11, provisional) replaces it operationally: a list of paid STL lines still to be emailed, each with a "mark as sent" action.
- **Route to retire:** `/admin/products/:id/assets`.

#### FVS-019 — Admin entitlement grant
- **Removed by:** ADR-019 (`BACKEND-RESPONSE.md` P1-9).
- **Components with no backend counterpart:** `GrantEntitlementDialog`, `entitlementGrantModels`.
- **Components that stay useful (generic, not removed):** `DialogShell`, `SearchableCombobox`.
- **What replaces it:** nothing — to give an STL away, the administrator emails it; the platform records nothing.

#### FVS-020 — Customer STL library
- **Removed by:** ADR-019 (`BACKEND-RESPONSE.md` §3, C9).
- **Components with no backend counterpart:** `EntitlementModel`, `EntitlementList`, `EntitlementCard`.
- **Route to retire:** `/account/library`.
- **What replaces it:** a future, filtered view of `GET /me/orders` (not built; C8/P1-11, provisional) — "My STL purchases" with no download button, once orders exist.

#### FVS-021 — Customer STL download experience
- **Removed by:** ADR-019 (`BACKEND-RESPONSE.md` §3, C10).
- **Components with no backend counterpart:** `DownloadButton`, `downloadHistoryModel`, `DownloadHistoryTable`, `DownloadNotice`.
- **Route to retire:** `/account/downloads`.
- **What replaces it:** the order page will show "We will email your file" while a line is `awaiting_delivery`, and "Sent on <date>" once `delivered` (provisional, C10/VS-023b) — no download UI of any kind.

#### FVS-024 — Admin shipping-zone management
- **Removed by:** ADR-024 (`BACKEND-RESPONSE.md` §3, C4).
- **Components with no backend counterpart:** `ShippingZoneManager`.
- **Route to retire:** `/admin/shipping-zones`.
- **What replaces it:** nothing — the courier sets and collects the delivery fee; the platform never computes or stores one.

### E — Requires a product decision

#### FVS-027 — Payment result & verification UX
- **Backend status:** C7 not built; explicitly "several parts undecided, not merely unbuilt" (`BACKEND-RESPONSE.md` C7).
- **Unresolved product/business decisions blocking correct design (not just missing code):** which online payment provider — Whish, a card gateway, or both (`BACKEND-RESPONSE.md` §7 Q4, decider: product owner, before VS-032); the payment return URL shape, its query parameters, and the polling interval/backoff/max-duration/timeout, all of which "depend on the online provider, which is not chosen" (§7 Q3).
- **Frontend work that remains valid:** `PaymentVerificationState` (4-variant model), `usePaymentStatusPoller` (parameterized, no hardcoded interval), all five result-state components, and — most importantly — the test proving a manipulated success-looking query string still renders the pending state when the backend says pending. None of this needs to change regardless of which provider is chosen.
- **Can implement now:** no — the UI shell can stay as built, but the return-URL contract and the terminal-state enum cannot be finalized until the provider decision lands.

#### FVS-030 — Admin order fulfillment console
- **Backend status:** P1-11 not built; the admin "available actions" affordance is **explicitly unspecified**, not merely unbuilt: "no list of legal next transitions per line is planned... it needs a decision before VS-029" (`BACKEND-RESPONSE.md` P1-11 notes; §7 Q1, decider: product owner, before VS-029).
- **Impact:** without a server-provided affordance list, the frontend's only alternative is to hand-maintain a client-side transition table mirrored from the backend's state diagram — exactly the anti-pattern the original FVS plan said it would avoid (FVS-030's own text: "the frontend does not attempt to enumerate the full state machine independently... if the backend doesn't return an explicit affordance list, the frontend maintains a client-side transition table... flagged in §17"). This decision should be pushed before any `TransitionActions`/`LineTransitionButton` wiring work starts.
- **Frontend work that remains valid:** `AdminOrderDetail`, `AdminOrderLine`, `InternalNoteEditor`, `StatusBadge`.
- **Can implement now:** no.

---

## 4. BUILT backend capabilities ready for frontend integration

Everything in class A above, concretely:

- Health/readiness (`GET /health/live`, `/health/ready`)
- Auth: register, verify-email, resend-verification, login, logout, refresh, password-reset request/confirm
- Admin MFA: setup, setup/confirm, verify, recovery-codes/regenerate — **and the authorization model is now fully resolved** (role from `/me`, no `mfaVerified` field, `MFA_REQUIRED` handled globally)
- `GET /me` (customer and admin)
- Public settings (`GET /settings/public`)
- Public catalogue: list (`GET /products`), detail (`GET /products/{slug}`), search suggestions (`GET /search/suggestions`), public reference lists (`GET /categories`, `/materials`, `/colours`)
- Notifications (`GET /me/notifications`, `PATCH /me/notifications/{id}`) — channel only, no events populate it yet
- Admin: settings (list/get/patch), users (list/get/patch is_active), categories/materials/colours (full CRUD), products (full CRUD with optimistic locking), product images (upload/update/reorder/cover/delete, synchronous scanning)

## 5. REMOVED concepts requiring frontend retirement

- Shipping zones, shipping cost, free-shipping threshold (ADR-024) — FVS-024 entirely; the zone step inside FVS-026; the `free_shipping_threshold` display anywhere it might appear (FVS-007, FVS-022, FVS-026)
- STL entitlements, customer library, STL download, admin STL asset-version upload, admin entitlement grant (ADR-019) — FVS-018, FVS-019, FVS-020, FVS-021 entirely
- The "digital refund revokes entitlement" confirmation gate and the "shipping" refund row inside the already-built `RefundCreateForm` (FVS-032) — correct now, independent of backend readiness

## 6. PROVISIONAL / not-built backend areas

Address book (C3), cart (C5), checkout (C6), payment verification (C7), order/order-line status + available actions (C8), per-product ownership signal (C11, not even planned), idempotency-key mechanism (C12, header name confirmed but TTL/format open), admin payments (P1-10), admin order fulfillment (P1-11), cancellation/returns (P1-12), refunds (P1-13), captcha (P2-1), Bring Your Idea (P2-2), contact form (P2-3), admin contact queue (P2-4). None of these should be wired to a network call; all may have presentational/model work continue.

## 7. Wrong frontend assumptions now corrected

| Area | Was assumed | Actually |
|---|---|---|
| Admin auth (FVS-005) | A session-level `mfaVerified` boolean the frontend tracks | No such field; session existence = MFA complete for an enrolled admin; `401 MFA_REQUIRED` is the one exception |
| Catalogue filters (FVS-013) | URL keys `category`/`material`/`colour` are wire names | Wire params are `category_id`/`material_id`/`colour_id`, UUIDs resolved via reference lists |
| Catalogue filters (FVS-013) | Multi-value facets possible | One value per facet; repeated/comma-joined params are rejected or silently truncated |
| Sort options (FVS-013) | A "most downloaded" sort might exist | Not in the enum: `-created_at`, `price`, `-price`, `-average_rating`, `-relevance` only |
| Image upload (FVS-012) | Async scan with a pollable pending state (same model as the now-removed FVS-018) | Synchronous: `201` means already scanned, re-encoded, and live; no polling |
| Reference-data archive (FVS-010) | One "archive" action | Two distinct actions: permanent `DELETE` (archive) vs. reversible `PATCH is_active` (disable) |
| Product edits (FVS-011) | Not previously confirmed as concurrency-safe | Optimistic locking via `version`; every write must send it and handle `409 VERSION_CONFLICT` |
| Cart item addressing (FVS-025) | `{item_id}` path segment | `{product_id}` — a cart holds at most one line per product |
| Registration/resend captcha (FVS-002) | Request doc called Turnstile "confirmed" | No captcha exists on these routes; sending a token field is a `422` |
| STL ownership on product page (FVS-014) | An "already owned → go to library" state | No per-customer ownership signal exists or is planned; library is removed |
| Refund shipping (FVS-032) | A shipping-refund line item | Nothing to refund — no shipping was ever charged |
| Digital refund (FVS-032) | A revocation confirmation gate tied to an entitlement | No entitlement; becomes a plain informational warning |

## 8. Product-owner decisions still unresolved

From `BACKEND-RESPONSE.md` §7, the items that block correct (not just complete) frontend design in this slice range:

1. **Q1** — Should admin order responses list the legal next actions per line? Blocks FVS-030, FVS-031. Decider: product owner, before VS-029.
2. **Q4** — Which online payment provider (Whish, a card gateway, or both)? Blocks FVS-026, FVS-027. Decider: product owner, before VS-032.
3. **Q3** (consequence of Q4) — Payment return-URL shape and polling parameters. Blocks FVS-027.
4. **Q7** — Captcha vendor, and whether captcha should also cover registration/resend/password-reset. Blocks FVS-002 (reconsideration), FVS-015, FVS-016.
5. **Q8** — Consent wording (terms, digital-final-sale, cash-terms text). Blocks FVS-026; needs legal sign-off, not just backend work.
6. **Q9** — STL delivery-time promise shown on product pages/checkout. Blocks FVS-014, FVS-026.
7. **Q2** — Should a signed-in customer see "you own this STL" before clicking "add to cart"? Blocks FVS-014, FVS-025. Nothing is specified; not building it is the safe current default.
8. **Q10** — Can a default address be deleted, and what becomes default afterward? Blocks FVS-023 design details (backend's call, not product's).

## 9. Safe implementation batches, in recommended order

**Batch 1 — Mount the real public storefront (no backend changes needed, all A-class):**
FVS-001 (verify against a live backend) → FVS-013 (`/shop`, with the UUID-facet and single-value-filter corrections) → FVS-014 (`/shop/:slug`, without the owned-STL/library state) → FVS-022 (`/`, `/about`, real Home/About content, floating WhatsApp).

**Batch 2 — Mount real customer/auth/account features (all A-class):**
FVS-002/003 (verify against a live backend — already functionally complete) → FVS-004 (`/forgot-password`, `/reset-password`) → FVS-006 (verify, already mounted) → FVS-008 (`/account/notifications`).

**Batch 3 — Mount the currently-built admin features, unblocked by the MFA resolution (all A-class), in dependency order:**
FVS-005 (`/admin/*` guard + MFA, fixing the `mfaVerified` assumption first — everything below depends on this) → FVS-007 (`/admin/settings`) → FVS-009 (`/admin/customers`) → FVS-010 (`/admin/categories`, `/admin/materials`, `/admin/colours`) → FVS-011 (`/admin/products`, with version-conflict handling added) → FVS-012 (embedded image management, with scan-polling removed).

**Batch 4 — Retire the superseded slices (no backend dependency, pure cleanup):**
Delete or clearly mark unreachable: FVS-018, FVS-019, FVS-020, FVS-021 (ADR-019: `AssetVersionWorkflow`, `AssetVersionList`, `AssetVersionUploader`, `useScanStatusPolling`, `GrantEntitlementDialog`, `entitlementGrantModels`, `EntitlementModel`, `EntitlementList`, `EntitlementCard`, `DownloadButton`, `downloadHistoryModel`, `DownloadHistoryTable`, `DownloadNotice`) and FVS-024 (ADR-024: `ShippingZoneManager`). Correct `RefundCreateForm` now (drop the shipping row, change the entitlement gate to a plain warning) even though FVS-032 as a whole stays blocked.

**Later — cart/checkout/orders/payments, only once the backend actually exists:**
FVS-023 → FVS-025 → FVS-026 (after Q7/Q8 resolve enough to ship placeholder-but-honest consent copy) → FVS-027 (after Q3/Q4 resolve) → FVS-028 → FVS-029 → FVS-030 (after Q1 resolves) → FVS-031 → FVS-032 (after the refundable-balance field location is decided). FVS-015/016/017 (BYI, contact, contact queue) can move in parallel with this group once P2-1/P2-2/P2-3/P2-4 land — they have no commerce dependency, only a captcha dependency (Q7).

## 10. Exact first batch for a real, manually testable storefront

This is the smallest set of work that produces a storefront a human can click through end-to-end against the real backend, per `docs/backend-handoff/README.md`'s "Start the backend" instructions and `BACKEND-RESPONSE.md` §5's "Level 1/2 unlocked now" table:

1. Stand up the backend locally (`docker compose up -d --build`, migrate, seed) and serve `storage/media_public/` with a `/media/*` proxy rewrite — required until VS-020, per `BACKEND-RESPONSE.md` B4.
2. Mount `/shop` (FVS-013) with the `category_id`/`material_id`/`colour_id` facet-mapping fix and the corrected sort allowlist.
3. Mount `/shop/:slug` (FVS-014) without the owned-STL/library state.
4. Mount `/` and `/about` (FVS-022) with the real Home composition and floating WhatsApp button.
5. Verify FVS-002/FVS-003 (already built) against the real backend, using the seeded `seed-customer@example.com` account and the `email_outbox` SQL workaround for any email-dependent step (`BACKEND-RESPONSE.md` A3).
6. Mount `/forgot-password`/`/reset-password` (FVS-004).

At that point, a tester can browse, search, filter, view a product, register, verify, log in, reset a password, and chat via WhatsApp — the entire "Level 1 + Level 2" unlock from `MINIMUM-MANUAL-TEST-UNLOCK.md`, fully backed by real, built endpoints, with zero invented contracts.

## 11. Risks / migration notes

- **Do not let FVS-032's existing components ship un-corrected.** `RefundCreateForm` currently (per its design intent) contains a shipping-refund row and an entitlement-revocation confirmation gate, both of which reference removed concepts (ADR-024, ADR-019). This is a correctness bug waiting to surface the moment refunds are demoed, independent of whether the refund backend exists yet.
- **`/media` is not served locally today.** Any manual test of the storefront batch (section 10) needs the workaround in `BACKEND-RESPONSE.md` B4 (serve `storage/media_public/` yourself and proxy `/media/*` to it) or every product image will 404.
- **Admin MFA fixture gap:** the seeded administrator is already MFA-enrolled, so FVS-005's enrollment screens (`MfaSetupWizard`) cannot be manually tested without a non-enrolled admin account, which has no self-service creation path (`BACKEND-RESPONSE.md` A3(b), open question #13). Request one from the backend owner before testing enrollment specifically.
- **Rate limits apply during manual/automated testing** and must be reset between test runs via the documented Redis `ratelimit:*` key deletion (never `FLUSHALL` — it also holds MFA challenges and the job queue) (`BACKEND-RESPONSE.md` A3(d)).
- **The FVS plan's own slice numbers occasionally disagree with where `BACKEND-RESPONSE.md` points.** For example, `BACKEND-RESPONSE.md`'s removal table cites "the threshold display in FVS-022 and FVS-026" for the free-shipping threshold, but FVS-022 as written in `FRONTEND-VERTICAL-SLICE-PLAN.md` (Home/About/WhatsApp) does not itself render a threshold banner — only FVS-007 (settings editor) and FVS-026 (checkout) plausibly would. Treat `BACKEND-RESPONSE.md`'s slice-number citations as approximate pointers into milestone FM-B/C, not as a guarantee that the named FVS file is the only place to check, and grep the actual component tree before assuming a concept is or isn't present somewhere.
- **No real backend has been reachable in this environment at any point** (`BACKEND-UNLOCK-HANDOFF.md` line 14). Every "ready now" (A) classification in this document is ready on paper, against documented contracts and `openapi.json` — it still needs a first real round-trip against a running backend before being called done, per `docs/setup/frontend-setup.md` and the project's own slice Definition of Done.
