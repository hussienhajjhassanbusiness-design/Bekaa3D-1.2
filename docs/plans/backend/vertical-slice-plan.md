# Bekaa3D — Vertical Slice Implementation Plan

**Step:** 18 — Split the project into vertical slices  
**Date:** 2026-08-10  
**Status:** Planned for V1 implementation  
**Source:** Approved SRS + frozen database design + endpoint contract + ADRs

> This plan deliberately avoids layer-first work such as “build all models, then all repositories, then all routes.” Each slice must leave one usable/testable capability merged end-to-end.

# 1. Ordering Rules

Order is based on:

1. **Dependency:** a slice cannot rely on business capability that does not exist.
2. **Risk:** security, payment, upload, concurrency, file-delivery and irreversible data-model risks are proven early.
3. **Business value:** catalogue, purchasing, fulfillment and digital delivery stay on the critical path.
4. **Mergeability:** early slices are independently reviewable and deployable; later slices reuse already-proven ports and boundaries.

Cross-cutting requirements are **not deferred to a final layer phase**. A slice that introduces an unsafe write also introduces its authorization, CSRF/rate-limit rule, audit/outbox behavior, tests and API documentation.

# 2. External Risk Track — Starts Immediately

The following work begins in parallel with VS-001 and does not wait for the code sequence:

- Whish merchant onboarding, sandbox access and credentials.
- Confirm webhook signature mechanism.
- Confirm transaction status-query capability.
- Confirm refund API versus manual transfer.
- Confirm USD settlement/support and callback allowlisting details.
- Select/configure transactional email provider and SPF/DKIM once the domain is available.

Until Whish credentials are available, commerce is built against the payment-provider port and mock adapter. **VS-027 is the adapter swap/contract-validation slice, not a rewrite of checkout.**

# 3. Milestones

| Milestone | Slices | Exit condition |
|---|---|---|
| A — Secure Foundation | VS-001–VS-009 | API, auth, verification, MFA, settings, notifications/admin account operations are usable |
| B — Catalogue & Risky Uploads | VS-010–VS-018 | Catalogue, secure uploads, STL versioning, entitlement and protected download architecture are proven |
| C — Commerce | VS-019–VS-027 | Mixed cart → checkout → verified payment → fulfillment/refund works; Whish can replace mock |
| D — Negotiation & Engagement | VS-028–VS-035 | Offers, reviews, wishlist and BYI operations are complete |
| E — Reporting, Data Rights & Release | VS-036–VS-040 | Analytics, audit visibility, privacy rights and production hardening pass release gates |

# 4. Vertical Slices

## VS-001 — Bootable API, PostgreSQL migration baseline, health/readiness, request correlation

**SRS features:** F-134, F-137  
**Priority:** P0  
**Risk:** High technical foundation  
**Business value:** Enables every later slice  
**Depends on:** None

- **Model change:** No business model yet. Establish SQLAlchemy metadata conventions and PostgreSQL extensions required by the frozen schema.
- **Migration:** Alembic baseline; required PostgreSQL extensions; migration smoke test.
- **Request/response schema:** `LivenessRead`, `ReadinessRead`, RFC 9457 base problem model.
- **Logic / side effects:** Application startup/shutdown, DB connectivity/readiness, request IDs, structured PII-safe logging, global error translation.
- **Endpoint / entrypoint:** `GET /health/live`, `GET /health/ready`.
- **Tests:** App boots; liveness works without DB probe; readiness fails when DB is unavailable; correlation ID present; malformed/error response contract.
- **Documentation:** Environment/bootstrap instructions; health semantics; migration command; logging/request-ID contract.
- **Mergeable outcome:** A clean checkout of the repository can start the API against PostgreSQL and CI can prove the service is alive/ready.

## VS-002 — User registration, email verification, resend, transactional outbox and first worker job

**SRS features:** F-020, F-023, F-130, F-136  
**Priority:** P0  
**Risk:** High — email gates all customer actions  
**Business value:** First real customer capability  
**Depends on:** VS-001

- **Model change:** `users`, `verification_tokens`, `email_outbox`, initial `audit_logs` support.
- **Migration:** Create the four tables, live-email uniqueness, token expiry/uniqueness, outbox due-work index.
- **Request/response schema:** `RegisterRequest`, `RegistrationAccepted`, `VerifyEmailRequest`, `ResendVerificationRequest`.
- **Logic / side effects:** Argon2id hashing; enumeration-safe registration/resend; single-use verification token; outbox insert in same transaction; email-provider port; `dispatch_outbox` arq job with retry/backoff.
- **Endpoint / entrypoint:** `POST /api/v1/auth/register`, `/verify-email`, `/resend-verification`.
- **Tests:** New/existing email enumeration behavior; invalid/expired/used token; unverified boundary; outbox durability; worker retry; audit event.
- **Documentation:** OpenAPI examples; email/outbox failure behavior; local dev email adapter; worker startup.
- **Mergeable outcome:** A user can register and verify through a durable email workflow; email-provider failure never rolls back registration.

## VS-003 — Login, logout, refresh rotation, CSRF and session reuse detection

**SRS features:** F-021  
**Priority:** P0  
**Risk:** High security  
**Business value:** Unlocks authenticated features  
**Depends on:** VS-002

- **Model change:** `sessions`.
- **Migration:** Session table with hashed refresh token, token version, rotation/reuse/revocation timestamps and expiry indexes.
- **Request/response schema:** `LoginRequest`, `SessionRead`; cookie/CSRF response contract.
- **Logic / side effects:** Credential verification; progressive failure delay/lockout; short-lived access cookie; rotating refresh cookie; double-submit CSRF; reuse detection; logout/revocation.
- **Endpoint / entrypoint:** `POST /api/v1/auth/login`, `/logout`, `/refresh`.
- **Tests:** Bad credentials remain enumeration-safe; cookie flags; CSRF rejection; successful rotation; old-token reuse revokes session; logout; expired/revoked sessions.
- **Documentation:** Browser auth flow, cookie settings, CSRF header, session lifecycle.
- **Mergeable outcome:** A verified customer can maintain a secure browser session and a stolen old refresh token cannot be replayed silently.

## VS-004 — Password reset with global session revocation

