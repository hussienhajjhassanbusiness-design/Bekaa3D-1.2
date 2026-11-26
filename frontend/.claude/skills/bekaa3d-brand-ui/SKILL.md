---
name: bekaa3d-brand-ui
description: Use when building or reviewing any Bekaa3D frontend UI — pages, components, admin screens, product/STL cards, forms, buttons, badges, navigation, modals, tables, or any visual element — to keep color, typography, spacing, and component styling consistent with the Bekaa3D brand instead of inventing ad hoc styles per page or per component.
---

# Bekaa3D Brand UI

## Authority (read this first)

| Layer | Role |
|---|---|
| **Stitch design handoff** — `docs/design-handoff/` (`DESIGN-SYSTEM.md`, `DESIGN-TOKENS.md`, `design-tokens.json`, `COMPONENT-SPECS.md`, `RESPONSIVE-SPECS.md`) and the `bekaa3d-stitch-design` skill | **Current visual authority.** Colours, type, spacing, radius, elevation, component patterns. When anything here disagrees with it, the handoff wins. |
| **This skill + `tokens.md`** | Implementation guidance aligned with Stitch: which token to use, the legacy-alias map, accessibility rules the static mockups do not cover. |
| `src/app/globals.css` | The single source of truth for token **values** in code. |

Above all visual rules sit functional correctness, security and accessibility (priority order in `bekaa3d-stitch-design`).

## Overview

Bekaa3D is an engineering/3D-printing company. The Stitch "Precision Engineering System" reads as **engineered, precise, technological, clean, trustworthy**: a cool off-white canvas (`#f9f9ff`), white cards with soft green-grey borders, lavender containers, one solid green action colour, Hanken Grotesk headings, Inter body text and JetBrains Mono uppercase labels.

**Core principle:** green is the action and identity colour, not a background. Most surfaces are neutral (canvas, white cards, lavender containers); `primary` appears at decision points — primary actions, active/selected states, prices, links, focus.

The logo asset keeps its own embedded green and is never recoloured to match the UI tokens.

## When to Use

- Before styling any new component, page, or admin screen (together with `bekaa3d-stitch-design` for page redesigns).
- When reviewing a PR that adds UI and you're unsure if it matches the system.
- When a design decision isn't covered — add a token centrally (handoff docs → `globals.css`), never an inline one-off value.

**Not for:** backend contract questions (`bekaa3d-api-contract`) or commerce domain logic (`bekaa3d-commerce-ux`).

## What to Avoid

Generic dropshipping-store look, random one-off colours, inconsistent card styles per page, oversized decorative UI, and effects that don't earn their place.

**Glass and gradients:** use glass/gradient effects only where specified by the approved Stitch design system (e.g. the sticky glass header, the documented gradient CTA variant, the home H1 text-gradient accent, the blueprint shell backgrounds). They are never a general visual style; the default CTA is solid `primary`. Utilities: `glass-panel`, `bg-blueprint`, `text-gradient-primary`, `--gradient-primary` (globals.css).

## Token quick reference (full list in `tokens.md`)

| Role | Token | Value |
|---|---|---|
| Primary action / brand | `primary` | `#0d631b` |
| Primary hover | `primary-container` | `#2e7d32` |
| Lime accent (chip backgrounds only) | `secondary-container` | `#b9f474` |
| Raspberry accent | `tertiary` | `#923357` |
| Error | `error` / `error-container` / `on-error-container` | `#ba1a1a` / `#ffdad6` / `#93000a` |
| Warning | `warning` / `warning-container` / `on-warning-container` | `#d97706` / `#fef3c7` / `#92400e` |
| Info | `info` / `info-container` / `on-info-container` | `#2563eb` / `#dbeafe` / `#1e40af` |
| Page canvas | `background` | `#f9f9ff` |
| Card | `surface-container-lowest` | `#ffffff` |
| Lavender range | `surface-container-low` → `surface-container-highest` | `#f1f3ff` → `#dce2f7` |
| Heading text | `on-surface` | `#141b2b` |
| Body text | `on-surface-variant` | `#40493d` |
| Muted text | `outline` | `#707a6c` |
| Border | `outline-variant` | `#bfcaba` |

