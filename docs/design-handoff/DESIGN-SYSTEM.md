# Bekaa3D: Design System ("Precision Engineering System")

This document gives the reusable visual rules behind the 35 Stitch screens. Each rule cites real values and the source file it comes from. Token values are defined in [DESIGN-TOKENS.md](./DESIGN-TOKENS.md); this file explains **how** to apply them.

Stitch's own brief (`precision_engineering_system/DESIGN.md`) describes the intent as "functional luxury": a Modern Minimalism + Corporate Technology look with Laboratory-White surfaces, a green signature colour, Hanken Grotesk / Inter / JetBrains Mono, glass navigation, and ambient shadows. The HTML implements that brief through a Material 3 colour scheme. Where the brief and the HTML disagree, the HTML wins (see §12).

---

## 1. Visual language

The concrete traits that define the look:

1. **A cool off-white canvas.** The page background is `#f9f9ff` (`background`), with a faint blue cast, not pure white. Pure white (`#ffffff`, `surface-container-lowest`) is kept for cards, so cards read as raised paper on the canvas.
2. **Lavender-tinted neutrals.** Every neutral container is a lavender-grey step: `#f1f3ff` → `#e9edff` → `#e1e8fd` → `#dce2f7`. No warm greys or Tailwind `gray-*` surfaces are used.
3. **One saturated colour.** Deep forest green `#0d631b` carries every primary action, link, active state, and price. Lime `#b9f474` and raspberry `#923357` appear only as small accents (chips, badges, chart segments).
4. **A three-font system.** Hanken Grotesk headlines run tight, heavy, and slightly negatively tracked. Body text is Inter. Everything technical (labels, buttons, table headers, SKUs, IDs, chips) is uppercase JetBrains Mono at 10–12px with +0.05em tracking. This mono "data label" voice is the most recognisable trait of the system.
5. **Thin green-grey borders.** Cards and inputs use a 1px `#bfcaba` (`outline-variant`) border, often at 30% opacity, rather than heavy shadows. Shadows are `shadow-sm` at rest, growing on hover.
6. **A blueprint-grid texture.** Many backgrounds (auth, admin, account) carry a 40px grid of 1px lines in `rgba(13,99,27,0.05)`, or a dot grid in `#bfcaba`. It reads as engineering paper.
7. **Glass navigation.** Top bars are 80%-opaque white/surface with 20–24px backdrop blur and a 1px bottom border at 30% `outline-variant`.
8. **Product-photography imagery.** Images are cinematic studio shots of 3D-printed parts, printers, and labs, cropped `object-cover` in rounded containers, and they zoom 5–10% on hover.

---

## 2. Page background system

| Context | Background | Example |
|---|---|---|
| Storefront pages | `bg-background` `#f9f9ff`, plain | shop, cart, checkout, product/STL details, contact |
| Storefront alternating sections | `surface-container-lowest` `#fff` → `white` → `surface-container-low` `#f1f3ff` → `white` → `surface-container-lowest` | home (sections alternate to create rhythm without dividers) |
| Full-bleed tinted band | `surface-container-low` + `border-y border-outline-variant/30` | STL marketplace "Precision-First Philosophy" |
| Brand band | `primary-container` `#2e7d32` with `on-primary-container` `#cbffc2` text | about stats band |
| Auth pages | `#f9f9ff` + pattern (login: SVG dot pattern; register: radial dot grid 24px; forgot: `#e5e7eb` line grid 40px; admin login: green line grid 40px + two blurred `primary/5` orbs) | |
| Account/admin canvas | `#f9f9ff` + blueprint grid (green lines at 5% opacity, 40px) or dot grid (`#bfcaba`, 24–40px) | admin dashboard `.grid-bg`, manage orders, settings |
| Decorative orbs | `bg-primary/5` and `bg-secondary/5`, `rounded-full`, `blur-[100–120px]`, 40–60% of the viewport, positioned at -10% offsets | home hero, admin login |

**Rule:** use one page background (`#f9f9ff`). Create depth with white cards and lavender containers, never with grey. Apply the blueprint grid to app shells (auth, account, admin), not to storefront content pages.

---

## 3. Content hierarchy

Storefront pages follow this order: **fixed glass nav → hero (H1 48px) → sections each introduced by a 32px H2 plus a muted 16px subtitle → card grids → dark promo or green CTA band → footer.**

App pages (account and admin) follow: **256px sidebar | sticky 64px topbar → page header (32px H1 + 16px muted description + right-aligned actions) → KPI card row → filter bar → data table or card list → pagination.**

Visual weight ladder, heaviest to lightest:
1. Primary green CTA (solid or gradient, white mono uppercase label, `shadow-lg shadow-primary/20`)
2. Display/H1 text in `on-surface #141b2b`, weight 800
3. Prices in `primary`, Hanken 20–48px
4. Card titles, Hanken 20px/600
5. Body in `on-surface-variant #40493d`
6. Mono labels in `on-surface-variant` or `outline #707a6c`
7. Captions at 10–12px `outline` / `on-surface-variant/60`

