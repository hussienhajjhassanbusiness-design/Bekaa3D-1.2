# Bekaa3D Stitch Design Handoff

This is a portable design-handoff package extracted from the Google Stitch export **"stitch_bekaa3d_premium_e_commerce_platform"**. It holds enough implementation-level detail to recreate the design in the real **Bekaa3D Next.js + React + TypeScript** application at high fidelity, so nobody has to guess.

> This package contains **documentation only**. No application code was written, and the Stitch source was not modified.

## What was analysed

| Item | Count |
|---|---|
| Folders inspected | 36 (35 page folders + `precision_engineering_system/`), plus the parent export folder |
| Stitch pages (`code.html`) | **35** |
| Screenshots (`screen.png`) | 35 (desktop, 1280px viewport; no mobile/tablet variants) |
| Design brief | 1 (`precision_engineering_system/DESIGN.md`) |
| Local image/icon/CSS asset files | 0. All imagery is remote placeholders (124 `<img>` + 39 CSS backgrounds); icons come from the Material Symbols font |
| Distinct icons | 165 Material Symbols Outlined glyphs |
| Component patterns documented | 64 |

Method: each page's inline Tailwind config and `<style>` block were parsed and diffed across all 35 files. Tailwind class usage was counted on every page, all 35 pages were read in full, and the screenshots were checked to confirm what actually renders.

## The design in one paragraph

The design is a "functional luxury" engineering aesthetic. A cool off-white canvas (`#f9f9ff`) holds white cards with thin green-grey borders (`#bfcaba`) and soft shadows. A single deep forest-green brand colour (`#0d631b`, hovering to `#2e7d32`) appears with small lime (`#b9f474`) and raspberry (`#923357`) accents, inside a Material-3 tonal palette of lavender-tinted neutrals. Type is three-voiced: heavy, tightly tracked **Hanken Grotesk** headlines, **Inter** body, and uppercase **JetBrains Mono** micro-labels for every technical datum, button, and table header. Navigation uses glassmorphism, app shells sit on blueprint-grid backgrounds, imagery is studio photography of 3D-printed parts, and Material Symbols Outlined icons run throughout. Radii nest at 4px for badges, 8px for controls, 12–16px for cards, and 24px for banners.

## Files

| File | Contents |
|---|---|
| [DESIGN-SYSTEM.md](./DESIGN-SYSTEM.md) | Visual language and reusable rules (backgrounds, hierarchy, type, spacing, surfaces, borders, elevation, colour/status mapping, CTA hierarchy, imagery, icons, states, motion, theme). **§12 STITCH INCONSISTENCIES** gives 22 groups of issues with recommendations. |
| [DESIGN-TOKENS.md](./DESIGN-TOKENS.md) | Exact colour (49 roles + off-palette), gradient, pattern, typography, spacing, layout, border, radius, shadow, glass, motion, icon, z-index, and scrollbar tokens, with usage counts |
| [design-tokens.json](./design-tokens.json) | Machine-readable tokens |
| [COMPONENT-SPECS.md](./COMPONENT-SPECS.md) | 64 component specs: purpose, structure, dimensions, type, colour, borders/shadows, icons, images, states, mobile/desktop, variants, sources |
| [PAGE-SPECS.md](./PAGE-SPECS.md) | Full page inventory table and a section-by-section spec for all 35 pages, plus the gaps that could not be determined |
| [RESPONSIVE-SPECS.md](./RESPONSIVE-SPECS.md) | Breakpoints (Tailwind defaults; md 768 is primary), per-breakpoint behaviour, per-component matrix, overflow risks |
| [ASSET-INVENTORY.md](./ASSET-INVENTORY.md) | Logos, third-party brand marks, fonts, decorations, a per-page list of all 163 image slots, the semantic icon map, and the full icon list |
| [IMPLEMENTATION-GUIDE.md](./IMPLEMENTATION-GUIDE.md) | How to apply this to the existing app: order of work, DO/DON'T, component mapping, token snippet, definition of done |
| [VISUAL-QA-CHECKLIST.md](./VISUAL-QA-CHECKLIST.md) | Reusable comparison checklist (global, header, footer, cards, forms, buttons, images, states, breakpoints, admin, overflow) |
| [stitch-design-skill.md](./stitch-design-skill.md) | Drop-in Claude Code project skill (copy to `.claude/skills/bekaa3d-stitch-design/SKILL.md` in the app repo) |

## Page families (35)

- **Storefront (9):** Home · Shop (physical) · STL Marketplace · Product Details · STL Details · Cart · Checkout · About · Contact
- **Auth (4):** User Login · Registration · Forgot Password · Admin Login
- **Customer account (7):** Account Dashboard · Order History · Offer History · My Reviews · Wishlist · STL Library (downloads) · Profile
- **Admin console (15):** Admin Dashboard · Admin Console (alt. dashboard) · Analytics · Manage Physical Products · Edit Product · Upload Product · Manage STL Files · Upload STL · Categories · Orders · Customers · Reviews · Offers · Discounts · System Settings

Folder-to-page mapping: see the inventory table in [PAGE-SPECS.md](./PAGE-SPECS.md#page-inventory).

## Read this first: critical findings

1. **The HTML is the source of truth, not DESIGN.md.** The brief lists different neutrals (`#111827`, `#F9FAFB`, `#E5E7EB`) and a different radius scale. The code renders MD3 tokens (`#141b2b`, `#f9f9ff`, `#bfcaba`) with radius DEFAULT 4 / lg 8 / xl 12.
2. **`font-*` classes set only the family.** Stitch often omits the matching `text-*` size, so many headings render at 16px. Three pages lack the font-size config entirely. Recommendations are in DESIGN-SYSTEM §12.2–12.3.
3. **Broken spacing tokens** (`max-w-container-max`, `max-w-spacing-max-width`, `px-spacing-margin-desktop`, `py-unit-margin-desktop`) leave four pages without a max width and three flush against the left edge. Use 1440px max width with 64px/16px gutters.
4. **There are no mobile designs.** The storefront has no mobile menu, and the admin has no responsive behaviour. RESPONSIVE-SPECS marks these gaps with recommendations.
5. **Several admin pages show the customer sidebar menu.** Use the real admin navigation.
6. All copy, prices, people, and images are **placeholders**. The demo JavaScript is not production behaviour.

## Using it with Claude in the app repo

1. Copy this folder to `docs/design-handoff/` in the Bekaa3D repo. Optionally copy the Stitch page folders to `docs/stitch/`.
2. Copy `stitch-design-skill.md` to `.claude/skills/bekaa3d-stitch-design/SKILL.md`.
3. Ask Claude to restyle one route at a time. The skill makes it read DESIGN-SYSTEM → TOKENS → COMPONENTS → that page's spec → RESPONSIVE → the original `code.html`/`screen.png` before editing, and keeps functionality, security, and accessibility first.
