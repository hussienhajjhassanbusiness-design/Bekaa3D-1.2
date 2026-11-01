# VS-030 audit: refunds and settlement

Independent, read-only audit. Auditor date: 2026-11-01. Tree audited: `main` @ `fbd5872` (clean). VS-030 landed in three PRs, all ancestors of this commit; later slices (VS-031 to VS-050) built on it, so the audit covers VS-030's code as it stands today. No source, test, migration or status file was changed. Mutations ran only on a `git archive fbd5872` copy in the session scratchpad.

## 1. Verdict

**Yes.** VS-030 is a trustworthy base. **All six findings are fixed on branch `fix/vs030-audit-findings`, tests and docs only (§9).** Its money rules are right and well tested: every "Done when" line, and every slice test but one, had a passing test on real PostgreSQL. Concurrent refunds never pay out more than was paid (R1 and R2, through `meet_or_fail`). The lock order is checked at runtime (LO2, LO3). Every CHECK, FK and partial index in the migration refuses its row by name. Of 57 mutations, 44 turned a test red at audit time. They include every balance and payment cap, the cancellation rule, Q-2 on create, the orders-lock guard, the idempotency claim, the late-capture `ON CONFLICT`, chargeback absorption, D4 and every migration constraint. No Critical finding. One Major (A-01): the audit rows for settle, fail, reissue and a recorded chargeback were written but never asserted, so removing any of them left every suite green. The other survivors were Minor test gaps (A-02 to A-06): the refund rate limits, Q-2 on the chargeback path, re-buying an STL product after a full refund, the second guard of ADR-042 d10, and the integrity log line. One survivor, M55, turned out to be equivalent (§3). In each case the code did what the plan says; only the test that would catch a regression was missing. On the fix branch every non-equivalent survivor turns a test red. The open question (Q-1) is answered: intended, now ADR-042 d24.

## 2. Repo state

| Item | Finding |
|---|---|
| Branch / commit | `main` @ `fbd5872dc6de` ("VS-050: manual payment provider for production (ADR-049) (#55)") |
| Uncommitted / untracked | None at the start (`git status --short` empty). Afterwards the only untracked file is this report |
| On `main`? | Yes. PR #34 `326aa40` (cash-block search audit, docs), PR #37 merged as `7b346a4` (schema: `37a9c49`, `87e6ce6`, `874922d`, `18cb1ff`; migration `c01e53ab3e0f`), PR #38 `34af46d` (refund core), PR #39 `a873774` (late capture, backfill migration `80e56abf0969`, chargebacks, record-capture, docs) |
| Size (`3949bf1^..a873774`, src + tests + migrations) | 78 files, +10755 / -90 |
| Later commits touching the slice's core files | `7649b7d` VS-031 (cancellation refunds through `create_cancellation_refund` and `refund_balances`); VS-036, VS-043, VS-045 and VS-050 read refunds through `app.payments.public` without changing the refund rules |

## 3. Command results