**SRS features:** F-022  
**Priority:** P0  
**Risk:** High security  
**Business value:** Account recovery  
**Depends on:** VS-002, VS-003

- **Model change:** `password_reset_tokens`.
- **Migration:** Reset-token table, single-use/expiry indexes.
- **Request/response schema:** `PasswordResetRequest`, `PasswordResetConfirm`.
- **Logic / side effects:** Enumeration-safe request, hashed token, expiry/use validation, password replacement, revoke all sessions, outbox email, audit event.
- **Endpoint / entrypoint:** `POST /api/v1/auth/password-reset/request`, `/confirm`.
- **Tests:** Unknown email; expired/used token; password rules; old sessions rejected after reset; outbox retry.
- **Documentation:** Reset lifecycle and security behavior.
- **Mergeable outcome:** A customer can recover an account without leaking whether arbitrary email addresses exist.

## VS-005 — Administrator MFA and isolated admin security boundary

**SRS features:** F-118  
**Priority:** P0  
**Risk:** High privileged security  
**Business value:** Safely unlocks admin development  
**Depends on:** VS-003

- **Model change:** `mfa_credentials`, `mfa_recovery_codes`.
- **Migration:** MFA credential and one-time hashed recovery-code tables/constraints.
- **Request/response schema:** MFA setup/challenge/verify/recovery-code schemas.
- **Logic / side effects:** TOTP enrollment/confirmation, challenge, recovery-code use/regeneration, admin dependency requiring MFA, non-admin admin-route 404 behavior, separate admin rate-limit policy.
- **Endpoint / entrypoint:** `POST /api/v1/auth/mfa/setup`, `/setup/confirm`, `/verify`, `/recovery-codes/regenerate` plus protected `/api/v1/admin` boundary.
- **Tests:** MFA required for admin; invalid TOTP; recovery code one-time use; non-admin sees 404; audit events.
- **Documentation:** Admin enrollment/recovery runbook and OpenAPI security scheme.
- **Mergeable outcome:** Admin routes can now be built behind one tested MFA/auth boundary instead of repeating security per endpoint.

## VS-006 — Current customer profile

**SRS features:** F-024  
**Priority:** P1  
**Risk:** Low  
**Business value:** Account self-service foundation  
**Depends on:** VS-003

- **Model change:** None beyond existing `users` columns.
- **Migration:** None.
- **Request/response schema:** `UserProfileRead` (ID, email, verification/account state — no mutable fields in V1).
- **Logic / side effects:** Read own profile; ownership enforcement. No write path — the SRS defines no mutable profile field for V1. If one is approved later, add it as a requirement change rather than inventing it here.
- **Endpoint / entrypoint:** `GET /api/v1/me`.
- **Tests:** Ownership; unverified read allowed.
- **Documentation:** Profile contract.
- **Mergeable outcome:** The customer can view their own account profile through an ownership-checked, read-only endpoint.

## VS-007 — Typed settings editor and safe public settings

**SRS features:** F-114, supports F-068/F-002/F-011  
**Priority:** P0  
**Risk:** Medium — business controls must not be hardcoded  
**Business value:** Operational control  
**Depends on:** VS-005

- **Model change:** `settings`.
- **Migration:** Typed setting table and unique key/index.
- **Request/response schema:** `SettingRead`, `SettingUpdate`, `PublicSettingsRead`.
- **Logic / side effects:** Type/range validation; fixed key allowlist; audit every change; strict public-key allowlist. Seed required settings: accepting orders, offer windows, cooldown, offer floor, checkout hold, unverified purge, daily download cap, free shipping, pickup address/hours, WhatsApp number.
- **Endpoint / entrypoint:** `GET/PATCH /api/v1/admin/settings/{key}`, list settings, `GET /api/v1/settings/public`.
- **Tests:** Wrong type/range; secret/internal setting never leaks publicly; audit; setting changes require no restart.
- **Documentation:** Setting key registry and which keys are public.
- **Mergeable outcome:** Business-tunable values are database-backed before commerce code starts depending on them.

## VS-008 — In-app notification centre

**SRS features:** F-032, F-105  
**Priority:** P1  
**Risk:** Low  
**Business value:** Reusable customer communication channel  
**Depends on:** VS-003

- **Model change:** `notifications`.
- **Migration:** Notification table and user/recent/unread indexes.
- **Request/response schema:** `NotificationRead/Page`, `NotificationUpdate`.
- **Logic / side effects:** Create notification application service; own-user list; mark read/unread; bounded pagination.
- **Endpoint / entrypoint:** `GET /api/v1/me/notifications`, `PATCH /api/v1/me/notifications/{id}`.
- **Tests:** Ownership/IDOR; pagination; unread filter; read/unread mutation; verified write rule.
- **Documentation:** Notification type/payload contract. Later slices add concrete event types.
- **Mergeable outcome:** Later payment/order/offer slices can emit durable in-app events without redesigning customer communication.

## VS-009 — Admin user management

**SRS features:** F-116  
**Priority:** P1  
**Risk:** Medium security/PII  
**Business value:** Core admin operations  
**Depends on:** VS-005

- **Model change:** Use `users` and existing auth state.
- **Migration:** None expected.
- **Request/response schema:** `AdminUserPage`, `AdminUserDetail`, `AdminUserUpdate`.
- **Logic / side effects:** Search/list users, view account state, activate/deactivate only approved fields, PII-safe audit/logging.
- **Endpoint / entrypoint:** `GET /api/v1/admin/users`, `GET/PATCH /api/v1/admin/users/{id}`.
- **Tests:** Admin MFA; non-admin hiding; search/pagination; disabled account behavior; audit.
- **Documentation:** Allowed admin mutations and PII handling.
- **Mergeable outcome:** The admin can manage accounts without database access.

## VS-010 — Category, material and colour management

**SRS features:** F-112; supports F-007/F-008/F-013  
**Priority:** P1  
**Risk:** Low — plain reference-data tables (see ADR-016)  
**Business value:** Prerequisite for catalogue  
**Depends on:** VS-005

- **Model change:** `categories`, `materials`, `colours`.
- **Migration:** Reference-data tables; category slug partial unique index.
- **Request/response schema:** Public lists plus admin create/read/update/archive schemas.
- **Logic / side effects:** Active/soft-delete behavior, no subcategories.
- **Endpoint / entrypoint:** Public `/categories`, `/materials`, `/colours`; admin CRUD groups.
- **Tests:** Slug collision; archived values hidden publicly; bounded reference lists.
- **Documentation:** Admin reference-data workflow.
- **Mergeable outcome:** Products can reference controlled facet values.

