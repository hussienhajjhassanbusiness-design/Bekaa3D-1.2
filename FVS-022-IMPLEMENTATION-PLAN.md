# FVS-022 — Home Page, About Us & Floating WhatsApp — Implementation Plan

> **For agentic workers:** TDD where marked, full verification at every task boundary, one local commit per logical unit of work, STOP after the safe frontend batch.

**Goal:** Give the public site a real front door: a reusable `HeroSection`, a global `FloatingWhatsAppButton` architecture that shares exactly one public-settings cache with FVS-014's product WhatsApp CTA, and the canonical public-settings query-key family FVS-022 itself is the one to establish. About Us content, featured products, and the actual home-route composition are all correctly deferred — each for a distinct, documented reason (no approved copy, no confirmed product-list contract, and no confirmed public-settings response schema respectively) — rather than shipped with fabricated or faked content.

**Architecture:** `publicSettingsKeys` (`.root`/`.current()`) is the ONE shared TanStack Query key for `GET /api/v1/settings/public`, consumed (eventually) by `FloatingWhatsAppButton`, FVS-014's `WhatsAppChatButton`, and any future shipping-threshold display. `PublicSettingsModel` is a frontend-normalized shape holding only `whatsappNumber`, never a claim about the real response envelope. `FloatingWhatsAppButton` is purely presentational — it accepts an already-resolved href/number and renders nothing without one; it never fetches settings itself. `HeroSection` is a reusable, brand-focused component that reuses the repository's one approved copy fragment (the "Bekaa3D — Engineered Grade 3D Solutions" tagline) rather than inventing new hero copy, which also means it doesn't collide with the pre-existing `e2e/smoke.spec.ts` assertion that this exact text renders as the home page's heading.

**Spec:** `vertical-slice-plan.md`'s F-001/F-002/F-003 entries and `FRONTEND-VERTICAL-SLICE-PLAN.md`'s FVS-022 entry (lines 584-604).

---

## 0. Repository / Contract Audit

Read: `FRONTEND-VERTICAL-SLICE-PLAN.md` (FVS-022 entry, FVS-007/FVS-013/FVS-014 entries, §6/§17), `FVS-014-IMPLEMENTATION-PLAN.md`. Inspected `src/app/page.tsx`, `src/app/layout.tsx`, `src/components/layout/AppLayout.tsx`, `src/components/layout/Footer.tsx`, `src/components/layout/Header.tsx`, `src/app/` (route directory listing), `src/lib/catalog/whatsapp.ts`, `src/components/catalog/WhatsAppChatButton.tsx`, `e2e/smoke.spec.ts`. Grepped for `Hero|FloatingWhatsApp|AboutPageContent|publicSettings|PublicSettings|settings/public|FeaturedProducts` (zero matches — none exist yet) and for approved Home/About copy (`engineered grade|about us|our story|founded|years of experience|mission statement`, case-insensitive, across `.md`/`.ts`/`.tsx`).

