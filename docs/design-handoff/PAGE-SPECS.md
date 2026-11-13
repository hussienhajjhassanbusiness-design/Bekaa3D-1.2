# Bekaa3D — Page Specifications

Root of all source paths: `stitch_bekaa3d_premium_e_commerce_platform/` (the folder that contains `design-handoff/`). Each page folder holds exactly one `code.html` and one `screen.png`. There are **no mobile or tablet variants** in the export: every screenshot is a full-page desktop capture at a **1280px CSS viewport** (1600px-wide PNGs are 1.25× device-pixel captures; tall pages were downscaled to 1600px height).

Component numbers (§n) refer to [COMPONENT-SPECS.md](./COMPONENT-SPECS.md). "Renders 16px" notes refer to DESIGN-SYSTEM §12.3.

---

## Page inventory

| # | Page folder | Design name (`<title>` intent) | Source HTML | Screenshot (px) · approx page height @1280 | Layout type | Major sections | Likely purpose | Shared components | Unique components |
|---|---|---|---|---|---|---|---|---|---|
| S1 | `bekaa3d_engineered_grade_3d_solutions` | Home — "Precision Manufacturing & 3D Solutions" | `…/code.html` | `screen.png` 336×1600 · ~6095px | Storefront: fixed nav + full-width sections + footer | Hero, Category bento, Physical products, Promo banner, STL marketplace, Features, Testimonials, Custom-quote CTA, Footer | Landing page | Nav, Footer, Product card (showcase), STL card, WhatsApp FAB, Buttons | Split hero w/ floating glass chips, Bento category grid, Dark promo banner, Feature tiles, Testimonials, Green CTA panel |
| S2 | `shop_physical_products_manufacturing_bekaa3d` | Shop — Physical Products | `…/code.html` | 969×1600 · ~2114px | Storefront: nav + hero banner + sidebar/grid | Image search hero, Filters sidebar, Toolbar, 3-col product grid, Pagination, Footer | Physical product catalogue | Nav, Footer, Product card (catalog), Pagination, Filter controls, WhatsApp FAB | Glass pill hero search, Custom-quote sidebar box, view toggle |
| S3 | `digital_stl_marketplace_bekaa3d` | Digital STL Marketplace | `…/code.html` | 768×1600 · ~2667px | Storefront: nav + centered hero + sidebar/grid | Hero w/ search, Filters, Results bar, STL grid, Pagination, Verification band, Footer | STL catalogue | Nav, Footer, STL card, Pagination, Filters | Card search hero + trust row, license toggle buttons, format chips, 12-col footer |
| S4 | `product_details_bekaa3d_precision_kit` | Product Details — "NX7 Ultra-Poly Carbon" | `…/code.html` | 645×1600 · ~3175px | Storefront: nav + 7/5 split + stacked sections | Gallery + buy box, Material engineering, Reviews, Recommended pairings, Footer | Physical product page | Nav, Footer, Spec tiles, Stepper, Rating, Review cards, Compact product cards | Hover-zoom gallery, sticky side intro, case-study image card |
| S5 | `stl_details_planetary_gear_system_bekaa3d_digital` | STL Details — "Planetary Gear System" | `…/code.html` | 843×1600 · ~2429px | Storefront: nav + breadcrumb + 7/5 split | Breadcrumb, Viewer + thumbs, Info card, Secure note, Tabs, Description + review summary, Related STL, Footer | Digital product page | Nav, Footer, Breadcrumb, Tabs, Spec tiles, Related STL cards | 3D-viewport glass control bar, compatibility chips, stat strip |
| S6 | `your_cart_bekaa3d_precision_engineering` | Your Cart | `…/code.html` | 1240×1600 · ~1652px | Storefront: nav + 8/4 split | Page header, Line items, Order summary (sticky), Frequently bought together, Footer | Cart | Nav, Footer, Compact product cards, Stepper | Cart line item (physical/digital), coupon field, Hanken CTA |
| S7 | `checkout_bekaa3d_precision_engineering` | Secure Checkout | `…/code.html` | 1232×1600 · ~1662px | Storefront (reduced nav): 7/5 split | Shipping form, Billing, Payment, Order summary (sticky), Trust badges, Footer | Checkout | Footer, Form fields, Order summary | Step headers, payment option cards, trust tiles, "Secure Checkout" header |
| S8 | `about_us_bekaa3d_engineering` | About — Engineering | `…/code.html` | 354×1600 · ~5785px | Storefront: nav + full-bleed sections | Photo hero, Story, Mission/Vision, Capabilities bento, Stats band, Team, Masonry gallery, CTA, Footer | Company page | Nav, Footer, Buttons | Full-bleed photo hero, dark vision card, stats band, masonry grid, team cards |
| S9 | `contact_us_bekaa3d_inquiry` | Contact — Inquiry | `…/code.html` | 868×1600 · ~2359px | Storefront: nav + boxed hero + 7/5 split | Hero, Inquiry form, Direct channels, Map/address, Community, FAQ, Footer | Contact/support | Nav, Footer, Form fields | Contact channel list, map card, FAQ accordion, open-now pulse |
| A1 | `user_login_bekaa3d_precision_engineering` | User Login | `…/code.html` | 1600×1280 · 1024px | Auth: centered card | Card (brand, form, social, footer strip), status bar | Customer sign-in | Form fields, Buttons | Split wordmark, social login, SVG dot pattern bg |
| A2 | `user_registration_bekaa3d_precision_engineering` | User Registration | `…/code.html` | 1600×1374 · ~1099px | Auth: centered glass card | Header, 2-col form, terms, submit, icon strip; success overlay | Account creation | Form fields | Success overlay modal, decorative icon strip |
| A3 | `forgot_password_bekaa3d_precision_engineering` | Reset Password | `…/code.html` | 1600×1280 · 1024px | Auth: centered glass card | Fixed logo, rotating rings, card, side image, fixed footer | Password recovery | Form field, Gradient button | Rotating ring decoration, glass shine |
| A4 | `admin_login_bekaa3d_operations_console` | Admin Login — Operations Console | `…/code.html` | 1600×1280 · 1024px | Auth: split card | Integrity panel (left), form (right), footer | Admin sign-in | Form fields | Split auth layout, glow dot |
| C1 | `account_dashboard_bekaa3d` | Account Dashboard | `…/code.html` | 1106×1600 · ~1852px | App: sidebar (gradient active) + glass header | KPI row, Recent orders table, Digital assets, Recent access + B2B licensing, Account info band, Footer, Mobile bottom nav | Customer home | Sidebar, Table, KPI cards, Asset cards, Bottom nav | Tier brand card, licensing negotiation list |
| C2 | `order_history_bekaa3d_precision_management` | Order History | `…/code.html` | 1600×1535 · ~1228px | App: full-width header + sidebar | Title, Filter panel, Orders table + pagination, Live feed card + promo image | Customer orders | Sidebar, Table, Pagination, Filter bar | Date-range filter, factory feed card |
| C3 | `offer_history_bekaa3d_precision_management` | Offer History | `…/code.html` | 1600×1400 · ~1120px | App: sidebar, no top bar | Title, 3 KPI cards, Offers table, Help strip | Customer price negotiations | Sidebar, Table, KPI | Offer status chips (blue/green/amber/red), seller response column |
| C4 | `my_reviews_bekaa3d_precision_management` | My Reviews | `…/code.html` | 1563×1600 · ~1310px | App: sidebar + sticky glass header | Header w/ search+sort, 3 stats, Review cards, Pagination | Customer reviews | Sidebar, KPI, Pagination | Account review card |
| C5 | `my_wishlist_bekaa3d_precision_engineering` | My Wishlist | `…/code.html` | 1299×1600 · ~1577px | App: sidebar + sticky header | Title, Filter/sort bar, 3-col product grid, (empty state), Help footer, Mobile bottom nav | Saved products | Sidebar, Product card (wishlist), Empty state, Bottom nav | Glass action buttons on cards |
| C6 | `purchased_stl_downloads_bekaa3d_digital_library` | My STL Library | `…/code.html` | 1600×1280 · 1024px | App: sidebar + sticky header | Title, Filter bar, 3-col library cards, (empty state), Meta footer | Purchased STL downloads | Sidebar, STL library card, Empty state | Download count states |
| C7 | `user_profile_bekaa3d_precision_management` | User Profile | `…/code.html` | 1600×1328 · ~1062px | App: sidebar + sticky header, 12-col bento | Profile header, Personal info, Address, Security, Preferences, Mobile bottom nav | Account settings | Sidebar, Toggles, Form fields, Bottom nav | Avatar w/ camera button, toggle list |
| D1 | `admin_dashboard_bekaa3d_operations` | Admin Dashboard — Operational Overview | `…/code.html` | 1345×1600 · ~1523px | Admin: sidebar (collapsible) + sticky header, dot-grid canvas | Title, 6 KPI cards, Bar chart + donut, Recent orders + system logs, FAB | Admin home | Admin sidebar, KPI, Table, Charts, FAB | Conic donut, CSS bar chart w/ tooltips, activity timeline |
| D2 | `admin_console_bekaa3d_operations` | Admin Console — Dashboard Overview | `…/code.html` | 1600×1280 · 1024px | Admin: app-shell (h-screen, internal scroll) | Quick actions, 5 KPIs, Revenue bars + sales mix, Recent activity table, Notification panel | Alternate admin home | KPI, Table, Charts | Grouped sidebar, quick-action bar, notification dropdown |
| D3 | `admin_analytics_bekaa3d_operations_console` | Analytics Dashboard | `…/code.html` | 1162×1600 · ~1762px | Admin: sidebar + glass header, blueprint canvas | Title + actions, 4 square KPIs, Line chart + doughnut, 2 tables, Bar chart + capacity card | Analytics | Sidebar, Tables, KPI | Chart.js charts, square (rounded-none) cards |
| D4 | `manage_physical_products_bekaa3d_admin` | Manage Physical Products | `…/code.html` | 1600×1280 · 1024px | Admin: sidebar + sticky header | Toolbar, Products table (bulk/toggles/hover actions), 4 stat cards | Product CRUD list | Table, Toggle, Pagination, KPI | Hover-reveal row actions, featured toggle column |
| D5 | `edit_physical_product_bekaa3d_admin` | Edit Physical Product | `…/code.html` | 1399×1600 · ~1464px | Admin: sidebar + breadcrumb header, 8/4 form | Header actions, General info, Media manager, Specs, Pricing, Visibility, SEO, meta footer | Product edit | Form fields, Rich text, Toggles | Underline inputs, media manager w/ PRIMARY |
| D6 | `upload_physical_product_bekaa3d_admin` | Upload Physical Product | `…/code.html` | 1059×1600 · ~1934px | Admin: sidebar, 8/4 form | Header, General, Pricing, Specs, Media dropzone, Visibility, SEO, Organization, Pro tip | Product create | Form fields, Dropzone, Toggles, Tag input | Key/value spec rows, character counters |
| D7 | `manage_stl_files_bekaa3d_admin` | Manage STL Files | `…/code.html` | 1600×1339 · ~1071px | Admin: sidebar, no top bar | Header + CTA, 4 stats, Filter bar, STL table, Bulk footer | STL CRUD list | Table, Toggles, KPI, Pagination | Preview thumbnails, license/offer chips, Live toggle |
| D8 | `upload_stl_file_bekaa3d_admin` | Upload New Asset (STL) | `…/code.html` | 907×1600 · ~2258px | Admin: sidebar + sticky action header | General, Tech specs, Asset upload + Thumbnail, Preview gallery, Marketplace + SEO, status pill | STL create | Form fields, Dropzone, Radio cards, Toggles | Upload progress row, printer checklist, HH:MM input |
| D9 | `manage_categories_bekaa3d_admin` | Categories — Management Portal | `…/code.html` | 1600×1412 · ~1130px | Admin: sidebar + sticky header, dot-grid | Controls row, 4-col category cards + add tile | Category CRUD | Admin category card | Drag handles, dashed add tile |
| D10 | `manage_orders_bekaa3d_admin_console` | Manage Orders | `…/code.html` | 1600×1515 · ~1212px | Admin: sidebar + fixed header | Blueprint title box, 4 stats, Filter bar, Orders table, Meta footer | Order management | Table, KPI, Filter bar, Pagination | Tracking link cell, payment icon cell |
| D11 | `manage_customers_bekaa3d_admin_console` | Manage Customers | `…/code.html` | 1600×1280 · 1024px | Admin: sidebar + sticky header (overflowing) | Title + CTA, 4 metric cards, Filter+table card | Customer management | Table, KPI, Pagination | Display-size metrics, suspend/reactivate actions |
| D12 | `manage_reviews_bekaa3d_admin_console` | Manage Reviews | `…/code.html` | 1600×1687 · ~1350px | Admin: sidebar + fixed header, dot bg | Title + export, 4 stats, Sticky filters, Moderation cards, Pagination | Review moderation | KPI, Pagination | Review moderation card |
| D13 | `manage_offers_bekaa3d_admin_console` | Manage Price Offers | `…/code.html` | 1600×1280 · 1024px | Admin: sidebar + fixed header | Title + actions, 3 stats, Filters, Offers table, FAB | Offer negotiation (admin) | Table, KPI, FAB | Negotiation cell (rounds), accept/reject/counter |
| D14 | `manage_discounts_bekaa3d_admin_console` | Discount Management | `…/code.html` | 1600×1622 · ~1298px | Admin: sidebar, no top bar, blueprint | Title + CTA, 3 stats, Search+filters, Discounts table, Banner preview | Discount/coupon management | Table, KPI | Button toggle, banner-star column, homepage banner preview |
| D15 | `system_settings_bekaa3d_admin_console` | System Settings — Console Operations | `…/code.html` | 1101×1600 · ~1860px | Admin: sidebar + fixed header, 3/9 settings layout | Header actions, Settings sub-nav, General, Prefs, Contacts, Hero config, Payments, Security, Sessions, Toast | Platform settings | Toggles, Form fields, Dropzone, Toast | Settings sub-nav, segmented control, sessions list |

