# Bekaa3D: Implementation Guide

**Audience:** a developer, or another Claude session, who will apply this Stitch design to the **existing Bekaa3D Next.js + React + TypeScript application**.

**The export is a visual reference, not code to ship.** It has 35 static Tailwind-CDN HTML mockups with fake data, decorative JavaScript, and several token bugs. Your job is to **re-skin the real app** so it looks like these screens, while keeping every real behaviour.

---

## 1. How to use this package

| File | Use it for | When |
|---|---|---|
| [README.md](./README.md) | Orientation, file map, page list | First |
| [DESIGN-SYSTEM.md](./DESIGN-SYSTEM.md) | The *rules*: background system, hierarchy, CTA ranking, colour/status mapping, states. **§12 lists every Stitch inconsistency with a recommended resolution.** | Before writing any component |
| [DESIGN-TOKENS.md](./DESIGN-TOKENS.md) + [design-tokens.json](./design-tokens.json) | Exact values: colours, type scale, spacing, radius, shadow, motion, z-index | When setting up the theme (step 2) and whenever you need a number |
| [COMPONENT-SPECS.md](./COMPONENT-SPECS.md) | Class-level anatomy of 64 component patterns, with variants and source references | When building or restyling each shared component |
| [PAGE-SPECS.md](./PAGE-SPECS.md) | Section-by-section composition of all 35 pages, quirks to keep or drop | When restyling a specific route |
| [RESPONSIVE-SPECS.md](./RESPONSIVE-SPECS.md) | Breakpoints, what collapses where, and **gaps the source never designed** (mobile nav, admin mobile) | When building layouts and checking mobile/tablet |
| [ASSET-INVENTORY.md](./ASSET-INVENTORY.md) | Fonts, icons, image slots and ratios, decorations | Theme setup, image components |
| [VISUAL-QA-CHECKLIST.md](./VISUAL-QA-CHECKLIST.md) | Page-by-page visual comparison | After each page |
| [stitch-design-skill.md](./stitch-design-skill.md) | Drop-in Claude project skill enforcing this workflow | Copy into the app repo |
| Original `…/code.html` + `screen.png` | Ground truth for anything ambiguous | Always open both for the page you are working on |

**Resolution order when sources disagree:**
1. The real app's behaviour and data.
2. A **Recommendation** in DESIGN-SYSTEM §12.
3. The `code.html` classes.
4. The `screen.png`.
5. `precision_engineering_system/DESIGN.md`.

The screenshot shows what renders, including Stitch bugs. The classes show what was intended.

---

## 2. Recommended order of work

1. **Audit the target app.** Find its styling approach (Tailwind version? CSS modules? a component library?), its existing shared components (Button, Input, Card, Header, Footer, layouts), its routes, and its loading/error/empty patterns. **Do not change routes to match Stitch page names.**
2. **Centralise tokens.**
   - **Tailwind v3:** add the colour roles, `fontFamily`, `fontSize`, `spacing` (`gutter`, `margin-mobile`, `margin-desktop`, `max-width`), and `borderRadius` (DEFAULT 4px, lg 8px, xl 12px) from `design-tokens.json` to `tailwind.config.ts` under `theme.extend`. Keep the MD3 role names so source classes translate 1:1 (`bg-surface-container-low`, `text-on-surface-variant`, `font-label-caps text-label-caps`).
   - **Tailwind v4:** declare them as `@theme` CSS variables with the same names.
   - **No Tailwind:** emit CSS custom properties (`--color-primary: #0d631b; …`) and reference them everywhere.
   - Add font fallback stacks (DESIGN-TOKENS §2.1).
   - Add utility classes once, globally: `.glass-panel`, `.bg-blueprint`, `.text-gradient-primary`, `.bg-gradient-primary`, Material Symbols base settings, custom scrollbar.
