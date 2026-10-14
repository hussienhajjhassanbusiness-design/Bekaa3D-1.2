# Bekaa3D Design Token Reference

Source: `docs/assets/ChatGPT Image Sep 26, 2026, 04_34_37 PM.jpg` (the supplied Bekaa3D logo — hexagonal "B" mark, lime→forest-green gradient, near-black "BEKAA" wordmark, dark-green "3D," tagline "Engineered Grade 3D Solutions" in mid-green).

**Status: initial proposal, not an approved brand spec.** These tokens are visually sampled/approximated from the one logo asset provided. If an official brand guideline (exact hex values, approved type family, usage rules) becomes available, update this file and treat it as the new source of truth — do not keep both versions in circulation.

## 1. Brand Colors

| Token | Hex | Sampled from | Use |
|---|---|---|---|
| `brand-dark-green` | `#195B2D` | Logo's upper-right hexagon facet (darkest green) | Primary actions, headers, active nav/links, primary text accents |
| `brand-lime` | `#8AC143` | Logo's lower-left hexagon facet (lightest green) | Accents, ratings, hover glow, secondary highlights — used sparingly |
| `brand-green` | `#3D793A` | Mid-tone between the two facets / tagline text color | Secondary buttons, icons, tag backgrounds, "3D" wordmark color |
| `ink` | `#21201F` | "BEKAA" wordmark | Primary text, headings |
| `white` | `#FFFFFF` | Logo background | Base surface |

**Given confidence:** high on hue family (three-stop green gradient + near-black wordmark is unambiguous in the source image); medium on exact hex precision (sampled from a JPEG, not a vector/brand-book source) — treat these as "close enough to ship a consistent v1," not pixel-exact brand values.

## 2. Semantic Colors

Deliberately **not** all derived from brand green — status meaning must stay legible independent of brand identity (a green "paid" badge and a green "brand accent" button must never be visually confusable as the same signal).

| Token | Hex | Use |
|---|---|---|
| `success` | `#3D793A` (`brand-green`) | Paid, delivered, accepted, completed states |
| `success-bg` | `#3D793A` at 8% opacity | Success alert/badge background |
| `warning` | `#B8860B` | Pending, awaiting response, cooldown-active, in-production |
| `warning-bg` | `#B8860B` at 8% opacity | Warning alert/badge background |
| `danger` | `#B3261E` | Errors, destructive actions, rejected, cancelled, failed payment |
| `danger-bg` | `#B3261E` at 8% opacity | Error alert/badge background |
| `info` | `#2B6CB0` | Neutral informational banners, "verifying," in-transit |
| `info-bg` | `#2B6CB0` at 8% opacity | Info alert/badge background |

## 3. Neutral Palette

10-step gray scale, `ink` (`#21201F`) anchors the darkest step so text always ties back to brand identity rather than a generic pure-black.

| Token | Hex |
|---|---|
| `neutral-50` | `#FAFAFA` |
| `neutral-100` | `#F2F2F1` |
| `neutral-200` | `#E4E3E1` |
| `neutral-300` | `#CBC9C6` |
| `neutral-400` | `#A6A4A0` |
| `neutral-500` | `#7D7B77` |
| `neutral-600` | `#5C5A57` |
| `neutral-700` | `#413F3D` |
| `neutral-800` | `#2D2C2A` |
| `neutral-900` (= `ink`) | `#21201F` |

## 4. Text Colors

| Token | Value | Use |
|---|---|---|
| `text-primary` | `ink` (`#21201F`) | Headings, primary body text |
| `text-secondary` | `neutral-600` | Supporting text, captions, metadata |
| `text-disabled` | `neutral-400` | Disabled control labels |
| `text-on-brand` | `white` | Text on `brand-dark-green`/`brand-green` solid surfaces |
| `text-link` | `brand-dark-green` | Inline links, underline on hover |

## 5. Surfaces & Borders

| Token | Value | Use |
|---|---|---|
| `surface-base` | `white` | Page background |
| `surface-subtle` | `neutral-50` | Section alternation, table header row, input backgrounds |
| `surface-sunken` | `neutral-100` | Well/inset areas (e.g., code blocks, quoted content) |
| `border-default` | `neutral-200` | Card/table/input borders |
| `border-strong` | `neutral-300` | Emphasized dividers |
| `border-focus` | `brand-lime` (2px, see §9) | Focus ring on all interactive elements |

## 6. Typography

Assumption (flag if the team has a licensed brand typeface): a clean geometric/grotesk sans for UI (e.g., Inter or similar system-adjacent sans) for all interface text, reserving the logo's own lettering strictly for the logo itself — **never recreate or approximate the logo's custom lettering as a UI font**.

