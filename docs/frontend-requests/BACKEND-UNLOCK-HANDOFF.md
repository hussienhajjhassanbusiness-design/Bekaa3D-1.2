# Bekaa3D Frontend — Backend-Unlock Handoff

**Audit scope:** FVS-001 through FVS-032 (Milestones FM-A, FM-B, FM-C — the entire frontend built to date). Built from repository evidence only: `vertical-slice-plan.md`, `FRONTEND-VERTICAL-SLICE-PLAN.md` (esp. §17 and the §18 traceability matrix), `docs/frontend-setup.md`, all 32 `FVS-*-IMPLEMENTATION-PLAN.md` files, and the actual `src/` tree.

---

## Current frontend status

- **154 presentational/model units built and unit-tested** across FM-A/B/C. Every slice followed the same discipline: build everything that doesn't require a guessed backend contract, defer everything that does.
- **Only 6 routes are actually mounted:** `/`, `/account`, `/account/profile`, `/login`, `/register`, `/verify-email`, `/verify-email/resend`. Every other page — `/shop`, product detail, `/cart`, `/checkout`, `/account/orders`, `/account/addresses`, `/account/library`, `/account/downloads`, `/about`, `/contact`, `/bring-your-idea`, and **the entire `/admin/*` tree** — exists only as unmounted components today.
- **Fully working end-to-end against a confirmed contract (frontend side only — never tested against a real backend):** registration, email verification, resend, login (incl. the 202 MFA handoff), logout, token refresh, cross-tab logout, `/me` session bootstrap, account profile. This is the one slice of the app that needs *no new backend confirmation* — only a running backend to test against.
- **The single largest structural blocker:** no backend confirmation exists for how the frontend learns a user is an admin (`isAdmin`/`mfaVerified` — source unconfirmed). `AdminProtectedRoute` cannot be built without it, and every admin route in the entire app (FVS-005, 007, 009, 010, 011, 012, 017, 018, 019 partial, 024 admin half, 028, 030, 031, 032) is blocked on this one decision.
- **The single most under-specified endpoint:** the actual STL file-download endpoint (distinct from the confirmed `GET /me/downloads` *history* endpoint) has no path anywhere — not even a placeholder.
- No real backend has been reachable in this environment at any point in this engagement. Every "real backend acceptance" task across all 32 slices is still pending for that reason alone, independent of any contract gap below.

**Raw backend-confirmation gaps found in the plans:** 170 `NEEDS BACKEND CONFIRMATION` markers across 31 plan files. **Deduplicated into the domains below: 24.**

---

## P0-A — Local Runtime / Local Integration

*What we need to run frontend and backend together at all.*

### A1. OpenAPI / schema source
**Classification:** CONFIRMATION. **Priority:** Highest — ask this first, it may resolve many items below at once.
- Frontend work complete: `apiClient`, proxy, error model all built against RFC 9457 generically.
- Ask: Does an OpenAPI spec or Pydantic schema set already exist for any confirmed slice? If so, send the file/location rather than having anyone re-type field lists by hand.
- Unlocks: potentially dozens of the items below without further back-and-forth.

### A2. Local backend startup
**Classification:** RUNTIME-TESTING.
- Frontend already confirmed/built: `.env.local`'s `API_PROXY_TARGET`, Next.js proxy rewrites (`/api/health/*` strips the `/api` prefix, `/api/v1/*` preserves it), `GET /health/ready`/`GET /health/live` both confirmed and wired (`BackendUnreachableBanner`).
- Needed: how to start the backend locally (Docker Compose or equivalent), DB provisioning, migrations, seed command, and whether the frontend needs any CORS allowance (expected: no, since the browser only ever calls same-origin `/api/...` — confirm this is still true for any tooling that bypasses the Next proxy, e.g. direct Postman testing).
- Unlocks: every real-backend acceptance task across all 32 slices (currently 100% pending).

### A3. Test account & fixture provisioning
**Classification:** RUNTIME-TESTING.
- Needed now: (a) a working way to retrieve a registration/verification/reset email during local testing — the plan mentions a file-based dev email adapter "being built on the backend side, not ready yet"; until then, confirm the manual `email_outbox` SQL-read workaround is acceptable. (b) One disposable **admin** account with MFA already enrolled (or a documented way to enroll one) — admin MFA setup itself is a blocked frontend slice (FVS-005), so the backend must hand us a working admin session for testing independent of that UI.
- Unlocks: manual testing of FVS-002/003/004/006 (customer) and any admin testing at all.