3. **Load fonts properly.** Use `next/font/google` for Hanken Grotesk (400/600/700/800/900), Inter (400/500/600/700), and JetBrains Mono (400/500/600), exposed as CSS variables mapped to `font-headline`/`font-body`/`font-label`. Load Material Symbols Outlined once, not 2–3× as in the source. Alternatively, use an icon component that renders the same glyph names; keep the outline style with weight 400 and the FILL toggle.
4. **Build or restyle primitives** (COMPONENT-SPECS §8, §18, §21, §27–29, §61): Button (variants: primary, gradient, outline, neutral, tonal, inverse, danger, link, icon; sizes sm/md/lg), Badge/StatusBadge, Input/Select/Textarea/Field (label + help + **error**), Checkbox/Radio/RadioCard, Switch, SegmentedControl, Pagination, Avatar, Rating, Price, Icon.
5. **Build layout shells:** `StorefrontLayout` (nav + footer + WhatsApp FAB), `AuthLayout` (patterned background + centered card), `AccountLayout` (sidebar + top bar + mobile bottom nav), `AdminLayout` (sidebar + top bar + drawer below `lg`). Each shell is a single shared component per family.
6. **Build composite components:** ProductCard (variants), StlCard (variants), CategoryTile, FeatureTile, KpiCard, DataTable, FilterSidebar, Toolbar, Gallery, SpecGrid, OrderSummary, CartLineItem, CheckoutStep, PaymentOption, ReviewCard, ModerationCard, EmptyState, Toast, Dialog, Charts.
7. **Restyle pages one at a time.** Follow PAGE-SPECS, wire existing data and handlers into the new components, then run VISUAL-QA-CHECKLIST against `screen.png`.
8. **Do responsive and accessibility passes** (RESPONSIVE-SPECS §1–6; focus states; contrast).

---

## 3. DO

- **Translate Stitch HTML into reusable React components.** The 35 pages repeat the same ~60 patterns. A product card appears in 4 places; build it once with variants.
- **Reuse the existing application's behaviour.** Use its data fetching, server actions/API routes, auth/session, cart state, routing, i18n, analytics, and SEO metadata. Restyle what exists; don't re-implement it.
- **Preserve real API/business logic.** Prices, discounts, stock, licences, offer negotiation states, order statuses, roles and permissions all come from the backend. Map **real** status values onto the StatusBadge palette (DESIGN-SYSTEM §9).
- **Preserve accessibility.** Use semantic elements (`header/nav/main/aside/footer`, `table` with `th scope`), labels tied to inputs (`htmlFor`), `aria-label` on icon-only buttons (the source has none), `aria-current="page"` on active nav, `role="switch"`/`aria-checked` on toggles, `role="tablist"` on tabs, `aria-live` on toasts, and keyboard-reachable hover-only actions. **Add visible `focus-visible` rings.** The source defines input focus only (`ring-2 ring-primary/20`); use `ring-2 ring-primary ring-offset-2` for buttons and links. Respect `prefers-reduced-motion` (disable bounce, spin, and parallax).
- **Centralise tokens.** Every colour, radius, shadow, and font size goes through the theme. Component code should read like `bg-primary text-on-primary rounded-lg`, never `bg-[#0d631b]`.
- **Recreate layouts accurately.** Match container widths (1440px; 1200px for admin forms), gutters (64px desktop / 16px mobile), section rhythm (96px), grid splits (7/5, 8/4, 3/9), card padding (24/32px), and the type pairings (Hanken headings, Inter body, **mono uppercase labels**).
- **Reuse repeated patterns.** One Footer, one storefront Nav, one App Sidebar, one KPI card, one DataTable.
- **Preserve responsive behaviour** from the source (RESPONSIVE-SPECS), and **fill the gaps** it left: a mobile nav menu, filter drawer, admin sidebar drawer, table overflow, and mobile type scale.
- **Fix the Stitch defects** listed in DESIGN-SYSTEM §12 (broken tokens, missing font sizes, tiled background images, cart button overflow, customers header overflow, wrong admin menus) rather than reproducing them.
- **Use `next/image`** for every photo slot (`fill`, `object-cover`, `sizes`, placeholder colour `surface-container-low`).
- **Use real content.** Replace all Stitch copy and numbers with the app's data or existing copy. Keep Stitch marketing copy only if the product owner approves it.

## 4. DO NOT