| Token | Size / Line-height | Weight | Use |
|---|---|---|---|
| `display` | 40px / 48px | 700 | Hero/landing headline only |
| `h1` | 32px / 40px | 700 | Page title |
| `h2` | 24px / 32px | 600 | Section heading |
| `h3` | 20px / 28px | 600 | Card/subsection heading |
| `h4` | 16px / 24px | 600 | Small heading, table section label |
| `body-lg` | 16px / 24px | 400 | Primary body text |
| `body` | 14px / 20px | 400 | Default UI text |
| `caption` | 12px / 16px | 400 | Metadata, timestamps, helper text |
| `label` | 12px / 16px | 600, uppercase, +0.04em tracking | Form field labels, table headers |

Admin UI uses `body`/`caption` as its default density; storefront leans on `body-lg` for readability.

## 7. Spacing

4px base unit — every margin/padding/gap value is a multiple of it, no arbitrary in-between values.

| Token | Value |
|---|---|
| `space-1` | 4px |
| `space-2` | 8px |
| `space-3` | 12px |
| `space-4` | 16px |
| `space-5` | 20px |
| `space-6` | 24px |
| `space-8` | 32px |
| `space-10` | 40px |
| `space-12` | 48px |
| `space-16` | 64px |

Storefront default gap: `space-4`/`space-6`. Admin default gap: `space-2`/`space-3` (denser, tool-like — matches `bekaa3d-brand-ui`'s admin density rule).

## 8. Radius

| Token | Value | Use |
|---|---|---|
| `radius-sm` | 4px | Inputs, small badges |
| `radius-md` | 8px | Cards, buttons, dialogs' inner elements |
| `radius-lg` | 12px | Modals, large panels |
| `radius-pill` | 999px | Pills, status badges, avatar |

No sharper-than-4px or fully-square interactive elements — softens the "engineered" look without going playful/rounded-bubbly (avoid >12px on anything but a pill).

## 9. Elevation (Shadow)

Flat by default — shadow exists only to signal something is floating above the page, never as decoration.

| Token | Value | Use |
|---|---|---|
| `elevation-0` | none | Default resting state for cards, inputs, buttons |
| `elevation-1` | `0 1px 3px rgba(33,32,31,0.08)` | Hover-lift on interactive cards only |
| `elevation-2` | `0 4px 12px rgba(33,32,31,0.10)` | Dropdowns, popovers |
| `elevation-3` | `0 12px 32px rgba(33,32,31,0.16)` | Modals/dialogs |
| `focus-ring` | `0 0 0 2px white, 0 0 0 4px #8AC143` | Keyboard focus on any interactive element (double-ring so it's visible on both light and colored backgrounds) |

## 10. Container Widths & Breakpoints

| Token | Value |
|---|---|
| `breakpoint-mobile` | ≤ 767px |
| `breakpoint-tablet` | 768–1023px |
| `breakpoint-desktop` | ≥ 1024px |
| `container-max` (storefront) | 1280px, centered, `space-4` side gutter minimum on mobile |
| `container-max` (admin) | fluid up to 1600px — admin tables/dashboards benefit from more width than storefront content |

Matches `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §14 exactly — this is the single breakpoint system for the whole app, not a second competing scale.

## 11. Button Variants

| Variant | Background | Text | Border | Use |
|---|---|---|---|---|
| Primary | `brand-dark-green` | `white` | none | The one primary action per view (submit, buy, confirm) |
| Secondary | `white` | `brand-dark-green` | 1px `brand-dark-green` | Secondary actions (cancel-but-safe, view details) |
| Tertiary/ghost | transparent | `ink` | none | Low-emphasis actions (dismiss, skip) |
| Destructive | `danger` | `white` | none | Irreversible/destructive actions only (cancel order, delete, revoke) |
| Disabled | `neutral-200` | `neutral-400` | none | Any variant in a disabled state — always paired with a reason (`aria-describedby`), never a bare grey-out |

Hover: darken background 8%. Active: darken 12% + scale 0.98 (subtle, no bounce). Focus: `focus-ring` token, always. Never more than one Primary button visible in the same view/section.

## 12. Field States

| State | Border | Background | Notes |
|---|---|---|---|
| Default | `border-default` | `surface-subtle` | |
| Hover | `neutral-400` | `surface-subtle` | |
| Focus | `border-focus` (2px) | `white` | `focus-ring` shadow applied |
| Error | `danger` (2px) | `danger-bg` | Paired with inline error text below the field, `aria-describedby` |
| Disabled | `border-default` | `neutral-100` | `text-disabled` for both label and value |
| Success (rare — e.g., verified address) | `success` (1px) | `white` | Used sparingly, only where positive confirmation adds real value |

## Open Items

- Exact hex precision should be re-verified against a vector/brand-book source if one becomes available (see Status note above).
- No licensed/approved UI typeface has been specified — this document assumes a system-adjacent geometric sans as a placeholder; confirm with brand/marketing before final implementation.
- Dark-mode tokens are intentionally not defined — nothing in `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` or `docs/plans/backend/vertical-slice-plan.md` requires dark mode for V1; add a token set here if that requirement appears.
