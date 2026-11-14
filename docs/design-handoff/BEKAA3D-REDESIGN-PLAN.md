# Bekaa3D: Stitch Redesign Plan

**Goal:** current working Bekaa3D **plus** the Stitch "Precision Engineering System" design language. This is a re-skin, not a rebuild.

**Status:** Batch 1 (tokens, fonts, global foundation, shared primitives), Batch 2 (storefront Header, mobile navigation, Footer, ProductCard), Batch 3 (Home, Shop, Product Detail, WhatsApp action, skip link), Batch 4 (authentication and verification surfaces), Batch 5 (account shell, Profile, Addresses, Notifications), Batch 6 (Cart and Checkout) and Batch 7 (Orders, order detail, payment UI, checkout return, Offers, Wishlist) **complete** — see "Batch status" below. Batches 8–11 not started.

Companion documents:
- [BEKAA3D-TOKEN-MIGRATION.md](./BEKAA3D-TOKEN-MIGRATION.md): what every token becomes, and the alias-first strategy
- [BEKAA3D-COMPONENT-MIGRATION.md](./BEKAA3D-COMPONENT-MIGRATION.md): 116 component files mapped (classes A–E)
- [BEKAA3D-ROUTE-MIGRATION.md](./BEKAA3D-ROUTE-MIGRATION.md): 51 routes + 3 surfaces mapped (HIGH / MEDIUM / DERIVED)

**Baseline to preserve:** lint 0/0 · typecheck clean · unit 2199/2199 · build pass · E2E (smoke project) 176/176 · git clean.

**Design authority when sources disagree:**
1. DESIGN-SYSTEM.md recommendation
2. DESIGN-TOKENS.md
3. COMPONENT-SPECS.md
4. PAGE-SPECS.md
5. the dominant repeated Stitch pattern
6. one-off HTML

Above all of these sit the real app's behaviour, security, and accessibility (skill priority order).

---

## 0. Decisions needed before or at Batch 1

These are product-owner calls. The plan proceeds with the **default** shown unless told otherwise.

| # | Decision | Default in this plan | Why it matters |
|---|---|---|---|
| D1 | Adopt the Stitch primary `#0d631b` (and its MD3 palette) over the logo-derived `#195b2d` in `tokens.md`. | Adopt Stitch. | Brand identity. `tokens.md` says its palette was sampled from the real logo. |
| D2 | Update or supersede the `bekaa3d-brand-ui` skill and `tokens.md`. The skill currently says "avoid glassmorphism and gradients", which contradicts Stitch. | Update both in Batch 1 so they point at the Stitch handoff. | Two checked-in skills would otherwise give contradictory instructions to every future session. |
| D3 | Icon system: vendored Material Symbols **SVGs** via an `Icon` component, or a self-hosted icon font. | SVG `Icon` component, only the glyphs used. | CSP `font-src 'self'` and `style-src 'self'` block the Google CDN; no new remote dependency. |
| D4 | Font delivery: `next/font/google` (downloads at build time, self-hosted at runtime) or vendored `next/font/local`. | `next/font/google`; switch to local if CI builds offline. | Build reproducibility. |
| D5 | Admin chrome: hide the storefront header and footer on `/admin/*`. | Yes, via a client `SiteChrome` switch in `AppLayout` (no file moves). | Stitch admin is a full app shell. Today admin renders inside the storefront header and footer. |
| D6 | Add an account/login entry to the storefront header (Stitch has one; the app does not). | **Not added** unless approved. If approved, it ships in Batch 2 with its own tests. | It changes the navigation structure. |
| D7 | Marketing copy and stats from Stitch ("2,500+ models shipped", testimonials, trust badges). | Not used. Real or approved copy only. | Placeholder data must not ship. |
| D8 | Stitch screenshots. | Add the 35 `screen.png` files to `docs/design-reference/stitch/screens/`. | Only the HTML is in the repo. The 1280px comparison needs the PNGs. |

---

## Batch status

### Batch 1 — Global tokens, fonts, foundation, shared primitives: COMPLETE

**Decisions applied (product owner, Batch 1):**

| # | Outcome |
|---|---|
| D1 | Adopted Stitch `primary #0d631b`, hover `primary-container #2e7d32`. The logo asset is untouched (keeps its embedded green). |
| D2 | `bekaa3d-brand-ui` `SKILL.md` + `tokens.md` rewritten as implementation guidance aligned with Stitch; the handoff is named the visual authority. "Avoid glassmorphism and gradients" replaced by "use glass/gradient effects only where specified by the approved Stitch design system". Accessibility/engineering guidance kept. `bekaa3d-stitch-design` quick reference now says icons render through the local `Icon` component. |
| D3 | No remote icon font. New local `components/ui/Icon.tsx` (inline 24px outline SVGs, `aria-hidden`): `check-circle`, `error`, `warning`, `info`, `close`, `chevron-down`, `visibility`, `visibility-off`, `search`. No icon package added. |
| D4 | `next/font/local` with **vendored** variable woff2 files (Latin subset, OFL) instead of `next/font/google`: no network at build or run time, so offline CI builds work and CSP `font-src 'self'` is satisfied. |
| D5 / D6 | Recorded for later batches (dedicated admin shell, Batch 9; header Login/Account entry with returnTo preserved, Batch 2). Not implemented in Batch 1. |

**Tokens adopted** (`src/app/globals.css`, Tailwind v4 `@theme`):
- Full Stitch MD3 colour set under Stitch names (primary/secondary/tertiary families, all surfaces incl. lavender `#f1f3ff → #dce2f7`, `on-surface #141b2b`, `on-surface-variant #40493d`, `outline #707a6c`, `outline-variant #bfcaba`, error family) — values verified against `design-tokens.json`.
- Off-palette semantics named as tokens with the handoff's exact values: `warning #d97706` / `warning-container #fef3c7` / `warning-outline #fde68a` / `on-warning-container #92400e`; `info #2563eb` / `info-container #dbeafe` / `info-outline #bfdbfe` / `on-info-container #1e40af`; `whatsapp #25d366`.
- Families `font-headline`, `font-display`, `font-body` (= `font-sans`), `font-label`.
- Type roles `display` 48/1.1/800/-0.02em, `headline-lg` 32/1.2/700/-0.01em, `headline-md` 20/1.3/600, `title-sm` 16/1.5/600, `body-lg` 18/1.6, `body-md` 16/1.5, `label-caps` 12/1/600/0.05em, `label-sm` 11, `label-micro` 10. Mobile (<768) step-down: display 36, headline-lg 24.
- Layout/spacing: `gutter` 24, `margin-mobile` 16, `margin-desktop` 64, `section` 96 / `section-mobile` 64, `sidebar` 256, `topbar` 64, `container-content` 1440, `container-form` 1200. Defined only — no layout uses them yet.
- Shape: `rounded-badge` 4, `rounded-control` 8, `rounded-card` 12, `rounded-panel` 16, `rounded-banner` 24; `--radius-lg` 12 → 8 (after moving its 3 uses — DialogShell, AddressBook panel, NotificationBell — to 12px tokens).
- Elevation `shadow-ambient`; focus ring recoloured to `primary` (still box-shadow); motion `ease-standard`, default transition 200ms, `--duration-*`, `--press-scale`; gradients `--gradient-primary/-signature/-text-primary`.
- Utilities `glass-panel` (with opaque `@supports` fallback), `bg-blueprint`, `text-gradient-primary` — defined, not yet applied.

**Global foundation:** body `background #f9f9ff`, text `on-surface`, Inter; `h1–h6` Hanken Grotesk (base layer, utilities still win); `::selection` `primary-fixed` / `on-primary-fixed`; native checkbox/radio `accent-color: primary`; global `prefers-reduced-motion` block; `:focus-visible` = 2px white + 4px `#0d631b` box-shadow (unlayered, so it beats utility shadows while focused).

**Compatibility aliases retained** (each a `var()` to a Stitch token, no duplicate hex; remove in Batch 11): `brand-dark-green`, `brand-green`, `brand-lime`, `ink`, `success`, `success-bg` (lime 40%), `warning-bg`, `warning-text`, `danger`, `danger-bg`, `info-bg`, `neutral-50…900`, `text-primary/secondary/disabled/on-brand/link`, `surface-base/subtle/sunken`, `border-default/strong/focus`, `text-h1` (→ headline-lg incl. step-down), `text-h2` (kept 24/32), `text-h3` (→ headline-md), `text-h4` (→ title-sm), `text-body` (kept 14/20), `text-caption`, `text-label` (12/16, tracking 0.05em), `rounded-sm/md/pill`, `shadow-elevation-1/2/3` (→ e1 / shadow-lg / shadow-2xl). Full map in `.claude/skills/bekaa3d-brand-ui/tokens.md` §8.

**Fonts:** `src/app/fonts.ts` (three `localFont` loaders exposing `--font-*-face` variables on `<html>`), files in `src/app/fonts/` with a licence README. Vitest aliases `next/font/local` to `src/test/nextFontLocalStub.ts` (the real loader is a compile-time transform). Verified in the browser: all three families load from same-origin files and are the computed fonts on body / headings / buttons.

**Primitives restyled (public APIs preserved):**
- `Button` — Stitch hierarchy: `primary` (solid, hover `primary-container`, `shadow-lg shadow-primary/20`), `secondary` (2px primary outline), new `outline` (neutral), new `ghost`, `destructive` (solid error). Optional `size` sm/md/lg (default md). Mono uppercase label via CSS. Spinner while `isLoading`; `disabled || isLoading`, `aria-busy`, `type="button"` default and `ref` unchanged. Press scale only when enabled and not under reduced motion. `box-shadow` is not transitioned, so the focus ring appears instantly.
- Shared `forms/fieldStyles.tsx` used by `TextField`, `PasswordField`, `SelectField`, `TextAreaField`, `MoneyInput`: mono uppercase label, 48px+ white control, 8px radius, `outline` border, focus border primary + global ring, error border + `ring-error/20` + caption error text with icon, disabled lavender + 50%. `PasswordField` toggle moved inside the field (icon + sr-only "Show/Hide password", `aria-pressed` kept). `SelectField` keeps the native select with a decorative chevron. `TextAreaField` `resize-y`. All ids, `aria-describedby`, `aria-invalid`, `ref`, RHF/Zod wiring untouched.
- `Form` error summary — error-container card (same `role="status"`, same content).
- `Alert` — callout card (12px, tinted border, MD3 container, per-variant icon); roles/live regions unchanged.
- `Toast` / `ToastProvider` — inverse surface, 12px, `shadow-2xl`, per-variant icon, close icon (same "Dismiss notification" name); container bottom-right from tablet, centred on mobile, `pointer-events-none` on the empty container.
- `DialogShell` — panel `rounded-card`, white, `outline-variant/30` border, `shadow-2xl`, `p-6 tablet:p-8`; scrim `on-surface/40 backdrop-blur-sm`. Focus trap, Escape/backdrop-unless-busy, focus return, `max-h-[90vh]`, `panelClassName` seam untouched. `AddressBook` panel override restyled to match.
- `ConfirmDialog` — `headline-md` title, `body-md` description, Cancel → `outline` variant (one rank-1 action), confirm primary/destructive rightmost. Busy lock and DOM order unchanged.
- `LoadingSpinner` (`text-primary`), `EmptyState` (§49 layout, same props), `StatusBadge` (§9 tone map, mono 11px pill; additive `info` tone), `ProductTypeBadge` (format tag), `PriceDisplay` (additive optional `size` card/summary/detail; omitted = no classes, so every caller is unchanged).

**Deviations from Stitch (and why):**
- Input resting border `outline` instead of `outline-variant` — WCAG 1.4.11 (≥3:1 control boundary).
- Global focus ring kept (box-shadow, 4px primary) instead of Stitch's faint `ring-primary/20` — WCAG 2.4.7, and E2E asserts it.
- Buttons: 2px border on every variant (equal heights), min heights 36/44/52 (44px target size), wrapping labels with 16px leading at narrow widths.
- `label-caps`-based labels use a 16px line height where text can wrap (token doc).
- `MoneyInput` has no `$` prefix: currency is never hardcoded (it stays in the label).
- `success-bg` alias = lime at 40%, so legacy left-rail banners stay a tint.
- Button variants `gradient`, `tonal`, `inverse` not added yet — no call site needs them; add with the batch that does.
- `Container` and `Skeleton` primitives deferred to the batches that first use them (no unused components shipped).

**Targeted checks during development:** `vitest run` on `src/components/{forms,feedback,catalog,account,notifications}`, `StatusBadge.test`, `app/layout.test` (510/510). Updated presentation-only assertions in the `Button`, `ConfirmDialog`, `DialogShell`, `Alert`, `Toast`, `ToastProvider`, `StatusBadge` and `MoneyInput` tests; added tests for the new variants, sizes, loading spinner, press-scale guard, Cancel hierarchy, StatusBadge tone map + CSS-only uppercase, and PriceDisplay opt-in sizes. No behavioural assertion was removed or weakened.

**Visual QA** (temporary primitives page, not committed; Edge at 320 / 375 / 768 / 1280 / 1440): no horizontal overflow at any width; computed fonts Inter / Hanken / JetBrains Mono from self-hosted files; display 36 → 48 at 768; inputs/selects 50px; md buttons 44px; long button labels and alerts wrap without clipping; badges fit at 320; dialog fits the viewport (288px at 320, 448px ≥768), Escape closes it and focus returns to the trigger; keyboard focus shows the 2px white + 4px `#0d631b` ring on buttons and inputs, and the input border turns primary; disabled = 50% / not-allowed / no shadow; busy = disabled + `aria-busy` + spinner; error = red border + soft ring + `aria-invalid` + describedby. Fixed during QA: the Button transitioned `box-shadow`, so the focus ring faded in over 200ms; `box-shadow` was removed from its transition list.

**Gate:** lint ✓ (0 errors/0 warnings) · typecheck ✓ · unit 2212/2212 (230 files; baseline 2199 + 13 new) · build ✓ · E2E (smoke) 176/176. Production check: `next start` under the real CSP serves all three fonts from the same origin with no CSP errors. Note: typecheck first failed on a stale `.next/dev/types` entry for the deleted QA page (a generated artifact); after clearing `.next/dev` it passed.

**Deferred to Batch 2+:** Header (incl. the Login/Account entry, D6), Footer, mobile navigation, ProductCard, `Container`, `PageHeader`, `Skeleton`; per-call-site promotion of `text-body` → `body-md` and `text-h2` → `headline-lg`/`headline-md`; checkbox/radio sizing and radio cards (inline in pages today); `FileUploader`, `CaptchaWidget`, `SuccessReceipt`, `LoadMore` restyles; admin shell (D5); alias removal (Batch 11).

### Batch 2 — Storefront chrome and product card: COMPLETE

**Decision applied:** D6 approved (product owner, Batch 2) — the header gets a Login / Account entry using the existing routes, with returnTo preserved. No dropdown, no new account features.

**Header** (`components/layout/Header.tsx`, COMPONENT-SPECS §1 canonical / DESIGN-SYSTEM §12.5–§12.7):
- 64px bar, content capped at 1440px (`max-w-content`), gutters 16 / 32 / 64px. Glass surface `bg-surface/80` + `backdrop-blur-xl` + `border-outline-variant/30` hairline + `shadow-sm`, painted on its own absolutely positioned layer, so `backdrop-filter` never becomes the containing block of a fixed descendant.
- Sticky: `AppLayout`'s `<header>` landmark is `sticky top-0 z-40` (Stitch uses `fixed` + content offset; sticky needs no offset). z-40 keeps dialogs, toasts and the skip link (z-50) above it. `html { scroll-padding-top: 72px }` keeps focused elements and anchors clear of it (WCAG 2.4.11).
- Logo: new shared `BrandMark` — the **real** logo glyph (`public/brand/bekaa3d-mark.png`, 129×144, cropped from `docs/assets/…jpg` with white converted to alpha; no hue change, never recoloured) beside the §12.6 standard wordmark (Hanken 20px / 800 / `primary`). The image is decorative (`alt=""`), so the home link's name stays exactly "Bekaa3D".
- Desktop nav (≥1024): logo + links left (`gap-8`), Inter 16px `on-surface-variant` → hover `primary` (200ms); active = `primary` bold with a 2px `primary` underline and `aria-current="page"`. Same five real routes; Stitch link sets not used.
- Right group: cart icon button (40px, round hover tint, 16px `primary` count badge capped "99+", count only in the accessible name, as before), then the auth entry, then (below 1024) the menu button.

