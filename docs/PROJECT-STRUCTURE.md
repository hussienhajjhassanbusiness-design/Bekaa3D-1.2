# Project Structure

How this repository is organized, and where to find or file things. This is a
map of the repo, not a design doc — it does not describe product behavior.

## Top-level folders

| Folder | What's in it |
|---|---|
| `src/` | Application source. `src/app` (Next.js App Router routes), `src/components` (feature-grouped UI components), `src/lib` (feature-grouped client/query/domain logic). |
| `e2e/` | Playwright end-to-end specs (`npm run test:e2e`, `test:e2e:backend`). |
| `.claude/skills/` | Project-local Claude Code skills (see below). Do not move skill files out of here. |
| `docs/` | All project documentation. See breakdown below. |
| `public/` | Static assets served by Next.js (currently empty/absent — add as needed). |

Unit/component tests live next to the source file they test (`*.test.ts(x)`),
following the existing Vitest/Next.js convention — they are not collected
under a separate top-level `tests/` folder.

Standard tooling config stays at the repository root: `package.json`,
`tsconfig.json`, `next.config.ts`, `eslint.config.mjs`, `postcss.config.mjs`,
`playwright.config.ts`, `vitest.config.mts`, `vitest.setup.mts`,
`.env.local.example`, `CLAUDE.md` / `AGENTS.md`.

## `docs/` breakdown

| Location | Contents | Authoritative? |
|---|---|---|
| `docs/plans/frontend-slices/` | `FRONTEND-VERTICAL-SLICE-PLAN.md` (the frontend slice plan, FVS-001–FVS-046) and every `FVS-0NN-IMPLEMENTATION-PLAN.md` task-by-task plan. | Yes — per-slice implementation detail and the `NEEDS BACKEND CONFIRMATION` tracker (FVS plan §17) live only here. |
| `docs/plans/backend/` | `vertical-slice-plan.md` — the backend's own VS-001–VS-040 plan, mirrored here for reference. | Yes, for backend capability/sequencing — if this and the FVS plan disagree, this file wins. |
| `docs/backend-handoff/` | The backend team's answers: `BACKEND-RESPONSE.md`, `openapi.json`, and a `README.md` index. | Yes, for confirmed contract shape — `openapi.json` is generated from running backend code. |
| `docs/frontend-requests/` | What the frontend asked the backend to confirm: `BACKEND-UNLOCK-HANDOFF.md` (the audit/request), `BACKEND-RESPONSE-TEMPLATE.md` (the reply format), `MINIMUM-MANUAL-TEST-UNLOCK.md` (smallest unlock path). | Yes, as the request side of the handoff — `docs/backend-handoff/BACKEND-RESPONSE.md` answers these by ID. |
| `docs/setup/` | `frontend-setup.md` — developer setup and the as-built architecture reference (what's actually implemented, not planned). | Yes, for what is currently running/committed. |
| `docs/assets/` | Binary reference assets, e.g. the supplied brand logo source image used by `bekaa3d-brand-ui`. | — |
| `docs/architecture/` | Reserved for standalone architecture docs if/when one is written separately from the slice plans. Not created yet — nothing currently warrants it independent of `docs/plans/` and `docs/setup/frontend-setup.md`. | — |
| `docs/archive/` | Reserved for plans/docs that become superseded. Not created yet — nothing in the current set is superseded; everything in `docs/plans/` is still-relevant historical/authoritative record. | — |

## Claude Code skills

`.claude/skills/` holds four project-local skills: `bekaa3d-api-contract`,
`bekaa3d-brand-ui` (+ `tokens.md`), `bekaa3d-commerce-ux`,
`bekaa3d-frontend-slice-dod`. These stay in place — they are loaded by name
and relocating them would break skill discovery.

## Source areas

- `src/app/**` — routed pages (App Router). Only a handful of routes are
  currently mounted; see `docs/frontend-requests/BACKEND-UNLOCK-HANDOFF.md`
  for the full list of what's built vs. mounted.
- `src/components/**` — grouped by feature (`account`, `admin`, `auth`,
  `byi`, `cart`, `catalog`, `checkout`, `contact`, `feedback`, `forms`,
  `home`, `layout`, `notifications`, `payment`).
- `src/lib/**` — grouped the same way, plus cross-cutting concerns
  (`api`, `query`, `shared`, `health`).

This grouping is consistent and was left as-is during the repository
hygiene pass — no structural problems were found that justified moving
code.
