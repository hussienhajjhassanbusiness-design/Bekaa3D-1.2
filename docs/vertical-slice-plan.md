# Bekaa3D — Vertical Slice Plan

Slices are ordered by **dependency first** (a slice never relies on something that does not exist yet), then **risk** (security, money, file delivery and concurrency are proven early, on their thinnest path), then **business value**. Each slice is one working capability through every layer (migration, domain, application, API, tests, docs), mergeable on its own. [`docs/SRS.md`](SRS.md) wins over this plan on any requirement; this plan only decides order and packaging.

| ID | Title | Depends on | Status |
|---|---|---|---|
| VS-001 | Bootable API, migration baseline, health, request correlation | — | Done |
| VS-002 | Registration, email verification, outbox, worker | VS-001 | Done |
| VS-003 | Login, logout, rotating refresh sessions, CSRF | VS-002 | Done |
| VS-004 | Password reset with global revocation | VS-002, VS-003 | Done |
| VS-005 | Administrator MFA and the admin boundary | VS-003 | Done |
| VS-006 | Current customer profile | VS-003 | Done |
| VS-007 | Typed settings and public settings | VS-005 | Done |
| VS-008 | In-app notification centre | VS-003 | Done |
| VS-009 | Admin user management | VS-005 | Done |
| VS-010 | Categories, materials, colours | VS-005 | Done |
| VS-011 | Harden the admin boundary and request handling | VS-005, VS-009 | Done |
| VS-012 | Partitioned audit log and audit-log viewer | VS-002, VS-005 | Done |
| VS-013 | Admin product management | VS-010 | Done |
| VS-014 | Product images with storage and malware scanning | VS-013 | Done |
| VS-015 | Public catalogue: browse, filter, sort, detail | VS-013, VS-014 | Done |
| VS-016 | Search and autocomplete | VS-015 | Done |
| VS-017 | STL bundle upload and version publishing | — | Removed (ADR-019) |
| VS-018 | Entitlements: admin grant and STL library | — | Removed (ADR-019) |
| VS-019 | Protected STL download through nginx | — | Removed (ADR-019) |
| VS-022 | Mixed cart | VS-013 | Done |
| VS-023 | Checkout and verified payment for digital orders | VS-022, VS-008, VS-007 | In progress |
| VS-023b | STL delivery queue and mark-as-sent | VS-023 | Not started |
| VS-024 | Payment recovery: reconciliation, stale checkouts, manual confirm | VS-023 | Not started |
| VS-025 | Customer order history | VS-023 | Not started |
| VS-026 | Address book | VS-008 | Done |
| VS-027 | Shipping zones | — | Removed (ADR-024) |
| VS-028 | Physical checkout: delivery, pickup, payment method, dispatch estimate | VS-023, VS-024, VS-026 | Not started |
| VS-029 | Admin order queue, fulfillment and cash handover | VS-028, VS-023b, VS-024, VS-025 | Not started |
| VS-030 | Refunds and settlement | VS-029, VS-024 | Not started |
| VS-031 | Cancellation and returns | VS-030 | Not started |
| VS-033 | Contact form and captcha | VS-005 | Done |
| VS-029b | Receipt confirmation and problem report | VS-029, VS-033 | Not started |
| VS-034 | Bring Your Idea submission | VS-014, VS-033 | Done |
| VS-035 | Bring Your Idea pipeline and funnel | VS-034 | Done |
| VS-036 | Reviews and Verified Purchase badge | VS-015, VS-028, VS-030, VS-031 | Not started |
| VS-037 | Review moderation | VS-036 | Not started |
| VS-038 | Wishlist and wishlist analytics | VS-013 | Done |
| VS-039 | Offer submission and inactivity expiry | VS-023, VS-007 | Not started |
| VS-040 | Offer counter, accept, reject, withdraw | VS-039 | Not started |
| VS-041 | Accepted-offer checkout and auto-close | VS-040, VS-023, VS-024 | Not started |
| VS-042 | Download statistics rollup | — | Removed (ADR-019) |
| VS-043 | Business analytics | VS-029, VS-030, VS-031, VS-036, VS-039 | Not started |
| VS-044 | Customer data export | VS-023b, VS-025, VS-026, VS-036, VS-039 | Not started |
| VS-045 | Account deletion by anonymisation | VS-026, VS-031, VS-036, VS-038, VS-039 | Not started |
| VS-046 | Security data retention and IP-salt rotation | VS-004 | Done |
| **Final phase** | **Needs a server; built after everything above is finished and tested locally** | | |
| VS-020 | Staging environment and deploy pipeline | VS-015 | Not started |
| VS-021 | Production email delivery | VS-020 | Not started |
| VS-032 | Live online payment provider | VS-020, VS-024, VS-030 | Not started |
| VS-047 | Backups, restore drill and monitoring | VS-020 | Not started |
| VS-048 | Launch readiness | VS-011 – VS-047 | Not started |

**Final phase (owner decision, 2026-10-17):** no server is set up until the project is finished and tested locally. VS-020, VS-021, VS-032, VS-047 and VS-048 come last, in that order. Nothing before them may depend on them; where an earlier slice would have used nginx, it uses the API instead and records how VS-020 may take over (VS-035, ADR-031).

---

## VS-001 — Bootable API, migration baseline, health, request correlation
**Status:** Done
**Depends on:** —
**Goal:** The API starts against PostgreSQL, and CI can prove it is alive and ready.
- **Model / migration:** `24d82aa2fbee`, the Alembic baseline creating extensions `pgcrypto`, `citext`, `pg_trgm`, `unaccent` and `btree_gin`.
- **Endpoints / jobs:** `GET /health/live` (no dependency probing) and `GET /health/ready` (probes Postgres and Redis; returns version and commit).
- **Logic:**
  - `X-Request-ID` middleware: echoes a caller-supplied ID or generates `req_<uuid4hex>`.
  - structlog logging: JSON in production, console in development.
  - Every error is RFC 9457 `application/problem+json` with a stable `code` and the `request_id`.
- **Tests:** `tests/integration/test_health.py`, `test_migrations.py`, `test_migration_reversibility.py`; `tests/unit/test_error_contract.py`, `test_errors.py`.
- **Done when:**
  - Liveness answers without touching the DB.
  - Readiness returns 503 as a problem response when a dependency is down.
  - Every response carries a request ID.
  - The migration chain upgrades and downgrades cleanly.

## VS-002 — Registration, email verification, outbox, worker
**Status:** Done
**Depends on:** VS-001
**Goal:** A visitor registers and verifies their email through a durable outbox, and an email failure never rolls back a registration.
- **Model / migration:** `42601a09ada6` creates `users`, `verification_tokens`, `email_outbox` and `audit_logs`. `audit_logs` is a plain, unpartitioned table; VS-012 fixes that. `8bd689bf2024` - which sits after VS-005's `c42f47ccac47` in the revision chain - adds the outbox attempt-count check, the verification-token expiry index, and a backfill that redacts raw tokens from already-delivered outbox payloads.
- **Endpoints / jobs:**
  - `POST /api/v1/auth/register`, `/verify-email` and `/resend-verification`.
  - Jobs in `src/app/jobs/registry.py`: `dispatch_outbox` (every minute and at worker start) and `purge_unverified_accounts` (daily; SRS §23 uses the same name).
- **Logic:**
  - Argon2id password hashing.
  - Enumeration-safe responses.
  - Hashed single-use verification tokens.
  - User, token, outbox row and audit row are written in one transaction.
  - The outbox is claimed with `FOR UPDATE SKIP LOCKED`, backs off exponentially, and marks a message `failed` after 5 attempts.
  - Email goes through a provider port with a `console` adapter only.
  - `core/rate_limit.py` provides the fixed-window Redis rate limiter used by every public endpoint.
- **Tests:** `tests/integration/identity/test_registration.py`, `test_verify_email.py`, `test_resend_verification.py`, `test_purge_unverified.py`; `tests/integration/platform/test_outbox_*.py`.
- **Done when:**
  - Responses are identical for new, unverified and verified addresses.
  - A used token returns 400 and an expired one 410. Once VS-046 purges the expired token (7 days past expiry by default), the link returns 400 `INVALID_TOKEN`.
  - Two workers never send the same outbox row.

## VS-003 — Login, logout, rotating refresh sessions, CSRF
**Status:** Done
**Depends on:** VS-002
**Goal:** A customer keeps a secure browser session, and replaying a stolen refresh token kills that session.
- **Model / migration:** `33a9f7a809ea` creates `sessions` (hashed refresh token, `token_version`, rotation, reuse and revocation timestamps).
- **Endpoints / jobs:** `POST /api/v1/auth/login`, `/logout`, `/refresh`.
- **Logic:**
  - JWT cookies: `access_token` (15 min) and `refresh_token` (30 days, path `/api/v1/auth`).
  - `csrf_token` = HMAC of the session ID, which must be echoed back in `X-CSRF-Token`.
  - Refresh rotates under `SELECT … FOR UPDATE`.
  - A token carrying a stale version revokes the session.
  - A per-`(email, IP)` Redis login throttle (attempts 4–7 delayed 1/2/4/8 s; the 10th locked out for 15 min with `Retry-After`).
- **Tests:** `tests/integration/identity/test_login.py`, `test_session_lifecycle.py`; `tests/concurrency/test_refresh_rotation.py`; `tests/unit/test_csrf.py`, `tests/unit/identity/test_login_throttle.py`.
- **Done when:**
  - A missing CSRF header returns 403 `CSRF_INVALID`.
  - Replaying a rotated refresh token revokes the session.
  - Bad credentials are enumeration-safe.

## VS-004 — Password reset with global revocation
**Status:** Done
**Depends on:** VS-002, VS-003
**Goal:** A customer recovers their account without the flow leaking which emails exist, and the reset ends every earlier session, token and MFA challenge.
- **Model / migration:** `6bb89f11d84b` creates `password_reset_tokens` and adds `users.auth_epoch` (ADR-018).
- **Endpoints / jobs:** `POST /api/v1/auth/password-reset/request` (uniform 202; 1 h token; 2 min cooldown) and `/confirm` (204).
- **Logic:** Confirm runs in one transaction:
  1. Lock the token, then lock the user.
  2. Advance `auth_epoch`, replace the password hash, and burn the user's other reset tokens.
  3. Revoke every session. Outstanding access tokens and MFA login challenges are invalidated by the `auth_epoch` advanced in step 2, which lives in PostgreSQL (ADR-018) - nothing in the reset touches Redis, so there is no Redis failure mode to fail closed on.
  4. Write the audit row.

  Lock order is `users` before `sessions` everywhere.
- **Tests:** `tests/integration/identity/test_password_reset*.py`, `test_auth_epoch.py`; `tests/concurrency/test_password_reset_*.py` (3 files).
- **Done when:**
  - Pre-reset access tokens, sessions and MFA challenges are refused.
  - A token works exactly once under concurrency.

## VS-005 — Administrator MFA and the admin boundary
**Status:** Done
**Depends on:** VS-003
**Goal:** Admin features are built behind one tested boundary: authenticated, administrator, MFA complete.
- **Model / migration:** `c42f47ccac47` creates `mfa_credentials` (encrypted TOTP secret) and `mfa_recovery_codes` (hashed, one-time).
- **Endpoints / jobs:** `POST /api/v1/auth/mfa/setup`, `/setup/confirm`, `/verify`, `/recovery-codes/regenerate`. `/api/v1/admin` router (`src/app/api/v1/admin.py`) with router-level `require_admin`.
- **Logic:**
  - Admin sessions are gated at login (ADR-017).
  - Anonymous callers get 401 on real admin routes (an imaginary admin path answers 404 today; VS-011 makes it 401 everywhere - BUG-08). Non-admins get 404 on real and imaginary paths alike for the routed method (a wrong method or trailing slash still reveals the route until VS-011 - BUG-10, BUG-29). Admins without MFA get 401 `MFA_REQUIRED`.
  - TOTP steps cannot be replayed.
- **Tests:** `tests/integration/identity/test_mfa_*.py`, `tests/integration/test_admin_boundary.py`; `tests/concurrency/test_totp_step_single_use.py`, `test_recovery_code_single_use.py`.
- **Done when:**
  - A customer gets 404 on every `/api/v1/admin/*` path.
  - A recovery code works exactly once.

## VS-006 — Current customer profile
**Status:** Done
**Depends on:** VS-003
**Goal:** A signed-in user reads their own profile.
- **Model / migration:** None.
- **Endpoints / jobs:** `GET /api/v1/me` (`UserProfileRead`).
- **Logic:** `current_user` dependency. The endpoint is read-only because V1 has no mutable profile field. Unverified users may read.
- **Tests:** `tests/integration/identity/test_profile.py`, `tests/unit/identity/test_profile_schema.py`.
- **Done when:** A user sees only their own ID, email and verification or account state.

## VS-007 — Typed settings and public settings
**Status:** Done
**Depends on:** VS-005
**Goal:** The administrator changes business parameters without a deploy. The public site reads five safe values.
- **Model / migration:** `de1d8a23512f` creates `settings`, seeded with twelve keys, among them `accepting_orders` (default `false`), the offer windows, cooldown and floor, `checkout_hold_period`, `daily_download_cap`, `free_shipping_threshold` (obsolete since ADR-024; removed by VS-028), pickup address and hours, and `whatsapp_number`. See [`settings-registry.md`](settings-registry.md).
- **Endpoints / jobs:** `GET /api/v1/admin/settings`, `GET/PATCH /api/v1/admin/settings/{key}`, `GET /api/v1/settings/public`.
- **Logic:**
  - A code-side registry defines each key's type, range and visibility.
  - A `PATCH` takes a row lock and writes a `setting.updated` audit row, even for a no-op.
  - Other contexts read through `SettingsReader`, which validates on read and has no fallback.
- **Tests:** `tests/integration/platform/test_admin_settings.py`, `test_public_settings*.py`, `test_settings_seed.py`; `tests/concurrency/test_setting_update_race.py`.
- **Done when:**
  - A bad type or range returns 422 `SETTING_INVALID`.
  - A non-allowlisted key can never appear in the public endpoint.

## VS-008 — In-app notification centre
**Status:** Done
**Depends on:** VS-003
**Goal:** Customers read and mark their notifications, and later slices can emit events without new plumbing.
- **Model / migration:** `ac29d4c2170c` creates `notifications` with the `notification_type` enum (`account`, `order`, `payment`, `refund`, `offer`, `download`) and a partial unread index.
- **Endpoints / jobs:** `GET /api/v1/me/notifications`, `PATCH /api/v1/me/notifications/{id}`.
- **Logic:**
  - `create_notification(session, …)` is the only write port. It never commits, so a notification rides in the caller's transaction.
  - Payloads require an `event` key and are capped at 16 KiB.
  - The `current_verified_user` dependency guards writes.
  - See [`notification-contract.md`](notification-contract.md).
