# Bekaa3D: Token Migration (current app → Stitch)

Status: **done.** Batch 1 of [BEKAA3D-REDESIGN-PLAN.md](./BEKAA3D-REDESIGN-PLAN.md) adopted the Stitch tokens with compatibility aliases; Batch 11 migrated every remaining call site and **deleted all aliases** (none retained; `src/app/legacyTokens.test.ts` guards against their return). The tables below are the original planning record.

Sources compared:
- **Current:** `src/app/globals.css` (Tailwind v4 `@theme`, no `tailwind.config.*`, transcribed from `.claude/skills/bekaa3d-brand-ui/tokens.md`), `src/app/layout.tsx` (no font loading), and class usage counted across `src/**/*.tsx` excluding tests.
- **Stitch:** [DESIGN-TOKENS.md](./DESIGN-TOKENS.md), [design-tokens.json](./design-tokens.json), the recommendations in [DESIGN-SYSTEM.md](./DESIGN-SYSTEM.md) §12, and the inline `tailwind.config` in `docs/design-reference/stitch/*.html` (spot-checked: `primary #0d631b`, `background #f9f9ff`, `outline-variant #bfcaba`).

Verdicts: **KEEP** (already right, or kept for a stated reason) · **CHANGE** (same role, new value) · **ADD** (new token) · **REMOVE** (retire after its uses are migrated).

---

## 0. Architecture facts that shape the migration

| Fact | Consequence |
|---|---|
| Tailwind **v4**, CSS-first `@theme` in `globals.css`. No config file. | Stitch's v3 `theme.extend` snippet (IMPLEMENTATION-GUIDE §6) has to be rewritten as `@theme` variables: `--color-primary`, `--text-headline-lg`, `--radius-xl`, and so on. |
| The current tokens use **app-specific semantic names**: `brand-dark-green`, `text-text-primary`, `border-border-default`, `surface-subtle`, `success/warning/danger/info`, `text-h1…h4`, `text-body`, `text-caption`, `text-label`. | Measured use (non-test `.tsx`): `text-text-primary` 315 uses in 127 files · `text-body` 251/109 · `text-text-secondary` 194/85 · `rounded-sm/md/lg/pill` 130/76 · `text-caption` 129/56 · `text-h1–h4` 121/78 · `brand-dark-green` 91/36 · `danger` 64/31 · `border-border-default` 60/49 · `text-text-link` 46/25. Renaming them all in one pass is a large diff touching 147 files. |
| No hex literals in any `.tsx` (0 found). | Every colour already goes through a token, so changing token values re-skins the whole app centrally. |
| `globals.css` header: "Do not add a token here that `tokens.md` does not define." The `bekaa3d-brand-ui` skill says to avoid glassmorphism and gradients and names `#195B2D` as primary. | **Governance conflict.** `tokens.md` and the `bekaa3d-brand-ui` skill must be updated, or marked superseded by the Stitch handoff, in Batch 1. Otherwise two checked-in skills give contradictory instructions. The primary colour change `#195b2d → #0d631b` needs product-owner sign-off, because `tokens.md` says its palette was sampled from the real logo (`docs/assets/…jpg`). |
| Breakpoints: custom `tablet:` (768) and `desktop:` (1024). 88 + 24 uses. Default `sm:/md:/lg:/xl:` used only twice. | The pixel values already match Stitch `md`/`lg`. **KEEP** the names and translate Stitch `md:` → `tablet:` and `lg:` → `desktop:`. Stitch `xl:` (1280) has no app equivalent yet; add `--breakpoint-wide: 1280px` only if a batch needs it. |
| Global `:focus-visible { box-shadow: var(--shadow-focus-ring) }` (2px white + 4px dark green). E2E asserts `not.toHaveCSS("box-shadow","none")` on focused links (`e2e/account-profile.spec.ts`). | Keep focus on `box-shadow`, which Tailwind `ring-*` also uses. Do not switch to `outline`, or that E2E assertion fails. |
| CSP (production): `font-src 'self' data:`, `style-src 'self' 'unsafe-inline'`, `img-src 'self' data: blob: https:`. | Google Fonts CSS or the Material Symbols CDN **will be blocked** in production. Fonts must be self-hosted (`next/font`). Stitch's remote placeholder images would load under `img-src https:`, but they must not be used anyway (asset rule). |

