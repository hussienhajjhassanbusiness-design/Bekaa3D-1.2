# Bekaa3D — Design Tokens

All values below are **extracted from the Stitch source**: each page's inline `tailwind.config` (identical colour/typography/spacing block on all 35 pages), its `<style>` block, and the Tailwind class usage counted across every `code.html`. Where Tailwind defaults are used (e.g. `shadow-lg`, `text-sm`), the resolved Tailwind v3 value is given.

> Source of truth priority used in this document:
> 1. Tailwind config inside each `code.html` (what actually renders)
> 2. Tailwind v3 default theme (for un-customised utilities)
> 3. `precision_engineering_system/DESIGN.md` (design intent — **where it conflicts with the code it is flagged**)

A machine-readable copy lives in [`design-tokens.json`](./design-tokens.json).

Usage counts are written as `N uses / M pages` (from a scan of all 35 `code.html` bodies).

---

## 1. Colour

The palette is a **Material Design 3 tonal scheme** generated from a green seed (`surface-tint #1b6d24`). Token names are MD3 role names and are used verbatim as Tailwind colour names (`bg-primary`, `text-on-surface-variant`, …).

### 1.1 Core brand roles

| Token | Hex | RGB | Role in the UI | Usage |
|---|---|---|---|---|
| `primary` | `#0d631b` | 13, 99, 27 | Main brand green. Solid CTAs, active nav text/underline, prices, links, filled stars (some pages), focus rings, selected pagination. | `bg-primary` 93/31, `text-primary` 412/35 |
| `on-primary` | `#ffffff` | 255,255,255 | Text/icons on primary. | |
| `primary-container` | `#2e7d32` | 46, 125, 50 | Lighter green. **Hover state** of primary buttons (`hover:bg-primary-container` 25/13), secondary solid buttons, gradient start, active admin nav pill. | `bg-primary-container` 36/17 |
| `on-primary-container` | `#cbffc2` | 203,255,194 | Text on `primary-container` (pale mint). | |
| `primary-fixed` | `#a3f69c` | 163,246,156 | Pale green chip backgrounds (`+12%` trend chips, `PRO MEMBER`, `LIVE`), selection highlight. | |
| `primary-fixed-dim` | `#88d982` | 136,217,130 | "Delivered" chip bg (admin), eyebrow text on dark hero, selection bg. | |
| `on-primary-fixed` | `#002204` | 0,34,4 | Text on primary-fixed chips. | |
| `on-primary-fixed-variant` | `#005312` | 0,83,18 | Link hover (login), "Shipped" chip text. | |
| `inverse-primary` | `#88d982` | 136,217,130 | Accent icon on dark (`bg-inverse-surface`) cards. | |
| `surface-tint` | `#1b6d24` | 27,109,36 | Gradient end colour; "COMMERCIAL LICENSE" badge bg on home. | |
| `secondary` | `#3e6a00` | 62,106,0 | Olive green. Category badges, "Shipped"/"In Stock" text, star colour on Shop, footer link hover, gradient end (signature gradient). | `text-secondary` 60/16 |
| `on-secondary` | `#ffffff` | | | |
| `secondary-container` | `#b9f474` | 185,244,116 | **Lime accent.** "IN STOCK" pills, "Approved"/"Delivered" chips, server-online dot, donut 2nd segment. | `bg-secondary-container` 16/13 |
| `on-secondary-container` | `#437000` | 67,112,0 | Text on lime chips. | |
| `secondary-fixed` | `#b9f474` | 185,244,116 | Same lime; promo banner CTA bg, accent text on dark promo, progress fill on dark. | |
| `secondary-fixed-dim` | `#9ed75b` | 158,215,91 | Average-rating stars (admin reviews). | |
| `on-secondary-fixed` | `#0f2000` | 15,32,0 | Text on lime CTA. | |
| `on-secondary-fixed-variant` | `#2e4f00` | 46,79,0 | "Commercial" license chip text (admin STL). | |
| `tertiary` | `#923357` | 146,51,87 | Raspberry accent. Discount badges (`-30%`), Automotive badge, "Low Stock", third chart series, "Pending" accents. | `text-tertiary` 18/11 |
| `on-tertiary` | `#ffffff` | | | |
| `tertiary-container` | `#b14b6f` | 177,75,111 | "EXCLUSIVE" badge bg; light tint backgrounds (`/10`, `/20`). | |
| `on-tertiary-container` | `#ffedf0` | | | |
| `tertiary-fixed` | `#ffd9e2` | 255,217,226 | "Pending" / "Open Offers" chip bg. | |
| `tertiary-fixed-dim` | `#ffb1c7` | | (declared, unused) | |
| `on-tertiary-fixed` | `#3f001c` | | (declared) | |
| `on-tertiary-fixed-variant` | `#7f2448` | 127,36,72 | Text on tertiary-fixed chips. | |

### 1.2 Surfaces & neutrals

