# Bekaa3D: Asset Inventory

## 0. Summary

| Asset class | Count | Local files in export? | Notes |
|---|---|---|---|
| Page screenshots | 35 PNG (`<page>/screen.png`) | **Yes** | Full-page desktop renders at a 1280px viewport. Reference only; not production assets. |
| Design brief | 1 (`precision_engineering_system/DESIGN.md`) | **Yes** | Stitch "Precision Engineering System" brief. |
| Raster images (`<img>`) | 124 | **No** (remote) | All `src` point to `https://lh3.googleusercontent.com/aida-public/…`. These are AI-generated placeholder photos. |
| CSS background images | ~39 | **No** (remote) | `style="background-image:url('https://lh3.googleusercontent.com/aida-public/…')"` |
| Inline SVG | 9 | Inline | WhatsApp ×2, Google "G", Facebook "f", 3 social glyphs (contact), spinner (admin-login JS), plus 1 data-URI pattern (login) |
| Icon font | Material Symbols Outlined | Remote (Google Fonts) | 165 distinct glyphs |
| Web fonts | Hanken Grotesk, Inter, JetBrains Mono | Remote (Google Fonts) | |
| Logos | **None as files** | — | Brand is a text wordmark "Bekaa3D" (see COMPONENT-SPECS §2). No SVG/PNG logo, no favicon. |
| Scripts | Tailwind CDN (`cdn.tailwindcss.com?plugins=forms,container-queries`), Chart.js (`cdn.jsdelivr.net/npm/chart.js`, analytics only) | Remote | Not assets to ship; build-time Tailwind replaces the CDN. |

No images were downloaded for this handoff, as instructed. The remote URLs are signed Google "aida-public" links. Treat them as **ephemeral placeholders**: they may expire, and they must not be hot-linked in production.

---

## 1. Logos & brand marks

| Mark | Source | Where used | Reusable | Notes |
|---|---|---|---|---|
| Text wordmark "Bekaa3D" | HTML text, Hanken Grotesk | every page | Yes | 7 styling variants; canonical = 20px / 800 / `#0d631b` |
| Split wordmark "Bekaa" + "3D" (green) | `user_login` | login card | Optional | |
| Gradient wordmark | `bekaa3d_engineered_grade_3d_solutions` | home nav | Optional | `#0d631b → #b9f474` |
| App tile mark | Material Symbol `deployed_code` (filled) in a 40px green tile | admin dashboard, admin login, manage products | Yes | Recommended app/sidebar mark; candidate favicon |
| Motif glyph | Material Symbol `precision_manufacturing` | registration logo, watermarks (account tier, profile, analytics), custom-quote box, hero/feature icons | Yes | Brand motif |

**Recommendation:** commission a real SVG logo. Until then, implement the wordmark as a component and export a favicon from the `deployed_code` tile.

## 2. Third-party brand assets

| Asset | Source | Where | Notes |
|---|---|---|---|
| WhatsApp glyph (SVG path, `fill=currentColor`) | inline `<svg viewBox="0 0 24 24">` | home FAB (`w-8 h-8`), shop FAB (32×32) | Brand colour `#25D366` |
| Google "G" (4-colour SVG) | inline | user login social button (20px) | Fills `#4285F4 #34A853 #FBBC05 #EA4335` |
| Facebook "f" | inline | user login social button (20px) | Fill `#1877F2` |
| 3 social network glyphs | inline `svg.w-5.h-5.fill-current` | contact "Join the Community" | Path data present in source; networks not labelled |
| Payment logos: Visa, Mastercard, PayPal, Bitcoin | remote `<img>` `h-6`, `grayscale opacity-40` → hover colour | home footer bottom bar | Replace with official brand SVGs (licensing) |
| Payment glyphs (Material) | `credit_card`, `account_balance_wallet`, `payments`, `branding_watermark` | cart summary, checkout | Generic, not brand marks |
| PayPal colour | `#003087` on `account_balance_wallet` icon | system settings | |

## 3. Fonts

| Font | Import | Weights requested | Used for |
|---|---|---|---|
| Hanken Grotesk | `fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;600;700;800` (some pages `600;700;800`; ~half also `wght@100..900`) | 400, 600, 700, 800 (+900 on some) | headlines, prices, KPI numbers, wordmark |
| Inter | `…family=Inter:wght@400;500` / `400;500;600` / `400;600` (varies per page) | 400, 500, 600 | body/UI |
| JetBrains Mono | `…family=JetBrains+Mono:wght@600` (some `400;600`, `500;600`) | 400, 500, 600 | labels, buttons, data |
| Material Symbols Outlined | `…family=Material+Symbols+Outlined:wght,FILL@100..700,0..1` (loaded 2–3× per page, a duplicate) | variable | icons |

