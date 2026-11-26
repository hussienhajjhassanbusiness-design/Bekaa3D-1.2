# Bekaa3D Design Token Reference

**Status: aligned with the approved Stitch design handoff (Redesign Batch 1).**

The visual authority is the Stitch handoff in `docs/design-handoff/` (`DESIGN-TOKENS.md`, `design-tokens.json`, `DESIGN-SYSTEM.md` §12 recommendations). This file is the implementation guide: which token to reach for, the accessibility rules, and the map from the pre-Stitch names that still exist as aliases. Token **values** live in `src/app/globals.css`; if this file and the handoff ever disagree, the handoff wins and this file is corrected.

History: the previous palette (`#195B2D` dark green, `#8AC143` lime, `#21201F` ink, neutral greys) was sampled from the logo JPEG as an unapproved v1. It is superseded by the Stitch palette (product-owner decision, Batch 1). The logo asset itself is unchanged and keeps its own embedded green.

## 1. Colour (Stitch MD3 roles)

Use these names in new code (`bg-primary`, `text-on-surface-variant`, `border-outline-variant`, …).

### Brand roles

| Token | Hex | Use |
|---|---|---|
| `primary` | `#0d631b` | Solid CTAs, active nav, links, prices, focus ring. 7.45:1 on white, 7.11:1 on canvas. |
| `on-primary` | `#ffffff` | Text/icons on primary |
| `primary-container` | `#2e7d32` | **Primary hover** (Stitch lightens on hover) |
| `on-primary-container` | `#cbffc2` | Text on primary-container |
| `primary-fixed` / `-dim` | `#a3f69c` / `#88d982` | Pale green chips, selection highlight, toast success icon |
| `on-primary-fixed` / `-variant` | `#002204` / `#005312` | Text on primary-fixed |
| `inverse-primary` | `#88d982` | Accent on dark surfaces |
| `surface-tint` | `#1b6d24` | Gradient end colour |
| `secondary` | `#3e6a00` | Olive: category badges, "in stock" text |
| `secondary-container` | `#b9f474` | **Lime accent — backgrounds only** (success chips). Never lime text on light. |
| `on-secondary-container` | `#437000` | Text on lime (4.66:1) |
| `secondary-fixed` / `-dim` | `#b9f474` / `#9ed75b` | Promo CTA background, rating on admin |
| `on-secondary-fixed` / `-variant` | `#0f2000` / `#2e4f00` | Text on secondary-fixed |
| `tertiary` | `#923357` | **Raspberry**: discounts, low stock |
| `tertiary-container` | `#b14b6f` | |
| `tertiary-fixed` / `on-tertiary-fixed-variant` | `#ffd9e2` / `#7f2448` | "Pending" chip |

### Surfaces & text

| Token | Hex | Use |
|---|---|---|
| `background` / `surface` / `surface-bright` | `#f9f9ff` | Page canvas (body background) |
| `surface-container-lowest` | `#ffffff` | Cards, dialogs, inputs |
| `surface-container-low` | `#f1f3ff` | Table headers, muted panels, skeletons, image placeholders |
| `surface-container` | `#e9edff` | Icon tiles, chips, empty-state circle |
| `surface-container-high` | `#e1e8fd` | **Dominant hover background** |
| `surface-container-highest` / `surface-variant` | `#dce2f7` | Format tags, neutral badges |
| `surface-dim` | `#d3daef` | Map/avatar placeholder |
| `inverse-surface` / `inverse-on-surface` | `#293040` / `#edf0ff` | Toast, dark cards |
| `on-surface` / `on-background` | `#141b2b` | Headings, primary text |
| `on-surface-variant` | `#40493d` | Body text (most used) |
| `outline` | `#707a6c` | Muted text, **resting input border**. 4.27:1 on canvas — not for essential small text. |
| `outline-variant` | `#bfcaba` | Default border & divider (1.7:1 — decorative borders only, never a control boundary) |