| Token | Hex | Role | Usage |
|---|---|---|---|
| `background` | `#f9f9ff` | Page background (cool off-white with a faint blue cast). | `bg-background` 23/23 |
| `surface` | `#f9f9ff` | Identical to background. Used for sidebars, nav glass base (`bg-surface/80`). | `bg-surface` 54/20 |
| `surface-bright` | `#f9f9ff` | Identical. Login input bg, table row hover. | |
| `surface-container-lowest` | `#ffffff` | Pure white. **Cards**, admin sidebar, footer (some pages). | 116/25 |
| `surface-container-low` | `#f1f3ff` | Very light lavender. Table headers, sidebar active item bg, alternating sections, image placeholders, inputs. | 126/31 |
| `surface-container` | `#e9edff` | Light lavender. Icon tiles, chips, select backgrounds, hover states. | 87/20 |
| `surface-container-high` | `#e1e8fd` | **Most common hover bg** (`hover:bg-surface-container-high` 140/17). Feature cards on product detail. | |
| `surface-container-highest` | `#dce2f7` | Add-to-cart icon button bg, format chips, footer bg (about/contact/STL details). | 40/13 |
| `surface-variant` | `#dce2f7` | Same as highest. Toggle off-track, hover. | |
| `surface-dim` | `#d3daef` | Map placeholder, avatar bg. | |
| `inverse-surface` | `#293040` | Dark navy-charcoal cards ("Our Vision", DfAM), tooltips, toast, dark filter button. | 11/4 |
| `inverse-on-surface` | `#edf0ff` | Text on inverse-surface. | |
| `on-surface` / `on-background` | `#141b2b` | **Primary text** (near-black navy). Also used as dark promo bg (`bg-[#141b2b]`). | `text-on-surface` 352/35 |
| `on-surface-variant` | `#40493d` | **Secondary/muted text** (dark grey-green). By far the most used text colour. | 1018/35 |
| `outline` | `#707a6c` | Tertiary text (captions, placeholders, table header text in admin), outlined button borders. | `text-outline` 111/16 |
| `outline-variant` | `#bfcaba` | **Default border & divider colour.** Also toggle-off track, scrollbar thumb. | `border-outline-variant` 471/33 |

### 1.3 Semantic

| Purpose | Token(s) | Hex | Notes |
|---|---|---|---|
| Error / destructive | `error` | `#ba1a1a` | Delete buttons, logout link, notification dot, "Out of Stock", `-2%` trend. |
| Error container | `error-container` | `#ffdad6` | "Cancelled"/"Suspended"/"Pending" (reviews) chip bg; delete hover bg. |
| On error container | `on-error-container` | `#93000a` | Chip text. |
| Success | `primary` / `secondary` / `secondary-container` | `#0d631b` / `#3e6a00` / `#b9f474` | No dedicated success token; green family is reused. |
| Warning | Tailwind `amber-*` (not in config) | `amber-100 #fef3c7`, `amber-200 #fde68a`, `amber-500 #f59e0b`, `amber-600 #d97706`, `amber-700 #b45309`, `amber-800 #92400e` | Used for "Pending" offers and "Processing" payment dot. **Off-palette.** |
| Info | Tailwind `blue-*` (not in config) | `blue-100 #dbeafe`, `blue-200 #bfdbfe`, `blue-600 #2563eb`, `blue-700 #1d4ed8`, `blue-800 #1e40af` | "Counter Offer"/"Countered" chips only. **Off-palette.** |
| Accepted / Rejected (offer history) | `green-100 #dcfce7` / `green-700 #15803d`, `red-100 #fee2e2` / `red-700 #b91c1c` | | Offer history page only. **Off-palette.** |
| Rating stars | `amber-400 #fbbf24` (home, wishlist), `amber-500 #f59e0b` (STL pages, analytics), `primary`, `secondary` | | See inconsistencies in DESIGN-SYSTEM.md §12. |

### 1.4 Off-palette literals found in source

| Value | Where | Purpose |
|---|---|---|
| `#25D366` | home, shop (FAB), home CTA, STL details | WhatsApp brand green (FAB bg, button bg, text, `/30` border, `/5` hover bg) |
| `#141b2b` | home promo banner `bg-[#141b2b]` | Equals `on-surface`. Dark promo card. |
| `#003087` | system settings | PayPal brand icon colour |
| `#4285F4 #34A853 #FBBC05 #EA4335` | user login | Google "G" logo SVG fills |
| `#1877F2` | user login | Facebook logo SVG fill |
| `#E5E7EB` | `.blueprint-bg` (forgot password, manage STL), discounts glass border | Tailwind gray-200; grid lines. Also named in DESIGN.md as border colour. |
| `#d1d5db` (`gray-300`) | toggle knob border `after:border-gray-300` | |
| `white` / `black` alpha | overlays | `bg-black/40` image hover overlay (11 uses), `bg-black/30`→`/10` category tiles, `from-black/80` gradients, `bg-white/80`, `/90`, `/50`, `/20` glass |
| `#388e3c` | login `.brand-gradient:hover` | gradient hover start (Material green 600) |

### 1.5 Opacity modifiers in use (tints)

The design relies heavily on alpha tints of tokens. Most frequent:
`bg-primary/10` (40/19) · `border-outline-variant/30` (117/18) · `border-outline-variant/20` (27/9) · `bg-surface/80` (17/13) · `hover:bg-primary/5` (15/7) · `bg-primary-container/10` (9/6) · `bg-secondary-container/20` · `bg-tertiary-container/10` · `bg-error-container/10–30` · `text-on-surface-variant/40–80` · `shadow-primary/20` (10/10).

### 1.6 Gradients