### Recommended strategy: alias first, then rename

1. **Batch 1:** add the full Stitch MD3 token set under its Stitch names (`--color-primary`, `--color-on-surface-variant`, `--color-surface-container-low`, …). At the same time, **re-point the legacy semantic tokens to the Stitch values** (e.g. `--color-brand-dark-green: var(--color-primary)`, `--color-text-primary: var(--color-on-surface)`). Every existing screen moves to the Stitch palette at once, with zero class churn and zero logic risk.
2. **Batches 2–10:** each batch rewrites its own components' classes to the Stitch names as it restyles them, so the legacy names stop being used.
3. **Batch 11:** grep for remaining legacy names. When the count is 0, delete the aliases (the REMOVE rows below).

This keeps every intermediate commit shippable. The 9 unit-test files that assert class names (`toHaveClass("bg-brand-dark-green")` ×5, `text-warning-text` ×2, `bg-danger` ×2, …) keep passing until the batch that renames that component, which then updates its own test.

---

## 1. Colours

| Role | Current token → value | Stitch token → value | Verdict | Notes / risk |
|---|---|---|---|---|
| Brand green (actions, links, active, prices) | `brand-dark-green` `#195b2d` | `primary` `#0d631b` | **CHANGE** + **ADD** `primary`, `on-primary #ffffff` | Owner sign-off needed (logo-derived colour). `#0d631b` measures 7.45:1 on white and 7.11:1 on `#f9f9ff`, so focus-ring and link contrast stay compliant. Alias `brand-dark-green → primary` in Batch 1. |
| Hover green | none (buttons have no hover colour today) | `primary-container` `#2e7d32` (+ `on-primary-container #cbffc2`) | **ADD** | Stitch lightens on hover (DESIGN-SYSTEM §9.1). New hover states need visual QA only; no logic. |
| Supporting green | `brand-green` `#3d793a` (6 uses: WhatsApp buttons, success) | `secondary` `#3e6a00` | **CHANGE** (alias) | WhatsApp buttons move to the new `whatsapp` token below, not `secondary`. |
| Lime accent | `brand-lime` `#8ac143` (2 uses in 1 file); also the old focus-ring colour | `secondary-container` `#b9f474`, `on-secondary-container #437000`, `secondary-fixed`, `secondary-fixed-dim #9ed75b`, `on-secondary-fixed #0f2000` | **CHANGE** + **ADD** | Lime is a chip background only. Never use lime text on a light background (Stitch defect: checkout FREE chip, PAGE-SPECS S7). |
| Raspberry | none | `tertiary` `#923357`, `tertiary-container #b14b6f`, `tertiary-fixed #ffd9e2`, `on-tertiary-fixed-variant #7f2448` | **ADD** | For discount, low-stock, and "pending" chips (StatusBadge mapping). |
| Other MD3 green roles | none | `primary-fixed #a3f69c`, `primary-fixed-dim #88d982`, `on-primary-fixed #002204`, `on-primary-fixed-variant #005312`, `inverse-primary #88d982`, `surface-tint #1b6d24` | **ADD** | Trend chips, eyebrows on dark backgrounds, gradient end. Low usage, so add them all for 1:1 class translation. |
| Page background | `surface-base` = `#ffffff`; `body { background: var(--color-surface-base) }` | `background` / `surface` `#f9f9ff` | **CHANGE** | Highest-visibility change. Cards become white on an off-white canvas. Any component that relies on "white page = white card" without a border loses contrast, so Batch 1 QA must sweep every route. |
| Cards | `surface-base` `#fff` (5 uses), DialogShell `bg-white` | `surface-container-lowest` `#ffffff` | **ADD** (+ alias `surface-base → surface-container-lowest`) | Same value, Stitch name. |
| Subtle panel | `surface-subtle` `#fafafa` (4 uses, Footer) | `surface-container-low` `#f1f3ff` | **CHANGE** (alias) | Warm grey becomes lavender. |
| Sunken / placeholder | `surface-sunken` `#f2f2f1` (2 uses) | `surface-container` `#e9edff` | **CHANGE** (alias) | Image placeholders should use `surface-container-low` per DESIGN-SYSTEM §11. |
| Lavender steps | none | `surface-container-high #e1e8fd`, `surface-container-highest #dce2f7`, `surface-variant #dce2f7`, `surface-dim #d3daef`, `surface-bright #f9f9ff` | **ADD** | `surface-container-high` is the dominant hover background. |
| Dark surfaces | `ink` used as the dialog scrim (`bg-ink/50`) | `inverse-surface #293040`, `inverse-on-surface #edf0ff` | **ADD** | Toast uses `inverse-surface` (COMPONENT-SPECS §47). Dialog scrim moves to `bg-on-surface/40` (RESPONSIVE-SPECS drawer overlay). |
| Primary text | `ink` / `text-primary` `#21201f` (315 uses) | `on-surface` / `on-background` `#141b2b` | **CHANGE** (alias) | Near-black warm becomes near-black navy. Low visual risk. |
| Body text | `text-secondary` = `neutral-600 #5c5a57` (194 uses) | `on-surface-variant` `#40493d` | **CHANGE** (alias) | Darker than today, so contrast improves. |
| Muted / tertiary text | `text-disabled` = `neutral-400 #a6a4a0` (1 use); `neutral-500 #7d7b77` | `outline` `#707a6c` | **CHANGE** | `#707a6c` measures 4.27:1 on `#f9f9ff` (4.48:1 on white), which fails AA for small text. Use it for ≥14px bold, large text, or non-essential captions only, never as the sole carrier of required info (forms, prices). |
| Link | `text-link` = brand-dark-green (46 uses) | `primary` | **CHANGE** (alias) | |
| Borders | `border-default` = `neutral-200 #e4e3e1` (60 uses); `border-strong #cbc9c6` (0 uses) | `outline-variant` `#bfcaba` (1px; `/30` in soft storefront cards) | **CHANGE** (alias); **REMOVE** `border-strong` (unused) | `outline-variant` at full opacity measures 1.7:1 on white. That is fine for decorative card borders, but **input borders must stay ≥3:1** (WCAG 1.4.11). Recommend inputs use `outline` `#707a6c` for the resting border, or rely on the bg contrast plus a label. This is a deliberate accessibility deviation from COMPONENT-SPECS §27 (which uses `outline-variant`); record it in the Batch 1 notes. |
| Focus border | `border-focus` = brand-lime (unused in classes; ring uses brand-dark-green) | `primary` + `ring-2 ring-primary/20` (inputs); `ring-2 ring-primary ring-offset-2` (buttons/links) | **CHANGE** | Keep the global `:focus-visible` box-shadow ring and recolour it to `primary`. Inputs additionally get `focus:border-primary focus:ring-primary/20`. A `/20` ring alone is too faint to be the only focus indicator, so keep the global ring. |
| Error | `danger` `#b3261e`, `danger-bg` 8% tint (64 uses) | `error` `#ba1a1a`, `on-error #fff`, `error-container #ffdad6`, `on-error-container #93000a` | **CHANGE** + **ADD** | Alias `danger → error`, `danger-bg → error-container`. The current 8% `color-mix` tints are replaced by real MD3 containers. Alert and Toast will look stronger, so check every error banner. |
| Warning | `warning #b8860b`, `warning-bg`, `warning-text #805b07` (39 uses) | No config token. Source uses Tailwind `amber-100/200/600/800`. DESIGN-SYSTEM §9 maps "Pending" to `tertiary-fixed` / `on-tertiary-fixed-variant` and "Warning (offers pending)" to amber. | **CHANGE** to new tokens `warning-container #fef3c7`, `on-warning-container #92400e`, `warning #d97706` (amber values, named as tokens, since Stitch said "off-palette") | Rule: no Tailwind `amber-*` in components (IMPLEMENTATION-GUIDE §4). Keep `warning-text` as an alias of `on-warning-container` until Batch 11. |
| Success | `success` = brand-green, `success-bg` 8% (17 uses) | No dedicated token. Green family reused: `secondary-container #b9f474` + `on-secondary-container #437000`, or `primary/10` + `primary`. | **CHANGE** (alias `success → primary`, `success-bg → secondary-container`) | Use the StatusBadge mapping (component doc) rather than raw success classes. |
| Info | `info #2b6cb0`, `info-bg` (12 uses) | Off-palette `blue-100/200/600/800` ("Countered" offers only) | **CHANGE** to `info-container #dbeafe`, `on-info-container #1e40af`, `info #2563eb` | Used for informational banners plus the offer "countered" state. |
| WhatsApp | `brand-green` on WhatsApp buttons | `#25D366` literal | **ADD** `whatsapp` | White text on `#25D366` measures 1.98:1 and **fails** contrast. Options: use the logo glyph only (icon button with `aria-label`), or `on-surface` text on `#25D366` (8.67:1). Decide in Batch 2 (FAB) and Batch 3 (product page WhatsApp CTA). |
| Neutral scale | `neutral-50…900` (20 uses in 15 files) | none (no greys in Stitch; lavender containers only) | **REMOVE** (after migration) | Map each use: 100 → `surface-container`, 200 → `outline-variant`/`surface-container-high`, 400/500 → `outline`, 600/700 → `on-surface-variant`. AdminTable skeleton `bg-neutral-200` → `bg-surface-container-low`. |
| Rating stars | none | amber `#f59e0b` (products), `primary` (review rows) | **ADD** `rating #f59e0b` only if ratings ship | The backend has no reviews feature today, so this is likely **not needed**. Do not add it speculatively. |

