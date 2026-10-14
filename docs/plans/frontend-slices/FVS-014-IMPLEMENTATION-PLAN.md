# FVS-014 — Public Product Detail Page — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: Medium.

**Goal:** A visitor eventually views full product detail — gallery, price, type-specific panels, WhatsApp CTA, and the correct next action. This batch builds every genuinely contract-independent presentational primitive and correctly defers `ProductDetailView` composition, the real `/shop/:slug` route, and SEO — the product-detail field matrix is still unconfirmed.

**Architecture:** `PriceDisplay`/`ProductTypeBadge`/`UnavailableNotice` are small, stateless presentational primitives. `ProductImageGallery` is a new public-only main+thumbnail viewer, deliberately separate from FVS-012's admin `ImageGallery` (see §5/T03). `src/lib/catalog/whatsapp.ts` isolates phone/message handling behind pure helpers; `WhatsAppChatButton` is the presentational wrapper. `AddToCartButton` resolves the source's own cart-dependency wording by treating it as two viewer states, not a contradiction (see §0).

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-013/VS-007 entries and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-014 entry, §13 (SEO).

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-013, VS-007), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-014, §13 SEO, existing §17 gaps), `FVS-013/012/011/007/003-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/components/catalog/`, `src/components/admin/ImageGallery.tsx`, `src/components/forms/MoneyInput.tsx`, `src/components/feedback/`, `src/lib/catalog/`, `src/lib/auth/returnTo.ts`, `src/app/not-found.tsx`, `src/app/shop/` (does not exist), `next.config.ts`. Searched for `ProductDetail`/`PriceDisplay`/`ProductTypeBadge`/`WhatsApp`/`wa.me`/`availability`/`purchase mode`/`license`/`owned`/`library`/`canonical`/`open graph`/`structured data`/`JSON-LD`/`generateMetadata` and any OpenAPI source — **none exists beyond what this batch itself adds.**

