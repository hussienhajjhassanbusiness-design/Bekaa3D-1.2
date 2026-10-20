# Bekaa3D

Backend for Bekaa3D, a dual-commerce platform for a Lebanese 3D-printing business:

- **Physical catalogue** — made-to-order 3D-printed products, sold online, via WhatsApp, or both, per product.
- **STL marketplace** — 3D model files, sold online only; after payment the administrator emails the files (ADR-019).

## Status

In development, following the vertical-slice plan in [`docs/vertical-slice-plan.md`](docs/vertical-slice-plan.md). Merged so far:

- **VS-001** — bootable API, migration baseline, health/readiness, request correlation
- **VS-002** — user registration, email verification, resend, transactional outbox, first worker job
- **VS-003** — login, logout, rotating refresh sessions, CSRF, refresh-token reuse detection
- **VS-004** — password reset, with every pre-reset session and MFA challenge invalidated
- **VS-005** — administrator MFA (TOTP), login-gated admin sessions, one-time recovery codes, isolated `/api/v1/admin` boundary
- **VS-006** — current customer profile (`GET /api/v1/me`)
- **VS-007** — typed settings editor, seeded registry, and a strict public-settings allowlist
- **VS-008** — in-app notification centre (`notifications` table, own-user list with cursor pagination, read/unread mutation, `create_notification` write port)
- **VS-009** — admin user management (list/search, detail, activate/deactivate with session revocation)
- **VS-010** — category, material and colour reference data (public lists, admin CRUD, `AuditWriter` port)
- **VS-011** — hardened admin boundary (no admin route is discoverable by anonymous callers or customers; admin rate limit; the last active administrator cannot be deactivated)
- **VS-012** — monthly-partitioned audit log with a read-only admin viewer; admin PII reads audited and kept out of the access log; contexts talk only through published ports
- **VS-013** — admin product management for physical and STL products: database-enforced type integrity, optimistic versioning (`409 VERSION_CONFLICT`), soft delete releasing the slug, and a used category, material or colour cannot be archived (`409 CATEGORY_IN_USE`)
- **VS-014** — product images: content-checked, malware-scanned and re-encoded uploads, one cover per product, reordering, soft delete, and a daily orphan-file reaper
- **VS-015** — public catalogue: browse physical and STL products with AND-combined facets, price/rating/newest sorts and stable cursors; product pages with gallery, SEO fields and commerce capabilities; hidden, deleted and inactive-category products never show
- **VS-016** — search and autocomplete: English full-text search over names and descriptions ranked by relevance (name above description), trigram fallback below five hits (terms with a 3+ letter word that exclude no word) that finds one-typo queries, mode pinned in the cursor, and `GET /search/suggestions` (a 3+ letter word, at most 10); search p95 174-181 ms on 10,000 products (the test's own query shapes, including the slowest the fallback allows, measured locally after the audit fix; budget 800 ms)
- **VS-022** — mixed cart: one persistent cart per verified customer mixing physical and STL products, merges within the live per-line cap (never clamped), STL quantity 1 enforced in the database, price snapshot with `price_changed`, `over_cap` and `purchasable` flags, a 50-line cap, and a per-cart lock that serialises concurrent adds
- **VS-023** — checkout and verified payment for digital orders: an idempotent two-transaction checkout at live prices (owned STLs dropped and named, every unbuyable line named), the provider called with no transaction open, a signed and rate-limited payment webhook answered at once, verification that asks the provider itself and pays only an exact USD match (anything else is a late capture, recorded once), STL lines moved to `awaiting_delivery`, the mock provider with `scripts/mock_pay.py`, and a boot refusal of the mock in production ([ADR-032](docs/adr/ADR-032-checkout-idempotency-and-payment-verification.md), [`docs/checkout.md`](docs/checkout.md))
- **VS-024** — payment recovery: a customer retries a failed or expired payment on the same order within its hold; a 15-minute reconciliation applies missed callbacks; unpaid checkouts are released only on the provider's explicit `failed` or `expired`, and an administrator releases the rest after a 24 h grace; manual confirmation for providers without a status API refuses a differing amount; late captures store the captured amount and alert every administrator ([ADR-036](docs/adr/ADR-036-payment-recovery.md), [`docs/payment-recovery.md`](docs/payment-recovery.md))
- **VS-026** — address book: up to 20 Lebanese delivery addresses per customer, phones normalised to E.164, required landmark notes, the first address default automatically, and default switches atomic under a per-user lock (one default per user, enforced in the database)
- **VS-033** — public contact form and audited admin message queue (forward-only statuses under a row lock); Cloudflare Turnstile captcha, failing closed, on the contact form, registration, resend verification and the password-reset request
- **VS-034** — Bring Your Idea submission: a guest multipart form (0–5 reference images) behind a pre-parse attempt limit, captcha and per-IP/per-email limits; every image scanned raw, re-encoded and stored privately; each active administrator notified in-app; attachments purged daily after a 90-day, admin-editable retention, and orphans reaped ([ADR-030](docs/adr/ADR-030-bring-your-idea-submission.md))
- **VS-035** — Bring Your Idea pipeline: an audited admin queue and detail, transitions along `new → contacted → quoted → in_progress → completed → closed` (or `lost`) under a row lock, a required quote in cents, a server-derived won/lost outcome, private attachments streamed to administrators only (`no-store`, `attachment`, `nosniff`; expired ones are 404), and a submission-cohort conversion funnel ([ADR-031](docs/adr/ADR-031-bring-your-idea-pipeline-and-api-streamed-download.md))
- **VS-038** — wishlist: idempotent add/remove (`PUT`/`DELETE /me/wishlist/{product_id}`), cursor-paginated own list, a maintained `products.wishlist_count` kept exact under concurrent writes (DB-enforced one-active-row-per-user-and-product), and an admin wishlist-totals/most-wishlisted read
- **VS-046** — security data retention: a daily purge of expired verification and reset tokens (7 d past expiry) and ended sessions (30 d past the earlier of expiry and revocation), both admin-editable within 1–90 d, batched with `SKIP LOCKED`; and keyed IP hashes (HMAC under an env pepper plus a database salt) whose salt is rotated and deleted once per UTC month, so old hashes cannot be linked to new ones ([ADR-028](docs/adr/ADR-028-keyed-monthly-rotated-ip-hashes.md))

Each slice adds one complete, tested, end-to-end capability. Build order and the status of every slice live in [`docs/vertical-slice-plan.md`](docs/vertical-slice-plan.md); the SRS [Build Phases](docs/SRS.md#28-build-phases) describe scope, not order. Everything that needs a server (VS-020 staging and deploy, VS-021 production email, VS-032 the live payment provider, VS-047 backups and monitoring, VS-048 launch readiness) is a final phase, built once the rest is finished and tested locally.

## Documentation

[`docs/SRS.md`](docs/SRS.md) is the **single authoritative document** for this project — business rules, features, domain model, database schema, API contract, and non-functional/security requirements. Where anything else conflicts with it, the SRS wins.

Supporting documents in [`docs/requirments/`](docs/requirments/):

| Document | Purpose |
| --- | --- |
| [`project-brief.md`](docs/requirments/project-brief.md) | Business case, scope, constraints, budget, and milestones |
| [`entities-and-business-rules.md`](docs/requirments/entities-and-business-rules.md) | Entity-by-entity model: identity, lifecycle, invariants, deletion strategy |
| [`functional-requirements.md`](docs/requirments/functional-requirements.md) | Gherkin-style functional requirements (FR-01 … FR-19) with negative cases and concurrency behaviour |
| [`non-functional-requirements.md`](docs/requirments/non-functional-requirements.md) | Performance, availability, retention, and capacity targets |
| [`domain-glossary.md`](docs/requirments/domain-glossary.md) | Canonical vocabulary — required naming across code, database, API, and docs |

Architecture decisions get recorded in [`docs/adr/`](docs/adr/) as they're made.

## Stack

| Layer | Technology |
| --- | --- |
| API | Python 3.13, FastAPI, Pydantic v2 |
| ORM | SQLAlchemy 2 (async), Alembic migrations |
| Database | PostgreSQL 16 |
| Queue / cache / rate limits | Redis |
| Worker | arq (jobs and cron) |
| Reverse proxy | nginx (TLS, static assets, rate limiting) |
| Scanning | ClamAV |
| Containerisation | Docker Compose |

Architectural style: Clean Architecture (domain → application → infrastructure → API) organized into bounded contexts (Identity, Catalog, Ordering, Payments, Fulfillment, Negotiation, Engagement, Platform). See [SRS §18](docs/SRS.md#18-architecture).

## Project Layout

```
src/                   # application code (src/app/, per pyproject.toml)
tests/                 # unit, integration, contract, e2e, concurrency, security tests
migrations/            # Alembic migrations
docs/
  SRS.md               # authoritative specification
  requirments/          # supporting requirements documents
  adr/                 # architecture decision records
.env.example           # required environment variables — copy to .env
```

## Getting Started

### Bootstrap

```
cp .env.example .env          # fill in real secrets before anything but local dev
docker compose up -d --build  # postgres, redis, clamav, api
docker compose exec api alembic upgrade head
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

`.env.example` documents every environment variable the application needs (database, Redis, JWT/CSRF secrets, storage paths, Whish, email, captcha, observability). Note that on this machine host port `5432` is already in use by a native Windows PostgreSQL service (not Docker), so `docker-compose.yml` publishes `postgres` on `5442` instead — change it back to `"5432:5432"` once that conflict is resolved. `api`/`redis`/`clamav` use their standard ports (`8000`/`6379`/`3310`).

For local Python tooling (ruff, mypy, pytest) outside Docker:

```
python -m venv .venv
source .venv/Scripts/activate   # .venv/bin/activate on Linux/macOS
pip install --require-hashes -r requirements-dev.txt   # exact, tested versions
pip install --no-deps -e .
ruff check . && ruff format --check . && mypy src tests && pytest
```

### Smoke checks

```
pytest -m smoke                                 # fast must-work tests (~30s); suite list: tests/smoke/
scripts/smoke/vs012_post_deploy.sh              # read-only post-deploy check, local docker compose stack
READONLY_DATABASE_URL=... API_LOG_CMD="..." WORKER_LOG_CMD="..." \
  scripts/smoke/vs012_post_deploy.sh https://<site>   # the same, against the live site after every deploy
```

The post-deploy script sends only anonymous `GET`s and runs every query in a read-only transaction; see its header for every variable.

### Health endpoints

Both live outside `/api/v1` (they're operational, not business API) and never require authentication:

- `GET /health/live` — process liveness only. Never probes the database or Redis; a slow dependency must never make an orchestrator kill a healthy process. Always `200` if the process is running.
- `GET /health/ready` — checks the dependencies this instance actually needs (Postgres, Redis). Returns `200` with `{"status": "ok", "version", "commit"}` when ready, or a `503` RFC 9457 problem response when a dependency is unreachable. Never includes secrets.

### Migrations

```
docker compose exec api alembic upgrade head        # apply
docker compose exec api alembic revision -m "..."    # new empty revision
```

Migrations run against `DATABASE_URL` from the environment. Alembic is configured for SQLAlchemy's async engine (`migrations/env.py`), so no separate sync driver is needed.

### Request correlation and logging

Every request gets a stable ID (`X-Request-ID`): the incoming header value if the caller supplies one, otherwise a generated `req_<uuid4hex>`. It's echoed back as a response header and bound into every structured log line for that request, and it appears as `request_id` in every error response body. Logs are structured via `structlog` — JSON in production, human-readable console output in development (`ENVIRONMENT` setting).

### Error contract

Every non-2xx API response is `application/problem+json` (RFC 9457): `type`, `title`, `status`, `detail`, `instance`, a stable machine-readable `code`, `request_id`, and an `errors` array for field-level validation failures. Clients should branch on `code`, never on `detail` (which is a diagnostic string, not a translation key). See `docs/requirments/api-endpoints.md` §5 for the full stable error-code table.

### Background jobs (worker)

The `worker` Compose service runs `arq app.worker.WorkerSettings`, sharing one process for both on-demand jobs and cron schedules (arq's `unique=True` cron default means a schedule only fires once even with multiple worker replicas — see `docs/adr/`). Job functions and their schedules live in `src/app/jobs/registry.py`; each job is a plain coroutine that takes an arq `ctx` dict, so it can be unit-tested by calling it directly with a fake `ctx`.

`dispatch_outbox` (every minute, plus once at worker startup) claims due `email_outbox` rows with `SELECT ... FOR UPDATE SKIP LOCKED` — safe with multiple worker replicas — and hands each to the configured email provider. A provider failure never crashes the batch: the message stays `pending` with exponential backoff until it hits 5 attempts, then moves to `failed` and logs at error level.

Watch it locally:

```
docker compose logs -f worker
```

### Registration and email verification (VS-002)

`POST /api/v1/auth/register`, `/verify-email`, and `/resend-verification` are all **enumeration-safe**: the response is identical regardless of whether the email is new, already registered-unverified, or already verified — see `docs/requirments/api-endpoints.md` §8.1. Registration writes the user, verification token, outbox message, and audit-log row in one transaction; the actual email send happens later via the outbox worker, so an email-provider outage never rolls back an account creation.

`EMAIL_PROVIDER=console` (the `.env.example` default) logs that an email was "sent" instead of sending it. The log line (`console_email_send`) carries only the names of the payload fields, never the token (SEC-26), so it cannot give you a verification link. To read one during local development, stop the worker and query `email_outbox`; the exact commands are in [`docs/frontend-handoff/BACKEND-RESPONSE.md`](docs/frontend-handoff/BACKEND-RESPONSE.md) (item A3).

### Frontend handoff and development seed

[`docs/frontend-handoff/`](docs/frontend-handoff/) answers the frontend team's contract questions, and holds `openapi.json` (regenerate with `python scripts/export_openapi.py`; a unit test fails while it is stale). `scripts/dev_seed.py` fills a development database with an administrator (MFA enrolled), a verified customer and a small catalogue:

```
docker compose run --rm -T -e PYTHONPATH=src api python - < scripts/dev_seed.py
```

It refuses to run unless `ENVIRONMENT` is `development` or `test`, and prints the generated credentials once.

### Browser sessions (VS-003)

`POST /api/v1/auth/login` sets three cookies and returns `SessionRead`. The tokens are never in the response body.

| Cookie | Contents | Lifetime | `httpOnly` | `Path` |
| --- | --- | --- | --- | --- |
| `access_token` | signed JWT: user, session, role, verified flag | `ACCESS_TOKEN_MINUTES` (15) | yes | `/` |
| `refresh_token` | signed JWT: session id + `token_version` | `REFRESH_TOKEN_DAYS` (30) | yes | `/api/v1/auth` |
| `csrf_token` | `HMAC(CSRF_SECRET, session_id)` | 30 days | **no** | `/` |

`csrf_token` is deliberately readable by JavaScript: every unsafe cookie-authenticated request must echo its value in the **`X-CSRF-Token`** header, or the request is rejected with `403 CSRF_INVALID`. Because the token is derived from the session id rather than being a random value, a token minted for one session cannot be replayed against another.

`POST /api/v1/auth/refresh` rotates the refresh token, replaces `sessions.refresh_token_hash`, and increments `token_version`. Rotation does **not** extend `expires_at`, so a session always dies on its original deadline.

**Refresh-token reuse detection.** A validly signed refresh token carrying an *older* `token_version` can only be a replay of a token that was already rotated away. That is treated as theft: `reuse_detected_at` and `revoked_at` are both set, the whole session dies, and a fresh login is required. The response is an ordinary `401 AUTH_REQUIRED` — identical to any other rejected token, so an attacker learns nothing.

A consequence worth knowing: two clients sharing one session (for example two browser tabs refreshing at the same instant) will trip this. The row lock guarantees exactly one rotation succeeds, and the loser is indistinguishable from a replay, so it revokes the session. That is the intended strict-rotation trade-off, not a bug.

**Logout, and the 15-minute access-token tail (accepted trade-off).** `POST /api/v1/auth/logout` ends the session named by the access token, or — once that has expired — by the refresh cookie, so logging out still works after the tab has been idle; it always clears the cookies. What logout does *not* do is invalidate an access token that was already issued: authentication checks the signature and the account-wide `auth_epoch` (ADR-018), not the individual session row (ADR-006), so a copied access token keeps working for at most `ACCESS_TOKEN_MINUTES` (15) after logout or after refresh-token reuse is detected. Events that must cut access immediately — password reset, deactivation — advance the epoch instead. `test_an_access_token_lives_out_its_fifteen_minutes_after_logout` documents the exact behaviour.

Repeated login failures are throttled per `(email, IP)`. Thresholds count **attempts**, not failures already recorded: attempts 1–3 are free, attempts 4–7 wait 1s/2s/4s/8s, 8 and 9 stay at the 8s cap, and the 10th attempt is refused outright for 15 minutes (`429 RATE_LIMITED` with `Retry-After: 900`). Counters live in Redis and reset on a successful login.

### Password reset (VS-004)

`POST /api/v1/auth/password-reset/request` always answers `202` with the same body, whether the address is unknown, known and eligible, or known but still inside its cooldown. Nothing about the account leaks through the status, the body, or a missing email — the enumeration rule from registration applies here too (`docs/requirments/api-endpoints.md` §5).

Eligible accounts get an outbox message (`password_reset_email`) carrying a 32-byte random token. Only its SHA-256 hash reaches `password_reset_tokens`, so a database leak yields nothing redeemable. The window is **1 hour**, deliberately shorter than the 24h a verification token gets: this token authorises taking over an account. A **2-minute cooldown** per account stops one visitor flooding a mailbox.

`POST /api/v1/auth/password-reset/confirm` takes `{token, new_password}` and returns `204`. In one transaction it:

1. reads the token `FOR UPDATE` and marks it used — single-use has to survive two requests arriving at once, not just in sequence;
2. takes a row lock on the user (see **Racing an MFA login** below);
3. advances the account's **authentication epoch**, invalidating every access token, session and outstanding MFA challenge at once;
4. replaces the Argon2id password hash;
5. burns every **other** unused reset token the account holds, so an older link the user requested earlier stops working;
6. **revokes every session** the user has (SEC-08);
7. writes a `user.password_reset` audit row recording how many sessions died.

Steps 3 and 6 are the point of the whole slice. The usual reason to reset a password is that somebody else may have it, and an attacker who is already logged in keeps a working refresh token for 30 days unless the reset kills it. Changing the credential without ending the sessions would report success while leaving the intruder inside.

**Pre-reset authentication state, and what survives.** Sessions are not the only thing a reset has to end, and the other two live outside the `sessions` table. An access token is signed and self-contained, good for its full 15 minutes. An MFA login challenge — handed out as soon as an administrator's password checks out — lives in Redis. Revoking rows reaches neither, so before ADR-018 a reset left the attacker's access token working and their challenge redeemable.

All three now carry the account's **authentication epoch**, a monotonic counter in `users.auth_epoch`: access tokens as an `auth_epoch` JWT claim, challenges alongside the user id in Redis. A successful reset advances it by one — in the same transaction, on the same locked row, as the password change and the session revocation — and every authentication decision refuses anything stamped with a stale value.

It lives in PostgreSQL rather than Redis on purpose. A cache that answers *successfully* with a lost key — a restarted container, an evicted entry, a restored snapshot — would silently re-validate every token the reset had just revoked, and that failure looks exactly like normal operation. `docker-compose.yml` runs `redis:7-alpine` with no volume under `restart: unless-stopped`, so an empty, healthy keyspace after a restart is the expected case, not an edge one.

`current_claims` validates the JWT signature and standard claims first — a forged or expired token is refused with no database traffic at all — and only then reads one indexed scalar. Tokens minted before this claim existed read as epoch 0, as does every pre-existing row, so current sessions survive the deploy and start failing only once their account's epoch actually moves. This reverses one half of ADR-006 knowingly; see [ADR-018](docs/adr/ADR-018-authentication-epoch.md).

**Lock order is `users` before `sessions`, everywhere** — reset, login, MFA completion and refresh rotation. Refresh was restructured for it: VS-003 locked the session row first, and bolting a user lock on after it closes a deadlock cycle against the reset's order (PostgreSQL reports `DeadlockDetectedError`). Login takes the lock *before* verifying the password, so a reset committing mid-login cannot leave login validating a hash the database no longer holds.

The invalidation runs **before** the database writes are allowed to stand. If Redis is unreachable it raises, the transaction rolls back, and no reset is reported — the endpoint fails closed rather than answering `204` while a pre-reset challenge is still live. The reverse (challenges invalidated for a reset that then fails) costs an administrator one extra sign-in and is the safe direction to err.

What a reset deliberately does **not** touch: MFA enrolment, the TOTP secret, and the recovery codes. A reset proves control of the mailbox, which is exactly the thing the second factor exists to be independent of — clearing it would turn a mailbox compromise into a full account takeover.

**Racing an MFA login.** Both the reset and `POST /auth/mfa/verify` take `SELECT ... FOR UPDATE` on the user row, so they cannot interleave and only two orderings exist. If the reset commits first, the epoch check refuses the challenge and no session is ever created. If the redemption commits first, its session already exists when `revoke_all_for_user` runs, so the reset revokes it. Without that lock a third ordering is possible — the redemption inserting its session *after* the revocation `UPDATE` has run — which would leave a live session minted from a pre-reset challenge. `tests/concurrency/test_password_reset_vs_mfa_challenge.py` holds that hole closed.

Failures follow the same shape as email verification: `410 RESOURCE_EXPIRED` for a token past its window, `400 INVALID_TOKEN` for one that is unknown, already used, or belongs to a deactivated account. The used check runs before the expiry check, so a replayed token always answers `400` — a status code that changed once the window closed would tell an attacker when the token was issued.

Reset tokens and verification tokens live in separate tables and cannot be redeemed at each other's endpoints. They prove different things: control of a mailbox, versus authority to replace a credential.

## Conventions

Working conventions are in [`CONTRIBUTING.md`](CONTRIBUTING.md). Architecture rules, naming and the invariants that must hold under concurrency come from the [SRS](docs/SRS.md), the [domain glossary](docs/requirments/domain-glossary.md), [`entities-and-business-rules.md`](docs/requirments/entities-and-business-rules.md) and the [ADR index](docs/adr/README.md).
