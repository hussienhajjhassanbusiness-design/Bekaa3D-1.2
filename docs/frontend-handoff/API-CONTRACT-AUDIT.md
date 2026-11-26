# API Contract Audit: frontend requirements against the live backend

> **DRAFT.** Not final until frontend editing and the final verification run are complete
> (see [FINAL-ACCEPTANCE-CHECKLIST.md](FINAL-ACCEPTANCE-CHECKLIST.md)).

| | |
|---|---|
| Date | 2026-11-26 |
| Backend | `C:\My projects\Bekaa3D-backend`, branch `feat/homepage-hero-image` at `76f43f6` (on top of `feat/promotions` `ab34ff4`, on top of `main`/`origin/main` `7e52174`) |
| Frontend | `C:\My projects\bekaa3D`, branch `master` at `54cda03` (no git remote configured) |
| Contract source | the **running** backend's `GET http://localhost:8000/openapi.json`, compared with `docs/frontend-handoff/openapi.json`: identical, **153 operations** |
| Method | every `/api/v1/...` path the frontend source references (72 distinct path templates) matched against the live operations, then each feature area checked by hand in both codebases |

## 1. Classification key

| Classification | Meaning here |
|---|---|
| CONFIRMED BACKEND BUG | Backend behaviour contradicts the backend's own rules or contract; evidence from source or runtime |
| MISSING BACKEND ENDPOINT | The frontend needs an operation that does not exist |
| BACKEND CONTRACT CHANGE REQUIRED | The operation exists, but its shape or semantics do not meet a frontend need |
| FRONTEND INTEGRATION REQUIRED | The backend is built; the frontend does not use it yet |
| CONFIGURATION REQUIRED | Environment, deployment or operations work, not code contract |
| ALREADY IMPLEMENTED | Built and integrated on both sides |
| OPTIONAL FEATURE | Not required by any current document; a possible improvement |
| INTENTIONALLY UNSUPPORTED | Excluded by an ADR or an explicit product decision |
| NEEDS VERIFICATION | Open question or unverified behaviour; needs a decision or a run |

## 2. Endpoint coverage summary

- **Frontend paths missing from the live contract: 0.** The four apparent misses in the automatic
  scan are template artefacts: `/api/v1/admin/payments${query}`, `/api/v1/admin/refunds${query}`,
  `/api/v1/admin/${resource}` (reference data) and `/api/v1/me/orders/${id}/${action}` all resolve
  to existing operations.
- **Live operations with no frontend caller, by area.** These are checked by feature, not only by
  literal string:

| Area | Operations | Frontend status | Finding |
|---|---|---|---|
| Reviews (customer) | `GET /products/{slug}/reviews`, `POST /reviews`, `PATCH/DELETE /reviews/{id}`, `GET /me/reviews` | no UI; only `average_rating` and `review_count` are shown | FE-02 |
| Review moderation | `GET /admin/reviews`, `GET /admin/reviews/{id}`, `POST .../hide`, `POST .../restore` | no UI | FE-03 |
| Account deletion | `DELETE /me` (body `AccountDeletionRequest`) | no UI | FE-04 |
| Data export | `GET /me/export` | no UI | FE-05 |
| Business analytics | `GET /admin/analytics/{overview,revenue,customers,recent-purchases,stl-sales,top-rated-products,wishlist}` | no UI (`/admin` redirects to settings; only the BYI funnel is used) | FE-06 |
| STL ownership | `GET /me/stl-ownership` | no UI | FE-07 |
| Audit logs | `GET /admin/audit-logs`, `GET /admin/audit-logs/{id}` | no UI | FE-08 |
| Webhooks, health | `POST /webhooks/payments/{provider}`, `/health/*` | server-to-server; the frontend uses `/api/health/ready` via its proxy | n/a |

Everything else (catalogue, cart, checkout, orders, offers, payments, refunds, chargebacks, cash
blocks, contact, BYI, wishlist, notifications, settings, promotions, hero image, reference data,
products and images, customers, MFA, auth) is called by the frontend.

## 3. Findings register

IDs are stable; detail lives in the linked file.