| Name in source | Value | Pages | Recommendation |
|---|---|---|---|
| `.btn-gradient`, `.green-gradient-btn`, `.brand-gradient`, `.primary-gradient` (edit) | `linear-gradient(135deg, #2e7d32 0%, #1b6d24 100%)` | about, contact, user login, edit product | **Dominant (4 pages) → `--gradient-primary`** |
| `.signature-gradient`, `.text-gradient` | `linear-gradient(135deg, #0d631b 0%, #3e6a00 100%)` | STL marketplace (buttons), about (text) | `--gradient-signature` (DESIGN.md "signature green gradient") |
| `.text-gradient-primary` | `linear-gradient(to right, #0d631b, #3e6a00)` | home H1 accent "3D Solutions" | text gradient |
| `.primary-gradient` (shop), `.sidebar-active` | `linear-gradient(135deg, #0d631b 0%, #1b6d24 100%)` | shop, account dashboard | variant |
| `.btn-primary-gradient` (forgot) | `linear-gradient(135deg, #0d631b 0%, #2e7d32 100%)` | forgot password | variant |
| `.btn-primary-gradient` (STL details) | `linear-gradient(135deg, #2e7d32 0%, #0d631b 100%)` | STL details | variant (reversed) |
| `bg-gradient-to-r from-primary to-primary-container` | `#0d631b → #2e7d32`, 90° | product details Add to Cart | variant |
| Logo gradient (home) | `bg-gradient-to-r from-primary to-secondary-fixed` = `#0d631b → #b9f474` text | home | unique |
| `.brand-gradient:hover` | `linear-gradient(135deg, #388e3c 0%, #2e7d32 100%)` | login | hover variant |
| Image scrims | `bg-gradient-to-t from-black/80 via-transparent to-transparent`; `from-black/80 via-black/20 to-transparent`; `from-inverse-surface/80 to-transparent`; `bg-gradient-to-r from-on-surface/80 to-transparent` (about hero); `from-primary/90 to-transparent` (discount banner) | various | |
| Radial glow | `bg-[radial-gradient(circle_at_top_right,_var(--tw-gradient-stops))] from-white/10 to-transparent` | home CTA | |
| Conic donut | `conic-gradient(#0d631b 0% 65%, #b9f474 65% 100%)` | admin dashboard | |

Gradient hover rule (where specified): `filter: brightness(1.1)` + `translateY(-1px)` + `box-shadow: 0 4px 12px rgba(46,125,50,0.2)`.

### 1.7 Background patterns ("blueprint")

| Class (page) | Definition |
|---|---|
| `.blueprint-grid` (admin login, manage orders, system settings, manage discounts) and `body` (manage physical products), `.blueprint-bg` (purchased downloads, user profile), `.grid-pattern` (wishlist, at `opacity-50`) | `linear-gradient(to right, rgba(13,99,27,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(13,99,27,0.05) 1px, transparent 1px)` · `background-size: 40px 40px` → **dominant (8 pages)** |
| `.blueprint-grid` (upload physical product) | same lines, `24px 24px` |
| `.blueprint-bg` (order history) | `rgba(13,99,27,0.03)` lines, `20px 20px` |
| `.blueprint-bg` (forgot password, manage STL) | bg `#f9f9ff`; lines `#e5e7eb`; 40px |
| `.blueprint-bg` (manage offers) | lines `#e1e8fd`; 40px |
| `.blueprint-bg` (upload STL) | lines `#e9edff`; 40px |
| `.blueprint-grid` (admin analytics) | lines `#bfcaba22`; 24px |
| `body` (manage customers) | lines `rgba(191,202,186,0.1)`; 24px |
| `body` (my reviews) | lines `rgba(203,255,194,0.05)`; 40px |
| `.grid-bg` (admin dashboard) | `radial-gradient(circle, #bfcaba 1px, transparent 1px)` 40px (dot grid) |
| `body` (manage categories) | `radial-gradient(circle at 2px 2px, #bfcaba 1px, transparent 0)` 40px (dot grid) |
| `.blueprint-bg` (manage reviews) | `radial-gradient(#bfcaba 0.5px, transparent 0.5px)` 24px |
| `.bg-blueprint` (registration) | `radial-gradient(circle at 1px 1px, rgba(13,99,27,0.05) 1px, transparent 0)` 24px |
| `.technical-pattern` (user login) | inline SVG data-URI dot/circle pattern, 100×100 tile, on `#f9f9ff` |
| `.blueprint-grid` (edit product) | dots + lines `#bfcaba` 40px at `opacity: 0.1` |
| About CTA | `radial-gradient(circle, white 1px, transparent 1px)` 32px at 10% opacity on green |

---

## 2. Typography

### 2.1 Families

| Tailwind key(s) | Family | Google Fonts weights loaded | Role |
|---|---|---|---|
| `font-display`, `font-headline-lg`, `font-headline-lg-mobile`, `font-headline-md` | **Hanken Grotesk** | 400, 600, 700, 800 (plus `100..900` on ~half the pages) | Headings, logo, prices, KPI numbers |
| `font-body-lg`, `font-body-md` | **Inter** | 400, 500, 600 (pages vary: some 400/500 only) | All body/UI text (set on `<body>`) |
| `font-label-caps` | **JetBrains Mono** | 600 (some pages 400/500/600) | Labels, eyebrows, buttons, table headers, chips, SKUs, technical values |
| `font-mono` (10 uses / 4 pages) | Tailwind default mono stack `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace` | — | Order IDs (admin dashboard), "68% COMPLETE", original price column. **Not JetBrains.** |
| Icons | **Material Symbols Outlined** (variable: `wght 100..700`, `FILL 0..1`) | | See §9 |

