# Backend Feature Requests and Integration Gaps

> **DRAFT.** Not final until frontend editing and the final verification run are complete.

Date 2026-11-26. IDs follow [API-CONTRACT-AUDIT.md](API-CONTRACT-AUDIT.md).

**No required endpoint is missing.** Every operation the frontend needs exists. This file holds
the two contract changes the frontend needs, the frontend integration work for features the
backend has already built, and the optional ideas. In each table, "Existing" names an endpoint
that exists today, and "Proposed" is a suggestion only.

## Contract changes

### CC-01

| Field | Value |
|---|---|
| Title | Price filter and price sort ignore promotions |
| Classification | BACKEND CONTRACT CHANGE REQUIRED |
| Priority | P2 |
| Affected page | Shop (`/shop`): price range filter, "price" sort |
| Existing | `GET /api/v1/products?price_min_cents=&price_max_cents=&sort=` (public) |
| Current contract | Filters and sort compare `products.price_cents`, the **list** price (`storefront_query.py:115`). Each item's `price` is the **effective** price, and the `promotion_id` parameter description says "Price filters and the price sort use the list price." |
| Expected | A product on sale for $20 (list $25) matches "max $20" and sorts as $20 |
| Actual | It is excluded from "max $20" and sorts as $25 |
| Reproduction | Active 20 % promotion on a $25 product → `GET /products?price_max_cents=2000` does not list it, although its `price` would be 2000 |
| Proposed | Filter and sort on the effective price, computed in SQL from the active promotions (the same rule as `apply_best`), keeping the cursor stable |
| Auth / CSRF | none (public GET) |
| Validation | unchanged |
| Migration | no (query change). A denormalised column is possible but not needed at this catalogue size |
| Backward compatibility | Same parameters, different matching; document it in `docs/storefront-catalogue.md` and `docs/promotions.md` |
| Acceptance | Integration tests: a discounted product matches by its effective price and sorts by it; with no promotions, results are unchanged |
| Responsible | Backend |

### CC-02

| Field | Value |
|---|---|
| Title | Wishlist shows the list price during a promotion |
| Classification | BACKEND CONTRACT CHANGE REQUIRED |
| Priority | P3 |
| Affected page | Account → Wishlist |
| Existing | `GET /api/v1/me/wishlist` → `WishlistItemRead {product_id, created_at, available, name, slug, price_cents, currency, type}` |
| Actual | `price_cents = product.attributes.price_cents` (list price, `engagement/api/schemas.py:92`) |
| Proposed (additive) | `price_cents` becomes the effective price, plus `list_price_cents` and an optional `promotion` (the same `ProductPromotionRead` as product reads) |
| Auth / CSRF | customer session; GET needs no CSRF |
| Migration | no |
| Backward compatibility | Additive fields. `price_cents` changes meaning (list → effective), matching what product reads already do |
| Acceptance | During an active promotion, the wishlist price equals the product's `price`; the frontend shows the struck list price |
| Responsible | Backend, then frontend |

## Frontend integration required (backend built)

### FE-01

| Field | Value |
|---|---|
| Title | Manual payment provider: the customer sees the wrong outcome after checkout |
| Classification | FRONTEND INTEGRATION REQUIRED |
| Priority | **P1**: `manual` is production's V1 online provider (ADR-049, `.env.example`) |
| Affected pages | Checkout confirmation; offer checkout panel |
| Existing | `POST /api/v1/checkout` and `POST /api/v1/me/offers/{id}/checkout` → `payment: CheckoutPaymentRead {id, status, provider, redirect_url, next_step, hold_expires_at}`, `next_step ∈ {redirect, await_admin_contact}` |
| Actual (frontend) | `checkoutModel.ts:129` decides only on `redirect_url`. With `manual` the redirect is null, so the "online-no-redirect" state shows "The payment page isn't available right now, so nothing has been charged. Please contact us…" (`CheckoutConfirmation.tsx:179`, `OfferCheckoutPanel.tsx:162`) |
| Expected | For `await_admin_contact`: "Order placed. We'll contact you to arrange payment before {hold_expires_at}", plus the order link. Keep the current copy only for a real failure |
| Backend change | none |
| Acceptance | A unit test for each `next_step`; a real-backend run with `PAYMENT_PROVIDER=manual` |
| Responsible | Frontend |

### FE-02 – FE-08: frontend integration of built backend features

| ID | Priority | Feature (backend slice, status) | Existing operations | Frontend page to build |
|---|---|---|---|---|
| FE-02 | P1 | Reviews + Verified Purchase badge (VS-036, Done) | `GET /products/{slug}/reviews`, `POST /reviews`, `PATCH/DELETE /reviews/{id}`, `GET /me/reviews` | Product detail reviews section; write or edit after delivery; Account → My reviews |
| FE-03 | P1 | Review moderation (VS-037, Done) | `GET /admin/reviews`, `GET /admin/reviews/{id}`, `POST /admin/reviews/{id}/hide`, `POST .../restore` | Admin → Reviews |
| FE-04 | P1 | Account deletion by anonymisation (VS-045, Done) | `DELETE /me` (body `AccountDeletionRequest`, CSRF) | Account → Delete account (confirmation, then sign-out) |
| FE-05 | P2 | Customer data export (VS-044, Done) | `GET /me/export` | Account → Download my data |
| FE-06 | P2 | Business analytics (VS-043, Done) | `GET /admin/analytics/{overview,revenue,customers,recent-purchases,stl-sales,top-rated-products,wishlist}` | An admin dashboard (`/admin` currently redirects to Settings) |
| FE-07 | P3 | STL ownership | `GET /me/stl-ownership` | Account → My STL files (ownership list; no downloads, ADR-019) |
| FE-08 | P3 | Audit logs | `GET /admin/audit-logs`, `GET /admin/audit-logs/{id}` | Admin → Audit log (read-only) |

These need no backend change. Field lists are in `openapi.json`. Every write needs CSRF and
every admin route needs MFA, as elsewhere.

## Optional features

| ID | Priority | Idea | Notes | Migration |
|---|---|---|---|---|
| OPT-01 | P3 | Promotions list pagination and search | `GET /admin/promotions` returns the newest 200; a handful of campaigns a year makes this a future concern | no |
| OPT-02 | P3 | Category-scoped promotions | New scope `category` plus `category_ids`; same no-stacking rule | yes (`promotion_scope` enum value, link table) |
| OPT-03 | P3 | Record the applied promotion on order lines | Lets reports attribute discounts; the charged price is already snapshotted | yes (nullable `promotion_id` on `order_items`) |
| OPT-04 | P3 | Admin-initiated offers | Offers are customer-submitted by design (`docs/offers.md`); the admin can already counter. Needs a product decision before any design | yes |
| OPT-05 | P3 | Customer payment-status route and return-URL contract | Only relevant to a redirecting live provider (VS-032, deferred by ADR-049); customers read status from `GET /me/orders/{id}` | no |