Also in the export: `precision_engineering_system/DESIGN.md` (Stitch design brief; no HTML/screenshot).

**Page families**
- **Storefront (9):** S1–S9. Fixed glass top nav plus a footer.
- **Auth (4):** A1–A4. Centered card on a patterned background, with no nav or footer.
- **Customer account (7):** C1–C7. 256px left sidebar; mobile bottom nav on C1, C5, and C7.
- **Admin console (15):** D1–D15. 256px left sidebar plus a 64px top bar. Desktop-only.

---

# Storefront pages

## S1 · Home
**SOURCE** `bekaa3d_engineered_grade_3d_solutions/code.html` · screenshot `…/screen.png`
**OVERALL LAYOUT** A single column of full-width sections. Each section's inner container uses `max-w-container-max` (undefined → no max width) with `mx-auto px-margin-desktop` (64px at every width). Body: `bg-background text-on-background font-body-md overflow-x-hidden`, selection `bg-primary-fixed text-on-primary-fixed`.
**HEADER** Nav variant A (§1): `fixed top-0 w-full z-50 bg-white/70 backdrop-blur-md border-b border-white/10 shadow-sm`, inner `py-4 flex justify-between items-center`. Gradient wordmark at 32px. Centered links Home (active) · Shop · STL Store · About (`gap-8`). Right side (`gap-4`): search icon button, cart button with `0` badge (`top-0 right-0`), LOGIN outline (hidden <md), REGISTER solid. JS: after 50px of scroll, `py-4 shadow-sm` changes to `py-2 shadow-lg`. A global JS handler adds `scale(0.95)` on mousedown to all buttons and links.
**MAIN – SECTIONS IN ORDER**
1. **Hero** (§9 split). Section: `relative pt-32 pb-20 min-h-screen flex items-center overflow-hidden`, background `background` plus 2 blurred orbs. Grid: `md:grid-cols-2 gap-16 items-center`.
   - Left: eyebrow "PRECISION MANUFACTURING". H1 "Engineered Grade" `<br>` "3D Solutions" (the second line in `.text-gradient-primary`). Body-lg paragraph `max-w-lg`. Buttons (`gap-4 flex-wrap`): "SHOP PRODUCTS →" (primary `px-8 py-4 shadow-lg`, `arrow_forward text-sm`) and "EXPLORE STL FILES" (2px outline). Mini stats: "2,500+ / MODELS SHIPPED" and "0.02mm / PRECISION TOLERANCE".
   - Right: square image `rounded-2xl shadow-2xl border border-white/20`, plus two floating glass chips (STATUS: PRINTING with a 68% bar; AI CALIBRATION with a `memory` icon in a 48px `bg-primary/10` circle).
2. **Curated Specialized Collections**. `py-24 bg-surface-container-lowest`. Centered header `mb-16`. Bento grid `grid-cols-1 md:grid-cols-4 gap-6` (§13): one large tile "Digital STL Archives" (2×2, 500px, `bg-primary-container`, image at 40% opacity), plus four 240px tiles: Engineering Parts, Home Decor, Miniatures, Automotive.
3. **Physical Masterpieces**. `py-24 bg-white`. Split header (`flex justify-between items-end mb-12`; link "VIEW ALL PRODUCTS"). Grid `md:grid-cols-4 gap-8` of Showcase product cards (§11a), with these badges: card 1 NEW (primary), card 2 -30% (tertiary) with strike price $45.00, cards 3–4 no badge. Card 2 has 4.5 stars (`star_half`). Only card 1 has the wishlist button.
4. **Promo banner**. Dark promo (§52): "30% OFF / Storewide Launch", lime "REDEEM DISCOUNT", product collage image (400px, glow). Wrapper `mb-24`, no section padding.
5. **STL Marketplace**. `py-24 bg-surface-container-low`. Header `flex-col md:flex-row justify-between items-start md:items-center mb-12 gap-4` with FILTER: ALL / SORT: NEWEST outline buttons. Grid `md:grid-cols-3 gap-8` of home STL cards (§12a): Cyber-Arm Kit v2.4 $19.99 COMMERCIAL LICENSE; Brutalist Facade Set $12.50 PERSONAL USE; Guardian of the Glen $35.00 EXCLUSIVE.
6. **Precision as Standard**. `py-24 bg-white`. Centered header. Feature tiles (§14) `md:grid-cols-3 lg:grid-cols-6 gap-8`: biotech High Precision, category Premium Materials, speed Fast Production, verified_user Secure STL, settings_input_component Custom Manufacturing, support_agent Local Support.
7. **Trusted by Innovators**. `py-24 bg-surface-container-lowest`. H2 centered `mb-16`. Testimonial cards (§15) `md:grid-cols-3 gap-8` (glass, `p-10`).
8. **Custom Quote CTA**. `py-24`. Green CTA panel (§52) `rounded-3xl p-16`. Note that the container itself carries the bg and padding (`max-w-container-max mx-auto px-margin-desktop bg-primary … p-16`), so the panel spans the full width minus nothing.
**FOOTER** `bg-surface-container-low pt-24 pb-12`, grid `md:grid-cols-4 gap-gutter mb-20`. Brand column (wordmark 20px primary, text, 3 social circles: public / alternate_email / share). Columns: Company (Mission, Terms of Service, Privacy Policy, Careers), Categories (Engineering, Digital STL, Home Decor, Automotive). Each link column uses `md:ml-auto`. Newsletter (input + send button). Bottom bar: "© 2024 Bekaa3D. Precision Manufacturing." plus 4 payment logo images (h-6, grayscale 40%).
**FLOATING** WhatsApp FAB 56px, `bottom-8 right-8`.
**DESKTOP** As described. Content is full-bleed (no 1440 cap), as the screenshot confirms.
**TABLET (768–1023)** Hero is 2 columns. Bento is 4 columns. Product grid is 4 columns (cramped). Features are 3 columns. LOGIN is visible.
**MOBILE (<768)** Nav links and LOGIN are hidden (no menu). Hero stacks (image under text; the bottom-left chip is hidden). Bento, products, STL, and testimonials go to 1 column. Features go to 1 column. Promo image is hidden and text is centered. Footer is 1 column with the bottom bar stacked. Gutter stays 64px (quirk).
**UNIQUE** Hero floating chips, bento tiles, feature tiles, dark promo, green CTA.
**QUIRKS TO KEEP** Lime promo headline line; text-gradient H1 accent; card 1's NEW badge with the wishlist heart revealed on hover; quick-view overlay; `animate-bounce` chip with a 4s duration.
**DO NOT KEEP** Broken `max-w-container-max`; 64px mobile gutter; `font-label-md` (no-op).

## S2 · Shop (Physical Products)
**SOURCE** `shop_physical_products_manufacturing_bekaa3d/code.html`
**OVERALL LAYOUT** Nav plus `main.pt-24.pb-16.max-w-max-width(1440).mx-auto.px-margin-desktop`. Body `bg-background`.
**HEADER** Nav variant B: `bg-surface/80 backdrop-blur-xl border-b border-outline-variant/30 shadow-sm`, inner `px-margin-desktop py-4 max-w-max-width`. Logo 20px bold primary. Centered links with Shop active (`font-bold`). Right: search pill (lg+), cart with badge 2 (`-top-2 -right-2`), person icon.
**SECTIONS**
1. **Hero/Search**. `section mb-12`. Box `relative rounded-xl overflow-hidden h-[300px] flex flex-col items-center justify-center text-center px-6`. Background image `brightness-50 bg-cover`. Content `max-w-2xl`: H1 "Find Your Precision Part" (display, white, `mb-6`) plus glass pill search (§5) with a primary-gradient SEARCH button.
2. **Catalogue**. `flex flex-col md:flex-row gap-gutter`.
   - **Aside** `w-full md:w-64 space-y-8` (§19 shop). Groups: Categories (4 checkboxes), Material (3 radios), Price Range ($0 / $1000), Custom Quote box ("Request Slot").
   - **Grid area** `flex-grow`. Toolbar (§20). Grid `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8` of 6 Catalog product cards (§11b). Badges: Engineering (primary), Home Decor (secondary), Automotive (tertiary), Robotics (primary), Accessories (secondary), Industrial (primary). Stars in `text-secondary`, empty in `outline-variant`. Only the first-row cards carry the hover overlay buttons.
   - Pagination circle variant (§21), `mt-16`: ‹ 1 2 3 … 12 ›.