---

## 4. Typography hierarchy

| Level | Spec | Real examples |
|---|---|---|
| H1 hero | `font-display text-display`: Hanken 48/52.8, 800, -0.02em | "Engineered Grade 3D Solutions" (home, with "3D Solutions" in the green→olive text gradient), "Find Your Precision Part" (shop, white on image), "Your Cart", "Digital STL Marketplace", "Contact Our Engineering Team" |
| H1 app page | `font-headline-lg text-headline-lg`: Hanken 32/38.4, 700, -0.01em | "Order History", "Manage Customers", "Operational Overview" |
| H2 section | 32px Hanken 700 (`font-display text-headline-lg`), centered, `mb-4`, followed by `text-on-surface-variant max-w-2xl mx-auto` | "Curated Specialized Collections", "Precision as Standard" (home) |
| H3 card | `font-headline-md text-headline-md`: Hanken 20/26, 600 | "Recent Physical Orders", "General Information" |
| Eyebrow | `font-label-caps text-primary tracking-widest`: 12px mono, green, 0.1em | "PRECISION MANUFACTURING" (home), "ESTABLISHED 2014" (about, `text-primary-fixed-dim tracking-[0.2em]`) |
| Pill eyebrow | `font-label-caps text-primary bg-primary-container/20 px-4 py-1 rounded-full` | "ENGINEERING ARCHIVE" (STL marketplace) |
| Field label | `font-label-caps text-label-caps text-on-surface-variant uppercase`, mb 8px | "FULL NAME", "EMAIL ADDRESS" |
| Table header | `font-label-caps` 11–12px, `on-surface-variant` or `outline`, uppercase, often `tracking-widest`, on `surface-container-low` | all tables |
| Body | Inter 16/24 `on-surface-variant` | |
| Lead | Inter 18/28.8 `on-surface-variant` | hero subcopy, page descriptions |
| Quote | Inter 16–18px *italic* `on-surface` | testimonials, reviews |

**Rules**
- Headlines are always `on-surface` (`#141b2b`). They become white on image or dark backgrounds. A headline is `primary` only for small brand-coloured titles: category admin cards, "Custom Quote", "Request Received".
- Mono labels are UPPERCASE. When a mono label renders in mixed case in the source, the omission is a Stitch slip (e.g. "Categories" in the STL marketplace filters). Recommend uppercase.
- Numbers (KPIs, prices, stats) use Hanken (`font-display`), not Inter.
- Technical IDs (order IDs, SKUs, versions, file sizes) use mono.

---

## 5. Spacing rhythm

- **Base unit: 4px.** All spacing is on Tailwind's 4px scale.
- **Storefront vertical rhythm:** sections `py-24` (96px). Section header to grid is `mb-16` (64px) for centered headers and `mb-12` (48px) for split headers (title left, link right). Hero top padding is `pt-32` (128px) under the fixed nav.
- **Product-detail rhythm:** major sections are separated by `mt-32` (128px). Hero grid bottom margin is `mb-20` (80px).
- **App rhythm:** content area padding is `p-8` (32px) or `px-12 py-8`. Blocks stack with `mb-8`/`space-y-8` (32px). KPI rows use `gap-6` (24px).
- **Card internals:** `p-6` (24px) by default and `p-8` (32px) for form or summary cards. Title→body `mb-2`; body→actions `mb-6`/`mt-auto`.
- **Gutters:** desktop 64px (`px-margin-desktop`) on storefront, mobile 16px (`px-margin-mobile`). The grid gutter is 24px (`gap-gutter`).
- **Inline:** icon + label gap is 8px (buttons, links) or 12px (sidebar items, list rows). Groups of buttons use a 12–16px gap.

---

## 6. Surface / card system

| Surface | Spec | Use |
|---|---|---|
| **Card (standard)** | `bg-white`/`surface-container-lowest`, `border border-outline-variant` (or `/30`), `rounded-xl` (12px), `shadow-sm`, `p-6` | product, STL, KPI, table wrappers, form sections |
| **Card (large/soft)** | same with `rounded-2xl` (16px), `p-8` | account dashboard cards, testimonials, feature cards, summary panels |
| **Muted panel** | `surface-container-low` `#f1f3ff`, `rounded-2xl`, `border-outline-variant/20`, no shadow | cart order summary, account info band, info callouts |
| **Tinted tile** | `surface-container` / `-high`, `rounded-xl`, `p-3…p-8` | spec tiles (STL details), feature cards (product details `surface-container-high`) |
| **Glass card** | `.glass-panel` (white 80% + blur 20px), `rounded-xl`/`2xl`, `border-white/50` | testimonials (home), floating hero chips, admin dashboard KPI/chart cards, filters |
| **Dark card** | `inverse-surface` `#293040` (or `#141b2b`) + white/`surface-variant` text | "Our Vision", DfAM card (about), home promo banner (`rounded-3xl`) |
| **Brand card** | `bg-primary` + `on-primary`, `shadow-xl shadow-primary/20`, watermark icon at 10% opacity | "ACCOUNT TIER" (account dashboard), "Print Capacity" (analytics), home CTA (`rounded-3xl p-16`) |
| **Accent-outline card** | `border-2 border-primary bg-primary-fixed/5` | selected payment method (checkout) |
| **Dashed add tile** | `border-2 border-dashed border-outline-variant`, `surface-container-low`, hover `border-primary` | add category, add image, add address, dropzones |