**Recommendation:** self-host (e.g. `next/font/google`) Hanken Grotesk 400/600/700/800/900, Inter 400/500/600/700, JetBrains Mono 400/500/600, and Material Symbols Outlined (variable, or a subset of the 165 used glyphs). Use `display=swap`.

## 4. Backgrounds, gradients & decorative graphics (CSS-only; no files)

| Decoration | Definition | Pages | Reusable | Decorative? |
|---|---|---|---|---|
| Blueprint line grid | `linear-gradient(…rgba(13,99,27,0.05) 1px…)` 40px (+10 variants) | auth, account, admin | Yes | Decorative |
| Dot grid | `radial-gradient(circle, #bfcaba 1px, transparent 1px)` 40px / 24px | admin dashboard, categories, reviews, registration | Yes | Decorative |
| Technical SVG pattern | data-URI SVG, 100×100 tile of circles/dots (`fill` light) | user login | Optional | Decorative |
| Blurred orbs | `bg-primary/5` / `bg-secondary/5` circles, `blur-[100–120px]` | home hero, admin login | Yes | Decorative |
| Rotating rings | 800px & 600px circles, 1px `outline-variant/40`, spin 60s / 45s reverse | forgot password | Optional | Decorative |
| Glass shine | `bg-gradient-to-br from-white/20 to-transparent rotate-45` | forgot password card | Optional | Decorative |
| Radial glow | `radial-gradient(circle at top right, white/10, transparent)` | home CTA | Yes | Decorative |
| Dot texture on green | `radial-gradient(circle, white 1px, transparent 1px)` 32px @10% | about CTA | Yes | Decorative |
| Conic donut | `conic-gradient(#0d631b 0% 65%, #b9f474 65% 100%)` | admin dashboard | Data viz | Content-bearing |
| Brand gradients | see DESIGN-TOKENS §1.6 | buttons, text | Yes | — |
| Image scrims | `from-black/80`, `from-inverse-surface/80`, `from-on-surface/80`, `from-primary/90` | image cards, heroes | Yes | Functional (legibility) |
| Watermark icons | Material Symbols at `text-[120px]`/`[240px]`, opacity 3–10% | account tier card, profile header, analytics capacity | Yes | Decorative |
| Decorative icon strip | 5 icons `text-6xl opacity-10` (`3d_rotation layers settings_suggest architecture biotech`) | registration card footer | Optional | Decorative |
| Wireframe schematic images | 2 remote images at `opacity-[0.03]` / `[0.02]`, rotated ±12°, scaled 1.25–1.5 | user login (lg+) | Optional | Decorative |

## 5. Photography (remote placeholders)

Every photo is an AI-generated placeholder whose `data-alt` attribute holds the generation prompt. Common art direction across all of them:
- Clean studio or lab lighting ("clinical", "high-key").
- Green accent highlights.
- Subjects: 3D-printed industrial parts, printers, filament, labs, and engineers.
- Light-mode backgrounds.

**Content-bearing vs decorative:**
- **Content-bearing (replace with real data):**
  - Product/STL images
  - Avatars
  - Team photos
  - Map
  - Payment logos
- **Decorative (replace with brand photography or remove):**
  - Hero/background imagery
  - Category tiles
  - Case-study banners
  - Portfolio masonry
  - Schematic watermarks

**Reusable placeholder slots:**

| Slot | Ratio / size | Used on |
|---|---|---|
| Product image | 1:1 | product cards, gallery thumbs, related items |
| STL preview | 16:10 (home), fixed 256px height (marketplace), 16:9 (library), 4:3 (detail viewer), 1:1 (related) | STL cards and detail |
| Hero / banner | full-bleed or 300–819px tall | page heroes |
| Avatar | 1:1 circle, 28–128px | headers, tables, reviews, profile |
| Team portrait | 4:5 | about |

**Recommendation:** `next/image` with `fill` + `object-cover` + `sizes`, and a `bg-surface-container-low` placeholder.

### 5.1 Per-page image list

Box/ratio is derived from the element's (or its parent's) Tailwind classes. "fill parent" means the image fills a sized wrapper (see PAGE-SPECS for the wrapper size). "css bg" = `background-image` on a div. Full prompts are in each `code.html` `data-alt` attribute.

