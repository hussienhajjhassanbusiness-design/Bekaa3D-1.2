# Bekaa3D: Responsive Specifications

## 0. What the source actually contains

- **Every screenshot is desktop-only.** Each was captured at a 1280px CSS viewport. No mobile or tablet mockups exist in the export.
- All responsive behaviour below is **derived from the Tailwind breakpoint prefixes in each `code.html`**, plus one custom media query. Where the source has no responsive rule and the layout would break, the gap is labelled **Recommendation** (a proposal, not source).
- **Breakpoints:** standard Tailwind v3 defaults. The config does not customise `screens`.

| Name | Min width | Prefix usage (all pages) | Role in this design |
|---|---|---|---|
| (base) | 0 | — | Mobile-first base: mostly single column |
| `sm` | **640px** | 13 uses | Small-tablet refinements: 2-col product grids, toolbars go horizontal, "Cart" text label, search shown (wishlist) |
| `md` | **768px** | **183 uses** | **Primary breakpoint.** Nav links appear, sidebars appear, grids go multi-column, mobile bottom nav hides, gutters switch 16→64px |
| `lg` | **1024px** | 71 uses | Desktop: 12-col splits (7/5, 8/4), 3–4-col grids, header search fields appear, marketplace sidebar goes beside the grid |
| `xl` | **1280px** | 9 uses | Wide: 3-col STL grid, 6-col admin KPI row, 4-col category cards, the forgot-password side image |
| `2xl` | 1536px | 0 | Not used. Content caps at 1440px where the token works. |
| custom | `@media (max-width: 768px)` | home `.bento-grid` (4→2 cols; class unused in markup) | — |

Per-page density of responsive classes (md / lg counts) shows the split clearly. **Storefront and account pages** are responsive: home md 22, cart md 15/lg 5, my-reviews md 16, about md 17, product md 11/lg 4. **Admin pages** barely are: upload-product 0, edit-product lg 2, manage STL md 1, offers md 1, discounts md 2.

DESIGN.md intent: 12-column grid on desktop, 4-column on mobile, 1440px max width, 64px desktop margin, 16px mobile margin, 24px gutter.

---

## 1. Mobile (< 640px, base styles)

### Header
- **Storefront nav:** links are `hidden md:flex`, so they disappear. **There is no hamburger or menu in any storefront page.** **Recommendation:** add a menu button (24px `menu` icon in a `p-2` button) that opens a full-height sheet (`bg-surface`, links Inter 18px, 56px rows, active `text-primary`).
- Header search inputs (`hidden lg:block/flex`) are hidden. LOGIN is hidden (`hidden md:block`); REGISTER stays. The marketplace "Cart" text is hidden (`hidden sm:inline`).
- Logo size does not change (20px, or 32px on home/marketplace). **Recommendation:** use the 20px wordmark on mobile everywhere.
- Nav height stays 64/72/80px.

### Layout
- All grids collapse to `grid-cols-1`. This covers home bento, product/STL grids, features, testimonials, footer columns, checkout/cart/product splits, contact split, and account KPI rows.
- Exceptions that stay 2-col on mobile:
  - Product-detail spec tiles (`grid-cols-2`)
  - Product "Recommended Pairings" (`grid-cols-2 lg:grid-cols-4`)
  - Product gallery thumbs (`grid-cols-4`)
  - STL detail thumbs (`grid-cols-5`)
  - About stats band (`grid-cols-2 md:grid-cols-4`)
  - Checkout card expiry/CVC (`grid-cols-2`)
  - Checkout trust badges (`grid-cols-3`)
  - STL card actions (`grid-cols-2`)
  - Upload-STL preview gallery (`grid-cols-2`)
- Stacking order:
  - Product detail: gallery first, then info.
  - Cart: items first, then summary.
  - Checkout: form first, then summary.
  - About story: image first (`order-1 md:order-2`), then text.
  - Shop and marketplace: filter sidebar above the grid, full width.