**FOOTER** `bg-surface-container-lowest border-t border-outline-variant`. Grid `md:grid-cols-4 gap-gutter py-16`. Brand (share/mail/map circles). Products (Printers, Materials, Case Studies). Support (Documentation, Support, Privacy, Terms). Newsletter (input `bg-surface-container border-none` + send). Copyright bar centered `py-8 border-t border-outline-variant/30`.
**FLOATING** WhatsApp FAB (`p-4`, 32px glyph, `z-[60]`, `shadow-2xl`).
**RESPONSIVE** <md: sidebar stacks above the grid (full width); toolbar stacks (`sm:flex-row`); grid 1 column, 2 at ≥640, 3 at ≥1024. Header search is hidden below lg.
**QUIRKS** The 300px rounded hero sits inside the container (not full-bleed). The sort select is tinted (`bg-surface-container`).

## S3 · Digital STL Marketplace
**SOURCE** `digital_stl_marketplace_bekaa3d/code.html`
**OVERALL LAYOUT** Nav (80px) plus `main.pt-20`. Body `overflow-x-hidden`. Custom scrollbar 8px (track `#f9f9ff`, thumb `#bfcaba`).
**HEADER** Nav variant C: `fixed h-20 px-margin-desktop max-w-max-width mx-auto bg-surface/80 backdrop-blur-md border-b border-outline-variant/30`. Note the nav itself is the max-width box, so at >1440px it would not span full width (quirk). Logo 32px extrabold. Links Marketplace (active, `py-7` underline at the bottom edge) · Services · Materials · Community, `gap-8`, logo-to-links `gap-12`. Right: search input `w-64` (lg+), Cart (icon + text sm+), Login button.
**SECTIONS**
1. **Hero** `h-[400px]`, centered (§9): pill "ENGINEERING ARCHIVE", H1 "Digital STL Marketplace", body-lg, card search, trust row. **No background image** (plain background).
2. **Marketplace layout** `max-w-max-width mx-auto px-margin-desktop py-16 flex flex-col lg:flex-row gap-gutter`.
   - Aside `lg:w-72 space-y-10` (§19 marketplace): Filters + Reset All; Categories (Engineering & CAD checked); License Type toggle buttons (Personal Only selected); Compatibility select; Format chips (STL active); Price Range ($0 / $500+).
   - Main: results row (§20) plus grid `grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-8` of 6 STL cards (§12b): Precision V2 Gear Housing $45 COMMERCIAL; Voronoi Apex Lamp FREE PERSONAL ("Download Free" inverse button); X-Pro Drone Chassis $89; Industrial Parallel Gripper $120; Lunar Base: Sector 7 $12.50 PERSONAL (Buy Now only); ErgoKey 65 Shell $35. Pagination bordered `mt-16`: ‹ 1 2 3 … 24 ›.
3. **Precision-First Philosophy** `bg-surface-container-low py-20 border-y border-outline-variant/30`, centered. H2 (`font-headline-lg` only → **renders 16px**), body-lg `max-w-3xl mb-12`. Grid `md:grid-cols-4 gap-gutter text-left` of glass tiles (§14): architecture CAD Verified, verified_user Manifold Check, settings_input_component Print Optimization, copyright Clear Rights.
**FOOTER** `footer bg-surface-container-low border-t py-16 px-margin-desktop max-w-max-width mx-auto grid grid-cols-12 gap-gutter`: brand `col-span-12 lg:col-span-4` (social squares `bg-surface-container-highest` rounded-full), Marketplace and Resources `col-span-6 lg:col-span-2` (links `/70`, hover translate-x), Legal & Corporate `col-span-12 lg:col-span-4` (inline links plus copyright 12px `/50`).
**RESPONSIVE** Sidebar stacks until lg (1024). Grid 1 → 2 (md) → 3 (xl 1280). At 1024–1279 the grid shows 2 columns beside a 288px sidebar. Hero search stacks button under input (<md).
**QUIRKS** Card titles and prices sit side by side with `justify-between`; long titles wrap to 2 lines (visible). Card titles render 16px (§12.3).

## S4 · Product Details
**SOURCE** `product_details_bekaa3d_precision_kit/code.html` (**no fontSize config**; all token text sizes are no-ops)
**OVERALL LAYOUT** Nav plus `main.pt-24.pb-16.px-margin-mobile.md:px-margin-desktop.max-w-max-width.mx-auto`.
**HEADER** Nav variant D (`bg-surface/80 backdrop-blur-xl py-4 shadow-sm`). Logo plus links (`gap-6`, Shop active). Right: cart, person.
**SECTIONS**
1. **Product hero** `grid grid-cols-1 lg:grid-cols-12 gap-gutter mb-20`.
   - Gallery `lg:col-span-7` (§24 product bento): main image with hover zoom ×1.8 (JS) plus 4 thumbnails (+4).
   - Info `lg:col-span-5 flex flex-col`:
     - Chips row: IN STOCK (lime pill) + "SKU: BK-NX7-CF" mono.
     - H1 "NX7 Ultra-Poly Carbon" (intended 48px display; renders 16px).
     - Stars in `text-primary` (4 filled + half via `FILL 0.5`) + "(128 Reviews)".
     - Description body-lg `leading-relaxed mb-6`.
     - Price "$189.00" (intended 48px primary) + strike "$245.00".
     - Spec grid 2×2 (§25): MATERIAL PA12-CF Nylon; STRENGTH 85 MPa Tensile; HEAT DEFLECTION 175°C @ 0.45MPa; PRECISION ± 0.05mm.
     - Actions `mt-auto flex-col gap-4`: stepper (§26 square) + "ADD TO CART" (`flex-1 bg-gradient-to-r from-primary to-primary-container py-4 rounded-lg shadow-lg hover:shadow-xl hover:scale-[1.02] active:scale-[0.98]`), then full-width outline "DOWNLOAD DATASHEET (PDF)" (`hover:bg-primary-fixed`).
2. **Material Engineering** `mt-32`, `flex flex-col md:flex-row gap-12 items-start`.
   - Left `md:w-1/3 sticky top-24`: H2 (intended 32px), paragraph, checklist (`check_circle` primary + text, `space-y-4`).
   - Right `md:w-2/3 grid md:grid-cols-2 gap-6`: 2 feature cards (thermostat Thermal Resistance; precision_manufacturing Isotropic Strength) + full-width case-study image card (`md:col-span-2 h-80 rounded-2xl`, "Case Study: Automotive Prototyping").
3. **Verified Performance** `mt-32`: split header + "WRITE A REVIEW" tonal pill. Grid `md:grid-cols-3 gap-6` of 3 review cards (§15) with initials avatars MS (primary), JH (secondary), DK (tertiary). Card 3 has 4 stars.
4. **Recommended Pairings** `mt-32`: H2 `mb-12`. Grid `grid-cols-2 lg:grid-cols-4 gap-6` of compact cards (§11d): Supra-Temp Support $75, Hardened Steel Nozzle Kit $32, Planetary Gearbox STL $12 (`visibility` icon instead of cart), Active Dry-Vault X1 $299.
**FOOTER** `bg-surface-container-lowest border-t mt-24`. 4 columns: Brand + 2 social; Catalog; Company; Newsletter stacked with SUBSCRIBE. Bottom bar: © + Privacy/Terms `text-[14px]`.
**RESPONSIVE** Hero stacks <lg (gallery on top); main image square <md, 16:9 ≥md. Engineering section stacks <md (the sticky column becomes static). Reviews 1 column <md. Pairings 2 columns → 4 at lg.
**QUIRKS / DEFECTS** The zoom `div` lacks `bg-cover` (the image tiles), and headings render 16px. **Recommendation:** fix both.

## S5 · STL Details
**SOURCE** `stl_details_planetary_gear_system_bekaa3d_digital/code.html` · `<html class="scroll-smooth">`
**OVERALL LAYOUT** Nav (64px) plus `main.pt-24.pb-20.max-w-spacing-max-width(broken).mx-auto.px-4.md:px-spacing-margin-desktop(broken)` → effectively 16px padding everywhere and no max width.
**HEADER** Nav variant E: `h-16 bg-surface/80 backdrop-blur-xl border-b shadow-sm`. Logo `font-black tracking-tighter text-on-surface`. Mono links Printers · Materials (active) · Software · Support · Industry. Right: search, cart, account_circle buttons (`hover:bg-surface-container`). Container padding is broken, so the logo sits at x=0 (visible).
**SECTIONS**
1. Breadcrumb (§22) "MARKETPLACE › MECHANICAL MODELS › PLANETARY GEAR SYSTEM".
2. **Grid** `lg:grid-cols-12 gap-gutter`.
   - Left `lg:col-span-7 space-y-4`: viewer (§24 STL) + 5 thumbs.
   - Right `lg:col-span-5 space-y-6`:
     - Info card `bg-surface-container-lowest p-8 rounded-xl border-outline-variant/20 shadow-sm space-y-6`: title row (H1 headline-lg + favourite icon button), price $49.00 `text-2xl` + COMMERCIAL LICENSE chip (lime, `text-[11px] rounded`), description, 2×2 spec tiles (File Formats STL, STEP, SLDPRT; File Size 45 MB; Layer Height 0.12mm Recommended; Print Time 4h 12m (Est.)), "COMPATIBLE PRINTERS" chips.
     - CTAs: full-width gradient "BUY NOW & DOWNLOAD" (`download` icon, `shadow-lg shadow-primary/20`) + 2-col "MAKE AN OFFER" (2px `outline-variant/30`) / "WHATSAPP" (green outline). Stat strip: 1,240 Downloads | 4.9/5 Rating | Instant Delivery.
     - Secure Download callout (§56).
3. **Tabs** `mt-16` (§23).
4. **Description** `mt-8 grid md:grid-cols-3 gap-12`. Left `md:col-span-2 space-y-6`: "Engineering Details" headline-md, paragraph, 3 check items (18px primary icons). Right: "Review Summary" (§15 snippet).
5. **Related STL Files** `mt-24 space-y-8`: split header (H2 headline-lg + subtitle; link "VIEW ALL DESIGNS →" mono primary). Grid `sm:grid-cols-2 lg:grid-cols-4 gap-gutter` of related cards (§12c): Worm Gear Drive $24, Dual Axis Gimbal $32, 2020 Corner Bracket FREE, Modular Spool Rack $15.
**FOOTER** `bg-surface-container-highest border-t`, 4 columns (`py-12`). Brand + terminal/share icons; Products, Resources, Legal (links mono caps 12px, `hover:underline decoration-primary decoration-2`). Bottom bar mono 10px: © left, "PROUDLY MADE FOR THE DIGITAL FORGE." right.
**RESPONSIVE** Grid stacks <lg. Description stacks <md. Related 1 → 2 (sm) → 4 (lg). Nav links hidden <md.
**QUIRKS** Container/padding tokens are broken (flush left). A FAB is commented out.

