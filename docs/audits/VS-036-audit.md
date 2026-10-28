# VS-036 audit: reviews and the Verified Purchase badge

Independent, read-only audit. Auditor date: 2026-10-28. Tree audited: `main` @ `131949a` (VS-036 and VS-037 merged; clean). No source, test, migration or status file was changed, and nothing was committed. Mutations and probes ran only on `git archive 131949a` copies in the session scratchpad.

**Follow-up (2026-10-28):** findings A-01 to A-07 are fixed on branch `test/vs036-audit-fixes`; see §9. The nits (A-08, A-09) and the open questions (§7) are left as they are. Sections 1-8 describe the tree as audited.

## 1. Verdict

**Yes, with minor gaps.** The badge, the part that matters most, is well defended. It is recomputed in all eight line-state writers, a static allow-list fails if a ninth writer appears, and every badge-changing writer has a behaviour test that fails when its hook is given no lines (M23-M26). The per-user advisory lock `R_user` is proven load-bearing by race C9, and the product lock by race C4. Each CHECK, the live unique index and both FKs refuse their rows by name on real PostgreSQL. The migration goes down and comes back cleanly. CI is green on the audited commit (6,213 passed). Of 49 mutations, 42 are killed by VS-036's own tests, one more (M04) only by VS-037's, and 2 are equivalent (M40, M47). **5 survive, and all 5 are on the edit path or the cursor:**
- A body edit is never checked to have been saved. Making PATCH ignore `body` leaves every test green (A-01).
- PATCH content checks have no test. Dropping the link and profanity check on edit, or its 422 mapping, goes unnoticed (A-02). The code is correct today (probe P2).
- The PATCH share of the write rate limit and the review cursor's out-of-range guard have no test (A-03, A-04).

Separately, the plan's must-have races C1, C2, C6 and C7, its e2e and its smoke test were never built, and nothing records them as dropped (A-05). Probes of C1 and C7 pass 60 runs each, so this is a coverage gap, not a bug. Close A-01 and A-02 before VS-044 and VS-045 build on the review rows.

## 2. Repo state (Phase 1)