---

## P0-B — Real Visible Storefront

*Smallest contract set so home/shop/product pages show real data instead of empty/mocked components.*

### B1. Public settings response shape
**Classification:** BLOCKER. **Affected FVS:** 007 (partial), 014, 022, 026 (kill-switch/threshold fields).
- Confirmed endpoint: `GET /api/v1/settings/public` (literal path, reused by FVS-007/014/022).
- Needs confirmation: is the response a flat object or a `{key, value}[]` list (explicitly unresolved in the plan)? Exact field names for: WhatsApp business number (+ optional message param), `accepting-orders` kill-switch, free-shipping threshold amount + currency.
- Frontend work complete: `publicSettingsKeys.ts`/`publicSettingsModel.ts` (model only, no fetch adapter — intentionally, since the envelope shape is unknown), `buildWhatsAppHref`, `FloatingWhatsAppButton`, `HeroSection`.
- Minimum answer to unblock: the literal response shape plus these three field names.

### B2. Catalogue — public list contract
**Classification:** BLOCKER. **Affected FVS:** 013.
- Confirmed: URL filter keys are literal (`category`, `material`, `colour`, `sort`, `q`, `cursor`).
- Needs confirmation: `GET /products` exact path/query-param wire names; `ProductListItem` response fields (zero given anywhere); whether a facet can carry multiple values and how they're serialized (repeated params / comma / pipe / JSON — flagged by the plan itself as its own gate).
- Frontend work complete: `shopUrlState.ts`, `FilterPanel`, `SortSelect`, `SearchBar`, `EmptyState`, `LoadMore` — all built, awaiting the response contract to build `ProductCard`/`ProductGrid`.
- Fixture needed: a small seeded catalogue (a few products per category/material/colour combination) for acceptance testing.

### B3. Product detail contract
**Classification:** BLOCKER. **Affected FVS:** 014.
- Confirmed literal paths: product detail, `GET /settings/public` (shared with B1).
- Needs confirmation: full response schema (price, type, material, colour, images, stock/availability, an ownership/"owned" indicator for STL products — see C11).
- Frontend work complete: `PriceDisplay`, `ProductTypeBadge`, `UnavailableNotice`, `ProductImageGallery`, WhatsApp CTA helpers, anonymous-path `AddToCartButton`.

### B4. Image/asset URL format
**Classification:** CONFIRMATION. **Affected FVS:** 012 (partial), 013, 014.
- Needs confirmation: does the product/image API response include a ready-to-use public URL per image, or a storage key the frontend must combine with a base path? Is it stable across dev/staging/prod?

### B5. Search-suggestions endpoint
**Classification:** CONFIRMATION. **Affected FVS:** 013 (secondary).
- Needs confirmation: endpoint shape, debounce/min-character expectations, response field names.

---

## P0-C — Real Customer Purchase Flow

*Registration → products → cart → address/shipping → checkout → payment verification → orders → entitlement/download.*