## VS-011 — Create and manage physical/STL products

**SRS features:** F-110  
**Priority:** P0  
**Risk:** High — central domain/type integrity  
**Business value:** Core sellable catalogue  
**Depends on:** VS-007, VS-010

- **Model change:** `products` (name/description/slug/SEO fields live directly on the table — ADR-016).
- **Migration:** Product/type fields, physical-only CHECK constraints, live slug index, catalogue indexes needed immediately.
- **Request/response schema:** `AdminProductCreate/Update/Detail`.
- **Logic / side effects:** Immutable product type; physical purchase modes; no stock quantity; required name; server-controlled aggregates; soft delete releases slug.
- **Endpoint / entrypoint:** Admin product list/create/detail/update/delete.
- **Tests:** Physical/STL invalid-field combinations; name-required validation; slug reuse after soft delete; WhatsApp-only/availability rules; money validation.
- **Documentation:** Product type matrix and publication requirements.
- **Mergeable outcome:** Admin can create valid physical and STL catalogue records without touching SQL.

## VS-012 — Product image upload, cover selection and ordering using shared storage/scanning

**SRS features:** F-111; SEC-13/14/15/16  
**Priority:** P0  
**Risk:** High upload/security integration  
**Business value:** Required product presentation + proves shared integrations  
**Depends on:** VS-011

- **Model change:** `product_images`.
- **Migration:** Image metadata table, active-cover partial unique constraint.
- **Request/response schema:** Multipart upload, image update/order/cover response schemas.
- **Logic / side effects:** Introduce shared `StoragePort` + local adapter and `MalwareScannerPort` + ClamAV adapter; inspect content not extension; re-encode images; generated storage key; cover/order rules; soft-delete metadata.
- **Endpoint / entrypoint:** Admin product image upload/update/cover/reorder/delete.
- **Tests:** Fake extension, disallowed type, malware result, re-encoding, cover race/uniqueness, reorder ownership, storage cleanup behavior.
- **Documentation:** Upload limits, storage contract, ClamAV/dev setup.
- **Mergeable outcome:** One real upload path proves the cross-context storage/scanning abstraction before STL and guest uploads reuse it.

## VS-013 — Public catalogue, product detail, search, filters, sorting and SEO data

**SRS features:** F-004–F-010, backend part of F-013  
**Priority:** P0  
**Risk:** Medium search complexity  
**Business value:** First storefront discovery experience  
**Depends on:** VS-010, VS-011, VS-012

- **Model change:** Use `products.search_vector`; maintained product aggregates.
- **Migration:** GIN FTS/trigram indexes; final browse/facet/sort indexes.
- **Request/response schema:** `ProductPage`, `ProductListItem`, `ProductDetail`, search suggestions.
- **Logic / side effects:** English FTS; trigram fallback; cursor pagination; allowlisted facets/sorts; only live/visible products in active categories; unavailable stays visible; SEO fields.
- **Endpoint / entrypoint:** `GET /api/v1/products`, `/products/{slug}`, `/search/suggestions`.
- **Tests:** Typo tolerance; filters AND together; cursor stability; hidden/deleted/category-inactive exclusion; most-downloaded sort only where valid; NFR query shape.
- **Documentation:** Search/filter/sort contract; SEO fields. Sitemap/page rendering remains frontend/rendering responsibility.
- **Mergeable outcome:** A visitor can discover and evaluate either product type.

## VS-014 — Secure guest Bring Your Idea submission with captcha and private attachments

**SRS features:** F-106, F-132; part of F-133  
**Priority:** P0  
**Risk:** High guest-upload security  
**Business value:** High-value lead channel  
**Depends on:** VS-012

- **Model change:** `custom_requests`, `custom_request_attachments`.
- **Migration:** Lead and attachment tables, expiry/queue indexes.
- **Request/response schema:** Multipart `CustomRequestCreate`, safe receipt response.
- **Logic / side effects:** Shared CaptchaPort; per-IP/email rate limit; strict attachment count/size; magic-byte validation; image re-encoding; ClamAV; private storage; expiry assignment; no payment/order creation.
- **Endpoint / entrypoint:** `POST /api/v1/custom-requests`.
- **Tests:** Guest success; captcha failure; rate limit; malicious/bad file; oversized/count overflow; storage private; expiry set; disk failure cleanup.
- **Documentation:** Public form limits, retention setting, security controls.
- **Mergeable outcome:** The riskiest unauthenticated upload path is proven before launch rather than left to hardening.

## VS-015 — Contact form and admin message queue

**SRS features:** F-108; F-132/F-133 for this form  
**Priority:** P1  
**Risk:** Medium abuse surface  
**Business value:** Direct lead/support channel  
**Depends on:** VS-005

- **Model change:** `contact_messages`.
- **Migration:** Contact queue table/status/date indexes.
- **Request/response schema:** `ContactMessageCreate/Receipt`, admin detail/page/update.
- **Logic / side effects:** Guest captcha/rate limit; new/read/replied/archived state; admin list/read/status update; audit admin access.
- **Endpoint / entrypoint:** `POST /api/v1/contact-messages`; admin contact list/detail/update.
- **Tests:** Captcha/rate limit; queue status validation; admin boundary; no email enumeration/PII logs.
- **Documentation:** Queue states and contact-form limits.
- **Mergeable outcome:** Visitor messages flow into a controlled admin queue.

## VS-016 — STL multi-file upload, checksum, malware scan and atomic version publishing

**SRS features:** F-080, F-081, F-082  
**Priority:** P0  
**Risk:** High digital-asset security  
**Business value:** Prerequisite for STL revenue  
**Depends on:** VS-011, VS-012

