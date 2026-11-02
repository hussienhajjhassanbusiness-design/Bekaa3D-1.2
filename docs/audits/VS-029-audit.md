# VS-029 audit: admin order queue, fulfillment and cash handover

Independent, read-only audit. Auditor date: 2026-11-02. Tree audited: `main` @ `c10f80e` (clean). No source, test, migration or status file was changed. Mutation experiments and probes ran only on a scratch copy (`git archive HEAD`) outside the repo.

**Update 2026-11-02:** A-01 to A-04, A-06, A-07 and A-08 are fixed on branch `fix/vs029-audit-findings`. A-05 stays as defensive code. Q-1 to Q-3 are decided. M43 to M46 have now run (§3, §6, §7).

## 1. Verdict

**Yes.** VS-029 is a trustworthy base for the slices built on it (VS-029b, VS-030, VS-031, VS-036, VS-043). Every "Done when" line and every test the slice plan lists has a test, and the guards that protect money hold under mutation: the `orders` lock, the BR-148 payment gate, the cash-handover-only rule, the handover's refusals and amount check, the one-cash-payment index and its translation, the queue predicate, the cash-due filter, the audit writes, the notices and the cash-block lock. 35 of the 42 mutations that ran were killed. Of the 7 survivors, one is a redundant backstop (M02); the other six are test gaps. I found **no Critical or Major issue**. The gaps are in how strong the tests are, and none of them is a live bug. The probes show that the three VS-029 rate limits, the BR-040 kill-switch exemption and the `completed_at` rule all behave correctly today, but no test would catch a regression in them (A-02, A-03, A-07). The only `one_live` → `already_recorded` mapping branch is untested (A-04). One test is planner-dependent and turned the VS-029 merge commit's own CI run on `main` red (A-01). Four mutations (M43 to M46) did not run in the first pass: the system's low-memory reaper stopped the driver (§8). **Update:** they ran on the fix branch. M44 and M45 were killed. M43 survives as an expected backstop and M46 is an equivalent mutant (§3). The new tests kill every earlier survivor except M06 (A-05, kept as defensive code) and M02 (the expected backstop).

## 2. Repo state