#### `about_us_bekaa3d_engineering`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | css bg | fill parent | A cinematic, high-angle wide shot of a futuristic precision manufacturing floor with automated robotic arms an… |
| 2 | img | fill parent | A vintage black and white photograph of a small, meticulous engineering workshop from 2014, showing drafting t… |
| 3 | img | square | A clean, minimalist macro shot of a white Bambu Lab X1 Carbon printer head in motion, with a subtle green stat… |
| 4 | img | fluid×128px | A close-up shot of several 3D printed mechanical gears with various finishes: one matte raw, one vapor-smoothe… |
| 5 | img | [4/5] | A professional headshot of a female mechanical engineer in her 30s, wearing a modern gray lab coat, standing i… |
| 6 | img | [4/5] | A professional headshot of a male materials scientist in his 40s with glasses, holding a spool of carbon-fiber… |
| 7 | img | [4/5] | A professional headshot of a younger male industrial designer in a minimalist black turtleneck, sitting at a w… |
| 8 | img | [4/5] | A professional headshot of a female operations director in an industrial facility, wearing high-visibility acc… |
| 9 | img | fill parent | A high-detail macro photograph of a complex, white lattice structure 3D printed with SLS technology, showcasin… |
| 10 | img | fill parent | A grid of multiple identical industrial turbine parts, printed in a metallic-gray carbon-fiber composite, laid… |
| 11 | img | fill parent | A wide view of the Bekaa3D manufacturing floor at night, where hundreds of status lights from 3D printers crea… |
| 12 | img | fill parent | A close-up shot of a robotic arm holding a freshly printed aerospace bracket made of high-temperature polymer.… |
| 13 | img | fill parent | An assortment of colorful, multi-material 3D printed orthopedic models, showcasing the anatomical accuracy and… |

#### `account_dashboard_bekaa3d`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | css bg | fluid×160px | A clean, cinematic rendering of a complex 3D technical model, a high-precision mechanical gear assembly, showc… |
| 2 | css bg | fluid×160px | A professional high-fidelity 3D visualization of an industrial robot arm joint component. The model features s… |
| 3 | css bg | fluid×160px | A detailed 3D CAD rendering of a lightweight drone frame, showcasing the structural lattice design optimized f… |
| 4 | css bg | fluid×160px | A professional digital model of a dental implant abutment, visualized with medical-grade precision. The render… |

#### `admin_analytics_bekaa3d_operations_console`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional high-resolution headshot of a senior operations manager in a tech office setting. The person is… |
| 2 | img | 40px×40px | A high-precision 3D printed mechanical assembly with visible layer lines and intricate gear geometry. The mate… |
| 3 | img | 40px×40px | A detailed 3D printed industrial cooling fan housing, printed in a carbon-fiber reinforced matte black filamen… |
| 4 | img | 40px×40px | A series of precision-calibrated 3D printer nozzles made of hardened steel and ruby. The components are arrang… |

#### `admin_console_bekaa3d_operations`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional high-fidelity 3D rendering of a futuristic industrial mechanical part, displayed in a clean stu… |
| 2 | img | 40px×40px | Detailed macro photograph of a 3D printed precision gear made from carbon fiber material, showcased against a … |

#### `admin_dashboard_bekaa3d_operations`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | Professional headshot of a middle-aged male industrial engineer wearing clean workplace attire, set against a … |
| 2 | img | 28px×28px | Close-up portrait of a female designer with glasses working in a brightly lit studio. Her skin has natural tex… |
| 3 | img | 28px×28px | Headshot of a focused male professional in his late 20s, wearing a high-quality navy blue tech polo shirt. The… |
| 4 | img | 28px×28px | Portrait of an older male engineer with silver hair and a warm, intelligent gaze. He is wearing a lab coat and… |

