# Minimum Manual-Test Unlock Path

**Question answered:** what is the smallest backend package we need first to start seeing and manually testing a real Bekaa3D website? Four levels, each building on the last. Full detail for every item named here is in `BACKEND-UNLOCK-HANDOFF.md`.

---

## LEVEL 1 — Real Public Storefront

Someone can open a browser, see real products, and click into a real product page — no login required.

**Backend contracts required:**
- Public settings response shape (B1)
- Catalogue public list contract — `GET /products` + facet/pagination shape (B2)
- Product detail response contract (B3)
- Image/asset URL format (B4)

**Runtime prerequisites:**
- Local backend running (A2), frontend `.env.local` pointed at it.

**Fixtures required:**
- A small seeded catalogue: a few products spanning physical/STL, each category/material/colour combination touched at least once.

**Frontend slices unlocked:** FVS-013 (shop), FVS-014 (product detail), FVS-022 (home/about — currently deliberately left as a placeholder hero with no working CTA, since `/shop` doesn't exist yet).

**What can then be manually tested:** browsing, filtering, searching, sorting the catalogue; opening a product and seeing its real price/images/availability; the floating WhatsApp button with a real number.

---

## LEVEL 2 — Real Customer Account

Someone can register, verify their email, log in, and see their own profile — against a real backend, for the first time in this engagement.

**Backend contracts required:** **none new.** Registration, verification, resend, login (incl. MFA handoff), refresh, logout, and `/me` are all already confirmed and fully built on the frontend. This level is pure runtime enablement.

**Runtime prerequisites:**
- Level 1's runtime, plus a working way to retrieve the verification email (A3) — the planned file-based dev email adapter, or the manual `email_outbox` SQL-read workaround.

**Fixtures required:**
- None beyond the email-delivery mechanism above — a real account is created live through the real register→verify→login flow.

**Frontend slices unlocked:** FVS-002, FVS-003, FVS-006 — all route-complete already; this is their first real-backend run. FVS-004 (password reset) stays gated separately (P2-6 — field shapes unconfirmed).

**What can then be manually tested:** the full register → check-email → verify → login → `/account/profile` loop with real cookies, real CSRF, real session refresh, cross-tab logout.

---

## LEVEL 3 — Real Purchase Flow

A logged-in customer can save an address, build a mixed cart, check out, see verified payment status, and find the resulting order in their history.

**Backend contracts required (strict order, each depends on the previous slice's data):**
1. Addresses (C3)
2. Shipping zones — public read (C4)
3. Cart (C5)
4. Checkout, incl. Idempotency-Key mechanism (C6, C12)
5. Payment verification (C7)
6. Order status enum (C8, display-only at this level)
7. Validation-error shape (C1) and cursor pagination (C2) — needed throughout, not slice-specific

**Runtime prerequisites:** Level 2's runtime + account.

**Fixtures required:**
- A seeded shipping zone.
- A mixed cart scenario (one physical + one STL line) — this is the backend plan's own *mandatory* acceptance scenario, not an extra ask.
- A way to trigger each mock-payment outcome (paid/failed/expired/pending).

**Frontend slices unlocked:** FVS-023 (addresses), FVS-024 (public half), FVS-025 (cart), FVS-026 (checkout), FVS-027 (payment verification), FVS-029 (customer order history).

**What can then be manually tested:** the complete commerce loop — save an address → add physical + STL items to cart → pick a shipping zone → check out → watch real (not redirect-assumed) payment verification → see the order appear in history with the correct line items and purchase-time snapshot. Also: STL entitlement/library (C9) and download (C10) **if** those two contracts are additionally answered — they're not strictly part of the checkout chain but complete the "what did I just buy" loop for a digital product.

---

## LEVEL 4 — Real Admin Operations

An admin can log in with MFA and actually run the business: manage the catalogue, fulfill and refund orders.

**Backend contracts required:**
1. **Admin authorization source (P1-1)** — the one decision that unblocks every admin route; nothing else in this level can be mounted without it.
2. Admin MFA contract (P1-2)
3. Then, in whatever order is convenient once P1-1 lands: admin settings (P1-3), admin customers (P1-4), reference data (P1-5), product CRUD (P1-6), product image upload (P1-7), STL asset upload (P1-8), entitlement grant (P1-9), admin payments (P1-10), admin order fulfillment (P1-11), cancellation/returns (P1-12), refunds (P1-13).

**Runtime prerequisites:** Level 3's runtime + a disposable admin account with MFA already enrolled (A3).

**Fixtures required:**
- Seeded customers, products, and — once Level 3 is running — real orders/payments/refunds to manage. Until the admin mutation endpoints land, order-state fixtures for fulfillment testing need direct DB seeding.

**Frontend slices unlocked:** FVS-005, 007, 009, 010, 011, 012, 017, 018, 019, 024 (admin half), 028, 030, 031, 032 — effectively every remaining slice in FM-A/B/C.

**What can then be manually tested:** admin login with MFA; editing business settings; managing customers, categories/materials/colours, products, product images, STL asset versions; granting entitlements by hand; reconciling/manually confirming payments; running a physical order through production to delivery; cancelling a line before production starts; refunding a mixed order's physical failure while leaving its digital line untouched (the backend's own mandatory refund acceptance scenario).

---

## Summary table

| Level | New backend contracts needed | New fixtures needed | Unlocks |
|---|---|---|---|
| 1 — Storefront | 4 | 1 (catalogue seed) | FVS-013, 014, 022 |
| 2 — Account | 0 | 1 (email delivery) | FVS-002, 003, 006 |
| 3 — Purchase | 7 | 3 (zone, mixed cart, payment triggers) | FVS-023–027, 029 |
| 4 — Admin | 13 (12 after P1-1) | ongoing seed data | FVS-005, 007, 009–012, 017–019, 024, 028, 030–032 |