- **Do not copy the static JS blindly.** The source scripts are demos: `mousedown` scale effects on every button, `console.log` handlers, `alert()`/`confirm()`, `setTimeout` fake submissions, client-side DOM filtering, parallax on mousemove, and IntersectionObserver fade-ins on every div. Re-create only meaningful interactions with React state and CSS: password visibility toggle, quantity stepper, gallery thumbnail selection and hover zoom, tabs, FAQ disclosure, notification dropdown, toast, sidebar collapse, and the nav shadow on scroll.
- **Do not replace real forms with static HTML.** Keep the app's form library, validation, server errors, CSRF, and submission flow. Only restyle the fields.
- **Do not remove loading, error, or empty states.** The source rarely designs them. Style them using DESIGN-SYSTEM tokens: skeleton `bg-surface-container-low animate-pulse`, error field `border-error ring-error/20`, empty state COMPONENT-SPECS §49, toast §47.
- **Do not replace functional backend logic** with Stitch placeholders (fake cart badges, hard-coded totals, mock charts).
- **Do not create fake data.** No hard-coded "Dr. Elena Vance", "$42,910", or "© 2024" in components. Charts render real series.
- **Do not alter routes** to match Stitch folder names or nav labels. The Stitch nav link sets are inconsistent (DESIGN-SYSTEM §12.7). Use the app's real navigation items with Stitch styling.
- **Do not duplicate components** per page (e.g. three different footers, four status chip palettes). Pick the recommended canonical variant.
- **Do not scatter hard-coded colours or spacing** (`text-[#25D366]`, `p-[13px]`). Add a token if a value is genuinely new (e.g. `--color-whatsapp: #25D366`).
- **Do not hot-link the `lh3.googleusercontent.com/aida-public` placeholder images.**
- **Do not ship the Tailwind CDN script** or per-page inline `tailwind.config`.
- **Do not introduce a dark theme.** None is designed.

---

## 5. Mapping cheatsheet (Stitch → app component)

| Stitch pattern | Build as | Key props / variants |
|---|---|---|
| Glass top nav (§1) | `<SiteHeader>` | `links` from router config, `activeHref`, `cartCount`, `user` |
| Footer (§6) | `<SiteFooter>` | columns from config; newsletter wired to the real endpoint, if any |
| WhatsApp FAB (§7) | `<WhatsAppButton>` | phone from settings (admin settings has a "WhatsApp Settings" section) |
| Buttons (§8) | `<Button variant size iconLeft iconRight loading>` | loading shows a spinner and `disabled` |
| Product card (§11) | `<ProductCard variant="showcase|catalog|wishlist|compact">` | real product, onAddToCart, onWishlist |
| STL card (§12) | `<StlCard variant="home|marketplace|related|library|dashboard">` | licence, formats, price/free, onBuy, onOffer, onDownload |
| Status chips (§18) | `<StatusBadge status>` | single mapping table |
| Filters (§19) | `<FilterPanel>` + `<FilterDrawer>` (mobile) | bound to the existing query params |
| KPI card (§42) | `<KpiCard icon label value delta trend>` | |
| Data table (§43) | `<DataTable columns rows selectable rowActions pagination>` | hover-reveal actions **also** reachable via keyboard focus (`group-focus-within:opacity-100`) |
| Charts (§44) | the app's chart lib, themed: primary `#0d631b`, secondary `#3e6a00`, tertiary `#923357`, lime `#b9f474`, grid hidden, tension 0.4 | |
| App sidebar (§40) | `<AppSidebar items active collapsible>` | admin items from the role's permissions |
| Auth card (§38) | `<AuthCard variant="login|register|reset|admin">` | existing auth handlers |

---

## 6. Token setup snippet (reference, Tailwind v3 `theme.extend`)