- **Model change:** `asset_versions`, `stl_assets`.
- **Migration:** Version/file tables, unique version number/current version, checksum/storage-key constraints.
- **Request/response schema:** Admin asset-version list/upload/detail/publish schemas.
- **Logic / side effects:** Private storage; server UUID filenames; checksum; scan states; one-or-more file bundle; cannot publish until clean; publish entire version atomically; superseded files retained.
- **Endpoint / entrypoint:** Admin product asset-version list/upload, asset-version detail/publish.
- **Tests:** Multi-file atomicity; infected/pending files cannot publish; current-version race; old version retained; product must be STL.
- **Documentation:** Bundle/version lifecycle and storage/scan contract.
- **Mergeable outcome:** Admin can safely publish a current STL bundle without mixing versions.

## VS-017 — First-class entitlement grant and purchased STL library

**SRS features:** F-027, F-083 (admin-grant path first)  
**Priority:** P0  
**Risk:** High authorization model  
**Business value:** Proves digital ownership before payments  
**Depends on:** VS-005, VS-016

- **Model change:** `entitlements`.
- **Migration:** Entitlement table; partial unique active `(user_id, product_id)`.
- **Request/response schema:** `AdminEntitlementGrant`, `EntitlementPage/Detail`.
- **Logic / side effects:** Entitlement is sole download authority; admin grant source; revoke-capable model; customer sees current version/file metadata without private paths.
- **Endpoint / entrypoint:** `POST /api/v1/admin/users/{user_id}/entitlements`, `GET /api/v1/me/entitlements*`.
- **Tests:** Only STL; active uniqueness; ownership; current version visible; revoked hidden/no download capability; audit/notification.
- **Documentation:** Grant sources and authorization invariant.
- **Mergeable outcome:** Digital ownership can be tested end-to-end before introducing payment side effects.

## VS-018 — Authorized resumable STL download with abuse cap and logging

**SRS features:** F-028, F-084–F-087  
**Priority:** P0  
**Risk:** Critical digital security/performance  
**Business value:** Completes STL delivery path  
**Depends on:** VS-017, VS-007

- **Model change:** `downloads` monthly-partitioned table.
- **Migration:** Downloads parent/current partitions, indexes, partition-aware PK.
- **Request/response schema:** Download-history page; HTTP file response contract.
- **Logic / side effects:** Check verified user + active entitlement + daily cap; write salted-IP download log; return nginx `X-Accel-Redirect`; support HTTP Range via nginx; never expose storage key.
- **Endpoint / entrypoint:** Entitlement-file download endpoint; `GET /api/v1/me/downloads`.
- **Tests:** No entitlement/revoked/other user; cap; Range; invalid range; log fields; X-Accel path inaccessible directly; FastAPI does not stream bytes.
- **Documentation:** nginx internal location, local storage permissions, download authorization sequence.
- **Mergeable outcome:** An admin-granted user can securely download a private STL through the exact production delivery architecture.

## VS-019 — Saved addresses and shipping-zone administration/selection

**SRS features:** F-025, F-043, F-044, F-045, F-113  
**Priority:** P1  
**Risk:** Medium commerce prerequisite  
**Business value:** Enables physical checkout  
**Depends on:** VS-005, VS-007

- **Model change:** `addresses`, `shipping_zones`.
- **Migration:** Address/default partial unique index; shipping-zone table.
- **Request/response schema:** Address CRUD/default schemas, admin/customer shipping-zone schemas.
- **Logic / side effects:** Own address book; one default; explicit active-zone selection; rates server-owned; pickup requires no address; free-shipping threshold read from Setting.
- **Endpoint / entrypoint:** `/api/v1/me/addresses*`, `GET /api/v1/shipping-zones`, admin shipping-zone CRUD.
- **Tests:** Default switching; ownership; archived zone unavailable to checkout; no automatic governorate mapping; old-order snapshot independence later.
- **Documentation:** V1 explicit zone-selection rule.
- **Mergeable outcome:** Physical orders now have validated delivery/pickup inputs ready for checkout.

## VS-020 — Mixed cart with physical quantity caps and STL ownership rules

**SRS features:** F-040, F-041  
**Priority:** P0  
**Risk:** High mixed-commerce rules  
**Business value:** Core purchase funnel  
**Depends on:** VS-011, VS-017

- **Model change:** `carts`, `cart_items`.
- **Migration:** One cart/user; unique `(cart, product)`; quantity checks.
- **Request/response schema:** `CartRead`, `CartItemAdd`, `CartItemQuantityUpdate`.
- **Logic / side effects:** One persistent cart; merge duplicate product; STL qty=1; reject owned STL; reject unavailable/WhatsApp-only physical; enforce current max quantity; store price snapshot.
- **Endpoint / entrypoint:** `GET /api/v1/cart`, add/update/delete cart item.
- **Tests:** Merge race; quantity cap; STL duplicate/owned; unverified write; product mode/availability; snapshot/current price exposure.
- **Documentation:** Cart invariants and price snapshot semantics.
- **Mergeable outcome:** A verified customer can hold a valid mixed physical+digital cart.

## VS-021 — Idempotent checkout with mock payment, price confirmation and order snapshots

**SRS features:** F-042, F-046, F-052, F-067, F-068; mock path for F-047  
**Priority:** P0  
**Risk:** Critical transaction/concurrency  
**Business value:** Core revenue path  
**Depends on:** VS-007, VS-019, VS-020

- **Model change:** `orders`, `order_items`, `order_status_history`, `payments`, `idempotency_records`.
- **Migration:** Order/payment/idempotency tables, one-live-payment constraint, order-number uniqueness, snapshot/check constraints.
- **Request/response schema:** `CheckoutRequest`, price-change conflict extension, `CheckoutRead`, order/payment summaries.
- **Logic / side effects:** Introduce Payments provider port + mock adapter. In one DB transaction: idempotency, kill switch, lock cart, revalidate products/ownership/quantities, validate delivery/pickup, calculate trusted shipping/free threshold/totals, detect/confirm price changes, capture terms/digital-final-sale consent, snapshot product/address/zone/rates, compute dispatch estimate, create pending payment, clear cart.
- **Endpoint / entrypoint:** `POST /api/v1/checkout`.
- **Tests:** Parallel double checkout; idempotency replay/body conflict; price changes; cart mutates concurrently; delivery/pickup matrix; exact totals; digital consent; kill switch; rollback leaves cart intact on failure.
- **Documentation:** Checkout transaction sequence and mock-provider redirect flow.
- **Mergeable outcome:** A customer can convert a valid mixed cart into one immutable pending-payment order safely.