**Nesting rule (from DESIGN.md, confirmed in code):** inner elements get a smaller radius than their container. A 12–16px card holds 8px inputs/buttons and 4px badges.

---

## 7. Border system

- **Default:** 1px `outline-variant` `#bfcaba`. Use full opacity in admin/data UIs and 30% (`/30`) in softer storefront cards.
- **Dividers:** `divide-y divide-outline-variant` (admin tables) or `divide-outline-variant/20` (account tables). Card footers use `border-t border-outline-variant/30 pt-4`.
- **Active indicators:** a 2px bottom border in `primary` (top nav, tabs) and a **4px right border** in `primary` on active sidebar items.
- **Emphasis:** a 2px border for outlined CTAs (`border-2 border-primary`), the selected thumbnail, and the selected payment card.
- **Focus:** border switches to `primary`, plus a 2px ring `primary/20` (see §11).
- Per DESIGN.md "Flat Stacking": in dense views, prefer a 1px border over a shadow.

---

## 8. Elevation

| Level | Value | Use |
|---|---|---|
| 0 | border only | tables, admin cards, inputs |
| 1 | `shadow-sm` | resting cards (155 uses) |
| 2 | `0 4px 20px -2px rgba(20,27,43,0.04)` ambient | account dashboard cards, category cards |
| 3 | `shadow-md` → `shadow-xl` on hover | product/STL card hover |
| 4 | `shadow-lg shadow-primary/20` | primary CTAs (green-tinted glow) |
| 5 | `shadow-2xl` | hero media, FABs, toasts, dropdowns, auth card hover |

Glassmorphism is the second depth mechanism. It is used on nav bars, floating hero chips, the 3D-viewport control bar, and admin dashboard panels.

---

## 9. Colour hierarchy

1. **Action/brand:** `primary #0d631b`. Hover moves to the lighter `primary-container #2e7d32`. This counter-intuitive lightening on hover is the dominant pattern (25 uses on 13 pages).
2. **Supportive green:** `secondary #3e6a00` for category badges, "shipped/in stock" text, and footer link hover.
3. **Highlight:** lime `secondary-container #b9f474` for success/positive chips and the promo CTA.
4. **Counter-accent:** raspberry `tertiary #923357` for discounts, "low stock", and the third data series.
5. **Danger:** `error #ba1a1a`.
6. **Text:** `on-surface #141b2b` for headings and `on-surface-variant #40493d` for body. `outline #707a6c` is for tertiary text.
7. **Structure:** `outline-variant #bfcaba` for borders and the lavender containers for fills.

Status colour mapping, recommended and drawn from the most frequent source usage:

| Status | Background | Text | Source example |
|---|---|---|---|
| Success / Delivered / Approved / In stock / Active | `secondary-container` `#b9f474` (or `primary/10`) | `on-secondary-container` `#437000` (or `primary`) | order history, admin reviews, product details |
| In production / Processing (positive) | `primary/10` | `primary` | account dashboard, manage orders |
| Shipped / In transit | `secondary-container/30` | `on-secondary-container` | manage orders |
| Pending / Awaiting | `tertiary-fixed` `#ffd9e2` | `on-tertiary-fixed-variant` `#7f2448` | order history, manage STL "Open Offers" |
| Warning (offers pending) | `amber-100` + `border-amber-200` | `amber-800` + `amber-600` dot | manage offers |
| Info (countered) | `blue-100` + `border-blue-200` | `blue-800` + `blue-600` dot | manage offers |
| Error / Cancelled / Suspended / Out of stock | `error-container` `#ffdad6` | `on-error-container` `#93000a` / `error` | order history, customers |
| Neutral / Hidden / Delivered (archived) | `surface-container-highest` / `surface-variant` | `on-surface-variant` | admin reviews, manage orders |

---

## 10. CTA hierarchy