**Confirmed by repository evidence:**
- `GET /api/v1/settings/public` is literal/confirmed (appears directly in FVS-007's, FVS-014's, and FVS-022's own "Endpoint / entrypoint" lines) — but its **response schema is not given anywhere**. FVS-007's own description of the admin settings surface ("a control per setting's declared type... keyed by the settings list response") implies the settings data may be shaped as a list of `{key, type, value}` entries rather than a flat object; guessing either shape would be inventing a backend contract.
- `/shop`, `/bring-your-idea`, `/contact`, `/about` **do not exist** as route directories under `src/app/` — confirmed via directory listing. Only `account/`, `login/`, `register/`, `verify-email/` exist as real route directories (plus the root-level `page.tsx`/`layout.tsx`/`error.tsx`/`global-error.tsx`/`not-found.tsx`).
- `src/app/page.tsx` is still the exact FVS-001 placeholder, rendering the brand tagline "Bekaa3D — Engineered Grade 3D Solutions" as its `<h1>`.
- **`e2e/smoke.spec.ts`** — described in its own header comment as "the default, deterministic, backend-independent E2E suite... the ONLY spec the 'smoke' Playwright project matches" — hard-asserts `page.getByRole("heading", { name: "Bekaa3D — Engineered Grade 3D Solutions" })` is visible on `/`, in two separate test cases (initial load, and after a 404-back-link navigation). Any real home-page composition must either preserve this exact string as the page's main heading, or this foundational E2E spec needs deliberate updating — this plan chooses the former (§5, T03/T06).
- `src/lib/catalog/whatsapp.ts`'s `buildWhatsAppHref` now has an optional `message` parameter (default `""`), extended in this batch via TDD so `FloatingWhatsAppButton` can reuse it without a product-specific message, with zero regression to FVS-014's existing 8 `whatsapp.test.ts` cases or its 9 `WhatsAppChatButton.test.tsx` cases (all still green).
- **Zero approved About Us body copy exists anywhere in the repository.** The only approved marketing-copy fragment of any kind is the brand tagline itself (found in `bekaa3d-brand-ui/SKILL.md`, `bekaa3d-brand-ui/tokens.md`, `e2e/smoke.spec.ts`, `FRONTEND-VERTICAL-SLICE-PLAN.md`, `FVS-001-IMPLEMENTATION-PLAN.md`, `src/app/page.tsx`). No founding date, customer count, years-in-business, delivery-area claim, quality guarantee, team bio, or manufacturing-capacity claim exists anywhere to reuse.
- FVS-013's `ProductCard`/`ProductGrid` (which FVS-022's own spec line says to reuse for `FeaturedProductsSection`) were **deliberately never built** — `ProductListItem`'s schema was left unconfirmed in FVS-013's own plan. There is nothing to reuse yet, and building a second, home-specific card/grid (or faking fixtures) would both violate this engagement's explicit "reuse before rebuild" and "no fabricated production content" rules.

**What is genuinely unconfirmed:** `GET /api/v1/settings/public`'s exact response envelope/field names; whether `featured`/`newest`/`popular` product semantics exist at all, and if so their exact query parameter; `ProductListItem`'s schema (owned by FVS-013, not this slice); whether any approved About Us copy will ever be supplied, and by whom; whether `/login`/`/register`/`/verify-email` count as "public" pages for the floating button's visibility scope.

---

## 1. Contract Confidence Table