**Fallback stacks:** the config declares **no fallbacks** (e.g. `["Hanken Grotesk"]`). Recommended:
- Headline: `"Hanken Grotesk", ui-sans-serif, system-ui, sans-serif`
- Body: `"Inter", ui-sans-serif, system-ui, sans-serif`
- Label: `"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace`

### 2.2 Type scale (custom tokens — `text-*` utilities)

| Token | Size | Line height | Weight (baked in) | Letter spacing | Family pairing | Usage |
|---|---|---|---|---|---|---|
| `display` | **48px** | 1.1 (52.8px) | 800 | -0.02em | `font-display` | Page H1s on storefront (`Your Cart`, `Digital STL Marketplace`, hero), large prices, KPI numbers (manage reviews). 19 uses / 10 pages |
| `headline-lg` | **32px** | 1.2 (38.4px) | 700 | -0.01em | `font-headline-lg` / `font-display` | Section H2s, account/admin page titles. 63/30 |
| `headline-lg-mobile` | 24px | 1.2 | 700 | — | | **Declared but never used** in markup |
| `headline-md` | **20px** | 1.3 (26px) | 600 | — | `font-headline-md` / `font-display` | Card titles, logo, subsection headings, card prices. 128/34 |
| `body-lg` | **18px** | 1.6 (28.8px) | 400 | — | `font-body-lg` | Hero/intro paragraphs. |
| `body-md` | **16px** | 1.5 (24px) | 400 | — | `font-body-md` | Default body. 161/18 |
| `label-caps` | **12px** | 1.0 (12px) | 600 | **0.05em** | `font-label-caps` | Labels, eyebrows, table headers, buttons. 209/22. **Note: the token does NOT apply `text-transform`; uppercase comes from the literal text or a separate `uppercase` class (217 uses).** |

> ⚠ **Critical Stitch pattern:** `font-<token>` sets **only the family**; `text-<token>` sets size/line-height/weight/tracking. Stitch frequently writes `font-headline-md` **without** `text-headline-md` (and `font-label-caps` without `text-label-caps`). In those cases the element renders in the right family but at the **inherited 16px / weight 400** (or whatever Tailwind size class sits alongside, e.g. `text-sm`). The screenshots show these smaller renders. See DESIGN-SYSTEM.md §12 for how to handle this.

> ⚠ Three pages (`manage_categories_bekaa3d_admin`, `product_details_bekaa3d_precision_kit`, `user_registration_bekaa3d_precision_engineering`) have **no `fontSize` block** in their config, so every `text-display / text-headline-* / text-body-* / text-label-caps` class is a no-op there (headings render 16px in the screenshots).

### 2.3 Tailwind default sizes also used heavily

| Class | Size / line-height | Usage | Typical role |
|---|---|---|---|
| `text-[10px]` | 10px | **226 / 31** | Badges, chips, eyebrow labels, mono captions, bottom-nav labels |
| `text-[11px]` | 11px | 73 / 14 | Table headers (admin), chip text, small mono buttons |
| `text-xs` | 12px / 16px | 245 / 24 | Captions, meta text, helper text |
| `text-[12px]` | 12px | 57 / 9 | Meta lines, small mono buttons |
| `text-sm` | 14px / 20px | **426 / 28** | Secondary body, table cells, buttons in dense UIs |
| `text-[13px]` | 13px | 4 / 1 | Mono order IDs (admin dashboard) |
| `text-[14px]` | 14px | 35 / 11 | Names, small body |
| `text-lg` | 18px / 28px | 56 / 11 | Card titles (wishlist), prices (shop) |
| `text-xl` | 20px / 28px | 24 / 5 | Stat numbers (STL details), tile titles |
| `text-2xl` | 24px / 32px | 12 / 6 | Prices (STL details), stat numbers, icons |
| `text-[24px]` | 24px | 5 | KPI values (admin console, with `font-headline-lg tracking-tight`) |
| `text-3xl` | 30px / 36px | 24 / 9 | KPI numbers (manage orders), bento tile title, icons |
| `text-[32px]` | 32px | 3 | KPI numbers (discounts) |
| `text-4xl` | 36px / 40px | 12 / 5 | KPI numbers (offer history), large icons |
| `text-[40px]` | 40px | 4 | Stats band (about) |
| `text-6xl` | 60px | 5 / 1 | Decorative icons (registration) |
| `text-[9px]` | 9px | 4 | Chart axis labels, notification timestamps |
| `text-[18px] / [20px] / [22px] / [48px] / [120px] / [240px]` | | | Almost exclusively **icon** sizes |

### 2.4 Weights, tracking, transform