| Rank | Style | Spec | Examples |
|---|---|---|---|
| **1. Primary** | Solid green | `bg-primary text-on-primary font-label-caps px-8 py-4 rounded-lg shadow-lg hover:bg-primary-container active:scale-95` | "SHOP PRODUCTS →" (home), "COMPLETE PURCHASE" (checkout, `rounded-xl py-5 tracking-widest`) |
| 1-alt | Gradient green | `--gradient-primary` 135° `#2e7d32→#1b6d24`, white mono label, `py-4 rounded-lg shadow-lg shadow-primary/20`, hover `brightness(1.1) translateY(-1px)` | "LOGIN TO DASHBOARD", "SEND MESSAGE", "ADD TO CART" (shop) |
| **2. Secondary** | Outline green | `border-2 border-primary text-primary px-8 py-4 rounded-lg hover:bg-primary/5` (or `border` 1px) | "EXPLORE STL FILES", "OFFER", "DOWNLOAD DATASHEET (PDF)", "SAVE AS DRAFT" |
| 3. Tertiary | Neutral outline / tonal | `border border-outline-variant` or `bg-surface-container-highest text-on-surface-variant`, hover `bg-surface-container(-high)` | "MAKE AN OFFER", "WRITE A REVIEW" (pill), filter chips, "DUPLICATE" |
| 4. Text link | `text-primary font-bold hover:underline underline-offset-8` (or `font-label-caps`) | "VIEW ALL PRODUCTS", "View All Orders", "READ ALL 42 REVIEWS" |
| Inverse | Dark | `bg-on-surface text-surface` (`#141b2b`), hover `opacity-90` / `bg-on-surface-variant` | "Apply" coupon, "DOWNLOAD FREE", "Add All to Cart", "Apply Filters" (reviews) |
| Accent | Lime | `bg-secondary-fixed text-on-secondary-fixed px-10 py-5 rounded-xl` | "REDEEM DISCOUNT" (dark promo) |
| On-brand | White on green | `bg-on-primary text-primary rounded-xl` or `bg-white text-primary rounded-full` | "REQUEST A QUOTE" (home CTA), "REQUEST B2B QUOTE" (about) |
| WhatsApp | `bg-[#25D366] text-white` or outline `border-2 border-[#25D366]/30 text-[#25D366]` | "WHATSAPP US", "WHATSAPP" |
| Danger | `border-2 border-error text-error hover:bg-error hover:text-white` / `text-error` ghost | "DELETE PRODUCT", "Remove", "Withdraw" |

**Rule:** a view has at most one rank-1 button. In multi-button bars, the primary sits rightmost (admin page headers: DELETE · DUPLICATE · PREVIEW · **UPDATE PRODUCT**).

---

## 11. Imagery, icons, interaction states, motion, theme

### Imagery
- Photography is AI-generated 3D-printing product/lab imagery (see `data-alt` prompts). Lighting is studio/clinical, accents are green, and backgrounds are clean.
- Images always use `object-cover` (or `bg-cover bg-center`) inside `overflow-hidden` rounded wrappers (`rounded-xl`/`2xl`).
- Placeholder fill while loading: `bg-surface-container-low` or `bg-surface-container`.
- Scrims: `bg-black/40` hover overlay (product quick view), `bg-black/30` → `bg-black/10` on hover (category tiles), and bottom gradients `from-black/80` for text over images.
- Hover: zoom `scale-105` (500ms) or `scale-110` (500–700ms). STL dark cards: image `opacity-80 → 100`.
- Treatments: `grayscale hover:grayscale-0` (payment logos, map, forgot-password side image), `brightness-50` (shop hero, "+4" thumbnail), `blur-sm` ("+8" thumbnail), `opacity-[0.03]` watermark schematics (login).
- Avatars: circular, 28–40px (tables/headers), 48px (testimonials), 128px with a 4px `surface-container-high` border (profile). Initials fallback: `bg-primary/20 text-primary font-bold` (or `bg-surface-container-high`).

### Icons
- Material Symbols Outlined, weight 400, unfilled by default, 24px.
- Filled (`FILL 1`) marks active/selected state: the active sidebar icon, rating stars, verified badges, lock icons, success checks.
- Icon tiles: a 40–48px square, `rounded-lg`/`rounded-xl`, `bg-primary/10 text-primary` (or `bg-secondary-container/20 text-secondary`, `bg-tertiary-container/10 text-tertiary`). On hover in feature tiles it becomes `bg-primary text-white rotate-6`.
- Inline icons in buttons are 14–20px (`text-sm`, `text-[18px]`), sitting before or after the label with an 8px gap.
- `precision_manufacturing` (robotic arm) acts as the brand motif glyph (registration logo, watermarks, custom quote, account tier).

### Hover
- Text links/nav: `on-surface-variant → primary` (`transition-colors duration-200`).
- Neutral buttons/rows: background → `surface-container-high` (most common), `surface-container-low`, or `primary/5` (admin table rows).
- Primary button: `primary → primary-container`, or `brightness-110` for gradients.
- Cards: shadow `sm → md/xl`, optional lift (-4px to -8px), border `→ primary` (KPI/category cards).
- Row actions: hidden actions fade in (`opacity-0 group-hover:opacity-100`) in admin product and customer tables.

