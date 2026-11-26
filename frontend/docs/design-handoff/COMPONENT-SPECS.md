# Bekaa3D — Component Specifications

Every repeated UI pattern found across the 35 Stitch screens. Values are literal Tailwind classes from the source plus their resolved CSS. Token names refer to [DESIGN-TOKENS.md](./DESIGN-TOKENS.md). Where Stitch has several variants, the **Recommended canonical** form is marked; deviations are listed so nothing is lost.

Page short-names used in "Source references" (full folder names in [PAGE-SPECS.md](./PAGE-SPECS.md#page-inventory)):
`home` · `shop` · `marketplace` · `product` · `stl-detail` · `cart` · `checkout` · `about` · `contact` · `login` · `register` · `forgot` · `admin-login` · `acct-dash` · `orders-hist` · `offers-hist` · `my-reviews` · `wishlist` · `stl-library` · `profile` · `admin-dash` · `admin-console` · `analytics` · `adm-products` · `edit-product` · `upload-product` · `adm-stl` · `upload-stl` · `adm-categories` · `adm-orders` · `adm-customers` · `adm-reviews` · `adm-offers` · `adm-discounts` · `settings`

Components index:
1. [Storefront Top Navigation](#1-storefront-top-navigation) · 2. [Wordmark / Logo](#2-wordmark--logo) · 3. [Nav Link](#3-nav-link) · 4. [Header Icon Button & Cart Badge](#4-header-icon-button--cart-badge) · 5. [Search Fields](#5-search-fields) · 6. [Footer](#6-footer) · 7. [WhatsApp FAB](#7-whatsapp-floating-button) · 8. [Buttons](#8-buttons) · 9. [Hero Sections](#9-hero-sections) · 10. [Section Header](#10-section-header) · 11. [Product Card](#11-product-card) · 12. [STL Card](#12-stl-card) · 13. [Category Bento Tile](#13-category-bento-tile) · 14. [Feature Tile](#14-feature-tile) · 15. [Testimonial / Review Card](#15-testimonial--review-card) · 16. [Rating Stars](#16-rating-stars) · 17. [Price Display](#17-price-display) · 18. [Badges, Chips & Tags](#18-badges-chips--tags) · 19. [Filter Sidebar & Controls](#19-filter-sidebar--controls) · 20. [Results Toolbar](#20-results-toolbar) · 21. [Pagination](#21-pagination) · 22. [Breadcrumbs](#22-breadcrumbs) · 23. [Tabs](#23-tabs) · 24. [Media Gallery](#24-media-gallery) · 25. [Spec Tile Grid](#25-spec-tile-grid) · 26. [Quantity Stepper](#26-quantity-stepper) · 27. [Form Fields](#27-form-fields) · 28. [Checkbox, Radio, Radio Card](#28-checkbox-radio-radio-card) · 29. [Toggle Switch & Segmented Control](#29-toggle-switch--segmented-control) · 30. [Dropzone & Upload Row](#30-dropzone--file-upload-row) · 31. [Rich-text Toolbar](#31-rich-text-toolbar) · 32. [Tag Input](#32-tag-input) · 33. [Checkout Step Header](#33-checkout-step-header) · 34. [Payment Option Card](#34-payment-option-card) · 35. [Order Summary Card](#35-order-summary-card) · 36. [Cart Line Item](#36-cart-line-item) · 37. [Trust Badge Tile](#37-trust-badge-tile) · 38. [Auth Card](#38-auth-card) · 39. [Divider with Label & Social Button](#39-divider-with-label--social-login-button) · 40. [App Sidebar](#40-app-sidebar-account--admin) · 41. [App Top Bar](#41-app-top-bar) · 42. [KPI / Stat Card](#42-kpi--stat-card) · 43. [Data Table](#43-data-table) · 44. [Charts](#44-charts) · 45. [Activity Feed](#45-activity-feed--timeline) · 46. [Notification Panel](#46-notification-dropdown-panel) · 47. [Toast](#47-toast) · 48. [Modal / Success Overlay](#48-modal--success-overlay) · 49. [Empty State](#49-empty-state) · 50. [Loading State](#50-loading-state) · 51. [FAQ Accordion](#51-faq-accordion) · 52. [Promo Banner & CTA Panel](#52-promo-banner--cta-panel) · 53. [Stats Band](#53-stats-band) · 54. [Mobile Bottom Nav](#54-mobile-bottom-navigation) · 55. [Admin FAB](#55-admin-fab) · 56. [Callout / Info Box](#56-callout--info-box) · 57. [Admin Category Card](#57-admin-category-card) · 58. [Review Moderation Card](#58-review-moderation-card) · 59. [Settings Sub-nav](#59-settings-sub-nav) · 60. [Progress Bar](#60-progress-bar) · 61. [Avatar](#61-avatar) · 62. [Account Review Card](#62-account-review-card) · 63. [Filter Bar (app)](#63-app-filter-bar) · 64. [Page Header (app)](#64-app-page-header)

---

## 1. Storefront Top Navigation

**PURPOSE** Global site header on all storefront pages (home, shop, marketplace, product, stl-detail, cart, about, contact) and simplified on checkout.

**STRUCTURE**
```
nav/header (fixed top-0 w-full z-50, glass)
└─ inner container (max-w 1440 mx-auto px-64 flex justify-between items-center)
   ├─ left: Wordmark [+ link group (hidden md:flex gap-6|8)]
   └─ right: [search (hidden lg:flex)] · icon buttons (search / cart+badge / account) · [LOGIN outline] · [REGISTER solid]
```
Home and shop put the link group in the **center** (justify-between with 3 children); product, cart, marketplace, about, contact put links **next to the logo** (`gap-8` / `gap-12` after logo).

**DIMENSIONS**
- Height: **64px** (`h-16`) canonical; 80px (`h-20`) on marketplace; `py-4` (16px vertical + content ≈ 72px) on home/shop/product (home shrinks to `py-2` + `shadow-lg` when `scrollY > 50`).
- Horizontal padding: `px-margin-desktop` 64px.
- Link gap: 32px (`gap-8`) home/shop/marketplace; 24px (`gap-6`) product/cart/contact.
- Right group gap: 16px (`gap-4`) – 24px (`gap-6`).

**TYPOGRAPHY** Links Inter 16px (`font-body-md`), weight 400 (marketplace inactive `font-medium` 500). Alt (about/contact/stl-detail): JetBrains Mono 12px 600 0.05em (`font-label-caps text-label-caps`). LOGIN/REGISTER buttons: mono 12px caps.

**COLORS** Background `bg-surface/80` (`rgba(249,249,255,.8)`) or `bg-white/70` (home), `backdrop-blur-xl` (24px) / `backdrop-blur-md` (12px, home & marketplace). Link `on-surface-variant` → hover `primary`; active `primary`.

**BORDERS / SHADOWS** `border-b border-outline-variant/30` (home: `border-white/10`). `shadow-sm` on most.

**ICON PLACEMENT** Right-side icons 24px Material Symbols in `p-2` buttons. Cart badge top-right (see §4).

**HOVER** link color 200–300ms; icon buttons `hover:text-primary` and/or `hover:bg-surface-container rounded-full`; `active:scale-95`.

**FOCUS** none defined → add `focus-visible:ring-2 ring-primary`.

**ACTIVE** current page link: `text-primary font-bold border-b-2 border-primary pb-1` (marketplace: `py-7` so underline sits on nav bottom edge).

**MOBILE BEHAVIOR** Links `hidden md:flex` (hidden <768px). Search `hidden lg:block/flex` (<1024px hidden). LOGIN `hidden md:block`; REGISTER stays. "Cart" text label `hidden sm:inline`. **No hamburger menu exists in any storefront page** → implementer must add a mobile menu (recommend: menu icon button left of cart, opening a full-height sheet with the same links).

**DESKTOP BEHAVIOR** Fixed; content below offset by `pt-24`/`pt-32` (96/128px).

**VARIANTS**
| Variant | Pages | Notes |
|---|---|---|
| A · Centered links + auth buttons | home | gradient logo 32px, LOGIN outline (`border border-outline/30 px-4 py-2 rounded-lg`) + REGISTER solid (`bg-primary px-4 py-2 rounded-lg shadow-sm`) |
| B · Centered links + search pill + cart + person | shop | search pill `bg-surface-container rounded-full px-4 py-2 border-outline-variant/20 w-48 input` |
| C · Logo+links left, search + Cart(text) + Login button | marketplace | `h-20`, search `w-64 bg-surface-container-low border rounded-lg pl-10`, Login `bg-primary px-6 py-2 rounded-lg font-bold` with `account_circle` icon |
| D · Logo+links left, cart + person icons | product, cart | cart icon `text-primary` + badge `bg-secondary` on cart |
| E · Mono links, search/cart/account icon buttons | about, contact, stl-detail | `hover:bg-surface-container rounded-full`; contact account button has `border-2 border-primary/10` |
| F · Checkout | checkout | logo left; right: filled `lock` icon `text-primary` + "SECURE CHECKOUT" mono caps `tracking-wider` `on-surface-variant` |

**Recommended canonical:** Variant D/B hybrid — 64px, glass `bg-surface/80 backdrop-blur-xl border-b border-outline-variant/30`, logo + links left (`gap-8`), right: search pill (lg+), cart w/ badge, account icon or LOGIN/REGISTER when signed out.

**SOURCE REFERENCES** all storefront `code.html` files listed above.

---

## 2. Wordmark / Logo

**PURPOSE** Brand identity; always text "Bekaa3D" (no image logo exists in the export).

**STRUCTURE** `<a|span|h1>` text; optionally preceded by an icon tile.

**DIMENSIONS / TYPOGRAPHY / COLORS**
| Variant | Spec | Pages |
|---|---|---|
| Standard | Hanken Grotesk 20px (`text-headline-md`), `font-extrabold` 800 (or `font-bold`), `text-primary` | shop, product, cart, checkout, order-hist, most sidebars |
| Large | 32px (`text-headline-lg`), extrabold, `tracking-tight`, `text-primary` | marketplace, forgot |
| Gradient | 32px bold, `bg-clip-text text-transparent bg-gradient-to-r from-primary to-secondary-fixed` | home |
| Mono-ink | 20px `font-black tracking-tighter text-on-surface` | about, contact, stl-detail |
| Split | "Bekaa" `on-surface` + "3D" `text-primary`, 20px black tracking-tighter | login |
| Tile + text | 40×40 `rounded-lg bg-primary-container text-on-primary-container` with filled `deployed_code` 24px, then wordmark 20px `leading-none` + caption `text-[10px] font-label-caps tracking-widest on-surface-variant` "ENGINEERING PRECISION" | admin-dash |
| Tile (solid) | 40×40 `bg-primary rounded` (4px) white `deployed_code` + wordmark | admin-login |
| Icon + text | `precision_manufacturing` 36px `text-primary` + wordmark extrabold | register |
| Footer | Hanken 20px bold `on-surface` (or `primary` on home) | footers |

Sidebar caption under wordmark: `text-xs`/`text-[10px] font-label-caps uppercase tracking-widest text-outline` — "ENGINEERING PRECISION", "Admin Console", "Precision Control", "Precision Console".

**Recommended canonical:** Standard (20px/800/primary). App sidebars: Tile + text.

---

## 3. Nav Link

See §1. States: default `text-on-surface-variant`, hover `text-primary` (`transition-colors duration-200`), active `text-primary font-bold border-b-2 border-primary pb-1`. Footer links: `on-surface-variant` hover `text-primary` / `text-secondary` / `underline decoration-primary decoration-2 underline-offset-4`; marketplace footer adds `hover:translate-x-1 duration-300`.

---

## 4. Header Icon Button & Cart Badge

**STRUCTURE** `button.p-2 > span.material-symbols-outlined` (24px icon) + optional badge.

**DIMENSIONS** 40×40 hit area (`p-2` + 24px icon). Admin variant: `w-10 h-10 rounded-full flex items-center justify-center`.

**COLORS** `text-on-surface-variant` hover `text-primary` and/or `hover:bg-surface-container(-low/50) rounded-full`.

**CART BADGE** `absolute`, 16×16 (`w-4 h-4`), `rounded-full`, `bg-primary` (cart page: `bg-secondary`), `text-white text-[10px] font-bold`, centered digits. Position `top-0 right-0` (home), `-top-2 -right-2` (shop), `-top-1 -right-1` (cart).

**NOTIFICATION DOT** 8×8 `bg-error rounded-full`, `absolute top-2 right-2` (or `top-0 right-0`), often `border-2 border-white|surface` ring.

**ACTIVE** `active:scale-95`.

**Source:** all navs/topbars.

---

## 5. Search Fields

| Variant | Spec | Pages |
|---|---|---|
| Nav pill | `flex items-center bg-surface-container rounded-full px-4 py-2 border border-outline-variant/20 focus-within:border-primary` + leading `search` icon `mr-2` + borderless input `w-48` | shop |
| Nav/admin rounded | `relative`; icon `absolute left-3 top-1/2 -translate-y-1/2 text-outline`; input `pl-10 pr-4 py-2 bg-surface-container-low border border-outline-variant rounded-lg|rounded-full w-64 focus:ring-2 focus:ring-primary/20` | marketplace, admin topbars, my-reviews, wishlist (`focus:w-80` expands) |
| Admin borderless | `bg-surface-container-low border-none rounded-lg py-2.5 pl-11` | admin-dash |
| Hero glass search | `glass-panel rounded-full p-2 flex shadow-2xl`; input `flex-grow bg-transparent px-6 py-4 text-body-lg`; button `primary-gradient text-white px-8 rounded-full font-label-caps uppercase` w/ search icon | shop hero |
| Hero card search | `max-w-3xl mx-auto bg-surface p-2 rounded-xl shadow-xl flex flex-col md:flex-row gap-2 border border-outline-variant/30`; leading `search` icon `text-primary`; button `signature-gradient px-10 py-3 rounded-lg font-bold text-label-caps tracking-widest uppercase` "Search Database" | marketplace hero |
| Trailing-icon search | input `rounded-full px-6 py-2 w-64`, icon `absolute right-4 top-2` | order-hist header |
| Filter search | `w-full pl-12 pr-4 py-3 rounded-lg border border-outline-variant focus:ring-2 focus:ring-primary` | adm-stl, adm-discounts |

**FOCUS** `focus:ring-2 focus:ring-primary/20` (+ `focus:border-primary`). JS in several pages adds `ring-2 ring-primary/20` or `scale-105` to the wrapper on focus — replicate ring via `:focus-within`, skip scale.

---

## 6. Footer

**PURPOSE** Site footer on storefront & account-dashboard pages.

**STRUCTURE (recommended canonical, from home + shop)**
```
footer (bg-surface-container-low, border-t border-outline-variant, pt-24 pb-12 | py-16)
├─ grid (max-w 1440, px-64, grid-cols-1 md:grid-cols-4, gap-gutter 24px, mb-20)
│  ├─ Brand col: wordmark (mb-6) · description (on-surface-variant, mb-8) · social circles row (gap-4)
│  ├─ Link col × 2: heading (mb-6) · ul space-y-4 of links
│  └─ Newsletter col: heading · helper text (text-xs, mb-4) · input+icon button row (gap-2)
└─ bottom bar (pt-8 border-t border-outline-variant/30 flex justify-between): copyright · payment logos (h-6, opacity-40 grayscale → hover full)
```

**DIMENSIONS** Social circle `w-10 h-10 rounded-full border border-outline/20` (or `bg-surface-container-highest`), icon `text-sm`/24px. Newsletter input `px-4 py-2 rounded-lg text-xs`; button `p-2 rounded-lg bg-primary` with `send` icon.

**TYPOGRAPHY** Headings: `font-bold` Inter 16px (home/product) or mono caps 12px (`font-label-caps text-label-caps uppercase`) `on-surface` (shop) / `primary` (about, contact, checkout); links 16px Inter (or 14px `text-sm`); copyright `text-[14px]`/`text-xs`/mono `text-[10px]`.

**COLORS** Bg variants: `surface-container-low` (home, marketplace), `surface-container-lowest` (shop, product, cart, checkout, acct-dash), `surface-container-highest` (about, contact, stl-detail). Links `on-surface-variant` (marketplace `/70`).

**HOVER** social circle `hover:bg-primary hover:text-white` (home, about) or `hover:text-primary`; links `hover:text-primary|secondary` / underline.

**VARIANTS**
- Shop: 4-col, mono headings, centered copyright bar.
- Marketplace: `grid-cols-12` (4/2/2/4), legal links inline wrap, copyright inside 4th col.
- Product: newsletter stacked (input over full-width SUBSCRIBE button), bottom bar with Privacy/Terms links.
- Cart: compact; links `underline` by default; mono 10px headings `tracking-widest`.
- Checkout: mono `primary` headings; bottom bar mono uppercase with `language` icon + "English (CH)".
- About/contact/stl-detail: `surface-container-highest`, mono headings `primary`, 2 social squares/circles or terminal/share icons.
- Account dashboard: inside main column (offset by sidebar); newsletter input joined to "SUB" button (`rounded-l-lg` / `rounded-r-lg`).
- Account/app pages otherwise have **no site footer** (downloads/orders-admin use a slim meta footer: mono 10px uppercase version/status + text-xs links).

**MOBILE** columns stack to 1 col; bottom bar `flex-col md:flex-row gap-4`.

---

## 7. WhatsApp Floating Button

**STRUCTURE** `a.fixed.bottom-8.right-8` > WhatsApp SVG glyph (white).
**DIMENSIONS** 56×56 (`w-14 h-14`, home) or `p-4` + 32px SVG = 64×64 (shop). `rounded-full`.
**COLORS** `bg-[#25D366] text-white`. **SHADOW** `shadow-xl` (home) / `shadow-2xl` (shop).
**HOVER** `hover:scale-110` 200–300ms; `active:scale-95`.
**Z** `z-50` / `z-[60]`.
**Pages** home, shop (stl-detail has it commented out). Link should be `https://wa.me/<number>` `target="_blank" rel="noopener"` + `aria-label`.

---

## 8. Buttons

All buttons: `inline-flex items-center justify-center gap-2`, label JetBrains Mono 12px 600 0.05em uppercase (`font-label-caps`) unless noted; transitions `transition-all`; press `active:scale-95` (or `[0.98]` for full-width).

| Variant | Classes (source) | Resolved | Hover / Active | Disabled | Pages |
|---|---|---|---|---|---|
| **Primary (canonical)** | `bg-primary text-on-primary px-8 py-4 rounded-lg shadow-lg font-label-caps` | `#0d631b` bg, white, 32×16 pad, 8px radius | `hover:bg-primary-container` (#2e7d32); `active:scale-95` | add `opacity-50 cursor-not-allowed` | home hero, checkout, register (`h-14`), profile, admin |
| Primary – medium | `px-6 py-2.5 / py-3` | 24×10–12 | same | | admin headers |
| Primary – small | `px-4 py-2` (`text-xs`) | | | | home nav REGISTER, table "VIEW DETAILS" |
| Primary – glow | + `shadow-lg shadow-primary/20` | green-tinted shadow | | | login, register, STL detail, admin |
| Primary – gradient | `.btn-gradient` etc. (135° `#2e7d32→#1b6d24`) | | `filter: brightness(1.1); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(46,125,50,.2)` | | login, contact, about, edit-product, shop (variant colours), marketplace, forgot, stl-detail |
| Primary – container | `bg-primary-container text-white|on-primary-container` | #2e7d32 | `hover:brightness-110` | | wishlist, admin-login, adm-stl, categories, stl-library ("DOWNLOAD STL": `text-on-primary-container` → hover `bg-primary text-white`) |
| Secondary outline (2px) | `border-2 border-primary text-primary px-8 py-4 rounded-lg` | | `hover:bg-primary/5` or `hover:bg-primary hover:text-white` (shop "REQUEST SLOT", order-hist) | | home, shop sidebar, order-hist |
| Secondary outline (1px) | `border border-primary text-primary py-3/4 rounded-lg` | | `hover:bg-primary/5` / `hover:bg-primary-fixed` | | home STL "OFFER", product datasheet, upload-product "SAVE AS DRAFT" |
| Neutral outline | `border border-outline-variant (or outline) text-on-surface rounded-lg px-4 py-2` | | `hover:bg-surface-container(-low/-high)` | | wishlist "Share", my-reviews "Edit", tables |
| Tonal | `bg-surface-container-highest text-on-surface-variant` | #dce2f7 | `hover:bg-outline-variant` | | product "WRITE A REVIEW" (`rounded-full px-6 py-3`), admin console quick actions |
| Secondary tonal (lime) | `bg-secondary-container text-on-secondary-container px-6 py-2.5 rounded-lg` | #b9f474 / #437000 | `hover:bg-secondary hover:text-on-secondary` | | admin console "UPLOAD STL" |
| Inverse | `bg-on-surface text-surface` / `bg-on-background text-white` / `bg-inverse-surface text-inverse-on-surface` | #141b2b / #293040 | `hover:opacity-90` / `hover:bg-on-surface-variant` | | cart Apply, marketplace "DOWNLOAD FREE", wishlist "Add All", adm-reviews filter |
| Accent lime | `bg-secondary-fixed text-on-secondary-fixed px-10 py-5 rounded-xl shadow-lg` | | `hover:scale-105 hover:shadow-secondary-fixed/20` | | home promo |
| White on brand | `bg-on-primary text-primary px-8 py-4 rounded-xl shadow-lg` / `bg-white text-primary px-10 py-5 rounded-full shadow-xl` | | `hover:bg-primary-fixed` / `hover:bg-surface-container-low` | | home CTA, about CTA |
| Ghost on brand | `border border-on-primary/30 text-on-primary` / `border-white/30|40 text-white` | | `hover:bg-white/10` | | home CTA, about hero/CTA |
| WhatsApp solid | `bg-[#25D366] text-white px-8 py-4 rounded-xl shadow-lg` | | `hover:scale-105` | | home CTA |
| WhatsApp outline | `border-2 border-[#25D366]/30 text-[#25D366] py-3 rounded-lg` + `chat` icon | | `hover:bg-[#25D366]/5` | | stl-detail |
| Danger outline | `border-2 border-error text-error px-5 py-2 rounded-lg` | | `hover:bg-error hover:text-white` | | edit-product |
| Danger ghost | `text-error` / `border border-error/20 text-error` | | `hover:bg-error-container` / `hover:bg-error/5` | | my-reviews Delete, offers-hist Withdraw, cart Remove (`hover:text-error`) |
| Text link | `text-primary font-bold hover:underline decoration-2 underline-offset-8` | | | | home "VIEW ALL PRODUCTS" |
| Icon square | `bg-surface-container-highest p-2 rounded-lg` (add-to-cart) | 40×40 | `hover:bg-primary hover:text-white active:scale-90` | | home product card |
| Icon circle (white) | `bg-white text-on-surface p-3 rounded-full shadow-lg` | 48×48 | `hover:bg-primary hover:text-white` | | shop card overlay |
| Icon glass | `w-10 h-10 rounded-full glass-panel` | | `hover:text-error` / `hover:bg-error hover:text-white` | | marketplace, wishlist |
| Row icon | `p-1.5 text-on-surface-variant` (`text-xl` icon) | | `hover:text-primary` / `hover:text-error` | | admin tables |
| Large CTA (Hanken) | `w-full bg-primary py-5 rounded-xl font-display text-headline-md font-bold shadow-lg shadow-primary/20` + `arrow_forward` | 20px Hanken | `hover:bg-primary-container active:scale-[0.98]` | | cart "Proceed to Checkout" |

**Icon placement** trailing `arrow_forward` (14–24px) for forward actions; leading icon for verbs (`shopping_cart`, `download`, `add`, `send`).
**Loading** (JS in contact/admin-login): label replaced by `sync`/spinner `animate-spin` + "Sending...", `disabled`; success: `check_circle` + "Message Sent", bg `#0d631b`.
**Recommended canonical:** Primary, Secondary outline (2px), Neutral outline, Tonal, Inverse, Danger, Text link, Icon — sizes `sm` (px-4 py-2), `md` (px-6 py-3), `lg` (px-8 py-4).

---

## 9. Hero Sections

| Variant | Spec | Page |
|---|---|---|
| **Split hero** | `section relative pt-32 pb-20 min-h-screen flex items-center overflow-hidden`; 2 blurred orbs (`bg-primary/5 blur-[120px]` top-right 60%, `bg-secondary/5 blur-[100px]` bottom-left 40%); grid `md:grid-cols-2 gap-16 items-center`. Left: eyebrow (mono primary tracking-widest mb-4) · H1 display `leading-tight mb-6` with gradient span · body-lg `max-w-lg mb-8` · button row `gap-4` · mini-stats (`mt-12 flex gap-8 border-t border-outline/10 pt-8`; value `font-headline-md text-primary`, label mono `opacity-70`). Right: image `rounded-2xl shadow-2xl border-white/20 aspect-square` + glass chips: top-right `-top-6 -right-6 glass-panel p-4 rounded-xl shadow-lg animate-bounce(4s)` with "STATUS: PRINTING" + progress bar `w-32 h-1.5`; bottom-left `-bottom-10 -left-10 glass-panel p-6 rounded-xl` (hidden <md) with 48px icon circle `bg-primary/10` + "AI CALIBRATION". | home |
| **Image banner w/ search** | `rounded-xl overflow-hidden h-[300px]`, bg image `brightness-50` cover, centered H1 display white mb-6, glass pill search `max-w-2xl` | shop |
| **Centered text hero** | `h-[400px] flex items-center justify-center`; pill eyebrow; H1 display; body-lg `max-w-2xl mb-10`; card search `max-w-3xl`; trust row `mt-6 gap-8 font-label-caps text-[10px]` with 14px icons (`check_circle`, `verified_user`, `precision_manufacturing`) | marketplace |
| **Full-bleed photo hero** | `h-[819px]`; image + `bg-gradient-to-r from-on-surface/80 to-transparent`; left text `max-w-2xl`: eyebrow `text-primary-fixed-dim tracking-[0.2em]`, H1 display white, body-lg `text-surface-container-low leading-relaxed`, buttons (gradient + white ghost) | about |
| **Boxed hero** | `rounded-xl bg-surface-container-low p-12 md:p-20 text-center border-outline-variant/20`; H1 display; body-lg `max-w-2xl`; response-time pill `bg-primary-container/20 text-on-primary-container border-primary/20 rounded-full px-4 py-1.5` with filled `timer` icon | contact |
| **Page title header** | `mb-12`: H1 display + body-md muted | cart |

---

## 10. Section Header

- **Centered:** `text-center mb-16` → H2 `font-display text-headline-lg mb-4` (32px) → `p.text-on-surface-variant.max-w-2xl.mx-auto`. (home ×3, about, marketplace)
- **Split:** `flex justify-between items-end mb-12` → left H2 + muted subtitle; right text link (`text-primary font-bold`) or filter buttons (`bg-white border border-outline/20 px-4 py-2 rounded-lg font-label-caps text-xs` "FILTER: ALL", "SORT: NEWEST") or carousel arrows (`p-2 rounded-full border border-outline-variant/30`). (home, product, cart, stl-detail, about)
- **Accent underline:** H2 + `div.h-1.w-20.bg-primary.mx-auto.mt-4.rounded-full` (contact FAQ).

---

## 11. Product Card

**PURPOSE** Physical product tile in grids.

### 11a · Showcase (home "Physical Masterpieces")
```
div.group
├─ media: relative aspect-square rounded-xl overflow-hidden mb-4 bg-surface-container-low border border-outline/5 shadow-sm
│  ├─ badge top-4 left-4 (NEW: bg-primary | -30%: bg-tertiary) text-[10px] font-bold px-2 py-1 rounded
│  ├─ wishlist btn top-4 right-4 bg-white/80 backdrop-blur-sm p-2 rounded-full shadow-sm, opacity-0 → group-hover:opacity-100, hover:text-error (favorite 20px)
│  ├─ img w-full h-full object-cover group-hover:scale-105 duration-500
│  └─ overlay inset-0 bg-black/40 opacity-0 group-hover:opacity-100 → "QUICK VIEW" button (bg-white px-4 py-2 rounded-lg mono text-xs, visibility icon; hover bg-primary text-white)
├─ category: mono 10px on-surface-variant
├─ title: font-headline-md (20px) mb-2, group-hover:text-primary
├─ rating row: 5 amber-400 stars (24px, FILL 1) + "(124)" text-xs, gap-2 mb-3
└─ footer: flex justify-between — price font-headline-md text-primary (+ strike text-xs) · add-to-cart icon square
```
### 11b · Catalog (shop)
```
div.bg-white rounded-xl overflow-hidden border border-outline-variant/20 group (hover: translateY(-8px), shadow 0 20px 40px rgba(0,0,0,.08), 300ms)
├─ media relative aspect-square bg-surface-container-low; img group-hover:scale-110 duration-500
│  ├─ category pill top-4 left-4: bg-primary|secondary|tertiary text-white text-[10px] font-bold px-3 py-1 rounded-full uppercase tracking-widest
│  └─ hover overlay bg-black/40: two 48px white circle buttons (visibility, favorite)  [first row only]
└─ body p-6
   ├─ stars: 5× text-sm (14px) text-secondary filled / outline-variant empty + "(42)" text-label-caps text-outline-variant ml-1
   ├─ title font-headline-md text-headline-md text-on-surface mb-1 truncate
   ├─ price text-lg font-bold text-on-surface-variant mb-4
   └─ CTA w-full py-3 primary-gradient text-white rounded-lg mono uppercase + shopping_cart icon; hover brightness-110
```
### 11c · Wishlist
`bg-surface-container-lowest rounded-xl border border-outline-variant flex flex-col` + `.card-hover` (lift -4px, soft shadow). Media aspect-square; top-right column of two 40px glass buttons (delete `text-error` hover `bg-error text-white`; visibility hover `bg-primary`); bottom-left stock/discount tag (`bg-secondary-container text-on-secondary-container` "In Stock" / `bg-primary-container text-white` "20% OFF", `text-[10px] font-label-caps px-2 py-1 rounded`). Body `p-6 flex-1 flex flex-col`: title `font-headline-md text-lg leading-tight` + price `font-headline-md text-primary` (right; strike `text-xs line-through opacity-50` below); stars 16px amber-400 + "(48 Reviews)" text-xs; CTA `mt-auto w-full bg-primary-container text-white py-3 rounded-lg font-label-caps text-sm` + cart icon. Remove animation (JS): opacity 0 + scale .95 over 300ms then removal → empty state.
### 11d · Compact / related (product, cart)
`div.group` → `aspect-square rounded-2xl bg-surface-container(-low) overflow-hidden mb-4 relative shadow-sm` with image zoom (105/110) and a quick-add circle `absolute bottom-4 right-4 bg-surface|white/90 p-2|3 rounded-full shadow-md|lg opacity-0 translate-y-2 → group-hover:opacity-100 translate-y-0` (icon `add_shopping_cart`, cart page `text-primary` filled). Below: name `font-bold`/`font-headline-md` + price `text-primary font-bold` (cart: `text-sm on-surface-variant`).

**MOBILE** grids 1-col → `sm:2` → `lg:3` / `md:4`. Hover-only controls (quick view, wishlist) must be reachable on touch — recommend always-visible icon buttons <md.
**Recommended canonical:** 11b structure with 12px radius, 1px `outline-variant/30` border, `shadow-sm`, hover lift -4px + `shadow-xl`, solid primary CTA.

---

## 12. STL Card

### 12a · Home marketplace card
`bg-white rounded-2xl overflow-hidden shadow-sm hover:shadow-xl transition-shadow border border-outline/5 group`. Media `relative aspect-[16/10] bg-black`, image `opacity-80 group-hover:opacity-100`; license badge `top-4 left-4 text-[10px] font-bold px-2 py-1 rounded` — COMMERCIAL `bg-surface-tint text-white`, PERSONAL `bg-on-surface-variant text-white`, EXCLUSIVE `bg-tertiary-container text-on-tertiary-container`. Body `p-6`: title row (`font-headline-md mb-1` + "Format: STL, OBJ, STEP" text-xs | price `font-headline-md text-primary`) mb-4; meta strip `flex gap-4 mb-6 text-xs border-y border-outline/10 py-3` with 14px icons (`precision_manufacturing` "0.1mm Opt", `download` "1.2k Downloads"); actions `grid grid-cols-2 gap-3`: BUY NOW (solid primary `py-3 rounded-lg text-xs`) + OFFER (1px outline).
### 12b · Marketplace card
`group bg-surface rounded-xl border border-outline-variant/30 overflow-hidden shadow-sm hover:shadow-xl duration-300 flex flex-col`. Media `h-64` image zoom 110 / 700ms; license badge `px-3 py-1 bg-primary|secondary text-on-* font-label-caps text-[10px] rounded shadow-lg`; favourite glass circle 40px top-right `hover:text-error`. Body `p-6 flex-grow flex flex-col`: title (`font-headline-md`, renders 16px — see DESIGN-SYSTEM §12.3) + price `font-bold text-headline-md text-primary` (FREE: `text-secondary`); description `text-sm line-clamp-2 mb-4`; meta row `gap-4 mb-6`: amber-500 star 14px + "4.9" bold text-sm · "(128 reviews)" text-xs · format tag `text-xs px-2 py-0.5 bg-surface-container-highest rounded`; actions `flex gap-2 mt-auto`: "Buy Now" `flex-grow signature-gradient py-3 rounded-lg font-bold text-label-caps uppercase` + offer icon button `px-4 py-3 border border-outline-variant rounded-lg` (`bid_landscape`). Free variant: "Download Free" `bg-on-surface text-surface`.
### 12c · Related STL (stl-detail)
`.bento-card group bg-surface-container-lowest rounded-xl border border-outline-variant/30 overflow-hidden` (hover shadow `0 20px 40px -20px rgba(0,0,0,.1)`). Media aspect-square, zoom 105; price tag top-right `px-2 py-1 bg-surface/80 backdrop-blur-md rounded font-label-caps text-[10px]` (FREE: `bg-primary text-white`). Body `p-4 space-y-2`: title `font-bold group-hover:text-primary`; desc `text-xs line-clamp-1`; meta row mono 10px "STL / STEP" + download icon 12px count.
### 12d · Library / download card (stl-library)
`bg-white rounded-xl border border-outline-variant shadow-sm hover:shadow-xl hover:-translate-y-1 duration-300 flex flex-col group`. Media `aspect-video`, license badge `top-3 left-3 bg-primary|secondary text-white text-[10px] font-label-caps px-2 py-1 rounded shadow-lg uppercase`. Body p-6: title + version mono `text-xs text-outline`; purchase date `text-xs` w/ `calendar_month` 14px; 2-col meta grid (`pt-4 border-t border-outline-variant/50`; label mono 10px `outline` uppercase / value `text-sm font-semibold`); footer: download count (`download_done` text-primary / `cloud_off` text-outline "Never Downloaded") + "DOWNLOAD STL" `bg-primary-container text-on-primary-container px-6 py-2.5 rounded-lg font-label-caps text-sm` (hover `bg-primary text-white`).
### 12e · Dashboard asset card (acct-dash)
`bg-surface-container-lowest border-outline-variant/30 rounded-2xl card-shadow hover:translate-y-[-4px]`. Media `h-40` with format tag top-right `bg-primary/10 text-primary text-[10px] font-bold px-2 py-0.5 rounded backdrop-blur-md`. Body p-4: title `font-bold text-sm`, meta `text-[12px]` "Version 2.4 • 42.1 MB", actions `flex gap-2`: DOWNLOAD `flex-1 bg-primary text-white py-2 rounded-lg text-[12px] font-label-caps` + 40px info outline button.

---

## 13. Category Bento Tile

**STRUCTURE** `group relative overflow-hidden rounded-2xl` → bg image layer (`absolute inset-0 bg-cover`, zoom 110/500ms; large tile `opacity-40` zoom 105/700ms on `bg-primary-container`) → scrim (`bg-black/30 → group-hover:bg-black/10`; large: `bg-gradient-to-t from-black/80 via-transparent`) → content (`absolute inset-0 flex items-end p-6`, title `text-white font-bold text-xl`).
Large featured tile: `md:col-span-2 md:row-span-2 h-[500px]`, content `p-8`: eyebrow mono `text-primary-fixed` · title `text-white text-3xl font-bold mb-4` · desc `text-white/80 mb-6` · link `text-white font-bold hover:gap-4` "EXPLORE LIBRARY" + `arrow_right_alt`.
Small tiles: `h-[240px] shadow-sm`. Grid `grid-cols-1 md:grid-cols-4 gap-6`. **Page:** home.

## 14. Feature Tile

Home "Precision as Standard": `text-center group p-4` → 64px icon box `w-16 h-16 bg-surface-container rounded-2xl mx-auto mb-6` (icon `text-3xl`), hover `bg-primary text-white rotate-6` 300ms → title `font-headline-md text-sm mb-2` → desc `text-xs on-surface-variant`. Grid `md:grid-cols-3 lg:grid-cols-6 gap-8`.
Marketplace verification tiles: `glass-panel p-6 rounded-xl border-[rgba(191,202,186,.3)]` left-aligned; icon `text-primary text-3xl mb-4`; title `font-headline-md mb-2`; desc `text-sm`. Grid `md:grid-cols-4 gap-gutter`.
Product "Material Engineering" cards: `bg-surface-container-high p-8 rounded-2xl border-outline-variant/20 hover:shadow-md`; icon box `w-12 h-12 bg-primary/10 rounded-xl text-primary mb-6`; title `font-display text-headline-md mb-3`.
About capabilities bento: see PAGE-SPECS (about).

## 15. Testimonial / Review Card

- **Testimonial (home):** `glass-panel p-10 rounded-2xl border border-white/50 shadow-sm flex flex-col justify-between`; 5 filled stars `text-primary mb-6`; quote `font-body-lg italic text-on-surface mb-8`; author row `gap-4`: 48px round photo + name `font-bold` + role `text-xs`.
- **Product review (product):** `bg-surface p-6 rounded-2xl border-outline-variant/30 flex flex-col h-full`; stars 20px `text-primary gap-1 mb-4`; headline `font-bold mb-2` in quotes; body `text-body-md italic flex-grow mb-6`; author: 40px initials circle (`bg-primary/20 text-primary` | `secondary/20` | `tertiary/20`) + name `font-bold text-[14px]` + role `text-[12px]`.
- **Review summary snippet (stl-detail):** 48px avatar + name `font-bold text-sm` + amber-500 14px stars; quote `text-xs italic`; link "READ ALL 42 REVIEWS" `text-xs text-primary font-bold`.

## 16. Rating Stars

Glyph `star` with `font-variation-settings:'FILL' 1` for filled; `star_half` (or `FILL 0.5`) for half; unfilled `star` (FILL 0) in muted colour. Sizes: 24px (home), 20px (reviews), 16px (wishlist), 14px (`text-sm`, shop/marketplace/stl-detail/analytics). Gap 0 (adjacent glyphs) or `gap-1`. Count text: `text-xs on-surface-variant` "(124)" / `text-label-caps text-outline-variant`. Numeric variant: single star + "4.9" `font-bold text-sm`. Colours: see DESIGN-SYSTEM §12.12. Accessibility: wrap with `aria-label="4.5 out of 5"` and hide glyphs (`aria-hidden`).

## 17. Price Display

| Context | Spec |
|---|---|
| Card | `font-headline-md text-primary` (Hanken 20/600 green) — home/marketplace; shop `text-lg font-bold text-on-surface-variant` |
| Discount pair | current `font-headline-md text-primary` + old `text-xs line-through on-surface-variant` with `items-baseline gap-2` |
| Detail hero | `text-display font-display text-primary` (48px/800) + old `line-through text-headline-md on-surface-variant` `gap-4 items-baseline` |
| STL detail | `text-2xl font-bold text-primary font-headline-md` + license chip |
| Summary total | label mono `text-xs uppercase tracking-tighter` "TOTAL DUE" + `text-headline-lg font-bold` (cart) / "Total Due" `font-headline-lg` + `font-display text-headline-lg text-primary` (checkout) |
| Summary line | `flex justify-between on-surface-variant` (values mono in checkout `font-label-caps`) |
| Free | "FREE" `text-secondary font-bold` / mono chip `text-secondary-container bg-on-secondary-container/10 px-2 rounded` (checkout shipping) |
| Table | `text-sm font-bold text-on-surface` or mono `font-label-caps font-bold` |
| Offer table | original `text-sm font-mono on-surface-variant`, offer `text-sm font-bold text-primary` |

## 18. Badges, Chips & Tags

| Type | Spec | Examples |
|---|---|---|
| Image overlay badge (square) | `absolute top-4 left-4 text-[10px] font-bold px-2 py-1 rounded`, white text on `primary`/`tertiary`/`surface-tint`/`on-surface-variant` | NEW, -30%, COMMERCIAL LICENSE |
| Image overlay pill | `px-3 py-1 rounded-full uppercase tracking-widest text-[10px] font-bold` on `primary`/`secondary`/`tertiary` | ENGINEERING, HOME DECOR |
| Status pill (canonical) | `px-3 py-1 rounded-full font-label-caps text-[10px]/[11px] font-bold uppercase` + bg/text per status (DESIGN-SYSTEM §9) | Active, Pending, Suspended |
| Status pill with dot | `flex items-center gap-1.5 px-3 py-1 rounded-full w-fit text-[11px] font-bold` + `w-1.5 h-1.5 rounded-full` dot in the text colour (pulse on pending) | In Stock, Low Stock, PENDING |
| Bordered status | + `border border-amber-200 / blue-200 / primary-container/20` | adm-offers, acct-dash |
| Stock pill | `bg-secondary-container text-on-secondary-container px-3 py-1 rounded-full font-label-caps text-label-caps` | IN STOCK (product) |
| Trend chip | `text-[10–11px] font-label-caps px-2 py-0.5 rounded-full`: `+12%` `text-primary bg-primary-fixed` · `-2%` `text-error bg-error-container` · `New` `on-surface-variant bg-surface-container-high` | admin-dash, admin-console |
| Format tag | `px-3 py-1 bg-surface-container-highest rounded text-[12px] font-bold` (inactive `text-on-surface/40`) / `text-xs px-2 py-0.5 rounded` | STL, STEP |
| Compatibility chip | `px-3 py-1 rounded-full bg-surface-container-high border border-outline-variant/30 text-[12px] font-medium` | Bambu Lab X1 |
| Spec pill | `px-3 py-1 bg-surface-container rounded-full font-label-caps text-[10px]` | 600MM/S SPEED |
| Verified pill | `bg-primary-container text-on-primary-container font-label-caps text-[10px] px-3 py-1 rounded-full border border-primary/20` | VERIFIED DESIGN |
| Verified purchase | `flex items-center gap-1 text-xs font-label-caps text-primary bg-primary-container/20 px-3 py-1 rounded-full` + filled `verified` 14px | my-reviews |
| Member badge | `px-3 py-1 bg-primary-fixed text-on-primary-fixed text-xs font-label-caps rounded-full` + filled `verified` | PRO MEMBER |
| Default tag | `bg-secondary-container text-on-secondary-container px-2 py-0.5 rounded text-[10px] font-label-caps` | DEFAULT address |
| Count chip | `bg-primary-container text-white text-[10px] font-label-caps px-3 py-1 rounded-full uppercase tracking-tighter shadow-md` | 12 Products |
| Removable tag | `px-2 py-1 bg-primary/10 text-primary rounded text-xs flex items-center gap-1` + `close` 12px button | Mechanical × |
| Draft chip | `bg-secondary-container text-on-secondary-container px-3 py-1 rounded-full text-xs font-label-caps tracking-tighter` | Draft Mode |
| Discount-on-row | `text-xs font-bold text-primary px-2 py-1 bg-primary/10 rounded-full` / none `text-outline bg-surface-container-high` | adm-products |
| Small value tag | `text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-label-caps` (`-15%`) / error variant | adm-offers |

## 19. Filter Sidebar & Controls

**Shop variant:** `aside w-full md:w-64 flex-shrink-0 space-y-8`. Title `font-headline-md text-headline-md mb-4` + `filter_list` icon. Group: label `font-label-caps text-label-caps text-outline uppercase block mb-4`; options `space-y-3`, each `label.flex.items-center.gap-3.cursor-pointer.group` with 20px checkbox (`w-5 h-5 rounded border-outline-variant text-primary focus:ring-primary`) or radio, text `text-body-md on-surface-variant group-hover:text-on-surface`. Price range: `input[type=range] w-full h-2 bg-surface-container-highest rounded-lg appearance-none accent-primary` + thumb CSS (20px circle `#0d631b`, 2px white border, `0 2px 4px rgba(0,0,0,.2)`); min/max labels mono. Promo box: `p-6 rounded-xl bg-primary-container/10 border border-primary-container/20` (icon, `font-headline-md text-primary` title, body, full-width 2px outline button).
**Marketplace variant:** `lg:w-72 space-y-10`; header row "Filters" + "Reset All" (`text-primary font-label-caps text-[10px] hover:underline`); group label `font-label-caps on-surface-variant border-b border-outline-variant pb-2`; checkboxes default size; license as stacked toggle buttons (`px-4 py-2 rounded-lg border border-outline-variant text-left text-sm`, selected `border-primary bg-primary-container/10 font-bold`, hover `border-primary bg-primary-container/10`); compatibility `select w-full bg-surface-container border-none rounded-lg`; format chips; range.
**MOBILE** sidebar stacks above the grid (`flex-col md:flex-row` / `lg:flex-row`). Recommend collapsing into a "Filters" drawer on mobile.

## 20. Results Toolbar

Shop: `flex flex-col sm:flex-row justify-between items-center bg-white p-4 rounded-xl shadow-sm border border-outline-variant/30 mb-8 gap-4`; left: "**48** results found" + 1px×24px divider (`bg-outline-variant/50`, hidden <sm) + view toggle (`p-2 rounded`; active `bg-primary-container text-white`; inactive `hover:bg-surface-container`) `grid_view` / `list`; right: mono "SORT BY:" label `text-outline` + `select bg-surface-container border-none rounded-lg px-4 py-2`.
Marketplace: plain row `flex justify-between mb-8`: "Showing **1,240** results for …" + "Sort by:" mono 12px + borderless bold select.
Library: white bar `p-4 rounded-xl border shadow-sm flex flex-wrap gap-4`: select chips `px-4 py-2 bg-surface-container rounded-lg border min-w-[200px]` with label "Category:" + borderless `text-primary font-semibold` select; view toggle right (`bg-primary-container text-on-primary-container` active).

## 21. Pagination

| Variant | Spec | Pages |
|---|---|---|
| Circle | `w-10 h-10 rounded-full`; active `bg-primary text-white font-bold`; others `hover:bg-surface-container`; chevrons; ellipsis `px-2` | shop |
| Bordered (canonical) | `w-10 h-10 rounded-lg border border-outline-variant hover:bg-surface-container(-high)`; active `bg-primary text-on-primary font-bold` (no border); prev disabled `disabled:opacity-30|50` | marketplace, order-hist (`font-label-caps`), my-reviews, adm-stl, adm-reviews |
| Compact | `w-8 h-8 rounded|rounded-lg text-xs|[12px] font-bold`; active `bg-primary text-white`; others bordered or borderless hover | offers-hist, adm-products, adm-customers, adm-orders |
| Text-pill | `px-3 py-1 rounded font-label-caps text-sm` | adm-discounts |
| Prev/next only | `p-1.5 rounded-lg border` + "Page 1 of 5" mono 10px | adm-offers |
Table footers: `px-6 py-4 border-t border-outline-variant flex justify-between items-center` (bg `surface-bright` / `surface-container-lowest` / `surface-container-low/50`), left "Showing 1-4 of 24 results" (`text-body-md`/`text-xs`/mono uppercase). Page section spacing `mt-12`/`mt-16 flex justify-center`.

## 22. Breadcrumbs

- STL detail: `nav flex items-center gap-2 mb-8 font-label-caps text-label-caps on-surface-variant`; links `hover:text-primary`; separator `chevron_right` 14px; current `text-on-surface`.
- Edit product (topbar): `ol inline-flex space-x-2 text-sm font-label-caps`; current `text-primary font-bold`.
- Upload product / manage orders: `text-sm text-outline|on-surface-variant font-medium`, separator `chevron_right text-xs`, current `text-primary font-medium|bold`.
- Settings: mono `text-xs` "ADMIN › SETTINGS" above H1, current `text-primary`.
- Wishlist header: single mono eyebrow "Portal / Wishlist" `text-primary text-[10px] tracking-widest`.

## 23. Tabs

STL detail: container `mt-16 border-b border-outline-variant/30`; `flex gap-8`; tab `pb-4 border-b-2 font-label-caps text-label-caps`; active `border-primary text-primary`; inactive `border-transparent text-on-surface-variant hover:text-on-surface`. Labels: DESCRIPTION, REVIEWS (42), PRINT SETTINGS, LICENSE DETAILS. (Only Description panel designed.) Implement with `role="tablist"`.

## 24. Media Gallery

- **Product (bento):** `lg:col-span-7 grid grid-cols-4 gap-4`. Main `col-span-4 aspect-square md:aspect-video rounded-xl shadow-sm bg-surface-container-low cursor-zoom-in` with hover-zoom (JS: `transform-origin` follows cursor, `scale(1.8)`) and "HOVER TO ZOOM" pill (`absolute bottom-4 right-4 bg-surface/80 backdrop-blur-md px-3 py-1 rounded-full mono 10px`). Thumbs `aspect-square rounded-lg border border-outline-variant/30 hover:border-primary`; last thumb "+4" overlay (`brightness-50`, centered `text-on-primary font-bold`).
- **STL detail (viewer):** main `aspect-[4/3] rounded-xl bg-surface-container shadow-sm border-outline-variant/20`; floating control bar `absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-3 glass-panel p-2 rounded-full border-outline-variant/30` of 40px `bg-surface rounded-full shadow-sm` buttons (`3d_rotation`, `zoom_in`, `fullscreen`; hover `bg-primary-container text-on-primary-container`); "VERIFIED DESIGN" pill top-right. Thumbs `grid-cols-5 gap-3`, active `border-2 border-primary`, others `border border-outline-variant/30 hover:border-primary`; "+8" thumb `blur-sm` + `bg-black/40 text-white font-bold`.
- **Admin media manager (edit-product):** `grid-cols-4 gap-4`; tiles `aspect-square rounded-lg overflow-hidden`; primary `border-2 border-primary` + "PRIMARY" tag (`bg-primary text-white text-[10px] font-label-caps rounded top-2 left-2`); hover overlay `bg-on-surface/40` with white round buttons (delete `text-error`, `open_in_full`) or "MAKE PRIMARY" pill; add tile dashed with `add_a_photo`.

## 25. Spec Tile Grid

- Product: `grid grid-cols-2 gap-4`; tile `p-4 rounded-xl border border-outline-variant/30 bg-surface-container-lowest`; label `font-label-caps text-label-caps on-surface-variant mb-1`; value `font-bold on-surface`.
- STL detail: tile `bg-surface-container p-3 rounded-lg border border-outline-variant/10`; label `text-[10px] font-label-caps uppercase mb-1`; value `font-bold`.
- Inline stat strip (stl-detail): `flex justify-center gap-6 pt-4 border-t border-outline-variant/20`; value `text-xl font-bold`, label mono 10px uppercase; 1px×32px dividers `bg-outline-variant/30`.
- Key/value rows (edit-product): `flex justify-between border-b border-outline-variant py-2` label mono / value `font-semibold`.

## 26. Quantity Stepper

- Square (product): `flex items-center border border-outline-variant rounded-lg overflow-hidden`; buttons `p-3 hover:bg-surface-variant` (`remove` / `add`); input `w-16 text-center border-none font-bold bg-transparent`. Min 1.
- Pill (cart): `flex items-center bg-surface-container-high rounded-full px-2 py-1 border border-outline-variant/20`; buttons `w-8 h-8 hover:text-primary` (icon `text-lg`); value `w-10 text-center font-label-caps`.
- Digital items: replaced by "Fixed Quantity" mono `text-xs opacity-50`.

## 27. Form Fields

**Label (canonical):** `font-label-caps text-label-caps text-on-surface-variant uppercase block mb-2` (12px mono 600 0.05em). Variants: `text-outline` (upload-product, profile `text-[11px]`), `ml-1` (login), with leading 14px icon `flex items-center gap-2` (admin-login), optional hint `text-on-surface-variant/50 text-[10px]` "(Optional)", counters right-aligned `text-[10px] text-outline` "45/60".

**Text input (canonical):** `w-full px-4 py-3 bg-surface-container-lowest|white border border-outline-variant rounded-lg font-body-md text-on-surface placeholder:text-outline-variant|outline focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-all` → 48px tall.

| Variant | Spec | Pages |
|---|---|---|
| Large | `p-4` (56px) `bg-white` | checkout |
| Fixed height | `h-12 px-4 bg-surface-container-lowest` | register |
| Tinted | `bg-surface-container-low` (contact, admin-login `py-4`, settings), `bg-surface-bright` (login), `bg-surface` (upload-stl `p-3`) | |
| Leading icon | wrapper `relative group`; icon `absolute left-3 top-1/2 -translate-y-1/2 text-outline-variant group-focus-within:text-primary`; input `pl-11` | login, forgot (`pl-12`, icon `left-4 text-outline`) |
| Trailing action | password visibility button `absolute right-3|4 top-1/2 -translate-y-1/2 text-outline-variant hover:text-on-surface` (`visibility` ↔ `visibility_off`) | login, admin-login |
| Trailing icon | `lock` in card number (`right-4 text-outline`) | checkout |
| Prefix | `$` `absolute left-4` + input `pl-8` | upload-stl |
| Underline | `w-full border-b border-outline-variant py-2|3 focus:border-primary focus:ring-0` (no box); big value `text-2xl font-bold` for price | edit-product |
| Read-only display | `p.font-body-md border-b border-outline-variant pb-2` | profile |
| Key/value pair input | `w-1/3 bg-surface-container-low readonly text-outline` + `w-2/3 bg-surface-container-lowest` | upload-product |
| Split time | two `w-20 text-center` inputs with ":" | upload-stl |

**Select:** same box + `appearance-none` and either native arrow (forms plugin chevron, visible in screenshots) or custom `expand_more` icon `absolute right-3 top-1/2 pointer-events-none` with `pr-10`. Borderless inline select: `bg-transparent border-none font-bold focus:ring-0` (sort, settings prefs).
**Textarea:** same box, `rows=5|6` or `h-24|h-48`, `resize-none` in admin.
**Date input:** native `type=date` boxed `px-4 py-3` (order-hist).
**Error state:** **not designed** in any page. Recommend `border-error ring-2 ring-error/20` + helper `text-xs text-error mt-1` with `error` icon.
**Disabled:** not designed → `opacity-50 cursor-not-allowed bg-surface-container-low`.
**Field spacing:** `space-y-6` between fields; 2-col rows `grid grid-cols-1 md:grid-cols-2 gap-4|6`.

## 28. Checkbox, Radio, Radio Card

- Checkbox (forms plugin): `w-5 h-5` (or default 16px `w-4 h-4`) `rounded border-outline-variant text-primary focus:ring-primary(/20)`; checked = solid primary with white check (visible in checkout screenshot). Label `gap-3 text-on-surface-variant group-hover:text-on-surface`.
- Radio: `w-5 h-5 border-outline-variant text-primary focus:ring-primary`.
- Radio card (upload-stl license): `label.flex.items-center.gap-3.p-3.rounded-lg.border.border-outline-variant.cursor-pointer.hover:bg-surface-container-low`; selected `border-primary bg-primary/5`; content title `text-sm font-semibold` + desc `text-xs`.
- Toggle-button group (marketplace license): see §19.
- Scrollable checklist: `border border-outline-variant rounded-lg p-3 bg-surface max-h-40 overflow-y-auto custom-scrollbar` with `space-y-2` checkbox rows `text-sm` (upload-stl compatible printers).

## 29. Toggle Switch & Segmented Control

**Toggle (canonical):** `label.relative.inline-flex.items-center.cursor-pointer > input.sr-only.peer + div.w-11.h-6.bg-outline-variant|surface-variant|surface-container-highest.rounded-full.peer-checked:bg-primary` with `after:` knob `after:absolute after:top-[2px] after:left-[2px] after:h-5 after:w-5 after:rounded-full after:bg-white after:border after:border-gray-300 after:transition-all peer-checked:after:translate-x-full peer-checked:after:border-white`. Track 44×24, knob 20px. Compact variant 40×20 / 16px knob (adm-products). Button variant (discounts): `w-12 h-6 bg-primary rounded-full p-1 flex items-center` + `w-4 h-4 bg-white rounded-full shadow-sm`; on = `justify-end`, off = `bg-outline justify-start`.
Toggle row: `flex items-center justify-between py-2 border-b border-outline-variant` (title `font-headline-md text-body-md` / `font-semibold` + desc `text-xs on-surface-variant`; warning desc `text-error font-medium`). Card-row variant: `p-4 bg-surface rounded-lg`.
**Segmented control:** `flex bg-surface-container p-1 rounded-full`; active `px-3 py-1 bg-white text-primary rounded-full shadow-sm text-xs font-bold`, inactive `text-on-surface-variant`. Two-button group (2FA): `flex gap-2`, buttons `flex-1 py-2 rounded-lg text-xs font-bold`, active `bg-primary-container text-on-primary-container`, inactive `bg-surface-container on-surface-variant`. Chart period toggle: `text-[11px] font-label-caps px-3 py-1 rounded-md` active `bg-primary text-white` / inactive `bg-surface-container-high`.

## 30. Dropzone & File Upload Row

Dropzone: `border-2 border-dashed border-outline-variant rounded-xl|2xl p-10 flex flex-col items-center justify-center text-center bg-surface-container-low/50 hover:bg-primary/5 (or hover:border-primary) transition cursor-pointer group`; icon circle `w-16 h-16 rounded-full bg-primary/10` with `upload_file` `text-primary text-3xl` (`group-hover:scale-110`); title `font-bold text-lg` / `text-body-lg font-bold`; helper `text-sm on-surface-variant` with inline "browse files" `text-primary font-bold underline`; limit mono `text-xs opacity-60` "MAX FILE SIZE: 250MB". Drag-over (JS) adds highlight classes.
Upload row: `w-full max-w-sm bg-white border border-outline-variant rounded-lg p-3 flex items-center gap-3` → `description` icon primary → filename `text-xs font-bold truncate` + progress `h-1 bg-surface-container-high rounded-full` fill `bg-primary` → `close` `text-error text-sm`.
Compact logo dropzone (settings): `p-6 rounded-xl`, icon `text-4xl text-outline-variant group-hover:text-primary`.
Thumbnail picker: `w-48 h-48 rounded-xl border overflow-hidden` + hover `bg-black/40` "CHANGE PHOTO" mono white.

## 31. Rich-text Toolbar

`border border-outline-variant rounded-lg overflow-hidden` → toolbar `bg-surface-container-low p-2 border-b border-outline-variant flex gap-2|4` of `p-1 rounded hover:bg-white|surface-container-high` buttons (`format_bold`, `format_italic`, `format_list_bulleted`|`list`, `link` — link pushed right with `ml-auto` in edit-product), icon 14–18px → `textarea w-full p-4 border-none focus:ring-0 resize-none` `rows=6`/`h-48`. Pages: edit-product, upload-product, upload-stl.

## 32. Tag Input

Upload-product "TAGS": chip list `flex flex-wrap gap-2 mb-3` (see removable tag §18) + input `w-full p-2 pr-10 rounded-lg border text-sm` with `add` button `absolute right-2 top-2 text-outline hover:text-primary`.

## 33. Checkout Step Header

`flex items-center gap-4 mb-8` → 32px circle (`w-8 h-8 rounded-full flex items-center justify-center font-label-caps`): current `bg-primary text-on-primary`; upcoming `border-2 border-primary text-primary` → `h2 font-headline-lg text-headline-lg` (32px). Steps: 1 Shipping Information · 2 Billing Details · 3 Payment Method. Sections spaced `space-y-12`. (Completed state not designed — recommend filled primary with `check` icon.)

## 34. Payment Option Card

Selected: `border-2 border-primary bg-primary-fixed/5 rounded-xl p-6` → header `flex justify-between mb-6`: `credit_card` primary + "Credit Card" `font-headline-md text-headline-md`; right brand icons `opacity-50` → nested card fields grid `grid-cols-2 gap-4`. Unselected: `border border-outline-variant rounded-xl p-6 flex justify-between items-center hover:border-primary cursor-pointer` with icon + label `text-on-surface-variant` + `open_in_new` `text-outline`. Implement as radio group.

## 35. Order Summary Card

- Cart: `aside lg:col-span-4`; card `bg-surface-container-low rounded-2xl p-8 border border-outline-variant/20 sticky top-24`; title (font-headline-lg, renders 16px); breakdown `space-y-4 mb-8` rows `flex justify-between on-surface-variant`; total block `pt-4 border-t border-outline-variant/30` (mono "TOTAL DUE" + `text-headline-lg font-bold`); coupon: mono 10px label, `flex gap-2` input (`bg-surface border-outline-variant rounded-lg px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary`) + inverse "Apply" button (`px-6 py-3 rounded-lg font-label-caps text-xs`) — **add `min-w-0` to input to fix overflow**; CTA (Large Hanken CTA §8); payment icons row `mt-6 gap-4 opacity-50 grayscale` (`credit_card`, `account_balance_wallet`, `payments` 24px).
- Checkout: `bg-white border border-outline-variant rounded-2xl p-8 shadow-sm`, `sticky top-24`; title `font-headline-lg text-headline-lg mb-8`; items `space-y-6 mb-8` (80px thumb `rounded-lg bg-surface-container`, title `font-headline-md text-headline-md`, price mono `text-primary`, meta `text-sm`); calcs `border-t border-outline-variant pt-6 space-y-3` (values mono); total row `font-headline-lg` + `font-display text-headline-lg text-primary`; CTA `w-full mt-8 bg-primary py-5 rounded-xl font-label-caps uppercase tracking-widest shadow-lg hover:bg-primary-container hover:shadow-primary/20` + arrow; legal note `text-xs text-center mt-6 px-4` with underlined links.

## 36. Cart Line Item

`bg-surface-container-lowest border border-outline-variant/30 rounded-xl p-6 flex flex-col md:flex-row gap-6 items-center` + `.bento-card` shadow/hover. Image `w-full md:w-32 h-32 rounded-lg bg-surface-container-low` (digital: download badge `absolute bottom-1 right-1 bg-primary/90 text-white rounded px-1.5 py-0.5` filled `file_download`). Middle `flex-grow text-center md:text-left`: type eyebrow mono 10px `tracking-widest uppercase` (`text-secondary` "Physical Material" / `text-primary` "Digital Asset (STL)"), title `font-headline-md`, meta `text-sm mt-1` "1.75mm • 1kg Spool • Industrial Grade", Remove button `mt-4 text-sm font-medium on-surface-variant hover:text-error` + `delete` 18px. Right `flex flex-col items-center md:items-end gap-4`: stepper (§26) + price `font-headline-md`. List `space-y-4`.

## 37. Trust Badge Tile

Checkout: `grid grid-cols-3 gap-4`; tile `bg-white/50 border border-outline-variant rounded-xl p-4 flex flex-col items-center text-center gap-2`; filled icon `text-primary` (`verified_user`, `encrypted`, `workspace_premium`); label mono 10px uppercase. Variants: marketplace hero inline trust row (§9); admin-login trust pills `bg-white/50 px-4 py-2 rounded-lg border border-outline-variant/30` (icon `text-sm` + mono label); login status bar `mt-8 flex justify-center gap-6 opacity-60` (8px `bg-secondary-container` dot + "SERVERS ONLINE", `verified_user` 14px + "AES-256 ENCRYPTED", mono 10px).

## 38. Auth Card

| Variant | Spec | Page |
|---|---|---|
| Login | `main w-full max-w-[440px]`; card `bg-surface-container-lowest rounded-2xl shadow-xl border border-outline-variant/30 overflow-hidden hover:shadow-2xl duration-300`; header `pt-10 pb-6 px-8 text-center` (split wordmark mb-4, H1 "Welcome Back" `font-headline-md text-headline-md mb-2`, subtitle body-md muted); form `px-8 pb-10 space-y-6`; actions row (remember-me checkbox 16px + "Forgot Password?" `text-primary font-medium hover:underline underline-offset-4`); gradient submit `py-4 rounded-lg shadow-lg shadow-primary/20 tracking-widest font-bold`; divider; 2-col social buttons; footer strip `bg-surface-container-high/50 px-8 py-5 text-center border-t border-outline-variant/30` "New to the platform? **Create Account**". Page bg SVG dot pattern; decorative schematic images fixed right (w-1/3, `opacity-[0.03]`) and left (`opacity-[0.02]`), hidden <lg. | login |
| Register | `max-w-[640px] glass-panel(0.85) border-outline-variant/30 rounded-xl shadow-[0_32px_64px_-16px_rgba(0,0,0,0.08)]` hover `0 40px 80px -20px rgba(13,99,27,.1)`; header `pt-10 pb-6 px-8 md:px-12 text-center border-b border-outline-variant/20` (icon+wordmark, mono caps "DIGITAL PRECISION HUB" `tracking-widest`, H2 headline-lg mt-6, desc `max-w-sm`); form `p-8 md:p-12 space-y-6` with 2-col rows; terms checkbox row; submit solid `h-14 bg-primary tracking-widest shadow-lg shadow-primary/20 hover:bg-secondary`; login link; decorative footer strip `h-24 bg-surface-container-high/30` with 5 icons `text-6xl opacity-10`. | register |
| Forgot | fixed logo top-left (`top-8`, 32px extrabold primary, centered <md); two rotating ring outlines (800/600px, `border-outline-variant/40|30`, 60s/45s spin) at 30% opacity; card `glass-panel max-w-md p-8 md:p-12 rounded-xl shadow-2xl border-outline-variant/20 flex flex-col gap-8` with glass shine (`-top-1/2 -right-1/2 bg-gradient-to-br from-white/20 rotate-45`); H1 `font-display text-headline-lg`; email field with leading icon in bordered wrapper (`.input-focus-effect:focus-within` primary border + glow); gradient submit with arrow that nudges right on hover; "BACK TO LOGIN" link `font-label-caps text-primary` + `keyboard_backspace`; side image card (xl only) fixed `bottom-12 right-12 w-64 h-64` grayscale; fixed footer copyright mono 11px. | forgot |
| Admin split | `main max-w-[1100px] flex flex-col md:flex-row glass-panel(0.9, border #bfcaba) rounded-xl overflow-hidden shadow-xl`. Left `md:w-1/2 bg-surface-container-low p-12 border-r border-outline-variant` (hidden <md): 96px circle `bg-primary/10 border-primary/20` with filled `verified_user` 48px, H2 "Engineering Integrity" headline-lg, desc, trust pills, node label `absolute bottom-6 left-6 mono 10px text-primary/40`. Right `md:w-1/2 p-8 md:p-16 bg-white`: tile logo, H1 "Admin Access", form (inputs `bg-surface-container-low px-4 py-4`, labels with icons, Forgot link mono primary right), submit `bg-primary-container py-5 rounded-lg tracking-widest` + `login` icon, hover `btn-hover-effect` (lift -1px + green shadow); footer indicators (`glow-dot` + "Secure Encrypted Connection", version). Bg: green blueprint grid + 2 blurred orbs. | admin-login |

## 39. Divider with Label & Social Login Button

Divider: `relative flex items-center py-4` → `flex-grow border-t border-outline-variant/30` · label `mx-4 font-label-caps text-[10px] text-outline-variant uppercase` "Or continue with" · line.
Social button: `flex items-center justify-center gap-2 py-3 border border-outline-variant rounded-lg hover:bg-surface-container active:scale-[0.97] group`; 20px brand SVG (`group-hover:scale-110`); label `font-body-md font-medium`. Google & Facebook.

## 40. App Sidebar (Account & Admin)

**PURPOSE** Persistent left navigation for account and admin areas.

**STRUCTURE**
```
aside (fixed left-0 top-0 h-screen w-64 z-40|50, flex flex-col, bg-surface, border-r border-outline-variant, py-8 px-6)
├─ brand block (mb-10|12): wordmark + mono caption   [admin: optional tile icon]
├─ [primary CTA: "New Print Job" full-width bg-primary-container py-3 rounded-lg|xl font-label-caps]
├─ nav (flex-1 space-y-1|2, overflow-y-auto custom-scrollbar)
│   ├─ [group label: pt-4 pb-2 px-3|4 mono 10–11px uppercase tracking-wider|[0.2em] text-outline | on-surface-variant/50]
│   └─ item: a.flex.items-center.gap-3.px-4.py-3.rounded-lg  (icon 24px + label Inter 16px)
├─ bottom section (mt-auto pt-6 border-t border-outline-variant space-y-1): Settings / Help / Logout (text-error hover:bg-error-container/10)
└─ [user chip: flex gap-3 p-3 bg-surface-container-low rounded-xl — 40px avatar + name text-sm font-bold truncate + role text-xs|10px]
```

**DIMENSIONS** 256px wide; items 48px tall (`py-3` + 24px icon); icon–label gap 12px.

**COLORS** Item `text-on-surface-variant`, hover `bg-surface-container-high` (+ `hover:text-primary` on some). Active (canonical): `text-primary font-bold bg-surface-container-low border-r-4 border-primary` + filled icon.

**VARIANTS**
- Account dashboard: `bg-surface-container-lowest border-outline-variant/30`, items `rounded-xl` with 20px icons, active `.sidebar-active` (135° `#0d631b→#1b6d24`, white text — pill), user chip with initials circle `bg-primary text-white` + "INDUSTRIAL TIER" mono primary; `hidden md:flex` + mobile bottom nav.
- Admin console: `bg-surface-container-low`, `px-3 py-2.5` items with 22px icons, active `bg-primary-container text-on-primary-container font-semibold` pill; group headers "INVENTORY", "SALES & CRM"; user chip "JD" `bg-primary-fixed text-on-primary-fixed`.
- Analytics / customers / discounts: "Bekaa3D Admin" + "Precision Control", "New Print Job" CTA, help/logout footer (mono 11px in customers).
- Orders / reviews / offers / settings (admin): items `px-6 py-3` no radius (full-bleed), active right border, "New Print Job" CTA bottom, "Admin Profile" link.
- Customer account (orders-hist, offers-hist, my-reviews, wishlist, stl-library, profile): items Profile · Orders · STL Downloads · Wishlist · Reviews · Offers · Account Settings · Logout.
- Admin dashboard (canonical admin list): Dashboard · Physical Products · STL Files · Categories · Orders · Customers · Reviews · Offers · Discounts · Analytics | Settings · Logout. Collapsible to 80px via header `menu_open` button (labels hidden).

**MOBILE** `hidden md:flex` on account pages (bottom nav replaces it). **Admin pages have no responsive behavior** (sidebar always visible, main `ml-64`).

**Recommended canonical** see DESIGN-SYSTEM §12.14.

## 41. App Top Bar

`header sticky top-0 z-30|40 h-16 flex justify-between items-center px-8|12 bg-white/80 (or bg-surface/80, glass-panel) backdrop-blur-xl border-b border-outline-variant`. Left: [sidebar toggle `menu_open` in 40px round button] · search (max-w-md) · or page title (`font-headline-md`, `font-display text-headline-md font-extrabold text-primary` "Physical Products", "Categories" headline-lg primary + divider + "Management Portal") · or breadcrumb. Right `gap-4|6`: notification button + dot, help, [print, mail, settings], vertical divider `h-8 w-px bg-outline-variant mx-2`, profile cluster (`text-right`: name `text-label-caps font-bold`/`text-sm font-bold` + role `text-[10–11px]` mono/Inter; avatar 40px round with `border-2 border-primary-container p-0.5` ring or `ring-2 ring-primary/20 hover:ring-primary`).
Variants: fixed `left-64 right-0 h-16` (adm-orders/reviews/offers/settings); account pages `px-8 py-4` with search left + notifications/help/avatar right; acct-dash `h-20 px-8` with greeting H1 ("Welcome back, Dr. Elena Vance" headline-md + `text-[14px]` subline) and pill CTA "NEW PROJECT" (`bg-primary px-5 py-2.5 rounded-full`); upload-stl header with title + "Draft Mode" chip + SAVE DRAFT / PUBLISH buttons (`rounded` 4px).

## 42. KPI / Stat Card

| Variant | Spec | Pages |
|---|---|---|
| Icon-top with trend | `p-5|6 rounded-xl` (glass or white bordered) → row `flex justify-between items-start mb-4`: icon tile `w-10 h-10 rounded-lg bg-primary-container/10 text-primary` (or `p-2 bg-primary/10 rounded-lg`) + trend chip → label mono 11px uppercase `tracking-wider mb-1` → value `font-display text-headline-md` (20px) / `font-headline-lg text-[24px] tracking-tight`; hover `shadow-lg`/`shadow-md`; group-hover icon tile fills (`bg-primary text-on-primary`) | admin-dash (6-up `xl:grid-cols-6`), admin-console (5-up) |
| Label-top | `p-6 rounded-2xl border card-shadow` → mono label `mb-1` → `flex items-baseline gap-2` value `font-display text-headline-lg` (32px) + delta `text-sm text-primary` | acct-dash |
| Brand highlight | `bg-primary text-on-primary p-6 rounded-2xl shadow-xl shadow-primary/20 relative overflow-hidden` + watermark icon `absolute -bottom-4 -right-4 text-[120px] opacity-10` | acct-dash "ACCOUNT TIER", adm-reviews "Pending Moderation" (`bg-primary-container`) |
| Value + icon right | `bg-white p-6 rounded-xl shadow-[0px_4px_24px_rgba(0,0,0,.04)] border-outline-variant/30 flex justify-between items-center hover:border-primary/50` → label mono + value `font-display text-4xl font-bold text-primary|secondary|tertiary`; 48px circle icon `bg-*/5` | offers-hist |
| Icon-left | `bg-white p-6 rounded-xl border shadow-sm flex items-center gap-4` → 48px icon tile (`rounded-lg bg-primary-container text-primary` / `rounded-full bg-primary/10`) → label + value `text-headline-md font-display` / `text-2xl font-display font-bold` | my-reviews, adm-products |
| Display-number | `glass-panel p-6 rounded-2xl border shadow-sm flex flex-col gap-2` → mono 10px label → `flex items-end justify-between`: value `font-display text-display text-4xl` (renders 48px) + chip/pulse dot/trend icon | adm-customers |
| Square (analytics) | `bg-surface-container-lowest p-6 border border-outline-variant rounded-none shadow-sm hover:border-primary` → icon `p-2 rounded` + chip → `mt-4` label `text-sm font-label-caps` + value `font-headline-lg` (renders 16px Hanken — §12.3) | analytics |
| Simple | `bg-white p-6 rounded-xl border hover:border-primary` → icon `p-2 rounded-lg bg-primary-fixed` → label mono 12px → value `font-headline-lg text-headline-lg mt-1` | adm-stl |
| Plain number | `bg-surface-container-lowest p-6 rounded-xl border shadow-sm hover:shadow-md` → icon + right label `text-xs font-label-caps text-secondary font-bold` → label `text-sm font-medium uppercase tracking-wider` → value `text-3xl font-bold` | adm-orders |
| Progress KPI | label + bar (`h-2 bg-surface-container-high rounded-full` fill `bg-secondary w-[94%]`) + `font-headline-md` "94% Satisfaction" | adm-reviews |
**Recommended canonical:** Icon-top with trend, white card `rounded-xl border border-outline-variant/30 shadow-sm p-6`, value Hanken 32px/700.

## 43. Data Table

**STRUCTURE** wrapper `bg-white|surface-container-lowest|glass-panel rounded-xl|2xl border border-outline-variant (/30) overflow-hidden shadow-sm` → optional header bar `px-6|8 py-4|6 border-b flex justify-between` (title `font-headline-md` + link) / filter bar → `div.overflow-x-auto > table.w-full.text-left.border-collapse` → footer pagination.

| Part | Spec |
|---|---|
| thead row | `bg-surface-container-low` (+ `border-b border-outline-variant`) |
| th | `px-6 py-4 font-label-caps text-label-caps|text-[11px]|text-xs text-on-surface-variant|text-outline uppercase tracking-wider|widest`; numeric/action columns `text-right`/`text-center`; checkbox column `w-12` |
| tbody | `divide-y divide-outline-variant` (admin) / `divide-outline-variant/20–30` (soft) |
| tr | `hover:bg-surface-container-low/50` · `hover:bg-primary/5` (admin products/discounts) · `hover:bg-surface-bright` · `hover:bg-surface-container/30`, `transition-colors`, `group` |
| td | `px-6 py-4` (or `py-5` account tables, `p-4` discounts, `py-4 px-4` adm-stl) |
| Cell: ID | mono `text-primary` (+ `font-bold`), or `font-mono text-[13px] text-primary` |
| Cell: entity | `flex items-center gap-3|4` → 40–64px thumb `rounded|rounded-lg bg-surface-container border overflow-hidden` or avatar → title `font-bold`/`font-semibold text-sm` + sub `text-[10–12px]` (SKU mono) |
| Cell: status | badge (§18) |
| Cell: payment | dot `w-2 h-2 rounded-full bg-primary|amber-500|outline` + label, or icon `check_circle` filled 14px `text-secondary` + "Paid" |
| Cell: money | `font-bold` or mono bold, right-aligned in some |
| Cell: actions | `flex justify-end gap-2` icon buttons; **hover-reveal** `opacity-0 group-hover:opacity-100` (adm-products, adm-customers); solid "VIEW DETAILS" (order-hist); pill buttons "Accept Counter"/"View Receipt"/"Withdraw"/"Locked" (offers-hist); accept/reject/COUNTER (adm-offers) |
| Cell: toggle | switch (§29) |
| Row states | disabled/expired `opacity-75 grayscale` (discounts), `opacity-60` |
| Bulk | header checkbox; footer "Bulk Delete" (error outline) / "Export CSV" / "Bulk Actions" select + APPLY |

**MOBILE** `overflow-x-auto` horizontal scroll only; no card-list fallback designed. Recommend horizontal scroll with sticky first column or a stacked card layout <md.

## 44. Charts

- **CSS bar chart (admin-dash):** `h-64 flex items-end justify-between gap-1`; bars `flex-1 bg-primary/10 rounded-t-sm h-[40–95%] hover:bg-primary duration-300` with tooltip (`absolute -top-8 bg-inverse-surface text-inverse-on-surface text-[10px] px-2 py-1 rounded opacity-0 group-hover/bar:opacity-100`); legend `mt-4 pt-4 border-t flex gap-6` (12px dots, mono 12px). Period toggle (§29).
- **Admin console bars:** background `bg-surface-variant/30 rounded-lg`, bars `bg-primary/20 hover:bg-primary/40`, last bar `bg-primary`; axis labels `absolute -bottom-6 font-label-caps text-[9px] on-surface-variant/40 uppercase tracking-widest`.
- **Conic donut (admin-dash):** 192px circle `conic-gradient(#0d631b 0% 65%, #b9f474 65% 100%)`, inner 144px white circle `shadow-inner` with "100%" `text-headline-md font-display` + "TOTAL REACH" mono 10px; legend rows `flex justify-between` (8px dot + label / `font-bold` %).
- **Progress-bar mix (admin-console):** rows `space-y-2`: label + `font-semibold` % / bar `h-2 bg-surface-container-high rounded-full` fill `bg-primary|secondary|tertiary-container`; insight box `p-4 bg-surface-container-low rounded-lg border` `text-xs` with bold primary "Insight:".
- **Chart.js (analytics, chart.js from jsDelivr):**
  - Revenue line: `type:'line'`, 12 monthly points; dataset 1 `borderColor:#0d631b`, `backgroundColor:rgba(13,99,27,0.1)`, `fill:true`, `tension:0.4`, `borderWidth:3`, `pointRadius:0`; dataset 2 "Projected" `borderColor:rgba(13,99,27,0.2)`, `borderDash:[5,5]`, `borderWidth:2`, no fill; legend hidden; y-axis hidden; x grid hidden; container `h-80`.
  - Category doughnut: `cutout:'75%'`, colours `#0d631b #3e6a00 #923357`, `borderWidth:0`, `hoverOffset:10`; container `h-64`; custom legend with 12px `rounded-sm` swatches.
  - Sales bar: 12 weekly bars `#0d631b`, `borderRadius:4`; y hidden; container `h-48`.

## 45. Activity Feed / Timeline

Admin-dash "System Logs": card header `px-6 py-6 border-b` (title + mono 11px "REAL-TIME UPDATES"); list `p-6 space-y-6 max-h-[500px] overflow-y-auto custom-scrollbar`; item `flex gap-4 relative` → 32px icon circle (`bg-primary-container/10 text-primary` / `bg-error-container/10 text-error` / `bg-secondary-container/20 text-secondary` / `bg-outline-variant/30`) 18px icon → connector `absolute left-4 top-8 bottom-[-24px] w-0.5 bg-outline-variant/30` → text `text-body-md leading-snug` with bold spans + mono 10px timestamp.
Account "Recent File Access": rows `flex items-center gap-4 p-3 rounded-xl hover:bg-surface-container-low` → 40px `rounded-lg bg-surface-container-high` `history` icon primary → filename `text-sm font-semibold` + meta `text-[12px]`.
Licensing list: rows `p-4 rounded-xl` (highlight `bg-primary/5 border-primary/20`; default `border-outline-variant/30`; expired `opacity-60` + `lock` icon) with right status (`70% READY` mono white pill / "VIEW OFFER" tonal button).

## 46. Notification Dropdown Panel

Admin console: `absolute top-16 right-8 w-80 bg-surface-container-lowest border border-outline-variant/30 rounded-xl shadow-2xl z-50`; hidden `opacity-0 translate-y-4 pointer-events-none` → visible (300ms). Header `p-4 border-b` "System Alerts" `font-bold text-sm` + "3 New" `bg-error text-on-error text-[10px] rounded-full px-1.5`. Items `p-4 hover:bg-surface-container-low border-b border-outline-variant/10`: title `text-xs font-bold` (`text-primary` / `text-error` / `text-on-surface`), body `text-[11px] on-surface-variant/80`, time `text-[9px] on-surface-variant/40 mt-2`. Footer `p-3 bg-surface-container-low rounded-b-xl` "Mark all as read" `text-primary text-[11px] font-bold uppercase tracking-wider`. Closes on outside click.

## 47. Toast

Settings: `fixed bottom-8 right-8 bg-inverse-surface text-inverse-on-surface px-6 py-4 rounded-xl shadow-2xl flex items-center gap-4 z-50`; hidden `translate-y-24` → shown 300ms; auto-hide 4s. Content: filled `check_circle` `text-primary-fixed` · title `font-bold text-sm` "Changes synchronized" + body `text-xs opacity-80` · close button `ml-4 text-sm`. Error/warning variants not designed (recommend `error` icon in `text-error-container`). Use `role="status" aria-live="polite"`.
Floating status pill (upload-stl): `fixed bottom-8 right-8 glass-panel border px-4 py-2 rounded-full shadow-lg animate-bounce` with pulsing dot + mono `text-xs text-primary` "System Ready for Processing".

## 48. Modal / Success Overlay

Register: `fixed inset-0 z-50 bg-background/80 backdrop-blur-md flex items-center justify-center p-6`, hidden `opacity-0 pointer-events-none` → `opacity-100` (300ms). Card `max-w-md bg-surface-container-lowest rounded-xl shadow-2xl p-12 text-center border border-primary/20` → 80px circle `bg-secondary-container text-on-secondary-container` with `verified` `text-4xl` → `font-headline-lg text-headline-lg text-primary mb-2` "Request Received" → body. (No generic dialog with actions exists; confirm dialogs use native `confirm()` in edit-product JS → replace with an accessible dialog using this card style + Primary/Neutral buttons.)

## 49. Empty State

Wishlist/library (hidden by default): `flex flex-col items-center justify-center py-24|32 text-center` → 96px circle `bg-surface-container` with icon (`favorite text-primary text-[48px]` / `search_off text-display text-outline-variant`) `mb-6` → title `font-display text-headline-md` / `font-headline-md` → desc `on-surface-variant max-w-sm mb-8` → CTA ("Explore Catalog" primary `px-8 py-4 rounded-lg font-label-caps text-sm`, or "Clear all filters" text link mono primary). Categories "Create New Category" dashed tile (§57) doubles as add/empty affordance.

## 50. Loading State

Only JS-simulated: admin login submit → spinner SVG `animate-spin h-5 w-5 text-white` in button; contact → `sync` icon `animate-spin` + "Sending...", disabled. **No skeletons designed.** Recommend skeleton blocks `bg-surface-container-low animate-pulse rounded-*` matching card/image shapes, and button spinner as above.

## 51. FAQ Accordion

`details.faq-item.group bg-surface-container-lowest border border-outline-variant/30 rounded-xl duration-300` → `summary.flex.justify-between.items-center.p-6.cursor-pointer.list-none` (question `font-headline-md` (renders 16px Hanken) `pr-4` + `expand_more` `text-primary` rotating 180° when open, 300ms) → answer `px-6 pb-6 pt-4 border-t border-outline-variant/10 font-body-md leading-relaxed on-surface-variant`. Stack `max-w-3xl mx-auto space-y-4`.

## 52. Promo Banner & CTA Panel

- **Dark promo (home):** section `max-w mx-auto px-64 mb-24` → `relative rounded-3xl overflow-hidden bg-[#141b2b] py-20 px-12 text-center md:text-left` → grid `md:grid-cols-2 gap-12 items-center`: H2 `text-white font-display text-display leading-tight` "30% OFF" + line 2 `text-secondary-fixed`; body `text-white/70 font-body-lg max-w-md mb-8`; lime CTA; right image `w-[400px] drop-shadow-[0_20px_50px_rgba(163,246,156,0.3)]` (hidden <md).
- **Green CTA (home):** `bg-primary text-on-primary rounded-3xl p-16 relative overflow-hidden text-center` + radial white/10 glow top-right; H2 display; body `text-primary-fixed font-body-lg max-w-2xl opacity-90 mb-10`; buttons: white "REQUEST A QUOTE" (`description` icon), WhatsApp, ghost "CONTACT US" (all `rounded-xl px-8 py-4`).
- **About CTA:** `bg-primary-container rounded-[2rem] p-12 md:p-24 text-center text-white` + dot pattern 10%; H2 display `mb-8`; body `text-on-primary-container max-w-2xl mb-12`; pill buttons white + ghost `rounded-full px-10 py-5`.
- **Image promo cards:** order-hist "Precision Guaranteed" (`h-64 rounded-xl`, image zoom, `from-black/80 via-black/20` scrim, white title + body bottom-left); product case study (`h-80 rounded-2xl`, `from-inverse-surface/80`); discounts banner preview (`h-48 rounded-2xl shadow-xl`, `from-primary/90 to-transparent`, "LIVE NOW" lime chip, H4 `font-display text-headline-lg text-white`, mono code line `text-lg tracking-widest`, glass action buttons `bg-white/20 backdrop-blur-md p-2 rounded-lg`).

## 53. Stats Band

About: `section py-16 bg-primary-container text-on-primary-container` → `grid grid-cols-2 md:grid-cols-4 gap-12 text-center` → value `font-display text-[40px] mb-1` + label mono 10px `tracking-widest opacity-80 uppercase`. Home hero mini-stats (§9).

## 54. Mobile Bottom Navigation

`nav.md:hidden.fixed.bottom-0.left-0.w-full.z-50` `bg-surface-container-lowest`/`bg-white/90 backdrop-blur-lg|md` `border-t border-outline-variant(/30)` `flex justify-around|between py-3 px-2|6`. Items `flex flex-col items-center gap-1`: 24px icon + `text-[10px] font-label-caps` (uppercase in profile). Active `text-primary` (+ filled icon, `font-bold`); inactive `text-on-surface-variant`/`text-outline`. Sets: acct-dash (Home/Orders/Files/Profile), wishlist (Home/Search/Wishlist/Cart/Account), profile (Profile/Orders/STL/Settings). Add bottom padding to page content (≥64px) to avoid overlap (not done in source).

## 55. Admin FAB

`fixed bottom-8|10 right-8|10 w-14 h-14 bg-primary text-white|on-primary rounded-full shadow-2xl|xl flex items-center justify-center hover:scale-110 active:scale-95 group z-50` with filled `add` (24–28px). Tooltip on hover (admin-dash): `absolute right-full mr-4 bg-inverse-surface text-inverse-on-surface px-3 py-1.5 rounded text-[11px] font-label-caps` "QUICK ACTION". Pages: admin-dash, adm-offers.

## 56. Callout / Info Box

- Secure info (stl-detail): `bg-surface-container-high p-4 rounded-xl border border-primary/20 flex items-start gap-4`; `verified_user` primary `mt-1`; title `font-bold text-sm`; body `text-xs leading-relaxed mt-1`.
- Pro tip (upload-product): `bg-primary/5 p-6 rounded-xl border border-primary/20`; header `flex gap-3 text-primary mb-2` (`lightbulb` + "Pro Tip" bold); body `text-sm leading-relaxed`.
- Help strip (offers-hist): `mt-12 flex justify-between items-center p-8 bg-surface-container rounded-xl border-outline-variant/30` → 40px `bg-primary/10` `help` circle + title/desc → white outlined button.
- Custom quote box (shop sidebar) §19; Live Factory Feed card (order-hist): `glass-panel border border-primary p-6 rounded-xl` with 48px `bg-primary-fixed` icon tile + 2px outline CTA.

## 57. Admin Category Card

`bg-white rounded-xl border border-outline-variant overflow-hidden flex flex-col custom-shadow group hover:border-primary duration-300` → image `h-48` zoom 105 + count chip top-left + drag handle top-right (`p-1.5 bg-white/90 backdrop-blur rounded-lg shadow-sm drag_indicator`, revealed on hover, `cursor: grab/grabbing`) → body `p-5 flex flex-col flex-1`: title `font-headline-md text-primary mb-1`, desc `text-sm mb-6 flex-1`, footer `pt-4 border-t border-outline-variant/30 flex justify-between`: Edit (`text-sm font-semibold on-surface-variant hover:text-primary` + `edit` 18px) / Delete (`text-error hover:opacity-70`). Add tile: `border-2 border-dashed rounded-xl bg-surface-container-low hover:bg-surface-container hover:border-primary h-[420px]` with 64px `bg-primary-container/10` circle + `add_circle text-primary-container text-3xl`, "Create New Category" bold, helper `text-xs text-outline`. Grid `md:2 lg:3 xl:4 gap-8`, `px-12 pb-20`.

## 58. Review Moderation Card

`bg-surface-container-lowest border border-outline-variant rounded-xl p-6 hover:shadow-md hover:border-primary/50` → `flex justify-between items-start` → left `flex items-start space-x-6`: 96px product image `rounded-lg border` → stack `space-y-1`: status eyebrow mono (`text-primary` "PENDING MODERATION" / `text-secondary` "PRODUCT FEEDBACK" / `on-surface-variant` "SPAM / LOW QUALITY"), product `font-headline-md text-headline-md`, reviewer row (24px avatar, name `font-medium`, 4px dot separator, date `text-sm`), stars 20px `text-primary py-2`, review `max-w-3xl leading-relaxed` → right `flex flex-col items-end space-y-4`: status pill + action buttons (`p-2 rounded-lg`: approve `bg-primary/10 text-primary hover:bg-primary hover:text-on-primary`; hide `bg-surface-container-high hover:bg-inverse-surface hover:text-inverse-on-surface`; reply `hover:bg-primary-container`; delete `bg-error-container/10 text-error hover:bg-error hover:text-on-error`). Hidden variant: `bg-surface-container-low/50 opacity-70 hover:opacity-100`, image `grayscale`, quote italic.

## 59. Settings Sub-nav

`nav col-span-3 space-y-1 sticky top-24` → item `flex items-center justify-between w-full p-4 rounded-xl border` → icon + label `font-body-md`; active `bg-white border-primary text-primary font-bold shadow-sm` + `arrow_forward_ios` revealed on hover; inactive `border-transparent text-on-surface-variant hover:bg-surface-container-high font-medium`; group label mono 10px `text-outline` "COMMUNICATIONS". Anchors scroll smoothly to sections (#general, #payment…).

## 60. Progress Bar

Track `h-1|1.5|2 bg-surface-container(-high|-highest) rounded-full overflow-hidden` · fill `bg-primary` (or `bg-secondary`, `bg-secondary-fixed` on dark, `bg-white/20` track on primary). Widths via `w-2/3`, `w-[84%]`, inline `style="width:68%"`. Hero chip "STATUS: PRINTING" `w-32 h-1.5`; upload `h-1`; analytics capacity `h-2`. Decorative growing rule: `h-1 w-24 bg-primary/20 group-hover:w-full duration-500` (about mission/vision).

## 61. Avatar

Image: `rounded-full object-cover` 28 (`w-7`), 32, 40, 48, 128px; borders `border border-outline-variant`, `border-2 border-primary`, `border-2 border-primary-container p-0.5` (ring w/ gap), `border-4 border-surface-container-high shadow-inner` (profile), `ring-2 ring-primary/20`. Initials: same sizes, `flex items-center justify-center font-bold text-xs`, bg `bg-primary text-white` / `bg-primary/20 text-primary` / `bg-surface-container-high text-primary` / `bg-primary-fixed text-on-primary-fixed` / `bg-surface-container-highest on-surface-variant border`. Profile edit button: `absolute bottom-0 right-0 p-2 bg-primary text-white rounded-full shadow-lg hover:scale-110` (`photo_camera`).

## 62. Account Review Card

My reviews: `article.bg-white.rounded-xl.border.border-outline-variant.shadow-sm.hover:shadow-md.p-6.flex.flex-col.md:flex-row.gap-6` → image `w-full md:w-32 h-32 rounded-lg` → body: header `flex flex-col md:flex-row md:items-start justify-between mb-4` (title `font-headline-md`, stars primary 24px + date mono `text-sm`; buttons Edit neutral outline / Delete error outline `px-4 py-2 rounded-lg text-sm` with 18px icons) → review `text-body-md leading-relaxed mb-4` → footer `flex gap-4`: verified purchase pill + helpful button (`thumb_up` 14px `text-xs`).

## 63. App Filter Bar

- Glass filter panel (order-hist): `glass-panel p-6 rounded-xl border mb-8 shadow-sm` → `flex flex-wrap items-end gap-6`: search (`flex-1 min-w-[280px]`), date range (two date inputs + "to"), status select `md:w-48`, "RESET FILTERS" text button mono primary.
- Sticky filter (adm-reviews): `glass-panel border rounded-xl p-6 sticky top-20 z-30` with 3 labelled selects (`flex-1 min-w-[200px]`, `bg-transparent border-outline-variant rounded-lg`) + inverse "Apply Filters" button.
- Toolbar row (adm-products): selects with custom chevrons (`bg-white border rounded-lg px-4 py-2.5 pr-10 text-sm font-medium hover:border-primary`) + "Advanced Filters" (`tune`) + right primary "Add Product".
- In-card bar (adm-customers): `p-4 border-b flex flex-col lg:flex-row justify-between` mono-caps selects with leading `filter_list` + ghost buttons "Date Range" / "Export CSV".
- Compact bar (adm-orders): `bg-surface-container-lowest border rounded-xl p-4` borderless tinted inputs/selects (`bg-surface-container-low border-none rounded-lg py-2 text-sm`) + date chip + "Apply Filters" primary.

## 64. App Page Header

`flex justify-between items-end mb-8|10` → left: [breadcrumb/eyebrow mono] + H1/H2 `font-headline-lg text-headline-lg on-surface` (32px) + description `font-body-md|body-lg on-surface-variant mt-1` (max-w-2xl) → right: action buttons (`flex gap-3`; primary rightmost). Variants: boxed header with blueprint grid (adm-orders: `blueprint-grid relative p-8 rounded-xl border mb-8` + breadcrumb under title); analytics eyebrow "OPERATIONAL INTELLIGENCE" mono primary `text-xs tracking-widest`.
