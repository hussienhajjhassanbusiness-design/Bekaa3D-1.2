# VS-023b audit: STL delivery queue and mark-as-sent

Independent, read-only audit. Auditor date: 2026-11-04. Tree audited: branch `fix/vs040-audit` @ `cd8bd80` (clean), which is `origin/main` @ `41e1ac5` plus PR #60. That PR touches none of the slice's code, tests or documents: `git diff origin/main HEAD` over `src/app/fulfillment`, `src/app/ordering`, `src/app/payments`, `migrations`, `tests/integration/fulfillment`, the slice's race and e2e files, `docs/stl-delivery.md` and ADR-039 is empty. No source, test, migration or status file was changed. Mutation experiments and probes ran only on a scratch copy (`git archive HEAD`) outside the repo.

**Fixed afterwards.** A-01 to A-10 are fixed and Q-2 to Q-4 decided on `fix/vs023b-audit`, cut from `main` @ `75da7c1` (PR #60 merged, same tree as audited). The body describes the tree as audited: its line numbers and verdict predate the fixes. Section 3 ends with the re-run.

## 1. Verdict

**Yes, with minor gaps.** VS-023b is a trustworthy base for later slices. Every behaviour checked works on real PostgreSQL, including through the real refund and checkout paths: no paid STL leaves the queue except by delivery or a full refund, one race produces one delivery record, and no illegal edge moves a line. No application bug can cause a lost, duplicated or unpaid delivery. 38 of 55 mutations were killed, and the guards that protect money and paid access all were: the orders lock, lock order, the refusal, the audit row, the notices, the admin boundary, CSRF and the schema. The one Major finding is a test gap, not a bug: nothing tests keyset paging across equal `created_at` values, and that tie is the normal case for any order with two STL lines, because they share one timestamp (A-01). A regression there would hide a paid STL from the administrator, which is what the slice's first "Done when" forbids. Two small contract bugs exist on the transition endpoint: STL refusals omit the documented `fulfillment_status` (A-02), and an STL delivery silently discards the administrator's note (A-03). Close A-01 first.

## 2. Repo state (Phase 1)

| Item | Finding |
|---|---|
| Current branch | `fix/vs040-audit` @ `cd8bd80`, 6 commits ahead of `origin/main` (open PR #60). Local `main` is behind `origin/main` @ `41e1ac5` |
| Uncommitted/untracked at start | None (`git status --short` empty). Afterwards the only untracked file is this report |
| VS-023b on `main`? | Yes. `effa2b0` "Vs 023b stl delivery (#29)" is an ancestor of `origin/main` |
| Later commits on the slice's files | `4a5a545` VS-029 (#33: physical edges, `AdminOrderDetail` response, `deliver_stl_line` split out), `34af46d` VS-030 refund core (#38: real refund facts replace the `refund_present` stop-gap). `src/app/fulfillment` as a whole also changed in `a873774` (#39), `7649b7d` (#41) and `16ab43e` (#51) |
| Slice's migration | `7a1c3e9b5d24`, revises `fcd589e89e59`; the chain's head is now `95ffee5fde3b` |

## 3. Command results (Phase 2)

Docker Desktop was stopped at the start and was started for the audit. The full suite was not run locally (the machine runs out of memory); its result comes from GitHub CI.

| Command | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!", 0.3 s |
| `ruff format --check .` | PASS | 1022 files already formatted |
| `mypy src tests` | PASS | "no issues found in 870 source files", served from the mypy cache in 2.4 s |
| `pytest tests/unit` | PASS | **2509 passed, 1 skipped** (no clamd, not this slice), 2 min 56 s |
| Slice suite: `test_stl_delivery_api.py`, `test_stl_delivery_races.py`, `test_vs023b_stl_delivery.py`, `test_transition_refund_facts.py`, `test_settings_seed.py` | PASS | **34 passed**, 51 s |
| Touched code: `test_order_payment_schema.py`, `test_admin_settings.py`, `test_line_transition_api.py` | PASS | **264 passed**, 4 min 58 s |
| `test_i14_stl_delivery_after_partial_and_full_refunds`, `test_model_migration_parity.py`, `test_openapi_security.py` | PASS | **39 passed**, 21 s |
| `tests/unit/ordering`: `test_line_transitions.py`, `test_order_item_writers.py`, `test_order_status.py` | PASS | **262 passed**, 26 s |
| `test_r4_a_full_stl_refund_racing_its_delivery` (real refund against real delivery) | PASS | 2 passed, 16 s |
| Smoke | Not applicable | No `tests/smoke` file lists a VS-023b test (`grep` empty), and no VS-023b smoke suite exists |
| Full suite on `main` | CI PASS | Run `41609443385` on `41e1ac5`: all shards and `ci-ok` success, 10 min 4 s. CI's result, not a local one |
| Full suite on the audited commit | CI PASS | Run `41748380843` on `cd8bd80` (PR #60): success, 10 min 22 s. CI's result |
| `alembic heads` | PASS | Exactly one: `95ffee5fde3b` |
| Migration cycle (throwaway `postgres:16`) | PASS | See below |

**Migration cycle.** Each row was read back from the database after the step.

| Step | `alembic_version` | `ix_order_items_stl_awaiting` | `daily_download_cap` |
|---|---|---|---|
| upgrade `7a1c3e9b5d24` | `7a1c3e9b5d24` | `(created_at, id) WHERE product_type = 'stl' AND fulfillment_status = 'awaiting_delivery'` | absent |
| downgrade `fcd589e89e59` | `fcd589e89e59` | gone | back: `integer`, `20`, original description |
| upgrade `7a1c3e9b5d24` | `7a1c3e9b5d24` | back, same definition | absent |
| upgrade `head` | `95ffee5fde3b` | same definition | absent |

**Mutation results.** Target set T1: `test_line_transitions.py`, `test_order_item_writers.py`, `test_order_status.py`, `test_stl_delivery_api.py`, `test_stl_delivery_races.py`, `test_vs023b_stl_delivery.py`, `test_transition_refund_facts.py`, `test_settings_seed.py`. Baseline on the copy: **296 passed, 83 s**. Migration mutations ran on the schema, seed and parity tests (M53 and M54 also on `test_every_migration_step_goes_down_and_up_with_data_present`). Survivors of T1 ran again on the wider tests that exercise this code: `test_line_transition_api.py`, plus `test_cancel_api.py`, `test_admin_order_queue_api.py`, `test_i14`, `test_data_export_api.py`, `test_vs011_admin_boundary.py`, `test_deep_vs005_admin_mfa.py`, `test_cancel_refusals.py`, `test_refund_races.py` or `test_refund_lock_order.py`, as fits each one.

| Mutation (scratch copy only) | Result |
|---|---|
| M01 drop `FOR UPDATE` on the orders lock | RED: `OrderLockRequiredError` at `test_marking_a_line_sent_writes_every_record_once` (a runtime guard, the strongest kind) |
| M02 drop `FOR UPDATE` on the lines lock | T1 green; RED wide: `test_lo2_every_refund_path_locks_in_rank_order` and two more |
| M06 ignore the refusal | RED: `test_a_line_that_is_not_awaiting_delivery_is_a_409_that_writes_nothing` |
| M07 409 stops carrying `fulfilled_at` (use case) | RED: same test |
| M08 skip the line history row | RED: `test_marking_a_line_sent_writes_every_record_once` |
| M09 history row loses its actor | RED: same |
| M10 skip the review badge refresh | RED: `test_every_caller_of_a_state_writer_refreshes_the_badge_after_the_write` |
| M11 recompute from the pre-delivery state | RED: `test_marking_a_line_sent…` |
| M12 recompute with `reached_paid=False` | RED: same |
| M13 recompute ignores the refund facts | RED: `test_delivery_on_a_partly_refunded_order_keeps_it_partially_refunded` |
| M14 an STL line accepts any target | RED: `test_an_unknown_target_is_a_422_and_a_physical_target_a_409` |
| M15 `cancel_reason` accepted on a non-cancel target | T1 green; RED wide: `test_a_transition_needs_csrf_and_a_foreign_line_is_a_404` (physical line only) |
| M16 skip the audit write | RED: `test_marking_a_line_sent…` |
| M17 audit loses its actor | RED: same |
| M21 skip the notices | RED: same |
| M22 category `order` instead of `download` | RED: same |
| M23 wrong email template | RED: same |
| M25 email to a fixed address, not the snapshot | RED: same |
| M26 queue drops the `awaiting_delivery` filter | RED: `test_only_awaiting_stl_lines_are_queued` |
| M27 queue drops the STL filter | RED: `test_the_queue_query_uses_the_partial_index` |
| M29 queue ignores `customer_id` | RED: `test_the_queue_is_oldest_first_and_paging_loses_and_repeats_nothing` |
| M30 newest first | RED: same |
| M32 cursor `>=` repeats a row | RED: same |
| M39 `next_cursor` never set | RED: same |
| M40 queue stops over-fetching | RED: same |
| M41 queue router without `AdminBoundaryRoute` | T1 green; RED wide: `test_every_admin_route_authenticates_before_reading_the_body` |
| M42 transition router without `AdminBoundaryRoute` | T1 green; RED wide: same, plus `test_the_boundary_runs_before_the_body_is_parsed` |
| M43 no CSRF | RED: `test_a_delivery_without_a_csrf_token_is_refused` |
| M44 no rate limit | T1 green; RED wide: `test_the_admin_cancel_shares_the_transition_rate_limit` |
| M46 `LineNotFoundError` untranslated | RED: `test_unknown_order_unknown_item_and_a_foreign_item_share_one_404` |
| M47 409 body drops `fulfilled_at` | RED: `test_a_line_that_is_not_awaiting_delivery…` |
| M48 409 body drops `fulfillment_status` | RED: `test_an_unknown_target_is_a_422_and_a_physical_target_a_409` |
| M49 lock lines before the order | RED: `test_two_administrators_marking_one_line_sent_get_one_200_and_one_409` |
| M50 migration creates no queue index | RED: `test_every_lookup_index_exists` |
| M51 index not partial | RED: `test_the_stl_delivery_queue_index_is_partial_on_created_at_and_id` |
| M52 `daily_download_cap` kept | RED: `test_every_registered_setting_is_seeded_and_nothing_else_is` |
| M54 downgrade does not drop the index | RED: `test_every_migration_step_goes_down_and_up_with_data_present` |
| M55 index missing from the model | RED: `test_models_match_the_migration` |
| **M31 no `id` tie-break in the inner ordering** | **GREEN (survives)**: A-01 |
| **M33 cursor on `created_at` only, loses ties** | **GREEN (survives)**: A-01. A probe through a real checkout kills it |
| **M05 `set_line_delivered` stops setting `updated_at`** | **GREEN (survives)**: A-04 |
| **M18 audit `before_data` emptied** | **GREEN (survives)**: A-04 |
| **M19 audit `after_data` loses `fulfilled_at`** | **GREEN (survives)**: A-04 |
| **M20 audit `after_data` loses `order_id`, `order_number`** | **GREEN (survives)**: A-04 |
| **M24 notice payload loses `product_name`** | **GREEN (survives)**: A-04 |
| **M28 queue ignores `product_id`** | **GREEN (survives)**: A-05 |
| **M35 no page cap** | **GREEN (survives)**: A-05 |
| **M36 `limit=0` allowed** | **GREEN (survives)**: A-05 |
| **M37 cursor accepts a naive time** | **GREEN (survives)**: A-05. Under it a probe gets 200 instead of 422 |
| **M38 cursor without the out-of-range guard** | **GREEN (survives)**: A-05. Under it a probe gets an asyncpg `DataError` instead of 422 |
| **M45 the rate limit is effectively off** (`limit=10**9`) | **GREEN (survives)**: A-06 |
| **M53 downgrade does not re-seed the setting** | **GREEN (survives)**: A-07 |
| M03 `set_line_delivered` drops its status guard | GREEN. Expected: the guard is belt and braces behind the refusal, made under the locks. Not a finding |
| M04 `set_line_delivered` drops its STL guard | GREEN. Expected: `transition_line` routes physical lines elsewhere and the refusal runs first. Not a finding |
| M34 outer query unordered | GREEN. Expected on small sets: the plan keeps the subquery's order. Removing `ORDER BY` is still wrong, and only a plan change would expose it. Not a finding |

Totals: **38 killed, 17 survived**, of which 3 are expected and 14 feed findings A-01 and A-04 to A-07.

**Re-run after the fixes.** On a fresh copy of the fix commit. Target: `test_stl_delivery_api.py` and `test_vs023b_stl_delivery.py`; baseline 32 passed before the last test below was added. M53 ran on the new migration test. `F*` are new mutations that undo the fixes.

| Mutation | Result |
|---|---|
| M33 cursor on `created_at` only | RED: `test_the_queue_is_oldest_first_and_paging_loses_and_repeats_nothing`, now with the tie split by `limit=3` |
| M31 no `id` tie-break | GREEN at first: the partial index hands ties over in `id` order. RED in 3 of 3 runs after adding `test_paging_tied_lines_holds_when_the_planner_sorts_instead_of_using_the_index` |
| M05, M18, M19, M20, M24 | RED: `test_marking_a_line_sent_writes_every_record_once` |
| M28 | RED: `test_the_product_filter_lists_only_that_product` |
| M35, M36 | RED: `test_a_limit_outside_one_to_a_hundred_is_a_422[101]`, `[0]` |
| M37, M38 | RED: `test_a_bad_cursor_is_a_422[naive]`, `[before_year_1_in_utc]` |
| M45 | RED: `test_the_transition_answers_429_at_the_documented_limit` |
| M53 | RED: `test_the_stl_queue_migration_restores_the_setting_when_it_goes_down` |
| F1 the refusal drops `current_status` | RED: `test_a_line_that_is_not_awaiting_delivery_is_a_409_that_writes_nothing` |
| F2 the `cancel_reason` refusal drops it | RED: `test_a_cancel_reason_is_refused_with_the_state_and_an_unknown_line_stays_a_404` |
| F3 `cancel_reason` refused before the line is read | RED: same |
| F4 the note is not passed to the delivery | RED: `test_a_delivery_keeps_the_administrators_note_and_hides_it_from_the_customer` |
| F5 the history row drops the note | RED: same |
| F6 the audit row drops the note | RED: `test_marking_a_line_sent_writes_every_record_once` |
| F7 no notice or email for a deactivated buyer | RED: `test_a_deactivated_buyer_stays_queued_and_still_gets_the_file_sent_email` |

All 14 finding-bearing survivors are now killed. M03, M04 and M34 stay accepted, for the reasons above. A-01's real-checkout test is `test_two_stls_of_one_checkout_share_a_moment_and_paging_hides_neither`, through real payment verification. A-08's dispatch is asserted in `test_register_buy_queue_mark_sent_customer_notified`. A-09 and A-10 have no mutation: the function is deleted and the docs corrected.

The fixes' independent reviews changed three of those tests. The e2e's spy moved to `ConsoleEmailProvider.send`, because a spy on the job's factory could not see an inline send (F8). The rate-limit test also pins the hour (F9). The `too_long` cursor is now well-formed, because `"A" * 201` also failed base64 decoding (F10).

| Mutation | Result |
|---|---|
| F8 the delivery also sends the email inline | RED: `test_register_buy_queue_mark_sent_customer_notified` |
| F9 the window is 60 seconds, not an hour | RED: `test_the_transition_answers_429_at_the_documented_limit` |
| F10 no `max_length` on the cursor | RED: `test_a_bad_cursor_is_a_422[too_long]` |

**Probes (scratch copy only, no repo change).**

| Probe | Result |
|---|---|
| P1 mark sent on `delivered`, `refunded`, `cancelled`, `pending` | Each 409 with the right `reason`; **no `fulfillment_status` in any body**: A-02 |
| P2 STL delivery with `reason: "Sent by link, too big."` | 200; `order_status_history.reason` is NULL and the audit row has no note: A-03 |
| P2b the same field on a physical step | Kept: `reason = 'Printer two.'` |
| P3 `cancel_reason` on an STL delivery | 409 `cancel_reason_not_allowed`, line untouched; no `fulfillment_status`: A-02 |
| P4 queue inputs | `limit=0`, `limit=101`, naive cursor, year-1 cursor, year-9999 cursor, 201-character cursor, bad UUID: all 422. `limit=100`: 200. `product_id` filter returns the right subset |
| P5 `dispatch_outbox` with a spy provider | Nothing sent before the job; then one `order_stl_delivered` to the snapshot address, with `product_name` |
| P6 real partial and full refunds | A partly refunded line stays listed; a fully refunded one leaves |
| P7 customer's order detail after delivery | No `delivered_by` in the response |
| P8 buyer deactivated before delivery | Still listed; POST 200; one email queued: Q-2 |
| P9 POST with the counter at the limit | 429 with `Retry-After: 3600`; the limit is 300 |
| P10 STL line in `awaiting_delivery` or `pending`, target `cancelled`, `refunded`, `pending`, `awaiting_delivery`, `returned`, `picked_up` | All 12 cases 409 `not_a_legal_edge`, line untouched |
| P11 real checkout of two STL products | Both lines have the identical `created_at`; paging with `limit=1` returns each once. Under M33 the same probe fails: A-01 |

## 4. Requirement checklist (Phase 3)

| Requirement | Status | Where | Proof |
|---|---|---|---|
| Queue index, partial on STL and `awaiting_delivery` | DONE | `7a1c3e9b5d24_…py:46-53`; `ordering/infrastructure/models.py:432-439` | `test_the_stl_delivery_queue_index_is_partial_on_created_at_and_id`, `test_the_queue_query_uses_the_partial_index`, `test_models_match_the_migration`; M50, M51, M55 red |
| `delivered_by` and delivery CHECKs | DONE (VS-023) | `models.py:413-417` | `test_order_payment_schema.py`; the slice adds no column |
| `daily_download_cap` deleted, registry entry removed | DONE | Migration `:54` | `test_every_registered_setting_is_seeded_and_nothing_else_is`, `test_the_obsolete_daily_download_cap_setting_is_gone`, `test_the_removed_daily_download_cap_is_an_unknown_key`; M52 red |
| Downgrade re-seeds the setting | PARTIAL | Migration `:58-62` | Works in the cycle above; no test (M53, A-07) |
| `GET /api/v1/admin/stl-deliveries` | DONE | `fulfillment/api/stl_deliveries.py:70-99`; `ordering/infrastructure/orders.py:454-489` | `test_only_awaiting_stl_lines_are_queued`, `test_a_queue_row_carries_the_admin_fields_and_nothing_else` |
| Queue shows order number, product, customer, `customer_email_snapshot`, oldest first (SRS 10.2) | DONE | `orders.py:473-489` | Same, plus `test_the_queue_is_oldest_first…`; M30 red |
| Keyset paging loses and repeats nothing | PARTIAL | `orders.py:471-473` | Correct by probe P11. The test never splits a tie across pages (M31, M33, A-01) |
| `product_id` filter, `limit` bounds, cursor time rules | PARTIAL | `stl_deliveries.py:53-68, 83-85` | Correct by probe P4; untested (M28, M35-M38, A-05). Only garbage cursors are tested |
| Queue exposes no payment ids, phone or hashes | DONE | `stl_deliveries.py:25-35` | Exact key set in `test_a_queue_row_carries…` |
| `POST …/items/{item_id}/transition`, STL `awaiting_delivery -> delivered` | DONE | `fulfillment/api/item_transition.py:72-135`; `application/transition_line.py:62-81`; `application/mark_stl_delivered.py:52-86`; `ordering/public.py:401-451` | `test_marking_a_line_sent_writes_every_record_once` |
| ADR-024 lock order: orders, then lines by id | DONE | `ordering/public.py:228-234`; `orders.py:245-258` | M01, M02, M49 red |
| Sets `fulfilled_at`, `delivered_by` together | DONE | `orders.py:321-337` | `test_marking_a_line_sent…`; `ck_order_items_stl_delivery_record` |
| Recomputes the order status, `completed` when the only line is delivered | DONE | `public.py:435-445` | `test_marking_a_line_sent…`, `test_a_pending_physical_line_keeps_the_order_in_progress`; M11, M12 red |
| Partly refunded order stays `partially_refunded` | DONE | `public.py:442`; `transition_line.py:62` | `test_delivery_on_a_partly_refunded…`, `test_transition_refund_facts.py`; M13 red |
| History row with the administrator as actor | DONE | `public.py:423-433` | `test_marking_a_line_sent…`; M08, M09 red |
| Audit row (BR-132) | DONE, content PARTIAL | `mark_stl_delivered.py:69-85` | Actor, request id, IP hash and `delivered_by` asserted; `before_data` and the rest of `after_data` not (M18-M20, A-04) |
| In-app notification, `download`, `payload.event = "stl.delivered"` | DONE, content PARTIAL | `fulfillment/infrastructure/delivery_side.py:219-245` | Count, user and type asserted; `product_name` not (M24, A-04) |
| "Your STL file has been sent" email through the outbox, to the snapshot | PARTIAL | `delivery_side.py:44, 224-230` | Row, recipient and template asserted; `dispatch_outbox` never run on it in a test (A-08). Works by probe P5 |
| One transaction, nothing external inside | DONE | `api/dependencies.py` session; `mark_stl_delivered.py:1-2` | `test_a_failing_notice_rolls_the_whole_delivery_back`; outbox row is `pending` after the call |
| Reuses the admin boundary, `AuditWriter`, `create_notification`, outbox, `derive_order_status` | DONE | Imports above | M41, M42 red wide; `test_deep_architecture.py` in `tests/unit` |
| CSRF on the POST | DONE | `item_transition.py:75` | `test_a_delivery_without_a_csrf_token_is_refused`; M43 red |
| 300 per administrator per hour | PARTIAL | `item_transition.py:59-69`; `fulfillment/domain/limits.py:3-4` | Sharing tested through the cancel; the value and an STL 429 are not (M45, A-06). Works by probe P9 |
| Removes `src/app/digital_assets`, its test folders, stale VS-019 references | DONE | Directories absent; `grep "VS-019\|digital_assets" src tests` empty | `test_every_context_exists` |
| Legal edges are a pure table (ADR-039 d8) | DONE | `ordering/domain/line_transitions.py:37` | `test_line_transitions.py`, `test_every_stl_refusal_keeps_its_stable_reason` |

### "Tests" and "Done when" lines of the plan, and FR-12 cases

| Case | Status | Test |
|---|---|---|
| Only `awaiting_delivery` lines appear; a pending line never does | DONE | `test_only_awaiting_stl_lines_are_queued` |
| Delivered, refunded or physical lines give 409 | DONE | `test_a_line_that_is_not_awaiting_delivery…`, `test_an_unpaid_physical_line_is_a_409_and_stays_untouched` |
| Two admins, one line: one 200, one 409, one audit row and one email | DONE | `test_two_administrators_marking_one_line_sent_get_one_200_and_one_409`; effects `(1, 1, 1, 1)` |
| Customer 404, anonymous 401 on both routes | DONE | `test_both_routes_refuse_anonymous_customer_and_unverified_mfa` |
| Order `completed` when its only line is delivered | DONE | `test_marking_a_line_sent…` |
| End to end: register, buy, queue, mark sent, customer notified | DONE | `test_register_buy_queue_mark_sent_customer_notified` (stops at the outbox row, A-08) |
| Done when: no paid STL can be forgotten | DONE for filters and refunds; PARTIAL for paging | `test_only_awaiting…`, `test_i14…`, probe P6; the paging tie is untested (A-01) |
| Done when: every delivery records who and when, and the customer is notified | DONE | `test_marking_a_line_sent…` |
| FR-12 neg: unverified payment never queued, cannot be marked | DONE | `test_only_awaiting…`, `test_a_delivery_on_an_unpaid_line_is_never_recorded` |
| FR-12 neg: delivered or refunded cannot be marked again | DONE | `test_a_line_that_is_not_awaiting_delivery…`, `test_i14…` |
| FR-12 neg: refunded line leaves the queue, must not be sent | DONE | `test_only_awaiting…` (seeded), `test_i14…` (real refund refuses the delivery), probe P6 (real refund, queue) |
| FR-12 neg: non-administrators; customers 404 | DONE | `test_both_routes_refuse…`; route walks in `test_deep_vs005_admin_mfa.py` and `test_vs011_admin_boundary.py` |
| FR-12 neg: cannot buy an owned STL | DONE (VS-023) | VS-023's checkout tests; the slice adds no code there |
| FR-12 conc: marking and refunding lock the order, "exactly one succeeds" | DONE, wording Q-3 | `test_r4_a_full_stl_refund_racing_its_delivery`, `test_a_refund_that_commits_first_makes_the_delivery_a_409_that_writes_nothing` |
| FR-12 conc: two administrators, one record and one notification | DONE | Two-admins race above |
| FR-12 conc: parallel checkouts, one live line | DONE (VS-023) | `uq_order_items_stl_ownership`; `test_checkout_races.py` |
| Mark-sent racing payment verification | DONE | `test_the_line_state_is_read_after_the_lock_not_before_it` |
| FR-12 failure: record, projection, audit and outbox commit atomically | DONE | `test_a_failing_notice_rolls_the_whole_delivery_back` |
| F-073 refunded line leaves the queue, F-083 paid line enters, F-089 queue and mark | DONE | As above; F-083 through the e2e's real verification |
| INV-04, INV-05, BR-057 | DONE | `not_awaiting_delivery` refusal; `public.py:287-312`; e2e |

## 5. Definition of Done

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Cycle above; one head; `test_every_migration_step_goes_down_and_up_with_data_present` passes. The re-seed has no test (A-07) |
| Rules in the owning context; others through ports | Met | Fulfillment holds the use case and routes; Ordering every `order_items` write; imports through `app.ordering.public`, `app.payments.public`, `app.platform.public`; `test_deep_architecture.py`, `test_order_item_writers.py` |
| Auth, verified email, 404 on foreign ids, admin boundary, CSRF, rate limits | Met in code, one test gap | Boundary and CSRF mutations killed; foreign item 404 tested. `GET` has no rate limit, like the other admin reads, and none is specified. The POST's value is unpinned (A-06). Verified email is not applicable to an admin route |
| Money in cents; UTC; server computes status | Met | `line_total_cents`, `currency`; `fulfilled_at` from `datetime.now(UTC)`; status through `recompute_order_status` only; a client sends only `target_status` |
| Audit, notification, outbox in the same transaction | Met | `test_a_failing_notice_rolls_the_whole_delivery_back` |
| Background jobs registered, idempotent, tested | Not applicable, with one gap | No new job. `dispatch_outbox` is reused and tested generally, not on this template (A-08) |
| Unit, PG integration, API errors and IDOR, a race test for every known race | Met | Unit table, real PostgreSQL through testcontainers, three real races. See test strength below |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Partly | CI green. "No paid STL can be forgotten" is not covered for tied paging (A-01) |
| Docs and OpenAPI updated; Status Done | Partly | Plan and README say Done; OpenAPI snapshot test passes. A-02, A-03 and A-10 record what drifted |

**Test strength.**

- `caplog`: none in the slice's tests (`grep -c` gives 0), so the `configure_logging()` weakness does not apply.
- Race tests: `test_stl_delivery_races.py` does not use `meet_or_fail` (`grep -c` gives 0). It holds the `orders` row in a third connection and uses `wait_for_lock_waiters` until `pg_stat_activity` shows the racers blocked, then releases. That is deterministic and stronger for this lock, as M01 and M49 being killed shows. Not a finding.
- `test_a_delivery_on_an_unpaid_line_is_never_recorded` sits in the race file but has no race. Harmless.
- The mark-sent-versus-refund race in that file uses a raw-SQL stand-in for the refund. `test_r4_a_full_stl_refund_racing_its_delivery` covers the real path in both orders.
- Timing: no timing claim in this slice.

## 6. Findings

No Critical findings. A-01 is the only Major, and it is a test gap. All ten are fixed; each row states the finding as audited, and the proof is in section 3's re-run.

| ID | Severity | Location | What is wrong | Impact | Concrete fix | Slice |
|---|---|---|---|---|---|---|
| A-01 | Major; **fixed** | `tests/integration/fulfillment/test_stl_delivery_api.py:73-96`; `ordering/infrastructure/orders.py:471, 473` | Nothing tests paging across a `created_at` tie. The test's stamps `(5, 1, 3, 3, 2)` with `limit=2` always put the two tied lines on one page, so M31 and M33 survive. **Reproduced:** P11, a real checkout of two STLs gives both lines the same `created_at`, so ties are normal for any multi-STL order, not rare | The code is correct today. A regression such as M33 silently drops an STL from the next page: the customer paid, the queue no longer shows it and nothing fails. That is the slice's first "Done when" | Add a test from one real checkout of two STL products that pages with `limit=1` and expects both ids (the P11 shape, which fails under M33). Also change the existing test to `limit=3` so the tie splits | VS-023b, test only |
| A-02 | Minor; **fixed** | `ordering/public.py:419, 422`; `fulfillment/application/transition_line.py:54`; contract at `docs/stl-delivery.md:32` and `item_transition.py:82-87` | The STL refusals `already_delivered`, `line_closed`, `not_awaiting_delivery` and `cancel_reason_not_allowed` carry no `fulfillment_status`, although both the doc and the OpenAPI description promise it. Only `not_a_legal_edge` and the physical refusals set `current_status`. **Reproduced:** P1, P3 | A client built to the contract reads `undefined` on exactly these refusals. `reason` still lets it act, so no wrong state results | Pass `current_status=line.fulfillment_status.value` at `public.py:419, 422`, and raise the `cancel_reason` refusal after the line is read, or state the exception in the doc. Assert the field in the parametrised 409 test | VS-029's extension of the error |
| A-03 | Minor; **fixed** | `fulfillment/api/item_transition.py:49-51, 113`; `transition_line.py:69-80`; `ordering/public.py:423-433` | The request's `reason`, described in OpenAPI as "A note kept in the status history", is dropped on an STL delivery: `transition_line` does not pass `note` to `deliver_stl_line`. The physical path keeps it. **Reproduced:** P2 (NULL), P2b (kept) | The administrator gets 200 and the note is lost. ADR-019 expects such notes: an oversized bundle may go by cloud link, which is what someone would record here | Thread `note` through `deliver_stl_line` and `mark_stl_line_delivered` into `StatusChange` and the audit `after_data`, as the physical path does. Assert it. Alternative: refuse a note on STL and document that | VS-029's shared endpoint |
| A-04 | Minor; **fixed** | `test_stl_delivery_api.py`, `test_marking_a_line_sent_writes_every_record_once`; `mark_stl_delivered.py:69-85`; `delivery_side.py:239-245`; `orders.py:334` | Payload content is mostly unasserted. M18 (`before_data`), M19 and M20 (`after_data` keys), M24 (`product_name`, a field of `docs/notification-contract.md:63`) and M05 (`updated_at`) all survive | BR-132's audit row could lose its content, or the in-app notice its product name, with the suite green | Assert `before_data`, the exact `after_data`, the exact notification and outbox payloads, and `updated_at` | VS-023b, test only |
| A-05 | Minor; **fixed** | `fulfillment/api/stl_deliveries.py:60-62, 83-85`; `orders.py:466-467`; `test_a_bad_cursor_is_a_422` | Queue input guards are untested. M28 (`product_id`), M35 and M36 (`limit` bounds), M37 (naive cursor, plan section 6 [M]) and M38 survive. Without the M38 guard a year-1 cursor raises asyncpg `DataError`. The behaviour is right today (P4) | A regression returns the wrong subset or an unbounded page, or a crafted cursor raises a server error. Admin-only, so low exposure | Parametrise the cursor test with a naive and an out-of-range time; add `limit` 0 and 101; add a `product_id` subset test | VS-023b, test only |
| A-06 | Minor; **fixed** | `item_transition.py:59-69`; `limits.py:3-4`; `test_cancel_api.py:96-113` | Nothing pins the documented 300 per hour, or shows the transition route itself answering 429. M45 survives because the one test compares against the constant and only reaches 429 on the cancel. Works by probe P9 | The limit can be raised or disabled by accident. The rule on the catalogue routes already has a pinning test | Add a transition test with the counter at the limit that expects 429 and `Retry-After`, and assert `STL_DELIVERY_RATE_LIMIT == 300` | VS-023b, test only |
| A-07 | Minor; **fixed** | `7a1c3e9b5d24_…py:58-62` | The downgrade's re-seed has no test, although plan section 6 marks it [M]. M53 survives both the schema tests and the per-step down/up test. It works in the manual cycle above | A broken re-seed would surface only on a real rollback | Assert in a migration test that `daily_download_cap` returns with `integer`, `20` after the downgrade | VS-023b, test only |
| A-08 | Minor; **fixed** | `tests/e2e/test_vs023b_stl_delivery.py`; `test_stl_delivery_api.py` | The plan's [M] tests "`dispatch_outbox` sends one email" and "zero sends until `dispatch_outbox` runs" were not built: `grep dispatch_outbox` over the slice's three test files gives 0. The e2e stops at the outbox row. Works by probe P5 | `order_stl_delivered` reaching the provider is unproven by the suite, though the job is tested on other templates | Run `dispatch_outbox` with a spy provider in the e2e and assert one send, its address and payload | VS-023b, test only |
| A-09 | Minor; **fixed** | `fulfillment/application/mark_stl_delivered.py:22-49` | `mark_stl_delivered` is dead code: `grep -rn "mark_stl_delivered\b" src tests` finds only its definition and the module path. Since VS-029, `transition_line` takes the lock itself and calls `deliver_stl_line` | A second, unused entry point to a money-adjacent write, which a later change may fix or call by mistake | Delete the function; keep `deliver_stl_line` and rename the module if wanted | VS-029's refactor |
| A-10 | Minor; **fixed** | `docs/stl-delivery.md:32, 50-52`; `docs/notification-contract.md:67-71` | Docs drifted. The "For VS-030" section still instructs VS-030 to replace a stop-gap it already replaced (plan's as-built note, ADR-042 d9). The 409 row omits `cancel_reason_not_allowed` (P3). The contract's email list omits `order_stl_delivered` (`grep` empty), though it lists the others | Misleads the next reader, and VS-021, which builds real email templates from that list | Delete the section, add the reason, and add `order_stl_delivered` with `order_id`, `order_number`, `item_id`, `product_name` | Docs |

## 7. Open questions

- **Q-1, one unreproduced end-to-end red (open; no decision needed).** `test_register_buy_queue_mark_sent_customer_notified` failed once, in the first M03 run; the driver did not yet keep output, so the error is lost. M03 was then green, and six runs alone and eight in sequence with the delivery tests were all green, as was every later run reaching it. CI is green. It is not a finding, because it was not reproduced. One structural note: the test uses `customer` again at line 112 after a nested `admin_client` closes at line 100, a pattern that has mixed event loops before in this repo. Recommendation: open the clients one after the other when next touching this test. Done with A-08; the failure itself stays unexplained.
- **Q-2, deactivated buyer (decided, owner 2026-11-04: keep the email; [ADR-039](../adr/ADR-039-stl-delivery-workflow.md) d11, locked by a test).** P8: a deactivated customer's paid line stays in the queue, and marking it sent still emails them. SRS line 1019 and ADR-035 d10 exclude deactivated customers only from the four offer emails, and the SRS is silent on this one. Recommendation: keep it, since the file was paid for and the email says it was sent. The owner should confirm.
- **Q-3, FR-12's "exactly one succeeds" (decided, owner 2026-11-04: reworded in `functional-requirements.md`, and in the same claim at `api-endpoints.md`, `database-design.md` and the VS-030 plan entry).** `functional-requirements.md:674` says of marking delivered and refunding that exactly one succeeds. `test_r4_a_full_stl_refund_racing_its_delivery` and SRS 10.4 and 20.3 say otherwise when the delivery goes first: both succeed, because `delivered -> refunded` is legal and the file simply cannot be recalled. Only the order "refund first" refuses the other. The code follows the SRS, which wins. Recommendation: reword the FR line to "the two are serialised; a line refunded first cannot then be delivered".
- **Q-4, queue reads and the audit log (decided, owner 2026-11-04: covered; added to [ADR-040](../adr/ADR-040-admin-order-queue-fulfillment-and-cash-handover.md) d12).** The queue shows customer email and writes no `*.list_viewed` row. ADR-040 d12 decides this for "the queue, the detail and the cash-block list" of admin orders and does not name the STL queue. Recommendation: treat it as covered, and add the STL queue to that sentence.
- **Q-5, from the fixes' money review (decided, owner 2026-11-05: added to [ADR-047](../adr/ADR-047-account-deletion-by-anonymisation.md)'s list, docs only; the text stays in the audit rows).** An STL note now sits as text in the permanent `audit_logs` row (ADR-039 d12), as physical steps and the handover already do, while the cancel audits `has_note` only. An administrator could type personal data into it. ADR-047's "Not reached by the scrub" list does not name admin notes in audit rows.
- **Q-6, from the fixes' SRS review (open).** On a paid physical `-> cancelled`, the `refund_exceeds_available` refusal carries no `fulfillment_status` (`fulfillment/api/admin_orders.py:343`), although the route's OpenAPI text promises it. STL lines refuse `cancelled` first, so A-02 does not reach it, and it predates this audit. Recommendation: add the field in a physical-fulfillment change, which needs the line passed to `cancel_refusal`.

## 8. How the commands were run

- `.venv/Scripts/` binaries from the repo root in Git Bash, on the real checkout for `ruff`, `mypy`, `alembic heads` and the suites in section 3, with `-p no:cacheprovider`. Output was redirected to files and exit codes read directly, never through a pipe.
- Docker Desktop was started for testcontainers (`postgres:16`, `redis:7-alpine`). The compose stack stayed down. Available memory stayed between 1.7 and 3.9 GB.
- Scratch copy: `git archive HEAD | tar -x`, outside the repo. It has no `.env`: the repo's hook blocks that path, so a small wrapper loaded `.env.example`'s placeholders (what CI copies) into the process environment and set `PYTHONPATH` to the copy's `src`.
- Mutations: one Python driver applied one exact-match replacement (asserted to match once), ran the target with `-x`, restored the file and appended the result, in foreground batches of under 10 minutes. Re-runs on wider tests applied survivors together: a green result means each survives there, and a red one was split to single mutations. `M03` with `M04`, and `M35` with `M36`, patch the same text, so those were run apart. After the runs, each mutated file on the copy was compared to `git show HEAD:<file>`: identical.
- Migration cycle: `alembic upgrade` and `downgrade` from the scratch copy against a throwaway `postgres:16`, read back through `pg_indexes`, `settings` and `alembic_version`.
- Full suite: from GitHub CI (`gh run view 41609443385`, `gh run view 41748380843`), never locally.
