# Bekaa3D — Visual QA Checklist

Reusable checklist for comparing an implemented page against its Stitch reference (`<page>/screen.png` + `code.html`). Compare at **1280px** viewport first (the screenshot width), then 1440, 1024, 768, 390/360.

How to use: copy the **Global** section + the relevant family section(s) into the PR/page QA note; tick each item; record intentional deviations (Stitch defects fixed per DESIGN-SYSTEM §12) under "Deviations".

Tip: overlay the screenshot at 50% opacity (browser extension or devtools) — 1600px-wide PNGs are 1.25× captures of a 1280px viewport; tall PNGs are downscaled (scale = 1280 / PNG width).

---

## GLOBAL

### Colors
- [ ] Page background is `#f9f9ff` (not `#fff`, not gray).
- [ ] Cards are pure white `#ffffff` (`surface-container-lowest`) where the source uses `bg-white`/`surface-container-lowest`.
- [ ] Muted panels use lavender tints (`#f1f3ff`, `#e9edff`, `#e1e8fd`, `#dce2f7`) — no Tailwind grays.
- [ ] Primary actions/links/prices/active states = `#0d631b`; primary hover = `#2e7d32`.
- [ ] Headings text `#141b2b`; body/secondary text `#40493d`; tertiary/captions `#707a6c`.
- [ ] Borders/dividers `#bfcaba` (full or /30 per source).
- [ ] Lime `#b9f474` only on chips/accents; raspberry `#923357` only on discount/low-stock/3rd-series accents; error `#ba1a1a`.
- [ ] Status chips use the single StatusBadge mapping (DESIGN-SYSTEM §9).
- [ ] No hard-coded hex values outside the token file (WhatsApp `#25D366` as a token).

### Typography
- [ ] Headlines in **Hanken Grotesk**; body in **Inter**; labels/buttons/table headers/IDs in **JetBrains Mono**.
- [ ] H1 hero 48px / 800 / -0.02em / lh 1.1; page title 32px / 700 / -0.01em; card title 20px / 600.
- [ ] Mono labels 12px / 600 / +0.05em / **UPPERCASE**; micro labels 10–11px.
- [ ] Body 16px / lh 1.5; lead 18px / lh 1.6.
- [ ] Prices & KPI numbers use Hanken (not Inter).
- [ ] Fonts actually load (no fallback flash to Times/Arial — check computed font in devtools).
- [ ] Material Symbols render as glyphs (not ligature text like "shopping_cart").

### Content width & gutters
- [ ] Content max-width 1440px (1200px for admin long forms), centered.
- [ ] Desktop gutter 64px (storefront); mobile 16px.
- [ ] Nothing sits flush against the viewport edge (Stitch defect on about/contact/STL details must be fixed).

### Section spacing
- [ ] Storefront sections 96px vertical (`py-24`); compact bands 64–80px.
- [ ] Centered section header → grid gap 64px; split header → 48px.
- [ ] Top offset under fixed nav ≈ 96–128px; nothing hidden under the nav.
- [ ] App pages: 32px content padding, 32px between blocks, 24px grid gaps.

### Shadows & elevation
- [ ] Resting cards: `shadow-sm` (0 1px 2px rgba(0,0,0,.05)) or border-only in admin tables.
- [ ] Hover: shadow grows (`md`/`xl`) and lifts only where the source lifts (-4px / -8px shop).
- [ ] Primary CTAs have the green-tinted `shadow-lg shadow-primary/20` where specified.
- [ ] Glass surfaces: white 80% + 20px blur (nav bars, glass panels).

### Radius
- [ ] Buttons/inputs/selects/sidebar items 8px; badges 4px; cards 12px; large panels 16px; promo/CTA bands 24px; pills/avatars full.
- [ ] Nested radii decrease inward (card 12–16 → input 8 → badge 4).

### Borders
- [ ] 1px default; 2px for outlined CTAs, selected thumbnail, selected payment card; 4px right rail for active sidebar item; 2px bottom for active nav/tab.

---

## HEADER (storefront)
- [ ] Fixed, 64px (or documented variant), glass `bg-surface/80` + blur + bottom border `outline-variant/30`.
- [ ] Wordmark: Hanken 20px/800/primary (or approved variant).
- [ ] Links Inter 16px `#40493d`, gap 32px; active link green, bold, 2px underline with 4px offset.
- [ ] Right cluster: search (≥1024), cart with 16px green badge, account/login; icon buttons 40px hit area.
- [ ] Hover colors & 200ms transitions.
- [ ] Mobile: links hidden, **menu button present** and opens a usable menu.
- [ ] No content hidden behind the fixed header on any page; anchor links offset correctly.