## 2. Gradients, patterns, glass

| Item | Current | Stitch | Verdict |
|---|---|---|---|
| Primary gradient | none | `--gradient-primary: linear-gradient(135deg,#2e7d32,#1b6d24)`; signature `135deg #0d631b → #3e6a00` | **ADD** as CSS variables plus a `Button variant="gradient"`. Solid primary stays the default (§12.9). |
| Text gradient (home H1 accent) | none | `linear-gradient(to right,#0d631b,#3e6a00)` | **ADD** utility `.text-gradient-primary` (home only, optional). |
| Blueprint grid | none | `rgba(13,99,27,.05)` 1px lines, 40px | **ADD** `.bg-blueprint` (auth, account, admin shells only; §12.20). |
| Dot grid | none | `radial-gradient(#bfcaba 1px, transparent 1px)` 24–40px | **ADD** optional `.bg-dot-grid`; prefer the one blueprint grid. |
| Glass | none | `rgba(255,255,255,.8)` + `blur(20px)`; nav `bg-surface/80 backdrop-blur-xl` | **ADD** `.glass-panel`, `.glass-nav`. Add `@supports not (backdrop-filter)` fallback to an opaque surface. |
| Scrims | none | `from-black/80` bottom gradients, `bg-black/40` hover overlays | **ADD** only when an image-with-text component needs one (no hero imagery exists yet; see asset rule). |