| Item | Finding |
|---|---|
| Working tree | Branch `vs-043-analytics` @ `a148a6b`, clean. VS-036 files there differ from `main` only in VS-043's additive `reports.py` and `public.py` lines, so the audit ran on `main` @ `131949a` |
| Uncommitted/untracked | None at the start. Afterwards the only untracked file is this report |
| VS-036 on `main`? | Yes. PR A #43 (`5022b7e`, schema): `22874f1` to `a801aa9`. PR B #44 (`1882a3e`, code): `1789766` to `d7f621a` |
| Later commits touching its code | VS-037 (#45): `3d22150`, `cb3c80d` (moderation store methods in `engagement/infrastructure/reviews.py`, public helpers). Audited here only where they exercise VS-036 code |
| Migration | `eeed201dcfd2` (`reviews` plus `ix_order_items_badge_received`), revises `595b7e6e2792` |
| Landed during the audit | VS-043 (#46, `7f94c0c`) on `origin/main`. **Not** audited |

## 3. Command results (Phase 2)

| Command | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 933 files already formatted |
| `mypy src tests` (strict) | PASS | 800 source files, no issues, 60 s |
| `pytest tests/unit` | PASS | 2,262 passed, 94 s (includes `test_deep_architecture.py` and the badge writer allow-list) |
| `test_review_badges`, `test_reviews_api`, `test_review_schema`, `test_review_lock_order` | PASS | 59 passed, 64 s |
| `tests/concurrency/test_review_races.py` | PASS | 10 passed (C3, C4, C5, C9×2, C10a×2, C10b×2, C11; 20 repeats each), 98 s |
| Existing files VS-036 changed: `ordering/test_lock_order`, `payments/test_manual_recovery`, `payments/test_payment_lock_order`, `payments/test_release_job`, `test_deep_db_constraints_and_migrations`, `test_migration_reversibility`, `test_model_migration_parity`, `test_openapi_security` | PASS | 98 passed, 112 s |
| **GitHub Actions, full suite on `131949a`** (run 40577658142) | PASS | **6,213 passed, 1 skipped, 8 deselected (`timing`)** across 7 shards. CI's result, not a local run |
| `alembic heads` | PASS | Exactly one head: `eeed201dcfd2` |
| upgrade → downgrade → upgrade on a throwaway `postgres:16` container | PASS | See below |

No VS-036 smoke file exists (A-05), so none was run. No local suite had a skip, xfail or error.

**Migration cycle.** I probed 11 objects: the table, its 4 CHECKs (`ck_reviews_rating_range`, `_body_shape`, `_hidden_shape`, `_updated_after_created`), 2 FKs and 4 indexes (`uq_reviews_user_product_live`, `ix_reviews_product_visible`, `ix_reviews_user_live`, `ix_order_items_badge_received`). At head: all 11. After `downgrade 595b7e6e2792`: none (the table is gone with its constraints, and the `order_items` index is dropped). After `upgrade head`: all 11, with the predicates intact, e.g. `uq_reviews_user_product_live … (user_id, product_id) WHERE (deleted_at IS NULL)` and `ix_reviews_product_visible … WHERE ((deleted_at IS NULL) AND (NOT is_hidden))`.

### Mutation results (Phase 4)

Each mutation is one or two exact string replacements on the scratch copy (each asserted to match once), run against its area's targets with `-x`, then reverted. The copy was diffed against a clean archive afterwards. Baseline over the union of targets: **177 passed** (unit review/badge/writer files, the four integration files, parity, the VS-011 CSRF route walk and `test_openapi_security`). The race file was green separately (10 passed). Survivors were then re-run against all review tests (397, including VS-037's), and lock mutations against the races alone.

| Mutation (scratch copy only) | Result |
|---|---|
| M01 drop the product row lock (`review_aggregates.py:45`) | RED: race C4 |
| M02 drop `R_user` in `create_review` | RED: unit call order; alone, race C9 |
| M03 drop `R_user` in `refresh_review_badges` | RED: `test_the_payment_hook_locks_a_review_row_only_when_one_exists`; alone, race C9 |
| M32 drop the product lock on edit/delete | RED: unit call order; alone, race C4 |
| M45 product lock `FOR UPDATE` instead of `FOR NO KEY UPDATE` | RED: `test_review_create_edit_delete_lock_r_user_then_product_then_review` |
| M05 aggregates count deleted reviews | RED: `test_edit_and_delete_keep_aggregates_exact_and_never_bump_the_product` |
| **M04 aggregates count hidden reviews** | GREEN on VS-036 tests; RED on VS-037's `test_hide_leaves_the_public_list_and_aggregates_and_restore_brings_it_back` |
| M30 aggregates bump `products.version`; M33 delete skips the recompute | RED: the edit/delete aggregates test |
| M06 / M07 public list shows hidden / deleted rows | RED: `test_the_public_list_hides_hidden_and_deleted_and_filters_and_pages` |
| M08 `/me/reviews` shows deleted rows | RED: `test_my_reviews_show_hidden_with_state_and_never_deleted` |
| M09 edit/delete without the ownership filter | RED: `test_someone_elses_review_is_the_same_404_as_a_missing_one` |
| M10 edit/delete reach deleted rows | RED: the edit/delete aggregates test |
| **M11 edit skips the content and rating checks** | **GREEN (survives)**, also against all 397 review tests |
| **M52 PATCH stops translating `ReviewContentRejectedError`** | **GREEN (survives)**, all 397 |
| **M42 PATCH never applies `body`** (`body_given=False`) | **GREEN (survives)**, all 397 |
| **M12 PATCH without the write rate limit** | **GREEN (survives)**, all 397 |
| M15 POST without the write rate limit | RED: `test_the_eleventh_write_in_an_hour_is_429_and_anonymous_posts_spend_nothing` |
| M16 public list without its rate limit | RED: `test_the_public_list_is_limited_at_600_per_ip_per_hour` |
| M13 / M14 PATCH / DELETE without CSRF | RED: VS-011's `test_every_authenticated_write_enforces_csrf` (route walk) |
| M17 create on an invisible product | RED: unit `test_create_refuses_a_missing_deleted_or_invisible_product[product2]` |
| M18 no WhatsApp-only mask | RED: unit `test_a_whatsapp_only_product_never_shows_the_badge` |
| M19 / M20 public list ignores the mask in the `verified_purchase` filter | RED: `test_d14_whatsapp_only_masks_every_read_and_keeps_the_stored_fact` |
| M21 physical badge at `shipped`; M22 STL badge only once `delivered` | RED: `test_only_owned_stl_and_received_physical_lines_earn` |
| M25 W1 payment hook gets no lines; M24 W6 refund hook gets no lines | RED: `test_stl_paid_after_the_review_then_delivered_then_fully_refunded` |
| M26 W4 transition hook gets no lines | RED: `test_online_physical_earns_only_when_delivered` |
| M23 W5 handover hook gets no lines | RED: `test_an_unpaid_cash_line_earns_nothing_and_the_handover_grants_it` |
| M51 W5 never calls the hook | RED: `test_every_caller_of_a_state_writer_refreshes_the_badge_after_the_write` |
| M27 evidence ignores the user | RED: `test_b_loss_only_the_flag_changes[refund]` |
| M28 create never reads evidence | RED: unit call order; alone, `test_partial_keeps_full_revokes_and_fail_void_settle_change_nothing` |
| M29 hook updates deleted reviews; M54 hook skips hidden ones | RED: `test_the_hook_skips_a_deleted_review_and_updates_a_hidden_one` |
| M46 hook bumps `reviews.updated_at` | RED: `test_partial_keeps_full_revokes_and_fail_void_settle_change_nothing` |
| M31 average rounds half-even | RED: `test_rating_average_rounds_half_up_to_cents[9-8-1.13]` |
| M34-M37 migration loses the rating, unique, body or hidden-shape guard | RED: `test_review_schema.py` (each by name) |
| M38 badge index predicate misses `picked_up` | RED: `test_the_indexes_exist_with_their_predicates` |
| M39 create without the duplicate pre-check | RED: unit call order (the `ON CONFLICT` backstop still gives 409) |
| M41 POST stops translating the duplicate to 409 | RED: `test_a_duplicate_is_409_also_while_hidden_and_allowed_after_delete` |
| **M53 review cursor accepts non-UTC-representable times** | **GREEN (survives)**, also with `test_review_cursor.py` and the VS-037 API tests |
| M40 insert without `ON CONFLICT DO NOTHING` | GREEN. **Equivalent**: under `R_user`, the pre-check always sees a committed duplicate first, so the backstop is unreachable (C5 still passes) |
| M47 edit keeps the stored badge instead of re-reading evidence | GREEN behaviourally (killed only by the unit call-order test). **Equivalent**: the hook keeps the stored value current under the same `R_user` |

## 4. Requirement checklist (Phase 3)

| Requirement | Status | Where | Proven by |
|---|---|---|---|
| `reviews`, rating CHECK 1-5 (BR-105) | DONE | `eeed201dcfd2…py:50` | `test_ck_reviews_rating_range` (M34 red); API `rating` 0/6/`"5"` → 422 in `test_bad_content_is_422` |
| One live review per (user, product) (BR-101) | DONE | `…py:59-65` | `test_uq_reviews_user_product_live_refuses_a_second_live_review`, `test_a_deleted_review_frees_the_pair` (M35 red) |
| `GET /products/{slug}/reviews` | DONE | `engagement/api/reviews.py:117-160` | `test_the_public_list_hides_hidden_and_deleted_and_filters_and_pages`, `test_the_cursor_is_stable_under_inserts` |
| `GET /me/reviews` | DONE | `reviews.py:163-189` | `test_my_reviews_show_hidden_with_state_and_never_deleted`, `test_my_reviews_need_only_a_session` |
| `POST /reviews` | DONE | `reviews.py:192-225` | `test_a_non_buyer_reviews_without_a_badge_and_the_aggregates_move` |
| `PATCH /reviews/{id}` | PARTIAL | `reviews.py:228-254`; `services/reviews.py:86-106` | Rating edits and `body: null` tested; a body edit being saved is not (A-01); content checks on edit untested (A-02) |
| `DELETE /reviews/{id}` (soft) | DONE | `reviews.py:257-279`; `infrastructure/reviews.py` `soft_delete` | The edit/delete aggregates test (repeat 404, row kept); M33 red |
| Badge hook on payment (W1), handover (W5), refund (W6) | DONE | `ordering/public.py:274, 528, 601` (all 8 writers: `:274, 364, 400, 463, 528, 601, 630, 667`) | Static `test_every_writer_of_a_line_state_is_listed_for_the_badge` and `…refreshes_the_badge_after_the_write` (M51 red); behaviour M23-M26 red |
| Badge = paid, non-refunded line; STL owned, physical received (BR-102 as amended) | DONE | `ordering/domain/badge.py:10-13`; evidence `ordering/infrastructure/orders.py:173-191` | `test_only_owned_stl_and_received_physical_lines_earn` over every status × type (M21/M22 red); integration STL/physical/pickup/return tests |
| A cash line counts only once its cash is recorded (ADR-024, BR-149) | DONE | `line_transitions.py` `CASH_HANDOVER_REQUIRED`; W5 | `test_an_unpaid_cash_line_earns_nothing_and_the_handover_grants_it` (M23 red) |
| A refused cash line never earns, even when the rest is handed over | DONE | `cancellation.py:27`; W2 | `test_a_refused_cash_line_never_earns_while_the_rest_is_handed_over`; race C10b |
| A refund removes the badge; partial keeps it; fail/void/settle change nothing | DONE | W6 | `test_partial_keeps_full_revokes_and_fail_void_settle_change_nothing`, `test_stl_paid_after_…_fully_refunded` (M24 red) |
| Chargeback emptying a delivered line revokes | DONE | W6 via VS-030 | `test_a_chargeback_emptying_a_delivered_line_revokes_and_an_unfinished_one_does_not`, `test_b_loss_only_the_flag_changes[chargeback]` |
| A non-buyer can review, with no badge (BR-100) | DONE | `services/reviews.py:48-68` | `test_a_non_buyer_reviews_without_a_badge_and_the_aggregates_move` |
| WhatsApp-only products never show the badge (BR-103, D14) | DONE | `domain/reviews.py:94-96`; `reviews.py:141-147`; `public.py` `reviews_for_export` | `test_a_whatsapp_only_product_reviewer_without_a_line_has_no_badge`, `test_d14_…` (M18-M20 red) |
| Links rejected; profanity filter | DONE (POST) / PARTIAL (PATCH) | `domain/reviews.py:40-84` | Unit link/profanity tests; `test_bad_content_is_422` (POST only). PATCH: A-02. Zero-width bypass: A-06 |
| Posting rate-limited | DONE (POST, DELETE, list) / PARTIAL (PATCH) | `reviews.py:58-62, 77-89` | M15, M16 red; PATCH untested (A-03) |
| Aggregates recomputed under the product lock in the same transaction | DONE | `services/reviews.py:40-45`; `review_aggregates.py:40-59` | Races C3, C4 (M01, M32 red); lock-order test (M45 red) |
| Aggregates never bump `version` / `updated_at` (ADR-020 d5) | DONE | `review_aggregates.py:50-59` | M30 red |
| No author identity exposed (ADR-044 d10) | DONE | `review_schemas.py:50-82` | Field-set assertion in the public-list test |
| The product must be visible to review (FR-14 Given) | DONE | `services/reviews.py:61` | `test_a_non_public_product_is_404_on_create_and_on_the_list` ×3; probe P3: disabled category → 404 |

### "Done when", slice tests and FR-14 cases → tests

| Case | Test |
|---|---|
| Done when: the badge is never stale after a payment or refund | Hook in all 8 writers plus the static allow-list; races C9 (both orders), C10a/b, C11. C1 (create vs payment) and C2 not built (A-05); probe C1 passes 60/60 |
| Done when: aggregates always match the visible reviews | `_assert_exact` / `fresh_totals` in API tests; races C3, C4 |
| Slice: duplicate → 409 | `test_a_duplicate_is_409_also_while_hidden_and_allowed_after_delete`; race C5 (one 201, one 409, 20×) |
| Slice: concurrent edits keep aggregates correct | Race C4 |
| FR-14 neg: hidden reviews do not count in aggregates | No VS-036 test (M04 green on VS-036 files); covered by VS-037's moderation test |
| FR-14 neg: unverified users cannot review | `test_unverified_anonymous_and_missing_csrf_are_refused` (403 `EMAIL_VERIFICATION_REQUIRED`) |
| FR-14 neg: customers cannot edit others' reviews | `test_someone_elses_review_is_the_same_404_as_a_missing_one` (M09 red) |
| FR-14 neg: excessive submissions rejected | The 11th-write test (POST + DELETE); PATCH untested (A-03) |
| FR-14 conc: unique constraint prevents duplicates | Schema test + race C5 |
| FR-14 conc: payment (online or cash) or refund triggers recompute | C9, C10, C11 for refund/cancel; C1 (payment) and C2 (handover vs refund) not built (A-05) |
| FR-14 failure: review and aggregate in one transaction | By construction (the service never commits; one session per request); no failure-injection test, as in earlier audits |

## 5. Definition of Done (Phase 5)

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Cycle above; single head `eeed201dcfd2`; `test_migration_reversibility` passes |
| Rules in owning context; other contexts only via ports | Met | `test_deep_architecture.py` passes. Engagement reaches Catalog only through `catalog.public` / `application.ports`; Ordering calls `engagement.public`, and `engagement.public` never imports Ordering (`test_engagement_public_never_imports_ordering`) |
| Auth, verified email, ownership 404, admin boundary, CSRF, rate limits | Mostly | Verified writes, same-body 404 and CSRF are all proven (M09, M13, M14 red). The PATCH rate limit is untested (A-03). The rate limit runs before CSRF (A-08) |
| Money in cents; UTC timestamps; server computes status | Met | No money; all timestamps `timestamptz`; edits stamp `clock_timestamp()` (`ck_reviews_updated_after_created`); the badge is server-computed and the client cannot set it (`test_an_edit_needs_a_field_and_the_client_cannot_set_moderation_or_badge`) |
| Audit / notification / outbox side effects | n/a | Customer review writes are not audited by decision (ADR-044 d10, Q9) |
| Background jobs | n/a | None |
| Unit + PG integration + API error/IDOR + a race test for every known race | Partly | Strong overall; plan races C1, C2, C6 and C7 not built (A-05). C9, C10 and C11 sequence through `R_user` waits (`queued_on_user`, `pg_stat_activity`) and C4, C5 through `meet_or_fail`; none swallows a barrier timeout |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Met | CI run 40577658142 green |
| Docs and OpenAPI updated; Status Done | Mostly | api-endpoints §14.1, §29.8 and error codes match the code; OpenAPI regenerated; plan and slice table Done; CLAUDE.md lists VS-036. README's Status list skips VS-036 and VS-037 (A-07) |
| Glossary naming | Met | `Review`, `reviews`, `is_verified_purchase`, `ReviewAlreadyExistsError`; no synonyms |

## 6. Findings

| ID | Sev | Location | What is wrong | Impact | Suggested fix (not applied) | Scope |
|---|---|---|---|---|---|---|
| A-01 (fixed) | Major | `engagement/api/reviews.py:250`; `test_reviews_api.py:177-181` | No test checks that a body edit is saved. M42 (`body_given=False`) survives all 397 review tests. The body-only PATCH asserts only `rating == 4`, and the `body: null` step passes vacuously because that review never had a body | A regression where edits silently drop the new text (the core of "the customer edits a review", FR-14) would ship green | Assert `body == "Changed my mind."` in the response and in `review_row` after the body-only PATCH; give the review a body before testing `body: null` | VS-036 (tests) |
| A-02 (fixed) | Major | `services/reviews.py:98-99`; `reviews.py:252` | PATCH content checks have no test. M11 (edit skips the link and profanity check) and M52 (PATCH stops mapping `ReviewContentRejectedError` → 422, so it becomes a 500) both survive. Probe P2 shows the code is correct today: link and profanity → 422 `REVIEW_CONTENT_REJECTED`; NUL and 2001 chars → 422 | api-endpoints §14.1 says PATCH "revalidates content". Edit is the obvious way round the filter (post clean, then edit in a link), and a regression would go unnoticed | Parametrise `test_bad_content_is_422` over POST and PATCH, asserting `code` and `reason`; add PATCH cases to the unit `test_a_refusal_calls_no_port` | VS-036 (tests) |
| A-03 (fixed) | Minor | `reviews.py:231`; `test_reviews_api.py:339-355` | The shared write limit is exercised through POST and DELETE only. M12 (PATCH without the limit) survives | Unlimited edits per hour: aggregate churn and filter probing at no cost | Make the 11th write a PATCH, or count a mix of POST, PATCH and DELETE | VS-036 (tests) |
| A-04 (fixed) | Minor | `review_cursor.py:29-30` | The out-of-range guard (BUG-36) on the review cursor has no test. M53 survives VS-036's tests, `test_review_cursor.py` and VS-037's API tests. A scratch probe (`0001-01-01T00:00:00+05:00` → 422 on real code) kills it | Removing the guard would turn a tampered cursor into a 500 on the public list and the admin list | Add the probe as a test, parametrised over `/products/{slug}/reviews`, `/me/reviews` and `/admin/reviews`, with a naive time too | VS-036 (tests) |
| A-05 (fixed) | Minor | `docs/plans/VS-036-reviews-plan.md:777-791, 837-841`; `tests/concurrency/test_review_races.py` | Plan `[M]` tests never built: races C1 (create vs STL payment), C2 (handover vs refund, same product), C6 (edit vs wishlist add vs admin product edit) and C7 (refund vs same-user edit); the e2e journey; the smoke test (head + five routes). Repeats are 20, not the planned 50. Neither the plan, ADR-044 nor PR #44 records them as dropped | The lock-order proof for those paths rests on SQL capture (`test_review_lock_order`, `test_payment_lock_order`), not on real runs. Scratch probes of C1 and C7 (3 modes × 20 repeats each, `queued_on_user` both orders plus `together`) **pass**, so no bug is shown | Add C1 and C7 (the probes can be lifted as they are), C2 and C6; add `tests/smoke/test_vs036_smoke.py`; or record in the plan that they were dropped and why | VS-036 (tests) |
| A-06 (fixed) | Minor | `engagement/domain/reviews.py:75-84` | The link filter runs after NFKC, but NFKC keeps zero-width characters (Unicode `Cf`), and `has_control_characters` checks only `Cc`. `"visit cheap3d\u200b.com today"` passes the schema and `content_refusal` (probe), and it shows as `cheap3d.com` | A trivial bypass of the link rule (FR-14 neg). Unlisted TLDs such as `.shop` / `.store` also pass; that part is by design (closed list, see Q-1) | Strip `Cf` characters (or reject them) before matching, and add the case to `test_links_are_refused` | VS-036 |
| A-07 (fixed) | Minor | `README.md:12-45` | The Status list jumps from VS-035 to VS-038; VS-036 and VS-037 are missing, though CLAUDE.md says README summarises the slice table | Out-of-date status for readers who start at the README | Add one line each for VS-036 and VS-037 | VS-036/037 (docs) |
| A-08 | Nit | `reviews.py:196, 231, 261` | `_write_rate_limit` runs before `require_csrf`. Probe P1: ten CSRF-less POSTs (all 403) use up the budget, and the user's next valid POST is 429. The same order is used on cart, offers and wishlist; `SameSite=lax` keeps cross-site callers out | A same-site script or a buggy client can lock a user out of review writes for an hour | Put `require_csrf` first on review writes (as `item_transition.py` and `admin_cash_blocks.py` do) and decide the convention project-wide | Cross-cutting (hardening) |
| A-09 | Nit | `infrastructure/reviews.py` `update`; `domain/reviews.py:118-119` | A PATCH that changes nothing (same rating) returns 200 with `edited: true` and moves `updated_at` (probe P4). ADR-044 d17 asks for a full recompute, not a timestamp bump | The public "edited" mark claims an edit that never happened | Leave `updated_at` alone when rating and body are unchanged (still recompute) | VS-036 |

Also checked, no issue found: ownership (another user's id, a missing id and a deleted id all give the same 404 body); IDOR on `/me/reviews` (filtered by the session user); N+1 (`/me/reviews` resolves products in one batched read); a hidden review stays hidden after an edit and still blocks a second review; the hook skips deleted reviews and updates hidden ones; losing the badge touches neither the aggregates, `products.version`/`xmin` nor `reviews.updated_at` (B-LOSS); cancel edges never start from a badge state (`ADMIN_CANCELLABLE`, `CANCEL_REASONS`), so the W2, W3, W7 and W8 hooks cannot change a badge, as ADR-044 d12 says. The `ON CONFLICT` backstop (M40) is unreachable while `R_user` serialises creates; it is a sound second line, not dead weight. VS-036's own files never prove that hidden reviews stay out of the aggregates (M04); VS-037 does.

## 7. Open questions (SRS ambiguous)

- **Q-1:** The profanity list is a first draft that "needs owner review before go-live" (ADR-044 d20), and the link filter is a closed list of 15 TLDs (`.shop`, `.store` and handles like `@shop3d` pass). FR-14 says links "may be rejected". Is a closed list acceptable for go-live, or should any `word.word` with a known public suffix count as a link? This is a go-live gate, not a code defect.
- **Q-2:** FR-14's "Given the product is visible" is applied to create only. An author can still edit or delete a review after the product is hidden or archived (`services/reviews.py:74`, by plan decision). The SRS does not say whether edits to reviews of non-public products should be allowed.
- **Q-3:** BR-149 says "a line cancelled by a chargeback is still a paid line", while BR-102 says the badge needs a line "not refunded, returned or cancelled". As built, the two agree: a chargeback only cancels unfinished physical lines, which never earned the badge. If a later slice lets a chargeback cancel a received line, the two rules would conflict. Worth stating explicitly in BR-102.

## 8. How the commands were run

- Every command ran on `git archive 131949a` copies in the session scratchpad, using the repo's `.venv` with `PYTHONPATH=<copy>/src`, which overrides the editable install that points at the working tree (checked with `import app; app.__file__`). `.env.example` was exported into the process environment, as CI does with `cp .env.example .env`; `.env` was never read. Tests use their own testcontainers.
- Docker Desktop was stopped at the start. I started it before any integration run, so no suite ran without it.
- The migration cycle ran against a throwaway `postgres:16` container on port 55436, removed afterwards; no dev or real database was touched.
- Mutations ran through a driver that applies exact replacements (asserted unique), runs pytest with `-x`, and restores the files in `finally`. A first pass was stopped after 10 mutations because its summary filter caught teardown log lines; the copy was re-extracted and the whole set re-run. Afterwards the copy matched a clean archive (`diff -rq`, `__pycache__` excluded).
- Probes P1-P4, the C1/C7 race probes and the cursor probe were scratch-only test files and print-only scripts. None is in the repository.

## 9. Fixes (branch `test/vs036-audit-fixes`, 2026-10-28)

A-06 is the only code change. Everything else is tests and docs. Each surviving mutation was re-applied to a scratch copy of the branch, and each is now killed by the new test.

| Finding | Fix | Proof |
|---|---|---|
| A-01 | `test_edit_and_delete_keep_aggregates_exact_and_never_bump_the_product` now creates the review with text, checks that a rating-only edit keeps it, that a body edit is saved (response and row, trimmed), and that `body: null` clears real text | M42 RED from this test alone |
| A-02 | New `test_an_edit_with_bad_content_is_422_and_keeps_the_text`: PATCH with a link, profanity or a zero-width link → 422 `REVIEW_CONTENT_REJECTED` with `reason`; stored text and `updated_at` unchanged | M11, M52 RED |
| A-03 | New `test_edits_spend_the_same_write_budget`: 1 POST and 9 PATCHes pass, the 11th write (a PATCH) is 429 | M12 RED |
| A-04 | New `test_an_out_of_range_or_naive_cursor_is_422_on_every_review_list`, over the public list, `/me/reviews` and `/admin/reviews` | M53 RED |
| A-05 | Races C1 (`test_c1_review_create_vs_the_stl_payment`) and C7 (`test_c7_refund_vs_an_edit_of_the_same_users_review`) added to `test_review_races.py`: both forced commit orders plus a `meet_or_fail` start, 20 repeats each | 6 runs green locally |
| A-06 | `content_refusal` drops Unicode format characters (category `Cf`: zero-width space and joiners, BOM, word joiner, soft hyphen, bidi marks) and the other default-ignorable ones (e.g. Hangul filler, variation selectors) before NFKC, for both the link and the profanity checks. Create and PATCH share it. The stored text is unchanged. Unit cases cover each class (and an emoji ZWJ sequence still passes); API cases cover `cheap3d\u200b.com` on POST and PATCH | 8 new unit cases fail without the fix; M55 (drop the stripping) RED |
| A-07 | README Status gains VS-036 and VS-037 | — |

**Dropped from the plan, by decision (A-05):**
- **C2** (handover vs full refund on two orders of one user, same product): both are hooked writers that serialise on `R_user` and read evidence after taking it. C9, C10 and C11 already prove that mechanism, and `test_another_received_order_of_the_product_keeps_the_badge` covers evidence across orders.
- **C6** (review edit vs wishlist add vs admin product edit): the three paths share only the product row, and otherwise lock rows of their own tables (reviews, wishlist items), so no wait cycle can form. The `version` rule is pinned by the edit/delete aggregates test (review writes never bump it).
- **e2e journey** (register → buy STL → review → refund): every step already runs through the real writers in `test_review_badges.py` (W1 by late capture, W6 by the admin refund over HTTP, the public list over HTTP). The mock checkout adds no review guard.
- **Smoke test** (head plus five routes in OpenAPI): already pinned by `alembic heads` in CI, `test_migration_reversibility`, `test_model_migration_parity` and the VS-036 route tests in `test_openapi_security.py`.