| Area | Item | Status |
|---|---|---|
| **Public settings** | Endpoint path | **CONFIRMED** (literal) |
| **Public settings** | Response envelope / field names | **NEEDS BACKEND CONFIRMATION** |
| **WhatsApp** | wa.me href construction | **CONFIRMED, reused from FVS-014** (`buildWhatsAppHref`) |
| **WhatsApp** | Fallback number if setting missing | **CONFIRMED: none** — button renders nothing (spec's own "never hardcode a fallback" line) |
| **Featured products** | `ProductListItem` schema | **BLOCKED — owned by FVS-013, not re-decided here** |
| **Featured products** | Query semantics (`featured`/`newest`/`sort`/`limit`) | **NEEDS BACKEND/PRODUCT CONFIRMATION** |
| **Content** | Approved Home/About marketing copy | **NOT SUPPLIED — PRODUCT/COPY GATED** (only the brand tagline exists) |
| **Routes** | `/shop`, `/bring-your-idea`, `/contact`, `/about` | **CONFIRMED: do not exist yet** |
| **E2E** | `e2e/smoke.spec.ts` heading assertion | **CONFIRMED constraint** — must be preserved, not altered |

---

## 2. Task List

| Task | Purpose | Classification |
|---|---|---|
| T01 | Canonical public-settings query keys + normalized model | **CAN IMPLEMENT NOW** |
| — | `buildWhatsAppHref` optional-message extension (shared helper reuse) | **CAN IMPLEMENT NOW** (done ahead of T02 as a prerequisite) |
| T02 | `FloatingWhatsAppButton` (presentational, not globally mounted) | **CAN IMPLEMENT NOW** |
| T03 | `HeroSection` (reusable, approved tagline only) | **CAN IMPLEMENT NOW** |
| T04 | About Us (`/about` route + content) | **CORRECTLY DEFERRED — no approved copy exists** |
| T05 | `FeaturedProductsSection` | **BLOCKED — `ProductCard`/`ProductGrid`/`ProductListItem` don't exist (FVS-013)** |
| T06 | Home route (`/`) composition | **CORRECTLY DEFERRED — see §5 rationale** |
| T07 | Global `FloatingWhatsAppButton` mounting in `AppLayout` | **BLOCKED — no real public-settings query exists yet** |

## 3. Safe Batch

The `whatsapp.ts` extension, T01, T02, T03. T04–T07 are each deferred/blocked for a distinct, documented reason (no fabricated content is produced to work around any of them).

---

## 4. Backend / Product Questions For Tomorrow

**Public settings:** 1. Exact response envelope for `GET /api/v1/settings/public` — a flat object, or a `{key, value}[]` list like the admin settings surface implies? 2. Exact field name for the WhatsApp number setting. 3. Is the number pre-normalized to digits-only, or does the frontend need a normalization step (currently explicitly out of scope — `buildWhatsAppHref`'s precondition is digits-only)? 4. Will this same endpoint eventually carry the free-shipping threshold (FVS-025/026), and under what field name?

**Featured products:** 5. Does `GET /api/v1/products` support a `featured`/`sort=newest`/`limit` parameter, or is "featured" a different endpoint entirely? 6. Exact `ProductListItem` field names (owned by FVS-013 — tracked there, not duplicated here).

**Content:** 7. Who supplies approved Home/About marketing copy, and when? 8. Is there a real company history/founding date/delivery-area claim to publish, or should About Us ship v1 with only the brand tagline and a contact/WhatsApp pointer?

**Visibility scope:** 9. Should the floating WhatsApp button appear on `/login`/`/register`/`/verify-email` (auth/utility pages) or only on public-marketing pages (`/`, `/shop`, `/about`)? Not yet answered — recorded rather than guessed; T07 stays blocked regardless since the public-settings fetch itself isn't wired yet.

---

## 5. Task Detail (Safe Batch)

### Prerequisite — `buildWhatsAppHref` optional message

**Status:** DONE. **Files:** `src/lib/catalog/whatsapp.ts`, `src/lib/catalog/whatsapp.test.ts`.
**Design:** `message` parameter now defaults to `""` so a caller with no product context (i.e. `FloatingWhatsAppButton`) can build a valid href without duplicating wa.me construction/encoding logic. FVS-014's existing 8 tests plus `WhatsAppChatButton.test.tsx`'s 9 tests remain green, unmodified.
**Tests:** 1 new (`defaults to an empty message when none is supplied`).

### FVS022-T01 — Canonical Public-Settings Query Keys + Model

**Status:** DONE. **Files:** `src/lib/settings/publicSettingsKeys.ts` (+test), `src/lib/settings/publicSettingsModel.ts` (+test).
**Design:** `publicSettingsKeys = {root: ["publicSettings"], current: () => [...root, "current"]}` — `.current()` rather than `.list()`/`.detail(id)` because this is a single shared resource, not a per-id collection. `PublicSettingsModel {whatsappNumber: string | null}` — no backend field name encoded, no free-shipping field invented ahead of its own slice. No fetch/adapter function is built yet (response envelope unconfirmed — §0/§1) — only the key family and the normalized type, exactly mirroring FVS-020's `entitlementKeys`/`entitlementModel` precedent for the same kind of gate.
**Marker:** `#ARCHITECTURE-CANONICAL-PUBLIC-SETTINGS`, `#ARCHITECTURE-PUBLIC-SETTINGS-ADAPTER`.
**Tests:** 4 (`publicSettingsKeys`) + 3 (`PublicSettingsModel`, type-only, RED-confirmed via `tsc` not `vitest run`).

### FVS022-T02 — `FloatingWhatsAppButton`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/layout/FloatingWhatsAppButton.tsx` (+test).
**Design:** `{whatsappNumber: string | null}` prop — already-normalized data, never fetched by this component itself. Renders `null` if `whatsappNumber` is `null` or `buildWhatsAppHref` rejects it. Otherwise renders a real `<a href={buildWhatsAppHref(whatsappNumber)} target="_blank" rel="noopener noreferrer" aria-label="Chat with us on WhatsApp">`. Floating position via fixed-position utility classes plus a CSS custom-property seam (`--mobile-sticky-action-offset`, defaulting to `0px` via a fallback in the `bottom` calculation) so a future FVS-014 mobile sticky action bar can coordinate position without this component inventing a magic pixel offset tied to a bar that doesn't exist yet. Documented (not yet executed) for DOM placement after `<main>`/`<footer>` in `AppLayout`, matching the confirmed DOM order, so it is keyboard-reachable without being the first tab stop on any page — not globally mounted this batch (T07 blocked).
**Marker:** none new — reuses `buildWhatsAppHref` directly, no duplicated WhatsApp URL logic.
**Tests:** 11 minimum, per the task's own matrix — no destination (null)→renders nothing; valid destination→real anchor; exact accessible name "Chat with us on WhatsApp"; exact href (matches a direct `buildWhatsAppHref` call, proving no duplicated construction logic); safe external-link `rel`; never hardcodes a fallback number; no network call; no storage; floating/fixed-position classes present; component does not itself call any fetch/query for settings; invalid number (fails `buildWhatsAppHref`'s digits-only precondition) also renders nothing.

### FVS022-T03 — `HeroSection`

**Status:** CAN IMPLEMENT NOW. **Files:** `src/components/home/HeroSection.tsx` (+test).
**Design:** `{heading?: string, supportingCopy?: string, primaryCta?: {label: string, href: string}, secondaryCta?: {label: string, href: string}}` — `heading` defaults to the one approved tagline "Bekaa3D — Engineered Grade 3D Solutions" so this component can satisfy both a real hero requirement and (if ever composed onto `/`) `e2e/smoke.spec.ts`'s existing assertion without altering that spec. Renders exactly one `<h1>`. CTAs are entirely optional and only rendered as real `<a>` elements when explicitly supplied with a non-empty `href` — never a disabled anchor, never a default destination, since no currently-valid destination route exists for a home-page CTA to point to yet (§0). No image/video slot is wired in this batch (no approved hero visual asset exists) — the component accepts no `visual` prop yet rather than inventing a placeholder image.
**Tests:** 9 — renders the default tagline heading when no heading is supplied; renders a supplied heading override; renders supporting copy when supplied; renders nothing extra when supporting copy is omitted; renders a real anchor for a supplied primary CTA; renders a real anchor for a supplied secondary CTA; renders no CTA element at all when none is supplied (no disabled anchor); renders exactly one `<h1>`; CTA anchors use the caller's exact label/href unmodified.

---

## 6. Deferred / Blocked Tasks (Rationale)

**T04 — About Us:** Not built this batch. Zero approved About Us body copy exists anywhere in the repository or project docs (§0) — only the brand tagline, which is not substantive "About Us" content. Building a structural `AboutPageContent` shell with no real content to pass it, for a single use site, would be exactly the premature/decorative abstraction this engagement has consistently avoided elsewhere (e.g. not building `ScanStatusBadge`/a second combobox when nothing justified it). The `/about` route stays unbuilt until real, approved copy exists.

**T05 — `FeaturedProductsSection`:** Not built this batch. FVS-013's `ProductCard`/`ProductGrid`/`ProductListItem` were deliberately never built (schema unconfirmed) — there is nothing to reuse, and this plan does not build a second, home-specific product card/grid or fabricate product fixtures in production code. Also blocked independently on the featured-vs-newest-vs-popular query semantics question (§4, Q5).

**T06 — Home route (`/`) composition:** Not replaced this batch. With T04 (About) and T05 (Featured Products) both genuinely blocked, and T07 (global WhatsApp mounting) also blocked, the only safe ingredient available for a new `/` composition would be `HeroSection` alone with no valid CTA destination (§0 confirms `/shop`/`/bring-your-idea`/`/contact` don't exist yet). A hero-only page would not add genuine value over the existing FVS-001 placeholder (which already shows the same approved tagline), and replacing the route merely to claim "FVS-022 has a page" would violate the task's own explicit instruction not to force route replacement. `src/app/page.tsx` is left untouched; `e2e/smoke.spec.ts` requires no changes.

**T07 — Global `FloatingWhatsAppButton` mounting:** Not wired into `AppLayout`/`layout.tsx` this batch. Doing so would require either a real public-settings query (blocked — response envelope unconfirmed, §0/§1) or mounting with fake/undefined data, which the spec explicitly forbids ("never hardcode a fallback phone number"). The component itself (T02) is complete and tested in isolation, ready to be wired in once T01's model has a real adapter.

---

## Global Constraints

- Local Git only: no remote, no push, no PR.
- Full verification (`lint`/`typecheck`/`test`/`build`) before every commit. No route/page file is touched this batch, so a single `test:e2e` regression run suffices (no re-run-twice trigger).
- No new runtime dependency.
- No fabricated About Us copy, no fake featured-product fixtures, no hardcoded/fallback WhatsApp number, no dead CTA links, no route replacement that would introduce any of the above, until the respective gates in §6 unblock.