## 3. Typography

Current state: **no font family is configured**. `globals.css` deliberately leaves the system-sans stack in place ("typeface unconfirmed").

| Item | Current | Stitch | Verdict | Notes / risk |
|---|---|---|---|---|
| Heading family | system sans | **Hanken Grotesk** 400/600/700/800 (+900 for black wordmarks) | **ADD** via `next/font/google` → `--font-hanken` → `--font-display`/`--font-headline` | `next/font/google` downloads at **build time** and self-hosts, so CSP `font-src 'self'` is satisfied. Risk: an offline CI build fails. Fallback: vendor the woff2 files and use `next/font/local`. |
| Body family | system sans | **Inter** 400/500/600/700 | **ADD** → `--font-body`, set on `body` | Changes the metrics of every text node. Re-run the overflow/geometry E2E specs (login form width, etc.). |
| Label family | none | **JetBrains Mono** 400/500/600 | **ADD** → `--font-label` (`font-label-caps`) | Mono uppercase is the signature voice: labels, buttons, table headers, IDs. Mono text is ~20% wider than Inter at the same size, so check button and table-header overflow at 320px. |
| Fallback stacks | n/a | DESIGN-TOKENS §2.1 | **ADD** | `"Hanken Grotesk", ui-sans-serif, system-ui, sans-serif` and so on. |
| Icons | inline SVG paths per component (cart, menu, heart, search, WhatsApp) | Material Symbols Outlined (variable font, Google CDN) | **CHANGE (decision)** | The CDN is blocked by CSP and is a new remote dependency. **Recommendation:** an `Icon` component that renders vendored Material Symbols **SVGs** (Apache-2.0) for only the glyphs the real app needs, keeping `aria-hidden`. A self-hosted subset font via `next/font/local` is an alternative. Never ligature text, which reads aloud as "shopping_cart". |