| ID | Area | Classification | Priority | Summary | Detail |
|---|---|---|---|---|---|
| BUG-01 | Promotions / checkout | CONFIRMED BACKEND BUG | P2 | A promotion can set an effective price of $0 (100 % or fixed ≥ price), and checkout refuses a zero total (`PAYMENT_METHOD_NOT_ALLOWED`, `reason: zero_total`). The covered products become unbuyable, with no warning to the admin. | [BACKEND-BUG-REGISTER.md](BACKEND-BUG-REGISTER.md#bug-01) |
| CC-01 | Promotions / catalogue | BACKEND CONTRACT CHANGE REQUIRED | P2 | `price_min_cents`, `price_max_cents` and price sorting use the **list** price, while the list shows the **effective** price | [BACKEND-FEATURE-REQUESTS.md](BACKEND-FEATURE-REQUESTS.md#cc-01) |
| CC-02 | Promotions / wishlist | BACKEND CONTRACT CHANGE REQUIRED | P3 | `WishlistItemRead.price_cents` is the list price; the product page shows the promotional price | [BACKEND-FEATURE-REQUESTS.md](BACKEND-FEATURE-REQUESTS.md#cc-02) |
| FE-01 | Checkout, offer checkout | FRONTEND INTEGRATION REQUIRED | **P1** | With the V1 `manual` provider, checkout returns `next_step: "await_admin_contact"` and `redirect_url: null`. The frontend ignores `next_step` and shows "The payment page isn't available right now… Please contact us". | [BACKEND-FEATURE-REQUESTS.md](BACKEND-FEATURE-REQUESTS.md#fe-01) |
| FE-02 | Product detail, account | FRONTEND INTEGRATION REQUIRED | P1 | Reviews (VS-036 Done) have no UI | [BACKEND-FEATURE-REQUESTS.md](BACKEND-FEATURE-REQUESTS.md#fe-02--fe-08-frontend-integration-of-built-backend-features) |
| FE-03 | Admin | FRONTEND INTEGRATION REQUIRED | P1 | Review moderation (VS-037 Done) has no UI | same |
| FE-04 | Account | FRONTEND INTEGRATION REQUIRED | P1 | Account deletion (VS-045 Done) has no UI | same |
| FE-05 | Account | FRONTEND INTEGRATION REQUIRED | P2 | Data export (VS-044 Done) has no UI | same |
| FE-06 | Admin | FRONTEND INTEGRATION REQUIRED | P2 | Business analytics (VS-043 Done) has no dashboard | same |
| FE-07 | Account | FRONTEND INTEGRATION REQUIRED | P3 | STL ownership list has no UI | same |
| FE-08 | Admin | FRONTEND INTEGRATION REQUIRED | P3 | Audit log viewer has no UI | same |
| CFG-01 | Email | CONFIGURATION REQUIRED (adapter not built, VS-021) | P0 for production | Only the `console` email adapter exists, so verification and reset emails cannot be delivered in production | [DATABASE-AND-INFRASTRUCTURE.md](DATABASE-AND-INFRASTRUCTURE.md#7-production-configuration) |
| CFG-02 | Media | CONFIGURATION REQUIRED | P0 for production | Production has no web server serving `MEDIA_PUBLIC_DIR` at `/media` (nginx omitted from compose); local development is solved by the `media` service | same |
| CFG-03 | Payments | CONFIGURATION REQUIRED | P0 for production | Production must run `PAYMENT_PROVIDER=manual` (mock is refused) | same |
| CFG-04 | Captcha | CONFIGURATION REQUIRED | P0 for production | `CAPTCHA_PROVIDER=turnstile` and `TURNSTILE_SECRET`; `fake` is refused outside dev/test | same |
| CFG-05 | Secrets | CONFIGURATION REQUIRED | P0 for production | Generated `JWT_SIGNING_KEY`, `CSRF_SECRET`, `IP_HASH_SALT`, `PHONE_HASH_SALT` (≥ 32, never rotated), `MFA_SECRET_KEY`; HTTPS for `Secure` cookies | same |
| CFG-06 | Operations | CONFIGURATION REQUIRED | P1 for production | Staging and deploy (VS-020), backups and monitoring (VS-047), launch readiness (VS-048): Not started | same |
| NV-01 | Refunds | NEEDS VERIFICATION (backend decision) | P2 | A pending reissued refund cannot be voided once its line is `refunded` (`409`, `line_already_refunded`). Still in code (`payments/domain/refunds.py:381`) | [BACKEND-BUG-REGISTER.md](BACKEND-BUG-REGISTER.md#nv-01) |
| NV-02 | Worker | NEEDS VERIFICATION | P3 | The arq heartbeat refreshes on arq's default 3600 s interval, so a stalled worker shows unhealthy only after up to about 1 h. The compose comment implies "each poll". | [BACKEND-BUG-REGISTER.md](BACKEND-BUG-REGISTER.md#nv-02) |
| NV-03 | Whole backend | NEEDS VERIFICATION | **P1** | Full backend suite not rerun after `4289c4a`, `778a0bd`, `76f43f6` (only targeted suites) | [FINAL-ACCEPTANCE-CHECKLIST.md](FINAL-ACCEPTANCE-CHECKLIST.md) |
| NV-04 | Worker | NEEDS VERIFICATION | P3 | The previous worker container counted `j_failed=13` over 31 h; its logs are gone (container recreated) | [BACKEND-BUG-REGISTER.md](BACKEND-BUG-REGISTER.md#nv-04) |
| OPT-01 | Promotions | OPTIONAL FEATURE | P3 | Admin promotion list is capped at 200, with no pagination or search | [BACKEND-FEATURE-REQUESTS.md](BACKEND-FEATURE-REQUESTS.md#optional-features) |
| OPT-02 | Promotions | OPTIONAL FEATURE | P3 | Category-scoped promotions | same |
| OPT-03 | Promotions / orders | OPTIONAL FEATURE | P3 | Record the applied `promotion_id` on order lines (reporting) | same |
| OPT-04 | Offers | OPTIONAL FEATURE | P3 | Admin-initiated offers (offers are customer-submitted by design, `docs/offers.md`) | same |
| OPT-05 | Payments | OPTIONAL FEATURE (deferred with VS-032) | P3 | Customer payment-status route and return-URL contract; only relevant to a redirecting provider | same |
| NEW-01 | Categories | MISSING BACKEND ENDPOINT (proposed; product decision needed) | P3 | No way to restore an archived category: V1 archiving is terminal by design. Proposed `POST /admin/categories/{id}/restore`, restoring to disabled | [BACKEND-FEATURE-REQUESTS.md](BACKEND-FEATURE-REQUESTS.md#new-01) |

## 4. Already implemented (verified this audit)

| Area | Backend | Frontend |
|---|---|---|
| Seasonal promotions | `ab34ff4`: admin CRUD (no delete), public active list, effective price on product reads, cart, checkout, order snapshot and offer ceiling | `e1fbbdd` |
| Homepage hero image | `4289c4a`: `PUT /admin/home/hero-image`, `GET /home/hero-image`, setting `homepage_hero_image` | `b1f6651`, restore default `805942d` |
| Local `/media` serving | `778a0bd`: compose `media` service on `127.0.0.1:8001` | `54cda03` (docs) |
| Worker health | `76f43f6`: `app.worker_health` probe | n/a |
| Order-number search | `GET /admin/orders?order_number=` (exact) | `adminOrdersApi.ts:31`, admin orders page |
| Product payment methods | `accepted_payment_methods` on product reads (VS-049) | used |
| Cart payment eligibility | `CartRead.payment_methods` | used |
| Admin line actions (old Q1) | `AdminOrderLineRead.available_actions` | `LineActions.tsx` |
| Manual provider (admin side) | `POST /admin/payments/{id}/confirm`, `awaiting_confirmation` filter, `available_actions` | `AdminPaymentView.tsx` |
| Notifications | `GET /me/notifications`, `PATCH /me/notifications/{id}` | used |
| Search suggestions | `GET /search/suggestions` | `searchSuggestionsApi.ts` |
| Category lifecycle (active, disabled, archived) | `GET /admin/categories?include_deleted=true`, `PATCH` (`is_active`), `DELETE` (archive) | Admin → Categories: Active / Disabled / Archived tabs with counts, archive confirmation, read-only Archived tab (2026-11-26) |

## 5. Intentionally unsupported

| Item | Source |
|---|---|
| STL file storage, entitlements, downloads | ADR-019 |
| Shipping charges, free-shipping threshold | ADR-024 |
| Live online provider (Whish) for V1 | ADR-049; VS-032 deferred, VS-050 `manual` replaces it |
| Negotiating physical products | `docs/offers.md` (`not_negotiable`) |
| Deleting a promotion (switch it off instead; the audit log keeps history) | `docs/promotions.md` |
| Promotion stacking, coupon codes, loyalty points, holiday calendar | product decision for the promotions slice |

## 6. Stale frontend documents (frontend team to update)

`bekaa3D/docs/backend-handoff/CURRENT-BACKEND-DRIFT-AUDIT.md` §6 and
`FRONTEND-BACKEND-RECONCILIATION.md` §8 still list reviews, moderation, analytics, export,
account deletion and the admin "available actions" decision (Q1) as not built. All are now
built. This audit supersedes those rows.