| Command | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 1010 files already formatted |
| `mypy src tests` (strict) | PASS | 864 source files, no issues |
| `pytest tests/unit` | PASS | 2481 passed, 87.9 s |
| VS-030 integration, security, smoke, e2e (13 files: `test_refunds_api`, `test_refund_guards`, `test_refund_schema`, `test_refund_migration_precheck`, `test_chargebacks_api`, `test_chargeback_guards`, `test_late_capture_refunds`, `test_late_capture_backfill`, `test_record_capture`, `test_mixed_cancel_refunds`, `security/test_refund_records_never_leak`, `smoke/test_vs030_smoke`, `e2e/test_vs030_refunds`) | PASS | 162 passed, 156.8 s |
| VS-030 concurrency (`test_refund_races`, `test_chargeback_races`, `test_late_capture_races`, `test_refund_lock_order`) | PASS | 40 passed, 115.2 s |
| Existing suites for code the slice changed (`fulfillment/test_stl_delivery_api`, `fulfillment/test_transition_refund_facts`, `ordering/test_cash_block_search_audit`, `ordering/test_order_history_api`, `payments/test_payment_lock_order`, `test_model_migration_parity`, `test_migration_reversibility`, `test_deep_db_constraints_and_migrations`) | PASS | 92 passed, 115.2 s |
| Full suite | PASS (**CI, not local**) | Run `41319121894`, push to `main` on `fbd5872`, conclusion success: unit 2480 passed + 1 skipped; integration-payments-platform 620; integration-rest 1176; integration-ordering 496; integration-identity 674 (8 deselected); concurrency-security-e2e-smoke 592; integration-catalog-fulfillment 680. The VS-030 merges themselves were green on `main` too: `40014004192` (`7b346a4`), `40029662977` (`34af46d`), `40085087224` (`a873774`) |
| `alembic heads` | PASS | Exactly one head: `941b40d285ce` |
| upgrade head → downgrade `0f43e238eaae` (VS-030's parent) → upgrade head, throwaway `postgres:16` | PASS | At head: 66 objects (4 tables, 2 enum types, 18 indexes, the constraints of the 4 tables, and `fk_order_items_order_owner`, `uq_orders_id_user`, `uq_order_items_id_order`, `uq_payments_id_order_provider`). After downgrade: 0 of them. After re-upgrade: 66, byte-identical (`pg_indexes`, `pg_get_constraintdef`, `pg_type`). `uq_refunds_one_live_late_capture` is `UNIQUE (payment_id) WHERE kind = 'late_capture' AND status NOT IN ('failed','voided')`; `ix_refunds_obligations` is `(created_at, id) WHERE status = 'pending' OR (status = 'failed' AND reissued_at IS NULL)` |
| Committed `docs/frontend-handoff/openapi.json` vs `app.openapi()` | PASS | Identical. All 11 VS-030 routes declare 401, 403 (writes), 404, 409 (writes), 422 and 429 |

No `xfail` or `skip` in any VS-030 test file.

**Mutation results.** Target set (17 files): `test_refunds_api`, `test_refund_guards`, `test_refund_schema`, `test_chargebacks_api`, `test_chargeback_guards`, `test_late_capture_refunds`, `test_mixed_cancel_refunds`, `test_record_capture`, `e2e/test_vs030_refunds`, the four VS-030 concurrency files, and `ordering/test_cart_api`, `ordering/test_checkout_api`, `ordering/test_stl_ownership_api`, `ordering/test_cash_block_search_audit`. Baseline on the scratch copy: **278 passed**, 272.8 s. Each mutation first ran on its focused subset with `-x`. The 18 survivors were re-run on all 17 files (278 tests each). The domain and service ones (M04, M06-M10, M41) were also run on `tests/unit` (2481 tests).

| Mutation (scratch copy only) | Result |
|---|---|
| M01 line balance: `>` becomes `>=` (the exact balance refused) | RED: `test_i2_partial_then_rest_on_a_delivered_line_and_an_awaiting_stl` |
| M02 drop the payment-balance cap on the sum | RED: `test_i4_a_cash_payment_below_its_lines_caps_the_sum` |
| M03 drop `REFUND_REQUIRES_CANCELLATION` | RED: `test_a_full_refund_of_an_unfinished_line_needs_a_cancellation[pending]` |
| M04 an owed (failed, not reissued) refund stops reserving its balance | GREEN on the 17 files; RED in unit `test_which_refunds_count_against_the_balances[failed-False-True]` |
| M05 a bare-cancelled line keeps its full balance | RED: `test_i4_cash_is_capped_at_the_cash_recorded` |
| M06 `late_capture` refunds count in the status facts | GREEN on the 17 files (the payment filter, M07, also excludes them); RED in unit `test_a_late_capture_refund_never_counts` |
| M07 facts read every payment's refunds, not only the paid one's | GREEN on the 17 files (the kind filter, M06, also excludes them); RED in unit `test_only_the_paid_payments_refunds_and_chargebacks_make_the_facts` |
| M08 order status: owed checked after `all_cancelled` and `covers_paid` | GREEN on the 17 files; RED in unit `test_each_branch[pr8-case-b-all-cancelled-refund-owed]` |
| M09 Q-2: drop the line-sum clause | GREEN on the 17 files; RED in unit `test_a_cash_order_total_must_equal_its_lines_too` |
| M10 Q-2: drop the online payment = total clause | GREEN on the 17 files; RED in unit `test_an_online_payment_must_equal_the_order_total_and_cash_need_not` |
| M11 Q-2 never runs on create | RED: `test_i5_an_order_total_mismatch_writes_nothing_and_alerts` |
| M12 a partial refund already marks the line `refunded` | RED: `test_i1_create_on_a_paid_mixed_order` |
| M13 / M14 void ignores a `refunded` / `cancelled` line | RED: `test_i11_void_a_pending_partial` / `test_a_void_never_strands_the_money_of_a_cancelled_line` |
| M15 reissue does not mark the failed refund reissued | RED: `test_i9_a_failed_full_refund_stays_owed_until_reissued` |
| M16 settle runs the Q-2 check | RED: `test_settle_records_a_payout_even_when_the_totals_drifted` |
| M17 / M18 no "refund issued" notice at creation / at a late-capture settle | RED: `test_i1_create_on_a_paid_mixed_order` / `test_i15_the_admin_fails_reissues_and_settles_it_on_an_unpaid_order` |
| M19 no `refund.created` audit row | RED: `test_i1_create_on_a_paid_mixed_order` |
| **M20 / M21 / M22 no `refund.settled` / `refund.failed` / `refund.reissued` audit row** | **GREEN** on all 17 files (A-01) |
| M23 fail does not recompute the statuses | RED: `test_i9_a_failed_full_refund_stays_owed_until_reissued` |
| M24 refund facts read without the orders-lock guard | RED: `test_reading_refund_facts_without_the_orders_lock_is_refused` |
| M25 the orders-lock guard always passes | RED: same test |
| **M26 refund row read without `FOR UPDATE`** | **GREEN** on all 17 files (A-05) |
| **M27 state UPDATE without its source-status guard** | **GREEN** on all 17 files (A-05) |
| M28 obligations-queue filter dropped | RED: `test_i8_settle_changes_no_status_and_repeats` |
| M29 late-capture insert without `ON CONFLICT` | RED: `test_the_unique_index_is_the_last_guard_against_a_second_obligation` |
| M30 create skips the idempotency claim | RED: `test_i7_idempotency` |
| **M31 / M32 refund write / read rate limit removed** | **GREEN** on all 17 files (A-02) |
| M33 settle without CSRF | RED: `test_customers_get_404_admins_without_mfa_401_and_writes_need_csrf` |
| M34 Q-2 refusal raises no alert | RED: `test_i5_an_order_total_mismatch_writes_nothing_and_alerts` |
| M35 an unpaid order is no longer refused | RED: `test_i3_an_unpaid_order_is_not_refundable[online]` |
| M36 chargeback excess not capped by what is refundable | RED: `test_i17_after_a_settled_full_refund_the_whole_charge_is_excess_and_alerted` |
| M37 chargeback does not void open refunds | RED: `test_i17_a_pending_goodwill_refund_is_absorbed_and_payout_stays_within_paid` |
| M38 chargeback leaves an emptied unfinished line open (D4) | RED: `test_i18_d4_an_emptied_unfinished_line_is_cancelled_and_closed` |
| M39 chargeback items allowed on a late-captured attempt | RED: `test_i19_a_late_captured_attempt_absorbs_its_obligation` |
| M40 chargeback writes no remainder for a partly absorbed refund | RED: `test_c1_a_partial_charge_on_a_pending_full_refund_leaves_the_rest_owed` |
| **M41 chargeback skips Q-2** | **GREEN** on all 17 files and on `tests/unit` (A-03) |
| **M42 no `chargeback.recorded` audit row** | **GREEN** on all 17 files (A-01) |
| M43 the excess alert uses the plain `chargeback` kind | RED: `test_i17_after_a_settled_full_refund_the_whole_charge_is_excess_and_alerted` |
| M44 chargeback does not recompute the payment status | RED: `test_i17_a_pending_goodwill_refund_is_absorbed_and_payout_stays_within_paid` |
| **M45 open refunds read for a chargeback without `FOR UPDATE`** | **GREEN** on all 17 files (A-05) |
| M46 / M47 / M48 migration: no one-live-late-capture index / amount may be 0 / requester CHECK dropped | RED: `test_uq_refunds_one_live_late_capture` / `test_ck_refunds_amount` / `test_ck_refunds_requester` |
| M49 migration: line-owner FK not added | RED: `test_fk_order_items_order_owner_refuses_another_customers_line` |
| M50 migration: chargeback money CHECK dropped | RED: `test_ck_chargebacks_money[split-not-summing]` |
| M51 cash-block search not audited | RED: `test_a_search_is_audited_without_the_phone_or_its_hash` |
| M52 lock order: payments locked before the order | RED: `test_lo2_every_refund_path_locks_in_rank_order` |
| M53 a covered STL line never leaves `awaiting_delivery` | RED: `test_i2_partial_then_rest_on_a_delivered_line_and_an_awaiting_stl` |
| M54 a refunded STL line still counts as owned | RED: `test_i2_partial_then_rest_on_a_delivered_line_and_an_awaiting_stl` |
| M55 `refunded` added to `LIVE_STL_STATES` | GREEN on all 17 files. **Equivalent**, found while fixing A-04: `LIVE_STL_STATES` is read only after `uq_order_items_stl_ownership` has refused an insert, to name the products in the 409, and a refunded line never trips that index. The audit first listed M55 as A-04's evidence; M58 replaces it |
| **M58 `uq_order_items_stl_ownership` also covers `refunded` (migration and model together)** | **GREEN** on all 17 files plus `test_model_migration_parity` (280 tests) (A-04) |
| **M56 Q-2 refusal not logged as `refund_integrity_error`** | **GREEN** on all 17 files (A-06) |

Totals: 57 mutations (M58 added while fixing A-04), 44 RED (38 on the focused subsets, 6 more on `tests/unit`), 13 GREEN, of which M55 is equivalent. The other 12 are killed on the fix branch (§9). M04 and M06-M10 are caught only by unit tests. That is enough for pure domain rules, so it is not a finding.

## 4. Requirement checklist

Source: the VS-030 section of `docs/vertical-slice-plan.md`, ADR-042 d1-d23, SRS §9 refund text, BR-148, BR-149. File references are to `src/app/` unless stated.

| Requirement | Status | Where | Test |
|---|---|---|---|
| `refunds`, `refund_items`, `chargebacks`, `chargeback_items`; non-negative money; `refund_kind`, `refund_status` (with `voided`) | DONE | `migrations/versions/c01e53ab3e0f_refunds_and_chargebacks.py` | `test_refund_schema.py` (every CHECK, FK and index refuses its row by name), `test_model_migration_parity.py` |
| `requested_by` nullable only for `late_capture` | DONE | `ck_refunds_requester` | `test_refund_schema.py`; M48 |
| One live late-capture refund per payment | DONE | `uq_refunds_one_live_late_capture` | `test_the_unique_index_is_the_last_guard_against_a_second_obligation`, R9; M29, M46 |
| Obligations index | DONE | `ix_refunds_obligations` | schema test; queue via `refund_page` (`payments/infrastructure/refunds.py:354`) |
| A line's customer is its order's (`fk_order_items_order_owner`, validated) | DONE | migration `upgrade()`; precheck `_refuse_mismatched_lines` | `test_fk_order_items_order_owner_refuses_another_customers_line`, `test_refund_migration_precheck.py`; M49 |
| No `method` column, no provider refund call | DONE | No such column; the provider port has no refund method | `test_s3_the_provider_port_has_no_refund_method` |
| `POST /admin/orders/{id}/refunds` with required `Idempotency-Key`; list, get, settle, fail, reissue, void | DONE | `payments/api/admin_refunds.py:392-660` | `test_refunds_api.py`, `test_refund_guards.py`, `test_create_and_reissue_require_an_idempotency_key` |
| Idempotent replay; claim in the refund's transaction | DONE | `_idempotent` (`admin_refunds.py:355`) | `test_i7_idempotency`, R3 (same key in parallel); M30 |
| Lock order: orders, lines by id, payments by id, refund | DONE | `services/refunds.py:90-122`, `_locked_refund` `:328` | LO2 runtime lock-order tests, LO3 random workload; M52 |
| Refund facts read only under the orders lock (ADR-042 d9) | DONE | `require_order_lock` (`payments/infrastructure/order_lock.py`) | `test_reading_refund_facts_without_the_orders_lock_is_refused`, `test_another_orders_lock_does_not_count`; M24, M25 |
| Order total equals its lines (Q-2): 409, nothing written, alerted | DONE | `check_order_totals` (`payments/domain/refunds.py:212`), `_integrity_alert` (`admin_refunds.py:288`) | `test_i5_an_order_total_mismatch_writes_nothing_and_alerts`; unit `test_the_order_total_must_equal_its_lines`, `…online_payment_must_equal…`, `…currency…`; M09-M11, M34 |
| "…and is logged as an integrity error" | PARTIAL (fixed, §9) | `admin_refunds.py:293` logs `refund_integrity_error` | No test asserts the log line (the alert row is asserted); M56 |
| Paid lines only (BR-149); over-balance 422 `REFUND_EXCEEDS_AVAILABLE` | DONE | `check_request` (`domain/refunds.py:230`), `line_balances` `:191`, `payment_balance` `:204` | I3, I4, unit `test_exactly_the_balance_passes_and_one_cent_more_is_refused`, `…payment_balance_caps_the_sum…`; M01, M02, M35 |
| A cancelled cash line has 0 | DONE | `line_balances` bare-cancel rule | unit `test_a_bare_cancelled_line_and_a_refunded_line_have_no_balance`; M05 |
| Unfinished physical line to 0 → 422 `REFUND_REQUIRES_CANCELLATION`; partial succeeds | DONE | `check_request` | `test_a_full_refund_of_an_unfinished_line_needs_a_cancellation` (5 states), unit; M03 |
| Partial refunds keep the line state; full coverage makes it `refunded` | DONE | `lines_becoming_refunded` (`domain/refunds.py:265`) | I2 (delivered physical and awaiting STL), unit; M12, M53 |
| Fully refunded STL leaves the delivery queue and frees ownership; partial stays | DONE | `REFUNDABLE_WHEN_COVERED`; queue and ownership filter on line state | I2 (`stl_owned` before/after), `test_stl_delivery_api.py` (queue excludes `refunded`); M53, M54 |
| Failed refunds stay owed until reissued; reissue = same kind, items, amount | DONE | `fail_refund` `:412`, `reissue_refund` `:493`, `is_owed`/`is_counted` | I9, I10, R7; M04, M15, M23 |
| Status recomputed from refund records at create, fail, reissue, void; never on settle; late captures never count | DONE | `facts_for` (`domain/refunds.py:285`), `derive_order_status` (`ordering/domain/order_status.py:48`) | I8, I9, I12, unit `test_order_status_refunds.py`, `test_order_status_old_vs_new.py`; M06-M08, M16 |
| Cash refunded up to the cash recorded | DONE | `payment_balance` on the cash row; Q-2 exempts cash from payment = total | `test_i4_cash_is_capped_at_the_cash_recorded`, `test_i4_a_cash_payment_below_its_lines_caps_the_sum` |
| "Refund issued" email | DONE | `SqlRefundNotices` (`payments/infrastructure/refund_side.py`); admin and cancellation at creation, late capture at settle (Q7) | I1 (outbox count and payload), late-capture outbox count; M17, M18 |
| Audit rows for every refund action | PARTIAL (fixed, §9) | `_audit` calls in `services/refunds.py` | Only `refund.created` (I1) and `refund.voided` (I25) are asserted; settle, fail, reissue and `chargeback.recorded` are not (M20-M22, M42; A-01) |
| Cash-block phone search audited, never the phone or hash | DONE | `ordering/api/admin_cash_blocks.py:166-190` | `test_a_search_is_audited_without_the_phone_or_its_hash`; M51 |
| Automatic `late_capture` refund through `LateCaptureSink`, capped by `captured_amount_cents` | DONE | `SqlLateCaptureRefunds` (`payments/infrastructure/alerts.py:136`), `create_late_capture_refund` (`services/refunds.py:556`) | I15, `test_an_overpayment_on_a_live_attempt_is_owed_in_full`, Q6 cases |
| Backfill for older late captures | DONE | `80e56abf0969` | `test_i16_the_backfill_migration`, R9 backfill-vs-live race |
| Chargebacks: own tables, endpoint with `Idempotency-Key`, absorb open refunds, D4, excess alert | DONE | `payments/application/services/chargebacks.py`, `payments/domain/chargebacks.py`, `payments/api/admin_chargebacks.py` | `test_chargebacks_api.py` (I17-I19), `test_chargeback_races.py` (R8, R11-R13); M36-M45 |
| Rate limits: 60 writes, 300 reads per admin per hour | PARTIAL (fixed, §9) | `admin_refunds.py:198-215` | Only the constants are pinned (`tests/unit/payments/test_limits.py`); M31, M32 |

### Slice tests and "Done when" lines → tests

| Line | Test |
|---|---|
| Concurrent partial refunds never exceed the paid amount, online and cash | R1 `test_r1_concurrent_partials_never_exceed_the_paid_amount[online,cash]` (barrier: `meet_or_fail`) |
| Total ≠ sum of lines refuses and writes nothing; DB refuses a foreign `user_id` line | I5; `test_fk_order_items_order_owner_refuses_another_customers_line` |
| Two concurrent partials summing to the total both succeed; order `refunded` | R2 |
| Idempotent replay | I7, R3 |
| Partial then the rest, on a delivered physical line and an awaiting STL line | I2 (line states, ownership, final statuses). The intermediate `partially_refunded` is asserted in I12 and E1, not in I2 |
| Mark delivered on a partly refunded STL works; fully refunded gives 409 | I14 |
| Full refund of an unfinished physical line → 422; partial succeeds | `test_a_full_refund_of_an_unfinished_line_needs_a_cancellation` |
| A refunded STL awaiting delivery leaves the queue | I2 + `test_stl_delivery_api.py`; chargeback variant in `test_a_mixed_order_charged_back_in_full_after_a_partial_stl_refund` |
| Refund racing mark-delivered on one STL line: one wins | R4 (both orders) |
| A customer whose STL line was refunded in full can buy it again | **MISSING** at audit time. I2 asserts that ownership ends, but no test bought the product again; M58 survives (A-04). Fixed: `test_a_customer_whose_stl_line_was_refunded_in_full_can_buy_it_again` (§9) |
| Unpaid order 409, including unpaid cash | I3 `[online,cash]` |
| Refund racing a cash handover | R5 (both orders, 5 rounds each) |
| Cash refund capped at the cash recorded | I4 (two tests) |
| Late capture: one obligation, no items, no requester, ignored by the status; two provider events → one refund | I15, R9 (20 runs) |
| Failed `late_capture` refund reissued as `late_capture` | `test_i15_the_admin_fails_reissues_and_settles_it_on_an_unpaid_order` |
| Settling leaves both statuses unchanged | I8, `test_settle_records_a_payout_even_when_the_totals_drifted` |
| Failed refund owed, no line change, order `partially_refunded`, only reissue refunds it again, then leaves the queue | I9 |
| Two partials complete a line, the first fails: line stays `refunded`, failed amount owed, reissue restores | I10 |
| Mixed: STL refunded first, physical line then started, shipped, delivered (BR-148) | I13 |
| Mixed orders, four cases, asserting line states, refundable balances and order status | I12 asserts line states and statuses for all four. It does not assert the refundable balances; those are asserted in `test_the_admin_order_detail_lists_refunds_and_balances` and unit tests, not per case |
| Done when: no refund exceeds a line's or the payment's balance, touches an unpaid line, or empties an unfinished physical line | I3, I4, unfinished-line test, R1, R2, unit property test `test_no_sequence_of_refunds_pays_out_more_than_was_paid` |
| Done when: a line is `refunded` only when fully refunded | I2, unit `test_a_partial_refund_leaves_the_line_in_its_state`; M12 |
| Done when: no obligation leaves the queue until settled, reissued or voided | I8, I9, I11, E1, chargeback absorption tests |

## 5. Definition of Done

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Cycle in §3; per-step test `test_migration_reversibility.py`; backfill downgrade deletes only its own pending rows (I16) |
| Rules in the owning context; other contexts via ports | Met | Refund rules are in `payments/domain`; Ordering is reached through `app.ordering.public` (`lock_order_for_change`, `refund_lines`, `recompute_order_status`), Engagement through `create_notification`. `test_deep_architecture.py` passes in the unit run |
| Auth, verified email, ownership, admin boundary, CSRF, rate limits | Partly | Boundary and CSRF: `test_customers_get_404_admins_without_mfa_401_and_writes_need_csrf` and the OpenAPI-driven matrix (M33). Rate limits are wired but untested (A-02) |
| Money in cents; UTC; server computes every price and status | Met | `BigInteger` cents, `timestamptz`; amounts come from the request only as item amounts and are capped server-side; statuses only through `facts_for` and `derive_order_status` |
| Audit, notification and outbox in the same transaction | Met | One session per request (`_in_transaction`); the Q-2 alert is deliberately in its own transaction after the rollback (ADR-042 d12) |
| Background jobs | n/a | None new; the late-capture sink runs in VS-024's Tx B |
| Unit, PostgreSQL integration, API error/IDOR, a concurrency test per known race | Met | R1-R14, LO2, LO3, chargeback and late-capture races, all through `meet_or_fail` or an ordered `queued` start |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Met | §4; CI run `41319121894` |
| Docs and OpenAPI; Status Done | Met | `docs/refunds.md`, ADR-042 (Accepted), database-design, OpenAPI identical to the app; slice table and README say Done |

## 6. Findings

No Critical findings. One Major. All six are fixed on branch `fix/vs030-audit-findings` (§9).

| ID | Sev | Location | What is wrong | Why it matters | Suggested fix (not applied) | Scope |
|---|---|---|---|---|---|---|
| A-01 | Major | `payments/application/services/refunds.py:393` (`refund.settled`), `:433` (`refund.failed`), `:541` (`refund.reissued`); `payments/application/services/chargebacks.py:283` (`chargeback.recorded`) | Four money actions write an audit row that no test asserts. `grep -rn` over `tests/` finds none of the four action names. M20, M21, M22 and M42 each delete one call, and all 278 tests stay green | Settling, failing and reissuing refunds and recording chargebacks are the admin's money actions. The audit log is the only record of who did them, so a refactor could drop one silently. Same class as VS-010 A-04 | Assert the audit row (action, actor, target, and the amount or status in its details) in I8 (settle), I9 (fail, then reissue) and I17 (chargeback), as I1 already does for `refund.created` | VS-030 follow-up (tests only) |
| A-02 | Minor | `payments/api/admin_refunds.py:198-215` (`_limit`, `_WRITE_LIMIT`, `_READ_LIMIT`) | The limits of 60 writes and 300 reads per hour are wired on all 11 routes but never exercised. `tests/unit/payments/test_limits.py` pins only the constants. M31 and M32 each remove one dependency, and everything stays green | `docs/refunds.md` promises these limits, and the DoD lists rate limits. A route could lose its limit unnoticed | One integration test that lowers the limit (or seeds the Redis counter) and expects 429 on the next write and the next read | VS-030 follow-up (tests only) |
| A-03 | Minor | `payments/application/services/chargebacks.py:102` | Q-2 on the chargeback path is untested. No chargeback test seeds a drifted total. M41 skips the check, and every suite, unit included, stays green | On a drifted order, a chargeback would compute balances from wrong totals, and from them the absorbed and excess amounts. ADR-042 d18 relies on Q-2 to guard these | A test in `test_chargebacks_api.py` that drifts `orders.total_cents` on a paid order, records a chargeback and expects 409 `ORDER_TOTAL_MISMATCH`, nothing written and a `refund_integrity` alert | VS-030 follow-up (tests only) |
| A-04 | Minor | `migrations/versions/03a4730dd046_orders_payments_webhooks_idempotency.py:265` and `ordering/infrastructure/models.py:445` (the `uq_order_items_stl_ownership` predicate); `ordering/infrastructure/orders.py:36` (`OWNED_STATES`); `docs/vertical-slice-plan.md:830` | The slice test "A customer whose STL line was refunded in full can buy it again" does not exist. I2 asserts that ownership ends (`stl_owned`), but no test then adds the product to a cart and checks out again. M58 widens the ownership index to cover `refunded` lines, in the migration and the model together, and all 280 tests stay green, parity included. (The audit first cited M55, which is equivalent; see §3) | The behaviour is right today, but a regression in the index would stop a refunded customer from buying again, with a 409 at checkout, and no test would fail | Extend I2, or add a test: refund the STL line in full, then add the same product to the cart and check out, and expect both to succeed | VS-030 follow-up (tests only) |
| A-05 | Minor | `payments/infrastructure/refunds.py:74` (`FOR UPDATE` on the refund row), `:157` (UPDATE source-status guard in `_move`), `:225` (`FOR UPDATE` in `lock_open_for_payment`) | ADR-042 d10 says "Two guards back the state machine", but only the first (the decision on the locked row) is tested. M26, M27 and M45 each remove a second guard, and the race and lock-order suites stay green | Every path takes the orders lock first, so today these guards are redundant and no behaviour changes. They exist for a future path that skips the orders lock, and a test would keep them honest | A repository test that calls `_move` with a source state the row has already left and expects no row to be updated. If the guards are not meant to be kept, drop the claim from ADR-042 d10 | VS-030 follow-up (tests only) |
| A-06 | Minor | `payments/api/admin_refunds.py:294` | ADR-042 d12 says a Q-2 mismatch is logged as `refund_integrity_error`. I5 asserts the 409 and the alert row, but not the log line. M56 removes the log line and I5 stays green | The alert row is the durable signal, so the impact is small, but the log line is a stated requirement | Assert the log record in I5 with a capture that still works after `configure_logging()` (deep-test report, weakness 2) | VS-030 follow-up (tests only) |

## 7. Open questions

- **Q-1:** On a drifted order, settle still works (ADR-042 d23, C3), but fail, void and reissue answer 409 `ORDER_TOTAL_MISMATCH`. `test_settle_records_a_payout_even_when_the_totals_drifted` asserts that fail is refused. So if a payout bounces on a drifted order, the admin can neither record the failure nor void the refund until the order's data is repaired. Neither ADR-042 nor `docs/refunds.md` says how to repair it. Is that intended (repair the data by hand first), or should fail and void be exempt like settle, since neither pays anything out? **Answered by the owner (2026-11-01): intended.** When `refund_integrity_error` appears, the administrator stops and contacts the developer; the data is repaired by a reviewed fix, never by hand, and no repair tool is built. Recorded as ADR-042 d24 and runbook step 8 in `docs/refunds.md`.
- **Q-2:** The slice text asks I12 to assert "refundable balances" in each of the four mixed cases. I12 asserts the line states and order statuses. The balances are asserted elsewhere: in `test_the_admin_order_detail_lists_refunds_and_balances` and in the unit rules. §4 notes this rather than raising a finding. Given the SRS's call for heavy coverage of mixed-order partial refunds, the owner may want I12 to assert the balances in each case.

## 8. How the commands were run

- The repo's `.venv` (Python 3.13) ran everything. Integration and concurrency tests use their own testcontainers (`postgres:16`, Redis); Docker Desktop 29.2.1 was running.
- The full suite was **not** run locally (this machine runs out of memory); its result is CI run `41319121894` on the audited commit.
- Migration cycle: a throwaway `postgres:16` container on port 55447, `.env.example` exported into the environment and `DATABASE_URL` pointed at it; removed afterwards. No real or dev database was touched.
- Mutations: `git archive fbd5872` into the scratchpad, `.env.example` exported into the environment (as CI does with `cp .env.example .env`), `PYTHONPATH` set to the copy's `src` (checked: `app.__file__` resolved inside the copy). Each mutation was one exact-match text replacement (refused unless the pattern occurs exactly once), run with `pytest -x` on its focused tests, then the file was restored from memory before the next one.

## 9. Fixes (branch `fix/vs030-audit-findings`)

Tests and docs only; no source or migration changed. Each fix was checked by re-applying its mutation on the scratch copy with the new tests in place.

| Finding | Fix | Mutation after the fix |
|---|---|---|
| A-01 | I8 asserts the one `refund.settled` row (actor, `before_data`, `after_data`; the replayed settle writes none). I9 asserts `refund.failed` (with the reason) and `refund.reissued` (with `reissued_by_refund_id`). I17 (`…pending_goodwill_refund_is_absorbed…`) asserts the whole `chargeback.recorded` row. New helper `audit_rows` in `refund_support.py` | M20, M21, M22, M42: RED |
| A-02 | `test_the_refund_write_and_read_budgets_are_separate_and_enforced` (`test_refund_guards.py`) presets each Redis counter one short of its limit. The last write passes, then a create and a settle are 429 `RATE_LIMITED` and write nothing; with the write budget spent a read still passes, then a get and the queue are 429. `RateLimit-Limit` is checked against `limits.REFUND_WRITE_RATE_LIMIT` and `REFUND_READ_RATE_LIMIT` | M31, M32: RED |
| A-03 | `test_a_chargeback_on_a_drifted_order_writes_nothing_and_alerts` (`test_chargebacks_api.py`): 409 `ORDER_TOTAL_MISMATCH`, no chargeback, the open refund not absorbed, no idempotency claim, one `refund_integrity` alert, statuses unchanged | M41: RED |
| A-04 | `test_a_customer_whose_stl_line_was_refunded_in_full_can_buy_it_again` (`test_refunds_api.py`): after a full refund of the STL line, the customer adds the product to the cart and checks out (201, one new `pending` line) | M58: RED (checkout 409 `PRODUCT_ALREADY_OWNED`); M54: RED (cart 409); M55: still GREEN (equivalent) |
| A-05 | `test_a_state_update_matches_only_a_row_still_in_its_source_state`: on a settled refund, the store's `fail` and second `settle` match nothing and the row stays settled. `test_the_refund_rows_a_decision_reads_are_locked[lock, lock_open_for_payment]`: while each store method holds the row, another connection's `FOR UPDATE NOWAIT` is refused | M26, M45: RED. M27: RED, because without the guard `ck_refunds_state_stamps` refuses the row and the store raises instead of reporting no match (d10's last backstop) |
| A-06 | I5 captures the app's log handlers (the `app_logs` pattern from `test_deep_logs_and_leaks.py`, since `caplog` captures nothing after `configure_logging()`) and asserts one `refund_integrity_error` line at `error` level naming the order | M56 (`aerror` lowered to `ainfo`): RED |
| Q-1 | ADR-042 d24 and `docs/refunds.md` (Balances, runbook step 8): a Q-2 mismatch stops refund work on the order; the administrator contacts the developer; the data is repaired by a reviewed fix, never by hand; no repair tool | n/a |

Commands on the fix branch: `ruff check .` and `ruff format --check .` pass; `mypy src tests` passes (864 files); `pytest tests/unit` 2481 passed; `test_refunds_api.py`, `test_chargebacks_api.py` and `test_refund_guards.py` 67 passed. The full suite is left to CI on the pull request.