### Focus
- Inputs: `focus:border-primary focus:ring-2 focus:ring-primary/20 outline-none`. This is the dominant pattern, matching DESIGN.md's "2px green border + soft glow". Custom CSS equivalents: `box-shadow: 0 0 0 2px rgba(13,99,27,0.1)` or `rgba(46,125,50,0.1–0.2)`.
- Leading icons recolour on focus: `group-focus-within:text-primary`.
- **Buttons and links have no explicit focus style in the source.** Implementers must add a visible `focus-visible` ring (recommended `ring-2 ring-primary ring-offset-2`).

### Active / pressed
- `active:scale-95` (buttons), `active:scale-[0.98]` (wide CTAs), `active:scale-[0.99]` (sidebar links). The source also has JS `mousedown` scale effects; replicate them with CSS `:active` only.

### Disabled
- `disabled:opacity-50` / `disabled:opacity-30` + `disabled:cursor-not-allowed` (pagination prev). Locked states use `opacity-50 cursor-not-allowed` ("Locked" button, "WAITING ON CUST."), and expired rows use `opacity-60`/`opacity-75 grayscale`.

### Motion
- 200ms colour transitions, 300ms layout/shadow/transform, 500–700ms image zoom. Easing is the Tailwind default `cubic-bezier(0.4,0,0.2,1)`.
- Ambient: pulsing status dots, a bouncing hero chip (4s), slowly rotating rings (60s/45s) on forgot password.
- Respect `prefers-reduced-motion` (not handled in the source; add it).

### Dark / light
- Only a **light theme** is designed. `<html class="light">` and `darkMode: "class"` are declared, and some navs/footers carry `dark:` utilities (`dark:bg-inverse-surface/80`, `dark:text-primary-fixed-dim`, …), but no complete dark palette or screens exist. System settings shows a LIGHT/DARK segmented control as UI only. **Do not ship a dark theme from this export.**

---

## 12. STITCH INCONSISTENCIES

Below are inconsistencies **inside the Stitch export itself**. Each has a **Recommendation**, marked as such. The source is not silently rewritten; the implementer should apply the recommendation deliberately.

### 12.1 Broken / undefined token classes (render as nothing)

| Class | Pages | Effect seen in screenshot | Recommendation |
|---|---|---|---|
| `max-w-container-max` | home (11×) | No max width; content spans the full viewport inside 64px gutters. | **Recommendation:** use `max-width: 1440px` + `margin-inline: auto`. |
| `max-w-spacing-max-width` + `px-spacing-margin-desktop` | about (10×), contact (5×), STL details (4×) | No max width **and 0 horizontal padding**. Nav logo, footer, and about content sit flush against the viewport's left edge (visible in about and STL-details screenshots). | **Recommendation:** treat as `max-w 1440px` + `px 64px` (desktop) / `16px` (mobile). |
| `p-spacing-margin-mobile md:p-spacing-margin-desktop` | user login | No body padding. | **Recommendation:** 16px / 64px. |
| `py-unit-margin-desktop` | manage orders, manage reviews, system settings sidebars | Sidebar has no vertical padding (logo touches the top). | **Recommendation:** `py-8` (32px), matching the other admin sidebars. |
| `px-unit-gutter` | order history sidebar | No horizontal padding (items run edge to edge). | **Recommendation:** `px-6` (24px). |
| `max-width` (bare class) | system settings content | No-op. | **Recommendation:** `max-w-[1440px]`. |
| `text-label-md`, `font-label-md` | home footer | No-op (inherits 16px Inter). | **Recommendation:** Inter 14px (`text-sm`). |

### 12.2 Missing `fontSize` config
`manage_categories_bekaa3d_admin`, `product_details_bekaa3d_precision_kit`, and `user_registration_bekaa3d_precision_engineering` omit the `fontSize` block, so `text-display`, `text-headline-*`, `text-body-*`, and `text-label-caps` do nothing. In the product-details screenshot, the H1 "NX7 Ultra-Poly Carbon" and the price "$189.00" render at about 16px. In registration, "Create Professional Account" renders at 16px.
**Recommendation:** apply the token sizes (H1 48px, price 48px, H2 32px, card titles 20px, labels 12px mono). The 16px rendering is a defect, not a design choice.

### 12.3 `font-*` family class used without the matching size class
This is very common (e.g. `font-headline-lg` with no `text-headline-lg`: "Order Summary" in cart, "Frequently Bought Together", "Precision-First Philosophy", the "Material Engineering" H2 on product details). `font-headline-md` alone appears on STL marketplace card titles, the Filters heading, FAQ questions, and account card titles. Such elements render in Hanken Grotesk at the **inherited 16px, weight 400**.
**Recommendation:**
- For **section headings** (h2/h3 introducing a section), apply the intended token size (`headline-lg` 32px / `headline-md` 20px).
- For **card/list item titles** inside dense cards (STL marketplace cards, FAQ summaries, profile card titles), use a **16px Hanken Grotesk, weight 600** "title-sm" style. It keeps the compact rendered size but adds the weight the designer clearly expected.
- `font-label-caps` alone: render 12px mono uppercase (the label token). Exception: nav/footers where it sits next to `text-body-md`.