**Login / Account** (`components/layout/HeaderAccountLink.tsx`):
- Signed out: "Sign in" → `/login?returnTo=<current path>` built with the shared `buildLoginRedirectPath` (same validator as everywhere else). On `/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email/*` it links to plain `/login` (an auth page is never a returnTo). `aria-current="page"` on `/login`.
- Signed in: "Account" → `/account` (redirects to the profile and owns its own protection); `aria-current="true"` anywhere under `/account`.
- While the session resolves: an inert `aria-hidden` placeholder of the same size — no flash of the wrong state, no layout shift.
- One element at every width: below 768px the label is `sr-only` (icon-only 40px button), from 768px icon + mono caps label in an outline pill. The accessible name never depends on layout. Logout stays where it already lives (account area); none added to the header.

**Mobile navigation** (below 1024px; Stitch has none — RESPONSIVE-SPECS §1 recommendation):
- Menu button (40px, `aria-label="Open menu"`, `aria-expanded`, `aria-haspopup="dialog"`, `aria-controls="mobile-nav"`) opens a right-hand full-height sheet (`max-w-sm`, `bg-surface`, `shadow-2xl`) built on the **existing `DialogShell`** (focus trap, Escape, backdrop click, focus return) via `panelClassName` — no second modal system. Portaled to `<body>` (the sticky header is its own stacking context), mounted client-only through `useSyncExternalStore`, and kept mounted while closed because `DialogShell` restores focus on the open→closed transition.
- Inside: brand + "Close menu" button (receives focus on open), the same five links in a `nav "Main"` (`id="mobile-nav"`, Inter 18px, 56px rows, active `primary` bold on `surface-container-low`), and a full-width primary auth entry (Sign in / Account) at the foot.
- Closes on: Close button, Escape, backdrop, following a link, any route change (render-time pathname comparison), and growing past 1024px (`matchMedia` listener). Page scroll is locked while open (`documentElement.style.overflow`, restored on close).
- Cart stays in the bar at every width; the auth entry is in the bar at every width **and** in the sheet.

**Footer** (`components/layout/Footer.tsx`, DESIGN-SYSTEM §12.8 / COMPONENT-SPECS §6):
- `surface-container-low`, `border-t outline-variant`, `pt-24 pb-12` (`pt-16 pb-8` below 768), content capped at 1440 with the header's gutters.
- Brand column (BrandMark in `on-surface` + one line condensed from the approved `/about` copy) + `nav "Footer"` with three headed lists (mono caps `label-caps` `h2`s, Inter 16px links `on-surface-variant` → `primary`): **Shop** (Shop, Bring your idea) · **Company** (About, Contact) · **Your account** (My account → `/account`, Wishlist → `/account/wishlist`, Cart → `/cart`; each route already protects itself, so the footer needs no auth state).
- Bottom bar: `© <current year> Bekaa3D. All rights reserved.` + the real tagline in mono caps. Layout: 4 columns ≥1024, brand above a 3-column link grid at 768, brand above a 2-column link grid below 768.
- The footer wordmark is plain text, not a second "Bekaa3D" link. No admin links.

