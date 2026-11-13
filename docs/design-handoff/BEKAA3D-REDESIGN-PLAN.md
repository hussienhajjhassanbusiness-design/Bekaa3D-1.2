# Bekaa3D: Stitch Redesign Plan

**Goal:** current working Bekaa3D **plus** the Stitch "Precision Engineering System" design language. This is a re-skin, not a rebuild.

**Status:** Batch 1 (tokens, fonts, global foundation, shared primitives), Batch 2 (storefront Header, mobile navigation, Footer, ProductCard) and Batch 3 (Home, Shop, Product Detail, WhatsApp action, skip link) **complete** — see "Batch status" below. Batches 4–11 not started.

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
| **Account nav geometry** | `AccountLayout` and `e2e/account-profile.spec.ts` | `navigation "Account"` must exist and have a bounding box at 320–1920, be narrower than the viewport ≥768, and focused links must have a non-`none` `box-shadow`. | Keep the nav visible at all widths (horizontal scroller or bottom nav, still labelled "Account"). Keep box-shadow-based focus rings. |
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