#### `bekaa3d_engineered_grade_3d_solutions`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | square | A high-end industrial 3D printer like a Bambu Lab X1E, captured in a clean, modern studio setting with cinemat… |
| 2 | css bg | fluid×500px | A macro rendering of complex 3D wireframe models and STL mesh structures in a dark, high-tech digital workspac… |
| 3 | css bg | fluid×240px | Close-up of high-precision functional gears and mechanical parts printed in matte black carbon fiber filament.… |
| 4 | css bg | fluid×240px | Modern geometric 3D printed vase in a minimalist living room setting. The vase has a silk white finish and com… |
| 5 | css bg | fluid×240px | Incredibly detailed 3D printed fantasy miniatures of warriors and monsters on a wooden gaming table. Painted w… |
| 6 | css bg | fluid×240px | 3D printed automotive engine bay components and dashboard accessories. High-temperature resistant materials wi… |
| 7 | img | square | Front view of a precision-engineered 3D printed articulated dragon toy in a vibrant dual-tone iridescent filam… |
| 8 | img | square | A set of custom-designed 3D printed ergonomic grip handles for professional photography rigs. Shot in a high-t… |
| 9 | img | square | Architectural 3D printed model of a modern skyscraper in clear resin with internal structural details visible.… |
| 10 | img | square | High-fidelity 3D printed mechanical keyboard case with a unique honeycomb lattice structure in aluminum-filled… |
| 11 | img | 400px×auto | A collection of premium 3D printed objects—including an architectural model, a detailed bust, and mechanical p… |
| 12 | img | [16/10] | A digital render of a sci-fi cybernetic arm STL model with highlighted internal wireframe. Bright green glowin… |
| 13 | img | [16/10] | 3D render of a complex modular architectural facade STL with interlocking segments. Rendered in a soft clay-li… |
| 14 | img | [16/10] | High-polygon 3D sculpt of a mythical forest creature, showing extreme organic detail and fur texture. Rendered… |
| 15 | img | 48px×48px | A portrait of a professional engineer in a modern industrial office setting. High-quality lighting, profession… |
| 16 | img | 48px×48px | Portrait of a young creative digital artist in a bright, modern studio filled with 3D models. Cinematic lighti… |
| 17 | img | 48px×48px | Portrait of a male hobbyist maker wearing workshop gear, looking confident. Warm, ambient lighting in a home w… |
| 18 | img | fluid×24px | Icon of Visa card payment method. |
| 19 | img | fluid×24px | Icon of Mastercard card payment method. |
| 20 | img | fluid×24px | Icon of PayPal payment method. |
| 21 | img | fluid×24px | Icon of Bitcoin payment method. |

#### `checkout_bekaa3d_precision_engineering`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 80px×80px | A high-resolution, close-up photograph of a professional 3D printing filament spool featuring NX7 Ultra-Poly C… |
| 2 | img | 80px×80px | A detailed 3D technical rendering of a complex Planetary Gear System, displayed as a digital CAD blueprint. Th… |

#### `contact_us_bekaa3d_inquiry`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | css bg | fluid×192px | A clean, minimalist high-contrast digital map rendering showing a stylized urban industrial district in the Be… |

#### `digital_stl_marketplace_bekaa3d`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | fluid×256px | A hyper-realistic 3D render of a precision-machined mechanical gear assembly with carbon fiber textures. The l… |
| 2 | img | fluid×256px | A clean, minimalist 3D render of a geometric architectural desk lamp model for 3D printing. The model is shown… |
| 3 | img | fluid×256px | An industrial 3D render of a rugged drone chassis kit designed for carbon fiber reinforced filaments. The scen… |
| 4 | img | fluid×256px | A detailed 3D visualization of an industrial robotic gripper attachment. The render showcases the inner mechan… |
| 5 | img | fluid×256px | A macro 3D render of a highly detailed miniature terrain piece for table-top gaming, representing a futuristic… |
| 6 | img | fluid×256px | A professional product render of an ergonomic custom keyboard case design with an integrated wrist rest. The s… |

#### `edit_physical_product_bekaa3d_admin`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional headshot of a senior manufacturing engineer in a modern industrial setting. The person is weari… |
| 2 | img | square | A macro photograph of the Viper-X Extruder Kit, showcasing the intricate metal gears and sleek green anodized … |
| 3 | img | square | An exploded view of the Viper-X Extruder components laid out on a blueprint background. Each part, from the mo… |
| 4 | img | square | A close-up shot of the Viper-X Extruder mounted on a 3D printer carriage, in the process of extruding a high-q… |

#### `forgot_password_bekaa3d_precision_engineering`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | fill parent | A highly detailed close-up of a professional 3D printer nozzle extruding a translucent green material with ext… |

#### `manage_categories_bekaa3d_admin`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | Close-up professional portrait of an engineer in a high-tech lab setting, wearing a sleek headset, focused and… |
| 2 | img | fluid×192px | A professional product shot of high-grade industrial 3D printer mechanical parts like gears and bearings. The … |
| 3 | img | fluid×192px | A collection of colorful high-quality 3D printing filament spools arranged in a minimalist aesthetic. The ligh… |
| 4 | img | fluid×192px | High-detail 3D printed aerospace components like turbine blades and rocket engine nozzles displayed on a light… |
| 5 | img | fluid×192px | A clean top-down view of high-performance electronics components such as PCB boards, sensors, and cables on a … |

#### `manage_customers_bekaa3d_admin_console`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A clean, professional headshot of a middle-aged male administrator wearing a minimalist black polo shirt, with… |
| 2 | img | 40px×40px | A portrait of a female industrial designer in her early 30s, with a focused expression, wearing modern glasses… |
| 3 | img | 40px×40px | A portrait of a male mechanical engineer in his 40s with a short beard, wearing a crisp white dress shirt. The… |
| 4 | img | 40px×40px | A portrait of a young woman with curly hair, representing a startup founder or independent industrial designer… |