## VS-022 — Payment webhook persistence, independent verification, reconciliation and manual fallback using mock provider

**SRS features:** F-048, F-049, F-050, F-051; completes mock F-047  
**Priority:** P0  
**Risk:** Critical payment security  
**Business value:** Turns pending orders into safely paid orders  
**Depends on:** VS-008, VS-017, VS-021

- **Model change:** `webhook_events`; use payments/orders/entitlements/history/outbox/notifications.
- **Migration:** Webhook unique `(provider,event_id)`; processing/reconciliation indexes.
- **Request/response schema:** Webhook receipt; admin payment page/detail/manual confirm.
- **Logic / side effects:** Persist duplicate-safe callback and return quickly; never trust callback as proof; query mock provider outside DB locks; exact amount match; transactionally mark paid, grant STL entitlements, advance physical lines into paid/production-ready workflow as frozen, recompute order projection, close applicable offer later, append history/audit/outbox/notifications. Add `reconcile_payments` scheduled job and manual confirmation fallback.
- **Endpoint / entrypoint:** Whish-shaped payment webhook route backed by mock in dev; admin payment list/detail/reconcile/confirm.
- **Tests:** Forged/invalid signature path; duplicate webhook; amount mismatch; missing callback recovered by reconciliation; concurrent verifier; no double entitlement; manual confirm audit.
- **Documentation:** Payment verification sequence and operational reconciliation runbook.
- **Mergeable outcome:** No product is granted or produced from callback data alone; a lost callback is recoverable.

## VS-023 — Customer order history and detail

**SRS features:** F-026  
**Priority:** P1  
**Risk:** Medium ownership  
**Business value:** Customer trust/support reduction  
**Depends on:** VS-021

- **Model change:** No new tables.
- **Migration:** Query indexes already created; adjust only if explain plans require.
- **Request/response schema:** `OrderPage`, `OrderDetail` with customer-safe payment/refund/history projections.
- **Logic / side effects:** Own-order filtering; no admin note leak; cursor pagination; status/date filters.
- **Endpoint / entrypoint:** `GET /api/v1/me/orders`, `GET /api/v1/me/orders/{id}`.
- **Tests:** IDOR/404 hiding; mixed order detail; snapshot values survive product/address edits; pagination.
- **Documentation:** Customer-visible order projection/status semantics.
- **Mergeable outcome:** A customer can inspect immutable purchase history without seeing admin-only data.

## VS-024 — Admin order queue, internal notes and per-line delivery/pickup transitions

**SRS features:** F-060–F-064  
**Priority:** P0  
**Risk:** High state machine  
**Business value:** Enables actual fulfillment  
**Depends on:** VS-005, VS-008, VS-022

- **Model change:** Use order/order-item/history tables.
- **Migration:** Fulfillment queue indexes if not already present.
- **Request/response schema:** `AdminOrderPage/Detail`, `AdminOrderUpdate`, `OrderItemTransitionRequest`.
- **Logic / side effects:** Filter/search queue; edit internal note only; legal delivery and pickup state transitions; row lock; derive order status; append history/audit; enqueue localized email + notification events.
- **Endpoint / entrypoint:** Admin orders list/detail/update; line transition endpoint.
- **Tests:** Every legal/illegal edge; mixed-order projection; row-lock concurrency; admin note never customer-visible; email/notification side effects.
- **Documentation:** State-machine transition tables and operational queue usage.
- **Mergeable outcome:** Admin can take a paid physical line through production to delivery or pickup without direct status mutation.

## VS-025 — Customer self-cancellation, admin cancellation and returned-item resolution

**SRS features:** F-033, F-065, F-066  
**Priority:** P0  
**Risk:** High concurrency/refund boundary  
**Business value:** Essential exception handling  
**Depends on:** VS-024

- **Model change:** Use order items/history; refund obligation may be invoked once VS-026 exists.
- **Migration:** None expected.
- **Request/response schema:** Customer/admin cancellation requests; return transition reason.
- **Logic / side effects:** Customer may cancel paid physical work only pre-production; STL never self-cancellable; admin cancellation after production follows refund obligation path; shipped can become returned; returned can re-ship/reprint/refund; lock same line so production-start vs self-cancel has one winner.
- **Endpoint / entrypoint:** Customer order cancel; admin order cancel; existing line transition endpoint handles returned/re-ship/reprint.
- **Tests:** Mandatory cancellation-vs-production race; STL unaffected; partial mixed cancellation; illegal edges; notifications/history/audit.
- **Documentation:** Cancellation cutoff and returned nonterminal flow.
- **Mergeable outcome:** The system handles the highest-risk physical fulfillment exceptions deterministically.

## VS-026 — Full/partial per-line refunds, shipping refund and settlement obligations

**SRS features:** F-070–F-074  
**Priority:** P0  
**Risk:** Critical financial correctness  
**Business value:** Required commerce safety net  
**Depends on:** VS-022, VS-024, VS-017

- **Model change:** `refunds`, `refund_items`.
- **Migration:** Refund tables; pending-obligation indexes; amount checks.
- **Request/response schema:** `RefundCreate`, `RefundDetail/Page`, `RefundSettlementRequest`.
- **Logic / side effects:** Idempotent refund creation; server derives refundable balances; selected line amounts + shipping; obligation remains pending until settlement; provider/manual method; digital refund revokes entitlement; recompute order projection; audit/outbox/notification.
- **Endpoint / entrypoint:** Create refund on order; admin refund queue/detail/settle.
- **Tests:** **Mandatory mixed-order partial-refund E2E**; over-refund; duplicate idempotency; shipping refund; entitlement revocation; failed/manual settlement; already-downloaded file remains evidence only.
- **Documentation:** Refund accounting rules and settlement runbook.
- **Mergeable outcome:** A mixed order can refund only the physical failure and shipping while preserving valid digital ownership.

## VS-027 — Live Whish adapter and production payment contract

**SRS features:** F-047–F-051 live provider  
**Priority:** P0 / externally blocked  
**Risk:** Critical external integration  
**Business value:** Unlocks real revenue  
**Depends on:** VS-021, VS-022; Whish credentials/capabilities