```ts
// values from design-tokens.json — keep names identical to the Stitch classes
colors: {
  primary: '#0d631b', 'on-primary': '#ffffff', 'primary-container': '#2e7d32', 'on-primary-container': '#cbffc2',
  'primary-fixed': '#a3f69c', 'primary-fixed-dim': '#88d982', 'on-primary-fixed': '#002204', 'on-primary-fixed-variant': '#005312',
  'inverse-primary': '#88d982', 'surface-tint': '#1b6d24',
  secondary: '#3e6a00', 'on-secondary': '#ffffff', 'secondary-container': '#b9f474', 'on-secondary-container': '#437000',
  'secondary-fixed': '#b9f474', 'secondary-fixed-dim': '#9ed75b', 'on-secondary-fixed': '#0f2000', 'on-secondary-fixed-variant': '#2e4f00',
  tertiary: '#923357', 'on-tertiary': '#ffffff', 'tertiary-container': '#b14b6f', 'on-tertiary-container': '#ffedf0',
  'tertiary-fixed': '#ffd9e2', 'tertiary-fixed-dim': '#ffb1c7', 'on-tertiary-fixed': '#3f001c', 'on-tertiary-fixed-variant': '#7f2448',
  error: '#ba1a1a', 'on-error': '#ffffff', 'error-container': '#ffdad6', 'on-error-container': '#93000a',
  background: '#f9f9ff', 'on-background': '#141b2b', surface: '#f9f9ff', 'surface-bright': '#f9f9ff', 'surface-dim': '#d3daef',
  'surface-container-lowest': '#ffffff', 'surface-container-low': '#f1f3ff', 'surface-container': '#e9edff',
  'surface-container-high': '#e1e8fd', 'surface-container-highest': '#dce2f7', 'surface-variant': '#dce2f7',
  'on-surface': '#141b2b', 'on-surface-variant': '#40493d', 'inverse-surface': '#293040', 'inverse-on-surface': '#edf0ff',
  outline: '#707a6c', 'outline-variant': '#bfcaba', whatsapp: '#25D366',
},
fontFamily: {
  display: ['var(--font-hanken)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
  'headline-lg': ['var(--font-hanken)', 'ui-sans-serif', 'sans-serif'],
  'headline-md': ['var(--font-hanken)', 'ui-sans-serif', 'sans-serif'],
  'body-lg': ['var(--font-inter)', 'ui-sans-serif', 'sans-serif'],
  'body-md': ['var(--font-inter)', 'ui-sans-serif', 'sans-serif'],
  'label-caps': ['var(--font-jetbrains)', 'ui-monospace', 'monospace'],
},
fontSize: {
  display: ['48px', { lineHeight: '1.1', letterSpacing: '-0.02em', fontWeight: '800' }],
  'headline-lg': ['32px', { lineHeight: '1.2', letterSpacing: '-0.01em', fontWeight: '700' }],
  'headline-lg-mobile': ['24px', { lineHeight: '1.2', fontWeight: '700' }],
  'headline-md': ['20px', { lineHeight: '1.3', fontWeight: '600' }],
  'body-lg': ['18px', { lineHeight: '1.6', fontWeight: '400' }],
  'body-md': ['16px', { lineHeight: '1.5', fontWeight: '400' }],
  'label-caps': ['12px', { lineHeight: '1', letterSpacing: '0.05em', fontWeight: '600' }],
},
spacing: { unit: '4px', gutter: '24px', 'margin-mobile': '16px', 'margin-desktop': '64px', 'max-width': '1440px' },
borderRadius: { DEFAULT: '0.25rem', lg: '0.5rem', xl: '0.75rem', full: '9999px' },
maxWidth: { container: '1440px', form: '1200px' },
boxShadow: { ambient: '0 4px 20px -2px rgba(20,27,43,0.04)', 'card-hover': '0 20px 40px rgba(0,0,0,0.08)' },
```

Note that `@tailwindcss/forms` is used by the source (checkbox/radio/select styling). Include it, or replicate its checkbox look: 16–20px, 4px radius, `outline-variant` border, checked `primary`.

---

## 7. Definition of done (per page)

- [ ] Uses the shared layout shell and shared components (no page-local copies).
- [ ] All values come from tokens; no new hex literals.
- [ ] Matches `screen.png` at 1280px on every VISUAL-QA-CHECKLIST item (with the documented Stitch defects intentionally fixed).
- [ ] Works at 360px, 768px, 1024px, and 1440px with no horizontal overflow.
- [ ] Real data, real handlers, real routes; loading, error, and empty states present.
- [ ] Keyboard navigable with visible focus; icon buttons labelled; contrast OK (watch out for `text-secondary-container` on a light background, `text-outline-variant` placeholder text, and 10px labels).
- [ ] No Stitch demo JS, CDN Tailwind, or placeholder image URLs.