- Weights used: `font-bold` 700 (356/33), `font-medium` 500 (121/16), `font-semibold` 600 (67/12), `font-extrabold` 800 (18/17, logos), `font-black` 900 (4/4, logos — only renders as 900 where the `100..900` font link is present), `font-normal` (1).
- Tracking: `tracking-widest` 0.1em (56/24 — eyebrows, bottom-nav, footer labels), `tracking-wider` 0.05em (30/11), `tracking-tight` -0.025em (19/11, logos/titles), `tracking-tighter` -0.05em (12/9, logos, "TOTAL DUE"), `tracking-[0.2em]` (4/4, eyebrows "ESTABLISHED 2014", copyright lines).
- Transform: `uppercase` 217/29. Mono labels are almost always uppercase (via text or class).
- Leading: `leading-relaxed` 1.625 (28/12, paragraphs), `leading-tight` 1.25 (14/5), `leading-snug` 1.375, `leading-none` 1.
- `italic` 15/7 — testimonial/review quotes and "seller response" cells.
- `antialiased` on several admin/auth bodies.

### 2.5 Text-role mapping (recommended canonical set)

| Role | Spec |
|---|---|
| Hero H1 | Hanken Grotesk 48/1.1, 800, -0.02em, `on-surface` (white on image heroes) |
| Page title (account/admin) | Hanken Grotesk 32/1.2, 700, -0.01em, `on-surface` |
| Section title | Hanken Grotesk 32/1.2, 700 (storefront: centered, mb-4/16px, then muted 16px subtitle max-w 672px) |
| Card title | Hanken Grotesk 20/1.3, 600 |
| Compact card / row title | Hanken Grotesk or Inter 16px bold (`font-bold`) or 14px semibold |
| Body | Inter 16/1.5, 400, `on-surface-variant` |
| Lead paragraph | Inter 18/1.6, 400, `on-surface-variant` |
| Secondary body | Inter 14/20, `on-surface-variant` |
| Caption / meta | Inter 12/16, `on-surface-variant` or `outline` |
| Label / eyebrow / table header | JetBrains Mono 12/1.0, 600, 0.05em, UPPERCASE, `on-surface-variant` (admin tables: `outline`) |
| Micro label / chip | JetBrains Mono 10–11px, 600, uppercase, often `tracking-widest` |
| Button text | JetBrains Mono 12px 600 0.05em uppercase (dominant) |
| Nav link | Inter 16px, `on-surface-variant`; active: `primary` + bold + 2px bottom border |
| Price (card) | Hanken Grotesk 20px 600 `primary` |
| Price (detail hero) | Hanken Grotesk 48px 800 `primary`; strike-through 20px `on-surface-variant` |

---

## 3. Spacing

### 3.1 Custom spacing tokens (config `spacing`)

| Token | Value | Utilities that work | Notes |
|---|---|---|---|
| `unit` | 4px | `p-unit`, `gap-unit` … | Base unit (never actually used as a class) |
| `gutter` | **24px** | `gap-gutter` (25/16), `px-gutter`, `p-gutter`, `space-y-gutter`, `mb-gutter` | Grid gutter |
| `margin-mobile` | **16px** | `px-margin-mobile`, `p-margin-mobile` | Mobile page gutter |
| `margin-desktop` | **64px** | `px-margin-desktop` (37/13), `p-margin-desktop` | Desktop page gutter |
| `max-width` | **1440px** | `max-w-max-width` (22/10) — works because Tailwind ≥3.4 extends `max-w` with the spacing scale | Content max width |

**Broken token references** (render as nothing): `max-w-container-max`, `max-w-spacing-max-width`, `px-spacing-margin-desktop`, `p-spacing-margin-mobile`, `md:p-spacing-margin-desktop`, `py-unit-margin-desktop`, `px-unit-gutter`, `max-width` (bare class). See DESIGN-SYSTEM.md §12.

### 3.2 Scale actually in use (Tailwind 4px scale)

| Step | px | Most frequent utilities |
|---|---|---|
| 0.5 | 2 | `py-0.5` (chips), `mt-0.5`, `p-0.5` (avatar ring) |
| 1 | 4 | `py-1` (124/28 chips), `gap-1`, `mb-1`, `space-y-1` (sidebar nav) |
| 1.5 | 6 | `py-1.5`, `gap-1.5`, `p-1.5` (row icon buttons), `space-y-1.5` (field label→input) |
| 2 | 8 | `p-2` (153/29 icon buttons), `gap-2` (255/31), `py-2`, `mb-2`, `space-y-2` |
| 2.5 | 10 | `py-2.5` (36/11 buttons/inputs) |
| 3 | 12 | `py-3` (225/28 — buttons, inputs, nav items), `gap-3` (278/31 — icon+label), `px-3` |
| 4 | 16 | `py-4` (292/25), `px-4` (264/31), `p-4`, `gap-4`, `mb-4`, `space-y-4` |
| 5 | 20 | `py-5` (table rows, big CTAs), `p-5` |
| 6 | 24 | `px-6` (**367/28 — most used padding**), `p-6` (123/27 card padding), `gap-6`, `mb-6`, `space-y-6` |
| 8 | 32 | `p-8` (60/25 large cards), `gap-8`, `mb-8`, `px-8` |
| 10 | 40 | `mb-10`, `p-10`, `py-10` |
| 12 | 48 | `p-12`, `px-12` (admin headers), `mb-12`, `mt-12`, `gap-12` |
| 16 | 64 | `py-16`, `mb-16`, `gap-16`, `p-16` |
| 20 | 80 | `py-20`, `pb-20`, `mb-20` |
| 24 | 96 | `py-24` (**storefront section rhythm**), `pt-24` (page top under fixed nav), `mt-24` |
| 32 | 128 | `pt-32` (hero/cart top), `mt-32` (product detail sections) |