- **Tests:** `tests/integration/engagement/*`; `tests/concurrency/test_notification_read_race.py`.
- **Done when:**
  - Another user's notification returns 404.
  - An unverified user can list notifications but not `PATCH` them.

## VS-009 — Admin user management
**Status:** Done
**Depends on:** VS-005
**Goal:** The administrator finds, inspects, activates and deactivates accounts without database access.
- **Model / migration:** None.
- **Endpoints / jobs:** `GET /api/v1/admin/users`, `GET/PATCH /api/v1/admin/users/{user_id}`.
- **Logic:**
  - Cursor-paginated search and filters.
  - Deactivation takes a row lock, revokes every session and advances `auth_epoch`.
  - Audit rows carry no PII.
- **Tests:** `tests/integration/identity/test_admin_users*.py` (includes two strict `xfail`s that VS-011 fixes); `tests/concurrency/test_admin_user_activation_race.py`.
- **Done when:** A deactivated user's existing tokens stop working immediately.

## VS-010 — Categories, materials, colours
**Status:** Done
**Depends on:** VS-005
**Goal:** Products can be tagged with admin-managed facet values that the storefront lists.
- **Model / migration:** `a9c0aec909a9` creates `categories` (with a live-slug partial unique index), `materials` and `colours`, each with an `is_active` flag and `deleted_at`.
- **Endpoints / jobs:** `GET /api/v1/categories`, `/materials` and `/colours` (hard limit 100 rows; 600 requests per hour per IP), plus admin CRUD under `/api/v1/admin/{categories,materials,colours}`.
- **Logic:**
  - Rows are live, disabled or archived. Archiving releases the slug.
  - A slug conflict is caught from the index, never pre-checked.
  - Mutations take row locks.
  - Introduces the `AuditWriter` port in Platform.
  - See [`reference-data.md`](reference-data.md).
- **Tests:** `tests/integration/catalog/*`, `tests/unit/catalog/*`; `tests/concurrency/test_category_slug_race.py`, `test_reference_data_mutation_race.py`.
- **Done when:**
  - Only live values are public.
  - Concurrent identical slugs yield exactly one category: the race test proves it below HTTP (one success, one `SlugConflictError`), and the `SlugConflictError` → `409 SLUG_CONFLICT` mapping is tested separately.
  - The "category in use" guard is **not** built yet; VS-013 adds it.

---

## VS-011 — Harden the admin boundary and request handling
**Status:** Done
**Depends on:** VS-005, VS-009
**Goal:** Close the security gaps the existing slices left open, before more admin routes are built on top of them.
- **Model / migration:** None.
- **Endpoints / jobs:** No new endpoints; this changes behaviour of existing ones.
- **The admin rule** (SEC-10), for **every** `/api/v1/admin/*` path - real or imaginary, any method (including `HEAD`/`OPTIONS`), with or without a trailing slash:
  - an anonymous caller gets `401 AUTH_REQUIRED`;
  - an authenticated non-administrator gets `404 NOT_FOUND`, byte-identical to an imaginary path;
  - only an MFA-complete administrator ever reaches routing, and so ever sees a `405` or a redirect.
  - One deliberate exception, already in place: a control character anywhere in the path or query is `422 VALIDATION_ERROR` for every caller, before authentication (BUG-03, `RequestTargetMiddleware`). It answers identically for real and imaginary paths, so it reveals nothing; keep it ahead of the admin boundary. `HEAD` is answered as `GET` everywhere (BUG-20), so under `/api/v1/admin` it follows the rule exactly as `GET` does.
- **Logic:**
  - Reuses the `/api/v1/admin` router from VS-005 and the rate limiter from VS-002.
  - BUG-08: anonymous callers get 401 on imaginary admin paths too (today they get 404 there and 401 on real ones, which maps the admin surface).
  - BUG-10: a wrong method under `/api/v1/admin` answers per the admin rule instead of `405` + `Allow`.
  - BUG-29: a trailing slash under `/api/v1/admin` answers per the admin rule instead of `307` (FastAPI `redirect_slashes`).
  - BUG-38: `PATCH /admin/users/{id}` refuses to deactivate the last active administrator (`409 INVALID_STATE_TRANSITION`), because recovery would otherwise need database access.
  - The admin router gets its own rate limit (SRS §22.4).
  - *Already done in the VS-001–009 hardening branch:* NUL and control characters in query, path or body return 422, not 500 (BUG-03); every 429 from `core/rate_limit.py` carries `Retry-After` (BUG-11).
- **Tests** (all already written as strict `xfail`s - VS-011 flips them by removing the markers):
  - `tests/integration/identity/test_deep_vs005_admin_mfa.py`: `test_anonymous_callers_cannot_tell_real_admin_paths_from_imaginary_ones` (BUG-08), `test_a_customer_cannot_enumerate_admin_routes_with_wrong_methods` (BUG-10), `test_a_trailing_slash_does_not_reveal_admin_routes[customer,anonymous]` (BUG-29).
  - `tests/integration/identity/test_admin_users_adversarial.py::test_a_wrong_method_does_not_reveal_that_the_route_exists` (BUG-10).
  - `tests/integration/identity/test_deep_vs009_admin_users.py::test_the_last_active_administrator_cannot_be_deactivated` (BUG-38).
  - The anonymous-401 matrix test (`test_anonymous_callers_get_401_on_every_admin_operation`) must stay green.
- **Done when:**
  - Neither an anonymous caller nor a customer can tell a real admin path from a fake one by any method, slash or status.
  - Deactivating the only active admin returns 409.
  - The five xfails above pass with their markers removed.

## VS-012 — Partitioned audit log and audit-log viewer
**Status:** Done (012a partitioned audit_logs and ensure_partitions; 012b viewer and BUG-39; 012c BUG-41).
**Depends on:** VS-002, VS-005
**Goal:** The administrator can search who did what, and `audit_logs` becomes the monthly-partitioned table the design requires while it is still small.
- **Model / migration:** Convert `audit_logs` into a range-partitioned parent on `created_at` with PK `(id, created_at)`, copy the existing rows, and create partitions for the current month plus 3 months ahead (ADR-015).
- **Endpoints / jobs:**
  - `GET /api/v1/admin/audit-logs` (filters: actor, action, entity type/ID, request ID, date range) and `GET /api/v1/admin/audit-logs/{id}`.
  - New `ensure_partitions` job (monthly, and at worker start) that keeps 3 months of partitions ahead.
- **Logic:**
  - Reuses the `AuditWriter` from VS-010 and the admin boundary from VS-005.
  - The viewer is read-only; no create, update or delete routes exist.
  - `ensure_partitions` takes a list of partitioned tables, so VS-019 can add `downloads` to it.
  - BUG-39: admin reads of account PII are audited - `GET /admin/users` (list and `?search=`) and `GET /admin/users/{id}` each write an audit row naming the admin, with no PII in the row - and email searches are kept out of the server access log (the access log must not record query strings for `/api/v1/admin/users`, or the search moves out of the URL), as api-endpoints.md 530 requires ("PII access audited/redacted from logs").
  - BUG-41: Identity writes audit and outbox rows only through Platform ports (`AuditWriter`, plus a new outbox port) and never imports `app.platform.infrastructure`; Platform and Catalog read token claims through an Identity port instead of `app.identity.infrastructure.session_tokens`.