### 12.4 Container width and gutters

| Variant | Pages |
|---|---|
| `max-w-[1440px]` | account dashboard, cart, checkout, forgot, analytics, admin dashboard, offer history, downloads, profile |
| `max-w-max-width` (=1440px) | shop, marketplace, product details, wishlist, my reviews, order history, admin products/customers/offers/upload |
| `max-w-[1200px]` | edit product, upload STL |
| none / broken | home, about, contact, STL details, settings, categories, discounts, manage STL, manage orders/reviews |

**Recommendation:** use one `Container` (max-width 1440px, padding 16px mobile / 64px desktop) for storefront and app content, plus a `narrow` variant (1200px) for long admin forms.

### 12.5 Header height and construction

| Height | Pages |
|---|---|
| 64px `h-16` | cart, checkout, about, contact, STL details, admin topbars |
| 80px `h-20` | STL marketplace (nav links use `py-7` so the 2px underline sits on the bottom edge) |
| padding-based `py-4` (≈72px) | home (shrinks to `py-2 shadow-lg` after 50px scroll via JS), shop, product details, order history |
| `py-6` (≈88px) | admin categories header |

**Recommendation:** use a 64px storefront nav (`h-16`) and a 64px admin topbar. Keep the home scroll-shrink only if it is wanted, and implement it as a class toggle.

### 12.6 Logo / wordmark treatments (7 variants)
1. Gradient text `from-primary to-secondary-fixed`, Hanken 32px bold (home).
2. `text-primary` Hanken 20px bold/extrabold (shop, product, cart, checkout, most sidebars).
3. `text-primary` Hanken 32px extrabold tracking-tight (STL marketplace, forgot password).
4. `text-on-surface` Hanken 20px **black**, tracking-tighter (about, contact, STL details).
5. "Bekaa" `on-surface` + "3D" `primary`, black, tracking-tighter (user login).
6. Icon + wordmark: `precision_manufacturing` icon 36px + text (register); a 40px `bg-primary rounded` tile holding `deployed_code` (admin login); a 40px `primary-container rounded-lg` tile with filled `deployed_code` (admin dashboard); a filled `deployed_code` 30px glyph (manage products).
7. "Bekaa3D Admin" text (analytics, customers, discounts, offers topbar).

**Recommendation:** use variant 2 (Hanken Grotesk 20px, weight 800, `primary`) as the standard wordmark. Use variant 6 (40px `primary-container` rounded-lg tile with filled `deployed_code` + wordmark + "ENGINEERING PRECISION" 10px mono caption) for app sidebars. Reserve the gradient wordmark for the home hero if desired.

### 12.7 Top navigation link sets differ

| Links | Pages |
|---|---|
| Home · Shop · STL Store · About | home, shop, product details |
| Marketplace · Services · Materials · Community | STL marketplace |
| Marketplace · Services · Materials · Showcase · Support | cart |
| Printers · Materials · Software · Support · Industry | about, contact, STL details |
| (none, "Secure Checkout") | checkout |

Link typography also varies: Inter 16px (`font-body-md`) on home/shop/product/marketplace/cart, versus JetBrains Mono 12px (`font-label-caps text-label-caps`) on about/contact/STL details.
**Recommendation:** links come from the real app's routes, not from Stitch. Style them as Inter 16px `on-surface-variant`, `gap-8`; active links get `text-primary font-bold border-b-2 border-primary pb-1`.

### 12.8 Footer variants (at least 7)
Backgrounds: `surface-container-low` (home, marketplace), `surface-container-lowest` (shop, product, cart, checkout, account dashboard), `surface-container-highest` (about, contact, STL details). Column headings: `font-bold` Inter (home, product), mono caps `on-surface` (shop), mono caps `primary` (about, contact, checkout), mono 10px `tracking-widest` (cart). The newsletter is present on 4 pages, social icons on 5, payment logos on 1.
**Recommendation:** one footer. `surface-container-low` bg, `border-t border-outline-variant`, `pt-24 pb-12` (or `py-16`), 4 columns (brand + description + social circles | 2 link columns | newsletter). Headings in mono caps `on-surface`, links Inter 16px `on-surface-variant` hover `primary`. Bottom bar: `border-t border-outline-variant/30 pt-8` with copyright left and payment icons right.