#### `manage_discounts_bekaa3d_admin_console`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional headshot of a senior manufacturing engineer in a clean, high-tech lab environment. He wears a s… |
| 2 | css bg | fluid×192px | A cinematic, low-angle shot of a high-precision 3D printer working on a complex emerald-green geometric struct… |

#### `manage_offers_bekaa3d_admin_console`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 32px×32px | A professional headshot of a female administrative user with sharp, high-key lighting. She is wearing a modern… |
| 2 | img | 40px×40px | A macro portrait of an industrial designer in a high-tech studio. Soft cool-toned lighting, crisp focus on the… |
| 3 | img | 48px×48px | A clean, high-fidelity 3D rendering of a complex aerospace turbine component STL model on a neutral gray studi… |
| 4 | img | 40px×40px | A professional portrait of a senior mechanical engineer in a modern manufacturing lab setting. The lighting is… |
| 5 | img | 48px×48px | A 3D visualization of a high-precision medical orthopedic implant model for 3D printing. The model is rendered… |
| 6 | img | 40px×40px | A portrait of a youthful creative director in a minimalist, sun-drenched architectural office. The lighting is… |
| 7 | img | 48px×48px | A professional architectural 3D model of a modern skyscraper, rendered with fine lattice details and a high-fi… |

#### `manage_orders_bekaa3d_admin_console`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | Professional headshot of a senior administrator for a high-tech manufacturing facility. The person is an adult… |
| 2 | img | 32px×32px | A small circular avatar portrait of a modern female engineer. She has glasses and short blonde hair, smiling w… |

#### `manage_physical_products_bekaa3d_admin`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional studio portrait of a male engineer in his 40s with a focused and friendly expression. He is wea… |
| 2 | img | 48px×48px | A high-resolution product macro shot of a precision-engineered 3D printer extruder assembly. The components ar… |
| 3 | img | 48px×48px | A clean product shot of a spool of emerald green 3D printing filament. The filament is neatly wound on a trans… |
| 4 | img | 48px×48px | A macro photograph of three different brass 3D printer nozzles of varying diameters (0.2mm, 0.4mm, 0.6mm). The… |

#### `manage_reviews_bekaa3d_admin_console`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 32px×32px | Close-up portrait of a professional industrial engineer in a bright tech office environment. He wears a dark p… |
| 2 | img | 96px×96px | High-resolution studio shot of a Viper-X Extruder Kit for a professional 3D printer. The product is shot again… |
| 3 | img | 24px×24px | A professional close-up headshot of a customer named Robert Chen, a mid-30s engineer with short dark hair, wea… |
| 4 | img | 96px×96px | Close-up detailed photograph of a set of industrial-grade 3D printed mechanical gears made from high-strength … |
| 5 | img | 24px×24px | Portrait of Sarah Miller, a professional industrial designer. She is shown in a bright, modern studio with a c… |
| 6 | img | 96px×96px | Technical close-up of a 3D printer nozzle assembly with cooling fans and heating block. The style is highly te… |
| 7 | img | 24px×24px | A professional avatar of a customer, a young woman with a focused expression working in a modern industrial de… |

#### `manage_stl_files_bekaa3d_admin`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | css bg | 64px×64px | A hyper-realistic 3D render of a complex mechanical industrial part with clean topology, illuminated by cinema… |
| 2 | css bg | 64px×64px | A sharp 3D model render of a highly detailed fantasy tabletop miniature representing an armored warrior. The l… |
| 3 | css bg | 64px×64px | A crisp, high-definition 3D render of a futuristic ergonomic camera handle attachment. The design features com… |

#### `my_reviews_bekaa3d_precision_management`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional studio portrait of a high-end industrial designer, middle-aged with subtle glasses, wearing a d… |
| 2 | img | 128px×128px | A macro photograph of a high-precision aerospace grade titanium alloy bracket, 3D printed using DMLS technolog… |
| 3 | img | 128px×128px | A close-up shot of a Bekaa3D Pro-X industrial 3D printer nozzle assembly during a print process. Glowing filam… |
| 4 | img | 128px×128px | A high-density arrangement of custom-engineered nylon 12 gears and mechanical linkages, 3D printed with SLS te… |