### Spacing / gutters
- Pages that implement mobile gutters correctly use **16px** (`px-margin-mobile`): product details, cart, registration, admin login, forgot password.
- Pages that keep **64px** at all widths (source quirk): home, shop, checkout, marketplace sections, footers. **Recommendation:** 16px below `md`.
- Pages with broken tokens (about, contact, STL details) have **0px**. **Recommendation:** 16px.
- Section padding (`py-24` 96px) has no mobile reduction in the source. **Recommendation:** 64px (`py-16`) below `md`.

### Typography
- **No responsive type scaling exists in the source.** `headline-lg-mobile` (24px) is declared but never used, so display (48px) and headline-lg (32px) stay fixed.
- **Recommendation:**

| Token | Below `md` |
|---|---|
| display | 36px, line-height 1.1 |
| headline-lg | 24px (= `headline-lg-mobile`) |
| headline-md, body | unchanged |

- The home hero H1 at 48px with a `<br>` will wrap to 3–4 lines on a 360px screen without this change.

### Cards
- **1 per row:**
  - Product cards: home, shop, wishlist.
  - STL cards: home, marketplace, library.
  - Related STL cards (`sm:` 2).
- **2 per row:**
  - "Recommended pairings".
- **Images:**
  - Square cards stay `aspect-square` (full-width squares).
  - Marketplace STL images are fixed at `h-64`.
  - Product main image is `aspect-square` on mobile and `md:aspect-video` above.
  - The cart line image becomes full width × 128px (`w-full md:w-32 h-32`).
- **Hover-only affordances** (quick view, wishlist heart, row actions, quick-add) are unreachable on touch. **Recommendation:** show them persistently below `md`.

### Forms
- Two-column field rows become one column:
  - Registration: `grid-cols-1 md:grid-cols-2`.
  - Checkout: `md:grid-cols-2`.
  - Contact: `md:grid-cols-2`.
  - Profile security: `md:grid-cols-2`.
- The contact submit is full width (`w-full md:w-auto`).
- Auth cards go full width with reduced padding:
  - Register: `p-8` instead of `md:p-12`.
  - Forgot: `p-8` instead of `md:p-12`.
  - Admin login: right panel `p-8`.
- Admin login hides its left "Engineering Integrity" panel (`hidden md:flex`).
- Input heights are unchanged (48px), which satisfies touch targets.

### Tables
- Wrapped in `overflow-x-auto` → **horizontal scroll** (order history, offer history, admin tables). Account dashboard and analytics tables have no wrapper → **overflow**. **Recommendation:** wrap every table, or switch to stacked row cards below `md`. A stacked card shows: title row (ID + status chip), then label/value pairs in mono caps.

### Sidebars
- **Account pages:**
  - Hidden below `md` (`hidden md:flex`) on account dashboard, wishlist, STL library, and profile.
  - Main loses its offset (`md:ml-64`).
  - **Mobile bottom nav** (`md:hidden fixed bottom-0`) replaces the sidebar on account dashboard, wishlist, and profile.
  - STL library has no bottom nav (gap).
- **Account pages with no mobile handling:** order history, offer history, and my reviews keep `ml-64` and the fixed sidebar, which breaks on phones. **Recommendation:** use the same hidden sidebar plus bottom nav.
- **Wishlist header** shows a `menu` button below `md` (non-functional in the source). **Recommendation:** open the sidebar as a left drawer (256px, overlay `bg-on-surface/40`).
- **Shop/marketplace filters:** stack above results. **Recommendation:** a "Filters" button opening a bottom sheet or drawer.

### Footer
- 4 columns → 1 column (`grid-cols-1 md:grid-cols-4`). The marketplace footer uses `col-span-12` brand, `col-span-6` link columns (2 side by side), and `col-span-12` legal.
- The bottom bar stacks (`flex-col md:flex-row gap-4`) and centres.