## S6 · Your Cart
**SOURCE** `your_cart_bekaa3d_precision_engineering/code.html`
**OVERALL LAYOUT** Nav (`h-16 max-w-[1440px] px-margin-desktop`) plus `main.pt-32.pb-24.max-w-[1440px].mx-auto.px-margin-mobile.md:px-margin-desktop`.
**HEADER** Nav variant D: logo extrabold primary; links Marketplace, Services, Materials, Showcase, Support (none active). Cart icon `text-primary` with a `bg-secondary` badge "2"; person icon. JS toggles the nav shadow on scroll.
**SECTIONS**
1. Page header `mb-12`: H1 "Your Cart" (display) + "Review your selection of precision hardware and digital assets." (body-md).
2. Grid `lg:grid-cols-12 gap-gutter items-start`.
   - `section lg:col-span-8 space-y-4`: 2 cart line items (§36). The physical item "NX7 Ultra-Poly Carbon Filament" $59.00 has a stepper. The digital item "Planetary Gear System STL" $14.50 shows "Fixed Quantity" and a download badge.
   - `aside lg:col-span-4`: Order Summary (§35 cart). Subtotal $73.50, Shipping (Standard) $8.00, Estimated Tax $5.88, TOTAL DUE $87.38. Discount Code input (placeholder PRECISION20) + Apply. "Proceed to Checkout →". Payment icons.
3. **Frequently Bought Together** `mt-24`: split header with circular arrow buttons. Grid `md:grid-cols-3 lg:grid-cols-4 gap-gutter` of compact cards (§11d). The 4th card is `hidden lg:block`.
**FOOTER** `py-16 bg-surface-container-lowest border-t`, 4 columns: brand + "© 2024 Bekaa3D. Precision in every layer."; Company / Legal / Shipping (mono 10px headings, underlined links).
**RESPONSIVE** <lg: summary below items (stops being sticky in effect). <md: line items stack vertically and center (image full width, 128px tall). Suggestions 1 column → 3 (md) → 4 (lg).
**DEFECT** The Apply button overflows the summary card. **Recommendation:** `min-w-0` on the input.

## S7 · Checkout
**SOURCE** `checkout_bekaa3d_precision_engineering/code.html`
**OVERALL LAYOUT** Reduced header plus `main.pt-24.pb-16.max-w-[1440px].mx-auto.px-margin-desktop`, grid `lg:grid-cols-12 gap-12`.
**HEADER** Variant F (logo + "SECURE CHECKOUT" with lock). No nav links, no cart.
**SECTIONS**
- Left `lg:col-span-7 space-y-12`:
  1. Step 1 Shipping Information (§33). Grid `md:grid-cols-2 gap-6`: Full Name (span 2), Shipping Address (span 2), City, Country (select), Postal Code. Inputs `p-4 bg-white border-outline-variant rounded-lg`. Focus: CSS `border-color:#0d631b; box-shadow:0 0 0 2px rgba(13,99,27,.1)`, and JS scales the parent wrapper by 1.01.
  2. Step 2 Billing Details: checkbox "Billing address is the same as shipping" (checked).
  3. Step 3 Payment Method `space-y-4`: Credit Card selected card (§34) with Card Number (lock icon), Expiry, CVC (password). Then the PayPal option.
- Right `lg:col-span-5`, `sticky top-24 space-y-6`: Order Summary (§35 checkout) with 2 items (NX7 Filament $89.00, Planetary Gear System STL $24.00); Subtotal $113.00, Shipping FREE chip, Tax $9.04, Total Due $122.04 (green); COMPLETE PURCHASE; legal note. Trust tiles 3-up (§37).
**FOOTER** `bg-surface-container-lowest border-t py-16`. 4 columns (mono primary headings Company / Support / Legal). Bottom bar mono uppercase: © + language "English (CH)".
**RESPONSIVE** <lg: summary stacks below the form. Form rows are 1 column <md.
**NOTE** The FREE shipping chip uses `text-secondary-container` (lime) on `on-secondary-container/10`: low contrast (visible as pale lime). **Recommendation:** `text-on-secondary-container bg-secondary-container`.

## S8 · About Us
**SOURCE** `about_us_bekaa3d_engineering/code.html` · `<html class="scroll-smooth">` · JS fades every `section > div` in (`opacity-0 translate-y-10` → visible, 1000ms) via IntersectionObserver (threshold 0.1).
**OVERALL LAYOUT** Nav (64px) plus `main.pt-16`. Every container uses broken tokens (no max width, 0 padding), so content is flush to the viewport's left edge in the screenshot.
**HEADER** Nav variant E (mono links, Industry active). Right: cart, account_circle.
**SECTIONS**
1. **Hero** `h-[819px] flex items-center`: background image (no `bg-cover`) + left gradient `from-on-surface/80`. Content `max-w-2xl`: eyebrow "ESTABLISHED 2014", H1 "Engineering the future of manufacturing." white display, body-lg `text-surface-container-low`, buttons "CONSULT AN ENGINEER" (btn-gradient) + "VIEW CAPABILITIES" (white/30 border).
2. **Story** `py-24 bg-surface`: `md:grid-cols-2 gap-16 items-center`. Text (order 2 on mobile): H2 headline-lg `mb-8` "From a single prototype to a global fleet." + 3 paragraphs `space-y-6`. Image (order 1): `aspect-square rounded-2xl shadow-xl` with `bg-primary/10` overlay.
3. **Mission & Vision** `py-24 bg-surface-container-low`, `md:grid-cols-2 gap-8`.
   - Mission card: `bg-white p-12 rounded-2xl shadow-sm border-outline-variant/30 hover:border-primary`, filled `precision_manufacturing` 36px primary, H3 headline-lg. Growing rule at the bottom (`h-1 w-24 bg-primary/20` → full width on hover).
   - Vision card: `bg-inverse-surface`, `auto_awesome` in `inverse-primary`, white title, `text-surface-variant` body, rule `bg-inverse-primary/20`.
4. **Technical Capabilities** `py-24 bg-surface`. Centered header. Bento `md:grid-cols-3 gap-6`:
   - (a) `md:col-span-2` white card `p-8 flex md:flex-row gap-8`: eyebrow "THE HARDWARE", "Industrial Bambu Fleet", spec pills, square image `md:w-64`.
   - (b) "Material Science" `bg-surface-container-highest p-8` with a mono primary checklist.
   - (c) "Surface Fidelity" white card + image `h-32 rounded-lg`.
   - (d) `md:col-span-2 bg-inverse-surface text-white` "DfAM Consultation" + "LEARN MORE" `text-primary-fixed` (empty image div).
5. **Stats band** (§53): 10k+ Projects Delivered · 99.9% Precision Rate · 50+ Industrial Materials · 24h Global Dispatch.
6. **The Engineering Mindset** `py-24 bg-surface`: split header (H2 + "JOIN OUR TEAM" outline, hidden <md). Grid `sm:grid-cols-2 lg:grid-cols-4 gap-8` team cards: `aspect-[4/5] rounded-xl shadow-sm` image (zoom 105), name `font-headline-md text-headline-md`, role mono 10px primary `tracking-widest uppercase`.
7. **Portfolio of Precision** `py-24 bg-surface-container-low`: H2 centered `mb-12`. `.masonry-grid` (`grid-template-columns: repeat(auto-fill, minmax(300px,1fr)); grid-auto-rows:200px; gap:24px`). Items 1 and 4 span 2 rows. `rounded-2xl shadow-md`.
8. **CTA** `py-24`: About CTA panel (§52) "Scale your production."
**FOOTER** `bg-surface-container-highest border-t`, 4 columns (`py-12`): brand + 2 circle buttons (`bg-surface-container hover:bg-primary`); Solutions / Resources / Legal (mono primary headings; © in the Legal column `text-[10px] mt-8`).
**RESPONSIVE** Hero text stays left. Story stacks with the image first. Cards 1 column <md. Team 1 → 2 (sm) → 4 (lg). Stats 2 → 4 columns.
**DEFECTS** Hero image repeats; container padding is missing; the DfAM image is empty.

## S9 · Contact Us
**SOURCE** `contact_us_bekaa3d_inquiry/code.html` · scroll-smooth
**OVERALL LAYOUT** Nav (64px, variant E) plus `main.pt-32.pb-24`. Broken container tokens (flush layout, same as S8).
**SECTIONS**
1. **Hero** `mb-20`: boxed hero (§9) "Contact Our Engineering Team" + 4h response pill.
2. **Main** `grid lg:grid-cols-12 gap-gutter`.
   - Form card `lg:col-span-7 bg-surface-container-lowest rounded-xl p-8 md:p-12 shadow-sm border-outline-variant/30`: H2 "Submit an Inquiry" + subtitle `mb-8`. Form `space-y-6`: Full Name | Company (Optional) (`md:grid-cols-2 gap-6`), Email, Subject (select: Technical Hardware Support, Material Science Consultation, Enterprise Licensing Inquiry, Custom Manufacturing Quote, General Question), Message (textarea rows 5), submit "Send Message" (`green-gradient-btn w-full md:w-auto px-10 py-4 tracking-widest` + `send`). Inputs `px-4 py-3 bg-surface-container-low` with `.input-focus-effect` (border `#2e7d32` + 2px glow). JS shows loading/sent states.
   - Right `lg:col-span-5 space-y-gutter`:
     - "Direct Channels" card (`bg-surface-container p-8 rounded-xl`): 3 rows (`flex items-start gap-4 group`; 40px `bg-surface-container-highest rounded-lg` icon tile, `group-hover:bg-primary text-on-primary`) Technical Email, WhatsApp Business (filled chat), Headquarters (call). Divider. Business hours row with a pulsing "OPEN NOW".
     - Map card: `h-48` map image (grayscale → colour on hover, `bg-primary/10` overlay) + address block + 2 circle buttons.
     - "Join the Community" bar with 3 SVG social icons.
3. **FAQ** `mt-32`: centered H2 + 80×4px green rule; 3 accordions (§51) `max-w-3xl`.
**FOOTER** `bg-surface-container-highest border-t py-12`, 4 columns; brand column holds the © (mono). Solutions / Resources / Legal headings in mono primary uppercase `mb-6`.
**RESPONSIVE** Right column stacks under the form <lg. Name/company 1 column <md. Submit full width <md.

---

# Auth pages

## A1 · User Login
**SOURCE** `user_login_bekaa3d_precision_engineering/code.html`
**LAYOUT** `body min-h-screen flex items-center justify-center technical-pattern` (padding tokens broken → 0). `main w-full max-w-[440px] z-10`.
**CONTENT** Login auth card (§38). Fields: Email Address (`mail` icon, placeholder engineer@bekaa3d.com), Password (`lock` icon, visibility toggle). Remember Me / Forgot Password? row. "LOGIN TO DASHBOARD" (`.brand-gradient`, hover gradient `#388e3c→#2e7d32`). Divider "OR CONTINUE WITH". Google / Facebook buttons. Footer strip "New to the platform? Create Account". Below the card: status bar (opacity 60%). Decorative fixed schematic images at 2–3% opacity (lg+).
**JS** Password toggle swaps `visibility`/`visibility_off`. On focus, the field's label turns `#0d631b`.
**RESPONSIVE** Card stays 440px max, full width on mobile. Decorative images hidden <lg.