### 12.9 Primary button styling
- Fill: solid `bg-primary` (dominant), five different gradients (see DESIGN-TOKENS §1.6), or `bg-primary-container` (wishlist, admin login, manage STL, categories).
- Radius: `rounded-lg` 8px (dominant), `rounded-xl` 12px (home CTA, cart, checkout, customers), `rounded-full` (shop hero search, account "NEW PROJECT", about CTA).
- Label: mono caps (dominant), Inter bold (marketplace nav Login, manage products "Add Product"), Hanken 20px (cart "Proceed to Checkout").
- Hover: `bg-primary-container` (dominant), `brightness-110`, `opacity-90`, `hover:bg-secondary` (registration), `hover:scale-105` (settings save).

**Recommendation:** primary = solid `#0d631b`, `rounded-lg`, mono 12px caps label, `shadow-lg shadow-primary/20`, hover `#2e7d32`, active `scale-95`. Offer an optional `gradient` variant using `--gradient-primary`.

### 12.10 Card radius
Product/STL cards use `rounded-xl` (12px) on shop, marketplace, wishlist, and downloads, but `rounded-2xl` (16px) on home STL cards, account dashboard, product-detail reviews, and related items. Profile cards use `rounded-lg` (8px). Analytics uses `rounded-none`. DESIGN.md says 16px for cards.
**Recommendation:** 12px (`rounded-xl`) for standard cards, which is the most frequent at 210 uses. Use 16px for large feature/summary panels and 24px for full-width promo/CTA banners. Do not use the square analytics cards.

### 12.11 Product card has 4 different designs
Home (borderless, image card + text below, quick-view overlay, icon add-to-cart), Shop (bordered white card, full-width gradient "ADD TO CART"), Wishlist (bordered card, glass delete/view buttons, `primary-container` CTA), Related (image + name + price only). These are **context variants**, documented in COMPONENT-SPECS.md.
**Recommendation:** build one `ProductCard` with `variant="showcase" | "catalog" | "wishlist" | "compact"`.

### 12.12 Rating star colour
`amber-400` (home, wishlist), `amber-500` (STL marketplace, STL details, analytics), `secondary` (shop), `primary` (product details, home testimonials, my reviews, admin reviews entries), `secondary-fixed-dim` (admin reviews average).
**Recommendation:** amber `#f59e0b` for product ratings (shopping context), `primary` for testimonial/review-card star rows. Empty stars use `outline-variant`.

### 12.13 Status chip palettes for the same status

| Status | Variants found |
|---|---|
| Shipped | `secondary-container/10 + text-secondary` (account dash) · `surface-container-high + on-primary-fixed-variant` (order history, renders bluish) · `secondary-fixed + on-secondary-fixed` (admin dash) · `secondary-container/30 + on-secondary-container` (manage orders) |
| Pending | `tertiary-fixed + on-tertiary-fixed-variant` (order history) · `amber-100/800` (offers) · `surface-variant + on-surface-variant` (manage orders) · **`error-container`** (admin reviews) |
| Delivered | `secondary-container` (order history) · `primary-fixed-dim` (admin dash) · `outline-variant` (manage orders) · `surface-variant/30` (account dash) |

Chip shape also varies: `px-3 py-1 rounded-full text-[10px]/[11px] font-bold` (dominant) vs `px-2.5 py-0.5 text-xs font-medium` (order history), and mono vs Inter text.
**Recommendation:** a single `StatusBadge` mapping (DESIGN-SYSTEM §9 table): `px-3 py-1 rounded-full`, mono 10–11px bold uppercase, optional 6px leading dot.

### 12.14 Sidebar navigation

- **Wrong items on admin pages:** `manage_physical_products`, `manage_stl_files`, `manage_categories`, and `upload_stl_file` use the **customer** menu (Profile, Orders, STL Downloads, Wishlist, Reviews, Offers, Account Settings). Manage products even shows two active items (Orders + Physical Products), and categories highlights "STL Downloads".
- Admin menus differ between pages: the full menu of 10 items on admin dashboard; 5 items + "New Print Job" on orders/reviews/offers/settings; "Dashboard · Orders · Inventory · Customers/Marketing · Analytics · Settings" on analytics/customers/discounts; grouped sections ("INVENTORY", "SALES & CRM") on admin console.
- Active style: `border-r-4 border-primary bg-surface-container-low text-primary font-bold` (dominant, ~20 pages) vs gradient pill `.sidebar-active` (account dashboard) vs `bg-primary-container text-on-primary-container` pill (admin console) vs `bg-surface-variant/30` (analytics) vs `bg-surface-container` (customers).
- Background: `surface` (dominant) vs `surface-container-lowest` vs `surface-container-low` (admin console).
- Item radius: `rounded-lg` vs none (manage orders/reviews/offers, profile) vs `rounded-xl` (account dashboard).

**Recommendation:** one `AppSidebar` (256px, `bg-surface`, `border-r border-outline-variant`, `py-8 px-6`). Items: `flex gap-3 px-4 py-3 rounded-lg text-on-surface-variant hover:bg-surface-container-high`. Active: `text-primary font-bold bg-surface-container-low border-r-4 border-primary` with a filled icon. Take menu contents from the real app's admin/account routes.