### Admin layouts
- **No mobile design.** The sidebar is always fixed at 256px, main is `ml-64`, and fixed headers use `left-64`. Admin KPI grids do collapse to 1 column, but the layout is unusable below ~1024px.
- **Recommendation:**
  - Below `lg`, hide the sidebar behind a `menu` toggle in the top bar (drawer).
  - Make main full width.
  - Collapse 12-col form splits (8/4) to stacked.
  - Scroll tables horizontally.
  - Treat admin as "desktop-first, tablet-tolerant".

---

## 2. Tablet (640–1023px: `sm` and `md`)

| Area | Behaviour (from source classes) |
|---|---|
| Header | At `md` (768+): nav links visible (`gap-6`/`gap-8`), LOGIN visible. Header search still hidden until `lg`. |
| Gutter | 64px at `md`+ where `md:px-margin-desktop` is used. |
| Home | Hero becomes 2 columns (`md:grid-cols-2 gap-16`); hero chip bottom-left appears (`hidden md:block`). Bento: 4 columns (`md:grid-cols-4`) with the 2×2 feature tile. Products 4-up (`md:grid-cols-4`, tight at 768). STL 3-up. Features 3-up (`md:grid-cols-3`, 6-up at `lg`). Testimonials 3-up. Promo becomes 2 columns, image visible, text left. |
| Shop | `sm`: grid 2-up, toolbar horizontal. `md`: sidebar (256px) beside the grid (`md:flex-row`) → the grid gets ~400px at 768, i.e. 2 cards that are narrow. **Recommendation:** keep the sidebar stacked until `lg`. |
| Marketplace | Sidebar still stacked (`lg:flex-row`); grid 2-up (`md:grid-cols-2`); hero search goes horizontal (`md:flex-row`). |
| Product detail | Gallery and info still stacked (`lg:` split); main image 16:9; engineering section 1/3 + 2/3 (`md:flex-row`); reviews 3-up; pairings 2-up. |
| STL detail | Stacked viewer/info; description 2/3 + 1/3 (`md:grid-cols-3`); related 2-up (`sm`). |
| Cart | Line items horizontal (`md:flex-row`, image 128px); summary below; suggestions 3-up (`md:grid-cols-3`). |
| Checkout | Form rows 2-col; summary below form. |
| About | Story 2-col; mission/vision 2-col; capabilities bento 3-col; team 2-up (`sm`); stats 4-up. |
| Contact | Hero `md:p-20`; form 2-col name row; right column still below. |
| Account | Sidebar appears at `md` (768); bottom nav hides; KPI 2-up (`sm:grid-cols-2`); asset cards 2-up; profile cards stacked until `lg`. |
| Admin | Fixed sidebar takes 256 of 768px. KPI rows 2-up (`md:grid-cols-2`). Tables scroll. Forms (8/4 fixed `col-span-8/4`) get cramped. **Recommendation:** drawer sidebar below `lg`. |
| Footer | 4 columns at `md`. |

---

## 3. Desktop (1024–1279px: `lg`)

- Header search fields appear (shop pill `w-48`, marketplace `w-64`, admin console `w-64`, admin products `w-72`).
- 12-column splits activate:
  - Product 7/5, STL detail 7/5, contact 7/5.
  - Cart 8/4, checkout 7/5.
  - Edit-product 8/4, upload-STL file 7/5.
  - Profile 12/7+5/6+6.
- Shop grid 3-up next to the 256px sidebar. The marketplace sidebar (288px) moves beside the grid, which is 2-up until `xl`.
- Home features 6-up; product pairings 4-up; cart suggestions 4-up (4th card `hidden lg:block`).
- Admin KPI rows: admin dashboard 3-up (`lg:grid-cols-3`), admin console 5-up (`lg:grid-cols-5`), others 4-up. Charts 2/3 + 1/3.
- Analytics tables 2-up (`lg:grid-cols-2`).
- Login decorative schematic images appear (`hidden lg:block`).
- Account dashboard KPI 4-up, assets 4-up, two-column panels.
- This is the screenshot width (1280) minus one step: all screenshots represent `xl` (1280) behaviour.

