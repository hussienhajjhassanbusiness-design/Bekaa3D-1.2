# Final Acceptance Checklist

> **DRAFT.** Tick items only with evidence (command output, test report or real-browser run).
> Date of draft: 2026-11-26.

## A. Merge and build (backend)

- [ ] Merge `feat/homepage-hero-image` (includes `feat/promotions`) into `main`, without the stray `.gitignore` change
- [ ] `docker compose config --quiet` passes
- [ ] `docker compose up -d`: every service running; api, postgres, redis, clamav and worker `healthy`
- [ ] `docker compose exec api alembic upgrade head`, then `alembic current` = `c8e2f4a6b1d3 (head)`
- [ ] `scripts/export_openapi.py` produces no diff against `docs/frontend-handoff/openapi.json`

## B. Backend quality gate (NV-03)

- [ ] `ruff check`, `ruff format --check`, `mypy` (strict): clean
- [ ] Unit suite: all pass
- [ ] **Full** integration suite, run once with the test environment: `.env.example` plus
      `PHONE_HASH_SALT=test-only-phone-hash-salt-0123456789abcdef`, so the placeholder salt does
      not trip the production/staging startup tests. Last full run, 2026-11-24 (before the hero
      and worker changes): 6,986 passed, 21 failed, all 21 explained and passing on rerun
      (BACKEND-BUG-REGISTER RES-03, RES-04)
- [x] Targeted since then: promotions API and pricing, settings, hero image (268), media
      service and worker probe (22). All pass

## C. Frontend quality gate

- [ ] `npm run lint`, typecheck (`tsc --noEmit`): clean
- [ ] `npm test` (Vitest): all pass. Last full run: 2,481 tests
- [ ] `npm run build`: passes
- [ ] Full Playwright smoke suite: all pass. Last full run: 250; focused hero spec 5/5 on 2026-11-26

## D. Real-backend acceptance (no mocking, localhost:3000 → :8000, media :8001)

- [x] Seasonal promotions: 18/18 (2026-11-24, `bekaa3D/docs/backend-handoff/REAL-BACKEND-ACCEPTANCE.md`)
- [x] Hero image upload, refusal and restore: 22/22 (2026-11-26)
- [x] Hero image shows after save: same browser, already-open tab after a refresh, separate session: 12/12 (2026-11-26)
- [x] Runtime: `/health/live` and `/health/ready` 200; 11/11 public product cover images served; hero image 200 `image/png`; active promotion listed
- [ ] Rerun after the merge (sections A and B)

## E. Open items to decide or close before submission

| ID | Item | Owner | Blocks submission? |
|---|---|---|---|
| NV-03 | Full backend suite after the merge | Backend | **Yes** |
| FE-01 | Manual provider `next_step` copy | Frontend | Yes, if online checkout is demonstrated with `PAYMENT_PROVIDER=manual` |
| BUG-01 | $0 promotional price vs `zero_total` refusal | Backend + product owner | No, if 100 % and over-price fixed promotions are avoided in the demo; document it |
| FE-02, FE-03, FE-04 | Reviews, moderation, account deletion UI | Frontend | Depends on the submission scope (backend Done) |
| CFG-01 – CFG-06 | Production configuration | Ops | Only for a production launch, not a local demo |
| NV-01 | Refund void after reissue | Backend + product owner | No |
| CC-01, CC-02 | Promotion-aware price filter, sort and wishlist | Backend | No (documented limitation) |

## F. Sign-off

- [ ] Reports in `docs/frontend-handoff/` changed from DRAFT to FINAL
- [ ] Backend and frontend commit hashes recorded here
- [ ] Nothing secret committed (`.env` ignored and untracked in the backend)