- **Model change:** No schema redesign; provider metadata only.
- **Migration:** Only additive provider-specific metadata if confirmed necessary and approved first.
- **Request/response schema:** No client contract change expected.
- **Logic / side effects:** Implement Whish create-payment/redirect, signature verification if available, status query, refund if available; exact mapping to provider port. Keep reconciliation/manual fallback for missing capabilities.
- **Endpoint / entrypoint:** Existing checkout/webhook/admin payment routes; no provider-specific business routes beyond `/webhooks/payments/whish`.
- **Tests:** Provider contract tests against sandbox/mock fixtures; signature cases; status mapping; amount mismatch; network timeout/retry; duplicate callback; refund capability branches.
- **Documentation:** Credentials, webhook allowlist/signature, sandbox, reconciliation, manual fallback, provider incident runbook.
- **Mergeable outcome:** Switching `PAYMENT_PROVIDER=whish` exercises the same proven business flows without rewriting checkout/order logic.

## VS-028 — Offer submission, customer history, minimum floor, cooldown and expiry

**SRS features:** F-029, F-090, F-093, F-096, F-097  
**Priority:** P1  
**Risk:** High state/deadline rules  
**Business value:** STL negotiation revenue  
**Depends on:** VS-007, VS-011, VS-017

- **Model change:** `offers`, `offer_rounds`.
- **Migration:** One live offer/user/product partial unique; deadline/status indexes; append-only rounds.
- **Request/response schema:** `OfferCreate`, `OfferPage/Detail`.
- **Logic / side effects:** STL-only; not already owned; configured minimum floor; one live offer; first append-only round; turn/deadline; rejection cooldown; `expire_offers` scheduled job; history visibility.
- **Endpoint / entrypoint:** `POST /api/v1/offers`, `GET /api/v1/me/offers*`; admin offer list/detail.
- **Tests:** Concurrent duplicate offer; floor/cooldown; owned product; automatic expiry; permanent round history.
- **Documentation:** Offer state/deadline definitions.
- **Mergeable outcome:** A customer can open one valid negotiation and both sides can inspect its immutable history.

## VS-029 — Admin/customer offer counter, accept, reject and withdraw

**SRS features:** F-091, F-092, F-095  
**Priority:** P1  
**Risk:** High state machine  
**Business value:** Completes negotiation interaction  
**Depends on:** VS-008, VS-028

- **Model change:** Use offers/rounds.
- **Migration:** None expected.
- **Request/response schema:** Counter/reject/withdraw action schemas.
- **Logic / side effects:** Turn enforcement; unlimited counters; every counter resets correct party deadline; accept freezes agreed price and starts checkout window; reject arms cooldown; customer withdraw pending states; timer precedence after acceptance; notifications/outbox.
- **Endpoint / entrypoint:** Customer counter/accept/withdraw; admin counter/accept/reject.
- **Tests:** Wrong turn; concurrent actions; deadline reset; accepted timer precedence; illegal transition; audit/notifications.
- **Documentation:** Offer state diagram and allowed actions.
- **Mergeable outcome:** Negotiation can reach accepted/rejected/withdrawn outcomes without generic status PATCHes.

## VS-030 — One-time accepted-offer checkout and auto-close on acquisition

**SRS features:** F-094, F-098  
**Priority:** P1  
**Risk:** High commerce integration  
**Business value:** Converts negotiation to revenue  
**Depends on:** VS-021, VS-022, VS-029

- **Model change:** Use offer/order/payment/idempotency records.
- **Migration:** None expected.
- **Request/response schema:** `OfferCheckoutRequest`, existing `CheckoutRead`.
- **Logic / side effects:** Accepted offer + owner + unexpired checkout window; immutable agreed price; one-time idempotent order/payment creation; digital final-sale consent; payment success grants entitlement and marks offer paid; acquiring product by any other route auto-closes live offer.
- **Endpoint / entrypoint:** `POST /api/v1/me/offers/{id}/checkout`.
- **Tests:** Expired window 410; list-price change ignored; second checkout prevented; normal-cart acquisition closes offer; payment side effects exactly once.
- **Documentation:** Offer checkout sequence.
- **Mergeable outcome:** An accepted negotiation converts into the same safe payment/entitlement pipeline at the frozen agreed price.

## VS-031 — Reviews, editable one-per-user and Verified Purchase badge

**SRS features:** F-031, F-100, F-102  
**Priority:** P1  
**Risk:** Medium abuse/aggregate correctness  
**Business value:** Storefront trust  
**Depends on:** VS-008, VS-011, VS-017, VS-024

- **Model change:** `reviews`; maintained product rating/review aggregates.
- **Migration:** Review table, rating check, active user/product unique constraint, moderation indexes.
- **Request/response schema:** Public review page; own review page; create/update response.
- **Logic / side effects:** Any verified user may review without purchase; one active review/product/user; rating 1–5; content filters; server recomputes verified-purchase badge from entitlement/physical purchase; aggregate updates transactionally.
- **Endpoint / entrypoint:** Public product reviews; `GET /me/reviews`; create/update/delete review.
- **Tests:** Non-purchaser allowed; duplicate rejected; badge grant/revoke; WhatsApp-only cannot badge; aggregate update on edit/delete; rate limit/content filter.
- **Documentation:** Explicit no-purchase-required rule and badge semantics.
- **Mergeable outcome:** Reviews work according to the approved open-review model without corrupting rating aggregates.

## VS-032 — Review moderation

**SRS features:** F-101  
**Priority:** P1  
**Risk:** Medium content moderation  
**Business value:** Protects catalogue quality  
**Depends on:** VS-031, VS-005

- **Model change:** Use review moderation fields.
- **Migration:** None expected.
- **Request/response schema:** Admin review page/detail, moderation request.
- **Logic / side effects:** Admin filter/view; hide/restore only; recalculate product aggregate; audit.
- **Endpoint / entrypoint:** Admin review list/detail/hide/restore.
- **Tests:** Hidden review excluded publicly; restore; aggregate changes; non-admin 404; audit.
- **Documentation:** Moderation behavior.
- **Mergeable outcome:** Admin can moderate abuse without deleting review history.

## VS-033 — Wishlist and most-wishlisted statistics

**SRS features:** F-030, F-103, F-104/F-123  
**Priority:** P2  
**Risk:** Low  
**Business value:** Customer engagement + merchandising signal  
**Depends on:** VS-011, VS-003