#### `my_wishlist_bekaa3d_precision_engineering`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | square | A professional high-resolution studio photograph of a precision-engineered 3D printer extruder nozzle. The lig… |
| 2 | img | square | A macro photography shot of industrial-grade carbon fiber 3D printing filament spool. The spool is sleek black… |
| 3 | img | square | A professional product rendering of a sleek, high-precision linear rail system for 3D printers. The rails are … |
| 4 | img | square | A high-tech digital control board for a 3D printer, showing complex circuitry, green PCB components, and golde… |
| 5 | img | square | A studio photograph of a premium magnetic PEI spring steel build plate. The plate has a distinct golden-textur… |
| 6 | img | square | A detailed professional shot of an industrial stepper motor for a 3D printer. The motor is clean, metallic, wi… |

#### `offer_history_bekaa3d_precision_management`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 48px×48px | A macro shot of a complex 3D printed planetary gear system made from translucent resin. The lighting is studio… |
| 2 | img | 48px×48px | A professional visualization of a high-precision industrial nozzle STL blueprint. The object is rendered with … |
| 3 | img | 48px×48px | An artistic 3D model of a parametric geometric vase with a complex lattice structure. The render uses a soft-t… |
| 4 | img | 48px×48px | A technical blueprint render of a customized drone frame component. The image highlights precise drill holes a… |

#### `order_history_bekaa3d_precision_management`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional close-up studio portrait of a tech-savvy engineer in a clean, modern workspace. The lighting is… |
| 2 | css bg | fluid×256px | A futuristic, high-tech industrial 3D printing facility with rows of sleek, modern printers. Glowing green sta… |

#### `product_details_bekaa3d_precision_kit`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | css bg | square | A macro close-up of a high-precision 3D printed aerospace bracket made from carbon-fiber reinforced nylon. The… |
| 2 | css bg | square | A technical isometric view of a 3D printed mechanical assembly featuring several interlocking parts. The light… |
| 3 | css bg | square | An action shot of a professional 3D printer nozzle extruding high-performance filament onto a glass bed. Spark… |
| 4 | css bg | square | A detail shot showing the internal honeycomb infill structure of a 3D printed part, sliced open to reveal the … |
| 5 | css bg | square | A collage of various 3D printed engineering samples arranged on a white minimalist table. The objects range fr… |
| 6 | css bg | fluid×320px | A cinematic wide shot of a futuristic automotive manufacturing facility where 3D printers are integrated into … |
| 7 | css bg | square | A sleek industrial vacuum-sealed filament spool of high-temperature support material. The packaging is minimal… |
| 8 | css bg | square | A hardened steel 3D printer nozzle set for abrasive filaments like carbon fiber. The nozzles are arranged in a… |
| 9 | css bg | square | A 3D model render of a complex planetary gearbox assembly, displayed as a digital STL file preview. The backgr… |
| 10 | css bg | square | An industrial filament drying station with a transparent front panel showing multiple spools inside. The digit… |

#### `purchased_stl_downloads_bekaa3d_digital_library`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A clean professional headshot of a precision engineer in a modern minimalist office environment, soft high-key… |
| 2 | img | video | A high-fidelity 3D technical rendering of a complex planetary gear system assembly. The gears are shown in a p… |
| 3 | img | video | A highly detailed 3D blueprint visualization of a turbine housing assembly for a high-performance jet engine. … |
| 4 | img | video | A clean 3D render of a modular prosthetic arm joint design. The aesthetic is medical-grade technology, featuri… |

#### `shop_physical_products_manufacturing_bekaa3d`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | css bg | fill parent | Close-up macro shot of a high-tech 3D printer nozzle extruding vibrant green carbon fiber filament. The backgr… |
| 2 | img | square | High-detail 3D printed mechanical planetary gear system made from translucent green SLA resin. The part is dis… |
| 3 | img | square | A minimalist architectural home decor piece, a 3D printed geometric vase with a complex Voronoi pattern, print… |
| 4 | img | square | An automotive component, a custom air intake manifold 3D printed in high-temperature carbon fiber nylon. The p… |
| 5 | img | square | A macro shot of a complex 3D printed robotic gripper hand, assembled with stainless steel 3D printed joints an… |
| 6 | img | square | A pair of custom 3D printed eyewear frames with an intricate topological optimization design, printed in light… |
| 7 | img | square | A large-scale industrial 3D printed structural bracket made of 316L Stainless Steel. The part shows a high-qua… |