- **As built (012b):**
  - The date range is half-open, `[created_after, created_before)`, and both bounds must carry a UTC offset; `AuditLogRead` omits `ip_hash`; reading the audit log is not itself audited.
  - BUG-39 audit rows: `user.list_viewed` (filters used, `search` as a boolean, result count) and `user.viewed` (the account's id). Neither stores an address or search term; a 404 writes no row. `AdminQueryStringFilter` on `uvicorn.access` drops the query string for every `/api/v1/admin` path, not only `/admin/users`.
  - **Follow-up, cross-endpoint (not VS-012):** api-endpoints.md 31 says unknown filter or sort fields return `400 VALIDATION_ERROR`, but every list endpoint ignores unknown query parameters, and the project's `VALIDATION_ERROR` is a 422. The viewer follows the existing convention. Resolve the spec and all list endpoints together, in one change.
- **As built (012c):**
  - Each context publishes `app.<context>.public` (concrete adapters and dependencies for other contexts) and `app.<context>.application.ports` (`Protocol`s); another context may import only those. `test_cross_context_imports_go_only_through_public_or_ports` enforces it, beside the two BUG-41 tests, and all three are in the smoke suite.
  - Platform: `AuditWriter` and `OutboxWriter` ports, `SqlAuditWriter`/`SqlOutboxWriter` in infrastructure. Identity writes audit and outbox rows only through them, and reads token claims through `app.identity.application.token_claims`.
  - Identity's `password_hasher`, `token_service`, `session_tokens`, `totp` and `secret_cipher` moved to `app.identity.application.security`: they do no I/O, so they are security services rather than adapters.
- **Tests:**
  - Migration up and down with existing rows preserved.
  - An insert lands in the correct partition.
  - `ensure_partitions` is idempotent.
  - Filters, cursors and a query across a month boundary.
  - The viewer is admin-only.
  - Flip the strict `xfail`s: `test_deep_vs009_admin_users.py::test_admin_reads_of_account_pii_are_audited` and `::test_an_admin_email_search_never_reaches_the_server_log` (BUG-39); `tests/unit/test_deep_architecture.py::test_no_context_imports_another_contexts_infrastructure` and `::test_the_application_layer_depends_on_the_domain_only` (BUG-41).
- **Done when:**
  - `audit_logs` is partitioned, with no rows lost.
  - Running the job twice changes nothing.
  - The admin can filter the log by entity.
  - Admin PII reads are audited and no admin email search appears in any log.
  - The architecture tests pass.

## VS-013 — Admin product management
**Status:** Done
**Depends on:** VS-010
**Goal:** The administrator creates and maintains valid physical and STL products through the API.
- **Model / migration:** `products` per `database-design.md` §6.4:
  - type-integrity CHECKs (physical-only fields required on physical, forbidden on STL);
  - live-slug partial unique index;
  - generated `search_vector`;
  - aggregate columns defaulting to 0 (`average_rating`, `review_count`, `wishlist_count`; no `download_count`, removed by ADR-019);
  - `ON DELETE RESTRICT` foreign keys to categories, materials and colours;
  - `version INTEGER NOT NULL DEFAULT 1`, an addition to the frozen §6.4 design, required for FR-04.
- **Endpoints / jobs:** `GET/POST /api/v1/admin/products`, `GET/PATCH/DELETE /api/v1/admin/products/{id}`.
- **Logic:**
  - Reuses the admin boundary (VS-005), `AuditWriter` and the slug pattern (VS-010).
  - `type` is immutable, and aggregates cannot be written by clients.
  - Soft delete releases the slug.
  - Optimistic concurrency (FR-04):
    - `PATCH` and `DELETE` must carry the `version` the admin last read;
    - the write is `UPDATE … WHERE id = :id AND version = :version` and increments `version`;
    - if 0 rows change, the request gets 409 `VERSION_CONFLICT`, a new stable code, with the current version in the body, and nothing is written;
    - reads return `version`.
  - Adds the deferred guard: archiving a category, material or colour that a live product uses returns 409 `CATEGORY_IN_USE`.
- **Tests:**
  - Invalid physical/STL field mixes are rejected by the API and by the DB CHECK.
  - Slug race; slug reuse after delete.
  - Archive racing a product assignment.
  - Two admins `PATCH` with the same version: one 200, one 409, and no silent overwrite.
  - A stale version on `DELETE` gives 409.
  - Audit rows are written for successful writes only.
- **Done when:**
  - An STL product with a lead time cannot be stored, even via SQL.
  - A used category cannot be archived.
  - A stale edit never overwrites a newer one; it gets 409 `VERSION_CONFLICT`.
  - Every change is audited.
- **As built:**
  - Migration `fc18b48a1780`; contract in [`products.md`](products.md); versioning rules in ADR-020.
  - Owner decisions: availability is common to both types (SRS §6.1 updated); `DELETE` takes `?version=N`; `dimensions` is `{length_mm, width_mm, height_mm}`; material and colour stay optional on physical products (open conflict with the entities doc, recorded in `products.md`); lead time ≥ 0; disabled (not archived) values may be assigned.
  - The archive guard is a lock protocol (`FOR SHARE` on assignment, `FOR UPDATE` on archive), proven in both orders by `tests/concurrency/test_reference_archive_vs_assignment_race.py`; see [`reference-data.md`](reference-data.md).
  - `ApiError` carries RFC 9457 extension members (`current_version`) and field `errors`.
  - Tests seeding reference values retire them afterwards (`tests/catalog_seed.py`), so they cannot crowd shared lists (audit A-06).

## VS-014 — Product images with storage and malware scanning
**Status:** Done
**Depends on:** VS-013
**Goal:** The administrator uploads, orders and picks a cover image for products, and the shared storage and scanning components are proven on a low-risk path.
- **Model / migration:** `product_images`, with a partial unique index allowing one active cover per product.
- **Endpoints / jobs:**
  - `POST /api/v1/admin/products/{id}/images`.
  - `PATCH …/images/{image_id}`, `PUT …/images/{image_id}/cover`, `PUT …/images/order`, `DELETE …/images/{image_id}`.
  - New `reap_orphan_files` job (daily).
- **Logic:**
  - New `StoragePort` with a local adapter (generated UUID keys) and new `MalwareScannerPort` with a ClamAV adapter and a fake for tests.
  - Upload pipeline: size check → magic-byte type check → decode → re-encode (strips metadata) → scan → store → commit the row.
  - If the scanner is unavailable, the upload is rejected (fail closed).
  - The reaper deletes files that no row references, after a grace period.
- **Tests:**
  - A fake extension is rejected; the EICAR test file gives 422 `MALWARE_DETECTED`.
  - Re-encoding strips EXIF.
  - A cover race leaves exactly one cover.
  - A DB failure after the file write leaves an orphan that the reaper removes.
- **Done when:**
  - Only re-encoded, scanned images are stored.
  - A product never has two covers.
  - Orphan files are cleaned up.
- **As built:**
  - Migration `cc87333ebe79`; contract in [`product-images.md`](product-images.md); pipeline in ADR-021.
  - **Pipeline order changed from the plan above:** the raw upload is scanned right after the size check, before type sniffing and re-encoding. In the planned order EICAR could never reach the scanner, and re-encoding would destroy any payload first (ADR-021).
  - Owner decisions: limits are code constants (10 MB, 20 images, 40 MP, alt text 300); the format family is kept; the first image is the cover; deleting the cover while others remain is 409; files of soft-deleted images are kept (BR-033); `503 SERVICE_UNAVAILABLE` when the scanner is down; 24 h reaper grace period.
  - Ports and adapters in `app.integrations`: `StoragePort`/`LocalStorage`, `MalwareScannerPort`/`ClamAvScanner` (clamd `INSTREAM`, no new dependency)/`FakeScanner`, `ImageSanitizerPort`/`PillowImageSanitizer`. New dependency: Pillow.

## VS-015 — Public catalogue: browse, filter, sort, detail
**Status:** Done
**Depends on:** VS-013, VS-014
**Goal:** A visitor browses physical and STL products with facets and sorting, and opens any visible product page.
- **Model / migration:** Partial catalogue indexes from SRS §21.3 (type/category/price, type/material/colour/price, rating, newest), all `WHERE deleted_at IS NULL AND is_visible`. *Already created by VS-013 (`fc18b48a1780`, `ix_products_browse_*`), so no migration is expected.*
- **Endpoints / jobs:** `GET /api/v1/products` (cursor pagination; filters: type, category, material, colour, price range, minimum rating, featured; sorts: price, `-average_rating`, `-created_at`) and `GET /api/v1/products/{slug}`.
- **Logic:**
  - Reuses the reference lists (VS-010) and the public rate limiter (VS-002).
  - Visible means not deleted, visible, and in a live category.
  - Unavailable products are still listed.
  - The detail view returns the gallery, SEO fields, `purchase_mode` and `is_available`, so the frontend can show WhatsApp or add-to-cart.
- **Tests:**
  - Hidden, deleted and disabled-category products are excluded.
  - Facets combine with AND.
  - The cursor stays stable under inserts.
  - `EXPLAIN` on 10,000 seeded products uses the indexes.
- **Done when:**
  - Browse is under 500 ms p95 with 10,000 products (NFR-01).
  - Unavailable products show but are marked unavailable.
- **As built:**
  - No migration; contract in [`storefront-catalogue.md`](storefront-catalogue.md); capability flags in ADR-022.
  - Owner decisions: `ProductDetail.capabilities` (`can_add_to_cart`, `can_offer`, `whatsapp_available`) derived from product state only; no STL delivery-promise field until SRS §30.2 closes; bad query values are `422 VALIDATION_ERROR` (api-endpoints.md §7.1 corrected from 400); `q` is left to VS-016; a product whose price or rating changes mid-browse may cross the cursor (documented limit); disabled materials/colours still show on their products.
  - The product cursor is shared with the admin list (`app/catalog/api/product_cursor.py`). Visibility is one predicate used by both list and detail.

## VS-016 — Search and autocomplete
**Status:** Done
**Depends on:** VS-015
**Goal:** A visitor finds products by name or description, even with a typo.
- **Model / migration:** GIN index on `search_vector` and a GIN trigram index on `name`.
- **Endpoints / jobs:** `q` parameter on `GET /api/v1/products`; `GET /api/v1/search/suggestions` (at most 10 results).
- **Logic:**
  - Reuses the catalogue query from VS-015.
  - English full-text search, name weighted above description (English only per ADR-016, although SRS §28 still lists "i18n").
  - Falls back to trigram similarity when full-text returns fewer than 5 hits.
  - All queries are parameterised.
- **Tests:**
  - Exact, stemmed and one-typo queries.
  - SQL-injection strings are harmless.
  - Search combined with facets.
  - Latency on 10,000 products.
- **Done when:**
  - A one-typo query finds the product.
  - Search p95 is under 800 ms (NFR-02).
- **As built:**
  - No migration: the GIN indexes came with VS-013. Contract in [`storefront-catalogue.md`](storefront-catalogue.md). Ordering, fallback and cursor decisions are in ADR-023.
  - With `q`, the default sort is `-relevance` (full-text hits by `ts_rank`, then trigram-only hits by `word_similarity`). The fallback counts full-text hits with facets applied and is pinned in the cursor. The trigram threshold is 0.5, set per transaction.
  - `q` is trimmed (blank means no search), up to 200 characters like the admin list; suggestions need 3 to 200 with a word of 3+ letters or digits, `limit` 1 to 10. Suggestion and `q` errors are 422 (api-endpoints.md §7.1 corrected from 400, and from "translated" text per ADR-016).
  - Known limit: a transposed pair of letters (`dargon`) is not found; trigrams count it as two edits.
  - Audit fixes ([`VS-016-audit.md`](audits/VS-016-audit.md)): the trigram fallback needs a word of 3+ letters or digits and no excluded word (a one-letter search had failed NFR-02 in CI), and suggestions need the same word (ADR-023 amended).
  - Audit Q-2 and Q-4: suggestions allow 3,000 requests/hour/IP (carrier-grade NAT; the frontend debounces about 300 ms), and typo tolerance stays on names only for V1 (ADR-023 decision 7 and consequences).

## VS-017 — STL bundle upload and version publishing
**Status:** Removed by ADR-019 (STL files are emailed manually; the platform stores none).
**Was:** uploading and versioning STL bundles. Nothing replaces it: no STL file reaches the platform.

## VS-018 — Entitlements: admin grant and STL library
**Status:** Removed by ADR-019 (STL files are emailed manually; the platform stores none).
**Was:** entitlements, admin grants and the customer library. Ownership is now a paid, unrefunded STL line (VS-023); delivery is tracked by VS-023b.

## VS-019 — Protected STL download through nginx
**Status:** Removed by ADR-019 (STL files are emailed manually; the platform stores none).
**Was:** downloads through nginx `X-Accel-Redirect`. Its nginx service and client-IP fix move to VS-020. The only protected files left, Bring Your Idea attachments, are streamed by the API (VS-035, ADR-031); VS-020 may move them to an nginx `internal` location.

## VS-020 — Staging environment and deploy pipeline
**Status:** Not started (final phase: needs a server)
**Depends on:** VS-015
**Goal:** Any `main` build can be deployed to a production-shaped staging host with a health gate, and rolled back in one command.
- **Model / migration:** None. `alembic upgrade head` becomes a deploy step.
- **Endpoints / jobs:**
  - CI builds and pushes an image tagged with the commit SHA.
  - A deploy job gates on `/health/ready` and rolls back automatically on failure.
- **Logic:**
  - Adds the nginx service in front of `api` (moved from the removed VS-019).
  - May switch the VS-035 attachment download (`GET /api/v1/admin/custom-requests/{id}/attachments/{attachment_id}/download`) to `X-Accel-Redirect` on an nginx `internal` location over `uploads_private`. The API keeps the admin check, the expiry check, the audit row and the response headers; nginx only sends the bytes (ADR-031).
  - Fixes client IPs behind the proxy: uvicorn runs with `--proxy-headers` and `--forwarded-allow-ips` limited to nginx. Otherwise the rate limiter, login throttle and IP hashes would all see nginx's IP.
  - Production Compose: nginx with TLS and automatic renewal, HSTS/CSP/security headers, body-size limits, and an allowlisted webhook location.
    - Body-size limits: `POST /api/v1/custom-requests` needs about 51 MB (5 × 10 MB images plus framing, ADR-030); admin image uploads about 10 MB; everything else can stay small.
  - Containers run as non-root with CPU and memory limits.
  - Secrets live outside the repository.
  - **Required: shared-IP rate limiting** (found in the VS-016 audit, PR #6). The SRS rules out a plain client-side storefront, so catalogue pages are server-rendered. Without this, every visitor's API calls arrive from the frontend server's IP and share one 600/hour bucket. Carrier-grade NAT also puts many Lebanese mobile customers behind one IP. Record the design in an ADR.
    - **Forwarded visitor IP.** The frontend server sends the visitor's IP in a dedicated header, together with a shared secret. The API trusts that header only when the secret matches (constant-time comparison) and the request comes from the frontend; otherwise it uses the connection IP. nginx strips both headers from outside traffic. The secret lives outside the repository and can be rotated.
    - **Caching.** The public reference lists (`GET /categories`, `/materials`, `/colours`, `/settings/public`) send `Cache-Control` headers, so browsers and the frontend stop refetching them on every page load. The `max-age` stays short for `/settings/public` because it carries the accepting-orders state.
    - **Recheck auth limits.** Recheck the login and registration limits (20 and 5 per hour per IP today) under the same rule. They must key on the real visitor IP, and the numbers must be reviewed for carrier-grade NAT.
  - **After every deploy to the live site, run `scripts/smoke/vs012_post_deploy.sh <site URL>`** with `READONLY_DATABASE_URL` (a read-only database role), `API_LOG_CMD`, `WORKER_LOG_CMD`, and `EXPECTED_MIN_AUDIT_ROWS` set to the `audit_logs` count taken just before the deploy. It is read-only and exits non-zero on any failure. Wire it in as a deploy step, beside the `/health/ready` gate.
- **Tests:**
  - A broken build is rolled back automatically.
  - A header check against staging.
  - `id -u` is non-zero in every container.
  - Two client IPs get separate rate-limit buckets through nginx.
  - Through the frontend server, two visitors' forwarded IPs get separate buckets. A forwarded-IP header with a wrong or missing secret, or sent from outside the frontend, is ignored.
  - The four public reference lists send `Cache-Control`.
  - Login and registration limits key on the forwarded visitor IP.
- **Done when:**
  - A push to `main` reaches staging without manual steps.
  - Rollback is one command.
  - HTTPS and security headers are present.
  - Rate limits apply per real client IP, including for requests the frontend server makes on a visitor's behalf.
  - The public reference lists are cacheable, and the login and registration limits have been rechecked and recorded.

## VS-021 — Production email delivery
**Status:** Not started (final phase: needs a server)
**Depends on:** VS-020
**Goal:** Verification and reset emails, and every later email, actually reach inboxes.
- **Model / migration:** None.
- **Endpoints / jobs:** None new.
- **Logic:**
  - Reuses the email port and outbox from VS-002.
  - Adds a real provider adapter (HTTP API), with SPF, DKIM and DMARC set up on the domain.
  - A message reaching `failed` emits an alert event.
- **Tests:**
  - Adapter contract test against the provider's test mode.
  - A provider error keeps the message retrying, and never touches the business transaction.
- **Done when:**
  - A registration email on staging arrives with SPF, DKIM and DMARC passing.
  - Provider keys never appear in logs.

## VS-022 — Mixed cart
**Status:** Done
**Depends on:** VS-013
**Goal:** A verified customer keeps one persistent cart mixing physical and STL products.
- **Model / migration:** `carts` (one per user) and `cart_items` (unique `(cart_id, product_id)`, a CHECK that STL quantity = 1, a price snapshot).
- **Endpoints / jobs:** `GET /api/v1/cart`, `POST /api/v1/cart/items`, `PATCH/DELETE /api/v1/cart/items/{product_id}`.
- **Logic:**
  - Reuses `current_verified_user` (VS-008).
  - Products are read through a Catalog read port.
  - Adding an item upserts and merges quantities under a cart lock, then re-checks the cap.
  - Refused: WhatsApp-only, hidden, deleted or unavailable products. The "STL already owned" refusal is added by VS-023, which creates `order_items`; before it no STL can be owned.
  - `CartRead` shows the snapshot price, the current price and a `price_changed` flag.
- **Tests:**
  - Two concurrent adds of one product produce one line within the cap.
  - A WhatsApp-only product gives 422.
  - An unverified user can read but not write.
- **Done when:**
  - The cart can never hold duplicate lines, an STL quantity above 1, or a quantity over the cap.
- **As built:**
  - Migration `bde6135b2538` (`carts`, `cart_items`, `uq_products_id_type`); decisions in [ADR-029](adr/ADR-029-cart-decisions.md); contract in [`cart.md`](cart.md); plan in [`plans/VS-022-mixed-cart-plan.md`](plans/VS-022-mixed-cart-plan.md).
  - STL quantity = 1 is enforced by a CHECK on a type snapshot that a composite FK `(product_id, product_type) → products (id, type)` proves; lines are hard-deleted.
  - Every write takes the cart lock first (`INSERT … ON CONFLICT DO NOTHING`, then `SELECT … FOR UPDATE`); two concurrent first adds both succeed (`tests/concurrency/test_cart_races.py`, 20 runs plus a rollback variant).
  - `CartRead` lines carry `over_cap` and `purchasable` / `unpurchasable_reason`; checkout (VS-023) must refuse such lines with 422 naming each one, never drop them (ADR-029 decision 6, owner question 14).
  - Storefront visibility is one shared `listed_predicate()`, used by the storefront and the cart's `CartProductReader`.

## VS-023 — Checkout and verified payment for digital orders
**Status:** In progress
**Depends on:** VS-022, VS-008, VS-007
**Goal:** A customer buys an STL end to end on the mock provider, and the line enters the STL delivery queue (`awaiting_delivery`) only after independent server-side verification.
- **Model / migration:**
  - `orders`, `order_items`, `order_status_history`, `payments`, `webhook_events`, `idempotency_records`, created with their full frozen columns, including the physical/delivery columns VS-028 and VS-029 will use: `orders.payment_method` (new `payment_method` enum `online`/`cash`), `orders.contact_phone_snapshot` (E.164) and `orders.contact_phone_hash`, `orders.cash_terms_accepted_at`, `order_items.payment_method`, `order_items.cancel_reason` (new enum `refused`/`no_show`/`other`), `order_items.receipt_confirmed_at` and `problem_reported_at`, `payments.order_payment_method`, `payments.recorded_by`, `payments.late_captured_at`. No shipping, zone or shipping-refund columns (ADR-024).
  - Cash integrity in the database (INV-21, INV-22): `UNIQUE (orders.id, payment_method)`; composite foreign keys `order_items (order_id, payment_method)` and `payments (order_id, order_payment_method)` to it; CHECKs that a cash line is physical and that `provider = 'cash'` exactly when `order_payment_method = 'cash'`; a partial unique index `payments(order_id) WHERE provider = 'cash'`; a cash payment's status is `paid`, `partially_refunded` or `refunded`, above zero and has `recorded_by`.
  - Constraints: one live payment per order (`UNIQUE(order_id) WHERE status NOT IN ('failed', 'expired')`, so a paid or refunded order never gets a second); unique `(provider, event_id)`; `UNIQUE NULLS NOT DISTINCT (scope, user_id, key)`.
  - `payment_provider` is created with `mock` and `cash`; real provider values are added by VS-032 once §30.4 is decided. The provider of each attempt is stored on its payment row.
  - STL ownership (ADR-019, database-design §8.4): `order_items.user_id` and the partial unique index `(user_id, product_id) WHERE product_type = 'stl' AND fulfillment_status IN ('pending', 'awaiting_delivery', 'delivered')`; `orders.customer_email_snapshot`.
- **Endpoints / jobs:**
  - `POST /api/v1/checkout` (requires an `Idempotency-Key` header; optional `payment_provider`, required when more than one online provider is configured) and `POST /api/v1/webhooks/payments/{provider}` (provider-neutral, ADR-024).
  - A verification arq job.
  - New `purge_expired_idempotency_records` job (daily).
  - `GET /api/v1/me/stl-ownership?product_id=` (ADR-025): `200 {product_id, owned}` for any signed-in user.
- **Logic:**
  - Reuses `SettingsReader` (VS-007), `create_notification` (VS-008) and the outbox (VS-002).
  - Adds the "STL already owned" check: the cart (VS-022) refuses an owned STL with 409 `PRODUCT_ALREADY_OWNED`; checkout silently drops an STL acquired since it was added (SRS §7.3 step 5); and an ownership-index violation during checkout (the STL is in another live order) gives 409 `PRODUCT_ALREADY_OWNED`.
  - The ownership check (ADR-025) reads through the same ownership query: `owned` is true for a paid, unrefunded STL line (`awaiting_delivery` or `delivered`, not fully refunded). An unknown, hidden or physical product answers `owned: false`, so it reveals no product. It is a hint; the cart and checkout refusals above stay.
  - New payment-provider port with a mock adapter covering every verification branch.
  - Checkout runs in one transaction:
    1. Idempotency check.
    2. `accepting_orders` (503 `ORDERS_PAUSED` when off).
    3. Lock the cart and revalidate every line.
    4. Price-change check (409 `CART_PRICE_CHANGED` unless accepted).
    5. Recompute totals.
    6. Create the order, lines with snapshots and a pending payment.
    7. Record terms and digital-final-sale consent.
    8. Clear the cart.
  - The provider is called **after** the transaction commits.
  - The webhook routes only configured online providers (404 otherwise; `cash` never; `mock` never in production), stores the event and returns 200.
  - The verification job queries the provider outside any lock, through the adapter named on the payment row (`payments.provider`), never the URL. An event whose provider differs from its payment's provider is stored, ignored and alerted. It applies the result only if the amount matches exactly, under the ADR-024 lock order (`orders`, then lines by `id`, then `payments`): mark paid, move STL lines to `awaiting_delivery`, write history, audit, emails and notifications. The confirmation email says the file will be emailed by the administrator.
  - `derive_order_status()` is the only writer of `order.status`. It implements the full SRS §20.2 projection, including the cash-order branch (no payment: all lines cancelled → `cancelled`, otherwise `in_progress`), so later slices never change it. It is a pure function, and this slice unit-tests every branch, including cash, "refunds cover all paid money → refunded" and the all-cancelled case.
  - Every order in this slice is `payment_method = online`; cash is added by VS-028.
  - A failed or expired attempt leaves the order `pending_payment`, so it can be retried (BR-058, VS-024). The order becomes `cancelled` only once its checkout hold is released (`orders.cancelled_at` set by `release_stale_checkouts`), as SRS §20.2 states; `derive_order_status` takes `cancelled_at` as an input.
  - Carts with physical lines return 422 `INVALID_FULFILLMENT` until VS-028.
  - Settings validation refuses to start the API and the worker when `ENVIRONMENT=production` and `mock` is the configured payment provider. (The single `payment_provider` setting becomes a list of configured online providers in VS-032; until then "configured providers" means that one value.)
- **Tests:**
  - Parallel double checkout.
  - Same key with a different body gives 409.
  - The kill switch blocks new checkouts but not in-flight payments.
  - A forged callback changes nothing; an underpayment is never marked paid.
  - A duplicate webhook applies the payment once.
  - Two parallel checkouts of one STL by one customer: one order, one 409 `PRODUCT_ALREADY_OWNED`.
  - An owned STL cannot be added to the cart (409).
  - Ownership check: `owned` is false before payment and for another customer's purchase, true once the line is `awaiting_delivery` or `delivered`, and false for an unknown, hidden or physical product id; anonymous gives 401; a missing or malformed `product_id` gives 422.
  - A failure leaves the cart intact.
  - A provider-reported failure leaves the order `pending_payment`.
  - Startup fails with `ENVIRONMENT=production` and `mock` configured.
  - A webhook to `/payments/cash`, to an unconfigured provider, or to `/payments/mock` in production gives 404 and stores nothing. The production case runs with `ENVIRONMENT=production` and a test-only stub online provider configured, so startup validation passes.
  - A webhook event whose provider differs from its payment's provider changes nothing.
  - The database refuses an STL line on a cash order, a cash payment on an online order, an online payment on a cash order, and a second cash payment on one order.
  - Every branch of `derive_order_status` (unit).
  - Full end-to-end: register → buy → line `awaiting_delivery`.
- **Done when:**
  - `paid` is reachable only through verification.
  - One checkout per idempotency key.
  - A paid STL line is `awaiting_delivery`, ready for VS-023b's queue.
- **As built:**
  - Migration `03a4730dd046`; contract in [`checkout.md`](checkout.md); decisions in [ADR-032](adr/ADR-032-checkout-idempotency-and-payment-verification.md); plan [`plans/VS-023-digital-checkout-plan.md`](plans/VS-023-digital-checkout-plan.md).
  - Consent is validated before writing and recorded on the order insert; the cart is cleared last, in the same transaction. Checkout is **two** transactions around the provider call, not one: only the `201` and the post-commit `502 PAYMENT_PROVIDER_UNAVAILABLE` are stored for replay.
  - The cash CHECKs are the full list: cash line physical, `provider = 'cash'` iff a cash order, one cash payment per order, a cash payment `paid`/`partially_refunded`/`refunded` with `recorded_by` and `verified_at` and above zero, `late_captured_at` never on cash or a paid row, `recorded_by` never on an online payment.
  - `webhook_events` carries `provider_payment_id` and `payment_id`, resolved at receipt (the provider's reference first, then our `payments.id`); an event that cannot be applied is stored already processed with `processing_error`.
  - Verification runs in a background task after the webhook's 200, with the `verify_payments` job (every minute) as fallback; SRS §23 lists both new jobs.
  - Paid only on an exact amount in USD on a live attempt of an uncancelled order; anything else is a late capture, recorded once. Until VS-030 the only supported view of late captures is the SQL listing in [`checkout.md`](checkout.md).
  - `PAYMENT_PROVIDER=none` gives `503 ONLINE_PAYMENT_UNAVAILABLE`; boot refuses the mock outside development, test and staging (and staging with the default secret) in the API and the worker.
  - `scripts/mock_pay.py` is the only way to pay a mock payment outside the tests.

## VS-023b — STL delivery queue and mark-as-sent
**Status:** Not started
**Depends on:** VS-023
**Goal:** The administrator sees every paid STL still owed to a customer, emails it from their own drive, marks it sent, and the customer is told (ADR-019).
- **Model / migration:**
  - `order_items.delivered_by` and the delivery CHECKs, unless VS-023 already created them with the frozen columns.
  - The queue index `order_items(created_at) WHERE product_type = 'stl' AND fulfillment_status = 'awaiting_delivery'`.
  - Deletes the obsolete seeded `daily_download_cap` setting (VS-007) and its registry entry.
- **Endpoints / jobs:** `GET /api/v1/admin/stl-deliveries`; `POST /api/v1/admin/orders/{order_id}/items/{item_id}/transition` for STL lines only (`awaiting_delivery → delivered`). VS-029 adds the physical edges to the same endpoint.
- **Logic:**
  - Reuses the admin boundary, `AuditWriter`, `create_notification` (category `download`, `payload.event = "stl.delivered"`), the outbox, and `derive_order_status`.
  - Marking delivered locks the order and then the line (ADR-024 lock order), sets `fulfilled_at` and `delivered_by`, recomputes the order status, and writes history, audit, an in-app notification and a "your STL file has been sent" email in one transaction.
  - The queue shows order number, product, customer and `customer_email_snapshot`, oldest first.
  - Removes the empty `src/app/digital_assets` package and its test folders, and the stale VS-019 references (`jobs/partitions.py`, `identity/api/admin_users.py`, `test_deep_architecture.py`'s context list).
- **Tests:**
  - Only `awaiting_delivery` lines appear; a pending (unpaid) line never does.
  - Delivered, refunded or physical lines give 409 `INVALID_STATE_TRANSITION`.
  - Two admins marking the same line: one 200, one 409; one audit row and one email.
  - Customer gets 404 and anonymous 401 on both routes.
  - Order becomes `completed` when its only line is delivered.
  - End-to-end: register → buy → line in queue → admin marks sent → customer notified.
- **Done when:**
  - No paid STL can be forgotten: each one sits in the queue until marked delivered or refunded.
  - Every delivery records who and when, and the customer is notified.

## VS-024 — Payment recovery: reconciliation, stale checkouts, manual confirm
**Status:** Not started
**Depends on:** VS-023
**Goal:**
- A customer whose payment attempt failed or expired retries on the same order.
- A lost callback can no longer leave a customer charged with nothing delivered.
- **Notes from VS-023:** `webhook_events.processed_at` is set once verification applied the provider's answer, or at receipt for an ignored event (`processing_error`); a provider that did not answer leaves the event unprocessed with its error. An attempt with no `provider_payment_id` older than the provider timeout is a reconciliation candidate (a crash between checkout's two transactions); reconcile it by our `payments.id` through `verify_payment()`, which stores the reference.
- An unpaid order is cancelled when its checkout hold ends.
- The administrator can confirm a payment by hand when automatic verification is unavailable.
- **Model / migration:** None. The one-live-payment partial unique index from VS-023 enforces a single live attempt.
- **Endpoints / jobs:**
  - `POST /api/v1/me/orders/{id}/payments` (retry; requires an `Idempotency-Key` header; a new route, not yet in `api-endpoints.md`).
  - `GET /api/v1/admin/payments`, `GET /api/v1/admin/payments/{id}`, `POST …/{id}/reconcile`, `POST …/{id}/confirm`.
  - New `reconcile_payments` job (every 15 min) and `release_stale_checkouts` job (every 5 min).
- **Logic:**
  - Reuses the verify-and-apply function from VS-023; the webhook, reconciliation and manual confirm share one apply path.
  - **Retry (BR-058)** creates a new `pending` attempt on the **same** order for the order's snapshot total. It is allowed only when:
    - the caller owns the order;
    - the order is `pending_payment` and `cancelled_at` is null;
    - no attempt is `pending` or `processing` (otherwise 409 `PAYMENT_ALREADY_ACTIVE`, backed by the unique index);
    - no STL line has become owned since checkout (otherwise 409 `PRODUCT_ALREADY_OWNED`; the ownership index makes this rare, because the order's own `pending` line holds the STL).

    The retry locks the `orders` row first and re-checks these conditions under the lock, so it cannot insert a payment on an order the hold release has just cancelled. It may name a configured `payment_provider` (default: the previous attempt's); it is stored on the new payment row. The provider is called after commit. The kill switch does not block a retry, because the order already exists.
  - Retry, reconciliation and stale-checkout release apply to online orders only. A cash order (VS-028) has no payment row until its handover, so none of them can select it; retry on a cash order gives 409 `INVALID_STATE_TRANSITION` (ADR-024).
  - Reconciliation selects candidate attempts without locking, queries the provider outside any lock, then locks the order before the payment to apply the result (ADR-024: never `payments` before `orders`, including batch selection). It covers attempts stuck in `pending` or `processing`. A `failed` or `expired` result marks that attempt so, which frees the order for a retry.
  - `release_stale_checkouts` finds `pending_payment` orders whose `placed_at + checkout_hold_period` has passed. It queries the provider first; a paid result is applied instead. It **skips** (and alerts on) an order whose provider query fails or times out, whose provider has no status API, or that has an unprocessed webhook event: such an attempt stays live for reconciliation or manual confirmation. Only when the provider confirms the attempt unpaid does it, under the ADR-024 lock order (`orders`, then lines by `id`, then `payments`), expire any live attempt, set `orders.cancelled_at`, move the order's lines to `cancelled` (which frees the STL ownership index; an unpaid online order's physical lines can only be `pending`, because BR-148 blocks every transition until payment), and recompute the status to `cancelled`.
  - Manual confirm applies a live online attempt on an uncancelled order when the provider has no status API, and the amount must equal the total. On an attempt that is no longer live, or on a cancelled order, it records a late capture instead of refusing. Cash is recorded by VS-029's handover, never here.
  - **Late capture (SRS §9.2):** if verification or manual confirmation finds money captured for an attempt that is `failed` or `expired`, for a cancelled order, or for an amount that does not match the order total (the attempt is then marked `failed`), it sets `late_captured_at` on that row (which stays not live), raises an alert, and never touches the order's lines; VS-030 adds the automatic `late_capture` refund obligation. A duplicate success for an attempt already `paid` is a no-op, even if the order was cancelled since.
- **Tests:**
  - A failed attempt, then a retry: a second attempt on the same order with the same order number, and it pays through.
  - Two concurrent retries: one 201 and one 409.
  - A retry while an attempt is `pending` gives 409.
  - A retry after the hold is released gives 409 `INVALID_STATE_TRANSITION`.
  - A missed callback is recovered in one run.
  - Reconciliation racing a webhook applies once.
  - A hold expiring while a payment verifies: the payment wins.
  - A manual confirm with the wrong amount gives 422.
  - A retry naming an unconfigured provider gives 422 `PAYMENT_METHOD_NOT_ALLOWED`.
  - `release_stale_checkouts` on a `pending_payment` order with physical lines finds them all `pending` and cancels them; no other line state is reachable before payment (BR-148).
  - A retry on a paid or refunded order gives 409 (the live-payment index counts them).
  - A retry racing `release_stale_checkouts` (`meet_or_fail`): either the retry commits first and the release then finds a live attempt, or the release commits first and the retry gets 409; never a pending payment on a cancelled order.
  - Late success: a provider success for an `expired` attempt on an order cancelled by the release, for a `failed` attempt while a retry attempt is live, and for a second capture after the retry is paid — each records `late_captured_at` and an alert, and leaves the order and lines unchanged. (The automatic refund obligation is tested in VS-030.)
  - Manual confirm on an expired attempt, or on a cancelled order, records a late capture and an alert; it never applies the payment.
  - Provider without a status API: the hold release runs while a payment waits for manual confirmation (unprocessed webhook) — the order is skipped and stays `pending_payment`; the later manual confirm applies it.
  - The hold release's provider query errors or times out — the order is skipped, alerted, and still payable.
  - An underpayment and an overpayment on a live attempt are never applied: the attempt is `failed` and the capture recorded as a late capture.
  - A duplicate success for a `paid` attempt on an order the customer has since self-cancelled changes nothing.
- **Done when:**
  - A customer retries a failed or expired attempt on the same order, and never has two live attempts on it.
  - An order is cancelled only when its checkout hold ends unpaid.
  - No payment stays stuck without an alert.
- **Must resolve before build** (final PR #8 review, both reviewers; recorded per the owner's stop rule, not yet decided):
  1. **No-status-API providers dead-end the hold release.** The release cancels only "when the provider confirms the attempt unpaid", and this section and the entities doc skip any order "whose provider has no status API". Admin cancel of a `pending_payment` order is 409, and manual confirm only applies or records a late capture. So an abandoned checkout stays `pending_payment` forever: the attempt stays live (retry gets `PAYMENT_ALREADY_ACTIVE`), its `pending` STL line holds the ownership index (the customer can never buy that STL again), and an alert repeats every run. The same trap catches a provider that keeps answering "pending", an order whose only attempt is a mismatched-amount late capture, and a provider-mismatch event that was "stored and ignored" if that leaves it unprocessed. This contradicts BR-039 and this slice's "Done when". Suggested fix: because a later success becomes a late capture anyway, release after the hold plus a grace period when the provider cannot answer and no webhook event exists, with an alert; or add an admin "expire attempt / release order" action. Define "unpaid" per provider state, and say that ignored or failed events set `processed_at`.
  2. **Manual confirm with a wrong amount: 422 or late capture?** This section ("A manual confirm with the wrong amount gives 422") and `api-endpoints.md` ("Server requires exact order-total match") refuse it. ADR-024 decision 15, SRS §9.2 and the late-capture rule above say a mismatched amount found by verification **or manual confirmation** is a late capture with an automatic refund. Scenario: a no-status-API provider, and the customer transfers $45 on a $50 order. The admin enters 4500 and gets 422, so no refund obligation exists, the attempt stays live, and with item 1 the order hangs. Suggested fix: separate an admin typo from a provider showing a different captured amount (for example a `captured_amount_cents` that must match the dashboard, plus an explicit "record mismatch as late capture" path), and align the API row and this slice's test.

## VS-025 — Customer order history
**Status:** Not started
**Depends on:** VS-023
**Goal:** A customer sees their orders and each order's immutable details.
- **Model / migration:** None.
- **Endpoints / jobs:** `GET /api/v1/me/orders` (cursor; filters: status and date range) and `GET /api/v1/me/orders/{id}`.
- **Logic:**
  - Ownership is enforced in the SQL predicate.
  - Fixed customer-facing schemas that cannot carry `internal_note` or provider references.
  - STL lines show `awaiting_delivery` or `delivered` with `delivered_at`; this is the customer's STL purchase list (F-027).
  - Each order shows its payment method and the derived `payment_due` and `can_cancel` flags (`can_cancel`: at least one physical line, cash or a payment that reached `paid`, status `in_progress` or `partially_refunded`, every physical line `pending`); a physical line in `in_production` is shown as `pending` ("Received"), and the customer's status history omits `in_production` entries, because "start printing" is internal (ADR-024). VS-029 tests the masking once physical lines can move.
- **Tests:**
  - Another user's order gives 404.
  - Snapshots survive product edits.
  - The internal note never appears.
  - Pagination is stable.
- **Done when:** A customer sees exactly what they bought, at the price they paid.

## VS-026 — Address book
**Status:** Done
**Depends on:** VS-008
**Goal:** A verified customer saves Lebanese delivery addresses and picks a default.
- **Model / migration:** `addresses` (label, recipient, phone, governorate, city, area, street, landmark notes), soft-deletable, with a partial unique index allowing one default per user.
- **Endpoints / jobs:** `GET/POST /api/v1/me/addresses`, `GET/PATCH/DELETE /api/v1/me/addresses/{id}`, `PUT /api/v1/me/addresses/{id}/default`.
- **Logic:**
  - Reuses `current_verified_user` (VS-008).
  - Switching the default happens in one transaction under a lock.
  - Validates a Lebanese phone number and required location fields. The phone is the courier's contact and is snapshotted onto delivery orders (BR-078).
- **Tests:**
  - Concurrent default switches leave one default.
  - Another user's address gives 404.
  - An unverified user cannot write.
- **Done when:** A customer always has at most one default address.

## VS-027 — Shipping zones
**Status:** Removed by ADR-024 (the courier prices and collects the delivery fee; the platform charges no shipping).
**Was:** admin-managed flat-rate Lebanese delivery zones and the customer zone list. Nothing replaces it: no order carries a shipping amount.

## VS-028 — Physical checkout: delivery, pickup, payment method, dispatch estimate
**Status:** Not started
**Depends on:** VS-023, VS-024, VS-026
**Goal:** A customer checks out physical and mixed carts with courier delivery or free workshop pickup, pays online or (physical-only orders) in cash on delivery or at pickup, and sees an honest estimated ready date.
- **Model / migration:**
  - No order columns (they come from VS-023).
  - Seeds three settings (ADR-024): `cash_payment_enabled` (boolean, `true`, public), `cash_max_open_orders` (integer, `1`, range 1–10), `cash_max_order_total` (money, `10000` cents USD, range 1 – 1 000 000, public).
  - Deletes the obsolete seeded `free_shipping_threshold` setting (VS-007) with its registry entry and public-allowlist slot, as VS-023b does for `daily_download_cap`.
  - `cash_payment_blocks` (Ordering): `user_id`, `contact_phone_hash`, `order_id`, `reason` (`refused`/`no_show`), `created_at`, `cleared_at`, `cleared_by`; partial indexes on `user_id` and on `contact_phone_hash` `WHERE cleared_at IS NULL`. VS-031 inserts blocks; VS-029 lists and clears them.
  - New secret `PHONE_HASH_SALT` in settings and `.env.example`: the key of the phone hash (`HMAC-SHA256` of the E.164 number). Unlike `IP_HASH_SALT` it is never rotated, because every block and open-order match depends on it.
  - The open-cash-order count reads `orders` by `user_id` and by `contact_phone_hash`; add an index for the hash lookup on unpaid cash orders if `EXPLAIN` shows the need.
- **Endpoints / jobs:** `POST /api/v1/checkout` accepts `fulfillment_method`, `address_id`, `contact_phone` (pickup only), `payment_method`, `payment_provider` (online, when more than one is configured) and a note.
- **Logic:**
  - Reuses the checkout transaction from VS-023, addresses from VS-026, and `SettingsReader` (VS-007).
  - Locks the chosen address `FOR SHARE` (owner, live) and refuses a deleted or foreign one with 422 `INVALID_FULFILLMENT`; that is why the address `DELETE` has no `409` (ADR-027). Contact phones are normalised with `app.core.phone` (VS-026), the same parser as the address book.
  - Enforces the SRS §7.4 matrix; a mismatch gives 422 `INVALID_FULFILLMENT`.
  - Snapshots the address, the contact phone normalised to E.164 and its hash (the address's phone for delivery, the entered Lebanese phone for pickup), the payment method, lead time and batch size.
  - Totals are recomputed first (`subtotal + tax`; no shipping). Cash rules are then checked against the **recomputed** total, under the cart lock (which serialises one customer's checkouts) and a transaction-scoped advisory lock on the phone hash (which serialises checkouts from different accounts sharing it):
    - every line physical, `cash_payment_enabled` on, a total above 0, and no uncleared `cash_payment_blocks` row for the customer or the phone hash, otherwise 422 `PAYMENT_METHOD_NOT_ALLOWED`;
    - fewer than `cash_max_open_orders` unpaid, uncancelled cash orders for the customer or the phone hash, and a total of at most `cash_max_order_total`, otherwise 422 `CASH_PAYMENT_LIMIT_REACHED`.
  - An online order with an unconfigured `payment_provider` gives 422 `PAYMENT_METHOD_NOT_ALLOWED`; the chosen provider is stored on the pending payment row.
  - A cash order is created with **no payment row** and no provider call; its status derives to `in_progress`; consent records the cash terms; the confirmation email states the amount due in cash on delivery (or at pickup).
  - Every delivery-order response and email says "delivery fee paid to the courier on delivery".
  - Dispatch days = max over lines of (lead time × ceil(quantity ÷ batch size)), counted from placement for both payment methods.
  - After an online payment, or at placement of a cash order, physical lines stay `pending` (eligible for production).
- **Tests:**
  - Table test over all five §7.4 rows, crossed with both payment methods (cash refused for STL-only and mixed carts).
  - 10 units with lead time 2 and batch size 4 gives 6 days.
  - Cash limits: switch off, blocked customer, blocked phone on another account, a second open cash order for the same customer, a second open cash order on another account with the same phone, a total one cent over the cap — each refused with nothing created.
  - The same phone written in different formats (`+961 3 123 456`, `03123456`, `9613123456`) normalises to one number and one hash, and matches the same block and the same open-order count.
  - A cash order whose recomputed total is 0 (free products) is refused; the setting rejects a `cash_max_order_total` of 0.
  - A cart whose snapshot total is under the cap but whose recomputed total is one cent over is refused for cash.
  - Two accounts sharing a normalised phone check out cash in parallel with `cash_max_open_orders = 1`: one order, one 422.
  - The same `Idempotency-Key` with only `payment_method` changed gives 409 `IDEMPOTENCY_KEY_CONFLICT`.
  - A cash order is never selected by `release_stale_checkouts`, reconciliation or retry.
  - Snapshots survive later edits; the phone is stored normalised; no block row contains a readable phone.
  - In a mixed order the STL line is `awaiting_delivery` and the physical lines stay pending.
  - `free_shipping_threshold` is gone from the settings table, the registry and `GET /settings/public`.
- **Done when:**
  - Every cart type checks out with correct totals and the right payment methods.
  - No order carries a shipping amount, and snapshots are immutable.
  - The cash limits hold across accounts that share a phone.

## VS-029 — Admin order queue, fulfillment and cash handover
**Status:** Not started
**Depends on:** VS-028, VS-023b, VS-024, VS-025
**Goal:** The administrator moves each physical line of a cash order or a paid online order from received to delivered or picked up, records the cash for a cash order at handover, and the customer is told at each visible step.
- **Model / migration:** A partial index for the cash-due filter on unpaid cash orders, shaped by `EXPLAIN`; other queue indexes only if `EXPLAIN` shows the need.
- **Endpoints / jobs:**
  - `GET /api/v1/admin/orders` (filters include `payment_method` and `payment_due`), `GET/PATCH /api/v1/admin/orders/{id}` (`PATCH` edits the internal note only). The fulfillment queue never lists `pending_payment` orders.
  - `POST …/items/{item_id}/transition` (created by VS-023b for STL lines; this slice adds the physical edges).
  - `POST /api/v1/admin/orders/{id}/cash-handover` (body: `amount_cents`).
  - `GET /api/v1/admin/cash-blocks` (filters: customer, active), `POST /api/v1/admin/cash-blocks/search` (phone in the body, so it never reaches request logs; hashed before matching) and `POST /api/v1/admin/cash-blocks/{block_id}/clear` (audited).
- **Logic:**
  - Reuses `derive_order_status`, the outbox, `create_notification`, `AuditWriter`, and VS-025's `OrderDetail`.
  - Pure transition tables (ADR-024):
    - delivery: `pending → in_production → ready_to_ship → shipped → delivered`;
    - pickup: `pending → in_production → ready_for_pickup → picked_up`.
  - **No physical work on an unpaid online order (BR-148):** every physical transition requires the order to be a cash order or to have an online payment that reached `paid` (`paid`, `partially_refunded` or `refunded`), otherwise 409 `INVALID_STATE_TRANSITION`. The hold release's `pending → cancelled` (VS-024) is the only exception, and it does not use this endpoint.
  - **Lock order (ADR-024):** every transition locks the `orders` row first, then the line, then recomputes the status, and writes history, audit, email and notification in the same transaction.
  - `in_production` ("start printing") sends no email or notification, and is hidden from the customer's status history. `OrderDetail.can_cancel` is true only when the order has a physical line, is cash or has a payment that reached `paid`, has status `in_progress` or `partially_refunded`, and every physical line is `pending`. Emails and notifications: finished (`ready_to_ship`), shipped, ready for pickup (with the pickup address and hours), delivered or picked up. Delivery emails say "delivery fee paid to the courier on delivery".
  - On a cash order the transition endpoint refuses `→ delivered` and `→ picked_up` with 409 `INVALID_STATE_TRANSITION`; only the handover reaches them.
  - **Cash handover** (SRS §9.8), in one transaction:
    - locks the `orders` row, then all its lines by `id`;
    - requires at least one live line, and every live line `shipped` (delivery) or `ready_for_pickup` (pickup), otherwise 409 `INVALID_STATE_TRANSITION`;
    - requires `amount_cents` to equal the sum of live line totals and to be above zero, otherwise 422 `CASH_AMOUNT_MISMATCH`;
    - marks them all delivered / picked up and inserts one `payments` row (`provider = 'cash'`, `status = 'paid'`, `recorded_by`, `verified_at`); the unique cash-payment index is the final guard;
    - recomputes the status and writes history, audit, notification and the email with the cash receipt.
  - The delivered / picked-up email's "I got it" and "Report a problem" buttons link to the order page; VS-029b adds the actions.
  - Clearing a cash block sets `cleared_at` and `cleared_by`; clearing an already-cleared block is a no-op 200.
  - **Available actions (ADR-025):** every line of every `AdminOrderDetail` carries `available_actions`, a list of `{target_status, cancel_reasons}` the transition endpoint would accept at read time. It comes from the same pure transition table, so it includes the BR-148 payment gate, the cash-handover rule and the $0 `shipped → cancelled` edge; `cancel_reasons` is empty when no reason is taken. VS-023b's STL edge is listed too. Customer responses never carry it.
- **Tests:**
  - Every legal and illegal edge, per fulfillment method and payment method.
  - "Start printing" (or any physical transition) on a `pending_payment` online order gives 409, and the order never appears in the fulfillment queue.
  - `in_production` produces no email and no notification, appears as `pending` to the customer, and is absent from the customer's status history; `can_cancel` turns false when printing starts, and is false for an STL-only order and for an unpaid online order.
  - Two admins acting on the same state: one wins.
  - Cash handover: a wrong amount gives 422 with nothing changed; a line not yet shipped gives 409; two admins recording one handover give one payment, one audit row and one email; a handover racing a transition on another line of the same order ends with one winner and no deadlock.
  - A `reconcile_payments` run (VS-024) running at the same time as a handover or a line transition on the same order: no deadlock, both outcomes correct.
  - A cash order reaches `completed` through the handover, and its payment is `paid` for exactly the live line total.
  - Cash blocks (rows seeded directly, since VS-031 creates them): a customer gets 404 on both routes; clearing writes an audit row; a second clear is idempotent; after clearing, checkout offers cash again for that customer and phone.
  - An email-provider outage does not block a transition.
  - The internal note is never visible to the customer.
  - `available_actions` matches the endpoint: for every line state, fulfillment method, payment method and payment state, each listed action succeeds with one of its `cancel_reasons` (when any), and every unlisted target gives 409; an unpaid online order's lines and a cash order's `→ delivered` / `→ picked_up` are never listed.
- **Done when:**
  - No route sets `order.status` directly, and no route but the handover creates a cash payment.
  - No physical line of an unpaid online order ever moves, except the hold release cancelling it.
  - A physical order reaches `completed` with either payment method.

## VS-030 — Refunds and settlement
**Status:** Not started
**Depends on:** VS-029, VS-024
- **Notes from VS-023:**
  - Create a late-capture refund obligation for every row that already has `late_captured_at` (`SELECT id, order_id, provider, amount_cents, status, late_captured_at FROM payments WHERE late_captured_at IS NOT NULL`); until then that listing is the only view.
  - `derive_order_status` implements SRS §20.2 as written. The VS-023 plan's Revision 1 item 1 records two cases (one line `refunded` with a refund still owed; all lines cancelled with a refund owed) where a reorder may be wanted; a change needs an ADR and the co-developer's confirmation.
**Goal:** The administrator refunds any part of any paid line by hand, records each refund here, and every refund stays in a queue until settled — or, if it fails, until it is reissued.
- **Model / migration:** `refunds` and `refund_items`, with non-negative money checks.
  - `refunds.kind` (new enum `refund_kind`: `admin`, `cancellation`, `late_capture`, `chargeback`); `reason` stays free text for people. No `method` column and no provider refund id: every V1 refund is manual (ADR-024).
  - `refunds.status`: `pending`, `settled`, `failed`. `refunds.reissued_at` and `reissue_of_refund_id` link a failed refund to its reissue. `refunds.excess_cents` (chargebacks only).
  - `requested_by` is nullable only for `kind = late_capture` (created by the system).
  - `UNIQUE(payment_id) WHERE kind = 'late_capture' AND status <> 'failed'`: one live late-capture refund per payment.
  - Obligations index: `(created_at) WHERE status = 'pending' OR (status = 'failed' AND reissued_at IS NULL)`.
  - No shipping component (ADR-024).
- **Endpoints / jobs:** `POST /api/v1/admin/orders/{id}/refunds` (requires an `Idempotency-Key` header), `GET /api/v1/admin/refunds`, `GET /api/v1/admin/refunds/{id}`, `POST …/{id}/settle`, `POST …/{id}/fail`, `POST …/{id}/reissue`.
- **Logic:**
  - Reuses the idempotency service from VS-023.
  - Adds the automatic `late_capture` refund to VS-024's late-capture path: no items, no requester, the captured amount; the item-sum check is waived for this kind.
  - **Every refund is manual:** the administrator pays it in the provider dashboard or in cash, then settles it here. The platform never calls a provider refund API.
  - **Lock order (ADR-024):** the `orders` row, then the affected lines by `id`, then the payment, then the refund; balances are derived under those locks. Settle, fail and reissue take the same order.
  - **Paid lines only (BR-149):** a line is refundable only if it is a paid line. Its refundable balance is `line_total` minus its items in non-failed refunds and in failed refunds not yet reissued; a cancelled line of a cash order has 0. A request over any line's balance or the payment's balance gives 422 `REFUND_EXCEEDS_AVAILABLE`.
  - **Unfinished physical lines:** a refund that would bring a `pending`, `in_production`, `ready_to_ship`, `shipped` or `ready_for_pickup` line to 0 gives 422 `REFUND_REQUIRES_CANCELLATION`; the administrator cancels it instead (VS-031).
  - **Partial refunds per line:** a refund of less than a line's balance leaves the line in its state. A line becomes `refunded` when its refunds cover its whole total: a fully refunded STL line still `awaiting_delivery` leaves the delivery queue and frees ownership; a partially refunded one stays. A fully refunded physical terminal line becomes `refunded`.
  - **Failed refunds stay owed:** `fail` marks a pending refund `failed` (a bounced transfer or a rejected dashboard refund). Lines keep their state. The refund stays in the obligations queue as owed until `reissue`, which creates a new pending refund of the same kind, items and amount, and sets `reissued_at` on the failed one; a failed `late_capture` refund is reissued the same way.
  - The payment and order statuses are recomputed from refund records at creation: non-failed refunds covering all paid money make the order `refunded` (unless every line is cancelled); any non-failed or owed refund makes it at least `partially_refunded`; `late_capture` refunds never count; settlement never changes either status.
  - A cash payment is refunded up to the cash recorded.
  - Sends a "refund issued" email.
- **Tests:**
  - Concurrent partial refunds never exceed the paid amount, on an online and on a cash payment.
  - Two concurrent partial refunds that together equal the full paid amount both succeed, and the order becomes `refunded`.
  - Idempotent replay.
  - Partial-amount refunds on one line, then a refund of the rest: the line stays in its state after the first and becomes `refunded` after the second; the order goes `partially_refunded` then `refunded`. Run it on a delivered physical line and on an STL line still `awaiting_delivery` (it stays in the queue and owned after the first refund, and leaves both after the second).
  - Marking delivered on an STL line that has been partly refunded still works; a fully refunded line gives 409 (moved from VS-023b).
  - A full-amount refund of a `pending`, `in_production`, `ready_to_ship`, `shipped` or `ready_for_pickup` physical line gives 422 `REFUND_REQUIRES_CANCELLATION`; a partial one succeeds.
  - A refunded STL line awaiting delivery disappears from the delivery queue.
  - A refund racing mark-delivered on one STL line: exactly one wins.
  - A customer whose STL line was refunded in full can buy it again.
  - An unpaid order gives 409, including an unpaid cash order.
  - A refund racing a cash handover on the same order: before the handover it gives 409 (unpaid), after it succeeds; never both a refund and an unpaid order.
  - A refund on a cash order after handover is capped at the cash recorded.
  - A late capture (VS-024) creates exactly one `late_capture` refund obligation for the captured amount, with no items and no requester, and the order status ignores it. Two distinct provider events for one late capture still create one refund.
  - A failed `late_capture` refund stays owed and is reissued as a new `late_capture` refund.
  - Settling a refund leaves the order and payment status unchanged.
  - A failed refund stays in the obligations queue as owed, changes no line state, keeps the order `partially_refunded`, and its amount can only be refunded again by reissuing it; after the reissue it leaves the queue.
  - Two partial refunds complete a line's coverage; the earlier one then fails: the line stays `refunded`, the failed amount is owed, and reissuing restores full coverage.
  - Mixed: the STL line is refunded first (payment `partially_refunded`), then the physical line is started, made ready, shipped and delivered — none refused by BR-148.
  - Mixed orders (SRS mandatory coverage), each asserting line states, refundable balances and the order status:
    - STL line refunded while the physical line is delivered → `partially_refunded`;
    - physical line refunded after delivery while the STL line is `awaiting_delivery` → `partially_refunded`, STL still in the queue;
    - both lines refunded across two separate refunds → `refunded`;
    - a failed refund in a mixed order → owed, order `partially_refunded`.
- **Done when:**
  - A refund cannot exceed any line's or the payment's balance, never touches an unpaid line, and never empties an unfinished physical line.
  - A line is `refunded` only when fully refunded.
  - No refund obligation, pending or failed, leaves the queue until it is settled or reissued.
- **Must resolve before build** (final PR #8 review; recorded per the owner's stop rule, not yet decided):
  1. **Order status after a refund fails (both reviewers).** SRS §20.2 checks "all lines refunded → refunded" before "any non-failed or owed refund → partially_refunded", and database-design §17.2 and the entities projection do the same. But a failed refund reverts no line, so on a single-line order (or one where every line is fully refunded) a full refund that later fails leaves the line `refunded`. The order then reads `refunded` while money is still owed, which breaks ADR-024 decision 11 ("an owed one keeps the order `partially_refunded`") and this slice's tests. Read by coverage instead of line state, the rule is redundant with "refunds cover all paid money". Separately, "all lines cancelled → cancelled" is checked first, so an all-cancelled order whose cancellation refund failed reads `cancelled`, not `partially_refunded`. Suggested fix: drop "all lines refunded" or define it by non-failed coverage; evaluate "an owed refund exists" before both refunded rules; state where an all-cancelled order with an owed refund lands; add order-status assertions to the failed-refund tests (resolve with VS-023's `derive_order_status`).
  2. **A chargeback leaves pending and owed refunds payable, and no obligation can be closed without paying it (money reviewer).** The remaining balance subtracts pending and owed refunds, and anything beyond it becomes `excess_cents`. Refund states are only pending, settled and failed, and a `cancelled` refund state is forbidden. Scenario: $50 paid → $10 goodwill refund pending → the bank charges back $50 → the chargeback records $40 + $10 excess → the admin, following the queue, still pays the $10: $60 out on a $50 payment. The same happens with an owed refund reissued after a chargeback. A refund created by mistake can only be falsely settled or left owed forever, which keeps the order `partially_refunded` and blocks account deletion. A chargeback on a late-captured attempt with a pending `late_capture` refund is undefined. Suggested fix: a terminal `voided` refund outcome (audited, admin-only, reason required); chargeback recording voids or absorbs pending and owed refunds on the payment before computing excess; define chargebacks on late-captured payments.
  3. **A chargeback on a payment with zero remaining balance cannot be recorded (money reviewer).** `refunds.amount_cents` has `CHECK > 0`, but a chargeback after a full settled refund would be `amount_cents = 0, excess_cents = 5000`. The CHECK rejects it, so the double-dip leaves no record, alert or audit. Suggested fix: allow `amount_cents >= 0` when `kind = 'chargeback'` and `excess_cents > 0`, or keep chargebacks in their own table.
  4. **After a full chargeback, an unfinished physical line can still be shipped (both reviewers).** ADR-024 decision 16 and SRS §9.7 say lines covered in full "become `refunded` (an unfinished physical line … is then cancelled)". Read literally that is an illegal `in_production → refunded` edge, and VS-032 has the admin cancel the line later. In between, the transition gate is only "payment reached paid" (`refunded` counts), so `ready_to_ship → shipped → delivered` stays allowed on a line whose money the bank took back. A fully charged-back `shipped` or `returned` paid line has no exit at all: it can't be cancelled, `returned → cancelled` is cash-only, and `returned → refunded` needs a balance above 0. Suggested fix: cancel zero-balance unfinished lines inside the chargeback transaction with no refund, or refuse forward transitions on a physical line whose refundable balance is 0; let `returned → refunded` go through when coverage is already full; fix the ADR and SRS wording.
  5. **Chargeback recording has no endpoint, schema or idempotency (both reviewers).** api-endpoints §19 has no chargeback route, `RefundCreate` always records `kind = admin`, the idempotency list covers refund creation only, and VS-032 says "Endpoints / jobs: None new" while requiring chargebacks to be recorded. Nothing says the `REFUND_REQUIRES_CANCELLATION` check is waived for chargebacks. A double-submitted partial chargeback is recorded twice, marking lines `refunded`, removing an unsent STL from the queue (paid access lost) and understating revenue. VS-032's test cancels a line after a chargeback, which needs VS-031, but VS-032 doesn't depend on it. Suggested fix: `POST /api/v1/admin/orders/{id}/chargebacks` with a required `Idempotency-Key`, a unique provider dispute reference, per-line items and the target `payment_id` (online only, never cash); add VS-031 to VS-032's dependencies.

## VS-031 — Cancellation and returns
**Status:** Not started
**Depends on:** VS-030
**Goal:** A customer cancels before printing starts, the administrator cancels at any legal point, a returned item is re-shipped, reprinted, refunded or (unpaid cash) cancelled, and a whole-order cash refusal blocks cash for that customer and phone.
- **Model / migration:** None (`order_items.cancel_reason` comes from VS-023, `cash_payment_blocks` from VS-028).
- **Endpoints / jobs:** `POST /api/v1/me/orders/{id}/cancel`, `POST /api/v1/admin/orders/{id}/cancel`; the transition endpoint gains the `returned` and no-show edges. Admin cancels from `ready_to_ship`, `returned` or `ready_for_pickup` require `cancel_reason`: `refused` (any of the three), `no_show` (`ready_for_pickup` only) or `other`.
- **Logic:**
  - Reuses the transitions from VS-029 and refund creation from VS-030.
  - **Lock order (ADR-024):** every cancel locks the `orders` row, then all physical lines by `id`, then checks and changes them, creates any refund, and recomputes the status. A cancel that may insert a block then also locks the customer's cart and takes the phone advisory lock, so it serialises against that customer's checkouts with any phone and against other accounts' checkouts with the same phone.
  - Customer cancel requires at least one physical line, a cash order or a payment that reached `paid`, and every physical line `pending`, otherwise 409 `ORDER_NOT_CANCELLABLE` with no partial change. It works for paid online orders and unpaid cash orders; it matches `can_cancel`.
  - Admin cancel covers `pending`, `in_production`, `ready_to_ship` and `ready_for_pickup` lines.
  - Every cancellation of a paid line creates a pending `cancellation` refund for the line's **remaining balance** in the same transaction (none when that is 0, e.g. after a full chargeback); cancelling an unpaid cash line creates none.
  - Admin cancel restates BR-148: on an unpaid online order (`pending_payment`) it gives 409; only the hold release cancels those.
  - An unpaid cash line with a total of 0 may also go `shipped → cancelled` (reason `other`), so an accepted $0 line is not recorded as a return.
  - STL lines are never cancelled.
  - `returned → shipped | in_production | refunded` (paid line) `| cancelled` (unpaid cash line only; `refused` or `other`).
  - **Cash block (BR-144):** when a cancel leaves a cash order with no live line, and every line cancelled from `ready_to_ship`, `returned` or `ready_for_pickup` carries `refused` or `no_show` (at least one), a `cash_payment_blocks` row is inserted for the customer and the order's phone hash, in the same transaction. The rule reads all of the order's lines, so it does not depend on cancel order. A refusal of only some lines, and any `other` cancel, never blocks. An online order never blocks.
  - If a refusal leaves only lines totalling 0, the administrator cancels them (reason `other`) instead of a handover.
  - A cancellation that leaves a cash order with lines still live sends the "order cancelled" email with the new amount due.
- **Tests:**
  - A customer cancel racing "start printing" has exactly one winner (repeated 100 times), including on a two-line order where printing starts on the line the cancel checks last.
  - A cash handover racing an admin cancel on another line of the same order: one winner, no deadlock.
  - A cash handover on an order whose lines are all cancelled gives 409.
  - Two concurrent line changes on one order (cancels of both remaining lines) leave the order status correct: an all-cancelled cash order is `cancelled`, leaves the cash-due view and stops counting toward `cash_max_open_orders`.
  - Two concurrent `refused` cancels of the last two live lines of a cash order create exactly one block row.
  - Illegal edges: `returned → cancelled` on a paid online line, `returned → refunded` on an unpaid cash line, `no_show` from `returned` or `ready_to_ship` — each 409.
  - `ready_for_pickup → cancelled`: on a cash order with `no_show` or `refused` it blocks; on an online order it creates a refund and never blocks.
  - A refusal before shipping (`ready_to_ship → cancelled`, `refused`) of a whole cash order blocks.
  - The block outcome is the same whichever order the lines are cancelled in (`refused` then `other`, and `other` then `refused`: no block in both).
  - STL lines are unaffected.
  - Self-cancel on a `pending_payment` online order and on an STL-only order gives 409, and `can_cancel` is false for both.
  - Self-cancel on a paid mixed order: only the physical lines are cancelled and refunded, the STL line stays in the delivery queue, and the order is `partially_refunded`.
  - Cash refusal end to end: cash order → shipped → returned → cancelled (`refused`), no refund, order `cancelled`, and the next checkout by that customer, or by another account with the same phone, offers online only.
  - A partly refused cash order: one line cancelled (`refused`), the handover records the rest, no block. (Revenue and badge for the refused line are tested in VS-043 and VS-036.)
  - A refusal that leaves only $0 lines: the administrator cancels them with `other`; the order ends `cancelled` without a handover and without a block.
  - A refund item on a cancelled line of a paid cash order gives 422.
  - An `other` cancel of a whole cash order never blocks.
  - **Mandatory end-to-end (SRS §5.6):** mixed order → paid online → admin cancels the physical line in production → partial refund of that line → STL line still delivered or awaiting delivery → order `partially_refunded` → refund pending until settled.
  - Mixed: physical line cancelled (cancellation refund) and then the STL line refunded → `refunded`.
  - Mixed: the STL line refunded first (payment `partially_refunded`), then the physical line started and cancelled by the admin with its refund — not refused by BR-148; order `refunded`.
  - Mixed: physical `returned → refunded` while the STL line is delivered → `partially_refunded`.
  - Mixed: a manual refund after a cancellation-created refund, at exactly the remaining balance (succeeds) and at one cent over (422).
  - Mixed: an STL refund racing a cancellation of the physical line on the same order → both commit in turn, and the final status reflects both.
  - Mixed: a partial refund of the STL line, then a cancellation (full refund) of the physical line → `partially_refunded`, not `refunded`.
  - Mixed: the physical line's cancellation refund fails while the STL line is delivered → the refund stays owed, and the order is `partially_refunded`, never `completed`.
  - A partial goodwill refund on a `pending` physical line, then a self-cancel (and separately an admin cancel), refunds exactly the remaining balance.
  - Self-cancel of a paid physical-only online order: order `cancelled`, refund pending in the obligations queue.
  - Admin cancel on a `pending_payment` online order gives 409.
  - A same-customer cash checkout with a different phone, racing a cancel that inserts a block: the checkout either commits first or sees the block; never an order placed after the block that should have stopped it.
  - An accepted $0 cash line that is `shipped` is cancelled directly (`other`) without a return.
- **Done when:**
  - The SRS §5.6 end-to-end test passes.
  - The cancel-versus-start-printing race always has one winner, with no deadlock.
  - An unpaid cash line is never refunded, and only a whole-order refusal or no-show blocks cash, whatever the cancel order.

## VS-032 — Live online payment provider
**Status:** Not started (final phase: needs a server)
**Depends on:** VS-020, VS-024, VS-030 (and the SRS §30.4 provider decision and merchant credentials)
**Go-live gate:** [ADR-032](adr/ADR-032-checkout-idempotency-and-payment-verification.md) decision 24: no real online provider is configured in production before VS-024 and VS-030 are merged, unless an operational alert on late captures and stuck payments exists. Every adapter must sign its webhooks (ADR-032 decision 15).
**Goal:** Real online revenue: configuring the chosen provider(s) runs the same checkout, verification and recovery flows against them. Refunds stay manual (ADR-024).
- **Model / migration:** Adds the chosen provider value(s) to `payment_provider`; provider metadata only if needed.
- **Endpoints / jobs:** None new; the provider-neutral webhook route from VS-023 is IP-allowlisted in VS-020's nginx.
- **Logic:**
  - Reuses the payment port from VS-023.
  - Replaces the single `payment_provider` setting with a list of configured online providers, and renames the Whish-specific settings in `src/app/core/config.py` and `.env.example` (`whish_*`, `whish_webhook_ips`) to per-provider names. If §30.4 chooses both, checkout and retry let the customer pick one, stored on the payment row (VS-023, VS-024).
  - The adapter implements create-payment and redirect, signature check (if offered), and status query (if not offered, manual confirmation from VS-024 stays on). It has no refund operation: every V1 refund is manual, even if the provider offers a refund API. A card gateway uses a hosted or redirect page so card data never reaches the platform.
  - Chargebacks are recorded as a refund of `kind = chargeback`, already `settled` and never in the obligations queue, split across lines by the administrator, under the ADR-024 lock order (`orders`, lines, `payments`, `refunds`). Lines covered in full become `refunded`; an unfinished physical line covered in full is then cancelled with no further refund (balance 0). Any amount beyond the payment's remaining balance is recorded as `excess_cents` and alerted.
  - Record the decision and the provider's answers to SRS §30.1 in an ADR.
- **Tests:**
  - The same contract fixtures as the mock (paid, underpaid, failed, bad signature, duplicate, timeout, late success after expiry), run against the provider's sandbox; an end-to-end payment on staging.
  - A chargeback on a mixed order whose physical line is still `in_production`: the chargeback is `settled` at once and never appears as a pending obligation; the STL line becomes `refunded`; the admin then cancels the physical line and no second refund is created; the order status is correct.
  - A chargeback after a partial refund: allocations stay within each line's balance, and any amount beyond the payment's remaining balance is recorded as `excess_cents` with an alert.
  - A chargeback can never be settled again or marked failed.
- **Done when:**
  - Every fixture passes against the sandbox.
  - No checkout, order or cash-handover code changed.

## VS-033 — Contact form and captcha
**Status:** Done
**Depends on:** VS-005
**Goal:** A visitor messages the business without an account, the administrator works through a message queue, and every public form is captcha-protected (SEC-12, ADR-025).
- **Model / migration:** `c2b3aae1cdee` creates `contact_messages` (status `new`, `read`, `replied` or `archived`), without `user_id` and `order_id`, which VS-029b adds.
- **Endpoints / jobs:** `POST /api/v1/contact-messages`, `GET /api/v1/admin/contact-messages`, `GET/PATCH /api/v1/admin/contact-messages/{id}`.
- **Logic:**
  - Reuses the rate limiter (VS-002) and `AuditWriter`.
  - New `CaptchaPort` with a Cloudflare Turnstile adapter (`TURNSTILE_SECRET`) and a fake adapter refused outside `test` and `development` (an allowlist, like the scanner's).
  - **Applied to all five public forms (ADR-025):** `POST /api/v1/contact-messages` here, `POST /api/v1/custom-requests` when VS-034 builds it, and the already-built `POST /api/v1/auth/register`, `/auth/resend-verification` and `/auth/password-reset/request`. Each request schema gains a required `captcha_token`. This is a breaking change for the three auth routes, so release it with the frontend's Turnstile widget.
  - On the three auth routes the captcha is verified before any account lookup, and a refused captcha gives the same answer whatever the email; the enumeration floor (SEC-06) still applies.
  - Adds one stable error code for a missing or refused token to api-endpoints.md §5.2, and decides how a Turnstile outage is answered (failing open would defeat the control).
  - Captcha is checked, then per-IP and per-email limits, then the row is inserted.
  - Admin status changes take a row lock and are audited.
  - Message bodies are never logged.
- **Tests:**
  - A bad captcha stores nothing.
  - Register, resend and reset-request each refuse a missing or bad token, with the same answer and timing for a new, unverified and verified address; existing auth tests send a token the fake adapter accepts.
  - The fake adapter is refused with `ENVIRONMENT` set to `production`, `staging` and `prod`.
  - A rate-limit breach gives 429.
  - The queue is admin-only.
  - Status changes are audited.
- **Done when:** Only captcha-verified, rate-limited messages reach the queue, and register, resend verification and the password-reset request require a valid Turnstile token.
- **Built:** ADR-026 (a refused token is `400 CAPTCHA_INVALID`, an outage fails closed with `503`, a 60/hour attempt limit runs before the captcha). Tests: `tests/integration/engagement/test_contact_messages_api.py`, `test_contact_message_schema.py`; `tests/integration/identity/test_auth_captcha.py`; `tests/concurrency/test_contact_message_status_race.py`; `tests/unit/integrations/test_captcha_factory.py`, `test_turnstile_adapter.py`; `tests/unit/engagement/test_contact_*.py`.

## VS-029b — Receipt confirmation and problem report
**Status:** Not started
**Depends on:** VS-029, VS-033
**Goal:** After delivery or pickup a customer can say "I got it" or report a problem, and the administrator sees it on the order, without either being required.
- **Model / migration:** nullable `contact_messages.user_id` and `order_id`, which VS-033 left out (`order_items.receipt_confirmed_at` and `problem_reported_at` come from VS-023).
- **Endpoints / jobs:** `POST /api/v1/me/orders/{id}/confirm-receipt` and `POST /api/v1/me/orders/{id}/report-problem` (body: message).
- **Logic:**
  - Owner-only, verified, CSRF-protected POSTs from the order page. The email buttons only open that page: nothing changes state on a GET, because email scanners follow links.
  - Both lock the `orders` row first, then the lines (ADR-024 lock order).
  - Confirm sets `receipt_confirmed_at` on the order's `delivered` / `picked_up` lines that lack it; idempotent; no state change and no effect on the order status.
  - Report creates a contact message linked to the order in the VS-033 queue (no captcha, as the caller is signed in; rate-limited) and sets `problem_reported_at`. Resolution uses the existing return, refund and cancel tools.
- **Tests:**
  - Another customer's order gives 404; an order with no delivered line gives 409.
  - Confirming twice changes nothing the second time.
  - An order completes without confirmation.
- **Done when:** Receipt confirmation and problem reports are recorded on the order and never block completion.

## VS-034 — Bring Your Idea submission
**Status:** Done
**Depends on:** VS-014, VS-033
**Goal:** A guest submits a custom-print request with reference images, which are stored privately and safely.
- **Model / migration:**
  - `custom_requests` and `custom_request_attachments` (with `expires_at`).
  - Seeds a new `custom_request_attachment_retention` setting, default 90 days.
- **Endpoints / jobs:** `POST /api/v1/custom-requests` (multipart); new `purge_expired_attachments` job (daily).
- **Logic:**
  - Reuses the image pipeline, `StoragePort`, the scanner and the reaper (VS-014), and captcha (VS-033).
  - Stored in the private `uploads_private` area.
  - Count and size caps.
  - The request and its attachment metadata commit together; files written for a failed request are removed.
  - No order or payment is ever created.
- **Tests:**
  - Captcha, rate limit, fake type, EICAR file and oversize are each rejected with nothing stored.
  - Attachments are not publicly reachable.
  - The purge job deletes both file and row and is idempotent.
- **Done when:**
  - Guest uploads are validated, re-encoded, scanned and private.
  - They expire on schedule.
- **Built:** migration `26d5d039d72c`; ADR-030 (0–5 images at 10 MB, a 20/hour attempt limit and body cap before parsing, 90-day retention stamped at submission, no `user_id`, an in-app notification of new type `custom_request` to every active administrator); `docs/custom-requests.md`. Tests: `tests/integration/engagement/test_custom_requests_api.py`, `test_custom_request_schema.py`, `test_purge_expired_attachments.py`, `test_reap_private_attachments.py`; `tests/concurrency/test_attachment_purge_race.py`; `tests/unit/engagement/test_custom_request_*.py`, `test_submit_custom_request.py`.

## VS-035 — Bring Your Idea pipeline and funnel
**Status:** Done
**Depends on:** VS-034 (VS-020 dropped on 2026-10-17: the download is streamed by the API, ADR-031)
**Goal:** The administrator works each lead through the pipeline, records the quote and outcome, and measures conversion.
- **Model / migration:** None.
- **Endpoints / jobs:** `GET /api/v1/admin/custom-requests`, `GET/PATCH /api/v1/admin/custom-requests/{id}`, `POST …/{id}/transition`, `GET …/{id}/attachments/{attachment_id}/download`, `GET /api/v1/admin/analytics/custom-requests/funnel`.
- **Logic:**
  - The admin-only download is streamed by the API: `Cache-Control: no-store`, `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`. VS-020 may later switch it to nginx `X-Accel-Redirect` (ADR-031).
  - Pipeline: `new → contacted → quoted → in_progress → completed → closed`, with `lost` reachable from `contacted` or `quoted`.
  - `quoted` requires an amount in cents.
  - The funnel counts submissions by cohort (submission date).
- **Tests:**
  - Legal and illegal transitions.
  - Two admins racing on one lead.
  - An expired attachment cannot be downloaded.
  - Funnel counts match seeded data.
- **Done when:** Every lead follows the state machine, and the funnel shows won and lost counts.
- **Built:** no migration. Decisions in [ADR-031](adr/ADR-031-bring-your-idea-pipeline-and-api-streamed-download.md), which amends ADR-030 decision 3; contract in [`custom-requests.md`](custom-requests.md#admin-pipeline-vs-035).
  - The server derives the outcome (`won` at `in_progress`, `lost` at `lost`, which also stamps `closed_at`). A quote of 1 to 100,000,000 cents is required on `quoted` and refused elsewhere, in USD. A same-state move is 409.
  - The download sends a sandboxed CSP and `same-origin` CORP too, renames the file to its stored type, and has no Range support. Expired, purged, missing and another request's attachments are all 404.
  - The funnel takes `[from, to)` (default the last 90 days, at most 366, errors 422) and counts a stage once reached.
  - List, view, transition, notes and download are audited, notes without their text.
  - New `StoragePort.open` streams an object.
  - Tests: `tests/unit/engagement/test_custom_request_pipeline.py`, `tests/unit/integrations/test_local_storage.py`; `tests/integration/engagement/test_custom_request_admin_api.py`, `test_custom_request_attachment_download.py`, `test_custom_request_funnel.py`; `tests/concurrency/test_custom_request_transition_race.py`; `tests/smoke/test_vs035_smoke.py`.

## VS-036 — Reviews and Verified Purchase badge
**Status:** Not started
**Depends on:** VS-015, VS-028, VS-030, VS-031
**Goal:** Any verified user reviews a product. The badge honestly reflects current purchase evidence, and product ratings stay correct.
- **Model / migration:** `reviews` (rating CHECK 1–5; unique `(user_id, product_id)` among live rows).
- **Endpoints / jobs:** `GET /api/v1/products/{slug}/reviews`, `GET /api/v1/me/reviews`, `POST /api/v1/reviews`, `PATCH/DELETE /api/v1/reviews/{id}`.
- **Logic:**
  - Adds a badge-recompute hook to payment application (VS-023), the cash handover (VS-029) and refunds (VS-030).
  - The badge is true when the user has a paid (BR-149), non-refunded line (STL or physical) for the product. A cash line counts only once its cash is recorded (ADR-024).
  - Links are rejected; the text passes a profanity filter; posting is rate-limited.
  - `average_rating` and `review_count` are recomputed under a product lock in the same transaction.
- **Tests:**
  - A non-buyer can review but gets no badge.
  - A duplicate review gives 409.
  - A refund removes the badge.
  - An unpaid cash line gives no badge; the handover grants it; a refused (cancelled) cash line never does, even when the rest of its order was handed over and paid.
  - Concurrent edits leave the aggregates correct.
  - WhatsApp-only products never get a badge.
- **Done when:**
  - The badge is never stale after a payment or refund.
  - Aggregates always match the visible reviews.

## VS-037 — Review moderation
**Status:** Not started
**Depends on:** VS-036
**Goal:** The administrator hides and restores reviews without deleting history.
- **Model / migration:** None.
- **Endpoints / jobs:** `GET /api/v1/admin/reviews`, `GET /api/v1/admin/reviews/{id}`, `POST …/{id}/hide`, `POST …/{id}/restore`.
- **Logic:** Reuses the aggregate recompute from VS-036. Each action takes a row lock, checks state, toggles, recomputes and writes an audit row.
- **Tests:**
  - A hidden review leaves both the public list and the aggregates.
  - Hiding an already-hidden review gives 409.
  - The routes are admin-only.
- **Done when:** A hide or restore updates public ratings in the same transaction.

## VS-038 — Wishlist and wishlist analytics
**Status:** Done
**Depends on:** VS-013
**Goal:** Customers save products, and the administrator sees totals and the most-wishlisted products.
- **Model / migration:** `wishlist_items` (soft delete; unique `(user_id, product_id)` among live rows).
- **Endpoints / jobs:** `GET /api/v1/me/wishlist`, `PUT/DELETE /api/v1/me/wishlist/{product_id}`, `GET /api/v1/admin/analytics/wishlist`.
- **Logic:** `PUT` inserts or restores idempotently. `products.wishlist_count` changes only on a real state change, under a product lock. Analytics reads the maintained counts.
- **Tests:**
  - A repeated `PUT` or `DELETE` counts once.
  - Concurrent adds leave the count equal to the number of live rows.
  - An unverified user cannot write.
- **Done when:** `wishlist_count` always equals the number of live wishlist rows.

## VS-039 — Offer submission and inactivity expiry
**Status:** Not started
**Depends on:** VS-023, VS-007
**Goal:** A customer opens one valid price offer per STL product, both sides see its history, and an offer nobody answers expires on its own.
- **Model / migration:** `offers` (partial unique index: one live offer per user and product across `awaiting_admin`, `awaiting_customer` and `accepted`; `(status, responds_by)` index) and `offer_rounds`, which is append-only.
- **Endpoints / jobs:**
  - `POST /api/v1/offers`, `GET /api/v1/me/offers`, `GET /api/v1/me/offers/{id}`, `GET /api/v1/admin/offers`, `GET /api/v1/admin/offers/{id}`.
  - New `expire_offers` job (every 5 min).
- **Logic:**
  - Reuses the STL ownership check (VS-023) and the offer settings (VS-007).
  - Only STL products the customer does not own.
  - The amount must be at least `minimum_offer_percentage` of the current list price.
  - Refused while a rejection cooldown is active.
  - The first round is `submitted`; then it is the admin's turn, with `responds_by` = now + `offer_response_window`.
  - The job expires overdue offers under a lock and records a `system` round.
- **Tests:**
  - Concurrent submissions: one 201, one 409 `OFFER_ALREADY_ACTIVE`.
  - Below the floor gives 422.
  - A physical product or an owned STL is refused.
  - The expiry job is idempotent.
- **Done when:**
  - At most one live offer per customer and product, enforced by the DB.
  - Stale offers expire.

## VS-040 — Offer counter, accept, reject, withdraw
**Status:** Not started
**Depends on:** VS-039
**Goal:** The customer and the administrator negotiate turn by turn until the offer is accepted, rejected, withdrawn or expired.
- **Model / migration:** None.
- **Endpoints / jobs:**
  - `POST /api/v1/me/offers/{id}/counter`, `/accept`, `/withdraw`.
  - `POST /api/v1/admin/offers/{id}/counter`, `/accept`, `/reject`.
  - `expire_offers` also moves accepted offers past their checkout window to `checkout_expired`.
- **Logic:**
  - Each action locks the offer and checks the state, the turn (409 `OFFER_NOT_YOUR_TURN`) and the deadline (410 `OFFER_EXPIRED`).
  - A counter appends a round, switches the turn and resets `responds_by`.
  - Accept freezes the agreed amount and sets the checkout window from `offer_checkout_window`. From then on, the inactivity timer no longer applies.
  - Reject starts `offer_rejection_cooldown`.
  - Emails: countered, accepted, rejected, and "expiring soon" at 75% of the response window.
- **Tests:**
  - Acting out of turn gives 409.
  - An accept racing a reject: one wins.
  - An accepted offer never expires from inactivity.
  - Resubmitting during cooldown gives 422; with a cooldown of 0 it is allowed.
- **Done when:** Every transition follows SRS §20.6, and every round is kept permanently.

## VS-041 — Accepted-offer checkout and auto-close
**Status:** Not started
**Depends on:** VS-040, VS-023, VS-024
**Goal:** An accepted offer is paid once at the agreed price, and buying the product any other way closes the offer.
- **Model / migration:** None.
- **Endpoints / jobs:** `POST /api/v1/me/offers/{id}/checkout` (requires an `Idempotency-Key` header).
- **Logic:**
  - Reuses the order, payment and verification pipeline from VS-023 and VS-024; the order `source` is `offer`, and the price comes only from the agreed amount.
  - Returns 410 `OFFER_CHECKOUT_EXPIRED` after the checkout window.
  - Payment marks the offer `paid`, and the STL line enters `awaiting_delivery` like any other purchase.
  - Paying for an STL by any route closes any live offer for that user and product as `auto_closed`.
  - A payment already in flight completes even if the checkout window closes meanwhile.
- **Tests:**
  - A list-price change is ignored.
  - A second checkout while a payment is live gives 409.
  - Buying through the cart auto-closes the offer.
  - Offer checkout racing cart checkout yields one owning line (the ownership index).
  - End-to-end SRS §5.4.
- **Done when:** An accepted offer can charge the customer at most once, and a live offer never outlives ownership.

## VS-042 — Download statistics rollup
**Status:** Removed by ADR-019 (STL files are emailed manually; the platform stores none).
**Was:** download statistics and the `downloads` partition rollup. Best-selling STLs come from paid lines (VS-043).

## VS-043 — Business analytics
**Status:** Not started
**Depends on:** VS-029, VS-030, VS-031, VS-036, VS-039
**Goal:** The administrator sees revenue split by physical and STL (attributed per line), recent purchases, customer statistics, pending offers, top-rated products and best-selling STLs.
- **Model / migration:** None.
- **Endpoints / jobs:** `GET /api/v1/admin/analytics/overview`, `/revenue`, `/recent-purchases`, `/customers`, `/top-rated-products`, `/stl-sales` (best-selling STLs from paid, unrefunded lines, plus lines awaiting delivery; replaces the removed download analytics).
- **Logic:**
  - Metric definitions are written first, in the endpoint docs:
    - revenue = paid line (BR-149) snapshot amounts minus refunds, dated by payment date (a cash payment's date is its handover); no shipping (ADR-024); an unpaid cash order and a cancelled cash line are not revenue;
    - day boundaries use `Asia/Beirut`.
  - Date ranges are bounded to 366 days.
  - Each context is read through a reporting port, with no cross-context joins.
- **Tests:**
  - A mixed order splits revenue correctly by stream.
  - A partial refund reduces revenue.
  - An unpaid cash order adds nothing; its handover adds its revenue on the handover date; a refused line of a partly accepted cash order adds nothing.
  - A partial-amount refund of one line reduces revenue by that amount only, and a refund of the rest removes the line entirely; a failed refund reduces nothing; a late-capture refund never appears.
  - An out-of-range period gives 400.
  - A failing query returns an error, not zeros.
- **Done when:** The backend's figures match the documented definitions on seeded data.

## VS-044 — Customer data export
**Status:** Not started
**Depends on:** VS-023b, VS-025, VS-026, VS-036, VS-039
**Goal:** A customer downloads their data as JSON.
- **Model / migration:** None.
- **Endpoints / jobs:** `GET /api/v1/me/export`.
- **Logic:**
  - Each context exposes an export port returning customer-safe records.
  - The export covers the profile, addresses, orders with payment method and STL delivery records, reviews and offers (the SRS list), including soft-deleted rows, marked as such.
  - It is streamed, rate-limited (3 per day) and audited.
- **Tests:**
  - Only the caller's data appears.
  - No hashes, secrets, internal notes or provider references are included.
  - An unverified user gets 403.
- **Done when:** The export contains exactly the five SRS data sets for the caller.

## VS-045 — Account deletion by anonymisation
**Status:** Not started
**Depends on:** VS-026, VS-031, VS-036, VS-038, VS-039
**Goal:** A customer deletes their account. Personal data is stripped and login disabled, while financial and STL delivery records survive anonymised.
- **Model / migration:** None.
- **Endpoints / jobs:** `DELETE /api/v1/me`. The current password is required in the body; this is the fresh-auth check.
- **Logic:**
  - Locks the user, then re-checks for open orders and unsettled refunds; either blocks with 409 `ACCOUNT_DELETION_BLOCKED`.
  - Then, in one transaction:
    - the email becomes `deleted+<uuid>@invalid` and other PII is stripped;
    - `auth_epoch` is advanced and every session revoked (reuses VS-004);
    - addresses and the wishlist are soft-deleted;
    - live offers are withdrawn;
    - reviews keep their text, and the author is shown as anonymous;
    - an audit row is written.
- **Tests:**
  - An open order or pending refund gives 409.
  - Deletion racing a checkout: never an anonymised user with a new order.
  - The old credentials fail.
  - Orders, payments and delivery records remain with no PII.
  - A failure injected midway rolls everything back.
- **Done when:**
  - Deletion is all-or-nothing.
  - The email can be registered again.

## VS-046 — Security data retention and IP-salt rotation
**Status:** Done
**Depends on:** VS-004
**Goal:** Expired security records stop accumulating, and old IP hashes can no longer be linked to new ones.
- **Model / migration:** `75ad58ebd9e5` adds a small `ip_hash_salts` table holding one current salt; old salts are deleted on rotation. `IP_HASH_SALT` is kept, now as the pepper ([ADR-028](adr/ADR-028-keyed-monthly-rotated-ip-hashes.md)). It also seeds `security_token_retention_period` and `session_retention_period`.
- **Endpoints / jobs:** New `purge_expired_security_records` job (daily: expired verification and reset tokens, expired or revoked sessions past retention) and new `rotate_ip_salt` job (daily check, rotates once per UTC month).
- **Logic:** `core.security.hash_ip` is an HMAC under a key derived from the pepper and the current salt; rotating replaces the salt. The purge deletes only rows past their retention. Operator notes: [`security-retention.md`](security-retention.md).
- **Tests:**
  - After rotation, the same IP produces a new hash, and audit and session writes keep working.
  - The purge is idempotent and never touches live tokens or sessions.
- **Done when:** Both jobs run on schedule and are safe to run twice.

## VS-047 — Backups, restore drill and monitoring
**Status:** Not started (final phase: needs a server)
**Depends on:** VS-020
**Goal:** The single-host system survives data loss through verified off-server backups, and silent failures alert a person.
- **Model / migration:** None.
- **Endpoints / jobs:**
  - Nightly full PostgreSQL backups plus continuous WAL archiving.
  - Daily encrypted snapshots of the upload volumes (no STL files are on the server, ADR-019).
  - New `backup_verify` job (daily).
- **Logic:**
  - The backup encryption key is stored off the server.
  - Monitoring:
    - error tracking and uptime checks;
    - a cron heartbeat per registered job;
    - disk usage above 80%;
    - payments stuck in processing and outbox failures (from VS-021 and VS-024).
- **Tests:**
  - A corrupted backup makes `backup_verify` fail and alert.
  - Stopping the worker triggers a heartbeat alert.
  - A timed restore drill on staging.
- **Done when:** The restore drill meets RPO ≤ 5 min for the database and ≤ 24 h for files, and RTO ≤ 4 h, and the result is recorded.

## VS-048 — Launch readiness
**Status:** Not started (final phase: needs a server)
**Depends on:** VS-011 – VS-047
**Goal:** Prove that the finished system meets its performance and security targets, and switch the shop on deliberately.
- **Model / migration:** None.
- **Endpoints / jobs:** None.
- **Logic:**
  - An IDOR and authorization test matrix generated from the OpenAPI route list.
  - A load test on staging-sized hardware.
  - A launch checklist:
    - client values for pickup address and WhatsApp number, and a review of the cash limits (`cash_max_order_total`, `cash_max_open_orders`);
    - the online payment provider decided (SRS §30.4) and live (VS-032);
    - legal pages;
    - the real captcha keys;
    - `accepting_orders` switched to `true`.
  - BUG-47 - database pool connection stalls. Opening a new PostgreSQL connection (TLS + SCRAM handshake in asyncpg) runs on the event loop and freezes the whole worker while it happens. Measured on the dev machine against a local container (event-loop gap, largest of a burst of logins): **55 ms** on a cold app's first burst, **16 ms** once 4 connections were warm, and **113 ms** when 8 concurrent requests forced the pool past its warm connections (also 77 ms in a cold timing-test run). Address before the load test: warm the pool at startup (`pool_pre_ping` plus a minimum pool size / pre-opened connections), size `pool_size`/`max_overflow` to the expected concurrency, and measure whether TLS to the database is needed on a single host. Re-measure with the event-loop-gap probe under the load test.
- **Tests:**
  - Every ID-bearing route is tested as another user, as an anonymous caller and as a non-admin.
  - Load: 200 concurrent users within NFR-01 to NFR-03 (NFR-04 removed by ADR-019).
  - BUG-47: under that load, no event-loop stall above 40 ms from opening database connections.
- **Done when:**
  - The route matrix is green.
  - The load targets are met.
  - The checklist is signed off.

---

## Definition of Done
- [ ] Migration reviewed and reversible, with one Alembic head (or the slice states that there is no migration).
- [ ] Rules live in the owning bounded context; other contexts are accessed only through ports.
- [ ] Auth, verified-email check, ownership (404 on foreign IDs), admin boundary, CSRF and rate limits applied.
- [ ] Money in integer cents; UTC timestamps; the server computes every price and status.
- [ ] Audit, notification and outbox side effects are written in the same transaction as the change.
- [ ] Every background job the feature needs is registered, idempotent and tested.
- [ ] Unit tests for rules, PostgreSQL integration tests for constraints, API tests for errors and IDOR, and a concurrency test for every known race.
- [ ] Each "Done when" statement is covered by a test; `ruff`, `mypy --strict` and `pytest` are green in CI.
- [ ] Docs and OpenAPI updated; the slice's **Status** in this file set to Done.

## Rules
- One PR per slice. A migration may merge first in its own small PR, and only one person holds the migration lock at a time (`CONTRIBUTING.md`).
- No layer-first work: never "all models", "all routes" or "tests later".
- Add a shared component (port, adapter, job framework) only when the first real feature needs it, then reuse it.
- A slice never depends on unmerged work, and `main` stays deployable after every merge.