- **Model change:** `wishlist_items`; product `wishlist_count` aggregate.
- **Migration:** Soft-delete wishlist table; partial active unique; query index.
- **Request/response schema:** Wishlist page; idempotent add/remove.
- **Logic / side effects:** Verified user add/restore/remove; active-row aggregate; admin analytics reads maintained counts.
- **Endpoint / entrypoint:** `GET /me/wishlist`, `PUT/DELETE /me/wishlist/{product_id}`; wishlist analytics endpoint later may reuse query.
- **Tests:** Idempotent add; re-add after soft delete; count correctness; ownership; deleted product behavior.
- **Documentation:** Wishlist soft-delete/aggregate semantics.
- **Mergeable outcome:** Customers can maintain a wishlist and admin has reliable counts.

## VS-034 — Download monthly rollup and download analytics

**SRS features:** F-088, F-124, F-127  
**Priority:** P1  
**Risk:** Medium data-retention/partition operations  
**Business value:** Digital business analytics  
**Depends on:** VS-018

- **Model change:** `download_stats_monthly`.
- **Migration:** Aggregate table; month/product unique; ensure future download partitions.
- **Request/response schema:** Admin download analytics response.
- **Logic / side effects:** `prune_download_details` monthly job rolls old detail into aggregate before dropping retention-expired partitions; most-downloaded reads aggregate/counters, not ancient raw detail.
- **Endpoint / entrypoint:** `GET /api/v1/admin/analytics/downloads`.
- **Tests:** Rollup idempotency; no double count; partition prune only after aggregate; analytics date range; current/raw + aggregate combination if needed.
- **Documentation:** Retention/rollup and partition runbook.
- **Mergeable outcome:** Download history can age out without losing long-term business statistics.

## VS-035 — Bring Your Idea admin pipeline, quote/outcome and funnel analytics

**SRS features:** F-107, F-128  
**Priority:** P1  
**Risk:** Medium state machine  
**Business value:** Measures highest-value lead channel  
**Depends on:** VS-014, VS-005

- **Model change:** Use custom request fields/status/outcome.
- **Migration:** Add only if final quote/outcome fields were not in initial migration.
- **Request/response schema:** Admin request page/detail/update/transition; funnel analytics.
- **Logic / side effects:** New→Contacted→Quoted→In Progress→Completed→Closed, Lost exit; quoted amount/outcome validation; private attachment download; audit; funnel aggregation.
- **Endpoint / entrypoint:** Admin custom-request list/detail/update/transition/attachment download; `/admin/analytics/custom-requests/funnel`.
- **Tests:** Legal/illegal transitions; quote requirements; lost outcome; expired attachment unavailable; admin-only download; funnel counts.
- **Documentation:** Lead pipeline state diagram and funnel definition.
- **Mergeable outcome:** Admin can operate and measure the custom-print lead lifecycle.

## VS-036 — Core admin analytics

**SRS features:** F-120, F-121, F-122, F-125, F-126 plus reuse F-123  
**Priority:** P2  
**Risk:** Medium reporting correctness  
**Business value:** Admin decision support  
**Depends on:** VS-013, VS-022, VS-024, VS-028, VS-031, VS-033

- **Model change:** No new domain ownership; analytics is read/reporting application logic.
- **Migration:** Only proven read indexes after EXPLAIN; no speculative analytics tables.
- **Request/response schema:** Overview, revenue, recent purchases, customer stats, top-rated responses.
- **Logic / side effects:** Revenue attributed per order line (physical vs STL); bounded date ranges; pending offers count; maintained aggregates.
- **Endpoint / entrypoint:** Admin analytics overview/revenue/recent-purchases/customers/top-rated.
- **Tests:** Mixed order revenue split; refunded revenue policy per agreed reporting contract; bounds; empty ranges; admin-only.
- **Documentation:** Metric definitions so dashboard and backend cannot disagree.
- **Mergeable outcome:** The admin dashboard can report core business metrics without cross-context domain ownership leakage.

## VS-037 — Audit-log viewer

**SRS features:** F-117; surfaces F-135 already written incrementally  
**Priority:** P2  
**Risk:** Medium security/history  
**Business value:** Operational traceability  
**Depends on:** VS-005 and accumulated audit-producing slices

- **Model change:** Use partitioned `audit_logs`.
- **Migration:** Ensure current/future monthly audit partitions and filter indexes.
- **Request/response schema:** `AuditLogPage/Read`.
- **Logic / side effects:** Read-only admin filtering by actor/action/entity/request/date; no mutation routes; PII/secrets already redacted at write.
- **Endpoint / entrypoint:** `GET /api/v1/admin/audit-logs`, `GET /api/v1/admin/audit-logs/{id}`.
- **Tests:** Admin only; filters; partition crossing; sensitive fields absent; no write/delete endpoint.
- **Documentation:** Audit event taxonomy and retention/archive behavior.
- **Mergeable outcome:** Admin can investigate material actions without direct database access.

## VS-038 — Customer JSON data export

**SRS features:** F-034  
**Priority:** P2  
**Risk:** Medium privacy/ownership  
**Business value:** Data rights  
**Depends on:** VS-023, VS-018, VS-028, VS-031

- **Model change:** No new table.
- **Migration:** None.
- **Request/response schema:** `DataExportRead`.
- **Logic / side effects:** Export own profile, addresses, orders, downloads, reviews and offers; bounded/stream-safe generation strategy; never include secrets/internal notes/provider secrets.
- **Endpoint / entrypoint:** `GET /api/v1/me/export`.
- **Tests:** Ownership; expected domains present; sensitive fields absent; deleted/revoked history policy; rate limit.
- **Documentation:** Export contents and privacy exclusions.
- **Mergeable outcome:** A customer can obtain the approved JSON account export.

## VS-039 — Account deletion via anonymisation with blocking rules

**SRS features:** F-035  
**Priority:** P1  
**Risk:** High privacy/referential integrity  
**Business value:** Data rights + compliance  
**Depends on:** VS-023, VS-026