#### `stl_details_planetary_gear_system_bekaa3d_digital`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | css bg | [4/3] | A highly detailed 3D CAD rendering of a complex planetary gear system featuring multiple interlocking brass an… |
| 2 | css bg | square | Close-up detail shot of the sun gear within the planetary gear system, showing intricate tooth profiles and hi… |
| 3 | css bg | square | Exploded view diagram of the planetary gear assembly, showing each component floating in space with technical … |
| 4 | css bg | square | A 3D printer bed visualizing the planetary gear system components neatly arranged for an optimal printing sess… |
| 5 | css bg | square | A macro photo of the physical 3D printed planetary gear system in high-quality PLA, demonstrating the fine lay… |
| 6 | css bg | square | Technical drawing schematic of the planetary gear system overlaid with mathematical dimensions and tolerances. |
| 7 | css bg | 48px×48px | A professional studio portrait of a mechanical engineer with a minimalist gray background, conveying expertise… |
| 8 | css bg | square | Technical 3D render of a high-torque worm gear assembly, presented in a clean white industrial environment wit… |
| 9 | css bg | square | Precision digital model of a dual-axis mechanical gimbals system, rendered with carbon fiber and aluminum text… |
| 10 | css bg | square | High-detail 3D model of a structural extrusion bracket for CNC machines, showing precise dimensions and reinfo… |
| 11 | css bg | square | Digital assembly view of a modular filament spool rack system for 3D printing workshops, rendered in a modern … |

#### `system_settings_bekaa3d_admin_console`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 32px×32px | A professional headshot of a senior industrial administrator in a high-tech office environment. The person is … |
| 2 | css bg | video | A high-contrast cinematic shot of a modern 3D printing nozzle depositing layers of translucent green resin ont… |

#### `upload_physical_product_bekaa3d_admin`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional headshot of a high-end engineering software administrator, clean lighting, soft bokeh, wearing … |
| 2 | img | square | A high-fidelity 3D printed mechanical part with complex internal gears, photographed in a professional studio … |
| 3 | img | square | Close up view of the surface texture and layer lines of a professional 3D printed model, highlighting the prec… |

#### `upload_stl_file_bekaa3d_admin`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 192px×192px | A professional, clean 3D render of a mechanical turbine blade with complex lattice structures. The object is s… |
| 2 | img | square | A detailed technical close-up shot of a 3D printed mechanical component showing fine layer lines and precise o… |
| 3 | img | square | A cross-section diagram render of a turbine blade, highlighting the internal cooling channels and structural s… |
| 4 | img | square | Action shot of a high-end FDM 3D printer head depositing material onto a print bed, creating the base of a com… |

#### `user_login_bekaa3d_precision_engineering`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | fill parent | A highly detailed technical wireframe schematic of a professional 3D printer extruder assembly. The drawing is… |
| 2 | img | fill parent | A complex 3D technical drawing of a heavy-duty gantry system for an industrial additive manufacturing machine.… |

#### `user_profile_bekaa3d_precision_management`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 40px×40px | A professional studio portrait of a male lead mechanical engineer in a clean, minimalist setting. He is wearin… |
| 2 | img | 128px×128px | A detailed close-up of a premium user profile avatar. The subject is a professional engineer with a focus on h… |

#### `your_cart_bekaa3d_precision_engineering`

| # | Type | Box / ratio (from classes) | Content (data-alt prompt, truncated) |
|---|---|---|---|
| 1 | img | 128px×128px | Close-up studio photography of a spool of high-grade NX7 Ultra-Poly Carbon 3D printing filament. The filament … |
| 2 | img | 128px×128px | A clean, isometric 3D render of a complex planetary gear system assembly. The gears are rendered in a transluc… |
| 3 | img | square | Professional macro photography of high-performance hardened steel 3D printer nozzles. The nozzles are arranged… |
| 4 | img | square | A spool of high-temperature translucent blue support filament. The filament is coiled perfectly, shimmering un… |
| 5 | img | square | Studio setup showing a 3D printing glue stick and a precision scraping tool on a clean white laboratory table.… |
| 6 | img | square | Macro view of high-speed industrial ball bearings used in 3D printer gantry systems. The steel spheres are gle… |

---

## 6. Iconography — Material Symbols Outlined

Base: `font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24`, 24px default. Filled (`FILL 1`) for active/selected/rating states. Sizes and colour rules: DESIGN-TOKENS.md §9 and DESIGN-SYSTEM.md §11.

**Semantic icon map (recommended — reuse these glyphs for the same meanings):**