### 3.3 Spacing roles

| Role | Value |
|---|---|
| Page gutter, desktop | 64px (`px-margin-desktop`) — storefront; admin/account content uses 32px (`p-8`) or 48px (`px-12`) |
| Page gutter, mobile | 16px (`px-margin-mobile`) where responsive; many pages keep 64px on mobile (bug) |
| Top offset under fixed 64px nav | 96px (`pt-24`) typical; 128px (`pt-32`) for cart/hero/contact |
| Storefront section vertical padding | 96px (`py-24`); compact bands 64px (`py-16`) / 80px (`py-20`) |
| Section header → content | 64px (`mb-16`) centered headers; 48px (`mb-12`) split headers |
| Card padding | 24px (`p-6`) dominant; 32px (`p-8`) for feature/summary/form cards; 16px (`p-4`) compact cards; 20px (`p-5`) category/KPI |
| Grid gaps | 24px (`gap-6` / `gap-gutter`) dominant; 32px (`gap-8`) product grids; 16px (`gap-4`) thumbnails/spec tiles; 48–64px (`gap-12/16`) hero columns |
| Form vertical rhythm | 24px between fields (`space-y-6`); label→input 8px (`mb-2` / `space-y-2`) or 6px (`space-y-1.5`) |
| Inline icon+text gap | 8px (`gap-2`) or 12px (`gap-3`, sidebar items) |
| Table cell padding | `px-6 py-4` (24×16) dominant; `py-5` (20px) in account tables; `p-4` (16) in discounts |

---

## 4. Layout

| Token | Value | Evidence |
|---|---|---|
| Max content width | **1440px** | `max-w-max-width`, `max-w-[1440px]` (17/9); DESIGN.md |
| Form page max width | 1200px | edit product, upload STL `max-w-[1200px]` |
| Paragraph measure | 672px (`max-w-2xl`, 12/9); 768px (`max-w-3xl`); 512px (`max-w-lg`); 448px (`max-w-md`) | |
| Auth card widths | Login 440px; Forgot 448px (`max-w-md`); Register 640px; Admin login 1100px (split) | |
| Sidebar width | **256px** (`w-64`, 29/24) | all account/admin pages |
| Collapsed sidebar (JS) | 80px | admin dashboard toggle script |
| Top nav height | **64px** (`h-16`, 25/17) dominant; 80px (`h-20`) STL marketplace; padding-based (`py-4` + 40px content ≈ 72px) home/shop/product/order history; admin categories `py-6` ≈ 88px | |
| Admin top bar | 64px (`h-16`), `fixed left-64 right-0` or `sticky top-0` | |
| Grid | 12-column (`grid-cols-12`, `lg:col-span-7/5`, `8/4`, `3/9`) for detail/checkout/settings; DESIGN.md: 12-col desktop, 4-col mobile | |
| Product grid | 4-up home (`md:grid-cols-4`), 3-up shop/marketplace (`lg:grid-cols-3`, `xl:grid-cols-3`), 4-up related | |
| Filter sidebar | 256px (`md:w-64`) shop; 288px (`lg:w-72`) STL marketplace | |
| Settings sub-nav | 3/12 columns, `sticky top-24` | |

### Image aspect ratios & fixed heights

| Context | Ratio / size |
|---|---|
| Product card image | `aspect-square` (1:1) |
| Home STL card image | `aspect-[16/10]` |
| Marketplace STL card image | fixed `h-64` (256px), width fluid |
| STL library card | `aspect-video` (16:9) |
| Account dashboard asset card | `h-40` (160px) |
| Category admin card | `h-48` (192px) |
| Product detail main | `aspect-square` mobile → `md:aspect-video` |
| STL detail main | `aspect-[4/3]` |
| Thumbnails | `aspect-square` (4 or 5 per row) |
| Team portraits | `aspect-[4/5]` |
| Home hero image | `aspect-square` |
| Home bento | large tile `h-[500px]` (2×2), small tiles `h-[240px]` |
| Shop hero | `h-[300px]` |
| STL marketplace hero | `h-[400px]` |
| About hero | `h-[819px]` |
| Case study banner | `h-80` (320px); order history promo `h-64`; discount banner preview `h-48` |
| Cart line image | `md:w-32 h-32` (128px) |
| Checkout summary thumb | 80px (`w-20 h-20`) |
| Table thumbs | 40px, 48px, 64px squares; avatars 28/32/40px |

---

## 5. Borders

| Token | Value |
|---|---|
| Default width | 1px (`border` 488/35) |
| Emphasis width | 2px (`border-2` 33/18 — outlined CTAs, selected payment card, selected thumbnail, dashed dropzones) |
| Active nav rail | 4px right border (`border-r-4 border-primary`, 21/20) |
| Active top-nav link | 2px bottom border (`border-b-2 border-primary pb-1`) |
| Tab underline | 2px bottom border, transparent when inactive |
| Default colour | `outline-variant #bfcaba` (471/33) |
| Soft colour | `outline-variant/30` (117/18), `/20`, `/10`, `/50` |
| Glass edge | `border-white/50`, `border-white/20`, `border-white/10` |
| Accent border | `border-primary` (53/27), `border-primary/20` |
| Dashed | `border-dashed` (8/6) dropzones, add-new tiles |
| Dividers | `divide-y divide-outline-variant` (tables), `/20`, `/30`; `border-t border-outline-variant/30` (card footers) |