**Cart-dependency discrepancy — audited and resolved, not silently decided:** `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` line 402 says both "ships the button disabled/hidden if cart doesn't exist yet" **and** "for an anonymous visitor the button is always enabled and... redirects to `/login?returnTo=...`". Read literally as one state, these conflict. Read as **two different viewer states**, they don't: the anonymous→login-redirect path is a pure auth-gate — it never touches cart logic at all, so it is not actually gated by FVS-025's existence. The "disabled/hidden" qualifier applies specifically to the **authenticated** "actually add to cart" path, which genuinely cannot do anything useful before FVS-025 lands. **Result: FVS-014 is expected to expose an auth-gated intent CTA before FVS-025** — built this batch (`AddToCartButton`) — while the authenticated add-to-cart behavior stays hidden (not merely disabled, since there's no user-facing reason to give) until FVS-025. This reuses FVS-003's existing `buildLoginRedirectPath` rather than duplicating redirect-safety logic.

**Confirmed by repository evidence:**
- A slug for a hidden/deleted/archived-category product returns a real backend 404 (FVS-014's own API-integration line, matching VS-013's exclusion rule) — rendered as the app's genuine not-found page, never a soft "unavailable" banner. This is a different state from "unavailable-but-still-listed," which shows `UnavailableNotice` instead of a purchase action.
- "WhatsApp number" is a named seeded public setting (VS-007's own Logic line) exposed via `GET /settings/public` — **no exact key name or number format is given anywhere.**
- Money uses integer cents globally (`docs/plans/backend/vertical-slice-plan.md` line 756); currency itself remains unconfirmed (§2's own open USD-settlement item) — `PriceDisplay` requires an explicit `currency` prop, never hardcoding one.
- §13 (SEO) assigns per-page SEO/OG/canonical/structured-data to this slice only "what §13 specifies and product detail data supports" — since product data isn't integrated, nothing in §13 is actionable yet.

**What is genuinely unconfirmed:** the entire product-detail response schema (type discriminator, name/description, price/currency fields, category/material/colour representation, physical-only/STL-only fields, availability/purchase-mode/shipping-eligibility literals, image response fields, ownership/viewer-sensitivity); the public-settings response schema and WhatsApp key/format; canonical base URL and structured-data field mapping.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Product detail** | Endpoint path | **CONFIRMED** (literal) |
| **Product detail** | Full response schema (type, name, description, price, images, facets, type-specific fields, availability, ownership) | **NEEDS BACKEND CONFIRMATION** |
| **Product detail** | 404 for hidden/deleted/archived-category | **CONFIRMED** |
| **Money** | Integer-cents domain | **CONFIRMED**; currency itself **NEEDS CONFIRMATION** |
| **Public settings** | Endpoint path | **CONFIRMED** (literal) |
| **Public settings** | Response schema, exact WhatsApp key/format, cache guidance | **NEEDS BACKEND CONFIRMATION** |
| **WhatsApp** | Message content requirement (product name must appear) | **CONFIRMED** (Testing line); exact copy/locale **NOT backend-owned** |
| **Cart CTA** | Anonymous→login-redirect applies independent of cart existing | **RESOLVED by audit** (§0) |
| **Ownership** | Viewer-sensitivity of detail response, exact "owned" field, library destination | **NEEDS BACKEND CONFIRMATION** — no owned-STL CTA built |
| **SEO** | Title/description/canonical/OG/JSON-LD field mapping | **BLOCKED** — depends on unconfirmed product data |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | `PriceDisplay` | **CAN IMPLEMENT NOW** |
| T02 | `ProductTypeBadge` + `UnavailableNotice` | **CAN IMPLEMENT NOW** |
| T03 | Public `ProductImageGallery` | **CAN IMPLEMENT NOW** |
| T04 | WhatsApp helpers + `WhatsAppChatButton` | **CAN IMPLEMENT NOW** |
| T06 (partial) | `AddToCartButton` (anonymous path only) | **CAN IMPLEMENT NOW** |
| T05 | `ProductDetailView` composition | **CORRECTLY DEFERRED** — product field matrix unconfirmed |
| T06 (owned-STL) | Owned-STL CTA | **CORRECTLY DEFERRED** — ownership contract unconfirmed |
| T07 | Product/public-settings API integration | **BLOCKED ON BACKEND CONTRACT** |
| T08 | `/shop/:slug` + SEO | **CORRECTLY DEFERRED** — depends on T05 (deferred) and T07 (blocked) |
| T09 | Integration/accessibility review | **BLOCKED** |
| T10 | Deterministic E2E/docs | **BLOCKED** |
| T11 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01, T02, T03, T04, T06 (anonymous-only). T05/T08/owned-STL correctly deferred. T07/T09–T11 blocked.

---

## 4. Backend Questions For Tomorrow

**Product detail:** 1. Exact response schema. 2. Type discriminator field/literals. 3. Name/title field. 4. Description field/format. 5. Price cents field. 6. Currency field. 7. Category representation. 8. Material representation/multiplicity. 9. Colour representation/multiplicity. 10. Image representation. 11. Image order field. 12. Cover field. 13. Image alt field and whether it's guaranteed non-empty.

**Physical:** 14. Purchase-mode field/literals. 15. Availability field/literals. 16. Shipping-eligibility field/semantics. 17. WhatsApp-only representation. 18. Unavailable-but-listed representation.

**STL:** 19. License fields. 20. Exact ownership indicator. 21. Is the detail response viewer-sensitive? 22. Anonymous-viewer ownership behavior. 23. Exact library destination for an owner.

**404:** 24. Confirm hidden/deleted/archived-category returns 404 (already confirmed conceptually — confirm exact body/code). 25. Error body shape.

**Public settings:** 26. Exact `GET /settings/public` response. 27. Exact WhatsApp key. 28. Number format. 29. Could the number be absent/disabled? 30. Cache guidance.

**WhatsApp:** 31. Required prefilled-message format (frontend currently owns a default). 32. Should the product URL be included? 33. Any localized copy requirement?

**Cart dependency:** 34. Confirm the audit's resolution (§0) with the product/backend team before FVS-025 — currently a frontend-reasoned interpretation, not a backend confirmation.

**SEO:** 35. Exact product SEO fields. 36. Canonical base URL mechanism. 37. OG image source. 38. Structured-data field mapping.

**Testing:** 39. Seed product types/states. 40. Hidden-product 404 fixture. 41. WhatsApp-only fixture. 42. Unavailable fixture. 43. Owned-STL fixture.

---

## 5. Task Detail (Safe Batch)

### FVS014-T01 — `PriceDisplay`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/catalog/PriceDisplay.tsx` (+test).
**Design:** `amountCents: number`, `currency: string` (required, never hardcoded — `docs/plans/backend/vertical-slice-plan.md` §2's own open USD-settlement item), optional `locale`. Never parses money (that stays `MoneyInput`'s job) and never computes a new monetary amount; the single division by 100 exists only for `Intl.NumberFormat`'s major-unit API contract, which rounds correctly to the currency's minor-unit digits — proven with a dedicated "no artifact for 10 cents" test, following the exact same reasoning `MoneyInput`'s own display-direction formatter already established.
**Marker:** `#SHARED-PRICE-DISPLAY`. **Tests:** 7 (zero, cents, no-artifact, whole units, large-amount grouping, explicit non-hardcoded currency, no network).

### FVS014-T02 — `ProductTypeBadge` + `UnavailableNotice`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/catalog/ProductTypeBadge.tsx` (+test), `UnavailableNotice.tsx` (+test).
**Design:** `ProductTypeBadge` reuses the `"physical"|"stl"` UI vocabulary (not imported from FVS-011's admin-scoped `ProductTypeSelector` — public code shouldn't depend on an admin component's type; redefined locally as a trivial 2-value union, not meaningful duplication). Text-only, never color/icon alone. `UnavailableNotice` is copy/state supplied entirely by the parent — never infers availability, never encodes a backend status literal, no purchase action inside.
**Tests:** 2 + 2 = 4.

### FVS014-T03 — Public `ProductImageGallery`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/catalog/ProductImageGallery.tsx` (+test).
**Extraction decision (recorded, not performed):** audited FVS-012's admin `ImageGallery` first. Its `GalleryImageModel` (`isCover` + reorder/delete actions) and this page's main+thumbnail viewer needs diverge enough that forcing one shared component now would mean either leaking admin actions onto the public page or building an abstraction with no second real pressure case yet — explicitly against the "do not over-engineer" guidance. Only the general pattern (ordered array of `{id, src, alt}`) is reused conceptually; a fresh, simpler `ProductGalleryImage` model was defined instead (no `isCover` field — the first array element is always the initial/main image, a future adapter's job to order correctly).
**Design:** Local `selectedIndex` state only (no persistence). Main image + a thumbnail strip of real `<button>`s, each with its own meaningful `alt` text (not a generic "thumbnail N" label), active one marked `aria-current="true"`. No carousel library, no auto-play; the thumbnail strip gets native horizontal scroll (`overflow-x-auto`) for mobile instead of a JS swipe gesture. Zero admin actions (Move up/down, Set cover, Delete) — proven by a dedicated negative test.
**`<img>` lint warning:** same documented, unresolved constraint as FVS-012's `ImageGallery` — the image host/URL format is itself an open contract gap (`docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §17), so `next/image`'s remote-pattern allowlist cannot be configured safely yet. Recorded inline, not silenced.
**Tests:** 10 (default main image, one thumbnail per image, switching, active-state marking, real buttons, meaningful alt text, no admin controls, empty-array safety, no network, no storage).

### FVS014-T04 — WhatsApp Helpers + `WhatsAppChatButton`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/catalog/whatsapp.ts` (+test), `src/components/catalog/WhatsAppChatButton.tsx` (+test).
**Design:** Phone/message logic isolated in pure helpers (`#ARCHITECTURE-WHATSAPP-ADAPTER`) so it's never scattered across components. `buildWhatsAppHref` does **not** normalize an arbitrary setting value — its precondition is explicit (`normalizedNumber` must already be digits-only); anything else (a leading `+`, spaces, hyphens, empty) is rejected (`null`), never "cleaned up" by an invented rule. `buildWhatsAppProductMessage` is a frontend-owned default (the only confirmed requirement is that the product name appears in the message — exact copy is not a backend contract item). The component fails safely (renders nothing) on an absent or invalid destination, uses `target="_blank"` with `rel="noopener noreferrer"`, and performs no API write of any kind.
**Tests:** 8 (helpers) + 8 (component) = 16.

### FVS014-T06 (partial) — `AddToCartButton` (anonymous path only)

**Status:** CAN IMPLEMENT NOW (anonymous path); authenticated/real-cart path and owned-STL CTA deferred. **Files:** `src/components/catalog/AddToCartButton.tsx` (+test).
**Design:** See §0 for the full discrepancy resolution. For an anonymous visitor: a real `<a>` whose `href` is `buildLoginRedirectPath(returnToPath)` (FVS-003's existing helper, not duplicated). For an authenticated visitor: renders `null` — nothing to click through to yet, and no user-facing reason worth displaying for an internal dependency-ordering fact. No guest cart, no fake cart state, no placeholder POST request anywhere in this component.
**Tests:** 5 (anonymous link renders, href matches the existing helper exactly, authenticated renders nothing, no network, no storage).

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; `test:e2e` re-run once at the batch boundary (no route/page work this batch — existing E2E must remain green).
- No new runtime dependency.
- No production API calls, no guessed product-detail/public-settings DTOs, no `ProductDetailView` composition, no `/shop/:slug` route, no SEO implementation, no owned-STL CTA, no real cart mutation, until T05/T07/T08 unblock.
