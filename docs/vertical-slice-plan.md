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
| VS-020 | Staging environment and deploy pipeline | VS-015 | Not started |
| VS-021 | Production email delivery | VS-020 | Not started |
| VS-022 | Mixed cart | VS-013 | Not started |
| VS-023 | Checkout and verified payment for digital orders | VS-022, VS-008, VS-007 | Not started |
| VS-023b | STL delivery queue and mark-as-sent | VS-023 | Not started |
| VS-024 | Payment recovery: reconciliation, stale checkouts, manual confirm | VS-023 | Not started |
| VS-025 | Customer order history | VS-023 | Not started |
| VS-026 | Address book | VS-008 | Not started |
| VS-027 | Shipping zones | — | Removed (ADR-024) |
| VS-028 | Physical checkout: delivery, pickup, payment method, dispatch estimate | VS-023, VS-026 | Not started |
| VS-029 | Admin order queue, fulfillment and cash handover | VS-028, VS-023b | Not started |
| VS-030 | Refunds and settlement | VS-029 | Not started |
| VS-031 | Cancellation and returns | VS-030 | Not started |
| VS-032 | Live online payment provider | VS-020, VS-024, VS-030 | Not started |
| VS-033 | Contact form and captcha | VS-005 | Not started |
| VS-029b | Receipt confirmation and problem report | VS-029, VS-033 | Not started |
| VS-034 | Bring Your Idea submission | VS-014, VS-033 | Not started |
| VS-035 | Bring Your Idea pipeline and funnel | VS-034, VS-020 | Not started |
| VS-036 | Reviews and Verified Purchase badge | VS-015, VS-028, VS-030 | Not started |
| VS-037 | Review moderation | VS-036 | Not started |
| VS-038 | Wishlist and wishlist analytics | VS-013 | Not started |
| VS-039 | Offer submission and inactivity expiry | VS-023, VS-007 | Not started |
| VS-040 | Offer counter, accept, reject, withdraw | VS-039 | Not started |
| VS-041 | Accepted-offer checkout and auto-close | VS-040, VS-023, VS-024 | Not started |
| VS-042 | Download statistics rollup | — | Removed (ADR-019) |
| VS-043 | Business analytics | VS-029, VS-030, VS-036, VS-039 | Not started |
| VS-044 | Customer data export | VS-023b, VS-025, VS-026, VS-036, VS-039 | Not started |
| VS-045 | Account deletion by anonymisation | VS-026, VS-031, VS-036, VS-038, VS-039 | Not started |
| VS-046 | Security data retention and IP-salt rotation | VS-004 | Not started |
| VS-047 | Backups, restore drill and monitoring | VS-020 | Not started |
| VS-048 | Launch readiness | VS-011 – VS-047 | Not started |

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
  - A used token returns 400 and an expired one 410.
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
**Was:** downloads through nginx `X-Accel-Redirect`. Its nginx service and client-IP fix move to VS-020; its internal-location pattern is first built by VS-035.

## VS-020 — Staging environment and deploy pipeline
**Status:** Not started
**Depends on:** VS-015
**Goal:** Any `main` build can be deployed to a production-shaped staging host with a health gate, and rolled back in one command.
- **Model / migration:** None. `alembic upgrade head` becomes a deploy step.
- **Endpoints / jobs:**
  - CI builds and pushes an image tagged with the commit SHA.
  - A deploy job gates on `/health/ready` and rolls back automatically on failure.
- **Logic:**
  - Adds the nginx service in front of `api` (moved from the removed VS-019).
  - Fixes client IPs behind the proxy: uvicorn runs with `--proxy-headers` and `--forwarded-allow-ips` limited to nginx. Otherwise the rate limiter, login throttle and IP hashes would all see nginx's IP.
  - Production Compose: nginx with TLS and automatic renewal, HSTS/CSP/security headers, body-size limits, and an allowlisted webhook location.
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
**Status:** Not started
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
**Status:** Not started
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