| Meaning | Glyph |
|---|---|
| Search | `search` |
| Cart / add to cart | `shopping_cart` / `add_shopping_cart` |
| Account | `account_circle` / `person` |
| Wishlist | `favorite` |
| Notifications | `notifications` |
| Help | `help` / `help_outline` |
| Settings | `settings` |
| Logout | `logout` |
| Dashboard | `dashboard` |
| Orders | `shopping_bag` (account), `receipt_long` / `package_2` (admin) |
| Physical products | `inventory_2` |
| STL files | `deployed_code` |
| Categories | `category` |
| Customers | `group` |
| Reviews | `rate_review` / `reviews` |
| Offers | `local_offer` / `request_quote` / `bid_landscape` (make-offer button) |
| Discounts | `percent` |
| Analytics | `analytics` |
| Download | `download` / `file_download` / `cloud_download` |
| Upload | `upload_file` / `cloud_upload` |
| View / hide | `visibility` / `visibility_off` |
| Edit / delete / duplicate | `edit` / `delete` / `content_copy` |
| Success / verified | `check_circle` / `verified` / `verified_user` |
| Warning / error | `warning` / `error` / `priority_high` |
| Pagination | `chevron_left` / `chevron_right` |
| Forward CTA | `arrow_forward` |
| Rating | `star` / `star_half` |
| Brand motif | `precision_manufacturing` |
| WhatsApp / chat | `chat` (plus WhatsApp SVG) |

**All 165 glyphs used (with occurrence counts):**

`star` 179, `delete` 39, `visibility` 34, `search` 28, `shopping_cart` 26, `edit` 26, `favorite` 24, `check_circle` 23, `settings` 22, `deployed_code` 21, `chevron_right` 20, `account_circle` 19, `download` 19, `precision_manufacturing` 17, `notifications` 17, `add` 16, `logout` 15, `dashboard` 14, `rate_review` 14, `help` 14, `shopping_bag` 14, `local_offer` 13, `chevron_left` 13, `payments` 11, `add_shopping_cart` 11, `expand_more` 10, `person` 8, `category` 8, `info` 8, `mail` 8, `more_vert` 7, `inventory_2` 7, `verified_user` 7, `verified` 6, `history` 6, `group` 6, `print` 6, `trending_up` 6, `star_half` 6, `arrow_forward` 6, `filter_list` 6, `content_copy` 6, `share` 5, `public` 5, `package_2` 5, `lock` 5, `description` 5, `chat` 5, `close` 5, `credit_card` 4, `analytics` 4, `calendar_today` 4, `upload_file` 4, `bid_landscape` 4, `drag_indicator` 4, `receipt_long` 4, `settings_suggest` 3, `grid_view` 3, `person_add` 3, `reviews` 3, `layers` 3, `cloud_upload` 3, `security` 3, `alternate_email` 3, `send` 3, `account_balance_wallet` 3, `architecture` 3, `format_bold` 3, `format_italic` 3, `link` 3, `add_circle` 3, `file_download` 3, `thumb_up` 3, `list` 3, `calendar_month` 3, `cloud_download` 2, `percent` 2, `campaign` 2, `warning` 2, `biotech` 2, `settings_input_component` 2, `language` 2, `timer` 2, `call` 2, `location_on` 2, `format_list_bulleted` 2, `image` 2, `add_a_photo` 2, `block` 2, `pending_actions` 2, `cancel` 2, `schedule` 2, `tune` 2, `visibility_off` 2, `remove` 2, `download_done` 2, `3d_rotation` 2, `edit_square` 2, `auto_awesome` 1, `view_in_ar` 1, `ads_click` 1, `horizontal_rule` 1, `model_training` 1, `request_quote` 1, `loyalty` 1, `assessment` 1, `menu_open` 1, `help_outline` 1, `sell` 1, `shopping_basket` 1, `person_pin` 1, `update` 1, `lock_open` 1, `login` 1, `memory` 1, `arrow_right_alt` 1, `speed` 1, `support_agent` 1, `branding_watermark` 1, `open_in_new` 1, `encrypted` 1, `workspace_premium` 1, `sync` 1, `copyright` 1, `open_in_full` 1, `keyboard_backspace` 1, `sort` 1, `task_alt` 1, `savings` 1, `event_busy` 1, `insights` 1, `hourglass_empty` 1, `account_balance` 1, `delete_sweep` 1, `inventory` 1, `error` 1, `priority_high` 1, `ios_share` 1, `trending_flat` 1, `menu` 1, `home` 1, `bolt` 1, `thermostat` 1, `cloud_off` 1, `search_off` 1, `map` 1, `zoom_in` 1, `fullscreen` 1, `terminal` 1, `settings_applications` 1, `arrow_forward_ios` 1, `business` 1, `local_shipping` 1, `admin_panel_settings` 1, `dark_mode` 1, `preview` 1, `cloud_done` 1, `desktop_windows` 1, `smartphone` 1, `lightbulb` 1, `photo_library` 1, `storefront` 1, `search_check` 1, `photo_camera` 1, `add_location` 1