## A2 · User Registration
**SOURCE** `user_registration_bekaa3d_precision_engineering/code.html` (**no fontSize config**)
**LAYOUT** Fixed `.bg-blueprint` layer (`-z-10`). `main min-h-screen flex items-center justify-center px-margin-mobile md:px-margin-desktop py-12`. Card `max-w-[640px]` (§38 register).
**FORM** Row 1: First Name | Last Name. Row 2: Email Address | Phone Number. Country / Region select (US, DE, LB, AE, UK, CA). Row 3: Password | Confirm Password. Every input is `h-12`. Terms checkbox with links. "CREATE ACCOUNT →" (`h-14 bg-primary hover:bg-secondary`). "Already have an account? Login".
**OVERLAY** The success overlay (§48) appears on submit for 3s.
**AS RENDERED** H2 "Create Professional Account" and the labels render at 16px. Labels render as mixed-case mono (e.g. "First Name") because no `uppercase` is applied.
**RECOMMENDATION** Apply the token sizes and uppercase the mono labels.
**RESPONSIVE** 2-column rows become 1 column <md; padding drops from `p-12` to `p-8`.

## A3 · Forgot Password
**SOURCE** `forgot_password_bekaa3d_precision_engineering/code.html`
**LAYOUT** `body blueprint-bg min-h-screen flex flex-col items-center justify-center p-margin-mobile md:p-0`. Fixed header logo at `top-8` (left-aligned ≥md inside `max-w-[1440px] px-margin-desktop`). `main max-w-[1440px] flex justify-center relative` with rotating rings behind. Card (§38 forgot) `max-w-md`.
**CONTENT** H1 "Reset Password" (headline-lg); paragraph; EMAIL ADDRESS field; "SEND RECOVERY LINK →"; divider; "BACK TO LOGIN" with `keyboard_backspace`. Side image card (xl+): grayscale nozzle photo with `bg-primary/10 mix-blend-multiply` and caption "HIGH-FIDELITY CALIBRATION" (mono 10px `tracking-[0.2em]` right-aligned). Fixed footer copyright `py-8`.
**JS** Background position follows the mouse (parallax up to 10px). Submit gains a green glow once the email looks valid.

## A4 · Admin Login
**SOURCE** `admin_login_bekaa3d_operations_console/code.html`
**LAYOUT** `body blueprint-grid min-h-screen flex flex-col items-center justify-center px-margin-mobile md:px-0` + 2 fixed blurred orbs (500px / 400px `bg-primary/5`). `main max-w-[1100px]` split card (§38 admin). Footer below the card `mt-8` (mono 10px `tracking-[0.2em]`, `on-surface-variant/40`).
**FORM** Admin Email (`alternate_email` label icon), Password (`lock_open`) + "Forgot Password?" mono primary, visibility toggle. "LOGIN TO CONSOLE" + `login` icon. Indicators: pulsing glow dot + "Secure Encrypted Connection" · "V2.4.0 Stable".
**JS** Submit shows a spinner SVG (loading state).
**RESPONSIVE** The left panel is hidden <md; the right panel goes full width with `p-8`. Header logo and title center <md.

---

# Customer account pages

Shared shell (C2–C7): fixed sidebar (§40, customer variant) 256px; main `ml-64` (`md:ml-64` where the sidebar collapses on mobile). No site footer except C1 and C5.

## C1 · Account Dashboard
**SOURCE** `account_dashboard_bekaa3d/code.html` (body has no bg class; the `<style>` sets `#f9f9ff` + Inter)
**SIDEBAR** `w-64 fixed inset-y-0 bg-surface-container-lowest border-r border-outline-variant/30 hidden md:flex`. Logo `p-8`. Nav `px-4 space-y-2`: Dashboard (active gradient pill), Orders, Downloads, Wishlist, Reviews, Profile, Notifications (20px icons, `rounded-xl px-4 py-3`). Bottom user chip (EV initials, "Dr. Elena Vance", "INDUSTRIAL TIER").
**HEADER** `glass-header sticky top-0 z-40 h-20 px-8 border-b` (§41 acct-dash).
**CONTENT** `p-8 max-w-[1440px] mx-auto space-y-8`:
1. KPI row `sm:grid-cols-2 lg:grid-cols-4 gap-6` (§42 label-top): TOTAL ORDERS 124 (+3 this month, primary); ACTIVE DOWNLOADS 18 (files ready); REWARD POINTS 4,250 (Platinum status, secondary); ACCOUNT TIER brand card "Industrial" + verified "Priority Manufacturing".
2. Recent Physical Orders: header row (headline-md + "View All Orders" link) + table card (§43). Columns ORDER ID / ITEM DETAILS (40px icon tile + name + material) / DATE / STATUS / ACTION. Statuses: IN PRODUCTION (`primary-container/10`, `text-primary-container`, bordered), SHIPPED (secondary), DELIVERED (neutral). Actions are text buttons Track / Invoices.
3. Digital Assets Library: header + "Manage All" (`grid_view`). 4-col asset cards (§12e).
4. Two-column `lg:grid-cols-2 gap-8`: Recent File Access + B2B Licensing Negotiations (§45).
5. Account info band `bg-surface-container-low p-8 rounded-3xl border-outline-variant/20`, `md:grid-cols-3 gap-8`: PROFILE DETAILS, DEFAULT SHIPPING, BILLING & CURRENCY (card line + "EDIT ACCOUNT SETTINGS" outline pill).
**FOOTER** Inside main: `py-16 bg-surface-container-lowest border-t`, 4 columns (QUICK LINKS / SUPPORT / NEWSLETTER with joined input+SUB).
**MOBILE** Sidebar hidden; bottom nav (§54) Home / Orders / Files / Profile. Header stays (may be crowded; consider hiding the subtitle).
**JS** `.card-shadow` cards lift 2px on hover.

## C2 · Order History
**SOURCE** `order_history_bekaa3d_precision_management/code.html` · body `.blueprint-bg` (3% green lines, 20px)
**HEADER** Full-width fixed `bg-white/80 backdrop-blur-xl border-b border-outline-variant px-margin-desktop py-4` (spans over the sidebar). Logo left; right: search pill (`w-64 rounded-full`, trailing icon), notifications, help, 40px avatar.
**SIDEBAR** `h-screen w-64 fixed bg-surface border-r py-24 px-unit-gutter(broken)`. Items: Profile, **Orders (active)**, STL Downloads, Wishlist, Reviews, Offers, Account Settings; Logout (`mt-auto`, hover `bg-error-container text-error`).
**CONTENT** `main ml-64 pt-24 px-margin-desktop pb-12` → `max-w-max-width mx-auto`:
1. Title: H1 headline-lg "Order History" + body-lg description `mb-8`.
2. Filter panel (§63 glass).
3. Table card `bg-white rounded-xl border border-outline-variant shadow-sm`. Columns ORDER ID (mono primary bold BK-72841…) · DATE · STATUS (Delivered `secondary-container`; Shipped `surface-container-high` + `on-primary-fixed-variant`; Pending `tertiary-fixed`; Cancelled `error-container`. Chip `px-2.5 py-0.5 text-xs font-medium rounded-full`) · TOTAL PRICE (mono bold) · PAYMENT (dot + Paid/Processing/Refunded) · ACTIONS ("VIEW DETAILS" primary `px-4 py-2 rounded-lg`). Rows `py-5`, hover `bg-surface-bright`. Footer pagination (bordered, `font-label-caps`).
4. `mt-12 md:grid-cols-3 gap-8`: Live Factory Feed glass card (`border-primary`, `precision_manufacturing` in a 48px `bg-primary-fixed` tile, "ENTER CONTROL VIEW" 2px outline) + `md:col-span-2` image promo "Precision Guaranteed" (`h-64`).
**RESPONSIVE** Not responsive (sidebar always shown). The search hides <md.

## C3 · Offer History
**SOURCE** `offer_history_bekaa3d_precision_management/code.html` · scrollbar 8px (`#f1f1f1` track)
**SIDEBAR** `bg-surface py-8 px-6`, logo + "Engineering Precision" (`text-sm opacity-70`). Items with **Offers active**. Logout in `text-error` under a border.
**CONTENT** `main ml-64 min-h-screen p-12 max-w-[1440px]` (no top bar):
1. Header `mb-10`: H2 headline-lg "Offer History" + body-lg `max-w-2xl`.
2. KPIs `md:grid-cols-3 gap-6 mb-12` (§42 value + icon right): Active Offers 04 (primary, `bolt`), Accepted Offers 12 (secondary, `check_circle`), Total Savings $184.50 (tertiary, `payments`).
3. Table `section bg-white rounded-xl shadow-[0px_4px_32px_rgba(0,0,0,0.02)] border-outline-variant/30`. Header `py-5` (labels in mixed case: "STL Asset", "Original"…). Rows: 48px thumb + title `text-sm font-semibold`; Original `font-mono`; Your Offer `font-bold text-primary`; Status `.status-badge` (mono 10px uppercase) Counter Offer (blue-100/700), Accepted (green-100/700), Pending (amber-100/700), Rejected (red-100/700); Seller Response italic; Date; Actions (Accept Counter primary + `more_vert`; View Receipt outline; Withdraw error ghost; Locked disabled). Pagination compact 32px.
4. Help strip (§56).
**JS** Rows translate 4px right on hover; summary cards get a subtle parallax.

## C4 · My Reviews
**SOURCE** `my_reviews_bekaa3d_precision_management/code.html` · body grid of `rgba(203,255,194,0.05)` lines, 40px
**SIDEBAR** `bg-surface py-8 px-6`. Items `p-3` with **Reviews active** (filled icon). Settings/Logout group under `border-t`. Bottom user chip (avatar, "Alex Chen", "Premium Account").
**HEADER** `sticky top-0 z-40 glass-panel border-b px-margin-desktop py-6`. Left: H2 "My Reviews" headline-lg + subtitle. Right: search (`w-64 md:w-80`) + sort select with `expand_more`.
**CONTENT** `section p-margin-desktop max-w-max-width mx-auto`:
1. Stats `md:grid-cols-3 gap-gutter mb-12` (§42 icon-left): Total Reviews 24 (`reviews` on primary-container tile), Average Rating 4.8 (`star` on secondary-container), Helpful Votes 142 (`visibility`). Labels use `text-label-caps` without `font-label-caps`, so they render in Inter.
2. Review cards `space-y-6` (§62) ×3.
3. Pagination footer `mt-12 border-t pt-8` (bordered 40px).