## VS-023 — Checkout and verified payment for digital orders
**Status:** Not started
**Depends on:** VS-022, VS-008, VS-007
**Goal:** A customer buys an STL end to end on the mock provider, and the line enters the STL delivery queue (`awaiting_delivery`) only after independent server-side verification.
- **Model / migration:**
  - `orders`, `order_items`, `order_status_history`, `payments`, `webhook_events`, `idempotency_records`, created with their full frozen columns, including the physical/delivery columns VS-028 and VS-029 will use: `orders.payment_method` (new `payment_method` enum `online`/`cash`), `orders.contact_phone_snapshot` (E.164), `orders.cash_terms_accepted_at`, `order_items.payment_method`, `order_items.cancel_reason` (new enum `refused`/`no_show`/`other`), `order_items.receipt_confirmed_at` and `problem_reported_at`, `payments.order_payment_method`, `payments.recorded_by`. No shipping, zone or shipping-refund columns (ADR-024).
  - Cash integrity in the database (INV-21, INV-22): `UNIQUE (orders.id, payment_method)`; composite foreign keys `order_items (order_id, payment_method)` and `payments (order_id, order_payment_method)` to it; CHECKs that a cash line is physical and that `provider = 'cash'` exactly when `order_payment_method = 'cash'`; a partial unique index `payments(order_id) WHERE provider = 'cash'`; a cash payment is `paid`-family, above zero and has `recorded_by`.
  - Constraints: one live payment per order (`UNIQUE(order_id) WHERE status NOT IN ('failed', 'expired')`, so a paid or refunded order never gets a second); unique `(provider, event_id)`; `UNIQUE NULLS NOT DISTINCT (scope, user_id, key)`.
  - `payment_provider` is created with `mock` and `cash`; real provider values are added by VS-032 once §30.4 is decided. The provider of each attempt is stored on its payment row.
  - STL ownership (ADR-019, database-design §8.4): `order_items.user_id` and the partial unique index `(user_id, product_id) WHERE product_type = 'stl' AND fulfillment_status IN ('pending', 'awaiting_delivery', 'delivered')`; `orders.customer_email_snapshot`.
- **Endpoints / jobs:**
  - `POST /api/v1/checkout` (requires an `Idempotency-Key` header; optional `payment_provider`, required when more than one online provider is configured) and `POST /api/v1/webhooks/payments/{provider}` (provider-neutral, ADR-024).
  - A verification arq job.
  - New `purge_expired_idempotency_records` job (daily).
- **Logic:**
  - Reuses `SettingsReader` (VS-007), `create_notification` (VS-008) and the outbox (VS-002).
  - Adds the "STL already owned" check: the cart (VS-022) refuses an owned STL with 409 `PRODUCT_ALREADY_OWNED`; checkout silently drops an STL acquired since it was added (SRS §7.3 step 5); and an ownership-index violation during checkout (the STL is in another live order) gives 409 `PRODUCT_ALREADY_OWNED`.
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
  - A failed or expired attempt leaves the order `pending_payment`, so it can be retried (BR-058, VS-024). The order becomes `cancelled` only once its checkout hold is released (`orders.cancelled_at` set by `release_stale_checkouts`). This narrows SRS §20.2's "payment failed or expired → cancelled".
  - Carts with physical lines return 422 `INVALID_FULFILLMENT` until VS-028.
  - Settings validation refuses to start the API and the worker when `ENVIRONMENT=production` and `mock` is among the configured payment providers.
- **Tests:**
  - Parallel double checkout.
  - Same key with a different body gives 409.
  - The kill switch blocks new checkouts but not in-flight payments.
  - A forged callback changes nothing; an underpayment is never marked paid.
  - A duplicate webhook applies the payment once.
  - Two parallel checkouts of one STL by one customer: one order, one 409 `PRODUCT_ALREADY_OWNED`.
  - An owned STL cannot be added to the cart (409).
  - A failure leaves the cart intact.
  - A provider-reported failure leaves the order `pending_payment`.
  - Startup fails with `ENVIRONMENT=production` and `mock` configured.
  - A webhook to `/payments/cash`, to an unconfigured provider, or to `/payments/mock` in production gives 404 and stores nothing.
  - A webhook event whose provider differs from its payment's provider changes nothing.
  - The database refuses an STL line on a cash order, a cash payment on an online order, an online payment on a cash order, and a second cash payment on one order.
  - Every branch of `derive_order_status` (unit).
  - Full end-to-end: register → buy → line `awaiting_delivery`.
