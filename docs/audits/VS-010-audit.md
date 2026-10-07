# VS-010 audit: categories, materials and colours

Independent, read-only audit. Auditor date: 2026-10-01. Tree audited: branch `docs/vs002-frontend-contract` @ `2cd8cda` (clean). No source, test or status file was changed. Mutation experiments ran only on a scratch copy (`git archive HEAD`) outside the repo.

## 1. Verdict

**Yes, with minor gaps.** Every VS-010 behaviour I checked works on real PostgreSQL, and every "Done when" line has a test. The gaps are in how strong the tests are. Four realistic regressions leave the whole suite green: dropping the material/colour row lock, dropping the PATCH slug-conflict translation, dropping the archived guard on materials/colours, and dropping material/colour audit writes (A-01 to A-04). Close those before treating this suite as a regression net for VS-013, which reuses these patterns.

## 2. Repo state (Step 1)

| Item | Finding |
|---|---|
| Current branch | `docs/vs002-frontend-contract`, 1 commit ahead of `main` (`2cd8cda`, which only adds `docs/frontend-contract-vs002.md`) |
| Uncommitted/untracked | None at the start (`git status --short` empty). Afterwards the only untracked file is this report |
| VS-010 in `main`? | Yes. The code landed inside `6f4650c` "Initial commit: VS-001 to VS-010 and new vertical slice plan" (an ancestor of `main`), so there is **no dedicated VS-010 commit or PR** |
| Later commits touching VS-010 | `433bd54` (adds `test_deep_vs010_known_bugs.py`), `b3280bc` (adds migration `5e1c0a7d2b94` on top of `a9c0aec909a9`), `cc0b547` (BUG-03 NUL rejection in `catalog/api/reference_data.py` and `schemas.py`) |

## 3. Command results (Step 2)

| Tool | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 324 files already formatted |
| `mypy src tests` (strict, as CI runs it) | PASS | 276 files, no issues; `mypy src`: 154 files, no issues |
| `pytest` (full) | PASS | **1267 passed, 5 deselected (`timing`, by addopts), 10 xfailed, 0 failed, 0 skipped**, 14 min 48 s |
| `pytest -m integration` | PASS | 941 passed, 333 deselected, 8 xfailed |
| `pytest -m concurrency` | PASS | 54 passed, 1228 deselected |
| `alembic heads` | PASS | Exactly one head: **`5e1c0a7d2b94`**. `a9c0aec909a9` is no longer head; `5e1c0a7d2b94` (audit_logs `clock_timestamp()`) revises it |
| upgrade → downgrade → upgrade on dev Postgres (localhost:5442) | PASS | Start `a9c0aec909a9` → `upgrade head` (→`5e1c0a7d2b94`) → `downgrade ac29d4c2170c` (all three tables and `ix_categories_live_slug` gone) → `upgrade head` → **ends at `5e1c0a7d2b94` (head)**; index re-created as `CREATE UNIQUE INDEX ix_categories_live_slug ON public.categories USING btree (slug) WHERE (deleted_at IS NULL)` |
| `test_every_migration_step_goes_down_and_up_with_data_present` | PASS | Separate container; seeds rows into all three tables |

**xfails (10). None belong to VS-010:**

