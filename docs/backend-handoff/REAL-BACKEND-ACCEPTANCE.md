# Real Backend Acceptance

**Date:** 2026-10-19
**Frontend commit:** `53b1ef33d5c2c22951d145e5bb5e1494cccb62c7` (`chore: retire ADR-019/ADR-024 frontend slices (FVS-018/019/020/021/024)`)
**Backend commit:** N/A — no backend checkout available in this workspace (see below)

## Outcome

**Real-runtime acceptance (Steps 2–9 of the acceptance phase) was not attempted.**
Environment discovery (Step 1) found a hard blocker: no backend repository and
no Docker runtime are available in this workspace. Per the acceptance
phase's own instruction ("If the backend repository is unavailable, STOP the
real-runtime portion and return the exact prerequisite needed"), the
real-runtime portion stopped at that gate. No mocked test was substituted
and reported as real acceptance.

## Environment discovery (Step 1)

| Check | Result |
|---|---|
| Docker (`docker --version`) | Not found — checked in both the Bash tool's shell and native PowerShell (`Get-Command docker` returns nothing) |
| Docker Compose | Not available (no `docker` binary at all) |
| Backend repository, locally | Not present. `C:\My projects\` contains only `bekaa3D` (this frontend) and an unrelated `h1.html`; no sibling backend checkout exists |
| Backend repository location, from docs | Not discoverable — `docs/backend-handoff/README.md` and `docs/setup/frontend-setup.md` describe how to start the backend but name no concrete local path or remote URL for this engagement; `frontend-setup.md` itself already states "This frontend workspace does not have the backend checkout available (no sibling backend repo, no Docker on this machine)" |
| Frontend Node version | v24.11.1 |
| Frontend npm version | 11.6.2 |
| Required frontend env vars | `API_PROXY_TARGET` (server-side only, read by `next.config.ts`'s `rewrites()`) |
| `.env.local` present | No — only the committed `.env.local.example` (`API_PROXY_TARGET=http://localhost:8000`) exists; no local override has been created, since there is nothing local to point it at |
| Current proxy configuration | `next.config.ts` registers two rewrites when `API_PROXY_TARGET` is set: `/api/health/:path*` → `${target}/health/:path*`, and `/api/:path*` → `${target}/api/:path*` (specific-before-general, matching `frontend-setup.md`). No `/media/*` rewrite exists yet — it is documented as a workaround to add once a backend checkout is available, per B4 |
| `/media` local dev setup | Not configured — correctly so, since there is no backend `storage/media_public/` directory to serve locally |

## Exact prerequisite needed to proceed

To run Steps 2–9 of this acceptance phase, this environment needs, in order:

1. **Docker Desktop (or an equivalent Docker Engine + Compose) installed** on this machine — currently absent entirely.
2. **A local checkout of the Bekaa3D backend repository**, alongside (or anywhere accessible from) this frontend checkout — currently absent. Its documented startup sequence (`docs/backend-handoff/README.md`) is:
   ```sh
   cp .env.example .env            # then replace every placeholder secret with one you generate
   docker compose up -d --build
   docker compose exec api alembic upgrade head
   docker compose run --rm -T -e PYTHONPATH=src api python - < scripts/dev_seed.py
   ```
3. Once the backend is running and seeded: a frontend `.env.local` pointing `API_PROXY_TARGET` at the backend's real local address, and the development-only `/media/*` rewrite added to `next.config.ts` per `docs/setup/frontend-setup.md`'s "Local Media Proxy" section, forwarding to a local static server over the backend's `storage/media_public/` folder (e.g. `npx serve storage/media_public -l 8001`).

None of this was installed or created automatically, per the acceptance phase's explicit instruction not to install system software or pretend mocked tests are real acceptance.

## Capabilities intentionally NOT tested (and why)

Every item in Steps 5–8 (public storefront, customer/auth, admin, error-contract
acceptance against a live backend) was **not tested**, for the single reason
above: no backend process exists to test against in this environment. This is
distinct from "not built" (per `BACKEND-RESPONSE.md`'s status table, most of
these capabilities — public settings, catalogue, auth, password reset,
notifications, admin CRUD, image upload, CSRF — are in fact already **Built**
on the backend side); the gap here is purely environmental (no runtime
available locally), not a backend-coverage gap.

This matches every prior phase's own documented state in
`docs/setup/frontend-setup.md` ("Real backend acceptance — still pending" /
"not attempted" sections for FVS-001, FVS-002, FVS-003, FVS-006, and the
Phase 1 storefront integration) — this phase did not change that state,
because the same blocking prerequisite (no backend, no Docker) is still
present.

## Frontend changes made this phase

None. No frontend defect could be exercised without a running backend, so
Step 9 (fix only real integration defects) does not apply. Working tree was
clean before this phase and remains clean except for this document.

## Exact commands to reproduce (once prerequisites are met)

```sh
# From the backend repository root
cp .env.example .env   # fill in generated secrets
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose run --rm -T -e PYTHONPATH=src api python - < scripts/dev_seed.py
npx serve storage/media_public -l 8001   # separate terminal, left running

# From this frontend repository root
cp .env.local.example .env.local   # set API_PROXY_TARGET to the running backend's address
# add the /media/:path* rewrite described in docs/setup/frontend-setup.md
npm install
npm run dev
npm run test:e2e:backend   # real-backend connectivity smoke test
```

Then re-run this acceptance phase's Steps 2–9 against the live backend.