## FOOTER
- [ ] Single shared footer: `surface-container-low` (or approved), top border, 4 columns ≥768px.
- [ ] Brand column (wordmark, description, 40px social circles), 2 link columns, newsletter (input + green icon button).
- [ ] Column headings style consistent (mono caps); links `#40493d` hover primary.
- [ ] Bottom bar: divider `outline-variant/30`, copyright left, payment/legal right; stacks on mobile.
- [ ] Copyright year and links are real (not "© 2024" mock).

## CARDS
- [ ] Product card: 1:1 image, `object-cover`, zoom on hover (105/110 over 500ms), badges top-left (4px or pill per variant), price Hanken green, CTA per variant.
- [ ] STL card: correct image ratio per variant (16:10 home / 256px marketplace / 16:9 library / 1:1 related), license badge, formats tag, stars + count, Buy/Offer actions.
- [ ] KPI card: icon tile 40–48px tinted, mono uppercase label, Hanken value, trend chip colors (+ green on `primary-fixed`, − red on `error-container`).
- [ ] Card padding 24px (32px large/form cards), border `outline-variant(/30)`, radius 12px (16 large).
- [ ] Equal-height cards in a row (`flex flex-col` + `mt-auto` CTA).
- [ ] Long titles: truncate/clamp as in source (`truncate`, `line-clamp-2`), price never wraps under title.

## FORMS
- [ ] Labels above fields: mono 12px uppercase `#40493d`, 8px gap.
- [ ] Inputs 48px tall, white/`surface-container-lowest`, 1px `#bfcaba`, 8px radius, 16px horizontal padding, Inter 16px, placeholder muted.
- [ ] Focus: border `#0d631b` + 2px ring `primary/20`; leading icon turns green on focus.
- [ ] Selects match inputs (chevron visible, `appearance-none` + icon where source does).
- [ ] Textareas match; rich-text toolbar strip `surface-container-low` with 4 icon buttons.
- [ ] Checkboxes/radios 16–20px, green when checked; radio cards highlight `border-primary bg-primary/5`.
- [ ] Toggles 44×24, knob 20px white, on = primary.
- [ ] Field spacing 24px; 2-col rows ≥768px.
- [ ] **Error state** styled (red border/ring + helper text) and **disabled** state styled.
- [ ] Dropzones dashed 2px `outline-variant`, 64px icon circle, hover green.

## BUTTONS
- [ ] Primary: `#0d631b`, white mono caps 12px label, 8px radius, correct padding per size (sm 16×8, md 24×12, lg 32×16), hover `#2e7d32`, press scale .95.
- [ ] Gradient variant (if used) = 135° `#2e7d32 → #1b6d24`, hover brightness 1.1 + 1px lift.
- [ ] Outline: 2px (or 1px per source) green border, hover `primary/5` fill.
- [ ] Neutral/tonal/inverse/danger variants match COMPONENT-SPECS §8.
- [ ] Icons 14–20px with 8px gap; forward actions trailing `arrow_forward`.
- [ ] Loading state (spinner + disabled) and disabled state (50% opacity, not-allowed) present.
- [ ] One rank-1 button per view; primary placed rightmost in action bars.

## IMAGES
- [ ] All photos via `next/image` (or equivalent), `object-cover`, correct aspect ratio box, no stretching, **no tiling** (fix product-detail & about hero defects).
- [ ] Placeholder bg `surface-container-low` while loading.
- [ ] Scrims present where text overlays images (bottom `black/80` gradients, hero left gradient).
- [ ] Hover zoom durations (500/700ms) and overlay fades (opacity 0→100).
- [ ] Avatars circular with specified ring/border; initials fallback styled.
- [ ] No `lh3.googleusercontent.com/aida-public` URLs.
- [ ] Meaningful `alt` text (not the Stitch generation prompt).