**ProductCard** (`components/catalog/ProductCard.tsx`, COMPONENT-SPECS §11b recommended canonical, DESIGN-SYSTEM §12.10/§12.11):
- Still **one link** to `/shop/{slug}`; the wishlist heart is still a sibling over the image corner (nothing interactive nested). White `surface-container-lowest`, `rounded-card` 12px, `border-outline-variant/30`, `shadow-sm`.
- Hover: the *wrapper* lifts 4px (300ms standard easing) so the heart moves with the card; the link gets `shadow-xl`; the image zooms to 105% over 500ms; the title turns `primary`; the CTA goes `primary-container`. All transforms off under `prefers-reduced-motion`.
- Media: square `aspect-square` on `surface-container-low`, real backend `coverImage` with its alt, `object-cover` (never tiled), `loading="lazy"`. No image → image glyph + "No image available" (mono caps), never a broken image.
- Over the image: category pill (`primary`, mono 10px bold caps `tracking-widest`, truncated before the heart's corner) and, when `is_featured`, a square "Featured" badge (§18 overlay badge, `on-surface-variant`).
- Body `p-6`: format tag (Physical / STL) and — only when `review_count > 0` — a rating (filled star + "4.5 (12)", spoken once as "Rated 4.5 out of 5 from 12 reviews"); Hanken 20px title clamped to 2 lines (full name stays in the DOM and the link name); price via `PriceDisplay size="card"` (Hanken 20 / `primary`); an "Unavailable" warning pill when `!is_available`; then a full-width solid primary **"View details →"** CTA that is part of the link (no add-to-cart action added: the card has no cart behaviour today).
- `WishlistButton` icon variant restyled only: translucent white circle, `shadow-sm`, `backdrop-blur-sm`, `on-surface-variant`, hover/saved `error` (Stitch favourite colour), always visible. `aria-pressed`, labels, sign-in link with returnTo, busy handling unchanged. `ProductGrid` gap → `gap-gutter` (24px) at every width.

**Shared components:** new `BrandMark` (2 call sites: header, footer) and `HeaderAccountLink` (2 call sites: bar, sheet). Reused `DialogShell`, `Icon` (+ `menu`, `shopping-cart`, `person`, `login`, `arrow-forward`, `image`, `star`), `PriceDisplay`, `ProductTypeBadge`, `buildLoginRedirectPath`. No `Container`, nav-item or icon-button abstraction was added (no second real call site yet).

**Deviations from Stitch (and why):**
- Inline nav from **1024px**, not Stitch's 768: Stitch's link sets had 4 short labels; the app's 5 (incl. "Bring your idea") + logo + labelled auth entry crowded the 768px gutter (measured: 1px overflow). The sheet covers 768–1023.
- Logo: real glyph + wordmark instead of Stitch's text-only wordmark (product decision: use the real logo).
- Sticky instead of fixed (no content offset needed); no scroll-shrink (§12.5 says optional).
- No header search pill (§1 canonical has one at lg+): it would be a new feature; `/shop` keeps its own search (Batch 3).
- Signed-out shows one "Sign in" entry, not Stitch's LOGIN + REGISTER pair (the locked header decision asks for one entry; `/login` links to registration).
- Footer: no newsletter, social circles, payment logos or Documentation/Privacy/Terms links (no real source); bottom bar shows the tagline instead of payment icons.
- ProductCard CTA is "View details" (navigation), not "Add to cart" — no card-level cart behaviour exists and adding one would nest a second action. Price uses the §17 card role (`primary` 20px) rather than the shop screenshot's `on-surface-variant` 18px (Batch 1 `PriceDisplay size="card"`). Title clamps to 2 lines instead of `truncate`, so long names stay readable. No hover-only quick-view overlay (hover-only controls are not reachable on touch/keyboard). Category pill is always `primary` (no per-category colour data).
- Rating star uses `warning` (amber-600, 3.2:1 on white) instead of amber-400 (2.1:1, below the 3:1 graphics minimum).
- Wishlist heart stays 44px (Stitch 40px) for the touch-target size.
- `CheckoutView` summary aside: `desktop:top-4` → `desktop:top-20` (one class), so the sticky summary is not hidden under the now-sticky header. Not a checkout redesign.

**Admin scope:** `/admin/*` still renders inside the storefront chrome exactly as before Batch 2 (nothing new was added to admin); the `SiteChrome` switch that removes it lands with the admin shell in Batch 9, so admin never shows half a shell. The Footer has no admin links.

**Account nav test constraint (account-profile.spec.ts):** that test protects the *account sidebar* `navigation "Account"` (present and bounded at 320–1920, narrower than the viewport from 768). Batch 2 does not touch it and it still passes unchanged. The new header entry is a link named "Account", never a `navigation` landmark, so it cannot collide with that locator; the header itself has no overflow at any width.

**Targeted tests:**
- `Header.test` rewritten (18): brand link + decorative real logo; landmark ownership; exact real nav hrefs; `aria-current`; signed-out Sign in with returnTo; signed-in Account; loading shows neither; cart → auth DOM order; menu closed state + `aria-controls`; open → labelled modal sheet, same links, focus on Close, scroll lock; auth state inside the sheet; Close returns focus + restores scroll; Escape; Tab wrap; link closes; route change closes; breakpoint growth closes.
- New `HeaderAccountLink.test` (13): returnTo of the current page; plain `/login` on each auth page; `aria-current`; unsafe path `//evil.example` → `returnTo=%2F`; signed-in Account + section current; label always in the DOM; loading placeholder; `onNavigate`.
- `Footer.test` (7): exact real link list, 7 links all inside `nav "Footer"`, no form/newsletter/legal text, no admin hrefs, headed lists, decorative logo, current year.
- `ProductCard.test` (17, +8): unavailable pill now asserts the `on-warning-container` token (same AA intent); no rating at 0 reviews; real rating with spoken summary when > 0; one link holds image/name/price/CTA and no nested control; heart is a sibling with the product returnTo; real image + alt + lazy + `object-cover` in a square; reduced-motion classes; category shown; long name kept in full under a 2-line clamp.
- `AppLayout.test`: header auth entry stubbed; sticky `z-40` header asserted; tab-walk bound raised for the extra stops.
- E2E: new `storefront-chrome.spec.ts` (11, added to the smoke project): per width 320/375/768/1024/1280/1440 — 64px header, visible Sign in with returnTo, Cart, the right nav pattern, ≥40px bar targets below 1024, footer nav, no overflow; signed-in Account at 320 and 1280; header stays at y=0 after scrolling; keyboard-open sheet with focus inside, 5 links, sheet within the viewport, scroll locked, Escape returns focus; link navigation closes the sheet; footer hrefs. `login-session.spec.ts` keyboard walkthrough now includes the header Sign in stop after Cart (deliberate: a new real tab stop). Two page-wide text checks were made precise because the new footer copy contains "order" / "STL": `admin-orders.spec.ts` checks `<main>` for leaked order text; `product-detail.spec.ts` matches the STL badge exactly inside `<main>`. Intent unchanged in both.

**Visual QA** (Edge, mocked catalogue with real-shaped data incl. a square image, a 16:9 image, no image, a long name, a long category, unavailable, featured, rated, saved-to-wishlist; signed out and signed in; 320 / 375 / 768 / 1024 / 1280 / 1440):
- No horizontal overflow at any width in either auth state (after moving the inline nav to 1024; it was 1px over at 768 signed in). Header 64px everywhere.
- 1280 vs `shop_…/screen.png`: same 64px glass bar, logo + links left (canonical) with the Shop underline, cart + auth on the right; 3-up cards at 296px with square media, category pill top-left, heart top-right, 24px body, Hanken title, price, full-width green CTA; footer brand + columns + bottom bar. Differences are the listed deviations.
- Cards: equal heights in a row; 16:9 image cropped square, never tiled; no-image placeholder; 2-line clamp with ellipsis; unavailable pill wraps under the price when narrow; long category pill truncates before the heart (full name stays in the link name). Card widths 288 (320) · 343 (375) · 208 (768) · 211 (1024) · 296 (1280/1440); the narrow 768/1024 cards come from the current shop filter column (Batch 3 moves filters to a drawer below 1024).
- Mobile: bar fits at 320 (logo, cart, sign-in icon, menu); sheet full-width at 320/375, 56px rows, clear Close, primary Account/Sign in at the foot.
- Cart badge renders on the icon corner with "Cart, 3 items" as the name; keyboard focus shows the 2px white + 4px primary ring on the round cart button, links, the menu button and card links.
- Reduced motion: lift, zoom and transitions disabled through `motion-reduce:` (asserted in unit tests) plus the global Batch 1 block.

**Gate:** lint ✓ (0 errors / 0 warnings) · typecheck ✓ · unit **2248/2248** (231 files; 2212 + 36) · build ✓ · E2E (smoke) **187/187** (176 + 11 new). The single gate run had 3 E2E failures: two were the page-wide text checks above (fixed in the specs only, re-run green); one (`account-profile` anonymous redirect) was a cold dev-server compile of `/login` under parallel load — the header had already resolved, the redirect was pending — and passed 3/3 in isolation and in the targeted re-run. No application code changed after the gate, so per §4 only the affected specs were re-run (25/25).

**Deferred to Batch 3+:** WhatsApp FAB restyle and its contrast decision (token doc), `SkipLink` restyle, `PageHeader`, `Container`, filter drawer and shop/home/PDP composition (Batch 3), header search (not planned without a product decision), wishlist page cards (`WishlistList`, Batch 7), admin chrome removal (Batch 9).

### Batch 3 — Home, Shop, Product Detail: COMPLETE

**Shared primitives (each with ≥ 2 real call sites):**
- `components/ui/Container` — 1440px cap (`max-w-content`), gutters 16 / 32 / 64 (same as header/footer); used by every Home section, Shop and Product Detail.
- `components/ui/SectionHeader` — optional mono eyebrow, a real `h2` in the `headline-lg` role (32 → 24 below 768), muted lead; `center` / `split` (+ action). Used by the three Home data sections.
- `components/ui/useSheetBehavior` — scroll lock + "close when the viewport grows past the breakpoint" for `DialogShell`-based side sheets. Used by the header menu (refactored onto it, same behaviour) and the new shop filter drawer.
- `components/ui/WhatsAppGlyph` — local WhatsApp mark (floating action + product-page button).
- `components/catalog/RatingSummary` — extracted from the Batch 2 card (output identical), now also on the product page.
- `buttonLinkClassName(variant, size)` in `forms/Button` — button hierarchy for `<a>`/`<Link>` (hero, CTA panel, sign-in links), without the `enabled:`/`disabled:` prefixes links cannot use.
- `Icon` + `filter-list`, `chevron-right`, `add`, `remove`, `deployed-code`, `download`, `verified`, `lightbulb`, `mail`, `category`. Tokens + `whatsapp-strong #128c7e`, `whatsapp-deep #075e54` (WhatsApp's own Teal Green / Dark Teal).
- **Not created:** `PageHeader` — Shop is the only page-level header in this batch (the PDP H1 sits in its info column); it lands with the account/admin pages that share §64.

**Home** (PAGE-SPECS S1, Stitch section order, full-width bands, 96px / 64px rhythm, alternating surfaces):
1. **Split hero** (§9): mono eyebrow "Physical prints · STL files"; display H1 — the approved tagline "Bekaa3D — Engineered Grade 3D Solutions" with the second half in `text-gradient-primary` (accessible name unchanged); lead from the approved `/about` copy; "Shop Now →" primary lg + "Learn More" secondary lg (same hrefs). Right: a decorative brand panel (real logo mark on the blueprint grid, two glass chips naming the two real product types), `aria-hidden`, shown from 768px; CSS orbs only. No photo, no Stitch statistics or machine status.
2. **Shop by Category** bento (§13): one 2×2 "Shop all products" feature tile (`primary-container`, → `/shop`) + one tonal tile per real category (→ `/shop?category=<id>`, unchanged); 1 → 2 (640) → 4 (1024) columns; tiles 144 / 192 / 240px tall. Omitted on loading/error/empty, as before.
3. **Featured Products** (S1 "Physical Masterpieces"): split header with "View all products →" (`/shop`) and the shared `ProductGrid` in a new `showcase` layout 1 → 2 → 3 (1024) → 4 (1280). Skeleton while loading; omitted on error/empty, as before.
4. **Why Choose Bekaa3D** (§14 feature tiles): the same three real points as cards with 64px tonal icon boxes (hover primary + 6° turn, off under reduced motion).
5. **CTA panel** (§52 green): "Have something in mind that isn't in the shop?" + copy from the approved Bring-your-idea intro; "Bring your idea" (white) and "Contact us" (outline). New file `home/CustomRequestCtaSection`.

**Shop** (PAGE-SPECS S2):
- Page banner (§9 image banner) without a stock photo: `inverse-surface` with a faint white blueprint grid and a primary glow; mono eyebrow, display H1 "Shop", lead, and the glass search pill.
- `SearchBar`: rounded pill, leading glyph, borderless field, "Clear", and a primary "Search" submit (same form submit — Enter still works); optional `hideLabel` keeps the label for AT (used here). Suggestions in a card under the pill (still real buttons).
- From 1024px: a 256px `aside` (labelled "Filters", §19) beside the results. Results toolbar (§20): Filters button (below 1024), a `role="status"` count ("6 products shown, more available" — cursor paging has no total), and the sort select (mono label, tinted borderless native select + chevron).
- `ProductGrid` `catalog` layout 1 → 2 (640) → 3 (1280); card-shaped skeletons (`role="status"`, `aria-busy`, shared "Loading…" copy, placeholder list `aria-hidden`); the existing Alert/EmptyState error and empty states unchanged.
- `FilterPanel` (§19): mono caps legends, 20px primary checkboxes with whole-row labels, applied filters as §18 removable tags (same "Remove X filter" names), "Clear filters" as a text action. `LoadMore` (shared): centred outline button `mt-12`.

**Responsive filter solution:** below 1024px the aside is not rendered visibly; a toolbar "Filters" button (`aria-haspopup="dialog"`, `aria-expanded`, `aria-controls`, `aria-label` "Filters, N active" with a visual count badge) opens a full-height left sheet on the existing `DialogShell` (`panelClassName`; focus trap, Escape, backdrop, focus return) with `useSheetBehavior` (scroll lock, closes at ≥1024). It renders **the same `FilterPanel` element with the same handlers**: ticking applies immediately through the URL exactly like the aside, so opening/closing never resets anything; "Show results" just closes; Clear filters works inside. Focus goes to "Close filters" on open. Card widths measured: 288 (320) · 343 (375) · 340 (768) · 296 (1024) · 275 (1280) · 328 (1440) — the Batch 2 ~210px squeeze at 768–1023 is gone.

**Product Detail** (PAGE-SPECS S4):
- Breadcrumb (§22, mono caps, `nav "Breadcrumb"`): Shop → the real category (`/shop?category=<id>`) → current product (`aria-current="page"`).
- 12-column 7/5 split from 1024px, stacked below (gallery first).
- Gallery (§24): main image square, 4:3 from 768px, real `<img>` + `object-cover` on `surface-container-low` (the Stitch tiling defect cannot occur); thumbnail grid 4 → 5 columns, selected `border-2 primary`; same buttons, alt names and `aria-current`. One image shows no strip; none shows a "No image available" panel (previously nothing rendered). No hover zoom (Stitch's was hover-only and not existing behaviour).
- Info column: type badge + real rating (only if `review_count > 0`), display H1 (`break-words`), price in the `detail` role (48/36), Unavailable callout (§56 warning), then **one action card**: Add to cart (primary lg, full width; square stepper §26 for physical — same labels, caps and disabled rules; anonymous = sign-in link with returnTo; unverified = verify message), WhatsApp (only with `whatsapp_available` + a configured number), wishlist (full variant, neutral outline), Make an offer (only with `can_offer`; secondary lg; offer form in a tonal card). Then "Specifications" (`h2` + `dl` of §25 spec tiles, 2-up at every width: Material, Colour, Dimensions, Production lead time — only fields that exist) and "Description" (`h2`, `whitespace-pre-line` so the author's line breaks show).
- States unchanged: spinner while loading, real 404 content, retryable Alert (now inside the Container).

**WhatsApp floating action:** 56px circle, `shadow-xl`, `hover:scale-110` (off under reduced motion). Fill **WhatsApp Teal Green `#128c7e`** (hover Dark Teal `#075e54`) with a white glyph: 4.1:1, above the 3:1 non-text minimum; Stitch's white on `#25d366` is 2.0:1. `z-30`, so it sits under the sticky header (40) and every dialog/sheet (50); inset 16px (mobile) / 32px (≥768) plus `env(safe-area-inset-*)` and the existing `--mobile-sticky-action-offset` seam. The Footer's bottom padding grew (96 / 112px) so the page's last line is never under it. Same `aria-label`, `href`, `target`/`rel`, and settings-driven visibility. Product-page "Chat on WhatsApp": neutral outline button, dark label, Teal Green glyph (green text would fail contrast).

**Skip link:** unchanged behaviour (`sr-only` until focused, explicit focus to `<main>`). On focus: a primary chip (white on `#0d631b`, 7.45:1), mono caps, 44px tall, `fixed` top-left at `z-[60]` — above the sticky header and sheets.

**Deviations from Stitch (and why):**
- Home: no promo banner, STL marketplace strip, testimonials, mini-stats or hero photo — no real data or asset (route doc, D7). The hero visual is the real logo on the blueprint grid. Category tiles are tonal (categories have no images). The hero's two-column split starts at 1024 (Stitch md 768): at 768 the 48px display heading would wrap to five lines in half the width.
- Shop: no photo in the banner (dark blueprint band instead); no price slider, material radios or "Request slot" promo box (no API/real equivalent; Bring your idea is in the header, footer and home CTA); no grid/list toggle; numbered pagination replaced by Load more (cursor API, COMPONENT-MIGRATION); result count is "N shown", not "N results found" (no total exists). Filter aside appears at 1024 (Stitch md 768) and the drawer covers 768–1023 — the point of this batch's card-width fix. Legends use `on-surface-variant` instead of `outline` (4.4:1 on the drawer's `#f9f9ff` would miss 4.5:1).
- PDP: actions sit **above** specs and description (Stitch: below), so long descriptions never push Add to cart off-screen. No stock pill, SKU, datasheet, material story, reviews or pairings (no data). Rating star in amber-600 (contrast, §12.12). Spec tiles 2-up on phones per RESPONSIVE-SPECS.
- WhatsApp: Teal Green fill instead of `#25d366` (contrast, above).

**Accessibility decisions:** one `h1` per page and `h2` sections (Home 4, PDP 2); every decorative layer `aria-hidden` (hero panel and orbs, banner grid/glow, CTA glow, skeleton list); visible labels unchanged where tests and users rely on them; filter count exposed via `aria-label` (concatenated badge text read "Filters1"); result count in a `role="status"`; drawer is a labelled modal dialog; thumbnails keep `aria-current`; breadcrumb `aria-current="page"`; all hover motion (card lift, image zoom, arrows, icon tiles, FAB) off under `prefers-reduced-motion`; ≥44px targets for the new controls (stepper 48, search buttons 44, drawer buttons 40–52, FAB 56, skip link 44).

**Bug found and fixed during QA:** Tailwind emits the custom `desktop:` variant **before** the default `sm:`, so `sm:grid-cols-2 desktop:grid-cols-4` resolved to 2 columns at ≥1024 (category bento stuck at 2-up, home grid at 2-up on 1024). Grids that combine `sm:` with a 1024 rule now use the default `lg:` (same 1024px) so the cascade order is correct; elements that use `sm:` and `desktop:` on different properties are unaffected.

**Targeted tests:**
- Unit (2248 → 2290, +42 across 233 files): `ShopView` (+8: one h1 + labelled search; status count; drawer opens as a labelled modal with focus inside and scroll lock; ticking in the drawer pushes the same URL and keeps it open; close/reopen keeps the URL-driven checks and never pushes; Escape and Show results return focus; Clear filters in the drawer; closes at the desktop breakpoint), `ProductDetailView` (+9: breadcrumb links/current; h1 → h2 outline; specs as term/definition pairs; rating only with reviews; no invented rating/stock/SKU/datasheet; no-image placeholder; anonymous STL cart/offer/wishlist sign-in links with returnTo; no offer without `can_offer`; description line breaks), STL absence checks now assert the exact term labels (the colon labels they used would have passed vacuously), `ProductImageGallery` (+4), `ProductGrid` (+2), Home `page.test` (+4: section order/outline, real links, category hrefs, no invented content), `HeroSection` (+2), `FloatingWhatsAppButton` (+4), `SkipLink` (+1), `WhatsAppChatButton` (+1), new `RatingSummary.test` (3), new `ui/layoutPrimitives.test` (4).
- E2E: new `storefront-pages.spec.ts` (12, smoke project): Home/Shop/PDP at 320/375/768/1024/1280/1440 (no overflow, one h1, cards ≥260px, aside vs drawer per width, breadcrumb); drawer at 768 by keyboard (focus inside, scroll lock, filter → URL, Escape returns focus to "Filters, 1 active", state survives reopen, Show results); drawer at 375 (fits, Clear filters); PDP thumbnails by keyboard + spec terms + category link; skip link topmost over the header and Enter focuses `<main>`; FAB fill `rgb(18,140,126)`/white, 56px, `z < 40`, clear of the footer's last line, focus ring; Home CTA/section links. `product-detail.spec.ts` STL absence check updated to exact terms (same intent).

**Visual QA** (Edge; mocked real-shaped data: square, wide and missing images, 5-image gallery, long title, long description with line breaks, physical/STL, unavailable, offer-capable, cart-capable, rated, signed in and out; 320 / 375 / 768 / 1024 / 1280 / 1440):
- No horizontal overflow on Home, Shop, PDP (physical, STL, no-image/unavailable) at any width. H1 36px below 768, 48px above.
- 1280 vs Stitch: Home — split hero, 2×2 + 4 bento, 4-up featured row, centred feature tiles, green CTA band, footer. Shop — dark search banner, 256px aside + toolbar + 3-up cards (275px) + centred Load more. PDP — breadcrumb, 7/5 split, display title, 48px price, action card, 2×2 spec tiles. Differences are the listed deviations.
- Drawer at 375 / 768: full-height left sheet within the viewport, dimmed + blurred page, FAB under the scrim.
- Long title wraps (no clipping); long description wraps; no-image panel; unavailable callout; STL shows no physical specs or stepper; Make an offer only on the offer-capable STL.
- FAB: never over the footer's last line at the page end; under the header when scrolled.

**Gate:** lint ✓ (0 errors / 0 warnings; the first lint run flagged a raw `<a>` in a new test fixture — test-only fix, lint re-run green) · typecheck ✓ · unit **2290/2290** (233 files) · build ✓ · E2E (smoke) **199/199** (187 + 12 new). The single E2E run had 5 failures, all in admin specs (`admin-orders` ×3, `admin-operations`, `admin-payments`), all showing the documented "We couldn't verify your session" state: the mocked `/me` read hit its client timeout while the dev server compiled the admin routes under full parallel load. No admin, auth or API code changed in this batch; the specs passed 16/16 in isolation and the five tests 18/18 over three repeats. No application code changed after the gate, so per §4 only the affected specs were re-run.

**Deferred to Batch 4+:** `PageHeader` (with the account/admin pages that share §64), related products on the PDP (no related-products endpoint; a category query would be new data behaviour), header search, the wishlist page cards (`WishlistList`, Batch 7), cart line items/stepper (Batch 6), admin chrome removal (Batch 9). The dev-server E2E load flake on cold admin routes is worth a separate look (e.g. a production-build E2E server or fewer workers), outside the redesign.

### Between Batch 3 and Batch 4 — E2E harness stabilized (test infrastructure only)

The dev-server cold-compile flake above (Batch 2 `/login`, Batch 3 admin routes) is fixed at the source: `npm run test:e2e` now runs against its own **production build** (`next build` + `next start` on `:3100`, output in `.next-e2e/`) instead of `next dev` on `:3000`, so no route compiles on demand during a run. Application timeouts, workers and retries are unchanged. No application code changed. Result: the previously flaky admin/auth group 58/58, then 135/135 over three repeats; full suite 199/199. Details: `docs/setup/frontend-setup.md` → "Default E2E Smoke Tests".

### Batch 4 — Authentication and verification surfaces: COMPLETE

**Route inventory (current mounted routes only; nothing added because Stitch has a design for it):**

| Route | Stitch | Captcha | Security-sensitive behaviour kept as-is |
|---|---|---|---|
| `/login` (+ MFA verify step in the same page) | A1 HIGH; MFA step DERIVED (A4 styling) | no | returnTo validator, `/me` invalidation + user-scoped cache clear before navigation, challenge_id in memory only, burned/expired challenge forces a fresh login, Problem.code → safe copy |
| `/register` | A2 HIGH | yes | single-use token reset after every attempt, enumeration-safe success, 429 copy, success-heading focus |
| `/forgot-password` | A3 HIGH | yes | enumeration-safe success, captcha reset, 429 with Retry-After |
| `/reset-password` | DERIVED (A3 card) | no | neutral first render, fragment read + sanitised in one client effect, token in memory only, 400/410/422/429 mapping |
| `/verify-email` | DERIVED (A3 card + §48) | no | one-shot ref guard, fragment cleared, invalid/used/already-verified collapse to one state |
| `/verify-email/resend` | DERIVED (A3 card) | yes | fixed 120s cooldown, two-announcement live region, non-live ticking countdown |
| `/admin/mfa/setup`, `/admin/mfa/recovery-codes` (inside AdminShell) | DERIVED (A4 card styling) | no | secret shown once, otpauth URI redacted, recovery codes one-time with acknowledgment |

Not built: the Stitch Admin Login (admins use `/login` + MFA), social login, remember-me, magic links, passkeys.

**Shared presentation:** new `components/auth/AuthShell.tsx` — `AuthShell` (blueprint canvas + centred card inside the existing storefront chrome) and `AuthCard` (card only; used inside AdminShell for the MFA pages), plus `AuthBackToLogin` and `AUTH_INLINE_LINK_CLASSES`. Layout only: optional split wordmark (`aria-hidden`), status glyph (§48 circle, decorative), mono eyebrow, the page's single `h1` (programmatic focus target only when the page passes a ref), description, body, footer strip. It owns no form, request, validation, captcha or live region. Tokens `max-w-auth` (440) / `max-w-auth-wide` (640). Field primitives gained presentation-only props: `TextField`/`PasswordField` `leadingIcon` and `TextField` `mono` (one-time codes). `CaptchaWidget` gained `align="center"` (default `start` keeps Contact/BYI unchanged). Icons + `arrow-back`, `lock`, `content-copy`, `print`.

**Chrome decision (Task 11):** auth pages keep the storefront Header and Footer (BEKAA3D-ROUTE-MIGRATION "Auth" shell) so users can navigate away; no route-group change. The MFA pages stay inside AdminShell (Batch 9).

**Per page:** Login — 440 card, split wordmark, "Log in", leading-icon email/password, "Forgot password?" (→ `/forgot-password`) between password and submit, full-width lg submit with pending spinner, footer strip "New to Bekaa3D? Create an account" (→ `/register`). MFA step — same card, lock glyph, "Two-factor authentication", mono code input (`inputmode=numeric`, `autocomplete=one-time-code`, single field, unchanged payload), Verify shows busy and ignores a second click while the single-use challenge is in flight, ghost "Use a recovery code instead". Register — 640 card with divided header, eyebrow, only email + password + captcha, success card with a link to the existing resend route. Forgot / Reset / Resend — left-aligned A3 card, "Back to log in" mono link. Verify — one card, state glyph per state, primary/secondary link buttons. MFA setup — "Step N of 3" eyebrow, setup key in a mono tonal panel. RecoveryCodeList — mono 2-column code grid, outline Copy/Print.

**Deviations from Stitch:** one canvas texture (green 40px blueprint grid, DESIGN-SYSTEM §12.20) instead of per-page patterns; forgot card 448 → 440; one 16px card radius; solid primary CTA instead of the login/forgot gradient (§12.9); all auth `h1`s use `headline-lg` (Stitch login used `headline-md`); no social buttons/divider, remember-me, Stitch-only registration fields (name, phone, country, confirm password, terms), status bar claims ("servers online", "AES-256"), rotating rings, parallax, side photo, decorative icon strip or timed success overlay; Stitch headings replaced by the app's real titles ("Log in", "Create your account", "Reset your password"); below 640px the card is full-bleed with a 16px gutter so the provider's fixed 300px captcha frame fits at 320 (it centres and spills ≤6px into the card padding rather than overflowing the page).

**Login geometry E2E (deliberate update):** `login-session.spec.ts` asserted form ≤420 at ≥768 and ≥ viewport−10 below. The card's padding makes those numbers obsolete; the spec now asserts the intent directly: form centred at every width, ≤440 and ≥300 from 640px, ≥ viewport−40 below, `h1` clear of the 64px sticky header, no overflow. The keyboard walkthrough now includes "Forgot password?" (with a visible focus ring) between show/hide and submit.

**Targeted tests:** unit 2290 → 2314 (+24): new `AuthShell.test` (5: one h1, ref-only focus target, decorative brand/glyph, owns no form/live region, back link); Login (+9: one h1 + forgot/register links, no social/remember-me, links never alter returnTo, four unsafe returnTo forms → `/`, pending submit busy/disabled, MFA single h1 + numeric one-time-code + no second verify while pending, recoverable MFA failure re-enables Verify); Register (+2: success links to resend; only email/password, link to /login); Reset (+2: token never rendered/stored/in URL across submit; one h1 + back link); TextField (+2), PasswordField (+1), CaptchaWidget (+2: centred widget unchanged; centred unavailable state loads nothing). E2E 199 → 206: header Sign in on `/about` → `/login?returnTo=%2Fabout` → log in → back on `/about`; new `auth-pages-responsive.spec.ts` (6 routes × 320/375/768/1024/1280/1440: one visible h1 below the header, no overflow, every control in the viewport, a simulated 300×65 captcha frame unclipped).

**Visual QA** (Edge, production build, mocked anonymous session; 320 / 1280 plus the E2E widths): login, register, forgot, reset, verify (invalid), resend, login validation errors, MFA step, forgot success. 1280 vs Stitch: login and register match the A1/A2 card composition (wordmark, centred heading, mono labels, leading icons, full-width green CTA, footer strip / divided header); forgot matches A3 (left heading, description, captcha, CTA with arrow, divider, "Back to log in"). Derived pages share the same card, glyph and link family. Bug found and fixed in QA: the resend description rendered a literal `\u2019` (JSX attribute strings do not decode JS escapes) — now `&rsquo;`.

**Known, unchanged:** the MFA countdown `<p role="status">` updates every second (pre-existing; the resend page already shows the non-spamming pattern) — worth aligning in Batch 11.

**Gate:** lint ✓ (0 errors / 0 warnings) · typecheck ✓ · unit **2314/2314** (234 files) · build ✓ · E2E (smoke, production build) **206/206**, first run, no retries needed.

### Batch 5 — Account shell, Profile, Addresses, Notifications: COMPLETE

**Direct vs DERIVED:** no direct Stitch page exists for any Batch 5 route. The shell follows the dominant customer sidebar (COMPONENT-SPECS §40 / DESIGN-SYSTEM §12.14 recommendation, C2–C7). `/account/profile` is MEDIUM against C7 (the `user_profile` export is not in `docs/design-reference/stitch/`; PAGE-SPECS C7 and the C5 wishlist screenshot were the references). `/account/addresses` is DERIVED from the C7 "Primary Address" box + §18 DEFAULT tag; `/account/notifications` is DERIVED from the §46 notification rows. `/account` still redirects to `/account/profile` (no C1 dashboard — its KPI/asset data does not exist).

**Account shell / navigation (`AccountLayout`, `accountNavItems`):** wraps every `/account/*` route inside the storefront chrome (unchanged; no route-group change, no admin change) in the shared `Container`. One `<nav aria-label="Account">`, two presentations: **≥1024** a 256px sticky side panel (card surface, mono "My account" caption — `aria-hidden`, the nav is already labelled), 44px+ items with a decorative icon, active = `aria-current="page"` + primary ink + bold + `surface-container-low` + 4px right rail (§12.14 canonical), hover `surface-container-high`, Log out in error ink under a divider. **<1024** (Stitch has no account mobile design; its bottom nav would collide with the WhatsApp FAB and the footer) the same links become a horizontally scrollable tab strip above full-width content (active = 2px primary underline + bold), Log out last. The nav is never hidden and never squeezed beside a narrow column. Same 6 real destinations (Profile, Orders, Offers, Wishlist, Addresses, Notifications); no Stitch STL Downloads / Reviews / Account Settings. The registry gained only an `icon` per item. `LogoutButton` gained a presentation-only `appearance="nav"` (admin keeps `default`); logout behaviour unchanged.

**PageHeader decision:** introduced `components/ui/PageHeader` now — 3 genuine call sites (Profile, Addresses, Notifications). Optional mono eyebrow, the page's single `h1` (headline-lg), description, optional actions (stacked under the text below 768), optional `meta` rendered in the **same parent as the h1** (ready for the order/offer detail status pills in Batch 7), optional `headingRef` (focus target only when passed). No data, state or business logic.

**Profile (`ProfileCard`):** still strictly read-only (VS-006; E2E asserts zero form controls), so there is no save / pending / success state to style; Stitch's edit link, password form, preference toggles, avatar upload, name/title, PRO badge and share buttons are not built. Layout: PageHeader in every state (loading and error now also have the h1); 12-col bento ≥1024 — identity card (decorative initial avatar, "Signed in as", the email once, mono "Member since <Month YYYY>" from the real `createdAt`, hidden if unparsable) + "Account details" card (`<dl>`: Verification status with icon + text, Account status "Active" — derived exactly as before). Unverified warning + resend link unchanged; card-shaped skeleton; error card keeps the same retry (refetch of the canonical session query).

**Addresses:** `AddressBook` logic untouched (mutations, notices, page errors, delete confirmation, 404 / limit / CSRF mapping, focus). PageHeader with "Add address" (+ icon) as the action when addresses exist. `AddressCard`: label `h2`, lime "Default" badge (text) plus a primary border on the default card, a `<dl>` with visible mono terms Recipient / Phone (`dir="ltr"`, tabular numerals) / Location (street, area — city, governorate) and a tinted Landmark notes panel; actions in a footer row (Edit outline, Set as default secondary, Delete outline with a trash icon), 44px targets, accessible names unchanged ("Edit Home", "Set as default: Home", "Delete Home"); the card itself is not clickable. Grid: 1 → 2 (768–1023, tab-strip layout) → 1 (1024, beside the sidebar) → 2 (≥1280). Empty state: dashed card + §49 empty state with a location glyph, same "Add an address" action. Dialog: same `DialogShell` (focus trap, busy lock, Escape/backdrop, trigger focus return) with the panel override restyled (p-5 / p-8), mono eyebrow + `headline-md` title, a tinted default-checkbox row (`accent-primary`, 20px), Cancel as outline, divided footer. Max-limit, 422 field mapping and failed-write retention are unchanged (dialog stays open with the values). `DefaultAddressSelector` is not mounted anywhere and was left as is.

**Notifications:** real contract only — no categories, filters, bulk "mark all", preferences or unread count were added. `NotificationItemModel` gained optional `createdAt` (the real `created_at`, mapped in the adapter), shown as a mono `<time datetime>`. Rows inside one list card: decorative type glyph (incl. `custom_request` → lightbulb), title as an `h2` naming the row's `article`, "Unread"/"Read" text badge (plus a tinted background and primary rail for unread — never colour alone), body, and the same single Mark read / Mark unread action (outline, 44px). Load more now uses the shared `LoadMore`. Loading = row-shaped skeleton, error = card with the same retry, empty = §49 empty state with a bell glyph.

**New / reused components:** new `ui/PageHeader`; Icon + `shopping-bag`, `sell`, `favorite`, `location-on`, `notifications`, `logout`, `edit`, `delete`, `call`, `schedule`; `EmptyState` gained an optional decorative `icon` (default unchanged). Reused: `Container`, `Button`, `StatusBadge`, `Alert`, `EmptyState`, `LoadMore`, `DialogShell`, `ConfirmDialog`, field primitives.

**Accessibility decisions:** one nav landmark labelled "Account" at every width with exactly one `aria-current="page"`; nav icons `aria-hidden`; focus uses the global box-shadow ring (the scroll strip has padding so the ring is not clipped); every page has exactly one h1 in every state, cards/rows use h2; address and profile facts are `<dl>` pairs; default / unread / verified are text, not colour; the address-book live region is kept; reduced motion disables transitions and skeleton pulse.

**Stitch deviations:** sticky side panel inside the storefront chrome instead of a full-height fixed sidebar with its own top bar (account keeps the storefront header — route-migration "Account" shell); scrollable tab strip instead of the §54 mobile bottom nav below 1024; sidebar from 1024 (Stitch: 768) so content keeps useful width; heavier-stroke outline glyphs instead of FILL-1 active icons (local SVG set); 12px card radius (§12) rather than C7's 8px; no user chip in the nav (the email is the profile's identity; repeating it adds nothing); no dashed "Add new address" tile — the header action and the empty-state action are the only add triggers (one control per action); no search, help, notification bell (no unread-count endpoint) or Stitch-only profile sections.

**Responsive QA** (Edge, production build, mocked real-shaped data incl. long Lebanese names / streets / areas / landmarks and long notification text; 320 / 375 / 768 / 1024 / 1280 / 1440): no horizontal overflow on Profile, Addresses (list and open dialog) or Notifications; the tab strip scrolls and every link is reachable below 1024, side panel beside the content from 1024; address actions wrap inside the card, phone readable, dialog within the viewport with a usable governorate select; notification body and timestamps wrap. 1280 vs the C5/C7 references: same sidebar composition (caption, icon items, active rail, logout under a divider), headline-lg title + description, white bordered cards with mono labels. States checked: unverified profile, addresses empty, notifications error.

**Tests:** unit 2314 → 2331 (+17): new `PageHeader.test` (4); `ProfileCard` (+3: one h1 in loading/error/loaded, member since + unparsable, email once + dl/h2); `AddressCard` (+2: dl terms; default as text, card not a control, named actions); `AccountLayout` (+2: plain accessible names / decorative icons / one current; Log out last of 7 controls); `NotificationItem` (+4: article/h2, `<time datetime>`, no time when missing/invalid, custom_request row + action); `notificationAdapter` (+1 createdAt); `EmptyState` (+1 icon). E2E 206 → 213: new `account-pages-responsive.spec.ts` (6 widths × Profile/Addresses/Notifications: one h1, no overflow, nav discoverable with every link visible after scroll + current marked + Log out, beside ≥1024 / above <1024, 44px address actions inside the card, edit dialog fits and keeps focus/values, notification `<time>` and Read/Unread text; plus a keyboard walk of the tab strip at 375 with visible focus). `account-profile.spec.ts` deliberate update: the old "≥768 → nav narrower than the viewport" check described the previous sidebar; it now asserts the intent directly (≥1024: ≤256px and left of the content; below: above the content).

**Gate:** lint ✓ (0 errors / 0 warnings) · typecheck ✓ · unit **2331/2331** (235 files) · build ✓ · E2E (smoke, production build) **213/213**, first run.

**Deferred to Batch 6+:** Orders, order detail, Offers and Wishlist bodies keep their pre-redesign headings inside the new shell (Batch 7 adopts `PageHeader`); the dashed add-address tile if the owner wants it; a header notification bell (needs an unread-count endpoint).

### Batch 6 — Cart and Checkout: COMPLETE

**Scope:** `/cart` and `/checkout` (incl. the checkout result / unknown-outcome / payment-not-started states rendered by `CheckoutView`). Visual only: no endpoint, request body, query key, mutation, CSRF, idempotency, redirect, eligibility, consent or Problem.code mapping changed. `src/lib/cart/*` and `src/lib/checkout/*` are untouched. Orders, payment retry/result pages, Offers, Wishlist, Contact, BYI and Admin were not redesigned; the only shared inheritance is `OrderSummary`'s new opt-in `emphasis` prop (default rendering unchanged, so the account Orders page is untouched).

**Stitch references:** `your_cart_bekaa3d_precision_engineering` (S6) and `checkout_bekaa3d_precision_engineering` (S7), both direct. COMPONENT-SPECS §26 (pill stepper), §28/§34 (radio / payment option cards), §33 (step header), §35 (summary cards), §36 (cart line item), §49 (empty state).

**Cart design** (`CartView`, `CartPage`, `CartLineItem`):
- Shared 1440px `Container`; S6 page header: display-role h1 "Your cart" (still the focus target after a remove) + one-line description.
- 8/4 grid from 1024px (`desktop:col-span-8 / 4`), one column below; summary after the lines in DOM and visual order.
- Line card (§36): white, 12px, `outline-variant/30` hairline, 128px media tile (full-width 128px tall below 768, as S6) with a decorative fallback glyph (image / deployed-code for STL) when there is no cover image; `ProductTypeBadge` as the type tag; title (title-sm, wraps, never truncated) linking to the product when a slug exists; price block right-aligned from 768.
- Pill stepper (§26) at 44px targets with plain-language names kept ("Decrease/Increase quantity of X", group "Quantity of X"), still bounded by the server `max_quantity` and still disabled while a write is in flight. **STL lines: no stepper, no input** — "Quantity: 1" in mono + "STL files are sold one copy per order."
- Remove: ghost button with a trash glyph, 44px, error tint on hover, name "Remove X from cart". No clear-cart action (no backend route).
- Summary (§35 cart): lavender 16px panel, sticky `top-24` (96px = 64px header + 32px) from 1024 only; h2 "Cart summary" names the region; **item count only** and the honest "total is calculated at checkout from current prices" note; attention / price-change callouts; `lg` primary CTA (link when the cart can proceed, disabled button otherwise); "Continue shopping" → `/shop`.
- Empty: dashed card + §49 empty state (cart glyph) + "Browse the shop" → `/shop`. Loading: line-card and summary-shaped skeletons (`surface-container-low`, pulse off under reduced motion) inside the same `role="status"`. Error: `Alert` + Retry (unchanged behaviour).

**Cart line / price-change presentation:** a server-flagged change shows "Price when added" (muted, struck through) and "Current price" (Hanken 20/600) with **visible mono labels** — the strike-through is decoration, the labels carry the meaning — plus a warning callout (icon + "The price has changed since you added it. Checkout uses the current price."). Nothing is accepted in the cart; acceptance still happens only at checkout. Unpurchasable lines: error callout with the existing safe reason copy, a red-tinted card border, a dimmed image, Remove still enabled, no stepper. Over-cap lines: warning callout with the cap and the "Reduce to N" action (44px). No line totals are computed (CartRead has none).

**Checkout layout** (`CheckoutView`): same Container; display h1 "Checkout" + description in every state (one h1). Form = 12-col grid from 1024: **7 columns of numbered step cards** (white 12px cards, `p-5 → p-8`) and a **5-column summary** sticky at `top-24` (clear of the 64px sticky header; verified by E2E while scrolling). Below 1024 one column: decisions first, then the summary with Place order (DOM order = visual order = keyboard order). Problem notices sit above the steps in the focusable `problemRef` container (collapsed when empty). Steps: **1 Delivery or pickup** (or **1 Delivery** for STL-only: an info step explaining email delivery, no fulfillment controls), **2 Payment**, an unnumbered **Order note** card (optional; kept between payment and consents, its original place), **3 Confirm**.

**Step header** (new `CheckoutStepHeading`, §33): 32px circle (2px primary outline with the number; filled primary + check once that step's choice is made — decoration only, `aria-hidden`, never gates submit) beside an h2 (headline-lg, 24px below 768). It renders **as the fieldset's `<legend>`** (HTML allows heading content in a legend), so each group's accessible name and the page's heading outline are the same visible text.

**Fulfillment presentation** (`FulfillmentSection`): Delivery / Pickup as radio cards (new shared `choiceCardStyles`: native 20px radio kept as the control, card reacts via `:has()` — primary border + ring + tint when checked, hover primary border, disabled = tinted surface with fully legible text). Pickup still only when the shop has a pickup address; pickup shows the configured location (address + hours, wraps) and the same Contact phone field. ADR-024: no shipping fee, zone, threshold or estimate anywhere; the existing courier-fee copy is now an info callout under the address list. Mixed carts keep the "STL files aren't shipped" note (mail glyph).

**Address selection:** saved addresses as radio cards in a 1 → 2 column grid (768+), Batch 5 language: label as title, lime "Default" text badge (§18), the existing display lines; the default address is still pre-selected by the unchanged `chooseFulfillment` logic. "Manage addresses" / "Add an address" still link to `/account/addresses`; no inline address creation. Loading = text + card skeleton; error = error card + Retry (unchanged).

**Payment-method presentation** (`PaymentMethodSection`, §34): Online and Cash as option cards. No card fields, no provider names or logos (the online provider is a mock in dev/staging); the online card's glyph is the generic "continues on another page" icon and its copy is unchanged ("counts as paid only once the payment is confirmed"). Cash still shown only when public settings enable it; **ineligible cash** (STL in the order) is disabled, keeps legible text, shows a "Not available" text tag and keeps the reason as its accessible description. The public cash maximum is still shown as information only; the server's cap / block refusals still surface through the unchanged error mapping.

**Consent treatment** (`ConsentCheckboxGroup`): step 3 "Confirm"; each consent is a bordered row whose whole surface is the `<label>` (20px native checkbox, text wraps), checked = primary border, error = red border + soft ring + error text with icon (`aria-describedby` / `aria-invalid` unchanged). Same three backend booleans, same conditions (terms always; digital final sale while an STL line remains; cash terms when cash is chosen), **never pre-ticked**. The wording is unchanged and remains **PENDING LEGAL REVIEW** (`checkoutCopy.ts`, open item Q8) — the redesign does not approve it.

**Price-change acceptance** (`PriceChangeConflictBanner`): a warning card (`role="alert"`, assertive) listing each changed line with **visible "Was" (struck) → "Now" (bold) labels**, the "Nothing has been charged" statement and the single "Accept new prices" action; Place order stays disabled with an inline reason until the customer accepts; accepting never submits; after acceptance an info status says so. The request body still carries `accepted_price_changes`, so a resubmission still gets a **new** idempotency key (unchanged `checkoutIdempotency`).

**Dropped lines** (`CheckoutLineIssues`, `CheckoutConfirmation`): warning card with each line in its own bordered row and the name in bold; refused / already-owned / over-cap lines keep the "Review your cart" link (now with an arrow, 44px row). Dropped STLs on a placed order keep the exact "not included … you weren't charged for them" copy and never appear in the order items; an online order with dropped lines still waits for an explicit "Continue to payment".

**Idempotency safety:** `submit`, `handleSubmit`, the `inFlight` ref guard, `tracker.keyFor/retire`, phase transitions, `followPaymentRedirect` and every `describeCheckoutError` effect are byte-for-byte unchanged (verified by diff: only JSX/className lines and indentation moved). Place order is the single submit control (`isLoading` → disabled + `aria-busy` + spinner); the whole form's fieldsets are disabled while submitting; a polite "Placing your order…" status is announced. The unknown-outcome state still offers only the same-body/same-key "Try again". Existing double-click, same-key retry and new-key-after-acceptance tests pass unchanged.

**Checkout summary** (`CheckoutItems`, §35 checkout): white 16px panel, h2 "Order summary" naming the `<aside>`; 64/80px thumbnail (decorative; fallback glyph), title, mono primary unit price + "each", type + quantity meta, "Price updated" (icon + text) for flagged lines; the honest "total is calculated … when you place your order" note; Place order (lg, full width) inside the card. **No subtotal / shipping / tax / total rows** — CartRead has none. Server totals (subtotal, total, line totals, amount due, delivery note, estimated dispatch) appear only on the confirmation from the 201 `CheckoutRead`, via `OrderSummary` (`emphasis`: total in the summary-total role) — nothing summed in the browser.

**Result states:** cash confirmation = check glyph on lime, "Order placed", mono order number, info callout "Payment due in cash …" + "hasn't been paid yet"; online without a redirect = "awaiting payment" with the open-in-new glyph (never a success treatment); items + totals card; fulfillment card (delivery address or pickup location, courier-fee note, estimated dispatch); "View order" (primary) + "Continue shopping" (outline). Payment-not-started and unknown-outcome states are cards with warning callouts; their focus targets are unchanged.

**New / reused components:** new `checkout/CheckoutStepHeading`, `checkout/choiceCardStyles.ts`; Icon + `check`, `local-shipping`, `storefront`, `payments`, `open-in-new`, `receipt-long`; `OrderSummary` + optional `emphasis`. Reused: `Container`, `Button` / `buttonLinkClassName`, `Alert`, `EmptyState` (icon), `StatusBadge`, `ProductTypeBadge`, `PriceDisplay` (`summary` size), `TextField`, `TextAreaField`. No separate `QuantityStepper` component (one call site).

**Accessibility decisions:** one h1 per state; steps are h2 legends naming their groups; summary is a labelled region (cart) / complementary landmark (checkout); stepper, remove and reduce buttons named with the product; price changes, unavailability, cash ineligibility, defaults and step completion are all stated in text (colour/strike-through are secondary); consent text is the checkbox's label; field errors linked by `aria-describedby`; problems still focus the announced notice container; 44px controls throughout (stepper, remove, CTAs, text-link rows); radios/checkboxes 20px with the global focus ring; transitions and skeleton pulse off under reduced motion; keyboard order = visual order at every width.

**Stitch deviations (and why):**
- Cart summary has no Subtotal / Shipping / Tax / Total Due rows, no discount code, no payment-method logos; checkout summary has no totals and no FREE shipping chip — CartRead has no totals, ADR-024 forbids a shipping charge, there is no coupon contract, and no real provider exists (D7 / commerce rules). The §35 coupon overflow defect therefore cannot occur.
- No "Frequently Bought Together" rail (no recommendations endpoint).
- Checkout keeps the storefront header instead of S7's reduced "SECURE CHECKOUT" header (navigation structure unchanged; no "secure" claim added).
- No Shipping-information form, Billing step or card fields — the real flow is saved-address selection / pickup and an online redirect or cash.
- Step titles are the real decisions ("Delivery or pickup", "Payment", "Confirm") at headline-lg; completed state = filled circle + check (§33 left it undesigned).
- Cart CTA uses the shared `lg` primary button (mono label) rather than S6's one-off Hanken "Large CTA", matching the checkout CTA and the Batch 1 button hierarchy.
- Line-card digital "download badge" not used: STL files are emailed, never downloaded from the site (ADR-019).

**Responsive QA** (Edge, production build, mocked real-shaped data incl. a 110-character product name, long Lebanese address strings, missing images, price-changed / STL / unavailable / over-cap lines; 320 / 375 / 768 / 1024 / 1280 / 1440): no horizontal overflow on /cart or /checkout at any width; all four cart line states visible and stated in text; every line action ≥44px and inside its card; summaries beside the content from 1024 and pinned below the header while scrolling, below the content under 1024; delivery with long addresses, pickup, STL-only (cash "Not available"), price-change banner and refused-lines notice all fit at 320; legal text wraps. 1280 vs S6/S7 screenshots: same 8/4 and 7/5 compositions, card radii/hairlines, lavender cart summary vs white checkout summary, step circles + large step headings, option cards with the selected border, mono labels/prices.

**Tests:** unit 2331 → **2359** (+28): `CheckoutView` (+7: one h1 + step h2s naming groups in order + labelled summary; summary has unit prices only, no total/shipping/tax/discount; Place order after every decision in DOM order; STL-only Delivery step without a fulfillment group; submitting = busy + disabled + locked choices + announced, still one request; price change Was/Now + blocked reason; cash confirmation one h1, unpaid wording, Continue shopping), `CartLineItem` (+5), `CartPage` (+3, incl. no clear-cart action), `FulfillmentSection` (+4), `PaymentMethodSection` (+3, no provider names / card fields), `ConsentCheckboxGroup` (+1), `PriceChangeConflictBanner` (+1), `OrderSummary` (+1, `emphasis` adds nothing), new `CheckoutStepHeading.test` (3). No existing assertion was changed or weakened. E2E 213 → **226** (+13): new `cart-checkout-responsive.spec.ts` (6 widths × cart + checkout, plus a 320px pickup / price-change / refused-lines / STL-only walk); the existing `cart.spec.ts` and `checkout.spec.ts` (incl. keyboard-only, double-submit, same-key retry, price-change new key, dropped STL) pass unchanged.

**Gate:** lint ✓ (0 errors / 0 warnings) · typecheck ✓ · unit **2359/2359** (236 files) · build ✓ · E2E (smoke, production build) **226/226**, first run.

**Deferred to Batch 7+:** Orders / order detail / payment result and retry pages (they still use `OrderSummary`'s default rendering), Offers (incl. `OfferCheckoutPanel`), Wishlist; a reduced checkout header if the owner wants S7's variant; product thumbnails in the cart when the media host is configured for real images (the fallback tile is what renders in E2E).

### Batch 7 — Orders, order detail, payment UI, checkout return, Offers, Wishlist: COMPLETE

**Scope:** `/account/orders`, `/account/orders/[id]` (incl. customer actions, payment status / polling / retry / hold countdown), `/checkout/return`, `/account/offers`, `/account/offers/[id]` (incl. `OfferCheckoutPanel`), `/account/wishlist`. Visual only: no endpoint, request body, query key, polling rule, idempotency key rule, redirect, capability flag, offer move, cancellation rule, receipt/problem action or Problem.code mapping changed. `src/lib/**` is untouched. Contact, Bring Your Idea and Admin were not redesigned (the admin offer page keeps the original rendering of the shared offer facts/history; see below).

**Direct vs DERIVED:**

| Route | Reference | Class |
|---|---|---|
| `/account/wishlist` | C5 `my_wishlist_bekaa3d_precision_engineering`, COMPONENT-SPECS §11c, §49 | Direct |
| `/account/orders` | C2 `order_history_bekaa3d_precision_management` (table → rows), §43 | MEDIUM / derived to rows |
| `/account/offers` | C3 `offer_history_bekaa3d_precision_management` (table → rows), §17 offer table | MEDIUM / derived to rows |
| `/account/orders/[id]` | none — account shell + PageHeader + §35/§45/§56 + Batch 6 line language | DERIVED |
| `/account/offers/[id]` | none — account shell + PageHeader + C3 language + §45 timeline | DERIVED |
| `/checkout/return` | none — Batch 6 checkout result card + §48 result card | DERIVED |

**Shared building blocks (new `components/account/accountUi.tsx`, presentation only):** `ACCOUNT_CARD` / `ACCOUNT_TERM` / `ACCOUNT_TEXT_LINK` class tokens; `AccountSection` (card section whose visible h2 names the region via `aria-labelledby`; optional decorative icon; `tinted` lavender §35 variant); `AccountListSkeleton` (one labelled `role="status"`, pulse off under reduced motion); `AccountErrorCard` (`role="alert"` message + outline "Try again"); `AccountSessionCard` (warning card + "Sign in" with the caller's returnTo); `AccountBackLink`; `AccountFact`; `AccountThumb` (decorative tile, Batch 6 fallback glyph). `EmptyState` gained an optional `actionHref` (link action; existing button behaviour unchanged). Reused: `PageHeader`, `StatusBadge`, `Alert`, `Button` / `buttonLinkClassName`, `PriceDisplay`, `DialogShell`, `Container`, `Icon`, `ProductTypeBadge`.

**Orders list (`OrderHistoryList`, page):** PageHeader ("Orders" h1 + description; "newest first" verified in `orderTypes.ts`). One list card of rows (C2's table would need horizontal scrolling inside the account column): mono primary "Order B3D-…" as the row's **single link**, stretched over the row; mono "Placed <date>"; status pill (text); a `<dl>` with visible mono terms Total (mono bold) / Payment / Fulfillment; an info chip "Payment due in cash: $X" (exact original wording, E2E-asserted) for unpaid cash orders; a decorative "View details ›" cue (`aria-hidden`, inside the link's hit area — no second control). No tracking, ETA, thumbnails or payment status (the summary contract has none). Loading = row skeleton; error = error card + retry; signed-out = session card; empty = §49 (shopping-bag glyph) + "Browse the shop" link; failed "Load more" keeps the loaded rows and shows an inline error; cursor paging unchanged ("Load more orders", outline).

**Order detail (`OrderDetailView`, page):** "Back to your orders" + PageHeader (eyebrow "Order details", h1 "Order <number>", status pill in `meta` — same parent as the h1, as the H1-parent E2E assertions require; description = placed / completed / cancelled dates). One column in a task-first DOM order (= visual = keyboard order): **Payment | Summary** (side by side from 1280px), **Refunds** (if any), **Order actions** (if any), **Items**, **Delivery/Pickup | Your note**, **Order updates** last. Summary = lavender §35 panel with server Subtotal / Tax / Total (headline-md) / Amount due and the courier-fee note — nothing summed. Fulfilment uses icon rows (address with recipient, phone `dir="ltr"`, estimated ready date — labels keep their original "Contact phone: " / "Estimated ready date: " text). Not found / error / signed-out / loading each keep one h1 (not-found copy unchanged, reveals nothing about ownership).

**Order lines (`OrderLineItem`):** 64px decorative tile (image, or image / deployed-code fallback), title-sm name, mono line total, "Physical item · Qty N × $X" / "STL file, sent by email · …" (unchanged copy), line status pill, dated notes (receipt confirmed, problem reported, cancelled, emailed, will be emailed) in a tinted list. **No download control of any kind (ADR-019).**

**Status history (`StatusTimeline`):** §45 timeline — still an `<ol>` in server order; decorative dot + connector rail; label in body text, time in the mono caption role; Current/Completed remain text.

**Customer actions (`OrderCustomerActions`, `CancelOrderDialog`, `ReportProblemDialog`):** shared section card "Order actions"; one primary ("I received my items"), Report a problem secondary, Cancel order outline; recorded receipt/problem facts with icons; availability (`orderActionAvailability`), handlers, success-notice focus, `useOrderAction` duplicate-submit guard, CSRF and refusal handling unchanged. Dialogs in the Batch 5 dialog language (mono eyebrow "Order <number>" on cancel, headline-md title, divided footer, safe action outline, stacked full-width buttons below 768). **The cash 24-hour warning is verbatim and now a warning callout inside the dialog description** (more prominent, never softened). The report textarea keeps its label, counter, validation and retained text after a failed send.

**Payment status (`OrderPaymentSection`, `HoldCountdown`):** section card with mono-labelled Method / Payment status (pill). Cash due = info callout; online unpaid = warning callout with the hold sentence and the countdown in a mono readout. Statuses are only the real seven (pending, processing, paid, failed, expired, refunded, partially_refunded) with "Status unavailable" for anything else (unchanged `orderStatus.ts`).

**Polling (unchanged, confirmed by diff):** `usePolledOrder`, the canonical `orderKeys.detail(id)` query, 3 s → slower interval, bounded window, hidden-tab pause, stop on final state, never for cash/no-payment orders, and `checkAgain` are untouched. Only the visible status changed: still the single polite `role="status"`, now a tinted box with a decorative spinner (off under reduced motion) while checking, and an outline "Check again" after the window.

**Retry (unchanged behaviour):** `useRetryPayment`, `can_retry_payment` gating, never for cash, same key only for an uncertain result / new key for a definite retry, redirect via `followPaymentRedirect`, PAYMENT_ALREADY_ACTIVE "Continue to payment", hold-expired and refusal outcomes — untouched. Restyled: primary "Retry payment" (busy labels "Starting payment…" / "Opening payment page…" unchanged), success = check callout, refusals = error callout card with the same links. No PAYMENT_NOT_RETRYABLE invented.

**Hold countdown:** still presentational (device clock), not a live region, not the order status; at zero it fires the one re-read and keeps the conditional "may be released" copy — never "expired".

**Checkout return:** centred white result card in the shared Container: neutral schedule glyph on an info circle (never a success check or an error mark), mono "Payment" eyebrow + one h1 (unchanged copy), the same `role="status"` info callout, the same explanation, and the same three links as a button hierarchy (View your orders primary, View notifications outline, Continue shopping ghost). Still reads nothing from the URL and calls no API.

**Offers list (`OfferList`, page):** PageHeader; one list card of rows with C3's 48px product thumb (real `cover_image`, else deployed-code glyph), "Offer on <product>" as the single stretched link, mono "Opened <date>", status pill (all nine server states keep their distinct labels; unknown → "Status unavailable"), Amount on the table / Agreed price in C3's bold primary offer role, Reply by / Check out by. No KPI tiles, savings, seller quotes or per-row actions (no such contract; moves live on the detail page). Loading / error / session / empty / load-more states as Orders.

**Offer detail (`CustomerOfferView`):** "Your offers" back link + PageHeader (h1 "Offer on <product>", status pill in `meta`, "View product" outline action when a slug exists). Then the success/refusal notices, **Offer details** card (facts), **Your reply** card — buttons are exactly `allowedMoves(allowed_actions)`, first primary, counter secondary, withdraw outline (destructive confirmation still in `OfferMoveDialog`) — the checkout panel for `accepted`, the paid note as an info callout, and the **History** timeline last. Move submit, `inFlight` guard, `describeOfferError`, refetch rules and the dialog are unchanged; no local price rule, minimum or discount.

**Shared offer facts/history:** `OfferFacts` and `OfferHistory` gained an opt-in `appearance` (`"default"` = original rendering, still used by `AdminOfferView`; `"account"` = Batch 7: mono labels, money in bold primary, a §45 `<ol>` timeline with party-coloured dots and quoted messages as plain text). Admin offer pages are visually unchanged.

**OfferCheckoutPanel:** classes and wrappers only — primary-bordered card with a cart glyph, agreed price (server's `agreed_amount`) in the bold primary role, Batch 6 consent rows (shared `ConsentCheckboxGroup`), `lg` "Check out and pay", phase headings in headline-md, warning/info callouts. Submit, phases, `useCheckoutAttemptTracker` key rules, `followPaymentRedirect` and error mapping are byte-for-byte unchanged; accepted offers never go through cart pricing.

**Wishlist (`WishlistList`, page):** C5 composition: mono "Showing N items" bar between hairlines, 1 → 2 (768) → 3 (1280) card grid. Card (§11c): 4:3 media tile with the type's fallback glyph (the list item has no image), always-visible 44px glass remove button top right (error ink, fills red on hover; name "Remove <product> from your wishlist"; spinner + `aria-busy` while removing; all removes disabled while one is in flight), "No longer available" tag bottom left for hidden products (record kept, name only, no link), then type badge, h2 title (the card's only link, when available), price (headline-md primary) and mono "Saved <date>". Query/cache, cursor following, remove mutation, focus-to-notice and logout/user-switch clearing unchanged. ProductCard not reused: it is one link around the whole card and would nest the remove control.

**Status consistency audit:** order, payment, line, offer and refund statuses all go through the existing describe tables and the one `StatusBadge` (5 bounded tones); no new tone, no one-off colours. Refunds stay text ("Cancellation refund · Refunded"), as before. Tones were not merged across domains (e.g. order `refunded` neutral vs offer `rejected` negative stay as their tables define). Unknown values → neutral "Status unavailable".

**Dates / money:** existing `formatOrderDate(Time)`, `PriceDisplay`, `formatMoney` only; every amount is a server field.

**Accessibility decisions:** exactly one h1 in every state of every Batch 7 route; detail pages use h2 section cards whose heading names the region; status always text; one link per list row (stretched hit area, decorative cue); order history and offer history are ordered lists; countdown not live and not authoritative; the polling line is the single polite status; dialogs keep DialogShell focus trap / Escape / busy lock / focus return, safe default focused, and fit 320px; report textarea labelled with counter; wishlist remove names its product and is never inside the link; unavailable stated in text; 44px controls and text links; global box-shadow focus ring; spinners, hovers and lifts off under reduced motion.

**Stitch deviations (and why):**
- C2/C3 tables rendered as list rows: the account column is ~650px at 1024 and a 6–7 column table would need horizontal scrolling (§43 mobile gap); row cards keep every real field visible at 320px.
- No C2 filter panel / search / pagination numbers / factory feed / promo image; no C3 KPI tiles, savings, seller-response column or per-row actions; no C5 filter/sort, Add to cart, Quick view, ratings, share or "Add all to cart" — no such contracts (cursor paging, no totals, no list-level cart action) and invented data is forbidden.
- Wishlist media tile shows a fallback glyph at 4:3 instead of a square product photo: `WishlistItemDTO` has no image.
- Order detail, offer detail and checkout return are DERIVED (no Stitch screens).
- No STL downloads / library (ADR-019), although Stitch shows them.

**Responsive QA** (Edge, production build, mocked real-shaped data incl. a 90-character product name, long Lebanese recipient/street/area/landmark, 8 history rows, a partially refunded mixed order with cancelled/delivered/emailed lines, a cash cancellable order, a countered offer with long messages, an unavailable wishlist item; 320 / 375 / 768 / 1024 / 1280 / 1440 via the new E2E spec, screenshots reviewed at 375 and 1280): no horizontal overflow on any Batch 7 route; titles, addresses, history labels and offer messages wrap; Payment|Summary and Delivery|Note pair up only from 1280; actions stay inside their cards at ≥44px; the cancel dialog fits at 320 with focus on "Keep my order"; the account tab strip / side panel unchanged. Polish from QA: wishlist price moved under the title (long names were breaking mid-word beside it in the 3-column grid), and the actions divider renders only when something sits above the buttons.

**Tests:** unit 2359 → **2391** (+32): new `accountUi.test` (6), new `offerPresentation.test` (12: OfferList loading / empty / error / session / one link per row with status, amount and deadline / all nine states + unknown / load more; offer detail h1-parent status, named sections, exact server moves, ordered history; no reply region without moves; one h1 loading + not found; shared facts/history default vs account appearance), `OrderHistoryList` (+2), `OrderDetailView` (+3: one h1 + status parent + task-first h2 order; history `<ol>`; countdown not a live status), `OrderCustomerActions` (+3: section named by h2; cash warning in the dialog description; labelled report textarea keeps text after a failed send), `wishlist` (+4: card structure / one link / no nested controls / unavailable keeps only Remove; single in-flight remove; loading status; session card), return page (+1: one h1, single primary, no success/failure mark), `EmptyState` (+1 `actionHref`). No existing assertion was changed or weakened (one E2E caught the "Payment due in cash:" wording on the list; the copy was restored, not the test). E2E 226 → **233**: new `account-commerce-responsive.spec.ts` (6 widths × orders / refunded detail / cash cancel dialog / offers list + detail / wishlist / return page, plus a 375px keyboard focus-ring check); `account-orders`, `account-order-actions`, `payment-result`, `offers`, `wishlist` pass unchanged.

**Gate:** lint ✓ (0 errors / 0 warnings) · typecheck ✓ · unit **2391/2391** (238 files) · build ✓ · E2E (smoke, production build) **233/233**, first run.

**Deferred to Batch 8+:** admin offer page restyle (switch `AdminOfferView` to the `account`-style facts/history or an admin variant — Batch 10); real wishlist/offer thumbnails once list contracts carry images and the media host is configured; a status filter on Orders if the owner wants one (the API supports `status`, the UI never built it — not added in a visual batch); the auth MFA countdown accessibility fix stays in Batch 11.

### Batch 8 — Contact and Bring Your Idea (public): COMPLETE

**Scope:** `/contact`, `/bring-your-idea`. Visual only: no endpoint, request body, schema, field, captcha lifecycle (fresh single-use token per attempt, reset in `finally`), error mapping (`describeGuestSubmissionFailure` / `describeCustomRequestFailure`), upload precheck or limit changed. `src/lib/**` untouched. Admin contact/BYI queues and details are Batches 9–10. `/about` was not touched (no change needed for this run's scope).

**Direct vs DERIVED:** `/contact` = S9 `contact_us_bekaa3d_inquiry` (Direct). `/bring-your-idea` = DERIVED (S9 hero + form card, D8 dropzone §30).

**Shared building blocks (new `components/forms/PublicFormLayout.tsx`, presentation only):** `PublicFormPage` (S9 boxed hero §9 with one h1, factual pill, 7/5 split stacked below 1024), `PublicFormCard` (white form card named by its h2; full-bleed below 640px with a 16px gutter, as the Batch 4 auth card, so the 300px captcha frame fits at 320), `PublicAsideCard` (tinted "Direct channels" / plain), `PublicAsideRow` (40px icon tile + mono label + value). No generic form abstraction: each form keeps its own schema, hooks and submission.

**Contact:** Name | Email and Phone (optional) | Subject (optional) pair up from 768; Message; captcha; lg "Send message" with send glyph (spinner while pending). Aside "Other ways to reach us" (new `ContactChannels`): email reply channel always; WhatsApp link, pickup address and pickup hours **only when configured in public settings** (shared `usePublicSettings` query, no second fetch). Plus a "Have something custom in mind?" card linking to `/bring-your-idea`. Card heading is "Write to us" (a heading containing "message" collided with the Message field's label lookup).

**Bring Your Idea:** two fieldsets with real legends ("Your details", "Your idea"; decorative mono step numbers `aria-hidden`), material | colour paired from 768, dropzone, captcha + lg "Send my idea". Aside: "What happens next" (send → we contact you by email or phone → nothing ordered or charged) and "Reference images" (the real limits: 5 files, JPEG/PNG/WebP, 10 MB, no 3D files). No budget/deadline/quantity/STL field.

**FileUploader (shared, also used by admin product images):** §30 dashed dropzone (upload glyph circle, "Drop files here or browse", mono "N / max selected · limit reached"); the native file input stays the real control (visually hidden but focusable; the zone shows the focus ring via `focus-within`; clicking the zone opens the picker; drop is an extra, never the only path); drag-over highlight; §30 file rows with image glyph, wrapped file name (`break-all`), mono size, 44px Remove (accessible name "Remove <file>" via `aria-label`) / Cancel / Retry; progress and errors unchanged; precheck, queue, driver seam and announcements unchanged.

**SuccessReceipt:** §48 result card (verified glyph in a lime circle, optional primary title, message) — still one `role="status"` holding title + message; optional `actions` rendered outside it ("Send another message/idea"). Titles "Message sent" / "Idea received"; messages unchanged; no receipt id, deadline, quote or tracking. Focus still moves to the receipt wrapper.

**Stitch deviations:** no Company field or Subject select (not in the contract — Subject stays free text); no map, office address, business hours / "Open now", phone, social links or FAQ (mock data; no real FAQ copy); the "4h average response" pill replaced by the factual "We reply by email" / "No order, no payment"; form card full-bleed below 640 (captcha width).

**Icons:** `send`, `upload-file` added to the local `Icon` set.

**Responsive QA** (production build, 320 / 375 / 768 / 1024 / 1280 / 1440, new `public-forms-responsive.spec.ts`; screenshots reviewed at 375 and 1280 against S9): no horizontal overflow with long validation errors, a 100-character name, three files incl. a very long file name and a refused `.stl`; 300px captcha frame inside the viewport at every width (found and fixed at 320 by the full-bleed card); 44px submit and Remove targets; success receipt at 320; native file input reached by Tab with a visible ring.

**Tests:** unit 2391 → **2398** (+7): new `ContactChannels.test` (3: configured rows, email-only when nothing configured, BYI link), `SuccessReceipt` (+1: title + message in the status, actions outside), `FileUploader` (+3: native input focusable and described, size + count, drag-over state). No existing assertion changed. E2E 233 → **236**: new `public-forms-responsive.spec.ts` (3); `contact.spec` and `bring-your-idea.spec` pass unchanged.

**Gate:** lint ✓ (0/0) · typecheck ✓ · unit **2398/2398** (239 files) · build ✓ · E2E **236/236**.

### Batch 9 — Admin shell, navigation, list/queue pages: COMPLETE

**Scope:** the admin chrome for all 27 admin routes, plus the list/queue pages `/admin/orders`, `/admin/stl-deliveries`, `/admin/offers`, `/admin/payments`, `/admin/refunds`, `/admin/cash-blocks`, `/admin/contact-messages`, `/admin/custom-requests` (incl. funnel), `/admin/customers`, `/admin/products`, `/admin/categories`, `/admin/materials`, `/admin/colours`. Visual only: no endpoint, query key, filter, query parameter, cursor rule, debounce, Suspense boundary, guard, MFA redirect, CSRF or audit-triggering call changed; `src/lib/**` untouched. `/admin` still redirects to `/admin/settings` — **no dashboard** (no real KPI data; Stitch's two dashboards are not built). Detail/form/action pages and `/admin/settings` are Batch 10 (they already sit inside the new shell).

**Storefront chrome removal (D5):** new client `SiteChrome` (used by `AppLayout`) + `useAdminChrome`. An **administrator on `/admin/*`** gets no storefront header, footer, `<main>` or floating WhatsApp button; AdminShell supplies its own chrome and the page's single `<main id="main-content" tabIndex=-1>` (skip-link target, sidebar outside it). Anyone else on an admin URL (guest being redirected, loading session, a customer seeing the 404) keeps the normal storefront chrome, so an admin URL looks like any other unknown page. Layout check only; access control stays with AdminGuard and the backend.

**AdminShell (D1 shell, §40/§41, §12.14/§12.15):** ≥1024px: fixed 256px sidebar (`bg-surface`, brand + mono "Admin console", grouped nav with mono section labels — Fulfilment / Money / Enquiries / Store / Catalogue — 20px icons, active = primary bold + `bg-surface-container-low` + 4px right rule + `aria-current`, footer "View store" + Log out); sticky 64px glass top bar inside the main column (mono "Admin" eyebrow + current area name, signed-in admin email + role from `useAuth` from 768px; no search/notifications/help — no such features). Blueprint grid canvas. Content capped at 1440 with 16/32px gutters. <1024px (Stitch has none): a menu button in the top bar opens a left drawer (`DialogShell` + `useSheetBehavior`: modal, focus trap, focus to close button, Escape/backdrop, focus return, scroll lock, closes past 1024px and on any route change) holding the same nav and footer. The customer-menu-on-admin Stitch bug is not reproduced; no "New Print Job" CTA, admin FAB or avatar photo.

**Navigation:** `adminNavItems.ts` now exports `ADMIN_NAV_GROUPS` (+ icons) and the flat `ADMIN_NAV_ITEMS` derived from it — the same 14 real routes in the **same order**; no dead or unbuilt entries (still no STL assets / entitlements / shipping zones).

**AdminTable (§43, §63, §49, §50):** one white card — in-card search bar (when the page has one), the table in a named, focusable horizontal-scroll region (inset focus ring; `min-w-[640px]` so columns never crush; page never overflows), mono uppercase headers on lavender, `px-4 py-3` → `px-6 py-4` from 1280, hairline dividers + row hover, skeleton rows, §49 empty state with the page's own copy, footer with outline 44px Previous / Next (cursor paging; no page numbers or totals — not provided by the backend). Columns are never dropped.

**List pages:** headline-lg h1 + muted description; filters in one white filter card (same fields, same order, same URL/query behaviour); "Showing one customer's …" notes as an info callout with the same "Show all" link; IDs in mono primary links (no wrap); `Products` uses a real link styled as the primary button (was a button nested in a link) with the same label; cash-block phone search wraps cleanly at 320 (phone still never in the URL). Reference data (`ReferenceDataManager`): one card — header with h2 + "Add …", the inline create/edit form in a tinted band under it (fields unchanged), rows with StatusBadge "Archived" / "Disabled" and 44px outline Edit / Enable·Disable / Archive (archive still confirmed by ConfirmDialog). BYI funnel: §42 tiles (mono label, headline value) for exactly the server's eight numbers; date range unchanged.

**Responsive QA** (production build; 320 / 375 / 768 / 1024 / 1280 / 1440, new `admin-shell-responsive.spec.ts`; screenshots reviewed at 375 and 1280 against D10): sidebar exactly 256px from 1024, drawer below with keyboard/Escape/route-change close; long admin email truncates in the top bar; long customer emails wrap and $12,345.67 amounts stay whole inside the table's own scroll region; no page-level overflow on any width; pager targets ≥44px. Polish from QA: mono order IDs no longer break mid-number; cell padding tightened below 1280.

**Tests:** unit 2398 → **2410** (+12): new `SiteChrome.test` (6: admin drops storefront chrome; customer / guest / loading keep it; admin outside /admin keeps it; path matching), `AdminShell` (+6: top bar names area and admin; grouped labels with unchanged link order; drawer modal + focus + Escape return; closes on route change; closes when growing to desktop; active item in drawer). Changed: the AdminShell "never creates a second `<main>`" test now asserts exactly one main (`#main-content`, tabindex −1) with the nav outside it — the D5 architecture change, not a weakening; `AppLayout.test` / `GlobalWhatsAppButton.test` mock `useAdminChrome` (storefront case). E2E 236 → **240**: new `admin-shell-responsive.spec.ts` (4: shell at six widths incl. no footer/Main nav/WhatsApp and table-only scroll; drawer keyboard flow; skip link past the sidebar; customer keeps storefront chrome + 404). All admin specs pass unchanged.

**Gate:** lint ✓ (0/0) · typecheck ✓ · unit **2410/2410** (240 files) · build ✓ · E2E **240/240**.

**Deferred:** the reference-data card repeats the page title as its h2 (kept: the component's tests and region name rely on it); detail/form pages and Settings are Batch 10.

### Batch 10 — Admin details, forms, actions, financial workflows: COMPLETE

**Scope:** `/admin/orders/[id]`, `/admin/payments/[id]`, `/admin/refunds/[id]`, `/admin/offers/[id]`, `/admin/contact-messages/[id]`, `/admin/custom-requests/[id]`, `/admin/customers/[id]`, `/admin/products/new`, `/admin/products/[id]`, `/admin/products/[id]/edit` (form, images, uploader, gallery), `/admin/settings`, plus the shared action dialog, line / order-level actions (fulfilment transitions, cash handover, cancel), payment recovery (check with provider, confirm by hand, manual release, late capture), create refund, chargebacks, refund settle / fail / void / reissue, internal notes and setting controls. `/admin/mfa/setup` and `/admin/mfa/recovery-codes` already use the Batch 4 auth card (unchanged). Visual only: no endpoint, request body, idempotency key, CSRF header, confirmation, busy lock, transition source (`available_actions` / `allowed_actions` / eligibility helpers), amount or Problem.code mapping changed; every amount is a server field; no optimistic success. `src/lib/**` untouched. No new backend capability: no STL upload/download/entitlement (ADR-019), no shipping settings (ADR-024), no contact assignments/replies, no chargeback update/resolve, no refund void/reissue workaround.

**Shared building blocks (new `components/admin/adminUi.tsx`, presentation only):** `AdminSection` (white card named by its visible h2, optional description, `tone="danger"` = error top rule for financial/irreversible areas), `AdminRow` (mono label / right-aligned value; `breakAll` for opaque references), `AdminField` (stacked mono label + value), `AdminBackLink`, `ADMIN_LINK_CLASSES`. They replace six identical page-local `Section` / `Row` / `Field` helpers (same names via import aliases, same semantics: `aria-label` regions, `<dl>` content).

**Token pass:** every Batch 10 file moved off the legacy palette/type (`text-text-*`, `text-h1/h3`, `text-body`, `border-border-default`, `rounded-md`, `bg-white`, `text-danger`, `bg-brand-dark-green`, `bg-neutral-200`) to the Stitch tokens. Raw `<input>/<textarea>` controls (product description / SEO description, internal notes, combobox, numeric setting) use the shared `fieldControlClasses` (48px, accessible border, error ring). `text-caption` (a defined alias) is left for the Batch 11 alias removal.

**Order detail / fulfilment:** back link, h1 + status pill, placed line; Order actions card; Items | Payment split from 1024 (384px side column); line actions still exactly the server's `available_actions`; cash handover still needs the exact amount; Fulfilment facts as mono rows; History as a §45 timeline (`<ol>`, decorative dots); internal note editor with a lock glyph (label text unchanged). Refund / chargeback lists and `CreateRefund` / `CreateChargeback` flows unchanged.

**Payments / refunds:** detail facts on the shared rows (references break anywhere); "Payment actions" and "Refund actions" sections danger-toned; recovery confirmation checkbox 20px with its label; mock-provider restrictions and eligibility unchanged.

**Action dialog (`AdminActionDialog`):** Batch 5 dialog language — headline-md title, description, divided footer, outline "Back" + primary/destructive confirm, stacked full-width below 768; DialogShell focus trap / Escape / busy lock / focus return unchanged.

**Offers:** the admin offer page now uses the Batch 7 `account` appearance of `OfferFacts` / `OfferHistory` inside an "Offer details" card, a "Your reply" card and the History timeline (Batch 7 deferral closed); moves still exactly `allowed_actions`; no local minimum.

**Contact / BYI detail:** back link, h1, status, facts card, message in a tinted block, Status / Pipeline / Images / Notes as cards; forward-only status moves, quote MoneyInput, won/lost, notes and admin-auth image download unchanged (images still never inlined).

**Customer detail:** back link, email h1 (breaks anywhere), facts card, "Customer records" as outline button-links (same URLs), an "Account access" danger card with Deactivate (outline, error ink) / Reactivate (primary); confirmation copy unchanged. No analytics.

**Products:** detail header with a real link styled as the Edit button (was a button nested in a link) and an outline Delete (ConfirmDialog unchanged); new/edit forms as card sections (type selector as radio cards, 44px checkbox rows), lg submit; edit page D5 split — form (7) | Images card (5) from 1280; gallery rows wrap (outline 44px Move up / Move down / Set as cover / Delete in error ink; alt-text editor wraps). Upload / delete / retry / reorder semantics unchanged.

**Settings:** h1 + factual description, rows in one divided card (`max-w-form`), outline Save per row with a "Saved" check, switch recoloured primary / outline (track at least 3:1), Security card with an outline "Regenerate recovery codes" link. Only the settings the API returns (no free-shipping threshold or shipping fee).

**Responsive QA** (production build; 320 / 375 / 768 / 1024 / 1280 / 1440, new `admin-detail-responsive.spec.ts`; screenshots reviewed at 1280): order detail with six long-named lines, long notes and a long customer email; a contact message with an unbroken 120-character token; settings; new-product form; the cash-handover dialog at 320 (inside the viewport, 44px buttons, Escape closes). **Found and fixed:** a 125px page overflow at 320 on order detail from an unbroken customer email — inherited `break-words` on the admin content region and detail roots (tables keep their sizing).

**Tests:** unit 2410 → **2414** (+4: new `adminUi.test`). No existing assertion changed. E2E 240 → **245** (+5: `admin-detail-responsive.spec.ts`). All admin workflow specs (`admin-orders`, `admin-payments`, `admin-operations`, `admin-routes`, `contact`, `bring-your-idea`, `offers`) pass unchanged.

**Gate:** lint ✓ (0/0) · typecheck ✓ · unit **2414/2414** (241 files) · build ✓ · E2E **245/245**.

**Deferred (Batch 11):** `text-caption` / legacy alias removal; the MFA countdown announcement; payment-detail and refund-detail width sweeps (their flows are covered by `admin-payments.spec.ts`); the whole-app consistency sweep.

---

## 1. High-risk areas and how to restyle them safely

General technique for all of them: **change classes and wrappers, never handlers, hooks, or conditions**. Diff review rule: in these files, every changed line should be in a `className`, a wrapper element, or a presentational prop. Any change to an `onClick` / `onSubmit` / `useMutation` / `if` condition / `key` / `aria-*` is a red flag and must be justified in the PR.

| Area | Where | What can break | Safe restyle approach |
|---|---|---|---|
| **Checkout** | `components/checkout/*`, `/checkout` | Idempotent order creation; price-change conflict resolution; disabled-checkout banner; unpaid/uncertain branches with focus-to-heading; cash eligibility and cap; consent validation. | Wrap the existing sections in step cards. Keep the section order and every `ref`/`tabIndex={-1}` heading. Radio cards use `has-[:checked]:` CSS only, with no new state. Do **not** add Stitch card fields, PayPal, or coupons. Run `checkout.spec.ts` + `CheckoutView` unit tests after each component. |
| **Payment redirects** | `lib/checkout/paymentRedirect.ts` (`window.location.assign`), `/checkout/return`, `OrderPaymentSection`, retry payment | Leaving before the server confirms; double submit; key reuse rules (`payment-result.spec.ts` checks the same key on uncertain, a new key after a definitive failure, one request on double click). | Never touch `paymentRedirect.ts` or the retry hooks. The Button `isLoading`/`disabled` contract must stay identical, because the double-click guard relies on it. Keep the return page wording neutral. Status comes only from the server. |
| **Order actions (customer)** | `OrderCustomerActions`, `CancelOrderDialog`, `ReportProblemDialog`, `HoldCountdown` | Cancel/report flows; countdown re-read; dialog busy lock. | Restyle through `DialogShell` and `Button` only. Keep the status text **inside the H1's parent element**: 9 E2E assertions use `heading(level 1).locator("..")`. A new `PageHeader` must render the H1 and the StatusBadge as siblings in one wrapper. |
| **Admin fulfilment** | `AdminOrderView`, `LineActions`, `OrderLevelActions`, `AdminActionDialog`, `/admin/stl-deliveries` | State machine actions; idempotency keys per attempt; reason requirements; per-line vs order-level actions. | Keep the action components' props untouched. Only regroup visually into an action bar (one primary, danger isolated). Keep button labels verbatim (E2E finds them by name). |
| **Admin payments and refunds** | `AdminPaymentView`, `CreateRefund`, `CreateChargeback`, `PaymentRecoveryActions`, `RefundView` | Refund amounts (MoneyInput cents logic); refundable remainder; confirmation steps; chargeback creation. | Class D: tokens only, no restructuring. Amounts in mono. Danger styling for irreversible actions. Never change MoneyInput parsing (228-line test suite). |
| **File upload** | `FileUploader` (Bring Your Idea, product edit) | Native input reachability; per-file errors; limits; upload driver; screen-reader live region. | The dropzone is a styled `<label>` around the **real** `<input type="file">`, which stays focusable and labelled. If drag-and-drop is added, it must call the same selection handler. Keep `role="alert"` errors and the `sr-only` live region. |
| **Captcha** | `CaptchaWidget` (register, forgot password, resend verification, contact, Bring Your Idea) | Turnstile mount; token lifecycle; CSP frame-src; the `data-testid="captcha-widget"` contract used by `e2e/support/fakeTurnstile.ts`. | Don't put it in an `overflow-hidden` or fixed-width box narrower than ~300px. Reserve a min-height. Keep its attributes. Test at 320px. |
| **MFA** | `/login` verify step, `/admin/mfa/setup`, `/admin/mfa/recovery-codes`, `AdminGuard` redirect | Challenge expiry and reset-to-login; recovery-code one-time display; enrolment confirm. | Restyle the card and fields only. Keep the code input attributes (`autocomplete="one-time-code"`, `inputmode`, if present). Recovery codes in mono grids. No copy changes to warnings. |
| **Dialogs** | `DialogShell` + its 5 direct callers (`ConfirmDialog`, `AddressBook`, `CancelOrderDialog`, `ReportProblemDialog`, `AdminActionDialog`) | Focus capture and return; Tab trap; Escape and backdrop suppressed while busy; `max-h-[90vh]` scroll; dialog width ≤ viewport (E2E). | Change `DEFAULT_PANEL_CLASSNAME` and the scrim class only. Audit every `panelClassName` override. The admin drawer and filter drawer **reuse** this focus logic (extract a hook if needed). Do not write a second trap. |
| **Data tables** | `AdminTable` (13 admin list pages) | Column render functions; cursor pagination; search debounce; empty and loading states; `scope="col"`. | Restyle `AdminTable` centrally. Keep the props API. Keep `overflow-x-auto`. Row actions stay visible (no hover-only reveal). A stacked mobile card mode is a later, separately tested enhancement. |
| **Responsive admin** | `AdminShell` | Today the nav is a horizontal scroller below 768px. A 256px sidebar would leave no room for content. | Sidebar ≥1024, drawer below that. The drawer toggle sits in the top bar, with `aria-expanded`/`aria-controls`. Verify keyboard access to all 14 nav items at 320px. |
| **Offer workflows** | `MakeOfferPanel`, `CustomerOfferView`, `OfferMoveDialog`, `OfferCheckoutPanel`, `AdminOfferView` | Offer state machine; idempotent moves; expiry; offer → checkout handoff. | Buttons keep their labels and handlers. Present the negotiation history as a timeline, but keep it an ordered list. Run `offers.spec.ts` + offer unit tests. |
| **Auth geometry** | `/login` and `e2e/login-session.spec.ts` | The spec asserts form ≤420px wide and centred at ≥768, full-bleed (≥ viewport−10) at <768, and a full-width submit. | The Stitch card adds padding. Update the spec **deliberately** in Batch 4. Keep the intent (centred, capped, full-width submit, no overflow), change the numbers, and record the reason in the PR. |
| **Account nav geometry** | `AccountLayout` and `e2e/account-profile.spec.ts` | `navigation "Account"` must exist and have a bounding box at 320–1920, sit beside the content (≤256px) from 1024 and above it below (updated in Batch 5), and focused links must have a non-`none` `box-shadow`. | Keep the nav visible at all widths (horizontal scroller or bottom nav, still labelled "Account"). Keep box-shadow-based focus rings. |
| **Global canvas colour** | `body` background white → `#f9f9ff` | Components that relied on white-on-white without borders lose separation. | Batch 1 sweep of every route at 375 and 1280. Add `border-outline-variant` where a card disappears. |

---

## 2. Batches

Each batch ends with **exactly one full gate** (§4). During a batch, run only the targeted tests listed.

The order follows the requested sequence. One adjustment: the `SiteChrome` switch that removes storefront chrome from admin lands in **Batch 9** together with the admin shell, so admin never shows half a shell. Batch 2 only builds the storefront chrome.

### Batch 1: Global tokens, fonts, backgrounds, shared primitives

| | |
|---|---|
| **Files** | `src/app/globals.css` (`@theme` tokens, utilities `.glass-panel`, `.bg-blueprint`, `.text-gradient-primary`, reduced-motion block, focus ring), `src/app/layout.tsx` (fonts via `next/font`, `className` on `<html>`/`<body>` only; providers untouched), `components/forms/{Button,TextField,PasswordField,SelectField,TextAreaField,MoneyInput}.tsx`, `components/feedback/{Alert,Toast,DialogShell,ConfirmDialog,LoadingSpinner,EmptyState}.tsx`, new `components/ui/{Icon,Container,Skeleton}.tsx`, `components/admin/StatusBadge.tsx`, `components/catalog/{PriceDisplay,ProductTypeBadge}.tsx`, `.claude/skills/bekaa3d-brand-ui/{SKILL.md,tokens.md}` (decision D2) |
| **Stitch refs** | DESIGN-TOKENS §1–§9; DESIGN-SYSTEM §6–§12 (esp. §12.9, §12.13, §12.18); COMPONENT-SPECS §8, §18, §27–§29, §47–§50 |
| **Shared dependencies** | Every route. Legacy token names are aliased (token doc §0) so nothing un-migrated breaks. Radius collision order: dialogs → `rounded-xl` **before** `--radius-lg` becomes 8px. |
| **Regression risk** | **Medium-high (breadth).** Font metrics change every text node, which can break geometry E2E (login form width, overflow sweeps). Class-asserting unit tests: `Button.test`, `StatusBadge.test`, `ConfirmDialog.test`, `LoadingSpinner.test`. |
| **Visual QA targets** | Canvas `#f9f9ff`; Inter body, Hanken headings, mono labels actually loaded (computed font); button variants and sizes; input 48px with focus and error states; StatusBadge tones; dialog panel; toast; contrast spot checks (`outline` text, lime chips). |
| **Targeted tests** | `vitest run src/components/forms src/components/feedback src/components/admin/StatusBadge.test.tsx src/components/catalog src/app/layout.test.tsx`; `playwright test --project=smoke login-session.spec.ts smoke.spec.ts` (geometry + overflow sentinels). |
| **Route coverage** | All 51 routes change visually (palette, fonts, primitives); no layout changes. |

### Batch 2: Header, Footer, navigation, shared cards

| | |
|---|---|
| **Files** | `components/layout/{Header,HeaderCartLink,Footer,SkipLink,FloatingWhatsAppButton,GlobalWhatsAppButton,AppLayout}.tsx`, `components/catalog/{ProductCard,ProductGrid}.tsx`, `components/wishlist/WishlistButton.tsx`, new `components/ui/PageHeader.tsx` (H1 + status slot in the same parent) |
| **Stitch refs** | COMPONENT-SPECS §1–§4, §6, §7, §11b/c/d, §64; DESIGN-SYSTEM §12.5–§12.8, §12.10–§12.11; RESPONSIVE-SPECS §1 (mobile menu) |
| **Shared dependencies** | Header and Footer on every storefront, auth, and account route; ProductCard on home, shop, and wishlist. |
| **Regression risk** | Medium. Header tests (`Header.test`, `HeaderCartLink.test`), the E2E nav and menu flows, the shop card locator (wishlist link must stay outside the card link), and `ProductCard.test`. |
| **Visual QA targets** | 64px sticky glass header, wordmark, active link underline, cart badge, mobile menu sheet; footer 4 columns → 1; product card radius, border, shadow, hover lift (reduced-motion off), price style. |
| **Targeted tests** | `vitest run src/components/layout src/components/catalog/ProductCard.test.tsx src/components/wishlist`; `playwright test --project=smoke smoke.spec.ts shop.spec.ts wishlist.spec.ts`. |
| **Route coverage** | Chrome on routes 1–24, 52–54; cards on `/`, `/shop`, `/account/wishlist`. |

### Batch 3: Home, Shop, Product detail

| | |
|---|---|
| **Files** | `components/home/*`, `components/catalog/{ShopView,FilterPanel,SearchBar,SortSelect,ProductImageGallery,ProductDetailView,AddToCartButton,UnavailableNotice,WhatsAppChatButton}.tsx`, `components/offers/MakeOfferPanel.tsx` (visual only), `components/feedback/LoadMore.tsx`, new filter drawer (reusing the DialogShell focus logic) |
| **Stitch refs** | PAGE-SPECS S1, S2, S3 (filters), S4, S5; COMPONENT-SPECS §9, §10, §13, §14, §17, §19, §20, §24, §25; DESIGN-SYSTEM §12.22 (gallery tiling fix) |
| **Shared dependencies** | ProductCard (Batch 2), Button, PriceDisplay, StatusBadge. |
| **Regression risk** | Medium-high: URL-bound filter state, the infinite query, product-type rules, add-to-cart and offer flows, the new drawer. |
| **Visual QA targets** | Hero type step-down at <768; section rhythm 96/64; filter aside 256px ≥1024 and drawer below; 3-up grid; PDP 7/5 split, `display` H1, 48px price, spec tiles, single primary CTA; no tiled images; real media only. |
| **Targeted tests** | `vitest run src/components/home src/components/catalog src/app/page.test.tsx`; `playwright test --project=smoke shop.spec.ts product-detail.spec.ts offers.spec.ts`. |
| **Route coverage** | `/`, `/shop`, `/shop/[slug]` (+ `/about` hero/section styles if trivially shared; otherwise Batch 8). |

### Batch 4: Authentication pages

| | |
|---|---|
| **Files** | `app/{login,register,forgot-password,reset-password,verify-email,verify-email/resend}/page.tsx` (markup and classes only), new `components/auth/AuthCard.tsx`, `components/auth/RecoveryCodeList.tsx`, `components/forms/{Form,CaptchaWidget}.tsx` (spacing only), `e2e/login-session.spec.ts` (deliberate geometry update) |
| **Stitch refs** | PAGE-SPECS A1–A4; COMPONENT-SPECS §27, §38, §39 (divider only; **no social buttons**), §48 |
| **Shared dependencies** | TextField, PasswordField, Button, Alert, CaptchaWidget; blueprint background utility. |
| **Regression risk** | **High**: login + MFA, captcha token flows, reset-token URL handling, success-heading focus, geometry E2E. |
| **Visual QA targets** | Card widths 440/448/640; blueprint canvas; split wordmark; full-width CTA; MFA step styling; captcha at 320; focus visible on every control. |
| **Targeted tests** | `vitest run src/app/login src/app/register src/app/forgot-password src/app/reset-password src/app/verify-email src/components/auth src/components/forms/CaptchaWidget.test.tsx`; `playwright test --project=smoke login-session.spec.ts register-and-verify.spec.ts auth-account-phase2.spec.ts`. |
| **Route coverage** | Routes 10–15. |

### Batch 5: Account shell, profile, addresses, notifications

| | |
|---|---|
| **Files** | `components/account/{AccountLayout,accountNavItems*,ProfileCard,AddressBook,AddressList,AddressCard,AddressForm,DefaultAddressSelector}.tsx`, `components/auth/LogoutButton.tsx`, `components/notifications/*` |
| **Stitch refs** | PAGE-SPECS C7 (+C1 shell), COMPONENT-SPECS §40 (customer), §41, §46, §54, §61; DESIGN-SYSTEM §12.14 |
| **Shared dependencies** | PageHeader, cards, DialogShell, fields. *Only the label/registry is touched in `accountNavItems.ts`; items stay the same 6. |
| **Regression risk** | Medium-high: the account nav geometry E2E, the zero-form-controls assertion on the profile, address CRUD dialogs. |
| **Visual QA targets** | 256px sidebar ≥768, active rail + filled icon, mobile nav still labelled "Account"; profile cards; address cards + dashed add tile; notification rows. |
| **Targeted tests** | `vitest run src/components/account src/components/notifications src/app/account/profile src/app/account/addresses src/app/account/notifications`; `playwright test --project=smoke account-profile.spec.ts account-addresses.spec.ts auth-account-phase2.spec.ts`. |
| **Route coverage** | `/account` (redirect), `/account/profile`, `/account/addresses`, `/account/notifications`; shell on all account routes. |

### Batch 6: Cart and Checkout

| | |
|---|---|
| **Files** | `components/cart/*`, `components/checkout/*` (classes and wrappers only), optional `components/ui/QuantityStepper.tsx` |
| **Stitch refs** | PAGE-SPECS S6, S7; COMPONENT-SPECS §26, §28, §33–§37 (no coupon, no card fields) |
| **Shared dependencies** | Button, radio cards, Alert, OrderSummary, PriceDisplay. |
| **Regression risk** | **High**: money flows (see §1 Checkout and Payment redirects). |
| **Visual QA targets** | 8/4 and 7/5 splits, sticky summaries ≥1024 only, line cards, stepper, step cards, payment option cards (cash disabled state legible), server totals. |
| **Targeted tests** | `vitest run src/components/cart src/components/checkout src/lib/checkout`; `playwright test --project=smoke cart.spec.ts checkout.spec.ts`. |
| **Route coverage** | `/cart`, `/checkout`. |

### Batch 7: Orders, payment UI, Offers, Wishlist

| | |
|---|---|
| **Files** | `components/account/{OrderHistoryList,OrderDetailView,OrderLineItem,OrderPaymentSection,OrderCustomerActions,StatusTimeline,HoldCountdown,CancelOrderDialog,ReportProblemDialog}.tsx`, `components/offers/*`, `components/wishlist/WishlistList.tsx`, `components/checkout/CheckoutConfirmation.tsx`, `app/checkout/return/page.tsx`, `app/account/{orders,offers}/**/page.tsx` (markup only) |
| **Stitch refs** | PAGE-SPECS C2, C3, C5; COMPONENT-SPECS §11c, §25, §45, §48, §49; DESIGN-SYSTEM §9 status mapping |
| **Shared dependencies** | PageHeader (H1 + status sibling), StatusBadge tones (offer `info`), DialogShell, LoadMore. |
| **Regression risk** | **High**: retry payment, cancel, report, offer moves, polling, the 9 H1-parent E2E assertions. |
| **Visual QA targets** | Order and offer cards, detail section cards, timeline, one primary action per view, wishlist grid and empty state, return page card. |
| **Targeted tests** | `vitest run src/components/account src/components/offers src/components/wishlist src/app/account/orders src/app/account/offers src/app/checkout`; `playwright test --project=smoke account-orders.spec.ts account-order-actions.spec.ts payment-result.spec.ts offers.spec.ts wishlist.spec.ts`. |
| **Route coverage** | `/account/orders`, `/account/orders/[id]`, `/account/offers`, `/account/offers/[id]`, `/account/wishlist`, `/checkout/return`. |

### Batch 8: Contact and Bring Your Idea

| | |
|---|---|
| **Files** | `components/contact/ContactForm.tsx`, `components/byi/BringYourIdeaForm.tsx`, `components/forms/FileUploader.tsx` (dropzone), `components/feedback/SuccessReceipt.tsx`, `app/{contact,bring-your-idea,about}/page.tsx` |
| **Stitch refs** | PAGE-SPECS S8, S9; COMPONENT-SPECS §9 (boxed hero), §30, §48, §51 (FAQ only with real copy), §52, §53 (only with approved numbers) |
| **Shared dependencies** | Fields, CaptchaWidget, FileUploader, Button loading state. |
| **Regression risk** | High: captcha, uploads, idempotent submit, success-receipt focus. |
| **Visual QA targets** | 7/5 form + channels card, dropzone, file rows at 320, captcha width, success card, about sections without fake imagery. |
| **Targeted tests** | `vitest run src/components/contact src/components/byi src/components/forms/FileUploader.test.tsx src/components/feedback/SuccessReceipt*`; `playwright test --project=smoke contact.spec.ts bring-your-idea.spec.ts`. |
| **Route coverage** | `/contact`, `/bring-your-idea`, `/about`. |

### Batch 9: Admin shell, dashboard entry, list pages

| | |
|---|---|
| **Files** | `components/layout/AppLayout.tsx` (`SiteChrome` switch, decision D5), `components/admin/{AdminShell,adminNavItems,AdminTable,ReferenceDataManager,AdminReferenceDataPage}.tsx`, new `components/ui/{AppTopBar,Drawer,KpiCard}.tsx`, `components/admin/customRequests/CustomRequestFunnel.tsx`, all admin list `page.tsx` files (markup only) |
| **Stitch refs** | PAGE-SPECS D4, D9, D10, D11, D13 (+D1 shell); COMPONENT-SPECS §40 (admin), §41, §42, §43, §63, §64; DESIGN-SYSTEM §12.14–§12.16; RESPONSIVE-SPECS §1 "Admin layouts" |
| **Shared dependencies** | Drawer (focus logic from DialogShell), StatusBadge, PageHeader, filter bar. **"Dashboard"**: `/admin` stays a redirect. No dashboard is built (no data). |
| **Regression risk** | Medium-high: `AdminGuard`/MFA redirect, drawer keyboard access, cursor pagination, URL filters (`Suspense` + `useSearchParams` pages), one `<main>` landmark after the chrome switch. |
| **Visual QA targets** | Sidebar 256 ≥1024 / drawer below; sticky 64px top bar never overflows; tables `px-6 py-4`, mono headers, scroll inside the card at 320; filter bars wrap cleanly; KPI funnel row. |
| **Targeted tests** | `vitest run src/components/admin src/components/layout src/app/admin`; `playwright test --project=smoke admin-routes.spec.ts admin-operations.spec.ts admin-orders.spec.ts admin-payments.spec.ts`. |
| **Route coverage** | `/admin` (redirect), `/admin/customers`, `/admin/categories`, `/admin/materials`, `/admin/colours`, `/admin/products`, `/admin/orders`, `/admin/stl-deliveries`, `/admin/offers`, `/admin/payments`, `/admin/refunds`, `/admin/cash-blocks`, `/admin/contact-messages`, `/admin/custom-requests` (the shell reaches all 27 admin routes). |

### Batch 10: Admin details, forms, financial workflows

| | |
|---|---|
| **Files** | `components/admin/{ProductForm,ProductTypeSelector,ImageGallery,InternalNoteEditor,SearchableCombobox}.tsx`, `components/admin/settings/*`, `components/admin/orders/*`, `components/admin/payments/*`, `components/admin/offers/*`, `components/admin/contact/*`, `components/admin/customRequests/CustomRequestView.tsx`, admin detail/form `page.tsx` files, `app/admin/mfa/**` |
| **Stitch refs** | PAGE-SPECS D5, D6, D8 (STL fields), D15; COMPONENT-SPECS §24 (admin media), §25, §29, §30, §45, §48, §59 |
| **Shared dependencies** | Container `narrow` (1200), section cards, MoneyInput, DialogShell, FileUploader. |
| **Regression risk** | **Highest**: fulfilment, refunds, chargebacks, settings, MFA enrolment (see §1). |
| **Visual QA targets** | 8/4 forms stack below 1024; media grid; toggle rows; financial actions isolated and danger-styled; mono amounts and IDs; MFA cards. |
| **Targeted tests** | `vitest run src/components/admin src/app/admin src/lib/admin`; `playwright test --project=smoke admin-orders.spec.ts admin-payments.spec.ts admin-operations.spec.ts admin-routes.spec.ts`. |
| **Route coverage** | `/admin/settings`, `/admin/customers/[id]`, `/admin/products/new`, `/admin/products/[id]`, `/admin/products/[id]/edit`, `/admin/orders/[id]`, `/admin/offers/[id]`, `/admin/payments/[id]`, `/admin/refunds/[id]`, `/admin/contact-messages/[id]`, `/admin/custom-requests/[id]`, `/admin/mfa/setup`, `/admin/mfa/recovery-codes`. |

### Batch 11: Responsive, visual consistency, accessibility polish

| | |
|---|---|
| **Files** | Any, for fixes only. `globals.css`: remove the legacy token aliases once `grep` shows 0 uses (token doc REMOVE rows). Update the remaining class-asserting tests. |
| **Stitch refs** | RESPONSIVE-SPECS §1–§6; VISUAL-QA-CHECKLIST (all sections); DESIGN-SYSTEM §11 (focus, reduced motion) |
| **Shared dependencies** | Everything. |
| **Regression risk** | Low–medium (cleanup), but alias removal can expose missed call sites. That is why it goes last. |
| **Visual QA targets** | Full §3 matrix on every route; axe sweep (`a11y-sweep` approach used previously); reduced-motion pass; no legacy tokens; no hex literals; no remote assets. |
| **Targeted tests** | Overflow and geometry specs across all families; the full gate. |
| **Route coverage** | All 51 + 3. |

---

## 3. Visual QA workflow (per redesigned page)

### 3.1 Viewports

Check **320, 375, 768, 1024, 1280, 1440** for every redesigned page. 1280 is the Stitch capture width: compare closely there against `screen.png` (decision D8) and the PAGE-SPECS entry. For DERIVED routes, compare against the closest family page named in the route doc.

### 3.2 Procedure

1. Run the app against the **real backend** (see `docs/backend-handoff/REAL-BACKEND-ACCEPTANCE.md` and the acceptance harness), with real products, media, orders, and offers. Also run with mocked edge states (empty lists, errors, long names) via the existing E2E fixtures.
2. For each viewport, run the overflow check in devtools or Playwright: `document.documentElement.scrollWidth <= document.documentElement.clientWidth`.
3. Walk the checklist below and fill in the sign-off template (VISUAL-QA-CHECKLIST "Per-page sign-off"), listing intentional deviations with their DESIGN-SYSTEM §12 or token-doc reference.
4. Keyboard pass: Tab through the whole page; Escape every dialog and drawer; check that the skip link reaches `<main>`.
5. States pass: force loading (throttle), empty, error (block `/api` in devtools), and busy (slow mutation) for each data region.

### 3.3 Checklist (every page, every viewport unless noted)

- [ ] **No horizontal overflow** (the scrollWidth check above); tables scroll inside their own card.
- [ ] **Content width**: storefront and app content capped at 1440 (admin forms 1200), centred; gutters 16 (<768), 32 (768–1023), 64 (≥1024 storefront) / 32 (app content).
- [ ] **Typography**: Hanken / Inter / JetBrains Mono actually rendered (computed font); display 48 → 36 and headline-lg 32 → 24 below 768; mono labels uppercase via CSS.
- [ ] **Spacing**: section rhythm (96/64), card padding (24/32), field rhythm (24), label → input 8.
- [ ] **Colour**: canvas `#f9f9ff`, white cards, lavender containers, one primary action colour, StatusBadge mapping; no legacy greys.
- [ ] **Radius**: badge 4 · control 8 · card 12 · panel 16 · banner 24 · pill full; nested radii decrease inward.
- [ ] **Cards**: border `outline-variant(/30)`, `shadow-sm`, hover per spec (and none when `prefers-reduced-motion`), equal heights in rows.
- [ ] **Responsive stacking**: splits (7/5, 8/4, 3/9) stack below 1024 in the documented order (gallery → info, items → summary, form → summary).
- [ ] **Keyboard usability**: every control reachable in a logical order; no keyboard traps except inside open dialogs/drawers.
- [ ] **Visible focus**: the global ring on every interactive element (buttons, links, card links, toggles, tabs, file input, captcha neighbours); inputs also show the green border + ring.
- [ ] **Dialogs**: focus moves in, is trapped, Escape closes (unless busy), focus returns to the trigger, width ≤ viewport at 320, scrolls within `90vh`.
- [ ] **Loading states**: skeletons or spinners in place of every data region; buttons show a spinner with `aria-busy` and stay disabled.
- [ ] **Empty states**: §49 layout with real copy and a working CTA.
- [ ] **Errors**: field errors (red border + text, `aria-invalid`), form summary, page-level Alert, toast; none removed for visual reasons.
- [ ] **Real backend data**: real names, prices, statuses, media; long names and SKUs truncate or wrap without breaking layout.
- [ ] **No broken media**: every image loads from the app's `/media` (or the backend media origin); the "No image available" placeholder renders when absent; no `lh3.googleusercontent.com` URLs; meaningful `alt`.
- [ ] **No clipped text**: buttons, chips, table headers, and nav items at 320 (mono text is wider); no text hidden under the sticky header.
- [ ] **No inaccessible hidden controls**: no hover-only actions; anything revealed on hover is also visible on focus and on touch (<1024 always visible); nothing `display:none` that a test or user needs.
- [ ] **1280 only**: side-by-side with `screen.png` for header height, H1 size, card width/gap, section order, and footer columns, within about ±4px after scaling (PNG width 1600 = 1.25×).

---

## 4. Testing rule for every batch

While developing a batch, run **only the targeted tests** listed for it (unit file subsets plus named Playwright specs).

At the **end** of each batch, run **exactly one** full gate, in this order, and record the results in the batch report:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

Do not re-run the full E2E suite repeatedly without a reason. If the gate fails, fix the cause, re-run only the affected targeted tests, then run the gate once more.

`npm run test:e2e` builds and serves its own production build (`.next-e2e/`, port 3100), separate from the `npm run build` step above, which checks the real build. Targeted re-runs after the gate can skip that rebuild with `E2E_REUSE_BUILD=1` when no source changed (see `docs/setup/frontend-setup.md`).

Batch report template:

```
Batch N — <name>
Files changed: …
Tests updated (and why): …
Deviations from Stitch (with §12 / token-doc refs): …
Gate: lint ✓  typecheck ✓  unit x/x  build ✓  e2e x/x
QA: routes × viewports signed off: …
Open issues: …
```

---

## 5. Recommended Batch 1 scope (precise)

**In scope**
1. Decisions D1–D4 recorded; `bekaa3d-brand-ui` `SKILL.md` + `tokens.md` updated to reference the Stitch handoff (D2).
2. `globals.css`:
   - the full Stitch MD3 colour set + `warning-*`, `info-*`, `whatsapp`
   - type tokens (with the <768 step-down), spacing, container, sidebar and top-bar tokens
   - radius (after converting the 4 `rounded-lg` dialog uses to `rounded-xl`)
   - shadows, glass, blueprint, gradient utilities
   - a reduced-motion block
   - focus ring recoloured (still `box-shadow`)
   - `body` background, colour, and font
   - **legacy tokens re-pointed as aliases**
3. `layout.tsx`: three fonts via `next/font` as CSS variables on `<html>`. No change to providers or composition.
4. New primitives: `Icon` (SVG, the glyph subset needed by Batches 1–2), `Container`, `Skeleton`.
5. Restyle: `Button` (variants and sizes, loading spinner; same API and names), `TextField`, `PasswordField` (trailing toggle), `SelectField`, `TextAreaField`, `MoneyInput` (prefix), `Alert`, `Toast`, `DialogShell` + `ConfirmDialog`, `LoadingSpinner`, `EmptyState` (backwards-compatible props), `StatusBadge` (tone mapping), `PriceDisplay` (size prop), `ProductTypeBadge`.
6. Update the class-asserting unit tests for exactly the components restyled (`Button`, `StatusBadge`, `ConfirmDialog`, `LoadingSpinner`). Assert variant or role where possible.

**Out of scope for Batch 1**
Header, Footer, shells, ProductCard, any page layout, any `page.tsx`, any E2E spec edits (except if the font change alone moves the login geometry; then fix it minimally and record it).

**Batch 1 exit criteria**
The full gate is green, all 51 routes render with the new palette, fonts, and primitives at 375 and 1280 without contrast regressions, and the production build serves the fonts under the CSP (`npm run build && npm start`, no CSP console errors).
