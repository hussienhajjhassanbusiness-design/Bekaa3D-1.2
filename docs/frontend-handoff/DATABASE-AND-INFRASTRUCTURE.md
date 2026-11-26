# Database and Infrastructure

> **DRAFT.** Not final until frontend editing and the final verification run are complete.

Date 2026-11-26. Verified against the running local stack.

## 1. Migration lineage (this handoff)

```
… → 941b40d285ce → 95ffee5fde3b (main, origin/main: manual_max_open_orders)
                  → b7c41e2a9d10  promotions            (ab34ff4, branch feat/promotions)
                  → c8e2f4a6b1d3  homepage_hero_image   (4289c4a, branch feat/homepage-hero-image)  ← head
```

| Revision | Creates | Downgrade |
|---|---|---|
| `b7c41e2a9d10` | enums `promotion_discount_type`, `promotion_scope`; tables `promotions` (CHECKs `ck_promotions_*`, partial index `ix_promotions_active_window WHERE is_active`) and `promotion_products` (composite PK, FK to products `RESTRICT`, to promotions `CASCADE`, index `ix_promotion_products_product`) | drops them (verified reversible) |
| `c8e2f4a6b1d3` | seeds the `settings` row `homepage_hero_image` (type `string`, JSON `null`, `on_conflict_do_nothing`) | deletes the row |

The local database is at `c8e2f4a6b1d3`; `alembic current` and `alembic heads` agree.
`tests/integration/test_model_migration_parity.py` includes the new tables.

## 2. Data preservation (local, 2026-11-26)

- PostgreSQL data lives in the named volume `bekaa3d-backend_pgdata` (created 2026-11-09).
  Recreating containers keeps it. **Never** run `docker compose down -v` or `docker volume prune`.
- Public media lives in the host folder `storage/media_public` (bind-mounted read-write into
  `api` and `worker`, read-only into `media`).
- Snapshot before and after the infrastructure work, identical: 34 products, 30 orders,
  56 users, 3 promotions, 25 product images, hero setting
  `home/hero/a1305bc954e94f78ae50955389ed4b3c.png`, 31 media files, 173 outbox emails all `sent`.

## 3. Compose services

| Service | Image | Ports | Health | Notes |
|---|---|---|---|---|
| postgres | postgres | `5442→5432` | healthy | volume `pgdata` |
| redis | redis:7-alpine | `6379` | healthy | |
| clamav | clamav | `3310` | healthy | malware scanning for uploads (fails closed) |
| api | built from `Dockerfile` | `8000` | healthy (`/health/live`) | `./src` and `./migrations` bind-mounted, `--reload` |
| worker | built from `Dockerfile` | — | healthy (`python -m app.worker_health`) | `docker compose restart worker` after worker code changes |
| **media** (new, `778a0bd`) | `bekaa3d-backend-api`, `pull_policy: never` | `127.0.0.1:8001` | disabled (the image's check probes :8000) | local development only: serves `storage/media_public` read-only for the frontend's dev `/media` rewrite |

## 4. Environment file

`.env` is required by `docker compose`: `api` and `worker` declare `env_file: .env`. It is
git-ignored (`.gitignore:26`) and must never be committed. On 2026-11-15 it was deleted together
with `.git`; on 2026-11-26 the original was restored from the Recycle Bin. A dry run confirmed it
matches the running containers. It defines every key in `.env.example`.

## 5. Starting the project

```sh
# backend, from the repository root
docker compose up -d                       # postgres, redis, clamav, api, media, worker
docker compose ps                          # every service running; all but media healthy
docker compose exec api alembic upgrade head
# first time only: seed accounts (printed once)
docker compose run --rm -T -e PYTHONPATH=src api python - < scripts/dev_seed.py

# frontend, from C:\My projects\bekaa3D
npm run dev                                # http://localhost:3000; /api → :8000, /media → :8001
```

Stop with `docker compose stop`. Rebuild images only when `requirements*.txt` or the `Dockerfile`
change: `docker compose build api worker`.

## 6. Merge notes for the backend team

- `feat/promotions` (`ab34ff4`) and `feat/homepage-hero-image` (`778a0bd`, `76f43f6` on top of
  `4289c4a`) are **local only, not pushed**. `feat/homepage-hero-image` contains
  `feat/promotions`, so merging it brings in all four commits in migration order.
- `main` and `origin/main` are both `7e52174`, with nothing newer upstream as of 2026-11-26, so
  the merge is a fast-forward.
- An unrelated, uncommitted trailing-whitespace change to `.gitignore` predates this work. Keep it
  out of the merge.
- After merging: `alembic upgrade head` (two revisions), run `scripts/export_openapi.py` (the
  committed `openapi.json` already matches), then run the full test suite once
  ([FINAL-ACCEPTANCE-CHECKLIST.md](FINAL-ACCEPTANCE-CHECKLIST.md)).

## 7. Production configuration

| ID | Item | Requirement | Status |
|---|---|---|---|
| CFG-01 | Email | A real email adapter. Only `console` exists (`integrations/email/factory.py`); verification and password-reset emails need one | Not built (VS-021 Not started) |
| CFG-02 | `/media` | A web server or CDN serving `MEDIA_PUBLIC_DIR` at `MEDIA_PUBLIC_URL` (`/media`). The compose `media` service is for development only; nginx is deliberately omitted from compose | Not configured |
| CFG-03 | Payments | `PAYMENT_PROVIDER=manual` (mock is refused in production). Frontend production build: leave `NEXT_PUBLIC_ALLOW_MOCK_PAYMENTS` unset | Config only |
| CFG-04 | Captcha | `CAPTCHA_PROVIDER=turnstile` with `TURNSTILE_SECRET`; `fake` is refused outside dev/test | Config only |
| CFG-05 | Secrets and HTTPS | Generated `JWT_SIGNING_KEY`, `CSRF_SECRET`, `IP_HASH_SALT`, `MFA_SECRET_KEY`, and a `PHONE_HASH_SALT` of at least 32 characters (startup refuses placeholders; can never be rotated). `ENVIRONMENT=production`, `DEBUG=false`, HTTPS (cookies are `Secure` outside development) | Config only |
| CFG-06 | Operations | Staging and deploy (VS-020), backups, restore drill and monitoring (VS-047), launch readiness (VS-048) | Not started |
| — | Worker probe | Production images import from site-packages (fast); `app.worker_health` works the same | Done |
