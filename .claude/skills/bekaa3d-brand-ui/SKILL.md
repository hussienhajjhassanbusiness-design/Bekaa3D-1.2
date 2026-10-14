---
name: bekaa3d-brand-ui
description: Use when building or reviewing any Bekaa3D frontend UI — pages, components, admin screens, product/STL cards, forms, buttons, badges, navigation, modals, tables, or any visual element — to keep color, typography, spacing, and component styling consistent with the Bekaa3D brand instead of inventing ad hoc styles per page or per component.
---

# Bekaa3D Brand UI

## Overview

Bekaa3D is an engineering/3D-printing company. The brand — confirmed from `bekaa3d-logo.jpg` (hexagonal "B" mark, lime-to-forest-green gradient, near-black wordmark, tagline "Engineered Grade 3D Solutions") — reads as **engineered, precise, technological, professional, clean, trustworthy**. Every screen should look like it belongs to the same product, built by the same team, with the same restraint.

**Core principle:** green is an accent and identity marker, not a background color. Most surfaces are neutral; brand color appears at intentional decision points (primary actions, active/selected states, key data highlights, the logo itself).

## When to Use

- Before styling any new component, page, or admin screen.
- When reviewing a PR that adds UI and you're unsure if it matches the system.
- When a design decision isn't covered here — extend `tokens.md`, don't invent a one-off value inline.

**Not for:** backend contract questions (see `bekaa3d-api-contract`) or commerce domain logic (see `bekaa3d-commerce-ux`).

## What to Avoid

Generic dropshipping-store look, excessive gradients/animation/glassmorphism, random one-off colors, inconsistent card styles per page, oversized decorative UI, and unnecessary visual effects. If a design choice doesn't earn its place (communicates hierarchy, state, or brand), leave it out.

## Full Token Reference

The complete color/typography/spacing/component-state system is in `tokens.md` (this directory) — load it before implementing any component. Quick summary below for fast lookup.

### Brand colors (source: logo)

| Token | Hex | Use |
|---|---|---|
| `brand-dark-green` | `#195B2D` | Primary brand color — headers, primary buttons, active nav, links |
| `brand-lime` | `#8AC143` | Accent — highlights, success accents, secondary CTA, hover glow on primary actions |
| `brand-green` | `#3D793A` | Supporting — secondary buttons, icons, tag/badge backgrounds |
| `ink` | `#21201F` | Near-black — primary text, wordmark-matching headings |
| `white` | `#FFFFFF` | Base surface |

These are initial tokens approximated from the supplied logo asset, not an exact brand spec — see `tokens.md` for the confirmation note and how to update them if an official brand guide arrives.

### Semantic colors (built from the above + standard status hues)

| Token | Hex | Use |
|---|---|---|
| `success` | `#3D793A` (= brand-green) | Success states, paid/delivered badges |
| `warning` | `#B8860B` (amber, not brand) | Pending/awaiting states, cooldowns |
| `danger` | `#B3261E` (red, not brand) | Errors, destructive actions, rejected/cancelled |
| `info` | `#2B6CB0` (blue, not brand) | Neutral informational banners |

Status colors deliberately do **not** reuse brand green for "success" alone — see `tokens.md` for why (a rejected offer and a paid order must never look alike just because both happen to touch green).

### Neutrals

`neutral-50` `#FAFAFA` → `neutral-900` `#21201F` (10-step gray scale, `ink` is the 900 step) — full scale in `tokens.md`.

### Typography, spacing, radius, shadow, breakpoints, component states

See `tokens.md` §§2–9 for: type scale (display/h1–h4/body/caption), 4px-based spacing scale, radius scale (sm/md/lg/pill), a two-tier shadow system (flat-by-default, elevation only for overlays), the four standard breakpoints, and the full hover/focus/active/disabled state contract (including the 2px `brand-lime`-derived focus ring used everywhere for keyboard visibility).

## Component Quick Reference

| Component | Key rule |
|---|---|
| Button hierarchy | Primary = solid `brand-dark-green`; Secondary = outline `brand-dark-green`; Tertiary = text-only `ink`; destructive = solid `danger`. Never more than one primary button per view. |
| Product card | White surface, 1px `neutral-200` border, `radius-md`, image top, no drop shadow at rest — shadow only on hover (`elevation-1`). |
| STL card | Same base as product card + a small dark badge (`brand-dark-green` bg, white text) reading the file type, distinguishing it from physical cards at a glance without full-card color. |
| Admin UI | Denser spacing (`space-2`/`space-3` instead of `space-4`/`space-6`), neutral surfaces throughout, brand color reserved for primary actions and active nav item only — admin is a tool, not a storefront. |
| Badges | Pill radius, semantic color background at 15% opacity + full-opacity text/border of the same hue — never color-only, always paired with text. |
| Rating | Filled/outline star icons in `brand-lime` (not `brand-dark-green` — lime reads better at small sizes), numeric value always shown alongside stars, never stars alone. |
| Alerts | Left border (4px, semantic color) + tinted background (semantic color at 8%) + `ink` body text — never a fully-colored alert block. |
| Empty state | Centered icon (neutral, not brand-colored) + one-line explanation + one primary action. Never brand-green decorative illustration filling the space. |
| Loading/skeleton | Neutral gray shimmer blocks matching the real content's shape — never a spinner for list/grid content, spinners only for full-page/full-action blocking waits. |
| Error state | Same alert pattern as above (`danger`), plus a retry action when the error is retryable. |
| Navigation | White/neutral-50 bar, `brand-dark-green` for the active link (text + 2px underline), `ink` for inactive links. |
| Breadcrumbs | `neutral-500` separators, `ink` for all but the current page, current page in `brand-dark-green` and not a link. |
| Modal/dialog | Centered, `radius-lg`, `elevation-3` shadow, scrim `ink` at 50% opacity, focus-trapped, `Escape` dismisses (see `bekaa3d-frontend-slice-dod` for the full a11y checklist this feeds). |
| Tables | Neutral-50 header row, `ink` header text (not brand-colored), zebra striping only if the table is dense/long, row hover = `neutral-50`. |

## Responsive & States

Breakpoints: mobile ≤767px, tablet 768–1023px, desktop ≥1024px (matches `docs/plans/frontend-slices/FRONTEND-VERTICAL-SLICE-PLAN.md` §14 — do not introduce a second breakpoint system).

Every interactive element needs distinct, visible: default → hover → focus-visible → active → disabled treatments. Focus indicator is **always** a visible 2px outline (brand-lime-derived, never removed via `outline: none` without an equivalent replacement) — this is a hard requirement, not a nice-to-have, per WCAG 2.4.7.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Making a whole page/section background brand green "for identity" | Use neutral backgrounds; green appears on buttons, active states, and small accents only. |
| Inventing a new shade of green per component | Use only the 3 brand green tokens + semantic colors from `tokens.md`; if none fit, that's a signal to revisit the token set, not to add an inline hex value. |
| Using brand-green for both "success" and generic decoration | Reserve brand-green-as-success for actual success states; decorative accents use `brand-lime` sparingly. |
| Color-only status (a green dot, no text) | Always pair color with a text label or icon+label. |
| Removing focus outlines for aesthetics | Never — replace with an equally visible custom focus style, don't delete it. |
| Drop shadows everywhere "to look modern" | Flat by default; shadow only signals elevation (modals, dropdowns, hover-lift on interactive cards). |
