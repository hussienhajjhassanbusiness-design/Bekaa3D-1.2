# FVS-026 — Checkout Flow — Implementation Plan

> **STATUS (2026-11-11, Phase 5D): IMPLEMENTED against the real backend 2dfb27b and accepted (28/28).** This plan is now historical. It was written before the backend existed, and the backend contract replaced every "NEEDS BACKEND CONFIRMATION" item below: the `Idempotency-Key` header, the `CheckoutRequest`/`CheckoutRead` shapes, `409 CART_PRICE_CHANGED` with `price_changes`, `dropped_lines`, and the public-settings field names. ADR-024 removed shipping zones and charges, so the shipping-zone parts are obsolete. T01 (`useCheckoutAttempt`), T02 (`checkoutModels`), T03 (`CheckoutStepper`), T04 (`DeliveryMethodSelector`) and the cart-conflict banner were replaced or removed. For what was built and why, see `docs/backend-handoff/REAL-BACKEND-ACCEPTANCE.md` "Phase 5D". Consent copy remains PENDING LEGAL REVIEW.

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch. Risk: CRITICAL — core revenue transaction.

**Goal:** Build the checkout-attempt idempotency architecture, normalized presentation models, and the full set of presentational pieces — `CheckoutStepper`, `DeliveryMethodSelector` (reusing FVS-023/024's canonical address/zone query+model), `ConsentCheckboxGroup`, the conflict/status banner set, and a minimal, display-only `OrderSummary` — while correctly deferring real checkout submission and the `/checkout` route until `POST /api/v1/checkout`'s request/response contract and the idempotency header are confirmed.

**Architecture:** The frontend never invents a final transaction value. `OrderSummary` only ever displays whatever subtotal/shipping/total it is given — it never sums line items itself (`#SECURITY-SERVER-CHECKOUT-TOTALS`). A price-change conflict is never silently retried — `PriceChangeConflictBanner` requires an explicit reconfirmation action (`#SECURITY-CHECKOUT-PRICE-CONFIRMATION`). `useCheckoutAttempt` generates one idempotency key per attempt via `crypto.randomUUID()` and only ever changes it when the caller explicitly calls `startNewAttempt()` — never automatically, never on every render, never tied to a guessed backend header name (`#SECURITY-CHECKOUT-IDEMPOTENCY`). `DeliveryMethodSelector` reuses FVS-023's `AddressModel`/`addressKeys` and FVS-024's `ShippingZoneOption`/`shippingZoneKeys` directly — no checkout-specific duplicate of either, and no address-to-zone inference anywhere (`#ARCHITECTURE-EXPLICIT-SHIPPING-ZONE`, carried over from FVS-024).

**Spec:** `docs/plans/backend/vertical-slice-plan.md`'s VS-021 entry and `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-026 entry (lines 688-712).

---

## 0. Repository / Contract Audit

Read: `docs/plans/backend/vertical-slice-plan.md` (VS-021, VS-007's settings Logic line, §13's global money rule), `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-023/024/025/026/007 entries), `FVS-023/024/025/007-IMPLEMENTATION-PLAN.md`, `docs/setup/frontend-setup.md`. Inspected `src/lib/addresses/{addressKeys,addressModel}.ts`, `src/lib/shippingZones/{shippingZoneKeys,shippingZoneModels}.ts`, `src/lib/cart/*`, `src/lib/settings/{publicSettingsKeys,publicSettingsModel}.ts`, `src/components/catalog/PriceDisplay.tsx`, `src/components/feedback/{DialogShell,Alert}.tsx`, `src/components/forms/`. Grepped both plan documents for `checkout|idempotency|price conflict|consent|terms|digital final sale|pickup|delivery|free shipping|accepting orders|kill switch|order total|transaction` — confirmed below. Grepped `src/` for `checkout|Checkout|idempotency|consent|Consent` — **zero existing checkout code anywhere**.

**Confirmed by repository evidence:**
- `POST /api/v1/checkout` is literal/confirmed (VS-021's own "Endpoint / entrypoint" line). `GET /api/v1/shipping-zones` is also literal (already established in FVS-024's audit).
- VS-021's Logic line confirms, at the **concept** level only: one DB transaction doing idempotency check, kill switch check, cart lock, revalidation, delivery/pickup validation, trusted shipping/free-threshold/total calculation, price-change detection/confirmation, terms/digital-final-sale consent capture, product/address/zone/rate snapshotting, dispatch estimate, pending-payment creation, cart clearing. **No field name, header name, status code, or RFC `code` value is given for any of these** — "price-change conflict extension" and "idempotency_records" are schema/table *names* only.
- VS-007's Logic line confirms an "accepting orders" setting and a "free shipping" setting exist as seeded business settings — but, exactly as already found during FVS-022's audit, `GET /api/v1/settings/public`'s response envelope/field names remain unconfirmed. No `acceptingOrders`/`isCheckoutEnabled`/`freeShippingThreshold` field name is repeated here as fact.
- Delivery granularity (per-order vs. per-line, for a mixed cart) is explicitly **not resolved** by either source — `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md`'s own FVS-026 entry says "per line if the cart mix requires it" without saying when or how. This plan builds `DeliveryMethodSelector` at the **per-order** level only (the one granularity level actually usable today) and records per-line granularity as unresolved rather than guessing it.
- No coupon/discount concept exists anywhere in either plan document — `OrderSummary` is built with `subtotal`/`shipping`/`total` only, no `discount` field.
- `AddressModel` (`src/lib/addresses/addressModel.ts`) and `ShippingZoneOption` (`src/lib/shippingZones/shippingZoneModels.ts`) are both directly reusable with zero modification for the delivery selector.

**What is genuinely unconfirmed:** the exact `POST /checkout` request body (cart id/version, address id, zone id, pickup representation, delivery granularity, consent fields); the idempotency mechanism (header vs. body field, exact name, TTL, scope, replay/reconfirmation semantics); the exact success response (order id/status/totals/payment-next-step fields); the price-conflict response's exact status/RFC-code/payload shape; the cart-concurrency response's exact representation; the exact `accepting-orders`/`free-shipping-threshold` public-settings field names.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Endpoints** | `POST /api/v1/checkout` path | **CONFIRMED** (literal) |
| **Endpoints** | `GET /api/v1/shipping-zones` path | **CONFIRMED** (literal, FVS-024 precedent) |
| **Request** | Body/fields (cart id, address id, zone id, pickup, consent) | **NEEDS BACKEND CONFIRMATION** |
| **Request** | Delivery granularity (per-order vs. per-line) | **UNCONFIRMED — not guessed, built at per-order level only** |
| **Idempotency** | Mechanism/header name/TTL/scope | **NEEDS BACKEND CONFIRMATION** |
| **Idempotency** | Concept: one key per attempt, reused across retries | **CONFIRMED** (FVS-025/026 entries' own State/API-integration lines) |
| **Response** | Success order/payment fields | **NEEDS BACKEND CONFIRMATION** |
| **Response** | Price-conflict status/code/payload | **NEEDS BACKEND CONFIRMATION** |
| **Totals** | Server computes trusted shipping/free-threshold/total | **CONFIRMED concept** (VS-021 Logic line); **no field names** |
| **Settings** | `accepting-orders`/`free-shipping-threshold` field names | **NEEDS BACKEND CONFIRMATION** (same gap as FVS-022's public-settings audit) |
| **Consent** | Terms + itemized digital-final-sale concepts | **CONFIRMED concept** (VS-021 Logic line); **no legal copy, no field names** |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Checkout-attempt idempotency helper | **CAN IMPLEMENT NOW** |
| T02 | Normalized checkout presentation models | **CAN IMPLEMENT NOW** |
| T03 | `CheckoutStepper` / section layout | **CAN IMPLEMENT NOW** |
| T04 | `DeliveryMethodSelector` | **CAN IMPLEMENT NOW** (per-order granularity only) |
| T05 | `ConsentCheckboxGroup` | **CAN IMPLEMENT NOW** (generic typed API, no legal copy) |
| T06 | `PriceChangeConflictBanner` + cart-conflict + kill-switch banners | **CAN IMPLEMENT NOW** |
| T07 | `OrderSummary` | **CAN IMPLEMENT NOW** (display-only, optional fields) |
| T08 | Real API integration | **BLOCKED ON BACKEND CONTRACT** |
| T09 | `/checkout` route | **BLOCKED** until T08 unblocks |
| T10 | Integration/E2E/docs | **BLOCKED** — no real route exists to exercise end-to-end |
| T11 | Real backend acceptance | **BLOCKED ON BACKEND AVAILABILITY** |

## 3. Safe Batch

T01–T07. T08–T11 are each blocked for a distinct, documented reason.

---

## 4. Backend Questions For Tomorrow

**Checkout request:** 1. Exact `POST /checkout` body. 2. Cart id/version required? 3. Address id field. 4. Shipping zone id field. 5. Pickup representation. 6. Delivery choice order-level or per-line? 7. Mixed physical/STL delivery semantics. 8. Terms-consent field. 9. Digital-final-sale consent representation. 10. Itemized digital consent required in the body, or one flag?

**Idempotency:** 11. Exact header or body field. 12. Required format. 13. TTL. 14. Scope per user? 15. Reusing the same key after a network timeout — confirmed safe? 16. Reusing the same key after a price-conflict response — safe, or does reconfirmation need a new key? 17. New key required after explicit reconfirmation? 18. Duplicate-in-progress response semantics.

**Response:** 19. Success status. 20. Exact order response shape. 21. Order id field. 22. Order status field. 23. Server subtotal field. 24. Shipping field. 25. Any discount concept at all? 26. Total field. 27. Currency field. 28. Payment-next-step representation (for FVS-027's handoff).

**Price conflict:** 29. Exact HTTP status. 30. RFC `code`. 31. Exact conflict payload shape. 32. Old/new price field names. 33. Affected-line identifier field. 34. Does the backend update the cart before returning the conflict? 35. Required reconfirmation request semantics — same idempotency key or a new one (§4 Q16/Q17 restated for this specific path)?

**Cart concurrency:** 36. Removed-item representation. 37. Unavailable representation. 38. Quantity-adjustment representation. 39. A generic cart-version conflict concept at all? 40. Does the checkout response include an authoritative refreshed cart?

**Delivery:** 41. Independently re-confirm explicit zone selection (already strongly implied). 42. Independently re-confirm no address-derived zone. 43. Exact public zone id/body field name for the request. 44. Pickup availability signal — is pickup even offered, and how would the frontend know? 45. Can one order mix pickup and delivery? 46. Can individual physical lines use different delivery modes (the still-unresolved per-line granularity question)?

**Settings:** 47. Exact `accepting-orders` public-setting field name. 48. Exact disabled semantics/value. 49. Exact free-shipping-threshold field name. 50. Currency for that threshold. 51. Is the threshold safe for the frontend to mirror as an estimate, or must it always wait for the server? 52. Should the frontend calculate any estimate at all, or only show backend output?

**Consent:** 53. Approved exact terms text/link (none exists in the repository today — product/legal must supply it). 54. Approved digital-final-sale wording (same gap). 55. Consent per digital product, or one digital-cart-wide consent? 56. Must a consent version/id be submitted in the request?

**Auth:** 57. Verified-email requirement for checkout. 58. Any other account-state requirement. 59. Session-expiry behavior mid-checkout.

**Testing:** 60. Mixed-cart fixture. 61. Price-conflict fixture. 62. Cart-concurrency fixture. 63. Kill-switch fixture. 64. Digital-consent fixture. 65. Idempotency-replay acceptance test. 66. Checkout-success → FVS-027 handoff fixture.

---

## 5. Task Detail (Safe Batch)

### FVS026-T01 — Checkout-Attempt Idempotency Helper

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/checkout/useCheckoutAttempt.ts` (+test).
**Design:** `useCheckoutAttempt()` — a hook, mirroring the `useScanStatusPolling` precedent (FVS-018) for testability via `renderHook`. `attemptKey` is generated exactly once via `useState(() => crypto.randomUUID())` — React's lazy-initializer form, which runs on mount only, never on a subsequent render, satisfying "do not generate on every render" and "same attempt returns same key across a retry" for free (the key simply persists in component state until the component unmounts or `startNewAttempt()` is called). `startNewAttempt()` is the one explicit, caller-driven way to retire the current key and mint a new one — never called automatically by this hook itself. Attempt-key generation is deliberately separate from any request/header mapping — no backend header name is referenced anywhere in this file; a future adapter (T08, blocked) maps `attemptKey` onto whatever header/body field the backend confirms.
**Marker:** `#SECURITY-CHECKOUT-IDEMPOTENCY`.
**Tests:** same key returned across multiple reads within one render cycle; re-render (simulating a retry) preserves the same key; `startNewAttempt()` produces a different key; calling `startNewAttempt()` once a "success" occurs demonstrates the old key is retired (same mechanism, different narrative); no `localStorage`/`sessionStorage` access anywhere.

### FVS026-T02 — Normalized Checkout Presentation Models

**Status:** CAN IMPLEMENT NOW. **Files:** `src/lib/checkout/checkoutModels.ts` (+test).
**Design:** `DeliveryMethodSelection = {kind: "address"; addressId: string; zoneId: string} | {kind: "pickup"}` — order-level only (§0's recorded granularity gap); `ConsentState {termsAccepted: boolean; digitalConsentByProductId: Readonly<Record<string, boolean>>}`; `PriceConflictLine {lineId: string; productDisplayName: string; oldPriceCents: number; newPriceCents: number; currency: string}`; `CartConflictLine {lineId: string; kind: "unavailable" | "quantity-adjusted" | "removed"; message: string}` — `kind` is a **frontend-owned** presentation category, not a claimed backend code, and `message` is always caller-supplied text from a future adapter, never fabricated here. No backend request-field name is claimed anywhere in this file.
**Marker:** `#ARCHITECTURE-CHECKOUT-ADAPTER`.
**Tests:** type-only tests (RED-confirmed via `tsc`) proving each shape accepts only the fields listed above — no address/governorate field on `DeliveryMethodSelection`, no backend-looking field name (e.g. no `httpStatus`/`rfcCode`) on either conflict type.

### FVS026-T03 — `CheckoutStepper`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/checkout/CheckoutStepper.tsx` (+test).
**Design:** a semantic progress indicator, not an interactive wizard — a single-page checkout shows Delivery/Review/Confirm as in-page sections simultaneously (so the price-conflict banner is never hidden behind a step transition), and this component only orients the user within that one page. `<nav aria-label="Checkout progress"><ol>` with one `<li>` per section; the current section gets `aria-current="step"`. `{currentSection: "delivery" | "review" | "confirm"}` — no click handlers, no internal state, no hidden sections.
**Marker:** none new — a plain, small presentational component.
**Tests:** renders exactly the three sections in order; marks the supplied `currentSection` with `aria-current="step"` and no other section; renders no interactive controls of its own (it's a progress indicator, not a wizard).

### FVS026-T04 — `DeliveryMethodSelector`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/checkout/DeliveryMethodSelector.tsx` (+test).
**Design:** `{addresses: readonly AddressModel[], zones: readonly ShippingZoneOption[], selection: DeliveryMethodSelection | null, onSelect: (s: DeliveryMethodSelection) => void, pickupAvailable?: boolean}` — reuses FVS-023's `AddressModel` and FVS-024's `ShippingZoneOption` directly (imported from their real modules, not re-declared). A single accessible radio group across: one option per saved address (rendering its `displayLines`), each paired with its own **separate, explicit** zone `<select>` (never auto-filled from the address) that only becomes meaningful once that address option is chosen, plus one "Pickup" option — **rendered only when `pickupAvailable` is `true`** (mirrors the CTA-only-if-supplied seam pattern already used for `HeroSection`/`AddressCard`'s `onEdit` — no invented pickup availability). Selecting an address never calls `onSelect` with a zone already filled in; the zone must be separately chosen before a complete `{kind: "address", addressId, zoneId}` selection exists.
**Marker:** none new — reuses `#ARCHITECTURE-EXPLICIT-SHIPPING-ZONE`'s existing rule (FVS-024), does not need a second marker.
**Tests:** renders one radio per saved address plus Pickup only when `pickupAvailable`; omits Pickup entirely when not supplied (no invented default); choosing an address does not call `onSelect` with any zone id pre-filled; choosing a zone for the selected address calls `onSelect` with the complete `{kind:"address", addressId, zoneId}`; choosing Pickup calls `onSelect` with `{kind:"pickup"}`; no governorate/address-parsing logic anywhere (grep-verifiable); no network.

### FVS026-T05 — `ConsentCheckboxGroup`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/checkout/ConsentCheckboxGroup.tsx` (+test).
**Design:** `{termsLabel: string, termsAccepted: boolean, onTermsChange: (checked: boolean) => void, digitalConsents?: readonly {productId: string; label: string; accepted: boolean}[], onDigitalConsentChange?: (productId: string, checked: boolean) => void}` — terms and every digital-product consent are **independent** checkboxes, never one blanket "I agree to everything." No legal copy is hardcoded anywhere — `termsLabel` and each digital consent's `label` are entirely caller-supplied, since no approved legal text exists in this repository (§0). Every checkbox defaults to unchecked; this component never pre-checks one. The caller is responsible for populating `digitalConsents` from the cart's STL lines (via `isStlLine`, FVS-025) — this component has no cart-filtering logic of its own.
**Marker:** none new.
**Tests:** terms checkbox and each digital consent checkbox are independently toggleable (checking one never affects another); renders no digital-consent checkboxes when none are supplied (a cart with no STL lines); renders one checkbox per supplied digital consent with its own accessible label; every checkbox starts unchecked by default even when some upstream state could be misread as "complete"; no pre-checked box under any prop combination; no network.

### FVS026-T06 — Conflict / Status Banners

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/checkout/PriceChangeConflictBanner.tsx` (+test), `src/components/checkout/CartConflictNotice.tsx` (+test), `src/components/checkout/CheckoutDisabledBanner.tsx` (+test).
**Design:** `PriceChangeConflictBanner({lines: readonly PriceConflictLine[], onReconfirm: () => void})` — `role="alert" aria-live="assertive"` (blocks progress, needs immediate attention per the source's own accessibility line); lists every affected line's product name plus old/new price via `PriceDisplay` (reused, no delta computed in floating point or otherwise — the two prices are shown side by side, never subtracted); exactly one "Reconfirm" button, which only ever calls `onReconfirm` — **never auto-retries**, and nothing in this component calls any mutation itself (`#SECURITY-CHECKOUT-PRICE-CONFIRMATION`). `CartConflictNotice({lines: readonly CartConflictLine[]})` — renders each line's own caller-supplied `message` individually, never collapsed into a generic "Checkout failed." `CheckoutDisabledBanner({reason: string})` — a plain `role="alert"` banner for the kill-switch case; takes only an already-resolved `reason` string, never a guessed `acceptingOrders`/`isCheckoutEnabled` settings field name — the real public-settings mapping stays backend-gated (§0).
**Marker:** `#SECURITY-CHECKOUT-PRICE-CONFIRMATION`.
**Tests:** `PriceChangeConflictBanner` renders every affected line's old and new price distinctly, uses `aria-live="assertive"`, and `onReconfirm` is the only callback ever invoked (no auto-call on mount/re-render); `CartConflictNotice` renders each line's distinct message, never a generic fallback string when lines are non-empty; `CheckoutDisabledBanner` renders the exact supplied reason, nothing invented; none of the three makes a network call.

### FVS026-T07 — `OrderSummary`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/checkout/OrderSummary.tsx` (+test).
**Design:** `{subtotalCents?: number, shippingCents?: number, totalCents?: number, currency: string}` — every amount field is optional, since no source confirms the checkout response's exact field names yet (only the *concept* that the server computes trusted shipping/totals, VS-021 Logic line); `currency` alone is required (never hardcoded). Each supplied field renders via `PriceDisplay` (reused); **no internal summation ever occurs** — if, say, `shippingCents` is omitted, this component does not compute it from the others. When no amount field is supplied at all, renders a plain "Order total will be confirmed at submission" placeholder rather than fabricating zeros.
**Marker:** `#SECURITY-SERVER-CHECKOUT-TOTALS`.
**Tests:** renders each supplied amount via `PriceDisplay` with the exact given currency; omitting one field never causes this component to compute or infer it from the others (e.g., supplying only `subtotalCents` and `shippingCents` never produces a `total`); renders the placeholder text when no amount field is supplied; no network.

---

## 6. Deferred / Blocked Tasks (Rationale)

**T08 — Real API integration:** Blocked — no confirmed request/response body for `POST /checkout`; the idempotency mechanism itself is also unconfirmed.

**T09 — `/checkout` route:** Blocked until T08 unblocks. This batch's components are deliberately not composed into one wired `CheckoutPage`, since the actual section composition depends on exactly how delivery/consent/conflict data flows together once the real contract exists — composing them prematurely risks baking in a guessed data flow.

**T10 — Integration/E2E/docs:** Blocked — no real route exists yet to exercise end-to-end.

**T11 — Real backend acceptance:** Blocked on backend availability.

**Free-shipping threshold math:** Not implemented anywhere in this batch — no confirmed field/currency/rule exists to mirror safely (§0/§4 Q47-52).

**Payment handoff:** Not built — FVS-027 owns the payment-result/redirect UX; no payment URL or result route is invented here.

**Independent-review follow-up (FVS-026 Important finding, resolved):** `DeliveryMethodSelector` could leave the caller's `selection` stale relative to the visible UI: switching address radios after a complete selection already existed for a different address left the parent's authoritative state disagreeing with what was on screen until a new zone was chosen. Classified **FRONTEND-SAFE TO FIX NOW** — a pure presentational-component correctness gap, no backend dependency. Fixed via TDD: `onSelect` now accepts `DeliveryMethodSelection | null`, and choosing a different address immediately invalidates a stale complete selection with `onSelect(null)` (re-clicking the address that already matches the current selection, or choosing from a blank starting selection, still calls nothing — only an actual invalidation fires). One remaining minor nitpick (also from the same review) was left as-is, consistent with the task's own scope: `activeAddressId`'s local state only re-syncs from `selection` on mount, so an external reset of `selection` later (e.g. after a future reconfirmation flow) won't move the radio UI without a remount — flagged for the future T08 adapter work, not fixed now since nothing in this batch resets `selection` externally yet.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit; one `test:e2e` regression run suffices (no route/page work this batch).
- No new runtime dependency.
- No real checkout `POST`, no guessed request body/idempotency header/status codes, no frontend-computed final total/shipping/free-threshold math, no address-to-zone inference, no invented legal consent copy, no guessed kill-switch settings field, no `/checkout` route, no payment redirect, until the respective gates in §6 unblock.
- `AddressModel`/`addressKeys` (FVS-023) and `ShippingZoneOption`/`shippingZoneKeys` (FVS-024) are reused completely unmodified.