### Semantic

| Token | Hex | Use |
|---|---|---|
| `error` | `#ba1a1a` | Destructive buttons, error text, invalid border |
| `error-container` / `on-error-container` | `#ffdad6` / `#93000a` | Error alerts, negative badges |
| `warning` | `#d97706` | Icons, borders, dots only (3.2:1 — not text) |
| `warning-container` / `on-warning-container` | `#fef3c7` / `#92400e` | Warning alerts & badges (6.4:1) |
| `warning-outline` | `#fde68a` | Warning border |
| `info` | `#2563eb` | Info icons/borders |
| `info-container` / `on-info-container` | `#dbeafe` / `#1e40af` | Info alerts & badges, offer "countered" |
| `info-outline` | `#bfdbfe` | Info border |
| `whatsapp` | `#25d366` | WhatsApp brand. White text on it fails contrast (1.98:1): use the glyph with an `aria-label`, or `on-surface` text. |

Success has no dedicated Stitch token: badges use `secondary-container` + `on-secondary-container`; alerts use `secondary-container/40` + an icon in `primary`.

### Status mapping (DESIGN-SYSTEM §9) — `StatusBadge` tones

| Tone | Background | Text |
|---|---|---|
| `positive` (success, delivered, active) | `secondary-container` | `on-secondary-container` |
| `warning` (pending, awaiting) | `warning-container` | `on-warning-container` |
| `negative` (error, cancelled, failed) | `error-container` | `on-error-container` |
| `info` (countered, informational) | `info-container` | `on-info-container` |
| `neutral` (archived, hidden) | `surface-container-highest` | `on-surface-variant` |

## 2. Typography

Families are self-hosted with `next/font/local` (`src/app/fonts.ts`, vendored OFL woff2). No Google request at build or run time.

| Family | Utility | Use |
|---|---|---|
| Hanken Grotesk | `font-headline`, `font-display` | All headings (applied to `h1`–`h6` globally), prices, KPI numbers |
| Inter | `font-body` (also `font-sans`, set on `body`) | Body and UI text |
| JetBrains Mono | `font-label` | Labels, buttons, table headers, chips, IDs — UPPERCASE via the `uppercase` class |

| Token | Size / line-height / weight / tracking | Use |
|---|---|---|
| `display` | 48 / 1.1 / 800 / -0.02em — **36px below 768** | Storefront page title / hero |
| `headline-lg` | 32 / 1.2 / 700 / -0.01em — **24px below 768** | Section heading, account/admin page title |
| `headline-md` | 20 / 1.3 / 600 | Card heading, dialog title |
| `title-sm` | 16 / 1.5 / 600 | Compact card / row title |
| `body-lg` | 18 / 1.6 | Intro / lead paragraph |
| `body-md` | 16 / 1.5 | Body paragraphs, form input text |
| `text-sm` (Tailwind) | 14 / 20 | Secondary body, compact UI, table cells (Stitch `text-sm`) |
| `text-xs` (Tailwind) | 12 / 16 | Helper, meta, error text (Stitch `text-xs`) |
| `label-caps` | 12 / 1.0 / 600 / 0.05em | Labels, buttons (pair with `font-label uppercase`; use `leading-4` where text can wrap) |
| `label-sm` | 11 / 1.0 / 600 / 0.05em | Status badges, chips |
| `label-micro` | 10 / 1.0 / 600 / 0.05em | Micro labels — never in `outline` colour |

Do not promote every 14px caption/helper/compact control to 16px: pick the role.

## 3. Spacing & layout

4px base unit (Tailwind default, unchanged).