| Item | Finding |
|---|---|
| Current branch | `main` @ `c10f80e` ("VS-050 audit fixes …", #57) |
| Uncommitted/untracked | None at the start (`git status --short` empty). Afterwards the only new file is this report |
| VS-029 on `main`? | Yes: squash commit `4a5a545` (#33), 57 files, +12303/−5386 (most of it the regenerated `openapi.json`) |
| Migration | `b6e1d0c4a2f7_orders_cash_due_index.py` (revises `7a1c3e9b5d24`): `ix_orders_cash_due` and `ix_orders_admin_queue` |
| Later commits touching VS-029 code or tests | `34af46d`, `a873774` (VS-030), `7649b7d` (VS-031: cancel/return edges, `step_newly_reached`), `e313393`, `5087f82` (VS-036 badge hook), `7f94c0c` (VS-043), `4cd3d12` (VS-044), `16ab43e` (VS-045), `136669c` (VS-049), `fbd5872` (VS-050) |
| Earlier code it extends | `effa2b0` (VS-023b: transition endpoint, STL edge) |

## 3. Command results

| Tool | Result | Notes |
|---|---|---|
| `ruff check .` | PASS | "All checks passed!" |
| `ruff format --check .` | PASS | 1017 files already formatted |
| `mypy src tests` (strict) | PASS | 868 source files, no issues |
| `pytest tests/unit` | PASS | 2496 passed, 4 warnings, 117.8 s |
| Slice integration batch (8 files, list in §8) | PASS | **318 passed**, 319 s |
| Slice concurrency + e2e + smoke batch | PASS | **13 passed** (9 races, 2 e2e, 2 smoke), 26 s |
| Audit probes (scratch copy only) | PASS | 5 passed: P1 kill switch, P2 three rate limits, P3 a `returned` line blocks the handover |
| Full suite | PASS **(CI, not local)** | Run 41431194901 on `c10f80e` (audited tree): 2495 + 635 + 680 + 497 + 1176 + 674 + 593 = **6750 passed, 1 skipped, 8 deselected**, all 7 shards green |
| Full suite on the VS-029 merge commit `4a5a545` | **FAIL (CI)** | Run 39933621938: 1 failed, 5313 passed. The failure was `test_the_queue_query_uses_its_partial_index[filters1-ix_orders_cash_due]`: the planner chose `ix_orders_status_placed`. The branch runs before the merge (39902251207, 39928827026) and every later `main` run passed. See A-01 |
| `alembic heads` | PASS | Exactly one head: **`95ffee5fde3b`** |
| upgrade → downgrade → upgrade (throwaway `postgres:16` testcontainer) | PASS | See below |
| Committed `docs/frontend-handoff/openapi.json` vs `app.openapi()` | IDENTICAL | 120 paths, no path or schema differs |

**Migration probe** (`migcycle.py`, own container):

| Step | `ix_orders_cash_due` | `ix_orders_admin_queue` |
|---|---|---|
| `upgrade head` → `95ffee5fde3b` | `btree (placed_at DESC, id DESC) WHERE payment_method = 'cash' AND status = 'in_progress'` | `btree (placed_at DESC, id DESC) WHERE status <> 'pending_payment' AND (payment_method = 'cash' OR cancelled_at IS NULL)` |
| `downgrade 7a1c3e9b5d24` (23 revisions down) | gone | gone |
| `upgrade head` again | identical definition | identical definition |

### Mutation results

Each mutation was applied alone to the scratch copy, run against its target tests, then reverted. Baseline on the copy (every slice file plus VS-031's shared-limit test): **222 passed**, 241.7 s. Targets were narrowed per mutation to bound memory. A survivor counts as a finding only if no other test in the slice's files kills it either; I checked that for M13 by searching the whole `tests/` tree.

| # | Mutation (scratch copy only) | Result |
|---|---|---|
| M01 | drop `FOR UPDATE` on the `orders` row (`orders.py:248`) | RED (races) |
| M02 | drop `FOR UPDATE` on the lines (`orders.py:257`) | GREEN. Expected: every line writer already holds the `orders` lock (`test_order_item_writers.py` pins this), so the line lock is a backstop that no behaviour test can see |
| M03 | remove the BR-148 gate (`line_transitions.py:104-105`) | RED |
| M04 | remove `cash_handover_required` (`line_transitions.py:112-113`) | RED |
| M05 | allow a $0 handover (`handover.py:39`) | RED |
| **M06** | **drop the currency comparison (`public.py:520`)** | **GREEN (survives)**: A-05, kept as defensive code |
| M07 | remove the `already_recorded` refusal (`handover.py:30-31`) | RED |
| M08 | remove the IntegrityError → `CashAlreadyRecordedError` translation | RED |
| **M09** | **map only `uq_payments_one_cash` to `already_recorded`** | **GREEN (survives)**: A-04. **Fix branch: RED** (`test_a_second_cash_payment_reported_by_the_live_index_is_already_recorded`) |
| M10 | queue predicate without `cancelled_at IS NULL` | RED |
| M11 | queue predicate without `status <> 'pending_payment'` | RED |
| M12 | remove the `status=pending_payment` 422 | RED |
| **M13** | **`completed_at` overwritten on every completion (`orders.py:433`)** | **GREEN (survives)**: A-03. **Fix branch: RED** (`test_an_order_completed_again_keeps_its_first_completed_at`) |
| M14 | notice on any line reaching the step, not every line (`all` → `any`) | RED |
| M15 | `in_production` made a visible step | RED |
| M16 | skip the transition audit row | RED |
| M17 | skip the handover audit row | RED |
| M18 | skip the handover email and notification | RED |
| M19 | a second clear of a cleared block runs the clear again | RED |
| M20 | skip the `cash_block.cleared` audit row | RED |
| M21 | drop the cash-block `FOR UPDATE` | RED (race) |
| M22 | match blocks on the raw phone instead of its hash | RED |
| M23 | write the note text into the audit row | RED |
| M24 | `payment_due=false` filter ignored | RED |
| M25 | cash-due filter without `status = 'in_progress'` | RED |
| M26 | the handover also moves cancelled lines | RED |
| M27 | `amount_due_cents` counts cancelled lines | RED |
| **M28** | **remove the handover rate limit** | **GREEN (survives)**: A-02. **Fix branch: RED** (`test_the_handover_has_its_own_hourly_limit`) |
| **M29** | **remove the note rate limit** | **GREEN (survives)**: A-02. **Fix branch: RED** (`test_the_note_has_its_own_hourly_limit`) |
| **M30** | **remove the cash-block search rate limit** | **GREEN (survives)**: A-02. **Fix branch: RED** (`test_search_and_clear_share_one_hourly_limit`) |
| M31 | remove the transition rate limit | RED (VS-031's shared-limit test) |
| M32 | remove CSRF on the handover | RED |
| M33 | `reached_paid = True` in the transition use case | RED |
| M34 | stop hiding `in_production` from the customer | RED |
| M35 | the migration creates neither index (the mutation skipped both) | RED (EXPLAIN test) |
| M36 | wait for cancelled and refunded lines before a notice | RED |
| M37 | drop the delivery-fee note from step emails | RED |
| M38 | drop the pickup address from "ready for pickup" | RED |
| M39 | never return `next_cursor` | RED |
| M40 | cursor `<` → `<=` (repeats a row) | RED |
| M41 | handover accepts a partly ready order (`any` → `all`) | RED |
| M42 | cash-block `active=false` filter returns active blocks | RED |
| M43 | `move_line` without its `from_status` guard (fix branch, light run) | GREEN. Expected: every caller decides on the state it read under the `orders` lock, so the guard is a backstop no behaviour test can see (like M02) |
| M44 | the handover accepts an online order (`not_a_cash_order` dropped) | RED |
| M45 | a notice on every transition (`step_reached` bypassed) | RED |
| M46 | note PATCH on an unknown order without its own 404 | GREEN. Equivalent mutant: `order_detail` still answers 404 and the request rolls back, audit row included, so response and database are the same |
| M47 | a direct `status` write added to `set_admin_note` (fix branch) | RED (`test_order_status_writer.py`, A-06) |
| M48 | remove the cash-block clear rate limit (fix branch) | RED (`test_search_and_clear_share_one_hourly_limit`) |

## 4. Requirement checklist

| Requirement (plan, ADR-040, SRS) | Status | Code | Test |
|---|---|---|---|
| Migration: partial index for the cash-due filter, shaped by `EXPLAIN`; other queue indexes only if `EXPLAIN` shows a need | DONE | `b6e1d0c4a2f7`; `admin_orders.py:80, 91` | `test_admin_order_queue_api.py::test_the_queue_query_uses_its_partial_index` (both indexes; M35 red). Flaky: A-01 |
| `GET /admin/orders` with `payment_method` and `payment_due` filters, keyset paging, newest first | DONE | `fulfillment/api/admin_orders.py:155-201`; `ordering/infrastructure/admin_orders.py:85-111` | `test_each_filter_narrows_the_queue`, `test_the_queue_pages_newest_first_without_gaps` (M24, M25, M39, M40 red) |
| The queue never lists a `pending_payment` (or released) online order; `status=pending_payment` is a 422 | DONE | `models.py:37-39`; `admin_orders.py:176` | `test_the_queue_never_lists_an_unpaid_online_order`, `test_the_pending_payment_status_filter_is_a_validation_error` (M10, M11, M12 red) |
| `GET /admin/orders/{id}` (`AdminOrderDetail`), any order, no actions on an unpaid online order | DONE | `admin_order_detail.py`; `admin_orders.py:94-140` | `test_the_detail_shows_what_only_the_administrator_may_see`, `test_an_unknown_order_is_a_404`, unpaid case inside the queue test |
| `PATCH` edits the internal note only; audit `has_note` only | DONE | `admin_orders.py:217-251`; `admin_order_schemas.py:297-305` | `test_the_note_is_set_cleared_and_audited_without_its_text` (M23 red), `test_only_the_note_can_be_patched`, `test_a_patch_needs_csrf_and_an_existing_order` |
| Transition endpoint gets the physical edges (delivery and pickup tables) | DONE | `line_transitions.py:36-49` | `test_each_legal_edge_moves_the_line_and_lists_the_next_one` (2×2 methods), unit `test_paid_online_delivery_and_pickup_edges` |
| BR-148: no physical work on an unpaid online order (409 `payment_required`) | DONE | `line_transitions.py:104-105`; `transition_line.py:82` | `test_no_physical_work_on_an_unpaid_online_order` (4 payment states), `test_every_payment_state_that_reached_paid_opens_the_gate` (M03, M33 red) |
| Lock order: `orders`, then lines, then the status recompute; side effects in the same transaction | DONE | `public.py:228-234`; `orders.py:248, 257` | races (M01 red); `test_a_failing_notice_rolls_the_transition_back`; static `test_physical_edges_are_written_only_under_the_orders_lock` |
| `in_production` silent, masked as `pending`, absent from history; `can_cancel` false once printing starts | DONE | `fulfillment_steps.py:26-29`; `customer_view.py:16` | `test_start_printing_is_silent_masked_and_closes_self_cancel` (M15, M34 red) |
| `can_cancel` false for an STL-only order and an unpaid online order | DONE | `customer_view.py` | unit `test_can_cancel_is_false_when_one_condition_fails[stl-only, online-never-paid, pending-payment]` |
| One notice per order per visible step, on the last live line; cancelled lines not waited for | DONE | `fulfillment_steps.py:35-42`; `transition_line.py:110-116` | `test_a_three_line_delivery_order_hears_once_per_step_on_the_last_line`, `test_cancelled_lines_are_not_waited_for` (M14, M36 red) |
| Pickup notice carries the address and hours; delivery notices carry the courier fee note | DONE | `delivery_side.py:296-312` | `test_a_pickup_order_is_told_the_workshop_address_and_hours` (M38 red), three-line test (M37 red) |
| On a cash order the endpoint refuses `→ delivered` / `→ picked_up` | DONE | `line_transitions.py:112-113` | `test_a_cash_order_reaches_its_last_step_only_through_the_handover` (M04 red) |
| Handover: order lock, then every line by id | DONE | `record_cash_handover.py:41`; `public.py:228` | races (M01 red) |
| Handover: at least one live line, every live line ready, else 409 (reasons in order) | DONE | `handover.py:21-35` | `test_a_line_not_yet_ready_is_a_409_and_changes_nothing` (5 cases), `test_an_online_order_and_an_order_with_no_live_line_are_refused`, unit `test_each_refusal_has_its_reason` (M07, M41 red). M44 not run |
| Handover: amount equals the live total and is above zero, else 422 `CASH_AMOUNT_MISMATCH` with `amount_due` | DONE | `handover.py:37-39`; `public.py:511-524` | `test_a_wrong_amount_is_a_422_and_changes_nothing`, `test_the_amount_due_leaves_out_cancelled_lines`, `test_a_zero_total_order_takes_no_handover` (M05, M27 red). Currency branch: A-05 |
| Handover: one `paid` cash payment with `recorded_by`, `verified_at`; unique index the final guard | DONE | `cash_payments.py:26-58` | `test_the_handover_completes_the_order_with_one_paid_cash_payment`, `test_a_second_cash_payment_is_refused_by_the_index`, `test_the_index_alone_refuses_a_second_cash_payment_from_two_unlocked_writers` (M08 red). `one_live` mapping: A-04 |
| Handover: status recompute, history, audit, notification, email with cash receipt | DONE | `public.py:527-570`; `record_cash_handover.py:50-69` | handover test above (M17, M18, M26 red) |
| Delivered / picked-up email links "I got it" / "Report a problem" to the order page | DONE | `delivery_side.py:305` (`receipt_actions`) | three-line test (`receipt_actions == [False, False, True]`), handover test |
| `completed_at` written the first time only (ADR-040 d5) | DONE (fix branch) | `orders.py:433` | `test_an_order_completed_again_keeps_its_first_completed_at` (complete, refund, void, date unchanged; M13 red). Was PARTIAL: A-03 |
| Cash blocks: list (customer, active), search by phone in the body (hashed), clear (audited, idempotent) | DONE | `admin_cash_blocks.py`; `cash.py:94-129` | `test_the_list_filters_by_customer_and_by_active`, `test_search_matches_any_spelling_of_the_phone`, `test_clearing_is_audited_and_a_second_clear_changes_nothing`, `test_two_administrators_clearing_one_block_write_one_audit_row` (M19-M22, M42 red) |
| Clearing restores cash at checkout for that customer and phone | DONE | — | `test_after_clearing_checkout_offers_cash_again_by_account_and_phone` |
| `available_actions` from the same table, BR-148 and the cash rule included; never in customer responses | DONE | `line_transitions.py:126-137`; `admin_order_detail.py:44-60` | `test_every_listed_action_succeeds_and_every_other_target_is_a_409` (2 × 6 × 10 = 120 cases), `test_an_stl_line_lists_only_its_own_edge`, masking test |
| Limits: transitions 300, handover 60, note 120, block search and clear 60 | DONE (fix branch) | `limits.py`; `admin_orders.py:222, 260`; `admin_cash_blocks.py:151, 197` | Transitions: VS-031's `test_the_admin_cancel_shares_the_transition_rate_limit` (M31 red). `test_the_handover_has_its_own_hourly_limit`, `test_the_note_has_its_own_hourly_limit`, `test_search_and_clear_share_one_hourly_limit` (M28-M30, M48 red). Was PARTIAL: A-02 |
| BR-040: the kill switch never blocks a handover | DONE (fix branch) | no gate in the code (correct) | `test_closing_the_shop_never_blocks_a_handover_or_a_transition`. Was PARTIAL: A-07 |
| Admin boundary (anonymous 401, customer 404, admin without MFA 401), CSRF | DONE | `AdminBoundaryRoute`, `require_csrf` | `test_customers_anonymous_and_admins_without_mfa_never_reach_a_transition`, `test_customers_anonymous_csrf_and_unknown_orders` (M32 red), `test_a_customer_gets_404_and_anonymous_401_on_every_route`, `test_vs011_admin_boundary.py`, `test_openapi_security.py::VS029_ROUTES` |

### "Done when" and the plan's test list → tests

| Case | Test |
|---|---|
| Every legal and illegal edge, per fulfillment method and payment method | `test_each_legal_edge_…` (4 combinations), `test_skipped_cross_method_and_later_slice_edges_are_409s`, the 120-case `available_actions` test, unit `test_line_transitions.py` |
| Start printing on a `pending_payment` online order is a 409, and the order is never in the queue | `test_no_physical_work_on_an_unpaid_online_order`, `test_the_queue_never_lists_an_unpaid_online_order` |
| `in_production`: no email, no notification, shown as `pending`, not in history; `can_cancel` false | `test_start_printing_is_silent_masked_and_closes_self_cancel`, e2e `test_a_cash_pickup_order_is_printed_handed_over_and_completed` |
| Two admins on the same state: one wins | `test_two_administrators_making_one_transition_get_one_200_and_one_409` (side effects counted: 1,1,1,1,0) |
| Wrong amount: 422, nothing changed | `test_a_wrong_amount_is_a_422_and_changes_nothing` (`effects == (0,0,0,0,0)`) |
| Line not yet shipped: 409 | `test_a_line_not_yet_ready_is_a_409_and_changes_nothing` |
| Two admins, one handover: one payment, one audit row, one email | `test_two_administrators_recording_one_handover_record_one_payment` |
| Handover racing a transition on another line: one winner, no deadlock | `test_a_handover_racing_a_transition_on_another_line_has_one_outcome[handover, transition]` |
| `reconcile_payments` beside a handover or a transition: no deadlock, both correct | `test_a_reconcile_run_racing_a_transition_on_an_unpaid_online_order[reconcile, transition]`, `test_a_reconcile_run_never_waits_on_a_cash_order_being_handed_over` |
| A cash order reaches `completed` through the handover, paid for exactly the live total | handover test, `test_the_amount_due_leaves_out_cancelled_lines`, e2e |
| Cash blocks (seeded): customer 404, audited clear, idempotent second clear, cash again afterwards | cash-block tests above |
| An email-provider outage does not block a transition | `test_an_email_outage_does_not_block_a_transition` (the outbox row stays `pending`, `attempt_count = 1`) |
| The internal note is never visible to the customer | `test_the_internal_note_is_never_visible_to_the_customer` |
| Done when: no route sets `order.status` directly | `tests/unit/ordering/test_order_status_writer.py` (fix branch, A-06): `set_order_status` is the only `orders.status` UPDATE and `recompute_order_status` its only caller (M47 red) |
| Done when: no route but the handover creates a cash payment | `tests/unit/payments/test_cash_payment_writers.py::test_only_the_handover_route_reaches_the_cash_insert_and_the_paid_lines`, `test_every_payments_insert_is_known` |
| Done when: no physical line of an unpaid online order moves, except the hold release | BR-148 tests above; static `test_physical_edges_are_written_only_under_the_orders_lock` |
| Done when: a physical order reaches `completed` with either payment method | e2e `test_a_cash_pickup_order_…`, `test_a_delivery_order_paid_online_is_moved_to_delivered_and_completed` |

## 5. Definition of Done

| Checkbox | Met? | Evidence |
|---|---|---|
| Migration reviewed, reversible, one head | Met | Cycle above; single head `95ffee5fde3b`; `downgrade()` drops both indexes |
| Rules in the owning context; other contexts only via ports | Met | Fulfillment owns no table and writes through `ordering.public` and `payments.public` (ADR-040 d7). `test_deep_architecture.py` passes in the unit run. The cash-block router (`ordering/api`) imports `ordering.infrastructure` directly, which is the same context |
| Auth, verified email, 404 on foreign ids, admin boundary, CSRF, rate limits | Met (code) / Partly (tests) | Boundary and CSRF tested; a foreign line is a 404 (`test_a_transition_needs_csrf_and_a_foreign_line_is_a_404`). Three rate limits untested (A-02). Verified email is n/a for admin routes |
| Money in cents; UTC; the server computes every price and status | Met | The handover compares the typed amount and never uses it as the payment amount: it writes `due` (`record_cash_handover.py:44`). Status only through `recompute_order_status` |
| Audit, notification and outbox in the same transaction | Met | `test_a_failing_notice_rolls_the_transition_back`; every refusal test asserts `effects == (0,0,0,0,0)`; the handover INSERT runs in a SAVEPOINT inside the request transaction |
| Background jobs registered, idempotent, tested | n/a | No new job. The interaction with `reconcile_payments` is tested |
| Unit + PG integration + API error/IDOR + a concurrency test per known race | Met | Races don't rely on a barrier alone: each racer is queued behind an externally held `orders` lock (`wait_for_lock_waiters`), which proves the overlap; the unlocked index race uses `meet_or_fail`. No `caplog` assertions. No timing claims |
| Each "Done when" covered; ruff, mypy, pytest green in CI | Met | All green locally and on CI for `c10f80e`. On the fix branch, "No route sets `order.status`" has its own static test (A-06) and the planner flake is fixed (A-01) |
| Docs and OpenAPI updated; Status Done | Met | `docs/fulfillment.md`, ADR-040, `api-endpoints.md` match the code (routes, bodies, limits, reasons). `openapi.json` is identical to `app.openapi()`. The plan table says Done |

## 6. Findings

| ID | Sev | Location | What is wrong | Impact | Fix (not applied) | Slice |
|---|---|---|---|---|---|---|
| A-01 | Minor | `tests/integration/fulfillment/test_admin_order_queue_api.py:181-202` | The `ix_orders_cash_due` EXPLAIN assertion depends on the planner. With `enable_seqscan = off` alone, Postgres may pick a bitmap scan on `ix_orders_status_placed` plus a sort. **Reproduced in CI:** run 39933621938, the VS-029 merge on `main`, failed on exactly this, after the branch runs had passed. 1 of the 12 failing CI runs since 2026-10-23 | `main` went red at the merge; the next unlucky stats sample will flake a PR or `main` again | Also `SET LOCAL enable_bitmapscan = off` and `enable_sort = off`, so only an ordered scan on a matching index qualifies. Or assert on a fixed, analysed seed in a fresh table | VS-029 (tests) |
| A-02 | Minor | `admin_orders.py:222, 260`; `admin_cash_blocks.py:151, 197` | The handover (60/h), note (120/h) and cash-block search and clear (60/h) limits have no test. M28, M29 and M30 each leave everything green | Deleting one `Depends(_limit…)` would go unnoticed; the handover is a money write. Probe P2 shows all three work today | Seed the Redis counter at the limit, as `test_the_admin_cancel_shares_the_transition_rate_limit` does, and assert `429 RATE_LIMITED` and no change, for each route | VS-029 (tests) |
| A-03 | Minor | `orders.py:432-433` (ADR-040 d5) | Nothing checks that `completed_at` keeps its first value. M13 (overwrite it on every completion) survives; every test asserts only `completed_at is not None` (search of `tests/`) | A real path re-completes an order: a refund moves it to `partially_refunded`, then the refund fails or is voided and the status derives `completed` again (ADR-042). A regression would silently move analytics' completion date | Integration test: complete, refund, void the refund, assert `completed_at` unchanged | VS-029 / VS-030 (tests) |
| A-04 | Minor | `cash_payments.py:17-18` | The `uq_payments_one_live` → `already_recorded` mapping is untested. M09 survives because Postgres reports `uq_payments_one_cash` first (created first), so tests only ever see that name | ADR-040 d6 says which name is reported depends on index order. After a reindex or an index rebuilt in another order, a regression here would turn a second handover into a 500 | In a rolled-back transaction, drop `uq_payments_one_cash`, insert twice, expect `CashAlreadyRecordedError` | VS-029 (tests) |
| A-05 | Nit | `public.py:520` | The handover's `typed_currency != order.currency` branch is unreachable today: the body accepts only `"USD"` and every order is USD. M06 survives | A backstop with no test; it only matters once a second currency exists | Unit test `check_cash_handover` with a non-USD `LockedOrder` | VS-029 (tests) |
| A-06 | Minor | `public.py:258-283`; `orders.py:430` | "No route sets `order.status` directly" (Done when) has no automated guard. Search of `tests/` finds no static check on `set_order_status` or other writes to `orders.status`. The cash-payment rule and the line-writer rules do have one | A future direct `update(orders).values(status=…)` would pass CI | Add a static test like `test_order_item_writers.py`: `set_order_status` is called only from `recompute_order_status`, and no other `update(OrderModel)` sets `status` | VS-029 (tests) |
| A-07 | Nit | `record_cash_handover.py`; `transition_line.py` | BR-040 (the kill switch never blocks a cash handover) has no test. The code has no gate, which is correct (probe P1: handover and transition both 200 with `accepting_orders = false`) | A later "shop closed" gate added too broadly would block collecting cash for existing orders | Add P1 to `test_cash_handover_api.py` | VS-029 (tests) |
| A-08 | Nit | `admin_cash_blocks.py:180, 223`; `ordering/domain/admin_orders.py:105` | Naming drift from the glossary's "Cash Payment Block": audit `entity_type` is `cash_block` for search but `cash_payment_block` for clear, actions are `cash_block.*`, the domain class is `CashBlock` | Audit queries by entity type miss half the rows; CLAUDE.md asks for no synonyms | Use `cash_payment_block` for both entity types (old rows stay as they are) and rename the class when the code is next touched | VS-029 / VS-030 |

### Fix status (branch `fix/vs029-audit-findings`, 2026-11-02)

| ID | Status | Change |
|---|---|---|
| A-01 | Fixed | The plan test also turns off `bitmapscan`, `sort` and `incremental_sort`. Then only an index already in `(placed_at DESC, id DESC)` order can serve the page, which leaves the two VS-029 partial indexes. `ANALYZE` and `enable_seqscan = off` were already there and were not enough. A scratch probe with CI-shaped data (71 `in_progress` orders, 14 of them cash due) showed the old settings choosing a bitmap heap scan; the new ones choose `Index Scan using ix_orders_cash_due` |
| A-02 | Fixed | Three tests preset the per-administrator counter one below the limit: handover, note, and the cash-block budget shared by search and clear. The last allowed request succeeds; the next is `429 RATE_LIMITED` and changes nothing. Kills M28, M29, M30, M48 |
| A-03 | Fixed | `test_an_order_completed_again_keeps_its_first_completed_at`: complete by transitions, refund 400 (`partially_refunded`), void the refund (`completed` again), `completed_at` unchanged. Kills M13 |
| A-04 | Fixed | `test_a_second_cash_payment_reported_by_the_live_index_is_already_recorded`: `DROP INDEX uq_payments_one_cash` inside a rolled-back transaction, then a second insert maps `uq_payments_one_live` to `CashAlreadyRecordedError`; the index is back afterwards. Kills M09 |
| A-05 | Not changed (owner) | The currency comparison stays as defensive code for a future second currency. It is unreachable while the request accepts only `"USD"` and every order is USD, so it has no test and M06 survives by design |
| A-06 | Fixed | `tests/unit/ordering/test_order_status_writer.py`: an AST scan finds every `update(OrderModel)` that sets `status` (and raw `UPDATE orders SET … status`); only `SqlOrderStore.set_order_status` may, and only `recompute_order_status` calls it. A third test checks the scan itself. Kills M47 |
| A-07 | Fixed | `test_closing_the_shop_never_blocks_a_handover_or_a_transition`: with `accepting_orders = false`, the handover and a transition both succeed |
| A-08 | Fixed | Audit actions `cash_payment_block.searched` and `cash_payment_block.cleared`, entity type `cash_payment_block` for both (no production data exists yet). Updated: the router, three tests, ADR-042 d15, `fulfillment.md`, `api-endpoints.md`, the slice plan, the regenerated `openapi.json` (the search route's description). The domain class `CashBlock` keeps its name, outside this PR's scope |

Also checked, no issue found:
- **Rollback.** A refused handover rolls back fully. The 409s and 422s are raised before any write; a late `move_line` miss raises inside the request transaction, which `session.begin()` rolls back. The tests assert zero side effects.
- **Amount trust.** The payment amount is `due`, computed under the lock; the typed value is compared, never stored.
- **Handover states.** A `returned` line blocks the handover (probe P3).
- **Leaks.** No phone or phone hash in a cash-block response, a notice payload or an audit row.
- **Queue paging.** Keyset over `(placed_at, id)`; a bad cursor or `limit=101` is a 422.
- **Re-ship notice.** `returned → shipped` re-sends "shipped". That is VS-031's documented decision (ADR-043 d8), which closes the ADR-040 consequence.

## 7. Open questions

- **Q-1 (decided 2026-11-02, ADR-040 d12): no audit on admin order reads.** The writes stay audited. Original question: The admin order queue and detail return the recipient's name, phone, address and email, but are not audited. The admin user, contact-message and custom-request reads are audited (`user.viewed`, `contact_message.viewed`, `custom_request.viewed`, BUG-39). SEC-27 ("comprehensive audit logging") does not say which reads count, and `api-endpoints.md` asks for audit only on those three. Should admin order reads be audited too? I have not called this a defect.
- **Q-2 (decided 2026-11-02, `BACKEND-RESPONSE.md` P1-11): a handover answering `already_recorded` is shown as done, then the order is reloaded.** Original question: The handover takes no `Idempotency-Key`. If the response is lost, a retry answers `409 already_recorded`, and the client cannot tell whether its own call succeeded without reloading the order. The SRS requires idempotency keys only on checkout and refunds, so this matches the spec. Should the admin client treat `already_recorded` as "reload and show", and should the handoff docs say so?
- **Q-3 (decided 2026-11-02, ADR-040 d13): no partial-shipment notice in V1; the order page shows each line's status.** Original question: Partial shipments are not announced (ADR-040 consequence): on a two-line order, the parcel with line A arrives without a "shipped" email until line B ships. SRS §8.3 does not settle partial shipments. This is accepted in the ADR; it is listed here only so it gets an owner decision before launch.

## 8. How the commands were run

- Local runs used the repo's `.venv` (Python 3.13) on Windows, with Docker Desktop and testcontainers (`postgres:16`, Redis). The repo's `.env` was never read; scratch runs loaded `.env.example` into the process environment, as CI does.
- Integration batch: `test_line_transition_api.py`, `test_cash_handover_api.py`, `test_admin_order_queue_api.py`, `test_stl_delivery_api.py` (fulfillment); `test_admin_cash_blocks_api.py`; `test_cash_payment_writer.py`; `test_vs011_admin_boundary.py`; `test_openapi_security.py`. Second batch: `tests/concurrency/test_admin_order_races.py`, `tests/e2e/test_vs029_admin_fulfillment.py`, `tests/smoke/test_vs029_smoke.py`. Output went to files with exit codes recorded, never piped. The full suite was not run locally; its result comes from CI run 41431194901.
- Migration cycle: `migcycle.py` in the session scratchpad started its own `postgres:16` container and ran `alembic upgrade head`, `downgrade 7a1c3e9b5d24`, `upgrade head` from this checkout, reading `pg_indexes` after each step. No dev or real database was touched.
- Mutations: `mutate.py` in the scratchpad applied one exact-string replacement at a time to a `git archive HEAD` copy (each anchor checked to match exactly once), ran its target tests with `-x` and `PYTHONPATH` pointing at the copy, and restored the file. During M43 Claude Code's low-memory reaper stopped the driver before its restore step. `orders.py` was left mutated in the scratch copy and was restored from `HEAD`; the copy's `src/` and `migrations/` were then checksummed equal to `HEAD`. M43 to M46 were not re-run.
- Probes P1 to P3 lived only in the scratch copy (`tests/integration/fulfillment/test_zz_audit_probes.py`).
- Fix branch: the touched suites (the five changed integration files, `test_cash_block_search_audit.py`, `test_admin_order_races.py`, `test_order_status_writer.py`) passed locally, 229 tests. A light mutation pass ran one mutation at a time with narrow targets: M43 to M48, plus M09, M13, M28, M29 and M30 against the new tests. Afterwards the scratch copy's mutated files were checked equal to the branch.
- CI history: `gh run list` / `gh run view --log-failed` over the 12 failing CI runs since 2026-10-23. Only run 39933621938 failed on the EXPLAIN test.