| Test | Bug | Slice |
|---|---|---|
| `test_admin_users_adversarial.py::test_a_wrong_method_does_not_reveal_that_the_route_exists` | FINDING 2 / BUG-10 | VS-011 (the catalogue admin routes are affected too) |
| `test_deep_vs005_admin_mfa.py::test_anonymous_callers_cannot_tell_real_admin_paths_from_imaginary_ones` | BUG-08 | VS-011 |
| `test_deep_vs005_admin_mfa.py::test_a_customer_cannot_enumerate_admin_routes_with_wrong_methods` | BUG-10 | VS-011 |
| `test_deep_vs005_admin_mfa.py::test_a_trailing_slash_does_not_reveal_admin_routes[customer]` / `[anonymous]` | BUG-29 | VS-011 |
| `test_deep_vs009_admin_users.py::test_the_last_active_administrator_cannot_be_deactivated` | BUG-38 | VS-011 |
| `test_deep_vs009_admin_users.py::test_admin_reads_of_account_pii_are_audited`, `::test_an_admin_email_search_never_reaches_the_server_log` | BUG-39 | VS-012 |
| `test_deep_architecture.py::test_no_context_imports_another_contexts_infrastructure` | BUG-41 | VS-012 (names Catalog's import of `identity.infrastructure.session_tokens`) |
| `test_deep_architecture.py::test_the_application_layer_depends_on_the_domain_only` | BUG-41 | VS-012 (includes `catalog/application/commands/category_admin.py:61`) |

**Mutation results.** The VS-010 target set is `tests/integration/catalog/*` minus the rate-limit file, plus `tests/unit/catalog`, `test_category_slug_race.py` and `test_reference_data_mutation_race.py`. Baseline: 95 passed.

| Mutation (scratch copy only) | Result |
|---|---|
| M1 drop `is_active` filter, public categories | RED: `test_categories_expose_only_live_active_rows`, `test_a_disabled_category_can_be_reactivated` |
| M9 drop `is_active` filter, public colours | RED: `test_colours_expose_only_live_active_rows` |
| M2 drop `.limit()` on public materials | RED: `test_the_public_list_is_capped` |
| M3 drop `FOR UPDATE`, categories | RED: `test_the_archive_audit_row_records_the_state_it_actually_replaced` (red in 6 of 6 runs) |
| M11 `archive()` stops clearing `is_active` | RED: 7 tests |
| M12 no-op PATCH bumps `updated_at` | RED: `test_a_no_op_patch_is_audited_without_moving_the_timestamp` |
| **M4 drop `FOR UPDATE`, materials and colours** | **GREEN (survives)** |
| **M5 remove IntegrityError→SlugConflictError in `CategoryRepository.save` (PATCH path)** | **GREEN (survives)** |
| **M7 allow PATCH on archived material/colour** | **GREEN (survives)** |
| **M8 allow re-archiving a material/colour** | **GREEN (survives)** |
| **M10 skip the audit write on material create** | **GREEN (survives)** |
| M6 add a `SELECT` slug pre-check before INSERT | GREEN. Expected: a pre-check cannot be detected by behaviour while the index exists. The rule is verified by code search instead |

## 4. Requirement checklist (Step 3)

| Item | Status | Evidence |
|---|---|---|
| `categories`, `materials`, `colours`, each with `is_active` + `deleted_at`, timestamptz | DONE | `a9c0aec909a9_…py:22-94`. `test_reference_schema.py::test_categories_match_the_frozen_design` and `::test_simple_reference_tables_match_the_frozen_design` read `information_schema` from a migrated PG16 |
| Live-slug partial unique index | DONE | `a9c0aec909a9_…py:48-54`. `test_the_live_slug_index_exists_and_is_partial`. psql probe in a rolled-back transaction: a duplicate live slug is refused, and after archiving the slug is re-usable |
| Uniqueness on materials/colours | DONE (matches spec) | No unique constraint beyond the PK (`pg_constraint` shows only `*_pkey`). Matches `database-design.md` §6.2/6.3, which lists none; `test_names_are_not_unique_on_simple_reference_tables`. Tension with SRS §592: see Q-1 |
| Public GET lists return only live rows | DONE | `repositories.py:156, 238, 300` (`deleted_at IS NULL AND is_active`); schemas expose only id/name(/slug) (`schemas.py:50-91`); M1/M9 red. Caveat: A-06 |
| Hard limit 100 | DONE | `reference_data.py:77`, `repositories.py:158/240/302`; `test_the_public_list_is_capped` (M2 red); pinned by `test_v1_contracts.py::test_the_public_reference_hard_cap_is_100` |
| 600 req/hour/IP, one counter per endpoint | DONE | `reference_data.py:85-102`; `test_the_public_lists_are_rate_limited_with_the_standard_contract`, `test_each_reference_endpoint_counts_independently`, `test_the_public_rate_limit_is_600_per_hour` |
| 429 carries `Retry-After` | DONE (code) / PARTIAL (test) | `core/rate_limit.py:50-53`. Asserted only on `/auth/register` (`test_deep_vs002_outbox_and_limits.py:313`), not on a catalogue route: A-08 |
| Admin CRUD behind `require_admin` (anon 401, customer 404, admin w/o MFA 401 `MFA_REQUIRED`) | DONE | `api/v1/admin.py:25,30`. The matrix in `test_deep_vs005_admin_mfa.py:60-81, 118-150` is built from OpenAPI, so it covers all 15 catalogue admin operations. Also `test_admin_reference_data.py:73-116` |
| CSRF on unsafe admin methods | DONE (code) / PARTIAL (test) | `require_csrf` on all 9 unsafe routes; only the category routes are tested (`test_unsafe_methods_require_the_csrf_header`): A-07 |
| Lifecycle live → disabled → archived | PARTIAL | Allowed: live↔disabled (PATCH `is_active`); live/disabled→archived (DELETE). Forbidden: archived→anything (PATCH or DELETE gives 409 `INVALID_STATE_TRANSITION`). Enforced in the **application** layer (`category_admin.py:144-149, 203-204`; `value_admin.py:133-134, 182-183`), **not the domain**: `entities.py:71-81` `archive()` and `apply_update()` accept an archived row. See A-09 |
| Archiving releases the slug | DONE | Partial index; `test_archiving_releases_the_slug_for_another_category`, `test_a_slug_may_be_reused_only_once_at_a_time`, `test_archiving_releases_the_slug_through_the_api` |
| Slug conflict comes from the index, never a SELECT pre-check | DONE | `repositories.py:97-102` (add) and `:190-195` (save) translate `IntegrityError` by constraint name (`:53-78`). A search for any slug predicate in `src/app/catalog` finds none |
| `SlugConflictError` → `409 SLUG_CONFLICT` | DONE (POST) / MISSING test (PATCH) | `reference_data.py:181-188, 322-323, 373-374`. POST: `test_a_duplicate_live_slug_is_a_conflict`. PATCH works (probe: 409 `SLUG_CONFLICT`) but has no test: A-02 |
| Mutations take row locks | DONE (code) / PARTIAL (test) | `repositories.py:147, 229, 291` (`with_for_update` + `populate_existing`). Guarded only for categories (M3 red, M4 green): A-01 |
| `AuditWriter` port in Platform | PARTIAL | `platform/application/services/audit_writer.py`. A concrete class that imports `app.platform.infrastructure.repositories` (`:25`); it is not an interface: A-10 |
| Audit rows in the same transaction, only for successful writes, no PII | DONE | The writer never commits (`audit_writer.py:9-13`); one transaction per request (`api/dependencies.py:7-22`). `test_a_rejected_create_writes_no_audit_row`, `test_a_failed_create_leaves_no_audit_row`. Probe: refused PATCH/DELETE wrote no `*.updated` row. Payload is name/slug/is_active/deleted_at plus a salted `ip_hash` |
| RFC 9457 problem+json, stable codes | DONE | `ApiError` → `api_error_handler` (`api/errors.py:117-125`); codes `SLUG_CONFLICT`, `INVALID_STATE_TRANSITION`, `VALIDATION_ERROR`, `NOT_FOUND`. Nit A-15 |
| "Category in use" guard not built (VS-013) | CONFIRMED absent | `CATEGORY_IN_USE` appears only in docstrings. Not a gap |
| Race test: exactly one success + one `SlugConflictError` below HTTP | DONE | `test_category_slug_race.py:78-122`: two sessions (separate pooled connections), transaction opened before an `asyncio.Barrier`, the loser's INSERT blocks on the index. Caveat A-12 |
| Constraint tests on real PostgreSQL | DONE | `tests/conftest.py:23-47`: testcontainers `postgres:16` + `alembic upgrade head`; no SQLite or mocks anywhere in the catalogue tests |

### "Done when" and FR-04 cases → tests

| Case | Test |
|---|---|
| Only live values are public | `test_{categories,materials,colours}_expose_only_live_active_rows`, `test_archiving_hides_publicly_but_stays_admin_readable`, `test_a_disabled_category_can_be_reactivated` |
| Concurrent identical slugs → one category, `SlugConflictError` below HTTP | `test_two_administrators_claiming_one_slug_produce_exactly_one_category`, `test_a_slug_may_be_reused_only_once_at_a_time` |
| `SlugConflictError` → 409 mapping, tested separately | `test_a_duplicate_live_slug_is_a_conflict` (POST only; PATCH: **no test**) |
| In-use guard not built | n/a (confirmed absent) |
| FR-04 neg: duplicate active slug rejected | as above |
| FR-04 neg: category with products cannot be deleted | deferred to VS-013 (no test, by design) |
| FR-04 neg: no hard delete | `test_archiving_hides_publicly_but_stays_admin_readable` (row still readable after DELETE) |
| FR-04 neg: non-admins cannot access | VS-005 deep matrix (all 15 ops) + `test_a_customer_gets_404_not_403`, `test_an_unauthenticated_caller_is_told_to_authenticate`, `test_an_admin_without_completed_mfa_is_refused` |
| FR-04 conc: simultaneous identical slugs | slug race tests above |
| FR-04 conc: deletion racing product assignment | deferred to VS-013 (no test, by design) |
| FR-04 conc: conflicting admin edits must not silently overwrite (optimistic version) | **no test**, not implemented for reference data: Q-2 |
| FR-04 failure: DB change + audit commit atomically | `test_a_rejected_create_writes_no_audit_row`, `test_a_failed_create_leaves_no_audit_row` (create path only) |
| FR-04: all changes audit-logged | `test_every_mutation_is_audited` (**categories only**; A-04) |

## 5. Definition of Done (Step 4)

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Cycle above; single head `5e1c0a7d2b94`; per-step down/up test passes |
| Rules in owning context; other contexts only via ports | Partly | Domain is pure (`test_the_domain_layer_is_pure` passes; the catalogue domain imports only stdlib). The application layer imports infrastructure (`category_admin.py:61`). The API imports `app.identity.infrastructure.session_tokens` (`reference_data.py:67`); tracked as BUG-41 → VS-012. No cross-context table access in `src/app/catalog` |
| Auth, verified email, 404 on foreign IDs, admin boundary, CSRF, rate limits | Met (code) | Boundary matrix; unknown id → hidden 404 (`test_an_unknown_id_is_a_hidden_404`). Resources are global, so there is no ownership IDOR. CSRF on materials/colours is untested (A-07). The admin rate limit is VS-011 scope |
| Money in cents; UTC timestamps; server computes status | Met / n/a | All timestamps timestamptz; `updated_at` set with `datetime.now(UTC)`; no money |
| Audit/notification/outbox side effects in the same transaction | Met | See checklist |
| Background jobs | n/a | None needed |
| Unit + PG integration + API error/IDOR + a concurrency test for every known race | Partly | The material/colour lock race has no lock-guarding test (A-01) |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Met locally | All green locally. CI status not verified (`gh` is not authenticated; the GitHub MCP failed to connect) |
| Docs and OpenAPI updated; Status Done | Partly | `docs/reference-data.md` matches the code except for slice references (A-05). OpenAPI omits the 409s (A-11). Plan Status is Done; README and CLAUDE.md list VS-010 accurately; CLAUDE.md "Next up: VS-011" is correct |
| Glossary naming | Met | `Category`/`Material`/`Colour` (British spelling), entity types `Category`/`Material`/`Colour`, actions `category.created` etc.; no synonyms |

## 6. Findings

| ID | Sev | Location | What is wrong | Why it matters | Suggested fix (not applied) | Scope |
|---|---|---|---|---|---|---|
| A-01 | Major | `repositories.py:224-233, 286-295`; `test_reference_data_mutation_race.py:361-405` | No test guards the material/colour `FOR UPDATE` (M4 survives). The only material race test is, by its own docstring, a dirty-tracking test; colours have no race test at all | The stale-"before" audit defect the lock prevents (proven for categories by M3) could return unnoticed on 2 of the 3 resources | Parametrise `test_the_archive_audit_row_records_the_state_it_actually_replaced` over material and colour | VS-010 |
| A-02 | Major | `repositories.py:190-195`, `reference_data.py:373-374` | PATCH to a taken slug has no test (M5 survives). Removing the translation would turn it into an unhandled IntegrityError | This is the second of the two write paths the index protects; a regression would surface as a 500/503 on an admin write | HTTP test: PATCH category B to category A's slug (and to its uppercase form) → 409 `SLUG_CONFLICT`, no `category.updated` audit row | VS-010 |
| A-03 | Major | `value_admin.py:133-134, 182-183` | The archived guard for materials/colours is untested (M7 and M8 survive). `test_an_archived_category_cannot_be_mutated` covers categories only | Archiving is documented as terminal; a regression would allow editing or re-archiving archived values, writing false audit history | Parametrise the archived-mutation test over `/materials` and `/colours` | VS-010 |
| A-04 | Major | `value_admin.py:90-100, 145-154, 188-197`; `test_admin_reference_data.py:394-410` | Material/colour audit writes are never asserted (M10 survives). `test_every_mutation_is_audited` covers categories only | BR-132 / FR-04 require every admin change to be audit-logged | Parametrise the audit test over all three resources and assert action + entity_type | VS-010 |
| A-05 | Minor | `docs/reference-data.md:217-236`; `category_admin.py:35-47,198`; `value_admin.py:22`; migration `a9c0…:100`; `test_reference_schema.py:126` | These say **VS-011** owns products and the `CATEGORY_IN_USE` guard; the slice plan assigns both to **VS-013** (VS-011 is admin hardening) | Misleads whoever implements the guard | Replace VS-011 with VS-013 in these comments and docs | VS-010 (docs) |
| A-06 | Minor | `test_public_reference_lists.py:98-135, 204-215`; `test_admin_reference_data.py:335-359, 547-559` | The tests share one DB and one 100-row cap. **Demonstrated:** running `test_the_public_list_is_capped` before `test_materials_expose_only_live_active_rows` makes the latter FAIL. In that order the material `not in public` assertion in `test_simple_values_round_trip_through_their_lifecycle` passes vacuously | Current file order hides it; any reorder, `-k` selection or new test can make the negative assertions pass vacuously or fail spuriously | Seed names that sort first (e.g. a `"!"`/`"0"` prefix), or delete seeded rows in teardown, or assert on a per-test namespace below the cap | VS-010 (tests) |
| A-07 | Minor | `reference_data.py:436,477,511,558,599,633`; `test_admin_reference_data.py:119-135` | CSRF is tested only on category POST/PATCH/DELETE; the 6 material/colour unsafe routes have no CSRF test | Deleting one `Depends(require_csrf)` goes unnoticed (SEC-03) | Parametrise the CSRF test over all three resources | VS-010 |
| A-08 | Minor | `test_public_reference_rate_limit.py:281-290` | The 429 test does not assert `Retry-After`, which the brief requires; it is covered only generically on `/auth/register` | Wiring is shared, so risk is low, but the requirement has no direct test | Add `assert int(refused.headers["Retry-After"]) > 0` | VS-010 |
| A-09 | Minor | `entities.py:71-81, 95-156` | The lifecycle rule "archived is terminal" lives in the application commands; the domain entities accept `archive()`/`apply_update()` on an archived row | Five commands repeat the check, and a future caller (importer, VS-013) can bypass it | Move the guard into the entity (raise `ArchivedValueNotMutableError` from `archive`/`apply_update`) | VS-010 |
| A-10 | Minor | `platform/application/services/audit_writer.py:25-32`; `category_admin.py:61` | `AuditWriter` is a concrete class that imports Platform infrastructure, not a port. `CreateCategory` depends on the concrete `CategoryRepository`, while `value_admin` uses a `Protocol` | This conflicts with "application depends on domain only" and is inconsistent within the slice | Define a Protocol for the category repo and for the audit writer in the application layer. Already tracked as BUG-41 | VS-012 (BUG-41); cheap part in VS-010 |
| A-11 | Minor | `reference_data.py:272-275` | Generated OpenAPI omits 409 on POST/PATCH/DELETE categories and PATCH/DELETE materials/colours (checked via `app.openapi()`) | `api-endpoints.md` §16 documents 409; clients generated from OpenAPI won't model `SLUG_CONFLICT` / `INVALID_STATE_TRANSITION` | Add 409 to the per-route `responses` | VS-010 |
| A-12 | Nit | `test_category_slug_race.py:63-64`; `test_reference_data_mutation_race.py:72-73` | The barrier's `TimeoutError` is suppressed, so a slow racer silently degrades the race to a sequential run that still passes | The invariant stays asserted, but overlap is never proven; it could pass without racing on a loaded CI host | Record whether the barrier completed and `pytest.fail`/`skip` if not | VS-010 (tests) |
| A-13 | Minor | migration `a9c0…:22-94` | The DB has no CHECK for `NOT (deleted_at IS NOT NULL AND is_active)`, no slug-format/lowercase CHECK, and no non-empty-name CHECK. Probe accepted `'Audit-Probe'` next to `'audit-probe'`, an archived+active row, and `name=''` | reference-data.md says the contradictory state "can never" exist; only application code enforces that, and the index is case-sensitive | Add CHECK constraints (or index `lower(slug)`) in a follow-up migration | VS-010 follow-up |
| A-14 | Nit | `schemas.py:34, 108, 132`; `slug.py:45` | Length is checked before trimming, so a 200-char slug with surrounding spaces gets 422 although the domain allows it. Names made only of a zero-width space (`"\u200b"`) are accepted (probe: 201) | Minor input-hygiene inconsistencies | Trim before length validation; reject invisible-only names | VS-010 |
| A-15 | Nit | `reference_data.py:207-213` | An invalid slug returns 422 `VALIDATION_ERROR` with `errors: []` (probe), unlike schema 422s, which carry field `loc`s | Clients cannot highlight the slug field | Raise a `RequestValidationError` with `loc=("body","slug")` | VS-010 |
| A-16 | Nit | `tests/integration/catalog/test_deep_vs010_known_bugs.py:1` | The docstring says "locked in as strict xfails", but the tests carry no xfail marker (fixed in `cc0b547`) | Stale | Update the docstring | VS-010 |
| A-17 | Nit | `docs/reference-data.md:55-60` | DELETE on an archived row → 409 `INVALID_STATE_TRANSITION` is implemented and tested but not documented; only PATCH is | Undocumented behaviour | One sentence in the doc | VS-010 |
| A-18 | Nit | `repositories.py:208-329`, `reference_data.py:414-655` | `MaterialRepository` and `ColourRepository` are identical, and 12 material/colour handlers are copy-paste | This drift is what caused A-01, A-03, A-04 and A-07 (tests cover only the category copy) | Generic repository keyed on the model; table-driven route registration or parametrised tests | VS-010 |

Also checked, no issue found: N+1 (each list is one query), leaking disabled/archived rows (filter plus schema-level field allowlist), no-op PATCH (200, `updated_at` unchanged, audited equal before/after; categories tested, colours probed), PATCH on an archived row (409), restoring an archived row whose slug was re-taken (no restore path exists; the DB refuses it anyway, verified in psql), pagination (tie-broken `(name,id)` cursor, `limit` 1..100, tampered/NUL cursor → 422, all tested), and IDOR (resources are global; unknown id → boundary-identical 404). The public rate limit keys on `request.client.host`, so behind the future reverse proxy every client would share one key. That belongs to the deploy slice (VS-020).

## 7. Open questions (SRS ambiguous)

- **Q-1:** SRS §592 justifies controlled lists by saying free text "would produce 'PLA', 'pla', and 'PLA plastic' as three distinct filters". `database-design.md` §6.2/6.3 specifies no uniqueness, and the implementation accepts `"pla"` and `"PLA"` as two live materials (probe: 201/201). Should live material/colour names be unique, case-insensitively? The SRS intent and the design doc disagree; I have not picked a side.
- **Q-2:** FR-04 (concurrent access) says conflicting admin edits "must not silently overwrite protected business fields; an optimistic version or equivalent conflict check should return a conflict response". VS-010 uses last-writer-wins under a row lock, and VS-013 adds `version` for products only. Are category/material/colour names and slugs "protected business fields"? The SRS doesn't say.
- **Q-3:** `api-endpoints.md` §16 says archive "409 when archive would violate an active product rule" for materials/colours, while BR-013 names only categories. The VS-013 plan applies the guard to all three. Confirm that materials/colours in use should block archiving rather than just be hidden.

## 8. How the commands were run

- There was no local venv. I created one in the session scratchpad from `requirements-dev.txt` (hash-pinned), with a `.pth` pointing at `src/`. There is no `.env` in this working tree, so I exported `.env.example` into the process environment, exactly as CI does with `cp .env.example .env`. Tests use their own testcontainers.
- **The running compose stack is not this checkout.** `bekaa3d-api-1` bind-mounts `C:\My_project\Bekaa3D\{src,migrations}`, and that checkout has no `5e1c0a7d2b94`. I therefore ran Alembic from this working tree against `localhost:5442` (credentials read from the postgres container's environment, never printed). The dev DB started at `a9c0aec909a9` (the three reference tables held 0 rows, so nothing was lost). As requested, it ends at this repo's head, `5e1c0a7d2b94`. Alembic run from the other checkout will not recognise that revision; `alembic downgrade a9c0aec909a9` from this repo restores the prior state.
- Mutations and probes ran against a `git archive HEAD` copy in the scratchpad. The repo stayed clean throughout.
