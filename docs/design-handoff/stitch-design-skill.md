---
name: bekaa3d-stitch-design
description: Use when redesigning, restyling, or building any UI page or component in the Bekaa3D Next.js app so it matches the Stitch "Precision Engineering System" design. Triggers include restyling a page, building a shared component (button, card, nav, footer, sidebar, table, form field), matching a Stitch screen or screenshot, applying design tokens, or doing a visual QA pass. It enforces reading the design handoff first and keeping app logic, security, accessibility, and responsiveness intact.
---

# Bekaa3D Stitch Design Skill

This project has a design handoff extracted from a Google Stitch export. It contains 35 static HTML mockups covering the storefront, auth, customer account, and admin console. Use it to make the real app look like the design **without breaking the app**.

## Where the files are

Paths below are the defaults. Adjust them once if the repo stores them elsewhere.

- Handoff docs: `docs/design-handoff/` (this folder was produced as `design-handoff/`)
  - `README.md`: overview and page list
  - `DESIGN-SYSTEM.md`: visual rules; **§12 lists Stitch inconsistencies and recommended fixes**
  - `DESIGN-TOKENS.md` and `design-tokens.json`: exact values
  - `COMPONENT-SPECS.md`: 64 component patterns with classes, states, and variants
  - `PAGE-SPECS.md`: all 35 pages, section by section, plus the page inventory
  - `RESPONSIVE-SPECS.md`: breakpoints and the mobile gaps the design left open
  - `ASSET-INVENTORY.md`: fonts, icons, image slots
  - `IMPLEMENTATION-GUIDE.md`: DO / DO NOT and the build order
  - `VISUAL-QA-CHECKLIST.md`: comparison checklist
- Original Stitch export (if copied into the repo): `docs/stitch/<page_folder>/code.html` and `screen.png`

## Mandatory reading before redesigning a page

Do these steps in order every time. If you have already read a file in this session, re-open only the relevant sections.

1. Read **DESIGN-SYSTEM.md**. At minimum read §1 (visual language), §6 (surfaces), §9 (colour and status mapping), §10 (CTA hierarchy), §11 (states), and **§12 (inconsistencies)**.
2. Read **DESIGN-TOKENS.md**, or load `design-tokens.json`. Confirm the app theme already exposes these tokens. If not, add them centrally first.
3. Read **COMPONENT-SPECS.md** for every component the page uses. Check whether the app already has that component; restyle it instead of creating a duplicate.
4. Read the page's entry in **PAGE-SPECS.md**. Use the inventory table to map the app route to its Stitch folder (e.g. `/shop` → `shop_physical_products_manufacturing_bekaa3d`).
5. Read **RESPONSIVE-SPECS.md** for the page's family (storefront, auth, account, or admin).
6. If the original Stitch files are available, open that page's **`code.html` and `screen.png`**. The classes show intent. The screenshot shows what rendered, including Stitch bugs.

Then inspect the app's existing implementation of the route: its components, data flow, forms, state, and tests.

## Then implement

- **Reproduce the visual design closely.** Match colours, type pairings (Hanken Grotesk headings, Inter body, JetBrains Mono UPPERCASE labels), spacing rhythm, radii, borders, shadows, image ratios, and hover motion. Use exact values; do not approximate when the handoff gives a number.
- **Prefer shared components.** Use one header, footer, sidebar, button set, card family, table, and status badge, each with variants. Never fork a page-local copy.
- **Use design tokens.** Every colour, size, radius, and shadow comes from the theme. Keep the Stitch/MD3 token names (`primary`, `on-surface-variant`, `surface-container-low`, `outline-variant`, `label-caps`…). Do not use new hex or arbitrary values unless you also add a token.
- **Preserve application logic.** Keep data fetching, server actions, API calls, auth and role checks, cart and checkout flow, validation, routing, and analytics. Restyle markup around the existing logic.
- **Preserve accessibility.** Use semantic HTML, labelled controls, `aria-label` on icon buttons, `aria-current` on active nav, and switch/tab roles. Add visible `focus-visible` rings (the source lacks them). Keep contrast acceptable, respect reduced motion, and make hover-only actions reachable by keyboard and touch.
- **Preserve responsive behaviour.** Keep the source breakpoints (md = 768 is primary) and fill the documented gaps: mobile menu, filter drawer, admin sidebar drawer, table overflow, and the mobile type scale.
- **Preserve loading, error, and empty states.** Style them with tokens: skeleton `bg-surface-container-low animate-pulse`, error `border-error ring-error/20`, empty state per COMPONENT-SPECS §49, toast §47. Never delete them to match a static mockup.
- **Do not copy static Stitch functionality blindly.** Skip the demo JS (mousedown scaling, `console.log`, `alert`/`confirm`, fake `setTimeout` submits, DOM filtering, parallax), the Tailwind CDN, inline configs, placeholder image URLs, and mock copy or data. Rebuild only the meaningful interactions with React state and CSS.
- **Fix known Stitch defects** instead of reproducing them: broken container tokens, missing font sizes, tiled background images, the cart coupon overflow, the customers header overflow, and customer menus on admin pages. Follow the recommendation in DESIGN-SYSTEM §12 and note the deviation.
- **Do not alter routes or navigation structure** to match Stitch labels. Use the app's real items with Stitch styling.

## Priority order (when goals conflict)

1. **Functional correctness**
2. **Security**: never weaken auth, validation, permission checks, or data handling for a visual reason
3. **Accessibility**
4. **Visual fidelity**
5. **Code reuse / maintainability**

Visual fidelity is fourth, but the bar is still **high**. Do not settle for "close enough" when the handoff provides exact values. Deviate only when a higher priority requires it, and say so explicitly.

## Quick reference (verify against DESIGN-TOKENS.md)

| Token | Value |
|---|---|
| Page bg | `#f9f9ff` |
| Card | `#ffffff`, 1px `#bfcaba` (often /30), radius 12px, `shadow-sm`, padding 24px |
| Primary | `#0d631b`, hover `#2e7d32`; lime accent `#b9f474`; raspberry `#923357`; error `#ba1a1a` |
| Text | headings `#141b2b`, body `#40493d`, muted `#707a6c` |
| Type | display 48/1.1/800/-0.02em · headline-lg 32/1.2/700/-0.01em · headline-md 20/1.3/600 · body-lg 18/1.6 · body-md 16/1.5 · label-caps 12/1/600/+0.05em mono uppercase |
| Radius | badge 4 · button/input 8 · card 12 · panel 16 · banner 24 · pill full |
| Layout | max-width 1440 (forms 1200) · gutter 64 desktop / 16 mobile · grid gap 24 · section 96 · sidebar 256 · top bar 64 |
| Motion | colours 200ms · cards 300ms · image zoom 500–700ms · press scale .95 · easing cubic-bezier(.4,0,.2,1) |
| Icons | Material Symbols Outlined, weight 400, FILL 0 (FILL 1 = active/selected/rating) |
| Glass | `rgba(255,255,255,.8)` + `blur(20px)` |

## Finish every page with

- Run the relevant sections of **VISUAL-QA-CHECKLIST.md** at 1280px against `screen.png`, then at 1440, 1024, 768, and 390.
- Check there is no horizontal overflow at 320–1920px.
- Confirm keyboard navigation and focus visibility.
- Confirm that existing tests, type-checks, and lint pass, and that no business logic changed.
- In the summary, list any intentional deviations from the screenshot with their DESIGN-SYSTEM §12 reference.