- **Model change:** Use user anonymisation/deletion fields and retained history.
- **Migration:** None expected.
- **Request/response schema:** `AccountDeletionRequest`.
- **Logic / side effects:** Fresh auth; block while open orders/unsettled refunds; strip PII, disable login/revoke sessions, soft-delete addresses/reviews/wishlist as approved, retain anonymized financial/download records, audit event.
- **Endpoint / entrypoint:** `DELETE /api/v1/me`.
- **Tests:** Blocked open order/refund; successful anonymisation; cannot log in; financial/download history preserved without PII; repeated deletion safe.
- **Documentation:** Anonymisation field map and retention justification.
- **Mergeable outcome:** Account deletion satisfies the frozen retention model without breaking financial history.

## VS-040 — Production hardening, maintenance jobs, backup verification and release gates

**SRS features:** F-133, F-136 completion, F-138; NFR/SEC operational gates  
**Priority:** P0 release gate  
**Risk:** Critical operations  
**Business value:** Makes completed features safe to launch  
**Depends on:** All preceding production slices

- **Model change:** No new business domain required; use retention/idempotency/audit/download tables.
- **Migration:** Automate/verify future partitions; any operational indexes discovered under load.
- **Request/response schema:** No new business API; readiness may expose non-secret dependency status.
- **Logic / side effects:** Complete per-endpoint rate-limit coverage; scheduled `purge_unverified_users`, `purge_expired_attachments`, `reap_orphan_files`, `ensure_partitions`, `rotate_ip_salt`, backup verification; cron-liveness monitoring; disk >80% alert; off-server encrypted backups; restore drill; secrets/non-root/resource limits; production CORS/security headers.
- **Endpoint / entrypoint:** No job-trigger public endpoints. Existing health/readiness only.
- **Tests:** Security sweep/IDOR; rate-limit tests; migration reversibility; backup restore test; partition exhaustion prevention; load targets (catalog/search/checkout/download initiation); failure drills for Redis/email/provider/DB/storage where practical.
- **Documentation:** Deployment/operations runbook, backup/restore, cron/job registry, monitoring alerts, incident checklist.
- **Mergeable outcome:** Release is blocked until security, recovery, monitoring and performance gates pass—not merely because feature tests are green.

# 5. Requirements Traceability Notes

## Public/front-end features that do not need their own backend slice

- **F-001 Home page** — composed by the frontend from public catalogue, settings, BYI/contact capabilities; no CMS was required.
- **F-002 Floating WhatsApp button** — uses `GET /api/v1/settings/public` from VS-007.
- **F-003 About Us** — frontend/static content under the approved V1 scope; no backend CMS requirement.
- **F-011 Product WhatsApp click-to-chat** — product detail from VS-013 + WhatsApp number from VS-007; no order/API write is created.
- **F-013 SEO rendering/sitemaps** — backend exposes slugs/SEO data in VS-013; rendering/sitemap generation remains in the web/rendering layer.

## Platform requirements implemented incrementally

- **F-130 Outbox:** introduced in VS-002; new event templates are added in the slice that introduces that event.
- **F-132 Captcha:** introduced on the first risky guest upload in VS-014 and reused by contact in VS-015.
- **F-133 Rate limiting:** applied to every sensitive slice when introduced; VS-040 performs final coverage verification.
- **F-134 Structured logging/correlation:** introduced in VS-001.
- **F-135 Audit logging:** audit persistence begins with security/admin-sensitive slices; each later mutation must write its own event; viewer arrives in VS-037.
- **F-136 Jobs:** worker/scheduler starts with durable outbox in VS-002; each feature registers its own expiry/reconciliation/retention job.
- **F-137 Health/readiness:** VS-001.
- **F-138 Backup verification:** VS-040.

# 6. Definition of Done for Every Slice

A slice is not complete because an endpoint returns 200 locally. It is complete only when all applicable items below are true:

- [ ] Domain/business rule implemented in the owning bounded context.
- [ ] Database change has a reviewed Alembic migration, or the slice explicitly states no migration is needed.
- [ ] Pydantic/OpenAPI request and response contract implemented.
- [ ] Authentication, verified-email boundary, ownership and admin-MFA rules applied.
- [ ] CSRF/rate limit/captcha/upload controls applied where required.
- [ ] Money uses integer cents; timestamps use UTC; server remains price/status authority.
- [ ] Transaction boundaries and concurrency behavior are explicit.
- [ ] Audit, history, notification and outbox side effects are included where required.
- [ ] Unit tests cover domain rules/state transitions.
- [ ] PostgreSQL integration tests exercise constraints and repository queries.
- [ ] API tests cover success + documented errors + authorization/IDOR.
- [ ] Concurrency test exists when the slice contains a known race.
- [ ] External-adapter contract tests exist when an integration is introduced.
- [ ] Documentation/OpenAPI examples updated.
- [ ] CI is green and the slice can be merged without depending on unfinished code in another branch.

# 7. Merge Strategy

1. Prefer one pull request per slice.
2. A slice may add only the tables/ports it actually needs; do not scaffold all 43 tables first.
3. Shared abstractions are introduced by the **first real feature that needs them** (for example Storage/ClamAV in VS-012), then reused.
4. Do not create placeholder repository/service classes for future slices.
5. Schema/index changes discovered by later real query plans are additive migrations, not speculative work.
6. Keep the main branch deployable after every merged slice.
7. Whish integration is allowed to merge as soon as credentials are available after its dependencies pass; it does not have to wait for engagement/analytics work.

# 8. Explicitly Do Not Plan as Separate Tasks

Do **not** create backlog items such as:

- “Create all SQLAlchemy models.”
- “Create all Pydantic schemas.”
- “Create all repositories.”
- “Create all services.”
- “Create all routes.”
- “Add tests for everything later.”
- “Add security later.”

Those are implementation layers inside a vertical slice, not deliverables by themselves.

# 9. Step 18 Completion

- [x] Work is split by working business/operational capability.
- [x] Every slice identifies model/migration/schema/logic/endpoint/tests/docs.
- [x] High-risk email/auth/upload/download/payment/concurrency paths are pulled forward.
- [x] Whish onboarding is an immediate parallel risk track.
- [x] Mock provider allows commerce to proceed without merchant credentials.
- [x] First slices are independently mergeable.
- [x] All V1 backend feature groups are mapped to slices or explicitly marked as frontend/non-API responsibilities.
- [x] Production hardening is a release gate, while security requirements are also implemented incrementally.

**Step 18: COMPLETE — implementation backlog is ready to be turned into tickets.**