## INTERACTION STATES
- [ ] Hover: links → primary; neutral rows/buttons → `surface-container-high`; cards → shadow/lift/border-primary as specified.
- [ ] Focus-visible ring on **every** interactive element (buttons, links, cards that are links, toggles, tabs).
- [ ] Active/pressed scales (.95 / .98 / .99) — CSS only.
- [ ] Selected states: active nav, active sidebar (right rail + filled icon), active tab, selected filter/license, selected thumbnail, current pagination page.
- [ ] Disabled: pagination prev, locked actions, expired rows (opacity/grayscale).
- [ ] Hover-reveal actions also appear on keyboard focus and on touch devices.
- [ ] Motion respects `prefers-reduced-motion`.

---

## DESKTOP (≥1024, compare at 1280 against screenshot)
- [ ] Section order and content match PAGE-SPECS for this page.
- [ ] Grid columns: product 3–4, STL 3, admin KPI 4–6, detail splits 7/5 or 8/4.
- [ ] Sticky elements stick (order summary, product intro column, settings sub-nav, reviews filter).
- [ ] Fixed elements: nav, FAB(s), toasts positioned per spec.
- [ ] Pixel spot-checks: header height, H1 size, card width/gap, footer column positions within ±4px of screenshot (after scaling).

## TABLET (768–1023)
- [ ] Nav links visible; header search hidden; no overlap.
- [ ] Grids at their `md` column counts (RESPONSIVE-SPECS §2); no cards narrower than ~240px (shop sidebar recommendation).
- [ ] Detail/cart/checkout splits stacked; summary below.
- [ ] Account sidebar visible from 768; admin uses drawer (recommended) below 1024.
- [ ] Tables scroll horizontally inside their card.

## MOBILE (<768, test 390 and 360)
- [ ] 16px gutters; no horizontal page scroll anywhere.
- [ ] Menu button works; cart/account reachable.
- [ ] All grids single-column (except the documented 2-col exceptions).
- [ ] Type scaled (display ≈36px, headline-lg 24px) — no awkward 4-line H1.
- [ ] Section padding reduced (~64px).
- [ ] Filters in a drawer/sheet; sort visible.
- [ ] Account pages: sidebar hidden, bottom nav visible, content padded above bottom nav.
- [ ] Touch targets ≥ 44px; hover-only controls visible.
- [ ] Footer single column, bottom bar stacked & centered.
- [ ] Auth cards full-width with 32px inner padding; admin login left panel hidden.

## ADMIN
- [ ] Shared `AdminLayout`: 256px sidebar (`bg-surface`, right border), 64px sticky top bar (glass, bottom border), content `p-8`.
- [ ] Sidebar shows **admin** items from real permissions (not customer items); one active item with right rail + `surface-container-low` + filled icon.
- [ ] Page header: 32px title, muted description, actions right.
- [ ] KPI row, filter bar, table, pagination styled per COMPONENT-SPECS §42/§63/§43/§21.
- [ ] Table header `surface-container-low`, mono uppercase 11–12px; rows 16px vertical padding; dividers; hover tint; row actions.
- [ ] Status chips via StatusBadge mapping.
- [ ] Charts themed with brand colors, no gridlines/axes where source hides them.
- [ ] Top bar never overflows the viewport (manage-customers defect fixed).
- [ ] Forms (edit/upload): 8/4 split ≥1024, stacked below; section cards with icon + 20px title.

## RESPONSIVE OVERFLOW
- [ ] Run at 320, 360, 390, 768, 1024, 1280, 1440, 1920: `document.documentElement.scrollWidth === innerWidth`.
- [ ] Absolute decorations (hero chips, orbs, rings) clipped by `overflow-hidden` parents.
- [ ] Flex rows with input + button have `min-w-0` on the input (cart coupon defect).
- [ ] Title/price rows: title `min-w-0`, price `shrink-0`.
- [ ] Tables wrapped in `overflow-x-auto`.
- [ ] Fixed/sticky headers use `left-0 right-0` / in-flow sticky — never `w-full` + margin.
- [ ] Long unbroken strings (emails, SKUs, file names) truncate or wrap (`truncate`, `break-all` where appropriate).

---

## Per-page sign-off template

```
Page: ____________________   Route: ____________   Stitch folder: ____________________
Viewport checks:  [ ]1280  [ ]1440  [ ]1024  [ ]768  [ ]390  [ ]360
Global ✓  Header ✓  Footer ✓  Cards ✓  Forms ✓  Buttons ✓  Images ✓  States ✓  Overflow ✓  (Admin ✓)
Deviations from screenshot (intentional, cite DESIGN-SYSTEM §12.x):
- 
Open issues:
- 
```