Type roles: `text-display` (48, 36 on mobile) · `text-headline-lg` (32, 24 on mobile) · `text-headline-md` (20) · `text-title-sm` (16/600) · `text-body-lg` (18) · `text-body-md` (16) · `text-sm` (14, secondary/compact) · `text-xs` (12, captions/helper) · `font-label text-label-caps uppercase` (12 mono). Families: `font-headline`/`font-display`, `font-body`, `font-label`.

Shape: `rounded-badge` 4 · `rounded-control` 8 · `rounded-card` 12 · `rounded-panel` 16 · `rounded-banner` 24 · `rounded-full` pills.

## Component quick reference

| Component | Key rule |
|---|---|
| Button hierarchy | `Button` variants: `primary` (solid `primary`, hover `primary-container`, green-tinted shadow) · `secondary` (2px `primary` outline) · `outline` (neutral `outline-variant`) · `ghost` (text-only `primary`) · `destructive` (solid `error`). Mono uppercase label via CSS. **At most one primary per view**, rightmost in action bars. |
| Form fields | Use `TextField` / `PasswordField` / `SelectField` / `TextAreaField` / `MoneyInput` (shared `fieldStyles`). 48px, 8px radius, white, resting border `outline` (≥3:1 — deliberate deviation from Stitch's `outline-variant`), focus border `primary` + the global ring, error `border-error ring-error/20` + text with icon. |
| Cards | White, 1px `outline-variant` (`/30` in soft storefront cards), `rounded-card`, `shadow-sm`, 24px padding. Large panels `rounded-panel`. |
| Status badges | `StatusBadge` tones (DESIGN-SYSTEM §9): pill, mono 11px bold uppercase, MD3 container + on-container text. Never colour-only — always a text label. |
| Alerts | `Alert`: 12px radius, tinted border, MD3 container, leading icon; error = `role="alert"`, others `role="status"`. No dismiss. |
| Toast | `Toast`: `inverse-surface`, 12px radius, `shadow-2xl`, leading icon, bottom-right (centred on mobile). |
| Modal/dialog | `DialogShell` only (focus trap, Escape/backdrop unless busy, focus return). Panel `rounded-card shadow-2xl`, scrim `on-surface/40` + light blur. Never write a second focus trap. |
| Empty state | `EmptyState`: 96px lavender circle with a neutral icon, one line, at most one primary action. |
| Loading | Spinner `text-primary` for blocking waits; skeletons `bg-surface-container-low animate-pulse` for lists/grids. |
| Icons | `components/ui/Icon` (local inline SVG, `aria-hidden`). No remote icon fonts (Material Symbols CDN is blocked by CSP). |
| Tables | `surface-container-low` header row, mono uppercase headers, `divide-outline-variant` rows, `hover:bg-primary/5`. Row actions always visible. |

## Responsive & States

Breakpoints: mobile ≤767px, `tablet:` 768–1023px, `desktop:` ≥1024px (= Stitch `md` / `lg`). Do not introduce a second breakpoint system.

Every interactive element needs distinct, visible default → hover → focus-visible → active → disabled treatments.

**Focus is non-negotiable:** the global `:focus-visible` ring is a box-shadow (2px white + 4px `primary`), never removed and never replaced by a weaker treatment to match a mockup (WCAG 2.4.7). E2E specs assert a non-`none` box-shadow on focus. Respect `prefers-reduced-motion` (globals.css base block plus `motion-reduce:` variants).

## Common Mistakes

| Mistake | Fix |
|---|---|
| Making a whole section background brand green "for identity" | Neutral canvas/cards; green on actions, active states, prices and small accents (Stitch brand cards/CTA banners only where the handoff specifies them). |
| Inventing a new shade per component | Use the Stitch tokens; if none fit, add one centrally (handoff → `globals.css`), never an inline hex. |
| Lime text on a light background | Lime (`secondary-container`) is a background; text on it is `on-secondary-container`. |
| `outline` (#707a6c) for required small text | It is 4.27:1 on the canvas; use `on-surface-variant` for anything essential. |
| Colour-only status | Always pair colour with a text label (and an icon shape where used). |
| Removing focus rings for aesthetics | Never — the global ring stays. |
| Rewriting a label's casing to get UPPERCASE | Use the `uppercase` class; source text (and accessible names) stay as written. |
| Using a removed legacy alias (`brand-dark-green`, `text-text-primary`, `danger`, `text-h1`, `text-body`, `text-caption`…) | Use the Stitch name. The aliases were deleted in Batch 11; a class using one generates no CSS. |