## C5 · My Wishlist
**SOURCE** `my_wishlist_bekaa3d_precision_engineering/code.html`
**SIDEBAR** `hidden md:flex`, **Wishlist active** (filled heart). The Profile icon is `text-primary` even though it is inactive (quirk).
**HEADER** `sticky top-0 z-30 px-8 py-4 bg-white/80 backdrop-blur-xl border-b`: mobile menu button (<md), eyebrow "Portal / Wishlist" (md+); right: search (sm+, expands on focus), notifications, "BK" initials 32px avatar.
**CONTENT** `main md:ml-64 relative` with `.grid-pattern` overlay at 50%:
1. Header `px-8 pt-12 pb-6`: H2 "My Wishlist" (`font-display font-bold text-headline-lg`) + description.
2. Bar `px-8 pb-8` → `py-4 border-y`: "Showing 6 items" mono + divider + "Filter" button; right "Sort by:" + borderless primary select.
3. Grid `px-8 pb-20` → `sm:grid-cols-2 lg:grid-cols-3 gap-gutter` of 6 wishlist cards (§11c): Titanium X-Gen Nozzle Kit $124 (In Stock), CarbonFiber Pro 1.75mm $89.50, Ultra-Glide Linear Rail V3 $210, Quantum Logic Mainboard $345, Textured PEI Build Plate $45 / $56 (20% OFF), High-Torque Stepper Motor $32.90. Hidden empty state (§49).
4. Footer strip `px-8 py-12 border-t bg-surface-container-low/50`: "Need help?" + "Share Wishlist" (outline) / "Add All to Cart" (`bg-on-background`).
**MOBILE** Bottom nav: Home / Search / Wishlist (active) / Cart / Account.

## C6 · My STL Library (Purchased downloads)
**SOURCE** `purchased_stl_downloads_bekaa3d_digital_library/code.html`
**SIDEBAR** `hidden md:flex`, **STL Downloads active** (`rounded-l-lg`, filled icon). Logout `text-error hover:bg-error-container`.
**WRAPPER** `md:ml-64 flex flex-col min-h-screen blueprint-bg`. Header `sticky top-0 px-8 py-4 bg-white/80 glass-panel border-b`: search `max-w-md rounded-full` (md+); right: notifications (red dot), help, divider, "ENGINEER #042 / Pro Tier" + 40px avatar `border-2 border-primary`.
**CONTENT** `main p-8 lg:p-12 max-w-[1440px]`:
1. H2 "My STL Library" (`font-display text-headline-lg`) + body-lg `max-w-2xl` `mb-12`.
2. Filter bar (§20 library).
3. Grid `md:grid-cols-2 xl:grid-cols-3 gap-8` of 3 library cards (§12d): Planetary Gear System V4 (Commercial, v4.2.0, 42.5 MB, 3 Downloads); Turbine Housing Assembly (Personal, Never Downloaded); Prosthetic Joint Modular (Commercial, 12 Downloads). Hidden empty state "No files matching your search".
**FOOTER** Meta footer `p-8 border-t bg-white/50` mono xs uppercase `text-outline`: © + Privacy Protocol / Usage License / Technical Support.
**JS** Live title filter that toggles the empty state.

## C7 · User Profile
**SOURCE** `user_profile_bekaa3d_precision_management/code.html` · body `.blueprint-bg` (green 40px)
**SIDEBAR** `hidden md:flex py-10 px-6`. Items with **Profile active** (no radius). Labels use `font-headline-md text-body-md` (Hanken 16px).
**HEADER** `sticky px-8 py-4 bg-white/80 backdrop-blur-xl`: search `max-w-xl rounded-full bg-surface-container border-none`; right: notifications, help, avatar.
**CONTENT** `main p-8 max-w-[1440px]` → `grid lg:grid-cols-12 gap-8`. Every card is `bg-white rounded-lg shadow-sm border border-outline-variant` (8px radius).
1. `lg:col-span-12` profile header `p-8 flex md:flex-row items-center gap-8`: 128px avatar + camera button; name "Alexander Wright" (`font-display text-headline-lg`) + PRO MEMBER badge; "Lead Mechanical Engineer" body-lg; mono "MEMBER SINCE MARCH 2023". Buttons "PUBLIC PROFILE" (primary) / "SHARE" (outline). Watermark icon 240px at 3% (10% on hover).
2. `col-span-7` Personal Information: title with icon + EDIT link. 2×2 read-only fields (mono 11px labels, underline values).
3. `col-span-5` Primary Address: address box (`bg-surface-container p-4 rounded-lg border`) with DEFAULT tag + dashed "ADD NEW ADDRESS".
4. `col-span-6` Security & Authentication: Current Password; New | Confirm (2 columns); "UPDATE PASSWORD" full-width primary `py-4`.
5. `col-span-6` Account Preferences: 4 toggle rows (§29): Email Notifications ✓, Order Updates ✓, Marketing News, Two-Factor Authentication (red helper).
**MOBILE** Bottom nav: Profile / Orders / STL / Settings (uppercase labels).

---

# Admin console pages

## D1 · Admin Dashboard (Operational Overview) — *canonical admin shell*
**SOURCE** `admin_dashboard_bekaa3d_operations/code.html`
**SIDEBAR** `#sidebar h-screen w-64 fixed bg-surface border-r border-outline-variant` → inner `py-8 px-6`. Tile logo (§2). Nav `space-y-1 overflow-y-auto` with items `px-4 py-3` (no radius) + **Dashboard active** (`border-r-4`, filled icon, `bg-surface-container-low`). Items: Physical Products (`inventory_2`), STL Files (`layers`), Categories, Orders, Customers, Reviews, Offers, Discounts (`percent`), Analytics. Bottom section under a border: Settings, Logout (error). JS collapses the sidebar to 80px.
**HEADER** `sticky top-0 z-40 bg-white/80 backdrop-blur-xl border-b px-12 py-4`: `menu_open` toggle, search `max-w-md` (borderless tinted); right: notifications (dot), help_outline, divider, "ADMIN USER / System Engineer" + avatar with a ring.
**CANVAS** `main ml-64 min-h-screen grid-bg` (dot grid 40px) → `px-12 py-8 max-w-[1440px] mx-auto`:
1. H2 "Operational Overview" (headline-lg) + description `mb-8`.
2. KPI row `md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-6 mb-10` (§42 icon-top, glass). Total Sales 1,284 (+12%), Revenue $42,910 (+8.4%), Orders 452 (-2%, error chip), STL Downloads 3,109 (+24%), Active Users 892 (+15%), Pending Offers 18 (New).
3. `lg:grid-cols-3 gap-8 mb-10`: bar chart card `lg:col-span-2 glass-panel p-8 rounded-2xl` (§44) + Marketplace donut card.
4. `xl:grid-cols-4 gap-8`: Recent Orders table `xl:col-span-3 glass-panel rounded-2xl` (header `px-8 py-6`; mono 13px IDs; 28px avatars; status chips Delivered `primary-fixed-dim`, Shipped `secondary-fixed`, Processing `surface-container-high`; totals right bold) + System Logs (§45).
**FAB** §55 with tooltip.

## D2 · Admin Console (Dashboard Overview, app-shell variant)
**SOURCE** `admin_console_bekaa3d_operations/code.html` · body `overflow-hidden h-screen flex`
**SIDEBAR** In-flow `w-64 h-full bg-surface-container-low border-r border-outline-variant/30`. Logo `p-6` + "PRECISION CONSOLE". Nav `px-4` with **Dashboard active** (`bg-primary-container text-on-primary-container` pill). Group labels "INVENTORY" (Physical Products `precision_manufacturing`, STL Files `model_training`, Categories) and "SALES & CRM" (Orders, Offers `request_quote`, Discounts, Reviews, Customers). Footer: Settings + user chip JD "Jane Doe / Admin Lead".
**MAIN** `flex-1 flex flex-col h-full overflow-hidden`. Header `h-16 px-8 bg-surface/80 backdrop-blur-md border-b border-outline-variant/20`: "Dashboard Overview" (`font-headline-md`, renders 16px) + divider + date; right: search pill (lg+), notification button (toggles panel), help. Scroll area `flex-1 overflow-y-auto p-8 custom-scrollbar`:
1. Quick actions `flex flex-wrap gap-4 mb-8`: ADD PRODUCT (primary), UPLOAD STL (lime tonal), CREATE DISCOUNT, GENERATE REPORT (surface-container-highest).
2. KPI row `lg:grid-cols-5 gap-6` (§42 icon-top, white): Revenue (MTD) $42,850.00, Total Orders 1,204, Sales Growth 18.5%, STL Downloads 8,492, Active Offers 14.
3. `lg:grid-cols-3 gap-8`: Revenue Performance bars (Weekly/Monthly toggle; May–Oct) + Sales Mix (progress bars + insight).
4. Recent Activity table: columns Asset/Product, Type (PHYSICAL / DIGITAL chips), Customer, Status (dot + text), Value (mono), Action (`more_vert`).
5. Notification panel (§46).

## D3 · Admin Analytics
**SOURCE** `admin_analytics_bekaa3d_operations_console/code.html` · loads `https://cdn.jsdelivr.net/npm/chart.js` · body `blueprint-grid` (`#bfcaba22`, 24px)
**SIDEBAR** `bg-surface-container-lowest border-r z-[60]`: "Bekaa3D Admin" / "Precision Control"; "New Print Job" CTA (`bg-primary-container py-3 rounded-lg`); nav `px-2` Dashboard, Orders, Inventory, Customers, **Analytics active** (`bg-surface-variant/30`), Settings; footer Help Center, Logout.
**HEADER** `sticky h-16 glass-panel border-b px-8`: "Bekaa3D Manufacturing" (headline-md bold primary) + search `max-w-md rounded-full`; right: notifications, print, mail, divider, "Alex Thompson / Sr. Operations Manager" + avatar `border-primary`.
**CONTENT** `p-8 space-y-8 max-w-[1440px]`:
1. Title row: eyebrow "OPERATIONAL INTELLIGENCE" + H1 "Analytics Dashboard" (`font-display text-headline-lg`); buttons "Last 30 Days" (outline + `calendar_today`) / "Export Report" (primary + glow).
2. KPI `md:grid-cols-2 lg:grid-cols-4 gap-6` (§42 square, `rounded-none`): Total Revenue $248,392.00, Conversion Rate 4.82%, Active Customers 18,521, STL Downloads 142,890.
3. `xl:grid-cols-3 gap-6`: Revenue Performance line chart (`xl:col-span-2`, legend dots) + Sales by Category doughnut with legend.
4. `lg:grid-cols-2 gap-6`: Most Sold Physical Products table (thumb, Units Sold mono, Revenue bold, Trend icon) + Top STL Downloads (file icon, downloads mono, amber stars, `more_vert`).
5. `lg:grid-cols-4 gap-6 pb-12`: Sales Trends bar chart (`lg:col-span-3`, Daily/Weekly/Monthly select) + Print Capacity card (`bg-primary text-white p-8 rounded-none`, 84% bar `bg-secondary-fixed`, "Optimize Workflow" white button).
**QUIRK** KPI values use `font-headline-lg` without a size (render 16px). Chart cards have square corners (unique).