- **Done when:**
  - `paid` is reachable only through verification.
  - One checkout per idempotency key.
  - A paid STL line is `awaiting_delivery`, ready for VS-023b's queue.

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

    The retry may name a configured `payment_provider` (default: the previous attempt's); it is stored on the new payment row. The provider is called after commit. The kill switch does not block a retry, because the order already exists.
  - Retry, reconciliation and stale-checkout release apply to online orders only. A cash order (VS-028) has no payment row until its handover, so none of them can select it; retry on a cash order gives 409 `INVALID_STATE_TRANSITION` (ADR-024).
  - Reconciliation queries the provider, outside any lock, for attempts stuck in `pending` or `processing`. A `failed` or `expired` result marks that attempt so, which frees the order for a retry.
  - `release_stale_checkouts` finds `pending_payment` orders whose `placed_at + checkout_hold_period` has passed. It queries the provider first; a paid result is applied instead. Otherwise, under the ADR-024 lock order (`orders`, then lines by `id`, then `payments`), it expires any live attempt, sets `orders.cancelled_at`, moves the order's lines to `cancelled` (which frees the STL ownership index; an unpaid online order's physical lines can only be `pending`, because BR-148 blocks every transition until payment), and recomputes the status to `cancelled`.
  - Manual confirm is allowed only for an online payment when the provider has no status API, and the amount must equal the total. Cash is recorded by VS-029's handover, never here.
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
- **Done when:**
  - A customer retries a failed or expired attempt on the same order, and never has two live attempts on it.
  - An order is cancelled only when its checkout hold ends unpaid.
  - No payment stays stuck without an alert.

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
  - Each order shows its payment method and the derived `payment_due` and `can_cancel` flags; a physical line in `in_production` is shown as `pending` ("Received"), and the customer's status history omits `in_production` entries, because "start printing" is internal (ADR-024). VS-029 tests the masking once physical lines can move.
- **Tests:**
  - Another user's order gives 404.
  - Snapshots survive product edits.
  - The internal note never appears.
  - Pagination is stable.
- **Done when:** A customer sees exactly what they bought, at the price they paid.

## VS-026 — Address book
**Status:** Not started
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
**Depends on:** VS-023, VS-026
**Goal:** A customer checks out physical and mixed carts with courier delivery or free workshop pickup, pays online or (physical-only orders) in cash on delivery or at pickup, and sees an honest estimated ready date.
- **Model / migration:**
  - No order columns (they come from VS-023).
  - Seeds three settings (ADR-024): `cash_payment_enabled` (boolean, `true`, public), `cash_max_open_orders` (integer, `1`, range 1–10), `cash_max_order_total` (money, `10000` cents USD, public).
  - Deletes the obsolete seeded `free_shipping_threshold` setting (VS-007) with its registry entry and public-allowlist slot, as VS-023b does for `daily_download_cap`.
  - `cash_payment_blocks` (Ordering): `user_id`, `contact_phone` (E.164), `order_id`, `reason` (`refused`/`no_show`), `created_at`, `cleared_at`, `cleared_by`; partial indexes on `user_id` and on `contact_phone` `WHERE cleared_at IS NULL`. VS-031 inserts blocks; VS-029 lists and clears them.
  - The open-cash-order count reads `orders` by `user_id` and by `contact_phone_snapshot`; add an index for the phone lookup on unpaid cash orders if `EXPLAIN` shows the need.