## 4. Wide desktop (≥ 1280px: `xl`; content cap 1440px)

- Marketplace STL grid 3-up (`xl:grid-cols-3`); STL library 3-up.
- Admin dashboard KPI row 6-up (`xl:grid-cols-6`); orders/logs split 3/4 + 1/4 (`xl:grid-cols-4`, `xl:col-span-3`).
- Categories 4-up (`xl:grid-cols-4`).
- Analytics charts 2/3 + 1/3 (`xl:grid-cols-3`).
- Forgot password side image card appears (`hidden xl:block`, 256×256 fixed bottom-right).
- Containers stop growing at **1440px** (`max-w-max-width` / `max-w-[1440px]`) on pages where the token works. Home, about, contact, and STL details grow unbounded (broken token). **Recommendation:** cap at 1440px.
- Content beyond 1440: backgrounds, full-bleed sections (home section bands, about hero, stats band), and fixed navs remain full width. The marketplace nav itself is capped (the bar would not span the screen). **Recommendation:** full-width nav bar with a capped inner container.

---

## 5. Per-component responsive summary

| Component | Mobile | `sm` | `md` | `lg` | `xl` |
|---|---|---|---|---|---|
| Storefront nav | logo + icons (+ REGISTER) | + "Cart" label | + links, + LOGIN | + search field | — |
| Hero (home) | stacked | — | 2-col, side chip | — | — |
| Product grid (shop) | 1 | 2 | (sidebar beside) | 3 | — |
| Product grid (home) | 1 | — | 4 | — | — |
| STL grid (marketplace) | 1 | — | 2 | (sidebar beside) | 3 |
| STL grid (home) | 1 | — | 3 | — | — |
| Related STL | 1 | 2 | — | 4 | — |
| Wishlist grid | 1 | 2 | — | 3 | — |
| Category admin | 1 | — | 2 | 3 | 4 |
| Admin KPI (dashboard) | 1 | — | 2 | 3 | 6 |
| Account KPI | 1 | 2 | — | 4 | — |
| Detail split (product/STL) | stacked | — | — | 7/5 | — |
| Cart / checkout split | stacked | — | — | 8/4 · 7/5 | — |
| Footer | 1 col, stacked bottom bar | — | 4 col | (marketplace 4/2/2/4) | — |
| Account sidebar | hidden + bottom nav | — | visible 256px | — | — |
| Admin sidebar | always visible (no handling) | | | | |
| Tables | horizontal scroll | | | | |
| Auth card | full width, `p-8` | — | `p-12`, admin split visible | decorative images | forgot side image |

## 6. Responsive overflow risks found in source

1. Manage customers header: `w-full ml-64` → 256px horizontal overflow at every width.
2. Cart coupon row: input without `min-w-0` → button overflows the card (visible at 1280px).
3. Account-dashboard and analytics tables have no `overflow-x-auto` → page-level horizontal scroll on small screens.
4. Home bento large tile `h-[500px]` and hero `min-h-screen`: fine. Absolutely positioned hero chips (`-top-6 -right-6`) can cause horizontal overflow on narrow screens (`overflow-x-hidden` on body masks it).
5. Order history / offer history / my reviews / all admin pages: fixed 256px sidebar plus `ml-64` with no breakpoint → the content column is unusable below ~900px.
6. Upload physical product: fixed `col-span-8 / col-span-4` with no breakpoint.
7. System settings: fixed `col-span-3 / col-span-9` with no breakpoint.
8. Shop at `md` (768–1023): sidebar beside a 2-col grid is cramped.
9. Long STL titles beside prices (`justify-between` with no `min-w-0`/wrap rules) wrap awkwardly. **Recommendation:** `min-w-0` on the title, `shrink-0` on the price.