## D4 · Manage Physical Products
**SOURCE** `manage_physical_products_bekaa3d_admin/code.html` · body green blueprint grid
**SIDEBAR** Customer-style items (inconsistent; DESIGN-SYSTEM §12.14): Dashboard, **Orders (active)**, STL Downloads, "MANAGEMENT" label, **Physical Products (active)**, Wishlist, Reviews, Offers, Account Settings; Logout. Logo uses the filled `deployed_code` 30px glyph + stacked wordmark.
**HEADER** `sticky px-margin-desktop py-4 bg-white/80 backdrop-blur-xl`: title "Physical Products" (`font-display text-headline-md font-extrabold text-primary`); right: search `w-72` (lg+), 40px round notification/help buttons, divider, "Alex Engineer / SUPER ADMIN" + avatar with `ring-2 ring-primary/20`.
**CONTENT** `p-8 max-w-max-width`:
1. Utility bar (§63): category/status selects + Advanced Filters; "Add Product" (`bg-primary px-6 py-3 font-bold uppercase text-sm tracking-wider shadow-lg shadow-primary/20`).
2. Table `glass-panel rounded-xl border`. Header `text-xs font-label-caps text-outline uppercase tracking-widest`. Columns ☐ / Product (48px thumb + name + SKU) / Category / Price / Discount (chip) / Status (dot pill: In Stock secondary, Low Stock tertiary, Out of Stock error) / Featured (40×20 toggle) / Actions (hover-reveal view/edit/duplicate/delete). Row hover `bg-primary/5` (+ JS `shadow-md`). Footer: Bulk Delete (error) + Export CSV; "Showing 1-10 of 42" + compact pagination.
3. Stat cards `md:grid-cols-4 gap-6 mt-8` (§42 icon-left round): Total SKUs 42, In Stock 36, Low Stock 4, Out of Stock 2.

## D5 · Edit Physical Product
**SOURCE** `edit_physical_product_bekaa3d_admin/code.html` · `.blueprint-grid` overlay at 10% opacity
**SIDEBAR** Items `p-3`: Dashboard, **Products (active)**, STL Downloads, Customers, Reviews, Settings; Logout.
**HEADER** `sticky glass-panel border-b px-12 py-4`: breadcrumb "PRODUCTS › EDIT PRODUCT › VIPER-X EXTRUDER KIT"; right: notifications, help, 40px avatar with a `border-2 border-primary-container` ring.
**CONTENT** `max-w-[1200px] mx-auto px-12 py-10`:
1. Header: H2 "Edit Physical Product" + description. Buttons DELETE PRODUCT (danger outline), DUPLICATE, PREVIEW (2px `border-outline`), UPDATE PRODUCT (`primary-gradient px-8 py-2.5 shadow-lg`).
2. `grid grid-cols-12 gap-8`. All cards `bg-white rounded-xl p-8 border shadow-sm hover:shadow-md`, with a title row (primary icon + `font-headline-md text-headline-md`).
   - Left `lg:col-span-8 space-y-8`: **General Information** (underline inputs: PRODUCT TITLE body-lg, CATEGORY select; DESCRIPTION rich text `h-48`); **Media Management** ("DRAG TO REORDER", §24 admin); **Technical Specifications** (2 columns: underline inputs RECOMMENDED MATERIALS, EST. PRINTING TIME with `timer`; key/value rows WEIGHT 450g, PRECISION 0.05mm, DRIVE RATIO 3:1; "ADD SPECIFICATION" link).
   - Right `lg:col-span-4 space-y-8`: **Inventory & Pricing** (UNIT PRICE `text-2xl font-bold`, DISCOUNT 15, AVAILABILITY dot "In Stock", SKU mono); **Visibility & Status** (3 toggles: Featured ✓, New Arrival, Marketplace Visibility ✓); **SEO Configuration** (META TITLE underline, META DESCRIPTION boxed textarea `h-24`).
3. Meta footer `mt-12` mono 11px `opacity-60`: "PRODUCT ID: BK-EX-001 | LAST MODIFIED…" + ADMIN POLICY / LOG CHANGES.
**JS** Native `confirm()` before deleting an image.

## D6 · Upload Physical Product
**SOURCE** `upload_physical_product_bekaa3d_admin/code.html` · body `blueprint-grid` (24px) · global focus CSS: `border-color:#2e7d32 !important; box-shadow:0 0 0 2px rgba(46,125,50,.2)`
**SIDEBAR** `bg-surface-container-lowest`: Dashboard, **Products (active)**, STL Models, Customers, Reviews, Settings (icons `text-outline group-hover:text-primary`). Bottom user chip "Admin Panel / SUPER USER".
**CONTENT** `main ml-64 p-margin-desktop max-w-max-width` (no top bar):
1. Header: H2 "Upload Physical Product" + breadcrumb "Products › New Product". Buttons SAVE AS DRAFT (1px outline) / PUBLISH PRODUCT (primary `px-8 py-3 shadow-lg`).
2. `grid grid-cols-12 gap-gutter`. Cards `glass-panel p-8|6 rounded-xl shadow-sm` (border `rgba(13,99,27,.1)`).
   - `col-span-8`: General Information (title; category | availability selects; description rich text rows 6); Inventory & Pricing (3 columns: PRICE, DISCOUNT, SKU mono); Technical Specifications (material | print time; "DETAILED SPECS LIST" key/value pairs + dashed "ADD NEW FIELD"); Product Media (dropzone §30 + 4-col thumbs with hover delete/view + add tile).
   - `col-span-4`: Visibility & Status (Featured, New Arrival ✓, hr, LAST UPDATED); SEO Configuration (counters 45/60, 122/160); Organization (BRAND select, TAGS §32); Pro Tip callout.
**QUIRK** Fixed 8/4 columns with no responsive breakpoints.

## D7 · Manage STL Files
**SOURCE** `manage_stl_files_bekaa3d_admin/code.html` · body `.blueprint-bg` (`#e5e7eb` lines)
**SIDEBAR** Customer items with **STL Downloads active** (inconsistent).
**CONTENT** `main ml-64 p-margin-desktop` (no top bar):
1. Header `mb-10`: H2 "Manage STL Files" + description; "ADD NEW STL" (`bg-primary-container text-on-primary py-4 px-8 rounded-lg shadow-lg shadow-primary-container/20`).
2. Stats `md:grid-cols-4 gap-gutter mb-10` (§42 simple): Total STL Files 1,284; Total Downloads 45.2k (+12% ↑); Active Offers 18; Avg. Rating 4.92. Icon tiles `bg-primary-fixed` / `secondary-fixed` / `tertiary-fixed` / `surface-container`.
3. Filter bar (white card `p-4`): search `min-w-[300px]`, Categories select, License select, EXPORT (`ios_share`).
4. Table: ☐ / Preview (64px) / Title & SKU (`font-headline-md`, renders 16px Hanken) / Price (mono) / License chip (Commercial lime, Personal neutral) / Downloads + trend icon / Rating (filled star primary + bold) / Offer chip (Open Offers `tertiary-fixed`, No Offers neutral) / Live toggle / Actions (always visible).
5. Footer bar: Bulk Actions select + APPLY | bordered pagination | "Showing 1-10 of 1,284 assets".

## D8 · Upload STL File
**SOURCE** `upload_stl_file_bekaa3d_admin/code.html` · body `.blueprint-bg` (`#e9edff` lines)
**SIDEBAR** Customer items (inconsistent), STL Downloads active.
**HEADER** Sticky action header `bg-white/80 backdrop-blur-xl px-margin-desktop py-4`: "Upload New Asset" (headline-md) + "Draft Mode" chip; SAVE DRAFT (outline, `rounded` 4px) / PUBLISH (`bg-primary-container text-on-primary-container`, `rounded`).
**CONTENT** `max-w-[1200px] mx-auto px-margin-desktop py-10 space-y-8`. Cards `bg-white rounded-xl shadow-[0_4px_20px_rgba(0,0,0,0.03)] border p-8`, each with a title row (primary icon + headline-md):
1. General Information `grid-cols-12`: left 8 (STL TITLE, DESCRIPTION rich text); right 4 (CATEGORY, PRICE with $ prefix).
2. Technical Specifications `md:grid-cols-3 gap-8`: LICENSE TYPE radio cards (Commercial selected); LAYER HEIGHT + EST. PRINT TIME (HH : MM); COMPATIBLE PRINTERS checklist + FILE SIZE "24.5 MB" (`text-lg font-semibold text-primary`).
3. `grid-cols-12 gap-8`: Asset Upload `lg:col-span-7` (dropzone + upload row with a 100% bar) + Thumbnail `lg:col-span-5` (192px image with hover "CHANGE PHOTO") + Preview Gallery `col-span-12` (`grid-cols-2 md:grid-cols-4 lg:grid-cols-6`: add tile + images, the last at 50% grayscale).
4. `md:grid-cols-2 gap-8`: Marketplace Settings (toggle rows in `p-4 bg-surface rounded-lg`: Enable 'Make an Offer', Featured Product ✓) + SEO Configuration (10px labels, small inputs `p-2 text-sm`).
**FLOATING** Bouncing status pill "System Ready for Processing".

## D9 · Manage Categories
**SOURCE** `manage_categories_bekaa3d_admin/code.html` (**no fontSize config**) · body dot grid
**SIDEBAR** Customer items (inconsistent), STL Downloads active; bottom user chip in a bordered `bg-surface-container-low rounded-xl` box.
**HEADER** `sticky px-12 py-6 bg-white/80 backdrop-blur-xl`: "Categories" (headline-lg primary; renders 16px) + divider + "Management Portal"; right: search `w-64`, "Add Category" (`bg-primary-container text-white px-6 py-2.5 shadow-lg shadow-primary-container/20`), notification and help.
**CONTENT**
1. Controls `px-12 py-8 flex justify-between`: "Bulk Actions" (`layers`) and "Sort by: Date Modified" (`sort`) outline dropdown buttons (white, `rounded-lg text-sm`); italic count text.
2. Grid `px-12 pb-20 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8`: 4 category cards (§57) Mechanical Parts (12), Filaments & Resins (48), Aerospace Models (08), Control Electronics (24) + "Create New Category" dashed tile.
**JS** Drag handle press scales the card by 1.02 with a grabbing cursor.

## D10 · Manage Orders
**SOURCE** `manage_orders_bekaa3d_admin_console/code.html` · scrollbar 6px
**SIDEBAR** `bg-surface-container-lowest`, padding token broken. "Bekaa3D" / "Admin Console". Items `px-6 py-3 space-x-3` (no radius): Dashboard, Physical Products, STL Files, Categories, **Orders active** (`scale-95`). "New Print Job" (`bg-primary text-white`) at the bottom of the nav; "Admin Profile" link under a border.
**HEADER** `fixed top-0 right-0 left-64 h-16 bg-surface/80 backdrop-blur-xl border-b px-gutter`: search `max-w-xl rounded-full`; right: notifications, settings, help, then profile "Alex Mercer / SENIOR ADMIN" + avatar with `border-2 border-primary/20`.
**CONTENT** `main ml-64 mt-16 p-gutter`:
1. Boxed header `blueprint-grid relative p-8 rounded-xl border mb-8`: H2 "Manage Orders" + breadcrumb "Dashboard › Orders".
2. Stats `md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8` (§42 plain): Total Orders 1,842; Pending Fulfillment 56 (+5 urgent, error); Monthly Revenue $24,910.00; Processing Payments 14.
3. Filter bar (§63 compact).
4. Table: Order ID (mono primary) / Customer (32px initials or avatar + name) / Date / Order Status (Processing `primary/10`, Shipped `secondary-container/30`, Pending `surface-variant`, Delivered `outline-variant`) / Payment (filled check "Paid" secondary; `schedule` "Pending" tertiary) / Total (mono bold) / Shipping (underlined DHL link / italic "In Transit" / "Unassigned" / "Delivered" secondary) / Actions centered (view, edit, print, delete). Footer: "Showing 1 to 4 of 1,842 orders" + compact pagination.
5. Meta footer: "BEKAA3D ENGINE V2.4.1 • STATUS: OPTIMAL PERFORMANCE" + links.