- **Endpoints / jobs:** `POST /api/v1/checkout` accepts `fulfillment_method`, `address_id`, `contact_phone` (pickup only), `payment_method`, `payment_provider` (online, when more than one is configured) and a note.
- **Logic:**
  - Reuses the checkout transaction from VS-023, addresses from VS-026, and `SettingsReader` (VS-007).
  - Enforces the SRS §7.4 matrix; a mismatch gives 422 `INVALID_FULFILLMENT`.
  - Snapshots the address, the contact phone normalised to E.164 (the address's phone for delivery, the entered Lebanese phone for pickup), the payment method, lead time and batch size.
  - Totals are recomputed first (`subtotal + tax`; no shipping). Cash rules are then checked against the **recomputed** total, under the cart lock (which serialises one customer's checkouts) and a transaction-scoped advisory lock on the normalised phone (which serialises checkouts from different accounts sharing it):
    - every line physical, `cash_payment_enabled` on, and no uncleared `cash_payment_blocks` row for the customer or the phone, otherwise 422 `PAYMENT_METHOD_NOT_ALLOWED`;
    - fewer than `cash_max_open_orders` unpaid, uncancelled cash orders for the customer or the phone, and a total of at most `cash_max_order_total`, otherwise 422 `CASH_PAYMENT_LIMIT_REACHED`.
  - An online order with an unconfigured `payment_provider` gives 422 `PAYMENT_METHOD_NOT_ALLOWED`; the chosen provider is stored on the pending payment row.
  - A cash order is created with **no payment row** and no provider call; its status derives to `in_progress`; consent records the cash terms; the confirmation email states the amount due in cash on delivery (or at pickup).
  - Every delivery-order response and email says "delivery fee paid to the courier on delivery".
  - Dispatch days = max over lines of (lead time × ceil(quantity ÷ batch size)), counted from placement for both payment methods.
  - After an online payment, or at placement of a cash order, physical lines stay `pending` (eligible for production).
- **Tests:**
  - Table test over all five §7.4 rows, crossed with both payment methods (cash refused for STL-only and mixed carts).
  - 10 units with lead time 2 and batch size 4 gives 6 days.
  - Cash limits: switch off, blocked customer, blocked phone on another account, a second open cash order for the same customer, a second open cash order on another account with the same phone, a total one cent over the cap — each refused with nothing created.
  - A cart whose snapshot total is under the cap but whose recomputed total is one cent over is refused for cash.
  - Two accounts sharing a normalised phone check out cash in parallel with `cash_max_open_orders = 1`: one order, one 422.
  - The same `Idempotency-Key` with only `payment_method` changed gives 409 `IDEMPOTENCY_KEY_CONFLICT`.
  - A cash order is never selected by `release_stale_checkouts`, reconciliation or retry.
  - Snapshots survive later edits; the phone is stored normalised.
  - In a mixed order the STL line is `awaiting_delivery` and the physical lines stay pending.
  - `free_shipping_threshold` is gone from the settings table, the registry and `GET /settings/public`.
- **Done when:**
  - Every cart type checks out with correct totals and the right payment methods.
  - No order carries a shipping amount, and snapshots are immutable.
  - The cash limits hold across accounts that share a phone.

## VS-029 — Admin order queue, fulfillment and cash handover
**Status:** Not started
**Depends on:** VS-028, VS-023b
**Goal:** The administrator moves each physical line of a cash order or a paid online order from received to delivered or picked up, records the cash for a cash order at handover, and the customer is told at each visible step.
- **Model / migration:** A partial index for the cash-due filter on unpaid cash orders, shaped by `EXPLAIN`; other queue indexes only if `EXPLAIN` shows the need.
- **Endpoints / jobs:**
  - `GET /api/v1/admin/orders` (filters include `payment_method` and `payment_due`), `GET/PATCH /api/v1/admin/orders/{id}` (`PATCH` edits the internal note only). The fulfilment queue never lists `pending_payment` orders.
  - `POST …/items/{item_id}/transition` (created by VS-023b for STL lines; this slice adds the physical edges).
  - `POST /api/v1/admin/orders/{id}/cash-handover` (body: `amount_cents`).
  - `GET /api/v1/admin/cash-blocks` (filters: customer, phone, active) and `POST /api/v1/admin/cash-blocks/{block_id}/clear` (audited).
- **Logic:**
  - Reuses `derive_order_status`, the outbox, `create_notification` and `AuditWriter`.
  - Pure transition tables (ADR-024):
    - delivery: `pending → in_production → ready_to_ship → shipped → delivered`;
    - pickup: `pending → in_production → ready_for_pickup → picked_up`.
  - **No physical work on an unpaid online order (BR-148):** every physical transition requires the order to be a cash order or to have a `paid` online payment, otherwise 409 `INVALID_STATE_TRANSITION`.
  - **Lock order (ADR-024):** every transition locks the `orders` row first, then the line, then recomputes the status, and writes history, audit, email and notification in the same transaction.
  - `in_production` ("start printing") sends no email or notification, and is hidden from the customer's status history. Emails and notifications: finished (`ready_to_ship`), shipped, ready for pickup (with the pickup address and hours), delivered or picked up. Delivery emails say "delivery fee paid to the courier on delivery".
  - On a cash order the transition endpoint refuses `→ delivered` and `→ picked_up` with 409 `INVALID_STATE_TRANSITION`; only the handover reaches them.
  - **Cash handover** (SRS §9.8), in one transaction:
    - locks the `orders` row, then all its lines by `id`;
    - requires at least one live line, and every live line `shipped` (delivery) or `ready_for_pickup` (pickup), otherwise 409 `INVALID_STATE_TRANSITION`;
    - requires `amount_cents` to equal the sum of live line totals and to be above zero, otherwise 422 `CASH_AMOUNT_MISMATCH`;
    - marks them all delivered / picked up and inserts one `payments` row (`provider = 'cash'`, `status = 'paid'`, `recorded_by`, `verified_at`); the unique cash-payment index is the final guard;
    - recomputes the status and writes history, audit, notification and the email with the cash receipt.
  - The delivered / picked-up email's "I got it" and "Report a problem" buttons link to the order page; VS-029b adds the actions.
  - Clearing a cash block sets `cleared_at` and `cleared_by`; clearing an already-cleared block is a no-op 200.
- **Tests:**
  - Every legal and illegal edge, per fulfillment method and payment method.
  - "Start printing" (or any physical transition) on a `pending_payment` online order gives 409, and the order never appears in the fulfilment queue.
  - `in_production` produces no email and no notification, appears as `pending` to the customer, and is absent from the customer's status history; `can_cancel` turns false when printing starts.
  - Two admins acting on the same state: one wins.
  - Cash handover: a wrong amount gives 422 with nothing changed; a line not yet shipped gives 409; an order with no live line gives 409; two admins recording one handover give one payment, one audit row and one email; a handover racing a transition on another line of the same order ends with one winner and no deadlock.
  - A cash order reaches `completed` through the handover, and its payment is `paid` for exactly the live line total.
  - Cash blocks: a customer gets 404 on both routes; clearing writes an audit row; a second clear is idempotent; after clearing, checkout offers cash again for that customer and phone.
  - An email-provider outage does not block a transition.
  - The internal note is never visible to the customer.
- **Done when:**
  - No route sets `order.status` directly, and no route but the handover creates a cash payment.
  - No physical line of an unpaid online order ever moves.
  - A physical order reaches `completed` with either payment method.

## VS-030 — Refunds and settlement
**Status:** Not started
**Depends on:** VS-029
**Goal:** The administrator refunds any subset of paid lines, and each refund stays in a queue until actually settled.
- **Model / migration:** `refunds` and `refund_items`, with non-negative money checks and a pending-obligation index. No shipping component (ADR-024).
- **Endpoints / jobs:** `POST /api/v1/admin/orders/{id}/refunds` (requires an `Idempotency-Key` header), `GET /api/v1/admin/refunds`, `GET /api/v1/admin/refunds/{id}`, `POST …/{id}/settle`.
- **Logic:**
  - Reuses the idempotency service from VS-023.
  - **Lock order (ADR-024):** the `orders` row, then the refunded lines by `id`, then the payment; balances are derived under those locks.
  - **Paid lines only (BR-149):** a line is refundable only if it is a paid line. Its refundable amount is `line_total − already refunded on it`; a cancelled line of a cash order has 0. A request over any line's balance or the payment's balance gives 422 `REFUND_EXCEEDS_AVAILABLE`.
  - A refunded STL line becomes `refunded`: one still `awaiting_delivery` leaves the delivery queue; one already delivered cannot be recalled (ADR-019). A refunded physical terminal line becomes `refunded`.
  - The payment and order statuses are recomputed; refunds covering all paid money make the order `refunded`.
  - The method is `provider` when the adapter supports refunds, otherwise `manual`. A cash payment is always `manual`, up to the cash recorded.
  - Sends a "refund issued" email.
- **Tests:**
  - Concurrent partial refunds never exceed the paid amount, on an online and on a cash payment.
  - Two concurrent partial refunds that together equal the full paid amount both succeed, and the order becomes `refunded`.
  - Idempotent replay.
  - A refunded STL line awaiting delivery disappears from the delivery queue.
  - A refund racing mark-delivered on one STL line: exactly one wins.
  - A customer whose STL line was refunded can buy it again.
  - An unpaid order gives 409, including an unpaid cash order.
  - A refund item on a cancelled line of a paid cash order gives 422.
  - A refund on a cash order after handover is `manual` and capped at the cash recorded.
  - Mixed orders (SRS mandatory coverage), each asserting line states, refundable balances and the order status:
    - STL line refunded while the physical line is delivered → `partially_refunded`;
    - physical line refunded after delivery while the STL line is `awaiting_delivery` → `partially_refunded`, STL still in the queue;
    - both lines refunded across two separate refunds → `refunded`;
    - a manual refund after a cancellation-created refund (VS-031 fixture), at exactly the remaining balance (succeeds) and at one cent over (422).
- **Done when:**
  - A refund cannot exceed any line's or the payment's balance, and never touches an unpaid line.
  - A pending refund stays in the queue until settled.

## VS-031 — Cancellation and returns
**Status:** Not started
**Depends on:** VS-030
**Goal:** A customer cancels before printing starts, the administrator cancels at any legal point, a returned item is re-shipped, reprinted, refunded or (unpaid cash) cancelled, and a whole-order cash refusal blocks cash for that customer and phone.
- **Model / migration:** None (`order_items.cancel_reason` comes from VS-023, `cash_payment_blocks` from VS-028).
- **Endpoints / jobs:** `POST /api/v1/me/orders/{id}/cancel`, `POST /api/v1/admin/orders/{id}/cancel`; the transition endpoint gains the `returned` and no-show edges. Admin cancels from `returned` or `ready_for_pickup` require `cancel_reason` (`refused`, `no_show`, `other`).
- **Logic:**
  - Reuses the transitions from VS-029 and refund creation from VS-030.
  - **Lock order (ADR-024):** every cancel locks the `orders` row, then all physical lines by `id`, then checks and changes them, creates any refund, and recomputes the status.
  - Customer cancel requires every physical line to be `pending`, otherwise 409 `ORDER_NOT_CANCELLABLE` with no partial change. It works for paid online orders and unpaid cash orders.
  - Admin cancel covers `pending`, `in_production`, `ready_to_ship` and `ready_for_pickup` lines (the last is a pickup no-show).
  - Every cancellation of a paid line creates a pending refund in the same transaction; cancelling an unpaid cash line creates none.
  - STL lines are never cancelled.
  - `returned → shipped | in_production | refunded` (paid line) `| cancelled` (unpaid cash line only; `refused` or `other`).
  - `no_show` is valid only from `ready_for_pickup`, `refused` only from `returned`.
  - **Cash block (BR-144):** a `refused` or `no_show` cancel that leaves a cash order with no live line inserts a `cash_payment_blocks` row for the customer and the order's contact phone, in the same transaction. A refusal of only some lines, and any `other` cancel, never blocks. An online order never blocks.
  - A cancellation that leaves a cash order with lines still live sends the "order cancelled" email with the new amount due.
- **Tests:**
  - A customer cancel racing "start printing" has exactly one winner (repeated 100 times), including on a two-line order where printing starts on the line the cancel checks last.
  - A cash handover racing an admin cancel on another line of the same order: one winner, no deadlock.
  - Two concurrent line changes on one order (cancels of both remaining lines) leave the order status correct: an all-cancelled cash order is `cancelled`, leaves the cash-due view and stops counting toward `cash_max_open_orders`.
  - Illegal edges: `returned → cancelled` on a paid online line, `returned → refunded` on an unpaid cash line, `no_show` from `returned` — each 409.
  - `ready_for_pickup → cancelled`: on a cash order with `no_show` it blocks; on an online order it creates a refund and never blocks.
  - STL lines are unaffected.
  - Cash refusal end to end: cash order → shipped → returned → cancelled (`refused`), no refund, order `cancelled`, and the next checkout by that customer, or by another account with the same phone, offers online only.
  - A partly refused cash order: one line cancelled (`refused`), the handover records the rest, no block, and the refused line earns no revenue and no badge.
  - An `other` cancel of a whole cash order never blocks.
  - **Mandatory end-to-end (SRS §5.6):** mixed order → paid online → admin cancels the physical line in production → partial refund of that line → STL line still delivered or awaiting delivery → order `partially_refunded` → refund pending until settled.
  - Mixed: physical line cancelled (cancellation refund) and then the STL line refunded → `refunded`.
  - Mixed: an STL refund racing a cancellation of the physical line on the same order → both commit in turn, and the final status reflects both.
- **Done when:**
  - The SRS §5.6 end-to-end test passes.
  - The cancel-versus-start-printing race always has one winner, with no deadlock.
  - An unpaid cash line is never refunded, and only a whole-order refusal or no-show blocks cash.

## VS-032 — Live online payment provider
**Status:** Not started
**Depends on:** VS-020, VS-024, VS-030 (and the SRS §30.4 provider decision and merchant credentials)
**Goal:** Real online revenue: configuring the chosen provider(s) runs the same checkout, verification, recovery and refund flows against them.
- **Model / migration:** Adds the chosen provider value(s) to `payment_provider`; provider metadata only if needed.
- **Endpoints / jobs:** None new; the provider-neutral webhook route from VS-023 is IP-allowlisted in VS-020's nginx.
- **Logic:**
  - Reuses the payment port from VS-023.
  - Replaces the single `payment_provider` setting with a list of configured online providers, and renames the Whish-specific settings in `src/app/core/config.py` and `.env.example` (`whish_*`, `whish_webhook_ips`) to per-provider names. If §30.4 chooses both, checkout and retry let the customer pick one, stored on the payment row (VS-023, VS-024).
  - The adapter implements create-payment and redirect, signature check (if offered), status query (if not offered, manual confirmation from VS-024 stays on) and refund (if not offered, settlement is `manual`). A card gateway uses a hosted or redirect page so card data never reaches the platform.
  - Chargebacks are recorded as a refund with reason `chargeback`, which marks affected STL lines `refunded`.
  - Record the decision and the provider's answers to SRS §30.1 in an ADR.
- **Tests:** The same contract fixtures as the mock (paid, underpaid, failed, bad signature, duplicate, timeout), run against the provider's sandbox; an end-to-end payment on staging.
- **Done when:**
  - Every fixture passes against the sandbox.
  - No checkout, order or cash-handover code changed.

## VS-033 — Contact form and captcha
**Status:** Not started
**Depends on:** VS-005
**Goal:** A visitor messages the business without an account, and the administrator works through a message queue.
- **Model / migration:** `contact_messages` (status `new`, `read`, `replied` or `archived`).
- **Endpoints / jobs:** `POST /api/v1/contact-messages`, `GET /api/v1/admin/contact-messages`, `GET/PATCH /api/v1/admin/contact-messages/{id}`.
- **Logic:**
  - Reuses the rate limiter (VS-002) and `AuditWriter`.
  - New `CaptchaPort` with a fake adapter and one real provider adapter.
  - Captcha is checked, then per-IP and per-email limits, then the row is inserted.
  - Admin status changes take a row lock and are audited.
  - Message bodies are never logged.
- **Tests:**
  - A bad captcha stores nothing.
  - A rate-limit breach gives 429.
  - The queue is admin-only.
  - Status changes are audited.
- **Done when:** Only captcha-verified, rate-limited messages reach the queue.

## VS-029b — Receipt confirmation and problem report
**Status:** Not started
**Depends on:** VS-029, VS-033
**Goal:** After delivery or pickup a customer can say "I got it" or report a problem, and the administrator sees it on the order, without either being required.
- **Model / migration:** None (`order_items.receipt_confirmed_at` and `problem_reported_at` come from VS-023); a nullable `contact_messages.order_id` if VS-033 did not add it.
- **Endpoints / jobs:** `POST /api/v1/me/orders/{id}/confirm-receipt` and `POST /api/v1/me/orders/{id}/report-problem` (body: message).
- **Logic:**
  - Owner-only, verified, CSRF-protected POSTs from the order page. The email buttons only open that page: nothing changes state on a GET, because email scanners follow links.
  - Confirm sets `receipt_confirmed_at` on the order's `delivered` / `picked_up` lines that lack it; idempotent; no state change and no effect on the order status.
  - Report creates a contact message linked to the order in the VS-033 queue (no captcha, as the caller is signed in; rate-limited) and sets `problem_reported_at`. Resolution uses the existing return, refund and cancel tools.
- **Tests:**
  - Another customer's order gives 404; an order with no delivered line gives 409.
  - Confirming twice changes nothing the second time.
  - An order completes without confirmation.
- **Done when:** Receipt confirmation and problem reports are recorded on the order and never block completion.

## VS-034 — Bring Your Idea submission
**Status:** Not started
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

## VS-035 — Bring Your Idea pipeline and funnel
**Status:** Not started
**Depends on:** VS-034, VS-020
**Goal:** The administrator works each lead through the pipeline, records the quote and outcome, and measures conversion.
- **Model / migration:** None.
- **Endpoints / jobs:** `GET /api/v1/admin/custom-requests`, `GET/PATCH /api/v1/admin/custom-requests/{id}`, `POST …/{id}/transition`, `GET …/{id}/attachments/{attachment_id}/download`, `GET /api/v1/admin/analytics/custom-requests/funnel`.
- **Logic:**
  - Adds an nginx `internal` location on `uploads_private` (the first protected-file location since VS-019 was removed), served with `X-Accel-Redirect` after the admin check.
  - Pipeline: `new → contacted → quoted → in_progress → completed → closed`, with `lost` reachable from `contacted` or `quoted`.
  - `quoted` requires an amount in cents.
  - The funnel counts submissions by cohort (submission date).
- **Tests:**
  - Legal and illegal transitions.
  - Two admins racing on one lead.
  - An expired attachment cannot be downloaded.
  - Funnel counts match seeded data.
- **Done when:** Every lead follows the state machine, and the funnel shows won and lost counts.

## VS-036 — Reviews and Verified Purchase badge
**Status:** Not started
**Depends on:** VS-015, VS-028, VS-030
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
**Status:** Not started
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
**Depends on:** VS-029, VS-030, VS-036, VS-039
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
**Status:** Not started
**Depends on:** VS-004
**Goal:** Expired security records stop accumulating, and old IP hashes can no longer be linked to new ones.
- **Model / migration:** A small `ip_hash_salts` table (versioned salts; exactly one current) replacing the static `IP_HASH_SALT` for new hashes.
- **Endpoints / jobs:** New `purge_expired_security_records` job (daily: expired verification and reset tokens, expired or revoked sessions past retention) and new `rotate_ip_salt` job (monthly).
- **Logic:** `core.security.hash_ip` reads the current salt; rotating inserts a new salt. The purge deletes only rows past their retention.
- **Tests:**
  - After rotation, the same IP produces a new hash, and audit and session writes keep working.
  - The purge is idempotent and never touches live tokens or sessions.
- **Done when:** Both jobs run on schedule and are safe to run twice.

## VS-047 — Backups, restore drill and monitoring
**Status:** Not started
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
**Status:** Not started
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