---

## 6. Radius

**Config (what renders):** `DEFAULT` 0.25rem (**4px**), `lg` 0.5rem (**8px**), `xl` 0.75rem (**12px**), `full` 9999px. Others fall back to Tailwind defaults: `sm` 2px, `md` 6px, `2xl` 16px, `3xl` 24px. (`my_wishlist` and `user_profile` restate the same values in px; `user_login` adds `2xl: 1rem` = default.)

> ⚠ `DESIGN.md` documents a different scale (`DEFAULT 0.5rem, md 0.75rem, lg 1rem, xl 1.5rem`). **The HTML never uses that scale.** Use the config values above.

| Class | px | Usage | Used for |
|---|---|---|---|
| `rounded` | 4 | 144/26 | Badges/overlay tags (`NEW`, license), format chips, table thumbs, tiny pagination |
| `rounded-md` | 6 | 4/2 | Chart toggle buttons |
| `rounded-lg` | **8** | **556/35** | **Buttons, inputs, selects, sidebar items, icon tiles, thumbnails, small cards** |
| `rounded-xl` | **12** | 210/32 | **Cards** (product/STL/KPI/tables/forms), toolbars, payment cards, CTAs (some) |
| `rounded-2xl` | 16 | 80/13 | Large cards (bento tiles, testimonials, summaries, account dashboard cards, glass charts) |
| `rounded-3xl` | 24 | 3/2 | Promo banner, CTA panel, account summary band |
| `rounded-[2rem]` | 32 | 1 | About CTA panel |
| `rounded-full` | 9999 | 372/35 | Pills, chips/status badges, avatars, icon buttons, search pills, toggles, dots, FABs |
| `rounded-none` | 0 | 10/1 | Admin analytics KPI/chart cards (unique) |

---

## 7. Shadows / elevation

### Tailwind defaults in use

| Class | Value | Usage |
|---|---|---|
| `shadow-sm` | `0 1px 2px 0 rgb(0 0 0 / 0.05)` | **155/28 — default card shadow** |
| `shadow-md` | `0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)` | `hover:shadow-md` 30/10 — card hover |
| `shadow-lg` | `0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)` | 48/24 — primary CTAs, floating glass chips |
| `shadow-xl` | `0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)` | 10/9 — search bars, auth card; `hover:shadow-xl` STL cards |
| `shadow-2xl` | `0 25px 50px -12px rgb(0 0 0 / 0.25)` | 8/7 — hero image, FABs, toasts, dropdowns |
| `shadow-inner` | `inset 0 2px 4px 0 rgb(0 0 0 / 0.05)` | donut hole, avatar ring |
| Coloured: `shadow-primary/20` | shadow colour → `rgba(13,99,27,0.2)` | 10/10 — paired with `shadow-lg` on primary CTAs |

### Custom shadows in source

| Name | Value | Page |
|---|---|---|
| `.card-shadow` | `0 4px 20px -2px rgba(20,27,43,0.04)` | account dashboard |
| `.custom-shadow` | `0 4px 20px -2px rgba(0,0,0,0.05)` | manage categories |
| `shadow-[0_4px_20px_rgba(0,0,0,0.03)]` | | upload STL (7 cards) |
| `shadow-[0px_4px_24px_rgba(0,0,0,0.04)]` | | offer history KPI |
| `shadow-[0px_4px_32px_rgba(0,0,0,0.02)]` | | offer history table |
| `.bento-card` (cart) | `0 4px 30px rgba(0,0,0,0.05)`; hover `0 10px 40px rgba(0,0,0,0.08)` + `translateY(-2px)` | cart |
| `.bento-card:hover` (STL details) | `0 20px 40px -20px rgba(0,0,0,0.1)` | STL details |
| `.product-card-hover:hover` | `0 20px 40px rgba(0,0,0,0.08)` + `translateY(-8px)` | shop |
| `.card-hover:hover` | `0 20px 25px -5px rgba(0,0,0,0.05), 0 10px 10px -5px rgba(0,0,0,0.02)` + `translateY(-4px)` | wishlist |
| Registration card | `0 32px 64px -16px rgba(0,0,0,0.08)`; hover `0 40px 80px -20px rgba(13,99,27,0.1)` | registration |
| Button hover glow | `0 4px 12px rgba(46,125,50,0.2)` (also `rgba(13,99,27,0.2)`) | admin login, contact, forgot |
| Valid-email glow (JS) | `0 0 20px rgba(13,99,27,0.3)` | forgot password |
| Range thumb | `0 2px 4px rgba(0,0,0,0.2)` | shop |
| Promo image glow | `drop-shadow(0 20px 50px rgba(163,246,156,0.3))` | home |

**Recommended elevation scale:** `e0` border only (data-dense, per DESIGN.md "flat stacking") → `e1` `shadow-sm` (resting card) → `e2` `0 4px 20px -2px rgba(20,27,43,0.04)` (ambient card) → `e3` `shadow-md`/`shadow-xl` (hover) → `e4` `shadow-lg + shadow-primary/20` (primary CTA) → `e5` `shadow-2xl` (floating: FAB, toast, dropdown, hero media).

### Glass