## D11 · Manage Customers
**SOURCE** `manage_customers_bekaa3d_admin_console/code.html` · body grid lines `rgba(191,202,186,.1)` 24px
**SIDEBAR** `bg-surface-container-lowest`: "Bekaa3D Admin" + "Precision Control". Items `px-3 py-3` Dashboard, Orders, Inventory, **Customers active** (`bg-surface-container`, no radius), Analytics, Settings. "New Print Job" in a bordered box; Help/Logout as mono 11px links.
**HEADER** `sticky h-16 ml-64 w-full` → **overflows by 256px** (DESIGN-SYSTEM §12.15). Contents: search pill `max-w-md`; right: notifications, print, mail, divider, "Admin User / Systems Engineer" + avatar.
**CONTENT** `main ml-64 p-8 max-w-max-width`:
1. Header: H2 "Manage Customers" (`tracking-tight`) + description; "Add New Customer" (`rounded-xl px-6 py-3`, `person_add`).
2. Metrics `md:grid-cols-2 lg:grid-cols-4 gap-6` (§42 display-number, glass `rounded-2xl`): TOTAL CUSTOMERS 1,284 (+12%), ACTIVE NOW 42 (pulsing dot), NEW THIS MONTH 156 (+8%), AVG. LIFETIME VALUE $4.2k (`trending_up` tertiary-container). Values render 48px Hanken 800.
3. Table card (`glass-panel rounded-2xl`): filter bar (§63) + table: PROFILE (40px avatar/initials + name `font-bold text-sm` + email), REGISTERED (mono), ORDERS, TOTAL SPEND (bold), STATUS (Active `primary/10`; Pending Verification `tertiary-container/20 text-tertiary`; Suspended `error-container text-error`), ACTIONS hover-reveal (view/edit/block; task_alt; check_circle reactivate). Footer mono "SHOWING 1-10 OF 1,284 CUSTOMERS" + compact pagination (…129).

## D12 · Manage Reviews
**SOURCE** `manage_reviews_bekaa3d_admin_console/code.html` · body dot grid 24px (0.5px dots)
**SIDEBAR** As in D10, with **Manage Reviews active** (`reviews` icon); bottom "New Print Job" + "Admin Profile".
**HEADER** Fixed `left-64 h-16`: "Bekaa3D Admin" + search `w-96`; right: notifications, settings, help, 32px avatar.
**CONTENT** `main ml-64 mt-16 p-gutter`:
1. Header: H3 "Manage Reviews" + description `max-w-2xl`; "Export CSV" outline mono button.
2. Stats `md:grid-cols-3 lg:grid-cols-4 gap-6`: Total Reviews 1,284 (display primary + "+12%"), Avg. Rating 4.8 (display + `secondary-fixed-dim` stars), Pending Moderation 23 (`bg-primary-container` card, pulsing `priority_high`), Positive Feedback (progress KPI).
3. Sticky filter panel (§63) at `top-20`.
4. Review moderation cards `space-y-4` (§58): Pending (Viper-X Extruder Kit, Robert Chen), Approved (Industrial Gear Set, Sarah Miller, 4★), Hidden (Standard Extruder Assembly, 1★).
5. Pagination footer `mt-12` (40px bordered, …129).

## D13 · Manage Offers
**SOURCE** `manage_offers_bekaa3d_admin_console/code.html` · body `.blueprint-bg` (`#e1e8fd` 40px)
**SIDEBAR** `bg-surface-container-lowest py-8`: "Bekaa3D" / "Admin Console". Items `px-6 py-3` Dashboard, Physical Products, **STL Files active** (`bg-surface-container-high`, `.fill-icon`), Categories, Orders. "New Print Job" (`rounded-xl`) + "Admin Profile".
**HEADER** Fixed `left-64 h-16 glass-panel px-8`: "Bekaa3D Admin" + search; notifications, settings, help, 32px avatar.
**CONTENT** `main pl-64` → `pt-24 pb-12 px-8 max-w-max-width mx-auto`:
1. Header: H3 "Manage Price Offers" + description; "Last 30 Days" (tonal `rounded-xl` with border) / "Export Report" (primary `rounded-xl` + glow).
2. Stats `md:grid-cols-3 gap-6` (`rounded-2xl`, 48px `rounded-xl` icon tiles with `.fill-icon`): Total Pending Offers 142, Avg. Negotiation Value $1,482.00, Conversion Rate 74.2%.
3. Filters: 2 selects with chevrons (`rounded-xl`, `min-w-[160|200px]`) + mono "Showing 42 active negotiations".
4. Table `rounded-2xl`: Customer Info (40px avatar + name + email mono xs), STL Asset (48px thumb + name + "Orig: $450.00"), Negotiation (offer price bold primary + % chip; `history` icon + underlined "2 Rounds"), Status (PENDING amber with a pulsing dot / COUNTERED blue), Actions (accept `check_circle` filled primary, reject `cancel` error, "COUNTER" outline mono; or disabled "WAITING ON CUST." + `hourglass_empty`). Footer "Page 1 of 5" + prev/next.
**FAB** `h-14 w-14 bg-primary shadow-xl` + `add` 28px.
**JS** Row click logs "open details" (intended to open a detail modal; not designed).

## D14 · Manage Discounts
**SOURCE** `manage_discounts_bekaa3d_admin_console/code.html` · body `blueprint-grid` (green 40px)
**SIDEBAR** `bg-surface-container-lowest`: "Bekaa3D Admin" / "Precision Control". Items `px-4 py-3 rounded-lg`: Dashboard, Orders, Inventory, **Marketing active** (`analytics` icon filled, right border, no bg), Customers, Settings. Bottom user card + "Logout" mono button.
**CONTENT** `main ml-64 p-margin-desktop` (no top bar):
1. Header: H2 "Discount Management" + description; "CREATE NEW DISCOUNT" (primary + glow, hover → primary-container).
2. Stats `md:grid-cols-3 gap-gutter` (glass): ACTIVE DISCOUNTS 24 (`text-[32px]` primary) + "+12% vs LY"; TOTAL SAVED BY CUSTOMERS $14,802.50 + "YTD REVENUE" chip; UPCOMING EXPIRATIONS 03 (error) + "7 DAYS REMAINING".
3. Search + 2 mono selects (STATUS: ALL, CATEGORY: ALL).
4. Table (glass): DISCOUNT TITLE (`font-headline-md`, renders 16px, + mono primary code), VALUE (mono bold `on-secondary-container`), APPLICABILITY (mono chip `bg-surface-variant`), SCHEDULE (date + mono sub, red "EXPIRED" / primary "STARTS IN 19 DAYS"), STATUS (button toggle), BANNER (star: filled primary = homepage banner), ACTIONS (edit, delete). Expired row `opacity-75 grayscale`. Pagination text-pill.
5. "ACTIVE HOMEPAGE BANNER PREVIEW" (§52 discount banner).

## D15 · System Settings
**SOURCE** `system_settings_bekaa3d_admin_console/code.html` · body `custom-scrollbar`; main `blueprint-grid`
**SIDEBAR** `bg-surface-container-lowest` (padding token broken): "Bekaa3D" / "Admin Console". Nav `px-4` Dashboard, Physical Products, STL Files, Categories, Orders. Bottom: "New Print Job" (filled `add`), **Settings active** (`bg-surface-container-high`, right border), Admin Profile.
**HEADER** Fixed `left-64 h-16 px-gutter`: search pill; notifications, help, divider, clickable profile (32px avatar `border-2 border-primary-fixed`, "Alex Rivera / SUPER ADMIN", lg+).
**CONTENT** `main ml-64 pt-16` → `mx-auto p-gutter` (max-width class broken):
1. Header: mono breadcrumb "ADMIN › SETTINGS", H1 "Console Operations", description. Buttons DISCARD CHANGES (outline) / SAVE CONFIGURATION (primary + glow, `hover:scale-105`; JS shows a toast).
2. `grid grid-cols-12 gap-8 items-start`: sub-nav `col-span-3` (§59): General Settings (active), Company Information, Payment Methods, Shipping Options, User Roles, Backup & Security; COMMUNICATIONS: Email Templates, WhatsApp Settings. Content `col-span-9 space-y-8` with cards `bg-white p-8 rounded-2xl border shadow-sm`:
   - **General** `md:grid-cols-2 gap-6`: General Configuration (`col-span-2`): SITE TITLE, TAGLINE inputs + ADMIN CONSOLE LOGO dropzone; info icon tile `bg-primary-fixed text-primary-container`.
   - SYSTEM PREFERENCES: Default Language and Timezone selects (borderless bold), Console Theme segmented control.
   - CONTACT CHANNELS: email/phone rows with `edit_square` buttons.
   - **Homepage Hero Configuration**: "LIVE PREVIEW" link; 1/3 aspect-video image + "REPLACE HERO IMAGE"; 2/3 MAIN CTA TEXT, LINK TYPE select, DESTINATION.
   - **Payment Gateway Integration**: rows (`p-4 bg-surface-container-low rounded-xl`, 48px white icon tile) Stripe Payments (LIVE chip + on toggle) / PayPal Express (`opacity-70`, INACTIVE, off).
   - **Security** `md:grid-cols-3 gap-6`: Security Protocols (`md:col-span-2`: 2FA ENFORCEMENT two-button group, AUTO-BACKUP select, last-backup panel with pulsing `cloud_done` + "FORCE NEW BACKUP" outline pill); ACTIVE SESSIONS card (`bg-surface-container-high`: desktop/phone rows, "TERMINATE ALL SESSIONS" `bg-error-container`).
3. Toast (§47).
**JS** Anchor smooth scroll; toast shows and hides after 4s.

---

## Pages whose design could not be fully determined

| Page | Gap |
|---|---|
| All pages | **No mobile or tablet designs.** Responsive behaviour is inferred from Tailwind breakpoint classes only (see RESPONSIVE-SPECS.md). Admin pages have almost no responsive classes. |
| S4 product details, A2 registration, D9 categories | Intended type sizes must be inferred (fontSize config missing); the screenshots show unintended 16px headings. |
| S8 about, S9 contact, S5 STL details | Container width/padding tokens are broken; intended gutters inferred (64px). |
| S3 marketplace hero | Background imagery absent; unclear whether a plain hero was intended. |
| S5 STL details | Only the DESCRIPTION tab panel is designed (Reviews, Print Settings, License panels not designed). |
| S7 checkout | Billing-address-different form, PayPal-selected state, validation errors, and order confirmation page are not designed. |
| C1–C7 / D* | Order detail, offer detail, edit-review, notification centre, and add-customer screens referenced by buttons are not designed. |
| All forms | Error/validation, disabled, and loading states mostly undesigned (only JS-simulated loading on contact/admin login). |
| D2 vs D1 | Two competing admin dashboard designs; D1 recommended as canonical (more complete; matches the most frequent admin shell). |