### 12.15 Admin top bar positioning
Sticky in-flow (`sticky top-0`, most) vs fixed (`fixed top-0 left-64 right-0`, orders/reviews/offers/settings). On manage customers, `w-full ml-64` makes the header **overflow the viewport by 256px** (the right-hand icons are clipped in the screenshot). Order history's header is full width over the sidebar.
**Recommendation:** a sticky 64px topbar inside the main column, `bg-surface/80 backdrop-blur-xl border-b border-outline-variant px-8`.

### 12.16 Pagination (3 styles)
Circles `w-10 h-10 rounded-full`, active `bg-primary text-white` (shop) · bordered squares `w-10 h-10 rounded-lg border-outline-variant` (marketplace, reviews, manage STL, order history) · small `w-8 h-8 rounded` (offer history, admin products/customers/orders).
**Recommendation:** use bordered `rounded-lg` 40px storefront/account and 32px admin, with active `bg-primary text-on-primary font-bold`.

### 12.17 Toggle switches
`w-11 h-6` peer switch with 20px knob (dominant), `w-10 h-5` with 16px knob (manage products), and a `<button>`-based `w-12 h-6 p-1` (discounts). Off-track colours: `surface-container-highest`, `outline-variant`, `surface-variant`.
**Recommendation:** 44×24 track, off `outline-variant`, on `primary`, white 20px knob with a `gray-300` border; use an accessible `role="switch"`.

### 12.18 Inputs
Backgrounds: `white`, `surface-container-low`, `surface-container-lowest`, `surface-bright`, `surface`, `surface-container`. Padding: `px-4 py-3` (dominant), `p-4` (checkout), `h-12 px-4` (register), `p-3` (admin forms), underline-only `border-b py-2/3` (edit product). Focus: ring `primary/20` (dominant), ring `primary` 100%, `ring-1`, `ring-0` + border.
**Recommendation:** 48px tall (`px-4 py-3`), `bg-surface-container-lowest`, `border border-outline-variant rounded-lg`, Inter 16px, placeholder `outline`; on focus `border-primary ring-2 ring-primary/20`. Use the underline variant only for inline edit forms.

### 12.19 Glass panel definition (8 variants)
Opacity 0.8/0.85/0.9, blur 12/20px, and various borders. **Recommendation:** `rgba(255,255,255,0.8)` + `blur(20px)`. Add the border `1px solid rgba(191,202,186,0.3)` when the panel sits on a same-colour background.

### 12.20 Blueprint background (11 variants)
See DESIGN-TOKENS §1.7. **Recommendation:** green line grid `rgba(13,99,27,0.05)`, 40px, on `#f9f9ff`, for auth/account/admin shells.

### 12.21 DESIGN.md vs code
| Topic | DESIGN.md | Code (renders) | Recommendation |
|---|---|---|---|
| Neutral text | `#111827` | `#141b2b` (`on-surface`) | code |
| Surface | `#F9FAFB` | `#f9f9ff` / `#f1f3ff` | code |
| Border | `#E5E7EB` | `#bfcaba` (`outline-variant`) | code (`#E5E7EB` only in two grid patterns) |
| Radius | sm 4 / DEFAULT 8 / md 12 / lg 16 / xl 24 | DEFAULT 4 / lg 8 / xl 12 / 2xl 16 | code |
| Primary button | "signature green gradient", uppercase Label-Caps | mostly solid primary; gradient on ~7 pages | solid default + gradient variant |
| Input focus | "2px green border + soft glow" | `border-primary` + `ring-2 ring-primary/20` | matches |
| Labels | "above the field in monospaced font" | yes | matches |
| Grid | 12-col desktop / 4-col mobile | 12-col used; mobile mostly 1-col | 12-col desktop, 1–2 col mobile |

### 12.22 Visual defects present in the export (do not copy)
- **Cart:** the coupon "Apply" button overflows the right edge of the order-summary card (flex input without `min-w-0`).
- **Product details:** the main zoom image is a `div` with `background-image` but no `bg-cover`, so the photo **tiles** (visible as repeated crops in the screenshot).
- **About hero:** background image div lacks `bg-cover bg-center`, so it repeats.
- **STL marketplace hero:** the 400px hero has no background image (empty `section` with only centered text).
- **About DfAM card:** an empty `absolute` image container (`w-1/2 h-full`). **Manage orders header** and **contact hero:** empty decorative divs.
- **Account sidebars** are `fixed inset-y-0` but the full-page screenshots end the sidebar at the first viewport (expected for fixed elements; not a defect in a browser).
- **Admin console** body is `h-screen overflow-hidden` with an internal scroll area (an app-shell pattern, unlike other admin pages).
- **Home:** `px-margin-desktop` (64px) is applied at all widths, with no mobile gutter.
- **Copy/data:** all names, prices, emails, phone numbers, and dates are mock content ("© 2024"). Do not ship them.