`.glass-panel` dominant: `background: rgba(255,255,255,0.8); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);` (12 pages). Variants: with `border: 1px solid #bfcaba` (categories), `rgba(191,202,186,0.3)` (admin dashboard, manage products), `rgba(13,99,27,0.1)` (upload product), `rgba(229,231,235,1)` (discounts); opacity 0.9 + blur 12px (login), 0.9 + border (admin login), 0.85 (register). Nav glass: `bg-surface/80` or `bg-white/80` + `backdrop-blur-xl` (24px) or `backdrop-blur-md` (12px).

---

## 8. Motion

| Token | Value | Evidence |
|---|---|---|
| Default transition | Tailwind default: 150ms `cubic-bezier(0.4, 0, 0.2, 1)` when only `transition-*` is given | `transition-colors` 510/32, `transition-all` 427/35 |
| Fast | 150ms (`duration-150`) | sidebar active press |
| Standard | **200ms** (`duration-200`, 114/20) | nav links, icon buttons, sidebar hovers |
| Medium | **300ms** (`duration-300`, 77/15) | cards, toggles, overlays, FAQ icon |
| Slow | **500ms** (`duration-500`, 47/10) | image zoom on hover |
| Slower | 700ms (`duration-700`) | bento/hero image zoom, grayscale reveals |
| Reveal | 1000ms (`duration-1000`) | about page scroll fade-in (JS) |
| Spring | `cubic-bezier(0.34, 1.56, 0.64, 1)` 300ms | `.hover-lift` (home, unused in markup) |
| Easing for custom buttons | `cubic-bezier(0.4, 0, 0.2, 1)` 300ms | `.green-gradient-btn`, `.btn-primary-gradient`, `.bento-card` |

| Effect | Values |
|---|---|
| Press | `active:scale-95` (54/18) — buttons; `active:scale-[0.98]` (15/9) — large CTAs; `active:scale-[0.99]` — sidebar links; `active:scale-90` — icon add-to-cart |
| Image hover zoom | `group-hover:scale-105` (32/8) 500ms; `group-hover:scale-110` (30/11) 500–700ms |
| Card lift | `-translate-y-1` (4px) / `translate-y-[-4px]`; shop `-8px`; cart `-2px`; account JS `-2px` |
| Overlay reveal | `opacity-0 → group-hover:opacity-100` (38/12), `transition-opacity` |
| Slide-up reveal | `opacity-0 translate-y-2 → group-hover:opacity-100 group-hover:translate-y-0` (quick add buttons) |
| Icon nudge | `group-hover:translate-x-1` (arrow), `hover:gap-4` (link arrow), `group-hover:rotate-6` (feature tile) |
| FAQ chevron | `rotate(180deg)` when `<details open>`, 300ms |
| Toggles | knob `translate-x-full`, `after:transition-all` |
| Toast | `translate-y-24 → 0`, 300ms |
| Dropdown | `opacity-0 translate-y-4 pointer-events-none` → visible, 300ms |
| Ambient | `animate-pulse` (status dots), `animate-bounce` (hero status chip at 4s, upload status pill), `animate-spin` (loading), `animate-[spin_60s_linear_infinite]` + `animate-[spin_45s_linear_infinite_reverse]` (forgot password rings), `.glow-dot` `pulse-slow` 3s (opacity 0.4↔0.8) |

---

## 9. Iconography

- Library: **Material Symbols Outlined** (Google Fonts variable font, `wght,FILL@100..700,0..1`).
- Base settings: `font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24; vertical-align: middle;`.
- Filled state: inline `style="font-variation-settings: 'FILL' 1;"` — used for active sidebar icons, rating stars, verified/lock/check badges. Half star uses glyph `star_half` (or `FILL 0.5`, product details).
- Default size 24px. Size utilities: `text-sm` (14px), `text-[14px]`, `text-base` (16), `text-[16px]`, `text-lg` (18), `text-[18px]`, `text-xl` (20), `text-[20px]`, `text-[22px]` (admin console nav), `text-2xl` (24), `text-3xl` (30), `text-4xl` (36), `text-[48px]`, `text-6xl` (60), `text-[120px]` & `text-[240px]` (decorative watermarks at 3–10% opacity).
- 165 distinct glyphs; top: `star` 179, `delete` 39, `visibility` 34, `search` 28, `shopping_cart` 26, `edit` 26, `favorite` 24, `check_circle` 23, `settings` 22, `deployed_code` 21, `chevron_right` 20, `account_circle` 19, `download` 19, `precision_manufacturing` 17 (brand motif), `notifications` 17. Full list in ASSET-INVENTORY.md.

---

## 10. Z-index

| Value | Usage |
|---|---|
| `z-0` / `z-10` / `z-20` / `z-30` | in-card layering, overlays, sticky filters |
| `z-40` | sticky headers within main, sidebars on some pages |
| `z-50` | fixed top nav, sidebars, FAB, bottom nav, overlays, dropdowns |
| `z-[60]` | WhatsApp FAB (shop), admin analytics sidebar |

## 11. Scrollbar

`.custom-scrollbar::-webkit-scrollbar { width: 4px | 6px }` · track `transparent` · thumb `#bfcaba` (`outline-variant`), `border-radius: 10px` (upload product uses `#dce2f7`). Global variants: 8px width, track `#f9f9ff` or `#f1f1f1`, thumb hover `#707a6c`.