### Type scale

| Role | Current token | Stitch token | Verdict | Uses affected |
|---|---|---|---|---|
| Display / hero H1 | `text-display` 40/48 | `display` 48 / 1.1 / 800 / -0.02em; **mobile (<768) 36px** (RESPONSIVE-SPECS §1) | **CHANGE** | 2 uses |
| Page title (account/admin H1) | `text-h1` 32/40 (68 of the 121 h-uses) | `headline-lg` 32 / 1.2 / 700 / -0.01em; **mobile 24px** (`headline-lg-mobile`) | **CHANGE** (alias `h1 → headline-lg`) | Same size; adds tracking. Responsive step-down is new. |
| Section H2 | `text-h2` 24/32 | `headline-lg` 32 (storefront section titles) | **CHANGE per call site** | 8 uses. Some h2s are in-card section titles, which should map to `headline-md` 20. Decide per component, not by alias. |
| Card title | `text-h3` 20/28 | `headline-md` 20 / 1.3 / 600 | **CHANGE** (alias) | 43 uses |
| Compact title | `text-h4` 16/24 | "title-sm" 16px Hanken 600 (DESIGN-SYSTEM §12.3 recommendation) | **ADD** `title-sm`; alias `h4 → title-sm` | 10 uses |
| Lead | `text-body-lg` **16/24** (2 uses) | `body-lg` **18 / 1.6** | **CHANGE** (name collision, value differs) | 2 uses. Check both call sites. |
| Body | `text-body` **14/20** (251 uses) | `body-md` **16 / 1.5** | **KEEP `text-body` as 14px** (it is Stitch's "secondary body", `text-sm`) and **ADD** `body-md` 16 | Re-mapping `text-body` to 16px would reflow 109 files at once, including dense admin tables. Each batch promotes primary paragraphs to `body-md` deliberately. |
| Caption | `text-caption` 12/16 | `text-xs` 12/16 (caption/meta) | **KEEP** | 129 uses; same value. |
| Label / button / table header | `text-label` 12/16 + `tracking-label` 0.04em + `uppercase` + `font-semibold` | `label-caps` 12 / 1.0 / 600 / **0.05em**, mono, uppercase | **CHANGE** (alias `text-label → label-caps`; tracking 0.04 → 0.05em; add mono family) | 38 uses. Line-height 1.0 makes multi-line labels collide, so keep 16px line-height on wrapped field labels. Documented deviation. |
| Micro label / chip | none | 10–11px mono 600 uppercase | **ADD** `label-micro` (10px) and `label-sm` (11px) | Contrast at 10px: use ≥`on-surface-variant` and never `outline` for 10px text. |

## 4. Spacing

| Item | Current | Stitch | Verdict | Notes |
|---|---|---|---|---|
| Base unit | Tailwind v4 `--spacing: 0.25rem` (4px), not overridden | 4px | **KEEP** | `p-6` etc. resolve identically. |
| Grid gutter | none (ad hoc `gap-4`/`gap-6`) | `gutter` 24px | **ADD** `--spacing-gutter: 24px` | Generates `gap-gutter`, `px-gutter`. |
| Page margin mobile | `px-4` (16px) in Header/Footer | `margin-mobile` 16px | **ADD** `--spacing-margin-mobile` | Same value. |
| Page margin desktop | `tablet:px-6` (24px), `desktop:px-8` (32px) | `margin-desktop` **64px** storefront; app content 32px (`p-8`) | **ADD** `--spacing-margin-desktop: 64px` | Recommend 16 → 32 (tablet) → 64 (desktop) for storefront; Stitch jumps 16 → 64 at 768, which crowds tablets. Admin/account content uses 32px. |
| Section rhythm | `mt-12` (48px) between home sections | 96px (`py-24`) desktop, **64px below `md`** | **CHANGE** | Home, about, and storefront marketing sections only. |
| Card padding | `p-3`/`p-4`/`p-6` mixed | 24px (`p-6`) standard, 32px (`p-8`) form/summary, 16px (`p-4`) compact | **CHANGE per component** | |
| Form rhythm | mixed (`gap-3`/`gap-4`) | 24px between fields (`space-y-6`), label→input 8px | **CHANGE** | Taller forms, so re-check geometry E2E (login form) and dialog `max-h-[90vh]` scroll. |
| Control padding | inputs `px-3 py-2` (~36px tall), buttons `px-4 py-2` | inputs `px-4 py-3` = **48px**; buttons sm `px-4 py-2` / md `px-6 py-3` / lg `px-8 py-4` | **CHANGE** | 48px meets touch targets. Buttons get explicit sizes. |
| Table cells | `px-3 py-2` | `px-6 py-4` admin (`py-5` account) | **CHANGE** | Wider tables: confirm `overflow-x-auto` wrappers everywhere. |

## 5. Layout

| Item | Current | Stitch | Verdict | Notes / risk |
|---|---|---|---|---|
| Main content cap | **none**: pages are full width inside Header/Footer padding | `max-width` **1440px** + `mx-auto` | **ADD** `--container-max: 1440px` and a `Container` component | Fixes Stitch defect §12.1/§12.4 by design. |
| Admin long forms | none | **1200px** (`max-w-[1200px]`) | **ADD** `--container-form: 1200px` (`Container size="narrow"`) | Product new/edit, settings, MFA pages. |
| Prose measure | none | 672px (`max-w-2xl`) | **KEEP** Tailwind default `max-w-2xl` | |
| App sidebar | account nav `tablet:flex-col` (auto width); admin `tablet:w-48` (192px) | **256px** (`w-64`), `py-8 px-6` | **ADD** `--sidebar-width: 256px` | Admin at 768–1023 cannot afford 256px, so use the drawer below `desktop` (RESPONSIVE-SPECS §1). |
| App top bar | none (account/admin reuse the storefront Header) | **64px** sticky glass bar | **ADD** `--topbar-height: 64px` | Needs a structural decision: the root layout always renders the storefront Header/Footer around `/account` and `/admin` (see the component doc, Shells). |
| Storefront nav height | ~64px (`py-3` + 40px controls) | **64px** (`h-16`), fixed glass | **CHANGE** to an explicit `h-16` | If it becomes `fixed`, every page needs a top offset. Prefer `sticky top-0`: it gives the same look with no offset bookkeeping and no content hidden under the nav. |
| Auth card widths | login form ≤420px (asserted by E2E) | login 440px card, forgot 448, register 640 | **CHANGE** | `e2e/login-session.spec.ts` asserts form width ≤420 and centred at ≥768, and ≥ viewport−10 at <768. A Stitch card with 32px padding and 16px gutters breaks the mobile assertion. Batch 4 must update that spec deliberately and document why. |
| Breakpoints | `tablet` 768, `desktop` 1024 | md 768, lg 1024, xl 1280 | **KEEP** | Add `wide` 1280 only on demand. |

## 6. Shape (radius)

Current `@theme`: `--radius-sm 4px`, `--radius-md 8px`, `--radius-lg 12px`, `--radius-pill 999px`. Tailwind v4 defaults otherwise: `rounded` 4px, `rounded-xl` 12px, `2xl` 16px, `3xl` 24px, `full`.

| Role | Current | Stitch | Verdict | Risk |
|---|---|---|---|---|
| Badge / tag | `rounded-sm` 4px (inputs also use it) | `rounded` 4px | **KEEP** value; inputs move off it | |
| Input / button | inputs `rounded-sm` **4px**, buttons `rounded-md` 8px | `rounded-lg` **8px** | **CHANGE** inputs to 8px | |
| Card | `rounded-md` 8px (ProductCard), dialogs `rounded-lg` 12px | `rounded-xl` **12px** | **CHANGE** | |
| Large panel | none | `rounded-2xl` 16px | **ADD** (Tailwind default) | |
| Banner / CTA | none | `rounded-3xl` 24px | **ADD** (Tailwind default) | |
| Pill | `rounded-pill` 999px (15 uses) | `rounded-full` | **REMOVE** `--radius-pill` after migration (alias meanwhile) | |
| **Name collision** | `rounded-lg` = **12px** (4 uses), `rounded-md` = **8px** (≈90 uses) | `rounded-lg` = **8px**, `rounded-md` = 6px (rare) | **CHANGE** `--radius-lg` to 8px; **keep `--radius-md: 8px` as a legacy alias** until its uses become `rounded-lg`, then remove the override (Tailwind default 6px) | Do the 4 current `rounded-lg` uses (dialog panels) first: convert them to `rounded-xl` in Batch 1 **before** redefining `--radius-lg`, or dialogs silently shrink from 12px to 8px. |

## 7. Elevation

| Item | Current | Stitch | Verdict |
|---|---|---|---|
| Resting card | `shadow-elevation-1` `0 1px 3px ink/8%` | `shadow-sm` `0 1px 2px rgb(0 0 0/.05)` + 1px `outline-variant(/30)` border | **CHANGE** (border-first; "flat stacking" in admin) |
| Ambient card | none | `0 4px 20px -2px rgba(20,27,43,.04)` | **ADD** `--shadow-ambient` |
| Hover | ProductCard `hover:shadow-elevation-1` | `shadow-md` → `shadow-xl` + lift -4px (300ms) | **CHANGE** (with `motion-reduce:` guards, which already exist on ProductCard) |
| Dialog / toast | `shadow-elevation-3`, `shadow-elevation-2` | `shadow-2xl` | **CHANGE** |
| Primary CTA glow | none | `shadow-lg shadow-primary/20` | **ADD** |
| Focus ring | `--shadow-focus-ring` (white 2 + dark green 4) | `ring-2 ring-primary ring-offset-2` | **KEEP** mechanism; recolour to `primary` |
| Borders | 1px `border-default` | 1px `outline-variant`; 2px emphasis; 4px right rail (active sidebar); 2px bottom (active nav/tab) | **CHANGE** |
| Motion | `transition-shadow`, `transition-opacity duration-200`, `motion-reduce:` variants | 200ms colours, 300ms cards, 500–700ms image zoom, `cubic-bezier(.4,0,.2,1)`, press `active:scale-95` | **ADD** duration tokens and a global `prefers-reduced-motion` block |
| Elevation tokens | `--shadow-elevation-1/2/3` | `e0…e5` scale (DESIGN-TOKENS §7) | **REMOVE** the elevation-N names after migration (alias meanwhile) |

---

## 8. Batch 1 token checklist (copy into the PR)

- [ ] `tokens.md` and the `bekaa3d-brand-ui` skill updated or marked superseded; primary-colour change signed off.
- [ ] All Stitch MD3 colour roles added under `@theme` with Stitch names, plus `warning-*`, `info-*`, `whatsapp`.
- [ ] Legacy colour tokens re-pointed via `var()` aliases (no duplicated hex).
- [ ] `body` background `#f9f9ff`, text `on-surface`, family Inter.
- [ ] Fonts via `next/font` (self-hosted), CSS variables, fallback stacks; verified under the production CSP (`npm run build && npm start`).
- [ ] Type tokens added (`display`, `headline-lg`, `headline-md`, `title-sm`, `body-lg`, `body-md`, `label-caps`, `label-sm`, `label-micro`) with the <768 step-down for display/headline-lg.
- [ ] Spacing (`gutter`, `margin-mobile`, `margin-desktop`), container widths, sidebar and top-bar sizes.
- [ ] Radius collision handled in order: dialogs to `rounded-xl` first, then `--radius-lg: 8px`.
- [ ] Shadows, glass, blueprint, gradient utilities; reduced-motion block.
- [ ] Focus ring recoloured, still `box-shadow`-based.
- [ ] Every route visually swept at 375 and 1280 for contrast regressions from the new canvas colour.
