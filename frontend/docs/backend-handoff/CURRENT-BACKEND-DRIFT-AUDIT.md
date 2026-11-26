# Current Backend Contract Drift Audit

**Date:** 2026-11-09
**Scope:** compare the frontend's stored backend handoff against the real backend as it is today. Audit only: no `src/` change and no new frontend behaviour.

**Inputs compared**

| Label | Source | Operations | Schemas |
|---|---|---|---|
| **A** | `bekaa3D/docs/backend-handoff/openapi.json` (frontend's stored snapshot) | 57 | 80 |
| **B** | `Bekaa3D-backend/docs/frontend-handoff/openapi.json` (backend repo snapshot, written by `scripts/export_openapi.py`) | 129 | 211 |
| **C** | `GET http://localhost:8000/openapi.json` (running backend) | 129 | 211 |

**Method:** a script parsed all three documents and compared them: operations keyed by (method, path), and component schemas field by field (properties, `required`, `enum`, other keys). Runtime behaviour was checked with non-destructive probes against the running API. Built/not-built status was cross-checked against the backend's `docs/vertical-slice-plan.md` status table and `docs/settings-registry.md`.

---

## 1. Backend commit tested

- **Repository:** `C:\My projects\Bekaa3D-backend`, branch `main`
- **Commit:** `2dfb27b` (2026-10-25) — `test(VS-031): close deep-audit findings A-01 to A-05; add the audit report (#42)`
- **Runtime:** Docker. `/health/live` → `{"status":"ok"}`; `/health/ready` → `{"status":"ok","version":"0.1.0","commit":"unknown"}`. The `commit` field reports `unknown`, so the runtime does not identify its own build. The OpenAPI comparison below shows the runtime serves exactly the contract at `2dfb27b`.

## 2. Old frontend handoff snapshot status: **STALE**

- The frontend's `openapi.json` **and** `BACKEND-RESPONSE.md` are byte-identical to backend commit **`d1c1cf1` (2026-10-12)**, `docs: frontend handoff pack … (#9)`. That snapshot only covers VS-001 to VS-016.
- The backend's `openapi.json` has been regenerated about 30 times since then (VS-022 to VS-031, VS-033 to VS-035, VS-038 to VS-041, VS-046).
- `FRONTEND-BACKEND-RECONCILIATION.md` was built from snapshot A. **Its built/not-built claims for everything from cart onward are no longer authoritative** (see §9).
- `REAL-BACKEND-ACCEPTANCE.md` (2026-10-19) recorded "no backend, no Docker". That blocker is gone, but no real-runtime acceptance has been run yet. This audit is a contract comparison, not an acceptance run.

## 3. Current backend OpenAPI status: **B and C are identical**

- A deep JSON comparison of B and C returned `True`. Only key order differs: the export script uses `sort_keys`.
- So the backend repo's handoff snapshot is the authoritative contract for the running API. Use **B** as the replacement for **A**.
- **Caveat (documentation drift inside the backend repo):** the top of the backend's own `docs/frontend-handoff/BACKEND-RESPONSE.md` still says *"Nothing else exists yet: no checkout, order, payment or refund route."* That is contradicted by its own `openapi.json` and by `vertical-slice-plan.md`, which marks VS-023 to VS-031 and VS-039 to VS-041 as **Done**. The prose is stale and the OpenAPI is right. Treat OpenAPI and `vertical-slice-plan.md` as the source of truth, and per-domain backend docs (`docs/cart.md`, `checkout.md`, `refunds.md`, …) as the explanation.

## 4. Exact material contract differences (A → C)

### Summary count

| Class | Count |
|---|---|
| 1. ADDED BUILT CONTRACT (new operations) | **72** operations (+131 schemas) |
| 1. ADDED BUILT CONTRACT (new fields on existing schemas) | **5** (`cash_payment_enabled`, `cash_max_order_total`, `captcha_token` ×3) |
| 2. REMOVED CONTRACT | **1** field (`PublicSettingsRead.free_shipping_threshold`); **0** operations; **0** schemas |
| 3. CHANGED FIELD/SCHEMA (response semantics) | **1** (the `400`/`503` meaning on the 3 captcha-gated auth routes) |
| 4. CHANGED ENUM | **1** (`NotificationType` + `custom_request`) |
| 5. CHANGED PATH/METHOD | **0** |
| 6. CHANGED REQUIRED/OPTIONAL/NULLABILITY | covered by the rows above: all 5 added fields are **required**; `cash_max_order_total` is **non-nullable** |
| 7. DOCUMENTATION-ONLY | **4** (`GET /settings/public` description "five"→"six"; `PublicSettingsRead` description; `NotificationType` description; `AuditLogRead` description). `info` is unchanged |
| 8. NO MATERIAL CHANGE | the other 53 pre-existing operations and 74 pre-existing schemas |

**Material differences on the pre-existing contract: 8.** **Material differences in total: 80** (those 8 plus 72 new operations).

### 4.1 Changes to contract the frontend already integrates

| # | Area | Class | Old (A) | Current (B = C) | Evidence |
|---|---|---|---|---|---|
| D1 | Public settings | 1 + 6 | absent | `cash_payment_enabled: boolean`, **required** | schema `PublicSettingsRead`; runtime: `"cash_payment_enabled": true` |
| D2 | Public settings | 1 + 6 | absent | `cash_max_order_total: MoneyRead`, **required, not nullable** | schema; runtime `{"amount_cents":10000,"currency":"USD"}`; `settings-registry.md` row (1 to 1,000,000 cents, default 10000) |
| D3 | Public settings | 2 | `free_shipping_threshold: MoneyRead \| null`, required | **removed** | schema description: "removed by VS-028 (ADR-024)"; `settings-registry.md`: deleted 2026-10-20; runtime body has no such key |
| D4 | Auth: register | 1 + 6 | body `{email, password}` | body `{email, password, captcha_token}`; `captcha_token` **required**, string ≤ 2048, "Cloudflare Turnstile token" | schema `RegisterRequest`; runtime `POST /auth/register` without it → `422 VALIDATION_ERROR`, `errors[0].loc = ["body","captcha_token"]`, `type: "missing"` |
| D5 | Auth: resend verification | 1 + 6 | `{email}` | `{email, captcha_token}` (required) | schema `ResendVerificationRequest` |
| D6 | Password reset request | 1 + 6 | `{email}` | `{email, captcha_token}` (required) | schema `PasswordResetRequest`; runtime → `422` `loc ["body","captcha_token"]`. The **confirm** step is unchanged |
| D7 | Auth: register / resend / reset-request | 3 | `400` = `MALFORMED_REQUEST`; `503` = DB/Redis down | `400` = **`CAPTCHA_INVALID`** (empty/invalid/expired/used token); `503` = **captcha could not be verified, nothing done** (`Retry-After: 30` per backend P2-1) | response descriptions on all three operations; backend `BACKEND-RESPONSE.md` P2-1 |
| D8 | Notifications | 4 | `NotificationType` = account, order, payment, refund, offer, download | **+ `custom_request`** (ADR-030) | schema `NotificationType` |

**Direct contradiction of the old handoff:** `FRONTEND-BACKEND-RECONCILIATION.md` §3 (FVS-002) and §7 say *"No captcha exists on these routes; sending a token field is a `422`."* The current backend says the opposite: **omitting** the token is a `422`. The backend's ADR-025 (decided 2026-10-14) and ADR-026 made Turnstile mandatory on five forms, and the backend doc warns: *"On the three auth routes this is a breaking change … Ship the widget in the same release."*

Local captcha fixture (backend P2-1): with `CAPTCHA_PROVIDER=fake`, the backend accepts exactly `XXXX.DUMMY.TOKEN.XXXX`, which is the token Cloudflare's public test site key `1x00000000000000000000AA` issues.

### 4.2 No change (verified)

Login, logout, refresh, verify-email, password-reset confirm, MFA (setup, confirm, verify, recovery codes), `GET /me`, catalogue (`/products`, `/products/{slug}`, `/search/suggestions`, `/categories`, `/materials`, `/colours`), notifications paths, admin settings, admin users, admin reference data, admin products, admin product images, and admin audit logs all have **no schema or path change** between A and C. Product `capabilities`, sort enum, `PurchaseMode`, `ProductType` and `SettingType` are unchanged.

**Repo-only change behind an unchanged admin schema (FVS-007):** per `settings-registry.md`, the admin settings list now holds `cash_payment_enabled`, `cash_max_open_orders` (integer, 1 to 10) and `cash_max_order_total`. `free_shipping_threshold` was deleted by VS-028 and `daily_download_cap` by VS-023b. The generic typed renderer covers the new keys without contract change. I did not query the admin list at runtime because that needs an MFA admin session.

## 5. Newly built routes and capabilities (72 operations, all present in B and C)

| Domain | Backend slice (vertical-slice-plan: Done) | Operations |
|---|---|---|
| **Address book** | VS-026 (ADR-027) | `GET/POST /me/addresses`; `GET/PATCH/DELETE /me/addresses/{id}`; `PUT /me/addresses/{id}/default` |
| **Cart** | VS-022 (ADR-029) | `GET /cart`; `POST /cart/items`; `PATCH/DELETE /cart/items/{product_id}` |
| **Checkout** (digital, physical, cash) | VS-023, VS-028 (ADR-032, ADR-038) | `POST /checkout` (required `Idempotency-Key` header) |
| **Payments (customer)** | VS-023, VS-024 | `POST /me/orders/{id}/payments` (retry, `Idempotency-Key`); `POST /webhooks/payments/{provider}` |
| **STL ownership** | VS-023 (ADR-025) | `GET /me/stl-ownership?product_id=` → `{product_id, owned}` |
| **Customer orders** | VS-025, VS-029b, VS-031 | `GET /me/orders`; `GET /me/orders/{id}`; `POST …/cancel`; `POST …/confirm-receipt`; `POST …/report-problem` |
| **Admin orders / fulfilment / cash** | VS-029, VS-031 (ADR-040, ADR-043) | `GET /admin/orders`; `GET/PATCH /admin/orders/{id}`; `POST …/items/{item_id}/transition`; `POST …/cash-handover`; `POST …/cancel`; `POST …/release` |
| **Admin STL delivery queue** | VS-023b (ADR-039) | `GET /admin/stl-deliveries` |
| **Admin payments** | VS-024 (ADR-036) | `GET /admin/payments`; `GET /admin/payments/{id}`; `POST …/confirm`; `POST …/reconcile`; `POST …/record-capture` |
| **Refunds / chargebacks** | VS-030 (ADR-042) | `POST/GET … /admin/orders/{id}/refunds`, `…/chargebacks`; `GET /admin/refunds`, `GET /admin/refunds/{id}`; `POST …/settle`, `…/fail`, `…/reissue`, `…/void`; `GET /admin/chargebacks/{id}` |
| **Cash payment blocks** | VS-028 (ADR-038) | `GET /admin/cash-blocks`; `POST /admin/cash-blocks/search`; `POST /admin/cash-blocks/{id}/clear` |
| **Contact form + admin queue** | VS-033 | `POST /contact-messages` (captcha); `GET /admin/contact-messages`; `GET/PATCH /admin/contact-messages/{id}` |
| **Bring Your Idea** | VS-034, VS-035 (ADR-030, ADR-031) | `POST /custom-requests` (multipart, captcha, ≤5 files ≤10 MB); `GET /admin/custom-requests`; `GET/PATCH …/{id}`; `POST …/{id}/transition`; `GET …/attachments/{attachment_id}/download`; `GET /admin/analytics/custom-requests/funnel` |
| **Offers** | VS-039, VS-040, VS-041 (ADR-034, ADR-035, ADR-037) | `POST /offers`; `GET /me/offers`, `GET /me/offers/{id}`; `POST /me/offers/{id}/accept`, `…/counter`, `…/withdraw`, `…/checkout`; `GET /admin/offers`, `GET /admin/offers/{id}`; `POST /admin/offers/{id}/accept`, `…/counter`, `…/reject` |
| **Wishlist** | VS-038 | `GET /me/wishlist`; `PUT/DELETE /me/wishlist/{product_id}`; `GET /admin/analytics/wishlist` |

**New enums now defined by the backend** (the frontend previously had to treat these as provisional):

- `OrderStatus` = pending_payment, cancelled, refunded, partially_refunded, completed, in_progress
- `OrderItemStatus` = pending, awaiting_delivery, in_production, ready_to_ship, shipped, delivered, returned, ready_for_pickup, picked_up, cancelled, refunded
- `PaymentStatus` = pending, processing, paid, partially_refunded, refunded, failed, expired
- `PaymentMethod` = online, cash · `PaymentProvider` = **mock, cash** · `FulfillmentMethod` = delivery, pickup · `OrderSource` = cart, offer
- `Governorate` = akkar, baalbek_hermel, beirut, beqaa, keserwan_jbeil, mount_lebanon, nabatieh, north, south
- `RefundKind` = admin, cancellation, late_capture · `RefundStatus` = pending, settled, failed, voided · `CancelReason` = refused, no_show, other
- `OfferStatus` (9 values), `OfferAction` (9), `OfferActor`, `OfferTurn`
- `ContactMessageStatus` = new, read, replied, archived · `CustomRequestStatus` (7) · `CustomRequestOutcome` = won, lost
- `PurchaseRefusal` = not_listed, unavailable, whatsapp_only

**Questions the old handoff listed as open, now answered by built contract:**

- **Q1 / C8 / P1-11, admin legal next actions:** **built.** `AvailableActionRead {target_status, cancel_reasons[]}` on the admin order detail (ADR-025).
- **C11 / Q2, "do I own this STL":** the old handoff said "not built and not planned". It is now **built** as `GET /me/stl-ownership`.
- **Q10, deleting the default address:** decided. The `DELETE` summary says "deleting the default leaves no default" (soft delete).
- **Q7, captcha vendor:** decided and **built**. Cloudflare Turnstile on register, resend, reset-request, contact and BYI.
- **C12, idempotency:** `Idempotency-Key` is a **required header** on `POST /checkout` and `POST /me/orders/{id}/payments`.
- **Checkout consents:** these are now wire fields: `accept_terms` (required), `accept_digital_final_sale?`, `accept_cash_terms?`, `accepted_price_changes?[]`. The **legal copy** (Q8) is still not a backend artifact.

## 6. Routes and capabilities still not built

From `docs/vertical-slice-plan.md` ("Not started") and confirmed absent from B and C:

| Capability | Slice | Evidence |
|---|---|---|
| Reviews, Verified Purchase badge | VS-036 | no review path in OpenAPI; runtime `GET /products/x/reviews` → 404 |
| Review moderation | VS-037 | no path |
| Business analytics dashboard (beyond the wishlist and BYI funnel endpoints) | VS-043 | only `/admin/analytics/wishlist` and `/admin/analytics/custom-requests/funnel` exist |
| Customer data export | VS-044 | no path |
| Account deletion / anonymisation | VS-045 | no path |
| **Live online payment provider** | **VS-032** | `PaymentProvider` enum = `mock`, `cash` only; `.env.example` `PAYMENT_PROVIDER=mock`; Whish vars present but empty. **Online checkout runs against the mock provider only** |
| Staging deploy, production email, backups, launch | VS-020, VS-021, VS-047, VS-048 | ops slices |
| `/media` served by the backend | VS-020 | unchanged from the old handoff (B4 workaround still needed locally) |

The payment **return URL / polling contract** (old Q3) is still not a dedicated route. `CheckoutPaymentRead` carries `redirect_url` (nullable) and `status: string`, and the customer reads payment state from `GET /me/orders/{id}` (`payment`, `payment_due`, `can_retry_payment`, `hold_expires_at`). There is no `GET /payments/{id}` customer route. The real provider's return parameters stay undefined until VS-032.

## 7. Removed concepts still removed

| Concept | ADR | Current evidence |
|---|---|---|
| STL asset versions, entitlements, library, downloads, download stats | ADR-019 | VS-017/018/019/042 "Removed"; no such paths in C; runtime `GET /me/downloads` → 404; `daily_download_cap` setting deleted (VS-023b) |
| Shipping zones, shipping cost, free-shipping threshold | ADR-024 | VS-027 "Removed"; no zone path in C; `free_shipping_threshold` now **also gone from `PublicSettingsRead`** (D3) and the settings table |

`GET /admin/shipping-zones` answers `401` unauthenticated. That comes from the admin boundary rejecting any `/admin/*` request without a session (SEC-10), not from a live route. The path is absent from OpenAPI.

**Still-legacy value:** `NotificationType` still contains `download` (database-design 12.3's original six), even though downloads are removed. It is a category label only, so do not build download UI from it.

## 8. Frontend code potentially affected (read-only inventory; nothing changed)

### Breaks against the real backend today (mounted routes)

| File | Problem | Drift |
|---|---|---|
| `src/lib/auth/useRegister.ts` (mounted `/register`) | request body has no `captcha_token` → every real registration is `422` | D4, D7 |
| `src/lib/auth/useResendVerification.ts` (mounted `/verify-email/resend`) | same | D5, D7 |
| `src/lib/auth/usePasswordResetRequest.ts` (mounted `/forgot-password`) | same | D6, D7 |
| `src/lib/settings/publicSettingsModel.ts` (+ `publicSettingsKeys.ts`, `usePublicSettings`) | `PublicSettingsRead` type declares `free_shipping_threshold` (removed) and lacks `cash_payment_enabled` / `cash_max_order_total`. Reading still works, but the type is wrong and its tests assert the old shape | D1–D3 |

### Type or test drift, not user-visible yet

- `src/lib/notifications/notificationTypes.ts`: union lacks `custom_request`. `notificationAdapter.ts` already falls back to a generic label (`UNKNOWN_TYPE_LABEL`), so it does not crash. (D8)
- `src/lib/admin/settings/settingsAdapter.ts` `OBSOLETE_KEYS` (`daily_download_cap`, `free_shipping_threshold`): both keys are now deleted on the backend, so the filter is dead but harmless. The new cash keys render through the generic path.
- Tests and mocks asserting the old settings shape: `publicSettingsModel.test.ts`, `usePublicSettings.test.ts`, `settingsAdapter.test.ts`, `ProductDetailView.test.tsx`, `GlobalWhatsAppButton.test.tsx`, `e2e/product-detail.spec.ts`.
- `src/lib/api/validationErrors.test.ts`, `src/components/forms/guestSubmissionFeedback.ts`: these already model a captcha error kind, so check that it maps `400 CAPTCHA_INVALID` and `503` with `Retry-After`.

### Unmounted components whose real contract now exists and differs from their models

- `src/lib/addresses/addressModel.ts`: deliberately carries only `{id, displayLines, isDefault}`, with comments saying no field is confirmed and "no governorate". The real `AddressRead` is `label, recipient_name, phone, governorate (enum), city, area?, street?, landmark_notes, is_default`, and the test asserts `governorate` is absent. Comments referencing zone selection are obsolete. **Resolved in Phase 5B (`05b0fb3`):** the model is now the real AddressRead; see REAL-BACKEND-ACCEPTANCE.md.
- `src/lib/payment/paymentStatusModel.ts`: `PaymentStatus` lacks `partially_refunded`, `refunded`. `paymentReturnIdentifier.ts` / `usePaymentStatusPoller.ts` assume a return/poll contract that does not exist as a route (see §6).
- `src/lib/cart/*`, `src/components/cart/*`: compare with `CartRead` / `CartLineRead` (`snapshot_price`, `current_price`, `price_changed`, `over_cap`, `purchasable`, `unpurchasable_reason`). **Resolved in Phase 5C (`0bbb859`):** the cart layer is now the real contract; see REAL-BACKEND-ACCEPTANCE.md.
- `src/lib/checkout/*`, `src/components/checkout/*`: compare with `CheckoutRequest` (payment_method, fulfillment_method, address_id, contact_phone, consents, accepted_price_changes) and `CheckoutRead.dropped_lines`.
- `src/lib/orders/*`, `src/components/account/Order*`, `StatusTimeline`, `CancellableOrderLine`, `CancelOrderLineButton`: real `OrderDetailRead` has `can_cancel`, `can_retry_payment`, `status_history`, `refunds`. Customer cancel is order-level (`POST /me/orders/{id}/cancel`), not per line.
- `src/components/admin/AdminOrderDetail`, `AdminOrderLine`, `TransitionActions`, `AdminCancelDialog`, `InternalNoteEditor`, `AdminPaymentList`, `PaymentDetail`, `ManualConfirmDialog`, `RefundCreateForm`, `RefundDetail`, `RefundQueue`, `SettleRefundDialog`, `MessageDetail`: all have real admin schemas now.
- `src/components/contact/ContactForm.tsx`, `src/components/byi/*`: real endpoints with captcha. The `captchaSlot` seam is where Turnstile goes.

## 9. Previous FVS classifications that change

Old class from `FRONTEND-BACKEND-RECONCILIATION.md` §2. New class follows the same legend (A ready · B partial · C backend not built · D retired · E product decision).

| Slice | Old | **New** | Reason (evidence) |
|---|---|---|---|
| FVS-002 Registration & verification | A | **B: frontend now broken** | captcha required (D4, D5, D7); runtime 422 without it |
| FVS-004 Password reset | A | **B: frontend now broken** | captcha required on request step (D6, D7) |
| FVS-007 Admin settings | A | A (note) | new cash keys; obsolete keys deleted server-side |
| FVS-008 Notifications | A | A (note) | enum + `custom_request` (D8) |
| FVS-014 Product detail | B | **A** | cart built; ownership signal now built (`GET /me/stl-ownership`), so the "never planned" premise is void; offers built |
| FVS-015 Bring Your Idea | C | **A** | VS-034 Done; `POST /custom-requests` |
| FVS-016 Contact form | C | **A** | VS-033 Done |
| FVS-017 Admin contact queue | C | **A** | VS-033 Done |
| FVS-022 Home/About/WhatsApp | A | A (note) | `free_shipping_threshold` now absent rather than null |
| FVS-023 Address book | C | **A** | VS-026 Done. **Integrated and accepted against the real backend in Phase 5B** (`05b0fb3`, `7acb321`) |
| FVS-025 Cart | C | **A** | VS-022 Done. **Integrated and accepted against the real backend in Phase 5C** (`0bbb859`–`472000c`) |
| FVS-026 Checkout | C | **B** | VS-023/028 Done. Legal consent copy (Q8) still open; online leg is mock-provider only |
| FVS-027 Payment result | E | **B** | checkout returns `redirect_url`; state via order detail. Real provider return contract waits on VS-032 |
| FVS-028 Admin payments | C | **A** | VS-024 Done |
| FVS-029 Order history | C | **A** | VS-025 Done |
| FVS-030 Admin fulfilment | E | **A** | Q1 decided (ADR-025), `AvailableActionRead` built, VS-029 Done |
| FVS-031 Cancellation & returns | C | **A** | VS-031 Done |
| FVS-032 Admin refunds | C | **A** | VS-030 Done (refunds, voids, chargebacks) |
| FVS-018/019/020/021/024 | D | D (unchanged) | ADR-019/024 still in force |
| FVS-001/003/005/006/009/010/011/012/013 | A | A (unchanged) | no contract change |

**Beyond FVS-032 (not in the old reconciliation's scope), backend status now:**

- **Built:** FVS-033 to FVS-036 (offers, VS-039/040/041), FVS-039 (wishlist, VS-038), FVS-040 (BYI pipeline and funnel, VS-035), FVS-042 (audit log viewer, VS-012, which was already built in A).
- **Not built:** FVS-037/038 (reviews, VS-036/037), FVS-041 (analytics, VS-043; only partial endpoints), FVS-043 (export, VS-044), FVS-044 (deletion, VS-045).

**Old count (32 slices):** A 14 · B 1 · C 10 · D 5 · E 2.
**New count (same 32):** **A 23 · B 4 (FVS-002, 004, 026, 027) · C 0 · D 5 · E 0.**

## 10. Recommended next integration batch

**Batch 0: contract refresh and auth repair (do first, small, unblocks acceptance):**

1. Replace `docs/backend-handoff/openapi.json` and `BACKEND-RESPONSE.md` with the backend's current copies (B), and mark `FRONTEND-BACKEND-RECONCILIATION.md` as superseded by this audit where they conflict.
2. Fix the **three broken mounted flows**: add a Cloudflare Turnstile widget and `captcha_token` to register, resend verification, and password-reset request. Map `400 CAPTCHA_INVALID` (reset widget, retry) and `503` + `Retry-After`. Use the test site key `1x00000000000000000000AA` locally against `CAPTCHA_PROVIDER=fake`.
3. Correct the `PublicSettingsRead` type (drop `free_shipping_threshold`, add `cash_payment_enabled`, `cash_max_order_total`) and its fixtures; add `custom_request` to `NotificationType`.
4. Then run the pending **real-backend acceptance** (Steps 2–9 of `REAL-BACKEND-ACCEPTANCE.md`) for the already-mounted batches 1 to 3.

**Batch 1 (next feature batch): customer commerce path,** where the backend is fully built and the frontend components exist unmounted. In order: FVS-023 (address book, rework `addressModel` to the real fields) → FVS-025 (cart) → FVS-026 (checkout: physical/digital/cash, `Idempotency-Key`, public cash settings gating, mock online provider; consent copy marked pending legal) → FVS-029 (order history/detail) → FVS-027 (payment result from order detail; no fabricated return contract) → FVS-031 (customer cancel / confirm receipt / report problem).

After that: admin operations (FVS-030, 028, 032), then guest forms (FVS-016, 015) and their admin queues (FVS-017, 040), then offers and wishlist (FVS-033 to 036, 039).

---

## Verification

- **No frontend source changed:** this audit adds one file, `docs/backend-handoff/CURRENT-BACKEND-DRIFT-AUDIT.md`. `git status` before the commit showed only that file.
- **Every drift is backed by evidence:** D1–D8 come from schema-level comparison of A against C (and B = C). D1–D4 and D6 were also confirmed by runtime probes. New routes come from the operation-set difference and match "Done" rows in the backend `vertical-slice-plan.md`.
- **No provisional feature is called built:** the live payment provider (VS-032), reviews, analytics, export and deletion are listed as not built, with evidence. Online checkout is described as **mock-provider only**.
- **Probes were non-destructive:** unauthenticated `GET`s, plus two `POST`s that the server rejected at validation (`422`) before any side effect.

---

## Follow-up (Phase 5A, 2026-11-09)

- `openapi.json` in this folder was **replaced** with the backend repo's snapshot at `2dfb27b`, after a sorted-key deep comparison showed it equal to the running `/openapi.json`. Old snapshot commit: `d1c1cf1`. Current tested backend commit: `2dfb27b`. The current OpenAPI supersedes the old contract assumptions.
- D1–D8 are fixed in the frontend (captcha on the three auth flows, `PublicSettingsRead`, `NotificationType`). Results are in `REAL-BACKEND-ACCEPTANCE.md`.