| Token | Value | Utility |
|---|---|---|
| `gutter` | 24px | `gap-gutter` — common grid gap |
| `margin-mobile` | 16px | `px-margin-mobile` — page gutter <768 |
| `margin-desktop` | 64px | `px-margin-desktop` — storefront page gutter ≥1024 (32px recommended at tablet) |
| `section` / `section-mobile` | 96px / 64px | `py-section` — storefront section rhythm |
| `sidebar` | 256px | `w-sidebar` — app sidebar |
| `topbar` | 64px | `h-topbar` — app top bar |
| `container-content` | 1440px | `max-w-content` — main content cap |
| `container-form` | 1200px | `max-w-form` — admin long-form cap |

Card padding 24px (`p-6`), form/summary cards 32px (`p-8`), compact 16px. Form rhythm 24px between fields, 8px label → input.

## 4. Shape

| Token | Value | Use |
|---|---|---|
| `rounded-badge` | 4px | Badges, tags |
| `rounded-control` | 8px | Buttons, inputs, selects, icon tiles |
| `rounded-card` | 12px | Standard card, dialog, alert, toast |
| `rounded-panel` | 16px | Large / summary panels |
| `rounded-banner` | 24px | Promo / CTA banners |
| `rounded-full` | pill | Status badges, avatars, icon buttons |

Nested radii decrease inward (a 12px card holds 8px controls and 4px badges). Tailwind's `rounded-lg` is now 8px (Stitch); use `rounded-xl` for 12px.

## 5. Elevation & effects

| Level | Value | Use |
|---|---|---|
| e0 | border only | Tables, admin cards, inputs |
| e1 | `shadow-sm` | Resting card |
| e2 | `shadow-ambient` | Account dashboard / category cards |
| e3 | `shadow-md` → `shadow-xl` on hover | Card hover |
| e4 | `shadow-lg shadow-primary/20` | Primary CTA |
| e5 | `shadow-2xl` | Dialog, toast, dropdown, FAB |

Glass (`glass-panel`: white 80% + 20px blur, opaque fallback), gradients (`--gradient-primary`, `--gradient-signature`, `text-gradient-primary`) and the blueprint grid (`bg-blueprint`) exist **only for the places the Stitch handoff specifies them**.

## 6. Motion

Colours 200ms (Tailwind default duration is set to 200ms), cards 300ms, image zoom 500–700ms, easing `ease-standard` (`cubic-bezier(.4,0,.2,1)`), press `scale .95` (`enabled:active:scale-95`). A global `prefers-reduced-motion` block neutralises animations and transitions; keep `motion-reduce:` variants on component-level motion too.

## 7. Focus & accessibility contract

- Global `:focus-visible` = `0 0 0 2px #fff, 0 0 0 4px primary` (box-shadow; E2E asserts it). Never removed, never replaced by Stitch's weaker `ring-primary/20`.
- Inputs: resting border `outline` (≥3:1), focus border `primary` + global ring, error `border-error ring-2 ring-error/20` + caption-size error text with an icon, linked by `aria-describedby`.
- Disabled: `opacity-50 cursor-not-allowed`, no hover change; pair with a reason where one exists.
- Status never by colour alone.

## 8. Legacy aliases (removed in Batch 11)

The pre-Stitch compatibility names (`brand-dark-green`, `brand-green`, `brand-lime`, `ink`, `text-text-*`, `neutral-50…900`, `surface-base/subtle/sunken`, `border-default/strong/focus`, `success`, `success-bg`, `danger`, `danger-bg`, `warning-bg`, `warning-text`, `info-bg`, `text-h1…h4`, `text-body`, `text-caption`, `text-label`, `tracking-label`, `rounded-md`, `rounded-pill`, `shadow-elevation-1/2/3`) no longer exist in `globals.css`. A class using one silently generates no CSS, so do not reintroduce them. Migration used: secondary body → `text-sm`, caption → `text-xs`, `rounded-sm/md/pill` → `rounded-badge/control/full`, `shadow-elevation-1/3` → `shadow-sm` / `shadow-2xl`, colours per the Stitch role table in §1.

## Open items

- Only the Latin font subsets are vendored; add other subsets if a locale needs them.
- No dark theme: Stitch designed light only.