### C1. RFC 9457 field-level validation-error shape
**Classification:** BLOCKER (affects every form in the purchase flow). **Affected FVS:** nearly all write-endpoints, most visibly 023/025/026.
- Needs confirmation: exact JSON shape of a 422, field-by-field (an `errors[]` array with `field`/`message`, or Pydantic's raw `loc`/`msg` passed through?).

### C2. Cursor pagination response shape
**Classification:** BLOCKER. **Affected FVS:** 013, 029, 008, admin lists generally.
- Needs confirmation: request param names for cursor + page size; response field names for next-cursor and has-more. Is the cursor opaque or a raw sortable value?

### C3. Address book contract
**Classification:** BLOCKER. **Affected FVS:** 023.
- Confirmed: `/api/v1/me/addresses*` (literal wildcard).
- Needs confirmation: every individual field (name/phone/street/city/governorate/postal/country/label); default-address mutation mechanism (dedicated action vs. `PATCH {is_default}`) and what happens to the previous default; delete semantics (hard vs. soft, can a default be deleted, can an address referenced by an order be deleted).
- Frontend work complete: query keys/model, `AddressCard`/`AddressList`, `DefaultAddressSelector`, optimistic-default helper.

### C4. Shipping zones — public read
**Classification:** BLOCKER. **Affected FVS:** 024 (public half), 026.
- Confirmed: `GET /api/v1/shipping-zones` (literal, public).
- Needs confirmation: exact `ShippingZoneRead` fields (id, name, rate-cents, currency, active flag, region list?).

### C5. Cart contract
**Classification:** BLOCKER. **Affected FVS:** 025.
- Confirmed: `GET /api/v1/cart` (literal).
- Needs confirmation: full envelope (cart id, item id, product type/display name/thumbnail, quantity + max-quantity, snapshot price vs. current price, currency), item mutation bodies (`POST /cart/items`, `PATCH .../{item_id}`, `DELETE .../{item_id}` — all placeholders), how an unavailable/owned-STL/quantity-capped rejection is represented, duplicate-add merge behavior.
- Known wiring gap: `EntitlementModel` (FVS-020) has no `productId` field, so the already-owned-STL cart precheck can't actually be wired even once cart mutations land — needs either that field or an explicit per-product ownership check (see C11).

### C6. Checkout contract — CRITICAL
**Classification:** BLOCKER. **Affected FVS:** 026.
- Confirmed: `POST /api/v1/checkout`, `GET /shipping-zones`.
- Needs confirmation: full request body (cart id/version, address id, zone id, pickup representation, consent fields); Idempotency-Key mechanism (header name, client- vs. server-generated, TTL, whether a key is reusable after a timeout/conflict or must be rotated); exact price-change-conflict / cart-changed-concurrently response (HTTP status, RFC code, payload shape, old/new price fields, affected-line id); kill-switch/threshold field names (shared with B1); digital final-sale consent representation — **this last one also needs approved legal/product copy, not just a backend field, since no consent wording exists anywhere in the repo.**
- Frontend work complete: `useCheckoutAttempt` (idempotency-key generator, contract-agnostic), `CheckoutStepper`, `DeliveryMethodSelector`, `ConsentCheckboxGroup`, three conflict/status banners, display-only `OrderSummary`.

### C7. Payment verification — CRITICAL, highest safety priority
**Classification:** BLOCKER. **Affected FVS:** 027.
- Needs confirmation: **no status-read endpoint is confirmed at all** — is it a dedicated endpoint, or is `GET /me/orders/{id}` (literal, but owned by FVS-029) the intended read? Exact return-URL query params (order id vs. payment id, extra provider params to strip); status enum literals (pending/processing/paid/failed/expired, and whether a distinct `cancelled` exists); recommended polling interval, backoff, max duration, request timeout — **none of these have any default anywhere in the frontend today, by design, rather than inventing one.**
- Frontend work complete: `PaymentVerificationState` (4-variant state model), contract-neutral `extractReturnIdentifier`, `usePaymentStatusPoller`, all 5 result-state components, `PaymentResultView` (contains the test proving query-string manipulation can never fake a success state).

### C8. Order/order-line status enum + "available actions"
**Classification:** BLOCKER. **Affected FVS:** 029 (display only here; 030/031 need the admin-transition half, see P1).
- Needs confirmation: the exhaustive order-line status enum (physical vs. STL — one shared enum or two?); whether API responses include a machine-readable "available actions" list so the frontend never has to re-encode a state machine itself.
- This is the single biggest cross-slice architecture gap in the whole engagement — FVS-029/030/031 all independently flagged it.

### C9. Entitlements / customer library contract
**Classification:** BLOCKER. **Affected FVS:** 020.
- Confirmed: `GET /api/v1/me/entitlements*` (both list and detail, literal).
- Needs confirmation: envelope/row field names. No ownership/status field is confirmed at all today — the only confirmed semantic is "absent from the list = not entitled" (revoked items are excluded, never shown in a revoked state).

### C10. STL download delivery — CRITICAL, no placeholder exists
**Classification:** BLOCKER. **Affected FVS:** 021.
- Confirmed: `GET /api/v1/me/downloads` (history list, literal).
- **Not confirmed, not even as a placeholder:** the actual file-download endpoint path. The frontend's `DownloadButton` must render a real `<a href>` (never a JS fetch, to preserve HTTP Range/resume) and needs the exact path.
- Also unresolved, with no analog in any existing gap list: since a plain anchor navigation can never read a JSON error body, **how does a daily-cap-exceeded or revoked-access failure ever reach the frontend as usable UX at all?** No redirect-with-error convention, no pre-download eligibility check, nothing — needs a concrete answer, not just a URL.
- Frontend work complete: `DownloadButton` (real anchor, required accessible label), `downloadHistoryModel.ts`, `DownloadHistoryTable`, `DownloadNotice` (generic kind: cap/revoked/generic — no status-code mapping yet).

### C11. Per-product ownership check
**Classification:** CONFIRMATION. **Affected FVS:** 014, 025.
- Needs confirmation: is there a dedicated "is this product owned by me" signal (on product detail or elsewhere), or must the frontend diff the full entitlement list client-side? The latter doesn't scale and isn't confirmed as intended.

### C12. Idempotency-Key mechanism
**Classification:** BLOCKER. **Affected FVS:** 026, 032 (and FM-D's 036, out of scope here).
- Needs confirmation: header name, who generates the key, format, TTL/replay window. (Folded into C6 above for checkout specifically; listed separately because it also gates refund creation, P1.)

---

## P1 — Admin Commerce

*Admin auth/MFA, products/assets, shipping, payments, orders, fulfillment, cancellation, refunds.*

### P1-1. Admin authorization source — THE top unlock
**Classification:** BLOCKER (architecture decision, not just a missing field). **Affected FVS:** 005 (directly), and transitively **every** admin route: 007, 009, 010, 011, 012, 017, 018, 019, 024, 028, 030, 031, 032.
- Needs confirmation: where does the frontend learn a logged-in user is an admin, and that their MFA is verified for the current session — a field on `GET /me`, a separate endpoint, a claim in a token? `AdminProtectedRoute` cannot exist without this, and nothing under `/admin/*` can be mounted until it does.

### P1-2. Admin MFA contract
**Classification:** BLOCKER. **Affected FVS:** 005.
- Confirmed: reuses `POST /auth/login`'s 202 `{challenge_id, expires_in_seconds}` handoff; `/api/v1/admin` 404s non-admins server-side.
- Needs confirmation: request/response shapes for `verify`/`setup`/`setup/confirm`/`recovery-codes/regenerate`; whether `challenge_id` is safe to hold in frontend state at all.
- Frontend work complete: `RecoveryCodeList` (presentational only).

### P1-3. Admin settings
**Classification:** BLOCKER. **Affected FVS:** 007.
- Confirmed: `GET/PATCH /admin/settings/{key}`.
- Needs confirmation: the settings-**list** endpoint (to enumerate all keys) is unconfirmed; an authoritative setting-key registry (which keys exist, which require a confirmation step before save — not just the one `accepting-orders` example used throughout the plans).
- Frontend work complete: `EditableSetting` model, `SettingControl`, `SettingRow`, generic `ConfirmDialog`.

### P1-4. Admin customer management
**Classification:** BLOCKER. **Affected FVS:** 009.
- Confirmed: `GET /admin/users` (list path only).
- Needs confirmation: detail/PATCH paths; whether deactivation immediately revokes existing sessions and what an already-logged-in session receives on its next request.
- Frontend work complete: generic `AdminTable` (now the shared primitive for every admin list), `StatusBadge`, URL-state helpers.

### P1-5. Admin reference data (categories/materials/colours)
**Classification:** CONFIRMATION. **Affected FVS:** 010.
- Needs confirmation: final paths against an OpenAPI spec (plan explicitly flags this, not yet done); archive mechanism (dedicated endpoint vs. `DELETE`); can a product keep referencing a value that's later archived.
- Frontend work complete: `ReferenceDataManager` (one generic component for all three entity types).

### P1-6. Admin product CRUD
**Classification:** BLOCKER. **Affected FVS:** 011.
- All endpoint paths are explicit frontend-constructed placeholders.
- Needs confirmation: the full field matrix — which fields are shared, physical-only, STL-only — currently only prose/illustrative, not an exhaustive contract. Nothing resembling a form was built because of this.
- Frontend work complete: `MoneyInput` (cents-safe, currency-agnostic), `ProductTypeSelector`.

### P1-7. Admin product image upload
**Classification:** BLOCKER. **Affected FVS:** 012.
- All paths placeholder. Needs confirmation: upload request shape (multipart confirmed as transport, field names not); whether upload is synchronous accept/reject or returns an async scanning/pending state.
- Frontend work complete: upload domain model, `FileUploader` (now reused by FVS-015/018), `ImageGallery`.

### P1-8. Admin STL asset-version upload
**Classification:** BLOCKER. **Affected FVS:** 018.
- All 4 endpoints (list/create/detail/publish) prose-only.
- Needs confirmation: create-request shape (multipart? one bundle? field names?); wire literals for scan states (pending/clean/infected — concepts confirmed, literals not); recommended polling interval (deliberately left as a required caller param, no default exists).
- Frontend work complete: `assetVersionWorkflow.ts`, `AssetVersionList`, `AssetVersionUploader`, `useScanStatusPolling`.

### P1-9. Admin entitlement grant
**Classification:** CONFIRMATION (rare case — the endpoint path IS confirmed). **Affected FVS:** 019.
- Confirmed literal: `POST /api/v1/admin/users/{user_id}/entitlements`.
- Needs confirmation: request body fields (`AdminEntitlementGrant` has zero given); already-entitled conflict shape; how the admin obtains the product/customer option lists to search.
- Frontend work complete: `entitlementGrantModels.ts`, `DialogShell` (now shared infrastructure for every dialog in the app), `SearchableCombobox`, `GrantEntitlementDialog`.

### P1-10. Admin payments — CRITICAL
**Classification:** BLOCKER. **Affected FVS:** 028.
- All 4 endpoints (list/detail/reconcile/confirm) prose-only placeholders.
- Needs confirmation: list/detail field shapes; whether reconcile blocks until the provider answers or enqueues and returns immediately; manual-confirm's exact reason-field name and whether acknowledgment is a request-body field or purely a UX gate; allowed source-status matrix for manual confirm.
- Frontend work complete: `AdminPaymentModel` (reuses FVS-027's `PaymentStatus`), `PaymentDetail`, `ManualConfirmDialog`, `AdminPaymentList`.

### P1-11. Admin order fulfillment
**Classification:** BLOCKER. **Affected FVS:** 030.
- All endpoints prose-only. Shares the status-enum/available-actions gap (C8) at the admin-transition level: no exact state diagram exists anywhere, so the frontend cannot encode a transition table — it needs the server to supply legal next actions per line.
- Needs confirmation: list/detail/update/line-transition endpoint shapes; row-lock concurrency behavior.
- Frontend work complete: `AdminOrderLineModel`/`TransitionAffordance`, `InternalNoteEditor`, `TransitionActions`, `AdminOrderLine`, `AdminOrderDetail`, `OrderConcurrencyConflictNotice`.

### P1-12. Cancellation & returns
**Classification:** BLOCKER. **Affected FVS:** 031.
- Customer-cancel and admin-cancel endpoints have **no literal path at all, not even a placeholder.** Returns/re-ship/reprint/refund are confirmed (in prose) to reuse the same line-transition endpoint as P1-11.
- Needs confirmation: both cancel endpoints' paths/bodies; cancellation-cutoff semantics (pre-production vs. not); exact race-lost response when fulfillment outpaces a cancel request; refund-obligation representation after a post-production admin cancel.
- Frontend work complete: `OrderActionAffordance` (extracted, shared with P1-11's architecture), `CancelOrderLineButton`, `CancellableOrderLine`, `AdminCancelDialog`.

### P1-13. Refunds — CRITICAL, highest financial risk
**Classification:** BLOCKER. **Affected FVS:** 032.
- All 4 endpoints (create/list/detail/settle) are schema **names** only (`RefundCreate`, `RefundDetail/Page`, `RefundSettlementRequest`) — zero fields given anywhere.
- Needs confirmation: exact request/response shapes for all 4 operations; where the refundable-balance field lives (never derivable from price — frontend will not compute it); exact over-refund race error shape; settlement request body and manual-vs-provider distinction; **exact moment digital-refund entitlement revocation happens (at creation or at settlement) — the policy itself ("digital refund revokes entitlement") is already confirmed in prose, only the timing is open.**
- Frontend work complete: `refundKeys`/`RefundModel`/`RefundLineCandidate`, `RefundCreateForm` (full per-line + shipping independent refund, digital-revocation confirmation gate), `RefundDetail`, `RefundQueue`, `SettleRefundDialog`, extracted `useIdempotencyAttempt` (shared with C12).

---

## P2 — Secondary / Support

### P2-1. Captcha provider (BYI/contact)
**Classification:** CONFIRMATION. **Affected FVS:** 015, 016.
- Distinct from Turnstile (already confirmed for register/resend, see P2-6). Needs confirmation: which vendor, site key per environment.

### P2-2. Bring-Your-Idea submission
**Classification:** BLOCKER. **Affected FVS:** 015.
- No literal endpoint path. Needs confirmation: single bundled multipart request confirmed as the shape, but exact field name(s) for files, attachment MIME/size/count limits, scan synchronicity, rejection status/message field.
- Frontend work complete: `byiTypes.ts`, `BringYourIdeaForm`+`SuccessReceipt`, captcha-slot seam, and a refactor making `FileUploader` support a "driver"/deferred-selection mode (now reused by FVS-018 too).

### P2-3. Contact form
**Classification:** CONFIRMATION. **Affected FVS:** 016.
- Endpoint path confirmed literal. Needs confirmation: field names/validation/success schema.
- Frontend work complete: `ContactForm`, generalized `SuccessReceipt`, shared `guestSubmissionFeedback.ts` vocabulary.

### P2-4. Admin contact queue
**Classification:** BLOCKER. **Affected FVS:** 017.
- No literal endpoint paths. Needs confirmation: full CRUD shapes; whether list rows include name/email or only id+status; URL filter param key name (deliberately left unresolved — only value-normalization was built).
- Frontend work complete: `contactMessageWorkflow.ts`, generalized `StatusBadge`, `MessageDetail`, `contactQueueFilter.ts`.

### P2-5. Notifications
**Classification:** CONFIRMATION. **Affected FVS:** 008.
- List path confirmed literal (PATCH path implied). Needs confirmation: pagination field names (shared with C2); a living registry of notification `type` values as future slices add them.
- Frontend work complete: `NotificationItemModel`, `NotificationItem`, `NotificationList`, `NotificationBell` (not yet wired into `Header` — deliberately, no fabricated unread count).

### P2-6. Password reset
**Classification:** BLOCKER. **Affected FVS:** 004.
- Endpoint path **names** given (`/auth/password-reset/{request,confirm}`) but every field is unconfirmed: request/confirm body fields, success status/body, reset-specific password policy, invalid/expired/used-token status+code, rate limiting.
- Frontend work complete: token extraction/URL-sanitization logic only (`passwordResetToken.ts`).

### P2-7. Turnstile field contract
**Classification:** CONFIRMATION. **Affected FVS:** 002 (resend/register).
- Vendor confirmed (Turnstile). Needs confirmation: request field name for the token, and when it's actually being turned on.

### P2-8. Rate-limit (429) universality
**Classification:** CONFIRMATION. **Affected FVS:** 004, 015, 016, (033 in FM-D).
- Partially resolved: the auth family's `Retry-After` is confirmed as whole-number seconds (not an HTTP-date) — already implemented in `ApiError.retryAfterSeconds`. Needs confirmation that the same shape applies to BYI/contact/offer rate limits.

---

## Test accounts and fixtures

The smallest useful set, each tied to a concrete testing need — nothing speculative:

1. **Working local email delivery** for the register/verify/reset loop (the planned dev file-based adapter, or confirmation that manual `email_outbox` SQL reads remain the accepted workaround).
2. **One disposable admin account with MFA already enrolled** (backend-provisioned — the frontend MFA-enrollment UI is itself blocked, see P1-2).
3. **One physical product** (priced, in stock) for catalogue/cart/checkout testing.
4. **One STL product with a clean, published, current asset version** for entitlement/cart/ownership/download testing.
5. **One STL entitlement already granted** to the test customer, for ownership-precheck, library, and download testing.
6. **One seeded shipping zone** for checkout/free-shipping-threshold testing.
7. **A way to trigger each mock-payment outcome** (paid / failed / expired / pending) for FVS-027 testing — confirm whether the existing mock provider already supports this.
8. **A mixed cart scenario** (one physical + one STL line) — this is the *mandatory* partial-refund/partial-cancellation acceptance scenario the backend plan itself requires (VS-025/VS-026).
9. **Seeded orders in a few fulfillment states** (paid, in-production, delivered, returned) for FVS-029/030/031 testing — until admin mutation endpoints exist, this has to come from direct DB seeding.

---

## Backend response format

See `BACKEND-RESPONSE-TEMPLATE.md` — one fill-in block per endpoint/domain. If an OpenAPI/Pydantic schema already answers a question, send the file/location (see A1) rather than retyping it.

---

## Backend domain → FVS unlock map

| Domain | Priority | Unlocks (FVS) |
|---|---|---|
| A1 OpenAPI/schema source | P0-A | potentially all |
| A2 Local backend runtime | P0-A | all (acceptance testing) |
| A3 Test accounts/fixtures | P0-A | 002, 003, 004, 006, + all admin |
| B1 Public settings | P0-B | 007, 014, 022, 026 |
| B2 Catalogue public list | P0-B | 013 |
| B3 Product detail | P0-B | 014 |
| B4 Image/asset URL format | P0-B | 012, 013, 014 |
| B5 Search suggestions | P0-B | 013 |
| C1 Validation-error shape | P0-C | all forms |
| C2 Cursor pagination | P0-C | 013, 029, 008 |
| C3 Addresses | P0-C | 023 |
| C4 Shipping zones (public) | P0-C | 024, 026 |
| C5 Cart | P0-C | 025 |
| C6 Checkout | P0-C | 026 |
| C7 Payment verification | P0-C | 027 |
| C8 Order status enum/actions | P0-C | 029, 030, 031 |
| C9 Entitlements/library | P0-C | 020 |
| C10 STL download | P0-C | 021 |
| C11 Ownership check | P0-C | 014, 025 |
| C12 Idempotency-Key | P0-C | 026, 032 |
| P1-1 Admin authorization | P1 | 005, 007, 009, 010, 011, 012, 017, 018, 019, 024, 028, 030, 031, 032 |
| P1-2 Admin MFA | P1 | 005 |
| P1-3 Admin settings | P1 | 007 |
| P1-4 Admin customers | P1 | 009 |
| P1-5 Admin reference data | P1 | 010 |
| P1-6 Admin product CRUD | P1 | 011 |
| P1-7 Admin image upload | P1 | 012 |
| P1-8 Admin STL asset upload | P1 | 018 |
| P1-9 Admin entitlement grant | P1 | 019 |
| P1-10 Admin payments | P1 | 028 |
| P1-11 Admin order fulfillment | P1 | 030 |
| P1-12 Cancellation/returns | P1 | 031 |
| P1-13 Refunds | P1 | 032 |
| P2-1 Captcha (BYI/contact) | P2 | 015, 016 |
| P2-2 BYI submission | P2 | 015 |
| P2-3 Contact form | P2 | 016 |
| P2-4 Admin contact queue | P2 | 017 |
| P2-5 Notifications | P2 | 008 |
| P2-6 Password reset | P2 | 004 |
| P2-7 Turnstile contract | P2 | 002 |
| P2-8 Rate-limit universality | P2 | 004, 015, 016 |

---

## Recommended answer order

1. **A1 (OpenAPI/schema source)** — may shortcut many items below.
2. **A2/A3 (runtime + fixtures)** — nothing else can be acceptance-tested without this.
3. **P1-1 (admin authorization source)** — unblocks the single largest share of remaining frontend work (14 slices) for the cost of one decision.
4. **B1/B2/B3 (public settings + catalogue)** — fastest path to a visibly real storefront.
5. **C3–C8 (addresses → checkout → payment verification)**, in that order — this is a strict dependency chain; each needs the previous slice's data.
6. **C9/C10 (entitlements/downloads)** — completes the customer loop; C10 is urgent given zero placeholder exists today.
7. **P1-6 through P1-13 (admin commerce)** — once P1-1 lands, these can be answered in any order; refunds (P1-13) and payments (P1-10) carry the highest financial/security risk and deserve the most scrutiny.
8. **P2 items** — whenever convenient; nothing downstream depends on them.
